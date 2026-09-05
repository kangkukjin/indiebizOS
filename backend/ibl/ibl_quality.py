# -*- coding: utf-8 -*-
"""ibl_quality.py — criteria 품질 계약 단일 소스 (2026-08-27, docs/IBL_QUALITY_CONTRACT_HANDOFF.md)

원샷 AI 단계는 예외를 던지지 않는다 — 그럴듯하지만 나쁜 결과를 성공으로 반환한다.
`criteria` 는 그 실패 모드를 **위치 있는 실패**로 만드는 표준 기능어 param 이다
(사용자 판정 2026-08-27: 이름=criteria, 미달 시 재시도 1회 기본 on).

    [table:brief]{instruction: "급변 종목 3문장 보고",
                  criteria: "종목명·수치 포함, items 에 없는 주장 없음"}

의미론:
  · criteria 선언 step 은 실행 직후 판정자 1회 심사 — 판정자의 모델 수준은 **기어의
    평가 축**(role="evaluate")이 정한다(절약·균형=경량, 최대=고급. 단언 금지 — 기어가 정본).
  · 미달 → **재시도 1회**(판정 사유를 instruction 에 얹어 재실행 — ai_call 액션이
    instruction 을 선언한 경우만. JSON 재시도 1회·others:ask 1회 자가교정과 같은 규약)
    → 재판정 → 그래도 미달이면 error_type="quality" 실패(트레이스백이 그 step 을 가리킴).
  · 통과는 criteria_verdict 로, 재시도 후 통과는 _criteria_retried(정직 표지 — 출처가
    재시도본)로 신고. 판정 불능(판정자 미가용·응답 파싱 실패)은 **통과 + 신고**
    (parse_eval_verdict 선례 — 잘못된 미달 판정은 재실행 낭비를 부른다. 침묵은 없다).
  · criteria 없으면 판정자 호출 0 (옵트인, 기존 문장 무변경). 실행 자체가 실패한
    step 은 판정하지 않는다 — 실행 실패가 우선이고 트레이스백이 이미 위치를 나른다.

경계 규칙 둘:
  · **액션이 criteria 를 자기 param 으로 선언하면 그 액션의 것이다** — engines:image_read
    {op:"critic"} 의 criteria 는 심사 도구의 입력이지 이 계약이 아니다(선언 = tool.json
    input_schema, B34 관문과 같은 진실 소스). 엔진 계약은 미선언 액션에만 적용.
  · 블록(_try/_goal/_condition/_case/_repeat/_assign/_parallel)에는 적용하지 않는다 —
    goal 은 자기 달성 판정을 이미 갖고, 블록 몸 leaf 들이 각자 criteria 를 갖는 게 맞다.

잎이 아니다(oneshot·registry 를 쓴다) — 모든 형제 import 는 지연(순환 회피).
"""
import json
import re
from typing import Any, Callable, Dict, Optional

JUDGE_OUTPUT_CAP = 6000     # 판정자에게 보여줄 결과 상한 (초과는 판정자에게도 절단 고지)
REJECTED_RAW_CAP = 4000     # 미달 실패 봉투에 원형으로 싣는 출력 상한 (초과=구조 요약)

_BLOCK_MARKS = ("_goal", "_condition", "_case", "_try", "_repeat", "_assign", "_parallel")

_JUDGE_SYSTEM = (
    "너는 품질 판정자다. 도구 실행 결과가 주어진 기준을 충족하는지만 판정한다. "
    "기준에 명시된 것만 따지고, 기준 밖의 취향을 추가하지 마라. 애매하면 충족으로 판정하라. "
    "'기계 계수' 블록이 주어지면 행 수·열 유무·조건 만족 행 수는 그 수로 판정한다 — 원문을 다시 세지 마라"
    "(원문은 잘려 보일 수 있고, 계수는 결과 전체에서 센 정본이다). "
    '반드시 JSON 하나로만 답하라: {"pass": true|false, "reason": "한두 문장"}'
)

FACTS_MAX_COLS = 24         # 기계 계수에 실을 열 상한


