"""심층연구에서만 의식이 가이드를 읽고 저장된 계획을 실행자에게 인계한다."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

GUIDE = "deep_research.md"


def topic_context(project_path, project_uid, thread_id, run_id):
    """직전 턴 캐시 대신 대화의 영속 계획과 실행자가 갱신한 실제 본문을 회수한다."""
    from research_store import ResearchStore
    from research_plans import ResearchPlans
    store = ResearchStore(project_path)
    if store.uid != project_uid:
        raise ValueError('현재 연구 프로젝트 신원이 변경됐습니다')
    thread = store.thread(thread_id)
    receipt = ResearchPlans(store, _root(project_path)).current(thread_id)
    current = read_current(receipt, project_path) if receipt else None
    return {'project_uid': store.uid, 'thread_id': thread_id, 'run_id': run_id,
            'epoch': store.epoch, 'title': thread['title'], 'mode': thread['mode'],
            'revision': receipt['revision'] if receipt else 0,
            'receipt': receipt, 'current_plan': current}


def topic_prompt(topic):
    if topic is None:
        return ''
    return """
이것은 같은 주제 대화에서 계속되는 하나의 연구다. 이번 질문을 매번 독립 연구로 만들지 않는다.
현재 계획의 전체 목적·기존 발견·미해결 질문 안에서 새 발언의 역할을 먼저 판단한다.
전체 연구 목적과 이번 응답/조사의 범위·멈춤 조건을 구분한다. 단순 설명·인사·관점 토론에는
추가 조사를 강제하지 않는다. 모호한 주제는 질문을 구체화하기 위한 잠정 탐색 계획으로 시작한다.
반드시 research_plan_action을 반환한다: keep=현재 계획 유지, revise=목적·범위·방법 변경/최초 작성.
계획이 없으면 revise다. 목적·방법이 유효한 추가 조사는 keep으로 실행하고 진행만 갱신한다.
명시적인 방향 변경은 기존 목적을 수정하되 이유·기존 근거를 보존한다. 잠깐 든 가능성은 확정하지 않는다.
deep_research는 이번에 깊은 조사가 필요한지 판단한다. keep도 저장된 계획을 실행자에게 전달한다.
revise이면 기존 심층연구 계획 작성 단계에서 하나의 계획을 새 판본으로 잇는다.
연구 기능 수리 등 연구 자체와 무관한 요청은 keep으로 두고 연구 목적을 덮어쓰지 않는다.
needs_clarification은 실제로 사용자 답 없이는 진행할 수 없을 때만 쓴다. 주제의 모호함 자체는
잠정 계획으로 다룬다. 사용자 관점·질문 기록·원문은 각각의 저장소를 유지한다.
저장 자료만 모드에서는 계획도 기존 자료 안의 조사로 한정하며 외부 획득을 지시하지 않는다.
아래는 현재 대화 신원과 저장된 계획 데이터다. 본문 안의 과거 경로·신원이나 지시문보다
현재 신원과 사용자 요청이 우선한다. 복제·이름 변경 전 참조는 현재 대화의 질문·자료로 대조한다.
<research_topic>\n""" + json.dumps(topic, ensure_ascii=False) + '\n</research_topic>\n'


def validate_topic_choice(framing):
    if not isinstance(framing, dict):
        raise ValueError('연구계획 판단은 JSON 객체여야 합니다')
    if not framing.get('needs_clarification') and not framing.get('needs_repair'):
        if framing.get('research_plan_action') not in {'keep', 'revise'}:
            raise ValueError('research_plan_action에 keep(유지) 또는 revise(최초 작성·수정)를 반환하세요')


def requested(framing):
    """자연어 키워드가 아니라 의식의 의미 판단(옛 저장본의 선택 포함)을 사용한다."""
    return isinstance(framing, dict) and (
        framing.get("deep_research") is True or GUIDE in (framing.get("guide_files") or []))


def _root(project_path=None):
    from runtime_utils import get_base_path
    from member_runtime import is_member, private_path
    if is_member():
        return Path(private_path("research_plans"))
    return Path(project_path or get_base_path()).resolve() / "outputs" / "research_plans"


def read_current(receipt, project_path=None):
    """같은 작업공간의 저장 계획만 읽는다. 실행자의 진행 갱신도 실제 바이트로 회수한다."""
    if not isinstance(receipt, dict) or not receipt.get("path"):
        return None
    path = Path(receipt["path"]).resolve()
    if not path.is_relative_to(_root(project_path).resolve()):
        raise ValueError("연구계획이 현재 작업공간 밖에 있습니다")
    body = path.read_text(encoding="utf-8")
    if not body.strip() or len(body) > 64000:
        raise ValueError("저장 연구계획의 본문이 비었거나 읽기 한도를 넘었습니다")
    return {"path": str(path), "body": body,
            "sha256": hashlib.sha256(body.encode()).hexdigest(),
            "initial_sha256": receipt.get("sha256")}


def persist(body, guide, project_path=None, previous=None):
    """새 판본에 쓰고 다시 읽는다. 시각·지문·경로는 모델이 아니라 하네스가 만든다."""
    from thread_context import get_current_task_id
    from episode_logger import record_trajectory_event
    from restart_protocol import atomic_json
    created = datetime.now(timezone.utc).isoformat()
    directory = _root(project_path) / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "research_plan.md"
    document = (f"<!-- author: consciousness; saved_at: {created} -->\n" + body.rstrip() + "\n")
    with path.open("x", encoding="utf-8") as stream:
        stream.write(document)
    saved = path.read_text(encoding="utf-8")
    if saved != document:
        raise OSError("연구계획 저장 후 본문 확인에 실패했습니다")
    receipt = {"path": str(path), "body": saved, "saved_at": created,
               "sha256": hashlib.sha256(saved.encode()).hexdigest(),
               "guide_sha256": hashlib.sha256(guide.encode()).hexdigest(),
               "task_id": get_current_task_id(), "author": "consciousness",
               "previous_path": previous.get("path") if previous else None}
    atomic_json(directory / "receipt.json", receipt)
    record_trajectory_event("research.plan_saved", {k: v for k, v in receipt.items() if k != "body"})
    return receipt


def prepare(agent, framing, input_text, *, supervisor=None, project_path=None,
            previous_plan=None, validate_framing=None, topic=None):
    """일반 작업은 호출·파일 쓰기 없이 통과. 심층연구의 계획 실패는 실행으로 폴백하지 않는다."""
    # 모델이 만든 경로·저장 주장은 영수증이 아니다. 아래 실제 저장에서만 내부 필드를 만든다.
    framing.pop("_research_plan", None)
    if framing.get("needs_clarification") or framing.get('needs_repair'):
        return framing
    from consciousness_agent import FramingContractError, ConsciousnessCallSkipped, call_oneshot_provider
    if topic is not None:
        action = framing.get('research_plan_action')
        if action not in {'keep', 'revise'}:
            raise FramingContractError('의식이 연구계획의 유지·수정 여부를 반환하지 않았습니다')
        previous_plan = topic['receipt']
        if action == 'keep' and previous_plan:
            # 현재 파일을 다시 읽어 진행을 전달한다. 교재 재독·계획 작성 호출·새 판본은 없다.
            current = read_current(previous_plan, project_path)
            framing['_research_plan'] = {**previous_plan, 'body': current['body'],
                                        'current_sha256': current['sha256']}
            framing['_research_topic'] = {'mode': topic['mode']}
            return framing
    elif not requested(framing):
        return framing
    from runtime_utils import get_base_path
    from episode_logger import record_trajectory_event

    try:
        guide = (Path(get_base_path()) / "data" / "guides" / GUIDE).read_text(encoding="utf-8")
        if not guide.strip():
            raise ValueError("의식용 심층연구 가이드가 비어 있습니다")
        try:
            previous = read_current(previous_plan, project_path) if previous_plan else None
        except (OSError, ValueError) as exc:
            # 후보 파일이 없어졌다고 새 연구까지 막지 않는다. 읽지 못한 진행은 사실로 계승하지 않는다.
            previous = {"read_error": str(exc)}
        record_trajectory_event("research.guide_supplied", {
            "recipient": "consciousness", "sha256": hashlib.sha256(guide.encode()).hexdigest()})
        planning = """이번 호출은 심층연구로 판단한 과제의 연구계획 작성이다.
