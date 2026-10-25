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




def _errors(r):
    return [i for i in r["issues"] if i["severity"] == "error"]


def _warnings(r):
    return [i for i in r["issues"] if i["severity"] == "warning"]


@pytest.mark.parametrize("fixture", ['[test:jobs]{}', '[test:jobs]', '[test:jobs]{op:"list"}'])
def test_default_fixture_observation_does_not_leak_to_other_ops(monkeypatch, fixture):
    import ibl_access
    from ibl_v2_adapters import observed_result
    from ibl_v2_types import Type
    observed = {"kind": "items", "keys": ["project", "id", "name"]}
    monkeypatch.setattr(ibl_access, "_return_shapes", lambda: {"test:jobs": observed})
    monkeypatch.setattr(TC, "_action_def", lambda *args: {
        "fixture": fixture, "ops": {"default": "list", "values": {"list": "", "start": ""}}})
    assert TC.catalog_entry("test", "jobs", {"op": "list"}) == observed
    assert TC.catalog_entry("test", "jobs", {"op": "start"}) is None
    contract = {"adapter": {"protocol": "legacy-envelope"}}
    result = observed_result("test:jobs", contract, {"op": "start"}, Type("Record"))
    assert result == Type("Record")


# ---------------------------------------------------------------- T1 낱말


# ---------------------------------------------------------------- T2 흐름


# ---------------------------------------------------------------- T3 union


# ---------------------------------------------------------------- T4 join


# ---------------------------------------------------------------- T5 변수 경로


# ---------------------------------------------------------------- T6 분기 태생 변수


# ---------------------------------------------------------------- T7 함수 반환


# ---------------------------------------------------------------- T8 each do


# ---------------------------------------------------------------- T9 미상은 초록




# ---------------------------------------------------------------- T10 열


# ---------------------------------------------------------------- T11 정직


# ---------------------------------------------------------------- T12 서명 반환










if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ── 2026-09-16 ep3816: 관측 열 경고의 중복 신고·columns_from 낱말의 op 별 fixture 열·경고의 봉투 탑승 ──
