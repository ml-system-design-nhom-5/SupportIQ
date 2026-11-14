# Worker C Bounded CAL & Objective Verification: `fit2-orig-teacher-kl-v1`

**Reviewer:** Worker C (`review` / independent CAL & objective audit)
**Target Candidate:** [fit2-orig-teacher-kl-v1](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/fit2-orig-teacher-kl-v1) (A's audit at `1319d3cc271f9abd3720c77d50aa2613ed4b032a`: [2026-11-14-fit2-teacher-kl-run-a.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-teacher-kl-run-a.md))
**Scope:** Strictly read-only CAL guard reproduction, lineage/input/source parity, 4-way right/wrong comparison, and read-only in-memory gradient/dropout probes (**zero** optimizer steps, **zero** new fits/calibrators, **zero** paid LLMs, **zero** holdout/OOD/full eval inference).
**Deliverables:**
- Script: [verify_teacher_kl_cal.py](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_teacher_kl_cal_review_c_20261114/verify_teacher_kl_cal.py)
- Metrics & Probe JSON: [teacher_kl_cal_and_probe_comparison.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_teacher_kl_cal_review_c_20261114/teacher_kl_cal_and_probe_comparison.json)
- Manifest: [run_manifest.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_teacher_kl_cal_review_c_20261114/run_manifest.json)

---

## 1. Dual Verdict Summary

- **Implementation & Lineage Verdict:** **`PASS`** — exact match to Worker B's approved `option_a_teacher_kl` profile (`lr=2e-5`, `epochs=3`, `batch_size=32`, `seed=42`, `alpha_kl=1.0`, `T_teacher=1.0`, `13,000` anchored / `80` `orig_ret_ch_*` excluded), forward `KL(p_teacher || p_student)`, `46`-class mapping & tokenizer match, `teacher_model` frozen in `.eval()`, post-fit `reconstructed-fit2-supcon-20261113` hash unchanged (`f695b1fe...`). **No implementation bug found.**
- **CAL Guard Verdict:** **`CAL_GUARD_REJECT_DO_NOT_PROMOTE` (`BLOCK`)** — independently reproduced **`4/12 PASS`, `8/12 FAIL`** (`max_guard_float_diff = 0.0 <= 3e-6`; `ModelContainer` parity `134/134` boundary CAL rows, `0` intent mismatches, `max_confidence_abs_diff = 2.72e-6 <= 3e-6`).
- **Root Scientific Finding (Exploratory Objective Failure):** Read-only probes show `teacher.eval()` (`entropy=0.492339`) vs `student.train()` with DistilBERT dropout (`entropy=0.557460`) creates a step-0 dropout-only KL (`0.004892`) whose gradient has **`+0.4759` positive cosine similarity** (`40.0%` of base grad norm) with the base `CE+SupCon+Neg` sharpening direction; by final checkpoint, student eval entropy fell **below** the teacher (`0.478472 < 0.492339`), while CAL drift exceeded unanchored `2e-5` (`+0.055831` vs `+0.036095` on `pos_cal`).

---

## 2. Archive, Sidecar, Prep, Input Parity & Untouched Checkpoints

| Check | Result | Verified Evidence / SHA-256 |
|---|---|---|
| Candidate Archive (`6/6`) | **PASS** | `model.safetensors` `3994af2c461cd029f4d03dbec38a75b2bb103a78d8550f4f3a20078b354bca06`; `calibration_manifest.json` `4e06df8f2ecd11fb72d9e8163525eafe06ca0feebba87310e808cdfbd7b88db8` (`T=1.0`, `min_T=1.0`, `rejector=false`); `candidate_provenance_manifest.json` `ceacdb9f00f8f1d3e5a588080cdb747543db0d71446fa4b89b99d0c9ef592bcc` |
| Sidecar (`41/41`) & Prep (`39/39`) | **PASS** | Sidecar `cal_guard_report.json` `34967831ff85a4d8a1da611f3c49cd5bda8d4d916a6428adc2448a4cd2eaeb8e`; `prep_manifest.json` `3234e31bea47402b4d6ef2da1ceb0fe3434e470c707c848dbc538918b2049286`; `0` inventory mismatches |
| Input Parity & Overlaps | **PASS** | `0` SHA diffs across `records/inputs` vs `prep/datasets` and shared `.jsonl` + `split_manifest.json` vs `v4-prep`; `noisy_vs_bitext_test=3`, `noisy_vs_cal=0`, `clean_vs_cal=0`, `clean_vs_eval_total=0` |
| Source Snapshot & Post-Teacher | **PASS** | `0` diffs across `source_snapshot/` vs `run_config.json`, `prep_manifest.json`, and disk; post-fit `orig_fit2` (`reconstructed-fit2-supcon-20261113`) unchanged at `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` |
| Untouched Models / Serving | **PASS** | `zero_delta_control` `904188...`, `prior_2e5` `dc3e88...`, `cand_lr5e6` `b7a285...`, `serving` `dc7af8...`, `fit1` `95a940...` all bit-identical |

---

## 3. Independent 12-Check CAL Guard Reproduction (`T = 1.0`, `tol = 3e-6`)

| # | Check Name | Rule / Limit | Recomputed (`teacher_kl`) | Baseline (`orig_fit2`) | Result |
|---:|---|---|---|---|---|
| 1 | `boundary_pos_cal_correct_count` | `>= 68` | `67 / 86` (`0.779070`) | `68` (`-1`) | **FAIL** |
| 2 | `boundary_pos_cal_sup12_correct_count` | `>= 38` | `37 / 48` (`0.770833`) | `38` (`-1`) | **FAIL** |
| 3 | `bitext_cal_correct_count` | `>= 687` | `689 / 690` (`0.998551`) | `689` (`0`) | **PASS** |
| 4 | `pos_train_added_18_correct_count` | `>= 15` | `18 / 18` (`1.000000`) | `8` (`+10`) | **PASS** |
| 5 | `boundary_pos_cal_sup12_conf_ge_070_count` | `>= 26` | `34` | `28` | **PASS** |
| 6 | `boundary_pos_cal_sup12_conf_ge_080_count` | `>= 24` | `32` | `28` | **PASS** |
| 7 | `boundary_neg_cal_pred_sup12_count` | `<= 9` | `10 / 48` | `9` (`+1`) | **FAIL** |
| 8 | `boundary_pos_cal_delta_mean_max_prob` | `<= 0.015` | `+0.055831` (`0.742175`) | `0.686344` | **FAIL** |
| 9 | `boundary_pos_cal_esc34_delta_mean_max_prob` | `<= 0.015` | `+0.060602` (`0.731564`) | `0.670962` | **FAIL** |
| 10 | `boundary_pos_cal_esc34_max_sup12_mass` | `<= 0.55` | `0.671330` | `0.467362` | **FAIL** |
| 11 | `boundary_neg_cal_max_sup12_mass` | `<= 0.715693` | `0.764955` | `0.715693` | **FAIL** |
| 12 | `boundary_neg_cal_max_single_sup12_prob` | `<= 0.557692` | `0.611628` | `0.557692` | **FAIL** |

---

## 4. Four-Way Paired CAL & Canonical TRAIN Comparison

| Surface (`n`) | Metric | `orig_fit2` | `zero_delta_control` (`+0`) | `prior_2e5` (`+18`, unanchored) | `teacher_kl` (`+18`, `alpha=1`) |
|---|---|---:|---:|---:|---:|
| `pos_cal` (`86`) | Correct / `eval KL` | `68` / `0.0` | `68` / `0.024527` | `68` / `0.054162` | **`67` / `0.061621`** |
| `pos_cal` (`86`) | Right / **Wrong** `mean_max_prob` | `0.732839` / `0.510698` | `0.767703` / `0.501403` | `0.753907` / `0.603560` | **`0.785285` / `0.590154`** |
| `sup12` (`48`) | Correct / Right / Wrong | `38` / `0.739562` / `0.542566` | `38` / `0.772121` / `0.563021` | `38` / `0.772354` / `0.591276` | **`37`** / `0.807993` / `0.557443` |
| `esc34` (`38`) | Correct / `max_sup12_mass` | `30` / `0.467362` | `30` / `0.607555` | `30` / `0.682218` | `30` / **`0.671330`** |
| `esc34` (`38`) | Right / **Wrong** `mean_max_prob` | `0.724323` / `0.470862` | `0.762108` / `0.424381` | `0.730540` / `0.618916` | `0.757279` / **`0.635133`** |
| `bitext_cal` (`690`) | Correct / `mean_max_prob` / `KL` | `689` / `0.977800` / `0.0` | `689` / `0.977043` / `0.001548` | `689` / `0.976676` / `0.001173` | `689` / **`0.979658`** / `0.000800` |
| `neg_cal` (`48`) | `pred_sup12` / `max_mass` / `single` | `9` / `0.715693` / `0.557692` | `9` / `0.734620` / `0.609309` | `10` / `0.733993` / `0.582643` | **`10` / `0.764955` / `0.611628`** |
| `pos_train` (`199`) | Correct / `mean_max_prob` / `KL` | `189` / `0.936206` / `0.0` | `188` / `0.935429` / `0.004622` | `199` / `0.979541` / `0.305938` | `199` / **`0.982391`** / `0.307763` |
| `neg_train` (`99`) | `pred_sup12` / `max_sup12_mass` | `0` / `0.222151` | `0` / `0.218654` | `0` / `0.219649` | `0` / `0.220075` |
| `added_18` (`18`) | Correct / `mean_max_prob` | `8` / `0.504559` | `7` / `0.489361` | `18` / `0.979646` | `18` / **`0.981548`** |

- **CAL Flips vs `orig_fit2`:** `teacher_kl` shares `cls_e34_avonl_cal_1_af025937dd54` (`lost`), `cls_hum_escalate_now_1_58df76a91338` (`lost`, shared with `prior_2e5`), `cls_neg_off_cal_finance_1_c16b2323f38a` + `bnd_neg_homonym_cal_0_b32c79aceec4` (`entered_sup12`), and `cls_neg_cmi_cal_pay_inv_pinfo_2_ed26ede4b742` (`exited_sup12`), while failing to recover `cls_dtm_pre_order_eta_0_0ab138c43752` (`+1` gained only in `prior_2e5`, leaving `teacher_kl` net `-1`).

---

## 5. Read-Only Objective & Synthetic/Mocked Gradient Probe Audit

### 5.1 Code vs Worker B Profile (`train_boundary_candidate.py` & `run_orig_fit2_return_contrast_fit.py`)
- **KL formulation & scaling (`lines 770-794`):** `F.kl_div(F.log_softmax(student/1.0), F.softmax(teacher.detach()/1.0), reduction="none").sum(-1)` computes exact forward `KL(p_teacher || p_student)` (`>= 0`), normalized by `active_count` (`13,000` masked `1`, `80` `orig_ret_ch_*` masked `0`), added with `teacher_kl_weight = 1.0`.
- **Mask & loop ordering (`lines 687-767, 1188-1263`):** `build_teacher_anchor_mask` indexes `pos_train` -> `bitext_clean + bitext_noisy` -> `neg_train` (`resolved_neg_reps`), matching `train_texts` 1-for-1 (`13,000` anchored, `80` excluded per epoch; logged `anchor_rows_seen=13000`, `excluded_rows_seen=80`). `neg_rng = Random(42+99)` and `DataLoader(..., generator=seed 42)` preserve exact `prior_2e5` `13,080`-row / `409`-batch / `1,227`-step order.
- **Mode & Teacher/Student setup (`lines 797-832, 1248-1250`):** `teacher_model` has `requires_grad_(False)`, `.eval()` inside every epoch, identical `46`-class `id2label` & `tokenizer.json`; student `model` runs in `.train()`. **No implementation defects found.**

### 5.2 In-Memory Forward/Backward Gradient Probes (`16` real Stage-2 batches, `0` optimizer steps)

| Metric (mean across `16` batches, `bs=32`) | Step 0 (`student == teacher == orig_fit2`) | Final (`fit2-orig-teacher-kl-v1`) |
|---|---:|---:|
| `KL(teacher.eval \|\| student.eval)` (true drift) | `1.19e-9` | `0.001204` |
| `KL(teacher.eval \|\| student.train)` (dropout active) | `0.004892` (logged Ep1 `0.004617`) | `0.003348` (logged Ep3 `0.003476`) |
| Dropout share of `.train()` KL | `0.004892` (**`100.0%`**) | `0.002144` (**`64.0%`**) |
| Teacher `.eval()` / Student `.eval()` / Student `.train()` entropy | `0.492339` / `0.492339` / **`0.557460`** | `0.492339` / **`0.478472`** / `0.527011` |
| `l_pos` / `l_sc` / `l_neg` | `0.267588` / `0.085528` / `0.009385` | `0.253829` / `0.080992` / `0.009032` |
| `\|\|grad(base)\|\|_2` / `\|\|grad(teacher_kl)\|\|_2` (ratio) | `0.939228` / `0.375948` (`0.400`) | `0.587365` / `0.260715` (`0.444`) |
| **`cos(grad_base, grad_tkl)`** | **`+0.475929`** | **`+0.291191`** |

- **Observed Facts:** (1) At step 0, teacher and student `.eval()` outputs are identical (`1.19e-9`), so the entire `~0.0046-0.0049` Epoch-1 KL comes from **student dropout (`0.557` vs `0.492` entropy) vs deterministic `teacher.eval()`**; (2) `grad(teacher_kl)` has **positive** cosine (`+0.476`) with `grad(CE+SupCon+Neg)`, pushing student weights slightly **sharper** (`eval entropy 0.492339 -> 0.478472`, `bitext_cal` prob `0.9778 -> 0.9797`); (3) on out-of-sample `pos_cal` and `neg_cal`, `teacher_kl` drifted **further** from `orig_fit2` (`pos_cal KL=0.061621`) than unanchored `prior_2e5` (`0.054162`).
- **Hypothesis (distinct from universal KL claim):** Anchoring a `.train()` student (`dropout=0.1`) toward a deterministic, already near-one-hot (`T=1.0`) `.eval()` teacher on Stage-2 training data rewards dropout-compensated over-sharpening rather than preserving off-manifold CAL boundaries under `lr=2e-5` full-backbone updates. This does **not** prove logit/embedding anchoring universally cannot help (e.g., frozen-encoder or deterministic dropout-free hidden/logit matching avoids this failure mode).

---

## 6. CAL Metric Limitation Note & Minimal Next Proposal (Stop Further Fits)

- **CAL `delta_mean_max_prob <= 0.015` Limitation (Without Relaxing Frozen Gate):** Pooling `all_mean_max_prob` mixes welcome correct-prediction confidence (`sup12` `conf>=0.80`: `28 -> 32`, `correct_mean_max_prob` `+0.068431`) with harmful wrong-prediction confidence. However, **even if `delta_mean_max_prob` were split**, `fit2-orig-teacher-kl-v1` still **fails** both accuracy floors (`67/86 < 68`, `37/48 < 38`), `neg_cal pred_sup12` (`10 > 9`), `esc34` **wrong** confidence (`+0.164271`), `esc34 max_sup12_mass` (`0.671330 > 0.55`), and `neg_cal` mass/single ceilings — so no gate relaxation is warranted and the frozen 12-check protocol remains binding.
- **Stop Further Optimizer Fits / Alpha-LR Sweeps.** Pending coordinator review, minimal non-compound paths starting cleanly from `orig_fit2` (`f695...`) are:
  1. **Constrained Adapter / Frozen-Encoder Head Adaptation:** Freeze all `6` DistilBERT transformer layers of `orig_fit2` (preventing canonical `esc34`/`neg` representation drift) and train only the classifier head (with L2 weight tether to `orig_fit2` head) or a single low-rank adapter on `+18` contrast + replay; or
  2. **CAL-Only Bounded Post-Hoc Calibration / Rejector (`0` weight mutation):** Evaluate bounded `T > 1.0` and/or the built-in `selective_rejector` (`logit_geometry_v1`) on frozen `orig_fit2` (`f695...`) to check boundary separation without mutating backbone weights (cannot improve raw base accuracy on `added_18`, which stays `8/18`).
