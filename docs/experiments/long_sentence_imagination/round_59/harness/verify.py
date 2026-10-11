"""Independent byte/visibility/link oracle; not provided to either executor."""
import hashlib
import json
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[5]
OUT=ROOT/'outputs/long_sentence_imagination/2026-10-12_59회차'
class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        for k,v in attrs:
            if k=='href':self.links.append(v)
def inspect(name):
    folder=OUT/name;root=folder/'warehouse'
    actual={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    oracle=json.loads((OUT/'oracle.json').read_text())
    expected=dict(oracle['expected'])
    if name=='empty':expected={}
    if name=='new_conflict':
        source='0/자료/문서 0-18.html';target='2/자료/문서 0-18.html'
        expected[source]=oracle['initial'][source]
        expected[target]=hashlib.sha256('새 충돌: 수동 파일 보존\n'.encode()).hexdigest()
    result={'name':name,'files':len(actual),'bytes_exact':actual==expected,
            'missing':sorted(set(expected)-set(actual)),'extra':sorted(set(actual)-set(expected))}
    result_path=folder/'result/result.json'
    if result_path.exists():
        doc=json.loads(result_path.read_text());result['schema']=list(doc)
        if 'decisions' in doc:
            result['decisions']=dict(Counter(r.get('status',r.get('decision','unknown')) for r in doc['decisions']))
            result['source_links']=doc.get('source_links')
        if 'visitor_lists' in doc:
            doc['views']=[]
            for lv,files in doc['visitor_lists'].items():
                summary=doc['link_check'][lv]
                doc['views'].append({'level':int(lv),'files':[{'relative':r['relative'],'sha256':actual[r['served_from']]} for r in files],
                                     'links':[None]*summary['internal'],'broken':summary['broken']})
            result['summary']=doc['summary']
        if isinstance(doc.get('views'),list):
            checks=[]
            for view in doc['views']:
                lv=view['level'];expected={}
                for p in sorted(root.rglob('*')):
                    if p.is_file():
                        level=int(p.relative_to(root).parts[0]);rel='/'.join(p.relative_to(root).parts[1:])
                        if level<=lv and (rel not in expected or level>expected[rel][0]):expected[rel]=(level,p)
                got={r['relative']:r['sha256'] for r in view['files']}
                want={r:hashlib.sha256(p.read_bytes()).hexdigest() for r,(_,p) in expected.items()}
                broken=[];n=0
                for rel,(_,p) in expected.items():
                    parser=Links();parser.feed(p.read_text())
                    for link in parser.links:
                        target=str(Path(rel).parent/link);n+=1
                        if target not in expected:broken.append((rel,target))
                checks.append({'level':lv,'visible':len(expected),'files_exact':got==want,'links':n,'broken':len(broken),'link_counts_exact':n==len(view['links']) and len(broken)==len(view['broken'])})
            result['views']=checks
    return result
if __name__=='__main__':
    import sys
    results=[inspect(n) for n in (sys.argv[1:] or ['trainer','variant','ai'])]
    print(json.dumps(results,ensure_ascii=False,indent=2))
    (OUT/'verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
