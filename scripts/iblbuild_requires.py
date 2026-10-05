"""build_ibl_nodes 검증 계층 — 액션 `requires:`(② 권한 연결 2026-10-05) 구조 검증.

규칙 정본은 backend/base/action_requires.py(실행기 관문과 같은 선언을 소비). iblbuild_validators 의 1500줄 한도 때문에 분리.
"""
from __future__ import annotations
from pathlib import Path
def validate_requires(data: dict, root: Path) -> list[str]:
    """액션 `requires:`(② 권한 연결 2026-10-05) 구조 검증 — 주체 종류·등급·사람 확인·op 이름. 규칙 정본은 backend/base/action_requires.py."""
    import sys as _sys
    if str(root / "backend" / "base") not in _sys.path:
        _sys.path.insert(0, str(root / "backend" / "base"))
    try:
        import action_requires
    except Exception as exc:  # noqa: BLE001
        return [f"requires 검증기 적재 실패: {type(exc).__name__}: {exc}"]
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict) or "requires" not in action:
                continue
            op_values = set(((action.get("ops") or {}).get("values") or {}).keys()) or None
            for issue in action_requires.validate(action["requires"], op_values):
                issues.append(f"{node_name}:{action_name} — {issue}")
    return issues


# ───────── 압축 상설 기관 (5-A): 개념중복 *경고* — 차단 아님 ─────────
# 배경(docs/VOCAB_DEDUP_HANDOFF.md): 정합성 가드는 존재 정합만 본다 — 같은 개념이
# 두 액션이어도 각자 정합이면 통과한다. 아래 두 신호는 2026-08-05 감사의 "자백"(desc
# 면책)과 "구조"(op 집합 닮음) 신호를 상설화한 것. 판단·병합은 사람 몫이라 경고만 낸다.
# (셋째 신호 "실증"=코퍼스 최근접은 주간 감사 vocab_overlap_audit — 빌드는 코퍼스를 안 읽는다.)
