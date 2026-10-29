"""api_ibl.py - IBL 직접 실행 API (MCP/외부 도구용 + 수동 모드 컴파일러 프론트엔드)"""
import json
import os
import re
import unicodedata
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, model_validator

router = APIRouter(prefix="/ibl", tags=["ibl"])
from api_supervision import router as supervision_router
router.include_router(supervision_router)


class TodoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: str
    task_id: str
    todos: list


@router.post("/todo")
async def todo_write(req: TodoRequest):
    import asyncio
    from todo_bridge import execute
    return await asyncio.to_thread(execute, req.todos, req.agent_id, req.task_id)


class IBLRequest(BaseModel):
    # An ignored reuse/approval typo can execute a different, costly request.
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def discard_retired_display_option(cls, value):
        # Saved clients may still send the retired display-only switch. It has
        # no execution semantics; every other undeclared key remains an error.
        if isinstance(value, dict) and "verbose" in value:
            return {key: item for key, item in value.items() if key != "verbose"}
        return value

    code: str
    edition: Optional[int] = None
    inputs: Optional[dict] = None
    # 표면 바인딩(2026-10-05 ①): 앱 템플릿이 참조하는 입력 이름 전부. inputs 에 없는 이름 = 미지정
    # (호출 인자 생략·보간 ""). 렌더러가 치환 대신 원문 + inputs + declared_inputs 를 보낸다.
    declared_inputs: Optional[List[str]] = None
    # 사람 승인 토큰(② 권한 연결, 2026-10-05): human_confirm 액션이 approval_required 를 돌려주면 표면이 /ibl/approve 로
    # 토큰을 받아 같은 요청(code·inputs 동일 = 같은 지문)에 실어 재전송한다. 관문이 1회 소비.
    approval: Optional[str] = None
    value_protocols: Optional[List[str]] = None
    function_refs: Optional[List[dict]] = None
    composition: Optional[str] = None
    completion: Optional[List[dict]] = None
    repair: Optional[dict] = None
    describe: Optional[List[str]] = None
    read_result: Optional[dict] = None
    check: bool = False                # 현재 컴파일러의 정적 검사만 수행(실행 없음)
    resume: Optional[dict] = None      # 현재 실행 영수증 {run_id}로 같은 프로그램을 재개.
    reuse: Optional[dict] = None       # 고친 프로그램이 이전 실행 {run_id}의 읽기 영수증을 재사용(2026-09-26).
    code_edits: Optional[List[dict]] = None  # code 가 $checked·$rejected 참조일 때 그 원문의 조각 치환(긴문장 L18-7).
    budget: Optional[dict] = None      # 판본 2 요청 단위 steps/rows 상한.
    project_id: Optional[str] = None   # 수동/앱 모드 등 표면이 자기 프로젝트를 지정
    project_path: str = "."
    agent_id: Optional[str] = None     # 발신 신원(channel_send/read 게이트). out-of-process 프로바이더(Claude Code)가
                                       # MCP→HTTP로 자기 agent_id를 실어 보내는 통로. None이면 신원 없음(외부 채널 차단).
    task_id: Optional[str] = None      # 태스크 컨텍스트(위임 체인). claude_code 재진입 경로는 원 요청과 다른
                                       # 스레드라 threading.local의 task_id가 비어 [others:delegate]{scope:"cross"}가
                                       # "현재 태스크 ID 없음"으로 실패했다 → agent_id처럼 payload로 복원 (없으면 현 동작 그대로).
    origin: Optional[str] = None       # 태스크 출처('user'=사람의 직접 명령). claude_code 재진입 봉투가
                                       # 부모의 task_origin 을 실어 보내는 통로(task_id 와 같은 부류) —
                                       # 없던 시절 아웃오브프로세스 실행의 쓰기가 전부 무출처로 원장에
                                       # 남았다(2026-08-21 실측). 미지정+무신원(직접 표면)이면 'user'.
    surface: Optional[str] = None      # 요청한 *표면* ('web' = 원격런처/포털/폰 WebView).
                                       # 소리·저장 같은 "어디서 나야 하는가"의 판정 축 — 실행하는 몸이
                                       # 아니라 보고 있는 표면이 정한다(thread_context.set_current_surface).
                                       # 데스크탑 일렉트론은 맥 자신이라 보내지 않는다(= 맥 재생이 곧 여기서 재생).
    episode_id: Optional[int] = None   # 부모 에피소드 신원(궤적 척추, 2026-08-29). claude_code 재진입은
                                       # 원 요청과 다른 스레드/프로세스라 contextvar 의 episode 가 안 보여,
                                       # 이 실행의 ibl.*·side_effect.* 사건이 전부 고아 run 으로 남았다
                                       # (실측 98.4%) → task_id 와 같은 통로(env/헤더→payload)로 복원.
    parent_run_id: Optional[str] = None  # 부모 run(에피소드의 run_id) — 자식 run 의 parent_run_id 로
                                       # 실려 "이 실행이 어느 턴의 일부였나" 조인을 닫는다. episode_id 와 한 쌍.
    completion_channel: Optional[str] = None  # 전송 계층의 취소/생존 채널, 모델 인자 아님
    ticket: Optional[str] = None       # ★표면 티켓(F51-1, 2026-08-27) — 표면의 HTTP 대기가 실행보다
                                       # 먼저 끊겨도 최종 봉투를 잃지 않는 통로. 실리면 시작·결말을
                                       # data/spill/ 에 남기고(/ibl/recover 로 회수), hex 8~32자만
                                       # 받는다(네트워크 값이 파일명이 된다 — common.spill.valid_ticket).
                                       # agent_id·task_id 와 같은 **전송 계층 필드**라 도구 스키마
                                       # (tool_loader)에는 없는 것이 맞다(B23-1 드리프트 아님 —
                                       # 모델이 아니라 표면(mcp_server)이 생성·소비한다).


