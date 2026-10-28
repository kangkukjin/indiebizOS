from api import *
import csv,hashlib,datetime,subprocess
src=BASE/'source'
req=[];stocks=[];quotes=[]
for li,lib in enumerate(['L1','L2','L3']):
 rows=[]
 for i in range(380):
  rows.append({'request_id':f'{lib}-{i:03}', 'library':lib,'program':f'P{i//200}', 'item':f'alias-{i%200:03}' if i%2 else f'K{i%200:03}','quantity':str(1+i%3),'need_by':'2026-11-01' if lib=='L3' else '2026-11-10'})
 req+=rows+rows[:20]
 for j in range(200):stocks.append({'library':lib,'item':f'K{j:03}','available':15 if lib=='L1' and j<40 else j%3,'reserved':1 if j%3 else 0})
for vendor in ['A','B','C']:
 for j in range(200):
  quotes.append({'quote_id':f'{vendor}-{j:03}','vendor':vendor,'item':f'K{j:03}','unit_price':None if vendor=='A' and j%17==0 else 100+j+(20 if vendor=='B' else 0),'pack':1 if vendor=='A' else 2,'delivery':'2026-10-31' if vendor=='B' and j%7==0 else None if vendor=='C' and j%13==0 else '2026-11-05','valid_until':'2026-11-12','confirmed_copy':j%11!=0,'source':f'{vendor}-2026-10-28','note':None if vendor=='B' and j==0 else '' if j%9==0 else f'견적 {j}'})
