from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import torch
from fastapi.testclient import TestClient

from apps.ml_inference.app import (
    CALIBRATION_SCHEMA_VERSION,
    EXPECTED_46_LABELS,
    EXPECTED_MANIFEST,
    ModelContainer,
    app,
)


def _sorted_id2label() -> dict[int, str]:
    return {i: label for i, label in enumerate(sorted(EXPECTED_46_LABELS))}


def _build_ready_container(logits_tensor: torch.Tensor) -> ModelContainer:
    mc = ModelContainer()
    mc.device = torch.device("cpu")
    mc.id2label = _sorted_id2label()
    mc.verified_model_version = EXPECTED_MANIFEST["model_version"]
    mc.model_version = EXPECTED_MANIFEST["model_version"]
    mc.model_checksum = EXPECTED_MANIFEST["weights_sha256"]
    mc.tokenizer_checksum = EXPECTED_MANIFEST["tokenizer_sha256"]
    mc.model_mode = "trained"
    mc.verified = True
    mc._is_dev_fallback = False

    seen_tok_kwargs: list[dict] = []

    def fake_tokenizer(text, **kwargs):
        seen_tok_kwargs.append({"text": text, **kwargs})
        return {
            "input_ids": torch.ones((1, kwargs.get("max_length", 64)), dtype=torch.long),
            "attention_mask": torch.ones((1, kwargs.get("max_length", 64)), dtype=torch.long),
        }

    class TinyLogitModel:
        def __call__(self, **inputs):
            return SimpleNamespace(logits=logits_tensor.unsqueeze(0))

    mc.tokenizer = fake_tokenizer
    mc.tokenizer._seen_calls = seen_tok_kwargs  # type: ignore[attr-defined]
    mc.model = TinyLogitModel()
    return mc


def test_controlled_logits_parity_raw_and_calibrated_softmax():
    logits = torch.linspace(-2.5, 3.5, 46, dtype=torch.float32)
    mc = _build_ready_container(logits)

    raw = mc.predict("Where is my order?", calibrated=False)
    expected_raw = torch.softmax(logits, dim=-1).tolist()
    assert mc.tokenizer._seen_calls[0]["max_length"] == 64
    assert mc.tokenizer._seen_calls[0]["padding"] == "max_length"
    assert mc.tokenizer._seen_calls[0]["truncation"] is True
    assert raw["score_kind"] == "uncalibrated_softmax"
    assert raw["intent"] == mc.id2label[45]
    assert raw["confidence"] == pytest.approx(expected_raw[45], abs=1e-6)
    assert raw["margin"] == pytest.approx(expected_raw[45] - expected_raw[44], abs=1e-6)

    cal = mc.predict("Where is my order?", calibrated=True)
    expected_cal = torch.softmax(logits / 1.25, dim=-1).tolist()
    assert cal["score_kind"] == "calibrated_probability"
    assert cal["confidence"] == pytest.approx(expected_cal[45], abs=1e-6)
    assert cal["margin"] == pytest.approx(expected_cal[45] - expected_cal[44], abs=1e-6)


@pytest.mark.parametrize("bad_temp", [0.0, -1.0, -0.01, float("nan"), float("inf"), float("-inf"), True, False])
@pytest.mark.parametrize("calibrated", [False, True])
def test_invalid_temperature_fails_closed_in_container_and_api(bad_temp, calibrated):
    logits = torch.linspace(-2.0, 3.0, 46, dtype=torch.float32)
    mc = _build_ready_container(logits)

    with pytest.raises(ValueError, match="temperature"):
        mc.predict("Where is my order?", temperature=bad_temp, calibrated=calibrated)


def test_predict_endpoint_rejects_invalid_temperature_with_4xx():
    logits = torch.linspace(-2.0, 3.0, 46, dtype=torch.float32)
    mc = _build_ready_container(logits)
    client = TestClient(app)
    with patch("apps.ml_inference.app.container", mc):
        res = client.post(
            "/predict",
            json={"text": "Where is my order?", "temperature": 0.0, "calibrated": True},
        )
    assert res.status_code in (400, 422)


