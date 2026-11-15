# Original Fit2 Safety Gap 3 Privacy Code Closure Audit (Worker C)

**Verdict:** `PASS` — **Gap 3 Privacy Code Enforcement Only**  
**Scope Boundary:** This closure verifies privacy/egress code enforcement on branch `minh` (`ce8ff53a5196ea44c513c0dea7c2c8d397830def`). It does **not** certify operational live `spaCy`/`en_core_web_sm` NER recall or whole-project readiness.

---

## 1. Environment & Verification Summary

| Check | Result | Scope / Conditions |
| :--- | :--- | :--- |
| Live `spacy` check | `spacy_spec: False` | Read-only check; `spacy` and `en_core_web_sm` are unprovisioned in `.venv`. |
| Gap 3 & privacy pytest suites | `56 passed, 1 skipped` (`65.61s`) | `test_live_spacy_free_form_ner_masking_integration` skipped due to missing `spaCy`/`en_core_web_sm`. |
| Independent Worker C matrix | `23 / 23 PASS` (`16.16s`) | Pre-frozen JSON spec; isolated disposable PostgreSQL schemas (`DROP CASCADE`), FastAPI `TestClient`, fake NER stubs, `httpx.MockTransport` spies, zero real HTTP/LLM calls. |
| Pinned invariants & `2/2 STOP` | `11 / 11 SHA-256 match`, `0` mismatches | Model checkpoints, KB/policy, `.local/ai.env`, `.local/training-cap-20261114.json` untouched. |

Re-verified `git diff --name-only d3c4c2a0..HEAD -- apps/`: only `apps/backend/platform/config.py`, `apps/backend/tickets/jobs.py`, `apps/backend/tickets/privacy.py`, and `apps/backend/tickets/service.py` changed since Gap 2 (`d3c4c2a0`).

---

## 2. Independent Pre-Frozen 23-Case Matrix Results

Artifact directory: [original_fit2_gap3_privacy_c_20261115](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/original_fit2_gap3_privacy_c_20261115/)  
- Frozen matrix: [frozen_gap3_case_matrix.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/original_fit2_gap3_privacy_c_20261115/frozen_gap3_case_matrix.json) (SHA-256 `67362282cf0770a6dd7e9af3ec63797ea6e78288ec63e5e3562e702c4f33a6e1`)
- Runner: [evaluate_gap3_privacy_c.py](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/original_fit2_gap3_privacy_c_20261115/evaluate_gap3_privacy_c.py) (SHA-256 `3f367f84eff9b51e42cc8b70a46660bb3941c1be013909be2342cadb519b2696`)
- Results: [gap3_privacy_verification.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/original_fit2_gap3_privacy_c_20261115/gap3_privacy_verification.json) (SHA-256 `6e1997ed88e961356e8420a12fbe4879c3ede428c8e1f312fbfe25bd2c6a56d3`)
- Manifest: [run_manifest.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/original_fit2_gap3_privacy_c_20261115/run_manifest.json)

### Group A — Strict Enforcement & Sticky Authority (`6 / 6 PASS`)
- `g3-cfg-strict-default`: `Settings(database_url_app=...)` defaults `require_privacy_ner=True`; rejects `require_privacy_ner=False` with any `ai_service_base_url` (`4` URL shapes tested); env var `SUPPORTIQ_REQUIRE_PRIVACY_NER` rejects `0`, `false`, `no`, `off` and `False` with `ai_service_base_url` (`5` env combinations).
- `g3-intake-missing-ner`, `g3-intake-load-exc`, `g3-intake-runtime-exc`: Fail closed (`draft_status="unavailable"`, `reason_codes=["pseudonymization_failed"]`, `jobs_queued=0`, `audit_outcome="failed"`, `retry_suggestion` absent from `allowed_actions`), zero raw secret leakage in payload/audit.
- `g3-worker-direct-strict`: Direct worker egress fails closed (`0` HTTP calls) across all `4` modes (`none_prod`, `real_httpx_client`, `mock_transport_with_url`, `duck_stub_with_url_and_false_flag`).
- `g3-authority-sticky-manual`: Preserves Gap 2 sticky authority (`staff` direct reply `403`, `submit-proposal` `201`, manager `approve` `201`).

