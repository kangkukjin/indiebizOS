"""
ibl_access.py - IBL Node Access Control & Environment Builder

에이전트의 IBL 환경을 정의하고 접근을 제어합니다.

핵심 개념:
    에이전트 = 허용된 노드들 + 각 노드의 액션들 + 동료 에이전트들
    IBL은 에이전트가 자신의 환경을 명확히 인식할 수 있게 하는 언어.

    환경 = 노드 (ibl_nodes.yaml)
         + 동료 에이전트 노드 (같은 프로젝트의 다른 에이전트)

함수:
    resolve_allowed_nodes() : allowed_nodes → 노드 집합
    check_node_access()     : 노드 접근 가능 여부 (hard enforcement)
    build_environment()     : 에이전트 환경 프롬프트 동적 생성 (soft enforcement)
"""

import os
import json
import yaml
import logging
from pathlib import Path
from typing import List, Optional, Set, Dict

logger = logging.getLogger(__name__)


# 항상 허용되는 인프라 노드 — 노드 yaml 의 `always_on: true` 플래그가 단일 소스.
# (역사: Phase 19-22 system/team → Phase 23 self/others → table 분리로 문법 계층 합류.
#  table = IBL 문법 계층(통화 변환자)이라 어떤 노드 선별에서도 꺼지면 파이프라인이 깨짐 —
#  노드 on/off 기능의 토대. 현재 always_on 노드: self, others, table)
# 레지스트리 미가용(부트스트랩/테스트) 시에만 쓰는 최후 폴백:
_ALWAYS_ALLOWED_FALLBACK = {"self", "others", "table"}


def _always_allowed() -> Set[str]:
    """ibl_nodes.yaml 에서 always_on: true 노드 집합을 읽는다 (load_nodes_raw 캐시 공유)."""
    nodes = load_nodes_raw().get("nodes") or {}
    if not nodes:
        return set(_ALWAYS_ALLOWED_FALLBACK)
    return {n for n, cfg in nodes.items()
            if isinstance(cfg, dict) and cfg.get("always_on")}


# ============ 접근 제어 ============

def resolve_allowed_nodes(allowed_nodes: Optional[List[str]]) -> Optional[Set[str]]:
    """
    agents.yaml의 allowed_nodes를 실제 노드 이름 집합으로 확장.

    Returns:
        허용된 노드 집합. None이면 모든 노드 허용.

    Examples:
        None / []           → None (제한 없음)
        ["sense"]           → {"sense", "self", "others", "table"}
        ["sense", "engines"]  → {"sense", "engines", "self", "others", "table"}
        ["limbs"]           → {"limbs", "self", "others", "table"}
    """
    if not allowed_nodes:
        return None

    groups = _load_node_groups()
    resolved = set()

    for entry in allowed_nodes:
        entry = str(entry).strip()
        if entry in groups:
            resolved.update(groups[entry])
        elif entry.startswith("info:") or entry.startswith("store:"):
            # 하위 호환: "info:legal", "store:photo" 등 → sense
            resolved.add("sense")
        elif ":" in entry and not entry.endswith(":*"):
            _, sub = entry.split(":", 1)
            resolved.add(sub)
        else:
            resolved.add(entry)

    resolved.update(_always_allowed())
    return resolved


def check_node_access(node: str, allowed: Optional[Set[str]]) -> bool:
    """노드 접근 가능 여부. allowed가 None이면 항상 True."""
    if allowed is None:
        return True
    return node in allowed


def get_denied_message(node: str, allowed: Set[str]) -> dict:
    """접근 거부 에러 메시지"""
    user_nodes = sorted(allowed - _always_allowed())
    return {
        "error": f"노드 '{node}'에 대한 접근 권한이 없습니다.",
        "allowed_nodes": user_nodes,
        "hint": "agents.yaml의 allowed_nodes에 해당 노드를 추가하세요."
    }


# ============ 환경 프롬프트 생성 ============


# 카탈로그 줄-표기 범례 — R1q+R3 인코딩(2026-07-28). 아래 _emit_action_line 과 한 몸.
CATALOG_LEGEND = (
    "# 표기법: '노드:액션 :: 설명' = 액션 한 줄 (호출은 [노드:액션]{...}). "
    "그 아래 들여쓴 '.op이름 설명' = 그 액션의 op (*표 = 기본 op, op 생략 시 적용; "
    "설명 없는 .op 는 이름 그대로의 동작). ⟨열: a·b⟩ = 실측 반환 열 이름 — 뒤에 붙일 "
    "filter/sort/select/compute 의 필드명은 이걸 쓴다. ⟨열: a·b | source=x: c·d⟩ 처럼 "
    "'|' 로 갈린 것은 그 파라미터에 따라 열이 달라진다는 뜻(앞자리=기본값의 열). "
    "⟨인자: a·b·(c)⟩ = 실측 입력 인자 이름(교재·실행에서 실제 쓰인 키) — 호출의 {…} 키는 "
    "이걸 쓴다; 괄호 없음 = 거의 항상 함께 오는 인자, (괄호) = 가끔 쓰는 선택 인자. "
    "⟨동반: >>a·&b⟩ = 교재·실행에서 그 낱말 **뒤에 실제로 이어진** 낱말(관측 상위 2, "
    "`&같은액션` = 같은 액션을 파라미터만 바꿔 병렬로 접은 자리). ★안 붙은 줄은 '조합 불가'가 "
    "아니라 '관측 없음'이다 — items 를 내는 액션이면 예외 없이 `>> [table:*]` 변환자를 물릴 수 있고, "
    "동반은 처방이 아니라 흔적이라 새 조합을 막지 않는다. "
    "(dormant: 키이름) = API 키가 없어 휴면 중."
)

