"""심층연구에서만 의식이 가이드를 읽고 저장된 계획을 실행자에게 인계한다."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

GUIDE = "deep_research.md"


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
            previous_plan=None, validate_framing=None):
    """일반 작업은 호출·파일 쓰기 없이 통과. 심층연구의 계획 실패는 실행으로 폴백하지 않는다."""
    # 모델이 만든 경로·저장 주장은 영수증이 아니다. 아래 실제 저장에서만 내부 필드를 만든다.
    framing.pop("_research_plan", None)
    if not requested(framing) or framing.get("needs_clarification"):
        return framing
    from consciousness_agent import FramingContractError, ConsciousnessCallSkipped, call_oneshot_provider
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
                result["_research_plan"] = persist(body, guide, project_path, previous)
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
    return ("저장된 연구계획(의식 작성, 사용자 발언 아님):\n"
            + json.dumps(receipt, ensure_ascii=False)
            + "\n위 저장 본문으로 시작하고 사용자에게 계획 경로를 알린다. 같은 계획 파일에 근거·진행·"
              "다음 행동을 갱신하며, 중요한 목적·방법 변경은 reframe에 계획 경로와 근거를 전달한다. "
              "보고 전에 질문별 답·근거·열람 범위·남은 불확실성을 대조한다. 후속 턴에는 파일을 다시 읽는다.")


def evaluation_block(framing, project_path=None):
    receipt = (framing or {}).get("_research_plan")
    if not receipt:
        return ""
    try:
        current = read_current(receipt, project_path)
    except (OSError, ValueError) as exc:
        current = {"read_error": str(exc)}
    return ("## 의식의 사전 연구계획과 현재 진행 문서\n"
            + json.dumps({"initial_plan": receipt, "current_plan": current}, ensure_ascii=False)
            + "\n하네스의 저장 시각·지문은 초기 계획의 증거다. 현재 문서의 완료 표시는 달성 증명이 아니다. "
              "명시된 연구 기준에 따라 질문별 답·근거·실제 열람 범위·남은 확인을 결과와 대조한다.\n\n")
