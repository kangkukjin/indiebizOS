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
    project_id: Optional[str] = None   # 수동/앱 모드 등 표면이 자기 프로젝트를 지정
    project_path: str = "."
    agent_id: Optional[str] = None     # 발신 신원(channel_send/read 게이트). out-of-process 프로바이더(Claude Code)가
                                       # MCP→HTTP로 자기 agent_id를 실어 보내는 통로. None이면 신원 없음(외부 채널 차단).
    task_id: Optional[str] = None      # 태스크 컨텍스트(위임 체인). claude_code 재진입 경로는 원 요청과 다른
                                       # 스레드라 threading.local의 task_id가 비어 [others:delegate]{scope:"cross"}가
                                       # "현재 태스크 ID 없음"으로 실패했다 → agent_id처럼 payload로 복원 (없으면 현 동작 그대로).
    surface: Optional[str] = None      # 요청한 *표면* ('web' = 원격런처/포털/폰 WebView).
                                       # 소리·저장 같은 "어디서 나야 하는가"의 판정 축 — 실행하는 몸이
                                       # 아니라 보고 있는 표면이 정한다(thread_context.set_current_surface).
                                       # 데스크탑 일렉트론은 맥 자신이라 보내지 않는다(= 맥 재생이 곧 여기서 재생).


class EmbedRequest(BaseModel):
    """폰-자아 해마 인코더 렌트(PHONE_SELF_HOSTING_HANDOFF §6.3): 텍스트→768벡터.
    단건은 text, 배치는 texts. 둘 다 오면 texts 우선."""
    text: Optional[str] = None
    texts: Optional[List[str]] = None


class GuideRequest(BaseModel):
    """가이드 읽기 — **claude_code(아웃오브프로세스 MCP) 프로바이더 전용 브리지**.

    in-process 프로바이더(Gemini 등)는 system_tools 의 read_guide → _search_guide 를
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

        # 직접조작 표면(앱/수동 모드)은 소유자가 직접 모는 것 = 시스템 운영자.
        # agent_id가 비어 있으면 system_ai 신원으로 채널 발신(메신저 작성·커뮤니티 게시)을 허용한다.
        # (이 표면은 데스크탑=localhost 또는 원격=런처 인증 게이트 뒤에 있음.)
        agent_id = req.agent_id
        if not agent_id and req.project_id in ProjectManager.SYSTEM_PROJECT_IDS:
            agent_id = "system_ai"

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
                                    set_current_task_id, get_current_task_id,
                                    clear_current_task_id)

        def _run_in_context():
            _prev_pid = get_current_project_id()
            _prev_surface = get_current_surface()
            _prev_task = get_current_task_id()
            if req.project_id:
                set_current_project_id(req.project_id)
            set_current_surface(req.surface)
            # 태스크 컨텍스트 복원 — claude_code(MCP→HTTP 재진입)가 실어 보낸 부모 task_id.
            # cross 위임(_execute_call_project_agent)이 get_current_task_id()로 부모를 찾는다.
            if req.task_id:
                set_current_task_id(req.task_id)
            try:
                from system_tools import _execute_ibl_unified
                return _execute_ibl_unified({"code": req.code}, project_path, agent_id=agent_id)
            finally:
                set_current_project_id(_prev_pid)
                set_current_surface(_prev_surface)
                if req.task_id:
                    # clear 는 set 과 대칭 — task_sysai_ 접두사가 이 워커 스레드에 등록한
                    # 활성작업(_touch_active_work)도 함께 해제된다.
                    if _prev_task:
                        set_current_task_id(_prev_task)
                    else:
                        clear_current_task_id()

        import asyncio
        result = await asyncio.to_thread(_run_in_context)

        # 결과가 str이면 JSON 파싱 시도. 실패 시 plain text로 wrap.
        # (일부 IBL 액션은 JSON이 아닌 평문/markdown/빈문자열을 반환)
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
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
        return _attach_steer(derive_items(result), req.agent_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

    in-process 경로(system_tools.handle_tool 'read_guide')와 **동일한 _search_guide** 를
    호출해 프로바이더 간 동작 동치를 보장한다. 이 라우트는 순수 배관(가이드 검색)일 뿐
    프로바이더 행동을 바꾸지 않는다 — read_guide 도구가 노출되는 곳은 claude_code 의
    MCP 화이트리스트(EAGER_TOOLS)뿐이다."""
    try:
        from ibl_routing import _search_guide
        return _search_guide(req.query, {"read": req.read})
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
    from ibl_access import _load_nodes_data
    data = _load_nodes_data()
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
    _IBL_TRANSLATE_TASK,
    _load_ibl_spec,
    _strip_code_fence,
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

        spec = _load_ibl_spec()
        system_prompt = _IBL_TRANSLATE_TASK + (f"\n\n<ibl_spec>\n{spec}\n</ibl_spec>" if spec else "")
        # 수동 모드 번역 = 모델 기어 '실행' 축(role=translate)으로 해소.
        return references, system_ai_call(prompt, system_prompt=system_prompt, role="translate")

    import asyncio
    references, raw = await asyncio.to_thread(_do_translate)
    if not raw:
        raise HTTPException(status_code=503, detail="번역 모델이 응답하지 않았습니다. 모델 기어(실행 축) 설정을 확인하세요.")

    ibl_code = _strip_code_fence(raw)
    return {
        "intent": intent,
        "ibl_code": ibl_code,
        "references": references,  # 리터러시: 어떤 과거 용례를 근거로 했는지 병기
        "raw": raw,
    }


