"""action_requires.py — 액션 선언 `requires:` 의 실행기 관문 (2026-10-05, 설치 목록 ② 권한 연결).

설계 정본: docs/APP_COMMON_FOUNDATION_GAPS_2026_10_05.md §1-②. 기존 principal(전송 관문이 세움·좁힐 수만 있음)을
**재사용**하고 세 가지를 연결한다:
  1. 액션이 요구 권한을 선언할 자리 — 사전(yaml)의 `requires:`
       requires:
         principal: [owner]            # 허용 주체 종류(owner / member / body / portal / anonymous). 생략 = 종류 제한 없음
         min_level: 3                  # member·portal 의 최소 등급(선택)
         human_confirm: true           # 사람 승인 토큰 필요(approval_tokens — 요청 지문에 결속, 1회성)
         exists: "launcher_ops:switch_exists"   # 사람에게 묻기 전 대상 존재 확인("모듈:함수", params → None | 실패 봉투).
                                                # 없는 대상은 승인을 묻지 않고 그 봉투로 거절한다(긴문장 28회차 L28-4)
         ops: {activate: {...}}        # op 별 덮어쓰기(op 분기 액션). 없는 op 는 액션 레벨을 따른다
  2. 실행기 관문 한 곳 — ibl_engine.execute_ibl 의 잎에서(판본 1·판본 2 어댑터·fn 전개·each 하위 전부 이 잎을 지난다).
  3. 사람 승인은 /ibl/approve 가 발급한 토큰을 요청에 실어 다시 보내는 것으로 — 매니페스트 변경 없음.
"누구인가"는 principal, "무엇이 허용됐나"는 이 선언, "사람이 승인했나"는 토큰 — 세 사실을 하나로 뭉개지 않는다.
"""
from typing import Optional

KINDS = ("owner", "member", "body", "portal", "anonymous")
KEYS = {"principal", "min_level", "human_confirm", "exists", "ops"}


def declared(action_cfg: dict, op: Optional[str] = None) -> Optional[dict]:
    """액션의 유효 requires — 액션 레벨 위에 ops[op] 를 덮는다. 선언이 없으면 None."""
    spec = (action_cfg or {}).get("requires")
    if not isinstance(spec, dict):
        return None
    base = {k: v for k, v in spec.items() if k != "ops"}
    override = (spec.get("ops") or {}).get(op) if op else None
    if isinstance(override, dict):
        base = {**base, **override}
    return base or None


def validate(spec, op_values: Optional[set] = None) -> list:
    """빌드 검증 — 구조·종류·op 이름. (실행이 아니라 저술 시점의 거절)"""
    issues = []
    if not isinstance(spec, dict):
        return ["requires 는 매핑"]
    unknown = set(spec) - KEYS
    if unknown:
        issues.append(f"requires 미지의 키 {sorted(unknown)} (허용: {sorted(KEYS)})")
    def check(level: dict, where: str):
        kinds = level.get("principal")
        if kinds is not None and (not isinstance(kinds, list) or not kinds or any(k not in KINDS for k in kinds)):
            issues.append(f"{where}principal 은 {list(KINDS)} 의 비어있지 않은 목록")
        if "min_level" in level and (type(level["min_level"]) is not int or level["min_level"] < 0):
            issues.append(f"{where}min_level 은 0 이상 정수")
        if "human_confirm" in level and type(level["human_confirm"]) is not bool:
            issues.append(f"{where}human_confirm 은 참/거짓")
        if "exists" in level and not (isinstance(level["exists"], str) and level["exists"].count(":") == 1 and all(level["exists"].split(":"))):
            issues.append(f"{where}exists 는 '모듈:함수' 문자열")
    check(spec, "")
    ops = spec.get("ops")
    if ops is not None:
        if not isinstance(ops, dict):
            issues.append("requires.ops 는 {op: {…}} 매핑")
        else:
            for op, level in ops.items():
                if op_values is not None and op not in op_values:
                    issues.append(f"requires.ops 의 '{op}' 은 선언된 op 가 아님")
                if not isinstance(level, dict) or set(level) - (KEYS - {"ops"}):
                    issues.append(f"requires.ops.{op} 는 principal/min_level/human_confirm 매핑")
                else:
                    check(level, f"ops.{op}.")
    return issues


def _target_missing(spec: str, params: Optional[dict]) -> Optional[dict]:
    """`exists: "모듈:함수"` — 함수(params) 가 None 이면 대상이 있다, 실패 봉투면 그대로 거절. 함수를 못 찾으면 거절(fail-closed)."""
    import importlib
    mod_name, _, fn_name = spec.partition(":")
    try:
        fn = getattr(importlib.import_module(mod_name), fn_name)
    except (ImportError, AttributeError) as exc:
        return {"success": False, "error_type": "permission", "denied": True,
                "error": f"requires.exists '{spec}' 을 찾지 못했습니다: {exc}"}
    out = fn(params or {})
    if isinstance(out, dict) and out.get("success") is False:
        return {"error_type": "not_found", **out}
    return None


def gate(node: str, action: str, action_cfg: dict, op: Optional[str], params: Optional[dict] = None) -> Optional[dict]:
    """실행 직전 관문. 통과면 None, 거절이면 오류 봉투(판본 2 어댑터가 permission Fault 로 바꾼다).

    op 는 호출자(ibl 층, ibl_ops.resolve_op)가 해소해 넘긴다 — base 층은 ibl 층을 import 하지 않는다(층 가드).
    human_confirm 거절 봉투에는 approval_required{challenge, action, op, principal} 를 싣는다 — 표면이 사람에게
    묻고 /ibl/approve 로 토큰을 받아 같은 요청을 approval 과 함께 재전송하면 그 요청 지문에 대해서만 통과한다.
    `exists` 가 선언돼 있으면 사람에게 묻기 **전에** 대상 존재를 확인한다 — 없는 대상의 승인을 사람에게 묻지 않는다(28회차 L28-4).
    params 는 호출자가 받은 원 인자(별칭 정규화 전)라 exists 함수는 별칭까지 읽어야 한다."""
    need = declared(action_cfg, op)
    if not need:
        return None
    import principal as _principal
    p = _principal.current()
    key = f"{node}:{action}"
    kinds = need.get("principal")
    if kinds and p.kind not in kinds:
        return {"success": False, "error_type": "permission", "denied": True,
                "error": f"{key}{'(' + op + ')' if op else ''} 은 {', '.join(kinds)} 주체만 부를 수 있습니다 (현재 {p.kind})."}
    min_level = need.get("min_level")
    if isinstance(min_level, int) and p.kind in ("member", "portal") and (p.level is None or p.level < min_level):
        return {"success": False, "error_type": "permission", "denied": True,
                "error": f"{key} 은 등급 {min_level} 이상 회원만 부를 수 있습니다 (현재 {p.level})."}
    if need.get("human_confirm") is True:
        if isinstance(need.get("exists"), str):
            missing = _target_missing(need["exists"], params)
            if missing:
                return missing
        from thread_context import get_approval
        import approval_tokens
        token, digest = get_approval()
        ch = approval_tokens.challenge(p.key(), key, digest or "", op)
        if not approval_tokens.consume(token, ch):
            return {"success": False, "error_type": "permission", "denied": True,
                    "error": f"{key}{'(' + op + ')' if op else ''} 은 사람의 확인이 필요합니다 — 표면에서 승인한 뒤 같은 요청을 다시 보내세요.",
                    "approval_required": {"challenge": ch, "action": key, "op": op, "principal": p.key(),
                                          "summary": f"[{key}]{{op: {op}}}" if op else f"[{key}]"}}
    return None
