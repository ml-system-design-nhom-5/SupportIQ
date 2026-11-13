# Fit2 Independent Gate Audit (`fit2-sibling-boundary-v2`)

- **Verdict:** **`REJECT`** (retain unchanged Serving `distilbert-supportiq` `dc7af8cf`).
- **Scope & Constraints:** `0` live LLM calls (offline `_OfflineValidSpyLLM` for `PipelineRunner` draft eligibility only; not real provider or semantic grading), `0` edits to Serving weights, A's archive, or B's tests. Small-sample holdouts (`n=36`, `n=72`) do not support universal acceptance claims.
- **Unavailability Disclosure:** Prior `Fit2` (`f695b1fe`) and `Old Closure` (`95a940b6`) checkpoints were removed with old workspaces; only historical non-paired reports exist (`docs/audits/2026-11-13-closure-round-acceptance.md`).

## 1. Pre-Registered Holdout, Archive & Data Lineage
- **Sealed Holdout:** Commit `efb6868` (`artifacts/evaluation/fit2_independent_gate_20261113/cases.jsonl`, `total_cases=36` [`12` supported: `11` answerable + `1` `human_agent`, `12` `novel_ood`, `12` `mandatory_escalation`], `cases_sha256=19a56d87299fd28c177f38cce87691598b47c1ed35143ce29194d5215daecc2f`); `0` exact/near-duplicate overlaps against `13,271` prior prompts (`max_jaccard=0.45`, `max_seq=0.619`) and `0` overlaps against A's `datasets_v2` (`14,986` rows, `max_jaccard=0.348`).
- **Archive Integrity (`F:/Năm 3/SD/project/SupportIQ/artifacts/models/candidates/`):** Both `fit1-sibling-boundary-v1` and `fit2-sibling-boundary-v2` present and reload cleanly (`num_labels=46`, `vocab=30522`). Verified `fit2-sibling-boundary-v2` hashes match `archive_sha_inventory.json`: `model.safetensors=d7ac47d002fcdc38c11290b22c6e2f1fedd015bfdedc64b49a9929b02dfd625b`, `calibration_manifest.json=71dffc1f...`, `candidate_provenance_manifest.json=5968f851...`, `T=1.29`, `selective_rejector.enabled=false`.
- **Canonical Prep Lineage:** `data/datasets/restored/bitext-12dd624/prep` (`13-11-2026-00`, `raw=13a98826...`, `cleaned=8bc10cfa...`, `splits=1d366e89...`; `44,884` raw -> `44,601` cleaned, `4` quarantined, `37,911` train / `6,690` test) matches `datasets_v2` provenance.
- **Provenance Caveats:** `candidate_provenance_manifest.json` records literal `git_commit: "HEAD"` (actual A commit `0f2da9274db55479741e38ec2fe42f7eedfdb13a`) and tiny internal `eval_pos=2`, `neg_eval=2`.

## 2. Independent Evaluation Results (`Serving dc7af8cf` vs `fit2-sibling-boundary-v2 d7ac47d0`)

| Suite / Metric | Serving (`dc7af8cf`) | Candidate (`d7ac47d0`) | Notes |
| :--- | :--- | :--- | :--- |
| **New Sealed 36 (`Runner`, `ans=11`)** | **`3/11`** (`27.3%`) corr, `1/11` wrong (`g2-sup-08`), prec `3/4` (`75.0%`), abst `7/11` | **`2/11`** (`18.2%`) corr, `1/11` wrong (`g2-sup-09`), prec `2/3` (`66.7%`), abst `8/11` | `human_agent` (`g2-sup-12`) escalated `1/1` both |
| **New Sealed 36 Leaks (`Engine` / `Runner`)** | **`1/25`** (`g2-esc-06`) | **`2/25`** (`g2-esc-05`, `g2-esc-06`) | `novel_ood` leaks: `0/12` both |
| **New Sealed 36 Bare `decide_route` (non-HTTP)** | `3/11` corr, `3` leaks (`g2-esc-02,06,10`) | `2/11` corr, `3` leaks (`g2-esc-02,05,06`) | Reported separately; not HTTP-reachable |
| **Fixed Gate (`run_classifier_acceptance_gate`)** | Baseline | **`PASS`** (`[]`) | Provenance/parity/isolation `True` |
| **`ml_oos_80` / `ml_noise_420` (`acc_12`/`f1_12`/`safe`/`prec`)** | `0/80` / `0.6548`/`0.6817`/`0.9214`/`177/210` (`84.3%`) | `0/80` / `0.7643`/`0.7710`/`0.9524`/`198/218` (`90.8%`) | ECE `0.0920` -> `0.0907` |
| **`system_acceptance_156` (`esc34 f1`/`draft34`/`mand63`)** | `0.6471` / `17/21` / `55/63` (`0` leaks) | `0.7990` / `21/22` / `61/63` (`0` leaks) | Regression suite |
| **`final_acceptance_24` (`ans12` corr/raw, wrong)** | `4/5` (`final-case-02`), `0` unans leaks | **`2/2`** (`[]`), `0` unans leaks | Severe coverage drop (`4/12` -> `2/12`) |
| **Old `sealed_72` (`sup24` Runner draft / `48` leaks)** | `9` drafts / `1` leak (`sh-esc-01`) | `3` drafts / `0` leaks (`1` bare `sh-esc-22`) | Historical evidence, not unseen |

## 3. Exact Blockers & Omitted Checks
- **Pre-registered Failures:** `R1_new_holdout_draft_leak` (`g2-esc-05` `refund_policy` `0.65812` + `g2-esc-06` `cancel_order` `0.97477` on `Engine`/`Runner`) and `R2_supported_coverage_below_serving_or_all_abstain` (`2/11` vs Serving `3/11`, plus `final_acceptance_24` `2/12` vs `4/12` and `old_sealed72` `3` vs `9` drafts).
- **Omitted Checks & Risks:** No live Gemini provider calls, no human/semantic grading, no `fit1` full suite run (reload verified only). Raw predictions in `artifacts/evaluation/fit2_independent_gate_20261113/results/predictions_*.jsonl`.
