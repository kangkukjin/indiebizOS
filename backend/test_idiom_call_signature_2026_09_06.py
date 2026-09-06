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
from workflow_contract import call_signature


def _executor_signature(code: str):
    return call_signature(code)


def test_원장_문이_서명을_계산해_저장한다():
    """add_example 로 들어온 프로그램은 서명을 갖는다 — 기록기가 아니라 문이 계산한다."""
    code = '$본 = [self:read]{path: "$경로"}; $본 >> [table:take]{n: "$개수"}'
    assert ibl_usage_db._signature_of(code) is not None, "서명 계산자가 조립 뿌리에서 안 꽂혔다"
    assert set(ibl_usage_db._signature_of(code).split()) == set(_executor_signature(code))


def test_저장_서명_규약_NULL과_빈문자열을_가른다():
    """NULL=미계산(폴백해야 한다), ''=인자 없음(빈 `{}` 가 참이다). 둘을 섞으면 거짓 서명을 가르친다."""
    assert ibl_usage_db.parse_signature(None) == ([], False)
    assert ibl_usage_db.parse_signature("") == ([], True)
    assert ibl_usage_db.parse_signature("a b") == (["a", "b"], True)


def test_표시_서명이_실행_요구와_같다():
    """이름 붙은 모든 용례: 회상·상시 블록이 보여 주는 슬롯 == `[fn:]` 이 요구하는 인자."""
    import sqlite3
    db = Path(__file__).resolve().parent.parent / "data" / "ibl_usage.db"
    if not db.exists():
        return
    con = sqlite3.connect(str(db))
    rows = con.execute("SELECT id, alias, ibl_code, signature FROM ibl_examples "
                       "WHERE COALESCE(alias,'') != ''").fetchall()
    con.close()
    bad = []
    for rid, alias, code, sig in rows:
        try:
            want = _executor_signature(code)
        except Exception:
            continue                       # 파스 불가 몸은 서명 미상 — 표시 쪽이 '미상'으로 말한다
        shown = hippo_tree.slot_names(code, sig)
        if sorted(shown) != sorted(want):
            bad.append(f"#{rid} {alias}: 표시 {shown} != 실행 {want}")
    assert not bad, ("가르친 서명대로 부르면 거절된다 — 서명의 소스가 갈라졌다:\n  " + "\n  ".join(bad))


def test_부를_수_없는_모양은_이름을_못_받는다():
    from ibl_idiom import uncallable_reason
    assert uncallable_reason([]) is None                       # 인자 없는 함수는 정당하다
    assert uncallable_reason(["경로", "줄"]) is None
    assert uncallable_reason([f"인자{i}" for i in range(9)])    # 상한 초과
    assert uncallable_reason(["보고서내용"], sentences=5)       # 인자가 전부 본문
    assert uncallable_reason(["경로", "새코드"], sentences=2)   # 아낄 문장이 없다
    assert uncallable_reason(["경로", "새코드"], sentences=5) is None   # 앞뒤 문장을 아껴 준다
    assert uncallable_reason(["본문지시"], sentences=5) is None         # 지시는 본문이 아니다


def test_이름_채널은_카테고리가_아니라_부를_수_있는가로_고른다():
    """`[fn:]` 해소가 카테고리 무관이므로 보여주기도 그래야 한다 — 잠기면 부를 수 있는데 안 보인다."""
    import inspect
    from ibl_usage_rag import IBLUsageRAG
    src = inspect.getsource(IBLUsageRAG.search_phrases)
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
