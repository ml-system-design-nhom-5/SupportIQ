# Original Fit2 NER Provisioning Report (Worker A)

- **Date:** 2026-11-15
- **Branch:** `minh`
- **Baseline Parent Commit:** `f7ab5ade7d2f6bcfea03691837886e708e58e45a` (Worker C Gap 3 code closure)
- **Interpreter / Environment:** `F:\Năm 3\SD\project\SupportIQ\.venv\Scripts\python.exe` (`Python 3.12.14`)
- **Scope Guardrails:** Pretrained `spacy` + `en_core_web_sm` provisioning only. No model training, no Fit2 dataset/candidate/pin changes, no CUDA/PyTorch/classifier changes, no paid LLM calls, and no restart of running processes.

## 1. Installed Versions, Model Provenance & Dependency Diff

Installed via the project `.venv` Python (`-m pip install`):
- `spacy==3.8.18`
- `en-core-web-sm==3.8.0` (`license: MIT`, `author: Explosion`, `spacy_version: >=3.8.0,<3.9.0`, `url: https://explosion.ai`)

Model wheel provenance from `.venv/Lib/site-packages/en_core_web_sm-3.8.0.dist-info/direct_url.json`:
- **Source URL:** `https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl`
- **SHA-256:** `1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85`

Pre/post `pip list --format=freeze` comparison in `.venv`:
- **Removed or changed existing packages:** `[]` (0 modified). Core packages verified intact: `torch==2.11.0+cu128`, `transformers==5.22.1`, `numpy==2.5.4`, `pydantic==2.14.1`, `fastapi==0.162.0`.
- **Added packages (17):** `blis==1.3.4`, `catalogue==2.0.10`, `cloudpathlib==0.26.0`, `confection==1.3.4`, `cymem==2.0.16`, `en_core_web_sm==3.8.0`, `murmurhash==1.0.16`, `preshed==3.0.15`, `smart_open==9.0.4`, `spacy-legacy==3.0.12`, `spacy-loggers==1.0.5`, `spacy==3.8.18`, `srsly==2.5.6`, `thinc==8.3.14`, `wasabi==1.1.3`, `weasel==1.0.1`, `wrapt==2.5.2`.

Note on `pip install --dry-run -r apps/backend/requirements.txt`: `spacy==3.8.18` is satisfied; pre-existing `Pillow>=11,<13` vs installed `pillow==13.0.0` was left untouched (outside scope).

## 2. Repeatable Provisioning & Startup/Readiness Diagnostics

- `apps/backend/requirements.txt`: pinned `spacy==3.8.18` and `en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl` (used by `scripts/start-app.ps1` and `.github/workflows/ci.yml`).
- `scripts/native_runtime.py`: added `check_privacy_ner()` and called it in `preflight()` to report NER readiness or missing-model instructions cleanly without blocking manual `-WithoutAI` flows.
- `scripts/start-app.ps1`: when `-not $WithoutAI`, checks `import spacy; spacy.load('en_core_web_sm')` during startup and fails fast with remediation if absent.
- `apps/backend/main.py`: `/health/ready` now reports `"privacy_ner_available": is_privacy_ner_available()`.
- `docs/guides/application-verification.md`: documented repeatable provisioning via `apps/backend/requirements.txt` and CI optional NER smoke (`pytest tests/unit/test_privacy_pii.py -k test_live_spacy`, guarded by `skipif` when unprovisioned).
- `Settings.require_privacy_ner` strict default remains `True` across all non-empty AI service URLs; no environment override to `False` is permitted.

## 3. Verification Proof (Executed Post-Final-Edit)

1. **Focused Privacy, Real-NER, Safety & Preflight Suite (`66 passed, 0 skipped, 0 failed` in `80.04s`):**
   - Command: `.\.venv\Scripts\python.exe -m pytest tests/application/test_gap3_privacy_ner_a.py tests/unit/test_privacy_pii.py tests/application/test_workflow_privacy.py tests/application/test_backend_safety_closure.py tests/unit/test_order_context_grounding.py tests/unit/test_typed_fault_propagation_a.py tests/unit/test_runtime_preflight.py -v --basetemp=tmp/pytest/ner_final_post_lf`
   - Real NER integration PASS: `test_live_spacy_free_form_ner_masking_integration` (previously skipped -> now PASS) and `test_live_spacy_real_ner_names_locations_identifiers_roundtrip_and_limits`.
   - Real NER positive intake -> worker -> MockTransport HTTP E2E PASS (`test_gap3_real_spacy_ner_positive_intake_to_worker_mock_http_e2e`): disposable PostgreSQL + `httpx.MockTransport` (zero external/paid egress), raw PII + mapping keys confirmed absent from outbound JSON, `/health/ready` confirmed `privacy_ner_available is True`, exact reply restoration verified locally.
   - Strict missing-NER & fault fail-closed tests still PASS with model installed (via monkeypatched fault injection): `test_gap3_settings_and_pseudonymize_default_strict`, `test_gap3_strict_default_blocks_egress_when_ner_missing_and_disables_retry`, `test_gap3_ner_exceptions_fail_closed_and_retain_sticky_authority`, `test_preflight_reports_missing_privacy_ner_without_failing_manual_mode`.
   - Worker C's verified 23-case fake-NER matrix in `tests/application/test_gap3_privacy_ner_a.py` remains intact and passing.
