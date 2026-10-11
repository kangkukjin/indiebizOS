"""긴문장 53회차(법률상담 준비철) 수리 회귀 — L53-1 검색 행의 상세 조회 번호, L53-2 못 찾음·0건의 모양,
L53-3 이름에 없으면 본문 검색, L53-4 법령 상세의 조 단위 행, L53-5 응답에서 사용자 식별값 제거,
L53-6 table:ai 결과 행의 입력 칸 정적 타입, 그리고 폴더 만들기·지우기·복사의 쓰기 자원 선언."""
import importlib.util
import json
import types
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parent.parent
KEY = "secret-user-id"


def _link(target, tail):
    return f"/DRF/lawService.do?OC={KEY}&target={target}&{tail}&type=HTML"


LAW_ROWS = [{"법령일련번호": "188376", "법령ID": "011300", "법령명한글": "난민법", "법령구분명": "법률", "시행일자": "20161220",
             "법령상세링크": _link("law", "MST=188376")},
            {"법령일련번호": "284415", "법령ID": "001706", "법령명한글": "민법", "법령구분명": "법률", "시행일자": "20260317",
             "법령상세링크": _link("law", "MST=284415")}]
LAW_DETAIL = {"법령": {"기본정보": {"법령명_한글": "민법", "법령ID": "001706", "시행일자": "20260317", "공포일자": "20260317",
                                "법종구분": {"content": "법률"}, "제개정구분": "일부개정"},
                     "부칙": {"부칙단위": []},
                     "조문": {"조문단위": [
                         {"조문여부": "전문", "조문번호": "162", "조문내용": "        제7장 소멸시효"},
                         {"조문여부": "조문", "조문번호": "162", "조문제목": "채권, 재산권의 소멸시효", "조문시행일자": "20260317",
                          "조문내용": "제162조(채권, 재산권의 소멸시효)",
                          "항": [{"항번호": "①", "항내용": "①채권은 10년간 행사하지 아니하면 소멸시효가 완성한다."},
                                {"항번호": "②", "항내용": "②채권 및 소유권 이외의 재산권은 20년간 행사하지 아니하면 소멸시효가 완성한다."}]},
                         {"조문여부": "조문", "조문번호": "163", "조문가지번호": "2", "조문제목": "가지 조문",
                          "조문내용": "제163조의2(가지 조문) 다음 각 호와 같다.",
                          "항": {"호": [{"호번호": "1.", "호내용": "1. 첫째", "목": {"목내용": ["가. 하나", "나. 둘"]}},
                                       {"호번호": "2.", "호내용": "2. 둘째"}]}}]}}}
PREC_ROW = {"판례일련번호": "605077", "사건명": "차임증액", "사건번호": "2024다315046", "법원명": "대법원", "선고일자": "2025.03.13",
            "판례상세링크": _link("prec", "ID=605077")}
PREC_DETAIL = {"PrecService": {"사건명": "차임증액", "사건번호": "2024다315046", "법원명": "대법원", "선고일자": "20250313",
                               "판시사항": "묵시적 이의의 요건<br/>", "참조조문": "민법 제628조, 제639조 제1항<br/>",
                               "판례내용": f"【주문】<br/>파기환송 <a href='{_link('prec', 'ID=1')}'>참조</a>"}}


