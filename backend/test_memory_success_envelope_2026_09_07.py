"""[self:memory] 봉투의 success — 성공은 말이 없고 실패만 말하던 비대칭 (2026-09-07).

실측 사고: `{"memory_id": 500, "message": "…저장 완료…"}` 에는 success 가 없어서
`resp.get("success")` 로 판정한 쪽이 **성공한 저장을 실패로 읽고 같은 요청을 또
보냈다** — 기억 원장에 같은 내용이 두 행(500·501) 생긴 직접 원인.

계약(초크포인트 `_with_success`, op 마다 손으로 넣지 않는다):
  · 딕셔너리 봉투는 성공이면 success:true, error 를 담았으면 success:false
  · 이미 success 가 있으면 손대지 않는다(recall·move 는 제 값을 갖고 있다)
  · **산문 반환(read 의 전문)은 감싸지 않는다** — 통화가 문자열이라 봉투로 바꾸면
    통화 모양이 바뀐다
  · delete 는 못 지웠으면 success:false — 초크포인트가 거짓을 물들이면 안 된다

실행: .venv/bin/python -m pytest -q backend/test_memory_success_envelope_2026_09_07.py
"""
import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))
import boot_paths  # noqa: E402,F401

_PKG = _ROOT / "data" / "packages" / "installed" / "tools" / "memory"
sys.path.insert(0, str(_PKG))


@pytest.fixture(scope="module")
def mem():
    spec = importlib.util.spec_from_file_location("_t_succ_mem_handler", str(_PKG / "handler.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def ctx(tmp_path):
    """★임시 저장소 — 시험은 실물 기억 원장에 쓰지 않는다."""
    return types.SimpleNamespace(tool_name="memory_op",
                                 project_path=str(tmp_path), agent_id="t_succ")


def _once(mem, ctx, **ti):
    """execute 는 **한 번만** 부른다 — 두 번 부르면 save 가 두 행을 만든다(이 사고의 모양)."""
    raw = mem.execute(ti, ctx)
    return json.loads(raw) if raw.lstrip().startswith("{") else raw


def test_save_says_success_and_says_it_first(mem, ctx):
    r = _once(mem, ctx, op="save", content="성공 키 확인", keywords=["a", "b"], category="기타")
    assert r["success"] is True, r
    assert list(r)[0] == "success", list(r)      # 첫 줄에서 결과가 보이도록
    assert isinstance(r["memory_id"], int)


def test_search_says_success(mem, ctx):
    _once(mem, ctx, op="save", content="검색 대상 문장", category="기타")
    r = _once(mem, ctx, op="search", query="검색")
    assert r["success"] is True and r["count"] >= 1, r


def test_recall_keeps_its_own_success(mem, ctx):
    _once(mem, ctx, op="save", content="지도에 실릴 기억", category="기타")
    r = _once(mem, ctx, op="recall")
    assert r["success"] is True, r
    # ★한 번도 안 쓴 저장소의 recall 은 "no such table: memories" 를 그대로 흘린다 —
    #   초크포인트가 success:false 로는 감싸지만 진단은 여전히 sqlite 속말이다(별건).


def test_read_stays_prose_not_wrapped(mem, ctx):
    """산문 통화를 봉투로 감싸면 하류(브리핑·문서)가 받는 모양이 바뀐다."""
    saved = _once(mem, ctx, op="save", content="산문으로 돌아와야 하는 본문", category="기타")
    raw = mem.execute({"op": "read", "memory_id": saved["memory_id"]}, ctx)
    assert isinstance(raw, str) and not raw.lstrip().startswith("{"), raw[:80]
    assert "산문으로 돌아와야 하는 본문" in raw


def test_delete_reports_truthfully(mem, ctx):
    saved = _once(mem, ctx, op="save", content="지울 것", category="기타")
    mid = saved["memory_id"]
    ok = _once(mem, ctx, op="delete", memory_id=mid)
    assert ok["success"] is True and ok["deleted"] is True, ok
    again = _once(mem, ctx, op="delete", memory_id=mid)
    # ★초크포인트가 '못 지움'을 success 로 물들이면 안 된다 — 지울 행이 없었다는 사실은 실패다
    assert again["success"] is False and again["deleted"] is False, again
    assert str(mid) in again["error"], again


def test_failures_keep_success_false(mem, ctx):
    for ti in ({"op": "save", "content": ""},
               {"op": "search"},
               {"op": "delete"},
               {"op": "없는op"}):
        r = _once(mem, ctx, **ti)
        assert r["success"] is False and r.get("error"), (ti, r)


def test_chokepoint_leaves_declared_envelopes_alone(mem):
    """이미 success 를 가진 봉투·산문은 통과 — 헬퍼 단위 계약."""
    assert json.loads(mem._with_success('{"success": false, "x": 1}'))["success"] is False
    assert mem._with_success("그냥 산문") == "그냥 산문"
    assert mem._with_success("[1, 2]") == "[1, 2]"
    assert json.loads(mem._with_success('{"error": "무엇"}'))["success"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
