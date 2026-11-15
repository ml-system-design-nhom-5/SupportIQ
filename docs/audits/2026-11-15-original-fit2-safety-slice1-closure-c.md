# Worker C Audit — Original Fit2 System Slice 1 CLOSURE (`a316377a` / `e8856394`)

- **Verdict:** **PASS** — **System Slice 1 (`Gap 1`) CLOSED** (`scope`: `SYSTEM_SLICE1_ONLY_NOT_RAW_ML_NOT_WHOLE_PROJECT`; `failed_criteria: []`).
- **Branch / Reviewed HEAD:** `minh` @ `e8856394043c93bdd64e79155396c6f282962000` (Worker B PASS review over Worker A fix `a316377abdb8d32a894efb161178a573cccf3473`).
- **Run Command & Artifact Dir:**
  - `.venv/Scripts/python.exe -B artifacts/evaluation/original_fit2_safety_slice1_closure_c_20261115/evaluate_safety_slice1_closure_c.py` (`eval_seconds=111.59`, `total_duration_seconds=132.67`)
  - Artifacts: `artifacts/evaluation/original_fit2_safety_slice1_closure_c_20261115/` (`predictions_post_slice1_closure_orig_fit2.jsonl` `82f0397ea8df17478119dc9d8184dc53b06e03f2a7275a1564740d1b334988d5`, `slice1_closure_paired_evaluation.json` `b4423df478bfd53a5749360112d3bf583a7c3f2fe2d6dab3352ba386a4230308`, `run_manifest.json`)

---

## 1. Frozen Invariants Verified

