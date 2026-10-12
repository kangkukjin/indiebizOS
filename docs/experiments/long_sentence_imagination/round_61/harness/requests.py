"""Create explicit requests; transport.py performs HTTP and records terminal replies."""
import argparse
import json
from pathlib import Path
from prepare import OUT, DOC, write

p=argparse.ArgumentParser();p.add_argument('version',choices=['v0','v1','v2','v3']);p.add_argument('case',choices=['base','missing','new','empty']);p.add_argument('--check',action='store_true');a=p.parse_args()
code=(DOC/'drafts'/f'{a.version}.ibl').read_text()
payload={'code':code,'origin':'training','project_id':'수동모드','inputs':{'input':str(OUT/'trainer'/a.case/'input'),'out':str(OUT/'trainer'/a.case/('out' if a.version in ('v0','v1') else 'fixed'))},'budget':{'steps':3000000,'rows':30000}}
if a.check: payload['check']=True
path=OUT/f'{"check_" if a.check else ""}{a.version}_{a.case}.json'
write(path,payload);print(path)
