# Index configuration `bge-small-en-v1.5-main-untuned-v1-kb-v2`

The source of `index.json` of the index asset of the first release, in `supportiq-retrieval-index/interim-1` ([`ai-service/README.md`, Asset formats](../../README.md#asset-formats)). It holds the values of `main`, which were never tuned ([ADR-0027](../../../docs/decisions/0027-retrieval-index-configuration-of-the-first-release.md)). The release command copies `index.json` into the index asset, at the path `index`, next to the files of the encoder in `index/encoder/`.

## Values

Each value comes from `main` at commit `19ece5d81fbd74c00602eb1b34bb53ead06c9668`, read with `git show`.

| Field | Value | Source in `main` |
|---|---|---|
| `encoder.name` | `BAAI/bge-small-en-v1.5` | `apps/core_backend/retrieval/encoder.py`, line 8, `BGE_MODEL_NAME` |
| `encoder.query_prefix` | `"Represent this sentence for searching relevant passages: "` (with its final space) | `apps/core_backend/retrieval/encoder.py`, line 9, `QUERY_PREFIX`, put before each query on line 124 |
| `encoder.max_length` | 512 | `apps/core_backend/retrieval/encoder.py`, line 150, for queries and passages alike |
| `chunking.max_tokens` | 480 | `apps/core_backend/retrieval/encoder.py`, line 20, the default of `chunk_policy` |
| `chunking.overlap_tokens` | 40 | `apps/core_backend/retrieval/encoder.py`, line 21, the default of `chunk_policy` |
| `relevance_min_score` | 0.55 | `apps/core_backend/retrieval/adapter.py`, line 50, the default of `RetrievalAdapter`, which `apps/ai_service/main.py`, line 133, builds without another value |

`version` names the encoder, the values of `main`, and the KB version together, because the index of a release is built from its KB ([`index_file.py`](../../src/supportiq_ai_service/retrieval/adapters/index_file.py)). `kb_version` is `v2`, the KB of the first release. `encoder.directory` is the folder of the encoder in the release, `index/encoder`.

## The files of the encoder

The encoder is not in git ([ADR-0018, Artifact store](../../../docs/decisions/0018-hosting-of-ai-service-on-modal.md#artifact-store)). Its files come from `bge-small-en-v1.5-hf-cache.zip`, an asset of the release `v2.0.0-model` of the organization repository (SHA-256 `90b90854c719403d5c972a8889bf650f88336dd379ad15fe925b3f9ac0d6022e`). The archive holds the Hugging Face snapshot `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` of `BAAI/bge-small-en-v1.5` as regular files:

| File | SHA-256 |
|---|---|
| `config.json` | `094f8e891b932f2000c92cfc663bac4c62069f5d8af5b5278c4306aef3084750` |
| `model.safetensors` | `3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad` |
| `special_tokens_map.json` | `b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3` |
| `tokenizer.json` | `d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66` |
| `tokenizer_config.json` | `9261e7d79b44c8195c1cada2b453e55b00aeb81e907a6664974b4d7776172ab3` |
| `vocab.txt` | `07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3` |

Only these six files of the snapshot go into `index/encoder/` of a release. The rest of the archive, `refs/main` and the empty markers of `.no_exist/`, belong to the cache layout and are not files of the encoder.
