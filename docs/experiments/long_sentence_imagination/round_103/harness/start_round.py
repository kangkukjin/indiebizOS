import sys,json,shutil,hashlib,datetime
from pathlib import Path
ROOT=Path('/Users/kangkukjin/Desktop/AI/indiebizOS');B1=ROOT/'outputs/long_sentence_imagination/2026-10-28_102회차';B2=ROOT/'outputs/long_sentence_imagination/2026-10-28_103회차'
sys.path.insert(0,str(B1/'harness'));from api import request
assert (B1/'harness/round_closed.json').exists()
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
start={'started':now.isoformat(),'deadline':(now+datetime.timedelta(minutes=60)).isoformat(),'preparation':'변형 자료와 프로그램 초안은 102회차 예산 중 작성, 둘째 요구는 미공개였다. 훈련자는 설계 전체를 이미 읽었다.'}
(B2/'harness/start.json').write_text(json.dumps(start,ensure_ascii=False,indent=2))
for p in (B1/'harness/variant_private').iterdir():shutil.copyfile(p,B2/'source'/p.name)
shutil.copyfile(B2/'trainer/normalize_vendor.py',ROOT/'data/scripts/ls103_normalize.py')
msg=f'''이제 여러 도서관의 결과를 묶어 지역 전체 공급 계획을 만들어 줘. 새 공급업체는 포장 단위가 다르고 운송비도 별도로 제시한다. 납기 우선안과 예산 우선안을 비교하고, 도서관 사이의 남는 재고를 이동하는 안도 함께 제안해 줘. 앞서 보관한 처리 능력을 활용하고, 이번 지역 계획도 다음 행사에서 다시 사용할 수 있게 보관해 줘. 앞서 기록한 출고 요청을 다시 등록하지 말고 이번에는 비교 계획과 제안서를 만들어 줘. 너 자신의 이전 산출물과 저장 능력은 활용해도 되지만 다른 실행자의 해법이나 정답은 참조하지 마.
기존 자료와 업무규칙: {B1}/source. 너의 이전 결과와 저장 스크립트: {B1}/ai. 새 공급업체 자료와 추가 규칙: {B2}/source/new_vendor.json, {B2}/source/RULES_VARIANT.txt. 출력은 {B2}/ai에 저장해 줘. 다른 실행자의 trainer/harness/drafts, 정답, 훈련 설계 문서는 참조하지 마. 실제 주문·발송 등 외부 행동과 이전 원장 추가는 하지 마. 저장 능력 이름은 AI103 접두사로 구분해도 된다.'''
(B2/'ai_request.txt').write_text(msg)
contract=f'''# 103회차 실행 계약\n\n시작 {start['started']}, 상한 {start['deadline']}. {start['preparation']}\n102회차 완료 자료/저장 능력과 원본 입력을 계승한다. 전용 새 입력 200행 D 견적+정책. 기대값은 공개 전 별도 고정, 102 harness/variant_expected.json.\n훈련자 기존 Read/Demand/Choose 계약 호출, 신규 정규화와 정책으로 지역 4개 안 재조합, 지역 능력 저장 후 제안서 조합에서 실제 사용. 도서관별 600행×4안 전건과 이동 40품목147개·기존 원장 바이트 불변 검증.\n배분: 준비/공개5·작성실행15·저장재호출15·AI검수20·종료5분.\nHTTP training 공용 리허설/카탈로그, 독립 발견·전이 미검증. local API 우회는 L102-1 때문에 계속 사용하며 기본 HTTP 성공과 구분한다. 코어 미수리 상태 유지.\n\n## AI 요청\n{msg}\n'''
D=ROOT/'docs/experiments/long_sentence_imagination/round_103';D.mkdir(parents=True,exist_ok=True);(D/'task.md').write_text(contract);(B2/'task.md').write_text(contract)
ledger=ROOT/'docs/LONG_SENTENCE_IMAGINATION_LEDGER.md';text=ledger.read_text();pos=text.index('## 102회차');text=text[:pos]+'## 103회차 — 지역 조달 비교·재고 이동 재조합 (2026-10-28, 진행 중)\n\n[과제](experiments/long_sentence_imagination/round_103/task.md). 102회차 완료 능력과 결과 계승.\n\n'+text[pos:];ledger.write_text(text)
for label,p in [('trainer',B1/'trainer/dispatch.jsonl'),('probe',B1/'trainer/probe_dispatch.jsonl'),('ai',B1/'ai/dispatch.jsonl')]:
 (B2/'harness'/f'prior_{label}_ledger.json').write_text(json.dumps({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':len(p.read_bytes())}))
r=request('/system-ai/chat',{'message':msg,'origin':'training','background':True});(B2/'harness/ai_submit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(r)
