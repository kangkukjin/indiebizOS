"""param 선언 완전성 검사 — iblbuild_validators 의 형제 모듈.

2026-08-24 분리: validate_declared_params(B35-3 2조각)가 iblbuild_validators 를
1500줄 규칙 너머로 밀어서, 변경분을 규칙대로 형제 모듈로 옮겼다. 로직 이동만이며
호출자는 build_ibl_nodes.py 하나다.
"""
from __future__ import annotations

from pathlib import Path

from iblbuild_common import (
    CORPUS_PARAM_ALLOW,
    RUNTIME_META_KEYS,
    UNIVERSAL_PARAM_KEYS,
    _extract_action_param_aliases,
)
from iblbuild_derive import build_tool_index
from iblbuild_validators import _load_corpus_param_keys


def validate_declared_params(data: dict, root: Path) -> list[str] | None:
    """B35-3 2조각 (2026-08-24 #repair): 코퍼스가 **실제로 쓰는** param 자리 중
    tool.json input_schema.properties 에 선언이 없는 것을 오류로 보고한다.

    왜 새 검사가 필요한가 — 형제인 validate_corpus_params 는 "**핸들러가 이 키를 읽나**"
    만 묻고 "**타입이 선언돼 있나**"는 묻지 않는다. 그 틈으로 타입 관문(ibl_routing)이
    눈감는 자리가 생겼고, 거기서 파이썬 예외가 그대로 새었다
    (실측: [self:read]{path: [...]} → "expected str, bytes or os.PathLike object, not list").

    ★이 검사는 카운터가 아니라 **빌드 실패**다. 수를 세어 지켜보는 장치는 수리를 미루는
    장치일 뿐이고, 판정 기준이 코드 안에 전부 있을 때는 세지 말고 닫아야 한다.
    남은 자리는 각 패키지 ibl_actions.yaml 의 tool_json.tools[].input_schema.properties 에
    타입을 적어 0 으로 만든다(정당한 컨테이너 용법은 object/array 로 선언).

    파서/코퍼스 미가용 시 None (검사 건너뜀).
    """
    corpus = _load_corpus_param_keys(root)
    if corpus is None:
        return None
    aliases = _extract_action_param_aliases(data)
    tool_index = build_tool_index(root)
    tj_cache: dict[Path, dict] = {}

    def _props_of(pkg_dir: Path, tool_name: str) -> set[str] | None:
        """그 패키지 tool.json 에서 tool_name 의 properties 키 집합. 문서가 없으면 None."""
        if pkg_dir not in tj_cache:
            path = pkg_dir / "tool.json"
            try:
                tj_cache[pkg_dir] = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                tj_cache[pkg_dir] = {}
        doc = tj_cache[pkg_dir] or {}
        for t in (doc.get("tools") or []):
            if isinstance(t, dict) and t.get("name") == tool_name:
                isch = t.get("input_schema")
                if not isinstance(isch, dict):
                    return set()
                return set((isch.get("properties") or {}).keys())
        return None

    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions", {}) or {}).items():
            if not isinstance(action, dict):
                continue
            qualified = f"{node_name}:{action_name}"
            used = corpus.get(qualified)
            if not used:
                continue
            if action.get("router") != "handler":
                continue          # tool.json 이 없는 라우터(system/engine/…)는 대상 밖
            tool_name = action.get("tool")
            if not tool_name or tool_name not in tool_index:
                continue
            declared = _props_of(tool_index[tool_name][0], tool_name)
            if declared is None:
                continue          # 액션 미소유 도구·문서 미이관 — 다른 가드의 일
            known = set(declared) | set(UNIVERSAL_PARAM_KEYS) | set(RUNTIME_META_KEYS)
            known |= aliases.get(qualified, set())
            known |= CORPUS_PARAM_ALLOW.get(qualified, set())
            missing = sorted(used - known)
            if missing:
                issues.append(
                    f"{qualified} ({tool_name}): 코퍼스가 쓰는 param 에 타입 선언이 없음 — {missing} "
                    f"(해당 패키지 ibl_actions.yaml 의 tool_json.tools[name={tool_name}]"
                    f".input_schema.properties 에 타입을 적을 것; 컨테이너 자리면 object/array)"
                )
    return issues


