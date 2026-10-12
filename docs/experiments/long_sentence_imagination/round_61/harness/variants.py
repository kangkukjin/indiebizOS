"""Post-repair new inputs: strict codes, source spelling, no movements, empty files."""
import json
from pathlib import Path
from prepare import OUT, write

rows=[
 dict(sku='A',warehouse='서울|A',opening=10,counted=11),
 dict(sku='a',warehouse='서울|A',opening=20,counted=18),
 dict(sku='01',warehouse='창고<&\n둘',opening=30,counted=33),
 dict(sku='1',warehouse='창고<&\n둘',opening=40,counted=44),
 dict(sku='é',warehouse='부산',opening=50,counted=55),
 dict(sku='NO-EVENT',warehouse='부산',opening=60,counted=60),
]
events=[dict(id=f'X{i}',version=1,sku=r['sku'],warehouse=r['warehouse'],kind='출고' if i==1 else '입고',qty=i+1) for i,r in enumerate(rows[:5])]
events[-1]['sku']='e\u0301';events[-1]['warehouse']='부산'
events.append(dict(id='EXTRA',version=1,sku='새품목',warehouse='부산',kind='반품',qty=None))
for case,stock,ev in [('new',rows,events),('empty',[],[])]:
    dest=OUT/'trainer'/case/'input'
    write(dest/'stock.json',stock);write(dest/'manifest.json',{'files':[f'events_{i}.json' for i in range(4)]})
    for i in range(4): write(dest/f'events_{i}.json',ev[i::4])
    payload=json.loads((OUT/'v3_base.json').read_text())
    payload['inputs']={'input':str(dest),'out':str(OUT/'trainer'/case/'fixed')}
    write(OUT/f'v3_{case}.json',payload)