def test_unit_temperature_with_calibrated_false_reports_uncalibrated_softmax():
    logits = torch.linspace(-2.0, 3.0, 46, dtype=torch.float32)
    mc = _build_ready_container(logits)

    res = mc.predict("Where is my order?", temperature=1.0, calibrated=False)
    assert res["score_kind"] == "uncalibrated_softmax"


def test_non_finite_or_wrong_shape_logits_fail_closed():
    bad_logits = torch.zeros(46, dtype=torch.float32)
    bad_logits[0] = float("nan")
    mc_nan = _build_ready_container(bad_logits)
    with pytest.raises(ValueError, match="finite"):
        mc_nan.predict("Where is my order?")

    mc_wrong_shape = _build_ready_container(torch.zeros(12, dtype=torch.float32))
    with pytest.raises(ValueError, match="46"):
        mc_wrong_shape.predict("Where is my order?")


def _write_candidate_dir(
    tmp_path: Path,
    *,
    num_labels: int = 46,
    hidden_size: int = 768,
) -> tuple[Path, dict[str, str]]:
    cdir = tmp_path / "candidate"
    cdir.mkdir(exist_ok=True)
    weights_bytes = b"candidate-weights-bytes"
    tok_bytes = b'{"model": "stub"}'
    cfg_obj = {
        "num_labels": num_labels,
        "hidden_size": hidden_size,
        "id2label": {str(i): lbl for i, lbl in enumerate(sorted(EXPECTED_46_LABELS))},
    }
    cfg_bytes = json.dumps(cfg_obj, sort_keys=True).encode("utf-8")
    (cdir / "model.safetensors").write_bytes(weights_bytes)
    (cdir / "tokenizer.json").write_bytes(tok_bytes)
    (cdir / "config.json").write_bytes(cfg_bytes)
    hashes = {
        "model.safetensors": hashlib.sha256(weights_bytes).hexdigest().lower(),
        "tokenizer.json": hashlib.sha256(tok_bytes).hexdigest().lower(),
        "config.json": hashlib.sha256(cfg_bytes).hexdigest().lower(),
    }
    return cdir, hashes


def _fake_model_and_tokenizer(logits: torch.Tensor, cls_vec: torch.Tensor | None = None):
    def fake_tok(text, **kwargs):
        return {
            "input_ids": torch.ones((1, kwargs.get("max_length", 64)), dtype=torch.long),
            "attention_mask": torch.ones((1, kwargs.get("max_length", 64)), dtype=torch.long),
        }

    class FakeModel:
        config = SimpleNamespace(num_labels=46, hidden_size=768)

        def eval(self):
            return self

        def to(self, _device):
            return self

        def __call__(self, **inputs):
            if inputs.get("output_hidden_states"):
                assert cls_vec is not None
                hidden = torch.zeros((1, 4, 768), dtype=torch.float32)
                hidden[0, 0, :] = cls_vec
                return SimpleNamespace(logits=logits.unsqueeze(0), hidden_states=(hidden,))
            return SimpleNamespace(logits=logits.unsqueeze(0))

    return fake_tok, FakeModel()


def test_wrong_num_labels_in_config_fails_closed(tmp_path: Path):
    cdir, _ = _write_candidate_dir(tmp_path, num_labels=34)
    # Without explicit calibration manifest, pinned hashes fail too; also check with valid manifest
    hashes = {
        name: hashlib.sha256((cdir / name).read_bytes()).hexdigest().lower()
        for name in ("model.safetensors", "tokenizer.json", "config.json")
    }
    cal_path = cdir / "calibration_manifest.json"
    cal_path.write_text(
        json.dumps(
            {
                "schema_version": CALIBRATION_SCHEMA_VERSION,
                "model_version": "cand-34",
                "artifact_hashes": hashes,
                "temperature": 1.25,
            }
        ),
        encoding="utf-8",
    )
    mc = ModelContainer()
    mc.load(cdir, calibration_manifest_path=cal_path)
    assert mc.is_ready() is False
    assert mc.is_trained_ready() is False
    assert mc.verified is False


