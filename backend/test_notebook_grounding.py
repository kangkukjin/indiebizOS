"""노트북 ask 근거 판정 회귀 (2026-09-04 실측 — 사용자 신고 "소스에 넣어도 답이 없다고만 한다").

재현: 'AI 동향' 노트북(65소스·1,879청크)에 "가장 유용한 AI 응용사례는?" → 검색은 관련 발췌 12개(0.66~0.70)를
냈는데 경량 판정기가 "발췌는 사례를 나열하지만 순위는 없다 … NOT_IN_SOURCES" 로 거절. 규칙 3이 '소스가
주제를 안 다룸'과 '확정 판단이 없음'을 한 낱말로 뭉갰고, 후처리는 표식이 어디든 있으면 통째로 버렸다.

계약:
  N1  표식이 답을 대신할 때만 '없음'(표식 + 유효 인용 0). 인용 달린 답에 표식이 섞이면 답을 살린다.
  N2  살린 답에서 표식 줄은 걷어낸다.
  N3  판정 프롬프트는 '주제를 전혀 다루지 않을 때만' 없음이라 말하고 한계 진술을 요구한다.
  N4  맨 표식인데 검색 최고점이 COVERAGE_SCORE 이상이면 검색 사실을 실어 한 번 되묻는다(점수 낮으면 안 되묻는다).

실행: .venv/bin/python -m pytest backend/test_notebook_grounding.py -q
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401
sys.path.insert(0, os.path.join(ROOT, "data", "packages", "installed", "tools", "notebook"))


def test_n1_mark_only_or_uncited_is_not_in_sources():
    import handler as H
    assert H._is_not_in_sources("NOT_IN_SOURCES", 12)
    assert H._is_not_in_sources("발췌는 사례를 나열하지만 순위는 없습니다. 따라서 답할 수 없습니다.\n\nNOT_IN_SOURCES", 12)
    assert H._is_not_in_sources("근거 [99] 로 답합니다. NOT_IN_SOURCES", 12)      # 범위 밖 인용은 무효
    assert not H._is_not_in_sources("보고서는 코사이언티스트 제도화를 꼽는다 [2]. 순위는 소스에 없다.\nNOT_IN_SOURCES", 12)
    assert not H._is_not_in_sources("보고서는 코사이언티스트 제도화를 꼽는다 [2].", 12)


def test_n2_strip_mark_keeps_answer():
    import handler as H
    out = H._strip_mark("답 [1][3].\nNOT_IN_SOURCES\n한계: 순위는 없다 [2].")
    assert "NOT_IN_SOURCES" not in out and out.startswith("답 [1][3].") and out.endswith("[2].")


def test_n3_prompt_contract():
    import inspect
    import handler as H
    src = inspect.getsource(H._grounded_generate)
    assert "주제를 전혀 다루지 않을 때만" in src and "한계를 밝혀라" in src


def test_n4_reask_only_when_search_covered_the_topic():
    import handler as H
    hi = [{"score": 0.70, "text": "x"}, {"score": 0.66, "text": "y"}]
    lo = [{"score": 0.31, "text": "x"}]
    assert H._should_reask("NOT_IN_SOURCES", hi)
    assert not H._should_reask("NOT_IN_SOURCES", lo)
    assert not H._should_reask("답 [1].", hi)                       # 답이 있으면 되묻지 않는다
    assert H._top_score([]) == 0.0 and not H._should_reask("NOT_IN_SOURCES", [])


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
