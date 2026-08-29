"""api_ibl.py - IBL 직접 실행 API (MCP/외부 도구용 + 수동 모드 컴파일러 프론트엔드)"""
import json
import os
import re
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/ibl", tags=["ibl"])

class IBLRequest(BaseModel):
    code: str
    verbose: bool = False              # 파이프 봉투 results[] 원형(true) / step 요약(기본) — ibl_envelope (2026-08-22 M1)
    resume: Optional[dict] = None      # 실패 봉투의 resume 값 그대로({from_step, prev_ref}) — 그 step 부터 재개.
    files: Optional[List[str]] = None  # 긴 텍스트/코드를 IBL 파서 밖에서 전달 ($file:0 로 참조).
    # ★2026-08-22 B23-1(상상훈련 23회차): 위 두 필드는 도구 스키마(tool_loader)와 엔진
    # (system_tools_ibl)에는 처음부터 있었는데 **이 요청 모델에만 없어서**, body 에 실어 보낸
    # resume/files 가 pydantic 단계에서 조용히 탈락했다. 봉투의 실패 note 는 표면을 가리지 않고
    # "execute_ibl(code, resume={from_step, prev_ref})" 를 모두에게 안내하므로, **안내받은 대로
    # 보낸 값이 침묵으로 사라지는 자리**였다(교재에 resume 용례가 0건인 이유 — 닿을 수가 없었다).
    # 표면은 도구 스키마와 같은 파라미터 집합을 날라야 한다 — 새 파라미터를 스키마에 넣을 때
    # 이 모델과 mcp_server.execute_ibl 도 함께 늘릴 것.
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


class TranslateRequest(BaseModel):
    """수동 모드: 자연어 의도 → IBL 코드 번역 요청"""
    intent: str
    allowed_nodes: Optional[List[str]] = None  # None이면 전체 노드 허용


class ValidateRequest(BaseModel):
    """수동 모드: dry-run 검증 요청 (실행하지 않고 효과만 미리보기)"""
    code: str


class DistillRequest(BaseModel):
    """수동 모드: 성공한 실행을 해마에 증류(학습)하는 요청.

    top_score = 번역 시 해마가 내놓은 최고 참조 점수. 임계값(0.7) 미만일 때만
    증류된다 — 해마가 이미 잘 아는 패턴은 다시 학습하지 않는다."""
    intent: str
    code: str
    top_score: float = 0.0

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
            if not p.exists() and req.project_id in ProjectManager.SYSTEM_PROJECT_IDS:
                p.mkdir(parents=True, exist_ok=True)
            if p and p.exists():
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
                                    actor_context)

        def _run_in_context():
            _prev_pid = get_current_project_id()
            _prev_surface = get_current_surface()
            _prev_channel = get_call_channel()
            _prev_ticket = get_surface_ticket()
            # 표면 티켓을 스레드에 싣는다(⑨) — 엔진 최외곽 파이프라인이 step 경계마다
            # ticket_progress 를 쓴다. to_thread 풀 스레드 재사용 → 복원 필수(선례 동일).
            set_surface_ticket(req.ticket or None)
            if req.project_id:
                set_current_project_id(req.project_id)
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
            _adopt = nullcontext()
            if req.episode_id is not None or req.parent_run_id:
                from episode_logger import trajectory_scope
                _adopt = trajectory_scope(task_id=req.task_id or "",
                                          parent_run_id=req.parent_run_id or "",
                                          episode_id=req.episode_id)
            with _adopt, actor_context(agent_id=agent_id, task_id=req.task_id or None,
                                       origin=_origin):
                try:
                    from system_tools import _execute_ibl_unified
                    # 도구 스키마와 같은 파라미터 집합을 나른다 (B23-1). 없을 때만 빼서
                    # 옛 호출의 tool_input 모양을 바꾸지 않는다(무회귀).
                    _ti = {"code": req.code, "verbose": req.verbose}
                    if req.resume is not None:
                        _ti["resume"] = req.resume
                    if req.files is not None:
                        _ti["files"] = req.files
                    return _execute_ibl_unified(_ti, project_path, agent_id=agent_id)
                finally:
                    set_current_project_id(_prev_pid)
                    set_current_surface(_prev_surface)
                    set_surface_ticket(_prev_ticket)
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
        envelope = _attach_steer(derive_items(result), req.agent_id)
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
    ticket: str


