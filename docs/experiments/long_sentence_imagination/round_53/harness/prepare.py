"""53회차 자료 — 마을 법률상담 접수지(전부 합성 인물·사건)와 정답. 사용: prepare.py
만드는 것: outputs/.../{trainer,agent}/{base,a,b}/input/(job.json, intake/*.md) + _oracle/expected_<mode>.json(실행자에게 안 보이는 자리)."""
import json, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-11_53회차'

# 접수번호, 가명, 접수일, 본문, 정답(law·articles(하나라도)·base·n·unit·dir·deadline·kind)
BASE = [
 ('C01', '한○수', '2026-10-05', """작년 말에 그만둔 인쇄소에서 마지막 석 달 치 월급을 아직 못 받았습니다. 2019년 3월 4일에 입사해서 2023년 11월 30일에 퇴사했고, 밀린 돈은 620만 원쯤입니다.
사장님이 2023년 12월 14일까지는 꼭 주겠다고 했는데 그날도 안 들어왔고 그 뒤로 전화를 안 받습니다. 지금이라도 받을 수 있는지, 언제까지 가만히 있으면 안 되는지 알고 싶습니다.""",
  dict(law='근로기준법', articles=['제49조'], base='2023-12-14', n=3, unit='년', dir='after', deadline='2026-12-14', kind='deadline')),
 ('C02', '오○민', '2026-10-06', """물류센터에서 2년 넘게 일했는데 2026년 8월 3일에 팀장이 내일부터 나오지 말라고 했습니다. 서면은 받은 게 없고 문자 한 통뿐입니다.
7월 20일에 휴게시간 문제로 다툰 적이 있습니다. 억울해서 노동위원회에 내 보려는데 늦은 건 아닌지 모르겠습니다.""",
  dict(law='근로기준법', articles=['제28조'], base='2026-08-03', n=3, unit='개월', dir='after', deadline='2026-11-03', kind='deadline')),
 ('C03', '배○정', '2026-10-06', """전세로 살고 있는 빌라 계약이 2027년 1월 31일에 끝납니다. 2025년 2월 1일에 들어왔고 보증금은 1억 8천만 원입니다.
집주인이 아무 말이 없는데, 한 번 더 살겠다고 하려면 언제까지 말해야 하는지요. 지난번에는 연장을 요구한 적이 없습니다.""",
  dict(law='주택임대차보호법', articles=['제6조의3', '제6조'], base='2027-01-31', n=2, unit='개월', dir='before', deadline='2026-11-30', kind='deadline')),
 ('C04', '임○아', '2026-10-13', """인터넷 쇼핑몰에서 10월 8일에 주문한 공기청정기를 2026-10-12에 받았습니다. 34만 9천 원입니다.
상자만 열어 봤고 써 보지는 않았는데 마음이 바뀌어 돌려보내고 싶습니다. 쇼핑몰은 '전자제품은 개봉하면 반품 불가'라고 적어 놨습니다.""",
  dict(law='전자상거래 등에서의 소비자보호에 관한 법률', articles=['제17조'], base='2026-10-12', n=7, unit='일', dir='after', deadline='2026-10-19', kind='deadline')),
 ('C05', '서○호', '2026-10-07', """아버지가 2026년 8월 16일에 돌아가셨습니다. 저는 지방에 있어서 8월 20일에야 연락을 받고 알았습니다.
정리하다 보니 은행 빚과 카드 빚이 재산보다 훨씬 많습니다. 빚을 물려받지 않으려면 뭘 언제까지 해야 합니까.""",
  dict(law='민법', articles=['제1019조'], base='2026-08-20', n=3, unit='개월', dir='after', deadline='2026-11-20', kind='deadline')),
 ('C06', '문○경', '2026-10-08', """2023년 10월 25일 저녁에 횡단보도에서 배달 오토바이에 치여 손목이 부러졌습니다. 상대방이 누구인지는 그 자리에서 경찰이 확인해 줬습니다.
치료비 일부만 받고 흐지부지됐는데, 2024년 3월까지 통원 치료를 했습니다. 지금 손해배상을 청구할 수 있을까요.""",
  dict(law='민법', articles=['제766조'], base='2023-10-25', n=3, unit='년', dir='after', deadline='2026-10-25', kind='deadline')),
 ('C07', '곽○택', '2026-10-08', """동창에게 2015년 9월 30일에 2천만 원을 빌려줬습니다. 차용증에는 2016년 9월 30일까지 갚는다고 적혀 있습니다. 장사하는 사이도 아니고 그냥 친구끼리 빌려준 돈입니다.
그 뒤로 한 푼도 못 받았고 독촉한 적도 딱히 없습니다. 이제라도 소송을 하면 받을 수 있습니까.""",
  dict(law='민법', articles=['제162조'], base='2016-09-30', n=10, unit='년', dir='after', deadline='2026-09-30', kind='deadline')),
 ('C08', '진○숙', '2026-10-09', """10월 1일에 집으로 찾아온 판매원에게 정수기 겸 안마의자 렌탈 계약을 했습니다. 계약서는 그날(2026-10-01) 바로 받았고 물건도 같은 날 놓고 갔습니다.
자식들이 말려서 취소하려고 하는데 판매원이 위약금을 내라고 합니다.""",
  dict(law='방문판매 등에 관한 법률', articles=['제8조'], base='2026-10-01', n=14, unit='일', dir='after', deadline='2026-10-15', kind='deadline')),
 ('C09', '천○영', '2026-10-08', """어머니가 2025년 6월에 돌아가셨는데, 살아 계실 때 집 한 채를 오빠에게만 넘겨준 사실을 작년 12월 1일에 등기부를 떼어 보고 알았습니다. 다른 재산은 거의 없습니다.
저도 자식인데 한 푼도 못 받는 게 맞는지, 요구하려면 언제까지 해야 하는지 궁금합니다.""",
  dict(law='민법', articles=['제1117조'], base='2025-12-01', n=1, unit='년', dir='after', deadline='2026-12-01', kind='deadline')),
 ('C10', '남○우', '2026-10-09', """원룸 계약이 끝나서 방을 뺐는데 집주인이 보증금 500만 원을 새 세입자가 들어오면 주겠다며 안 줍니다.
이사는 이미 했고 짐도 다 뺐습니다. 주소를 옮겨도 되는지, 돈은 어떻게 받아야 하는지 모르겠습니다.""",
  dict(law='주택임대차보호법', articles=['제3조의3', '제3조', '제4조'], kind='need_date')),
 ('C11', '설○희', '2026-10-10', """집주인이 월세를 50만 원에서 65만 원으로 올리겠다고 합니다. 계약 기간은 아직 1년 남았습니다.
인터넷에서 보니 「임차인보호특별법」 제5조에 따라 월세는 1년에 3% 넘게 못 올린다고 하던데, 그 조문을 들이대면 되는지요.""",
  dict(law='주택임대차보호법', articles=['제7조'], claimed='임차인보호특별법', kind='no_deadline')),
]

