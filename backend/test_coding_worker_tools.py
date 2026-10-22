import boot_paths  # noqa: F401
import json
import shlex
from types import SimpleNamespace

import pytest

from coding_process import available
from coding_worker_tools import configure_worker


def test_isolated_provider_survives_gear_and_role_switches():
    from agent_cognitive import AgentCognitiveMixin
    from system_ai_core import _switch_to_role
    ai = object()
    runner = SimpleNamespace(config={'_isolated_workspace': '/copy'}, ai=ai)
    AgentCognitiveMixin._sync_execution_gear(runner)
    assert _switch_to_role(runner, 'coding') is None
    assert runner.ai is ai


@pytest.mark.skipif(not available(), reason='macOS coding sandbox')
def test_api_worker_commands_write_only_copy_and_ibl_cannot_bypass(tmp_path):
    original = tmp_path / 'original.txt'
    original.write_text('keep')
    copy = tmp_path / 'copy'
    copy.mkdir()
    runner = SimpleNamespace(ai=SimpleNamespace(_provider=SimpleNamespace()))
    processes = configure_worker(runner, str(copy), 'test-worker', lambda: False)
    execute = runner.ai._custom_execute_tool
    try:
        output = json.loads(execute('run_command', {'command': 'printf result > result.txt'}, str(copy)))
        assert output['success'] and (copy / 'result.txt').read_text() == 'result'
        output = json.loads(execute('run_command', {'command': 'printf changed > ' + shlex.quote(str(original))}, str(copy)))
        assert not output['success'] and original.read_text() == 'keep'
        with pytest.raises(ValueError, match='격리된'):
            execute('execute_ibl', {'code': '[self:write]{path:"outside.txt",content:"changed"}'}, str(copy))
    finally:
        processes.close()


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