# R3: 이름이 자명한 op 는 설명을 방출하지 않는다(이름만) — 데이터(ops.values)는 그대로,
# 방출만 억제(마법책 UI 등은 계속 전체 설명을 봄). 판정 3조건: 자명 동사 어간 + 60자 이하
# + 파라미터 신호('='·'필수') 없음 — realty.query 처럼 source 열거를 실은 설명은 자동 보존.
# 근거: catalog_encoding_eval 150표본에서 R3=82.0%(R0 동률, 쌍별 5:5) — 억제 무손실.
_SELF_EVIDENT_OPS = {
    "list", "detail", "create", "delete", "update", "save", "add", "remove", "search",
    "play", "stop", "pause", "status", "scan", "refresh", "run", "open", "close", "send",
    "read", "write", "get", "set", "start", "download", "upload", "install", "uninstall",
    "enable", "disable", "clear", "cancel", "query", "info", "stats", "summary", "check",
    "test", "preview", "publish", "export", "import", "sync", "toggle", "history",
    "recent", "rename", "move", "copy", "edit", "view", "show",
}


def _op_desc_suppressible(op_name: str, op_desc: str) -> bool:
    base = op_name.split("_")[0]
    d = op_desc or ""
    return ((op_name in _SELF_EVIDENT_OPS or base in _SELF_EVIDENT_OPS)
            and len(d) <= 60 and "=" not in d and "필수" not in d)


_SHAPES_CACHE = {"mtime": None, "data": {}}


def _return_shapes() -> dict:
    """fixture 실측 반환 열(data/ibl_return_shapes.json, scripts/ibl_shape_sweep.py 산출) — mtime 캐시.

    2026-08-21: 조합의 1위 구조적 한계="뒷문장을 쓰려면 앞문장의 열 이름을 봐야 한다"(ep1325
    `where: "연도 == '2024'"` 실패 → 한 번 돌려 보고 다시 씀). 카탈로그가 열을 말하면 그 왕복이 준다.
    관측 데이터라 src yaml 이 아니라 런타임 파일에서 읽는다(세계의 명사=데이터)."""
    try:
        from runtime_utils import get_base_path
        path = get_base_path() / "data" / "ibl_return_shapes.json"
        mt = path.stat().st_mtime
    except Exception:
        return {}
    if _SHAPES_CACHE["mtime"] != mt:
        try:
            import json as _json
            _SHAPES_CACHE["data"] = _json.loads(path.read_text(encoding="utf-8")).get("shapes", {}) or {}
        except Exception:
            _SHAPES_CACHE["data"] = {}
        _SHAPES_CACHE["mtime"] = mt
    return _SHAPES_CACHE["data"]


def _variant_shapes(qualified: str) -> list:
    """`node:action@param=값` 변이 관측 — (라벨, 열) 목록 (2026-08-22, F20-1 판정).

    왜: ⟨열⟩ 색인 키는 `node:action[#op]` 인데, 반환 열이 **op 이 아니라 param 으로**
    갈리는 액션이 있다([sense:realty] source=molit/naver/zigbang — molit 은
    `아파트명·법정동·보증금·전용면적`, naver 는 `title·name·meta·price`). 그 상태의
    카탈로그는 *한 변이의 열을 전부인 양* 말한다 — 구조적 거짓말이고, 뒷문장
    (`>> [table:compute]`)이 없는 필드를 고르고 죽는 원인이 된다(20회차 F20-1 최소재현).
    열 이름 정규화(=몸이 세계에 이름 붙이기)는 기각하고 색인 키를 변이 축까지 넓혔다."""
    shapes = _return_shapes()
    prefix = f"{qualified}@"
    out = []
    for k in sorted(shapes):
        if k.startswith(prefix):
            keys = (shapes[k] or {}).get("keys") or []
            if keys:
                out.append((k[len(prefix):], keys))
    return out


def _shape_suffix(qualified: str, op: str = None, ops: dict = None) -> str:
    """'⟨열: a·b·c⟩' — 액션 줄엔 기본 op(또는 op 없는 fixture)의 열, op 줄엔 그 op 의 열(액션 열과 다를 때만).

    변이가 선언된 액션은 '⟨열: 기본열 | source=naver: 열…⟩' 로 병기한다(F20-1).
    라벨 없는 앞자리 = 기본값의 열."""
    shapes = _return_shapes()
    if not shapes:
        return ""
    variants = []
    if op is None:
        default = (ops or {}).get("default") if isinstance(ops, dict) else None
        ent = shapes.get(qualified) or (shapes.get(f"{qualified}#{default}") if default else None)
        variants = _variant_shapes(qualified)
    else:
        ent = shapes.get(f"{qualified}#{op}")
        base = shapes.get(qualified) or shapes.get(f"{qualified}#{(ops or {}).get('default')}")
        if ent and base and ent.get("keys") == base.get("keys"):
            return ""
    if not ent or not ent.get("keys"):
        return ""
    parts = ["·".join(ent["keys"][:8])]
    parts += [f"{label}: " + "·".join(keys[:8]) for label, keys in variants]
    # ⟨열⟩=통화(items/table)의 열, ⟨키⟩=통화가 아닌 봉투(효과·스칼라)의 필드 — `$변수.키` 로 읽는 자리
    # (2026-09-06 F55-1). 라벨이 갈려야 모델이 ⟨키⟩를 >> 변환자의 열로 오독하지 않는다.
    label = "열" if ent.get("kind") in (None, "items", "table") else "키"
    return f" ⟨{label}: " + " | ".join(parts) + "⟩"


_PARAM_CACHE = {"mtime": None, "data": {}, "always": 0.8}