def _machine_facts(result: Any, max_cols: int = FACTS_MAX_COLS) -> str:
    """결과 통화(items/table)에서 기계가 센 사실 한 블록 — 행 수·열별 값 있음 수·불리언 true 수.

    2026-09-05(ep2832, 시스템 AI 보고): criteria "selected 가 true 인 행이 정확히 4행" 이 5행 결과에
    pass 로 돌아왔다. 판정자는 원문 앞 6,000자만 보고 계수는 받지 못했다 — 48행 표는 그 안에
    들어가지 않으니 셀 수가 없었다. 셀 수 있는 것은 기계가 세어 준다(반증 가능한 계수는 판정자의
    추정이 아니라 정본). 통화가 아니면(효과·산문) 빈 문자열 — 판정은 종전대로 원문으로."""
    obj = result
    if isinstance(obj, str):
        s = obj.strip()
        if not s or s[0] not in "{[":
            return ""
        try:
            obj = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            return ""
    items = None
    if isinstance(obj, list):
        items = obj
    elif isinstance(obj, dict):
        if isinstance(obj.get("items"), list):
            items = obj["items"]
        else:
            try:
                from common.currency import derive_items
                d = derive_items(dict(obj))
                if isinstance(d, dict) and isinstance(d.get("items"), list):
                    items = d["items"]
            except Exception:
                items = None
    if items is None:
        return ""
    n = len(items)
    rows = [r for r in items if isinstance(r, dict)]
    cols: list = []
    for r in rows:
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    lines = [f"행 수 {n}" + (f" (dict 행 {len(rows)})" if len(rows) != n else "")]
    for c in cols[:max_cols]:
        vals = [r.get(c) for r in rows]
        present = sum(1 for v in vals if v is not None and v != "" and v != [] and v != {})
        line = f"- {c}: 값 있음 {present}/{n}"
        bools = [v for v in vals if isinstance(v, bool)]
        if bools:
            line += f" · true {sum(1 for v in bools if v)} · false {sum(1 for v in bools if not v)}"
        lines.append(line)
    if len(cols) > max_cols:
        lines.append(f"- …외 열 {len(cols) - max_cols}개")
    return "\n".join(lines)


def _declared_props(action_config: Optional[dict]) -> Dict[str, Any]:
    """액션의 선언 param — tool.json input_schema.properties (B34 관문과 같은 진실 소스).
    handler 라우터가 아니면 action_config.params 폴백(없으면 빈 dict = 미선언)."""
    if not isinstance(action_config, dict):
        return {}
    tool = action_config.get("tool")
    if tool:
        try:
            from tool_loader import load_tool_schema
            props = (((load_tool_schema(tool) or {}).get("input_schema") or {})
                     .get("properties") or {})
            if props:
                return props
        except Exception:
            pass
    p = action_config.get("params")
    return p if isinstance(p, dict) else {}


def _action_config(node: str, action: str) -> Optional[dict]:
    try:
        from ibl_engine import load_nodes_installed
        return ((load_nodes_installed().get("nodes", {}).get(node) or {})
                .get("actions", {}).get(action))
    except Exception:
        return None


def pop_criteria(tool_input: Any) -> Optional[str]:
    """leaf 액션의 params 에서 엔진 소유 criteria 를 꺼낸다(핸들러에 흘리지 않음).

    액션이 criteria 를 선언했으면 손대지 않고 None — 그 액션의 param 이다.
    문자열 아닌 값도 손대지 않는다(param 경고 경로가 정직하게 처리)."""
    if not isinstance(tool_input, dict) or any(tool_input.get(m) for m in _BLOCK_MARKS):
        return None
    node, action = tool_input.get("_node"), tool_input.get("action")
    if not node or not action:
        return None
    params = tool_input.get("params")
    if not isinstance(params, dict):
        return None
    val = params.get("criteria")
    if not isinstance(val, str) or not val.strip():
        return None
    cfg = _action_config(node, action)
    if "criteria" in _declared_props(cfg):
        return None                      # 액션 자신의 어휘 — 엔진이 가로채지 않는다
    params.pop("criteria")
    return val.strip()


