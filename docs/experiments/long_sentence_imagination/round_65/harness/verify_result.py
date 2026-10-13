"""Independent, read-only artifact oracle. Run on the designated test root."""
import hashlib
import json
from pathlib import Path
import sys

root=Path(sys.argv[1]);variant='--variant' in sys.argv
read=lambda p:json.loads((root/p).read_text(encoding='utf-8'))
settings=read('settings.json');manifest=read('input/manifest.json')
rows=read('input/sample.json')
names=['서울','東京','🌱','한 글','가나다','大阪','🧪','강릉','京都','작업 A','💡','끝']
expected=[{'id':f'{i:02d}','name':n,'value':i} for i,n in enumerate(names,1)]
assert rows==expected
for k,v in manifest.items():
 if k.startswith(('input/','protected/')):
  assert hashlib.sha256((root/k).read_bytes()).hexdigest()==v,k
for label,factor,total in [('out-a',2,156)]+([('out-b',3,234)] if variant else []):
 result=read(label+'/result.json')
 assert result==[{**r,'result':r['value']*factor} for r in expected],label
 assert sum(r['result'] for r in result)==total
assert read('out-a/empty.json')==[]
assert settings['factor']==(3 if variant else 2)
assert settings['output']==('out-b' if variant else 'out-a')
assert settings['unknown_setting']=={'keep':True}
assert settings['user_note']==('사용자가 새로 쓴 메모 東京 🌱' if variant else '보존할 메모 🌱')
events=[json.loads(l) for l in (root/'events.jsonl').read_text(encoding='utf-8').splitlines()]
counts={k:sum(e['kind']==k for e in events) for k in ['patch','conflict','process','service_start','service_stop']}
if variant:
 assert counts['patch']==2,counts
 assert counts['conflict']>=1,counts
 assert sum(e['kind']=='process' and e['count']==12 for e in events)==2,counts
 backup=root/'data/_backups/2026-10-14_tv1_setup'
 restored=root/'restored-copy.json'
 assert restored.exists()
 assert any(restored.read_bytes()==b.read_bytes() for b in backup.glob('*.json'))
print(json.dumps({'verified':True,'variant':variant,'counts':counts,'settings':settings,'results':['out-a','out-b'] if variant else ['out-a']},ensure_ascii=False))