def _param_shapes() -> dict:
    """교재·실행 실측 입력 인자(data/ibl_param_shapes.json, scripts/ibl_param_sweep.py 산출) — mtime 캐시.

    2026-08-23: 반환 모양(⟨열⟩)은 실측으로 구조화됐는데 **입력 모양은 아무 데도 구조로
    없었다** — 151 액션 중 params 스키마 0, 인자 의미는 target_description 산문에만 있고
    그 산문은 프롬프트에 실리지 않는다. 모델은 인자를 해마 예문에서 추측했다. 선언 스키마를
    손으로 쓰는 대신(선행 명사 스키마 금지) **쓰인 흔적**을 센다 — ⟨열⟩의 거울."""
    try:
        from runtime_utils import get_base_path
        path = get_base_path() / "data" / "ibl_param_shapes.json"
        mt = path.stat().st_mtime
    except Exception:
        return {}
    if _PARAM_CACHE["mtime"] != mt:
        try:
            import json as _json
            doc = _json.loads(path.read_text(encoding="utf-8"))
            _PARAM_CACHE["data"] = doc.get("shapes", {}) or {}
            _PARAM_CACHE["always"] = float(doc.get("always_ratio", 0.8))
        except Exception:
            _PARAM_CACHE["data"] = {}
        _PARAM_CACHE["mtime"] = mt
    return _PARAM_CACHE["data"]


def _param_suffix(qualified: str, op: str = None) -> str:
    """'⟨인자: a·b·(c)⟩' — 액션 줄엔 액션 전체의 인자, op 줄엔 그 op 의 인자(액션과 이름이 다를 때만).

    괄호 없음 = 그 액션 호출 중 always_ratio(기본 0.8) 이상 함께 온 키, (괄호) = 그 아래.
    `op` 키는 싣지 않는다 — `.op` 줄이 이미 구조로 말한다."""
    shapes = _param_shapes()
    if not shapes:
        return ""
    always = _PARAM_CACHE["always"]
    if op is None:
        ent = shapes.get(qualified)
    else:
        ent = shapes.get(f"{qualified}#{op}")
        base = shapes.get(qualified)
        if ent and base and not _op_adds_information(ent, base, always):
            return ""
    if not ent or not ent.get("keys"):
        return ""
    parts = [k if r >= always else f"({k})" for k, r in ent["keys"][:8]]
    return " ⟨인자: " + "·".join(parts) + "⟩"


_PARTNER_CACHE = {"mtime": None, "data": {}}


def _partners() -> dict:
    """교재·실행 실측 조합 파트너(data/ibl_partners.json, scripts/ibl_partner_sweep.py 산출) — mtime 캐시.

    2026-08-30: ⟨열⟩(반환)·⟨인자⟩(입력)은 관측으로 채워졌는데 **이웃만 비어 있었다** — 상시
    카탈로그 148줄에 조합 정보가 한 글자도 없어 낱말이 저마다 섬으로 제시된다. 문장이 닿는
    통로는 문법 프롬프트의 예문 29개(등장 32/148)와 회상 top-3(조합 20.1%)뿐이라 116 낱말은
    문장 안에 있는 모습을 본 적이 없다. 실측: 낱말별 '교재 조합 노출률→실행 조합률' r=0.72."""
    try:
        from runtime_utils import get_base_path
        path = get_base_path() / "data" / "ibl_partners.json"
        mt = path.stat().st_mtime
    except Exception:
        return {}
    if _PARTNER_CACHE["mtime"] != mt:
        try:
            import json as _json
            _PARTNER_CACHE["data"] = _json.loads(path.read_text(encoding="utf-8")).get("partners", {}) or {}
        except Exception:
            _PARTNER_CACHE["data"] = {}
        _PARTNER_CACHE["mtime"] = mt
    return _PARTNER_CACHE["data"]


def _partner_suffix(qualified: str) -> str:
    """'⟨동반: >>table:filter · &같은액션⟩' — 관측된 조합 파트너 상위(스윕이 top_n·min_count 로 이미 자름).

    액션 줄에만 붙인다(op 줄까지 가르면 폭 예산을 넘고 op 별 표본이 얇다). 관측이 없으면
    빈 문자열 — **없음은 '조합 불가'가 아니다**(범례가 그 규칙을 한 번 말한다)."""
    ent = _partners().get(qualified)
    if not ent or not ent.get("top"):
        return ""
    return " ⟨동반: " + " · ".join(t for t, _ in ent["top"]) + "⟩"


def _op_adds_information(ent: dict, base: dict, always: float) -> bool:
    """op 줄의 ⟨인자⟩ 는 액션 줄이 못 말한 것이 있을 때만 — 새 키가 있거나, 액션 줄에선
    (선택)이던 키가 이 op 에선 거의 항상 오는 키로 승격될 때. 그 밖엔 중복이라 카탈로그만 부푼다."""
    base_keys = {k for k, _ in base.get("keys", [])}
    base_plain = {k for k, r in base.get("keys", []) if r >= always}
    op_keys = [k for k, _ in ent.get("keys", [])[:8]]
    op_plain = {k for k, r in ent.get("keys", [])[:8] if r >= always}
    return bool(set(op_keys) - base_keys) or bool(op_plain - base_plain)


