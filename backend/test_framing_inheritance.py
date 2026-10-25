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


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
