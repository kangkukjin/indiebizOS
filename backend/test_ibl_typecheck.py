"""정적 통화 검사(ibl_typecheck) 회귀 — docs/IBL_STATIC_TYPECHECK_HANDOFF.md (2026-09-05).

계약:
  T1  낱말: returns 선언 + fixture 실측 카탈로그로 items⟨열⟩ · scalar · effect 를 안다.
  T2  흐름: keep(filter/sort/take) · subset(select=확정 열) · add(compute) · reset(groupby) 가 열을 옮긴다.
  T3  union: prose 가지 = error, scalar 가지 = warning(승격 가능 — 데이터 의존이라 확답 불가), effect 가지 = 통과(1행 규약).
  T4  join/merge: prose·effect 가지 = error, 병렬 아닌 단일 입력 = 통과(미상).
  T5  변수 경로: prose 에 .items = error · .count = scalar · .message = prose.
  T6  분기 몸에서만 태어난 변수를 밖에서 읽으면 warning(실행의 '아직 값을 기록하지 않았습니다' 를 앞당김).
  T7  함수 반환: 같은 프로그램 [def:] · 등록된 외부 소스(관용구/워크플로) 두 길 모두 `[fn:]` 의 반환을 안다.
  T8  each 의 do 를 재파싱해 방출 열(keep + do 의 열)을 안다.
  T9  ★unknown 은 절대 error 가 아니다 — 모르는 액션·동적 columns·스칼라 생산자(script/read) 뒤 변환자 전부 초록.
  T10 확정 열 밖 참조 = error, 관측(카탈로그) 열 밖 참조 = warning.
  T11 문법 오류는 syntax_error 로, 검사기 예외는 abstained 로 — 어느 쪽도 실행을 죽이지 않는다.
  T12 return_type_of(코드) — 관용구 서명의 반환 낱말.
실 DB·트리 무접촉(사전·카탈로그는 읽기만). 실행: .venv/bin/python -m pytest backend/test_ibl_typecheck.py -q
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

import ibl_typecheck as TC  # noqa: E402

SEARCH = '[sense:search]{query: "x", limit: 3}'


def _tc(code):
    return TC.typecheck_code(code)


def _errors(r):
    return [i for i in r["issues"] if i["severity"] == "error"]


def _warnings(r):
    return [i for i in r["issues"] if i["severity"] == "warning"]


# ---------------------------------------------------------------- T1 낱말
def test_t1_word_types_from_declaration_and_catalog():
    r = _tc(SEARCH)
    assert r["ok"] and r["types"] and r["types"][0].startswith("(1) items⟨")
    assert "title" in r["types"][0]                      # fixture 실측 열
    r2 = _tc('[self:write]{path: "a.md", content: "x"}')
    assert r2["types"] == ["(1) effect"]


# ---------------------------------------------------------------- T2 흐름
def test_t2_flow_keep_subset_add_reset():
    r = _tc(SEARCH + ' >> [table:filter]{where: "title contains AI"} >> [table:take]{n: 2}')
    assert r["ok"] and "title" in r["types"][0]
    r = _tc(SEARCH + ' >> [table:select]{columns: ["title", "url"]}')
    assert r["types"] == ["(1) items⟨title·url⟩"]          # 확정(닫힌) 열 — '·…' 없음
    r = _tc(SEARCH + ' >> [table:select]{columns: ["title", "url"]} >> [table:compute]{set: {"길이": "len(title)"}}')
    assert r["types"] == ["(1) items⟨title·url·길이⟩"]
    r = _tc(SEARCH + ' >> [table:groupby]{by: "title"}')
    assert r["ok"] and r["types"] == ["(1) items⟨열 미상⟩"]


# ---------------------------------------------------------------- T3 union
def test_t3_union_same_kind():
    prose = '$본 = ' + SEARCH + ' >> [table:brief]{instruction: "요약"}\n$본 & ' + SEARCH + ' >> [table:union]'
    r = _tc(prose)
    assert not r["ok"] and any("같은 종류" in e["message"] for e in _errors(r))
    assert _errors(r)[0]["statement"] == 2 and _errors(r)[0]["at"] == "table:union"
    scalar = '[self:time]{} & ' + SEARCH + ' >> [table:union]'
    r = _tc(scalar)
    assert r["ok"] and _warnings(r)                        # 스칼라는 승격 가능 — 경고까지만
    effect = '[self:write]{path: "a.md", content: "x"} & ' + SEARCH + ' >> [table:union]'
    assert _tc(effect)["ok"]


# ---------------------------------------------------------------- T4 join
def test_t4_join_pair():
    r = _tc('($a = ' + SEARCH + ' >> [table:brief]{instruction: "요약"}) & ' + SEARCH + ' >> [table:join]{on: "title"}') \
        if False else _tc('$a = ' + SEARCH + ' >> [table:brief]{instruction: "요약"}\n$a & ' + SEARCH + ' >> [table:join]{on: "title"}')
    assert not r["ok"] and _errors(r)[0]["at"] == "table:join"
    r = _tc('[self:write]{path: "a.md", content: "x"} & ' + SEARCH + ' >> [table:merge]{by: "title"}')
    assert not r["ok"]
    assert _tc(SEARCH + ' >> [table:join]{on: "title"}')["ok"]     # 단일 입력 — 판정 불능(미상) → 통과


# ---------------------------------------------------------------- T5 변수 경로
def test_t5_variable_paths():
    r = _tc('$본 = ' + SEARCH + ' >> [table:brief]{instruction: "요약"}\n$본.items >> [table:take]{n: 1}')
    assert not r["ok"] and ".items" in _errors(r)[0]["message"]
    r = _tc('$r = ' + SEARCH + '\n$n = $r.count\n$r.count >> [table:take]{n: 1}')
    assert "$n: scalar" in r["types"]
    r = _tc('$본 = ' + SEARCH + ' >> [table:brief]{instruction: "요약"}\n$본.message >> [self:write]{path: "a.md"}')
    assert r["ok"]


# ---------------------------------------------------------------- T6 분기 태생 변수
def test_t6_born_in_branch_warning():
    r = _tc('[if: 1 == 1]{ $투자 = ' + SEARCH + ' }\n$투자 & ' + SEARCH + ' >> [table:union]')
    assert r["ok"]
    assert any("분기 몸 안에서만 태어난" in w["message"] and "$투자" in w["at"] for w in _warnings(r))


# ---------------------------------------------------------------- T7 함수 반환
def test_t7_fn_returns_def_and_registered_source(monkeypatch):
    code = ('$r = [fn:모으기]{주제: "AI"}\n$r >> [table:take]{n: 3}\n'
            '[def: 모으기]{\n  [sense:search]{query: "${주제}", limit: 5} >> [table:select]{columns: ["title", "url"]}\n}')
    r = _tc(code)
    assert r["ok"] and r["fn_returns"] == {"모으기": "items⟨title·url⟩"}
    assert r["types"] == ["$r: items⟨title·url⟩", "(2) items⟨title·url⟩"]     # 정의 문장은 types 에도 문장 번호에도 없다
    # 외부 소스(관용구·워크플로)는 등록으로 온다 — 검사기(ibl 층)는 해마(data)를 직접 부르지 않는다
    monkeypatch.setattr(TC, "FN_CODE_SOURCES", [lambda n: '[sense:search]{query: "${q}"} >> [table:brief]{instruction: "요약"}' if n == "요약하기" else None])
    TC._FN_CACHE.clear()
    r = _tc('$s = [fn:요약하기]{q: "x"}\n$s >> [table:take]{n: 1}')
    assert r["fn_returns"] == {"요약하기": "prose"}
    assert not r["ok"] and _errors(r)[0]["at"] == "table:take"


# ---------------------------------------------------------------- T8 each do
def test_t8_each_do_columns():
    r = _tc(SEARCH + ' >> [table:each]{do: "[sense:crawl]{url: \'$it.url\'}", keep: ["title"]} >> [table:select]{columns: ["title", "text"]}')
    assert r["ok"] and r["types"] == ["(1) items⟨title·text⟩"]


# ---------------------------------------------------------------- T9 미상은 초록
def test_t9_unknown_is_never_error():
    for code in ('[self:script]{op: "run", id: "x"} >> [table:take]{n: 3}',
                 '[self:read]{path: "a.json"} >> [table:filter]{where: {cat: "카페"}}',
                 SEARCH + ' >> [table:select]{columns: "$열"}',
                 '[sense:nosuchaction]{} >> [table:take]{n: 1}',
                 '[self:time] & [sense:host]{op: "status"} >> [table:take]{n: 1}',
                 '[table:since]{items: [{"title": "a", "url": "u"}], key: "공지검침"}'):
        r = _tc(code)
        assert r.get("ok", True), (code, r["issues"])


# ---------------------------------------------------------------- T10 열
def test_t10_closed_vs_observed_columns():
    r = _tc(SEARCH + ' >> [table:select]{columns: ["title", "url"]} >> [table:filter]{where: "summary contains AI"}')
    assert not r["ok"] and "summary" in _errors(r)[0]["message"]
    r = _tc(SEARCH + ' >> [table:sort]{by: "views"}')
    assert r["ok"] and any("관측된 열" in w["message"] for w in _warnings(r))


# ---------------------------------------------------------------- T11 정직
def test_t11_syntax_error_and_abstain():
    r = _tc('$없음 >> [table:take]{n: 1}')                      # 미할당 변수 = 파서의 정직 문법 오류
    assert r["ok"] is False and r.get("syntax_error")
    assert TC.typecheck([{"weird": object()}])["ok"] is True     # 검사기 예외/미지 step = 기권


# ---------------------------------------------------------------- T12 서명 반환
def test_t12_return_type_of():
    assert TC.return_type_of('[sense:search]{query: "${질의}"} >> [table:select]{columns: ["title", "url"]}') == "items⟨title·url⟩"
    assert TC.return_type_of('[sense:search]{query: "${질의}"} >> [table:brief]{instruction: "${지시}"}') == "prose"
    assert TC.return_type_of("") == "?"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
