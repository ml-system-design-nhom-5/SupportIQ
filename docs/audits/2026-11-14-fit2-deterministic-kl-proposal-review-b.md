# Worker B Design Review: Deterministic-Student Masked Teacher-KL (`eval` KL Forward, Autograd ON)

- **Date:** 2026-11-14
- **Branch / Base Commit:** `minh` @ `8453899f246258da9aeda5b9c0244c55e0dfb682` ([2026-11-14-fit2-teacher-kl-cal-review-c.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-teacher-kl-cal-review-c.md))
- **Verdict:** **PASS (Bounded Single-Factor Design Review Only — NOT prep/fit authorization)**
- **Authorized Actions Here:** `0` implementation edits, `0` preps, `0` optimizer updates, `0` CAL/holdout runs. Rejected `fit2-orig-teacher-kl-v1` (`CAL 4/12 PASS, 8/12 FAIL`) remains untouched; Original Fit2 (`reconstructed-fit2-supcon-20261113`, `f695b1fe...`) remains the sole active base checkpoint.

---

## 1. Decision Scope & Preserved Invariants

- **Single minimal change evaluated:** Keep base `pos_ce + supcon + neg_loss` on the original stochastic `model.train()` forward unchanged; move **only** `KL(p_teacher || p_student)` onto a separate **deterministic student forward** (`model.eval()` temporarily inside `try/finally` per forward, **autograd enabled**, `output_hidden_states=False`, logits only), while frozen `teacher` stays in `.eval()` + `torch.no_grad()`.
- **Locked parameters (unchanged, zero bundling):** `alpha_kl = 1.0`, `T_teacher = 1.0`, `orig_fit2` (`f695b1fe...`) as both student init and frozen teacher, `18` added TRAIN return-contrast rows (`13,000` canonical replay anchored `m_i = 1`, `80` `orig_ret_ch_*` excluded `m_i = 0`), `epochs = 3`, `lr = 2e-5`, `batch_size = 32`, `seed = 42`, `fit_mode = "fit2_supcon_energy"`, `min_temperature = 1.0`, `enable_selective_rejector = False`. No encoder freeze, no logit L2/margin, no base-profile mutation (`option_a`, `lr5e6`, `zero_delta_control` untouched), no alpha/LR sweep.
- **Unchanged governance & disclosures:** All `12` CAL guards, Worker C full evaluation protocol, rejected-candidate records (`fit2-orig-teacher-kl-v1`), historical `3` `bitext_train_noisy` vs eval exact-norm overlaps (`exclude_noisy_test_overlap: false`), and one-seed (`seed=42`) limit remain binding. A PASS here does **not** promise zero CAL/OOD regressions.

---

## 2. Feasibility, Autograd Graph, RNG & Memory Assessment

Probed empirically on `f695b1fe` (`NVIDIA GeForce RTX 5060`, `8,150.6 MB` VRAM, `bs=32`, `0` optimizer updates via read-only autograd script):

| Check | Measured Evidence on `DistilBertForSequenceClassification` | Result |
| --- | --- | --- |
| **Module / BN Safety** | Module inventory has `Dropout`, `LayerNorm`, `Linear`, `Embedding`, `Embeddings`, `GELUActivation`, `FFN`, `Transformer*`; **`has_batchnorm = False`**, `has_dropout = True`, sole buffer = static `distilbert.embeddings.position_ids`. Temporary `.eval()` alters only dropout masks—zero running-stat corruption. | **SAFE** |
| **Nested Mode & Exception Restore** | Snapshot `{m: m.training for m in model.modules()}` before `model.eval()`, restoring in `finally: for m, flag in saved.items(): m.train(flag)`, restores custom child `.training` states even on injected exception (`all_train_restored = True`, `exception_restore_ok = True`). | **SAFE** |
| **RNG Preservation** | Placing base stochastic `model.train()` forward first, then deterministic student forward + backward consumes **0** `torch` CPU RNG, **0** CUDA RNG, **0** `numpy` RNG, and **0** `random` RNG (`rng_det_fwd_*_unchanged = True`, `rng_det_bwd_*_unchanged = True`). Base stochastic dropout/shuffle sequence stays identical to unanchored `option_a`. | **SAFE** |
| **Dual-Graph VRAM & Compute** | Holding stochastic `out` (`output_hidden_states=True`) + deterministic `det_out` (`output_hidden_states=False`) + frozen teacher (`no_grad()`) peaks at **`1,786.9 MB`** allocated CUDA (`21.9%` of `8,150.6 MB`; `+597.0 MB` vs `1,189.9 MB` single-graph, `> 6.3 GB` headroom). Step cost increases from ~`2` to ~`3` model forwards (`output_hidden_states=False` avoids redundant hidden activation copies). | **SAFE** |