def _emit_action_line(node_name: str, action_name: str, action_config, indent: str = "  ") -> str:
    """단일 액션을 완전수식 줄-표기(R1q)로 직렬화.

    형식: '노드:액션 :: 설명' + 들여쓴 '.op* 설명' 자식 줄.
    2026-07-28 XML(<action>/<op>) → 줄-표기 전환: 오프라인 선택 정확도 평가
    (scripts/catalog_encoding_eval.py, 표본 150·경량 티어)에서 완전수식 줄-표기가
    XML 과 액션 정확도 동률(82.0%, 쌍별 5:5)·op 정확도 우위(93.2% vs 88.5%)로
    카탈로그 −26% 무손실 확인. ★비수식 이름(액션명만)은 75.3%로 유의 손실
    (그룹명을 노드로 오인) — 완전수식(node:action)이 무손실의 조건이다.

    2026-05-28: ops 블록 도입(op 선택이 desc 산문 아닌 구조 정보를 보도록).
    2026-07-01 (Phase 4): dormant 표시 — 키가 없어 못 쓰는 액션은 지우지 않고
    표시만 한다(SIM 슬롯 비유). 지우면 "능력 자체가 없다"고 오판하고, 조용히
    실패만 하면 헛수고를 반복한다 — dormant 표시가 둘 다 피한다.
    """
    dormant = _dormant_reason(node_name, action_name)
    dormant_suffix = f" (dormant: {dormant})" if dormant else ""
    qualified = f"{node_name}:{action_name}"

    if not isinstance(action_config, dict):
        return f"{indent}{qualified}{dormant_suffix}"

    desc = action_config.get("description", "")
    ops = action_config.get("ops")

    lines = [f"{indent}{qualified} :: {desc}{_param_suffix(qualified)}"
             f"{_shape_suffix(qualified, None, ops)}{_partner_suffix(qualified)}{dormant_suffix}"]
    if isinstance(ops, dict) and ops.get("values"):
        default = ops.get("default")
        for op_name, op_desc in (ops.get("values") or {}).items():
            star = "*" if op_name == default else ""
            sfx = _param_suffix(qualified, op_name) + _shape_suffix(qualified, op_name, ops)
            if _op_desc_suppressible(op_name, op_desc) and not sfx:
                lines.append(f"{indent}  .{op_name}{star}")
            else:
                lines.append(f"{indent}  .{op_name}{star} {op_desc}{sfx}")
    return "\n".join(lines)


