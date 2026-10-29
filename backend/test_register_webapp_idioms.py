"""재등록은 수동 소개 선택을 보존하고 명시한 선정만 적용한다."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('selection,expected', [(None, 1), (True, 1), (False, 0)])
def test_seed_registration_preserves_or_explicitly_changes_selection(tmp_path, monkeypatch, selection, expected):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    import register_webapp_idioms as registration
    import ibl_usage_db

    folder = tmp_path / 'data/idioms'
    folder.mkdir(parents=True)
    monkeypatch.setattr(registration, 'ROOT', tmp_path)
    monkeypatch.setattr(ibl_usage_db, 'DB_PATH', str(tmp_path / 'data/ibl_usage.db'))
    monkeypatch.setattr(ibl_usage_db.IBLUsageDB, '_instance', None)
    monkeypatch.setattr(ibl_usage_db.IBLUsageDB, '_index_batch', lambda *a, **k: None)
    monkeypatch.setattr(ibl_usage_db.IBLUsageDB, '_index_single', lambda *a, **k: None)
    monkeypatch.setattr(ibl_usage_db, '_tree_refresh', lambda *a, **k: None)
    db = ibl_usage_db.IBLUsageDB()
    seed = {'alias': '재등록선정', 'intent': '명시적으로 선택한 관용구 소개를 재등록할 때',
            'ibl_code': '#!ibl edition=2\n[def:재등록선정](){return 1}', 'category': 'phrase'}
    assert db.add_examples_batch([seed]) == 1
    with db._get_connection() as conn:
        conn.execute('ALTER TABLE ibl_examples ADD COLUMN always_on INTEGER DEFAULT 0')
        conn.execute('UPDATE ibl_examples SET always_on=1 WHERE alias=?', (seed['alias'],))
        conn.commit()
    if selection is not None:
        seed['always_on'] = selection
    (folder / 'fixture_seeds.json').write_text(json.dumps([seed], ensure_ascii=False))
    monkeypatch.setattr(db, '_load_model_sync', lambda: True)
    monkeypatch.setattr(db, '_check_sqlite_vec', lambda: True)
    # 색인은 이 시험의 대상이 아니다. 등록/정적 검사/DB 갱신은 실제 경로를 쓴다.
    monkeypatch.setattr(db, '_get_vec_connection', lambda: SimpleNamespace(
        execute=lambda *a: SimpleNamespace(fetchone=lambda: (1,)), close=lambda: None))
    out = registration.register(apply=True, seed_file='fixture_seeds.json')
    assert out['inserted'] == 0 and out['always_on'] == bool(expected)
    with db._get_connection() as conn:
        assert conn.execute('SELECT always_on FROM ibl_examples WHERE alias=?',
                            (seed['alias'],)).fetchone()[0] == expected


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
