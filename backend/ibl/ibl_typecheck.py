"""Observed tool shapes and compiler-backed source inspection."""
import re
from typing import Any, Dict, List, Optional
_FIXTURE_OP_RE = re.compile(r"\bop\s*:\s*[\"']([\w-]+)[\"']")

def _action_def(node: str, action: str) -> Optional[Dict[str, Any]]:
    try:
        from ibl_registry import load_nodes_installed
        cfg = (load_nodes_installed().get("nodes", {}).get(node, {}).get("actions", {}).get(action))
        if isinstance(cfg, dict):
            return cfg
    except Exception:
        pass
    try:
        from ibl_access import load_nodes_raw
        cfg = (load_nodes_raw() or {}).get("nodes", {}).get(node, {}).get("actions", {}).get(action)
        return cfg if isinstance(cfg, dict) else None
    except Exception:
        return None

def catalog_entry(node: str, action: str, params: Dict[str, Any], *,
                  kinds=("items", "table")) -> Optional[Dict[str, Any]]:
    """fixture 실측 항목(data/ibl_return_shapes.json) — `node:action` · `#op` · `@param=값` 순. 없으면 None(미상).

    현행 컴파일러가 관측 열과 키를 같은 규칙으로 해소한다.
    상한에 잘린 관측(`more`)은 전체 열이 아니다 — 그걸 전체로 읽으면 잘린 뒤쪽 열을 '없는 열'로 오신고한다
    (2026-09-18: place.distance·book.loan_count). 판정 불능은 미상으로 기권한다."""
    try:
        from ibl_access import _return_shapes
        shapes = _return_shapes() or {}
    except Exception:
        return None
    shapes = {k: v for k, v in shapes.items()
              if isinstance(v, dict) and (v.get("kind") or "items") in kinds and not v.get("more") and v.get("keys")}
    q = f"{node}:{action}"
    op = params.get("op")
    ad = _action_def(node, action) or {}
    if ad.get("columns_from") == "data":
        # 열은 데이터가 정한다(ledger·read·script) — fixture 열은 그 fixture 의 것. 단 그 op 를 부른 fixture 가
        # 따로 관측돼 있으면(`self:script#list` 처럼 목록 op 의 열은 코드가 정한다) 그 열은 안다(2026-09-16 ep3816).
        if isinstance(op, str) and not _dynamic(op):
            return shapes.get(f"{q}#{op}")
        return None
    # A baseline observation is valid only for its shape coordinates.
    changed_axes = {k for k, default in shape_axes(ad).items()
                    if k in params and params[k] is not None and str(params[k]) != str(default)}
    # 변이 축(F20-1): param 리터럴이 변이 키와 맞으면 그 열이 정본
    for k, v in shapes.items():
        if not k.startswith(q + "@"):
            continue
        try:
            p, want = k[len(q) + 1:].split("=", 1)
        except ValueError:
            continue
        val = params.get(p)
        if val is not None and not _dynamic(val) and str(val) == want:
            if not changed_axes - {p}:
                return v
    if changed_axes:
        return None
    if isinstance(op, str) and not _dynamic(op):
        ent = shapes.get(f"{q}#{op}")
        if ent:
            return ent
    ent = shapes.get(q)
    if ent and ent.get("source") == "usage" and ad.get("ops"):
        # 실사용 원장 수확은 어느 op 가 낸 봉투인지 모른다 — op 가 있는 액션에 빌려주면 add 봉투의 키로
        # list 결과를 판정해 `.items` 에 거짓 경고를 냈다(77회차 T24 self:material·F76-2 재확인). 미상이 맞다.
        ent = None
    if ent:
        # 액션 레벨 관측은 액션 fixture 의 op 하나가 낸 열이다 — 다른 op 로 부른 문장에 그 열을 빌려주지 않는다
        # (2026-09-05 ep2858: `[self:lecture]{op:"load"}` 가 list fixture 의 title·meta·summary·url 을 받았다). 미상이 맞다.
        fop = _fixture_op(ad)
        if not (isinstance(op, str) and not _dynamic(op) and fop and op != fop):
            return ent
    try:
        from ibl_ops import default_op
        d = default_op(ad)
    except Exception:
        d = None
    if d and (op is None or op == d):
        return shapes.get(f"{q}#{d}")
    return None