VAR_A = [
 ('A01', '방○준', '2026-10-12', """학원에서 강사로 일하다 2026년 9월 14일에 원장에게 구두로 해고 통보를 받았습니다. 이유는 학부모 민원이라고만 합니다.
노동위원회에 구제 신청이라는 걸 할 수 있다고 들었습니다.""",
  dict(law='근로기준법', articles=['제28조'], base='2026-09-14', n=3, unit='개월', dir='after', deadline='2026-12-14', kind='deadline')),
 ('A02', '위○란', '2026-10-12', """「소상공인 임대료 동결법」 제2조에 따라 올해는 가게 월세를 못 올린다고 들었는데 건물주가 올려 달라고 합니다. 그 법 조문을 보여 주고 싶습니다.""",
  dict(law=None, articles=[], claimed='소상공인 임대료 동결법', kind='no_deadline')),
 ('A03', '(빈 접수지)', '', '', dict(kind='empty')),
 ('A04', '표○식', '2026-10-13', """홈쇼핑 방송을 보고 전화로 주문한 운동기구를 2026-10-10에 받았습니다. 조립은 안 했고 반품하고 싶습니다. 19만 8천 원입니다.""",
  dict(law='전자상거래 등에서의 소비자보호에 관한 법률', articles=['제17조'], base='2026-10-10', n=7, unit='일', dir='after', deadline='2026-10-17', kind='deadline')),
 ('A05', '금○화', '2026-10-13', """남편이 2026년 7월 9일에 사망했고 저는 그날 병원에서 임종을 지켰습니다. 사업하다 진 빚이 많아 상속을 받지 않으려고 합니다.""",
  dict(law='민법', articles=['제1019조'], base='2026-07-09', n=3, unit='개월', dir='after', deadline='2026-10-09', kind='deadline')),
]

def build(mode, cases, consult):
    for who in ('trainer', 'agent'):
        d = OUT / who / mode / 'input'; shutil.rmtree(d, ignore_errors=True); (d / 'intake').mkdir(parents=True)
        (d / 'job.json').write_text(json.dumps({'office': '느티나무 마을 법률상담 창구', 'consult_date': consult, 'note': '상담 준비 자료이며 법률 자문이 아님'}, ensure_ascii=False, indent=1))
        for cid, name, recv, body, _ in cases:
            (d / 'intake' / f'{cid}.md').write_text('' if not body else f'# 상담 접수지 {cid}\n\n- 신청인(가명): {name}\n- 접수일: {recv}\n\n## 하고 싶은 말\n{body}\n')
        (OUT / who / mode / 'out').mkdir(parents=True, exist_ok=True)
    exp = {'consult_date': consult, 'cases': {cid: e for cid, _, _, _, e in cases}}
    (OUT / '_oracle').mkdir(exist_ok=True)
    (OUT / '_oracle' / f'expected_{mode}.json').write_text(json.dumps(exp, ensure_ascii=False, indent=1))

build('base', BASE, '2026-10-17')
build('a', VAR_A, '2026-10-17')
build('b', BASE, '2026-10-24')
print('ok', [len(BASE), len(VAR_A)])
