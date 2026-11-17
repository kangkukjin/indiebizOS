"""과제 기억은 수리 권한을 상속하지 않는다. 새 의식의 선언만 현재 턴에 유효하다."""
import boot_paths  # noqa: F401
from types import SimpleNamespace
import pytest
from cognitive_consciousness import CognitiveConsciousnessMixin


@pytest.fixture
def run():
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
    assert out['criteria'] == [{'text': '새 기준'}]


def test_fresh_consciousness_may_declare_repair(run):
    runner, out = run(True, True)
    assert runner.calls == 1 and out['needs_repair'] is True


@pytest.mark.parametrize('message', ['#repair 로그 화면 줄바꿈을 고쳐줘', '로그 화면 줄바꿈을 고쳐줘 #repair',
                                     '#repair #think 로그 화면 줄바꿈을 고쳐줘', '로그 화면 줄바꿈을 고쳐줘'])
def test_every_repair_turn_is_framed_by_consciousness(monkeypatch, message):
    """수리 판정을 받은 일은 누가 판정했든 의식이 어떻게 고칠지 규정한다. 사용자가 #repair 를 붙인 것은 무의식이
    수리로 판정한 것과 같다(2026-11-17 사용자 판정). 그 전에는 #repair 가 붙으면 의식 없이 요청문이 그대로
    과제와 완료 기준이 됐다."""
    monkeypatch.setattr('thread_context.get_task_origin', lambda: 'user')

    class Runner(CognitiveConsciousnessMixin):
        calls = []
        def _run_consciousness(self, user_message, history, memory='', repair=False, **kw):
            self.calls.append(repair)
            return {'task_framing': '줄바꿈 스타일의 원인을 찾아 고친다', 'needs_repair': True,
                    'criteria': [{'text': '긴 줄이 화면 폭 안에서 줄바꿈된다'}]}
    runner = Runner()
    out = runner._run_consciousness_or_reuse(message, [], '', repair=True)
    assert runner.calls == [True]                                   # 수리 교리를 실은 의식 호출 한 번
    assert out['_framing_source'] == 'fresh_consciousness' and out['_repair_policy'] == 2
    assert out['task_framing'] == '줄바꿈 스타일의 원인을 찾아 고친다'     # 요청문을 그대로 쓰지 않는다
    assert out['criteria'] == [{'text': '긴 줄이 화면 폭 안에서 줄바꿈된다'}]


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
