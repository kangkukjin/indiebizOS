"""의식의 연구 설계와 저장·인계. 실행자는 조사·세부 조정·진행 갱신을 맡는다."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

GUIDE = "deep_research.md"
EXECUTION_GUIDE = "research_execution.md"

PLANNING_PROMPT = """이번 출력은 실행자가 읽고 바로 첫 조사를 시작할 수 있는 짧은 착수 메모다.
보통 한 화면에서 읽을 수 있는 몇 문단의 산문으로, 가장 중요한 판단 갈림길과 첫 확인에 집중한다.
사용자가 상세 설계를 명시한 경우에만 연구 프로토콜 수준으로 펼친다. 계획만 요청했다는 이유로
상세 제안서·방법론 교과서·가능한 모든 분석의 목록을 작성하지 않는다.
질문·가설·근거·방법을 여러 절에서 되풀이하지 말고 같은 판단의 연결 안에서 한 번 설명한다.
당신은 연구를 설계하는 의식 에이전트다.
사용자 원래 목적·명시 조건과 관련 맥락을 기준으로 제공된 심층연구 가이드를 읽고,
해당 분야 전문가라면 이 문제를 어떻게 구성하고 조사할지 생각해 연구계획을 작성한다.
핵심 질문·불확실성, 경쟁 설명을 가를 증거와 바뀌는 판단, 첫 조사를 이유와 함께 간결하게 연결한다.
전달된 접근 힌트는 유효한 내용을 계획에 통합하고 반복하지 않는다. 방법 이름·절차 목록으로 대신하지 않는다.
기존 계획·확보한 근거·진행을 보존하며 필요한 부분만 고친다. 전문가의 접근은 잠정 설계이며
사용자 요구나 추가 합격 조건이 아니다. 모르는 방법·자료 접근성은 예비 조사의 질문으로 남긴다.
요청 규정·기준에 AI가 덧붙인 방법 목록이 있어도 사용자 원문의 요구와 구별해 잠정 후보로 판단한다.
아직 수행하지 않은 조사·열람·검증을 완료했다고 쓰지 않는다. 계획만 요청했으면 수행을 지시하지 않는다.
저장 자료만 모드에서는 기존 자료 안에서 계획한다. 계획이 새로운 권한을 부여하지 않는다.
실행자는 첫 자료를 본 뒤 방법·조사 범위·멈춤을 판단한다. 사용자 명시 조건은 유지한다.
미확인 출처·지표는 후보로 남기고, 보고서 목차·표 형식·상세 후속 절차는 필요할 때만 정한다.
자료가 확보되기 전의 추정 모형·통제변수·강건성 검사까지 설계하지 말고, 어느 자료 조건이면
어떤 접근이 유효할지 판단의 이유를 남긴다. 사용자가 상세 설계를 명시한 경우에는 그 범위를 따른다.
일반 실행·표기 규칙은 실행자에게 직접 제공되므로 계획에 옮겨 적지 않는다.
중요한 발견·변경은 같은 계획에 갱신하며 작은 조정은 재승인받지 않는다.
현재 요청에 맞는 계획 본문만 Markdown으로 반환한다. JSON·출력용 코드펜스·파일 저장 주장은 불필요하다.
필요한 답의 수준과 중요한 공백을 드러내되 고정된 절·질문 수나 분량은 없다.
"""


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
    return ("기존 연구 문맥이다. 사용자 목적과 이번 요청의 관계, 전문가의 접근을 판단한다. "
            "현재 계획이 유효하면 재사용한다. 전체 목적·접근을 다시 설계해야 할 때만 "
            "revise_research_plan=true로 표시한다. 작은 방법 조정·진행 갱신은 실행자가 맡는다.\n<research_topic>\n"
            + json.dumps(topic, ensure_ascii=False) + '\n</research_topic>\n')


def requested(framing):
    """자연어 키워드가 아니라 의식의 의미 판단(옛 저장본의 선택 포함)을 사용한다."""
    return isinstance(framing, dict) and (
        framing.get("deep_research") is True or any(
            _planning_guide(name) for name in (framing.get("guide_files") or [])))


def _planning_guide(name):
    """가이드 선택의 경로 표기도 같은 교재로 해소하며 임의 경로를 열지는 않는다."""
    return isinstance(name, str) and name.replace('\\', '/').rsplit('/', 1)[-1] == GUIDE


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


def persist(body, guide, project_path=None, previous=None, *, exact=False, metadata=None):
    """새 판본에 쓰고 다시 읽는다. 시각·지문·경로는 모델이 아니라 하네스가 만든다."""
    from thread_context import get_current_task_id
    from episode_logger import record_trajectory_event
    from restart_protocol import atomic_json
    created = datetime.now(timezone.utc).isoformat()
    directory = _root(project_path) / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "research_plan.md"
    document = body if exact else (f"<!-- author: consciousness; saved_at: {created} -->\n" + body.rstrip() + "\n")
    with path.open("x", encoding="utf-8") as stream:
        stream.write(document)
    saved = path.read_text(encoding="utf-8")
    if saved != document:
        raise OSError("연구계획 저장 후 본문 확인에 실패했습니다")
    receipt = {"path": str(path), "body": saved, "saved_at": created,
               "sha256": hashlib.sha256(saved.encode()).hexdigest(),
               "guide_sha256": hashlib.sha256(guide.encode()).hexdigest(),
               "task_id": get_current_task_id(), "author": "consciousness",
               "previous_path": previous.get("path") if previous else None, **(metadata or {})}
    atomic_json(directory / "receipt.json", receipt)
    record_trajectory_event("research.plan_saved", {k: v for k, v in receipt.items() if k != "body"})
    return receipt


def prepare(agent, framing, input_text, *, supervisor=None, project_path=None,
            previous_plan=None, validate_framing=None, topic=None):
    """유효한 계획은 재사용한다. 최초·중요 개정만 의식이 가이드를 읽고 한 번 작성한다."""
    framing = dict(framing)
    framing.pop("_research_plan", None)
    revise = framing.pop("revise_research_plan", False)
    if framing.get("needs_clarification") or framing.get("needs_repair"):
        return framing
    previous = (topic or {}).get("receipt") or previous_plan
    if not previous and not requested(framing):
        return framing
    cancelled = getattr(supervisor, "cancelled", lambda: False)
    if cancelled():
        from consciousness_agent import ConsciousnessCallSkipped
        raise ConsciousnessCallSkipped("cancelled", "연구 문서 인계 전에 실행이 종료됐습니다")
    if previous:
        current = read_current(previous, project_path)
        receipt = {**previous, "body": current["body"], "current_sha256": current["sha256"]}
    if not previous or revise:
        receipt = plan_once(agent, framing, input_text, supervisor=supervisor,
                            project_path=project_path, topic=topic,
                            previous={**receipt, "sha256": current["sha256"]} if previous else None,
                            cancelled=cancelled)
        # 새 계획이 접근을 통합했다. 재사용 턴의 새 하위 질문 힌트는 그대로 보존한다.
        framing.pop("capability_focus", None)
    framing["_research_plan"] = receipt
    if topic:
        framing["_research_topic"] = {"mode": topic["mode"]}
    # 실행자에게는 주제별 계획을 전달한다. 명시적인 가이드 조회는 금지하지 않는다.
    if "guide_files" in framing:
        framing["guide_files"] = [g for g in framing["guide_files"] if not _planning_guide(g)]
    return framing


def plan_once(agent, framing, input_text, *, supervisor, project_path, topic, previous, cancelled):
    """계획 본문 한 번 작성. 형식 보정·재심사·저장 실패 후 재생성 루프는 두지 않는다."""
    from consciousness_agent import FramingContractError, call_oneshot_provider
    from episode_logger import record_trajectory_event
    from runtime_utils import get_base_path
    if agent is None:
        raise ValueError("새 연구계획은 의식의 가이드 기반 작성이 필요합니다")
    guide = (Path(get_base_path()) / "data" / "guides" / GUIDE).read_text(encoding="utf-8")
    if not guide.strip():
        raise ValueError("심층연구 가이드가 비어 있습니다")
    context = {"framing": framing, "previous_plan": previous,
               "topic": {k: v for k, v in (topic or {}).items() if k not in {"receipt", "current_plan"}}}
    prompt = (input_text + "\n<research_context>\n" + json.dumps(context, ensure_ascii=False)
              + "\n</research_context>\n<research_planning_guide>\n" + guide
              + "\n</research_planning_guide>")
    record_trajectory_event("research.guide_supplied", {
        "recipient": "consciousness", "sha256": hashlib.sha256(guide.encode()).hexdigest()})
    try:
        body = (supervisor.plan(prompt, PLANNING_PROMPT, completion=True) if supervisor else
                call_oneshot_provider(agent._provider, prompt, system_prompt=PLANNING_PROMPT,
                                      role="research_plan", step_role="consciousness"))
    except Exception as exc:
        from consciousness_agent import ConsciousnessCallSkipped
        if isinstance(exc, ConsciousnessCallSkipped):
            raise
        raise FramingContractError("의식의 연구계획 작성에 실패했습니다") from exc
    if not isinstance(body, str) or not body.strip() or len(body) > 64000:
        raise ValueError("의식의 연구계획 본문이 비었거나 읽기 한도를 넘었습니다")
    return publish_plan(body, guide, project_path, previous, topic, cancelled)


def revision_context(framing, runner, project_path):
    """감사가 판단할 실제 계획 판본. 보관된 초기 본문으로 진행을 덮어쓰지 않는다."""
    loader = getattr(runner, "_research_planning_context", None)
    topic = loader() if loader else None
    if topic is not None:
        return topic
    receipt = (framing or {}).get("_research_plan")
    return {"receipt": receipt, "current_plan": read_current(receipt, project_path)} if receipt else None


def publish_plan(body, guide, project_path, previous=None, topic=None, cancelled=lambda: False):
    """현재 출처를 확인하고 새 파일 판본을 게시한다. 기존 파일은 수정하지 않는다."""
    if cancelled():
        raise ValueError("연구계획 게시 전에 실행이 종료됐습니다")
    if previous and previous.get("sha256"):
        current = read_current(previous, project_path)
        if current["sha256"] != previous["sha256"]:
            raise ValueError("연구계획 본문이 변경됐습니다. 최신 판본으로 판단해야 합니다")
    receipt = persist(body, guide, project_path, previous)
    if cancelled():
        raise ValueError("연구계획 게시 전에 실행이 종료됐습니다")
    if topic and topic.get("thread_id"):
        from research_plans import ResearchPlans
        from research_store import ResearchStore
        store = ResearchStore(project_path)
        if store.uid != topic['project_uid'] or store.epoch != topic['epoch']:
            raise RuntimeError('계획 작성 중 연구 프로젝트가 변경됐습니다')
        expected = (previous['path'], previous['sha256']) if previous and previous.get('sha256') else None
        receipt = ResearchPlans(store, _root(project_path)).bind(
            topic['thread_id'], topic['run_id'], receipt, topic['revision'], expected_source=expected)
    return receipt


def apply_revision_plan(framing, update, topic, project_path, cancelled=lambda: False):
    """새 요청에 현재 작업 문서를 연결한다. 늦은 관측은 채택하지 않는다."""
    previous = (topic or {}).get("receipt")
    source = (topic or {}).get("current_plan")
    if cancelled():
        raise ValueError("종료된 실행의 연구계획은 변경하지 않습니다")
    if not previous:
        from types import SimpleNamespace
        return prepare(None, framing, "", project_path=project_path, topic=topic,
                       supervisor=SimpleNamespace(cancelled=cancelled))
    if previous:
        current = read_current(previous, project_path)
        if not source or current['sha256'] != source['sha256']:
            raise ValueError("판단 후 연구계획 본문이 변경됐습니다")
        if topic.get('thread_id'):
            from research_plans import ResearchPlans
            from research_store import ResearchStore
            store = ResearchStore(project_path)
            if store.uid != topic['project_uid'] or store.epoch != topic['epoch']:
                raise ValueError("연구 프로젝트가 변경됐습니다")
            ResearchPlans(store, _root(project_path)).check_source(
                topic['thread_id'], topic['run_id'], topic['revision'], source['path'], source['sha256'])
    receipt = {**previous, "body": source['body'], "current_sha256": source['sha256']}
    result = {**framing, "_research_plan": receipt}
    result.pop("research_plan", None)
    result.pop("research_plan_patch", None)
    if topic and topic.get('thread_id'):
        result['_research_topic'] = {'mode': topic['mode']}
    return result


def execution_block(framing):
    receipt = (framing or {}).get("_research_plan")
    if not receipt:
        return ""
    from prompt_builder import get_prompt_builder
    guide = get_prompt_builder()._guide_block(EXECUTION_GUIDE)
    if not guide:
        guide = (f"연구 실행 지침 미제공: read_guide로 {EXECUTION_GUIDE}를 확인한다. "
                 "읽지 못한 지침을 확인했다고 말하지 않는다.")
    library = (framing.get("_research_topic") or {}).get("mode") == "library"
    instruction = ("저장 자료만 모드다. 기존 자료로 답하고 파일 쓰기·외부 획득은 하지 않는다." if library else
                   "전달된 연구계획을 출발점으로 첫 자료를 확인하고 방법·범위·멈춤을 조정한다. "
                   "사용자 명시 조건을 보존하고 중요한 발견·변경을 같은 문서에 갱신한다. "
                   "계획을 처음부터 중복 작성하거나 작은 방법 조정마다 재승인받지 않는다. "
                   "전체 목적·접근을 다시 설계해야 할 때는 근거와 함께 reframe으로 의식에 전달한다. "
                   "현재 사용자 요청에 필요한 범위만 수행하며 계획만 요청했으면 계획을 전달하고 마친다.")
    return ("연구계획(사용자 요구를 대체하지 않는 잠정 설계·진행 기록):\n"
            + json.dumps(receipt, ensure_ascii=False) + "\n" + instruction + "\n\n" + guide)
