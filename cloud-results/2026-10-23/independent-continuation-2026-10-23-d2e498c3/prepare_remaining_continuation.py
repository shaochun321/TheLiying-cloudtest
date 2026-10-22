"""Bind the authorized continuation to the existing approved plans; no solver call."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import copy,hashlib,json,shutil,uuid,zipfile
PREV=Path('/workspace/thermal-g3-formal/formal-sparse125us-2026-10-22-40458034')
PACKAGE=Path('/workspace/attachments/6e877720-108f-4cae-a2c7-bcf78752f966/G0W_根因复算与条件续行方案_2026-10-23.zip')
ROOT=Path('/workspace/thermal-g3-formal')/('independent-continuation-2026-10-23-'+uuid.uuid4().hex[:8])
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
assert sha(PREV/'FORMAL_MANIFEST.json')=='6aa34994c8edcc139ba8e249fe8d15d4b4d101e0e5fae254a75ec6fc46a8f3ea'
old=read(PREV/'FORMAL_MANIFEST.json');software=Path(old['source_software'])
with zipfile.ZipFile(PACKAGE) as z:
 proposal=json.loads(z.read('remaining_formal_execution_proposal.json'))
 assert z.testzip() is None
assert sha(software/'prereg/cases_q1r.json')==proposal['source_registry_sha256']
registry=read(software/'prereg/cases_q1r.json')
registered={c['case_id']:c for c in registry['cases'] if c['phase']=='formal'}
proposed={c['case_id']:c for c in proposal['cases']}
assert set(proposed)==set(registered)-{'G0_W'} and len(proposed)==30
g0=read(PREV/'runs/G0_W/verdict-binding.json')
assert g0['scientific']=='FAIL' and g0['global_start_count']==35
assert read(PREV/'formal-budget-summary.json')['global_starts_after']==35
ROOT.mkdir(parents=True,exist_ok=False);(ROOT/'inputs').mkdir();(ROOT/'runs').mkdir()
with zipfile.ZipFile(PACKAGE) as z:
 for name in z.namelist():
  rel=Path(name);assert not rel.is_absolute() and '..' not in rel.parts
  dest=ROOT/'inputs'/'user-package'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(name))
shutil.copy2(PACKAGE,ROOT/'inputs'/PACKAGE.name)
qualified={}
for q in old['qualified_evidence']:
 assert sha(q['binding_path'])==q['binding_sha256']
 b=read(q['binding_path']);assert b['scientific']=='PASS' and b['complete_transient'] and b['actual_end_s']==100.27
 qualified[q['case_id']]={'scientific':'PASS','binding_path':q['binding_path'],'binding_sha256':q['binding_sha256'],'raw_sha256':b['raw_sha256']}
 shutil.copy2(q['binding_path'],ROOT/'inputs'/(q['case_id']+'-binding.json'))
for source in (PREV/'inputs').iterdir():
 if source.is_file():shutil.copy2(source,ROOT/'inputs'/source.name)
protected={str(PREV/n):sha(PREV/n) for n in ['FORMAL_MANIFEST.json','STOPPED.json','formal-ledger.jsonl','formal-budget-summary.json','runs/G0_W/verdict-binding.json','runs/G0_W/judge-output.json']}
cases={}
for cid,pr in proposed.items():
 source=PREV/'runs'/cid;p=read(source/'plan.json');c=p['case'];orig=registered[cid];approved=old['cases'][cid]
 assert sha(source/'plan.json')==approved['plan_sha256'] and sha(source/(cid+'.cir'))==approved['deck_sha256']
 assert p['original_registered_case']==orig
 assert c['depends_on']==pr['dependencies']==orig['depends_on']
 assert c['baseline_case_id']==pr['baseline_case_id']==orig['baseline_case_id']
 assert c['max_step_s']==pr['proposed_candidate_max_step_s']
 assert orig['max_step_s']==pr['original_max_step_s']
 assert c['timeout_s']==pr['existing_case_timeout_s']==orig['timeout_s']
 if c['analysis']!='op':
  assert c['max_step_s']<=orig['max_step_s']
  if c['baseline_case_id'] and cid.endswith('HALFSTEP'):
   bp=read(PREV/'runs'/c['baseline_case_id']/'plan.json')
   assert c['max_step_s']==bp['case']['max_step_s']/2
 run=ROOT/'runs'/cid;run.mkdir()
 before=(source/(cid+'.cir')).read_text();after=before.replace(str(PREV),str(ROOT))
 assert after.replace(str(ROOT),str(PREV))==before
 analyses=[line.strip() for line in after.splitlines() if line.strip().lower().startswith(('tran ','op','dc ','ac ','run','resume'))]
 assert analyses==[c['analysis']],(cid,analyses)
 deck=run/(cid+'.cir');deck.write_text(after,encoding='ascii',newline='\n')
 p=copy.deepcopy(p);p.update(deck=str(deck),deck_sha256=sha(deck),execution_contract_wall_cap_s=None,original_timeout_is_historical_reference=True)
 save(run/'plan.json',p)
 cases[cid]={'directory':str(run),'plan_sha256':sha(run/'plan.json'),'deck_sha256':sha(deck),
 'source_plan_sha256':approved['plan_sha256'],'source_deck_sha256':approved['deck_sha256'],
 'depends_on':c['depends_on'],'baseline_case_id':c['baseline_case_id'],'analysis':c['analysis'],
 'original_timeout_s':c['timeout_s'],'effective_wall_cap_s':None,'group':c['group'],'max_step_s':c['max_step_s']}
initial={**qualified,'G0_W':{'scientific':'FAIL','binding_path':str(PREV/'runs/G0_W/verdict-binding.json'),'binding_sha256':sha(PREV/'runs/G0_W/verdict-binding.json'),'raw_sha256':g0['raw_sha256']}}
ready=[cid for cid,c in cases.items() if all(initial.get(d,{}).get('scientific')=='PASS' for d in c['depends_on'])]
assert set(ready)==set(proposal['initial_dependency_ready'])
manifest={'run_id':ROOT.name,'prepared_at':now(),'source_software':str(software),'approved_formal_manifest':str(PREV/'FORMAL_MANIFEST.json'),
 'approved_formal_manifest_sha256':sha(PREV/'FORMAL_MANIFEST.json'),'backend':old['backend'],'spice_scripts':old['spice_scripts'],
 'source_registry_sha256':proposal['source_registry_sha256'],'input_zip_sha256':sha(PACKAGE),'cases':cases,'initial_bound_verdicts':initial,
 'global_starts_before':35,'global_start_cap':65,'max_new_starts':30,'per_case_max_starts':1,'automatic_retries':0,
 'protected_original_files_sha256':protected,'single_agent':True,'priority':['DC_2P7','DC_3','DC_3P2','CHAIN_12_W_F'],
 'original_limits_s':{'global':172800,'formal_phase':108000},'effective_wall_limits_s':{'global':None,'formal_phase':None,'per_case':None},
 'exact_historical_wall_s':None,'old_cost_gate_not_claimed_passed':True,'old_STOPPED_preserved':True,
 'external_reconstruction_evidence':'User-supplied fixed_order_reconstruction.json only; reconstructing scripts and cited source files absent. Not independently rerun and not used to change any scientific verdict.'}
save(ROOT/'CONTINUATION_MANIFEST.json',manifest)
save(ROOT/'AUTHORIZATION.json',{'user_instruction':'执行，暂时解除时间限制','authorized_at':now(),'manifest_sha256':sha(ROOT/'CONTINUATION_MANIFEST.json'),
 'policy':'Independent branches continue; only scientific PASS parents may release children; no retry, no new cases, global count <=65.',
 'wall_limit_override':'Temporary for this independent continuation batch: per-case, phase and global wall limits recorded as historical references and not enforced. Record actual elapsed time; do not claim original budget compliance.',
 'scientific_criteria_models_circuits_inputs_unchanged':True,'original_STOPPED_and_G0_W_FAIL_preserved':True})
save(ROOT/'PREFLIGHT_RESULT.json',{'status':'READY_UNDER_EXPLICIT_TEMPORARY_WALL_LIMIT_WAIVER','cases':30,'dependency_ready':ready,'new_solver_starts':0,'global_starts':35,'old_cost_gate_passed':False,'unknown_historical_time_not_assumed_zero':True})
shutil.copy2('/workspace/prepare_remaining_continuation.py',ROOT/'prepare_remaining_continuation.py')
save('/workspace/continuation-current.json',{'root':str(ROOT),'branch':'formal/'+ROOT.name})
print(json.dumps({'root':str(ROOT),'dependency_ready':ready,'case_count':len(cases),'new_solver_starts':0},ensure_ascii=False))
