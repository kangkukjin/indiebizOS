"""Round 80 residual contracts: provenance, read purity and honest absence."""
import boot_paths  # noqa: F401
import importlib.util
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'data/packages/installed/tools'


def module(package, name='handler'):
    path = TOOLS / package / (name + '.py')
    spec = importlib.util.spec_from_file_location('r80_' + package.replace('-', '_') + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def blog(tmp_path, monkeypatch):
    mod = module('blog')
    import tool_blog_insight as insight
    import blog_snapshot as snapshot
    monkeypatch.setattr(insight, 'DB_PATH', str(tmp_path / 'blog.db'))
    monkeypatch.setattr(insight, 'DATA_DIR', str(tmp_path))
    with closing(insight.get_db()) as conn:
        conn.execute("INSERT INTO posts(post_id,title,category,pub_date,content) VALUES('1','fixture','Group/Leaf','2026-09-21','body')")
        conn.commit()
    return mod, insight, snapshot


def test_blog_snapshot_never_invents_collection_time(blog):
    _, insight, snapshot = blog
    assert snapshot.snapshot_metadata()['as_of'] is None
    assert snapshot.snapshot_metadata()['stale'] is True
    with closing(insight.get_db()) as conn:
        snapshot.record_collection(conn)
        conn.commit()
    meta = snapshot.snapshot_metadata()
    assert meta['stale'] is False and meta['source'] == 'local_snapshot'
    future = datetime.now(timezone.utc) + timedelta(days=2)
    assert snapshot.snapshot_metadata(now=future)['stale'] is True


def test_blog_rag_reads_do_not_create_database_or_vector_index(tmp_path, monkeypatch):
    rag = module('blog', 'tool_blog_rag')
    db = tmp_path / 'search.db'
    monkeypatch.setattr(rag, 'DB_PATH', str(db))
    engine = rag.BlogHybridSearch()
    assert rag.get_post_content('1')['success'] is False
    assert not db.exists()
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE posts (post_id TEXT, title TEXT, content TEXT, pub_date TEXT, category TEXT)')
        conn.execute("INSERT INTO posts VALUES ('1','fixture','body','2026-09-29','test')")
    before = db.read_bytes()
    assert rag.get_post_content('1')['content'] == 'body'
    with closing(engine._get_plain_connection()) as conn:
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            conn.execute('CREATE TABLE hidden_write (id INTEGER)')
    monkeypatch.setattr(engine, 'generate_embedding', lambda query: b'fixture')
    monkeypatch.setattr(engine, '_ensure_vec_table', lambda conn: pytest.fail('read must not create an index'))
    assert engine.search_semantic('fixture') == []
    assert db.read_bytes() == before


def test_blog_latest_missing_vault_is_read_only(blog, monkeypatch):
    mod, insight, _ = blog
    import tool_blog_vault as vault
    monkeypatch.setattr(vault, 'find_post_md', lambda _: None)
    monkeypatch.setattr(vault, 'write_post_md', lambda _: pytest.fail('read must not write'))
    before = Path(insight.DB_PATH).read_bytes()
    result = json.loads(mod.execute({'op':'latest'}, SimpleNamespace(tool_name='blog_op')))
    assert result['success'] is False and result['path'] is None
    assert result['as_of'] is None and result['stale'] is True
    assert Path(insight.DB_PATH).read_bytes() == before


def test_blog_successful_read_metadata_and_category_validation(blog):
    mod, insight, _ = blog
    result = json.loads(mod.execute({'op':'posts', 'limit':1, 'category':'Group'}, SimpleNamespace(tool_name='blog_op')))
    assert result['source'] == 'local_snapshot' and result['items'][0]['post_id'] == '1'
    assert result['items'][0]['url'].endswith('/1')
    bad = json.loads(mod.execute({'op':'search','query':'x','category':['Leaf','missing']}, SimpleNamespace(tool_name='blog_op')))
    assert bad['success'] is False and 'missing' in bad['error']


def test_blog_empty_collection_updates_time_but_failed_rss_does_not(blog, monkeypatch):
    _, insight, snapshot = blog
    monkeypatch.setattr(insight, 'fetch_rss_feed', lambda: [])
    assert insight.blog_check_new_posts()['success'] is True
    first = snapshot.snapshot_metadata()['as_of']
    def fail():
        raise ValueError('bad RSS')
    monkeypatch.setattr(insight, 'fetch_rss_feed', fail)
    assert insight.blog_check_new_posts()['success'] is False
    assert snapshot.snapshot_metadata()['as_of'] == first


def test_blog_missing_read_does_not_initialize(tmp_path, monkeypatch):
    module('blog')
    import tool_blog_insight as insight
    path = tmp_path / 'absent' / 'blog.db'
    monkeypatch.setattr(insight, 'DB_PATH', str(path))
    with pytest.raises(sqlite3.OperationalError):
        insight.get_db(read_only=True)
    assert not path.parent.exists()


@pytest.mark.parametrize('raw', ['<html>not a feed</html>', '<rss/>'])
def test_blog_invalid_source_is_not_successful_collection(raw, monkeypatch):
    mod = module('blog', 'tool_blog_insight')
    monkeypatch.setattr(mod.requests, 'get', lambda *a, **k: SimpleNamespace(content=raw.encode(), raise_for_status=lambda:None))
    with pytest.raises(ValueError):
        mod.fetch_rss_feed()


def test_bulletin_primary_collection_and_compatibility(monkeypatch):
    mod = module('bulletin')
    core = SimpleNamespace(load_state=lambda:{'settings':{},'boards':[]},
        get_board=lambda *a:{'id':'b'}, board_row=lambda *a:{'id':'b','title':'board'},
        load_posts=lambda _: [{'id':'p','name':'author','body':'a\nb','at':'2026-09-29','image':'x'}])
    monkeypatch.setattr(mod, '_core', lambda:core)
    value = json.loads(mod._detail({'board_id':'b'}))
    assert value['items'] == value['posts']
    assert value['board']['id'] == 'b'
    row = value['items'][0]
    assert row['title'] == row['name'] == 'author'
    assert row['has_image'] and row['body'] == 'a\nb'


@pytest.mark.parametrize('name', ['guestbook.json','uploads/uploads.json'])
@pytest.mark.parametrize('raw', ['{broken', '{}', '[1]'])
def test_family_corruption_is_failure(tmp_path, monkeypatch, name, raw):
    mod = module('family-news')
    monkeypatch.setattr(mod, '_DATA', tmp_path)
    monkeypatch.setattr(mod, '_UPLOADS_META', tmp_path/'uploads/uploads.json')
    p = tmp_path/name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(raw)
    operation = mod._fn_comments if name == 'guestbook.json' else mod._fn_uploads
    with pytest.raises((ValueError, TypeError)):
        operation({})
    p.unlink()
    assert json.loads(operation({}))['items'] == []


def test_webapp_status_unknown_preserved(monkeypatch):
    mod = module('system_essentials', 'webapp_registry')
    monkeypatch.setattr(mod, '_all_entries', lambda:[{'title':'unknown','url':''},{'title':'dead','url':'https://invalid.example'}])
    import requests
    monkeypatch.setattr(requests, 'get', lambda *a, **k:SimpleNamespace(status_code=404,close=lambda:None))
    rows = mod.op_status({})['items']
    assert [(r['alive'],r['state']) for r in rows] == [(None,'unknown'),(False,'dead')]


@pytest.mark.parametrize('predicate', ['$r.alive','not $r.alive'])
def test_nullable_filter_reports_row(predicate):
    from ibl_v2_adapters import load_registry
    from ibl_v2_runtime import Runtime
    from ibl_v2_ir import Fault
    from ibl_v2_compile import compile_program
    source = 'return [{alive:true},{alive:null}] >> [table:filter]{where:($r)=>'+predicate+'}'
    result = Runtime(compile_program(source, load_registry())).run()
    assert not result["success"]
    assert result["diagnostic"]["details"]["row_index"] == 1


@pytest.mark.parametrize('branch', [{}, {'following':True}, {'author':'author'}])
def test_feed_since_and_order(monkeypatch, branch):
    import channel_engine
    seen = []
    def fetch(**kw):
        seen.append(kw)
        return [{'id':'old','created_at':1}, {'id':'new','created_at':3,'tags':[['e','old']]}]
    net = SimpleNamespace(fetch_board_posts=fetch, fetch_following_feed=fetch, fetch_author_posts=fetch,
        fetch_author_profile=lambda _: {}, settings=SimpleNamespace(active_board='fixture'), identity=None)
    monkeypatch.setattr(channel_engine,'_get_indienet',lambda:net)
    monkeypatch.setattr(channel_engine,'_bridge_status',lambda *a:{})
    value = channel_engine._community_feed({**branch,'since':1,'limit':2})
    assert seen[0]['since'] == 1
    assert [r['id'] for r in value['items']] == ['new','old']
    assert value['items'][0]['tags'] == [['e','old']]
    seen.clear()
    assert channel_engine._community_feed({**branch,'limit':0})['items'] == []
    assert seen == []


@pytest.mark.parametrize('message', ['error','empty','malformed'])
def test_relay_failure_distinct_from_empty(monkeypatch, message):
    import indienet_relay as relay
    monkeypatch.setattr(relay, '_ON_PHONE', False)
    class Socket:
        def __init__(self, url, **callbacks): self.callbacks = callbacks
        def run_forever(self):
            if message == 'error': self.callbacks['on_error'](self, 'offline')
            else:
                if message == 'malformed': self.callbacks['on_message'](self,'{broken')
                self.callbacks['on_message'](self,'["EOSE","q"]')
        def close(self): pass
    monkeypatch.setattr(relay, 'websocket', SimpleNamespace(WebSocketApp=Socket))
    net = SimpleNamespace(settings=SimpleNamespace(relays=['fixture']))
    query = relay.IndieNetRelayMixin._query_relays
    if message == 'empty':
        assert query(net,{},lambda x:x,timeout=1,require_success=True) == []
    else:
        with pytest.raises(RuntimeError):
            query(net,{},lambda x:x,timeout=1,require_success=True)


@pytest.mark.parametrize('args,valid', [
    ('agent_id:"a",message:"m",mode:"sinc"', False),
    ('agent_id:"a",message:"m",scope:"sam"', False),
    ('agent_id:"a"', False),
    ('message:"m"', False),
    ('scope:"system",message:"m"', True),
    ('scope:"cross",agent_id:"p/a",message:"m"', True),
    ('agent_id:"a",mode:"workflow",do:"[self:time]{}"', True),
    ('agent_id:"a",mode:"workflow"', False),
    ('agent_id:"a",message:"m",mode:"sync"', True),
])
def test_delegate_preflight_matches_runtime(args, valid):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    report = compile_program('[others:delegate]{'+args+'}', load_registry()).report()
    assert (report['status'] != 'invalid') is valid


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