def test_unpinned_directory_without_explicit_calibration_manifest_fails_closed(tmp_path: Path):
    cdir, hashes = _write_candidate_dir(tmp_path)
    # Even if a calibration_manifest.json sits in candidate dir, default serving load() must NOT silently trust unpinned weights.
    (cdir / "calibration_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": CALIBRATION_SCHEMA_VERSION,
                "model_version": "cand-v1",
                "artifact_hashes": hashes,
                "temperature": 1.5,
            }
        ),
        encoding="utf-8",
    )
    mc = ModelContainer()
    mc.load(cdir)
    assert mc.is_ready() is False
    assert mc.is_trained_ready() is False
    assert mc.calibration_schema_version is None


def test_explicit_selective_calibration_manifest_logit_geometry_separates_raw_cal_and_rejector(tmp_path: Path):
    cdir, hashes = _write_candidate_dir(tmp_path)
    cal_path = cdir / "calibration_manifest.json"
    # Weight on logit_max (index 6 in logit_geometry_v1): positive logit_max => accepted, negative => rejected.
    manifest = {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "model_version": "cand-sel-v1",
        "artifact_hashes": hashes,
        "temperature": 2.0,
        "calibrated": True,
        "selective_rejector": {
            "feature_spec": "logit_geometry_v1",
            "scaler_mean": [0.0] * 8,
            "scaler_scale": [1.0] * 8,
            "weights": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
            "bias": 0.0,
            "threshold": 0.5,
        },
    }
    cal_path.write_text(json.dumps(manifest), encoding="utf-8")

    # High peak logit (max_logit = +4.0 => sigmoid(+4) > 0.5 => accepted)
    high_logits = torch.full((46,), -1.0, dtype=torch.float32)
    high_logits[10] = 4.0
    tok, mdl = _fake_model_and_tokenizer(high_logits)

    with patch("apps.ml_inference.app.AutoTokenizer.from_pretrained", return_value=tok), patch(
        "apps.ml_inference.app.AutoModelForSequenceClassification.from_pretrained", return_value=mdl
    ):
        mc = ModelContainer()
        mc.load(cdir, calibration_manifest_path=cal_path)
        assert mc.is_ready() is True
        assert mc.is_trained_ready() is True
        assert mc.calibration_schema_version == CALIBRATION_SCHEMA_VERSION
        assert mc.calibration_temperature == pytest.approx(2.0)

        out = mc.predict("Track my package please")
        exp_raw = sorted(torch.softmax(high_logits, dim=-1).tolist(), reverse=True)
        exp_cal = sorted(torch.softmax(high_logits / 2.0, dim=-1).tolist(), reverse=True)
        assert out["score_kind"] == "calibrated_probability"
        assert out["calibration_temperature"] == pytest.approx(2.0)
        assert out["confidence"] == pytest.approx(exp_cal[0], abs=1e-6)
        assert out["margin"] == pytest.approx(exp_cal[0] - exp_cal[1], abs=1e-6)
        assert out["raw_score_kind"] == "uncalibrated_softmax"
        assert out["raw_confidence"] == pytest.approx(exp_raw[0], abs=1e-6)
        assert out["raw_margin"] == pytest.approx(exp_raw[0] - exp_raw[1], abs=1e-6)
        assert out["selective_accepted"] is True
        assert out["rejected_by_experimental_adapter"] is False
        assert out["selective_threshold"] == pytest.approx(0.5)
        assert out["selective_score"] == pytest.approx(1.0 / (1.0 + math.exp(-4.0)), abs=1e-6)

        # Negative peak logit (max_logit = -3.0 => rejected without mutating calibrated intent probabilities)
        low_logits = torch.full((46,), -6.0, dtype=torch.float32)
        low_logits[10] = -3.0
        mc.model = _fake_model_and_tokenizer(low_logits)[1]
        rej_out = mc.predict("What is the weather in Tokyo?")
        exp_rej_cal = sorted(torch.softmax(low_logits / 2.0, dim=-1).tolist(), reverse=True)
        assert rej_out["intent"] == mc.id2label[10]
        assert rej_out["confidence"] == pytest.approx(exp_rej_cal[0], abs=1e-6)
        assert rej_out["selective_accepted"] is False
        assert rej_out["rejected_by_experimental_adapter"] is True
        assert rej_out["selective_score"] == pytest.approx(1.0 / (1.0 + math.exp(3.0)), abs=1e-6)


