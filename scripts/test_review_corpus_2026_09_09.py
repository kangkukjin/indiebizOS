"""데이터 이관의 행 보존과 실제 IBL 값/반복 의미를 오프라인에서 검사."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_corpus_2026_09_09 as review
from ibl_boundary_probe import probe
import pytest


def replacement(index):
    return review.load_manifest()[0][index]['after']


def run(code, expected):
    result = probe(dict(id='corpus-review', code=code, expected=expected,
                        error=False, contains=None))
    assert result['ok'], (result['actual'], result.get('error_text'))


def test_manifest_has_one_decision_per_existing_row():
    changes, ledger = review.load_manifest()
    assert len(ledger) == 6545
    assert sum(r['decision'] == 'replace' for r in ledger) == 412
    targets = [review.key(t) for c in changes.values() for t in c['targets']]
    assert len(targets) == len(set(targets)) == 412
    # 동일한 코드를 가진 사이트 즐겨찾기 의도만 교체; 라디오 의도는 보존.
    assert ('db', 1759) not in targets


def test_prepare_is_idempotent_and_refuses_concurrent_changes():
    before = '[table:take]{items:[{x:1}],n:1}'
    after = '[table:take]{items:[{x:1},{x:2}],n:2}'
    row = {'intent': '상위 두 개', 'ibl_code': before}
    entry = dict(origin='fixture', row_id=0, decision='replace', replacement=1,
                 before_sha256=review.digest(before), after_sha256=review.digest(after),
                 intent_sha256=review.digest(row['intent']))
    args = ({1: {'after': after}}, [entry], {('fixture', 0): row})
    assert len(review.prepare(*args)[0]) == 1
    row['ibl_code'] = after
    assert review.prepare(*args)[0] == []
    row['ibl_code'] = '[self:time]'
    with pytest.raises(AssertionError, match='코드 변경'):
        review.prepare(*args)
    row['ibl_code'], row['intent'] = before, '동시 수정'
    with pytest.raises(AssertionError, match='의도 변경'):
        review.prepare(*args)


def test_revised_stock_gdp_join_uses_matching_years():
    code = replacement(1711)
    code = code.replace('[sense:stock]{op:"history",symbol:"005930",period:"5y"}',
                        '[table:take]{items:[{date:"2026-01-01",close:100},{date:"2026-01-02",close:200}],n:2}')
    code = code.replace('[sense:world_bank]{country:"KR",indicator:"NY.GDP.MKTP.CD"}',
                        '[table:take]{items:[{연도:2026,GDP:10}],n:1}')
    run(code, [{'연도': 2026, 'avg_close': 150, 'GDP': 10}])


def test_revised_union_preserves_currency_units():
    code = replacement(2271)
    code = code.replace('[sense:crypto]{coin:"bitcoin"}',
                        '[table:take]{items:[{symbol:"BTC",current_price_usd:100,change_24h_percent:2}],n:1}')
    code = code.replace('[sense:stock]{op:"quote",ticker:"^KS11"}',
                        '[table:take]{items:[{symbol:"^KS11",current_price:200,currency:"KRW",change_percent:3}],n:1}')
    run(code, [{'symbol': 'BTC', 'current_price': 100, 'currency': 'USD', 'change_percent': 2},
               {'symbol': '^KS11', 'current_price': 200, 'currency': 'KRW', 'change_percent': 3}])


def test_prose_each_collects_summary_instead_of_original_only():
    code = replacement(2337)
    code = code.replace('[sense:video]{op:"transcript",video_id:"${영상}"} >> [table:chunk]{size:15000}',
                        '[table:take]{items:[{text:"원문 하나"},{text:"원문 둘"}],n:2}')
    code = code.replace('${덩이지시}', '한 문장 요약')
    run(code, [{'text': t, 'message': 'SUMMARY: fixture', 'rows_in': 1}
               for t in ['원문 하나', '원문 둘']])