def build_environment(
    allowed_nodes: Optional[List[str]] = None,
    project_path: Optional[str] = None,
    agent_id: Optional[str] = None,
    allowed_set: Optional[Set[str]] = None
) -> str:
    """
    에이전트의 IBL 환경 프롬프트를 동적 생성.

    에이전트는 이 프롬프트를 통해 자신의 환경을 인식합니다:
    1. 노드: ibl_nodes.yaml에서 허용된 노드와 액션
    2. 동료 에이전트 노드: 같은 프로젝트의 다른 에이전트 (위임 가능)

    Args:
        allowed_nodes: agents.yaml의 allowed_nodes. None/[]이면 전체 노드.
        project_path: 프로젝트 경로 (동료 에이전트 탐색용)
        agent_id: 현재 에이전트 ID (자신을 제외하기 위해)

    Returns:
        환경 프롬프트 문자열
    """
    nodes_data = load_nodes_raw()
    if not nodes_data:
        return ""

    # allowed_set(이미 해소된 집합)이 오면 always-allow 보강 없이 *그대로* 쓴다 —
    # 포식처럼 "정확히 이 노드만"(예: {sense, self}, others 제외)을 강제할 때.
    allowed = allowed_set if allowed_set is not None else resolve_allowed_nodes(allowed_nodes)
    nodes = nodes_data.get("nodes", {})

    # 허용된 노드만 필터링
    if allowed is not None:
        visible = {k: v for k, v in nodes.items() if k in allowed}
    else:
        visible = nodes

    if not visible:
        return ""

    parts = []

    # 12_ibl_only.md를 기본 IBL 교재로 첫머리에 삽입
    # (문법, Goal 시스템, 파이프라인 vs 에이전틱 사고 등 핵심 개념 포함)
    from runtime_utils import get_base_path
    ibl_only_path = get_base_path() / "data" / "common_prompts" / "fragments" / "12_ibl_only.md"
    if ibl_only_path.exists():
        parts.append(ibl_only_path.read_text(encoding='utf-8').strip())
    else:
        logger.warning("12_ibl_only.md not found, IBL 기본 교재 누락")

    # 액션 카탈로그 시작 — 12_ibl_only.md가 개념을, 여기서는 "뭐가 있는지"를 담당
    # (외곽 <ibl_actions> 래퍼는 경계 표시로 유지 — 내용은 R1q 줄-표기, 2026-07-28)
    parts.append("<ibl_actions>")

    # 환경 선언
    node_names = sorted(visible.keys())
    constraint = nodes_data.get("meta", {}).get("constraint", "")
    parts.append(CATALOG_LEGEND)
    parts.append(f"# 사용 가능 노드: {', '.join(node_names)}")
    if constraint:
        parts.append(f"# 제약: {constraint}")

    # usage, pipeline, principles는 12_ibl_only.md에서 이미 커버하므로 생략

    # 노드 상세
    for node_name, node_config in visible.items():
        desc = node_config.get("description", "")
        actions = node_config.get("actions", {})
        if not actions:
            continue

        parts.append(f"\n= 노드 {node_name} :: {desc}")

        # group별 그룹화 (프롬프트 가독성용). group이 없는 액션은 ungrouped.
        # 2026-05-26 cleanup: category 폴백 제거 — 모든 액션에 group 부여 완료.
        grouped = {}  # group -> [(action_name, action_config), ...]
        ungrouped = []  # [(action_name, action_config), ...]
        for action_name, action_config in actions.items():
            if not isinstance(action_config, dict):
                ungrouped.append((action_name, action_config))
                continue
            # prompt_hidden: 에이전트 카탈로그에서만 숨김(실행은 ibl_engine이 별도 yaml 로드라 유지).
            # 배관 액션(예: engines:icon — 앱 전용 호출, AI 어휘 밖)에 사용.
            if action_config.get("prompt_hidden"):
                continue
            # 몸 소유-필터(몸 독립, 2026-07-22): 이 몸이 실행 못 하는 남의 어휘는
            # 카탈로그에서 제외 — 학습·구사 대상이 아니다(맥=phone_only 제외, 폰=runnable만).
            # 상대 능력은 이웃 몸 명함(냄새)으로 알고 [others:ask]{to, message}로 부탁한다.
            # 실행 경로(ibl_engine)는 과도기 동안 유지 — 기존 계기·스케줄 호환.
            try:
                from ibl_registry import self_can_run
                if not self_can_run(node_name, action_name, action_config):
                    continue
            except Exception:
                pass
            key = action_config.get("group")
            if key:
                grouped.setdefault(key, []).append((action_name, action_config))
            else:
                ungrouped.append((action_name, action_config))

        if grouped:
            for grp_name, grp_actions in grouped.items():
                parts.append(f"  [{grp_name}]")
                for action_name, action_config in grp_actions:
                    parts.append(_emit_action_line(node_name, action_name, action_config))

        for action_name, action_config in ungrouped:
            parts.append(_emit_action_line(node_name, action_name, action_config))

    # 동료 에이전트 노드
    peers = _load_peer_agents(project_path, agent_id)
    if peers:
        parts.append("<peers>")
        for peer in peers:
            name = peer["name"]
            role = peer.get("role", "")
            parts.append(f'  <agent name="{name}" role="{role}" call=\'[others:delegate]{{agent_id: "{name}", message: "..."}}\'/>')
        parts.append("</peers>")

    # pipeline, principles, strategy_rules는 12_ibl_only.md에서 커버
    # 동료 에이전트 위임 힌트만 추가
    if peers:
        parts.append(f"  <hint>Use [others:delegate] to delegate tasks to peer agents ({len(peers)} available)</hint>")

    # Phase 26: 활성 Goal 컨텍스트 주입 (DB에서 동적 로드)
    try:
        from conversation_db import ConversationDB
        _db_path = _resolve_db_path(project_path)
        if _db_path:
            db = ConversationDB(_db_path)
            active_goals = db.list_goals(status="active")
            pending_goals = db.list_goals(status="pending")
            all_goals = (active_goals or []) + (pending_goals or [])

            if all_goals:
                parts.append("<goal_context>")
                parts.append("  <!-- 현재 진행 중인 목표. 각 라운드에서 success_condition 달성 여부를 판단하라. -->")
                for g in all_goals:
                    attrs = f'id="{g["goal_id"]}" name="{g["name"]}" status="{g["status"]}"'
                    attrs += f' round="{g["current_round"]}/{g["max_rounds"]}"'
                    attrs += f' cost="${g["cumulative_cost"]:.4f}/${g["max_cost"]:.2f}"'
                    if g.get("success_condition"):
                        attrs += f' success_condition="{g["success_condition"]}"'
                    if g.get("deadline"):
                        attrs += f' deadline="{g["deadline"]}"'
                    if g.get("every_frequency"):
                        attrs += f' every="{g["every_frequency"]}"'
                    if g.get("until_condition"):
                        attrs += f' until="{g["until_condition"]}"'
                    parts.append(f"  <goal {attrs}/>")
                parts.append("  <instruction>목표의 success_condition이 충족되었다고 판단되면 [self:goal]{op: \"status\"}로 보고하라. "
                              "비용 한도(max_cost)에 근접하면 효율적인 전략을 선택하라.</instruction>")
                parts.append("</goal_context>")
    except Exception:
        pass  # Goal DB 접근 실패 시 조용히 무시

    # Phase 26b: 현재 태스크의 시도 이력 주입 (라운드 메모리)
    try:
        from conversation_db import ConversationDB
        from thread_context import get_current_task_id
        _db_path = _resolve_db_path(project_path)
        current_task = get_current_task_id()

        if _db_path and current_task:
            db = ConversationDB(_db_path)
            history = db.get_attempt_history(current_task, limit=10)
            failed_cats = db.get_failed_categories(current_task, threshold=3)

            if history:
                parts.append("<attempt_history>")
                parts.append(f'  <!-- task_id="{current_task}" 최근 시도 이력. 같은 실수를 반복하지 마라. -->')

                if failed_cats:
                    parts.append(f'  <exhausted_categories categories="{", ".join(failed_cats)}">'
                                 f'이 범주들은 3회 이상 연속 실패했으므로 더 이상 시도하지 마라.'
                                 f'</exhausted_categories>')

                for h in reversed(history):  # 시간순 (오래된 것 먼저)
                    result_icon = "✓" if h.get("result") == "success" else "✗"
                    attrs = (f'round="{h["round_num"]}" '
                             f'category="{h["approach_category"]}" '
                             f'result="{h["result"]}"')
                    lesson_text = f' lesson="{h["lesson"]}"' if h.get("lesson") else ""
                    parts.append(f'  <attempt {attrs}{lesson_text}>{result_icon} {h["description"]}</attempt>')

                parts.append("</attempt_history>")
    except Exception:
        pass  # 시도 이력 접근 실패 시 조용히 무시

    parts.append("</ibl_actions>")

    # 관용구 상시 블록 (2026-09-04, 사용자 판정 "최빈도 관용구는 교재 프롬프트에 넣어 언제나 기억하게"):
    # 해마 관용구(category='phrase') 가운데 가장 많이 쓰인 것 IDIOMS_TOP 건. 데이터(반증 가능 — 쓰이지
    # 않으면 순위에서 빠진다)이지 교재 산문이 아니다. 나머지 관용구는 회상 채널(Top-2)로 온다.
    idioms = _idioms_block(allowed)
    if idioms:
        parts.append(idioms)

    return "\n".join(parts)


