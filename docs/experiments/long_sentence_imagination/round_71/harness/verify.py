"""Independent oracle over saved results and artifact bytes; no system calls."""
import boot_paths  # noqa: F401
import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT/'outputs/long_sentence_imagination/2026-10-15_71회차'

def verify(label):
    evidence=json.loads((OUT/label/'evidence.json').read_text())
    checks=[]
    for run in evidence:
        name, variant=run['member'],run['variant']
        result=run['result']['result']; artifacts=run['artifacts']
        if variant=='concurrent':
            assert run['result']['state']=='failed' and result['error']=='file_changed'
            assert base64.b64decode(artifacts['copy.txt'])==b'human intervened'
            checks.append([name,variant,'human edit preserved']);continue
        assert run['result']['state']=='completed',run
        report=json.loads(base64.b64decode(artifacts['summary.json']))
        expected=[]
        for i in range(6):
            missing=variant=='broken' and i==2
            amount=sum((j+1)*((i+1)*100+(7 if name=='B' else 0)) for j in range(8) if j%4!=0)
            expected.append({'file':f'batch{i+1:02d}.json','ok':not missing,'count':0 if missing else 6,'amount':0 if missing else amount})
        if variant=='recovered':expected.reverse()
        assert report=={'files':expected,'total':sum(r['amount'] for r in expected),'missing':int(variant=='broken')}
        text=base64.b64decode(artifacts['summary.txt']).decode()
        assert str(report['total']) in text and f"미확인 {report['missing']}파일" in text
        assert base64.b64decode(artifacts['copy.txt'])=='첫 줄\r\n둘째 줄 🐣\r\n'.encode()
        value=result['app_result']['value'];assert value['copy_equal'] and value['summary_equal']
        checks.append([name,variant,report['total'],report['missing']])
    assert not (OUT/label/'hub/summary.json').exists()
    assert not (OUT/label/'hub/data/phone_jobs.db').exists()
    assert json.loads((OUT/label/'conflict.json').read_text())['preserved']
    (OUT/label/'verification.json').write_text(json.dumps({'passed':True,'checks':checks},ensure_ascii=False,indent=2))
    print(json.dumps(checks,ensure_ascii=False))

if __name__=='__main__':
    import sys
    verify(sys.argv[1])
