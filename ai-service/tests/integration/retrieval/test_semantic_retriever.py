import json
from pathlib import Path
import numpy as np


def test_gateway_release_excludes_legacy_kb_before_embedding():
    from apps.core_backend.retrieval.adapter import RetrievalAdapter
    release=json.loads(Path('apps/ai_service/kb-release.json').read_text())
    allowed={(item['document_id'],item['version']) for item in release['documents']}
    class Encoder:
        def encode_passages(self, texts):
            assert all('Standard Return Policy\n' not in text for text in texts)
            return np.ones((len(texts), 3),dtype=np.float32)
    adapter=RetrievalAdapter(encoder=Encoder(),allowed_document_versions=allowed)
    assert len(adapter.eligible_versions)==14
    assert all(not document.doc_id.startswith('b1000000') for document in adapter.eligible_versions)
    assert len([doc for doc in adapter.quarantined_docs if doc['reason']=='not_in_current_release'])==3


def test_empty_release_does_not_fall_back_to_older_documents():
    from apps.core_backend.retrieval.adapter import RetrievalAdapter

    class Encoder:
        def encode_passages(self, texts):
            raise AssertionError("An empty release must not embed any documents")

    adapter = RetrievalAdapter(encoder=Encoder(), allowed_document_versions=set())
    assert adapter.eligible_versions == []
    assert adapter.retrieve('return policy', 'return_policy')['evidence'] == []
