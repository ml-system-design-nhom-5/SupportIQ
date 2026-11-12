"""Exercise the application API, PostgreSQL job, real ML/BGE and configured LLM.

Uses and removes a dedicated database schema, never the user's tickets or orders.
Run explicitly: this check calls the configured external LLM.
"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import time
import uuid
import threading
import subprocess
import os

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.seed import seed


def main():
    local = json.loads(Path('.local/application.json').read_text())
    schema = 'verify_ai_' + uuid.uuid4().hex
    root = create_engine(local['database_url_owner'], hide_parameters=True)
    with root.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(local['database_url_owner'], connect_args={'options': f'-csearch_path={schema}'}, hide_parameters=True)
    try:
        database = Database(engine)
        database.create_schema()
        seed(database, local['passwords'])
        settings = Settings(database_url_app=local['database_url_owner'], allowed_origins=['http://testserver','http://127.0.0.1:18080'],
                            session_cookie_secure=False, ai_service_base_url='http://127.0.0.1:8002')
        with TestClient(create_app(settings=settings, database=database)) as customer, TestClient(create_app(settings=settings, database=database, start_worker=False)) as staff:
            for client, role in ((customer, 'customer'), (staff, 'staff')):
                client.headers['Origin'] = 'http://testserver'
                response = client.post('/v1/sessions', json={'login_name': role+'-1', 'password': local['passwords'][role]})
                assert response.status_code == 201
            response = customer.post('/v1/shop/tickets', headers={'Idempotency-Key': str(uuid.uuid4())}, json={'message': 'What is your return policy?'})
            assert response.status_code == 201, response.status_code
            identifier = response.json()['ticket_id']
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                workspace = staff.get('/v1/console/tickets/'+identifier).json()
                suggestion = workspace['suggestion']
                if suggestion['analysis_status'] != 'pending' and suggestion['draft_status'] != 'pending':
                    break
                time.sleep(.25)
            result = {'intent': suggestion.get('analysis', {}).get('intent'), 'draft_status': suggestion['draft_status'],
                      'sources': len(suggestion.get('analysis', {}).get('documents', [])),
                      'citations': len(suggestion.get('draft', {}).get('citations', [])),
                      'reason_codes': suggestion['reason_codes'], 'failure_code': suggestion.get('failure_code'),
                      'latency_ms': suggestion['step_latency_ms'], 'versions': suggestion.get('versions'),
                      'llm_usage': suggestion.get('llm_usage'), 'customer_reply': customer.get('/v1/shop/tickets/'+identifier).json()['reply']}
            Path('.local/integration-live.json').write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
            assert suggestion['draft_status'] == 'draft_ready', result
            assert result['sources'] > 0 and result['citations'] > 0
            assert result['customer_reply'] is None, 'Unreviewed draft must not reach the customer'
            # Render the production React build against this isolated database and real result.
            import uvicorn
            server=uvicorn.Server(uvicorn.Config(create_app(settings=settings,database=database,start_worker=False),host='127.0.0.1',port=18080,log_level='error',access_log=False))
            thread=threading.Thread(target=server.run,daemon=True);thread.start()
            try:
                until=time.monotonic()+5
                while not server.started and time.monotonic()<until:time.sleep(.05)
                browser_code=r"""
import {chromium} from '@playwright/test';
import {readFileSync} from 'node:fs';
const local=JSON.parse(readFileSync('../../.local/application.json','utf8'));
const browser=await chromium.launch({channel:'msedge'});const context=await browser.newContext({viewport:{width:1440,height:900}});
const base='http://127.0.0.1:18080';
await context.request.post(base+'/v1/sessions',{headers:{Origin:base},data:{login_name:'staff-1',password:local.passwords.staff}});
const page=await context.newPage();await page.goto(base+'/console/tickets/'+process.env.SUPPORTIQ_VERIFY_TICKET);
await page.getByRole('heading',{name:'AI draft',exact:true}).waitFor();
if(await page.locator('.source-row').count()<1 || await page.locator('.draft-text .citation').count()<1)throw new Error('Missing real evidence or citations');
await page.locator('.source-row').first().click();await page.getByRole('dialog').waitFor();await page.locator('.document-body').waitFor();await page.getByRole('button',{name:'Close dialog',exact:true}).click();
await page.screenshot({path:'../../.impeccable/review/ai-live-console.png',fullPage:true});
console.log('Production UI verified: real intent, draft, citations and full source document.');await browser.close();
"""
                subprocess.run(['node','--input-type=module'],input=browser_code,text=True,check=True,cwd='apps/frontend',env={**os.environ,'SUPPORTIQ_VERIFY_TICKET':identifier})
            finally:
                server.should_exit=True;thread.join(timeout=5)

    finally:
        engine.dispose()
        with root.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()


if __name__ == '__main__':
    main()