IDIOMS_TOP = 6
IDIOMS_MAP_CHARS = 7000     # 이름 지도 예산(자) — 시스템 프롬프트 한 자리, 캐시되므로 왕복마다 새로 물지 않는다(2026-09-06)
IDIOMS_MAP_ROWS = 400        # 지도 후보 상한(행)
_idioms_cache = {"t": 0.0, "text": "", "key": None}


def _stored_signature(raw):
    """저장 서명 → (names, known). 규약의 단일 소스는 원장(ibl_usage_db.parse_signature)."""
    try:
        from ibl_usage_db import parse_signature
        return parse_signature(raw)
    except Exception:
        return ([], False)


def _spread_by_topic(rows: list, top: int) -> list:
    """①쓰인 것 먼저 ②남은 자리는 가지별 하나씩(라운드로빈) — 한 가지가 블록을 다 먹지 않게(2026-09-06).

    rows 는 이미 (사용 횟수 DESC, created_at DESC) 로 정렬돼 있다. 사용된 것은 그 순서 그대로 앞에 두고,
    미사용은 topic 을 돌며 한 건씩 뽑는다. 상시 블록은 이번 턴의 주제를 모르므로, 적어도 서로 다른 주제를
    보여 주는 것이 한 주제로 몰리는 것보다 맞을 확률이 높다."""
    used = [r for r in rows if (int(r[2] or 0) + int(r[3] or 0)) > 0]
    rest = [r for r in rows if (int(r[2] or 0) + int(r[3] or 0)) == 0]
    out = used[:top]
    if len(out) >= top:
        return out
    buckets: dict = {}
    for r in rest:
        buckets.setdefault((r[4] or "").split("/")[0], []).append(r)
    while len(out) < top and any(buckets.values()):
        for k in list(buckets):
            if not buckets[k]:
                del buckets[k]
                continue
            out.append(buckets[k].pop(0))
            if len(out) >= top:
                break
    return out


def _idioms_block(allowed: Optional[Set[str]]) -> str:
    """부를 수 있는 이름의 **지도** — 가벼운 sqlite 읽기(모델·벡터 무접촉), 5분 캐시.

    2026-09-06 속편(사용자 판정 뒤 근본 집행): 옛 판은 6개만 보였다 — "관련성은 회상 채널 몫" 이라 했지만 회상은
    사건 요약으로 검색돼 자연 요청에 이름 0건이었고, 상시 블록은 주제를 몰라 무관한 6개를 보였다. 관련성 판단이
    양쪽 모두에서 비어 있었다. 이제 이 블록은 *지도* 다(심층기억 원칙 "지도가 있으면 단서는 지도에서 온다"):
    가지별로 모든 이름을 뜻 한 줄과 서명으로 싣고, 무엇을 부를지는 모델이 이번 일과 맞춰 본다.
    예산(IDIOMS_MAP_CHARS)을 넘으면 쓰인 것 → 가지별 라운드로빈 순으로 자른다(_spread_by_topic).
    허용 노드 밖 어휘가 든 것·한 문장짜리는 뺀다. 서명은 원장 문에서 계산해 저장한 것만 가르친다(미상이면 미상이라 말한다)."""
    import re as _re
    import sqlite3
    import time
    key = tuple(sorted(allowed)) if allowed is not None else None
    if _idioms_cache["text"] is not None and time.time() - _idioms_cache["t"] < 300 and _idioms_cache["key"] == key:
        return _idioms_cache["text"]
    text = ""
    try:
        from runtime_utils import get_base_path
        db_path = get_base_path() / "data" / "ibl_usage.db"
        if db_path.exists():
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            _cols = {r[1] for r in conn.execute("PRAGMA table_info(ibl_examples)").fetchall()}
            _ret = "COALESCE(returns,'')" if "returns" in _cols else "''"
            _sig = "signature" if "signature" in _cols else "NULL"
            rows = conn.execute(
                f"SELECT intent, ibl_code, success_count, fail_count, COALESCE(topic,''), COALESCE(alias,''), {_ret}, {_sig} "
                "FROM ibl_examples WHERE COALESCE(alias,'') != '' "
                "ORDER BY (success_count + fail_count) DESC, created_at DESC LIMIT ?",
                (IDIOMS_MAP_ROWS,)).fetchall()
            conn.close()
            kept = []
            for r in rows:
                code = r[1] or ""
                nodes = set(_re.findall(r"\[([a-z_-]+):", code)) - {"fn"}
                if allowed is not None and not nodes <= set(allowed):
                    continue
                if len(_split_sentences(code)) < 2:
                    continue                       # 한 문장은 낱말 — 이름으로 부를 것이 없다
                kept.append(r)
            # 예산 안에서 고른다: 쓰인 것 먼저, 남은 자리는 가지별 하나씩 — 그 뒤 가지별로 모아 그린다.
            chosen, budget = [], IDIOMS_MAP_CHARS
            for r in _spread_by_topic(kept, len(kept)):
                entry = _idiom_lines(r)
                cost = sum(len(x) + 1 for x in entry)
                if cost > budget:
                    continue
                budget -= cost
                chosen.append((r, entry))
            groups: dict = {}
            for r, entry in chosen:
                groups.setdefault((r[4] or "").split("/")[0] or "기타", []).extend(entry)
            lines = []
            for g in sorted(groups):
                lines.append(f"[{g}]")
                lines.extend(groups[g])
            if lines:
                text = ("<ibl_idioms note=\"이름 지도 — 자주 쓰는 관용구 = 이름 붙은 함수, 가지별. 각 이름의 뜻(무엇을 받아 무엇을 내는가)을 "
                        "읽고 이번 일과 맞으면 [fn:이름]{슬롯: 값} 한 줄로 부른다(정의 없이 이름만으로 돈다). "
                        "본문은 여기 없다 — 고쳐 써야 할 때만 [self:memory]{op: \\\"recall\\\", node: \\\"<가지>\\\", store: \\\"실행\\\", expand: \\\"이름\\\"} 으로 "
                        "정의를 열어 [def: 이름]{…} 를 프로그램에 붙이고 문장을 빼거나 더한 뒤 [fn:이름]{…} 으로 부른다. "
                        "★여러 문장은 execute_ibl 한 번에 여러 줄로 — 중간 통화($변수)는 엔진 안에 머물고 모델은 마지막 결과와 step 요약만 본다. 마지막 문장은 작은 결과(take/select/brief)로 끝내라.\">\n"
                        + "\n".join(lines) + "\n</ibl_idioms>")
    except Exception as e:
        logger.debug(f"[ibl_access] 관용구 블록 생략: {e}")
    _idioms_cache.update({"t": time.time(), "text": text, "key": key})
    return text