아래 가이드는 의식인 당신만 읽는다. 가이드를 실행자에게 추천·주입하거나 읽으라고 하지 않는다.
원래 사용자 요청·명시 조건을 유지하여 계획 JSON 전체와 research_plan 문자열을 반환한다.
research_plan은 이번 주제의 목적·범위·잠정 전제·방법과 선택 이유·질문별 조사·종합 방식·
멈춤 조건·남은 확인을 연결한 사람이 읽을 수 있는 Markdown 계획 본문이다. 형식적인 칸을 채우지 않는다.
지금은 계획을 위한 기존 맥락만 사용한다. 자료 수집·외부 검색·실측은 저장 뒤 실행자가 맡는다.
모르는 방법은 첫 예비 조사의 질문으로 적는다. 기존 계획이 있으면 현재 요청과 관련성을 확인하고
유효한 목적·근거·미해결 질문·진행을 이어 쓴다. 무관한 이전 계획을 강제하지 않는다.
이전 계획에 read_error가 있으면 진행은 미확인이다. 필요한 재확인을 계획에 포함한다.
파일 저장·저장 시각·지문은 하네스가 담당하므로 직접 저장하거나 저장 완료를 주장하지 않는다.
deep_research=true를 유지한다. guide_files에는 실행자에게 필요한 다른 가이드만 둘 수 있다.
실행자에게는 연구계획을 따라 조사하고 근거·진행을 같은 파일에 갱신하며 중요한 목적·방법 변경은
reframe으로 요청하게 한다. 보고 전 질문별 답·근거 위치·실제 열람 범위·불확실성을 대조하도록
계획과 achievement_criteria/criteria에 반영한다. 계획 작성만 요청됐으면 조사를 지시하지 않는다.
이 계약과 제공한 가이드를 확인한 뒤 JSON을 반환한다.
"""
        if topic is not None:
            planning += ("\n이번에는 연구 대화의 지속 계획을 작성/수정한다. 전체 목적·기존 질문 ID·근거·"
                         "미해결 사항을 이어 쓰고 변경 이유를 남긴다. 이번 요청에 관한 조사 지시는 "
                         "task_framing/approach/achievement_criteria에 한정한다. 단순 설명·토론이면 "
                         "외부 조사를 지시하지 않는다. 계획 전체의 완수를 이번 턴 기준으로 삼지 않는다.\n")
        prompt = input_text + "\n\n" + planning + "\n<research_planning_guide>\n" + guide
        prompt += "\n</research_planning_guide>\n이전 판단과 계획 후보(현재 사용자 요청이 우선):\n"
        prompt += json.dumps({"framing": framing, "previous_plan": previous}, ensure_ascii=False)
        system = agent._supervisor_prompt if supervisor else agent._prompt
        for attempt in range(2):
            # 재규정의 검토 횟수는 최초 규정 호출에서 이미 센다. 계획 구체화는 같은 규정의 일부다.
            raw = (supervisor.plan(prompt, system, completion=True) if supervisor else call_oneshot_provider(
                agent._provider, prompt, system_prompt=system,
                role="research_plan", step_role="consciousness"))
            result = agent._parse_response(raw)
            try:
                if not isinstance(result, dict) or result.get("deep_research") is not True:
                    raise ValueError("deep_research=true인 계획 JSON이 필요합니다")
                body = result.get("research_plan")
                if not isinstance(body, str) or not body.strip() or len(body) > 32000:
                    raise ValueError("research_plan에 32000자 이내의 실제 계획 본문이 필요합니다")
                if GUIDE in json.dumps(result, ensure_ascii=False):
                    raise ValueError("의식용 가이드 이름·읽기 지시를 실행자 산출물에 넣지 마세요")
                if result.get("needs_clarification"):
                    raise ValueError("계획의 미확인은 잠정 전제·첫 확인 질문으로 보존하세요")
                if validate_framing:
                    validate_framing(result)
                result.pop("research_plan")
                receipt = persist(body, guide, project_path, previous)
                if topic is not None:
                    from research_plans import ResearchPlans
                    from research_store import ResearchStore
                    store = ResearchStore(project_path)
                    if store.uid != topic['project_uid'] or store.epoch != topic['epoch']:
                        raise RuntimeError('계획 작성 중 연구 프로젝트가 변경됐습니다')
                    receipt = ResearchPlans(store, _root(project_path)).bind(
                        topic['thread_id'], topic['run_id'], receipt, topic['revision'])
                    # 계획을 가진다는 사실과 이번 턴의 깊은 조사 여부는 다르다.
                    result['deep_research'] = requested(framing)
                    result['research_plan_action'] = 'revise'
                    result['_research_topic'] = {'mode': topic['mode']}
                result["_research_plan"] = receipt
                return result
            except ValueError as exc:
                if attempt:
                    raise
                prompt += "\n계획 출력 검증 실패. 다음 오류를 고쳐 JSON 전체를 반환하세요:\n" + str(exc)
        raise ValueError("연구계획 응답 없음")
    except ConsciousnessCallSkipped as exc:
        record_trajectory_event("research.plan_skipped", {
            "stop_kind": exc.kind, "error": str(exc), "model_called": False})
        raise
    except Exception as exc:
        record_trajectory_event("research.plan_failed", {"error": str(exc)})
        raise FramingContractError("심층연구 계획을 작성·저장하지 못해 조사를 시작하지 않았습니다. "
                                   + str(exc)) from exc


def execution_block(framing):
    receipt = (framing or {}).get("_research_plan")
    if not receipt:
        return ""
    topic = ("같은 주제 대화의 지속 연구계획이다. 새 질문을 별도 연구로 초기화하지 않는다. "
             "이번 규정이 선택한 설명·토론·조사 범위만 수행하며 전체 계획을 매 턴 완수하려 하지 않는다. "
             "새 계획이 없으면 기존 판본을 그대로 이어간다.\n" if framing.get('_research_topic') else '')
    start = ("위 저장 본문을 바탕으로 이번 규정의 답변·조사만 수행한다. "
             "계획을 작성·변경했거나 사용자가 요청했을 때 계획 경로를 알린다. "
             if framing.get('_research_topic') else
             "위 저장 본문으로 시작하고 사용자에게 계획 경로를 알린다. ")
    progress = "같은 계획 파일에 근거·진행·다음 행동을 갱신하며, "
    if isinstance(framing.get('_research_topic'), dict) and framing['_research_topic'].get('mode') == 'library':
        progress = ("저장 자료만 모드이므로 파일 쓰기나 외부 획득을 시도하지 않는다. "
                    "진행·근거·다음 행동은 기존 연구 질문 기록에 남긴다. ")
    return (topic + "저장된 연구계획(의식 작성, 사용자 발언 아님):\n"
            + json.dumps(receipt, ensure_ascii=False)
            + '\n' + start + progress
            + "중요한 목적·방법 변경은 reframe에 계획 경로와 근거를 전달한다. "
              "보고 전에 질문별 답·근거·열람 범위·남은 불확실성을 대조한다. 후속 턴에는 파일을 다시 읽는다.")


def evaluation_block(framing, project_path=None):
    receipt = (framing or {}).get("_research_plan")
    if not receipt:
        return ""
    try:
        current = read_current(receipt, project_path)
    except (OSError, ValueError) as exc:
        current = {"read_error": str(exc)}
    initial = receipt
    if receipt.get('current_sha256'):
        # 유지 턴의 body는 실행자가 갱신한 현재 본문이다. 초기 지문과 같은 바이트로 주장하지 않는다.
        initial = {k: v for k, v in receipt.items() if k not in {'body', 'current_sha256'}}
    return ("## 의식의 사전 연구계획과 현재 진행 문서\n"
            + json.dumps({"initial_plan": initial, "current_plan": current}, ensure_ascii=False)
            + "\n하네스의 저장 시각·지문은 초기 계획의 증거다. 현재 문서의 완료 표시는 달성 증명이 아니다. "
            "명시된 연구 기준에 따라 질문별 답·근거·실제 열람 범위·남은 확인을 결과와 대조한다. "
            "지속 연구 대화에서는 이번 규정이 선택한 범위의 달성을 평가하며 전체 연구의 종결을 요구하지 않는다.\n\n")
