"""ep3854·3855 감사 수리(2026-09-18) — 실행자가 실제로 부딪힌 세 자리.

① `api.py status` 가 코드 매니페스트 두 벌(파일 791개 해시 × 2)을 그대로 찍어 수리 턴이 18만 자를 문맥으로 받았다.
② 스크립트는 `id` 로 부르는데 `[self:script]{op:"list"}` 행에 `id` 열이 없어 select·filter 가 두 번 실패했다.
③ ddg 검색 0건이 `success:false` "검색 실패: No results found." 로 돌아와 실행 실패로 세어졌다(뉴스 검색은 0행 성공 계약).
④ 검색 26건을 한 건씩 호출 — `queries` 배치가 뉴스 소스에만 있었고 가이드·설명에 묶어 부르기가 없었다.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "data" / "packages" / "installed" / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_status_is_compact_by_default_and_full_on_request(tmp_path, monkeypatch, capsys):
    import restart_controller as RC
    files = {f"backend/m{i}.py": "a" * 64 for i in range(800)}
    state = {"phase": "ACTIVE", "control_token": "secret", "defer_note": "x", "last_result": {"outcome": "restarted"},
             "manifest": {"digest": "d1", "files": files}, "target_manifest": {"digest": "d2", "files": files}}
    ctl = RC.control_dir(tmp_path)
    ctl.mkdir(parents=True, exist_ok=True)
    (ctl / "state.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    assert RC.main(["status"]) == 0
    out = capsys.readouterr().out
    assert len(out) < 2000 and "secret" not in out
    assert "'phase': 'ACTIVE'" in out and "'digest': 'd1'" in out and "'files': 800" in out and "restarted" in out
    assert RC.main(["status", "--full"]) == 0
    full = capsys.readouterr().out
    assert len(full) > 100_000 and "backend/m799.py" in full and "secret" not in full


def test_script_list_rows_carry_the_name_you_call_them_by(tmp_path, monkeypatch):
    ops = _load("_t_script_ops_3855", TOOLS / "system_essentials" / "script_ops.py")
    script = tmp_path / "정산.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setattr(ops, "_read_registry", lambda: {"정산": {"file": "정산.py", "interpreter": "python3", "description": "월말 정산"}})
    monkeypatch.setattr(ops, "_read_state", lambda: {})
    monkeypatch.setattr(ops, "_script_path", lambda e: script)
    row = ops.op_list({})["items"][0]
    assert row["id"] == "정산" == row["title"]                       # 부르는 이름 = 고르는 열
    assert row["description"] == "월말 정산" and row["path"] == "data/scripts/정산.py"
    assert {"meta", "summary", "last_status", "runnable"} <= set(row)   # 기존 열은 그대로


def test_ddg_zero_results_is_a_successful_empty_currency(monkeypatch):
    web = _load("_t_ddgs_3854", TOOLS / "web" / "tool_ddgs_search.py")
    from ddgs.exceptions import DDGSException

    class NoResults:
        def text(self, *a, **k):
            raise DDGSException("No results found.")

    class EngineDown:
        def text(self, *a, **k):
            raise DDGSException("error sending request for url (https://…)")

    monkeypatch.setattr(web, "DDGS", NoResults)
    r = json.loads(web.search_web('Copilot "PKSHA"', 4))
    assert r["success"] is True and r["count"] == 0 and r["items"] == [] and "0건" in r["message"]
    monkeypatch.setattr(web, "DDGS", EngineDown)
    r = json.loads(web.search_web("x", 4))
    assert r["success"] is False and "검색 실패" in r["error"]          # 엔진 오류는 여전히 실패다


def test_search_queries_batch_is_source_agnostic(monkeypatch):
    """④ ep3854: naver·ddg 검색 26건을 한 건씩 호출 — `queries` 배치가 뉴스 소스에만 있었다. 이제 모든 소스 공통:
    검색어마다 query 태그, sections 에 검색어별 건수, 0건은 실패가 아니고, 실패한 검색어만 errors(성공한 행은 보존)."""
    web = _load("_t_web_handler_3854", TOOLS / "web" / "handler.py")
    calls = []

    def fake_execute(tool_input, context):
        calls.append((context.tool_name, tool_input.get("query"), tool_input.get("limit")))
        q = tool_input["query"]
        if q == "망가진 검색":
            return json.dumps({"success": False, "error": "검색 실패: 시간 초과"})
        rows = [] if q == "결과 없음" else [{"title": f"{q} 1", "url": f"https://e.x/{q}/1"}, {"title": f"{q} 2", "url": f"https://e.x/{q}/2"}]
        return json.dumps({"success": True, "items": rows})

    monkeypatch.setattr(web, "execute", fake_execute)
    r = web._batch_search({"source": "naver", "queries": ["가", "나", "결과 없음"], "limit": 4, "type": "news"}, "naver_search", "naver", ".")
    assert r["success"] is True and r["count"] == 4 and [s["count"] for s in r["sections"]] == [2, 2, 0]
    assert {it["query"] for it in r["items"]} == {"가", "나"} and "errors" not in r
    assert sorted(calls) == [("naver_search", "가", 4), ("naver_search", "결과 없음", 4), ("naver_search", "나", 4)]   # queries 는 안쪽으로 새지 않는다
    r = web._batch_search({"source": "ddg", "queries": "가, 망가진 검색"}, "ddgs_search", "ddg", ".")
    assert r["success"] is False and r["count"] == 2 and r["errors"] == [{"query": "망가진 검색", "error": "검색 실패: 시간 초과"}]
    assert web._batch_search({"queries": " , "}, "ddgs_search", "ddg", ".")["success"] is False


def test_web_search_guide_teaches_batching_with_a_placeholder_skeleton():
    guide = (ROOT / "data" / "guides" / "web_search.md").read_text(encoding="utf-8")
    assert "queries:[" in guide and "<국내 검색어 1>" in guide and "[table:dedup]" in guide     # 완성 처방이 아니라 자리표 골격
    desc = (TOOLS / "web" / "ibl_actions.yaml").read_text(encoding="utf-8")
    assert "모든 source 공통 배치" in desc


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
