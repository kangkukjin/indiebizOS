"""union/merge 죽은 분기 규약 회귀 (2026-08-30 언어 개정, ep2355).

사고: 병렬 분기가 실패해 통화 없는 에러 봉투를 내면(crawl insufficient_content 실측)
union 이 "모든 입력의 통화 종류가 같아야 합니다"로 **오진**하며 전체를 죽였다 —
items:[] 실은 실패 봉투는 B24-1c 가 0행+경고로 흘려보내던 것과 같은 죽음의 다른 대접.

개정(사용자 판정): 죽은 분기의 대접은 한 벌 — 기본 = 건너뛰고 신고(branches_skipped
+ warning), on_error:"stop" = 전부-아니면-실패. 전 분기 실패 = 정직 에러.
산 분기끼리의 진짜 통화 혼합은 여전히 에러 + 분기별 통화 이름을 댄다.

실행: python3 backend/test_union_dead_branch.py  (또는 pytest)
"""
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

_HANDLER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "packages", "installed", "tools", "data-ops", "handler.py")
spec = importlib.util.spec_from_file_location("dataops_handler_t", _HANDLER)
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)

ITEMS_A = json.dumps({"success": True, "items": [{"title": "a1"}, {"title": "a2"}]})
ITEMS_B = json.dumps({"success": True, "items": [{"title": "b1"}]})
TABLE_ONLY = json.dumps({"success": True, "table": {"columns": ["이름"], "rows": [["t1"]]}})
DEAD = json.dumps({"success": False, "error": "본문을 충분히 추출하지 못했습니다.",
                   "reason": "insufficient_content"})
DEAD_EMPTY_ITEMS = json.dumps({"success": False, "error": "죽음", "items": []})


def _rows(r):
    """성공 봉투의 행 수 — items 또는 table 투영(_get_table 재구성 경로) 어느 쪽이든."""
    if isinstance(r.get("items"), list):
        return len(r["items"])
    return len(((r.get("table") or {}).get("rows")) or [])


def test_dead_branch_skipped_by_default_with_report():
    """ep2355 재현 — 죽은 분기(통화 없음)는 기본 건너뛰고 신고, 산 분기는 합쳐진다."""
    r = H._op_union([DEAD, ITEMS_A, ITEMS_B], {})
    assert r.get("success") is not False, r
    assert _rows(r) == 3
    assert r["branches_skipped"][0]["branch"] == 1
    assert "건너뛰" in r["warning"]


def test_on_error_stop_names_the_real_cause():
    """오진 봉인 — stop 이면 '통화 불일치'가 아니라 '분기 실패'라고 말한다."""
    r = H._op_union([DEAD, ITEMS_A], {"on_error": "stop"})
    assert r["success"] is False
    assert "분기 실패" in r["error"] and "통화" in r["error"]
    assert r["branches_failed"][0]["branch"] == 1
    assert "통화 종류가 같아야" not in r["error"]


def test_all_dead_is_honest_error():
    r = H._op_union([DEAD, DEAD], {})
    assert r["success"] is False and "전부 실패" in r["error"]


def test_table_and_items_branches_unite_by_columns():
    """table 전용 + items 분기 = 에러 아님 — _get_table 이 items 에서 표를 재구성해
    열 이름으로 통합한다(한쪽에만 있는 열은 None). '통화 불일치' 에러가 사실상
    죽은 분기 오진에서만 나던 이유가 이것이다."""
    r = H._op_union([TABLE_ONLY, ITEMS_A], {})
    assert r.get("success") is not False, r
    assert _rows(r) == 3
    cols = [str(c) for c in r["table"]["columns"]]
    assert "이름" in cols and "title" in cols


def test_currencyless_live_branch_errors_with_kinds():
    """산 분기가 통화 없이(스칼라 성공 봉투) 도달하면 — 여전히 에러 + 분기별 통화 이름."""
    scalar = json.dumps({"success": True, "result": "42"})
    r = H._op_union([scalar, ITEMS_A], {})
    assert r["success"] is False
    assert "통화 종류가 같아야" in r["error"]
    assert "1=없음" in r["error"]


def test_invalid_on_error_rejected():
    r = H._op_union([ITEMS_A, ITEMS_B], {"on_error": "keep"})
    assert r["success"] is False and "on_error" in r["error"]


def test_empty_items_dead_branch_behavior_unchanged():
    """items:[] 실은 실패 봉투 = 종전 B24-1c 경로(산 분기, 0행+경고) — 동작 불변."""
    r = H._op_union([DEAD_EMPTY_ITEMS, ITEMS_A], {})
    assert r.get("success") is not False
    assert _rows(r) == 2
    assert "실패" in (r.get("warning") or "")
    assert "branches_skipped" not in r


def test_merge_same_contract():
    r = H._op_merge([DEAD, ITEMS_A, ITEMS_B], {})
    assert r.get("success") is not False
    assert _rows(r) == 3 and r["branches_skipped"][0]["branch"] == 1
    r2 = H._op_merge([DEAD, ITEMS_A], {"on_error": "stop"})
    assert r2["success"] is False and "분기 실패" in r2["error"]
    r3 = H._op_merge([TABLE_ONLY, ITEMS_A], {})
    assert r3["success"] is False and "table" in r3["error"] and "분기 1" in r3["error"]


if __name__ == "__main__":
    # 러너는 하나 — pytest 에 위임 (test_single_runner 규약).
    import pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
