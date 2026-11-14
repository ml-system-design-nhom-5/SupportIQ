# Worker B Proposal Review: Single Frozen-Teacher KL Continuation on `f695b1fe`

- **Date:** 2026-11-14
- **Branch / Base Commit:** `minh` @ `f0a53d6dd28bf578c7ec92c79f5721334d2fadca` (`docs/audits/2026-11-14-fit2-zero-delta-control-review-c.md`)
- **Verdict:** **PASS (Proposal Design Only)** — mathematically well-specified, VRAM-safe (`1,189.9 MB / 8,150.6 MB`), non-invasive, and strictly testable. **Zero authorization to run prep or fit**; Worker A implementation + unit tests must land cleanly first, followed by the unchanged 12 CAL guards and Worker C independent full evaluation.

---

## 1. Scope & Non-Changes Preserved

- **Proposal under review:** Single additional term `teacher_kl_weight * KL(p_teacher || p_student)` at `T_teacher = 1.0`, masking **in** only the `13,000` canonical original Fit2 TRAIN replay rows and masking **out** the `80` effective (`18` raw) added return-contrast rows (`orig_ret_ch_*`), using Original Fit2 (`reconstructed-fit2-supcon-20261113`, `f695b1fe`) as both frozen teacher and student initialization under locked `lr=2e-5`, `epochs=3`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"`, `min_temperature=1.0`, `enable_selective_rejector=False`.
- **Unchanged invariants:**
  - Existing default profiles (`option_a`, `lr5e6`, `zero_delta_control`) and `DEFAULT_PREP_PROFILE = "lr5e6"` remain untouched (`teacher_kl_weight = 0.0`, no teacher instantiated).
  - No encoder freeze, no logit L2 / margin loss, no selective rejector (`False`), no temperature calibration change (`min_temperature=1.0`), no grid search / holdout tuning.
  - All `12` CAL guards (`CAL_GUARD_DEFINITION`: `7` integer count gates + `5` float drift/ceiling rules), Worker C independent evaluation protocol, and historical `3` noisy overlap handling (`exclude_noisy_test_overlap=False`) remain unchanged and disclosed.
  - Primary comparators remain `orig_fit2` (`f695b1fe`) and the unanchored `2e-5` continuation `prior_2e5` (`dc3e`), alongside `zero_delta_control` (`904188aa`) and `cand_lr5e6` (`b7a2`).

---

## 2. Plausibility vs Counterevidence

Measured `f695b1fe` behavior across the exact `13,080` effective TRAIN examples from `run-records-fit2-orig-ret-channel-v4-prep/datasets` (`max_length=64`, deterministic `apply_realistic_noise` applied once at dataset build):

| TRAIN Subset | Effective `N` | `f695b1fe` Acc | Wrong Eff `N` | Mean Entropy | Mean Max Prob | Mean `KL(uniform_46 \|\| p)` | Mean / Max `sup12` Mass |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `orig_pos` (`181` raw) | `772` | `1.000000` | `0` | `0.177250` | `0.979077` | `3.861508` | — |
| `bitext_clean` | `7,360` | `0.998641` | `10` | `0.182408` | `0.978254` | `3.795428` | — |
| `bitext_noisy` | `3,680` | `0.999185` | `3` | `0.182183` | `0.978270` | `3.807152` | — |
| `orig_neg_clean` | `891` | — (`0` `sup12`) | — | `3.823419` | `0.023969` | `0.005435` | `0.217677` / `0.222151` |
| `orig_neg_noisy` | `297` | — (`0` `sup12`) | — | `3.823268` | `0.024082` | `0.005595` | `0.217185` / `0.222726` |
| **Canonical Anchor Sum** | **`13,000`** | — | `13` (pos) | — | — | — | — |
| `added_18` (`orig_ret_ch_*`, masked OUT) | `80` | `0.400000` | `48` | `2.189205` | `0.487939` | `1.362893` | — |

### Why It Is Plausible
1. **Fixes the `+0`-row drift observed in `zero_delta_control`:** Worker C (`docs/audits/2026-11-14-fit2-zero-delta-control-review-c.md`) showed `zero_delta_control` (`904188aa`, `+0` added rows) still failed `5/11` CAL float checks (`pos_cal +0.025622`, `esc34 +0.020045`, `esc34 max_sup12_mass 0.607555`, `neg max_sup12_mass 0.734620`, `neg max_single 0.609309`). On canonical TRAIN, `f695b1fe` is already near optimum (`0` `orig_pos` errors, `13/11,040` `bitext` errors, `0/1,188` `neg` `sup12` errors); forward Teacher-KL (`0` at initialization) supplies a quadratic restoring penalty against re-running `pos_ce` + `supcon` + `AdamW` drift.
2. **Eliminates teacher contradiction on the `18` target rows:** Teacher `f695b1fe` gets only `40.0%` effective accuracy (`48/80` wrong; `8/18` unweighted) on `added_18`. Masking `added_18` (`0.61%` of `13,080` rows) to `anchor_mask = 0` keeps their CE/SupCon gradient unopposed by wrong teacher logits.

