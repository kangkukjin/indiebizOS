"""도구 함정 3건 (2026-09-06, ep2890 부동산 발굴 보고서 30호 자기 점검).

① `[sense:realty]{op:"codes", city:"충청북도"}` — 카탈로그 키가 축약형(충북)뿐이라 정식 도명이 거절됐다.
② `[self:script]{op:"run", args:{src:"~workspace/…"}}` — 러너가 stdin args 의 몸 토큰을 펼치지 않아
   스크립트가 "<repo>/~workspace/…" 를 열었다. 해소는 토큰을 아는 러너 경계 한 곳.
③ 네이버 검색 `count:10` 0건 — 파라미터 이름(count 는 limit 별칭) 탓이 아니라 낱말 5개 AND 질의였다.
   봉투가 그 뿌리를 말해야 다음 화자가 파라미터를 의심하지 않는다.

실행: .venv/bin/python -m pytest -q backend/test_tool_traps_2026_09_06.py
"""
import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "data", "packages", "installed", "tools")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_TOOLS, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── ① 정식 행정구역명 ──────────────────────────────────────────────
RC = _load("_t_traps_region_codes", "real-estate/tool_region_codes.py")


@pytest.mark.parametrize("given,key", [
    ("충청북도", "충북"), ("충청남도", "충남"), ("전라남도", "전남"), ("경상북도", "경북"),
    ("강원특별자치도", "강원"), ("전북특별자치도", "전북"), ("제주특별자치도", "제주"),
    ("세종특별자치시", "세종"), ("부산광역시", "부산"), ("서울특별시", "서울"), ("충북", "충북"),
])
def test_official_region_names_resolve_to_catalog_key(given, key):
    assert RC._normalize_region_name(given) == key
    out = RC.get_region_codes(given)
    assert out.get("success") is True and out.get("city") == key, out


def test_suffix_strip_is_at_end_only():
    # 옛 replace("시", "") 는 낱말 속 글자까지 지웠다 — '시흥시' 는 '시흥' 이어야 한다
    assert RC._normalize_region_name("시흥시") == "시흥"


# ── ② 러너의 ~workspace 펼침 ────────────────────────────────────────
SO = _load("_t_traps_script_ops", "system_essentials/script_ops.py")


def test_run_args_expand_workspace_token_recursively():
    from runtime_utils import get_base_path
    base = str(get_base_path())
    out = SO._expand_args_body_paths({
        "src": "~workspace/outputs/r.md",
        "dst": "~workspace/공유창고/0/x.html",
        "drop_lines": ["탐색 조건:", "~workspace/keep"],
        "nested": {"p": "~workspace"},
        "home": "~/y", "lookalike": "~workspacey", "n": 3, "flag": True,
    })
    assert out["src"] == os.path.join(base, "outputs", "r.md")
    assert out["dst"].startswith(base) and "~workspace" not in out["dst"]
    assert out["drop_lines"] == ["탐색 조건:", os.path.join(base, "keep")]
    assert out["nested"]["p"] == base
    assert out["home"] == "~/y" and out["lookalike"] == "~workspacey"     # 남의 몫·닮은 글자는 불변
    assert out["n"] == 3 and out["flag"] is True
    assert SO._expand_args_body_paths(None) is None


# ── ③ 네이버 0건의 말하는 빈손 ─────────────────────────────────────
NV = _load("_t_traps_naver", "web/tool_naver_search.py")


def _stub_naver(monkeypatch, payload):
    monkeypatch.setattr(NV, "check_api_key", lambda *_a, **_k: (True, None))
    monkeypatch.setattr(NV, "api_call", lambda *_a, **_k: payload)


def test_zero_rows_from_many_words_says_why(monkeypatch):
    _stub_naver(monkeypatch, {"total": 0, "items": []})
    out = NV.search_naver("충주 개발 호암지구 서충주신도시 2026", type="news", display=10)
    assert out["success"] is True and out["items"] == []
    assert "낱말 5개" in out["note"] and "전부 포함" in out["note"]


def test_zero_rows_from_short_query_has_no_note(monkeypatch):
    _stub_naver(monkeypatch, {"total": 0, "items": []})
    out = NV.search_naver("충주 호암지구", type="news", display=5)
    assert out["items"] == [] and "note" not in out


def test_nonempty_result_has_no_note(monkeypatch):
    _stub_naver(monkeypatch, {"total": 72, "items": [{"title": "t", "link": "https://n.example/1", "description": "d"}]})
    out = NV.search_naver("충주 개발 호암지구 서충주신도시", type="news", display=5)
    assert len(out["items"]) == 1 and "note" not in out


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
