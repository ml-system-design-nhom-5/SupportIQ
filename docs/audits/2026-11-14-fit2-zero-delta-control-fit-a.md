# Fit2 Matched Zero-Delta Control Fit Audit (Worker A)

- **Scope & Status:** Scientific **zero-delta control execution** (`fits_executed: 1`, `is_promotion_candidate: false`, `cal_guard_passed: false`, `cal_guard_status: "CONTROL_CAL_DRIFT_OR_REGRESSION_DETECTED"`). Not a promotion candidate; zero production acceptance claims; Original Fit2 remains the active baseline anchor.
- **Run ID / Profile:** `fit2-orig-zero-delta-control-v1` / `option_a` (`epochs=3, lr=2e-5, batch_size=32, seed=42, fit_mode="fit2_supcon_energy", min_temperature=1.0, enable_selective_rejector=False`)
- **Hardware & Timing:** `NVIDIA GeForce RTX 5060` (`cuda`); `train_seconds = 109.48` s; wall-clock run `2026-11-14T20:49:21.4537833+07:00` to `2026-11-14T20:51:42.6184764+07:00` (`141.16` s end-to-end).

---

## 1. Exact Lineage, Archive Paths & SHA-256 Inventory

- **Execution Git Commit (`HEAD` at fit):** `b58b6eb94f5825fc563bba274249dd0132e48916` (ancestor prep code commit `118196095ee040d3606fc6960a2fa94ae8d89957`; prep doc commit `2c4ca1755b72a5b94fcc6a3d83fc9cb6ff8cc937`)
- **Immutable Prep Bundle:** [`artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1-prep`](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1-prep)
  - `prep_manifest.json`: `5ad2f3eb888979e6cd913850aa423c77cae1cc60b345b3326ee17fa0c7aa3b92` (`orig_fit2_zero_delta_control_prep.v1`)
  - `sidecar_sha_inventory.json`: `0200ab011fd5afdf280c0c1c1dac5e46d85a81fe381e5ef9bc39d599b7c3952c`
