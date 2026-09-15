"""문서 편집·범위 계산·대중교통 수동 용례의 멱등 등록. 실행·발송은 하지 않는다."""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

# 파일명과 문구는 합성 예제. 편집은 inspect/range로 확인한 해시를 전달한다.
SEEDS = [
    ('워드 제안서에서 편집할 문단을 확인해줘', '[self:document]{op:"inspect",path:"제안서.docx"}', '파일·문서'),
    ('DOCX 표 안의 문구와 문단 주소를 읽어줘', '[self:document]{op:"inspect",path:"계약서.docx"}', '파일·문서'),
    ('머리말과 꼬리말까지 기존 Word 문서 구조를 살펴봐', '[self:document]{op:"inspect",path:"보고서.docx"}', '파일·문서'),
    ('긴 워드 문서의 다음 100개 문단을 보여줘', '[self:document]{op:"inspect",path:"설명서.docx",offset:100,limit:100}', '파일·문서'),
    ('Inspect editable paragraphs in this Word document', '[self:document]{op:"inspect",path:"proposal.docx",limit:50}', '파일·문서'),
    ('제안서와 계약서의 수정 가능한 문단을 함께 확인해', '[self:document]{path:"제안서.docx"} & [self:document]{path:"계약서.docx"}', '파일·문서'),
    ('첫 문단 납기를 9월 30일에서 10월 15일로 변경 추적해줘', '$d=[self:document]{path:"제안서.docx"}\n[self:document]{op:"edit",path:"제안서.docx",expected_sha256:"$d.sha256",edits:[{block_id:"word/document.xml#p0",old_string:"9월 30일",new_string:"10월 15일"}]}', '파일·문서'),
    ('첫 문단 납기 변경에 검토 주석을 붙여줘', '$d=[self:document]{path:"제안서.docx"}\n[self:document]{op:"edit",path:"제안서.docx",expected_sha256:"$d.sha256",author:"검토자",edits:[{block_id:"word/document.xml#p0",old_string:"9월 30일",new_string:"10월 15일",comment:"요청한 납기 반영"}]}', '파일·문서'),
    ('첫 문단 제목의 오타를 추적 없이 수정본에 반영해', '$d=[self:document]{path:"안내.docx"}\n[self:document]{op:"edit",path:"안내.docx",expected_sha256:"$d.sha256",track_changes:false,output:"안내_수정.docx",edits:[{block_id:"word/document.xml#p0",old_string:"안네",new_string:"안내"}]}', '파일·문서'),
    ('Find editable paragraphs before redlining a contract', '[self:document]{path:"contract.docx"} >> [table:filter]{where:{editable:true}}', '파일·문서'),
    ('엑셀 A2부터 C10까지 값과 수식을 보여줘', '[self:sheet]{op:"range",path:"장부.xlsx",range:"A2:C10"}', '표 다루기'),
    ('매출 시트의 합계 셀 수식을 확인해줘', '[self:sheet]{op:"range",path:"장부.xlsx",sheet:"매출",range:"C20"}', '표 다루기'),
    ('Read formulas and cached values from an Excel range', '[self:sheet]{op:"range",path:"budget.xlsx",range:"B2:D8"}', '표 다루기'),
    ('두 장부의 첫 데이터 행을 함께 비교해', '[self:sheet]{op:"range",path:"지난달.xlsx",range:"A2:C2"} & [self:sheet]{op:"range",path:"이번달.xlsx",range:"A2:C2"}', '표 다루기'),
    ('엑셀 수식을 실제 계산해 새 파일로 저장해줘', '[self:sheet]{op:"calculate",path:"장부.xlsx",output:"장부_계산.xlsx"}', '표 다루기'),
    ('Recalculate this spreadsheet and report formula errors', '[self:sheet]{op:"calculate",path:"budget.xlsx",timeout:90}', '표 다루기'),
    ('계산을 마친 엑셀 합계 값을 읽어줘', '$c=[self:sheet]{op:"calculate",path:"정산.xlsx"}\n[self:sheet]{op:"range",path:"$c.path",range:"C2:C20"}', '표 다루기'),
    ('A2와 B2 값을 110과 5로 바꾸고 원본은 보존해', '$s=[self:sheet]{op:"range",path:"장부.xlsx",range:"A2:B2"}\n[self:sheet]{op:"range_write",path:"장부.xlsx",expected_sha256:"$s.sha256",range:"A2:B2",values:[[110,5]]}', '표 다루기'),
    ('금액 범위에 천 단위 구분과 굵은 글씨를 적용해', '$s=[self:sheet]{op:"range",path:"장부.xlsx",range:"C2:C10"}\n[self:sheet]{op:"range_write",path:"장부.xlsx",expected_sha256:"$s.sha256",range:"C2:C10",format:{number_format:"#,##0",bold:true}}', '표 다루기'),
    ('D2에 부가세 수식을 넣어줘', '$s=[self:sheet]{op:"range",path:"장부.xlsx",range:"D2"}\n[self:sheet]{op:"range_write",path:"장부.xlsx",expected_sha256:"$s.sha256",range:"D2",values:[["=C2*0.1"]]}', '표 다루기'),
    ('서울역에서 강남역까지 대중교통으로 가는 길', '[sense:navigate_route]{mode:"transit",origin:"서울역",destination:"강남역"}', '여행·숙소·맛집'),
    ('시청에서 잠실역까지 버스나 지하철 경로 찾아줘', '[sense:navigate_route]{mode:"transit",origin:"서울시청",destination:"잠실역"}', '여행·숙소·맛집'),
    ('홍대입구에서 여의도까지 환승 횟수를 비교해', '[sense:navigate_route]{mode:"transit",origin:"홍대입구역",destination:"여의도역"} >> [table:sort]{by:"transfer_count"}', '여행·숙소·맛집'),
    ('서울역에서 강남까지 대중교통 요금을 비교해', '[sense:navigate_route]{mode:"transit",origin:"서울역",destination:"강남역"} >> [table:sort]{by:"fare_krw"}', '여행·숙소·맛집'),
    ('걷는 거리가 짧은 버스 지하철 경로부터 보여줘', '[sense:navigate_route]{mode:"transit",origin:"신촌역",destination:"광화문역"} >> [table:sort]{by:"walking_distance_m"}', '여행·숙소·맛집'),
    ('Public transit directions from Seoul Station to Gangnam', '[sense:navigate_route]{mode:"transit",origin:"126.9726,37.5547",destination:"127.0276,37.4979"}', '여행·숙소·맛집'),
    ('대중교통 예상 소요 시간이 짧은 순으로 정리해', '[sense:navigate_route]{mode:"transit",origin:"왕십리역",destination:"합정역"} >> [table:sort]{by:"duration_min"}', '여행·숙소·맛집'),
    ('부산 서면에서 해운대까지 지하철과 버스로 갈 수 있나', '[sense:navigate_route]{mode:"transit",origin:"부산 서면역",destination:"해운대역"}', '여행·숙소·맛집'),
    ('서울역에서 수원역까지 대중교통 연결을 확인해', '[sense:navigate_route]{mode:"transit",origin:"서울역",destination:"수원역"}', '여행·숙소·맛집'),
    ('인천터미널에서 부평역까지 도보와 환승 구간을 알려줘', '[sense:navigate_route]{mode:"transit",origin:"인천터미널역",destination:"부평역"}', '여행·숙소·맛집'),
]