def _idiom_lines(r) -> List[str]:
    """지도의 한 항목(두 줄): `- 이름 — 뜻 · 문장 n [· 사용 k회]` + 서명 한 줄."""
    intent, code, sc, fc, _topic, alias, returns, signature = r
    sents = _split_sentences(code)
    used = f" · 사용 {int(sc or 0) + int(fc or 0)}회" if (int(sc or 0) + int(fc or 0)) else ""
    head = f"- {alias} — {(intent or '').strip()[:120]} · 문장 {len(sents)}{used}"
    names, known = _stored_signature(signature)
    if known:
        sig = f"  [fn:{alias}]{{" + ", ".join(f'{s}: "…"' for s in names) + "}" + (f" → {returns}" if returns else "")
    else:
        sig = (f"  [fn:{alias}]{{…}} — 서명 미상, 부르기 전에 "
               f"[self:memory]{{op: \"recall\", store: \"실행\", expand: \"{alias}\"}} 로 인자를 확인")
    return [head, sig]


def _split_sentences(code: str) -> List[str]:
    """독립 문장 분할 — 정본은 hippo_tree.split_sentences(`;` 와 줄바꿈, 따옴표·괄호 안 제외).

    옛 판은 `;` 만 갈랐다 — 줄바꿈으로 이은 다문장 프로그램(정기 보고서 프로그램 14건, 09-06 실측)이 '한 문장'
    으로 세어져 이름 지도에서 통째로 빠졌다. 분할 규칙은 한 곳(hippo_tree)의 것을 쓴다; 아래 본문은 폴백."""
    try:
        import hippo_tree
        return hippo_tree.split_sentences(code)
    except Exception:
        pass
    out, buf, q, depth = [], [], None, 0
    i, n = 0, len(code or "")
    while i < n:
        ch = code[i]
        if q:
            buf.append(ch)
            if ch == "\\" and i + 1 < n:
                buf.append(code[i + 1]); i += 2; continue
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch; buf.append(ch)
        elif ch in "{[(":
            depth += 1; buf.append(ch)
        elif ch in "}])":
            depth = max(0, depth - 1); buf.append(ch)
        elif ch == ";" and depth == 0:
            out.append("".join(buf).strip()); buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return [x for x in out if x]


# ============ 내부 함수 ============

_node_groups_cache = None
_nodes_data_cache = None
_package_meta_cache = None


def invalidate_nodes_cache():
    """ibl_nodes.yaml 재빌드 후 노드/그룹/능력메타 캐시를 비운다.

    액션 추가·제거·op 변경(build_ibl_nodes.py 결과)을 backend 재시작 없이 반영하기 위해
    /packages/reload 경로에서 호출된다.
    """
    global _nodes_data_cache, _node_groups_cache, _package_meta_cache
    _nodes_data_cache = None
    _node_groups_cache = None
    _package_meta_cache = None

    # node_registry 도 같은 ibl_nodes.yaml 을 자기 캐시(_node_cache·_typed_node_cache)에
    # 물고 있다. 그쪽 무효화 함수는 정의만 있고 호출자가 0이었다(2026-08-18 발견) —
    # 그래서 재빌드 후에도 list_nodes() 소비처(인지 라우팅·node_summary·/nodes API)는
    # 기동 시점 스냅샷을 프로세스 수명 내내 봤다. 무효화의 단일 진입점이 이 함수이므로
    # 여기서 위임한다(층 방향 ibl → datastore, 정방향).
    try:
        from node_registry import invalidate_node_cache
        invalidate_node_cache()
    except Exception as e:
        print(f"[ibl_access] node_registry 캐시 무효화 실패(무시): {e}")


def load_package_meta() -> dict:
    """data/package_meta.json 로드 (캐시) — Phase 4, needs_key/weight/locale + action_owner.

    파일이 없거나 파싱 실패하면 빈 dict(관용 — 활성 필터가 통째로 죽지 않고 그냥
    전부-노출로 안전 착지, 부재-패키지 관용과 같은 철학).
    """
    global _package_meta_cache
    if _package_meta_cache is not None:
        return _package_meta_cache
    from runtime_utils import get_base_path
    path = get_base_path() / "data" / "package_meta.json"
    if not path.is_file():
        _package_meta_cache = {}
        return _package_meta_cache
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        _package_meta_cache = data
    except Exception:
        _package_meta_cache = {}
    return _package_meta_cache


