# SupportIQ ML Inference Service

This service provides non-generative single-label intent classification for customer support requests across the standard 46 Bitext retail e-commerce taxonomy.

## Model Provenance & Fail-Closed Architecture

The inference container enforces strict model provenance and fail-closed security to prevent unverified heuristics from masquerading as verified ML models:

1. **Pinned Artifact Integrity:**
   - On load, model weights (`model.safetensors`) and tokenizer (`tokenizer.json`) are checked against pinned SHA-256 release checksums from `EXPECTED_MANIFEST`.
   - Any checksum mismatch or missing artifact immediately fails closed: the model is not marked ready (`is_ready() == False`), `verified` is set to `False`, and `model_mode` is set to `"unavailable"`.

2. **Strict Taxonomy Bijection:**
   - Label mappings in `config.json` must be a strict, contiguous bijection covering indices `0..45` to the exact 46 standard Bitext labels.

3. **Fail-Closed by Default & Atomic State Reset:**
   - `SUPPORTIQ_DEV_FALLBACK_MODEL` is disabled by default (`false`).
   - If model files or directories are missing, the service raises HTTP 503 (`Model container not ready`) rather than synthesizing predictions.
   - All runtime container state (model, tokenizer, label map, hashes, versions, mode, verified status) is explicitly reset at the start of every `load()` attempt. If an error occurs on reload (such as malformed config or missing files after a previous success), stale identity/provenance is never retained.

4. **Explicit Demo Fallback Isolation:**
   - When explicitly opted into via `SUPPORTIQ_DEV_FALLBACK_MODEL=true` (e.g. for lightweight offline UI demos):
     - **Independent Identity:** Uses version `"demo-heuristic-v1"` and `model_mode="heuristic_demo"`.
     - **Unverified:** `verified` is strictly `False`.
     - **No Fabricated Hashes:** `model_checksum` and `tokenizer_checksum` are `None`.
     - **No Calibrated Probabilities:** Reports `score_kind="heuristic_score"` and rejects calibrated probability claims.
     - **Cannot Certify Trained Readiness:** `is_trained_ready()` is strictly `False`, ensuring benchmark and evaluation suites reject fallback runs.

5. **Safe Response Schemas:**
   - `PredictResponse` defaults do not invent trusted provenance if metadata is omitted (`model_mode` defaults to `None` and `verified` to `False`).

## Endpoints

- `GET /health`: Basic service liveness check.
- `GET /ready`: Readiness check exposing `ready`, `model_version`, `model_mode`, `verified`, and `trained_ready`.
- `POST /predict`: Intent prediction accepting `PredictRequest` and returning `PredictResponse` with confidence, margin, top-k ranking, score kind, and provenance metadata. Rejects expected version mismatches with HTTP 400.