@pytest.fixture()
def legal(monkeypatch):
    spec = importlib.util.spec_from_file_location("ls53_legal", ROOT / "data/packages/installed/tools/legal/handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def fake(service, endpoint, params=None, raw_response=False):
        calls.append((endpoint, dict(params)))
        target, body = params["target"], None
        if endpoint == "/lawSearch.do":
            q, in_body = params["query"], params.get("search") == 2
            if target == "law":
                rows = LAW_ROWS if q == "민법" and not in_body else []
                body = {"LawSearch": {"law": rows, "totalCnt": str(len(rows)), "section": "bdyText" if in_body else "lawNm"}}
            elif target == "prec":
                rows = [PREC_ROW] * 20 if (q == "차임" and not in_body) or (q == "갱신 이의" and in_body) else []
                total = 1382 if q == "차임" else len(rows)
                body = {"PrecSearch": {**({"prec": rows} if rows else {}), "totalCnt": str(total), "section": "bdyText" if in_body else "evtNm"}}
            elif target == "expc":      # 해석례의 래퍼 이름은 Search 로 끝나지 않는다
                body = {"Expc": {"expc": [{"법령해석례일련번호": "339999", "안건명": "재계약에 적용되는 법률", "회신일자": "2024.09.23"}],
                                 "totalCnt": "1", "section": "itmNm", "resultMsg": "success"}}
            else:
                return ""               # 원천이 모르는 target 이름에는 빈 응답을 준다
        else:
            if target == "law":
                hit = params.get("ID") == "001706" or params.get("MST") == "284415"
                body = LAW_DETAIL if hit else {"Law": "일치하는 법령이 없습니다.  법령명을 확인하여 주십시오."}
            elif target == "prec":
                body = PREC_DETAIL if params.get("ID") == "605077" else {"Law": "일치하는 판례가 없습니다.  판례명을 확인하여 주십시오."}
        return json.dumps(body, ensure_ascii=False)

    monkeypatch.setattr(module, "api_call", fake)
    monkeypatch.setattr(module, "get_api_key", lambda *a, **k: KEY)

    def run(**args):
        out = module.execute(args, types.SimpleNamespace(tool_name="legal_lookup"))
        out = json.loads(out) if isinstance(out, str) else out
        assert KEY not in json.dumps(out, ensure_ascii=False)       # L53-5: 어떤 응답에도 식별값이 없다
        return out
    run.calls = calls
    return run


def test_search_rows_carry_the_id_that_detail_accepts(legal):
    found = legal(query="민법")
    assert found["count"] == 2 and found["total"] == 2 and found["search_scope"] == "name"
    row = next(r for r in found["items"] if r["title"] == "민법")
    assert row["id"] == "001706" and row["url"] == "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=284415"
    assert "OC=&" in found["message"]                                # 원문은 남기되 값만 지운다
    detail = legal(id=row["id"])
    assert detail["success"] and detail["law"] == {
        "name": "민법", "id": "001706", "enforce_date": "2026-03-17", "promulgation_date": "2026-03-17",
        "revision": "일부개정", "kind": "법률", "url": "https://www.law.go.kr/LSW/lsInfoP.do?lsId=001706"}
    assert "조문" in detail["법령"] and "부칙" in detail["법령"]         # 원천 구조는 그대로 둔다(기존 프로그램 보존)


def test_law_detail_is_one_row_per_article(legal):
    items = legal(id="001706")["items"]
    assert [a["no"] for a in items] == ["제162조", "제163조의2"]
    first, second = items
    assert first["title"] == "제162조(채권, 재산권의 소멸시효)" and first["chapter"] == "제7장 소멸시효"
    assert first["date"] == "2026-03-17" and first["meta"] == "민법"
    assert first["text"] == ("제162조(채권, 재산권의 소멸시효)\n①채권은 10년간 행사하지 아니하면 소멸시효가 완성한다.\n"
                             "②채권 및 소유권 이외의 재산권은 20년간 행사하지 아니하면 소멸시효가 완성한다.")
    # 하나뿐인 항·목은 목록이 아니라 객체로 온다
    assert second["text"] == "제163조의2(가지 조문) 다음 각 호와 같다.\n1. 첫째\n가. 하나\n나. 둘\n2. 둘째"


def test_law_serial_number_from_the_link_also_resolves(legal):
    assert legal(id="284415")["law"]["name"] == "민법"
    assert [p for e, p in legal.calls if e == "/lawService.do"][-2:] == [
        {"OC": KEY, "target": "law", "type": "JSON", "ID": "284415"}, {"OC": KEY, "target": "law", "type": "JSON", "MST": "284415"}]


@pytest.mark.parametrize("target", ["law", "prec"])
def test_unknown_id_is_a_failure_not_a_success_envelope(legal, target):
    out = legal(id="99999999", target=target)
    assert out["success"] is False and out["error_code"] == "NOT_FOUND"
    assert "일치하는" in out["error"] and "99999999" in out["error"]


def test_zero_hits_are_an_empty_list_after_trying_the_body(legal):
    out = legal(query="없는법이름특별법")
    assert out["success"] and out["items"] == [] and out["count"] == 0 and out["total"] == 0
    assert out["search_scope"] == "name+body"
    assert [p.get("search") for e, p in legal.calls] == [None, 2]


def test_precedent_search_falls_back_to_body_and_says_so(legal):
    by_name = legal(query="차임", target="prec")
    assert by_name["search_scope"] == "name" and by_name["total"] == 1382 and by_name["count"] == 20
    assert "truncated" not in by_name          # 첫 쪽은 절단이 아니다 — 절단 표지는 실행기가 결과를 거절하게 만든다
    assert "1382" in by_name["note"]
    by_body = legal(query="갱신 이의", target="prec")
    assert by_body["search_scope"] == "body" and "본문" in by_body["note"] and by_body["count"] == 20
    row = by_body["items"][0]
    assert row["id"] == "605077" and row["case_no"] == "2024다315046" and row["date"] == "2025-03-13"
    assert row["url"] == "https://www.law.go.kr/LSW/precInfoP.do?precSeq=605077"
    one = legal(id=row["id"], target="prec")["items"]
    assert len(one) == 1 and one[0]["summary"] == "묵시적 이의의 요건" and one[0]["참조조문"] == "민법 제628조, 제639조 제1항"
    assert one[0]["판례내용"].startswith("【주문】\n파기환송") and one[0]["case_no"] == "2024다315046"


def test_vocabulary_target_names_reach_the_source_names(legal):
    out = legal(query="임대차", target="exp")
    assert out["count"] == 1 and out["items"][0]["id"] == "339999" and out["items"][0]["title"] == "재계약에 적용되는 법률"
    assert legal.calls[-1][1]["target"] == "expc"
    assert legal(id="1", target="law_form")["error_code"] == "UNSUPPORTED_OPERATION"


def _issue_codes(code):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    return [issue["code"] for issue in compile_program(code, load_registry(), {}).report()["issues"]]


def test_ai_result_rows_keep_input_fields_in_the_static_type():
    ask = '>> [table:ai]{instruction:"요약",schema:"note(문자열), n(숫자)",preserve_rows:true}'   # 칸 둘 — 하나뿐이면 자유 라벨이라 행 타입을 만들지 않는다
    # 반환 경로마다 모양이 다른 함수의 결과(= 닫힌 Record 하나로 확정되지 않는 입력)
    varied = ('[def:읽기]($n){ [if:$n > 1] { return {id:"a",text:"t",ok:true} } return {id:"b",text:"",reason:"x"} }\n'
              '$rows = [1,2] >> [table:each] { [fn:읽기]{n:$it} }\n')
    assert "MISSING_FIELD" not in _issue_codes(varied + f'$a = $rows {ask}\nreturn [$a.items[0].id,$a.items[0].note]')
    # 입력 모양이 확정이면 여전히 닫힌 행 — 없는 칸은 잡는다
    exact = f'$a = [{{id:"a",text:"t"}}] {ask}\n'
    assert "MISSING_FIELD" not in _issue_codes(exact + 'return [$a.items[0].id,$a.items[0].note]')
    assert "MISSING_FIELD" in _issue_codes(exact + 'return $a.items[0].nope')
    # 행을 받지 않는 추출(self:struct)은 schema 칸만 가진 닫힌 행 그대로
    assert "MISSING_FIELD" in _issue_codes('$r=[self:struct]{text:"x",schema:"a(설명), b(설명)"};return $r.items[0].typo')


@pytest.mark.parametrize("action,param", [("self:mkdir", "path"), ("self:delete", "path"), ("self:copy", "dest")])
def test_file_writers_declare_their_write_resource(action, param):
    from ibl_v2_adapters import load_registry
    assert load_registry()[action].contract.get("write_resources") == {"file": param}


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