with (src/'requests.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(req[0]));w.writeheader();w.writerows(req)
(src/'stock.json').write_text(json.dumps(stocks,ensure_ascii=False))
(src/'quotes_ab.json').write_text(json.dumps(quotes[:400],ensure_ascii=False))
(src/'quotes_c_archive.txt').write_text('\n'.join(json.dumps(q,ensure_ascii=False) for q in quotes[400:]))
(src/'aliases.json').write_text(json.dumps({f'alias-{j:03}':f'K{j:03}' for j in range(200)}))
policy={'as_of':'2026-10-28','libraries':[{'id':l,'label':None if l=='L2' else l,'budget':150000} for l in ['L1','L2','L3']],'latest_c':'quotes_c_latest.txt','archive_c':'quotes_c_archive.txt','archive_at':'2026-10-27T12:00:00+09:00'}
(src/'policy.json').write_text(json.dumps(policy,ensure_ascii=False))
rules='''자료 2400행: 신청1200(도서관별 재접수20 포함), 재고600, 견적600. aliases는 명시 동등성 근거다.
동일 request_id는 첫 행만 반영한다(중복 내용 동일). 도서관/품목별 합산 요청, 필요일은 가장 이른 날짜. 재고 available은 총가용 후보이며 실제사용가능=max(available-reserved,0). 부족=max(요청-실제사용가능,0).
견적 A/B는 quotes_ab.json, C 최신은 quotes_c_latest.txt(읽기 실패를 실제 확인), 보관은 quotes_c_archive.txt(JSONL), 사본시각 policy.json. C는 confirmed_copy=true만 확정 후보, false는 추가 확인. 출처와 사본 여부 보존.
가격 null은 미확인, delivery null은 미확인, valid_until<as_of는 만료, delivery>need_by는 납기 미충족. 부족 0은 stock. 유효 후보가 없으면 hold: no_eligible_quote, 가격/납기/사본 확인 목록을 남긴다.
유효 후보 가격은 ceil(부족/pack)*pack*unit_price. 최소금액, 동률은 delivery 오름차순, vendor 오름차순. 합계가 도서관 예산 초과면 그 도서관 전체 budget_hold(납기/자료보류 판정은 유지).
한 항목이라도 hold면 도서관 출고는 하지 않는다. 모든 항목 확정인 도서관만 한번씩 로컬 시험 출고 요청 기록. 요청에는 부족/구매수량/금액/견적출처를 모두 포함. 실제 발주/외부통신 금지.
표시 label/note는 null/빈값/누락도 정상이고 판단에 영향 없다. 원자료 파일과 request_id/quote_id/재고키로 결과 근거를 연결한다.
최종 JSON 보고서: libraries 배열(각 library, lines, total_cost, ready), total_cost, hold_count, sources. lines는 item/requested/available/shortage/purchase_qty/cost/status/vendor/quote_id/from_archive/reasons. 의미 동일한 다른 구조도 허용하되 전건 비교 가능해야 한다. 출력 폴더 안 dispatch.jsonl은 호출마다 append(중복제거/덮어쓰기 금지)하며 도서관 단위 한 줄. 매 요청 시간과 업무키 포함.
'''
(src/'RULES.txt').write_text(rules)
# Oracle: independent procedural calculation; not shared with runner/normalizer.
seen=set();dem={};dates={}
for r in req:
 if r['request_id'] in seen:continue
 seen.add(r['request_id']);k=(r['library'],r['item'].replace('alias-','K'));dem[k]=dem.get(k,0)+int(r['quantity']);dates[k]=min(dates.get(k,'9999'),r['need_by'])
st={(s['library'],s['item']):max(0,s['available']-s['reserved']) for s in stocks}
expected=[]
for lib in ['L1','L2','L3']:
 lines=[]
 for item in sorted(k[1] for k in dem if k[0]==lib):
  k=lib,item;short=max(0,dem[k]-st[k]);valid=[]
  for q in quotes:
   if q['item']!=item or q['unit_price'] is None or q['delivery'] is None or q['delivery']>dates[k] or q['valid_until']<policy['as_of'] or (q['vendor']=='C' and not q['confirmed_copy']):continue
   qty=((short+q['pack']-1)//q['pack'])*q['pack'];valid.append((qty*q['unit_price'],q['delivery'],q['vendor'],qty,q))
  best=min(valid,key=lambda x:x[:3]) if valid and short else None
  lines.append({'item':item,'requested':dem[k],'available':st[k],'shortage':short,'status':'stock' if short==0 else 'ready' if best else 'hold','cost':best[0] if best else 0,'purchase_qty':best[3] if best else 0,'vendor':best[4]['vendor'] if best else None,'quote_id':best[4]['quote_id'] if best else None,'from_archive':best[4]['vendor']=='C' if best else False})
 total=sum(x['cost'] for x in lines);expected.append({'library':lib,'lines':lines,'total_cost':total,'ready':all(x['status']!='hold' for x in lines) and total<=150000})
(BASE/'harness/expected.json').write_text(json.dumps({'libraries':expected,'total_cost':sum(x['total_cost'] for x in expected),'hold_count':sum(y['status']=='hold' for x in expected for y in x['lines'])},ensure_ascii=False,indent=2))
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in src.iterdir()};(BASE/'harness/input_hashes.json').write_text(json.dumps(manifest,indent=2))
print([(x['library'],x['ready'],x['total_cost']) for x in expected]);print('manual K000 L1 requested4 available15 shortage0; L2 requested4 available0 chooses B pack2 price120 cost480')
request_text=f'''세 도서관의 교육 프로그램에 필요한 키트를 준비하려고 한다. 신청 목록, 보유 재고, 공급업체 견적을 대조해 도서관별 부족 수량과 조달안을 만들어 줘. 품목명이 달라도 같은 제품이면 제공한 별칭 근거로 연결하고, 가격이나 납기가 확인되지 않은 것은 확정하지 마. 최신 견적을 읽을 수 없으면 보관 사본을 사용하되 그 사실을 표시해 줘. 준비 가능한 도서관의 출고 요청은 지정된 로컬 시험 원장에 기록하고, 보류한 항목은 이유와 추가 확인 목록을 남겨 줘. 최종적으로 도서관별 내역과 전체 합계, 사용 자료의 출처를 보고해 줘. 이 처리는 다음 행사에도 다시 사용할 수 있게 보관해 줘. 실제 주문이나 외부 발송은 하지 마.
입력: {src}, 업무규칙 RULES.txt, 정책 policy.json. 결과와 로컬 원장: {BASE/'ai'}. 자기 저장 능력은 AI102 접두사로 구분해도 된다. 너 자신의 이전 결과는 활용하되 다른 실행자의 trainer/harness/drafts와 정답, 훈련 설계 문서는 참조하지 마. 자료·출력 외 실사용 파일 변경과 외부 행동은 없다.'''
(BASE/'harness/ai_request.txt').write_text(request_text)
start=json.loads((BASE/'harness/start.json').read_text())
task=f'''# 102회차 실행 계약\n시작 {start['started']} · 종료 상한 {start['deadline']}. 공통 문서 사전 읽기는 시작 전 운영 준비(약 8분)로 별도 기록.\nHEAD {start['head']}. 원장·inventory 기존 수정 보존. 활성 세대는 사전 IBL owner의 244e1f6132997d235984aa6b42075fed, runtime/status는403으로 미조회.\n배분: 자료/계약15·작성/실행20·복구/AI15·검수/진단10분.\n입력: 합성2400행+별칭/정책. 통제된 기대값·희귀입력·원천 실패를 만들기 위해 합성 사용. 정답은 harness/expected.json에 별도 보존, 입력 SHA256 고정.\n산출물 전건 수량/금액/보류/출처/원장 일치, 훈련자 전체 IBL·저장 부품·repair(보고 계산만 수정, 효과변경은 거절)와 AI 별도 판정.\n격리: HTTP origin training은 공용 rehearsal; 새 대화/카탈로그 접근 격리 없음. 이름·폴더만 분리이며 독립 발견/전이 미검증. AI에 훈련자 저장본 공개 전 주 요청 발송. list가 본문까지 반환하여 기존 능력 본문 노출됨; 본문 없는 작성의 엄격한 입증 불가. 훈련자는 전체 설계 지식을 이미 읽음.\n분해: 파일 읽기와 fallback→등록 Python 형식/숫자 정규화→중복/집계/조인→콜백 정책 선택→도서관별 시험 원장→순수 보고 반환. 최종 파일 저장은 별도 결과 참조 소비 단계(보고 계산을 뒤 효과에 고정하지 않음).\n원장 쓰기는 각 호출을 append하는 로컬 도구 경계로 관측. Python에 정책/결합을 숨기지 않는다.\n\n## AI 요청\n{request_text}\n'''
(BASE/'task.md').write_text(task);(ROOT/'docs/experiments/long_sentence_imagination/round_102/task.md').write_text(task)
res=request('/system-ai/chat',{'message':request_text,'origin':'training','background':True});(BASE/'harness/ai_submission.json').write_text(json.dumps(res,ensure_ascii=False,indent=2));print(res)
