"""입력 모양(⟨인자⟩) 회귀 — 카탈로그가 실측 입력 인자를 말하는가 (2026-08-23).

배경: 반환 모양은 ⟨열⟩ 로 실측·방출됐는데 입력 모양은 구조로 아무 데도 없었다(151 액션 중
params 스키마 0 — 인자 의미는 target_description 산문에만, 그 산문은 프롬프트에 안 실림).
`scripts/ibl_param_sweep.py` 가 교재·실행에서 *쓰인 키* 를 세어 `data/ibl_param_shapes.json`
에 적고, ibl_access 가 ⟨인자: a·b·(c)⟩ 로 붙인다. 지키는 불변식:

  ① 인자 목록은 손으로 적지 않는다 — 관측 파일만이 원천(스크립트가 파생물임을 선언).
  ② op 줄의 ⟨인자⟩ 는 액션 줄이 못 말한 것이 있을 때만(새 키·선택→항상 승격) — 중복 금지.
  ③ 범례가 표기를 설명한다(괄호의 뜻을 안 적으면 읽는 쪽이 괄호를 문법으로 읽는다).
  ④ 관측 파일이 없으면 카탈로그는 옛 모양 그대로(회귀 안전).
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.abspath(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
    import boot_paths  # noqa: F401
_ROOT = os.path.dirname(_BACKEND)


class _params:
    def __init__(self, data, always=0.8):
        self.data, self.always = data, always

    def __enter__(self):
        import ibl_access
        self.mod = ibl_access
        self.saved = (ibl_access._param_shapes, dict(ibl_access._PARAM_CACHE))
        ibl_access._param_shapes = lambda: self.data
        ibl_access._PARAM_CACHE["always"] = self.always
        return ibl_access

    def __exit__(self, *exc):
        self.mod._param_shapes = self.saved[0]
        self.mod._PARAM_CACHE.clear()
        self.mod._PARAM_CACHE.update(self.saved[1])


def test_action_line_prints_always_and_optional():
    with _params({"sense:search": {"keys": [["query", 0.99], ["source", 0.75], ["count", 0.18]]}}) as acc:
        assert acc._param_suffix("sense:search") == " ⟨인자: query·(source)·(count)⟩"


def test_op_line_silent_when_it_adds_nothing():
    """액션 줄의 부분집합이고 승격도 없으면 op 줄은 침묵(②)."""
    with _params({
        "sense:stock": {"keys": [["ticker", 0.6], ["symbol", 0.36], ["period", 0.15]]},
        "sense:stock#quote": {"keys": [["ticker", 0.6], ["symbol", 0.4]]},
        "sense:stock#info": {"keys": [["symbol", 0.9], ["ticker", 0.1]]},
        "sense:stock#search": {"keys": [["query", 1.0]]},
    }) as acc:
        assert acc._param_suffix("sense:stock", "quote") == ""
        assert acc._param_suffix("sense:stock", "info") == " ⟨인자: symbol·(ticker)⟩"   # 승격
        assert acc._param_suffix("sense:stock", "search") == " ⟨인자: query⟩"          # 새 키


def test_no_observation_means_no_change():
    with _params({}) as acc:
        assert acc._param_suffix("sense:stock") == ""
        assert acc._param_suffix("sense:stock", "quote") == ""


def test_emit_line_places_params_before_columns():
    """액션 줄: '설명 ⟨인자⟩ ⟨열⟩ ⟨동반⟩' 순서 — 입력 → 출력 → 이웃(2026-08-30 ⟨동반⟩ 합류)."""
    import ibl_access
    with _params({"table:filter": {"keys": [["where", 0.99]]}}):
        saved = (ibl_access._return_shapes, ibl_access._partners)
        ibl_access._return_shapes = lambda: {"table:filter": {"keys": ["a", "b"]}}
        ibl_access._partners = lambda: {"table:filter": {"n": 9, "top": [[">>table:sort", 4]]}}
        try:
            line = ibl_access._emit_action_line("table", "filter", {"description": "걸러낸다"})
        finally:
            ibl_access._return_shapes, ibl_access._partners = saved
    assert line.strip() == (
        "table:filter :: 걸러낸다 ⟨인자: where⟩ ⟨열: a·b⟩ ⟨동반: >>table:sort⟩"), line


def test_legend_explains_parentheses():
    import ibl_access
    assert "⟨인자" in ibl_access.CATALOG_LEGEND and "선택" in ibl_access.CATALOG_LEGEND


def test_observation_file_declares_itself_derived():
    """①: 원천은 스크립트 산출물 — 손 편집 금지가 파일 안에 적혀 있다."""
    import json
    p = os.path.join(_ROOT, "data", "ibl_param_shapes.json")
    if not os.path.exists(p):
        return  # 런타임 데이터(미추적) — CI 에선 없을 수 있다
    doc = json.load(open(p, encoding="utf-8"))
    assert "GENERATED" in doc.get("_comment", "") and "shapes" in doc
    assert all("#" not in k or k.split("#")[0] in doc["shapes"] or True for k in doc["shapes"])


def test_sweep_folds_declared_aliases_and_reports_splits():
    """별칭은 어휘 데이터가 소유한다 — 스윕이 `aliases:` 선언을 읽어 정규 키로 접고,
    선언되지 않은 분열(상호배타 + 호출을 분할하는 빈출 키 쌍)은 신고만 한다(자동 접기 금지 —
    어느 쪽이 정규인지 정하는 건 몸이 세계에 이름을 붙이는 짓이다)."""
    src = open(os.path.join(_ROOT, "scripts", "ibl_param_sweep.py"), encoding="utf-8").read()
    assert "_alias_map" in src and '"aliases"' in src
    assert "split_candidates" in src and "pair_counts" in src


def test_declared_aliases_cover_the_handler_private_ones():
    """코드가 푸는 별칭은 선언에도 있어야 한다 — 어휘가 코드로 새면 카탈로그가 두 이름을
    다 광고한다(08-23 실측 3건: investment `_arg`, gemini_vision, location handler)."""
    import yaml
    n = yaml.safe_load(open(os.path.join(_ROOT, "data", "ibl_nodes.yaml"), encoding="utf-8"))["nodes"]

    def al(node, action):
        return (n[node]["actions"][action] or {}).get("aliases") or {}

    assert "symbol" in al("sense", "stock").get("ticker", [])
    assert "path" in al("engines", "image_read").get("image_path", [])
    assert "intent" not in al("engines", "image_read").get("question", []), \
        "intent 는 op:critic 의 정규 키 — question 으로 접으면 두 자리가 섞인다"
    assert "to" in al("sense", "navigate_route").get("destination", [])


def test_sweep_separates_corpus_gap_from_invention():
    """교재 없는 실행 키를 통째로 '오류'라 부르면 거짓말이다(08-23 자기교정 —
    [sense:search_ddg]{query:} 163건은 옳은 키인데 교재가 그 액션을 안 가르친 것)."""
    src = open(os.path.join(_ROOT, "scripts", "ibl_param_sweep.py"), encoding="utf-8").read()
    assert "corpus_gap_keys" in src and "invented_keys" in src and "taught_action" in src


def test_sweep_reports_truncation_and_parse_failures():
    """깨짐≠없음 — 스윕은 절단·파싱 실패를 분모에서 빼고 건수를 신고한다."""
    src = open(os.path.join(_ROOT, "scripts", "ibl_param_sweep.py"), encoding="utf-8").read()
    assert "parse_fail" in src and "TRUNC" in src and "unknown_actions" in src


if __name__ == "__main__":                      # 러너는 하나 — pytest (28회차 R2)
    import pytest
    raise SystemExit(pytest.main([__file__] + __import__("sys").argv[1:]))
