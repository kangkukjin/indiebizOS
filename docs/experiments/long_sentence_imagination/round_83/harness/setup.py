"""Create synthetic source graph and isolated live training agents; no task solution."""
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[5]
DOC = ROOT / 'docs/experiments/long_sentence_imagination/round_83'
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-20_83회차'
INPUT = OUT / 'inputs'
INPUT.mkdir(parents=True, exist_ok=True)

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))

def api(path, value=None):
    req = urllib.request.Request('http://localhost:8765' + path,
        data=None if value is None else json.dumps(value).encode(),
        headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=30))

pages = {
 'index.json': {'status':'ok', 'text':'가상 시장 자료 시작. 첫 쇼핑 검색, 다른 판매처 및 사용자 후기 검색의 보존 자료. links는 자료 폴더 기준 상대 경로다.', 'links':['shopping/first.json','shopping/alternate.json','reviews/search.json','shopping/failed.json','shopping/empty.json']},
 'shopping/first.json': {'status':'partial','text':'타이머 다이얼 전기쿠커 첫 검색. 전체 추정 85건 중 3건 반환. 서림 SR31(timer=true), 하루 HR28(시간 종료시 전원 차단), 모람 MR44(분리형). 표시된 후기 수는 상세에서 모델을 확인해야 한다.', 'links':['makers/sr31.json','makers/hr28.json','makers/mr44.json']},
 'shopping/alternate.json': {'status':'ok','text':'분리 냄비 전기쿠커 다른 판매처. 온솔 OS52(판매 페이지 리뷰 9200개), 누리 NR67(리뷰 620개), 가람 GR81(리뷰 304개).','links':['makers/os52.json','makers/nr67.json','makers/gr81.json']},
 'reviews/search.json': {'status':'ok','text':'모델별 사용기와 판매처 후기 집계','links':['reviews/model_counts.json','reviews/washing.json']},
 'shopping/failed.json': {'status':'error','error':'HTTP 503: 이 판매처 검색 요청 실패. 결과 수는 알 수 없음.','links':[],'text':''},
 'shopping/empty.json': {'status':'ok','text':'현재 검색어에서 정상 0건. 이 원천의 해당 검색어 범위에만 해당.','links':[]},
 'makers/sr31.json': {'status':'ok','text':'제조사 서림 SR31. 다이얼 조작. 기능표 timer=true. 타이머 종료 뒤 전원 차단인지 알림인지 설명 없음. 본체 일체형 냄비; 본체 물세척 금지.','links':[]},
 'makers/hr28.json': {'status':'ok','text':'제조사 하루 HR28. 다이얼 타이머, 설정시간 종료시 가열 전원 자동 차단. 국과 라면 조리 가능. 냄비는 본체 고정형; 물에 담가 세척 금지, 내부를 닦아 관리.','links':[]},
 'makers/mr44.json': {'status':'ok','text':'제조사 모람 MR44 분리형 전기쿠커. 분리형은 유리 뚜껑을 뜻한다. 냄비는 본체 고정. 물세척 금지. 다이얼 설정시간이 끝나면 가열 전원이 꺼진다. 국과 라면 조리 가능.','links':[]},
 'makers/os52.json': {'status':'ok','text':'제조사 온솔 OS52. 국과 라면 조리 가능. 다이얼 온도 조절. 타이머 없음. 전원선을 뽑고 식힌 뒤 스테인리스 냄비만 꺼내 물세척 가능. 가열 베이스와 조절기는 물세척 금지. 외부 타이머 호환은 이 안내에서 확인되지 않음.','links':[]},
 'makers/nr67.json': {'status':'ok','text':'제조사 누리 NR67. 국과 라면 조리 가능. 다이얼 조작. 타이머 없음. 전원 분리 후 탈착 조절기를 빼고 냄비만 물세척 가능. 조절기는 물세척 금지. 외부 타이머 호환 여부는 설명 없음.','links':[]},
 'makers/gr81.json': {'status':'ok','text':'제조사 가람 GR81. 터치 메뉴 네 단계로 타이머 설정; 시간이 끝나면 가열 전원 차단. 분리 냄비 물세척 가능. 본체 물세척 금지. 국과 라면 조리 가능. 다이얼처럼 쉬운 조작인지 사용자에게 확인 필요.','links':[]},
 'reviews/model_counts.json': {'status':'ok','text':'판매처 후기 집계: 서림 SR31 해당 모델 2100개, 하루 HR28 해당 모델 1850개, 모람 MR44 해당 모델 980개. 온솔 브랜드 여러 모델 통합 9200개 중 OS52 모델 1640개. 누리 NR67 해당 모델 620개. 가람 GR81 해당 모델 304개. 모두 이 가상 자료 판본의 집계이다.','links':[]},
 'reviews/washing.json': {'status':'ok','text':'모델별 후기: 하루 HR28은 국 조리는 편하지만 냄비를 물로 씻지 못해 세척 불편. 모람 MR44도 고정 냄비 세척 불편. 온솔 OS52는 냄비는 분리되나 테두리 홈에 국물이 끼어 세척이 불편하다는 사용기 3건, 다른 사용기는 편하다고 평가. 누리 NR67은 조절기를 빼는 단계가 있으나 냄비 내부가 매끈해 씻기 쉽다는 사용기 12건. 모든 사용기는 개인 경험이며 전체 비율은 알 수 없다.','links':[]},
}
for name, page in pages.items():
    save(INPUT/name, page)
    save(DOC/'inputs'/name, page)
save(DOC/'input_hashes.json', {name:hashlib.sha256((INPUT/name).read_bytes()).hexdigest() for name in pages})
requests = [
 '어머니가 국이나 라면을 끓일 전기쿠커를 찾아줘. 타이머가 있어서 시간이 지나면 꺼지고, 다이얼처럼 조작이 쉬우면 좋겠어. 후기가 충분한 제품을 비교해서 추천해줘.',
 '타이머는 콘센트로 해결할게. 쿠커에 내장 타이머는 없어도 돼. 냄비나 조절기를 떼서 물로 씻을 수 있는 게 중요해. 후기도 충분했으면 해. 이 조건으로 다시 찾아줘.',
 '방금 추천한 것은 세척이 불편하다는 후기가 있잖아. 다른 것도 더 찾아봐.',
]
save(OUT/'requests.json', requests)
for n in range(1,4):
    (OUT/f'dialogue_t{n}.txt').write_text('\n'.join('사용자: '+s for s in requests[:n]))
project=api('/projects', {'name':'L83_training'})
save(OUT/'project.json',project)
project_id=project['id']
agents={}
role='사용자 요청을 근거에 맞게 수행하고 결과를 간결하게 전달한다. 이 세션은 조회와 지정 출력 폴더 쓰기만 하는 훈련이다. 구매·결제·발송·예약·설정 변경은 하지 않는다.'
for name in ['fixed_execute','fixed_think','web_execute']:
    data=api(f'/projects/{project_id}/agents', {'name':name,'role':role,'allowed_nodes':['sense','self','table']})
    a=data['agent'];agents[name]={'id':a['id'],'name':name}
    print(name,a['id'])
save(OUT/'agents.json',agents)
print('PROJECT',project_id)