### Counterevidence & Residual Risks (Must Remain Disclosed)
1. **Different mechanism from `zero_delta_control` CAL wrong-`esc34` drop:** `zero_delta_control` lowered wrong `esc34` CAL `mean_max_prob` (`0.470862 -> 0.424381`, `-0.046481`) while `+18` runs raised it (`+0.148055` at `2e-5`, `+0.131582` at `5e-6`) alongside `neg_cal pred_sup12` regressions (`9 -> 10`, `9 -> 11`). Pinning canonical TRAIN only guarantees resistance to canonical drift; if the `added_18` return-channel representations themselves share features with false `esc34`/`neg_cal` triggers, `added_18` can still perturb CAL or fail adaptation if `alpha_kl` is too rigid.
2. **Mild `orig_neg` tension vs native Fit2 hinge (`0.18`):** Native Fit2 negative KL uses `0.80 * KL(uniform_46 || p_student)` plus `3.0 * relu(sup12_mass - 0.18)^2`. On `orig_neg`, `f695b1fe` is near uniform (`KL(uniform_46 || p_T) ~ 0.0054–0.0056`), yet sits at `mean_sup12_mass ~ 0.217` (`max 0.2227`, above `0.18`). Teacher-KL holds probabilities near `f695b1fe` (`~0.217` sup12 mass), slightly opposing the `0.18` hinge if weighted aggressively.
3. **Preserves `f695b1fe` canonical mistakes & does not prove OOD safety:** Teacher-KL locks in `f695b1fe`'s `13` effective `bitext` errors and CAL boundary (`68/86` pos_cal), and TRAIN/CAL preservation does **not** establish OOD robustness — full holdout suites remain gated solely by Worker C's evaluation.

---

## 3. Exact Mathematical Formulation & Exploratory Coefficient

- **Frozen teacher forward (`T_teacher = 1.0`, locked):**
  - Load `teacher_model` from `init_model_dir` (`f695b1fe`, verified SHA256 == `init_weights_sha256`), set `.eval()`, set `p.requires_grad_(False)` for all parameters, run strictly inside `torch.no_grad()` on the exact same batch `(input_ids, attention_mask)` as the student (`apply_realistic_noise` already materialized inside `_BoundaryDataset`, so noisy `bitext_noisy`/`orig_neg_noisy` inputs match token-for-token without RNG sync).
  - Forward KL at `T_teacher = 1.0`:
    $$p_T = \mathrm{softmax}(z_T), \qquad \mathrm{KL}_i(p_T \| p_S) = \sum_{c=0}^{45} p_{T,i,c}\left(\log p_{T,i,c} - \log p_{S,i,c}\right)$$
    Computed in PyTorch as `F.kl_div(F.log_softmax(logits, dim=-1), teacher_probs, reduction="none").sum(dim=-1)`.
- **Explicit masking & batch normalization:**
  - For batch size `B` and binary mask $m_i \in \{0, 1\}$ (`1` for canonical `13,000` rows, `0` for `added_18` `80` rows):
    $$\mathcal{L}_{\mathrm{tkl}} = \begin{cases} \dfrac{\sum_{i=1}^{B} m_i \, \mathrm{KL}_i(p_T \| p_S)}{\sum_{i=1}^{B} m_i}, & \sum_{i=1}^{B} m_i > 0 \\ 0, & \sum_{i=1}^{B} m_i = 0 \end{cases}$$
  - **Why anchor-masked mean (`sum(m_i * KL_i) / sum(m_i)`) vs `/ B`:** Divides strictly by active anchor rows so per-anchor gradient magnitude stays invariant regardless of how many excluded `added_18` rows land in a shuffled `bs=32` minibatch, while guarding `sum(m_i) == 0` cleanly against `0/0`.
- **Distinct role from native Fit2 negative uniform KL (`train_boundary_candidate.py:1057-1095`):**
  - Native `0.80 * KL(uniform_46 || p_student)` applies **only on `neg_mask`** (`1,188` rows) and pulls toward exact `1/46` (`entropy = 3.828641`); the new `teacher_kl_weight * L_tkl` applies across **all `13,000` canonical pos+neg rows** (not `added_18`) and anchors to `f695b1fe`'s learned 46-way distribution (`entropy ~ 0.18` on positives, `3.823` on negatives).
- **Single fixed a priori coefficient (`alpha_kl = 1.0`, exploratory):**
  - Total batch loss: `total_loss = pos_ce + 0.25 * supcon + neg_loss + 1.0 * L_tkl`.
  - **Rationale (TRAIN/CAL scale parity, zero sweeps):** Base `pos_ce` has weight `1.0` (`~91%` of `13,000` rows, `label_smoothing=0.03`) and native `neg_kl` has weight `0.80` (`~9%` of rows). Setting `alpha_kl = 1.0` at `T_teacher = 1.0` gives exact `1:1` logit-space parity against `pos_ce` drift (`zero_delta_control` failure at `lr=2e-5`) and comparable weight to `0.80` `neg_kl` without multi-factor over-damping (`>= 5.0`) that could starve the `0.61%` (`80/13,080`) `added_18` signal.
  - **Explicit status:** `alpha_kl = 1.0` is an **exploratory a priori baseline**, not tuned or proven optimal over `0.5` or `2.0`. One bounded run cleanly tells whether anchor stability passes CAL guards (`12/12`) and whether `added_18` still reaches `>= 15/18`.