def test_explicit_selective_calibration_manifest_cls_l2_rejector(tmp_path: Path):
    cdir, hashes = _write_candidate_dir(tmp_path)
    cal_path = cdir / "calibration_manifest.json"
    weights = [0.0] * 776
    weights[0] = 5.0  # First CLS L2 coordinate
    cal_path.write_text(
        json.dumps(
            {
                "schema_version": CALIBRATION_SCHEMA_VERSION,
                "model_version": "cand-cls-v1",
                "artifact_hashes": hashes,
                "temperature": 1.5,
                "selective_rejector": {
                    "feature_spec": "cls_l2_plus_logit_geometry_v1",
                    "scaler_mean": [0.0] * 776,
                    "scaler_scale": [1.0] * 776,
                    "weights": weights,
                    "bias": 0.0,
                    "threshold": 0.5,
                },
            }
        ),
        encoding="utf-8",
    )
    logits = torch.linspace(-1.0, 2.0, 46, dtype=torch.float32)
    cls_vec = torch.zeros(768, dtype=torch.float32)
    cls_vec[0] = -3.0  # L2 normalized => [-1.0, 0, ...] => z = -5.0 => rejected
    tok, mdl = _fake_model_and_tokenizer(logits, cls_vec=cls_vec)
    with patch("apps.ml_inference.app.AutoTokenizer.from_pretrained", return_value=tok), patch(
        "apps.ml_inference.app.AutoModelForSequenceClassification.from_pretrained", return_value=mdl
    ):
        mc = ModelContainer()
        mc.load(cdir, calibration_manifest_path=cal_path)
        assert mc.is_trained_ready() is True
        out = mc.predict("Some OOD message")
        assert out["selective_accepted"] is False
        assert out["selective_score"] == pytest.approx(1.0 / (1.0 + math.exp(5.0)), abs=1e-6)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda m: m.update({"schema_version": "unknown.v0"}),
        lambda m: m.update({"model_version": ""}),
        lambda m: m.update({"temperature": 0.75}),
        lambda m: m.update({"temperature": True}),
        lambda m: m.update({"calibrated": "yes"}),
        lambda m: m["artifact_hashes"].update({"config.json": "0" * 64}),
        lambda m: m["selective_rejector"].update({"feature_spec": "unknown_spec"}),
        lambda m: m["selective_rejector"].update({"weights": [0.0] * 7}),
        lambda m: m["selective_rejector"]["scaler_scale"].__setitem__(0, 0.0),
        lambda m: m["selective_rejector"].update({"threshold": 1.2}),
        lambda m: m["selective_rejector"].update({"reject_when": "above"}),
        lambda m: m["selective_rejector"].update({"type": "xgb_v1"}),
        lambda m: m["selective_rejector"].update({"feature_dim": 776}),
        lambda m: m["selective_rejector"].update({"enabled": "true"}),
        lambda m: m.update({"min_temperature": 1.8, "temperature": 1.5}),
    ],
)
def test_invalid_calibration_manifest_or_rejector_fails_closed(tmp_path: Path, monkeypatch, mutator):
    monkeypatch.setenv("SUPPORTIQ_DEV_FALLBACK_MODEL", "true")
    cdir, hashes = _write_candidate_dir(tmp_path)
    manifest = {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "model_version": "cand-bad",
        "artifact_hashes": dict(hashes),
        "temperature": 1.5,
        "selective_rejector": {
            "feature_spec": "logit_geometry_v1",
            "scaler_mean": [0.0] * 8,
            "scaler_scale": [1.0] * 8,
            "weights": [0.1] * 8,
            "bias": 0.0,
            "threshold": 0.5,
        },
    }
    mutator(manifest)
    cal_path = cdir / "calibration_manifest.json"
    cal_path.write_text(json.dumps(manifest), encoding="utf-8")

    mc = ModelContainer()
    mc.load(cdir, calibration_manifest_path=cal_path)
    assert mc.is_ready() is False
    assert mc.is_trained_ready() is False
    assert mc.verified is False
    assert mc._is_dev_fallback is False


