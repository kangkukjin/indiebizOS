"""최근 세 보고서의 미수리 결함 — 외부 API·모델 비용 없는 실행 회귀."""
import importlib.util
import json
from pathlib import Path
import uuid

import boot_paths  # noqa: F401
import workflow_store  # 시험 대역도 저장소 소유자에 설치한다.
import pytest

from system_tools import _execute_ibl_unified
from thread_context import actor_context


@pytest.fixture
def run(tmp_path, monkeypatch):
    import ibl_turn_vars
    monkeypatch.setattr(ibl_turn_vars, "store_path", lambda key: str(tmp_path / f"{key}.json"))
    task = f"task_test_{uuid.uuid4().hex}"

    def execute(code, **extra):
        with actor_context(agent_id="probe", task_id=task):
            raw = _execute_ibl_unified({"code": code,"edition":2,"verbose": True,**extra}, str(tmp_path), agent_id="probe")
        return json.loads(raw)

    return execute


@pytest.mark.parametrize("text", ['[{"id":1},{"id":2}]', '[]', '본문 $literal', '0', 'false', ''])
def test_single_read_assignment_keeps_original_value(run, tmp_path, text):
    path=tmp_path/'source.txt';path.write_text(text)
    first=run('[self:read]'+json.dumps({'path':str(path)}))
    assert first['success'],first
    path.unlink()
    second=run('return $입력',inputs=first['result_ref']['input_args'])
    assert second['success'],second
    assert second['value']['text']==text



def test_failed_single_read_never_becomes_a_live_variable(run, tmp_path):
    first = run('$없음 = [self:read]' + json.dumps({"path": str(tmp_path / "absent.txt")}))
    assert first["success"] is False
    assert "없음" not in first.get("turn_vars", {}).get("live", [])
    second = run('$없음')
    assert not second['success'] and 'UNBOUND' in str(second)