### Group B — Fail-Closed Egress & Forged Queued Jobs (`8 / 8 PASS`, `0` HTTP calls on every negative vector)
- `g3-egress-extra-nested`: Extra/nested keys on queued payload blocked (`0` HTTP).
- `g3-egress-raw-msg-pii` (`8` vectors): Raw email, phone, card, address, `ORDER_ID`, `TRACKING_ID`, `TRANSACTION_ID`, non-string `message` blocked (`0` HTTP).
- `g3-egress-orderctx-pii` (`8` vectors): Raw PII inside `order_context`, unknown keys (`customer_note`, `payment_status`), bool `amount_minor`, extra `order_total` key, bad `placed_at` blocked (`0` HTTP).
- `g3-egress-asof-intent` (`4` vectors): Naive/malformed `as_of`, raw PII or non-string `intent_override` blocked (`0` HTTP).
- `g3-egress-known-db-map`: DB `pseudonym_map` secret (`"Nguyen Thi Lan"`) triggers fail-closed without appearing in stored suggestion payload (`0` HTTP).
- `g3-egress-stale-ner-race`: Intake passes with NER, NER subsequently becomes unavailable before worker execution -> worker aborts (`0` HTTP, `pseudonymization_failed`, `retry_suggestion` disabled).
- `g3-error-no-map-exfil`: Captured `ValueError` strings (`"Unmasked EMAIL detected before egress"`, `"Unmasked PHONE detected before egress"`) contain zero raw PII/secrets.
- `g3-unknown-placeholder-vs-forged`: Unknown non-entity token `[FOOBAR_1]` passes egress while forged DB `[EMAIL_1]` mapping fails closed (`0` HTTP); `[LITERAL_1]` mapping `"[EMAIL_1]"` stays isolated.

### Group C — Positive Masked E2E Transport & Span Integrity (`9 / 9 PASS`)
- `g3-pos-masked-e2e-transport`: Full intake -> worker -> staff console flow makes `2` mocked HTTP calls (`/v1/ai/analyze-ticket`, `/v1/ai/draft-reply`). Outbound wire payload contains `"Hi, I am [NAME_1] in [ADDRESS_1] asking about [ORDER_ID_1]."` and canonical `order_context` keys (`order_status`, `order_total`, `shipment_status`, `shipping_cost`), with zero `pseudonym_map` or raw PII; staff draft cleanly restores `"Hello Tran Minh, order ORD-1001 is shipping."`.
- `g3-pos-ordinary-dates-money`: Non-PII currency/date strings pass through cleanly.
- `g3-span-literal-forgery`: Customer text `Your form showed [EMAIL_1] when I typed alice@example.com` masks cleanly to `Your form showed [LITERAL_1] when I typed [EMAIL_1]` and restores accurately.
- `g3-span-nested-nul-unicode`, `g3-span-p0p1-short-known`, `g3-span-overlapping-address`, `g3-span-gt999-index`, `g3-span-no-recursive-restore`: NUL/Unicode + nested `[[EMAIL_1]]`, short tokens `P0`/`P1`, overlapping `"123 Nguyen Hue Street"` vs `"Hue"`, `>999` indices (`[NAME_1000]`, `[EMAIL_1234]`), and 1-pass non-recursive restore all pass.
- `g3-span-fake-ner-disclaimer`: Confirms `spacy_installed=false` and unprovisioned `require_ner=True` call raises `ValueError` (fail-closed).

---

## 3. Fake-NER Boundary & Remaining Open Items

1. **Operational `spaCy` / `en_core_web_sm` Provisioning & Live Accuracy (`OPEN`):** Fake NER stubs (`_fake_ner_factory`) isolate privacy boundary logic from `spaCy` wheel absence. Real-world free-form person/organization/location recall and runtime latency remain **unmeasured** until `spacy` + `en_core_web_sm` are provisioned in the deployment environment (alongside regex coverage limits noted in [Worker B's review](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-15-original-fit2-safety-gap3-rereview-b.md)).
2. **`order_context` Key Parity (`OPEN`):** `6` allowed keys in `apps/core_backend/llm/gemini.py` vs `10` in `apps/backend/tickets/privacy.py` remain out of Gap 3 scope.
3. **Frontend Lower-Priority Send UX (`OPEN`):** Out of Gap 3 scope.
