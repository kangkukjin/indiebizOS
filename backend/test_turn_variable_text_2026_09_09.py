"""숫자 턴 변수 재사용 및 파일 산문에 컴파일러 슬롯이 새던 현장 보고 회귀."""
import json
import uuid

import boot_paths  # noqa: F401
import pytest

from ibl_code_ir import Literal, Template, bind_template, link_template, pack, unpack
from system_tools import _execute_ibl_unified
from thread_context import actor_context


@pytest.fixture
def run(tmp_path, monkeypatch):
    import ibl_turn_vars

    monkeypatch.setattr(ibl_turn_vars, "store_path", lambda key: str(tmp_path / f"{key}.json"))
    task = f"task_test_{uuid.uuid4().hex}"

    def execute(code, **extra):
        with actor_context(agent_id="probe", task_id=task):
            result = _execute_ibl_unified({"code": code, **extra}, str(tmp_path), agent_id="probe")
        try:
            return json.loads(result)
        except (TypeError, ValueError):
            return result

    return execute




def test_partial_binding_updates_text_and_preserves_data_after_transport():
    template = link_template(Template('알려진 $일차 / 남은 $unknown', quoted=True), {"일차": 2_000_000})
    data = '$unknown {{_step_2000000_result}}'
    bound = bind_template(template, lambda name, path: (True, data), namespace="step")
    assert str(bound) == f'알려진 {data} / 남은 $unknown'
    restored = unpack(json.loads(json.dumps(pack(bound))))
    final = bind_template(restored, lambda name, path: (True, "끝"))
    assert isinstance(final, Literal)
    assert final == f'알려진 {data} / 남은 끝'








if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
