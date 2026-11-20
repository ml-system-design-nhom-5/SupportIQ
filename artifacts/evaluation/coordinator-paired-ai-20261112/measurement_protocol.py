import sys,json,time,hashlib
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/evaluation/coordinator-paired-ai-20261112'

def now():return datetime.now(timezone.utc).isoformat()
def write(name,obj):(OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
if not OUT.exists():
 OUT.mkdir()
 suite=ROOT/'data/benchmarks/final_acceptance/cases.jsonl'
 kbpath=ROOT/'data/knowledge/approved_kb.v2.json'
 docs={f"{d['doc_id']}:{d['version']}":d for d in json.loads(kbpath.read_text())}
 baseline=[json.loads(x) for x in (ROOT/'artifacts/evaluation/coordinator-final-live-20261112-r3/final-evidence-20261112-151514-078471/evidence_records.jsonl').read_text().splitlines() if x.strip()]
 base={r['case_id']:r for r in baseline}
 corrected={r['case_id']:r for r in json.loads((ROOT/'artifacts/evaluation/coordinator-intent-correction-20261112-152013-0fb5c3/records.json').read_text())}
 materials=[]
 for case in [json.loads(x) for x in suite.read_text().splitlines() if x.strip()][:12]:
  cid=case['id']; original=base[cid]; correction=corrected.get(cid); selected=(correction or {}).get('assisted')
  suggestion=(selected or {}).get('suggestion') or {}
  draft=(suggestion.get('draft') or {}).get('text') if selected else original.get('full_draft_text')
  status=suggestion.get('draft_status') if selected else original.get('draft_status')
  context=(selected or {}).get('order') if selected else original.get('actual_executed_order_context')
  materials.append({'case_id':cid,'query':case['query'],'order_context':context,'source_cards':[{'source_key':key,'content':docs[key]['content'],'content_hash':docs[key]['content_hash']} for key in case['expected_docs']],'draft':draft if status=='draft_ready' else None,'status':status,'assistance_origin':'oracle_staff_override_diagnostic' if selected else 'automatic_r3'})
 schedule=[]
 for index,m in enumerate(materials):
  order=['assisted','manual'] if index%2==0 else ['manual','assisted']
  schedule.extend({'case_id':m['case_id'],'condition':c} for c in order)
 write('materials.json',materials)
 write('protocol.json',{'created_at':now(),'reviewer':'coordinator_AI_under_user_delegation','human_study':False,'task_count':12,'planned_phase_count':24,'counterbalance':'Six assisted-first and six manual-first cases, same case and source cards in each pair.','timing':'Real monotonic wall-clock elapsed from material exposure to recorded response. Includes model and tool/orchestration overhead; does not isolate human active work. No sleep or fabricated duration.','source_cards':'Relevant source cards preselected by frozen expected document IDs for both conditions; this removes realistic manual search and is an oracle evidence-selection aid.','assisted':'Review/edit an existing cached automatic or oracle-corrected draft; if unavailable, compose a manual fallback. No new LLM requests.','limits':['Same coordinator performs both conditions; no blinding, carryover and memory effects.','Twelve synthetic tasks are a convenience sample, not a real customer or human-participant study.','Measured phase times exclude earlier generation and staff-intent-override waiting time; cannot imply full handling-time savings.','Small model/tool timing differences are noisy and do not prove a causal productivity effect.','Earlier incomplete in-memory timing observations are not included or reconstructed.'],'cases_sha256':hashlib.sha256(suite.read_bytes()).hexdigest(),'kb_sha256':hashlib.sha256(kbpath.read_bytes()).hexdigest(),'schedule':schedule})
 write('state.json',{'index':0,'active':None,'events':[],'invalidated':[]})
command=json.load(sys.stdin) if not sys.stdin.isatty() else {}
state=read('state.json'); protocol=read('protocol.json'); materials={m['case_id']:m for m in read('materials.json')}
if command.get('invalidate') and state['active']:
 state['invalidated'].append({**state['active'],'invalidated_at':now(),'reason':command['invalidate']});state['active']=None
if 'finish' in command:
 assert state['active'] is not None,'No active timed phase'
 answer=command['finish'];assert isinstance(answer.get('response'),str) and answer['response'].strip()
 active=state['active']; elapsed=(time.perf_counter_ns()-active['started_monotonic_ns'])/1e9
 event={**active,'completed_at':now(),'duration_seconds':elapsed,**answer}
 if active['condition']=='assisted':assert answer.get('decision') in {'approve','edit','reject','manual_fallback'}
 state['events'].append(event);state['active']=None;state['index']+=1
if command.get('start') and state['index']<len(protocol['schedule']):
 assert state['active'] is None,'Timed phase already active'
 phase=protocol['schedule'][state['index']];m=materials[phase['case_id']]
 state['active']={**phase,'started_at':now(),'started_monotonic_ns':time.perf_counter_ns()}
 shown={**phase,'query':m['query'],'order_context':m['order_context'],'source_cards':m['source_cards']}
 if phase['condition']=='assisted':shown.update(draft=m['draft'],draft_status=m['status'],assistance_origin=m['assistance_origin'])
 write('state.json',state)
 print(json.dumps(shown,ensure_ascii=False))
else:
 write('state.json',state);print(json.dumps({'completed_phases':len(state['events']),'active_phase':state['active']}))