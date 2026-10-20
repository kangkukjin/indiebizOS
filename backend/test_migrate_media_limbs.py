"""저장 프로그램의 기본 op·인자·노드 이관 회귀."""
import boot_paths  # noqa: F401
import sys
from pathlib import Path
import sqlite3
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from migrate_media_limbs import transform, migrate


@pytest.mark.parametrize('old,new',[
    ('[sense:radio]{query:"jazz"}', '[limbs:radio]{op: "search", query:"jazz"}'),
    ('[sense:radio]{op:"korean"}', '[limbs:radio]{op: "stations"}'),
    ('[limbs:radio_favorite]{op:"add", name:"a,b}", stream_url:"https://x"}', '[limbs:radio]{op: "favorite_add", name:"a,b}", stream_url:"https://x"}'),
    ('[sense:cctv]{op:"webcam", lat:0, lng:0}', '[limbs:cctv]{op: "nearby", lat:0, lng:0, source: "windy"}'),
    ('[self:cctv]', '[limbs:cctv]{op: "stats"}'),
    ('[limbs:radio]{op:"play"}', '[limbs:radio]{op:"play"}'),
    ('[sense:classic]{op:"korean"}', '[sense:classic]{op:"korean"}'),
    ('[self:write]{content:"[sense:radio]{op:korean}"}', '[self:write]{content:"[sense:radio]{op:korean}"}'),
])
def test_transform_preserves_meaning_and_is_idempotent(old,new):
    assert transform(old)==new
    assert transform(new)==new


def test_migration_is_backed_up_and_only_updates_execution_examples(tmp_path):
    data=tmp_path/'data'; data.mkdir()
    path=data/'ibl_usage.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE ibl_examples (id INTEGER, ibl_code TEXT, nodes TEXT)')
        db.execute('INSERT INTO ibl_examples VALUES (1,?,?)',('[sense:cctv]{query:"a"}','sense'))
    assert migrate(tmp_path)['examples']==1
    assert not (data/'_backups').exists()
    assert migrate(tmp_path,apply=True)['examples']==1
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT nodes FROM ibl_examples').fetchone()[0]=='limbs'
    assert (data/'_backups/2026-10-20_media_limbs/ibl_usage.db').exists()
    assert migrate(tmp_path,apply=True)['examples']==0


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
