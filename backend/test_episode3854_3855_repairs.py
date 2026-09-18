"""ep3854·3855 감사 수리(2026-09-18) — 실행자가 실제로 부딪힌 세 자리.

① `api.py status` 가 코드 매니페스트 두 벌(파일 791개 해시 × 2)을 그대로 찍어 수리 턴이 18만 자를 문맥으로 받았다.
② 스크립트는 `id` 로 부르는데 `[self:script]{op:"list"}` 행에 `id` 열이 없어 select·filter 가 두 번 실패했다.
③ ddg 검색 0건이 `success:false` "검색 실패: No results found." 로 돌아와 실행 실패로 세어졌다(뉴스 검색은 0행 성공 계약).
④ 검색 26건을 한 건씩 호출 — `queries` 배치가 뉴스 소스에만 있었고 가이드·설명에 묶어 부르기가 없었다.
⑤ 수리 턴이 전수 시험(약 8분)을 전경으로 돌리고 30여 호출로 폴링 — 전수는 전경 거절, 실행기가 자식에게 실행 방식을 알린다.
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


def _run_test_script(args, mode):
    import os
    import subprocess
    env = {**os.environ, "INDIEBIZ_SCRIPT_MODE": mode} if mode else {k: v for k, v in os.environ.items() if k != "INDIEBIZ_SCRIPT_MODE"}
    p = subprocess.run([sys.executable, str(ROOT / "data" / "scripts" / "시험.py")], input=json.dumps(args),
                       capture_output=True, text=True, timeout=60, env=env)
    return json.loads(p.stdout), p.stderr


def test_whole_suite_is_refused_in_foreground_and_scoped_runs_still_work():
    """⑤ ep3855: 수리 턴이 8분짜리 전수 시험을 전경으로 돌리고 30여 호출로 폴링했다 — 전수는 전경으로 받지 않는다(거절은 즉시)."""
    for args in ({}, {"files": ["backend/"]}, {"files": ["backend/test_tree_doc.py", "backend"]}):
        out, _err = _run_test_script(args, "foreground")
        assert out["success"] is False and "background:true" in out["error"] and "바뀐 곳" in out["error"], args
    # 바뀐 곳의 시험 파일은 전경 그대로 — 없는 파일은 그 줄만 실패로 말한다(pytest 를 띄우지 않고 끝난다)
    out, err = _run_test_script({"files": ["backend/test_없는파일.py"]}, "foreground")
    assert "success" not in out and out["items"][0]["failures"] == ["파일 없음"] and "[진행] 1/1" in err
    # 백그라운드는 전수를 받는다 — 여기선 관문을 지나는지만 본다(전수를 실제로 돌리지 않는다)
    import importlib.util
    spec = importlib.util.spec_from_file_location("_t_시험_3855", ROOT / "data" / "scripts" / "시험.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    assert mod._whole_suite([]) and mod._whole_suite(["backend/"]) and not mod._whole_suite(["backend/test_tree_doc.py"])


def test_script_runner_tells_the_child_how_it_is_run(tmp_path, monkeypatch):
    ops = _load("_t_script_ops_mode_3855", TOOLS / "system_essentials" / "script_ops.py")
    monkeypatch.setattr(ops, "_review_environment", lambda: None)
    assert ops._child_env("foreground")["INDIEBIZ_SCRIPT_MODE"] == "foreground"
    assert ops._child_env("background")["INDIEBIZ_SCRIPT_MODE"] == "background" and "PATH" in ops._child_env("background")
    monkeypatch.setattr(ops, "_review_environment", lambda: {"PATH": "/x", "STAGING": "/s"})
    assert ops._child_env("foreground") == {"PATH": "/x", "STAGING": "/s", "INDIEBIZ_SCRIPT_MODE": "foreground"}
    for name, path in {"_RUN_DIR": tmp_path / "runs", "_JOB_DIR": tmp_path / "runs/jobs", "_STATE": tmp_path / "state.json"}.items():
        monkeypatch.setattr(ops, name, path)
    monkeypatch.setattr(ops, "_review_environment", lambda: None)
    script = tmp_path / "mode.py"
    script.write_text("import os, json; print(json.dumps({'items': [{'mode': os.environ.get('INDIEBIZ_SCRIPT_MODE')}]}))\n", encoding="utf-8")
    monkeypatch.setattr(ops, "_read_registry", lambda: {"mode": {"file": "mode.py", "interpreter": "python"}})
    monkeypatch.setattr(ops, "_script_path", lambda e: script)
    assert ops.op_run({"id": "mode"})["items"] == [{"mode": "foreground"}]


def test_repair_doctrine_and_guide_state_the_verification_scope():
    doctrine = (ROOT / "data" / "common_prompts" / "fragments" / "13_repair.md").read_text(encoding="utf-8")
    guide = (ROOT / "data" / "guides" / "script.md").read_text(encoding="utf-8")
    assert "검증의 범위는 바뀐 곳이다" in doctrine and "검증의 범위는 바뀐 곳이다" in guide
    assert "wait: 240" in doctrine and "background: true" in guide


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
