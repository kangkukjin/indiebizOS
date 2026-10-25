"""관문 — 가르친 서명대로 부르면 실행된다 (2026-09-06).

09-06 실측: 이름 붙은 45건 가운데 10건(22%)의 *표시* 서명이 *실행* 요구와 어긋났고, 그중 5건은
표시가 빈 `{}` 라 가르친 대로 부르면 100% "인자 누락"으로 거절됐다 — `[fn:]` 호출 0 의 뿌리.
뿌리는 서명의 소스가 둘이었다는 것: 표시는 `${…}` 정규식(hippo_tree), 실행은 자유변수(call_signature).

이 관문이 지키는 것: 서명의 소스는 하나(실행기)이고, 원장 문이 저장하며, 모든 표시 표면이 그것을 읽는다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401

import hippo_tree
import ibl_usage_db




def test_원장_문이_서명을_계산해_저장한다():
    """add_example 로 들어온 프로그램은 서명을 갖는다 — 기록기가 아니라 문이 계산한다."""
    code = '#!ibl edition=2\n[def:읽기]($경로,$개수){$본=[self:read]{path:$경로}\nreturn $본.items >> [table:take]{n:$개수}}'
    assert ibl_usage_db._signature_of(code) is not None, "서명 계산자가 조립 뿌리에서 안 꽂혔다"
    assert set(ibl_usage_db._signature_of(code).split()) == {'경로','개수'}


def test_저장_서명_규약_NULL과_빈문자열을_가른다():
    """NULL=미계산(폴백해야 한다), ''=인자 없음(빈 `{}` 가 참이다). 둘을 섞으면 거짓 서명을 가르친다."""
    assert ibl_usage_db.parse_signature(None) == ([], False)
    assert ibl_usage_db.parse_signature("") == ([], True)
    assert ibl_usage_db.parse_signature("a b") == (["a", "b"], True)






def test_이름_채널은_카테고리가_아니라_부를_수_있는가로_고른다():
    """`[fn:]` 해소가 카테고리 무관이므로 보여주기도 그래야 한다 — 잠기면 부를 수 있는데 안 보인다."""
    import inspect
    from ibl_usage_rag import IBLUsageRAG
    # 검색 본체는 search_phrases_split(2026-09-26 상시 이름 제외로 분리) — search_phrases 는 그 첫 몫.
    src = inspect.getsource(IBLUsageRAG.search_phrases_split)
    assert "search_phrases_split" in inspect.getsource(IBLUsageRAG.search_phrases)
    assert "aliased_only=True" in src, "이름 채널이 다시 category='phrase' 로 잠겼다"


def test_회상_이름_채널은_본문을_싣지_않는다():
    """본문이 보이면 베낀다(09-05 '이름 먼저' 사용자 판정) — 서명만 싣기에 문턱을 낮출 수 있었다."""
    import inspect
    from ibl_usage_rag import IBLUsageRAG
    src = inspect.getsource(IBLUsageRAG._format_references)
    assert "[def: " not in src, "이름 채널이 다시 [def:] 본문을 싣는다 — 베끼기 통로가 열렸다"
    assert IBLUsageRAG.PHRASE_MIN_SCORE <= IBLUsageRAG.LOW_CONF_FLOOR


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
