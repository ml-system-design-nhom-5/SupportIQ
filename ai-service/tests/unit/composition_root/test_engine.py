from datetime import datetime, timezone
from types import SimpleNamespace


class Model:
    def predict(self, text):
        return {"intent": "track_order", "confidence": .96, "margin": .9,
                "score_kind": "uncalibrated_softmax", "top_k": [{"intent": "track_order", "probability": .96}, {"intent": "request_refund", "probability": .03}], "model_version": "test-model"}


class Retriever:
    eligible_versions = [SimpleNamespace(doc_id="policy-1", version="1", title="Shipping", content="Shipping evidence", metadata=SimpleNamespace(valid_from="2026-01-01T00:00:00Z", valid_to=None))]
    def retrieve(self, *args, **kwargs):
        return {"status": "success", "evidence": [{"document_id": "policy-1", "version": "1", "title": "Shipping", "excerpt": "Shipping evidence"}]}


class LLM:
    def generate(self, *args, **kwargs):
        return {"body": "Please check the shipping policy. [S1]", "input_snapshot": {"sources": [{"source_id": "S1", "source_type": "policy", "document_id": "policy-1", "version": "1", "excerpt": "Shipping evidence"}]}}


def engine(llm=None):
    from apps.ai_service.engine import Engine
    return Engine(Model(), Retriever(), llm or LLM(), {"release_id": "test-release"}, policy={"supported_12_intents": ["track_order", "request_refund"], "sensitive_action_intents": ["request_refund"], "default_confidence_threshold": .7, "default_margin_threshold": .1})


def request(intent_override=None):
    return {"message": "Where is [ORDER_ID_1]?", "as_of": datetime.now(timezone.utc).isoformat(), "order_context": {"order_status": "shipped"}, **({"intent_override": intent_override} if intent_override else {})}


def test_existing_policy_accepts_high_raw_scores_without_fabricating_calibration():
    result = engine().draft(request())
    assert result["status"] == "draft_ready"
    assert "low_confidence" not in result["reason_codes"]
    assert result["analysis"]["intent"]["score_kind"] == "uncalibrated_softmax"


def test_staff_override_produces_versioned_citations_and_no_automatic_send():
    result = engine().draft(request("track_order"))
    assert result["status"] == "draft_ready"
    assert result["draft"]["citations"][0]["document_id"] == "policy-1"
    assert result["draft"]["citations"][0]["version"] == "1"
    assert not {"reply", "sent_at"} & result.keys()


def test_sensitive_override_requires_manager_authority():
    result = engine().analyse(request("request_refund"))
    assert "requires_authority" in result["routing"]["reason_codes"]


def test_uncovered_policy_escalation_is_accepted_by_application_contract():
    from apps.backend.tickets.jobs import validate_analysis
    payload = {**request(), 'message': 'Explain the archived shipping policy.'}
    result = engine().analyse(payload)
    assert result['routing']['recommendation'] == 'escalate'
    assert 'insufficient_evidence' in result['routing']['reason_codes']
    assert validate_analysis(result) is result


def test_unknown_placeholder_blocks_draft():
    class UnsafeLLM(LLM):
        def generate(self, *args, **kwargs):
            result = super().generate(*args, **kwargs)
            result["body"] = "Hello [NAME_99]. [S1]"
            return result
    result = engine(UnsafeLLM()).draft(request("track_order"))
    assert result["status"] == "llm_unavailable"
    assert "llm_invalid_output" in result["reason_codes"]


def test_low_score_still_abstains_without_calling_llm():
    class LowModel(Model):
        def predict(self,text):
            return {**super().predict(text),'confidence':.2,'margin':.01}
    class ForbiddenLLM:
        def generate(self,*args,**kwargs):
            raise AssertionError('LLM must not be called')
    subject=engine(ForbiddenLLM());subject.model=LowModel()
    assert subject.draft(request())['status']=='abstained'


