"""반사 경로 도구 로그의 ERR 사유 + [self:memory] keywords 배열 수용 (2026-09-05, ep2831 관찰).

  ① `[self:memory]{op:"save", keywords: ["a","b"]}` 가 sqlite 바인딩(list 미지원)에서 죽었다 — 키워드는
     본성상 목록이다. 저장소(memory_db.save)가 배열을 쉼표 문자열로 합쳐 받는다(핸들러는 통과).
  ② 반사 경로의 도구 로그 줄이 `-> ERR (21ms)` 만 남겨 로그만으로 원인을 알 수 없었다 — 오늘 아침
     고친 "원인 은닉" 부류. 실패 결과의 error 를 사유로 싣는다(예외도 이름+메시지).

실행: .venv/bin/python -m pytest -q backend/test_tool_err_reason_and_keywords_list.py
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: E402,F401

_PKG = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── ① keywords 배열 ──
def test_memory_db_normalizes_keywords_list():
    md = _load("_t_kw_memory_db", os.path.join(_PKG, "memory", "memory_db.py"))
    assert md.normalize_keywords(["ai_startup_report", " indiebizOS 출품 ", "", "ARC"]) == "ai_startup_report, indiebizOS 출품, ARC"
    assert md.normalize_keywords("a, b") == "a, b"
    assert md.normalize_keywords(None) == ""
    assert md.normalize_keywords(("x", 3)) == "x, 3"


def test_memory_handler_passes_list_keywords_to_store():
    """핸들러 → 저장소 경계: 배열이 그대로 저장소에 닿고(합치는 것은 저장소 계약), 응답은 성공."""
    h = _load("_t_kw_memory_handler", os.path.join(_PKG, "memory", "handler.py"))
    seen = {}

    class _Db:
        @staticmethod
        def normalize_category(c):
            return c or "기타"

        @staticmethod
        def save(**kw):
            seen.update(kw)
            return 7

        @staticmethod
        def body_noun_leak(text):
            return None

    out = json.loads(h._memory_save(_Db, {"content": "c", "node": "보고서", "keywords": ["a", "b"]}, "/p", "tester"))
    assert out.get("success") is not False and out.get("memory_id") == 7, out
    assert seen["keywords"] == ["a", "b"]


# ── ② ERR 사유 ──
def test_failure_reason_extracts_error_from_result():
    import system_tools as st
    assert st._failure_reason(json.dumps({"success": False, "error": "node가 필요합니다(빈 문자열 = 뿌리)."})) == "node가 필요합니다(빈 문자열 = 뿌리)."
    assert st._failure_reason({"success": False, "error": "x" * 300}).endswith("…") and len(st._failure_reason({"success": False, "error": "x" * 300})) <= 161
    assert st._failure_reason(json.dumps({"success": True})) == ""
    assert st._failure_reason("not json") == ""


def test_log_line_carries_reason(capsys):
    import system_tools as st
    st._log_ibl("execute_ibl", {"code": "[self:memory]{op: \"save\"}"}, 21.0, "system_ai", False,
                reason="Error binding parameter 1: type 'list' is not supported")
    out = capsys.readouterr().out
    assert "-> ERR (21ms): Error binding parameter 1" in out, out
    st._log_ibl("execute_ibl", {"code": "[self:time]"}, 5.0, "system_ai", True)
    assert "-> OK (5ms)" in capsys.readouterr().out


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