---

## 3. Objective Evidence & Counterevidence Caveat (`0` Optimizer Steps)

Read-only forward/backward gradient probes across `8` real Stage-2 batches (`bs=32`, deterministic vs stochastic anchor at `alpha_kl = 1.0`, `T = 1.0`):

| Checkpoint Probed (`8` Stage-2 batches) | `mean_det_kl` | `mean_stoch_kl` | `mean_grad_base` | `mean_grad_stoch` (`cos` vs base) | `mean_grad_det` (`cos` vs base) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `step0_orig_fit2` (`f695 == teacher`) | **`2.18e-9`** | `0.003861` | `0.656001` | `0.163320` (**`+0.4736`**) | **`4.73e-7`** (`+0.0093`) |
| `drifted_zero_delta_control` (`904188aa`) | `0.001241` | `0.004371` | `0.277378` | `0.104104` (`+0.3925`) | `0.030905` (**`-0.0853`**) |
| `drifted_prior_2e5` (`dc3e`) | `0.001548` | `0.004958` | `0.299229` | `0.224052` (`+0.5223`) | `0.093204` (`+0.0694`) |

- **What supports deterministic anchor (`PASS` rationale):** Worker C's 16-batch audit established that `student.train()` dropout vs `teacher.eval()` generated step-0 `KL = 0.004892` and `+0.4759` gradient sharpening (`final eval entropy 0.478472 < 0.492339`), worsening CAL (`+0.055831` vs `prior_2e5 +0.036095`). Switching only the KL branch to deterministic student `.eval()` eliminates that artificial step-0 bias cleanly (`2.18e-9` KL, `4.73e-7` grad norm).
- **Important counterevidence / caveat (why fix is NOT guaranteed):** Probes are evidence, **not** proof of exclusive cause or guaranteed CAL pass:
  1. At `step 0`, deterministic `grad_det ≈ 0`, so base stochastic `pos_ce + supcon + neg_loss` (`0.656`) drives initial steps unopposed until weights drift away from `f695`.
  2. Even at `zero_delta_control` (which fails `5/11` CAL float checks) and `prior_2e5`, saturated `f695` Stage-2 positives yield `mean_det_kl` of only `0.001241–0.001548` (`||grad_det||` = `11.1%–31.1%` of `||grad_base||` at `alpha_kl = 1.0`), and `cos` at `prior_2e5` is `+0.0694`.
  3. **Stop condition:** If this single deterministic-KL fit still fails CAL, do **not** run alpha/LR sweeps — pivot directly to Worker C's frozen-6-layer encoder + tethered head/adapter proposal from `f695b1fe`.

---

## 4. Exact Objective, Minimal Hook & Five Required Unit Tests

