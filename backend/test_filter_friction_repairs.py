"""table:filter · groupby 실사용 마찰 수리 회귀 (2026-08-27)

자유 턴의 조합률이 5%에 머무는 이유를 실측하다 잡은 마찰 4종 — 전부 실사용
에피소드(ep1879 사용자 심부름 · ep2114 부동산 보고서)에서 모델이 실제로 부딪혀
재시도 왕복을 태운 문장들이다. "긴 문장 = 위험"이라는 학습을 깨는 것이 목적.

  F1 `where: "A or B"`      — 옛 정직 거절 → 지원(우선순위 SQL: or 최하위)
  F2 `contains X and Y` 혼합 — 옛 조용한 0건(값으로 오독) → 중의성 정직 거절
  F4 groupby `{새열: ["count"]}` — 옛 거절 → 행수 집계 출력명(1원소 리스트 형).
     `{새열: "count"}` 는 39회차 오타-방어 계약(비실존 필드 거절)을 지키되,
     오류문이 옳은 모양({새열: ["count"]})을 그 자리에서 가르친다.
  (마찰 ③ 리터럴 items 는 이미 36회차 `968e245d` 가 수리 — [table:take] 경유 안내.)

실행: .venv/bin/python -m pytest backend/test_filter_friction_repairs.py
"""
import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKG = os.path.join(_ROOT, "data", "packages", "installed", "tools", "data-ops")


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_PKG, fname))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def h():
    return _load("_ffr_handler", "handler.py")


ROWS = [
    {"price": 100000000, "summary": "복층 테라스 좋음", "구": "용산"},
    {"price": 300000000, "summary": "복층만", "구": "용산"},
    {"price": 900000000, "summary": "테라스만", "구": "강남"},
]


def _filter(h, where, rows=ROWS):
    return h._op_filter({"success": True, "items": list(rows)}, {"where": where})


# ── F1: or 지원 (ep1879 — "price >= 2억 or price <= 4억" 가 두 번 죽었다) ──

def test_F1_or_는_이제_동작한다(h):
    out = _filter(h, "price < 200000000 or price > 500000000")
    assert out.get("success") is not False
    assert [r["price"] for r in out["items"]] == [100000000, 900000000]


def test_F1_우선순위는_SQL_이다_or_최하위(h):
    # (구 == 강남) or (구 == 용산 and price <= 100000000)
    out = _filter(h, "구 == 용산 and price <= 100000000 or 구 == 강남")
    assert [r["price"] for r in out["items"]] == [100000000, 900000000]


def test_F1_and_리스트_형_옛_동작_보존(h):
    s = _filter(h, "price >= 200000000 and price <= 400000000")
    l = _filter(h, ["price >= 200000000", "price <= 400000000"])
    assert [r["price"] for r in s["items"]] == [r["price"] for r in l["items"]] == [300000000]


# ── F2: 혼합 조각 = 중의성 정직 거절 (ep1879 — 조용한 0건이었다) ──

def test_F2_혼합_조각은_조용한_0건이_아니라_정직_거절(h):
    out = _filter(h, "summary contains 복층 and 테라스")
    assert out.get("success") is False, "옛 동작('복층 and 테라스' 리터럴 검색 → 0건 success)이 돌아왔다"
    assert "중의" in out["error"]
    # 오류가 안내한 두 형태는 실제로 동작한다
    both = _filter(h, "summary contains 복층 and summary contains 테라스")
    assert [r["price"] for r in both["items"]] == [100000000]
    lit = _filter(h, {"field": "summary", "op": "contains", "value": "복층 and 테라스"})
    assert lit["items"] == []


def test_F2_연산자_전무_문자열은_전필드_검색_옛_동작(h):
    out = _filter(h, "국밥 and 라면")  # 비교식이 하나도 없다 — 통째 substring (무변경)
    assert out.get("success") is not False
    assert out["items"] == []


# ── F4: groupby count 모양 (ep2114 — 두 모양이 연속 거절돼 groupby 를 포기했다) ──

def test_F4_count_1원소_리스트는_행수_출력명이다(h):
    out = h._op_groupby({"success": True, "items": list(ROWS)},
                        {"by": "구", "agg": {"건수": ["count"]}})
    assert out.get("success") is not False, out.get("error")
    assert out["columns"] == ["구", "건수"]
    assert sorted(map(tuple, out["rows"])) == [("강남", 1), ("용산", 2)]


def test_F4_count_스칼라_비실존_필드는_거절하되_옳은_모양을_가르친다(h):
    """39회차 계약(오타 방어) 보존 + ep2114 의 의도(행수 출력명)로 가는 길 안내."""
    out = h._op_groupby({"success": True, "items": list(ROWS)},
                        {"by": "구", "agg": {"건수": "count"}})
    assert out.get("success") is False
    assert '{건수: ["count"]}' in out["error"]


def test_F4_실제_필드명이면_문서_계약_보존_nonnull_관측수(h):
    rows = [{"구": "용산", "가격": 1}, {"구": "용산", "가격": None}]
    out = h._op_groupby({"success": True, "items": rows},
                        {"by": "구", "agg": {"가격": "count"}})
    assert out["columns"] == ["구", "count_가격"]
    assert out["rows"] == [["용산", 1]]  # non-null 관측 수 — 행수(2)가 아니다


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    raise SystemExit(pytest.main([__file__, "-q"]))
