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
        project_path = req.project_path
        if req.project_id:
            from project_manager import ProjectManager
            p = ProjectManager().get_project_path(req.project_id)
            if p and p.exists():
                project_path = str(p.resolve())

        # 직접조작 표면(앱/수동 모드)은 소유자가 직접 모는 것 = 시스템 운영자.
        # agent_id가 비어 있으면 system_ai 신원으로 채널 발신(메신저 작성·커뮤니티 게시)을 허용한다.
        # (이 표면은 데스크탑=localhost 또는 원격=런처 인증 게이트 뒤에 있음.)
        agent_id = req.agent_id
        if not agent_id and req.project_id in ("앱모드", "수동모드"):
            agent_id = "system_ai"

        # 직접조작 표면은 thread_context에 자기 project_id를 명시한다.
        # 이 엔드포인트는 이벤트 루프 스레드에서 동기 실행되므로, 직전 에이전트가
        # 남긴 project_id가 thread-local에 남아 있을 수 있다(누수). 이를 덮어써,
        # scope 판단(예: lecture 저장 위치=프로젝트 vs 전역)이 엉뚱한 프로젝트로
        # 새는 것을 막는다. 호출 후 이전 값으로 복원.
        from thread_context import set_current_project_id, get_current_project_id
        _prev_pid = get_current_project_id()
        if req.project_id:
            set_current_project_id(req.project_id)
        try:
            from system_tools import _execute_ibl_unified
            result = _execute_ibl_unified({"code": req.code}, project_path, agent_id=agent_id)
        finally:
            set_current_project_id(_prev_pid)

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
        return derive_items(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
# 모델은 선장이 아니라 컴파일러다. 자연어를 IBL로 "번역"만 하고,
# 지능(주권)은 인간 + 언어(IBL)에 남는다. 검수는 코드가 아니라 효과(dry-run)로 한다.

# 번역 task 프레이밍 — IBL 문법은 아래 정식 교재(12_ibl_only.md)에 맡기고, 여기선 '번역만 하라'는 역할과 출력 규칙만 둔다.
_IBL_TRANSLATE_TASK = """너는 IBL(IndieBiz Logic) 컴파일러다. 사용자의 자연어 명령을 IBL 코드로 번역만 한다.
아래 <ibl_spec>가 IBL 문법·노드 체계·패턴의 정식 명세다 (모든 에이전트가 쓰는 교재). 이대로 따르라.

규칙:
1. 아래 '참고 용례'에 나온 실제 액션 이름만 사용하라. 지어내지 마라.
2. IBL 원문만 출력하라 — execute_ibl('...') 같은 호출 래퍼, 따옴표, 코드블록 표시(```), 설명·인사 모두 금지. [node:action]{...} 으로 시작해서 끝나야 한다.
3. 의도가 모호하면 가장 단순하고 되돌릴 수 있는 해석을 택하라."""


def _load_ibl_spec() -> str:
    """모든 에이전트가 받는 정식 IBL 교재(12_ibl_only.md)를 그대로 읽는다.
    수동 모드 번역기도 같은 문법 진실 소스를 쓰게 해 중복을 없앤다 (사람-페이스라 매번 읽어도 무방)."""
    try:
        from runtime_utils import get_base_path
        p = get_base_path() / "data" / "common_prompts" / "fragments" / "12_ibl_only.md"
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _strip_code_fence(text: str) -> str:
    """모델 출력에서 IBL 원문만 추출. 앞의 펜스/설명/execute_ibl( 래퍼와
    뒤의 따옴표/괄호 잔여물(예: ...}')))을 모두 떼어낸다."""
    t = (text or "").strip()
    # ```lang ... ``` 펜스 제거
    fence = re.search(r"```[a-zA-Z]*\s*(.+?)\s*```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    # 첫 [node:action] 부터 채택 (앞에 execute_ibl(' 같은 래퍼·설명이 붙은 경우)
    m = re.search(r"\[[a-z_]+:[a-z_]+\]", t)
    if m:
        t = t[m.start():].strip()
    # 마지막 } 또는 ] 이후는 잘라낸다 (execute_ibl('...') 흉내의 ') 꼬리, 후행 설명 제거)
    last = max(t.rfind("}"), t.rfind("]"))
    if last != -1:
        t = t[:last + 1]
    return t


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
    raw = system_ai_call(prompt, system_prompt=system_prompt, role="translate")
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


def _load_safety_map() -> dict:
    """self-check가 만든 부작용 분류(self_check_plan.json)를 (node, action) → safe(bool)로.

    self-check가 이미 쓰는 캐시를 그대로 재사용한다. LLM 재생성은 트리거하지 않는다
    (dry-run 자체가 부작용을 내면 안 되므로 파일만 읽는다)."""
    plan_path = os.path.join(os.path.dirname(__file__), "..", "data", "self_check_plan.json")
    try:
        with open(plan_path, encoding="utf-8") as f:
            plan = json.load(f)
        return {(a.get("node", ""), a.get("action", "")): bool(a.get("safe"))
                for a in plan.get("actions", [])}
    except Exception:
        return {}


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

    def _safety(node: str, action: str) -> str:
        # 'read' = 부작용 없음(되돌릴 필요 없음), 'write' = 부작용 있음, 'unknown' = 미분류
        s = safety_map.get((node, action))
        return "read" if s is True else "write" if s is False else "unknown"

    steps = []
    all_valid = True
    has_side_effect = False
    for st in parsed:
        node = st.get("_node", "")
        action = st.get("action", "")
        params = st.get("params", {}) or {}

        # goal/조건/케이스 같은 복합 블록은 단순 검증을 건너뛴다
        if st.get("_goal") or st.get("_condition") or st.get("_case"):
            has_side_effect = True  # 내부 분기를 정적으로 알 수 없으므로 보수적으로 부작용 취급
            steps.append({
                "node": node, "action": action, "params": params,
                "kind": "block",
                "effect": "복합 블록(목표/조건/케이스) — 실행 시 내부에서 분기합니다.",
                "safety": "unknown",
                "valid": True, "error": None,
            })
            continue

        valid_actions = get_node_actions(node) if node else set()
        if not node:
            ok, err = False, "노드가 지정되지 않았습니다."
        elif not valid_actions:
            ok, err = False, f"'{node}'는 알 수 없는 노드입니다. (sense/self/limbs/others/engines)"
        elif action not in valid_actions:
            ok, err = False, f"'{node}' 노드에 '{action}' 액션이 없습니다."
        else:
            ok, err = True, None

        if not ok:
            all_valid = False

        safety = _safety(node, action)
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

        steps.append({
            "node": node, "action": action, "params": params,
            "kind": "action",
            "effect": _action_description(node, action) or "(설명 없음)",
            "safety": safety,
            "valid": ok, "error": err,
            "param_warning": param_warning,
        })

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
        ok = distill_experience(intent, tool_calls, req.top_score)
        return {"distilled": bool(ok)}
    except Exception as e:
        return {"distilled": False, "reason": str(e)}
