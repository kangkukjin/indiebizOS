"""Frozen live evaluator replay and a held-out venue goal correction."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from thread_context import set_task_origin
from final_evaluator import Evaluator
import framing_inheritance as fi

set_task_origin('training')
out = Path(sys.argv[1])
result = {}
evaluator = Evaluator()
evaluator._scheduled_repair_note = lambda: ''
result['claim_input'] = {
    'message': '시간이 지나면 꺼지고 다이얼처럼 조작이 쉬우며 후기가 충분한 제품을 골라줘.',
    'criteria': {'criteria': [{'id': 'C1', 'text': '시간이 지나면 꺼지는 기능 확인',
                              'source': 'user', 'fallback': ''},
                             {'id': 'C2', 'text': '다이얼처럼 쉬운 조작 확인'},
                             {'id': 'C3', 'text': '후기 수가 충분한지 비교'}]},
    'answer': 'C를 추천합니다. 세 조건을 모두 확인했습니다. 주의: 타이머는 있음으로만 표시되어 있고 시간이 끝나면 전원이 꺼지는지는 확인하지 못했습니다.',
    'evidence': 'C: timer=true, dial=true, reviews=850. 자동으로 꺼지는 방식에 대한 설명은 자료에 없다.',
}
case = result['claim_input']
t = time.monotonic()
result['claim_evaluation'] = evaluator._evaluate_achievement(
    case['message'], json.dumps(case['criteria'], ensure_ascii=False), case['answer'], '',
    tool_results_str=case['evidence'])
result['claim_seconds'] = time.monotonic() - t
out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
if '--claim-only' in sys.argv:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0)

history = [
    {'role': 'user', 'content': '가족 모임 장소를 찾아줘. 주차가 있어야 해.'},
    {'role': 'assistant', 'content': '주차장 있는 가람 식당을 추천한다.'},
    {'role': 'user', 'content': '차 대신 택시로 가니 주차는 없어도 돼. 휠체어를 쓰는 가족이 있어 입구부터 좌석까지 계단 없이 갈 수 있어야 해.'},
    {'role': 'assistant', 'content': '가람은 입구에 계단 세 개가 있지만 좌석이 넓다.'},
]
previous = {'message': history[0]['content'], 'framing': {
    'task_framing': '주차가 있고 편안한 가족 식당을 추천한다.',
    'achievement_criteria': '주차와 넓은 좌석을 가진 식당 추천',
    'criteria': [{'text': '주차와 넓은 좌석', 'user_quote': '', 'fallback': ''}],
}}
result['venue_input'] = {'history': history, 'previous': previous}
t = time.monotonic()
result['venue_patch'] = fi._patch(previous, '앞서 말한 조건대로 다른 곳을 더 찾아봐.',
                                  'followup', history=history)
result['venue_patch_seconds'] = time.monotonic() - t
t = time.monotonic()
result['venue_evaluation'] = evaluator._evaluate_achievement(
    '앞서 말한 조건대로 추천해줘.',
    json.dumps({'criteria': [{'id': 'C1', 'text': '주차와 넓은 좌석의 식당 추천'}]}, ensure_ascii=False),
    '가람은 주차가 있고 좌석이 넓어 추천합니다. 입구의 계단 세 개는 주의하세요.', '',
    consciousness_output=previous['framing'], conversation_history=history,
    tool_results_str='가람: 주차 있음, 좌석 넓음, 입구 계단 세 개, 경사로 없음.')
result['venue_evaluation_seconds'] = time.monotonic() - t
out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False, indent=2))
