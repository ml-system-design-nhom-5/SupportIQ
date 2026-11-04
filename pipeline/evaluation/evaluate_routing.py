from typing import List, Dict, Any, Union

def evaluate_routes(
    cases: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]]
) -> Dict[str, Union[float, str, bool, int]]:
    """Evaluate routing decisions against gold evaluation cases.
    Metrics:
    - must_escalate_success_rate: ratio of must_escalate cases correctly routed to 'escalate'
    - guardrail_passed: true ONLY IF count of must_escalate_correct == must_escalate_total (with total > 0)
    - selective_accuracy: accuracy on valid cases accepted for automated draft
    - coverage: fraction of test cases that were accepted for automated draft
    """
    total = len(cases)
    if total == 0:
        return {
            "total_cases": 0,
            "guardrail_passed": "N/A",
            "must_escalate_success_rate": "N/A",
            "selective_accuracy": "N/A",
            "coverage": "N/A",
        }

    valid_case_ids = {c["id"] for c in cases}
    # Only match decisions that belong to the test suite cases
    dec_by_id = {d["id"]: d for d in decisions if d.get("id") in valid_case_ids}

    must_escalate_total = 0
    must_escalate_correct = 0

    draft_total = 0
    draft_correct = 0

    for c in cases:
        cid = c["id"]
        dec = dec_by_id.get(cid)
        if not dec:
            continue
        action = dec.get("action")
        predicted_intent = dec.get("predicted_intent")
        true_intent = c.get("true_intent")

        if c.get("must_escalate"):
            must_escalate_total += 1
            if action == "escalate":
                must_escalate_correct += 1

        if action == "retrieve_draft":
            draft_total += 1
            if predicted_intent == true_intent:
                draft_correct += 1

    if must_escalate_total == 0:
        esc_rate = "N/A"
        guardrail_passed = "N/A"
    else:
        # P2: Check integer counts directly before rounding to avoid false positive from float roundoff
        guardrail_passed = (must_escalate_correct == must_escalate_total)
        esc_rate = round(must_escalate_correct / must_escalate_total, 4)

    selective_acc = (
        round(draft_correct / draft_total, 4)
        if draft_total > 0
        else "N/A"
    )

    # P2: Coverage is the proportion of total cases accepted for automated drafting
    coverage = round(draft_total / total, 4)

    return {
        "total_cases": total,
        "must_escalate_total": must_escalate_total,
        "must_escalate_correct": must_escalate_correct,
        "must_escalate_success_rate": esc_rate,
        "guardrail_passed": guardrail_passed,
        "selective_accuracy": selective_acc,
        "coverage": coverage,
    }