### Objective & Minimal Code Hook (`pipeline/training/train_boundary_candidate.py`)
$$\mathcal{L}_{\mathrm{total}} = \underbrace{\mathcal{L}_{\mathrm{pos\_ce}} + 0.25\,\mathcal{L}_{\mathrm{supcon}} + \mathcal{L}_{\mathrm{neg}}}_{\text{from stochastic } \texttt{model.train()} \text{ forward } \texttt{out}} + 1.0 \cdot \underbrace{\frac{\sum_{i=1}^{B} m_i\,\mathrm{KL}(p_{T,i} \| p_{S,\mathrm{det},i})}{\sum_{i=1}^{B} m_i}}_{\text{from deterministic } \texttt{model.eval()} \text{ forward } \texttt{det\_logits} \text{ (autograd ON)}}$$
- Helper `_forward_student_logits_eval_mode(model, input_ids, attention_mask)`: snapshots `{m: m.training for m in model.modules()}`, enters `model.eval()`, runs inside explicit `torch.enable_grad()` with `output_hidden_states=False`, returns `.logits`, restores all module `.training` flags in `finally:`.
- Inside `run_fit_and_lock_candidate` (`1299-1312`): keep `out` (`model.train()`) and all base losses strictly unchanged; guard `if teacher_model is not None:` cleanly — if `(batch["teacher_anchor_mask"] > 0).any()`, run `teacher_model` inside `torch.no_grad()` and `det_student_logits = _forward_student_logits_eval_mode(...)`, then pass `det_student_logits` to `compute_masked_teacher_kl_loss(...)`; if `active_count == 0`, return `0.0` without extra forward/graph (`slice_equiv_diff = 0.0`).
- **Provenance & Opt-In Profile Isolation (`run_orig_fit2_return_contrast_prep.py` / `fit.py`):** Sealed `run-records-fit2-orig-teacher-kl-v1-prep` and `fit2-orig-teacher-kl-v1` must **not** be overwritten; new prep/fit run must use a fresh `run_id` (e.g. `fit2-orig-teacher-kl-det-v1`), opt-in profile flag (`teacher_student_anchor_mode: "eval_no_dropout_autograd_enabled"` or dedicated profile `option_a_teacher_kl_det`), fail-closed `prep_manifest` / `run_config` / `training_lineage` recording, and untouched `option_a` / `lr5e6` / `zero_delta_control`.

### Five Focused Unit Tests Required Before Prep/Fit
1. **`init_identity_anchor_zero_and_zero_anchor_grad`:** With dropout modules present and `student == teacher`, deterministic student-eval KL yields `< 1e-7` and student parameter `.grad` norm `< 1e-6` (whereas `.train()` anchor yields strictly positive KL & grad).
2. **`perturbed_student_anchor_positive_and_gradient_toward_teacher`:** On perturbed weights (`student != teacher`), deterministic KL is `> 1e-4`, repeatable across two calls (`diff == 0.0`), and gradient moves `student` toward `teacher` (`(theta_s - theta_t) · grad_det > 0` / one-step KL decrease).
3. **`mask_all_added_empty_zero`:** Batch with `anchor_mask == 0` for all rows (`active_count == 0`) produces finite scalar `0.0` loss, zero student gradients from KL, and retains exact `13,000` anchor / `80` `orig_ret_ch_*` exclusion coverage.
4. **`base_ce_forward_rng_modes_unchanged_and_exception_restore`:** Running deterministic anchor forward + backward consumes `0` `torch` CPU/CUDA RNG, leaves base stochastic forward logits/CE/SupCon/Neg identical to unanchored execution, and restores nested child `.training` flags cleanly after both normal return and raised exception inside `finally:`.
5. **`no_grad_only_teacher_and_profile_archive_forward_flags`:** Only `teacher_model` runs in `torch.no_grad()` (`requires_grad=False`, weights unchanged); `det_student_logits` preserves `grad_fn` (`loss.requires_grad is True`); and opt-in profile / `prep_manifest.json` (`teacher_anchor_config`) / `run_config.json` / `candidate_provenance_manifest.json` (`training_lineage`) fail-closed forward the deterministic anchor flag while keeping base profiles untouched.