def _package_module(filename):
    path = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/real-estate" / filename
    spec = importlib.util.spec_from_file_location("episode_audit_" + path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 2026-09-09 /api/search 실측: 색장동이 먼저, 정확한 장동은 두 번째였다.
REGIONS = [
    {"cortarNo": "5211114400", "cortarName": "전북도 전주시 완산구 색장동"},
    {"cortarNo": "5211313200", "cortarName": "전북도 전주시 덕진구 장동"},
]


@pytest.fixture
def naver(monkeypatch):
    mod = _package_module("tool_naver.py")
    monkeypatch.setattr(mod, "has_curl_cffi", lambda: True)
    return mod


@pytest.mark.parametrize("query", ["전주 장동", "전주시 장동", "전주 덕진구 장동", "장동"])
def test_naver_selects_exact_dong_regardless_of_search_rank(naver, monkeypatch, query):
    requested = []

    def api(path, params):
        if path == "/api/search":
            return {"regions": REGIONS}
        requested.append(params["cortarNo"])
        return {"articleList": []}

    monkeypatch.setattr(naver, "_api_get", api)
    out = naver.get_naver_listings({"region": query})
    assert out["success"] and out["조회지역"] == REGIONS[1]["cortarName"]
    assert requested == ["5211313200"]


@pytest.mark.parametrize("regions", [REGIONS[:1], REGIONS + [
    {"cortarNo": "other", "cortarName": "전북도 전주시 다른구 장동"},
]])
def test_naver_rejects_wrong_or_ambiguous_regions_before_fetching(naver, monkeypatch, regions):
    def api(path, params):
        assert path == "/api/search", "모호한 위치로 매물을 조회하면 안 된다"
        return {"regions": regions}

    monkeypatch.setattr(naver, "_api_get", api)
    out = naver.get_naver_listings({"region": "전주 장동"})
    assert out["success"] is False and "검색 후보:" in out["error"]
    assert "count" not in out, "잘못된 위치를 0건으로 신고하면 안 된다"


def test_naver_complex_search_still_resolves(naver, monkeypatch):
    monkeypatch.setattr(naver, "_api_get", lambda *a: {"complexes": [
        {"complexNo": "123", "complexName": "시험아파트"},
    ]})
    loc = naver._resolve_keyword("시험아파트")
    assert loc["mode"] == "complex" and loc["complexNo"] == "123"


def test_zigbang_preserves_detail_fields_for_numeric_filter(run, monkeypatch):
    mod = _package_module("tool_zigbang.py")
    monkeypatch.setattr(mod, "_http_json", lambda *a, **k: {"items": [
        {"id": 1, "lat": 35, "lng": 127}, {"id": 2, "lat": 35, "lng": 127},
    ]})
    monkeypatch.setattr(mod, "_fetch_detail", lambda iid: {
        "itemId": iid, "salesType": "전세", "price": {"deposit": 10000 * iid, "rent": 0},
        "area": {"전용면적M2": 84}, "floor": {"floor": 2, "allFloors": 4},
        "jibunAddress": "시험 주소", "location": {"lat": 35, "lng": 127},
    })
    out = mod.get_zigbang_listings({"lat": 35, "lng": 127, "lease": "전세"})
    rows = out["items"]
    assert [r["deposit"] for r in rows] == [10000, 20000]
    assert rows[1]["rent"] == 0 and rows[1]["area_m2"] == 84 and rows[1]["floor"] == 2
    filtered = run('$rows >> [table:filter]{where:($r)=>$r.deposit>=20000}',inputs={'rows':rows})
    assert [r["itemId"] for r in filtered["value"]] == [2]


@pytest.mark.parametrize("body_fails", [False, True])
def test_named_idiom_records_its_own_result_once(run, monkeypatch, tmp_path, body_fails):
    import ibl_usage_db
    import ibl_usage_rag as rag
    import thread_context
    import workflow_engine

    body = ('[table:take]{items:[{x:1}],n:1}' if not body_fails else
            '[self:read]' + json.dumps({"path": str(tmp_path / "missing_body.txt")}))
    from function_library import register
    body='#!ibl edition=2\n[def:직전보고서찾아읽기](){return '+body+'}'
    register('직전보고서찾아읽기',body)
    row = {"id": 1, "alias": "직전보고서찾아읽기", "ibl_code": body}
    hits = []
    monkeypatch.setattr(workflow_store, "get_workflow", lambda name: None)
    monkeypatch.setattr(ibl_usage_db.IBLUsageDB, "find_phrase_by_alias", lambda self, name, **kw: row)
    monkeypatch.setattr(ibl_usage_db.IBLUsageDB, "alias_of_code", lambda self, code: row["alias"])
    monkeypatch.setattr(ibl_usage_db.IBLUsageDB, "update_success_by_code",
                        lambda self, code, ok, **kw: hits.append((code, ok, kw)) or True)
    monkeypatch.setattr(rag.IBLUsageRAG, "clear_cache", lambda self: None)
    # 회상에도 같은 몸이 있어도 중복 강화/감쇠하지 않는다.
    monkeypatch.setattr(thread_context, "get_phrase_recall", lambda: [body])
    monkeypatch.setattr(thread_context, "clear_phrase_recall", lambda: None)
    program = '[fn:직전보고서찾아읽기]\n[self:read]' + json.dumps({"path": str(tmp_path / "unrelated.txt")})
    out = run(program)
    assert out["success"] is False
    # 파일 부재는 정의 결함으로 확정할 수 없다. 실행 실패는 보존하되 감점은 보류한다.
    expected = []  # 함수 실적은 호출 ID와 revision으로만 기록한다.
    assert [(c, ok) for c, ok, _ in hits] == expected
    import episode_logger
    with episode_logger._get_db() as conn:
        recorded = [json.loads(r[0]) for r in conn.execute(
            "SELECT data FROM trajectory_event WHERE kind='ibl.started'")]
    assert any(r["fn_count"] == 1 and "fn:직전보고서찾아읽기" in r["actions"] for r in recorded)
    from capability_history import connection
    from function_store import resolve
    current = resolve('직전보고서찾아읽기', edition=2)
    with connection() as conn:
        feedback = [dict(row) for row in conn.execute(
            'SELECT * FROM function_calls WHERE function_id=? AND revision=?',
            (current['function_id'], current['revision']))]
    assert len(feedback) == 1
    assert bool(feedback[0]['success']) is (not body_fails)
    assert feedback[0]['dependency_revision']
    assert feedback[0]['run_id'] and feedback[0]['call_id']
    rag.record_recall_outcome(body, 0.95, [{
        "tool_name": "execute_ibl", "input": {"code": program}, "success": False,
    }], turn_tokens=1000)
    assert [(c, ok) for c, ok, _ in hits] == expected
    with connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM function_calls WHERE function_id=?',
                            (current['function_id'],)).fetchone()[0] == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
