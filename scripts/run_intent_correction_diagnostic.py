"""Bounded, explicitly oracle-assisted diagnostic through the real staff API.

Keeps initial outcomes separate from intervention outcomes. It does not measure
automatic classifier accuracy or pretend that staff time is human study data.
"""
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.platform.models import AuditEntry
from apps.backend.seed import seed
from scripts.collect_final_acceptance_evidence import AcceptanceEvidenceCollector, resolve_database_url
from scripts.native_runtime import configure_runtime_environment


def terminal(client, ticket_id):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        response = client.get(f'/v1/console/tickets/{ticket_id}')
        response.raise_for_status()
        view = response.json()
        suggestion = view['suggestion']
        if suggestion['analysis_status'] != 'pending' and suggestion['draft_status'] != 'pending':
            return view
        time.sleep(.05)
    raise TimeoutError('Suggestion did not become terminal within diagnostic budget')


def main():
    configure_runtime_environment()
    collector = AcceptanceEvidenceCollector(mode='live', max_cases=12, secrets_path=str(ROOT / '.local/application.json'))
    # Fixed diagnostic selection from the preserved first-run uncertainty failures.
    selected = {'final-case-03', 'final-case-04', 'final-case-05', 'final-case-06', 'final-case-07', 'final-case-10', 'final-case-12'}
    cases = [c for c in collector.cases if c['id'] in selected]
    assert len(cases) == 7
    run_id = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    out = ROOT / 'artifacts/evaluation' / ('coordinator-intent-correction-' + run_id)
    out.mkdir(exist_ok=False)
    owner_url, default_passwords = resolve_database_url(str(ROOT / '.local/application.json'))
    schema = 'diag_intent_' + uuid.uuid4().hex[:10]
    owner = create_engine(owner_url, hide_parameters=True)
    application = None
    schema_created = False
    records = []
    try:
        with owner.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_created = True
        application = create_engine(owner_url, connect_args={'options': f'-csearch_path={schema}'}, hide_parameters=True)
        db = Database(application)
        db.create_schema()
        passwords = {role: default_passwords.get(role, uuid.uuid4().hex) for role in ('customer', 'staff', 'manager', 'admin')}
        seed(db, passwords)
        settings = Settings(database_url_app=owner_url, database_url_owner=owner_url, session_cookie_secure=False,
                            allowed_origins=['http://testserver'], ai_service_base_url='http://127.0.0.1:8002',
                            ai_service_analysis_timeout_ms=3000, ai_service_draft_timeout_ms=11000, job_poll_interval_ms=50)
        app = create_app(settings=settings, database=db, start_worker=True)
        with TestClient(app) as customer, TestClient(create_app(settings=settings, database=db, start_worker=False)) as staff:
            for client, role in ((customer, 'customer'), (staff, 'staff')):
                client.headers['Origin'] = 'http://testserver'
                auth = client.post('/v1/sessions', json={'login_name': role + '-1', 'password': passwords[role]})
                auth.raise_for_status()
            for case in cases:
                record = {'case_id': case['id'], 'query': case['query'], 'gold_intent': case['intent'],
                          'intervention_authority': 'coordinator_AI_delegated_stakeholder',
                          'intervention_type': 'oracle_intent_correction_diagnostic', 'initial': None, 'assisted': None}
                try:
                    started = time.perf_counter()
                    payload = {'message': case['query'], **({'order_id': case['order_id']} if case.get('order_id') else {})}
                    submitted = customer.post('/v1/shop/tickets', json=payload, headers={'Idempotency-Key': uuid.uuid4().hex})
                    submitted.raise_for_status()
                    ticket_id = submitted.json()['ticket_id']
                    record['ticket_id'] = ticket_id
                    record['initial'] = terminal(staff, ticket_id)
                    record['initial_system_seconds'] = time.perf_counter() - started
                    correction = record['initial']['suggestion']['draft_status'] == 'abstained'
                    record['correction_executed'] = correction
                    if correction:
                        record['correction_started_at'] = datetime.now(timezone.utc).isoformat()
                        started = time.perf_counter()
                        changed = staff.post(f'/v1/console/tickets/{ticket_id}/suggestions', json={'intent_override': case['intent']},
                                             headers={'Idempotency-Key': uuid.uuid4().hex})
                        record['correction_http_status'] = changed.status_code
                        changed.raise_for_status()
                        record['assisted'] = terminal(staff, ticket_id)
                        record['correction_system_seconds'] = time.perf_counter() - started
                        record['correction_completed_at'] = datetime.now(timezone.utc).isoformat()
                    response = customer.get(f'/v1/shop/tickets/{ticket_id}')
                    response.raise_for_status()
                    customer_view = response.json()
                    record['customer_no_auto_send'] = ('reply' in customer_view and customer_view['reply'] is None and customer_view.get('customer_status') == 'received')
                    with db.transaction() as session:
                        entries = session.scalars(select(AuditEntry).where(AuditEntry.ticket_id == ticket_id, AuditEntry.event_type == 'intent.overridden')).all()
                        record['override_audit'] = [{'event_type': e.event_type, 'actor_account_id': e.actor_account_id, 'data': e.data} for e in entries]
                    assert not correction or record['override_audit'], 'Correction audit missing'
                except Exception as error:
                    record['error_type'] = type(error).__name__
                records.append(record)
                (out / 'records.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        if application is not None:
            application.dispose()
        if schema_created:
            with owner.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        owner.dispose()
    (out / 'manifest.json').write_text(json.dumps({'run_id': run_id, 'cases_sha256': collector.manifest_cases_sha256,
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'sample_count': len(records),
        'purpose': 'Actual staff API correction diagnostic, not automatic classifier accuracy or measured human productivity.',
        'boundary': 'TestClient HTTP application, real isolated PostgreSQL worker, actual ML/BGE/Gemini gateway.',
        'source_snapshot': 'data/knowledge/approved_kb.v2.json', 'source_sha256': hashlib.sha256((ROOT/'data/knowledge/approved_kb.v2.json').read_bytes()).hexdigest(),
        'no_reply_send_requested': True}, indent=2), encoding='utf-8')
    print(out.relative_to(ROOT))
    print(json.dumps({'cases': len(records), 'corrected': sum(r.get('correction_executed', False) for r in records),
        'assisted_drafts': sum((r.get('assisted') or {}).get('suggestion', {}).get('draft_status') == 'draft_ready' for r in records),
        'errors': sum('error_type' in r for r in records), 'no_auto_send_all': all(r.get('customer_no_auto_send') for r in records)}))


if __name__ == '__main__':
    main()
