"""반복 보고서의 실제 마찰: 공급자 날짜, 실행 전 식 거절, 관용구 개정 이력."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def youtube():
    return load('_report_youtube', 'data/packages/installed/tools/youtube/handler.py')


@pytest.mark.parametrize('raw,iso', [('20260117', '2026-01-17'), ('20260701', '2026-07-01'),
                                   ('20260312', '2026-03-12'), ('2024-02-29', '2024-02-29')])
def test_video_info_dates_reach_real_filter(youtube, raw, iso):
    from types import SimpleNamespace
    dataops = load('_report_dataops', 'data/packages/installed/tools/data-ops/handler.py')
    upstream = {'success': True, 'title': '후보', 'upload_date': raw}
    out = youtube._op_info({'video_id': 'candidate'}, SimpleNamespace(get_youtube_info=lambda **kw: upstream))
    assert upstream['upload_date'] == raw  # 공급자 객체를 변이하지 않는다
    assert out['upload_date'] == iso and out['upload_date_raw'] == raw
    assert out['items'][0]['upload_date'] == iso
    filtered = dataops._op_filter(out, {'where': 'upload_date >= "2026-03-12"'})
    assert filtered.get('success', True), filtered
    assert len(filtered['items']) == int(iso >= '2026-03-12')


@pytest.mark.parametrize('raw', [None, '', '20260230', '20261301', '2026-02-29', '2026/03/12', '2026-W01-1', 20260312])
def test_unknown_date_is_not_fresh(youtube, raw):
    out = youtube._snapshot_row({'success': True, 'title': '후보', 'upload_date': raw})
    assert not out['success'] and out['items'] == []
    assert out['upload_date_raw'] == raw


def test_missing_date_and_provider_failure(youtube):
    assert not youtube._snapshot_row({'success': True, 'title': '후보'})['success']
    failed = {'success': False, 'error': '공급자 장애'}
    assert youtube._snapshot_row(failed) is failed


@pytest.mark.parametrize('slot', ['set', 'columns', 'expr'])
def test_dict_compute_rejected_before_collection(slot):
    from ibl_typecheck import typecheck_code
    code = ('$자료 = [sense:search]{query: "자료"}\n'
            f'$자료 >> [table:compute]{{{slot}: {{source: "{{\'title\': title}}"}}}}')
    tc = typecheck_code(code)
    assert not tc['ok'], tc
    assert any('Dict' in i['message'] for i in tc['issues']), tc


def test_preflight_matches_runtime_and_defers_dynamic():
    from ibl_typecheck import typecheck_code
    prefix = '[table:compute]{items: [{x: 4}], '
    for spec in ['set: {y: "x * 2"}', 'expr: "x * 2", as: "y"',
                 'set: {y: "x * 2"}, columns: {ignored: "{bad}"}']:
        tc = typecheck_code(prefix + spec + '}')
        assert tc['ok'], tc
    # 동적 함수 인자 속의 식은 호출 때 검수한다. 임의 추측으로 거절하지 않는다.
    assert typecheck_code('[def: 계산]{$return = [table:compute]{set: "${계산식}"}}')['ok']
    bad = typecheck_code(prefix + 'expr: "x +", as: "y"}')
    assert not bad['ok'], bad


def test_expression_contract_is_data_not_action_name(monkeypatch):
    import ibl_typecheck as tc
    real = tc._action_def
    monkeypatch.setattr(tc, '_action_def', lambda n, a: {
        'returns': 'transform', 'flow': {'accepts': 'items', 'emits': 'items',
                                       'scalar_expr_params': ['formula']}
    } if a == 'custom_formula' else real(n, a))
    checker = tc._Checker()
    checker._type_action({'params': {'formula': '{"x": 1}', 'items': [{'x': 1}]}},
                         'custom', 'custom_formula', None, 0)
    assert any('Dict' in i['message'] for i in checker.issues)


@pytest.fixture
def registry(tmp_path, monkeypatch):
    from test_stale_idiom_overwrite_2026_09_07 import _FakeDB
    import ibl_usage_db
    monkeypatch.setattr(ibl_usage_db, '_tree_refresh', lambda *a: None)
    sys.path.insert(0, str(ROOT / 'scripts'))
    import register_idiom
    db = _FakeDB(tmp_path / 'usage.db')
    with db._get_connection() as conn:
        conn.execute('ALTER TABLE ibl_examples ADD COLUMN always_on INTEGER DEFAULT 1')
    return register_idiom, db


OLD = '$return = [table:take]{n: "${개수}"}'
NEW = '$고유 = [table:dedup]{by: "id"}\n$return = $고유 >> [table:take]{n: "${개수}"}'


def test_used_idiom_revised_with_history_and_same_identity(registry):
    reg, db = registry
    rid = db.add('시험추리기', OLD, ok=3, fail=2, bypass=4, intent='목록을 앞에서 정한 개수만큼 추릴 때')
    assert reg.update_idiom(db, '시험추리기', NEW, '중복 제거 후 경계 입력 검증')
    row = db.row(rid)
    assert row['ibl_code'] == NEW and row['always_on'] == 1
    assert (row['success_count'], row['fail_count'], row['bypass_count']) == (0, 0, 0)
    assert row['avg_ms'] == row['avg_tokens'] == -1
    with db._get_connection() as conn:
        history = dict(conn.execute('SELECT * FROM ibl_idiom_revisions').fetchone())
    before = json.loads(history['old_row'])
    assert before['ibl_code'] == OLD and before['success_count'] == 3 and before['fail_count'] == 2
    assert history['example_id'] == rid and history['new_code'] == NEW
    assert db.indexed[-1][0] == rid
    assert not reg.update_idiom(db, '시험추리기', NEW, '동일 수리 재실행')


@pytest.mark.parametrize('code,reason', [(NEW, ''), ('아무 산문', '불가'),
                                       (NEW.replace('개수', '다른인자'), '서명 변경')])
def test_invalid_revision_leaves_old_body(registry, code, reason):
    reg, db = registry
    rid = db.add('시험추리기', OLD, ok=3, intent='목록을 앞에서 정한 개수만큼 추릴 때')
    with pytest.raises(ValueError):
        reg.update_idiom(db, '시험추리기', code, reason)
    assert db.row(rid)['ibl_code'] == OLD and db.row(rid)['success_count'] == 3


def test_bad_expression_in_named_body_is_not_hidden_or_cached(monkeypatch):
    import ibl_typecheck as tc
    bad = '$return = [table:compute]{set: {source: "{\'title\': title}"}}'
    assert not tc.typecheck_code('[def: 수리대상]{' + bad + '}')['ok']
    monkeypatch.setattr(tc, '_external_fn_code', lambda name: bad)
    for _ in range(2):
        out = tc.typecheck_code('[fn:수리대상]{}')
        assert not out['ok'], out


def test_registration_does_not_ignore_severity(registry):
    reg, _db = registry
    info, why = reg._gates('시험추리기', '입력 목록을 받아 출처를 생성할 때',
                          '$자료 = [table:take]{n: "${개수}"}\n'
                          '$return = $자료 >> [table:compute]{set: {source: "{\'x\': x}"}}')
    assert info is None and '타입 오류' in why


def test_invalid_final_expression_runs_no_earlier_tool(monkeypatch, tmp_path):
    import ibl_engine
    import workflow_engine
    from system_tools_ibl import _execute_ibl_unified_impl
    def forbidden(*a, **kw):
        pytest.fail('실행 전 거절할 식 때문에 수집이나 쓰기가 실행됨')
    monkeypatch.setattr(ibl_engine, 'execute_ibl', forbidden)
    monkeypatch.setattr(workflow_engine, 'execute_pipeline', forbidden)
    result = json.loads(_execute_ibl_unified_impl({'code':
        '$자료 = [sense:search]{query: "회귀 fixture"}\n'
        '$자료 >> [table:compute]{set: {source: "{\'title\': title}"}}'}, str(tmp_path)))
    assert result['success'] is False and result['error_type'] == 'typecheck', result


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
