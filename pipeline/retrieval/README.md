# Native Semantic Policy Retrieval with BGE-small-en-v1.5

## Architecture
- **Embedding Model**: `BAAI/bge-small-en-v1.5` (384 dimensions, FP32, CLS pooling, L2 normalized).
- **Native Execution**: Directly executes in PyTorch / Transformers without extra vector database dependencies (no Chroma, no Faiss, no sentence-transformers).
- **Exact Cosine Dot-Product**: Fast vector dot-product ranking in memory using NumPy.
- **Top 3 Distinct Documents**: Returns up to 3 different documents, maximum 2 chunks per document, within a 1,500 token budget.
- **Strict Eligibility Filtering**:
  - `status == "approved"`
  - Temporal validity: `valid_from <= as_of <= valid_to`
  - Scoped role permissions (`allowed_roles`)
  - No-answer relevance threshold gate (rejection of low-similarity / out-of-domain queries).