def shape_axes(action_def: Dict[str, Any]) -> Dict[str, Any]:
    """기준 관측(fixture)의 좌표 — 결과 모양을 가르는 인자와 fixture 가 쓴 값.

    손 선언(`shape_axes`)만 보호하면 선언 없는 액션의 다른 원천 호출이 기본 원천의 열로 판정돼 거짓
    `UNOBSERVED_FIELD` 가 났다([sense:book]{source:"nl"} 의 meta — 77회차·F76-2 재확인). 축은 이미 있는
    선언에서 유도한다: shape_axes · shape_variants 라벨의 인자 · param_support 축 · 스키마의 유한 값 영역(enum 2개 이상).
    좌표 값 = 손 선언 > fixture 리터럴 > 스키마 기본값 > 미지정(None)."""
    ad = action_def or {}
    fixture = ad.get("fixture") if isinstance(ad.get("fixture"), str) else ""

    def at_fixture(name, fallback=None):
        m = re.search(rf'\b{re.escape(name)}\s*:\s*["\']([^"\']*)["\']', fixture)
        return m.group(1) if m else fallback

    axes = dict(ad.get("shape_axes") or {})
    for label in ad.get("shape_variants") or {}:
        name = str(label).split("=", 1)[0]
        axes.setdefault(name, at_fixture(name))
    support = ad.get("param_support")
    if isinstance(support, dict) and support.get("axis"):
        axes.setdefault(support["axis"], at_fixture(support["axis"], support.get("default")))
    tool = ad.get("tool")
    if tool:
        try:
            from tool_loader import load_tool_schema
            props = ((load_tool_schema(tool) or {}).get("input_schema") or {}).get("properties") or {}
        except Exception:
            props = {}
        for name, spec in props.items():
            if name != "op" and isinstance(spec, dict) and len(spec.get("enum") or ()) > 1:
                axes.setdefault(name, at_fixture(name, spec.get("default")))
    return axes

def _fixture_op(action_def: Dict[str, Any]) -> Optional[str]:
    """fixture의 명시 op 또는 무인자 호출의 선언 기본 op — 관측 열의 출처."""
    fx = (action_def or {}).get("fixture")
    if not isinstance(fx, str):
        return None
    m = _FIXTURE_OP_RE.search(fx)
    if m:
        return m.group(1)
    # 무인자 fixture도 default op 하나만 관측한다. 이를 모든 op의 반환으로
    # 빌리면 목록의 items 열이 start/delete 결과에까지 붙는다.
    # 인자가 있는 암묵 호출은 별도 디스패치일 수 있으므로 여기서 추측하지 않는다.
    if re.fullmatch(r"\s*\[[^\]]+\]\s*(?:\{\s*\})?\s*", fx):
        from ibl_ops import default_op
        return default_op(action_def)
    return None

def _dynamic(v: Any) -> bool:
    return isinstance(v, str) and ("$" in v or "{{" in v)

def format_issues(issues: List[Dict[str, Any]], limit: int = 6) -> str:
    """오류 봉투의 한 줄 요약(첫 error 우선)."""
    errs = [i for i in issues if i.get("severity") == "error"] or issues
    parts = []
    for i in errs[:limit]:
        parts.append(f"문장 {i.get('statement')} step {i.get('step')} [{i.get('at')}]: {i.get('message')}")
    return " | ".join(parts)

def typecheck_code(code):
    from function_library import compile_current
    from ibl_v2_ir import Fault
    try:
        return compile_current(code).report()
    except (Fault, ValueError) as exc:
        return {'ok': False, 'issues': [{'severity': 'error', 'message': str(exc)}], 'syntax_error': str(exc)}


def return_type_of(code, signature=None):
    from function_library import compile_current
    try:
        plan = compile_current(code)
        if plan.issues:
            return '?'
        contracts = list(plan.function_contracts.values())
        return str(contracts[0].get('result', '?')) if contracts else str(plan.result_type)
    except Exception:
        return '?'
