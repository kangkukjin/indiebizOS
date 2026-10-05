"""Read-only profile of the two original result references (local evidence required)."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/'backend'))
import boot_paths
import cProfile, pstats, json, time
from supervision_store import TurnStore
from model_result_view import resolve_input_refs
OUT=ROOT/'outputs/long_sentence_imagination/2026-10-05_19회차'
args=json.loads((OUT/'harness/p3_inputs.json').read_text())
ref=args['base']['$ref']
path=next((ROOT/'data/spill/tool_evidence').glob('*/'+ref+'.txt'))
store=TurnStore(path.parent)
if sys.argv[1]=='compare':
    samples=[]
    for _ in range(3):
        pair={}
        restored=[]
        for legacy in [True,False]:
            start=time.perf_counter()
            vals,ns=resolve_input_refs(args,store=store,legacy_fingerprints=legacy)
            pair['legacy' if legacy else 'certified']=time.perf_counter()-start
            restored.append(vals)
        assert restored[0]==restored[1]
        samples.append(pair)
    (OUT/'harness/refs_comparison.json').write_text(json.dumps(samples,indent=2))
    print(json.dumps(samples));sys.exit(0)
prof=cProfile.Profile(); start=time.perf_counter()
prof.enable(); values,notes=resolve_input_refs(args,store=store);prof.disable()
elapsed=time.perf_counter()-start
assert len(values['base']['result']['orders'])==1800
print('elapsed',elapsed,'notes',[(n['name'],n['chars']) for n in notes])
prof.dump_stats(str(OUT/'harness'/('refs_'+sys.argv[1]+'.prof')))
pstats.Stats(prof).sort_stats('cumulative').print_stats(22)
