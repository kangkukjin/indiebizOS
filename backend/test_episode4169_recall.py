"""현재 분석 턴 오선택 방지 + IBL에서 기존 통합 원문 읽기까지 연결하는 회귀."""
import boot_paths  # noqa: F401
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from test_execution_trace import trace, source_files, add_store  # noqa: F401


@pytest.fixture
def body():
    path = Path(__file__).parents[1] / "data/packages/installed/tools/system_essentials/body_ops.py"
    spec = importlib.util.spec_from_file_location("body_episode4169", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def journal(tmp_path, monkeypatch):
    import episode_logger as el

    path = tmp_path / "pulse.db"

    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(el, "_get_db", connect)
    el._ensure_episode_tables_core()
    with connect() as conn:
        # 최근 임의 개수를 먼저 뽑고 종료 여부를 거르면 오래된 종료 행을 놓친다.
        for eid in range(1, 105):
            ended = "closed" if eid in (1, 2, 104) else None
            source = "test" if eid == 104 else "usage"
            conn.execute("INSERT INTO episode_log(id,started_at,ended_at,agent,user_message,run_id,source) "
                         "VALUES(?,?,?,?,?,?,?)", (eid, str(eid), ended, "agent", f"request-{eid}", f"run-{eid}", source))
            conn.execute("INSERT INTO trajectory_event(run_id,event_seq,episode_id,ts,kind,data,source) "
                         "VALUES(?,1,?,'now','request.received','{}',?)", (f"run-{eid}", eid, source))
    return path


def test_default_skips_all_running_and_test_rows_but_explicit_live_id_works(body, journal):
    import episode_logger as el

    # 기존 주행기록 UI는 진행 중 행을 계속 보여준다.
    assert el.get_episode_journal(1)[0]["id"] == 103
    out = body.op_trajectory({})
    assert out["success"] and out["episode_id"] == 2
    assert {e["episode_id"] for e in out["items"]} == {2}
    assert out["trace_args"] == {"op": "trajectory", "view": "trace", "episode_id": 2}
    live = body.op_trajectory({"episode_id": 103})
    assert live["success"] and live["episode_id"] == 103


def test_recent_episodes_selects_before_limit_and_reports_selection(body, journal):
    out = body.op_trajectory({"view": "episodes", "limit": 1})
    assert out["success"] and out["has_more"]
    assert [e["episode_id"] for e in out["items"]] == [2]
    assert out["items"][0]["user_message"] == "request-2"
    assert out["items"][0]["evaluation_result"] is None
    assert out["items"][0]["trace_args"]["episode_id"] == 2
    assert [e["episode_id"] for e in body.op_trajectory({"view": "episodes"})["items"]] == [2, 1]


def test_no_ended_episode_is_empty_not_current(body, journal):
    with sqlite3.connect(journal) as conn:
        conn.execute("UPDATE episode_log SET ended_at=NULL")
    for view in ("events", "episodes", "trace"):
        out = body.op_trajectory({"view": view})
        assert out["success"] and out["items"] == []


def test_trace_to_log_document_keeps_identity_pagination_and_readonly(body, trace, monkeypatch):
    service, root = trace
    monkeypatch.setattr(body, "_repo_root", lambda: str(root))
    before = source_files(root)
    out = body.op_trajectory({"view": "trace", "episode_id": 1, "limit": 2})
    assert out["success"] and out["items"] and out["next_cursor"]
    assert out["identity"]["episode_ids"] == [1]
    assert out["usage"]["complete"] is False
    ref = next(d["source_ref"] for d in out["links"]["documents"] if d["label"] == "episode 1 log")
    first = body.op_trajectory({"view": "document", "episode_id": 1, "source_ref": ref, "limit": 4})
    assert first["success"] and first["items"][0]["text"] == "raw "
    second = body.op_trajectory({"view": "document", "episode_id": 1, "source_ref": ref,
                                 "offset": first["next_offset"], "cursor": first["next_cursor"]})
    assert first["text"] + second["text"] == "raw episode log"
    wrong = body.op_trajectory({"view": "document", "episode_id": 2, "source_ref": ref})
    assert not wrong["success"] and wrong["status"] == "forbidden"
    assert source_files(root) == before


def test_first_trace_page_links_response_without_scanning_all_events(body, trace, monkeypatch):
    service, root = trace
    store, _ = add_store(service, root)
    store.put_response("검토한 최종 답변")
    (store.directory / "review_status.json").write_text(json.dumps({
        "status": "ACHIEVED", "response": store.manifest()}))
    monkeypatch.setattr(body, "_repo_root", lambda: str(root))
    before = source_files(root)
    out = body.op_trajectory({"view": "trace", "episode_id": 1, "limit": 1})
    assert out["next_cursor"]  # 전 사건을 읽지 않은 첫 페이지에서도 응답에 바로 닿는다.
    ref = next(x["source_ref"] for x in out["links"]["documents"] if x["label"] == "supervision response")
    params = {"view": "document", "episode_id": 1, "source_ref": ref}
    assert body.op_trajectory(params)["text"] == "검토한 최종 답변"
    assert source_files(root) == before
    (store.directory / "response-v1.txt").write_text("변조한 답변")
    assert body.op_trajectory(params)["success"] is False


@pytest.mark.parametrize("params", [
    {"view": "typo"}, {"view": "episodes", "episode_id": 1},
    {"view": "episodes", "limit": 0}, {"view": "episodes", "limit": 101},
    {"view": "trace", "episode_id": True}, {"view": "trace", "limit": "10"},
    {"view": "trace", "cursor": "stale"}, {"view": "trace", "source_ref": "wrong-view"},
    {"view": "trace", "task_id": "task"}, {"view": "document", "source_ref": "ref"},
    {"view": "document", "episode_id": 1}, {"view": "events", "cursor": "cursor"},
])
def test_invalid_selection_does_not_silently_fall_back(body, params):
    assert body.op_trajectory(params)["success"] is False


def test_catalog_advertises_direct_recall():
    import yaml
    path = Path(__file__).parents[1] / "data/packages/installed/tools/system_essentials/ibl_actions.yaml"
    catalog = yaml.safe_load(path.read_text())
    # 구조를 손으로 복제하지 않고 선언에서 해당 action을 찾는다.
    def find(value):
        if isinstance(value, dict):
            if "body" in value and isinstance(value["body"], dict) and value["body"].get("tool") == "body_op":
                return value["body"]
            for child in value.values():
                result = find(child)
                if result:
                    return result
    action = find(catalog)
    assert {"view", "source_ref", "cursor", "offset"} <= action["params"].keys()
    assert "에피소드" in action["description"]


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
