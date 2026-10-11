"""Isolated HTTP adapter probe: production list/file code, synthetic auth and root.
Infrastructure-only source inspection; no live DB, warehouse or public service mutation.
"""
import json
import sys
import shutil
from pathlib import Path
from urllib.parse import urljoin

ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/'backend'))
import boot_paths  # noqa: E402
from fastapi import FastAPI
from fastapi.testclient import TestClient
import portal_warehouse as wh

OUT=ROOT/'outputs/long_sentence_imagination/2026-10-12_59회차'
label=sys.argv[1] if len(sys.argv)>1 else 'before'
source=OUT/'trainer/warehouse';root=OUT/('http_'+label)/'warehouse'
shutil.copytree(source,root,dirs_exist_ok=True)
wh._WAREHOUSE_ROOT=root
wh._ensure_warehouses=lambda:None
wh._check_secret=lambda secret:None
wh._core=lambda:None
wh._viewer_level=lambda core,request:('fixture',int(request.headers.get('x-test-level','0')))
app=FastAPI()
app.add_api_route('/f',wh.node_file,methods=['GET'])
@app.get('/manifest')
def manifest(level:int=0):
    files,total=wh._walk_accessible(level)
    return {'files':files,'total':total}
client=TestClient(app)
rows=[]
for lv in range(5):
    files=client.get('/manifest',params={'level':lv}).json()['files']
    failures=[]
    for f in files:
        if f.get('link'):continue
        response=client.get('/f',params={'path':f['name'],'download':1},headers={'x-test-level':str(lv)})
        expected=next((root/str(i)/f['name'] for i in range(lv,-1,-1) if (root/str(i)/f['name']).is_file()))
        if response.status_code!=200 or response.content!=expected.read_bytes():failures.append(f['name'])
    upper=client.get('/f',params={'path':'자료/문서 4-39.html'},headers={'x-test-level':str(lv)})
    rows.append({'level':lv,'manifest':len(files),'byte_failures':failures,'level4_status':upper.status_code})
# Isolated boundary extension: hidden ancestors and symlink across levels.
(root/'0/.internal').mkdir(exist_ok=True)
(root/'0/.internal/private.txt').write_text('synthetic hidden content')
(root/'0/.secret.txt').write_text('synthetic sidecar')
(root/'0/upper-alias.html').symlink_to(root/'4/자료/문서 4-39.html')
files=client.get('/manifest').json()['files']
names={r['name'] for r in files}
boundaries=[]
for rel in ['.internal/private.txt','.secret.txt','upper-alias.html']:
    r=client.get('/f',params={'path':rel})
    boundaries.append({'path':rel,'listed':rel in names,'status':r.status_code,'bytes':len(r.content)})
# Browser URL resolution of raw relative hrefs against canonical /f?path=.
page='/f?path=%E8%B3%87%E6%96%99/example.html'
relative=urljoin(page,'공통 0.html')
response=client.get(relative)
result={'scope':'production list/file routes; auth/secret/materialization stubbed; no real network',
        'levels':rows,'boundaries':boundaries,'relative_href':{'resolved':relative,'status':response.status_code}}
(OUT/('http_'+label+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
