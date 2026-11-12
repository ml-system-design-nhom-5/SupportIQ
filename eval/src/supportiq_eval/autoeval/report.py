"""Markdown report for an autoeval run (machine-readable data lives in report.json)."""
from __future__ import annotations

from typing import Any

ICON = {"pass": "PASS", "fail": "FAIL", "warn": "WARN", "skipped": "SKIP", "not_run": "—"}


def _f(v, pct=False):
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return f"{v * 100:.1f}%" if pct else f"{v:.3f}"
    if isinstance(v, list):
        return ", ".join(map(str, v)) if v else "(trống)"
    return str(v)


def _table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ") for x in r) + " |")
    return "\n".join(out)


def render(report: dict[str, Any]) -> str:
    meta, res, gates = report["meta"], report["results"], report["gates"]
    s = report["summary"]
    L = [f"# SupportIQ autoeval – {meta['run_id']}", "",
         f"Kết luận: **{'ĐẠT' if s['passed'] else 'KHÔNG ĐẠT'}** · {s['fail']} gate chặn không đạt · {s['warn']} cảnh báo · {s['pass']} đạt · {s['skipped']} bỏ qua",
         "", f"- Suite: {', '.join(meta['suites'])} · LLM mode: {meta.get('llm_mode')} · commit: {meta.get('git_commit') or '—'}",
         f"- Dữ liệu: manifest {'khớp' if meta['datasets']['ok'] else 'KHÔNG khớp: ' + ', '.join(meta['datasets'].get('mismatched', []))}",
         f"- Thời gian chạy: {meta['duration_s']:.1f} s", "", "## Gates", "",
         _table(["Trạng thái", "Gate", "Giá trị", "Ngưỡng", "Mức", "Tham chiếu", "Mô tả"],
                [[ICON[g["status"]], g["id"], _f(g["value"]), f"{g['op']} {_f(g['threshold'])}", g["severity"], g.get("ref") or "", g.get("desc") or ""] for g in gates])]
    if report.get("regression"):
        L += ["", "## So với lần chạy trước", "",
              _table(["Chỉ số", "Trước", "Nay", "Δ", "Tụt lùi"],
                     [[r["metric"], _f(r["previous"]), _f(r["current"]), f"{r['delta']:+.3f}", "CÓ" if r["regressed"] else ""] for r in report["regression"]])]

    ml = res.get("ml")
    if ml and "benchmark" in ml:
        b, m = ml["benchmark"], ml["model"]
        L += ["", "## ML", "",
              f"Backend `{ml['backend']}` · policy {ml.get('policy_version')} · checksum khớp: {m.get('checksum_match')} · weights `{m.get('weights_sha256', '')[:12]}`", "",
              "### Benchmark câu do người viết", "",
              _table(["Chỉ số", "Giá trị"], [["Số câu có nhãn", b["n_labeled"]], ["Accuracy", _f(b["accuracy"], True)], ["Macro-F1", _f(b["macro_f1"])],
                                             ["Đúng đội xử lý", _f(b["team_accuracy"], True)], ["Đúng phạm vi 12/34", _f(b["scope_accuracy"], True)],
                                             ["ECE", _f(b["calibration"]["ece"])], ["Sai mà tự tin ≥0,8", b["calibration"]["confident_errors"]]]), "",
              _table(["Slice", "n", "Accuracy", "Macro-F1", "Conf. trung vị"],
                     [[k, v["n"], _f(v["accuracy"], True), _f(v["macro_f1"]), _f(v["median_confidence"])] for k, v in b["by_slice"].items()]), "",
              "Độ tin cậy (reliability):", "",
              _table(["Khoảng", "n", "Tỷ lệ đúng", "Conf. TB"], [[r["bin"], r["n"], _f(r["accuracy"]), _f(r["mean_confidence"])] for r in b["calibration"]["reliability"]]), "",
              "Nhầm lẫn thường gặp: " + "; ".join(f"{g} → {p} ({n})" for g, p, n in b["top_confusions"][:6]), ""]
        r = b["routing"]
        me = r["must_escalate"]
        L += ["### Routing (policy thật)", "",
              _table(["Chỉ số", "Giá trị"], [
                  ["Phân bố hành động", r["action_distribution"]],
                  ["Bắt buộc chuyển cấp: chuyển/thủ công · clarify · sang soạn nháp", f"{me['escalate_or_fallback']} · {me['clarify']} · {me['forwarded_to_draft']} / {me['n']} (trong đó {me['forwarded_to_draft_downstream_responsibility']} do retrieval/LLM chịu trách nhiệm)"],
                  ["Draft không an toàn do ML", f"{r['ml_unsafe_drafts']} {r['ml_unsafe_draft_cases']}"],
                  ["Câu soạn được → tới bước soạn", _f(r["draftable_reached_draft_rate"], True)],
                  ["Câu soạn được → clarify", _f(r["clarify_rate_on_draftable"], True)],
                  ["Lượt soạn nháp mang intent sai", f"{r['wrong_intent_drafts']} / {r['drafts_n']}"],
                  ["Đúng đội khi chuyển cấp", _f(r["escalation_team_accuracy"], True)]])]
        n = ml["noise"]
        L += ["", "### Độ bền với nhiễu (NFR-02)", "",
              _table(["Biến thể", "n", "Accuracy", "Macro-F1"], [[k, v["n"], _f(v["accuracy"], True), _f(v["macro_f1"])] for k, v in n.items() if isinstance(v, dict)]),
              "", f"Giảm Macro-F1: lỗi chính tả {_f(n.get('typo_f1_drop'))}, văn nói {_f(n.get('casual_f1_drop'))}"]
        o = ml["oos"]
        L += ["", "### Câu ngoài phạm vi / mơ hồ / nhiều ý (NFR-02)", "",
              _table(["Nhóm", "n", "Gắn cờ/chuyển", "Conf. thấp", "Sang soạn nháp"],
                     [[k, v["n"], _f(v["flagged_rate"], True), _f(v["low_conf_rate"], True), v["drafted"]] for k, v in o["by_category"].items()]),
              "", f"AUROC phát hiện OOS: entropy {_f(o['auroc_entropy'])}, 1−confidence {_f(o['auroc_one_minus_conf'])}"]
        if o["confident_misses"]:
            L += ["", "Câu ngoài phạm vi nhưng model rất tự tin:", ""] + [f"- “{x['text']}” → `{x['pred']}` ({x['conf']:.2f}, {x['action']})" for x in o["confident_misses"][:10]]
        L += ["", f"Latency tính toán ({ml['latency_ms']['backend']}): p50 {_f(ml['latency_ms']['p50'])} ms, p95 {_f(ml['latency_ms']['p95'])} ms — {ml['latency_ms']['note']}"]
        if b["errors"]:
            L += ["", "<details><summary>Các câu dự đoán sai</summary>", "",
                  _table(["Case", "Câu", "Đúng", "Dự đoán", "Conf.", "Hành động"],
                         [[e["id"], e["text"][:70], e["gold"], e["pred"], _f(e["conf"]), e["action"]] for e in b["errors"]]), "", "</details>"]
    elif ml:
        L += ["", "## ML", "", f"Không chạy được: {ml.get('error')}"]

    llm = res.get("llm")
    if llm:
        pp, rd, va, pl = llm["payload_privacy"], llm["redaction"], llm["validator"], llm["pipeline"]
        L += ["", "## LLM", "", "### Payload gửi Gemini", "",
              f"{pp['cases_checked']} case có dữ kiện đơn hàng · rò rỉ theo trường: {pp['leaks_by_field']}", "",
              "### Probe bộ kiểm tra phản hồi (validator)", "",
              _table(["Probe", "Tham chiếu", "Mức", "Kỳ vọng", "Thực tế", "Kết quả"],
                     [[p["id"], p["ref"], p["severity"], p["expected"], p["outcome"], "PASS" if p["passed"] else "FAIL"] for p in va["probes"]]),
              "", "### Probe che dữ liệu (redact_contacts)", "",
              _table(["Probe", "Tham chiếu", "Đầu vào", "Đầu ra", "Kết quả"],
                     [[p["id"], p["ref"], p["input"], p["output"], "PASS" if p["passed"] else "FAIL"] for p in rd["probes"]]),
              "", "### Pipeline khi LLM/ML lỗi", ""]
        if pl.get("skipped"):
            L.append(f"Bỏ qua: {pl['reason']} (cần cài đủ requirements của dự án, gồm torch).")
        else:
            L.append(_table(["Probe", "Tham chiếu", "Kết quả", "Quan sát"],
                            [[p["id"], p["ref"], "PASS" if p["passed"] else "FAIL", p["observed"]] for p in pl["probes"]]))
        lv = llm.get("live")
        if lv:
            L += ["", "### Live (Gemini thật)", ""]
            if lv.get("skipped"):
                L.append(f"Bỏ qua: {lv['reason']}")
            else:
                rows = [[k, _f(lv.get(k), k.endswith("rate") or k.endswith("coverage"))] for k in (
                    "model", "evidence_mode", "calls", "cost_usd", "outcomes", "draft_rate_when_expected", "abstain_rate_when_expected",
                    "invalid_citation_rate", "citation_sentence_coverage", "unsupported_number_rate", "commitment_violations",
                    "gold_source_cited_rate", "must_mention_rate", "injection_violations", "latency_p50_s", "latency_p95_s")]
                L.append(_table(["Chỉ số", "Giá trị"], rows))
                for k in ("judge", "human"):
                    if lv.get(k):
                        L += ["", f"{k}: {lv[k]}"]
                L += ["", "Chi tiết từng case: `llm_live_records.jsonl`. Grounding bằng heuristic/LLM-judge chỉ để sàng lọc; NFR-04 vẫn cần người chấm."]
    return "\n".join(L) + "\n"
