"""봉투의 success 는 대칭이어야 한다 — 전역 결과 계약 (2026-09-07, 사용자 판정).

비대칭: 실패는 `success: false` 를 말하는데 성공은 아무 말도 안 하는 낱말이 많았다.
정적 스윕 42함수 · 실측 `shape="dict"` 성공 봉투 296건(10액션). 그래서
`resp.get("success")` 로 판정한 쪽은 **성공을 실패로 읽는다** — 실측 사고: 성공한
`[self:memory]{op:"save"}` 를 실패로 읽고 같은 요청을 다시 보내 기억 원장에 같은
내용이 두 행 생겼다.

수리 자리 = **모든 라우터가 공유하는 결과 계약**(ibl_engine, public_result 바로 뒤).
낱말마다 기억하지 않는다. 규약의 단일 소유자는 `common.currency.stamp_success` —
엔진 경계와 패키지(memory handler)가 같은 함수를 부른다(판정기는 하나).

★물들이지 않기: 다른 필드로만 실패를 말하는 봉투는 낱말 쪽에서 error 로 고쳐야 한다
(경계 실측으로 훑어 memory:delete 를 먼저 닫았다). 산문·목록 통화는 감싸지 않는다.

실행: .venv/bin/python -m pytest -q backend/test_envelope_success_contract_2026_09_07.py
"""
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))
import boot_paths  # noqa: E402,F401
from common.currency import stamp_success  # noqa: E402


# ── 규약 단위 ────────────────────────────────────────────────────────────
def test_dict_without_success_gets_true_first():
    out = stamp_success({"memory_id": 500, "message": "저장 완료"})
    assert out["success"] is True
    assert list(out)[0] == "success"          # 첫 줄에서 결과가 보이도록


def test_dict_with_error_gets_false():
    assert stamp_success({"error": "무엇이 잘못됨"})["success"] is False
    # 엔진의 성공 판정(result.get("error") 참이면 실패)과 같은 규칙 — 빈 error 는 실패가 아니다
    assert stamp_success({"error": ""})["success"] is True


def test_existing_success_is_never_overwritten():
    assert stamp_success({"success": False, "x": 1})["success"] is False
    assert stamp_success({"success": True, "error": "잔재"})["success"] is True
    assert stamp_success('{"success": false, "x": 1}') == '{"success": false, "x": 1}'


def test_prose_and_list_currency_untouched():
    """통화가 문자열·배열인 자리를 봉투로 바꾸면 하류가 받는 것이 달라진다."""
    assert stamp_success("그냥 산문입니다") == "그냥 산문입니다"
    assert stamp_success("[1, 2, 3]") == "[1, 2, 3]"
    assert stamp_success([{"a": 1}]) == [{"a": 1}]
    assert stamp_success(42) == 42
    assert stamp_success(None) is None
    assert stamp_success("{깨진 JSON") == "{깨진 JSON"      # 파싱 실패는 원형 그대로


def test_json_string_envelope_is_stamped_in_place():
    out = json.loads(stamp_success('{"count": 2, "items": []}'))
    assert out["success"] is True and out["count"] == 2


# ── 엔진 경계(모든 라우터가 지나는 자리) ─────────────────────────────────
def test_engine_boundary_stamps_router_result(monkeypatch):
    """라우터가 success 없는 봉투를 내도 경계에서 채워진다 — 낱말 수정 없이."""
    sys.path.insert(0, str(_ROOT / "backend" / "ibl"))
    sys.path.insert(0, str(_ROOT / "backend" / "cognition"))
    import ibl_engine
    from system_tools_ibl import _execute_ibl_unified

    def _fake_router(mapped_tool, params, project_path, agent_id=None, scope="project"):
        return {"rows": 3, "note": "success 를 말하지 않는 옛 봉투"}   # 42함수의 모양

    monkeypatch.setattr(ibl_engine, "_route_handler", _fake_router)
    out = _execute_ibl_unified({"code": '[table:take]{items: [{"a": 1}], n: 1}',
                                "verbose": True}, str(_ROOT))
    if isinstance(out, str):
        out = json.loads(out)
    assert out.get("success") is True and out.get("rows") == 3, out


def test_engine_boundary_marks_error_envelope_false(monkeypatch):
    sys.path.insert(0, str(_ROOT / "backend" / "ibl"))
    sys.path.insert(0, str(_ROOT / "backend" / "cognition"))
    import ibl_engine
    from system_tools_ibl import _execute_ibl_unified

    def _fake_router(mapped_tool, params, project_path, agent_id=None, scope="project"):
        return {"error": "옛 봉투의 실패 — success 를 안 달았다"}

    monkeypatch.setattr(ibl_engine, "_route_handler", _fake_router)
    out = _execute_ibl_unified({"code": '[table:take]{items: [{"a": 1}], n: 1}',
                                "verbose": True}, str(_ROOT))
    if isinstance(out, str):
        out = json.loads(out)
    assert out.get("success") is False, out


def test_one_owner_for_the_rule():
    """패키지와 엔진이 각자 판정하지 않는다 — 같은 함수를 부른다(판정기는 하나)."""
    handler = (_ROOT / "data" / "packages" / "installed" / "tools" / "memory"
               / "handler.py").read_text(encoding="utf-8")
    engine = (_ROOT / "backend" / "ibl" / "ibl_engine.py").read_text(encoding="utf-8")
    assert "from common.currency import stamp_success" in handler
    assert "from common.currency import stamp_success" in engine


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
