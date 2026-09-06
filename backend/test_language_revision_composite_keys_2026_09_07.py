"""키 자리 = 속성 집합 — 언어 개정 2026-09-07 (사용자 판정 "키 자리 전체 개정").

규칙: 관계대수의 키 자리(γ groupby.by · τ sort.by · δ dedup.by · ⋈ join.on · merge.by)는
스칼라 하나가 아니라 **속성 집합**을 받는다. 목록이 오면 복합키(교차집계·다단계 정렬·
복합 조인키)이지 "항목마다 실행"이 아니다.

죽었던 자리: ep2951(09-07 부동산 보고서) 라운드 27
    $유형별 = $내포실 >> [table:groupby]{by: ["아파트명", "계약유형"], agg: {…}}
    → data_groupby: `by` 에는 string 이 와야 하는데 2개짜리 목록이 왔습니다.
      목록의 항목마다 실행하려면 [table:each]{…}
관문 자체는 정직했지만 처방이 틀렸다 — each 로 돌리면 키마다 따로 그룹핑돼 의도와 다른
답이 success 로 나갔을 자리다. 실행자는 유형마다 filter 를 따로 도는 우회로 갔다(문장 수
= 출력 토큰 = 보고서 시간). 같은 거절이 ep2532(09-01)에도 있었다 — 같은 정기 작업 2/2.

실행: .venv/bin/python -m pytest -q backend/test_language_revision_composite_keys_2026_09_07.py
"""
import importlib.util
import json
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PKG = _ROOT / "data" / "packages" / "installed" / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load("_t_composite_keys_dataops", os.path.join(_PKG, "data-ops", "handler.py"))

# ep2951 이 세우려던 표 그대로 — 단지 × 계약유형
ROWS = [
    {"아파트명": "내포롯데캐슬", "계약유형": "전세", "보증금만원": 20000, "전용면적": 84.9},
    {"아파트명": "내포롯데캐슬", "계약유형": "전세", "보증금만원": 24000, "전용면적": 84.9},
    {"아파트명": "내포롯데캐슬", "계약유형": "매매", "보증금만원": 33000, "전용면적": 84.9},
    {"아파트명": "내포신도시e편한세상", "계약유형": "전세", "보증금만원": 21000, "전용면적": 76.5},
]
ITEMS = {"success": True, "items": ROWS}


# ── γ groupby — 교차집계 ────────────────────────────────────────────────
def test_groupby_composite_key_is_one_sentence():
    r = H._op_groupby(ITEMS, {"by": ["아파트명", "계약유형"],
                              "agg": {"평균보증금": ["avg", "보증금만원"], "건수": ["count", "보증금만원"]}})
    assert r.get("success") is not False, r
    rows = r["items"]
    assert len(rows) == 3, rows                       # 캐슬×전세, 캐슬×매매, e편한세상×전세
    # ★키마다 제 열 — 합성 문자열 한 칸으로 접지 않는다(하류가 다시 쪼개야 하므로)
    first = rows[0]
    assert first["아파트명"] == "내포롯데캐슬" and first["계약유형"] == "전세", first
    assert first["평균보증금"] == 22000 and first["건수"] == 2, first


def test_groupby_composite_result_feeds_downstream_filter():
    """ep2951 의 바로 다음 문장이 성립해야 개정이 값을 한다."""
    g = H._op_groupby(ITEMS, {"by": ["아파트명", "계약유형"], "agg": {"건수": ["count", "보증금만원"]}})
    f = H._op_filter(g, {"where": "계약유형 == '전세'"})
    assert f.get("success") is not False, f
    assert [x["아파트명"] for x in f["items"]] == ["내포롯데캐슬", "내포신도시e편한세상"], f


def test_groupby_single_key_unchanged():
    """단일 키 계약은 그대로 — 개정이 옛 문장의 뜻을 바꾸지 않는다."""
    r = H._op_groupby(ITEMS, {"by": "계약유형"})
    assert [x["계약유형"] for x in r["items"]] == ["전세", "매매"], r


def test_groupby_missing_key_named_honestly():
    r = H._op_groupby(ITEMS, {"by": ["아파트명", "없는열"]})
    assert r.get("success") is False and "없는열" in r["error"], r
    assert "아파트명" not in r["error"].split("사용 가능한 필드")[0], r   # 있는 키를 탓하지 않는다


def test_key_slot_rejects_nonsense_lists():
    for bad, mark in (([], "빈 목록"), (["a", "a"], "두 번"), ([["a"]], "중첩")):
        r = H._op_groupby(ITEMS, {"by": bad})
        assert r.get("success") is False and mark in r["error"], (bad, r)
    # 별칭 `or` 사슬이 빈 목록을 삼켜 형제 동사와 다른 진단을 내던 자리도 함께 고정
    assert "빈 목록" in H._op_sort(ITEMS, {"by": []})["error"]


# ── τ sort — 다단계 정렬 ────────────────────────────────────────────────
def test_sort_composite_key_is_multilevel():
    r = H._op_sort(ITEMS, {"by": ["계약유형", "보증금만원"]})
    got = [(x["계약유형"], x["보증금만원"]) for x in r["items"]]
    assert got == [("매매", 33000), ("전세", 20000), ("전세", 21000), ("전세", 24000)], got


def test_sort_composite_key_desc_applies_to_all():
    r = H._op_sort(ITEMS, {"by": ["계약유형", "보증금만원"], "desc": True})
    got = [(x["계약유형"], x["보증금만원"]) for x in r["items"]]
    assert got == [("전세", 24000), ("전세", 21000), ("전세", 20000), ("매매", 33000)], got


