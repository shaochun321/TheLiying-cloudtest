from pathlib import Path
import json,sys,hashlib
J=json.loads(Path('/workspace/repair-current.json').read_text());P=Path(J['root']);S=Path(J['source']);R=Path(J['previous_batch'])
sys.path.insert(0,str(S))
from runtime.decks import case_assets
A=case_assets('CHAIN_12_W_F');old=(R/'runs/CHAIN_12_W_F/CHAIN_12_W_F.cir').read_text()
D=P/'runs/C0_ORIGINAL_50MS';D.mkdir(parents=True)
save=list(dict.fromkeys(A['save']+['v('+n+')' for n in sorted(A['netlist'].domain) if A['netlist'].domain[n]=='elec']))
lines=old.splitlines();out=[]
for l in lines:
 if l.startswith('.save '):l='.save '+' '.join(save)
 elif l.startswith('tran '):
  assert l=='tran 0.001 39.2 0 0.000125',l
  fields=l.split();fields[2]='0.05';l=' '.join(fields)
 elif l.startswith('write '):l='write '+str(D/'C0_ORIGINAL_50MS.raw')
 out.append(l)
text='\n'.join(out)+'\n';(D/'C0_ORIGINAL_50MS.cir').write_text(text)
physical=lambda ls:[l for l in ls if not l.startswith(('.save ','tran ','write '))]
assert physical(lines)==physical(text.splitlines())
p={'case':{**A['case'],'case_id':'C0_ORIGINAL_50MS','analysis':'tran 0.001 0.05 0 0.000125','x_stop':.05,'max_step_s':.000125},'parent_case':'CHAIN_12_W_F','deck':str(D/'C0_ORIGINAL_50MS.cir'),'raw':str(D/'C0_ORIGINAL_50MS.raw'),'required_vectors':save,'deck_sha256':hashlib.sha256(text.encode()).hexdigest(),'physical_netlist_and_stimulus_unchanged':True,'new_probe_sources':0,'qualification_claimed':False,'optional_diagnostic':True}
(D/'plan.json').write_text(json.dumps(p,indent=2)+'\n')
print(json.dumps({'directory':str(D),'saved_vectors':len(save),'physical_and_inputs_unchanged':True}))
