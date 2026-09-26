"""판본 1 등록만 관용구 6개의 판본 2 이식(2026-09-26) — 실제 실행기로 값 계약·빈값·경계 검사.

정본은 data/idioms/legacy_port_seeds.json. 판본 2 호출자는 종전 legacy-envelope 다리 대신
이 정의를 우선 해소하므로(ibl_v2_store.definitions) 반환이 봉투가 아니라 값이다.
"""
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
SEEDS = json.loads((ROOT / 'data/idioms/legacy_port_seeds.json').read_text(encoding='utf-8'))
LIB = {r['alias']: r['ibl_code'] for r in SEEDS if r['alias']}


def run(call, inputs=None, adapters=None):
    registry = load_registry(str(ROOT))
    for key, fn in (adapters or {}).items():
        registry[key] = Adapter(registry[key].contract, fn)
    plan = compile_program(call, registry, inputs or {}, LIB)
    assert not plan.issues, plan.report()
    out = Runtime(plan, inputs or {}).run()
    assert out['success'], out
    return out


def test_seeds_close_every_input_and_calls_name_their_function():
    from ibl_v2_learning import check_source
    for row in SEEDS:
        assert check_source(row['ibl_code'], bool(row['alias']), library=LIB) is None, row.get('alias') or row['intent']
    assert set(LIB) == {'미처리만고르기', '중복빼고추리기', '묶어순위내기', '직전보고서찾아읽기', '고치고확인하기', '원장에누적', '고치고시험돌리기'}
    for row in SEEDS:
        if not row['alias']:
            assert any(f'[fn:{n}]' in row['ibl_code'] for n in LIB)


def test_unprocessed_only_keeps_first_row_order_and_empty_processed():
    out = run('[fn:미처리만고르기]{후보:[{url:"a",t:1},{url:"b",t:2},{url:"a",t:3}],키:"url",처리됨:[{url:"b"}]}')
    assert out['value'] == [{'url': 'a', 't': 1}]
    out = run('[fn:미처리만고르기]{후보:[{url:"a",t:1},{url:"a",t:3}],키:"url",처리됨:[]}')
    assert out['value'] == [{'url': 'a', 't': 1}]
    assert run('[fn:미처리만고르기]{후보:[],키:"url",처리됨:[{url:"b"}]}')['value'] == []


def test_dedup_take_and_group_rank_return_plain_lists():
    out = run('[fn:중복빼고추리기]{목록:[{url:"u1",t:1},{url:"u1",t:2},{url:"u2",t:3}],키:"url",개수:1}')
    assert out['value'] == [{'url': 'u1', 't': 1}]
    out = run('[fn:묶어순위내기]{목록:[{지역:"서울",매출:3},{지역:"부산",매출:5},{지역:"서울",매출:4}],묶음:"지역",값열:"매출",개수:1}')
    assert out['value'] == [{'지역': '서울', '합계': 7, '건수': 2}]


def test_previous_report_by_name_order_not_mtime(tmp_path):
    (tmp_path / 'ai_trend_report_2026-09-20.md').write_text('old\n' * 200, encoding='utf-8')
    newest = tmp_path / 'ai_trend_report_2026-09-25.md'
    newest.write_text('\n'.join(f'line{i}' for i in range(300)), encoding='utf-8')
    import os, time
    stale = time.time() - 86400
    os.utime(newest, (stale, stale))            # 이름순 최신이 수정시각으로는 옛것
    (tmp_path / 'ai_trend_report_dir').mkdir()
    out = run('[fn:직전보고서찾아읽기]{폴더:$p,패턴:"ai_trend_report_*"}', {'p': str(tmp_path)})
    v = out['value']
    assert v['found'] and v['path'].endswith('2026-09-25.md') and v['candidates'] == 1
    assert 'line0' in v['text'] and 'line159' in v['text'] and 'line200' not in v['text']
    out = run('[fn:직전보고서찾아읽기]{폴더:$p,패턴:"housing_*.md"}', {'p': str(tmp_path)})
    assert out['value'] == {'found': False, 'path': '', 'text': '', 'candidates': 0}