def main():
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    assert db._load_model_sync(), '임베딩 모델 로드 실패'
    with sqlite3.connect(ROOT/'data/ibl_usage.db') as conn:
        have = {r[0] for r in conn.execute('SELECT intent FROM ibl_examples')}
    rows = [{'intent': intent, 'ibl_code': code, 'nodes': 'sense,table' if '[sense:' in code else 'self,table',
             'source': 'manual_seed', 'category': 'pipeline' if '\n' in code or ' >> ' in code or ' & ' in code else 'single',
             'tags': 'document-sheet-transit', 'topic': topic} for intent, code, topic in SEEDS if intent not in have]
    added = db.add_examples_batch(rows)
    assert added == len(rows), f'용례 등록 실패: {added}/{len(rows)}'
    target = ROOT/'data/training/ibl_distilled.json'
    corpus = json.loads(target.read_text())
    have = {(r.get('intent'), r.get('ibl_code')) for r in corpus}
    for intent, code, _ in SEEDS:
        if (intent, code) not in have:
            corpus.append({'intent': intent, 'ibl_code': code, 'source': 'manual_seed'})
    target.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{added} manual examples added, indexed and copied to training corpus')
    for query in ('워드 문서 변경 추적 편집', '엑셀 범위 수식 실제 계산', '버스 지하철 대중교통 경로'):
        hits = db.search_hybrid(query, top_k=3)
        print(query, [(getattr(h, 'ibl_code', '')[:90], round(getattr(h, 'score', 0), 3)) for h in hits])


if __name__ == '__main__':
    main()
