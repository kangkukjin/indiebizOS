import ast,json,runpy,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
LOCAL=HERE.parents[3]/'outputs/long_sentence_imagination/2026-09-30_11회차'
tree=ast.parse((HERE/'generate.py').read_text())
keep=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom)) or isinstance(n,ast.FunctionDef) and n.name=='oracle']
ns={};exec(compile(ast.Module(body=keep,type_ignores=[]),'oracle','exec'),ns)
oracle=ns['oracle']
load=lambda name:json.loads((LOCAL/'inputs'/f'{name}.json').read_text())['rows']
a,b,m,t=[load(n) for n in ['readings_a','readings_b','meters','tariffs']]
v=json.loads((LOCAL/'tariffs_variant.json').read_text())['rows']
minimal=[dict(meter='M',date='2026-08-01',reading=x,source_id=str(i)) for i,x in enumerate([1,1,2])]
assert oracle(minimal,[dict(meter='M',zone='A',modulus=None)],t)['summary']['extra_rows']==1
for name,rows,rates in [('expected',a+b,t),('expected_variant',a+b,v),('expected_empty_b',a,t)]:
    old=LOCAL/(name+'.json'); backup=LOCAL/(name+'_before_status_fix.json')
    if backup.exists():raise RuntimeError('already corrected')
    shutil.copyfile(old,backup)
    result=oracle(rows,m,rates)
    old.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'name':name,'summary':{k:v for k,v in result['summary'].items() if k!='by_meter'}},ensure_ascii=False))