def _build_engine_fixture(prediction_payload: dict, *, evidence: list | None = None, llm_body: str = "Items can be returned within 30 days [S1]."):
    from apps.ai_service.engine import Engine

    policy_path = Path("apps/core_backend/config/policies/intent_policy.v2.json")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))

    stub_model = MagicMock()
    stub_model.predict.return_value = prediction_payload

    stub_retriever = MagicMock()
    stub_retriever.eligible_versions = []
    stub_retriever.relevance_threshold = 0.55
    default_evidence = [
        {
            "document_id": "POL-RET-001",
            "version": "1",
            "title": "Return Policy",
            "excerpt": "Items can be returned within 30 days.",
            "score": 0.92,
        }
    ]
    stub_retriever.retrieve.return_value = {
        "evidence": default_evidence if evidence is None else evidence,
        "has_conflict": False,
        "reason_codes": [],
    }

    stub_llm = MagicMock()
    stub_llm.generate.return_value = {
        "body": llm_body,
        "input_snapshot": {
            "sources": [
                {
                    "source_id": "S1",
                    "source_type": "policy",
                    "document_id": "POL-RET-001",
                    "version": "1",
                    "excerpt": "Items can be returned within 30 days.",
                }
            ]
        },
        "latency_seconds": 0.01,
        "usage": {},
    }
    engine = Engine(stub_model, stub_retriever, stub_llm, {"release_id": "rel-test", "model_version": "cand"}, policy)
    return engine, stub_llm


def test_engine_enforces_selective_rejection_abstains_without_calling_llm():
    """Explicit selective_accepted=False / rejector veto must abstain and never invoke LLM."""
    from apps.backend.tickets.jobs import validate_analysis

    rejected_pred = {
        "intent": "return_policy",
        "confidence": 0.96,
        "margin": 0.90,
        "top_k": [
            {"intent": "return_policy", "probability": 0.96},
            {"intent": "refund_policy", "probability": 0.06},
        ],
        "score_kind": "calibrated_probability",
        "model_mode": "trained",
        "verified": True,
        "selective_accepted": False,
        "rejected_by_experimental_adapter": True,
        "selective_score": 0.12,
        "selective_threshold": 0.50,
    }
    engine, stub_llm = _build_engine_fixture(rejected_pred)
    req = {"message": "How do I return a jacket?", "as_of": "2026-11-13T00:00:00Z"}
    analysis = engine.analyse(req)
    assert analysis["routing"]["recommendation"] == "abstain"
    assert "low_confidence" in analysis["routing"]["reason_codes"]
    assert "out_of_scope_intent" in analysis["routing"]["reason_codes"]
    assert analysis["intent"]["probability"] == pytest.approx(0.96)
    assert analysis["intent"]["confidence_band"] == "low"
    assert analysis["routing"]["selective_accepted"] is False
    assert analysis["routing"]["rejected_by_experimental_adapter"] is True
    assert validate_analysis(analysis) == analysis

    draft_res = engine.draft(req)
    assert draft_res["status"] == "abstained"
    stub_llm.generate.assert_not_called()


def test_engine_preserves_baseline_when_rejector_fields_absent_and_drafts_when_accepted():
    from apps.backend.tickets.jobs import validate_analysis

    base_pred = {
        "intent": "return_policy",
        "confidence": 0.96,
        "margin": 0.90,
        "top_k": [
            {"intent": "return_policy", "probability": 0.96},
            {"intent": "refund_policy", "probability": 0.06},
        ],
        "score_kind": "uncalibrated_softmax",
        "model_mode": "trained",
        "verified": True,
    }
    engine_absent, llm_absent = _build_engine_fixture(base_pred)
    req = {"message": "How do I return a jacket?", "as_of": "2026-11-13T00:00:00Z"}
    absent_analysis = engine_absent.analyse(req)
    assert absent_analysis["routing"]["recommendation"] == "draft"
    assert "selective_accepted" not in absent_analysis["routing"]
    assert validate_analysis(absent_analysis) == absent_analysis
    absent_draft = engine_absent.draft(req)
    assert absent_draft["status"] == "draft_ready"
    llm_absent.generate.assert_called_once()

    accepted_pred = {
        **base_pred,
        "score_kind": "calibrated_probability",
        "selective_accepted": True,
        "rejected_by_experimental_adapter": False,
        "selective_score": 0.91,
        "selective_threshold": 0.50,
    }
    engine_acc, llm_acc = _build_engine_fixture(accepted_pred)
    acc_analysis = engine_acc.analyse(req)
    assert acc_analysis["routing"]["recommendation"] == "draft"
    assert acc_analysis["routing"]["selective_accepted"] is True
    acc_draft = engine_acc.draft(req)
    assert acc_draft["status"] == "draft_ready"
    llm_acc.generate.assert_called_once()


