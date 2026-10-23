from pathlib import Path
import hashlib,json,shutil,sys,uuid,zipfile
OLD=Path('/workspace/thermal-g3-repair/startup-vrest-2026-10-23-15e484ac')
S=Path('/workspace/thermal-g3-qualification/sparse-qualification-2026-10-22-17fb81ea/software/thermal_g3_q1')
PR=Path('/workspace/thermal-g3-formal/independent-continuation-2026-10-23-d2e498c3')
P=Path('/workspace/thermal-g3-repair')/('executor-correction-v2-2026-10-23-'+uuid.uuid4().hex[:8]);P.mkdir()
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
state=json.loads(Path('/workspace/thermal-g3-latest-state.json').read_text());assert state['global_start_count']==40 and state['all_new_solver_processes_reaped']
save('/workspace/repair-v2-current.json',{'root':str(P),'source':str(S),'previous_batch':str(PR),'prior_error_batch':str(OLD)})
(P/'inputs').mkdir();(P/'offline').mkdir();(P/'executor').mkdir()
names=['THERMAL-G3_执行器纠错续接方案_v2_2026-10-23.zip.sha256','THERMAL-G3_执行器纠错续接方案_v2_2026-10-23.zip','给云端agent的续接说明.txt','THERMAL-G3_执行器纠错与原整改续接方案_v2_2026-10-23.md']
for f in Path('/workspace/attachments').glob('*/*'):
 if f.name in names:shutil.copy2(f,P/'inputs'/f.name)
zp=P/'inputs'/names[1];assert sha(zp)==(P/'inputs'/names[0]).read_text().split()[0]
with zipfile.ZipFile(zp) as z:
 assert z.testzip() is None
 for n in [names[2],names[3]]:assert z.read(n)==(P/'inputs'/n).read_bytes()
save(P/'PACKAGE_CHECK.json',{'zip_sha256':sha(zp),'zip_integrity':'PASS','external_documents_match_zip':True})
for n in ['original-chain-startup.json','original-dc-load.json','vrest-branch-inventory.json']:
 shutil.copy2(OLD/'offline'/n,P/'offline'/n)
shutil.copytree(S,P/'software',ignore=shutil.ignore_patterns('__pycache__','results'))
shutil.copy2(PR/'inputs/c05_ekv26_typ.lib',P/'inputs/c05_ekv26_typ.lib')
save(P/'AUTHORIZATION.json',{'user_instruction':'评判后执行，接触时间限制','interpretation':'评审后执行；解除本批墙钟限制','global_starts_before':40,'global_cap':65,'max_new_starts':9,'max_global_after':49,'previous_error_start_retained':True,'across_two_repair_batches_max_starts':10,'budget_revision':'Explicit v2 one-start increase over original two-batch repair allocation accepted by current execute instruction.','one_physical_candidate':True,'automatic_retries':0,'corrected_diagnostic_max_starts':1,'stop_at_first_candidate_failure':True,'effective_wall_limit_s':None,'effective_batch_wall_limit_s':None,'reference_total_wall_limit_s':36600,'waiver_scope':'This batch only. No original phase/global cost gate claimed passed.','exact_global_historical_wall_s':None,'other_formal_cases_authorized':False,'old_qualification_inherited':False})
sys.path.insert(0,str(S));from runtime.decks import case_assets
A=case_assets('CHAIN_12_W_F');olddeck=PR/'runs/CHAIN_12_W_F/CHAIN_12_W_F.cir';old=olddeck.read_text();oldlines=old.splitlines();target=P/'runs/C0_CORRECTED_50MS';target.mkdir(parents=True)
sv=list(dict.fromkeys(A['save']+['v('+n+')' for n in sorted(A['netlist'].domain) if A['netlist'].domain[n]=='elec']))
out=[]
for line in oldlines:
 if line.startswith('.save '):line='.save '+' '.join(sv)
 elif line.startswith('tran '):
  fields=line.split();assert fields==['tran','0.001','39.2','0','0.000125'];fields[2]='0.05';line=' '.join(fields)
 elif line.startswith('write '):line='write '+str(target/'C0_CORRECTED_50MS.raw')
 out.append(line)
deck=target/'C0_CORRECTED_50MS.cir';deck.write_text('\n'.join(out)+'\n')
assets={str(Path(oldlines[1].split()[1])):sha(oldlines[1].split()[1]),'/workspace/thermal-g3-env/host/native/models/ekv26_linux.osdi':sha('/workspace/thermal-g3-env/host/native/models/ekv26_linux.osdi'),'/workspace/thermal-g3-env/host/native/bin/ngspice':sha('/workspace/thermal-g3-env/host/native/bin/ngspice')}
assert assets['/workspace/thermal-g3-env/host/native/bin/ngspice']=='37d80c673bc4c03904ed4434bb3aa9aecd099ecfaeb66b86730a905e8c76ed89'
assert assets['/workspace/thermal-g3-env/host/native/models/ekv26_linux.osdi']=='7c07ae3728941189b77bf0ecfca5ebe56473d01eedc6ea59c46cc32bfdb9a43f'
plan={'case':{**A['case'],'case_id':'C0_CORRECTED_50MS','analysis':'tran 0.001 0.05 0 0.000125','x_stop':.05,'max_step_s':.000125},'parent_case_id':'CHAIN_12_W_F','deck':str(deck),'raw':str(target/'C0_CORRECTED_50MS.raw'),'deck_sha256':sha(deck),'baseline_deck':str(olddeck),'baseline_deck_sha256':sha(olddeck),'assets':assets,'required_vectors':sv,'qualification_claimed':False,'new_circuit_branches':0,'diagnostic_only':True,'command':['/workspace/thermal-g3-env/host/native/bin/ngspice','-n','-b',str(deck)],'cwd':str(target),'original_default_wall_s':300,'scoring_view_policy':'diagnostic only; never pass new por_hold vector into original formal judge by accident'}
save(target/'plan.json',plan)
save(P/'CURRENT_STATUS.json',{'status':'EXECUTOR_PREFLIGHT_REQUIRED','global_starts_before':40,'global_start_count':40,'new_starts':0,'solver_wall_s':0.,'active_case':None,'cases':{'C0_CORRECTED_50MS':'WAITING_PREFLIGHT',**{x:'NOT_STARTED' for x in ['DC_3','CHAIN_STARTUP_0_3S','Q1_MOTHER_PROTOCOL','Q1_MOTHER_HALFSTEP','CHAIN_12_W_F','G0_W','DC_2P7','DC_3P2']}}})
print(json.dumps({'root':str(P),'diagnostic_analysis':plan['case']['analysis'],'saved_vectors':len(sv),'starts_before':40,'max_global_after':49}))
