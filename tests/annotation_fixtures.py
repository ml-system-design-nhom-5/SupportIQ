"""Explicit synthetic reviewer/evidence fields for metric-formula unit tests only."""
from copy import deepcopy


def reviewed_annotations(rows):
    rows = deepcopy(rows)
    for row in rows:
        # Invalid reviewer tests must remain invalid.
        if not row.get('reviewer'):
            continue
        row.setdefault('reviewer_type', 'human')
        row.setdefault('reviewed_at', '2026-11-05T00:00:00Z')
        row.setdefault('relevance', 'not_assessed')
        row.setdefault('attestation', {})['all_factual_claims_reviewed'] = True
        for claim in row.get('claims', []):
            if claim.get('verdict') == 'supported':
                claim.setdefault('claim_text', 'Synthetic fixture claim')
                claim.setdefault('source_id', 'S1')
                claim.setdefault('doc_id', 'FIXTURE-POLICY')
                claim.setdefault('version', '1')
                claim.setdefault('evidence_span', 'Synthetic fixture evidence; not a real reviewer assessment.')
    return rows
