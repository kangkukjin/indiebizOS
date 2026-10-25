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


OLD = '#!ibl edition=2\n[def:시험추리기]($목록,$개수){return $목록 >> [table:take]{n:$개수}}'
NEW = '#!ibl edition=2\n[def:시험추리기]($목록,$개수){$고유=$목록 >> [table:dedup]{by:"id"}\nreturn $고유.items >> [table:take]{n:$개수}}'


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




def test_registration_does_not_ignore_severity(registry):
    reg, _db = registry
    info, why = reg._gates('시험추리기', '입력 목록을 받아 출처를 생성할 때',
                          '#!ibl edition=2\n[def:시험추리기](){return $없는값}')
    assert info is None and '검사 실패' in why


def test_invalid_final_expression_runs_no_earlier_tool(monkeypatch, tmp_path):
    import ibl_engine
    import workflow_engine
    from system_tools_ibl import _execute_ibl_unified_impl
    def forbidden(*a, **kw):
        pytest.fail('실행 전 거절할 식 때문에 수집이나 쓰기가 실행됨')
    monkeypatch.setattr(ibl_engine, 'execute_ibl', forbidden)
    result = json.loads(_execute_ibl_unified_impl({'edition':2,'code':
        '$자료 = [sense:search]{query: "회귀 fixture"}\n'
        '$자료 >> [table:compute]{set: {source: "[title for title in rows]"}}'}, str(tmp_path)))
    assert not result['success'] and (result.get('issues') or result.get('diagnostic')),result


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
