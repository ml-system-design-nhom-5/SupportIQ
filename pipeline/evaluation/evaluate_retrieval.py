from typing import List, Dict, Any, Union

def score_retrieval(
    cases: List[Dict[str, Any]],
    retrieved_results: List[Dict[str, Any]]
) -> Dict[str, Union[float, str, int]]:
    """Score retrieval results using Recall@3 and Hit@3 over answerable queries,
    and measure false-answer rate on unanswerable queries.
    """
    total = len(cases)
    if total == 0:
        return {
            "total_cases": 0,
            "answerable_count": 0,
            "unanswerable_count": 0,
            "recall_at_3": "N/A",
            "hit_at_3": "N/A",
            "false_answer_rate": "N/A",
        }

    res_by_id = {r["id"]: r for r in retrieved_results}

    answerable_count = 0
    unanswerable_count = 0
    hits_at_3 = 0
    total_recall = 0.0
    false_answers = 0

    for c in cases:
        cid = c["id"]
        res = res_by_id.get(cid, {})
        retrieved_doc_ids = [d["doc_id"] for d in res.get("documents", [])[:3]]
        is_answerable = c.get("is_answerable", True)
        gold_doc_ids = set(c.get("gold_doc_ids", []))

        if is_answerable:
            answerable_count += 1
            if gold_doc_ids:
                recalled = len(set(retrieved_doc_ids) & gold_doc_ids)
                total_recall += recalled / len(gold_doc_ids)
                if recalled > 0:
                    hits_at_3 += 1
        else:
            unanswerable_count += 1
            # If system returned documents when query was unanswerable, count as false answer
            if retrieved_doc_ids:
                false_answers += 1

    recall_at_3 = (
        round(total_recall / answerable_count, 4)
        if answerable_count > 0
        else "N/A"
    )
    hit_at_3 = (
        round(hits_at_3 / answerable_count, 4)
        if answerable_count > 0
        else "N/A"
    )
    false_answer_rate = (
        round(false_answers / unanswerable_count, 4)
        if unanswerable_count > 0
        else "N/A"
    )

    return {
        "total_cases": total,
        "answerable_count": answerable_count,
        "unanswerable_count": unanswerable_count,
        "recall_at_3": recall_at_3,
        "hit_at_3": hit_at_3,
        "false_answer_rate": false_answer_rate,
    }
