"""iblbuild_lands_on.py — 회원 개방 선언(lands_on) 검증 (2026-09-14, 외부 서비스 앱 1단계).

iblbuild_validators 에서 분가(1500줄 규칙). 정본 설계: docs/EXTERNAL_SERVICE_APP_HANDOFF.md §3-4·§3-6.
"""
from pathlib import Path
import re

VALID_LANDS_ON = {"hub", "body"}


def validate_lands_on(data: dict, root: Path) -> list[str]:
    """회원 개방 선언(2026-09-14, docs/EXTERNAL_SERVICE_APP_HANDOFF.md §3-4·§3-6).

    - `lands_on: body` → `limb_op`(dict, op 필수). member_transform:module:function은
      패키지 안의 감사된 임시 처리기이며 path_audited가 필수다. 영속 결과는 기기에 저장한다.
    - `lands_on: hub`  → `path_audited: {at, impl}` 필요, impl 은 그 패키지 실행 소스의 현재 지문과
      일치해야 한다(옛 감사 표식으로 바뀐 코드를 자동 개방하지 않는다). 부작용 액션은 hub 불가
      (주인 디스크를 쓴다). 패키지 핸들러가 없는 코어 액션은 지문 대상이 없어 hub 개방 불가.
    - `others` 노드는 lands_on 을 받지 않는다(헌법 — 회원이 주인 이름으로 남에게 닿지 않는다).
    - lands_on 없이 limb_op/path_audited 만 있으면 오류(선언 불완전).
    """
    from iblbuild_derive import build_tool_index, handler_fingerprint, declared_side_effect
    issues: list[str] = []
    tool_index = build_tool_index(root)
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict):
                continue
            q = f"{node_name}:{action_name}"
            lo = action.get("lands_on")
            if lo is None:
                if any(action.get(k) is not None for k in ("limb_op", "path_audited", "member_transform")):
                    issues.append(f"{q} — limb_op/path_audited 는 lands_on 선언과 함께여야 한다")
                continue
            if node_name == "others":
                issues.append(f"{q} — others 노드는 회원 개방(lands_on) 불가(헌법)")
                continue
            if lo not in VALID_LANDS_ON:
                issues.append(f"{q} — 잘못된 lands_on '{lo}' (허용: {', '.join(sorted(VALID_LANDS_ON))})")
                continue
            if lo == "body":
                lop = action.get("limb_op")
                if not isinstance(lop, dict) or not isinstance(lop.get("op"), str) or not lop["op"]:
                    issues.append(f"{q} — lands_on: body 는 limb_op {{op, ...}} 번역표가 필요하다")
                if action.get("member_transform") is None:
                    continue
            transform = action.get("member_transform")
            if transform is not None and (lo != "body" or not isinstance(transform, str) or not re.fullmatch(r"[a-z_][a-z_0-9]*:[a-z_][a-z_0-9]*", transform)):
                issues.append(f"{q} — member_transform은 body 전용 module:function 선언이다")
            # hub 또는 body의 감사된 임시 변환
            if lo == "hub" and declared_side_effect(action):
                issues.append(f"{q} — 부작용 액션은 lands_on: hub 불가(주인 디스크를 쓴다) — body 로 선언하라")
            pa = action.get("path_audited")
            if not isinstance(pa, dict) or not pa.get("at") or not pa.get("impl"):
                issues.append(f"{q} — 허브 실행/변환은 path_audited {{at, impl}} 감사 표식이 필요하다")
                continue
            tool = action.get("tool")
            pkg_dir = tool_index[tool][0] if tool and tool in tool_index else None
            if pkg_dir is None:
                issues.append(f"{q} — hub 개방은 패키지 핸들러 액션만 가능(구현 지문 대상 없음)")
                continue
            if transform and isinstance(transform, str) and not (pkg_dir / (transform.split(":")[0] + ".py")).is_file():
                issues.append(f"{q} — member_transform 모듈이 패키지에 없다")
            fp = handler_fingerprint(pkg_dir)
            if str(pa.get("impl")) != fp:
                issues.append(f"{q} — path_audited.impl '{pa.get('impl')}' ≠ 현재 지문 '{fp}' — 핸들러가 바뀌었다. "
                              f"재감사 뒤 지문을 갱신하라(자동 개방 없음)")
    return issues
