"""합성 복원 자료로 실제 reframe→의식→계획 저장 경로를 검사한다.

실행자의 자동 기억 검색·reframe 선택을 대신 입증하지 않는다.
"""
import json
from pathlib import Path


def recover(agent, controller, runner, case, directory, workspace, history, initial):
    from reframe import execute_reframe
    fixture = json.loads(Path(__file__).with_name('recovered_context.json').read_text())
    controller.framing = initial

    def rerun(message, messages, execution_memory='', repair=False, revision=None):
        return agent.process(message, messages, execution_memory,
            agent_name='연구계획 훈련', agent_role='사용자 요청에 맞게 문제·목적·연구계획을 구성한다.',
            supervisor=controller, project_path=str(workspace), revision=revision,
            previous_research_plan=(revision or {}).get('previous_research_plan'))

    runner._run_consciousness = rerun
    payload = {'broken_assumption':'이전 두 제안과 목적·조건이 현재 입력에 없어 연구계획을 구체화할 수 없던 상태가 기록 복원으로 해소되었다. 최초 연구계획은 아직 없다.',
               'evidence':json.dumps(fixture,ensure_ascii=False),
               'progress':'시험 자료에서 이전 사용자 발화 원문을 복원했다. 원문에 없는 성능·가격·효과를 조사하거나 확인하지 않았다. 원래 요청은 연구계획서 작성까지다.',
               'kind':'other'}
    (directory/'recovery_input.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    raw = execute_reframe(payload, controller.owner, controller.task)
    (directory/'recovery_response.json').write_text(raw+'\n')
    result = controller.framing
    (directory/'recovered_framing.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    plan = result.get('_research_plan')
    if plan:
        (directory/'recovered_plan.md').write_text(plan['body'])
    return {'revised':json.loads(raw).get('revised'),'has_plan':bool(plan),
            'owner':'consciousness' if plan else None,'fixture_source':'synthetic operator supplied recall result',
            'autonomous_executor_recall_or_reframe_tested':False}
