"""과제 기억은 수리 권한을 상속하지 않는다. 새 의식의 선언만 현재 턴에 유효하다."""
import boot_paths  # noqa: F401
from types import SimpleNamespace
import pytest
from cognitive_consciousness import CognitiveConsciousnessMixin


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr("framing_inheritance.inherit", lambda *a: None)
    def check(repair_framing, fresh_repair=False):
        class Runner(CognitiveConsciousnessMixin):
            calls = 0
            def _run_consciousness(self, *a, **kw):
                self.calls += 1
                return {'task_framing': '새 지도', 'achievement_criteria': '새 기준', 'needs_repair': fresh_repair}
        runner = Runner()
        return runner, runner._run_consciousness_or_reuse('이어해', [], '')
    return check


def test_repair_framing_reawakens_and_does_not_inherit(run):
    runner, out = run(True)
    assert runner.calls == 1 and not out.get('needs_repair')


def test_plain_framing_is_fresh_without_inherited_privilege(run):
    runner, out = run(False)
    assert runner.calls == 1 and not out.get('needs_repair')
    assert out['achievement_criteria'] == '새 기준'


def test_fresh_consciousness_may_declare_repair(run):
    runner, out = run(True, True)
    assert runner.calls == 1 and out['needs_repair'] is True


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
