from typing import List, Dict, Any, Union

def score_retrieval(
    cases: List[Dict[str, Any]],
    retrieved_results: List[Dict[str, Any]]
) -> Dict[str, Union[float, str, int]]:
    """Score retrieval results using Recall@3 and Hit@3 over answerable queries,
    measuring false-answer rate on unanswerable queries.
    P2: Matches (doc_id, version) tuple; raises ValueError if any test case prediction is missing.
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

    valid_case_ids = {c["id"] for c in cases}
    res_by_id = {}
    for r in retrieved_results:
        rid = r.get("id")
        if rid not in valid_case_ids:
            raise ValueError(f"Extra prediction ID '{rid}' not in test cases")
        if rid in res_by_id:
            raise ValueError(f"Duplicate prediction ID '{rid}' found in retrieved_results")
        res_by_id[rid] = r

    # P2: Raise error if any case has missing prediction
    for c in cases:
        if c["id"] not in res_by_id:
            raise ValueError(f"Missing prediction result for test case '{c['id']}'")


    answerable_count = 0
    unanswerable_count = 0
    hits_at_3 = 0
    total_recall = 0.0
    false_answers = 0

    for c in cases:
        cid = c["id"]
        res = res_by_id[cid]
        # P2: Extract (doc_id, version) tuples from retrieved documents
        retrieved_keys = set()
        for d in res.get("documents", [])[:3]:
            doc_id = d.get("doc_id", d.get("document_id"))
            ver = str(d.get("version", "1.0"))
            retrieved_keys.add((doc_id, ver))

        is_answerable = c.get("is_answerable", True)
        raw_gold = c.get("gold_doc_ids", [])
        # Gold can be list of strings or tuples of (doc_id, version)
        gold_keys = set()
        for g in raw_gold:
            if isinstance(g, tuple):
                gold_keys.add((g[0], str(g[1])))
            elif ":" in str(g):
                parts = str(g).split(":", 1)
                gold_keys.add((parts[0], parts[1]))
            else:
                gold_keys.add((str(g), "1.0"))

        if is_answerable:
            answerable_count += 1
            if gold_keys:
                recalled = len(retrieved_keys & gold_keys)
                total_recall += recalled / len(gold_keys)
                if recalled > 0:
                    hits_at_3 += 1
        else:
            unanswerable_count += 1
            # If system returned documents when query was unanswerable, count as false answer
            if retrieved_keys:
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