def test_sort_table_currency_keeps_shape():
    t = {"success": True, "table": {"columns": ["a", "b"], "rows": [[2, "x"], [1, "y"], [2, "a"]]}}
    r = H._op_sort(t, {"by": ["a", "b"]})
    assert r["table"]["rows"] == [[1, "y"], [2, "a"], [2, "x"]], r


# ── δ dedup / merge — 복합 중복키 ───────────────────────────────────────
def test_dedup_composite_key():
    r = H._op_dedup(ITEMS, {"by": ["아파트명", "계약유형"]})
    assert len(r["items"]) == 3, r
    # 단일 키였으면 단지 2개로 뭉개진다 — 복합키가 실제로 갈랐는지 확인
    assert len(H._op_dedup(ITEMS, {"by": "아파트명"})["items"]) == 2


def test_dedup_composite_key_with_empty_part_is_kept():
    rows = {"success": True, "items": [{"a": "x", "b": ""}, {"a": "x", "b": ""}]}
    r = H._op_dedup(rows, {"by": ["a", "b"]})
    assert len(r["items"]) == 2, r      # 빈 부분이 있는 행은 중복 판정 밖(단일 키 규약의 확장)


def test_merge_composite_key():
    a = json.dumps({"success": True, "items": [{"n": "A", "t": "전세"}, {"n": "A", "t": "매매"}]}, ensure_ascii=False)
    b = json.dumps({"success": True, "items": [{"n": "A", "t": "전세"}, {"n": "B", "t": "전세"}]}, ensure_ascii=False)
    r = H._op_merge([a, b], {"by": ["n", "t"]})
    assert [(x["n"], x["t"]) for x in r["items"]] == [("A", "전세"), ("A", "매매"), ("B", "전세")], r


# ── ⋈ join — 복합 조인키 ────────────────────────────────────────────────
def test_join_composite_key():
    left = json.dumps({"success": True, "items": [
        {"단지": "A", "유형": "전세", "보증금": 20000},
        {"단지": "A", "유형": "매매", "보증금": 33000}]}, ensure_ascii=False)
    right = json.dumps({"success": True, "items": [
        {"단지": "A", "유형": "전세", "건수": 2},
        {"단지": "A", "유형": "매매", "건수": 1}]}, ensure_ascii=False)
    r = H._op_join([left, right], {"on": ["단지", "유형"]})
    assert r.get("success") is not False, r
    got = [(x["유형"], x["보증금"], x["건수"]) for x in r["items"]]
    assert got == [("전세", 20000, 2), ("매매", 33000, 1)], got   # 단일 키였으면 2×2 로 부풀었다


def test_join_composite_key_table_currency():
    left = json.dumps({"success": True, "table": {
        "columns": ["단지", "유형", "보증금"], "rows": [["A", "전세", 20000], ["A", "매매", 33000]]}}, ensure_ascii=False)
    right = json.dumps({"success": True, "table": {
        "columns": ["단지", "유형", "건수"], "rows": [["A", "전세", 2]]}}, ensure_ascii=False)
    r = H._op_join([left, right], {"on": ["단지", "유형"]})
    assert r["table"]["columns"] == ["단지", "유형", "보증금", "건수"], r
    assert r["table"]["rows"] == [["A", "전세", 20000, 2]], r


def test_join_missing_composite_key_named():
    left = json.dumps({"success": True, "items": [{"a": 1, "b": 2}]}, ensure_ascii=False)
    right = json.dumps({"success": True, "items": [{"a": 1}]}, ensure_ascii=False)
    r = H._op_join([left, right], {"on": ["a", "b"]})
    # 표 경로와 대칭 — 없는 키를 조용히 0행으로 흘리지 않는다(⑧′)
    assert r.get("success") is False and "'b'" in r["error"] and "우측" in r["error"], r


# ── 선언(단일 소스) — 관문이 목록을 통과시키는 근거는 tool.json 이다 ──────
def test_key_slots_declared_as_string_or_array():
    tj = json.loads((_PKG / "data-ops" / "tool.json").read_text(encoding="utf-8"))
    props = {t["name"]: (t.get("input_schema") or {}).get("properties", {}) for t in tj["tools"]}
    for tool, slot in (("data_sort", "by"), ("data_dedup", "by"), ("data_groupby", "by"),
                       ("data_merge", "by"), ("data_join", "on")):
        assert props[tool][slot].get("type") == ["string", "array"], (tool, slot, props[tool].get(slot))
    # ★join 의 target_key 가 YAML 1.1 의 on→True 로 접혀 만들어지던 유령 param
    assert "true" not in props["data_join"], props["data_join"]


def test_gate_lets_composite_key_through():
    """실행 관문(ibl_routing)이 이 자리의 목록을 더는 거절하지 않는다 — 개정의 실제 통로."""
    import sys
    sys.path.insert(0, str(_ROOT / "backend"))
    sys.path.insert(0, str(_ROOT / "backend" / "ibl"))
    import ibl_routing as R
    out = R._route_handler("data_groupby", {"items": ROWS, "by": ["아파트명", "계약유형"]}, str(_ROOT))
    assert "개짜리 목록이 왔습니다" not in (out.get("error") or ""), out
    assert out.get("success") is not False, out


if __name__ == "__main__":                      # 직접 실행도 같은 러너로 — 두 번째 러너는 드리프트한다
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
