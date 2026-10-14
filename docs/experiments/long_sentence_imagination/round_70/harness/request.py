"""Build an explicit IBL request without implementing any task step."""
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
HERE=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/long_sentence_imagination/2026-10-15_70회차'
p=argparse.ArgumentParser();p.add_argument('version');p.add_argument('phase');p.add_argument('label')
p.add_argument('--check',action='store_true');p.add_argument('--previous',default='');a=p.parse_args()
payload={'code':(HERE/f'main_{a.version}.ibl').read_text(),'edition':2,'origin':'training','project_id':'study',
         'inputs':{'input':str(OUT/f'trainer-input/{a.phase}.json'),'out':str(OUT/a.label),
                   'previous':str(OUT/a.previous/'collected.json') if a.previous else ''}}
if a.check:payload['check']=True
path=OUT/f'{a.label}-request.json';path.write_text(json.dumps(payload,ensure_ascii=False));print(path)