class EmbedRequest(BaseModel):
    """폰-자아 해마 인코더 렌트(PHONE_SELF_HOSTING_HANDOFF §6.3): 텍스트→768벡터.
    단건은 text, 배치는 texts. 둘 다 오면 texts 우선."""
    text: Optional[str] = None
    texts: Optional[List[str]] = None


class GuideRequest(BaseModel):
    """가이드 읽기 — **claude_code(아웃오브프로세스 MCP) 프로바이더 전용 브리지**.

    in-process 프로바이더(Gemini 등)는 system_tools 의 read_guide → search_guide 를
    같은 프로세스에서 직접 부른다(이미 동작). 그러나 claude_code 는 MCP 브리지(execute_ibl)
    로만 백엔드에 닿아 가이드 읽기 통로가 없었다 — 그래서 read_guide 호출이
    'No such tool available' 로 실패하고 file_find+경로 하드코딩으로 우회하던 문제(헛걸음).
    이 엔드포인트가 그 통로다. read_guide 를 IBL 어휘(노드/액션)로 승격하지 않는 이유=
    그러면 모든 프로바이더의 IBL 표면에 퍼져 '보편화'되기 때문 — claude_code 결손만 메운다."""
    query: str
    read: bool = True
    if_hash: Optional[str] = None
    section: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None


class ReframeRequest(BaseModel):
    """턴 안 재규정 — claude_code(아웃오브프로세스 MCP) 브리지. GuideRequest 와 같은 이유·같은 모양."""
    broken_assumption: str
    evidence: str
    progress: str = ""
    kind: str = "other"
    agent_id: Optional[str] = None
    task_id: Optional[str] = None


class TranslateRequest(BaseModel):
    """수동 모드: 자연어 의도 → IBL 코드 번역 요청"""
    intent: str
    allowed_nodes: Optional[List[str]] = None  # None이면 전체 노드 허용


class ValidateRequest(BaseModel):
    """수동 모드: dry-run 검증 요청 (실행하지 않고 효과만 미리보기)"""
    code: str
    edition: Optional[int] = None
    inputs: Optional[dict] = None
    declared_inputs: Optional[List[str]] = None


class DistillRequest(BaseModel):
    """수동 모드: 성공한 실행을 해마에 증류(학습)하는 요청.

    top_score = 번역 시 해마가 내놓은 최고 참조 점수. 임계값(0.7) 미만일 때만
    증류된다 — 해마가 이미 잘 아는 패턴은 다시 학습하지 않는다."""
    intent: str
    code: str
    task_ref: dict
    top_score: float = 0.0

class ApproveRequest(BaseModel):
    """사람 승인(② 권한 연결): human_confirm 액션이 돌려준 approval_required.challenge 에 대해 토큰을 발급한다."""
    challenge: str


