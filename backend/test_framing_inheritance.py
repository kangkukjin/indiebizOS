"""Current-request criteria survive framing inheritance and reach final evaluation."""
import json

import boot_paths  # noqa: F401
import pytest
import framing_inheritance as fi
from supervisor_handoff import criteria_contract


@pytest.mark.parametrize('mode', ['followup', 'repeat'])
def test_patch_replaces_structured_criteria_used_by_evaluation(monkeypatch, mode):
    previous = {'framing': {'achievement_criteria': '소재 제작',
                           'criteria': [{'text': '이미지 세 장', 'user_quote': '', 'fallback': ''}]}}
    patch = {'achievement_criteria': '반응 검토', 'criteria': [
        {'text': '결측일을 밝히고 KPI 판정', 'user_quote': 'KPI 판정', 'fallback': '미측정 명시'}]}
    seen = []
    def answer(prompt, system_prompt, role):
        seen.append(json.loads(prompt))
        return json.dumps(patch, ensure_ascii=False)
    monkeypatch.setattr(fi, '_oneshot', answer)
    result = fi._patch(previous, 'KPI 판정', mode)
    contract = criteria_contract('KPI 판정', {**previous['framing'], **result})
    assert seen[0]['framing']['criteria'] == previous['framing']['criteria']
    assert len(contract['criteria']) == 1
    assert contract['criteria'][0]['text'] == '결측일을 밝히고 KPI 판정'
    assert contract['criteria'][0]['fallback'] == '미측정 명시'
    assert contract['criteria'][0]['source'] == 'user'


@pytest.mark.parametrize('patch', [{}, {'achievement_criteria': 'new'},
    {'criteria': []}, {'criteria': [{'text': 3}]},
    {'criteria': [], 'achievement_criteria': ''}])
def test_followup_missing_or_invalid_criteria_declines(monkeypatch, patch):
    monkeypatch.setattr(fi, '_oneshot', lambda *a: json.dumps(patch))
    with pytest.raises(ValueError):
        fi._patch({'framing': {}}, '조건 변경', 'followup')


def test_unchanged_repeat_preserves_criteria(monkeypatch):
    monkeypatch.setattr(fi, '_oneshot', lambda *a: '{}')
    assert fi._patch({'framing': {'criteria': [{'text': 'same'}]}}, 'same', 'repeat') == {}


def test_legacy_approval_requires_reframing_instead_of_assumed_success(tmp_path, monkeypatch):
    from test_framing_inheritance_2026_10_07 import Runner, _remember, _calls
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
    from dialogue_continuation import _execute
    from test_framing_inheritance_2026_10_07 import Runner, _remember
    from thread_context import actor_context
    monkeypatch.setattr(fi, '_store_root', lambda: tmp_path)
    runner = Runner()
    _remember(runner, '업데이트하다 중단했다', achieved=False)
    request = '다시 확인해 보고 완성해줘.'
    augmented = '이전 실행 복구 관측\n' * 1000 + '[이번 사용자 요청]\n' + request
    seen = []

    def answer(prompt, system_prompt, role):
        seen.append(json.loads(prompt))
        return 'CONTINUE' if role == 'classify' else json.dumps({
            'task_framing': request, 'achievement_criteria': '실제 동작 확인',
            'criteria': [{'text': '실제 동작 확인', 'user_quote': request, 'fallback': ''}]})

    monkeypatch.setattr(fi, '_oneshot', answer)

    def execute(prompt, history):
        framing = runner._run_consciousness_or_reuse(prompt, history)
        yield framing
        fi.remember(runner, prompt, framing)

    with actor_context(agent_id='agent_t', task_id='new'):
        result = list(_execute(execute, augmented, [{'role': 'user', 'content': '이어서'}], request))
    assert runner.calls == 0
    assert len(seen) == 2 and all(row['new_message'] == request for row in seen)
    assert result[0]['achievement_criteria'] == '실제 동작 확인'
    assert fi._load('agent_t')['last']['message'] == request
    # 바깥에서 같은 표식을 쓴 사용자 메시지는 그 자체가 원문이다.
    from dialogue_continuation import recall_query
    assert recall_query(augmented) == augmented


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