- **Initializer / Serving Anchors (Untouched):**
  - Initializer (`reconstructed-fit2-supcon-20261113`): `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (`T=1.0`, `rejector=False`, `46` labels)
  - Serving model: `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`
- **Archived Model Directory:** [`artifacts/models/candidates/fit2-orig-zero-delta-control-v1`](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/fit2-orig-zero-delta-control-v1) (`archive_sha_inventory.json`: `ab01eb821e47923018adfbb6269ecdef1201ef21a1c58b6b7638cdabd8e3f337`, `6` files verified; `reload_verified=true`, `46` labels)
  - `model.safetensors`: `904188aab6cb45d1150cbd5f0890ee06a1732177d0c7b2c62e43d54a05ffc0ee`
  - `calibration_manifest.json`: `70e86f044d3f2f496bc5682e472a35e64d60ab4b51a2e6ade2757b75140c2c5e` (`temperature: 1.0`, `min_temperature: 1.0`, `selective_rejector.enabled: false`, `calibration_sample_count: 776`)
  - `candidate_provenance_manifest.json`: `5e795138ce45525b0659978055d44a693fd5b67fb101624c459b6c21e0559f7c` (`token_truncation_audit.train_all.count: 11320`, `train_total_examples: 13000`)
  - `config.json`: `6fa1fa9cc6a94063a977b0adaf2c9c3b296cf296d4ad9dcc6f2c52ca3bac9cb2`
  - `tokenizer.json`: `41b9d12a4c559e4098f30173bc0f76d092c43d7b1f873e7027da45a256f30f87`
  - `tokenizer_config.json`: `15c067a68c4f12b2019e3a892c1158d4735544703fa496f2a6b73242b5812d84`
- **Archived Run-Records Directory:** [`artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1`](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1) (`sidecar_sha_inventory.json`: `df5e33b608516763bfd29cfe8a13c316b832170c3b7b0ba49aa9f4d9c1e6b5f1`, `40` files verified)
  - `status.json`: `32a8872b9b4e8350747dca07466bdb3901e914f16554d0aee01a6d8db7106190`
  - `cal_guard_report.json`: `4224d16e6f7d3dde6f2c87b64ea61e89d4c1ef6afb1efb6ee8691eb3d2f3e4c3`
  - `fit_result.json`: `a75c784430fe9ffb5a2e01b317602bc54091e60ab57c7ac057bf00585e2ff3fa`
  - `run_config.json`: `793445f05223daaef10c3e2ca4d18d71d5bdff4929015a503c4d4aa044420488`
  - `environment.json`: `6fae7ff00eb23e7e59a1f3e45e3d7cf890c24f3ea1713e358823f24318287bb1`
  - `run.log`: `7361b0367c2bf8a94088620627dfa2f92b8a560b061fce6a67570c4b8102f74e`
- **Training Epoch Summary (`407` batches/epoch, `1,221` total steps, `13,000` effective examples):**
  - Epoch 1: `mean_loss=0.35475`, `pos=0.25548`, `neg=0.00865`, `supcon=0.09062`
  - Epoch 2: `mean_loss=0.35094`, `pos=0.25139`, `neg=0.00840`, `supcon=0.09115`
  - Epoch 3: `mean_loss=0.34606`, `pos=0.24990`, `neg=0.00849`, `supcon=0.08766`

---

## 2. Control CAL Guard Result (All 11 Checks, Full Precision)

Evaluated in `matched_zero_delta_control_11_checks` mode (`pos_train_added_18_correct_count` omitted by design because `0` rows were added; `float_tolerance = 3e-06`): **6 integer checks PASSED, 5 float drift/ceiling checks FAILED**.

| # | Check Name | Kind | Actual (Full Precision) | Rule / Limit (`tol=3e-6`) | Passed |
| --- | --- | --- | --- | --- | --- |
| 1 | `boundary_pos_cal_correct_count` | integer | `68` | `>= 68` | `true` |
| 2 | `boundary_pos_cal_sup12_correct_count` | integer | `38` | `>= 38` | `true` |
| 3 | `bitext_cal_correct_count` | integer | `689` | `>= 687` | `true` |
| 4 | `boundary_pos_cal_sup12_conf_ge_070_count` | integer | `31` | `>= 26` | `true` |
| 5 | `boundary_pos_cal_sup12_conf_ge_080_count` | integer | `29` | `>= 24` | `true` |
| 6 | `boundary_neg_cal_pred_sup12_count` | integer | `9` | `<= 9` | `true` |
| 7 | `boundary_pos_cal_delta_mean_max_prob` | float | `0.025621808049262507` | `<= 0.015` | **`false`** |
| 8 | `boundary_pos_cal_esc34_delta_mean_max_prob` | float | `0.02004519303022334` | `<= 0.015` | **`false`** |
| 9 | `boundary_pos_cal_esc34_max_sup12_mass` | float | `0.60755485796946` | `<= 0.55` | **`false`** |
| 10 | `boundary_neg_cal_max_sup12_mass` | float | `0.7346201406401383` | `<= 0.7156928153564155` | **`false`** |
| 11 | `boundary_neg_cal_max_single_sup12_prob` | float | `0.6093085283593994` | `<= 0.5576920642670788` | **`false`** |

---

## 3. Read-Only Paired CAL & TRAIN Attribution Evidence (`orig_fit2` / `control` / `prior_2e5` / `cand_lr5e6`)

All 4 checkpoints evaluated post-`T=1.0` float64 softmax on identical frozen splits (no holdouts, no OOD suites, no LLM calls).

### 3A. Paired CAL Surfaces (`boundary_pos_cal` 86, `sup12` 48, `esc34` 38, `bitext_cal` 690, `boundary_neg_cal` 48)

| Surface / Metric | `orig_fit2` (`f695b1fe`) | `zero_delta_control` (`904188aa`, 0 added) | `prior_2e5` (`dc3e88e7`, +18 rows) | `cand_lr5e6` (`b7a28547`, +18 rows) |
| --- | --- | --- | --- | --- |
| `boundary_pos_cal` correct / 86 | `68` (`0.7906976744186046`) | `68` (`0.7906976744186046`) | `68` (`0.7906976744186046`) | `66` (`0.7674418604651163`) |
| `boundary_pos_cal` `all_mean_max_prob` (Δ vs orig) | `0.6863441951590312` | `0.7119660032082937` (`+0.025621808049262507`) | `0.7224391229709458` (`+0.03609492781191459`) | `0.7246390920091725` (`+0.03829489685014131`) |
| `boundary_pos_cal` `correct_mean_max_prob` (Δ) | `0.7328388661591876` | `0.767703303616882` (`+0.03486443745769441`) | `0.7539070422918969` (`+0.021068176132709282`) | `0.7719436260508503` (`+0.03910475989166273`) |
| `boundary_pos_cal` `incorrect_mean_max_prob` (Δ) | `0.5106976602695513` | `0.5014028683314041` (`-0.009294791938147196`) | `0.6035603166473528` (`+0.09286265637780144`) | `0.5685341296716355` (`+0.0578364694020842`) |
| `boundary_pos_cal` `mean_true_class_prob` (Δ) | `0.5922213868664987` | `0.6152443634173067` (`+0.023022976550807983`) | `0.6063380563174859` (`+0.014116669450987218`) | `0.6074497338892467` (`+0.015228347022748001`) |
| `sup12` correct / 48; conf `>=0.70` / `>=0.80` | `38`; `28` / `28` | `38`; `31` / `29` | `38`; `34` / `29` | `36`; `33` / `29` |
| `sup12` `all_mean_max_prob` | `0.6985214117078845` | `0.7285580399805526` | `0.7346296615436455` | `0.7373812424742581` |
| `sup12` `correct_mean_max_prob` / `incorrect_mean_max_prob` | `0.7395622070706708` / `0.5425663893292954` | `0.7721205077857803` / `0.5630206623206865` | `0.7723544289729711` / `0.591275545312208` | `0.8011990294928333` / `0.5459278814185328` |
| `sup12` `mean_true_class_prob` / `mean_sup12_mass` | `0.5912948319964139` / `0.7658830509685389` | `0.6147585974865614` / `0.7830134887168589` | `0.6147733012449083` / `0.7858171150436662` | `0.612860160355372` / `0.7908943071311758` |
| `esc34` correct / 38 | `30` (`0.7894736842105263`) | `30` (`0.7894736842105263`) | `30` (`0.7894736842105263`) | `30` (`0.7894736842105263`) |
| `esc34` `all_mean_max_prob` (Δ vs orig) | `0.6709624479394273` | `0.6910076409696506` (`+0.02004519303022334`) | `0.7070405479317463` (`+0.036078099992319035`) | `0.7085437440532749` (`+0.03758129611384764`) |
| `esc34` `correct_mean_max_prob` (Δ) | `0.7243226343379755` | `0.7621081783362772` (`+0.037785543998301696`) | `0.7305403524958692` (`+0.006217718157893737`) | `0.7368371419204709` (`+0.012514507582495393`) |
| `esc34` `incorrect_mean_max_prob` (Δ) | `0.4708617489448713` | `0.4243806258448011` (`-0.04648112310007024`) | `0.618916280816284` (`+0.1480545318714127`) | `0.6024435020512899` (`+0.13158175310641862`) |
| `esc34` `mean_true_class_prob` / `mean_sup12_mass` | `0.5933917719655531` / `0.08869418751013373` | `0.6158579624877218` / `0.0886888256941839` | `0.5956830100933735` / `0.0859065237994977` | `0.6006155109846675` / `0.079111126486014` |
| `esc34` `max_sup12_mass` | `0.4673615502178657` | `0.60755485796946` | `0.6822182090509582` | `0.4914717523196043` |
| `bitext_cal` correct / 690; `all_mean_max_prob` | `689`; `0.9778003038188137` | `689`; `0.9770432378567615` | `689`; `0.9766763325486254` | `689`; `0.977113477424977` |
| `boundary_neg_cal` `pred_sup12_count` / 48 | `9` | `9` | `10` | `11` |
| `boundary_neg_cal` `max_sup12_mass` / `mean_sup12_mass` | `0.7156928153564155` / `0.2484005192110247` | `0.7346201406401383` / `0.247651294016162` | `0.7339925073067534` / `0.25061020306174653` | `0.7451280811564883` / `0.25890843078676584` |
| `boundary_neg_cal` `max_single_sup12_prob` | `0.5576920642670788` | `0.6093085283593994` | `0.5826426842333712` | `0.5895935447263043` |

### 3B. Paired Canonical TRAIN Surfaces (`boundary_pos_train` 181, `boundary_neg_train` 99, plus read-only `ext_18` probe)

| Surface / Metric | `orig_fit2` (`f695b1fe`) | `zero_delta_control` (`904188aa`, 0 added) | `prior_2e5` (`dc3e88e7`, +18 trained) | `cand_lr5e6` (`b7a28547`, +18 trained) |
| --- | --- | --- | --- | --- |
| `pos_train_181` correct / 181; `mean_true_class_prob` | `181`; `0.9791324222269725` | `181`; `0.9797894369997584` | `181`; `0.9795309702323629` | `181`; `0.9797817510634689` |
| `pos_train_sup12` (133) `mean_true_class_prob` / `mean_sup12_mass` | `0.9794542520935886` / `0.9852338365133545` | `0.9799459186979909` / `0.9851932532113716` | `0.9796263749244628` / `0.9848916502113333` | `0.9800464967976016` / `0.9854366211049507` |
| `pos_train_esc34` (48) `mean_true_class_prob` / `mean_sup12_mass` | `0.9782406853048898` / `0.005862140060089086` | `0.9793558522942396` / `0.005563631950179671` | `0.9792666197313368` / `0.005540173544495346` | `0.9790481847584767` / `0.0056128774947892535` |
| `neg_train_99` `pred_sup12_count` / 99 | `0` | `0` | `0` | `0` |
| `neg_train_99` `max_sup12_mass` / `max_single_sup12_prob` | `0.22215113660198132` / `0.01930752524173135` | `0.2186541591516796` / `0.01856457140678965` | `0.21964879594142578` / `0.01853783457695493` | `0.2211193395947335` / `0.018897560961453355` |
| `ext_18` read-only probe (`return_policy` 10 + `store` 8) | `8/18` (`8/10` + `0/8`); `mmp=0.5045588112063999` | `7/18` (`7/10` + `0/8`); `mmp=0.48936061719377055` | `18/18` (`10/10` + `8/8`); `mmp=0.9796458406223894` | `18/18` (`10/10` + `8/8`); `mmp=0.9779935172352408` |

---

## 4. Scientific Interpretation, Prep Doc Correction & Explicit Limits

- **Correction to [2026-11-14-fit2-zero-delta-control-prep-a.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-zero-delta-control-prep-a.md) Section 3 (sealed prep doc left unmodified):** Section 3 of the prior prep doc framed this control in overly binary causal language (suggesting a control failure would isolate continuation optimization as *the* cause rather than the `+18` rows). That wording is stronger than a single matched run can support.
- **What This Run Establishes:** Continuing from converged `f695b1fe` for `3` extra epochs at `lr=2e-5` (seed `42`) with **zero added rows** (`11,320` rows / `13,000` effective) **is sufficient** in this seed/run to trigger all `5` float drift/ceiling failures (`CONTROL_CAL_DRIFT_OR_REGRESSION_DETECTED`), including higher `boundary_neg_cal max_single_sup12_prob` (`0.609309`) than both `prior_2e5` (`0.582643`) and `cand_lr5e6` (`0.589594`).
- **What This Run Does NOT Prove / Non-Identical Mechanics & Limits:**
  1. **Does not prove unique causation or rule out 18-row contribution/interaction:** The paired breakdown shows clear mechanistic differences between `zero_delta_control` and the `+18`-row runs (`prior_2e5` / `cand_lr5e6`): `zero_delta_control` held `boundary_neg_cal pred_sup12_count = 9` and reduced `esc34` `incorrect_mean_max_prob` (`-0.046481`), whereas `prior_2e5` increased `neg_cal pred_sup12_count` (`9 -> 10`) and spiked `esc34` `incorrect_mean_max_prob` by `+0.148055` (and `cand_lr5e6` pushed `neg_cal` to `11`, `esc34 incorrect_mean_max_prob` by `+0.131582`, and dropped `sup12` accuracy `38 -> 36`).
  2. **Batch / Step / Shuffle / LR-Slope Differences:** Because [`train_boundary_candidate.py`](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py#L1033-L1037) uses `DataLoader(shuffle=True, generator=seed=42)` and `get_linear_schedule_with_warmup(warmup=int(0.10 * total_steps))`:
     - `zero_delta_control` (`13,000` effective examples) runs `407` batches/epoch (`1,221` total steps, `122` warmup steps, `1,099` linear decay steps).
     - `prior_2e5` / `cand_lr5e6` (`13,080` effective examples) run `409` batches/epoch (`1,227` total steps, `122` warmup steps, `1,105` linear decay steps).
     So batch count, mini-batch shuffle pairing at every step, and LR decay slope all differ slightly between `control` and `+18`-row runs.
  3. **Single-seed / single-run observation:** Tested at `n=1` (`seed=42`, `lr=2e-5`); Worker C independent verification follows next.
