"""일회성 관문 — 이번 값이 얼어 있는 몸에는 이름을 주지 않는다 (2026-09-07 등록만 감사).

옛 반성기 프롬프트가 산문으로만 말하던 규약("슬롯으로 비우지 않은 값은 다음 주행에서도 같은 값이어야
한다")을 관문으로 옮긴 것. 산문은 지켜지지 않았다 — 38건 중 10건이 그 부류로 태어났다.

★이 관문은 **회수의 자**이기도 하다: 사람이 고른 목록으로 쓸지 않는다(hand-picked sweep leaks).
"""
import os
import sys

import pytest

import boot_paths  # noqa: E402,F401

BODY = '[self:edit]{path: "${파일}", old_string: "${앞}", new_string: "${뒤}"}; $return = $파일'








def test_registration_uses_the_same_gate():
    """등록 관문과 회수의 자가 한 벌이어야 한다 — 갈라지면 회수한 것이 다시 등록된다."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import register_idiom
    info, why = register_idiom._gates(
        "상태보고적용", "패치 상태를 보고 적용해야 할 때 그것을 한 번에",
        '#!ibl edition=2\n[def:상태보고적용](){return [self:patch]{op:"status"}}')
    assert info is not None and why is None  # 정의 등록은 무인자 함수도 허용한다.




if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
