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

        from system_tools import _execute_ibl_unified
        result = _execute_ibl_unified({"code": req.code}, project_path)

        # 결과가 str이면 JSON 파싱 시도. 실패 시 plain text로 wrap.
        # (일부 IBL 액션은 JSON이 아닌 평문/markdown/빈문자열을 반환)
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return {"result": result}
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actions/catalog")
async def get_actions_catalog():
    """IBL 액션 카탈로그 — 마법책 UI 데이터 소스.

    5개 노드(sense, self, limbs, others, engines)별로 분류된
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
            }
        nodes_out[node_name] = {"actions": actions, "count": len(actions)}
        total += len(actions)

    return {"nodes": nodes_out, "total": total}


# === 수동 모드: 컴파일러 프론트엔드 ===
# 모델은 선장이 아니라 컴파일러다. 자연어를 IBL로 "번역"만 하고,
# 지능(주권)은 인간 + 언어(IBL)에 남는다. 검수는 코드가 아니라 효과(dry-run)로 한다.

# 번역 task 프레이밍 — IBL 문법은 아래 정식 교재(12_ibl_only.md)에 맡기고, 여기선 '번역만 하라'는 역할과 출력 규칙만 둔다.
_IBL_TRANSLATE_TASK = """너는 IBL(IndieBiz Logic) 컴파일러다. 사용자의 자연어 명령을 IBL 코드로 번역만 한다.
아래 <ibl_spec>가 IBL 문법·5노드·패턴의 정식 명세다 (모든 에이전트가 쓰는 교재). 이대로 따르라.

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
    """자연어 의도 → IBL 코드 (해마 용례 + 경량 모델). 실행하지 않는다.

    수동 모드의 1단계. 경량 모델(거의 무료)이 해마(과거 용례)에 기대어
    번역만 하고, 사용자는 다음 단계에서 dry-run으로 검수한다.
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

    # 2) 경량 모델: 용례를 근거로 IBL 코드 번역
    from consciousness_agent import lightweight_ai_call
    prompt = f'사용자 명령: "{intent}"\n\n'
    if references:
        prompt += f"참고 용례 (이 액션 이름들만 사용하라):\n{references}\n\n"
    else:
        prompt += "(관련 과거 용례 없음 — 위 5개 노드 지식으로 직접 번역하라.)\n\n"
    prompt += "위 명령을 IBL 코드로 번역하라. IBL 코드만 출력."

    spec = _load_ibl_spec()
    system_prompt = _IBL_TRANSLATE_TASK + (f"\n\n<ibl_spec>\n{spec}\n</ibl_spec>" if spec else "")
    raw = lightweight_ai_call(prompt, system_prompt=system_prompt)
    if not raw:
        raise HTTPException(status_code=503, detail="경량 모델이 응답하지 않았습니다. lightweight_ai_config.json을 확인하세요.")

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

        steps.append({
            "node": node, "action": action, "params": params,
            "kind": "action",
            "effect": _action_description(node, action) or "(설명 없음)",
            "safety": safety,
            "valid": ok, "error": err,
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
