"""Bounded Task A closure candidate training, calibration selection, locking & evaluation.

Predeclares at most TWO DistilBERT fits inside one shared <= 1800s budget, using ONLY
the existing `selective_calibration.v1` schema (`cls_l2_plus_logit_geometry_v1` 776d):
  1. Fit 1 (`fit1_closure_dual_head`): Clean positive 46-class cross-entropy fine-tuning
     on Bitext 46-label train replay (heavy other_34 retention) + fresh disjoint
     closure positive train data (SUPPORTED_12 + retail ESCALATED_34), paired with a
     `cls_l2_plus_logit_geometry_v1` binary rejector distinguishing single-intent
     draftable SUPPORTED_11 (`y=1`) from compound multi-intent / unsupported retail /
     ambiguous / off-domain / escalated (`y=0`), plus scalar temperature T >= 1.0.
  2. Fit 2 (`fit2_closure_selective_margin`): Clean positive 46-class cross-entropy
     paired with bounded selective probability-mass + logit-energy separation on
     negative/multi-intent train examples ONLY (never flattening positives), paired with
     `cls_l2_plus_logit_geometry_v1` + scalar temperature T >= 1.0.

Winner, temperature T >= 1.0, logistic C, and threshold tau are chosen strictly on
isolated calibration splits BEFORE locking artifacts and running ONE post-decision
evaluation across unseen holdout, Bitext test, AutoEval suites, and frozen regression
benchmarks (with known uninjected faults tracked separately).
"""

from __future__ import annotations

import datetime
import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

from apps.ai_service.engine import Engine
from apps.core_backend.intent.routing import (
    ESCALATED_34_INTENTS,
    IntentPrediction,
    RoutingContext,
    STANDARD_INTENTS_46,
    SUPPORTED_12_INTENTS,
    decide_route,
    load_policy_v2,
)
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from pipeline.evaluation.autoeval import metrics as M
from pipeline.evaluation.classifier_acceptance_gate import (
    KNOWN_UNINJECTED_ACCEPTANCE_IDS,
    KNOWN_UNINJECTED_FINAL_IDS,
    run_classifier_acceptance_gate,
)
from pipeline.preparation.utils import CORE_PRODUCT_INTENTS, compute_sha256
from pipeline.training.closure_domain_data import export_closure_datasets
from pipeline.training.train_domain_candidate import (
    MAX_TRAINING_BUDGET_SECONDS,
    VerifiedOriginalLineage,
    _OfflineSpyLLM,
    build_replay_and_domain_train_df,
    collect_compute_and_model_inventory,
    fit_temperature_on_calibration_logits,
    verify_original_46_label_lineage,
)
from pipeline.training.train_selective_candidate import (
    SUPPORTED_11_DRAFT_INTENTS,
    SelectiveCandidateAdapter,
    SelectiveRejectorParams,
    _SelectiveTrainDataset,
    _engine_analyse_selective,
    _git_head_sha,
    compute_selective_feature_matrix,
    score_rejector,
    write_calibration_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _train_closure_single_fit(
    *,
    fit_name: str,
    objective_mode: str,  # "clean_positive_ce" | "closure_selective_margin"
    base_model_dir: Path,
    output_dir: Path,
    train_texts: Sequence[str],
    train_labels: Sequence[int],
    train_is_negative: Sequence[int],
    seed: int,
    epochs: int = 3,
    batch_size: int = 32,
    lr: float = 3e-5,
) -> Dict[str, Any]:
    """Run one bounded DistilBERT fine-tuning fit."""
    t0 = time.perf_counter()
    torch.manual_seed(seed)
    np.random.seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    tokenizer = AutoTokenizer.from_pretrained(str(base_model_dir))
    model = AutoModelForSequenceClassification.from_pretrained(str(base_model_dir))
    model.to(device)

    enc = tokenizer(
        list(train_texts),
        max_length=64,
        padding="max_length",
        truncation=True,
        return_tensors="pt",
    )
    ds = _SelectiveTrainDataset(enc, train_labels, train_is_negative)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    total_steps = max(1, len(loader) * epochs)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=max(1, int(0.1 * total_steps)),
        num_training_steps=total_steps,
    )
    ce_loss = torch.nn.CrossEntropyLoss()
    sup11_indices = [STANDARD_INTENTS_46.index(i) for i in SUPPORTED_11_DRAFT_INTENTS]
    sup11_idx_t = torch.tensor(sup11_indices, dtype=torch.long, device=device)

    epoch_stats: List[Dict[str, Any]] = []
    for ep in range(1, epochs + 1):
        model.train()
        tot_loss = pos_loss_sum = neg_loss_sum = 0.0
        n_pos_batches = n_neg_batches = 0
        for batch in loader:
            optimizer.zero_grad()
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)
            is_neg = batch["is_negative"].to(device)

            logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
            pos_mask = is_neg == 0
            neg_mask = is_neg == 1

            loss = logits.sum() * 0.0
            if pos_mask.any():
                lp = ce_loss(logits[pos_mask], labels[pos_mask])
                loss = loss + lp
                pos_loss_sum += float(lp.item())
                n_pos_batches += 1

            if objective_mode == "closure_selective_margin" and neg_mask.any():
                neg_logits = logits[neg_mask]
                neg_probs = torch.softmax(neg_logits, dim=-1)
                sup11_probs = neg_probs[:, sup11_idx_t]
                sup11_max_prob = sup11_probs.max(dim=-1).values
                sup11_prob_mass = sup11_probs.sum(dim=-1)

                l_sup_max = torch.relu(sup11_max_prob - 0.18).pow(2).mean()
                l_sup_mass = torch.relu(sup11_prob_mass - 0.30).pow(2).mean()

                neg_energy = -torch.logsumexp(neg_logits, dim=-1)
                if pos_mask.any():
                    pos_energy_mean = (-torch.logsumexp(logits[pos_mask], dim=-1)).mean().detach()
                else:
                    pos_energy_mean = torch.tensor(-8.0, device=device)
                l_energy = torch.relu((pos_energy_mean + 2.5) - neg_energy).pow(2).mean()

                ln = 0.75 * l_sup_max + 0.45 * l_sup_mass + 0.30 * l_energy
                loss = loss + ln
                neg_loss_sum += float(ln.item())
                n_neg_batches += 1

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            tot_loss += float(loss.item())

        epoch_stats.append(
            {
                "epoch": ep,
                "mean_total_loss": round(tot_loss / max(1, len(loader)), 5),
                "mean_pos_ce_loss": round(pos_loss_sum / max(1, n_pos_batches), 5),
                "mean_neg_margin_loss": round(neg_loss_sum / max(1, n_neg_batches), 5) if n_neg_batches else 0.0,
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir), safe_serialization=True)
    tokenizer.save_pretrained(str(output_dir))
    elapsed = round(time.perf_counter() - t0, 2)
    return {
        "fit_name": fit_name,
        "objective_mode": objective_mode,
        "elapsed_seconds": elapsed,
        "epoch_stats": epoch_stats,
    }