def _dormant_reason(node_name: str, action_name: str) -> Optional[str]:
    """이 액션이 dormant(설치는 됐지만 키가 없어 못 씀)인지 판정.

    Returns: dormant면 사람이 읽을 사유 문자열(누락 env var 나열), 아니면 None.
    부재-패키지 관용과 같은 결 — 액션을 카탈로그에서 지우지 않고 *왜 못 쓰는지*를
    보여준다(SIM 슬롯 비유, 임시방편 아님. docs/CAPABILITY_SELF_CONTAINMENT_PLAN.md Phase 4).
    """
    meta = load_package_meta()
    owner = meta.get("action_owner", {}).get(f"{node_name}:{action_name}")
    if not owner:
        return None
    needs_key = meta.get("packages", {}).get(owner, {}).get("needs_key") or []
    missing = [k for k in needs_key if not os.environ.get(k)]
    if not missing:
        return None
    return f"{owner} 패키지에 필요한 키 없음: {', '.join(missing)}"


def _load_peer_agents(project_path: Optional[str], agent_id: Optional[str]) -> List[Dict]:
    """
    같은 프로젝트의 다른 에이전트 목록 로드.

    에이전트는 동료 에이전트를 인식하여 [others:delegate]로 위임할 수 있다.
    자기 자신은 제외한다.

    Args:
        project_path: 프로젝트 경로
        agent_id: 현재 에이전트 ID (제외용)

    Returns:
        동료 에이전트 정보 리스트: [{name, role, id}, ...]
    """
    if not project_path:
        return []

    agents_file = Path(project_path) / "agents.yaml"
    if not agents_file.exists():
        return []

    try:
        with open(agents_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        # ★깨진 명부를 [] 로 눙치면 "동료가 없다"가 되어 위임 자체가 사라진다.
        # 파일이 없는 경우(위의 exists 검사)와 구별한다. 2026-08-22.
        raise RuntimeError(
            f"동료 명부가 깨졌습니다 — {agents_file} 를 읽을 수 없습니다: {e}"
        ) from e

    agents = data.get("agents", [])
    peers = []

    for agent in agents:
        aid = agent.get("id", "")
        # 자기 자신 제외, 비활성 에이전트 제외
        if aid == agent_id:
            continue
        if not agent.get("active", True):
            continue

        peers.append({
            "id": aid,
            "name": agent.get("name", aid),
            "role": agent.get("role", agent.get("role_description", "")),
        })

    return peers


def _get_nodes_path() -> Path:
    """원본 사전집(ibl_nodes.yaml)의 경로. 경로 앵커는 runtime_utils.get_base_path 하나 —
    INDIEBIZ_BASE_PATH 해석을 여기서 다시 짜지 않는다 (2026-08-24 앵커 단일화).
    ★이 함수는 test_corrupt_not_absent 의 몽키패치 지점이므로 모듈 수준을 유지한다."""
    from runtime_utils import get_base_path
    return get_base_path() / "data" / "ibl_nodes.yaml"


def load_nodes_raw() -> dict:
    """ibl_nodes.yaml 전체 로드 (캐시)"""
    global _nodes_data_cache
    if _nodes_data_cache is not None:
        return _nodes_data_cache

    path = _get_nodes_path()
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        # ★깨진 어휘 파일을 {} 로 눙치면 낱말 전부가 "없는 낱말"이 되고,
        # 환경 프롬프트가 빈 문자열이 되어 에이전트가 몸 없이 조용히 돈다
        # (build_environment_prompt: `if not nodes_data: return ""`). 2026-08-22.
        raise RuntimeError(
            f"어휘 원장이 깨졌습니다 — {path} 를 읽을 수 없습니다: {e}\n"
            f"→ 빌드 중이었다면 잠시 후 재시도, 아니면 "
            f"`python3 scripts/build_ibl_nodes.py` 로 재생성하세요."
        ) from e
    _nodes_data_cache = data
    return data


def _load_node_groups() -> dict:
    """nodes: 섹션에서 그룹 매핑 로드 (캐시)

    하위 호환:
      - "info:*", "store:*" 등 그룹 접두어 → resolve_allowed_nodes에서 처리
      - 6-노드 체계: sense, self, limbs, others, engines, table
    """
    # 2026-08-05 정리: 어떤 노드도 type: 을 선언하지 않아 옛 ntype 루프(store/exec/output
    # 매핑)는 한 번도 실행되지 않는 죽은 가지였고, exec→fs·output→output 은 존재하지
    # 않는 노드를 가리켰다. 오늘의 실제 산출( info:* → sense 하나 )을 정적으로 고정.
    # store:/info: 접두 개별 항목은 resolve_allowed_nodes 의 startswith 분기가 처리.
    global _node_groups_cache
    if _node_groups_cache is not None:
        return _node_groups_cache
    _node_groups_cache = {"info:*": ["sense"]}
    return _node_groups_cache


def _resolve_db_path(project_path: Optional[str]) -> Optional[str]:
    """프로젝트 경로에서 conversations.db 경로를 찾는다."""
    if project_path:
        db_file = Path(project_path) / "conversations.db"
        if db_file.exists():
            return str(db_file)
    # 환경변수에서 기본 경로 시도
    from runtime_utils import get_base_path
    base = get_base_path()
    default_db = base / "conversations.db"
    if default_db.exists():
        return str(default_db)
    return None

# (2026-08-05) 옛 invalidate_cache() 는 삭제 — invalidate_nodes_cache() 와 중복이면서
# _package_meta_cache 를 빠뜨린 불완전판이었고 호출처도 0이었다(감사 D19).
# 캐시 무효화의 단일 진입점은 invalidate_nodes_cache().
