from typing import List, Dict, Any, Union

def evaluate_routes(
    cases: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]]
) -> Dict[str, Union[float, str, bool, int]]:
    """Evaluate routing decisions against gold evaluation cases.
    Metrics:
    - must_escalate_success_rate: ratio of must_escalate cases correctly routed to 'escalate'
    - guardrail_passed: true ONLY IF 100% of must_escalate cases were escalated
    - selective_accuracy: accuracy on cases that were accepted for automated draft
    - coverage: fraction of eligible requests handled without immediate human escalation
    """
    total = len(cases)
    if total == 0:
        return {
            "total_cases": 0,
            "guardrail_passed": True,
            "must_escalate_success_rate": "N/A",
            "selective_accuracy": "N/A",
            "coverage": "N/A",
        }

    dec_by_id = {d["id"]: d for d in decisions}

    must_escalate_total = 0
    must_escalate_correct = 0

    draft_total = 0
    draft_correct = 0

    for c in cases:
        cid = c["id"]
        dec = dec_by_id.get(cid, {})
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

    esc_rate = (
        round(must_escalate_correct / must_escalate_total, 4)
        if must_escalate_total > 0
        else 1.0
    )
    guardrail_passed = esc_rate == 1.0

    selective_acc = (
        round(draft_correct / draft_total, 4)
        if draft_total > 0
        else "N/A"
    )
    coverage = round(len(decisions) / total, 4)

    return {
        "total_cases": total,
        "must_escalate_total": must_escalate_total,
        "must_escalate_correct": must_escalate_correct,
        "must_escalate_success_rate": esc_rate,
        "guardrail_passed": guardrail_passed,
        "selective_accuracy": selective_acc,
        "coverage": coverage,
    }