def _build_closure_rejector_on_train_and_cal(
    *,
    fit_name: str,
    model_dir: Path,
    feature_spec: str,
    c_grid: Sequence[float],
    rej_train_texts: Sequence[str],
    rej_train_y: Sequence[int],  # 1 = draftable single-intent SUPPORTED_11, 0 = non-draftable
    cal_pos_df: pd.DataFrame,
    cal_neg_df: pd.DataFrame,
    bitext_cal_df: pd.DataFrame,
    policy_v2: Any,
) -> Tuple[float, SelectiveRejectorParams, Dict[str, Any]]:
    """Fit T>=1.0 on positive cal, fit 776d logistic rejector on train only, tune (C, tau) strictly on cal."""
    label2id = {lbl: idx for idx, lbl in enumerate(STANDARD_INTENTS_46)}
    adapter = SelectiveCandidateAdapter(
        fit_name,
        model_dir,
        fit_name,
        mode="raw_uncalibrated",
        validate_manifest=False,
    )

    # 1. Fit scalar T >= 1.0 on isolated positive calibration logits
    cal_pos_all_texts = cal_pos_df["instruction"].tolist() + bitext_cal_df["instruction"].tolist()
    cal_pos_all_y = np.array(
        [label2id[x] for x in cal_pos_df["intent"].tolist() + bitext_cal_df["intent"].tolist()],
        dtype=np.int64,
    )
    cal_pos_logits, cal_pos_cls = adapter.extract_logits_and_cls(cal_pos_all_texts, batch_size=64)
    temperature = fit_temperature_on_calibration_logits(
        cal_pos_logits,
        cal_pos_all_y,
        min_temperature=1.0,
        max_temperature=2.5,
    )

    # 2. Extract train features once
    trn_logits, trn_cls = adapter.extract_logits_and_cls(rej_train_texts, batch_size=64)
    trn_feats = compute_selective_feature_matrix(
        trn_logits,
        trn_cls,
        temperature=temperature,
        feature_spec=feature_spec,
    )
    scaler = StandardScaler()
    trn_scaled = scaler.fit_transform(trn_feats)
    y_train_arr = np.asarray(rej_train_y, dtype=np.int64)

    # 3. Extract cal features & calibrated softmax probs once
    cal_neg_texts = cal_neg_df["instruction"].tolist()
    cal_neg_logits, cal_neg_cls = adapter.extract_logits_and_cls(cal_neg_texts, batch_size=64)

    cal_dom_pos_intents = cal_pos_df["intent"].tolist()
    n_dom_cal = len(cal_dom_pos_intents)
    cal_dom_logits = cal_pos_logits[:n_dom_cal]
    cal_dom_cls = cal_pos_cls[:n_dom_cal]
    bitext_cal_logits = cal_pos_logits[n_dom_cal:]
    bitext_cal_cls = cal_pos_cls[n_dom_cal:]

    cal_dom_feats = compute_selective_feature_matrix(
        cal_dom_logits, cal_dom_cls, temperature=temperature, feature_spec=feature_spec
    )
    cal_neg_feats = compute_selective_feature_matrix(
        cal_neg_logits, cal_neg_cls, temperature=temperature, feature_spec=feature_spec
    )
    bitext_cal_feats = compute_selective_feature_matrix(
        bitext_cal_logits, bitext_cal_cls, temperature=temperature, feature_spec=feature_spec
    )

    def _softmax_np(lg: np.ndarray, temp: float) -> np.ndarray:
        z = lg / float(temp)
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / np.clip(e.sum(axis=1, keepdims=True), 1e-12, None)

    cal_dom_probs = _softmax_np(cal_dom_logits, temperature)
    cal_neg_probs = _softmax_np(cal_neg_logits, temperature)
    bitext_cal_probs = _softmax_np(bitext_cal_logits, temperature)

    def _route_row(probs_vec: np.ndarray) -> Tuple[str, float, float, str]:
        order = np.argsort(-probs_vec)
        top1, top2 = int(order[0]), int(order[1])
        pred_lbl = STANDARD_INTENTS_46[top1]
        conf = float(probs_vec[top1])
        margin = float(probs_vec[top1] - probs_vec[top2])
        dec = decide_route(
            IntentPrediction(intent=pred_lbl, confidence=conf, margin=margin, model_version=fit_name),
            RoutingContext(ticket_customer_id="cal", extracted_slots={}, is_personal_lookup=False),
            policy_v2,
        )
        return pred_lbl, conf, margin, dec.action

    cal_dom_routes = [_route_row(cal_dom_probs[i]) for i in range(n_dom_cal)]
    cal_neg_routes = [_route_row(cal_neg_probs[i]) for i in range(len(cal_neg_texts))]
    bitext_cal_intents = bitext_cal_df["intent"].tolist()
    bitext_cal_routes = [_route_row(bitext_cal_probs[i]) for i in range(len(bitext_cal_intents))]

    # Calibration positive 46-class & ECE stats (independent of C/tau)
    all_cal_pos_probs = np.vstack([cal_dom_probs, bitext_cal_probs])
    all_cal_pos_gold = cal_dom_pos_intents + bitext_cal_intents
    all_cal_preds = [STANDARD_INTENTS_46[int(np.argmax(all_cal_pos_probs[i]))] for i in range(len(all_cal_pos_gold))]
    all_cal_confs = [float(np.max(all_cal_pos_probs[i])) for i in range(len(all_cal_pos_gold))]
    all_cal_corrs = [p == g for p, g in zip(all_cal_preds, all_cal_pos_gold)]
    cal_ece, _ = M.expected_calibration_error(all_cal_confs, all_cal_corrs, n_bins=10)
    cal_brier = sum((c - (1.0 if y else 0.0)) ** 2 for c, y in zip(all_cal_confs, all_cal_corrs)) / max(1, len(all_cal_corrs))

    b_preds = [STANDARD_INTENTS_46[int(np.argmax(bitext_cal_probs[i]))] for i in range(len(bitext_cal_intents))]
    b34_idx = [i for i, y in enumerate(bitext_cal_intents) if y in ESCALATED_34_INTENTS]
    b34_acc = accuracy_score([bitext_cal_intents[i] for i in b34_idx], [b_preds[i] for i in b34_idx]) if b34_idx else 0.0
    b46_acc = accuracy_score(bitext_cal_intents, b_preds) if bitext_cal_intents else 0.0

    sup11_cal_n = max(1, sum(1 for y in cal_dom_pos_intents if y in SUPPORTED_11_DRAFT_INTENTS))
    dom_esc34_cal_idx = [i for i, y in enumerate(cal_dom_pos_intents) if y in ESCALATED_34_INTENTS]
    bit_esc34_cal_idx = [i for i, y in enumerate(bitext_cal_intents) if y in ESCALATED_34_INTENTS]
    esc34_cal_total = max(1, len(dom_esc34_cal_idx) + len(bit_esc34_cal_idx))
    neg_cal_n = max(1, len(cal_neg_texts))

    best_overall_score = -1e9
    best_params: Optional[SelectiveRejectorParams] = None
    best_stats: Dict[str, Any] = {}
    best_c = float(c_grid[0])

    # Tune (C, tau) strictly on isolated CALIBRATION splits
    for c_val in c_grid:
        clf = LogisticRegression(
            C=float(c_val),
            class_weight="balanced",
            max_iter=2500,
            random_state=42,
        )
        clf.fit(trn_scaled, y_train_arr)
        cand_rej = SelectiveRejectorParams(
            enabled=True,
            feature_spec=feature_spec,
            feature_dim=trn_feats.shape[1],
            scaler_mean=scaler.mean_.tolist(),
            scaler_scale=scaler.scale_.tolist(),
            weights=clf.coef_[0].tolist(),
            bias=float(clf.intercept_[0]),
            threshold=0.50,
        )
        cal_dom_p_in = score_rejector(cal_dom_feats, cand_rej)
        cal_neg_p_in = score_rejector(cal_neg_feats, cand_rej)
        bit_cal_p_in = score_rejector(bitext_cal_feats, cand_rej)

        for tau in np.linspace(0.25, 0.90, 66):
            tau_f = round(float(tau), 4)
            pos_corr_draft = pos_raw_draft = pos_human_esc = 0
            esc34_unsafe_draft = 0

            for i, gold_y in enumerate(cal_dom_pos_intents):
                pred_lbl, _, _, raw_act = cal_dom_routes[i]
                accepted = cal_dom_p_in[i] >= tau_f
                eff_act = "manual_fallback" if (raw_act == "retrieve_draft" and not accepted) else raw_act
                if gold_y in SUPPORTED_11_DRAFT_INTENTS and eff_act == "retrieve_draft":
                    pos_raw_draft += 1
                    if pred_lbl == gold_y:
                        pos_corr_draft += 1
                elif gold_y == "human_agent" and eff_act == "escalate" and pred_lbl == "human_agent":
                    pos_human_esc += 1
                elif gold_y in ESCALATED_34_INTENTS and eff_act == "retrieve_draft":
                    esc34_unsafe_draft += 1

            for i in bit_esc34_cal_idx:
                _, _, _, raw_act = bitext_cal_routes[i]
                accepted = bit_cal_p_in[i] >= tau_f
                eff_act = "manual_fallback" if (raw_act == "retrieve_draft" and not accepted) else raw_act
                if eff_act == "retrieve_draft":
                    esc34_unsafe_draft += 1

            neg_false_draft = neg_false_accept_any = 0
            for i in range(len(cal_neg_texts)):
                _, _, _, raw_act = cal_neg_routes[i]
                accepted = cal_neg_p_in[i] >= tau_f
                if accepted:
                    neg_false_accept_any += 1
                if raw_act == "retrieve_draft" and accepted:
                    neg_false_draft += 1

            tau_obj = (
                (pos_corr_draft / sup11_cal_n)
                - 3.0 * (neg_false_draft / neg_cal_n)
                - 3.0 * (esc34_unsafe_draft / esc34_cal_total)
                - 0.25 * (neg_false_accept_any / neg_cal_n)
                - 0.02 * abs(tau_f - 0.50)
            )
            if tau_obj > best_overall_score:
                best_overall_score = tau_obj
                best_c = float(c_val)
                best_params = SelectiveRejectorParams(
                    enabled=True,
                    feature_spec=feature_spec,
                    feature_dim=cand_rej.feature_dim,
                    scaler_mean=cand_rej.scaler_mean,
                    scaler_scale=cand_rej.scaler_scale,
                    weights=cand_rej.weights,
                    bias=cand_rej.bias,
                    threshold=tau_f,
                )
                best_stats = {
                    "rejector_c": float(c_val),
                    "threshold": tau_f,
                    "cal_dom_raw_draft": pos_raw_draft,
                    "cal_dom_correct_draft": pos_corr_draft,
                    "cal_dom_sup11_total": sup11_cal_n,
                    "cal_dom_human_agent_correct": pos_human_esc,
                    "cal_esc34_unsafe_draft": esc34_unsafe_draft,
                    "cal_esc34_total": esc34_cal_total,
                    "cal_neg_false_draft": neg_false_draft,
                    "cal_neg_false_accept_any": neg_false_accept_any,
                    "cal_neg_total": len(cal_neg_texts),
                    "tau_objective": round(float(tau_obj), 5),
                }

    assert best_params is not None
    sel_utility = (
        (best_stats["cal_dom_correct_draft"] / sup11_cal_n)
        + 0.5 * float(b46_acc)
        - 3.0 * (best_stats["cal_neg_false_draft"] / neg_cal_n)
        - 3.0 * (best_stats["cal_esc34_unsafe_draft"] / esc34_cal_total)
        - 0.25 * float(cal_ece)
        - 0.25 * float(cal_brier)
    )

    cal_summary = {
        "temperature": round(float(temperature), 4),
        "feature_spec": feature_spec,
        "selected_rejector_c": best_c,
        "rejector_threshold_selection": best_stats,
        "cal_bitext_46_n": len(bitext_cal_intents),
        "cal_bitext_46_accuracy": round(float(b46_acc), 4),
        "cal_bitext_34_n": len(b34_idx),
        "cal_bitext_34_accuracy": round(float(b34_acc), 4),
        "cal_pos_ece_10bin": round(float(cal_ece), 4),
        "cal_pos_brier": round(float(cal_brier), 4),
        "calibration_selection_utility": round(float(sel_utility), 5),
    }
    return temperature, best_params, cal_summary


