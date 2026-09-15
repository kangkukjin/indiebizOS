"""정적 통화 검사(ibl_typecheck) 회귀 — docs/IBL_STATIC_TYPECHECK_HANDOFF.md (2026-09-05).

계약:
  T1  낱말: returns 선언 + fixture 실측 카탈로그로 items⟨열⟩ · scalar · effect 를 안다.
  T2  흐름: keep(filter/sort/take) · subset(select=확정 열) · add(compute) · reset(groupby) 가 열을 옮긴다.
  T3  union: prose 가지 = error, scalar 가지 = warning(승격 가능 — 데이터 의존이라 확답 불가), effect 가지 = 통과(1행 규약).
  T4  join/merge: prose·effect 가지와 확정된 단일 표 입력 = error, 미상 입력은 기권.
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


@pytest.fixture(autouse=True)
def _fixed_catalog(monkeypatch):
    """열 카탈로그(data/ibl_return_shapes.json)는 gitignore 된 로컬 관측 파일 — CI 에는 없다. 시험은 고정 카탈로그로 돈다."""
    import ibl_access
    cat = {"sense:search": {"kind": "items", "keys": ["title", "meta", "summary", "url"]},
           "sense:crawl": {"kind": "items", "keys": ["type", "text"]}}
    monkeypatch.setattr(ibl_access, "_return_shapes", lambda: cat)


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
    assert not _tc(SEARCH + ' >> [table:join]{on: "title"}')["ok"]


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


@pytest.mark.parametrize('items,mapping,reason', [
    ('[{other:1}]', '{파일:"file",path:"file"}', '후보'),
    ('[{파일:"a",path:"b"}]', '{파일:"file",path:"file"}', '함께 접힙니다'),
    ('[{파일:"a"},{path:"b"}]', '{파일:"file",path:"file"}', '함께 접힙니다'),
    ('[{파일:"a",file:"b"}]', '{파일:"file",path:"file"}', '기존 열'),
    ('[{파일:"a"}]', '{missing:"file"}', 'missing'),
])
@pytest.mark.parametrize('direct', [False, True])
def test_rename_closed_columns_reject_missing_candidates_and_collisions(items, mapping, reason, direct):
    code = (f'[table:rename]{{items:{items},map:{mapping}}}' if direct else
            f'{items} >> [table:rename]{{map:{mapping}}}')
    r = _tc(code)
    assert not r['ok'] and len(_errors(r)) == 1, r
    assert reason in _errors(r)[0]['message'], r


@pytest.mark.parametrize('mapping,warn', [
    ('{title:"name",headline:"name"}', False),
    ('{missing:"name",headline:"name"}', True),
    ('{title:"name",url:"name"}', True),
    ('{title:"url",headline:"url"}', True),
])
def test_rename_observed_columns_never_become_certain_errors(mapping, warn):
    r = _tc(SEARCH + f' >> [table:rename]{{map:{mapping}}}')
    assert r['ok'] and not _errors(r), r
    assert bool(_warnings(r)) == warn, r


@pytest.mark.parametrize('code', [
    '[self:read]{path:"unknown.json"} >> [table:rename]{map:{a:"out",b:"out"}}',
    '$mapping=[self:read]{path:"map.json"}; [{a:1}] >> [table:rename]{map:$mapping}',
    '$name="out"; [{a:1}] >> [table:rename]{map:{a:$name,b:$name}}',
])
def test_rename_unknown_input_or_dynamic_map_defers_to_execution(code):
    r = _tc(code)
    assert r['ok'] and not r['issues'] and not r.get('abstained'), r


def test_rename_output_columns_still_catch_downstream_typo():
    code = '[{파일:"a"}] >> [table:rename]{map:{파일:"file",path:"file"}}'
    r = _tc(code)
    assert r['ok'] and not r['issues'] and r['types'] == ['(1) items⟨file⟩'], r
    r = _tc(code + ' >> [table:select]{columns:["path"]}')
    assert not r['ok'] and all(i['at'] == 'table:select' for i in _errors(r)), r


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ── 2026-09-16 ep3816: 관측 열 경고의 중복 신고·columns_from 낱말의 op 별 fixture 열·경고의 봉투 탑승 ──
def test_observed_column_warning_is_reported_once_and_script_list_columns_are_known(monkeypatch):
    import ibl_access
    cat = dict(ibl_access._return_shapes())
    cat["sense:video"] = {"kind": "items", "keys": ["title", "duration", "uploader", "view_count", "upload_date", "video_id", "url"]}
    cat["sense:search_youtube"] = {"kind": "items", "keys": ["index", "id", "title", "channel", "duration", "url"]}
    cat["self:script"] = {"kind": "items", "keys": ["title", "meta", "summary", "registered_at", "last_status"]}
    cat["self:script#list"] = cat["self:script"]
    monkeypatch.setattr(ibl_access, "_return_shapes", lambda: cat)
    prog = ('$후보 = [sense:search_youtube]{queries:["a"], count:12} >> [table:dedup]{by:"video_id"} '
            '>> [table:rename]{map:{video_id:"id"}}\n'
            '$날짜 = $후보 >> [table:each]{limit:80, do:"[sense:video]{op:\\"info\\", video_id:$it.id}"}\n'
            '$날짜 >> [table:select]{fields:["id","title"]}')
    issues = TC.typecheck_code(prog)["issues"]
    hits = [i for i in issues if "'id'" in i["message"]]
    assert len(hits) == 1 and hits[0]["severity"] == "warning"
    # columns_from: data 인 self:script 도 `#list` fixture 가 관측한 열은 안다(run 은 여전히 미상)
    assert TC._catalog_cols("self", "script", {"op": "list"})[:3] == ["title", "meta", "summary"]
    assert TC._catalog_cols("self", "script", {"op": "run", "id": "x"}) is None
    r = TC.typecheck_code('[self:script]{op:"list"} >> [table:filter]{where:"id contains 보고서"}')
    assert any(i["severity"] == "warning" and "'id'" in i["message"] for i in r["issues"])


def test_precheck_warnings_ride_the_execution_envelope():
    from system_tools_ibl import _attach_precheck
    tc = {"ok": True, "issues": [{"severity": "warning", "statement": 3, "step": 7, "at": "table:select",
                                  "message": "'id' 은(는) 관측된 열에 없습니다", "hint": "columns 를 보라"},
                                 {"severity": "error", "message": "x"}]}
    ok = {"success": True}
    _attach_precheck(ok, tc)
    assert ok["precheck_warnings"] == [{"statement": 3, "step": 7, "at": "table:select",
                                        "message": "'id' 은(는) 관측된 열에 없습니다", "hint": "columns 를 보라"}]
    assert "precheck_note" not in ok
    failed = {"success": False, "error": "Step 7 에러"}
    _attach_precheck(failed, tc)
    assert failed["precheck_warnings"] and "precheck_note" in failed
    clean = {"success": True}
    _attach_precheck(clean, {"ok": True, "issues": []})
    assert "precheck_warnings" not in clean
