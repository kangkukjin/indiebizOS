"""Synthetic book club fixtures; contains no runtime implementation knowledge."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
DOC = ROOT/'docs/experiments/long_sentence_imagination/round_69'
OUT = ROOT/'outputs/long_sentence_imagination/2026-10-14_69회차'
def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
slots=[{'id':f'S{i+1}','date':f'2026-11-{7+i:02d}','start':'14:00','end':'16:00'} for i in range(6)]
tags=['사회','과학','문학','역사']
members=[{'id':f'P{i+1:02d}','name':f'참가자{i+1:02d}','interests':[tags[i%4],tags[(i+1)%4]],'slots':[s['id'] for j,s in enumerate(slots) if (i+j)%4!=0], 'wheelchair':i==2} for i in range(12)]
members[-1]['slots']=None
books=[{'id':f'B{i+1:02d}','title':f'시험도서{i+1:02d}','tags':[tags[i%4],tags[(i+2)%4]],'pages':180+i*30} for i in range(6)]
venues=[{'id':'V01','name':'동네책방','slots':['S1','S2','S3','S4','S5','S6'],'capacity':12,'fee':45000,'accessible':False}, {'id':'V02','name':'마을도서관','slots':['S1','S3','S5'],'capacity':10,'fee':50000,'accessible':True}, {'id':'V03','name':'커뮤니티실','slots':['S2','S4','S6'],'capacity':12,'fee':65000,'accessible':True}, {'id':'V04','name':'작은카페','slots':['S1','S2','S3','S4','S5','S6'],'capacity':8,'fee':None,'accessible':True}]
history=[{'member_id':p['id'],'book_id':b['id'],'record_id':f'H{i:02d}-{j:02d}'} for i,p in enumerate(members) for j,b in enumerate(books) if (i+j)%3==0]
# Repeated reading events must not increase the count of readers.
history += [{**h,'record_id':h['record_id']+'R'} for h in history[:8]]
notes=[{'id':'N01','topic':'접근성','speaker':'P03','text':'누구나 참여할 수 있다는 원칙과 실제로 문턱이 낮다는 것은 다른 것 같아요. 공간 접근성은 어떻게 확인하죠?'}, {'id':'N02','topic':'접근성','speaker':'P04','text':'휠체어 진입 정보만으로 충분한지, 화장실과 대중교통 접근도 확인할지 다음 모임에서 조사해 보죠. 아직 결정하지 않았습니다.'}, {'id':'N03','topic':'독서속도','speaker':'P01','text':'책을 다 읽지 못해도 토론에 참여할 수 있도록 어떤 진행 방식이 좋을까요?'}, {'id':'N04','topic':'독서속도','speaker':'P02','text':'요약 발제를 해보자는 제안은 있지만 동의가 모이지 않았어요. 다른 방식과 비교해 보고 싶습니다.'}, {'id':'N05','topic':'진행시간','speaker':'P05','text':'발언 시간을 제한할까요?'}, {'id':'N06','topic':'진행시간','speaker':'P06','text':'전원 동의로 이번에는 한 차례 발언을 3분으로 제한하기로 확정했습니다.'}, {'id':'N07','topic':'경험과근거','speaker':'P07','text':'개인의 경험과 통계가 충돌할 때 어떤 근거를 더 믿어야 할까요?'}, {'id':'N08','topic':'경험과근거','speaker':'P08','text':'단순히 통계를 우선하자는 데에는 반대가 있었습니다. 서로 다른 근거를 함께 검토할 방법을 다음에 찾아봅시다.'}]
data={'members':members,'books':books,'slots':slots,'venues':venues,'history':history,'notes':notes,'policy':{'budget':90000,'snack_per_person':1500,'minimum':5,'max_pages':300},'cancelled':[],'revision':'base'}
variant={**data,'cancelled':['P02','P03','P06','P10'],'revision':'cancelled'}
for name,d in [('base',data),('variant',variant)]:
    save(DOC/'fixtures'/f'{name}.json',d)
    save(OUT/'input'/f'{name}.json',d)
    save(OUT/'ai-input'/f'{name}.json',d)
request='''소규모 독서 모임을 기획하고, 취소가 생겼을 때 갱신할 수 있는 계획과 모임 뒤 후속 질문을 정리해 줘. 제공된 JSON의 참가자 관심사·가능 시간·독서 이력, 책·공간 후보만 이용해 모든 날짜×책×공간 조합을 비교해 줘. 취소된 참가자는 빼고 그 시간에 가능한 참가자는 모두 참석한다고 가정해. slots가 null인 사람은 가능 여부 미확인으로 따로 보고하고 참석으로 추정하지 마. 최소 인원, 책 분량 상한, 장소 수용 인원, 이용 가능 시간, 총예산을 모두 지켜. 휠체어 이용자가 참석하면 접근 가능한 장소만 가능해. 장소 비용 미확인은 0원으로 간주하지 마. 총비용은 장소비+참석자 수×간식비이며 책은 각자 준비해. 후보 우선순위는 참석 인원이 많은 순, 참석자들의 관심 태그와 책 태그의 공통 개수 총합이 큰 순, 해당 책을 안 읽은 참석자가 많은 순, 총비용이 작은 순, 날짜가 이른 순, 책 ID와 장소 ID 오름차순이야. 독서 이력이 여러 건이어도 읽은 사람은 한 번만 세어 줘. 모든 조합의 인원·관심점수·미독자수·총비용·탈락 사유를 보존하고, 가능한 최상위 안을 선택해. 가능한 안이 없으면 무리하게 정하지 말고 보류해. 예약 요청과 참가자 안내는 JSON 파일에 초안으로만 남겨 줘. 실제 예약·발송·캘린더 등록은 이 과제에 포함하지 않아. 선택한 안의 날짜·책·장소·참석자·비용을 기록해. 첨부된 가상 토론 기록은 별도의 완료된 모임 기록이야. 주제별로 논의를 종합해 이미 확정된 진행 규칙과 아직 해결되지 않은 질문을 구분하고, 열린 질문마다 원문 기록 ID와 다음에 확인할 방법을 제안해. 결과는 plan.json(모든 조합 candidates, 선택 selected, 미확인 unknown_members, 열린 질문 questions, 초안 drafts)과 사람이 읽을 report.md로 저장해. 질문 내용은 말뜻을 종합하되 원문에 없는 합의나 결론을 만들지 마. 두 파일 저장 후 재독 확인해. input 외 다른 실행자의 trainer/harness/drafts·정답·보고서는 참고하지 마. 너 자신의 앞선 결과·중간 참조는 재사용해도 돼.'''
(DOC/'request.txt').write_text(request+'\n')
(DOC/'task.md').write_text('''# 69회차 — 독서 모임 기획·취소·후속 질문\n\n시작 2026-10-14 23:24 KST, 훈련 상한 60분(00:24까지), 수리·회귀 별도. 시작 HEAD f7887261ebd7907cb84425482c6eb40416ede169. 주제는 사용자 지정, 새 도구 이음새 없음. 목적: 다중 조건 후보 결합·변경 갱신·의미 판단 결과 재사용.\n\n자연어 원문: request.txt. 전부 합성 자료인 이유: 실제 회원 개인정보와 예약·발송 없이 선택·취소·토론 근거 계약을 검증하기 위해. 실제 IBL 엔진·파일 IO·AI 호출 사용. 외부 행동은 초안 작성까지만이며 실제 예약/전송 미검증.\n\n입력 fixtures/base.json, variant.json. 기본 12명·6일·6책·4공간·32독서기록·8발언, 취소 변형 4명 제외. 산출물은 outputs/long_sentence_imagination/2026-10-14_69회차/{trainer-base,trainer-variant,ai-base,ai-variant}.\n\n완료: 144개 후보를 독립 Python 계산과 전건 비교(인원/관심/미독/비용/탈락), 순위 최상위 일치, 미확인 P12 보존, 예약·안내는 초안만. 열린 질문 3주제(접근성 N01/N02, 독서속도 N03/N04, 경험과근거 N07/N08), 진행시간 확정은 열린 질문 제외. 질문 제안의 의미·근거 검수. 최종 두 파일 재독. 후보 없음 변형은 보류, 초안 0. 원본 불변.\n\n분해: 자료읽기→후보별 참석·독서·예산 판정→명시 순위→토론 주제별 판단→초안·보고서 저장/재독. 후보 함수는 순수, 토론 함수는 모델, 저장 함수는 로컬 쓰기. 참고는 조합 교재·문법·describe만. 기존 회차의 HTTP transport만 참조, 내부 구현은 작성에 사용하지 않음.\n''')
save(OUT/'ai-base-request.json', {'message':request+'\n입력: '+str(OUT/'ai-input/base.json')+'\n출력: '+str(OUT/'ai-base'), 'origin':'training','background':True})
print(OUT)