def test_engine_selective_acceptance_never_bypasses_existing_gates():
    base_accepted = {
        "intent": "return_policy",
        "confidence": 0.96,
        "margin": 0.90,
        "top_k": [
            {"intent": "return_policy", "probability": 0.96},
            {"intent": "refund_policy", "probability": 0.06},
        ],
        "score_kind": "calibrated_probability",
        "model_mode": "trained",
        "verified": True,
        "selective_accepted": True,
        "rejected_by_experimental_adapter": False,
        "selective_score": 0.95,
        "selective_threshold": 0.50,
    }
    req = {"message": "How do I return a jacket?", "as_of": "2026-11-13T00:00:00Z"}

    # 1. Low confidence gate still blocks
    low_conf_engine, low_llm = _build_engine_fixture({**base_accepted, "confidence": 0.30, "margin": 0.02})
    assert low_conf_engine.analyse(req)["routing"]["recommendation"] == "abstain"
    assert low_conf_engine.draft(req)["status"] == "abstained"
    low_llm.generate.assert_not_called()

    # 2. Recognized escalated intent outside product scope escalates, while unmapped OOD abstains
    oos_engine, oos_llm = _build_engine_fixture({**base_accepted, "intent": "use_app"})
    oos_analysis = oos_engine.analyse(req)
    assert oos_analysis["routing"]["recommendation"] == "escalate"
    assert "out_of_scope_intent" in oos_analysis["routing"]["reason_codes"]
    oos_llm.generate.assert_not_called()

    unmapped_engine, unmapped_llm = _build_engine_fixture({**base_accepted, "intent": "unmapped_external_topic"})
    unmapped_analysis = unmapped_engine.analyse(req)
    assert unmapped_analysis["routing"]["recommendation"] == "abstain"
    assert "out_of_scope_intent" in unmapped_analysis["routing"]["reason_codes"]
    unmapped_llm.generate.assert_not_called()

    # 3. Missing retrieval evidence gate still blocks
    no_doc_engine, no_doc_llm = _build_engine_fixture(base_accepted, evidence=[])
    assert no_doc_engine.analyse(req)["routing"]["recommendation"] == "abstain"
    no_doc_llm.generate.assert_not_called()

    # 4. Authority / escalation gate still escalates (and even if rejector rejected too)
    auth_req = {"message": "I want a fraud policy exception right now.", "as_of": "2026-11-13T00:00:00Z"}
    auth_engine, auth_llm = _build_engine_fixture({**base_accepted, "selective_accepted": False, "rejected_by_experimental_adapter": True})
    auth_analysis = auth_engine.analyse(auth_req)
    assert auth_analysis["routing"]["recommendation"] == "escalate"
    assert "requires_authority" in auth_analysis["routing"]["reason_codes"]
    assert auth_engine.draft(auth_req)["status"] == "escalation_recommended"
    auth_llm.generate.assert_not_called()


def test_engine_preserves_validated_human_intent_override_and_sticky_authority():
    rejected_pred = {
        "intent": "use_app",
        "confidence": 0.42,
        "margin": 0.05,
        "top_k": [
            {"intent": "use_app", "probability": 0.42},
            {"intent": "return_policy", "probability": 0.37},
        ],
        "score_kind": "calibrated_probability",
        "model_mode": "trained",
        "verified": True,
        "selective_accepted": False,
        "rejected_by_experimental_adapter": True,
        "selective_score": 0.10,
        "selective_threshold": 0.50,
    }
    engine, stub_llm = _build_engine_fixture(rejected_pred)

    # Human staff override to supported intent on clean inquiry drafts via established override semantics
    ok_req = {
        "message": "How do I return a jacket?",
        "as_of": "2026-11-13T00:00:00Z",
        "intent_override": "return_policy",
    }
    ok_analysis = engine.analyse(ok_req)
    assert ok_analysis["intent"]["source"] == "staff"
    assert ok_analysis["intent"]["score_kind"] == "staff_choice"
    assert ok_analysis["routing"]["recommendation"] == "draft"
    assert engine.draft(ok_req)["status"] == "draft_ready"
    stub_llm.generate.assert_called_once()

    # Sticky authority still blocks drafting when customer message asks for exception even with staff override
    stub_llm.generate.reset_mock()
    exc_req = {
        "message": "Grant me a refund exception right now!",
        "as_of": "2026-11-13T00:00:00Z",
        "intent_override": "return_policy",
    }
    exc_analysis = engine.analyse(exc_req)
    assert exc_analysis["routing"]["recommendation"] == "escalate"
    assert "requires_authority" in exc_analysis["routing"]["reason_codes"]
    assert engine.draft(exc_req)["status"] == "escalation_recommended"
    stub_llm.generate.assert_not_called()


