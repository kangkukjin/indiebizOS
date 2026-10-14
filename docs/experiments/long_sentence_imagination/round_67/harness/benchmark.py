"""Measure the existing JSON reader only, excluding model/HTTP costs."""
import importlib.util
import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT/'backend'))
import boot_paths  # noqa: E402,F401
p=ROOT/'data/packages/installed/tools/system_essentials/essentials_file_io.py'
spec=importlib.util.spec_from_file_location('file_io_bench',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
rows=[{'id':str(i),'amount':23000,'note':'원문 보존'} for i in range(10000)]
body=json.dumps(rows,ensure_ascii=False)
times=[]
for _ in range(11):
    t=time.perf_counter();result=m.structured_data(body,'json','benchmark.json'); times.append(time.perf_counter()-t)
    assert result==rows
tracemalloc.start();m.structured_data(body,'json','benchmark.json');_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
loads=json.loads;calls=[]
def counted(value,*args,**kwargs):
    calls.append(len(value));return loads(value,*args,**kwargs)
json.loads=counted
try:
    assert m.structured_data(body,'json','benchmark.json')==rows
finally:
    json.loads=loads
print(json.dumps({'label':sys.argv[1],'rows':len(rows),'chars':len(body),'seconds':times,'median_s':statistics.median(times),'peak_bytes':peak,'decode_calls':len(calls)},indent=2))