def _action_description(node: str, action: str) -> str:
    """노드/액션의 사람이 읽는 효과 설명 (dry-run 미리보기용)."""
    try:
        from ibl_access import _load_nodes_data
        data = _load_nodes_data() or {}
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
        from ibl_access import _load_nodes_data
        data = _load_nodes_data() or {}
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
        from ibl_registry import _load_nodes_config
        return sorted((_load_nodes_config().get("nodes") or {}).keys())
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
        from ibl_access import _load_nodes_data
        from ibl_ops import resolve_op
        data = _load_nodes_data() or {}
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

    def _emit_action(st: dict, label: str = None, group: str = None, warn: str = None):
        """평범한 액션 한 개를 검증해 steps 에 싣는다. label=구조 안 위치 표시(effect 앞),
        group=기계용 표식(parallel/fallback/condition/case/goal), warn=구조 층 경고(조건 문법 등)."""
        nonlocal all_valid, has_side_effect
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

        if warn:
            param_warning = f"{param_warning} / {warn}" if param_warning else warn

        effect = _effect_description(node, action, params) or "(설명 없음)"
        entry = {
            "node": node, "action": action, "params": params,
            "kind": "action",
            "effect": f"{label} {effect}" if label else effect,
            "safety": safety,
            "valid": ok, "error": err,
            "param_warning": param_warning,
        }
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
            st.get("_parallel") or "_fallback_chain" in st
            or st.get("_condition") or st.get("_case") or st.get("_goal"))

    def _walk_each_do(st: dict, depth: int):
        """[table:each] 의 do 문자열 속 문장을 펼쳐 검증한다.

        do 는 이 언어가 코드를 *문자열로* 나르는 유일한 자리 — 여기만 안 펼치면
        do 안의 부작용·무효 액션이 'each 한 줄'(블랭킷 write) 뒤에 숨어
        조종실의 번역→dry-run→실행 계약이 반쪽이 된다."""
        nonlocal all_valid
        params = st.get("params", {}) or {}
        do = params.get("do")
        if isinstance(do, list):
            do = "\n".join(str(x) for x in do if str(x).strip())
        if not do or not str(do).strip():
            return
        do = str(do)
        from ibl_parser import parse as _parse_do, IBLSyntaxError as _DoSynErr
        try:
            try:
                inner = _parse_do(do)
            except _DoSynErr:
                # $it 치환 자리가 따옴표 밖(예: {n: $it.n})이면 실행 시엔 합법 —
                # 자리만 더미(1)로 메워 재시도한다. 이걸로도 안 되면 진짜 문법 오류.
                inner = _parse_do(re.sub(r"\$\w+(?:\.\w+)*", "1", do))
        except _DoSynErr as e:
            all_valid = False
            steps.append({
                "node": "table", "action": "each", "params": {}, "kind": "block",
                "effect": f"each do 문장 문법 오류 — 모든 행이 실패합니다: {str(e)[:160]}",
                "safety": "unknown", "valid": False, "error": str(e)[:200],
                "group": "each",
            })
            return
        for ist in inner:
            _walk(ist, depth + 1, label="[each 속]", group="each")

    def _condition_syntax_warning(cond: str):
        """조건 좌변이 node:action 소스 참조로 파싱되는지 미리 검사.

        실행기(_evaluate_sense_condition)는 좌변이 소스 참조가 아니면 값 None → 조용히
        거짓 판정이라, 자연어 조건('[if: 디스크가 부족하면]')이 침묵으로 else 에 떨어진다.
        dry-run 이 유일하게 미리 소리 낼 수 있는 자리다."""
        try:
            from ibl_executors import _find_top_level_comparison_op, _parse_source_ref
            op_info = _find_top_level_comparison_op(cond)
            src = cond[:op_info[0]].strip() if op_info else cond.strip()
            if _parse_source_ref(src) is None:
                return (f"조건 좌변 '{src}' 이(가) node:action 소스 참조가 아닙니다 — "
                        "실행 시 이 조건은 조용히 거짓이 되어 다음 분기/else 로 넘어갑니다. "
                        '예: [if: sense:host{op: "status"}.cpu_percent > 80]')
            return None
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
            if st.get("_node") == "table" and st.get("action") == "each":
                _walk_each_do(st, depth)
            return
        if st.get("_parallel"):
            branches = st.get("branches") or []
            n = len(branches)
            for i, br in enumerate(branches):
                _walk(br, depth + 1, label=f"[병렬 {i + 1}/{n}]", group="parallel")
            return
        if "_fallback_chain" in st:
            chain = st.get("_fallback_chain") or []
            for i, br in enumerate(chain):
                lb = "[폴백 1차(기본)]" if i == 0 else f"[폴백 {i + 1}차(대안)]"
                _walk(br, depth + 1, label=lb, group="fallback")
            return
        if st.get("_condition"):
            shown = False
            for br in (st.get("branches") or []):
                act = br.get("action")
                if isinstance(act, dict):
                    shown = True
                    cond = br.get("condition")
                    lb = f"[조건: {cond}]" if cond is not None else "[else]"
                    cw = _condition_syntax_warning(cond) if cond is not None else None
                    _walk(act, depth + 1, label=lb, group="condition", warn=cw)
            if not shown:
                _opaque_block("조건 블록 — 내부 분기를 읽지 못했습니다(실행 시 결정).", "condition")
            return
        if st.get("_case"):
            source = st.get("source") or ""
            shown = False
            for br in (st.get("branches") or []):
                act = br.get("action")
                if isinstance(act, dict):
                    shown = True
                    pat = br.get("pattern", "")
                    _walk(act, depth + 1, label=f'[case {source} = "{pat}"]', group="case")
            if isinstance(st.get("default"), dict):
                shown = True
                _walk(st["default"], depth + 1, label=f"[case {source} default]", group="case")
            if not shown:
                _opaque_block("case 블록 — 내부 분기를 읽지 못했습니다(실행 시 결정).", "case")
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

    for st in parsed:
        _walk(st)

    return {
        "valid": all_valid,
        "syntax_error": None,
        "step_count": len(steps),
        # 부작용 step이 하나라도 있으면 실행 전 명시적 확인을 요구한다 (되돌릴 수 없을 수 있음).
        # 전부 read-only면 무마찰 실행(검수 부담 최소화).
        "has_side_effect": has_side_effect,
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
