"""Dedicated suite and manifest validation tests for Final Acceptance (Worker C).

Verifies:
- Exactly 24 synthetic cases covering:
  * 11 core answerable product intents (12 drafting cases including restricted cosmetics regression)
  * Sensitive / authority / escalation scenarios
  * Human agent direct escalation (12th product scenario)
  * Unsupported / no-source scenarios
  * Out-of-domain (OOD) scenarios
  * Honest separate injected fixture boundary (temporal expiry and conflict detection)
- Accurate derivation of expected document versions from active approved KB
- Owned order IDs mapped to seeded demo customer orders
- Manifest integrity, file SHA-256 hashes, and root CRLF vs worker LF KB reconciliation
- 12 paired same-case tasks with alternating order (6 assisted_first, 6 manual_first)
"""

import hashlib
import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


@pytest.fixture(scope="module")
def suite_cases():
    cases_path = REPO_ROOT / "data/benchmarks/final_acceptance/cases.jsonl"
    assert cases_path.exists(), f"Cases file not found: {cases_path}"
    lines = [line.strip() for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


@pytest.fixture(scope="module")
def suite_manifest():
    manifest_path = REPO_ROOT / "data/benchmarks/final_acceptance/suite_manifest.json"
    assert manifest_path.exists(), f"Manifest file not found: {manifest_path}"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def active_kb_release():
    release_path = REPO_ROOT / "apps/ai_service/kb-release.json"
    assert release_path.exists(), f"KB release file not found: {release_path}"
    return json.loads(release_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def active_kb_docs():
    kb_path = REPO_ROOT / "data/knowledge/approved_kb.v2.json"
    assert kb_path.exists(), f"KB file not found: {kb_path}"
    docs = json.loads(kb_path.read_text(encoding="utf-8"))
    return {doc.get("doc_id") or doc.get("document_id"): doc for doc in docs}


@pytest.fixture(scope="module")
def paired_tasks():
    paired_path = REPO_ROOT / "data/benchmarks/final_acceptance/paired_agent_tasks.json"
    assert paired_path.exists(), f"Paired tasks file not found: {paired_path}"
    return json.loads(paired_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def injected_fixtures():
    fixtures_path = REPO_ROOT / "data/benchmarks/final_acceptance/injected_robustness_fixtures.json"
    assert fixtures_path.exists(), f"Injected fixtures not found: {fixtures_path}"
    return json.loads(fixtures_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def mock_orders():
    orders_path = REPO_ROOT / "data/knowledge/mock_orders.json"
    assert orders_path.exists(), f"Mock orders file not found: {orders_path}"
    return json.loads(orders_path.read_text(encoding="utf-8"))


def test_suite_case_count_and_uniqueness(suite_cases):
    """Must lock exactly 24 synthetic scenarios with unique IDs."""
    assert len(suite_cases) == 24
    ids = [c["id"] for c in suite_cases]
    assert len(set(ids)) == 24, "Case IDs must be unique"


def test_suite_covers_11_answerable_intents_plus_regression(suite_cases):
    """The 11 core answerable product intents must each be represented in answerable cases."""
    required_11_answerable_intents = {
        "return_policy",
        "return_product",
        "refund_policy",
        "request_refund",
        "refund_status",
        "cancel_order",
        "track_order",
        "shipping_costs",
        "delivery_time",
        "delivery_issue",
        "payment_issue",
    }
    product_cases = [c for c in suite_cases if c.get("slice") == "product_12_answerable"]
    assert len(product_cases) == 12
    observed_intents = {c["intent"] for c in product_cases}
    assert observed_intents == required_11_answerable_intents, f"Missing product intents: {required_11_answerable_intents - observed_intents}"

    # Verify cosmetics regression case exists under return_policy
    c11 = next(c for c in product_cases if c["id"] == "final-case-11")
    assert c11["intent"] == "return_policy"
    assert "cosmetics" in c11["query"].lower()
    assert "POL-RET-003:2.0" in c11["expected_docs"]

    # Verify human_agent is evaluated in sensitive/escalation group
    ha_case = next(c for c in suite_cases if c["intent"] == "human_agent")
    assert ha_case["id"] == "final-case-15"
    assert ha_case["expected_action"] == "escalate"
    assert ha_case["slice"] == "human_agent_escalation"

    for c in product_cases:
        assert c["is_answerable"] is True
        assert c["is_product_12_scope"] is True
        assert c["expected_action"] == "draft"
        assert len(c["expected_docs"]) >= 1, f"Case {c['id']} must define expected active KB documents"
        assert c["fixture_boundary"] == "active_kb"


def test_derived_doc_versions_match_active_kb(suite_cases, active_kb_release, active_kb_docs):
    """All expected documents in active cases must derive directly from the active KB release."""
    release_docs = {d["document_id"]: str(d["version"]) for d in active_kb_release["documents"]}

    for c in suite_cases:
        if c.get("fixture_boundary") == "active_kb" and c.get("expected_docs"):
            for doc_key in c["expected_docs"]:
                parts = doc_key.split(":")
                doc_id = parts[0]
                version = parts[1] if len(parts) > 1 else None

                assert doc_id in release_docs, f"Case {c['id']} references {doc_id} not in kb-release.json"
                assert doc_id in active_kb_docs, f"Case {c['id']} references {doc_id} not in approved_kb.v2.json"
                if version:
                    assert version == release_docs[doc_id], f"Version mismatch for {doc_id}: expected {release_docs[doc_id]}, got {version}"
                    assert version == str(active_kb_docs[doc_id]["version"]), f"Version mismatch in KB body for {doc_id}"


def test_cases_owned_order_ids_seeded(suite_cases, mock_orders):
    """All cases specifying order_id must use orders owned by demo-customer (customer-1)."""
    demo_orders = {o["order_id"] for o in mock_orders if o.get("customer_id") == "demo-customer"}
    for c in suite_cases:
        order_id = c.get("order_id")
        if order_id:
            assert order_id in demo_orders, f"Case {c['id']} references order {order_id} not owned by demo-customer"


def test_suite_slice_distribution(suite_cases):
    """Suite must cover sensitive, human agent, no-source, OOD, and honest separate fixture boundaries."""
    slice_counts = {}
    for c in suite_cases:
        s = c["slice"]
        slice_counts[s] = slice_counts.get(s, 0) + 1

    assert slice_counts.get("product_12_answerable") == 12
    assert slice_counts.get("sensitive_escalation") == 2
    assert slice_counts.get("human_agent_escalation") == 1
    assert slice_counts.get("unsupported_no_source") == 2
    assert slice_counts.get("out_of_domain") == 3
    assert slice_counts.get("expired_injected_boundary") == 2
    assert slice_counts.get("conflict_injected_boundary") == 2

    # Verify sensitive/escalation cases mandate escalation
    for c in suite_cases:
        if c["slice"] in ("sensitive_escalation", "human_agent_escalation"):
            assert c["expected_action"] == "escalate"
            assert "requires_authority" in c["expected_reasons"] or "human_agent_requested" in c["expected_reasons"]

        if c["slice"] in ("unsupported_no_source", "out_of_domain", "expired_injected_boundary", "conflict_injected_boundary"):
            assert c["expected_action"] == "abstain"
            assert c["is_answerable"] is False


def test_honest_fixture_boundary_separation(suite_cases, injected_fixtures):
    """Expired and conflicting cases must be explicitly flagged as injected_synthetic boundary."""
    injected_cases = [c for c in suite_cases if c["fixture_boundary"] == "injected_synthetic"]
    assert len(injected_cases) == 4

    active_cases = [c for c in suite_cases if c["fixture_boundary"] == "active_kb"]
    assert len(active_cases) == 20

    # Injected fixtures must be separated from active KB
    assert injected_fixtures["active_kb_polluted"] is False
    fixture_doc_ids = {d["doc_id"] for d in injected_fixtures["documents"]}
    assert "POL-INJ-EXP-01" in fixture_doc_ids
    assert "POL-INJ-EXP-02" in fixture_doc_ids
    assert "POL-INJ-CONF-01A" in fixture_doc_ids
    assert "POL-INJ-CONF-01B" in fixture_doc_ids


def test_manifest_sha256_checksums_and_reconciliation(suite_manifest):
    """Manifest file hashes must match current contents on disk and document KB line-ending reconciliation."""
    prov = suite_manifest["provenance"]
    for key, path_str in [
        ("cases_sha256", prov["cases_file"]),
        ("injected_fixtures_sha256", prov["injected_fixtures_file"]),
        ("paired_tasks_sha256", prov["paired_tasks_file"]),
    ]:
        disk_path = REPO_ROOT / path_str
        assert disk_path.exists(), f"File referenced in manifest not found: {disk_path}"
        disk_hash = compute_sha256(disk_path)
        assert disk_hash == prov[key], f"Hash mismatch for {path_str}: expected {prov[key]}, disk has {disk_hash}"

    reconcile = prov["kb_reconciliation"]
    root_served = reconcile["deployed_root_serving_gateway"]
    assert root_served["kb_source_sha256"] == "f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec"
    assert root_served["kb_release_sha256"] == "cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804"
    assert root_served["combined_kb_version_hash"] == "32547457f792d6c61c4dff4493f1b55791e5a28f63a60da0eaf0d9736dfdcf0c"

    local_worker = reconcile["worker_local_worktree"]
    assert local_worker["local_kb_source_sha256"] == "aaa924c4b48dcd53a14269045b278b66f6e5e8ae9d1b614cd59b757102b78594"
    assert local_worker["local_kb_release_sha256"] == "33cf05b50c25384fbb208cd0c0c5cae71991d29a0f754cb1b20a1d6d7285cdaa"

    # Verify that disk files match one of the declared valid pairs (worker LF or root CRLF)
    disk_kb_hash = compute_sha256(REPO_ROOT / "data/knowledge/approved_kb.v2.json")
    disk_rel_hash = compute_sha256(REPO_ROOT / "apps/ai_service/kb-release.json")
    disk_pair = (disk_kb_hash, disk_rel_hash)
    valid_pairs = {
        (local_worker["local_kb_source_sha256"], local_worker["local_kb_release_sha256"]),
        (root_served["kb_source_sha256"], root_served["kb_release_sha256"]),
    }
    assert disk_pair in valid_pairs, f"Disk files ({disk_pair}) must match either declared LF or CRLF pair"

    # Explicitly test real normalized LF and CRLF byte hashes
    kb_raw = (REPO_ROOT / "data/knowledge/approved_kb.v2.json").read_bytes()
    rel_raw = (REPO_ROOT / "apps/ai_service/kb-release.json").read_bytes()

    kb_norm_lf = kb_raw.replace(b"\r\n", b"\n")
    kb_norm_crlf = kb_norm_lf.replace(b"\n", b"\r\n")
    assert hashlib.sha256(kb_norm_lf).hexdigest() == local_worker["local_kb_source_sha256"]
    assert hashlib.sha256(kb_norm_crlf).hexdigest() == root_served["kb_source_sha256"]

    rel_norm_lf = rel_raw.replace(b"\r\n", b"\n")
    rel_norm_crlf = rel_norm_lf.replace(b"\n", b"\r\n")
    assert hashlib.sha256(rel_norm_lf).hexdigest() == local_worker["local_kb_release_sha256"]
    assert hashlib.sha256(rel_norm_crlf).hexdigest() == root_served["kb_release_sha256"]


def test_paired_agent_tasks_structure_and_order(paired_tasks, suite_cases):
    """12 paired tasks must alternate execution order (6 assisted-first, 6 manual-first) without invented ratings."""
    tasks = paired_tasks["tasks"]
    assert len(tasks) == 12

    assisted_first_count = sum(1 for t in tasks if t["execution_order"] == "assisted_first")
    manual_first_count = sum(1 for t in tasks if t["execution_order"] == "manual_first")
    assert assisted_first_count == 6
    assert manual_first_count == 6

    # Verify order strictly alternates
    for idx, t in enumerate(tasks):
        expected_order = "assisted_first" if idx % 2 == 0 else "manual_first"
        assert t["execution_order"] == expected_order, f"Task {t['task_id']} at index {idx} should be {expected_order}"

        # No invented ratings or decisions
        assert t["trial_status"] == "prepared_for_coordinator_execution"
        assert t["assisted_trial"]["agent_decision"] is None
        assert t["assisted_trial"]["duration_seconds"] is None
        assert t["manual_trial"]["manual_response_text"] is None
        assert t["manual_trial"]["duration_seconds"] is None
