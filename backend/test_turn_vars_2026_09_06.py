"""턴 범위 변수 — 언어 개정 2026-09-06(사용자 판정: `$rN` 핸들·resume_vars 명시 확장 대신 변수 수명을 턴으로).

`$이름 = …` 로 할당한 변수는 같은 턴(task_id)의 다음 execute_ibl 호출에서 그대로 보인다. 모델이 앞 결과를
다시 치지 않게(ep2890 부동산 22.8K자·ep2884 수리 112K자 되받아쓰기). 기판은 resume_vars 와 같은 스필+preset.

실행: .venv/bin/python -m pytest -q backend/test_turn_vars_2026_09_06.py
"""
import json
import uuid

import pytest

from system_tools import _execute_ibl_unified
from thread_context import actor_context


def _run(code, tmp_path, task, agent="probe", **extra):
    with actor_context(agent_id=agent, task_id=task):
        return json.loads(_execute_ibl_unified({"code": code, **extra}, str(tmp_path), agent_id=agent))


@pytest.fixture
def task():
    return f"task_test_{uuid.uuid4().hex[:8]}"


def _fr(out):
    fr = out.get("final_result")
    return json.loads(fr) if isinstance(fr, str) else fr
















def test_reserved_names_are_not_injected():
    from ibl_turn_vars import referenced
    assert referenced('$items >> [table:take]{n: $i} $error $return $file:0 $real ${also}') == ["also", "real"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
