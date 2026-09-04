"""봉투 규모 불변식 회귀 (2026-09-04, ep2814 실측).

재현한 결함: `[sense:search]{source:"naver"} >> [table:take]{n: 8}` 가 5건을 내고도 봉투에
`truncated: true` + "부분 실패·절단" 경고를 달았다. data-ops `_restate_scope` 는 정의대로
`total > len(items)` 면 truncated 를 켜는데, 네이버 봉투의 `total` 은 모집단이 아니라 제공자
추정치(18,804,311)였다 — 검색 뒤에 table 낱말이 붙기만 하면 매번 거짓 절단 경고(한 턴 3/9).

고정하는 계약:
  S1  `ibl_honesty.scope_violation` — items 통화에서 total>items 인데 truncated 침묵이면 위반.
      추정치를 `total_estimate` 로 내면 위반이 아니고, 스스로 truncated 를 켜도 위반이 아니다.
  S2  data-ops `_restate_scope` 는 `total_estimate` 를 보고 truncated 를 켜지 않는다(정의 밖의 수).
  S3  최외곽 관문(ibl_engine.execute_ibl)이 위반을 이름 붙여 신고한다 — 원천이 어디든 한 자리.
  S4  네이버 검색 봉투는 `total` 이 아니라 `total_estimate` 를 낸다(원천 명사 수리).

실행: .venv/bin/python -m pytest backend/test_envelope_scope_invariant.py -q
"""
import json
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

PKG = os.path.join(os.path.dirname(BACKEND), "data", "packages", "installed", "tools")


def test_s1_violation_shapes():
    from ibl_honesty import scope_violation, SCOPE_ESTIMATE_KEY
    assert scope_violation({"items": [1, 2], "total": 5}) is not None            # 침묵 표본
    assert scope_violation({"items": [1, 2], "total": 5, "truncated": True}) is None
    assert scope_violation({"items": [1, 2], "total": 2}) is None
    assert scope_violation({"items": [1, 2], SCOPE_ESTIMATE_KEY: 18804311}) is None
    assert scope_violation({"items": [1, 2], "total": True}) is None             # bool 은 수가 아니다
    assert scope_violation({"count": 3, "total": 9}) is None                     # items 통화가 아니면 대상 아님
    assert scope_violation(json.dumps({"items": [], "total": 3})) is not None    # 문자열 봉투도 푼다
    assert scope_violation("평문") is None


def test_s2_restate_scope_ignores_estimate():
    sys.path.insert(0, os.path.join(PKG, "data-ops"))
    import envelope_scope as es
    env = es._restate_scope({"items": [1, 2, 3], "total_estimate": 18804311}, 5, 3)
    assert "truncated" not in env
    env2 = es._restate_scope({"items": [1], "total": 29}, 29, 1)
    assert env2["truncated"] is True                                             # 정의대로 표본은 켠다


def test_s3_outer_gate_reports_violation(monkeypatch, capsys):
    import ibl_engine as eng
    monkeypatch.setattr(eng, "_execute_ibl_impl",
                        lambda ti, pp, aid: {"success": True, "items": [1], "total": 7})
    eng.execute_ibl({"_node": "sense", "action": "probe"}, project_path="/tmp")
    assert "[봉투불변식] [sense:probe]" in capsys.readouterr().out


def test_s4_naver_search_emits_estimate_not_total():
    sys.path.insert(0, os.path.join(PKG, "web"))
    import tool_naver_search as tns
    src = open(tns.__file__, encoding="utf-8").read()
    ret = src[src.index("def search_naver("):]
    assert '"total_estimate":' in ret and '"total":' not in ret


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