@router.post("/recover")
async def recover_ibl_result(req: RecoverRequest):
    """티켓의 결말을 묻는다 — done(원 봉투)/running(진행 중)/unknown(만료 또는 미탑재).

    실행이 아니라 조회라 가볍고 유한하다: 어떤 길이의 실행도 '유한 대기의 반복'으로
    덮는 것이 이 규약의 요지다(무한 대기 금지 — 틀린 대기가 틀린 쓰기보다 싸도,
    안 끝나는 대기는 표면을 인질로 잡는다)."""
    from common.spill import ticket_recover
    return ticket_recover(req.ticket)


def _attach_steer(envelope, explicit_agent_id: str):
    """MCP(에이전트) 호출의 응답 봉투에 대기 조향을 부록 키로 동봉. 직결 경로의
    execute_tool 부록과 같은 의미 — 이 경로는 execute_tool 미경유라 여기서 배달한다."""
    if not explicit_agent_id or not isinstance(envelope, dict):
        return envelope
    try:
        from steer_inbox import drain, render
        text = render(drain(explicit_agent_id))
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
        return search_guide(req.query, {"read": req.read})
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
    from ibl_access import load_nodes_raw
    data = load_nodes_raw()
    if not data:
        raise HTTPException(status_code=500, detail="ibl_nodes.yaml 로드 실패")

    nodes_out: dict = {}
    total = 0
    for node_name, node_config in (data.get("nodes") or {}).items():
        actions: dict = {}
        for action_name, action_config in (node_config.get("actions") or {}).items():
            actions[action_name] = {
                "description": action_config.get("description", ""),
                "target_description": action_config.get("target_description", ""),
                "target_key": action_config.get("target_key", ""),
                "implementation": action_config.get("implementation", ""),
                "keywords": action_config.get("keywords") or [],
                "group": action_config.get("group", ""),
                "ops": action_config.get("ops") or None,  # {default, values:{op명:설명}} — 수동모드 op 분기 안내용
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

    ibl_code = strip_code_fence(raw)
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
    # 조건식 검수용 — 이 코드가 할당하는 $변수 이름(조건의 미할당 $변수를 미리 잡는다, M2)
    import re as _re
    _assigned_vars = set(_re.findall(r'^\s*\$(\w+)\s*=', code, _re.M))

    # 1) 파싱 (문법 검사)
    try:
        from ibl_parser import parse
        parsed = parse(code)
    except Exception as e:
        return {
            "valid": False,
            "syntax_error": str(e),
            "steps": [],
        }

    # 2) step별 노드/액션 유효성 + 효과 설명 + 안전성(부작용)
    from ibl_engine import get_node_actions
    safety_map = _load_safety_map()
    op_safety_map = _load_op_safety_map()

    def _safety(node: str, action: str, params: dict = None) -> str:
        # 'read' = 부작용 없음(되돌릴 필요 없음), 'write' = 부작용 있음, 'unknown' = 미분류
        # ★op 단위 우선(2026-08-05 감사 ③): [self:music]{op:"library"} 를 액션 롤업으로
        #   판정하면 읽기 명령에 실행 자물쇠가 걸린다. op 를 알면 op 로 판정하고,
        #   op 를 못 짚으면(유령 op·미선언) 보수적인 액션 롤업으로 떨어진다.
        op = _resolve_op(node, action, params)
        s = op_safety_map.get((node, action, op)) if op else None
        if s is None:
            s = safety_map.get((node, action))
        return "read" if s is True else "write" if s is False else "unknown"

    steps = []
    all_valid = True
    has_side_effect = False
    has_ai_call = False

    def _is_ai_call(node: str, action: str, params: dict = None) -> bool:
        """AI 낱말(ai_call: true) 여부 — 실행마다 모델 비용·출력 편차라 dry-run 이
        초록불 대신 고지를 단다(0토큰 계약의 표시 의무, ONESHOT_VOCAB_DESIGN §7).

        ★op 레벨 지원 (F14-4, 2026-08-20): `ops.ai_call: {op: true}` 형제 맵 — notebook 처럼
        한 op(ask)만 모델을 부르는 액션용(side_effect 의 op 축과 같은 모양). 액션 레벨
        플래그가 우선하고, op 를 못 짚으면(유령 op) 보수적으로 고지한다."""
        try:
            from ibl_access import load_nodes_raw
            ad = ((load_nodes_raw() or {}).get("nodes", {})
                  .get(node, {}).get("actions", {}).get(action, {})) or {}
            if ad.get("ai_call"):
                return True
            op_map = (ad.get("ops") or {}).get("ai_call") or {}
            if op_map:
                op = _resolve_op(node, action, params)
                if op is None:
                    return any(bool(v) for v in op_map.values())
                return bool(op_map.get(op))
            return False
        except Exception:
            return False

    def _emit_action(st: dict, label: str = None, group: str = None, warn: str = None):
        """평범한 액션 한 개를 검증해 steps 에 싣는다. label=구조 안 위치 표시(effect 앞),
        group=기계용 표식(parallel/fallback/condition/case/goal), warn=구조 층 경고(조건 문법 등)."""
        nonlocal all_valid, has_side_effect, has_ai_call
        node = st.get("_node", "")
        action = st.get("action", "")
        params = st.get("params", {}) or {}

        valid_actions = get_node_actions(node) if node else set()
        if not node:
            ok, err = False, "노드가 지정되지 않았습니다."
        elif not valid_actions:
            # 노드 목록은 레지스트리에서 파생 — 손으로 적으면 어긋난다
            # (2026-06-30 table 노드 분리 후 이 문구가 5노드로 남아 있었다)
            ok, err = False, f"'{node}'는 알 수 없는 노드입니다. ({'/'.join(_known_nodes())})"
        elif action not in valid_actions:
            # ★F15 (2026-08-17 상상훈련 12회차): 다른 몸의 어휘는 "없다" 대신 정직하게.
            from ibl_registry import pruned_reason
            _why = pruned_reason(node, action)
            if _why:
                ok, err = False, (f"[{node}:{action}] 은 {_why} 어휘라 이 몸의 사전에 없습니다 — "
                                  f"[others:ask] 로 그 몸에 부탁하세요.")
            else:
                ok, err = False, f"'{node}' 노드에 '{action}' 액션이 없습니다."
        else:
            ok, err = True, None

        if not ok:
            all_valid = False

        safety = _safety(node, action, params)
        if safety != "read":
            has_side_effect = True

        # 인자 층 검사 (2026-07-03): 핸들러가 읽지 않는 키를 dry-run 단계에서 미리
        # 소리 나게 — 경량모델(조종실 번역)이 실행 전에 자가교정할 수 있게 한다.
        param_warning = None
        if ok:
            try:
                from ibl_param_vocab import check_params
                pw = check_params(node, action, params)
                if pw:
                    param_warning = pw["message"]
            except Exception:
                param_warning = None
            # F2-op (2026-08-16 상상훈련 5회차): op *값*도 dry-run 이 미리 검사한다 —
            # `[limbs:radio]{op:"search"}` 가 검수 초록 후 실행에서 "알 수 없는 op" 로
            # 죽었다(검색=sense:radio). enum 은 레지스트리 ops.values 에 이미 있다.
            # 소프트 경고(R2 param 경고와 같은 층) — 실행기의 정직 거절이 최종 심판.
            try:
                _op_val = str(params.get("op") or "").strip()
                if _op_val:
                    from ibl_access import load_nodes_raw
                    _ac = ((load_nodes_raw() or {}).get("nodes", {})
                           .get(node, {}).get("actions", {}).get(action, {})) or {}
                    _vals = ((_ac.get("ops") or {}).get("values") or {})
                    if _vals and _op_val not in _vals:
                        _ow = (f"op '{_op_val}' 은(는) 이 액션에 없습니다 — 실행 시 거절됩니다. "
                               f"사용 가능: {sorted(_vals)}")
                        param_warning = f"{param_warning} / {_ow}" if param_warning else _ow
            except Exception:
                pass

        if warn:
            param_warning = f"{param_warning} / {warn}" if param_warning else warn

        ai_call = ok and _is_ai_call(node, action, params)
        if ai_call:
            has_ai_call = True
            _ai_note = "AI 낱말 — 실행마다 모델 호출(비용·출력 편차). 검수는 출력 내용을 예측하지 못합니다."
            param_warning = f"{param_warning} / {_ai_note}" if param_warning else _ai_note

        effect = _effect_description(node, action, params) or "(설명 없음)"
        entry = {
            "node": node, "action": action, "params": params,
            "kind": "action",
            "effect": f"{label} {effect}" if label else effect,
            "safety": safety,
            "valid": ok, "error": err,
            "param_warning": param_warning,
        }
        if ai_call:
            entry["ai_call"] = True
        if group:
            entry["group"] = group
        steps.append(entry)

    def _opaque_block(effect: str, group: str):
        """속을 읽지 못한 블록 — 종전의 보수 처리(부작용 취급) 유지."""
        nonlocal has_side_effect
        has_side_effect = True
        steps.append({
            "node": "", "action": "", "params": {}, "kind": "block",
            "effect": effect, "safety": "unknown",
            "valid": True, "error": None, "group": group,
        })

    def _is_plain(st) -> bool:
        return isinstance(st, dict) and not (
            st.get("_parallel") or "_fallback_chain" in st or st.get("_branch_steps")
            or st.get("_condition") or st.get("_case") or st.get("_goal")
            or st.get("_try") or st.get("_repeat") or st.get("_assign"))

    # do(문장을 param 문자열로 나르는 자리)를 가진 액션들 — each 외에 M1 `do` 통일 자리 전부.
    # (2026-08-16 상상훈련 G2: each·goal.strategy 는 펼치는데 schedule.do 는 안 펼쳐,
    #  시간 문형이 검수 사각 = 고유수용감각 없는 팔이었다. 값=읽을 param 키 후보 순서.)
    _DO_CARRYING = {
        ("table", "each"): ("do",),
        ("self", "schedule"): ("do", "pipeline"),
        ("self", "trigger"): ("do", "pipeline"),
        ("self", "workflow"): ("do", "steps", "pipeline"),
        ("self", "manage_events"): ("do", "event_action"),
        ("others", "delegate"): ("do", "steps"),
    }

    def _walk_do_param(st: dict, depth: int, keys: tuple, gname: str):
        """액션의 do 성 param 문자열 속 문장을 펼쳐 검증한다.

        do 는 이 언어가 코드를 *문자열로* 나르는 자리 — 여기를 안 펼치면
        do 안의 부작용·무효 액션이 컨테이너 한 줄 뒤에 숨어
        조종실의 번역→dry-run→실행 계약이 반쪽이 된다."""
        nonlocal all_valid
        params = st.get("params", {}) or {}
        do = None
        for k in keys:
            do = params.get(k)
            if do:
                break
        if isinstance(do, list):
            do = "\n".join(str(x) for x in do if str(x).strip())
        if not do or not str(do).strip():
            return
        do = str(do)
        strict = (gname == "each")  # each 의 do 는 반드시 IBL. 다른 컨테이너는 경고까지만.
        if not strict and "[" not in do:
            return  # 자유 텍스트로 보임 — 컨테이너 재량(예: 위임 지시문)이라 침묵 통과
        from ibl_parser import parse as _parse_do, IBLSyntaxError as _DoSynErr
        try:
            try:
                inner = _parse_do(do)
            except _DoSynErr:
                # $it/$변수 치환 자리가 따옴표 밖(예: {n: $it.n})이면 실행 시엔 합법 —
                # 자리만 더미(1)로 메워 재시도한다. 이걸로도 안 되면 진짜 문법 오류.
                # ★B49-1(49회차 상상훈련): 이 재시도가 `$` 만 훑어서 **바깥 할당이 있는**
                #   문장을 놓쳤다. 파서는 `$n = 2` 가 앞에 있으면 do 속 `$n` 을 여기 오기
                #   *전에* `{{_step_0_result}}` 로 바꿔 둔다 — 남은 것은 `$` 가 아니라
                #   중괄호 자리표라, 재파싱이 그것을 객체 리터럴의 시작으로 읽고
                #   "파라미터를 끝까지 읽지 못했습니다" 로 죽었다. 실측:
                #     $n = 2
                #     [table:each]{items: [{a: 1}], do: "[sense:host]{op: \"apps\", limit: $n}"}
                #       → validate valid:false / execute success:true   ← 검수만 거짓 빨강
                #   따옴표로 감싼 `\"$n\"` 은 문자열 값이 되어 통과했으므로 **인용 없는
                #   자리에서만** 났다. _DO_CARRYING 6종(each·schedule·trigger·workflow·
                #   manage_events·delegate) 이 같은 재파싱을 쓰므로 부류 전체가 이 한 줄에 걸려 있다.
                #   자리표를 먼저 메우고, 남은 맨 `$참조`는 정본 REF_RE 로 훑는다
                #   (손으로 쓴 `\$\w+` 은 `${이름}` 괄호형을 놓쳤다 — ibl_vars.py 의 경고).
                from workflow_binding import blank_step_refs
                from common.ibl_vars import REF_RE
                inner = _parse_do(REF_RE.sub("1", blank_step_refs(do)))
        except _DoSynErr as e:
            entry = {
                "node": st.get("_node", ""), "action": st.get("action", ""),
                "params": {}, "kind": "block",
                "effect": f"{gname} do 문장 문법 오류 — 실행 시 실패합니다: {str(e)[:160]}",
                "safety": "unknown", "valid": (not strict), "error": str(e)[:200],
                "group": gname,
            }
            if strict:
                all_valid = False
            steps.append(entry)
            return
        for ist in inner:
            _walk(ist, depth + 1, label=f"[{gname} 속]", group=gname)

    def _condition_syntax_warning(cond: str):
        """조건 좌변이 node:action 소스 참조로 파싱되는지 미리 검사.

        실행기(_evaluate_sense_condition)는 좌변이 소스 참조가 아니면 값 None → 조용히
        거짓 판정이라, 자연어 조건('[if: 디스크가 부족하면]')이 침묵으로 else 에 떨어진다.
        dry-run 이 유일하게 미리 소리 낼 수 있는 자리다."""
        try:
            # 2026-08-22 M2: 술어 언어(ibl_predicates)의 정적 검수 — $변수·count/empty/exists·
            # and/or/not·matches·AI 술어까지 한 문법. 미할당 $변수도 여기서 미리 잡는다.
            from ibl_predicates import validate_condition
            return validate_condition(cond, known_vars=sorted(_assigned_vars))
        except Exception:
            return None

    def _walk(st, depth: int = 0, label: str = None, group: str = None, warn: str = None):
        """구조 step(병렬/폴백/블록)을 가지 단위로 펼쳐 전부 검증한다.

        검수기가 자기 엔진보다 좁으면 안 된다 — 실행기는 이 모양들을 전부 지원하는데
        (_execute_parallel/_execute_fallback/블록 디스패치) 여기서 못 읽으면 조종실이
        멀쩡한 문장을 반려하거나, 반대로 속을 안 본 채 초록불을 켠다."""
        nonlocal has_side_effect
        if not isinstance(st, dict) or depth > 6:
            return
        if _is_plain(st):
            _emit_action(st, label=label, group=group, warn=warn)
            _key = (st.get("_node"), st.get("action"))
            _dk = _DO_CARRYING.get(_key)
            if _dk:
                _gname = "each" if st.get("action") == "each" else st.get("action")
                _container_idx = len(steps) - 1
                _n_before = len(steps)
                _walk_do_param(st, depth, _dk, _gname)
                # F10 (2026-08-16 상상훈련 4회차): each 자체는 순수 적용자 — 부작용은 do 속
                # 문장의 것이다. 선언 side_effect:true 는 "속을 못 볼 때 초록불 금지"의 보수
                # 기본인데(그 의도의 src 주석 실존), 검수기가 do 를 펼치는 지금은 근거가 있다:
                # 속을 실제로 읽었고 전부 read·유효하면 컨테이너 라벨을 속의 OR 로 정밀화한다.
                # 속을 못 읽었으면(빈 do·파싱 실패) 선언 그대로 보수 유지. trigger/schedule/
                # workflow 등 다른 do-컨테이너는 등록·저장 자체가 부작용이라 제외.
                if _key == ("table", "each"):
                    _inner = steps[_n_before:]
                    if _inner and all(e.get("safety") == "read" and e.get("valid")
                                      for e in _inner):
                        steps[_container_idx]["safety"] = "read"
                        has_side_effect = any(e.get("safety") != "read" for e in steps)
            return
        if st.get("_parallel"):
            branches = st.get("branches") or []
            n = len(branches)
            for i, br in enumerate(branches):
                # 괄호 분기 파이프 (G13-1) — 속 step 들을 위치 라벨로 전부 펼친다
                if isinstance(br, dict) and br.get("_branch_steps"):
                    subs = br["_branch_steps"]
                    m = len(subs)
                    for j, sub in enumerate(subs):
                        _walk(sub, depth + 1,
                              label=f"[병렬 {i + 1}/{n} · 분기 파이프 {j + 1}/{m}]",
                              group="parallel")
                    continue
                _walk(br, depth + 1, label=f"[병렬 {i + 1}/{n}]", group="parallel")
            return
        if st.get("_branch_steps"):
            # 방어 — 병렬 밖에서 만날 일은 없지만, 만나면 속을 보이게(opaque 금지)
            subs = st.get("_branch_steps") or []
            for j, sub in enumerate(subs):
                _walk(sub, depth + 1, label=label or f"[분기 파이프 {j + 1}/{len(subs)}]",
                      group=group or "parallel")
            return
        if "_fallback_chain" in st:
            chain = st.get("_fallback_chain") or []
            for i, br in enumerate(chain):
                lb = "[폴백 1차(기본)]" if i == 0 else f"[폴백 {i + 1}차(대안)]"
                _walk(br, depth + 1, label=lb, group="fallback")
            return
        def _walk_branch(act, lb, gname, cw=None):
            """분기 몸 펼침 — 단일 액션(dict)과 파이프(steps 리스트) 둘 다 (9회차:
            파서가 분기 속 파이프를 리스트로 담는데 dict 만 펼쳐 opaque 로 새고 있었다)."""
            if isinstance(act, dict):
                _walk(act, depth + 1, label=lb, group=gname, warn=cw)
                return True
            if isinstance(act, list):
                for j, sub in enumerate(act):
                    _walk(sub, depth + 1,
                          label=(lb if j == 0 else None), group=gname,
                          warn=(cw if j == 0 else None))
                return bool(act)
            return False

        if st.get("_condition"):
            shown = False
            for br in (st.get("branches") or []):
                act = br.get("action")
                cond = br.get("condition")
                lb = f"[조건: {cond}]" if cond is not None else "[else]"
                cw = _condition_syntax_warning(cond) if cond is not None else None
                if _walk_branch(act, lb, "condition", cw):
                    shown = True
            if not shown:
                _opaque_block("조건 블록 — 내부 분기를 읽지 못했습니다(실행 시 결정).", "condition")
            return
        if st.get("_case"):
            source = st.get("source") or ""
            shown = False
            for br in (st.get("branches") or []):
                act = br.get("action")
                pat = br.get("pattern", "")
                if _walk_branch(act, f'[case {source} = "{pat}"]', "case"):
                    shown = True
            if _walk_branch(st.get("default"), f"[case {source} default]", "case"):
                shown = True
            if not shown:
                _opaque_block("case 블록 — 내부 분기를 읽지 못했습니다(실행 시 결정).", "case")
            return
        if st.get("_assign"):
            steps.append({"node": "assign", "action": f"${st.get('name')}", "params": {"expr": st.get("expr")},
                          "kind": "assign", "effect": f"변수 ${st.get('name')} = {st.get('expr')} (한 줄 식)",
                          "safety": "read", "valid": True, "error": None, "param_warning": None, "group": "assign"})
            return
        if st.get("_try"):
            shown = _walk_branch(st.get("body"), "[try]", "try")
            if st.get("catch") is not None:
                shown = _walk_branch(st.get("catch"), "[catch]", "try") or shown
            if st.get("finally") is not None:
                shown = _walk_branch(st.get("finally"), "[finally]", "try") or shown
            if not shown:
                _opaque_block("try 블록 — 내부를 읽지 못했습니다(실행 시 결정).", "try")
            return
        if st.get("_repeat"):
            _hdr = (f"[repeat {st.get('count')}회]" if st.get("mode") == "count"
                    else f"[repeat {st.get('mode')} {st.get('condition')} · max {st.get('max')}"
                         + (f" · every {st.get('every')}" if st.get("every") else "") + "]")
            _cw = (_condition_syntax_warning(st.get("condition"))
                   if st.get("condition") and st.get("mode") == "while" else None)
            if not _walk_branch(st.get("body"), _hdr, "repeat", _cw):
                _opaque_block("repeat 블록 — 내부를 읽지 못했습니다(실행 시 결정).", "repeat")
            return
        if st.get("_goal"):
            # 목표 블록 = 에이전트 반복 루프. 내부 실행이 정적으로 결정되지 않으므로
            # 컨테이너는 보수적 부작용 취급을 유지하고, strategy 속만 펼쳐 보인다.
            _opaque_block(
                f"목표 블록 '{st.get('name') or ''}' — 달성 기준까지 반복 실행합니다(내부는 실행 시 결정).",
                "goal")
            if isinstance(st.get("strategy"), dict):
                _walk(st["strategy"], depth + 1, group="goal")
            return

    # F13-2 (2026-08-19 상상훈련 13회차): 병렬(&) 결과는 이항 변환자(union/merge/join)가
    # 먼저 받아야 한다 — 다른 table 변환자를 바로 물리면 검수 초록 뒤 실행에서 굶는
    # 사각이었다. 소프트 경고(실행기의 정직 거절이 최종 심판).
    _BINARY_AFTER_PARALLEL = {"union", "merge", "join"}
    # T1 (2026-08-29): 머리 변환자가 변환할 통화 없이 서 있으면 검수에서 미리 경고 —
    # 실행기(execute_pipeline·단일 step 경로)의 정직 거절과 같은 판정(ibl_pipe_types 한 벌).
    try:
        from ibl_pipe_types import head_transform_error
        _head_warn = head_transform_error(parsed)
    except Exception:
        _head_warn = None
    for _pi, st in enumerate(parsed):
        _pw = _head_warn if _pi == 0 else None
        if (_pi > 0 and isinstance(parsed[_pi - 1], dict) and parsed[_pi - 1].get("_parallel")
                and isinstance(st, dict) and not st.get("_seq_boundary")
                and st.get("_node") == "table"
                and st.get("action") not in _BINARY_AFTER_PARALLEL):
            _pw = ("병렬(&) 결과는 이항 변환자(union/merge/join)가 먼저 받아야 합니다 — "
                   f"'{st.get('action')}' 은(는) 병렬 봉투를 소비하지 못해 실행에서 거절됩니다. "
                   "분기 하나에만 전처리를 붙이려면 괄호 분기: "
                   "[A] & ([B] >> [table:rename]{…}) >> [table:merge]")
        _walk(st, warn=_pw)

    return {
        "valid": all_valid,
        "syntax_error": None,
        "step_count": len(steps),
        # 부작용 step이 하나라도 있으면 실행 전 명시적 확인을 요구한다 (되돌릴 수 없을 수 있음).
        # 전부 read-only면 무마찰 실행(검수 부담 최소화).
        "has_side_effect": has_side_effect,
        # AI 낱말(ai_call) 포함 — 실행마다 모델 비용·출력 편차(표시 의무, 차단 아님).
        "has_ai_call": has_ai_call,
        "steps": steps,
    }


@router.post("/distill")
async def distill_ibl(req: DistillRequest):
    """수동 모드의 성공 실행을 해마에 증류한다 (자율주행/수동 → 학습 코퍼스의 상향 흐름).

    인간이 검수해 실행한 IBL이라 품질이 높다. 기존 경험 증류 경로를 그대로 재사용:
    top_score < 0.7 일 때만 일반화해 ibl_distilled.json + 해마 인덱스에 축적된다.
    """
    intent = (req.intent or "").strip()
    code = (req.code or "").strip()
    if not intent or not code:
        return {"distilled": False, "reason": "intent/code 가 비어 있습니다."}

    try:
        from ibl_usage_rag import distill_experience
        # 수동 모드 성공 = execute_ibl 성공 1건으로 모델링
        tool_calls = [{"tool_name": "execute_ibl", "input": {"code": code}, "success": True}]
        # ★워커 스레드에서 — 증류는 내부에서 경량 LLM(반성)을 블로킹 호출한다.
        #   translate 와 같은 부류(이벤트 루프 기아 → /health 무응답 → keeper 오발).
        import asyncio
        ok = await asyncio.to_thread(distill_experience, intent, tool_calls, req.top_score)
        return {"distilled": bool(ok)}
    except Exception as e:
        return {"distilled": False, "reason": str(e)}
