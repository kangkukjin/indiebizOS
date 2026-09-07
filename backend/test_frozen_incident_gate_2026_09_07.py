"""일회성 관문 — 이번 값이 얼어 있는 몸에는 이름을 주지 않는다 (2026-09-07 등록만 감사).

옛 반성기 프롬프트가 산문으로만 말하던 규약("슬롯으로 비우지 않은 값은 다음 주행에서도 같은 값이어야
한다")을 관문으로 옮긴 것. 산문은 지켜지지 않았다 — 38건 중 10건이 그 부류로 태어났다.

★이 관문은 **회수의 자**이기도 하다: 사람이 고른 목록으로 쓸지 않는다(hand-picked sweep leaks).
"""
import os
import sys

import pytest

import boot_paths  # noqa: E402,F401
from ibl_idiom import frozen_incident_reason, FROZEN_SLOT_CEILING  # noqa: E402

BODY = '[self:edit]{path: "${파일}", old_string: "${앞}", new_string: "${뒤}"}; $return = $파일'


def test_no_slot_is_a_macro_not_a_function():
    assert "슬롯 0" in frozen_incident_reason('[self:patch]{op: "status"}; [self:patch]{op: "apply"}', [])


def test_signature_as_long_as_the_body():
    names = [f"s{i}" for i in range(FROZEN_SLOT_CEILING)]
    assert f"슬롯 {FROZEN_SLOT_CEILING}개" in frozen_incident_reason(BODY, names)
    assert frozen_incident_reason(BODY, names[:-1]) is None


@pytest.mark.parametrize("code,frozen", [
    ('[self:read]{path: "~workspace/outputs/_tmp_투자.json"}', True),      # 남의 그날 그 파일
    ('[engines:render]{op: "xlsx", path: "정산표.xlsx"}', False),          # 확장자는 있으나 경로가 아니다
    ('[sense:crawl]{url: "https://simonwillison.net/"}', True),            # 얼어붙은 출처 — 부르는 쪽이 못 바꾼다
    ('[sense:crawl]{url: "${주소}"}', False),                                # 슬롯으로 비운 출처
    ('[self:read]{path: "${경로}/보고서.md"}', False),                      # 슬롯으로 비운 자리는 얼지 않았다
])
def test_path_literals(code, frozen):
    got = frozen_incident_reason(code, ["파일", "앞"])
    assert bool(got) is frozen, got


def test_registration_uses_the_same_gate():
    """등록 관문과 회수의 자가 한 벌이어야 한다 — 갈라지면 회수한 것이 다시 등록된다."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import register_idiom
    info, why = register_idiom._gates(
        "상태보고적용", "패치 상태를 보고 적용해야 할 때 그것을 한 번에",
        '[self:patch]{op: "status"}; [self:patch]{op: "apply"}')
    assert info is None and "슬롯 0" in why


def test_promoted_vocabulary_all_pass_the_gate():
    """어휘급으로 세운 것은 이 관문을 통과해야 한다 — 통과 못 하면 세운 쪽이 틀렸다."""
    import sqlite3
    from runtime_utils import get_base_path
    from ibl_usage_db import parse_signature
    db = get_base_path() / "data" / "ibl_usage.db"
    if not db.exists():
        pytest.skip("원장 없음")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute("SELECT alias, ibl_code, COALESCE(signature,'') FROM ibl_examples "
                       "WHERE COALESCE(always_on,0)=1").fetchall()
    con.close()
    bad = []
    for alias, code, sig in rows:
        names, known = parse_signature(sig)
        why = frozen_incident_reason(code, names if known else [])
        if why:
            bad.append(f"{alias}: {why}")
    assert not bad, bad


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
