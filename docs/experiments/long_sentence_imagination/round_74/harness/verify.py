"""Independent source-byte oracle; no runtime response is used as the expected text."""
import boot_paths  # noqa: F401
import base64
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT/'outputs/long_sentence_imagination/2026-10-15_74회차'

def expected(member, variant, numbered=False, unicode_boundary=False):
    sections = []
    indexes = list(range(1,13))
    if variant == 'recovered': indexes.reverse()
    for n, i in enumerate(indexes):
        ending = ('\n','\r\n','\r')[(i-1)%3]
        raw = ending.join([f'비공개 {member} 내부{i}',('배포 제외 표지\u2028비공개 구분자\v표지 계속' if unicode_boundary and i==1 else '배포 제외 표지'),
            f'{member} 절차{i} 첫 줄  ',f'  한글 🧭 "인용"\t{i}',f'마지막 공개 줄 {i}  ',
            '비공개 부록','내부 연락처 가상','끝'])+ending
        first,last = (1,1) if variant=='recovered' and n==0 else (3,5)
        missing = variant=='broken' and i==4
        import io
        selected = io.StringIO(raw, newline='').readlines()[first-1:last]
        text = ''.join(f'{n}\t{line}' for n,line in enumerate(selected,first)) if numbered else ''.join(selected)
        sections.append(dict(id=f'S{i:02d}',path=f'doc{i:02d}.txt',start_line=first,end_line=last,
            status='unavailable' if missing else 'ok',text=None if missing else text))
    absent = [r['path'] for r in sections if r['status']=='unavailable']
    handbook=''.join('## '+r['id']+'\n'+(r['text'] if r['status']=='ok' else '[미확인: '+r['path']+']')+'\n' for r in sections)+f'미확인 {len(absent)}건\n'
    return {'sections':sections,'missing_files':absent}, handbook.encode()

def verify(label):
    rows=json.loads((OUT/label/'evidence.json').read_text())
    checks=[]
    for r in rows:
        failures=[]
        def check(ok, name):
            if not ok: failures.append(name)
        check(r['inputs_unchanged'],'source bytes changed')
        check(r.get('reexecuted')==0,'duplicate execution')
        if r['variant']=='cancel':
            check(r['result']['state']=='cancelled','cancel state')
            check(not r['artifacts'],'cancel saved files')
        else:
            check(r['result']['state']=='completed','completion state')
            ex,handbook=expected(r['member'],r['variant'],numbered='review' in label,unicode_boundary='unicode' in label)
            artifacts={k:base64.b64decode(v) for k,v in r['artifacts'].items()}
            check(set(artifacts)=={'excerpts.json','handbook.txt'},'output files')
            if 'excerpts.json' in artifacts:
                try: check(json.loads(artifacts['excerpts.json'])==ex,'JSON exact all fields')
                except Exception: failures.append('JSON invalid')
            if 'handbook.txt' in artifacts:check(artifacts['handbook.txt']==handbook,'handbook bytes')
            # Trainer return is supplemental to independent disk evidence.
            if 'AI' not in label:
                result=r['result']['result']
                rvalue=result.get('app_result',{}).get('value',{})
                check(isinstance(rvalue,dict) and rvalue.get('handbook_equal') and rvalue.get('report_equal'),'IBL reread')
        checks.append(dict(member=r['member'],variant=r['variant'],passed=not failures,failures=failures))
    (OUT/label/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
    print(json.dumps(checks,ensure_ascii=False,indent=2))
    return all(r['passed'] for r in checks)

if __name__=='__main__':sys.exit(0 if verify(sys.argv[1]) else 1)