def _call_judge(prompt: str) -> Optional[str]:
    """판정자 1회 호출 — 테스트가 이 이름을 패치한다.

    ★모델 수준은 여기가 아니라 **기어의 평가 축**(role="evaluate")이 정한다 —
    cognitive_eval 의 달성 기준 평가자와 같은 축이다(절약·균형=경량, 최대=고급 이
    사용자 설정의 실물, 2026-08-27 정정: 옛 배선은 background(분류 축)로 박아
    "경량 판정자"를 단언했는데, 그건 기어의 평가-축 의도를 우회하는 티어 하드코딩의
    변형이었다). 구현(인지층 oneshot)은 능력 테이블로 주입받는다(_cap — 라우팅층은
    인지층을 모른다, 의존 역전). 미등록(부팅 배선 밖 스크립트)이면 예외 → 호출자가
    '판정 불능=통과+신고' 로 처리한다."""
    from ibl_routing import _cap
    return _cap("oneshot_ai_call")(prompt=prompt, system_prompt=_JUDGE_SYSTEM,
                                   role="evaluate")


def _judge(criteria: str, result: Any, node: str, action: str,
           params: Optional[dict]) -> Dict[str, Any]:
    """반환 {pass: bool, reason: str} 또는 {unjudgeable: True, reason}."""
    s = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    clipped = ""
    if len(s) > JUDGE_OUTPUT_CAP:
        clipped = f"\n(결과가 길어 앞 {JUDGE_OUTPUT_CAP}자만 보임 — 그 범위에서 판정)"
        s = s[:JUDGE_OUTPUT_CAP]
    inst = ""
    if isinstance(params, dict):
        for k in ("instruction", "do", "prompt"):
            v = params.get(k)
            if isinstance(v, str) and v.strip():
                inst = f"\n\n실행 지시:\n{v[:1000]}"
                break
    facts = _machine_facts(result)
    facts_block = (f"기계 계수(결과 전체에서 센 정본 — 아래 원문이 잘려도 이 수가 맞다):\n{facts}\n\n"
                   if facts else "")
    prompt = (f"[{node}:{action}] 실행 결과의 품질 판정.\n\n"
              f"충족해야 할 기준:\n{criteria}{inst}\n\n"
              f"{facts_block}"
              f"실행 결과:{clipped}\n{s}\n\nJSON 으로만 답하라.")
    try:
        raw = _call_judge(prompt)
    except Exception as e:
        return {"unjudgeable": True, "reason": f"판정자 호출 실패: {type(e).__name__}: {e}"}
    if not raw or not isinstance(raw, str):
        return {"unjudgeable": True, "reason": "판정자 응답 없음"}
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            d = json.loads(m.group())
            if isinstance(d, dict) and isinstance(d.get("pass"), bool):
                return {"pass": d["pass"], "reason": str(d.get("reason") or "").strip()}
        except Exception:
            pass
    # 관용 폴백 — 판정 토큰(parse_eval_verdict 부류). 그래도 없으면 판정 불능.
    t = raw.upper()
    if re.search(r"\bFAIL", t) and not re.search(r"\bPASS", t):
        return {"pass": False, "reason": raw.strip()[:300]}
    if re.search(r"\bPASS", t):
        return {"pass": True, "reason": raw.strip()[:300]}
    return {"unjudgeable": True, "reason": f"판정자 응답 파싱 실패: {raw.strip()[:200]}"}


def _mark(result: Any, extra: Dict[str, Any]) -> Any:
    """판정 사실을 결과에 병기 — dict 는 키로, JSON 문자열은 파싱-병기, 스칼라는 불변
    (스칼라의 신고는 _quality_meta 사이드채널이 step 기록으로 나른다, F19-1 규약).

    ★표지는 **머리에** 넣는다 (2026-08-28 실측): 에피소드 로그는 꼬리를 절단하므로,
    꼬리에 붙인 판정 표지는 결과가 크면 매번 잘려 라이브 관찰(unjudged 비율·재시도
    통과율)이 원리적으로 불가능했다. JSON 객체의 키 순서는 의미가 아니라 직렬화
    순서일 뿐이라 소비자 계약은 불변이다."""
    if isinstance(result, dict):
        return {**{k: v for k, v in extra.items() if k not in result}, **result}
    if isinstance(result, str):
        s = result.lstrip()
        if s.startswith("{"):
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    merged = {**{k: v for k, v in extra.items() if k not in obj}, **obj}
                    return json.dumps(merged, ensure_ascii=False)
            except Exception:
                pass
    return result


