"""Live production patch/evaluation calls on a frozen contradictory history."""
import inspect
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
import framing_inheritance as fi
from final_evaluator import Evaluator
set_task_origin('training')
HISTORY = [{'role':'user','content':'내장 타이머가 있는 쿠커를 찾는다.'},
 {'role':'assistant','content':'내장 타이머와 코팅이 있는 A를 추천한다.'},
 {'role':'user','content':'타이머는 콘센트로 해결한다. 내장 타이머는 없어도 된다. 냄비나 조절기를 분리해 물로 씻을 수 있어야 한다.'},
 {'role':'assistant','content':'A는 냄비가 붙어 있지만 코팅이 있어 닦기 쉽다.'}]
previous={'message':HISTORY[0]['content'],'framing':{'task_framing':'내장 타이머가 달린 청소 쉬운 쿠커를 1~2개 찾는다.',
 'achievement_criteria':'내장 타이머, 청소 편의 근거, 제품명과 가격을 제시한다.',
 'criteria':[{'text':'내장 타이머가 달리고 코팅 등 청소 편의 근거가 있는 후보 제시','user_quote':'','fallback':'미확인 사항을 표시'}]}}
label=sys.argv[1];out=Path(sys.argv[2]);result={'label':label,'history':HISTORY,'previous':previous}
t=time.time()
kw={'history':HISTORY} if 'history' in inspect.signature(fi._patch).parameters else {}
result['patch']=fi._patch(previous,'다른 제품을 더 찾아봐. 앞서 말한 조건대로.', 'followup',**kw)
result['patch_seconds']=time.time()-t
out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
e=Evaluator();e._scheduled_repair_note=lambda:''
# Deliberately stale criteria: the evaluation must detect a conflict with the user, not invent a new goal.
contract={'criteria':[{'id':'C1','text':'코팅 등 청소 편의 근거가 있는 후보의 제품명과 가격 제시','source':'plan'}]}
kw={'conversation_history':HISTORY} if 'conversation_history' in inspect.signature(e._evaluate_achievement).parameters else {}
t=time.time()
result['evaluation']=e._evaluate_achievement('앞서 말한 조건대로 다시 추천해줘.',json.dumps(contract,ensure_ascii=False),
 'A(32000원)를 추천합니다. 본체 일체형이지만 코팅이 있어 닦기 쉽습니다.', '',
 consciousness_output=previous['framing'],tool_results_str='제품 A: 32000원, 냄비 고정, 코팅 있음. 제품 B: 52000원, 온도조절기 분리 후 냄비 물세척 가능.', **kw)
result['evaluation_seconds']=time.time()-t
out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({'label':label,'patch':result['patch'],'evaluation':result['evaluation']},ensure_ascii=False))