| Artifact / Pin | Expected State | Observed SHA-256 |
|---|---|---|
| Orig Fit2 Weights (`reconstructed-fit2-supcon-20261113/model.safetensors`) | Unchanged | `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` |
| Orig Fit2 Calibration (`calibration_manifest.json`) | Unchanged | `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39` |
| Serving Weights (`distilbert-supportiq/model.safetensors`) | Unchanged | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` |
| Approved KB (`data/knowledge/approved_kb.v2.json`) | Unchanged | `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec` |
| KB Release (`apps/ai_service/kb-release.json`) | Unchanged | `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804` |
| Intent Policy (`apps/core_backend/config/policies/intent_policy.v2.json`) | Unchanged | `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7` |
| Training Cap (`.local/training-cap-20261114.json`) | `2/2` `STOP` (`budget_exhausted`) | `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922` |
| Runtime Env (`.local/ai.env`) | Unchanged | `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87` |
| Retrieval Adapter (`apps/core_backend/retrieval/adapter.py`) | Unchanged since `12d358d3` | `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f` |
| Safety Guard (`apps/core_backend/safety.py`) | Worker A `a316377a` | `45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000` |
| Frozen Gates (`gate27` / `gate16`) | Unchanged | `20bb9315...a66b84d8` / `c232bd6e...7fcc825a3a` |

- `diff_12d3_to_head_apps_data`: `["apps/core_backend/safety.py"]` only.
- Runtime score parity (`orig_fit2` + `serving_pinned_and_fail_closed`): `tokenization_mismatches=0`, `label_mismatches=0`, `score_kind_mismatches=0`, `max_calibrated_confidence_abs_diff=0.0`, `fail_closed_without_manifest=true`, `fail_closed_non_serving_checksum=true`, `engine_enforces_experimental_rejection=true`.
- Typed contracts: `engine_outside_ai_reasons=[]`, `priv_engine_outside_ai_reasons=[]`, `runner_spy_mismatches=[]`.

---

## 2. Frozen 43-Case Unseen Scope & Negation Gate (`gate27` + `gate16`)

### Isolated Gold-Intent (`return_product`) Guard & End-to-End Surfaces

| Gate | Must-Not-Draft Blocked (`scope=True`) | Supported `scope=False` (Real & Gold KB) | Supported Live Drafted | Retrieval-Only Misses (`<0.55`, `scope=False`) | Leaks |
|---|---:|---:|---:|---|---:|
| `gate27` (`20bb9315`, n=27: 11+16) | **11/11** | **16/16** | **16/16** | `0` | **0** |
| `gate16` (`c232bd6e`, n=16: 8+8) | **8/8** | **8/8** | **6/8** | `2`: `s1ng-sup-03`, `s1ng-sup-07` | **0** |
| **Combined 43** | **19/19** | **24/24** | **22/24** (`41/43` end-to-end) | `s1ng-sup-03`, `s1ng-sup-07` (`retrieved_doc_ids=[]`) | **0** |

- **`s1ng-sup-03` & `s1ng-sup-07` distinction preserved:** Unmodified KB retrieval returns `retrieved_doc_ids=[]` (`no_valid_document` / `below_relevance_threshold`), giving `Engine=manual_fallback` and `PipelineRunner=escalate` (`isolated_runner_llm_called=false`), while BOTH `scope_requires_review=False` and `scope_requires_review_with_gold_kb=False` confirm **0 false-positive scope blocks**.
- **Natural Orig Fit2 on `gate27` / `gate16`:**
  - `gate27`: `0/11` leaks across all surfaces (`raw_pre/raw_post/bare/engine/runner/priv_*`); `2/16` drafted on all surfaces (`14` ML non-drafts, unchanged vs `1325a240`).
  - `gate16`: Raw `s1ng-esc-06` leaks on `raw_pre`/`raw_post`/`bare`/`priv_raw_post` (**1** leak), reduced to **0/8** on `Engine`, `PipelineRunner`, `priv_engine`, `priv_runner`; `1/8` supported drafted cleanly.
  - **Paired diff vs `1325a240` on `gate27`+`gate16`:** Only `s1ng-sup-04` on natural `Engine` changed (`escalate` -> `manual_fallback`, dropping false-positive `insufficient_evidence` where `pred=delivery_issue conf=0.057159`).

---

## 3. Documented Worker B Regressions (`24/24` Pre-LLM Blocked)

Executed all `24` verbatim B FAIL-OPEN regressions under `ReturnProductClf` (`return_product`, `conf=0.96`, `margin=0.85`) and `_StrictPreLLMSpy(configured=True)` on `HEAD` `Engine` & `PipelineRunner`:

| Batch | Count | Real Retrieval Status | Real `Engine`/`Runner` Drafts | Injected `POL-RET` `scope_requires_review` | Injected `Engine`/`Runner` Action | External LLM Calls |
|---|---:|---|---:|---:|---|---:|
| `orig_9b4be434_6plus1` | 7 | `6 success`, `1 no_match` (`b-orig-04`) | `0` (`6 esc / 1 abs` Eng; `7 esc` Run) | **7/7** `True` | **7/7** `escalate` | **0** |
| `waiver_04e63ba3_9` | 9 | `9 success` | `0` (`9 esc` Eng; `9 esc` Run) | **9/9** `True` | **9/9** `escalate` | **0** |
| `quote_c1c2a766_8` | 8 | `6 success`, `1 no_match` (`b-q8-05`), `1 no_evidence` (`b-q8-01`) | `0` (`6 esc / 2 abs` Eng; `8 esc` Run) | **8/8** `True` | **8/8** `escalate` | **0** |
| **Total** | **24** | **21 `success`, 2 `no_match`, 1 `no_evidence`** | **0 leaks** | **24/24 `True`** | **24/24 `escalate`** | **0** |

*Denominator reconciliation:* Worker B audit reported `43/43` scope-guard checks (`27` + `16`) and `24/24` regression leaks `=0`; Worker C reproduces `43/43` isolated scope-guard checks (`19/19` `must_not_draft` blocked + `24/24` `scope_requires_review=False`, giving `41/43` end-to-end isolated-intent behavior due to `<0.55` retrieval misses `s1ng-sup-03` & `s1ng-sup-07`) plus all `24` cumulative Worker B regressions live pre-LLM on `HEAD` (`0` failures, `0` LLM calls).

---

## 4. Historical `1,406` Rows + `bitext6690` (`sample_031639`) + Post-Privacy Parity

- **Action parity vs `1325a240` across all `1,406` historical rows:** `historical_1406_nonempty_diffs={}` (**100% identical** on `Engine`, `PipelineRunner`, `priv_engine`, `priv_runner`).
- **Raw ML & Production Floors (unchanged):**
  - `noise420`: `acc_12=0.857143`, `macro_f1_12=0.857307`, `ece_10bin=0.063060`, `brier=0.113556`; `bare=267`, `Engine=268/291` (`safe_routing=0.945238`), `PipelineRunner=260/283` (`>= 260/420` floor PASS).
  - `final24`: `Engine` & `PipelineRunner` `ans12=10/12` (`0` wrong, `>= 10/12` floor PASS), `active_unans8=0` leaks.
  - `sa156`: `Engine` & `PipelineRunner` `sup34=25/34` (`3` wrong, `>= 25/34` floor PASS), `mand63` real leaks `9` (`raw_pre/raw_post`) -> **0** (`Engine` & `PipelineRunner`), strict match `59` (`Engine`) / `51` (`Runner`).
  - `unseen36`: `return_contrast_escalated` leaks `4` (`raw_pre/raw_post/bare`) -> **0** (`Engine` & `Runner`); supported `cross_intent=5/7` (post-privacy `6/7`), `return_contrast=5/5`.
  - `fresh34`: raw leak `1` (`v4p1-ood-08`) -> **0** (`Engine` & `Runner`).
  - `ind36`: `0` leaks; `answerable=6/11` (`Engine`), `5/11` (`Runner`).
  - `old_sealed72`: `0` leaks; `answerable=6/24` (`Engine`), `5/24` (`Runner`), `mand_strict=20/24`.
  - `oos80`: raw leaks `3` (`oos-general-08`, `oos-other_domain-19`, `oos-multi_intent-08`) -> **0** (`Engine` & `Runner`).
  - `pos175` + `neg51`: raw leaks `4` `esc34` + `1` `neg51` (`nonretail_ood_eval_019`) -> **0** (`Engine` & `Runner`); supported cost `-1` unchanged (`35->34` on `Runner` via `cls_dis_wrong_drop_0_841424c7a978`).
  - `cand_split_boundary_pos122_neg39`: `0` leaks; `sup11=31/77` (`Engine`), `30/77` (`Runner`).
  - `bitext6690` (`sample_031639` live): raw `retrieve_draft` -> **blocked** (`escalate`, `["insufficient_evidence"]`) on BOTH `Engine` & `PipelineRunner` (full 6,690-row DistilBERT cache in `3bbbe5f` unchanged: `acc46=0.996263`, `macroF1=0.996313`, `sup11=1600/1613`).
- **Pre-Slice-1 (`1bf9e6af`) -> Closure (`e8856394`) safety delta:** `11` `Engine` leaks and `9` `PipelineRunner` leaks across the `12` suites -> **0** leaks on every production and post-privacy surface (`priv_engine`, `priv_runner`).

---

## 5. Residual Risk & Next Sequential Gate Status

- **Bounded finite-grammar residual limits (`safety.py`):** Attributed-quote masking and negated-channel waivers follow conservative fail-closed finite patterns; novel syntactic constructions outside those finite grammars (e.g., complex multi-clause hedging or new quoted preambles) default to `scope_requires_review=True` (safe over-escalation rather than fail-open draft), without pretending arbitrary NLU coverage.
- **Open Workstreams (UNCLOSED):**
  - **Gap 2 (Authority / Outage Guard):** Remains **OPEN** — ready for coordinator to release Worker A sequentially now that Slice 1 is closed.
  - **Gap 3 (NER / Privacy Leakage Guard):** Remains **OPEN**.
  - **Raw ML Training Cap:** Remains **2/2 STOPPED** (`budget_exhausted`; original Fit2 `f695b1fe` stays active).