def _rejected_view(result: Any) -> Any:
    """미달 봉투에 싣는 원 출력 — 작으면 원형, 크면 구조 요약(summarize_result, B27-1)."""
    s = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    if len(s) <= REJECTED_RAW_CAP:
        return result if isinstance(result, str) else result
    try:
        from ibl_envelope import summarize_result
        return {"_summarized": True, **summarize_result(result)}
    except Exception:
        return s[:REJECTED_RAW_CAP] + f"…(+{len(s) - REJECTED_RAW_CAP}자)"


def apply_criteria(criteria: str, result: Any, tool_input: dict, node: str, action: str,
                   project_path: str, agent_id: Optional[str],
                   rerun: Callable[[dict], Any]) -> Any:
    """실행 결과에 품질 계약 적용 — 판정 → (미달이면 재시도 1회 → 재판정) → 통과 신고
    또는 error_type=quality 실패. execute_ibl 최외곽 관문에서만 부른다."""
    from workflow_engine import is_error_result
    from ibl_traceback import build_tb

    if is_error_result(result):
        return result                    # 실행 실패가 우선 — criteria 는 미판정

    params = tool_input.get("params") if isinstance(tool_input, dict) else None
    v = _judge(criteria, result, node, action, params)

    if v.get("unjudgeable"):
        note = f"criteria 판정 불능 — 통과 처리: {v['reason']}"
        tool_input["_quality_meta"] = {"criteria_verdict": "unjudged", "criteria_note": note}
        return _mark(result, {"criteria_verdict": "unjudged", "criteria_note": note})

    if v["pass"]:
        tool_input["_quality_meta"] = {"criteria_verdict": "pass"}
        return _mark(result, {"criteria_verdict": "pass"})

    reason1 = v.get("reason") or "기준 미달"

    # ── 재시도 1회 (기본 on, 사용자 판정) — ai_call 액션이 instruction 을 선언한 경우만
    #    (피드백을 얹을 자리가 있어야 재시도가 유의미하다. 결정론 액션 재실행 = 같은 결과).
    retried = False
    cfg = _action_config(node, action) or {}
    if cfg.get("ai_call") and "instruction" in _declared_props(cfg):
        retried = True
        try:
            from ibl_routing import _normalize_param_aliases
            p2 = _normalize_param_aliases(node, action, dict(params or {}), cfg)
        except Exception:
            p2 = dict(params or {})
        base_inst = p2.get("instruction") if isinstance(p2.get("instruction"), str) else ""
        p2["instruction"] = (base_inst + f"\n\n[품질 재시도] 이전 출력이 기준을 못 채웠다: {reason1}"
                                         f"\n기준: {criteria}\n기준을 채우도록 다시 수행하라.")
        ti2 = {**tool_input, "params": p2}
        try:
            result2 = rerun(ti2)
        except Exception as e:
            result2 = {"success": False, "error": f"{type(e).__name__}: {e}"}
        if not is_error_result(result2):
            v2 = _judge(criteria, result2, node, action, p2)
            if v2.get("unjudgeable") or v2.get("pass"):
                meta = {"criteria_verdict": "pass_after_retry", "criteria_feedback": reason1,
                        "_criteria_retried": True}
                if v2.get("unjudgeable"):
                    meta["criteria_note"] = f"재판정 불능 — 통과 처리: {v2['reason']}"
                tool_input["_quality_meta"] = dict(meta)
                return _mark(result2, meta)
            reason1 = v2.get("reason") or reason1
        # 재시도 실행 자체가 실패한 경우: 원 출력 기준 미달이 최종 판정 — 아래로 떨어진다.

    # ── 품질 실패: 위치 있는 실패 — 파이프 이음매가 이 트레이스백을 승계해 프레임을 얹는다.
    fail = {
        "success": False,
        "error": f"criteria 미달: {reason1}",
        "criteria": criteria,
        "criteria_verdict": "fail",
        "quality_retried": retried,
        "rejected_result": _rejected_view(result),
        "traceback": build_tb(f"criteria 미달: {reason1}", "quality"),
    }
    tool_input["_quality_meta"] = {"criteria_verdict": "fail", "quality_retried": retried}
    return fail
