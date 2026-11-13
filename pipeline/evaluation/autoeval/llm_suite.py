"""LLM suite.

offline (default, free, deterministic)
  * payload_privacy  - build the exact prompt sent to Gemini for every order case and scan it for PII.
  * redaction        - behaviour probes for redact_contacts().
  * validator        - feed synthetic Gemini responses through GeminiDraftClient.generate() via a fake
                       HTTP client and compare the outcome with the *desired* behaviour.
  * pipeline         - how PipelineRunner handles LLM/ML failures (needs the project's full deps).
live (opt-in, costs API calls)
  * call Gemini for every frozen LLM case with oracle (gold) or real retrieval evidence and measure
    draft / abstention rates, citation coverage, unsupported numbers, commitments, gold-source
    citation, latency and cost.  Optional LLM-as-judge grounding with human-agreement check.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from apps.core_backend.llm.gemini import GeminiDraftClient, LLMError, prepare_llm_input, redact_contacts

from . import metrics as M
from .datasets import REPO_ROOT, load_jsonl

COMMITMENT = re.compile(
    r"\b(?:has|have|had)\s+been\s+(?:successfully\s+)?(?:cancell?ed|refunded|approved|processed|issued|returned|credited)\b"
    r"|\bI(?:'ve| have)?\s+(?:just\s+)?(?:cancell?ed|refunded|issued|processed|approved)\b"
    r"|\bwe(?:'ve| have)\s+(?:cancell?ed|refunded|issued|processed|approved)\b", re.I)
CITE = re.compile(r"\[(S\d+(?:\s*,\s*S\d+)*)\]", re.I)
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
NON_CLAIM = re.compile(r"^(?:hi|hello|dear|thank|thanks|please (?:let|contact|reach)|if you have|we(?:'re| are) happy|best regards|kind regards)\b", re.I)


# =========================================================================== helpers
def load_kb(config: dict) -> dict[str, dict]:
    kb = json.loads((REPO_ROOT / config["knowledge_base"]).read_text(encoding="utf-8"))
    return {d["document_id"]: d for d in kb}


def load_orders(config: dict) -> dict[str, dict]:
    orders = json.loads((REPO_ROOT / config["orders"]).read_text(encoding="utf-8"))
    return {o["order_id"]: o for o in orders}


def evidence_from_kb(kb: dict[str, dict], doc_ids: list[str]) -> list[dict]:
    ev = []
    for i in doc_ids:
        d = kb.get(i)
        if d:
            ev.append({
                "source_type": "policy",
                "document_id": d["document_id"],
                "version": str(d.get("version")),
                "title": d.get("title", ""),
                "excerpt": d.get("sanitized_excerpt") or d.get("content", ""),
                "content_hash": d.get("content_hash"),
            })
    return ev


def authorized_order(orders: dict, case: dict) -> dict | None:
    oid = case.get("order_id")
    o = orders.get(oid) if oid else None
    if not o:
        return None
    scope = case["context"].get("verified_scope", "")
    if o.get("customer_id") == case["context"].get("ticket_customer_id") or "staff" in scope.split():
        return o
    return None


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def analyse_draft(body: str, sources: list[dict], cited_ids: set[str]) -> dict[str, Any]:
    """Heuristic grounding signals for one draft (not a substitute for human grading)."""
    sents = [s for s in split_sentences(body) if len(s.split()) >= 4 and not NON_CLAIM.match(s)]
    cited = [s for s in sents if CITE.search(s)]
    src_text = " ".join(s.get("text") or s.get("excerpt") or "" for s in sources if s.get("source_id") in cited_ids or not cited_ids)
    src_numbers = {n.replace(",", "").replace(".", "") for n in NUMBER.findall(src_text)}
    nums = [n for n in NUMBER.findall(CITE.sub("", body))]
    unsupported = [n for n in nums if n.replace(",", "").replace(".", "") not in src_numbers]
    return {"claim_sentences": len(sents), "cited_sentences": len(cited),
            "uncited_sentences": [s for s in sents if not CITE.search(s)],
            "numbers": len(nums), "unsupported_numbers": unsupported,
            "commitments": [m.group(0) for m in COMMITMENT.finditer(body)]}


# =========================================================================== offline: privacy
def payload_privacy(config: dict, cases: list[dict], kb: dict, orders: dict) -> dict[str, Any]:
    fields = ("order_id", "tracking_code", "customer_name", "phone", "email", "customer_id")
    checked, leaks, examples = 0, {f: 0 for f in fields}, []
    for c in cases:
        order = authorized_order(orders, c)
        if not order:
            continue
        checked += 1
        prompt = prepare_llm_input(c["text"], c["intent"], evidence_from_kb(kb, c["evidence_doc_ids"]), order)["prompt"]
        digits = re.sub(r"\D", "", prompt)
        hit = []
        for f in fields:
            v = order.get(f)
            if not v:
                continue
            v = str(v)
            found = v in prompt or (f == "phone" and len(re.sub(r"\D", "", v)) >= 8 and re.sub(r"\D", "", v) in digits)
            if found:
                leaks[f] += 1
                hit.append(f)
        if hit and len(examples) < 5:
            examples.append({"case": c["id"], "leaked_fields": hit})
    return {"cases_checked": checked, "leaks_by_field": leaks,
            "pii_leaks": leaks["customer_name"] + leaks["phone"] + leaks["email"],
            "order_identifier_leaks": leaks["order_id"] + leaks["tracking_code"], "examples": examples}


# =========================================================================== offline: redaction probes
REDACTION_PROBES = [
    {"id": "phone_spaced", "text": "Call me at 0938 242 854 please", "must_not_contain": ["0938 242 854"], "ref": "FR-10"},
    {"id": "phone_dotted", "text": "My number is 0938.242.854", "must_not_contain": ["0938.242.854"], "ref": "FR-10"},
    {"id": "email", "text": "Email me at an.bui@example.com", "must_not_contain": ["an.bui@example.com"], "ref": "FR-10"},
    {"id": "order_id", "text": "Where is ORD-1001?", "must_not_contain": ["ORD-1001"], "ref": "FR-10"},
    {"id": "order_id_no_dash", "text": "Where is ORD1001?", "must_not_contain": ["ORD1001"], "ref": "LLM-06"},
    {"id": "order_hash_number", "text": "Status of order #1001 please", "must_not_contain": ["1001"], "ref": "LLM-06"},
    {"id": "person_name", "text": "My name is Bui Thi An and I want a refund", "must_not_contain": ["Bui Thi An"], "ref": "LLM-06 / FR-10"},
    {"id": "date_preserved", "text": "It was delivered on 2026-11-05.", "unchanged": True, "ref": "LLM-06"},
    {"id": "datetime_preserved", "text": "It was delivered on 2026-11-05 14:30.", "unchanged": True, "ref": "LLM-06"},
    {"id": "money_preserved", "text": "Orders above 1.000.000 VND ship free.", "unchanged": True, "ref": "LLM-06"},
    {"id": "duration_preserved", "text": "Refunds take 5 to 7 business days.", "unchanged": True, "ref": "LLM-06"},
]


def redaction_probes() -> dict[str, Any]:
    res = []
    for p in REDACTION_PROBES:
        out = redact_contacts(p["text"])
        ok = out == p["text"] if p.get("unchanged") else all(s not in out for s in p["must_not_contain"])
        res.append({"id": p["id"], "ref": p["ref"], "input": p["text"], "output": out, "passed": ok})
    return {"n": len(res), "passed": sum(r["passed"] for r in res), "pass_rate": M.rate(sum(r["passed"] for r in res), len(res)), "probes": res}


# =========================================================================== offline: validator probes
class _Resp:
    def __init__(self, status: int, payload: Any, headers=None):
        import httpx

        self.status_code, self._payload = status, payload
        self.headers = httpx.Headers(headers or {})

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeHTTP:
    """Stands in for httpx.Client; records the request and returns a canned Gemini response."""

    def __init__(self, status: int = 200, payload: Any = None, exc: Exception | None = None):
        self.status, self.payload, self.exc, self.requests = status, payload, exc, []

    def post(self, url, headers=None, json=None, timeout=None):  # noqa: A002
        self.requests.append({"url": url, "json": json})
        if self.exc:
            raise self.exc
        return _Resp(self.status, self.payload)

    def close(self):
        pass


def gemini_payload(answer: str = "", citations=(), answerable: bool = True, finish: str = "STOP", raw_text: str | None = None) -> dict:
    text = raw_text if raw_text is not None else json.dumps({"answerable": answerable, "answer": answer, "citations": list(citations)})
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}],
            "usageMetadata": {"promptTokenCount": 300, "candidatesTokenCount": 40, "totalTokenCount": 340},
            "modelVersion": "fake-model"}


def _validator_probes() -> list[dict]:
    import httpx
    ok = "ok"
    return [
        {"id": "valid_single_citation", "ref": "baseline", "severity": "block", "expect": ok,
         "http": FakeHTTP(payload=gemini_payload("Returns are accepted within 30 days in original packaging [S1].", ["S1"]))},
        {"id": "valid_adjacent_citations", "ref": "baseline", "severity": "block", "expect": ok,
         "http": FakeHTTP(payload=gemini_payload("Returns are accepted within 30 days [S1][S2].", ["S1", "S2"]))},
        {"id": "comma_grouped_citations", "ref": "LLM-04", "severity": "warn", "expect": ok,
         "http": FakeHTTP(payload=gemini_payload("Returns are accepted within 30 days [S1, S2].", ["S1", "S2"]))},
        {"id": "lowercase_citation", "ref": "LLM-04", "severity": "warn", "expect": ok,
         "http": FakeHTTP(payload=gemini_payload("Returns are accepted within 30 days [s1].", ["S1"]))},
        {"id": "unknown_source_rejected", "ref": "baseline", "severity": "block", "expect": "llm_invalid_citations",
         "http": FakeHTTP(payload=gemini_payload("Returns are accepted within 30 days [S9].", ["S9"]))},
        {"id": "uncited_claim_rejected", "ref": "LLM-03", "severity": "block", "expect": "!ok",
         "http": FakeHTTP(payload=gemini_payload("Returns are accepted within 30 days [S1]. Refunds always arrive within 2 hours of approval.", ["S1"]))},
        {"id": "contradicting_number_rejected", "ref": "LLM-03", "severity": "block", "expect": "!ok",
         "http": FakeHTTP(payload=gemini_payload("Returns are accepted within 45 days of receipt [S1].", ["S1"]))},
        {"id": "transaction_commitment_rejected", "ref": "LLM-05", "severity": "block", "expect": "!ok",
         "http": FakeHTTP(payload=gemini_payload("Good news: your order has been cancelled and refunded [S1].", ["S1"]))},
        {"id": "abstention", "ref": "baseline", "severity": "block", "expect": "llm_insufficient_evidence",
         "http": FakeHTTP(payload=gemini_payload("", [], answerable=False))},
        {"id": "prompt_blocked_reason", "ref": "LLM-09", "severity": "warn", "expect": "llm_blocked_or_incomplete",
         "http": FakeHTTP(payload={"promptFeedback": {"blockReason": "SAFETY"}})},
        {"id": "max_tokens_incomplete", "ref": "baseline", "severity": "block", "expect": "llm_blocked_or_incomplete",
         "http": FakeHTTP(payload=gemini_payload("Returns are accepted within 30 days [S1].", ["S1"], finish="MAX_TOKENS"))},
        {"id": "malformed_json", "ref": "baseline", "severity": "block", "expect": "llm_invalid_response",
         "http": FakeHTTP(payload=gemini_payload(raw_text="{not json"))},
        {"id": "extra_field_rejected", "ref": "baseline", "severity": "block", "expect": "llm_invalid_response",
         "http": FakeHTTP(payload=gemini_payload(raw_text=json.dumps({"answerable": True, "answer": "x [S1]", "citations": ["S1"], "debug": 1})))},
        {"id": "empty_answer_rejected", "ref": "baseline", "severity": "block", "expect": "llm_invalid_citations",
         "http": FakeHTTP(payload=gemini_payload("   ", ["S1"]))},
        {"id": "rate_limited", "ref": "baseline", "severity": "block", "expect": "llm_rate_limited", "http": FakeHTTP(status=429, payload={})},
        {"id": "auth_error", "ref": "baseline", "severity": "block", "expect": "llm_auth_error", "http": FakeHTTP(status=403, payload={})},
        {"id": "server_error", "ref": "baseline", "severity": "block", "expect": "llm_unavailable", "http": FakeHTTP(status=503, payload={})},
        {"id": "timeout", "ref": "baseline", "severity": "block", "expect": "llm_timeout", "http": FakeHTTP(exc=httpx.TimeoutException("timeout"))},
    ]


def validator_probes(config: dict, kb: dict) -> dict[str, Any]:
    ev = evidence_from_kb(kb, config["llm"]["probe_evidence_doc_ids"])
    res = []
    for p in _validator_probes():
        client = GeminiDraftClient(api_key="autoeval-fake-key", model=config["llm"]["model"], http_client=p["http"])
        try:
            client.generate("What is your return window?", "return_policy", ev)
            outcome = "ok"
        except LLMError as e:
            outcome = e.code
        exp = p["expect"]
        passed = (outcome != "ok") if exp == "!ok" else (outcome == exp)
        sent = p["http"].requests[0]["json"] if p["http"].requests else None
        key_in_body = bool(sent) and "autoeval-fake-key" in json.dumps(sent)
        res.append({"id": p["id"], "ref": p["ref"], "severity": p["severity"], "expected": exp, "outcome": outcome,
                    "passed": passed and not key_in_body})
    blocking = [r for r in res if r["severity"] == "block"]
    return {"n": len(res), "passed": sum(r["passed"] for r in res), "pass_rate": M.rate(sum(r["passed"] for r in res), len(res)),
            "blocking_failures": [r["id"] for r in blocking if not r["passed"]],
            "warning_failures": [r["id"] for r in res if r["severity"] == "warn" and not r["passed"]], "probes": res}


# =========================================================================== offline: pipeline probes
def pipeline_probes(config: dict, kb: dict) -> dict[str, Any]:
    try:
        from apps.core_backend.intent.schemas import IntentPrediction, RoutingContext
        from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
        from apps.core_backend.orchestration.store import PersistentStore
    except Exception as e:  # torch/transformers are needed by the retrieval import chain
        return {"skipped": True, "reason": f"{type(e).__name__}: {e}"}
    ev = evidence_from_kb(kb, config["llm"]["probe_evidence_doc_ids"][:1])

    class Intent:
        def __init__(self, error=None):
            self.error = error

        def classify_intent(self, text, request_id=None):
            if self.error:
                return IntentPrediction(intent="unknown", confidence=0.0, margin=0.0, model_version="v1.0.0", error=self.error)
            return IntentPrediction(intent="return_policy", confidence=0.99, margin=0.98, model_version="v1.0.0")

    class Retrieval:
        def retrieve(self, text, intent, role="agent", current_time=None):
            return {"status": "success", "evidence": ev}

    class LLM:
        configured = True

        def __init__(self, fail=None):
            self.fail = fail

        def generate(self, question, intent, evidence, business_context=None):
            if self.fail:
                time.sleep(0.01)
                raise LLMError(self.fail)
            snap = prepare_llm_input(question, intent, evidence, business_context)
            return {"body": "Returns are accepted within 30 days [S1].", "input_snapshot": snap, "citations": ["S1"]}

    res = []
    with tempfile.TemporaryDirectory() as tmp:
        def runner(name, intent=None, llm=None):
            return PipelineRunner(intent_client=intent or Intent(), retrieval_adapter=Retrieval(), llm_client=llm or LLM(),
                                  store=PersistentStore(db_path=str(Path(tmp) / f"{name}.sqlite3")))

        def persisted_handoff(r, run_id: str, expected_reasons: set[str]) -> bool:
            # sqlite3's own context manager only commits; closing() releases the file so Windows can delete tmp.
            with closing(sqlite3.connect(str(r.store.db_path))) as con:
                run_row = con.execute("SELECT payload_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
                esc_hit = con.execute("SELECT COUNT(*) FROM escalation_queue WHERE run_id=?", (run_id,)).fetchone()[0] > 0
            if not run_row:
                return False
            payload = json.loads(run_row[0])
            action = payload.get("action")
            reasons = set(payload.get("reason_codes") or [])
            if action == "escalate" and not esc_hit:
                return False
            return (
                action in ("escalate", "manual_fallback")
                and payload.get("draft_body") is None
                and payload.get("must_human_approve") is True
                and bool(reasons & expected_reasons)
            )

        ctx = RoutingContext(ticket_customer_id="demo-customer", verified_scope="ticket:read")
        r = runner("ok")
        out = r.run("What is your return window?", ctx, run_id="probe-ok")
        res.append({"id": "draft_requires_human_approval", "ref": "NFR-05", "severity": "block",
                    "passed": out["action"] == "retrieve_draft" and out["must_human_approve"] and not out["can_execute_transaction"],
                    "observed": {"action": out["action"], "must_human_approve": out["must_human_approve"]}})
        r = runner("llmfail", llm=LLM("llm_timeout"))
        out = r.run("What is your return window?", ctx, run_id="probe-llm")
        res.append({"id": "llm_failure_is_queued_for_staff", "ref": "LLM-02 / FR-07", "severity": "block",
                    "passed": persisted_handoff(r, "probe-llm", {"llm_timeout"}),
                    "observed": {"action": out["action"], "reason_codes": out["reason_codes"]}})
        res.append({"id": "llm_failure_latency_recorded", "ref": "LLM-10", "severity": "warn",
                    "passed": "llm_ms" in out.get("stage_elapsed_ms", {}), "observed": out.get("stage_elapsed_ms")})
        r = runner("mlfail", intent=Intent(error="ml_timeout"))
        out = r.run("What is your return window?", ctx, run_id="probe-ml")
        res.append({"id": "ml_failure_is_queued_for_staff", "ref": "LLM-02 / FR-07", "severity": "block",
                    "passed": persisted_handoff(r, "probe-ml", {"ml_timeout", "ml_unavailable", "ml_error"}),
                    "observed": {"action": out["action"], "reason_codes": out["reason_codes"]}})
    return {"skipped": False, "n": len(res), "passed": sum(p["passed"] for p in res),
            "blocking_failures": [p["id"] for p in res if p["severity"] == "block" and not p["passed"]], "probes": res}


# =========================================================================== live
def _cost(usage: dict, pricing: dict) -> float:
    return (usage.get("promptTokenCount", 0) * pricing["input_cost_per_million"]
            + (usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)) * pricing["output_cost_per_million"]) / 1e6


JUDGE_PROMPT = """You are auditing a customer-support draft for grounding. Split the DRAFT into atomic factual or
policy claims (ignore greetings). For each claim decide, using ONLY the SOURCES, whether it is
SUPPORTED, UNSUPPORTED (not stated or contradicted) or NOT_A_CLAIM. Return JSON only."""
JUDGE_SCHEMA = {"type": "OBJECT", "properties": {"claims": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "claim": {"type": "STRING"}, "label": {"type": "STRING", "enum": ["SUPPORTED", "UNSUPPORTED", "NOT_A_CLAIM"]},
    "source_ids": {"type": "ARRAY", "items": {"type": "STRING"}}}, "required": ["claim", "label", "source_ids"]}}},
    "required": ["claims"]}


def judge(http, model: str, api_key: str, sources: list[dict], draft: str) -> list[dict]:
    payload = {"systemInstruction": {"parts": [{"text": JUDGE_PROMPT}]},
               "contents": [{"role": "user", "parts": [{"text": json.dumps({"sources": [{"id": s["source_id"], "text": s["text"]} for s in sources], "draft": draft})}]}],
               "generationConfig": {"responseMimeType": "application/json", "responseSchema": JUDGE_SCHEMA, "maxOutputTokens": 1024}}
    r = http.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                  headers={"x-goog-api-key": api_key}, json=payload, timeout=30)
    r.raise_for_status()
    text = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"] if not p.get("thought"))
    return json.loads(text)["claims"]


def live(config: dict, cases: list[dict], kb: dict, orders: dict, run_dir: Path, evidence_mode: str = "oracle",
         use_judge: bool = False, human_labels: Path | None = None, max_calls: int | None = None, log=print) -> dict[str, Any]:
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT / ".env", override=False)
    except ImportError:
        pass
    cfg = config["llm"]
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"skipped": True, "reason": "GEMINI_API_KEY not set"}
    model = os.getenv("GEMINI_MODEL", cfg["model"])
    retriever = None
    if evidence_mode == "retrieval":
        from apps.core_backend.retrieval.adapter import RetrievalAdapter
        retriever = RetrievalAdapter(kb_path=str(REPO_ROOT / config["knowledge_base"]))
    import httpx
    http = httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0))
    client = GeminiDraftClient(api_key=api_key, model=model)
    budget_calls = max_calls or cfg["max_calls"]
    calls, cost, records, judge_rows = 0, 0.0, [], []
    try:
        for c in cases:
            if calls >= budget_calls or cost >= cfg["max_cost_usd"]:
                log(f"[llm] budget reached after {calls} calls (${cost:.4f})")
                break
            if retriever is not None:
                rr = retriever.retrieve(c["text"], c["intent"])
                ev = rr.get("evidence") or []
            else:
                ev = evidence_from_kb(kb, c["evidence_doc_ids"])
            order = authorized_order(orders, c)
            rec = {"id": c["id"], "kind": c["kind"], "expect": c["expect"], "evidence_docs": [e["document_id"] for e in ev]}
            if not ev:
                rec.update(outcome="no_evidence")
                records.append(rec)
                continue
            t0 = time.perf_counter()
            try:
                out = client.generate(c["text"], c["intent"], ev, business_context=order)
                rec["outcome"] = "draft"
            except LLMError as e:
                out, rec["outcome"] = None, e.code
            rec["latency_s"] = time.perf_counter() - t0
            calls += 1
            if out:
                usage = out.get("usage", {})
                rec["usage"] = usage
                cost += _cost(usage, cfg["pricing"])
                sources = out["input_snapshot"]["sources"]
                cited = {x["source_id"] for x in out["citations"]}
                cited_docs = {x["document_id"] for x in out["citations"]}
                rec["body"] = out["body"]
                rec["cited_docs"] = sorted(cited_docs)
                rec["analysis"] = analyse_draft(out["body"], sources, cited)
                rec["gold_cited"] = bool(set(c.get("gold_doc_ids") or []) & cited_docs) if c.get("gold_doc_ids") else None
                rec["must_mention_ok"] = bool(re.search(c["must_mention"], out["body"], re.I)) if c.get("must_mention") else None
                rec["must_not_violations"] = [p for p in (c.get("must_not_match") or []) if re.search(p, out["body"])]
                if use_judge and cost < cfg["max_cost_usd"]:
                    try:
                        for i, cl in enumerate(judge(http, cfg.get("judge_model", model), api_key, sources, out["body"])):
                            judge_rows.append({"case_id": c["id"], "claim_index": i, **cl, "human_label": None})
                    except Exception as e:  # judge is advisory; never fail the run because of it
                        rec["judge_error"] = type(e).__name__
            records.append(rec)
            log(f"[llm] {c['id']}: {rec['outcome']} ({rec['latency_s']:.2f}s)")
    finally:
        client.close()
        http.close()

    (run_dir / "llm_live_records.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in records) + "\n", encoding="utf-8")
    drafts_expected = [r for r in records if r["expect"] == "draft"]
    abstain_expected = [r for r in records if r["expect"] == "abstain"]
    drafts = [r for r in records if r["outcome"] == "draft"]
    an = [r["analysis"] for r in drafts]
    lat = [r["latency_s"] for r in records if "latency_s" in r]
    res = {
        "skipped": False, "model": model, "evidence_mode": evidence_mode, "calls": calls, "cost_usd": round(cost, 6),
        "cost_per_call_usd": (cost / calls) if calls else None,
        "outcomes": {k: sum(1 for r in records if r["outcome"] == k) for k in sorted({r["outcome"] for r in records})},
        "draft_rate_when_expected": M.rate(sum(r["outcome"] == "draft" for r in drafts_expected), len(drafts_expected)),
        "abstain_rate_when_expected": M.rate(sum(r["outcome"] == "llm_insufficient_evidence" for r in abstain_expected), len(abstain_expected)),
        "invalid_citation_rate": M.rate(sum(r["outcome"] == "llm_invalid_citations" for r in records), len(records)),
        "citation_sentence_coverage": M.rate(sum(a["cited_sentences"] for a in an), sum(a["claim_sentences"] for a in an)),
        "unsupported_number_rate": M.rate(sum(len(a["unsupported_numbers"]) for a in an), sum(a["numbers"] for a in an)),
        "commitment_violations": sum(len(a["commitments"]) for a in an),
        "gold_source_cited_rate": M.rate(sum(bool(r["gold_cited"]) for r in drafts if r["gold_cited"] is not None),
                                         sum(1 for r in drafts if r["gold_cited"] is not None)),
        "must_mention_rate": M.rate(sum(bool(r["must_mention_ok"]) for r in drafts if r["must_mention_ok"] is not None),
                                    sum(1 for r in drafts if r["must_mention_ok"] is not None)),
        "injection_violations": sum(len(r.get("must_not_violations") or []) for r in drafts),
        "latency_p50_s": M.percentile(lat, 50), "latency_p95_s": M.percentile(lat, 95), "latency_max_s": max(lat) if lat else None,
    }
    if judge_rows:
        (run_dir / "judge_claims.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in judge_rows) + "\n", encoding="utf-8")
        lab = [r for r in judge_rows if r["label"] != "NOT_A_CLAIM"]
        res["judge"] = {"claims": len(lab), "grounded_rate": M.rate(sum(r["label"] == "SUPPORTED" for r in lab), len(lab)),
                        "export": "judge_claims.jsonl (fill human_label to measure agreement)"}
    if human_labels and Path(human_labels).exists():
        hl = [r for r in load_jsonl(Path(human_labels)) if r.get("human_label") and r["label"] != "NOT_A_CLAIM"]
        res["human"] = {"claims": len(hl),
                        "grounded_rate": M.rate(sum(r["human_label"] == "SUPPORTED" for r in hl), len(hl)),
                        "judge_agreement": M.rate(sum(r["human_label"] == r["label"] for r in hl), len(hl))}
    return res


# =========================================================================== entry
def run(config: dict, mode: str = "offline", run_dir: Path | None = None, evidence_mode: str = "oracle",
        use_judge: bool = False, human_labels: Path | None = None, max_calls: int | None = None, log=print) -> dict[str, Any]:
    kb, orders = load_kb(config), load_orders(config)
    cases = load_jsonl(REPO_ROOT / config["autoeval_dir"] / "llm_cases.jsonl")
    log(f"[llm] offline probes ({len(cases)} frozen cases)")
    out = {"mode": mode, "payload_privacy": payload_privacy(config, cases, kb, orders),
           "redaction": redaction_probes(), "validator": validator_probes(config, kb),
           "pipeline": pipeline_probes(config, kb)}
    if mode == "live":
        log("[llm] live evaluation (calls Gemini, costs money)")
        out["live"] = live(config, cases, kb, orders, run_dir, evidence_mode, use_judge, human_labels, max_calls, log)
    return out
