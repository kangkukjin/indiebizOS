"""봉투 기본값 반전(2026-09-06, 사용자 승인) — 에이전트 경계의 final_result 는 큰 구조 데이터이면 미리보기.

전체 값은 턴 저장소(변수·그림자)에 살고, 모델은 verbose:true 또는 `$이름 >> [table:take]` 로 요구한 만큼만 본다.
앱 표면(호출 통로 "app")은 전체를 받는다. 임계는 lifecycle_policy.yaml `envelope_preview:`.

실행: .venv/bin/python -m pytest -q backend/test_envelope_preview_2026_09_06.py
"""
import json
import uuid

import pytest

from system_tools import _execute_ibl_unified
from thread_context import actor_context, set_call_channel, clear_call_channel


def _run(code, tmp_path, task, channel="agent", **extra):
    with actor_context(agent_id="probe", task_id=task):
        set_call_channel(channel, override=True)
        try:
            return json.loads(_execute_ibl_unified({"code": code, **extra}, str(tmp_path), agent_id="probe"))
        finally:
            clear_call_channel()


@pytest.fixture
def task():
    return f"task_test_{uuid.uuid4().hex[:8]}"


ROWS = [{"단지": f"단지{i}아파트", "보증금": 24000 + i * 137, "메모": "긴 설명 " * 12, "url": f"https://x.test/item/{1000 + i}"}
        for i in range(60)]
ITEMS = json.dumps(ROWS, ensure_ascii=False)


def _fr(out):
    fr = out.get("final_result")
    return json.loads(fr) if isinstance(fr, str) else fr


def test_large_items_are_previewed_but_turn_var_keeps_full(tmp_path, task):
    out = _run(f'$표 = [table:take]{{items: {ITEMS}, n: 60}} >> [table:take]{{n: 60}}', tmp_path, task)
    assert out.get("success") is True
    fr = _fr(out)
    assert len(fr["items"]) == 8 and fr["_preview"]["total"] == 60 and "단지" in fr["_preview"]["columns"]
    assert "verbose" in fr["_preview"]["note"] and out["_preview"]["of"] == "final_result"
    # 전체는 턴 변수에 — 좁혀 요구하면 그만큼 온다
    nxt = _run('$표 >> [table:take]{n: 3}', tmp_path, task)
    assert len(_fr(nxt)["items"]) == 3 and "_preview" not in _fr(nxt)
    # 60행 전부가 꼭 필요하면 verbose
    full = _run('$표 >> [table:take]{n: 60}', tmp_path, task, verbose=True)
    assert len(_fr(full)["items"]) == 60 and "_preview" not in full


def test_small_results_are_untouched(tmp_path, task):
    out = _run('[table:take]{items: [{"a": 1}, {"a": 2}, {"a": 3}], n: 3}', tmp_path, task)
    assert "_preview" not in out and len(out.get("items") or _fr(out)["items"]) == 3


def test_single_step_large_result_is_previewed(tmp_path, task):
    out = _run(f'[table:take]{{items: {ITEMS}, n: 60}}', tmp_path, task)
    items = out.get("items")
    assert isinstance(items, list) and len(items) == 8 and out["_preview"]["total"] == 60


def test_app_surface_receives_full(tmp_path, task):
    out = _run(f'[table:take]{{items: {ITEMS}, n: 60}} >> [table:take]{{n: 60}}', tmp_path, task, channel="app")
    assert len(_fr(out)["items"]) == 60 and "_preview" not in out


def test_long_prose_is_capped_and_short_prose_is_not():
    from ibl_envelope import preview_envelope, PREVIEW_DEFAULT
    cap = PREVIEW_DEFAULT["prose_chars"]
    long = "가" * (cap + 500)
    out = preview_envelope({"success": True, "final_result": long})
    assert out["final_result"].startswith("가" * 100) and "미리보기" in out["final_result"] and out["_preview"]["total_chars"] == cap + 500
    short = preview_envelope({"success": True, "final_result": "짧은 산문"})
    assert short["final_result"] == "짧은 산문" and "_preview" not in short


def test_policy_is_data_and_core_reads_no_file():
    import ast, pathlib
    from ibl_envelope import PREVIEW_DEFAULT
    from ibl_retyping import load_policy_block
    pol = load_policy_block("envelope_preview", PREVIEW_DEFAULT)
    assert pol["rows"] == 8 and pol["min_chars"] == 3000 and pol["prose_chars"] == 12000
    src = (pathlib.Path(__file__).parent / "ibl" / "ibl_envelope.py").read_text(encoding="utf-8")
    assert "from boot_paths" not in src and "import yaml" not in src     # 순수 코어는 숙주·정책 파일을 모른다(주석 제외)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
