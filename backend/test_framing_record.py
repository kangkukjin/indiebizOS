"""직전 규정의 기록 — 옛 추천·복구 문맥이 기록에 섞이지 않는다. 규정 계승은 2026-11-17 없앴다."""
import json

import boot_paths  # noqa: F401
import pytest
import framing_record as fi


@pytest.mark.parametrize('key', ['capability_focus', 'ibl_focus'])
def test_old_saved_recommendations_do_not_enter_the_record(key):
    """기록에는 옛 추천 액션 목록이 남지 않는다 — 기록을 읽는 쪽(의식의 계획 후보, 수리 재개)에 흘러가지 않게."""
    framing = {'task_framing': '기간 비교', 'achievement_criteria': '근거 보존',
               'criteria': [{'text': '근거 보존', 'user_quote': '', 'fallback': ''}],
               key: {'hint': '기존 의존 관계', 'highlight_actions': ['self:read']}}
    stored = fi._storable(framing)
    assert 'highlight_actions' not in json.dumps(stored) and 'ibl_focus' not in stored
    assert stored['capability_focus'] == {'hint': '기존 의존 관계'}


def test_legacy_approval_requires_reframing_instead_of_assumed_success(tmp_path, monkeypatch):
    from test_think_always_fresh_framing import Runner, _remember, _calls
    from thread_context import actor_context
    monkeypatch.setattr(fi, "_store_root", lambda: tmp_path)
    runner = Runner()
    _remember(runner, "같은 보고서")
    data = fi._load("agent_t")
    for record in [data["last"], *data["repeat"].values()]:
        record.pop("goal_status", None)
        record["achieved"] = True  # 구기록의 승인만 있다.
    fi._save("agent_t", data)
    calls = _calls(monkeypatch)
    with actor_context(agent_id="agent_t", task_id="next"):
        runner._run_consciousness_or_reuse("같은 보고서", [], "")
    assert runner.calls == 1 and calls == []


def test_recovery_prefix_cannot_replace_new_user_request(monkeypatch, tmp_path):
    """복구 문맥이 앞에 붙어도 기록에 남는 요청은 사용자의 원문이다. 규정은 의식이 새로 쓴다."""
    from dialogue_continuation import _execute
    from test_think_always_fresh_framing import Runner, _remember
    from thread_context import actor_context
    monkeypatch.setattr(fi, '_store_root', lambda: tmp_path)
    runner = Runner()
    _remember(runner, '업데이트하다 중단했다', achieved=False)
    request = '다시 확인해 보고 완성해줘.'
    augmented = '이전 실행 복구 관측\n' * 1000 + '[이번 사용자 요청]\n' + request
    monkeypatch.setattr('repair_resume._oneshot', lambda *a: pytest.fail('경량 모델이 규정에 불렸다'))

    def execute(prompt, history):
        framing = runner._run_consciousness_or_reuse(prompt, history)
        yield framing
        fi.remember(runner, prompt, framing)

    with actor_context(agent_id='agent_t', task_id='new'):
        result = list(_execute(execute, augmented, [{'role': 'user', 'content': '이어서'}], request))
    assert runner.calls == 1 and result[0]['task_framing'] == '새 규정'
    assert fi._load('agent_t')['last']['message'] == request
    # 바깥에서 같은 표식을 쓴 사용자 메시지는 그 자체가 원문이다.
    from dialogue_continuation import recall_query
    assert recall_query(augmented) == augmented


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