def test_predict_http_endpoint_retains_rejection_and_calibration_metadata(tmp_path: Path):
    cdir, hashes = _write_candidate_dir(tmp_path)
    cal_path = cdir / "calibration_manifest.json"
    cal_path.write_text(
        json.dumps(
            {
                "schema_version": CALIBRATION_SCHEMA_VERSION,
                "model_version": "cand-http-v1",
                "artifact_hashes": hashes,
                "temperature": 1.5,
                "calibrated": True,
                "selective_rejector": {
                    "type": "logistic_regression_v1",
                    "enabled": True,
                    "feature_spec": "logit_geometry_v1",
                    "feature_dim": 8,
                    "scaler_mean": [0.0] * 8,
                    "scaler_scale": [1.0] * 8,
                    "weights": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
                    "bias": 0.0,
                    "threshold": 0.5,
                },
            }
        ),
        encoding="utf-8",
    )
    low_logits = torch.full((46,), -6.0, dtype=torch.float32)
    low_logits[10] = -2.0
    tok, mdl = _fake_model_and_tokenizer(low_logits)
    with patch("apps.ml_inference.app.AutoTokenizer.from_pretrained", return_value=tok), patch(
        "apps.ml_inference.app.AutoModelForSequenceClassification.from_pretrained", return_value=mdl
    ):
        mc = ModelContainer()
        mc.load(cdir, calibration_manifest_path=cal_path)
        client = TestClient(app)
        with patch("apps.ml_inference.app.container", mc):
            res = client.post("/predict", json={"text": "Some OOD message", "request_id": "req-http-1"})
        assert res.status_code == 200
        body = res.json()
        assert body["calibration_schema_version"] == CALIBRATION_SCHEMA_VERSION
        assert body["calibration_temperature"] == pytest.approx(1.5)
        assert body["raw_score_kind"] == "uncalibrated_softmax"
        assert body["score_kind"] == "calibrated_probability"
        assert body["selective_accepted"] is False
        assert body["rejected_by_experimental_adapter"] is True
        assert body["selective_threshold"] == pytest.approx(0.5)
        assert body["selective_score"] == pytest.approx(1.0 / (1.0 + math.exp(2.0)), abs=1e-6)