@router.post("/approve")
async def approve_ibl(req: ApproveRequest, request: Request):
    """사람 통로 전용 — 런처 세션(원격) 또는 로컬 브라우저 출처(데스크탑)만 통과(api_vocabulary.human_authority 와 같은 판정).
    IBL 안에서는 부를 수 없다(에이전트의 도구는 execute_ibl 하나). 토큰은 challenge 에 묶여 1회·120초."""
    from api_vocabulary import human_authority
    human_authority(request)
    import approval_tokens
    try:
        return {"success": True, **approval_tokens.issue(req.challenge)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/capabilities")
async def ibl_capabilities():
    from ibl_v2_entry import capabilities
    return capabilities()


@router.post("/call")
async def call_ibl_leaf(payload: dict):
    from starlette.concurrency import run_in_threadpool
    from project_manager import ProjectManager
    from ibl_remote_call import receive
    path = ProjectManager().get_project_path("앱모드")
    return await run_in_threadpool(receive, payload, str(path))


@router.post("/execute")
async def execute_ibl_code(req: IBLRequest):
    # 표면 티켓(F51-1) — 시작 표식은 실행 전에, 결말 표식은 모든 출구(성공 2·예외 1)에서.
    # 검증은 try 밖: 형식 오류는 실행 이전의 요청 결함이라 400 이 맞고, 아래 except 가
    # HTTPException 을 500 으로 다시 싸는 것을 피한다.
    from common.spill import valid_ticket, ticket_begin, ticket_finish
    if req.ticket is not None and not valid_ticket(req.ticket):
        raise HTTPException(status_code=400, detail="ticket 형식은 hex 8~32자입니다.")
    if req.ticket:
        ticket_begin(req.ticket)
    try:
        # project_id가 오면 절대경로로 해소해 project_path로 넘긴다 (해소 우선순위 1 — race 없음).
        # 활성 프로젝트 컨텍스트가 없는 수동/앱 모드 호출이 프로젝트 경로를 확보하는 통로.
        from project_manager import ProjectManager
        project_path = req.project_path
        if req.project_id:
            p = ProjectManager().get_project_path(req.project_id)
            # 시스템 프로젝트(앱/수동 모드)는 경로 홀더라, 부팅 provisioning이 누락됐거나
            # 폴더가 지워졌어도 여기서 즉석 보장(멱등 mkdir, json 읽기 없음)해 자가 치유한다.
            if p is not None and not p.exists() and req.project_id in ProjectManager.SYSTEM_PROJECT_IDS:
                p.mkdir(parents=True, exist_ok=True)
            if p is None or not p.is_dir():
                message = f"지정한 프로젝트를 찾을 수 없습니다: {req.project_id}. 프로젝트 ID를 확인하세요."
                result = {"success": False, "ok": False, "executed": False,
                          "status": "invalid", "error": message,
                          "diagnostic": {"code": "PROJECT_NOT_FOUND", "kind": "runtime",
                                         "message": message,
                                         "details": {"project_id": req.project_id}}}
                if req.ticket:
                    ticket_finish(req.ticket, result)
                return result
            project_path = str(p.resolve())

        # 직접조작 표면(앱/수동 모드·직접 호출)은 소유자가 직접 모는 것 = 시스템 운영자.
        # agent_id가 비어 있으면 system_ai 신원으로 채널 발신·수신(메신저 작성·커뮤니티 게시·
        # channel_read)을 허용한다. (이 표면은 데스크탑=localhost 또는 원격=런처 인증 게이트
        # 뒤에 있음.) ★2026-08-20 상상훈련 17회차 판정: 시스템 프로젝트 한정이던 기본 신원을
        # 전 직접 호출로 확장 — 이 엔드포인트에 닿는 경로는 전부 소유자 게이트 뒤라, 무신원
        # 기본값은 보호가 아니라 정직한 조회(channel_read)까지 막는 마찰이었다(8회차 관찰③).
        agent_id = req.agent_id or "system_ai"

        # 직접조작 표면은 thread_context에 자기 project_id를 명시한다.
        # thread_context 는 thread-local 이라, 워커 스레드 풀에선 직전 호출이 남긴
        # project_id 가 남아 있을 수 있다(누수) — 덮어쓰고 호출 후 이전 값으로 복원.
        # scope 판단(예: lecture 저장 위치=프로젝트 vs 전역)이 엉뚱한 프로젝트로
        # 새는 것을 막는다.
        # ★실행은 워커 스레드에서(asyncio.to_thread) — 블로킹 핸들러(예: guestpc 가
        # phone_jobs.wait_result 로 손발 회신을 동기 대기)가 이벤트 루프 위에서 돌면,
        # 그 대기를 풀어줄 /limb/poll·/phone 요청 자체를 서버가 못 받아 자기교착한다
        # (창고 폴러 anyio.to_thread 선례와 같은 부류). thread-local set/restore 는
        # 같은 스레드 안에서 해야 하므로 래퍼째 내린다.
        from thread_context import (set_current_project_id, get_current_project_id,
                                    set_current_surface, get_current_surface,
                                    set_call_channel, get_call_channel, clear_call_channel,
                                    set_surface_ticket, get_surface_ticket,
                                    set_progress_ticket, get_progress_ticket,
                                    set_approval, get_approval,
                                    actor_context)

        def _run_in_context():
            _prev_pid = get_current_project_id()
            _prev_surface = get_current_surface()
            _prev_channel = get_call_channel()
            _prev_ticket = get_surface_ticket()
            _prev_prog_ticket = get_progress_ticket()
            _prev_approval = get_approval()
            # 사람 승인(②) — 토큰과 이 요청의 지문(code·inputs·declared)을 스레드에 싣는다. 관문(action_requires.gate)이
            # (주체·액션·op·지문) challenge 로 대조·1회 소비. 풀 스레드 재사용 → 복원 필수(티켓 선례).
            import approval_tokens as _approval_tokens
            set_approval(req.approval or None, _approval_tokens.request_digest(req.code, req.inputs, req.declared_inputs, req.function_refs))
            # 표면 티켓을 스레드에 싣는다(⑨) — 엔진 최외곽 파이프라인이 step 경계마다
            # ticket_progress 를 쓴다. to_thread 풀 스레드 재사용 → 복원 필수(선례 동일).
            set_surface_ticket(req.ticket or None)
            # 신고 슬롯은 실행 중 엔진이 채운다(claim) — 들어올 때 비워 두고 나갈 때
            # 되돌린다. 풀 스레드 재사용이라 잔류하면 남의 티켓에 진행을 쓴다.
            set_progress_ticket(None)
            # project_id 를 안 실은 호출(claude_code MCP 재진입은 project_path 만 보낸다)도 경로의
            # 프로젝트를 세운다 — 비워 두면 풀 스레드의 남은 값이나 빈 값으로 행위자 열쇠
            # (red_report.current_owner = 프로젝트:에이전트)가 어긋나 자기 수리 세션 apply 가
            # '소유자 불일치'로 거절됐다(2026-10-08). 프로젝트 밖 경로는 "" 로 비운다.
            from trigger_engine import project_id_of_path
            set_current_project_id(unicodedata.normalize(
                "NFC", req.project_id or project_id_of_path(project_path)))
            set_current_surface(req.surface)
            # 호출 통로 (action_health.channel): req.agent_id 명시 = 에이전트 신원이 실린
            # 호출(claude_code MCP 재진입 등) / 비어 있음 = 앱·조종실·원격·포털 직접 실행.
            # to_thread 풀 스레드는 재사용되므로 반드시 복원한다 (surface 선례).
            set_call_channel("agent" if req.agent_id else "app", override=True)
            # 행위자 3칸(agent·task·origin) — 쓰기 관문 원장(write_ledger)·episode 조인의 재료.
            #   agent: 위에서 해소된 신원(직접 표면=system_ai — line 88 판정과 같은 근거).
            #     옛 코드는 이 값을 _execute_ibl_unified 인자로만 넘기고 thread_context 에
            #     안 실어, 이 경로의 쓰기가 전부 무기명으로 원장에 남았다(2026-08-21 실측).
            #   task: 재진입 봉투가 복원한 부모 task_id — cross 위임
            #     (_execute_call_project_agent)이 get_current_task_id()로 부모를 찾는다.
            #   origin: 봉투 값 우선. 없으면 직접 호출(무신원)만 'user' — 소유자 게이트 뒤
            #     표면의 직접 실행=사람의 명령. ★재진입(req.agent_id 실림)은 부모가 보낸
            #     값만 신뢰, 빈 값이면 빈 채로 둔다(모르는 출처를 'user' 로 단정 금지).
            _origin = req.origin or (None if req.agent_id else "user")
            # 궤적 신원 채택(2026-08-29) — 재진입 봉투가 복원한 episode/parent run 을
            # 실행 전에 걸어, 이 run 의 모든 사건(ibl.*·side_effect.*)이 부모 에피소드에
            # 실리게 한다. 신원이 안 실린 직접 호출은 종전대로(초크포인트가 run 을 세움).
            from contextlib import nullcontext
            from providers.base import adopt_turn_token_ledger
            from research_context import adopt_execution
            _adopt = nullcontext()
            if req.episode_id is not None or req.parent_run_id:
                from episode_logger import trajectory_scope
                _adopt = trajectory_scope(task_id=req.task_id or "",
                                          parent_run_id=req.parent_run_id or "",
                                          episode_id=req.episode_id)
            # 누락된 실행 ID는 풀 스레드에 남은 다른 수리 신원을 상속하지 않는다.
            with _adopt, actor_context(agent_id=agent_id, task_id=req.task_id or "",
                                       origin=_origin), adopt_turn_token_ledger(agent_id, req.task_id):
                try:
                    from system_tools import _execute_ibl_unified
                    # 도구 스키마와 같은 파라미터 집합을 나른다 (B23-1). 없을 때만 빼서
                    # 옛 호출의 tool_input 모양을 바꾸지 않는다(무회귀).
                    _ti = {"code": req.code}
                    for field in ("composition", "completion", "repair"):
                        if getattr(req, field) is not None:
                            _ti[field] = getattr(req, field)
                    if req.edition is not None:
                        _ti["edition"] = req.edition
                    if req.function_refs is not None:
                        _ti["function_refs"] = req.function_refs
                    if req.value_protocols is not None:
                        _ti["value_protocols"] = req.value_protocols
                    if req.inputs is not None:
                        _ti["inputs"] = req.inputs
                    if req.declared_inputs is not None:
                        _ti["declared_inputs"] = req.declared_inputs
                    if req.describe is not None:
                        _ti["describe"] = req.describe
                    if req.read_result is not None:
                        _ti["read_result"] = req.read_result
                    if req.resume is not None:
                        _ti["resume"] = req.resume
                    if req.reuse is not None:
                        _ti["reuse"] = req.reuse
                    if req.budget is not None:
                        _ti["budget"] = req.budget
                    if req.code_edits is not None:
                        _ti["code_edits"] = req.code_edits
                    if req.check:
                        _ti["check"] = True
                    from supervision_bus import current as supervisor_current
                    supervisor = supervisor_current(agent_id, req.task_id)
                    from completion_lease import channel_cancelled
                    cancel_check = (lambda: channel_cancelled(req.completion_channel)) if req.completion_channel else None
                    call = lambda: _execute_ibl_unified(_ti, project_path, agent_id=agent_id, **({"cancel_check": cancel_check} if cancel_check else {}))
                    with adopt_execution(agent_id, req.task_id, project_path):
                        result = supervisor.run_tool("execute_ibl", _ti, call) if supervisor else call()
                        from repeat_guard import observe_result, append_advisory
                        from model_result_view import repeat_observation
                        advisory = observe_result("execute_ibl", _ti, result, agent_id, req.task_id or "",
                                                  read_observation=repeat_observation)
                        return append_advisory(result, advisory)
                finally:
                    set_current_project_id(_prev_pid)
                    set_current_surface(_prev_surface)
                    set_surface_ticket(_prev_ticket)
                    set_approval(*_prev_approval)
                    set_progress_ticket(_prev_prog_ticket)
                    if _prev_channel is None:
                        clear_call_channel()
                    else:
                        set_call_channel(_prev_channel, override=True)

        import asyncio
        result = await asyncio.to_thread(_run_in_context)

        # 결과가 str이면 JSON 파싱 시도. 실패 시 plain text로 wrap.
        # (일부 IBL 액션은 JSON이 아닌 평문/markdown/빈문자열을 반환)
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                if req.ticket:
                    ticket_finish(req.ticket, {"result": result})
                return {"result": result}
        # 단일 통화 정규화 — 이 엔드포인트가 *렌더러 경계*(앱/수동/원격/폰 표면이 모두
        # /ibl/execute 로 들어옴, 에이전트의 내부 execute_ibl 은 안 거침). 여기서 옛 형태
        # (records/table/blocks)를 단일 통화 `items`로 파생해 렌더러 view의 from:items 가
        # 균일하게 풀리게 한다. 에이전트 경로는 거치지 않으므로 tool-result 토큰 중복이 없다.
        # 파싱 후라 문자열 반환 생산자(world_bank·pc-manager 등)도 함께 커버된다.
        # 규칙·예외(map_data 제외, items 과적 역방향 금지)는 common.currency.derive_items.
        from common.currency import derive_items
        # 조향(steer) 배달 — 클로드 코드 경로 어댑터 (2026-08-15): MCP 호출만
        # (req.agent_id 명시 = 에이전트 신원이 실린 호출). 앱/수동 모드는 req.agent_id 가
        # 비어 있어(위에서 system_ai 로 채워지기 *전* 값 기준) 결정론 결과가 오염되지 않는다.
        from common.value_semantics import public_result
        envelope = _attach_steer(derive_items(result), req.agent_id, req.task_id or "")
        out = public_result(envelope, producer="POST /ibl/execute")
        if req.ticket:
            # 표면(HTTP 클라이언트)이 이미 끊겼어도 이 핸들러는 완주한다 — 봉투는 여기 남는다.
            ticket_finish(req.ticket, out)
        return out
    except Exception as e:
        if req.ticket:
            # 실패도 결말이다 — running 으로 영영 남으면 회수자가 "아직 도는 중"으로 오독한다.
            ticket_finish(req.ticket, {"success": False, "error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


class RecoverRequest(BaseModel):
    """표면 티켓 회수(F51-1) — 표면 대기가 끊긴 실행의 최종 봉투를 되찾는다."""
    ticket: Optional[str] = None
    run_id: Optional[str] = None
    project_path: str = "."
    project_id: Optional[str] = None
    # 유한 대기(2026-09-01) — 0이면 종전대로 즉답. `[self:script]{op:"status", wait}` 와
    # 같은 계약(상한 240초, 넘기면 줄이고 신고). 없으면 부르는 쪽이 sleep 으로 대기를
    # 흉내 내다 폴링으로 무너진다(09-01 06:00 실측: 도구 호출의 36%가 기다림이었다).
    wait: float = 0


@router.post("/recover")
async def recover_ibl_result(req: RecoverRequest):
    """티켓의 결말을 묻는다 — done(원 봉투)/running(진행 중)/unknown(만료 또는 미탑재).

    실행이 아니라 조회라 가볍고 유한하다: 어떤 길이의 실행도 '유한 대기의 반복'으로
    덮는 것이 이 규약의 요지다(무한 대기 금지 — 틀린 대기가 틀린 쓰기보다 싸도,
    안 끝나는 대기는 표면을 인질로 잡는다).

    wait 초를 주면 그 안에서 결말을 기다린다. **대기는 워커 스레드로 내린다** — 이
    함수가 이벤트 루프 위에서 잠들면 그 대기를 풀어 줄 요청(진행 신고·실행 완료)을
    서버가 못 받아 자기교착한다(api_ibl 실행 경로가 to_thread 를 쓰는 것과 같은 이유)."""
    import asyncio
    if (req.run_id is None) == (req.ticket is None):
        raise HTTPException(status_code=422, detail='ticket 또는 run_id 중 하나만 지정하세요.')
    if req.run_id is not None:
        if not re.fullmatch(r'[0-9a-f]{32}', req.run_id):
            raise HTTPException(status_code=422, detail='run_id는 32자리 소문자 hex 문자열이어야 합니다.')
        from ibl_run_journal import inspect_run, journal_root
        def inspect():
            path = req.project_path
            if req.project_id:
                from project_manager import ProjectManager
                resolved = ProjectManager().get_project_path(req.project_id)
                if resolved is None:
                    raise HTTPException(status_code=404, detail='프로젝트를 찾을 수 없습니다.')
                path = str(resolved.resolve())
            return inspect_run(journal_root(path), req.run_id)
        return await asyncio.to_thread(inspect)
    from common.spill import ticket_recover, ticket_wait
    if not req.wait:
        return await asyncio.to_thread(ticket_recover, req.ticket)
    return await asyncio.to_thread(ticket_wait, req.ticket, req.wait)


def _attach_steer(envelope, explicit_agent_id: str, task_id=None):
    """MCP(에이전트) 호출의 응답 봉투에 대기 조향을 부록 키로 동봉. 직결 경로의
    execute_tool 부록과 같은 의미 — 이 경로는 execute_tool 미경유라 여기서 배달한다."""
    if not explicit_agent_id or not isinstance(envelope, dict):
        return envelope
    try:
        from steer_inbox import drain, render
        text = render(drain(explicit_agent_id, task_id))
        if text:
            envelope["steer_notice"] = text.strip()
            print(f"[조향] {explicit_agent_id}: MCP 응답에 조향 지시 배달")
    except Exception:
        pass
    return envelope


@router.post("/read_guide")
async def read_guide_bridge(req: GuideRequest):
    """가이드 DB 검색 — claude_code MCP 브리지(mcp_server.read_guide)가 호출하는 HTTP 통로.

    in-process 경로(system_tools.handle_tool 'read_guide')와 **동일한 search_guide** 를
    호출해 프로바이더 간 동작 동치를 보장한다. 이 라우트는 순수 배관(가이드 검색)일 뿐
    프로바이더 행동을 바꾸지 않는다 — read_guide 도구가 노출되는 곳은 claude_code 의
    MCP 화이트리스트(EAGER_TOOLS)뿐이다."""
    try:
        from ibl_routing import search_guide
        from thread_context import actor_context
        with actor_context(agent_id=req.agent_id or "", task_id=req.task_id or ""):
            return search_guide(req.query, {"read": req.read, "if_hash": req.if_hash, "section": req.section})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reframe")
async def reframe_bridge(req: ReframeRequest):
    """턴 안 재규정 — mcp_server.reframe 가 호출하는 HTTP 통로. in-process 경로(system_tools
    'reframe')와 **동일한 execute_reframe** 를 부른다. 의식 재호출(수십 초)은 스레드로 — 이 서버는
    MCP HTTP 마운트와 같은 루프라 루프를 막으면 자기 교착이다(_post_backend 주석)."""
    import asyncio
    try:
        from reframe import execute_reframe
        payload = {"broken_assumption": req.broken_assumption, "evidence": req.evidence,
                   "progress": req.progress, "kind": req.kind}
        raw = await asyncio.to_thread(execute_reframe, payload, req.agent_id or "system_ai", req.task_id or "")
        try:
            return json.loads(raw)
        except Exception:
            return {"revised": False, "content": raw}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/embed")
async def embed_text(req: EmbedRequest):
    """텍스트 → 768차원 L2 정규화 벡터 (폰-자아 해마의 인코더 렌트).

    상시 켜둔 맥엔 fine-tuned 임베딩 모델이 떠 있다. 폰-자아는 무거운 torch 런타임을
    번들하는 대신 이 엔드포인트로 질의 텍스트를 보내 벡터를 받고, 자기 로컬 인덱스에서
    brute-force 코사인 검색한다(인코더=공유 substrate / 인덱스=사적 경험, 절단면 일치).
    문서 인덱싱과 동일 encode+정규화라 같은 벡터공간 — search_semantic 과 동치.
    (PHONE_SELF_HOSTING_HANDOFF §6.3·§6.6)"""
    inputs = req.texts if req.texts is not None else ([req.text] if req.text else [])
    if not inputs:
        raise HTTPException(status_code=400, detail="text 또는 texts 가 필요합니다.")
    try:
        import asyncio
        from ibl_usage_db import IBLUsageDB
        db = IBLUsageDB()
        vectors = await asyncio.to_thread(db.embed_vectors, inputs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if vectors is None:
        raise HTTPException(status_code=503,
                            detail="임베딩 모델 미가용 (sentence-transformers 미설치 또는 로드 실패)")
    out = {"dim": IBLUsageDB.EMBEDDING_DIM, "count": len(vectors)}
    if req.texts is not None:
        out["vectors"] = vectors
    else:
        out["vector"] = vectors[0]
    return out


@router.get("/actions/catalog")
async def get_actions_catalog():
    """IBL 액션 카탈로그 — 마법책 UI 데이터 소스.

    6개 노드(sense, self, limbs, others, engines, table)별로 분류된
    전체 IBL 액션 목록을 반환한다. 프론트의 액션 사전 모달이
    이 데이터로 책장을 그린다.
    """
    import asyncio
    from execution_workers import bind_context
    return await asyncio.to_thread(bind_context(_build_actions_catalog))


def _build_actions_catalog():
    """사전/계약 파일 읽기는 작업자에서 하고 현재 작성 설명만 화면에 보낸다."""
    from ibl_registry import load_nodes_installed, self_can_run
    from ibl_v2_adapters import load_registry
    from model_result_view import current_action_definition
    data = load_nodes_installed()
    if not data:
        raise HTTPException(status_code=500, detail="ibl_nodes.yaml 로드 실패")
    registry = load_registry()

    nodes_out: dict = {}
    total = 0
    for node_name, node_config in (data.get("nodes") or {}).items():
        actions: dict = {}
        for action_name, action_config in (node_config.get("actions") or {}).items():
            adapter = registry.get(f"{node_name}:{action_name}")
            if adapter is None or not self_can_run(node_name, action_name, action_config):
                continue
            definition = current_action_definition(action_config, adapter.contract)
            contract = definition["callable_contract"]
            params = contract.get("params", {})
            signature = ", ".join(f"{key}: {value}" for key, value in params.items())
            target_key = action_config.get("target_key", "")
            actions[action_name] = {
                "description": definition.get("description", ""),
                "target_description": definition.get("target_description") or
                    f"인자: {signature or '없음'}. 반환: {contract.get('result', 'Unknown')}.",
                "target_key": target_key if target_key in params else "",
                "implementation": "",
                "callable_contract": contract,
                "keywords": action_config.get("keywords") or [],
                "group": action_config.get("group", ""),
                "ops": (action_config.get("ops") or None) if "op" in params else None,
            }
        nodes_out[node_name] = {"actions": actions, "count": len(actions)}
        total += len(actions)

    return {"nodes": nodes_out, "total": total}


# === 수동 모드: 컴파일러 프론트엔드 ===
# 번역 task 프레이밍·교재 로더·출력 정제기는 ibl_translate(언어층)로 이동 —
# body_ask(인지층)가 라우터를 import 하지 않게 (2026-08-05 감사 ⑦).
from ibl_translate import (  # noqa: E402
    IBL_TRANSLATE_TASK,
    load_ibl_spec,
    strip_code_fence,
)


@router.post("/translate")
async def translate_to_ibl(req: TranslateRequest):
    """자연어 의도 → IBL 코드 (해마 용례 + 본격 system_ai 모델). 실행하지 않는다.

    수동 모드(계기판)의 1단계. 시스템 AI와 *같은 모델*이 해마(과거 용례)에 기대어
    번역만 하고, 사용자는 다음 단계에서 dry-run으로 검수한다.
    (경량 모델보다 번역 품질↑ — 지역·맥락 추론 등. 비용은 번역 1회 분.)
    """
    intent = (req.intent or "").strip()
    if not intent:
        raise HTTPException(status_code=400, detail="빈 명령입니다.")

    allowed = set(req.allowed_nodes) if req.allowed_nodes else None

    # ★워커 스레드에서(asyncio.to_thread) — 해마 회상 + system_ai_call(블로킹 LLM HTTP)을
    #   이벤트 루프 위에서 돌리면 호출 내내 /health 까지 굶는다(2026-08-16 keeper 오발
    #   사건: 모델 교체 후 워밍업 translate 중 /health 무응답 → keeper 가 죽음으로 오판).
    #   /ibl/execute 의 to_thread 선례와 같은 부류.
    def _do_translate():
        # 1) 해마: 자연어 → 과거 IBL 용례 연상
        try:
            from ibl_usage_rag import IBLUsageRAG
            references = IBLUsageRAG().get_references(intent, allowed_nodes=allowed)
        except Exception:
            references = ""

        # 2) 본격 system_ai 모델: 용례를 근거로 IBL 코드 번역
        from consciousness_agent import system_ai_call
        prompt = f'사용자 명령: "{intent}"\n\n'
        if references:
            prompt += f"참고 용례 (이 액션 이름들만 사용하라):\n{references}\n\n"
        else:
            prompt += "(관련 과거 용례 없음 — 위 6개 노드 지식으로 직접 번역하라.)\n\n"
        prompt += "위 명령을 IBL 코드로 번역하라. IBL 코드만 출력."

        spec = load_ibl_spec()
        system_prompt = IBL_TRANSLATE_TASK + (f"\n\n<ibl_spec>\n{spec}\n</ibl_spec>" if spec else "")
        # 수동 모드 번역 = 모델 기어 '실행' 축(role=translate)으로 해소.
        return references, system_ai_call(prompt, system_prompt=system_prompt, role="translate")

    import asyncio
    references, raw = await asyncio.to_thread(_do_translate)
    if not raw:
        raise HTTPException(status_code=503, detail="번역 모델이 응답하지 않았습니다. 모델 기어(실행 축) 설정을 확인하세요.")

    from ibl_translate import translated_source
    try:
        ibl_code = translated_source(raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"번역 구문 검사 실패: {exc}") from exc
    return {
        "intent": intent,
        "ibl_code": ibl_code,
        "references": references,  # 리터러시: 어떤 과거 용례를 근거로 했는지 병기
        "raw": raw,
    }


def _action_description(node: str, action: str) -> str:
    """노드/액션의 사람이 읽는 효과 설명 (dry-run 미리보기용)."""
    try:
        from ibl_access import load_nodes_raw
        data = load_nodes_raw() or {}
        ac = (data.get("nodes", {}).get(node, {}).get("actions", {}).get(action, {})) or {}
        return ac.get("description", "")
    except Exception:
        return ""


def _effect_description(node: str, action: str, params: dict) -> str:
    """이 호출이 실제로 무엇을 하는지 (dry-run 효과 설명).

    op 분기가 있는 액션이면 액션 전체의 두루뭉술한 설명 대신, 지금 고른 op
    (없으면 기본 op)의 구체적 효과를 보여준다. 조종실 검수 패널이 "무엇을
    하는지"를 op 단위로 정확히 읽게 한다.
    """
    try:
        from ibl_access import load_nodes_raw
        data = load_nodes_raw() or {}
        ac = (data.get("nodes", {}).get(node, {}).get("actions", {}).get(action, {})) or {}
        base = ac.get("description", "")
        ops = ac.get("ops") or {}
        values = ops.get("values") or {}
        if values:
            op = (params or {}).get("op") or ops.get("default")
            op_desc = values.get(op)
            if op_desc:
                # op 효과만 — 액션 정체는 아래 [node:action] 코드가 이미 보여준다.
                # 전체 설명을 덧붙이면 사용자가 지적한 "두루뭉술한 요약"이 되돌아온다.
                return f"{op}: {op_desc}"
        return base
    except Exception:
        return _action_description(node, action)


def _known_nodes() -> list:
    """등록된 노드 이름 목록(정렬) — 에러 문구가 레지스트리를 따라가게."""
    try:
        from ibl_registry import load_nodes_installed
        return sorted((load_nodes_installed().get("nodes") or {}).keys())
    except Exception:
        return []


def _load_safety_map() -> dict:
    """부작용 분류를 (node, action) → safe(bool)로. 판정은 ibl_safety 단일 소스.

    옛 구현은 `self_check_plan.json`(LLM 분류 캐시)을 읽었는데, 그 생성 경로가 삭제된 뒤에도
    파일만 남아 3주 넘게 118개짜리 낡은 목록으로 판정해 왔다(현재 157개). 이제 레지스트리의
    `returns:` 선언에서 파생하므로 새 액션이 자동 분류된다."""
    from ibl_safety import load_safety_map
    return load_safety_map()


def _load_op_safety_map() -> dict:
    """op 단위 분류 (node, action, op) → safe(bool). 감사 부채 ③ (2026-08-05).

    액션 롤업만 쓰면 읽기 op 가 쓰기 액션 안에 갇혀 조종실이 실행 자물쇠를 헛 건다.
    해소 규칙은 `backend/ibl_ops.py` 단일 소스."""
    from ibl_safety import load_op_safety_map
    return load_op_safety_map()


def _resolve_op(node: str, action: str, params: dict = None) -> str:
    """이 호출에서 실제 실행될 op (없거나 유령이면 None) — ibl_ops 단일 소스."""
    try:
        from ibl_access import load_nodes_raw
        from ibl_ops import resolve_op
        data = load_nodes_raw() or {}
        ac = (data.get("nodes", {}).get(node, {}).get("actions", {}).get(action, {})) or {}
        return resolve_op(ac, params)
    except Exception:
        return None


@router.post("/validate")
async def validate_ibl(req: ValidateRequest):
    """dry-run: IBL 코드를 파싱·검증만 하고 실행하지 않는다.

    수동 모드의 2단계. 각 step의 노드/액션 유효성을 확인하고,
    '이 명령이 무엇을 하는지'를 효과 레벨로 풀어 보여준다(코드 검수 X).
    """
    code = (req.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="빈 코드입니다.")
    def _validate():
        if (getattr(req, "edition", None) is not None or getattr(req, "inputs", None) is not None
                or getattr(req, "declared_inputs", None) is not None):
            return validate_request_code(code, edition=req.edition, inputs=req.inputs,
                                         declared_inputs=req.declared_inputs)
        return validate_code(code)
    import asyncio
    from execution_workers import bind_context
    return await asyncio.to_thread(bind_context(_validate))


def validate_code(code: str) -> dict:
    """기존 관문/호출자의 단일 인자 API. 같은 판본별 검사 본체로 위임한다."""
    return validate_request_code(code)


def validate_request_code(code: str, edition=None, inputs=None, declared_inputs=None) -> dict:
    """dry-run 본체 — 라우터(`/ibl/validate`)와 관문(`scripts/check_validate_parity.py`)이
    **같은 함수**를 쓴다 (B53-1, 2026-09-02). 검수기가 파서 개정을 모르면 멀쩡한 문장에
    거짓 빨강이 난다(B49-1 `do` 재파싱 · B53-1 `$변수 >>` 파이프 머리 — 같은 속 두 번).
    그 부류는 "실행되는 문장 전수를 검수에 넣어 valid:false 가 0" 인 관문으로만 닫힌다."""
    from ibl_v2_entry import handle_request
    if isinstance(inputs, dict):
        # 실행 경로(system_tools_ibl)와 같은 참조 해석기를 통과한다 — 참조 dict 를 업무 값으로
        # 타입 검사하던 거짓 FIELD_TYPE 의 봉인(69회차 B69-3, B53-1 동형성 부류).
        try:
            from model_result_view import resolve_input_refs
            inputs, _notes = resolve_input_refs(inputs)
        except ValueError as exc:
            return {"edition": 2, "mode": "check", "executed": False, "ok": False, "valid": False,
                    "status": "invalid", "error": str(exc)}
    v2 = handle_request({"code": code, "edition": edition, "inputs": inputs, "check": True,
                         **({"declared_inputs": declared_inputs} if declared_inputs is not None else {})})
    effects = set(v2.get('effects') or [])
    return {**v2, "valid": v2.get("ok", False),
            'has_side_effect': bool(effects - {'read_external','model','pure'}),
            'has_ai_call': 'model' in effects}


@router.post("/distill")
async def distill_ibl(req: DistillRequest):
    """수동 모드의 성공 실행을 해마에 증류한다 (자율주행/수동 → 학습 코퍼스의 상향 흐름).

    인간이 검수해 실행한 IBL이라 품질이 높다. 기존 경험 증류 경로를 그대로 재사용:
    top_score < 0.7 일 때만 일반화해 ibl_distilled.json + 해마 인덱스에 축적된다.
    """
    intent = (req.intent or "").strip()
    code = req.code or ""
    if not intent or not code.strip():
        return {"distilled": False, "reason": "intent/code 가 비어 있습니다."}

    try:
        from ibl_usage_rag import distill_experience
        from ibl_continuations import completed_call
        call = completed_call(req.task_ref, code)
        if call is None:
            return {"distilled": False, "reason": "이 원문의 완료된 실행 영수증이 필요합니다. 실행 결과를 확인하세요."}
        tool_calls = [call]
        # ★워커 스레드에서 — 증류는 내부에서 경량 LLM(반성)을 블로킹 호출한다.
        #   translate 와 같은 부류(이벤트 루프 기아 → /health 무응답 → keeper 오발).
        import asyncio
        ok = await asyncio.to_thread(distill_experience, intent, tool_calls, req.top_score)
        return {"distilled": bool(ok)}
    except Exception as e:
        return {"distilled": False, "reason": str(e)}
