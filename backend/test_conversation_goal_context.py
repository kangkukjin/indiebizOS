"""L81: intervening user corrections reach framing inheritance and final judgment."""
import json
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import framing_inheritance as fi
from test_conscious_supervisor import supervisor  # noqa: F401

CORRECTION = '외부 타이머로 해결하니 내장 타이머는 필요 없다. 분리 물세척을 원한다.'
HISTORY = [{'role': 'user', 'content': '타이머가 있는 쿠커를 찾는다.'},
           {'role': 'assistant', 'content': 'A를 추천한다.'},
           {'role': 'user', 'content': CORRECTION},
           {'role': 'assistant', 'content': 'A는 냄비 고정이고 B는 분리된다.'}]


def test_intervening_execute_correction_reaches_both_inheritance_calls(monkeypatch):
    previous = {'message': HISTORY[0]['content'], 'framing': {
        'task_framing': '내장 타이머 추천', 'criteria': [{'text': '내장 타이머 후보'}]}}
    seen = []
    def answer(body, prompt, role):
        seen.append(json.loads(body))
        return 'CONTINUE' if role == 'classify' else json.dumps({
            'achievement_criteria': '분리 세척 후보', 'criteria': [{'text': '분리 세척 후보'}]})
    monkeypatch.setattr(fi, '_candidate', lambda *a: ('followup', previous))
    monkeypatch.setattr(fi, '_oneshot', answer)
    monkeypatch.setattr('pursuit_bind.validate_output', lambda *a, **kw: None)
    monkeypatch.setattr('pursuit_bind.accept_output', lambda *a, **kw: None)
    result = fi._inherit(SimpleNamespace(), '다른 것을 더 찾아봐.', HISTORY, lambda *a: None)
    assert result['_framing_source'] == 'inherited_followup'
    assert len(seen) == 2
    assert all(CORRECTION in json.dumps(body, ensure_ascii=False) for body in seen)
    assert 'history_summary' not in result  # executor still receives original history


def test_final_evaluation_gets_raw_conversation_even_with_stale_summary(supervisor, monkeypatch):
    from final_evaluator import prepare, invoke
    supervisor.history = HISTORY
    supervisor.framing['history_summary'] = '내장 타이머를 찾는 사용자'
    supervisor.store.put_response('A를 추천한다.')
    prompts = []
    monkeypatch.setattr('consciousness_agent.system_ai_call',
                        lambda prompt, **kw: prompts.append(prompt) or 'ACHIEVED')
    prepare(supervisor)
    invoke(supervisor)
    assert len(prompts) == 1
    assert CORRECTION in prompts[0]
    assert 'A는 냄비 고정이고 B는 분리된다.' in prompts[0]
    assert 'user' in prompts[0] and 'assistant' in prompts[0]


def test_history_excerpt_preserves_short_middle_corrections_and_roles():
    from history_excerpt import conversation_excerpt
    history = [{'role': 'user', 'content': '처음 요구'},
               {'role': 'assistant', 'content': '설명' * 20000},
               *HISTORY,
               {'role': 'assistant', 'content': '다른 설명' * 20000},
               {'role': 'user', 'content': '마지막 정정'}]
    before = json.dumps(history, ensure_ascii=False)
    text = conversation_excerpt(history, 4000)
    assert len(text) <= 4000
    assert CORRECTION in text and '처음 요구' in text and '마지막 정정' in text
    assert '[3 user]' in text and '[4 assistant]' in text
    assert '생략' in text
    assert json.dumps(history, ensure_ascii=False) == before


def test_history_excerpt_empty_and_many_messages_are_explicitly_bounded():
    from history_excerpt import conversation_excerpt
    assert conversation_excerpt([]) == ''
    history = [{'role': 'user', 'content': f'요청 {i}'} for i in range(1000)]
    text = conversation_excerpt(history, 2000)
    assert len(text) <= 2000
    assert '요청 0' in text and '요청 999' in text and '메시지 생략' in text
    with pytest.raises(ValueError):
        conversation_excerpt(history, 127)


def test_repeat_patch_does_not_import_unrelated_dialogue(monkeypatch):
    seen = []
    monkeypatch.setattr(fi, '_oneshot', lambda body, *a: seen.append(json.loads(body)) or '{}')
    assert fi._patch({'framing': {}}, '정기 보고', 'repeat', history=HISTORY) == {}
    assert CORRECTION not in json.dumps(seen, ensure_ascii=False)


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