def test_selective_rejector_shannon_entropy_nats_and_disabled_flag_parity(tmp_path: Path):
    cdir, hashes = _write_candidate_dir(tmp_path)
    cal_path = cdir / "calibration_manifest.json"
    # Weight = 1.0 strictly on cal_entropy (index 5 in logit_geometry_v1) to verify exact nats formula.
    cal_path.write_text(
        json.dumps(
            {
                "schema_version": CALIBRATION_SCHEMA_VERSION,
                "model_version": "cand-ent-v1",
                "artifact_hashes": hashes,
                "min_temperature": 1.0,
                "temperature": 1.5,
                "calibrated": True,
                "selective_rejector": {
                    "type": "logistic_regression_v1",
                    "enabled": True,
                    "feature_spec": "logit_geometry_v1",
                    "feature_dim": 8,
                    "scaler_mean": [0.0] * 8,
                    "scaler_scale": [1.0] * 8,
                    "weights": [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
                    "bias": 0.0,
                    "threshold": 0.5,
                },
            }
        ),
        encoding="utf-8",
    )
    logits = torch.linspace(-2.0, 2.0, 46, dtype=torch.float32)
    cal_probs = torch.softmax(logits / 1.5, dim=-1).tolist()
    expected_cal_entropy = -sum(p * math.log(max(p, 1e-12)) for p in cal_probs)
    expected_score = 1.0 / (1.0 + math.exp(-expected_cal_entropy))

    tok, mdl = _fake_model_and_tokenizer(logits)
    with patch("apps.ml_inference.app.AutoTokenizer.from_pretrained", return_value=tok), patch(
        "apps.ml_inference.app.AutoModelForSequenceClassification.from_pretrained", return_value=mdl
    ):
        mc = ModelContainer()
        mc.load(cdir, calibration_manifest_path=cal_path)
        assert mc.is_trained_ready() is True
        out = mc.predict("Some test")
        assert out["selective_score"] == pytest.approx(expected_score, abs=1e-6)
        assert out["selective_accepted"] is True

        # enabled=False disables rejector scoring while still validating manifest schema/hashes
        data = json.loads(cal_path.read_text(encoding="utf-8"))
        data["selective_rejector"]["enabled"] = False
        cal_path.write_text(json.dumps(data), encoding="utf-8")
        mc.load(cdir, calibration_manifest_path=cal_path)
        assert mc.is_trained_ready() is True
        out_disabled = mc.predict("Some test")
        assert out_disabled.get("selective_accepted") is None
        assert out_disabled.get("selective_score") is None


def test_nested_calibration_tokenization_label_space_manifest_and_fail_closed(tmp_path: Path):
    cdir, hashes = _write_candidate_dir(tmp_path)
    id2label_str = {str(i): lbl for i, lbl in enumerate(sorted(EXPECTED_46_LABELS))}
    base_manifest = {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "model_version": "supportiq-fit1_selective_head-test",
        "tokenization": {"max_length": 64, "padding": "max_length", "truncation": True},
        "label_space": {"num_labels": 46, "valid_46_label_bijection": True, "id2label": id2label_str},
        "calibration": {
            "method": "temperature_scaling",
            "temperature": 1.0857,
            "min_temperature": 1.0,
            "calibrated": True,
        },
        "selective_rejector": {
            "enabled": True,
            "type": "logistic_regression_v1",
            "feature_spec": "logit_geometry_v1",
            "feature_dim": 8,
            "scaler_mean": [0.0] * 8,
            "scaler_scale": [1.0] * 8,
            "weights": [0.0] * 8,
            "bias": 0.0,
            "threshold": 0.5,
            "positive_label": "in_scope",
        },
        "artifact_hashes": hashes,
    }
    cal_path = cdir / "calibration_manifest.json"
    cal_path.write_text(json.dumps(base_manifest), encoding="utf-8")

    logits = torch.linspace(-1.0, 2.0, 46, dtype=torch.float32)
    tok, mdl = _fake_model_and_tokenizer(logits)
    with patch("apps.ml_inference.app.AutoTokenizer.from_pretrained", return_value=tok), patch(
        "apps.ml_inference.app.AutoModelForSequenceClassification.from_pretrained", return_value=mdl
    ):
        mc = ModelContainer()
        mc.load(cdir, calibration_manifest_path=cal_path)
        assert mc.is_trained_ready() is True
        assert mc.calibration_temperature == pytest.approx(1.0857)
        res = mc.predict("Track my package")
        assert res["calibration_temperature"] == pytest.approx(1.0857)
        assert res["score_kind"] == "calibrated_probability"

        # Tampered tokenization / positive_label / label_space mismatch must fail closed
        for mutator in (
            lambda m: m["tokenization"].update({"max_length": 128}),
            lambda m: m["label_space"].update({"num_labels": 34}),
            lambda m: m["selective_rejector"].update({"positive_label": "out_of_scope"}),
            lambda m: m["label_space"]["id2label"].update({"0": "track_order", "43": "add_product"}),
        ):
            bad = json.loads(json.dumps(base_manifest))
            mutator(bad)
            cal_path.write_text(json.dumps(bad), encoding="utf-8")
            mc.load(cdir, calibration_manifest_path=cal_path)
            assert mc.is_ready() is False
            assert mc.is_trained_ready() is False
