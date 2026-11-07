"""연구 작업 문서의 저장·판본 전달. 계획 작성과 갱신은 실행자가 맡는다."""
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
    return ("같은 주제의 연구 문맥이다. 사용자 목적과 이번 요청의 관계를 정리한다. "
            "계획 작성·방법 선택·진행 갱신은 실행자가 맡는다.\n<research_topic>\n"
            + json.dumps(topic, ensure_ascii=False) + '\n</research_topic>\n')


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


def persist(body, guide, project_path=None, previous=None, *, exact=False, metadata=None):
    """새 판본에 쓰고 다시 읽는다. 시각·지문·경로는 모델이 아니라 하네스가 만든다."""
    from thread_context import get_current_task_id
    from episode_logger import record_trajectory_event
    from restart_protocol import atomic_json
    created = datetime.now(timezone.utc).isoformat()
    directory = _root(project_path) / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "research_plan.md"
    document = body if exact else (f"<!-- author: execution; saved_at: {created} -->\n" + body.rstrip() + "\n")
    with path.open("x", encoding="utf-8") as stream:
        stream.write(document)
    saved = path.read_text(encoding="utf-8")
    if saved != document:
        raise OSError("연구계획 저장 후 본문 확인에 실패했습니다")
    receipt = {"path": str(path), "body": saved, "saved_at": created,
               "sha256": hashlib.sha256(saved.encode()).hexdigest(),
               "guide_sha256": hashlib.sha256(guide.encode()).hexdigest(),
               "task_id": get_current_task_id(), "author": "execution",
               "previous_path": previous.get("path") if previous else None, **(metadata or {})}
    atomic_json(directory / "receipt.json", receipt)
    record_trajectory_event("research.plan_saved", {k: v for k, v in receipt.items() if k != "body"})
    return receipt


def prepare(agent, framing, input_text, *, supervisor=None, project_path=None,
            previous_plan=None, validate_framing=None, topic=None):
    """기존 문서를 인계하거나 실행자가 쓸 작업 메모를 연다. 모델 호출은 없다."""
    framing = dict(framing)
    framing.pop("_research_plan", None)
    if framing.get("needs_clarification") or framing.get("needs_repair"):
        return framing
    previous = (topic or {}).get("receipt") or previous_plan
    if not previous and topic is None and not requested(framing):
        return framing
    cancelled = getattr(supervisor, "cancelled", lambda: False)
    if cancelled():
        from consciousness_agent import ConsciousnessCallSkipped
        raise ConsciousnessCallSkipped("cancelled", "연구 문서 인계 전에 실행이 종료됐습니다")
    if previous:
        current = read_current(previous, project_path)
        receipt = {**previous, "body": current["body"], "current_sha256": current["sha256"]}
    else:
        # 요청은 출발 메모다. 모델이 작성한 사전 계획으로 표시하지 않는다.
        body = "# 연구 작업 메모\n\n" + framing.get("task_framing", "") + "\n"
        receipt = publish_plan(body, "", project_path, topic=topic, cancelled=cancelled)
    framing["_research_plan"] = receipt
    if topic:
        framing["_research_topic"] = {"mode": topic["mode"]}
    if requested(framing):
        framing["guide_files"] = list(dict.fromkeys([GUIDE, *framing.get("guide_files", [])]))
    return framing


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
    library = (framing.get("_research_topic") or {}).get("mode") == "library"
    instruction = ("저장 자료만 모드다. 기존 자료로 답하고 파일 쓰기·외부 획득은 하지 않는다." if library else
                   "실행자가 필요한 계획을 작성하고 같은 문서에 방법·진행을 갱신한다. "
                   "현재 사용자 요청에 필요한 범위만 수행한다.")
    return ("연구 작업 문서(사용자 요구가 아닌 실행 메모):\n"
            + json.dumps(receipt, ensure_ascii=False) + "\n" + instruction)