def test_edit_then_confirm_reports_matches_and_zero_match(tmp_path):
    f = tmp_path / 'config.ini'
    f.write_text('port = 8000\nhost = x\n', encoding='utf-8')
    out = run('[fn:고치고확인하기]{파일:$f,앞:"port = 8000",뒤:"port = 8765",확인:"port = 8765"}', {'f': str(f)})
    v = out['value']
    assert v['confirmed'] and v['total'] >= 1 and f.read_text(encoding='utf-8').startswith('port = 8765')
    out = run('[fn:고치고확인하기]{파일:$f,앞:"host = x",뒤:"host = y",확인:"never-there"}', {'f': str(f)})
    assert out['value']['confirmed'] is False and out['value']['matches'] == []


def test_ledger_accumulate_keeps_old_rows_and_writes_json(tmp_path):
    ledger = tmp_path / 'ledger.json'
    out = run('[fn:원장에누적]{옛것:[{url:"u1",t:"a"}],새것:[{url:"u1",t:"b"},{url:"u2",t:"c"}],키:"url",원장:$p}',
              {'p': str(ledger)})
    assert out['value'] == {'path': str(ledger), 'count': 2, 'added': 1}
    assert json.loads(ledger.read_text(encoding='utf-8')) == [{'url': 'u1', 't': 'a'}, {'url': 'u2', 't': 'c'}]


def test_edit_then_test_reports_per_file_results(tmp_path):
    f = tmp_path / 'mod.py'
    f.write_text('def f():\n    retrun 1\n', encoding='utf-8')
    seen = []

    def script(rt, args):
        seen.append(args)
        return {'ok': False, 'items': [{'file': args['args']['files'][0], 'passed': 2, 'failed': 1,
                                        'errors': 0, 'failures': ['test_x'], 'noise': 'drop me'}]}
    out = run('[fn:고치고시험돌리기]{파일:$f,앞:"retrun",뒤:"return",시험파일:"backend/test_mod.py"}',
              {'f': str(f)}, {'self:script': script})
    assert f.read_text(encoding='utf-8') == 'def f():\n    return 1\n'
    assert seen[0]['id'] == '시험' and seen[0]['args'] == {'files': ['backend/test_mod.py']}
    assert out['value'] == {'ok': False, 'edited': True,
                            'items': [{'file': 'backend/test_mod.py', 'passed': 2, 'failed': 1, 'failures': ['test_x']}]}


def test_register_idiom_gates_understand_edition_2(monkeypatch):
    """register_idiom._gates 는 판본 2 정의를 판본 2 검사기로 본다(종전엔 전부 '파싱 불가')."""
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    import ibl_v2_store
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: dict(LIB))
    from register_idiom import _gates
    for row in SEEDS:
        if row['alias']:
            info, why = _gates(row['alias'], row['intent'], row['ibl_code'])
            assert why is None, (row['alias'], why)
            assert info['edition'] == 2 and info['signature']
    body = LIB['미처리만고르기'].replace('미처리만고르기', '이번사건에만쓰는긴이름함수')
    _, why = _gates('이번사건에만쓰는긴이름함수', '충분히 긴 부를 조건 설명', body)
    assert why and '상한' in why
    _, why = _gates('미처리만고르기', '짧다', LIB['미처리만고르기'])
    assert why and '--when' in why
    _, why = _gates('미처리만고르기', '충분히 긴 부를 조건 설명', '#!ibl edition=2\n[def:미처리만고르기](){ return 1 }')
    assert why and '슬롯 0' in why
    info, why = _gates('좁혀서읽기', '충분히 긴 부를 조건 설명',
                       '$h = [self:grep]{pattern: "${패턴}", path: "${루트}", limit: 6}; $return = $h >> [table:take]{n: 3}')
    assert why is None and info['edition'] == 1


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