def test_conflicting_sources_abstains_with_warning():
    class ConflictRetriever(Retriever):
        def retrieve(self, *args, **kwargs):
            res = super().retrieve(*args, **kwargs)
            res["has_conflict"] = True
            return res
    subject = engine()
    subject.retriever = ConflictRetriever()
    result = subject.draft(request())
    assert result["status"] == "abstained"
    assert "conflicting_sources" in result["reason_codes"]
    assert any("conflicting" in w.lower() for w in result["analysis"]["warnings"])


def test_clarification_draft_sets_missing_information():
    class ClarifyingLLM(LLM):
        def generate(self, *args, **kwargs):
            res = super().generate(*args, **kwargs)
            res["is_clarification"] = True
            return res
    result = engine(ClarifyingLLM()).draft(request())
    assert result["status"] == "draft_ready"
    assert "missing_information" in result["reason_codes"]
    assert "clarification" in result["staff_note"].lower()


def test_high_entropy_triggers_ood_low_confidence():
    class FlatEntropyModel(Model):
        def predict(self, text):
            # Uniform probabilities across 4 classes -> maximum entropy
            return {
                "intent": "track_order",
                "confidence": 0.25,
                "margin": 0.0,
                "score_kind": "uncalibrated_softmax",
                "top_k": [
                    {"intent": "track_order", "probability": 0.25},
                    {"intent": "request_refund", "probability": 0.25},
                    {"intent": "cancel_order", "probability": 0.25},
                    {"intent": "human_agent", "probability": 0.25},
                ],
                "model_version": "test-model"
            }
    subject = engine()
    subject.model = FlatEntropyModel()
    analysis = subject.analyse(request())
    assert "low_confidence" in analysis["routing"]["reason_codes"]
    assert "out_of_scope_intent" in analysis["routing"]["reason_codes"]


def test_short_unsupported_commitment_blocks_draft_in_boundary():
    class ShortFactualLLM(LLM):
        def generate(self, *args, **kwargs):
            return {
                "body": "Refund amount is $50.",
                "input_snapshot": {"sources": [{"source_id": "S1", "source_type": "policy", "document_id": "policy-1", "version": "1", "excerpt": "Shipping evidence"}]}
            }
    result = engine(ShortFactualLLM()).draft(request())
    assert result["status"] == "llm_unavailable"
    assert "grounding_failed" in result["reason_codes"]


def test_polite_greeting_allowed_in_boundary():
    class GreetingLLM(LLM):
        def generate(self, *args, **kwargs):
            return {
                "body": "Hello [NAME_1],\n\nPlease check the shipping policy. [S1]",
                "input_snapshot": {"sources": [{"source_id": "S1", "source_type": "policy", "document_id": "policy-1", "version": "1", "excerpt": "Shipping evidence"}]}
            }
    result = engine(GreetingLLM()).draft({"message": "Hello [NAME_1], where is [ORDER_ID_1]?", "as_of": datetime.now(timezone.utc).isoformat(), "order_context": {"order_status": "shipped"}})
    assert result["status"] == "draft_ready"
    assert len(result["draft"]["segments"]) == 2
    assert result["draft"]["segments"][0]["citation_ids"] == []
    assert result["draft"]["segments"][1]["citation_ids"] == ["S1"]


def test_staff_override_provenance_in_boundary():
    result = engine().analyse(request("track_order"))
    intent = result["intent"]
    assert intent["source"] == "staff"
    assert intent["score_kind"] == "staff_choice"
    assert intent["model_mode"] == "override"
    assert intent["verified"] is False
    assert intent["probability"] == 1.0


def test_model_provenance_carried_through_analysis():
    class ProvenanceModel(Model):
        def predict(self, text):
            res = super().predict(text)
            res["model_mode"] = "trained"
            res["verified"] = True
            return res
    eng = engine()
    eng.model = ProvenanceModel()
    result = eng.analyse(request())
    assert result["intent"]["source"] == "model"
    assert result["intent"]["model_mode"] == "trained"
    assert result["intent"]["verified"] is True
