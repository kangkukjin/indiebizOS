"""Capture production boundary inputs without a model call or runtime mutation."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import framing_inheritance as fi  # noqa: E402
from final_evaluator import invoke  # noqa: E402

CORRECTION = '외부 타이머로 해결하니 내장 타이머는 필요 없다. 분리 물세척을 원한다.'
HISTORY = [{'role': 'user', 'content': '타이머가 있는 쿠커를 찾는다.'},
           {'role': 'assistant', 'content': 'A를 추천한다.'},
           {'role': 'user', 'content': CORRECTION},
           {'role': 'assistant', 'content': 'A는 냄비 고정이고 B는 분리된다.'}]

def run():
    seen = []
    previous = {'message': '타이머가 있는 쿠커를 찾는다.', 'framing': {
        'task_framing': '내장 타이머 제품 추천', 'achievement_criteria': '후보 제시',
        'criteria': [{'text': '내장 타이머 후보', 'user_quote': '', 'fallback': ''}]}}
    def call(body, prompt, role):
        seen.append(json.loads(body))
        return 'CONTINUE' if role == 'classify' else json.dumps({
            'achievement_criteria': '후보 제시', 'criteria': [{'text': '후보 제시'}]})
    with patch.object(fi, '_candidate', return_value=('followup', previous)), \
         patch.object(fi, '_oneshot', side_effect=call), \
         patch('pursuit_bind.validate_output'), patch('pursuit_bind.accept_output'):
        fi._inherit(SimpleNamespace(), '더 찾아봐.', HISTORY, lambda *a: None)
    evaluator = {}
    def evaluate(*args, **kwargs):
        evaluator.update(kwargs)
        return True, 'ACHIEVED', 0
    controller = SimpleNamespace(
        _evaluation_packet={'criteria': '{"criteria":[{"id":"C1","text":"후보 제시"}]}',
            'response': 'A 추천', 'files': '', 'calls': [], 'images': [], 'context': {'criteria_contract': {}}},
        _evaluation_snapshot={'response': {'version': 1, 'hash': 'test'}, 'delivery': None},
        cancelled=lambda: False, log=lambda *a, **k: None, message='더 찾아봐.',
        framing=previous['framing'], history=HISTORY, done_request=None)
    with patch('final_evaluator.Evaluator._evaluate_achievement', side_effect=evaluate):
        invoke(controller)
    return {'inherit_inputs': seen, 'evaluation_arguments': evaluator,
            'inherit_received_correction': CORRECTION in json.dumps(seen, ensure_ascii=False),
            'evaluator_received_correction': CORRECTION in json.dumps(evaluator, ensure_ascii=False)}

if __name__ == '__main__':
    result = run()
    Path(sys.argv[1]).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print({k: v for k, v in result.items() if k.endswith('_correction')})
