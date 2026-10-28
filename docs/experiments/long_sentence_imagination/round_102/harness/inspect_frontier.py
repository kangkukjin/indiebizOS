from api import *
sys.path.insert(0,str(ROOT/'backend'));import boot_paths
from ibl_v2_compile import compile_program
from ibl_v2_adapters import load_registry
from ibl_v2_repair_graph import Projection,walk
v=json.loads((BASE/'harness/probe_frontier.json').read_text());p=json.loads((BASE/'trainer/probe_request.json').read_text())
plan=compile_program(v['source']+v['library_source'],load_registry(str(ROOT)),inputs=p['inputs'])
class Inspect(Projection):
 def full(self,node,seen=None):
  import traceback
  dynamic=[(n.kind,n.data.get('fn').kind if n.data.get('fn') else '') for n in walk(node) if n.kind in ('named_call','pure_call')]
  if dynamic and not seen:
   print('FULL',node.kind,node.data.get('name'),dynamic[:6]);print(''.join(traceback.format_stack(limit=5)))
  return super().full(node,seen)
x=Inspect(plan);x.expr(x.root,{});print('retained',len(x.retained),'nodes',len(x.nodes))
