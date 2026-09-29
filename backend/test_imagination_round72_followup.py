"""상상훈련 72회차 후속 — 밭 이관 관문과 그 관문이 드러낸 잔여 자리. 라이브 서비스 없음."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'data/packages/installed/tools'
sys.path.insert(0, str(ROOT / 'scripts'))


def module(package, name):
    path = TOOLS / package / (name + '.py')
    spec = importlib.util.spec_from_file_location(f'r72f_{package.replace("-", "_")}_{name}', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_package(root, handler_src, props, action=None):
    pkg = root / 'data/packages/installed/tools/fake'
    pkg.mkdir(parents=True)
    (pkg / 'handler.py').write_text(handler_src, encoding='utf-8')
    (pkg / 'tool.json').write_text(json.dumps({'tools': [{
        'name': 'fake_op', 'input_schema': {'type': 'object', 'properties': {k: {'type': 'string'} for k in props}}}]}))
    cfg = {'router': 'handler', 'tool': 'fake_op', 'target_key': 'op',
           'ops': {'default': 'save', 'values': {'save': '', 'query': ''}}, **(action or {})}
    return {'nodes': {'self': {'actions': {'fake': cfg}}}}


def test_gate_follows_input_flow_not_variable_names(tmp_path):
    """B72-2 원형: input_data 로 받고 도우미로 넘긴 뒤 읽는 키 — 옛 관문(이름·패키지 합집합)은 못 봤다."""
    from iblbuild_action_reads import validate_action_reads
    data = _fake_package(tmp_path, '''
def _fields(d):
    return d.get("counterparty"), d["date"]

def save(input_data):
    _fields(input_data)
    return input_data.get("amount")

def query(input_data):
    return input_data.get("month")

_OP_DISPATCHERS = {"fake_op": {"save": save, "query": query}}
''', ['amount', 'month'])
    issues = validate_action_reads(data, tmp_path)
    assert len(issues) == 1 and "op:\"save\"" in issues[0]
    assert "['counterparty', 'date']" in issues[0]


def test_gate_accepts_aliases_and_keyword_dispatch(tmp_path):
    from iblbuild_action_reads import validate_action_reads
    data = _fake_package(tmp_path, '''
def save(query=None, lon=None, **kwargs):
    return kwargs.get("limit")

def query(query=None):
    return query

def _dispatch(op=None, **kwargs):
    fn = _OP_DISPATCHERS["fake_op"].get(op)
    return fn(**kwargs)

_OP_DISPATCHERS = {"fake_op": {"save": save, "query": query}}
''', ['query', 'lng'], {'aliases': {'lng': ['lon']}})
    issues = validate_action_reads(data, tmp_path)
    assert len(issues) == 1 and "['limit']" in issues[0]


def test_live_vocabulary_has_no_undeclared_dispatcher_reads():
    import yaml
    from iblbuild_action_reads import validate_action_reads
    from iblbuild_params_check import IMPL_READ_ALLOW
    nodes = yaml.safe_load((ROOT / 'data/ibl_nodes.yaml').read_text(encoding='utf-8'))
    assert validate_action_reads(nodes, ROOT, IMPL_READ_ALLOW) == []


def test_cctv_search_uses_canonical_longitude(monkeypatch):
    """선언 정본 lng 가 search 에서 시그니처 필터에 말없이 버려지던 자리."""
    import inspect
    h = module('cctv', 'handler')
    assert 'lng' in inspect.signature(h.cctv_search).parameters   # 시그니처 필터가 정본을 통과시킨다
    seen = {}
    def fake_search(query, lat=None, lng=None):
        seen.update(lat=lat, lng=lng)
        return '{}'
    monkeypatch.setitem(h._OP_DISPATCHERS['cctv_query'], 'search', fake_search)
    h._cctv_query(op='search', query='강남역', lat=37.5, lng=127.0)
    assert seen['lng'] == 127.0
    seen.clear()
    h._cctv_query(op='search', query='강남역', lat=37.5, lon=127.1)   # 별칭을 거치지 않는 옛 표기
    assert seen['lng'] == 127.1


def test_neighbor_delete_reads_canonical_npub(monkeypatch):
    h = module('business', 'handler')
    hidden = []
    monkeypatch.setattr(h, '_hide_dm_peer', hidden.append)
    out = h._nb_delete(None, {'npub': 'npub1abc'})
    assert hidden == ['npub1abc'] and '숨겼' in json.loads(out).get('message', out)


def test_pipe_collision_names_the_receiver():
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    plan = compile_program('"본문" >> [self:notify_user]{message:"요약"}', load_registry(), {}, {})
    msg = next(i['message'] for i in plan.issues if i['code'] == 'PIPE_COLLISION')
    assert '`message`' in msg and '[self:notify_user]' in msg


def test_nested_schedule_program_carries_inner_hint():
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    code = ('[self:manage_events]{op:"create", title:"t", date:"2026-10-01", time:"09:00", repeat:"monthly", '
            'do:"[self:finance]{op:\\"query\\", query_type:\\"summary\\"} >> [self:notify_user]{message:\\"요약\\"}"}')
    plan = compile_program(code, load_registry(), {}, {})
    msg = next(i['message'] for i in plan.issues if i['code'] == 'ARGUMENT_CONTRACT')
    assert '(PIPE_COLLISION)' in msg and '`message`' in msg and '빼거나' in msg


# ── B72-3 밭 이관: 로컬 저장소의 기본 상한 ─────────────────────────────

def _scan(tmp_path, files):
    import check_silent_clamp as c
    paths = []
    for name, src in files.items():
        p = tmp_path / name
        p.write_text(src, encoding='utf-8')
        paths.append(p)
    return [(h[2], h[3], h[4]) for h in c.scan_sql_defaults(paths)]


def test_sql_default_cap_rule_catches_b72_3_shape(tmp_path):
    """가계부 원형: 저장소 기본 200 + 핸들러 `get('limit') or 200` — 둘 다 신고 없음."""
    hits = _scan(tmp_path, {
        'storage.py': 'def rows(limit=200):\n    return "SELECT * FROM t LIMIT ?", limit\n'
                      'def search(q):\n    return "SELECT * FROM t WHERE x LIKE ? LIMIT 30"\n',
        'handler.py': 'import storage\ndef query(d):\n    return storage.rows(limit=d.get("limit") or 200)\n'})
    assert sorted(hits) == [('LIMIT', 30, 'search'), ('limit', 200, 'query'), ('limit', 200, 'rows')]


def test_sql_default_cap_rule_accepts_reporting_or_reason(tmp_path):
    hits = _scan(tmp_path, {
        'storage.py': 'def rows(limit=200):\n    total = 5\n    return {"sql": "SELECT * FROM t LIMIT ?", "total_count": total}\n'
                      '# clamp-ok: 순위 상위 N — 관련도 순위\ndef rank(top_k=10):\n    return "SELECT * FROM fts LIMIT ?"\n',
        'handler.py': 'import storage\ndef query(d):\n    return storage.rows(limit=d.get("limit") or 200)\n'})
    assert hits == []


def test_live_tree_has_no_silent_local_caps():
    import check_silent_clamp as c
    assert c.main_sql() == []


def test_health_summary_counts_full_population(tmp_path, monkeypatch):
    s = module('health-record', 'health_storage')
    monkeypatch.setattr(s, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(s, 'IMAGES_DIR', str(tmp_path / 'img'))
    monkeypatch.setattr(s, 'DB_PATH', str(tmp_path / 'health.db'))
    for i in range(70):
        s.save_measurement('blood_pressure', {'systolic': 120, 'diastolic': 80}, note=f'n{i}')
    assert len(s.get_measurements(days=30)) == 70
    assert len(s.get_measurements(days=30, limit=5)) == 5
    assert s.get_health_summary(days=30)['measurements']['blood_pressure']['count'] == 70
    assert len(s.search_records('n')['measurements']) == 70


def test_music_library_reports_population(monkeypatch):
    h = module('music-player', 'handler')
    from types import SimpleNamespace
    core = SimpleNamespace(query_tracks=lambda limit, **c: [{'path': str(i)} for i in range(limit)],
                           count_tracks=lambda **c: 450, load_sources=lambda: [1])
    monkeypatch.setattr(h, '_core', lambda: core)
    out = h._library({})
    assert out['count'] == 300 and out['total_count'] == 450 and out['truncated'] is True
    assert '450곡' in out['message']
    full = h._library({'limit': 500})
    assert full['count'] == 500 and full['truncated'] is False


def test_blog_posts_page_carries_total_and_next_offset(tmp_path, monkeypatch):
    import sqlite3
    ins = module('blog', 'tool_blog_insight')
    db = tmp_path / 'blog.db'
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE posts (post_id TEXT, title TEXT, category TEXT, pub_date TEXT, content TEXT)')
    con.executemany('INSERT INTO posts VALUES (?,?,?,?,?)', [(str(i), f't{i}', 'c', f'2026-09-{i % 28 + 1:02d}', 'x') for i in range(130)])
    con.commit(); con.close()
    def get_db(*, read_only=False):
        assert read_only
        c = sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True)
        c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(ins, 'get_db', get_db)
    out = ins.blog_get_posts(count=20)
    assert out['count'] == 20 and out['total_count'] == 130 and out['truncated'] and out['next_offset'] == 20
    big = ins.blog_get_posts(count=150, offset=100)
    assert big['clamped'] and big['requested'] == 150 and big['count'] == 30 and big['truncated'] is False


def test_partial_source_message_names_the_remedy():
    from ibl_v2_adapters import _partial_message
    raw = {"truncated": True, "message": "8087곡 중 앞 300곡 — 전부 보려면 limit 를 올리세요(최대 2000)."}
    msg = _partial_message(raw, {"truncations": [{"scope": "source", "reason": "limit", "limit": 300, "retained": 300}]})
    assert msg.startswith("도구의 원천 결과가 불완전합니다.")
    assert "`limit`(상한 300)" in msg and "명시하면" in msg and "8087곡" in msg
    assert _partial_message({}, {"truncations": []}) == "도구의 원천 결과가 불완전합니다."



def test_billing_notices_are_not_payments():
    """포획소 원문(2026-09-29 확인) — 청구 예정 안내가 545,408원 지출로 적히던 B72-1 #102."""
    sync = module('finance-record', 'finance_sync')
    assert sync._parse_payment('하나카드 결제예정금액', '강*진 님 09월 15일 결제예정금액은 545,408원 입니다.')['type'] == 'notice'
    assert sync._parse_payment('결제일 출금내역 안내', '강*진 님 08월 18일 결제대금 547,601원이 출금되었습니다.')['type'] == 'transfer'
    assert sync._record_to_row({'pkg': next(iter(sync.PAY_PKGS)), 'android.title': '하나카드 결제예정금액',
                                'android.text': '09월 15일 결제예정금액은 545,408원 입니다.', 'ts': 1}) == {}
    assert sync._parse_payment('하나카드 승인', '테스트상점(지점) / 신용(1234) / 09/29 12:00 / 누적 99,000원')['type'] == 'approve'


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