2. **Application & E2E Regressions (`49 passed, 0 failed` in `79.32s`):**
   - Command: `$env:PSYCOPG_IMPL="python"; $env:PATH="F:\PostgreSQL\bin;$env:PATH"; .\.venv\Scripts\python.exe -m pytest tests/application/test_application.py tests/e2e/test_full_pipeline.py -q --basetemp=tmp/pytest/ner_app_e2e`
3. **Runtime Preflight & Isolated Fresh Python Process Check (PASS):**
   - `.\.venv\Scripts\python.exe -X utf8 scripts/native_runtime.py preflight` -> exit `0` (`Privacy NER (spaCy en_core_web_sm 3.8.0): ready.`).
   - Isolated fresh Python invocation confirmed `Settings(ai_service_base_url='http://127.0.0.1:8002').require_privacy_ner is True`, `is_privacy_ner_available() is True`, `pseudonymize` masked `'Hi, I am Michael Johnson living in Seattle asking about order ORD-1001.'` -> `'Hi, I am [NAME_1] living in [ADDRESS_1] asking about order [ORDER_ID_1].'`, `validate_egress_payload(..., require_ner=True)` passed, and `restore(...)` returned exact input.

## 4. Empirical Real-NER Behavior & Known Limits

- **Positive masking & roundtrip:** English free-form `PERSON`/`GPE`/`LOC` entities (e.g., `Michael Johnson`, `Seattle`, `Robert Chen`, `Central Park`, `New York`) plus known/identifier patterns mask and restore identically.
- **Negative ordinary order facts:** `"Order placed on 2026-11-10 for 1402000 VND with 30000 VND shipping is in transit."` stayed unmasked (`masked == original`, `map == {}`).
- **Observed `en_core_web_sm==3.8.0` limits (cannot promise 100% free-form PII recall):**
  - Tokens with `len <= 2` (e.g., `WA`) are skipped by `_collect_ner_spans`.
  - Free-form street addresses lacking regex street suffixes can be split by `en_core_web_sm` into `CARDINAL`/`ORG` (e.g., `742 Evergreen Terrace` without `Street`/`St`/...) and missed if absent from DB `known` customer values.
  - Unaccented Vietnamese phrasing can cause false positives (`Xin chao` -> `PERSON`), entity-type swaps (`Da Nang` -> `PERSON`, still masked), or lowercase misses (`anh nam o quan 1`), confirming why strict regex + DB `known` customer metadata remain required alongside NER.

## 5. Runtime Cache Limit & Controlled Restart Requirement

- `apps/backend/tickets/privacy.py` caches `_SPACY_NLP = False` in-process if initial `spacy.load("en_core_web_sm")` fails (`_get_spacy_nlp()`).
- Running background processes started before `.venv` provisioning (`.local/processes.json`: `ai-service` PID `8680` and `backend` PID `36204`, started `2026-11-14T09:58:11Z`) were **not** restarted and will retain any stale cached state until a controlled restart by the coordinator.

## 6. Unchanged Invariant File SHA-256 Digests

- `apps/core_backend/safety.py`: `45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000`
- `apps/core_backend/retrieval/adapter.py`: `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`
- `apps/core_backend/llm/gemini.py`: `c6dd495724472d160f967869ee7553aea2e74a3828bfded8bf45fb39146d865b`
- `apps/ai_service/kb-release.json`: `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804`
- `data/knowledge/approved_kb.v2.json`: `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec`
- `apps/core_backend/config/policies/intent_policy.v2.json`: `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7`
- `.local/training-cap-20261114.json`: `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922`
- `.local/ai.env`: `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87`

## 7. Handoff

Ready for Worker B review, followed by coordinator-authorized controlled local startup smoke (with paid LLM provider blocked) and Worker C operational verification.
