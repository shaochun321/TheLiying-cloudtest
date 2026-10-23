from pathlib import Path
import hashlib,json,re
J=json.loads(Path('/workspace/repair-v2-current.json').read_text());P=Path(J['root']);D=P/'runs/C0_CORRECTED_50MS';p=json.loads((D/'plan.json').read_text());old=Path(p['baseline_deck']).read_text();actual=Path(p['deck']).read_text()
def sha(f):
 with Path(f).open('rb') as h:return hashlib.file_digest(h,'sha256').hexdigest()
def check(text):
 a,b=old.splitlines(),text.splitlines();lo=[x.strip().lower() for x in b if x.strip() and not x.strip().startswith('*')]
 if lo.count('.control')!=1 or lo.count('.endc')!=1:return False
 analyses=[x for x in lo if re.match(r'^\.?\s*(?:tran|op|dc|ac|noise|pz|tf|sens|disto)\b',x)]
 if analyses!=['tran 0.001 0.05 0 0.000125']:return False
 # Exact actual source text equality outside endpoint/save/output path: also rejects altered models, initialization, options, inputs, second controls.
 keep=lambda ls:[l for l in ls if not l.startswith(('.save ','tran ','write '))]
 if keep(a)!=keep(b):return False
 s=[l.split()[1:] for l in b if l.startswith('.save ')];os=[l.split()[1:] for l in a if l.startswith('.save ')]
 if len(s)!=1 or len(os)!=1 or not set(os[0]).issubset(s[0]):return False
 if [l for l in b if l.startswith('write ')]!=['write '+p['raw']]:return False
 return True
assert sha(p['baseline_deck'])==p['baseline_deck_sha256'] and sha(p['deck'])==p['deck_sha256']
assert all(sha(f)==h for f,h in p['assets'].items())
tests={'actual_generated_deck_accepted':check(actual),'uic_rejected':not check(actual.replace('tran 0.001 0.05 0 0.000125','tran 0.001 0.05 0 0.000125 uic')),'first_time_parameter_rejected':not check(actual.replace('tran 0.001','tran 0.000125')),'maximum_internal_step_rejected':not check(actual.replace('tran 0.001 0.05 0 0.000125','tran 0.001 0.05 0 0.00025')),'component_change_rejected':not check(actual.replace('rint vsrc vdd 10','rint vsrc vdd 11')),'second_analysis_rejected':not check(actual.replace('.endc','op\n.endc')),'second_control_block_rejected':not check(actual+'\n.control\ntran 1 2\n.endc\n'),'initial_state_override_rejected':not check(actual.replace('.control','.ic v(vdd)=3\n.control')),'model_path_change_rejected':not check(actual.replace('.include ','.include /wrong/')),'all_model_assets_identical':True,'no_extra_measurement_circuit':True,'zero_native_solver_starts':True}
assert all(tests.values()),tests
out={'result':'PASS','checks':tests,'actual_analysis':'tran 0.001 0.05 0 0.000125','original_analysis':'tran 0.001 39.2 0 0.000125','only_analysis_token_changed':'stop','actual_command':p['command'],'cwd':p['cwd'],'deck_sha256':p['deck_sha256'],'baseline_deck_sha256':p['baseline_deck_sha256'],'assets_sha256':p['assets'],'diagnostic_save_count':len(p['required_vectors']),'native_starts_by_preflight':0,'allowance_record':'AUTHORIZATION.json'}
(P/'EXECUTOR_PREFLIGHT.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
