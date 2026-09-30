import json, time, sys, urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
LOCAL=ROOT/'outputs/long_sentence_imagination/2026-09-30_11회차'
mode=sys.argv[1] if len(sys.argv)>1 else 'main'
if mode=='main':
    message=(HERE/'request.txt').read_text()+f'\n입력 폴더: {LOCAL}/system_inputs\n출력 폴더: {LOCAL}/system_main'
else:
    message=f'앞서 정산한 계량기 자료에서 zone B 요율만 3에서 5로 바뀌었어요. 다른 입력과 판정 규칙은 그대로입니다. 기존 검침 계산을 가능한 한 재사용하고 네 산출물과 검증을 {LOCAL}/system_variant에 만들어 주세요. 원래 출력은 보존하세요.'
start=time.time()
request=urllib.request.Request('http://127.0.0.1:8765/system-ai/chat',data=json.dumps(dict(message=message,origin='training')).encode(),headers={'Content-Type':'application/json'},method='POST')
try:
    with urllib.request.urlopen(request,timeout=1800) as response: body=response.read().decode()
    record={'mode':mode,'elapsed_seconds':time.time()-start,'response':json.loads(body)}
except Exception as exc: record={'mode':mode,'elapsed_seconds':time.time()-start,'error':str(exc)}
(LOCAL/f'system_{mode}_response.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
print(json.dumps(record,ensure_ascii=False))