def _evaluate_closure_adapter_mode(
    adapter: SelectiveCandidateAdapter,
    *,
    repo_root: Path,
    eval_pos_rows: Sequence[Dict[str, Any]],
    eval_neg_rows: Sequence[Dict[str, Any]],
    bitext_test_df: pd.DataFrame,
    policy_v2: Any,
    retriever: RetrievalAdapter,
) -> Dict[str, Any]:
    """Evaluate one locked adapter mode across closure holdout, Bitext test, noise, OOD, and regression."""
    engine = Engine(
        model=adapter,
        retriever=retriever,
        llm=_OfflineSpyLLM(),
        versions={"engine": "2.0.0", "policy": policy_v2.version, "model": adapter.version},
        policy=policy_v2.model_dump(),
    )

    # 1. Closure positive holdout (72 SUPPORTED_12 + 30 ESCALATED_34 = 102)
    pos_texts = [r["instruction"] for r in eval_pos_rows]
    pos_gold = [r["intent"] for r in eval_pos_rows]
    pos_preds = adapter.predict_batch(pos_texts, batch_size=64)
    pos_pred_labels = [p["intent"] for p in pos_preds]

    pos_sup11_n = pos_raw_draft = pos_corr_draft = pos_human_esc = 0
    pos_esc34_n = pos_esc34_unsafe_draft = 0
    pos_esc34_true: List[str] = []
    pos_esc34_pred: List[str] = []
    pos_sup12_true: List[str] = []
    pos_sup12_pred: List[str] = []
    for r, p in zip(eval_pos_rows, pos_preds):
        ans, _ = _engine_analyse_selective(engine, adapter, text=r["instruction"])
        rec = ans["routing"]["recommendation"]
        if r["intent"] in CORE_PRODUCT_INTENTS:
            pos_sup12_true.append(r["intent"])
            pos_sup12_pred.append(p["intent"])
        if r["intent"] in SUPPORTED_11_DRAFT_INTENTS:
            pos_sup11_n += 1
            if rec == "draft":
                pos_raw_draft += 1
                if p["intent"] == r["intent"]:
                    pos_corr_draft += 1
        elif r["intent"] == "human_agent":
            if rec == "escalate" and p["intent"] == "human_agent":
                pos_human_esc += 1
        elif r["intent"] in ESCALATED_34_INTENTS:
            pos_esc34_n += 1
            pos_esc34_true.append(r["intent"])
            pos_esc34_pred.append(p["intent"])
            if rec == "draft":
                pos_esc34_unsafe_draft += 1

    # 2. Closure negative holdout (33 rows across 4 categories)
    neg_false_draft = neg_false_accept_any = 0
    neg_false_draft_ids: List[str] = []
    neg_by_cat: Dict[str, Dict[str, int]] = {}
    for r in eval_neg_rows:
        cat = str(r.get("category", "unknown"))
        if cat not in neg_by_cat:
            neg_by_cat[cat] = {"n": 0, "false_draft": 0, "false_accept_any": 0}
        neg_by_cat[cat]["n"] += 1
        pred = adapter.predict(r["instruction"])
        ans, _ = _engine_analyse_selective(engine, adapter, text=r["instruction"])
        if pred["selective_accepted"]:
            neg_false_accept_any += 1
            neg_by_cat[cat]["false_accept_any"] += 1
        if ans["routing"]["recommendation"] == "draft":
            neg_false_draft += 1
            neg_by_cat[cat]["false_draft"] += 1
            neg_false_draft_ids.append(r["sample_id"])

    # 3. Verified 46-label Bitext test split
    test_preds = adapter.predict_batch(bitext_test_df["instruction"].tolist(), batch_size=128)
    test_pred_lbls = [p["intent"] for p in test_preds]
    test_gold = bitext_test_df["intent"].tolist()
    sup12_idx = [i for i, y in enumerate(test_gold) if y in CORE_PRODUCT_INTENTS]
    oth34_idx = [i for i, y in enumerate(test_gold) if y not in CORE_PRODUCT_INTENTS]
    oth34_unsafe_draft = 0
    for i in oth34_idx:
        p = test_preds[i]
        dec = decide_route(
            IntentPrediction(intent=p["intent"], confidence=p["confidence"], margin=p["margin"], model_version=adapter.version),
            RoutingContext(ticket_customer_id="bitext-test", extracted_slots={}, is_personal_lookup=False),
            policy_v2,
        )
        if dec.action == "retrieve_draft" and (adapter.mode != "calibrated_with_rejector" or p["selective_accepted"]):
            oth34_unsafe_draft += 1

    # 4. AutoEval ml_noise_420 (supported-12 noisy utterances)
    noise_cases = [
        json.loads(l)
        for l in (repo_root / "data/benchmarks/autoeval/v1/ml_noise.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    noise_preds = adapter.predict_batch([c["text"] for c in noise_cases], batch_size=64)
    n_confs, n_corrs = [], []
    n_safe = n_raw_draft = n_corr_draft = 0
    for c, p in zip(noise_cases, noise_preds):
        corr = p["intent"] == c["true_intent"]
        n_confs.append(p["confidence"])
        n_corrs.append(corr)
        dec = decide_route(
            IntentPrediction(intent=p["intent"], confidence=p["confidence"], margin=p["margin"], model_version=adapter.version),
            RoutingContext(ticket_customer_id="ml-noise", extracted_slots={}, is_personal_lookup=False),
            policy_v2,
        )
        rejected = (adapter.mode == "calibrated_with_rejector") and (not bool(p["selective_accepted"]))
        eff_draft = dec.action == "retrieve_draft" and not rejected
        if eff_draft:
            n_raw_draft += 1
            if corr:
                n_corr_draft += 1
        if corr or not eff_draft:
            n_safe += 1
    noise_ece, _ = M.expected_calibration_error(n_confs, n_corrs, n_bins=10)
    noise_brier = sum((cf - (1.0 if y else 0.0)) ** 2 for cf, y in zip(n_confs, n_corrs)) / max(1, len(noise_cases))

    # 5. AutoEval ml_oos_80
    oos_cases = [
        json.loads(l)
        for l in (repo_root / "data/benchmarks/autoeval/v1/ml_oos.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    oos_leak_ids: List[str] = []
    for c in oos_cases:
        ans, _ = _engine_analyse_selective(engine, adapter, text=c["text"])
        if ans["routing"]["recommendation"] == "draft":
            oos_leak_ids.append(c["id"])

    # 6. Known regression: system_acceptance_156
    sa_cases = [
        json.loads(l)
        for l in (repo_root / "data/benchmarks/system/v2/acceptance/cases.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    sa_raw_draft = sa_corr_draft = sa_ans_tot = 0
    sa_mand_tot = sa_mand_strict = 0
    sa_mand_real_leaks: List[str] = []
    sa_mand_uninjected_leaks: List[str] = []
    sa_esc34_true: List[str] = []
    sa_esc34_pred: List[str] = []
    for c in sa_cases:
        order_ctx = c.get("context", {}).get("extracted_slots", {})
        ans, _ = _engine_analyse_selective(engine, adapter, text=c["text"], order_ctx=order_ctx)
        rec = ans["routing"]["recommendation"]
        act = {"draft": "retrieve_draft", "abstain": "manual_fallback"}.get(rec, rec)
        pred_i = ans["intent"]["label"]
        exp = c.get("expected", {})
        ti = c.get("true_intent")
        if ti in ESCALATED_34_INTENTS:
            sa_esc34_true.append(ti)
            sa_esc34_pred.append(pred_i)
        if exp.get("answerable") or exp.get("draft_expected"):
            sa_ans_tot += 1
            if rec == "draft":
                sa_raw_draft += 1
                if pred_i == ti:
                    sa_corr_draft += 1
        if exp.get("must_escalate"):
            sa_mand_tot += 1
            if act in exp.get("actions", []):
                sa_mand_strict += 1
            if rec == "draft":
                if c["id"] in KNOWN_UNINJECTED_ACCEPTANCE_IDS:
                    sa_mand_uninjected_leaks.append(c["id"])
                else:
                    sa_mand_real_leaks.append(c["id"])

    # 7. Known regression: final_acceptance_24
    fa_cases = [
        json.loads(l)
        for l in (repo_root / "data/benchmarks/final_acceptance/cases.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    fa_ans_tot = fa_raw_draft = fa_corr_draft = 0
    fa_unans_tot = 0
    fa_unans_uninjected: List[str] = []
    fa_unans_real_ids: List[str] = []
    fa_wrong_draft_ids: List[str] = []
    for c in fa_cases:
        order_ctx = {"order_id": c["order_id"]} if c.get("order_id") else {}
        ans, _ = _engine_analyse_selective(
            engine,
            adapter,
            text=c["query"],
            as_of=c.get("as_of") or "2026-11-13T00:00:00Z",
            order_ctx=order_ctx,
        )
        rec = ans["routing"]["recommendation"]
        pred_i = ans["intent"]["label"]
        if c.get("is_answerable"):
            fa_ans_tot += 1
            if rec == "draft":
                fa_raw_draft += 1
                if pred_i == c["intent"]:
                    fa_corr_draft += 1
                else:
                    fa_wrong_draft_ids.append(c["id"])
        else:
            fa_unans_tot += 1
            if rec == "draft":
                if c["id"] in KNOWN_UNINJECTED_FINAL_IDS or c.get("fixture_boundary") != "active_kb":
                    fa_unans_uninjected.append(c["id"])
                else:
                    fa_unans_real_ids.append(c["id"])

    return {
        "evaluation_mode": adapter.mode,
        "temperature_used": 1.0 if adapter.mode == "raw_uncalibrated" else adapter.temperature,
        "rejector_active": adapter.mode == "calibrated_with_rejector",
        "new_holdout_positive": {
            "n_total": len(eval_pos_rows),
            "accuracy_all": round(float(accuracy_score(pos_gold, pos_pred_labels)), 4),
            "supported_12_n": len(pos_sup12_true),
            "supported_12_accuracy": round(float(accuracy_score(pos_sup12_true, pos_sup12_pred)), 4),
            "supported_12_macro_f1": round(
                float(f1_score(pos_sup12_true, pos_sup12_pred, labels=list(SUPPORTED_12_INTENTS), average="macro", zero_division=0)),
                4,
            ),
            "sup11_total": pos_sup11_n,
            "raw_draft_eligible_count": pos_raw_draft,
            "correct_intent_draft_eligible_count": pos_corr_draft,
            "precision_among_eligible": round(pos_corr_draft / max(1, pos_raw_draft), 4) if pos_raw_draft else 1.0,
            "human_agent_escalated_count": pos_human_esc,
            "escalated_34_n": pos_esc34_n,
            "escalated_34_accuracy": round(float(accuracy_score(pos_esc34_true, pos_esc34_pred)), 4) if pos_esc34_true else 0.0,
            "escalated_34_unsafe_draft_count": pos_esc34_unsafe_draft,
        },
        "new_holdout_negative": {
            "n_total": len(eval_neg_rows),
            "false_draft_count": neg_false_draft,
            "false_draft_ids": neg_false_draft_ids,
            "false_accept_any_count": neg_false_accept_any,
            "by_category": neg_by_cat,
        },
        "original_46_label_test": {
            "n_total": len(test_gold),
            "all_46_accuracy": round(float(accuracy_score(test_gold, test_pred_lbls)), 4),
            "all_46_macro_f1": round(float(f1_score(test_gold, test_pred_lbls, average="macro", zero_division=0)), 4),
            "supported_12_accuracy": round(
                float(accuracy_score([test_gold[i] for i in sup12_idx], [test_pred_lbls[i] for i in sup12_idx])), 4
            ),
            "other_34_accuracy": round(
                float(accuracy_score([test_gold[i] for i in oth34_idx], [test_pred_lbls[i] for i in oth34_idx])), 4
            ),
            "other_34_macro_f1": round(
                float(
                    f1_score(
                        [test_gold[i] for i in oth34_idx],
                        [test_pred_lbls[i] for i in oth34_idx],
                        labels=list(ESCALATED_34_INTENTS),
                        average="macro",
                        zero_division=0,
                    )
                ),
                4,
            ),
            "other_34_unsafe_draft_count": oth34_unsafe_draft,
        },
        "ml_noise_420": {
            "n_total": len(noise_cases),
            "overall_accuracy": round(sum(n_corrs) / max(1, len(noise_cases)), 4),
            "raw_draft_eligible_count": n_raw_draft,
            "correct_intent_draft_eligible_count": n_corr_draft,
            "precision_among_eligible": round(n_corr_draft / max(1, n_raw_draft), 4) if n_raw_draft else 1.0,
            "ece_10bin": round(float(noise_ece), 4),
            "binary_top_label_brier": round(float(noise_brier), 4),
            "safe_routing_rate": round(n_safe / max(1, len(noise_cases)), 4),
        },
        "ml_oos_80": {
            "n_total": len(oos_cases),
            "false_draft_count": len(oos_leak_ids),
            "false_draft_ids": oos_leak_ids,
        },
        "known_regression_system_acceptance_156": {
            "suite_role": "known_acceptance_regression_not_unseen_holdout",
            "answerable_total": sa_ans_tot,
            "raw_draft_eligible_count": sa_raw_draft,
            "correct_intent_draft_eligible_count": sa_corr_draft,
            "precision_among_eligible": round(sa_corr_draft / max(1, sa_raw_draft), 4) if sa_raw_draft else 1.0,
            "escalated_34_macro_f1": round(
                float(f1_score(sa_esc34_true, sa_esc34_pred, labels=list(ESCALATED_34_INTENTS), average="macro", zero_division=0)),
                4,
            )
            if sa_esc34_true
            else 0.0,
            "mandatory_total": sa_mand_tot,
            "mandatory_strict_match": sa_mand_strict,
            "mandatory_real_unsafe_draft_leaks": sa_mand_real_leaks,
            "mandatory_known_uninjected_fault_cases": sa_mand_uninjected_leaks,
        },
        "known_regression_final_acceptance_24": {
            "suite_role": "known_acceptance_regression_not_unseen_holdout",
            "answerable_total": fa_ans_tot,
            "raw_draft_eligible_count": fa_raw_draft,
            "correct_intent_draft_eligible_count": fa_corr_draft,
            "precision_among_eligible": round(fa_corr_draft / max(1, fa_raw_draft), 4) if fa_raw_draft else 1.0,
            "wrong_intent_draft_ids": fa_wrong_draft_ids,
            "unanswerable_total": fa_unans_tot,
            "unanswerable_real_active_kb_leaks": fa_unans_real_ids,
            "unanswerable_known_uninjected_fault_cases": fa_unans_uninjected,
        },
    }


def run_closure_candidate_pipeline(
    *,
    repo_root: Path = REPO_ROOT,
    output_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute bounded 2-fit closure training, calibration selection, locking & evaluation."""
    out_root = output_root or (repo_root / "artifacts/evaluation/task_a_closure_20261113")
    out_root.mkdir(parents=True, exist_ok=True)
    datasets_dir = out_root / "datasets"
    fits_dir = out_root / "fits"
    cand_dir = out_root / "candidate_model"
    serving_dir = repo_root / "artifacts/models/trained/distilbert-supportiq"

    # 1. Verify original 46-label Bitext lineage & export audited closure datasets
    lineage: VerifiedOriginalLineage = verify_original_46_label_lineage(repo_root=repo_root)
    ds_manifest = export_closure_datasets(datasets_dir, repo_root=repo_root)
    compute_inv = collect_compute_and_model_inventory(repo_root=repo_root)

    pos_train = [json.loads(l) for l in (datasets_dir / "closure_positive_train.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    neg_train = [json.loads(l) for l in (datasets_dir / "closure_negative_train.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    pos_cal = [json.loads(l) for l in (datasets_dir / "closure_positive_calibration.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    neg_cal = [json.loads(l) for l in (datasets_dir / "closure_negative_calibration.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    pos_eval = [json.loads(l) for l in (datasets_dir / "closure_positive_evaluation.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    neg_eval = [json.loads(l) for l in (datasets_dir / "closure_negative_evaluation.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    # Bitext replay train (80/label for other_34, 35/label for supported_12) + disjoint cal (5/label)
    replay_domain_train_df, bitext_cal_df = build_replay_and_domain_train_df(
        lineage,
        pos_train,
        replay_per_other_label=80,
        replay_per_supported_label=35,
        domain_train_repeat=4,
        cal_per_label=5,
        seed=42,
    )
    label2id = {lbl: idx for idx, lbl in enumerate(STANDARD_INTENTS_46)}

    pos_train_texts = replay_domain_train_df["instruction"].tolist()
    pos_train_labels = [label2id[x] for x in replay_domain_train_df["intent"].tolist()]
    pos_train_flags = [0] * len(pos_train_texts)

    # Rejector training set (strictly TRAIN only):
    # y=1: draftable single-intent SUPPORTED_11 (closure train sup11 x4 + Bitext sup11 train replay)
    # y=0: non-draftable (closure negative train x6 + closure esc34/human train x2 + Bitext esc34/human sample 8/label)
    rng = np.random.default_rng(42)
    bitext_train_only = lineage.train_df[~lineage.train_df["sample_id"].isin(set(bitext_cal_df["sample_id"]))].copy()
    bitext_sup11_df = pd.concat(
        [
            bitext_train_only[bitext_train_only["intent"] == lbl].sample(
                n=min(35, len(bitext_train_only[bitext_train_only["intent"] == lbl])),
                random_state=42 + i,
            )
            for i, lbl in enumerate(SUPPORTED_11_DRAFT_INTENTS)
        ],
        ignore_index=True,
    )
    non_draft_intents = [lbl for lbl in STANDARD_INTENTS_46 if lbl not in SUPPORTED_11_DRAFT_INTENTS]
    bitext_nondraft_df = pd.concat(
        [
            bitext_train_only[bitext_train_only["intent"] == lbl].sample(
                n=min(8, len(bitext_train_only[bitext_train_only["intent"] == lbl])),
                random_state=142 + i,
            )
            for i, lbl in enumerate(non_draft_intents)
        ],
        ignore_index=True,
    )

    dom_sup11_train = [r for r in pos_train if r["intent"] in SUPPORTED_11_DRAFT_INTENTS]
    dom_nondraft_train = [r for r in pos_train if r["intent"] not in SUPPORTED_11_DRAFT_INTENTS]

    rej_y1_texts = [r["instruction"] for _ in range(4) for r in dom_sup11_train] + bitext_sup11_df["instruction"].tolist()
    rej_y0_texts = (
        [r["instruction"] for _ in range(6) for r in neg_train]
        + [r["instruction"] for _ in range(2) for r in dom_nondraft_train]
        + bitext_nondraft_df["instruction"].tolist()
    )
    rej_train_texts = rej_y1_texts + rej_y0_texts
    rej_train_y = ([1] * len(rej_y1_texts)) + ([0] * len(rej_y0_texts))

    policy_path = repo_root / "apps/core_backend/config/policies/intent_policy.v2.json"
    policy_v2 = load_policy_v2(str(policy_path))
    release = json.loads((repo_root / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    allowed_docs = {(d["document_id"], d["version"]) for d in release["documents"]}
    retriever = RetrievalAdapter(allowed_document_versions=allowed_docs)

    cal_pos_df = pd.DataFrame(pos_cal)
    cal_neg_df = pd.DataFrame(neg_cal)
    c_grid = (0.15, 0.35, 0.75, 1.5)

    train_budget_start = time.perf_counter()

    # ------------------------------------------------------------------
    # Fit 1: Clean Positive 46-class CE + Dual-Head CLS+Logit Rejector
    # ------------------------------------------------------------------
    fit1_dir = fits_dir / "fit1_closure_dual_head"
    fit1_train_meta = _train_closure_single_fit(
        fit_name="fit1_closure_dual_head",
        objective_mode="clean_positive_ce",
        base_model_dir=serving_dir,
        output_dir=fit1_dir,
        train_texts=pos_train_texts,
        train_labels=pos_train_labels,
        train_is_negative=pos_train_flags,
        seed=42,
        epochs=3,
    )
    fit1_temp, fit1_rej, fit1_cal = _build_closure_rejector_on_train_and_cal(
        fit_name="fit1_closure_dual_head",
        model_dir=fit1_dir,
        feature_spec="cls_l2_plus_logit_geometry_v1",
        c_grid=c_grid,
        rej_train_texts=rej_train_texts,
        rej_train_y=rej_train_y,
        cal_pos_df=cal_pos_df,
        cal_neg_df=cal_neg_df,
        bitext_cal_df=bitext_cal_df,
        policy_v2=policy_v2,
    )

    # ------------------------------------------------------------------
    # Fit 2: Selective Margin + Energy Shaping + CLS+Logit Rejector
    # ------------------------------------------------------------------
    neg_repeat = 4
    fit2_texts = pos_train_texts + [r["instruction"] for _ in range(neg_repeat) for r in neg_train]
    fit2_labels = pos_train_labels + ([0] * (len(neg_train) * neg_repeat))
    fit2_flags = pos_train_flags + ([1] * (len(neg_train) * neg_repeat))
    perm = rng.permutation(len(fit2_texts))
    fit2_texts = [fit2_texts[i] for i in perm]
    fit2_labels = [fit2_labels[i] for i in perm]
    fit2_flags = [fit2_flags[i] for i in perm]

    fit2_dir = fits_dir / "fit2_closure_selective_margin"
    fit2_train_meta = _train_closure_single_fit(
        fit_name="fit2_closure_selective_margin",
        objective_mode="closure_selective_margin",
        base_model_dir=serving_dir,
        output_dir=fit2_dir,
        train_texts=fit2_texts,
        train_labels=fit2_labels,
        train_is_negative=fit2_flags,
        seed=1042,
        epochs=3,
    )
    fit2_temp, fit2_rej, fit2_cal = _build_closure_rejector_on_train_and_cal(
        fit_name="fit2_closure_selective_margin",
        model_dir=fit2_dir,
        feature_spec="cls_l2_plus_logit_geometry_v1",
        c_grid=c_grid,
        rej_train_texts=rej_train_texts,
        rej_train_y=rej_train_y,
        cal_pos_df=cal_pos_df,
        cal_neg_df=cal_neg_df,
        bitext_cal_df=bitext_cal_df,
        policy_v2=policy_v2,
    )

    total_train_elapsed = round(time.perf_counter() - train_budget_start, 2)
    if total_train_elapsed > MAX_TRAINING_BUDGET_SECONDS:
        raise RuntimeError(f"Exceeded 1800s training budget: {total_train_elapsed}s")

    # ------------------------------------------------------------------
    # Select winner strictly on isolated calibration splits and LOCK
    # ------------------------------------------------------------------
    fit_records = {
        "fit1_closure_dual_head": {
            "dir": fit1_dir,
            "train": fit1_train_meta,
            "temperature": fit1_temp,
            "rejector": fit1_rej,
            "calibration": fit1_cal,
        },
        "fit2_closure_selective_margin": {
            "dir": fit2_dir,
            "train": fit2_train_meta,
            "temperature": fit2_temp,
            "rejector": fit2_rej,
            "calibration": fit2_cal,
        },
    }
    winner_name = max(
        fit_records.keys(),
        key=lambda k: fit_records[k]["calibration"]["calibration_selection_utility"],
    )
    winner = fit_records[winner_name]

    if cand_dir.exists():
        shutil.rmtree(cand_dir)
    shutil.copytree(winner["dir"], cand_dir)

    cal_manifest_path = write_calibration_manifest(
        model_dir=cand_dir,
        model_version=f"supportiq-{winner_name}-20261113",
        fit_name=winner_name,
        temperature=winner["temperature"],
        rejector=winner["rejector"],
        train_split_sha256=ds_manifest["files"]["closure_combined_train"]["sha256"],
        calibration_split_sha256=ds_manifest["files"]["closure_combined_calibration"]["sha256"],
    )

    git_sha = _git_head_sha(repo_root)
    prov_manifest = {
        "provenance_status": "verified",
        "model_version": f"supportiq-{winner_name}-20261113",
        "selected_fit": winner_name,
        "training_lineage": {
            "bitext_preparation_run_id": lineage.run_id,
            "cleaned_csv_sha256": lineage.cleaned_sha256,
            "split_assignments_csv_sha256": lineage.splits_sha256,
            "closure_origin": "task_a_closure_20261113",
            "two_fit_budget_seconds": MAX_TRAINING_BUDGET_SECONDS,
            "total_training_elapsed_seconds": total_train_elapsed,
        },
        "dataset_hashes": {
            "bitext_cleaned_csv": lineage.cleaned_sha256,
            "bitext_split_assignments_csv": lineage.splits_sha256,
            **{k: v["sha256"] for k, v in ds_manifest["files"].items()},
        },
        "base_model": {
            "name": "distilbert-supportiq",
            "path": "artifacts/models/trained/distilbert-supportiq",
            "weights_sha256": compute_sha256(serving_dir / "model.safetensors").lower(),
            "tokenizer_sha256": compute_sha256(serving_dir / "tokenizer.json").lower(),
        },
        "git_commit": git_sha,
        "artifact_hashes": {
            "model.safetensors": compute_sha256(cand_dir / "model.safetensors").lower(),
            "tokenizer.json": compute_sha256(cand_dir / "tokenizer.json").lower(),
            "config.json": compute_sha256(cand_dir / "config.json").lower(),
        },
        "calibration_manifest_path": "artifacts/evaluation/task_a_closure_20261113/candidate_model/calibration_manifest.json",
        "calibration_manifest_sha256": compute_sha256(cal_manifest_path).lower(),
    }
    prov_path = cand_dir / "candidate_provenance_manifest.json"
    prov_path.write_text(json.dumps(prov_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    cal_selection_doc = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "selection_policy": "Selected solely on isolated calibration split before any holdout/regression eval.",
        "total_training_elapsed_seconds": total_train_elapsed,
        "budget_cap_seconds": MAX_TRAINING_BUDGET_SECONDS,
        "selected_winner": winner_name,
        "candidates": {
            k: {
                "train_summary": v["train"],
                "calibration_summary": v["calibration"],
            }
            for k, v in fit_records.items()
        },
    }
    (out_root / "calibration_selection.json").write_text(
        json.dumps(cal_selection_doc, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ------------------------------------------------------------------
    # Single post-decision locked evaluation + Task C gate verification
    # ------------------------------------------------------------------
    eval_modes: Dict[str, Any] = {}
    for mode_name in ("raw_uncalibrated", "calibrated_without_rejector", "calibrated_with_rejector"):
        adapter = SelectiveCandidateAdapter(
            prov_manifest["model_version"],
            cand_dir,
            prov_manifest["model_version"],
            mode=mode_name,
            validate_manifest=True,
        )
        eval_modes[mode_name] = _evaluate_closure_adapter_mode(
            adapter,
            repo_root=repo_root,
            eval_pos_rows=pos_eval,
            eval_neg_rows=neg_eval,
            bitext_test_df=lineage.test_df,
            policy_v2=policy_v2,
            retriever=retriever,
        )

    srv_adapter = SelectiveCandidateAdapter(
        "distilbert-supportiq",
        serving_dir,
        "distilbert-supportiq",
        mode="raw_uncalibrated",
        validate_manifest=False,
    )
    serving_eval = _evaluate_closure_adapter_mode(
        srv_adapter,
        repo_root=repo_root,
        eval_pos_rows=pos_eval,
        eval_neg_rows=neg_eval,
        bitext_test_df=lineage.test_df,
        policy_v2=policy_v2,
        retriever=retriever,
    )

    c_gate = run_classifier_acceptance_gate(
        repo_root=repo_root,
        candidate_name=prov_manifest["model_version"],
        candidate_dir=cand_dir,
        serving_dir=serving_dir,
        candidate_manifest_path=prov_path,
        calibration_manifest_path=cal_manifest_path,
        train_split_path=datasets_dir / "closure_combined_train.jsonl",
        calibration_split_path=datasets_dir / "closure_combined_calibration.jsonl",
        eval_split_path=datasets_dir / "closure_positive_evaluation.jsonl",
        verify_parity=True,
    )

    final_eval = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "compute_and_model_inventory": compute_inv,
        "git_head_before_run": git_sha,
        "locked_candidate": {
            "model_version": prov_manifest["model_version"],
            "model_dir": str(cand_dir),
            "artifact_hashes": prov_manifest["artifact_hashes"],
            "calibration_manifest_sha256": prov_manifest["calibration_manifest_sha256"],
        },
        "calibration_selection_summary": cal_selection_doc,
        "serving_baseline": serving_eval,
        "candidate_modes": eval_modes,
        "classifier_acceptance_gate": c_gate,
    }
    (out_root / "final_evaluation.json").write_text(json.dumps(final_eval, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_root / "classifier_acceptance_gate.json").write_text(json.dumps(c_gate, indent=2, ensure_ascii=False), encoding="utf-8")
    return final_eval


if __name__ == "__main__":
    summary = run_closure_candidate_pipeline(repo_root=REPO_ROOT)
    sel = summary["calibration_selection_summary"]
    srv = summary["serving_baseline"]
    cand = summary["candidate_modes"]["calibrated_with_rejector"]
    gate = summary["classifier_acceptance_gate"]
    print(
        json.dumps(
            {
                "selected_winner": sel["selected_winner"],
                "total_train_s": sel["total_training_elapsed_seconds"],
                "gate_decision": gate["gate_decision"],
                "gate_failures": gate["failure_reasons"],
                "serving_oos_leaks": srv["ml_oos_80"]["false_draft_count"],
                "cand_oos_leaks": cand["ml_oos_80"]["false_draft_ids"],
                "cand_sa_mand_real_leaks": cand["known_regression_system_acceptance_156"]["mandatory_real_unsafe_draft_leaks"],
                "cand_fa_real_leaks": cand["known_regression_final_acceptance_24"]["unanswerable_real_active_kb_leaks"],
                "cand_holdout_pos": cand["new_holdout_positive"],
                "cand_holdout_neg": cand["new_holdout_negative"],
                "cand_noise": cand["ml_noise_420"],
                "cand_bitext_46": cand["original_46_label_test"],
            },
            indent=2,
        )
    )