---

## 4. Hardware, Memory & Hook Plan for Worker A

### Measured Hardware / Memory Budget (`analyze_teacher_kl_scale.py`)
- `reconstructed-fit2-supcon-20261113/model.safetensors`: **`267,967,920` bytes** (~268 MB).
- Measured GPU: **`NVIDIA GeForce RTX 5060`**, `8,150.6 MB` total VRAM.
- Peak allocated/reserved 2-model VRAM (`bs=32`, frozen `eval()` teacher + trainable `train()` student + `AdamW` + backward/step): **`1,189.9 MB`** (`14.6%` of VRAM; `> 6.9 GB` headroom).

### Minimal Hook & Provenance Plan
1. **Explicit Provenance-ID Mask (`pipeline/training/train_boundary_candidate.py`):**
   - Identify `added_18` strictly by locked provenance `sample_id` (`orig_ret_ch_*`) read from `data_dir / "orig_fit2_return_contrast_extension.jsonl"` — **never** by fuzzy text matching or unverified heuristics.
   - Extend `_BoundaryDataset.__init__` (`train_boundary_candidate.py:654-667`) with optional `teacher_anchor_mask: Optional[List[int]] = None` (default `1` for backward compatibility). When `teacher_kl_weight > 0.0`, fail closed if `orig_fit2_return_contrast_extension.jsonl` is absent or if effective masked counts deviate from expected provenance (`added_sample_ids` matched `> 0` and all non-matching canonical rows `= 1`; for locked `v4` return-contrast prep: `anchor_effective_count = 13,000`, `excluded_added_effective_count = 80`).
2. **Teacher Forward & Masked KL Loss (`train_boundary_candidate.py:1057-1095`):**
   - Add optional `teacher_kl_weight: float = 0.0`, `teacher_temperature: float = 1.0`, `teacher_model_dir: Optional[Path] = None` (defaulting to `init_model_dir` when `teacher_kl_weight > 0.0`) to `run_fit_and_lock_candidate`. Skip loading a second model completely when `teacher_kl_weight <= 0.0`.
   - Record per-epoch `avg_teacher_kl_loss`, `anchor_rows_seen`, and `excluded_rows_seen` in `epoch_stats`.
   - Extend `training_lineage` (`train_boundary_candidate.py:1228-1262`, persisted to `candidate_provenance_manifest.json`) with `teacher_weights_sha256`, `teacher_kl_weight`, `teacher_temperature`, `teacher_anchor_effective_count`, `teacher_excluded_effective_count`.
3. **Thin Opt-In Profile (`scripts/run_orig_fit2_return_contrast_prep.py` & `scripts/run_orig_fit2_return_contrast_fit.py`):**
   - Add ONE opt-in entry to `AUTHORIZED_FIT_PROFILES`: `"option_a_teacher_kl"` (`lr=2e-5`, `epochs=3`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"`, `min_temperature=1.0`, `enable_selective_rejector=False`, `init_weights_sha256=EXPECTED_FIT2_SHA256`, `teacher_weights_sha256=EXPECTED_FIT2_SHA256`, `teacher_kl_weight=1.0`, `teacher_temperature=1.0`).
   - Update `validate_profile_settings`, `run_authorized_fit`, `run_config.json`, and `prep_manifest.json` so `teacher_kl_weight` and `teacher_temperature` are fail-closed verified against the selected profile and propagated into archival records (`candidate_model_option_a_teacher_kl` + `run-records-<run_id>`). Note: `RELEVANT_SOURCE_PATHS` already includes these files, so Worker A's commit will automatically hash cleanly into `source_hashes`.

### Required Unit Tests for Worker A (Must Pass Before Any Prep/Fit)
1. **Identity check:** Student == Teacher in `eval()` gives `L_tkl < 1e-7` on canonical batches.
2. **Teacher immutability:** After backward + `AdamW` step, all teacher params have `.grad is None` and bitwise-identical weights/SHA256; student params update normally.
3. **Exact mask coverage (`13,000` / `80`) & edge batch guard:** Locked `orig_fit2_return_contrast_extension.jsonl` `sample_id` set produces `80` `anchor=0` and `13,000` `anchor=1` rows; all-zero-mask batch yields finite `0.0` loss (no `NaN`); missing or malformed extension file fails closed.
4. **Default profile isolation:** `option_a`, `lr5e6`, and `zero_delta_control` remain `teacher_kl_weight = 0.0` with no behavior delta; invalid profile `teacher_kl_weight` or `teacher_temperature` fails closed.
5. **Provenance closure:** `candidate_provenance_manifest.json` (`training_lineage`) and `run_config.json` persist `teacher_weights_sha256`, `teacher_kl_weight`, `teacher_temperature`, and anchor/excluded counts.
