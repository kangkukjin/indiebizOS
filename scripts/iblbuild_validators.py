"""build_ibl_nodes 검증 계층 (2026-07-18 모듈화 — 1500줄 규칙).

build_ibl_nodes.py 에서 verbatim 이동: 액션 삼각검증(_check_action — src↔tool.json↔
handler _OP_DISPATCHERS AST)·코퍼스 param 정합·runs_on/변환자/폰도달성/fixture/가이드/
표준-코어/always_on 검증 + 총괄 validate().
"""
from __future__ import annotations
import ast
import json
import re
import sys
from pathlib import Path

from iblbuild_common import (
    CORPUS_FILES,
    DEFAULT_RUNS_ON,
    PHONE_VERIFIED_PACKAGES,
    VALID_RUNS_ON,
    UNIVERSAL_PARAM_KEYS,
    CORPUS_PARAM_ALLOW,
    _dir_read_keys,
    _extract_action_param_aliases,
)
from iblbuild_derive import build_tool_index
from iblbuild_appview import validate_app_blocks, validate_standalone_instruments


def _extract_op_dispatchers(handler_text: str) -> dict[str, tuple[set[str], object]] | None:
    """handler.py 본문에서 _OP_DISPATCHERS dict 를 AST 로 파싱.

    Returns:
        {tool_name: (op_key_set, raw_dict_node)} 또는 None (dict 없음).
        타입이 dict 가 아니거나 키가 문자열 상수가 아니면 None.
    """
    try:
        tree = ast.parse(handler_text)
    except SyntaxError:
        return None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "_OP_DISPATCHERS" not in names:
            continue
        if not isinstance(node.value, ast.Dict):
            return None
        result: dict[str, tuple[set[str], object]] = {}
        for k_node, v_node in zip(node.value.keys, node.value.values):
            if not (isinstance(k_node, ast.Constant) and isinstance(k_node.value, str)):
                continue
            tool_name = k_node.value
            if not isinstance(v_node, ast.Dict):
                continue
            op_keys: set[str] = set()
            for op_k in v_node.keys:
                if isinstance(op_k, ast.Constant) and isinstance(op_k.value, str):
                    op_keys.add(op_k.value)
            result[tool_name] = (op_keys, v_node)
        return result
    return None


def _extract_op_defaults(handler_text: str) -> dict[str, str] | None:
    """handler.py 본문에서 _OP_DEFAULTS dict 를 AST 로 파싱.

    Returns:
        {tool_name: default_op_str} 또는 None.
    """
    try:
        tree = ast.parse(handler_text)
    except SyntaxError:
        return None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "_OP_DEFAULTS" not in names:
            continue
        if not isinstance(node.value, ast.Dict):
            return None
        result: dict[str, str] = {}
        for k_node, v_node in zip(node.value.keys, node.value.values):
            if (isinstance(k_node, ast.Constant) and isinstance(k_node.value, str)
                    and isinstance(v_node, ast.Constant) and isinstance(v_node.value, str)):
                result[k_node.value] = v_node.value
        return result
    return None


def _check_action(
    qualified: str,
    action: dict,
    tool_index: dict[str, tuple[Path, dict]],
) -> list[str]:
    """단일 액션의 정합성을 검사하고 문제 리스트를 반환."""
    issues: list[str] = []
    router = action.get("router")
    tool_name = action.get("tool")
    target_key = action.get("target_key")
    ops = action.get("ops")

    # --- ops 스키마 자체 검증 ---
    if ops is not None:
        if target_key != "op":
            issues.append(
                f"{qualified}: ops 블록은 target_key:op 인 액션에서만 허용 "
                f"(현재 target_key={target_key!r})"
            )
        if not isinstance(ops, dict):
            issues.append(f"{qualified}: ops 는 매핑이어야 함")
            return issues
        values = ops.get("values")
        if not isinstance(values, dict) or not values:
            issues.append(f"{qualified}: ops.values 가 비어있거나 매핑이 아님")
            return issues

    # --- aliases(파라미터 별칭) 스키마 검증 — 어휘 데이터화(2026-07-03) ---
    # 형식: aliases: {<정규 키>: [<별칭>, ...]} — 런타임 _normalize_param_aliases 가 읽는다.
    aliases = action.get("aliases")
    if aliases is not None:
        if not isinstance(aliases, dict) or not aliases:
            issues.append(f"{qualified}: aliases 는 비어있지 않은 매핑이어야 함 ({{정규키: [별칭...]}})")
        else:
            for canonical, alts in aliases.items():
                if not isinstance(alts, list) or not alts or not all(
                    isinstance(a, str) and a for a in alts
                ):
                    issues.append(f"{qualified}: aliases.{canonical} 는 비어있지 않은 문자열 리스트여야 함")
                elif canonical in alts:
                    issues.append(f"{qualified}: aliases.{canonical} 에 정규 키 자신이 별칭으로 들어감")

    # target_key:op 인데 ops 없음 — 모든 라우터에서 강제 (IBL 어휘 일관성).
    # handler 가 아닌 라우터(system/workflow_engine/trigger_engine 등)는 tool.json 삼각 검증은 못 하지만
    # ops 블록 자체는 어휘 완성을 위해 필수.
    if target_key == "op" and ops is None:
        issues.append(f"{qualified}: target_key:op 인데 ops 블록 없음 ({router or 'unknown'} 라우터)")

    # --- returns(통화 역할) 검증 — 단일 통화(items) 이행 완료(2026-06-27) ---
    # 모든 액션은 자기 통화 역할을 명시한다: 생성(items) · 변환(transform) · 종착(scalar/effect).
    # ★단일 통화: 컬렉션은 전부 items {[{…열린 필드…}]}. 옛 records/table/document/currency 는
    #   전부 items로 흡수 완료 — table(연도×지표 등)·문서IR(type+text)도 items 행dict로, 소비자가 재구성.
    #   (이행 이력: docs/SINGLE_CURRENCY_MIGRATION_HANDOFF.md / architecture_single_currency_items 메모)
    #   ※geo/지도는 통화 아님 — map_data 는 *렌더링 봉투*(파이프 변환자 없음).
    _RETURNS_ENUM = {"items", "transform", "scalar", "effect"}
    returns = action.get("returns")
    group = action.get("group")
    if returns is None:
        issues.append(f"{qualified}: returns 필드 없음 — 통화 역할 명시 필수 (items|transform|scalar|effect)")
    elif returns not in _RETURNS_ENUM:
        issues.append(f"{qualified}: returns={returns!r} 허용 안 됨 (items|transform|scalar|effect)")
    else:
        if group == "transform" and returns != "transform":
            issues.append(f"{qualified}: group:transform 인데 returns={returns!r} — transform 이어야 함")
        if returns == "transform" and group != "transform":
            issues.append(f"{qualified}: returns:transform 은 group:transform 액션에만 (현재 group={group!r})")

    # --- handler 라우터 등록 검증 ---
    if router == "handler":
        if not tool_name:
            issues.append(f"{qualified}: router:handler 인데 tool 필드 없음")
            return issues

        if tool_name not in tool_index:
            issues.append(
                f"{qualified}: tool '{tool_name}' 가 어느 패키지 tool.json 에도 미등록"
            )
            return issues

        pkg_dir, tool_def = tool_index[tool_name]
        pkg_name = pkg_dir.name

        # --- op 삼각 검증 ---
        if ops:
            tj_op_prop = (
                tool_def.get("input_schema", {})
                .get("properties", {})
                .get("op", {})
            ) or {}
            tj_enum = tj_op_prop.get("enum")
            tj_default = tj_op_prop.get("default")

            if not tj_enum:
                issues.append(
                    f"{qualified}: src.ops 선언했으나 tool.json {pkg_name}/{tool_name} "
                    f"에 input_schema.properties.op.enum 없음"
                )
            else:
                src_keys = set(ops.get("values", {}).keys())
                tj_keys = set(tj_enum)
                if src_keys != tj_keys:
                    only_src = sorted(src_keys - tj_keys)
                    only_tj = sorted(tj_keys - src_keys)
                    detail = []
                    if only_src:
                        detail.append(f"src만 있음: {only_src}")
                    if only_tj:
                        detail.append(f"tool.json만 있음: {only_tj}")
                    issues.append(
                        f"{qualified}: op 키 불일치 ({pkg_name}/{tool_name}) — "
                        f"{'; '.join(detail)}"
                    )

            src_default = ops.get("default")
            if src_default != tj_default:
                issues.append(
                    f"{qualified}: op default 불일치 ({pkg_name}/{tool_name}) — "
                    f"src={src_default!r} / tool.json={tj_default!r}"
                )

            # --- handler.py 검사 (AST 우선, substring 폴백) ---
            handler_py = pkg_dir / "handler.py"
            if handler_py.is_file():
                src_text = handler_py.read_text(encoding="utf-8")
                src_op_keys = set(ops.get("values", {}).keys())
                dispatchers = _extract_op_dispatchers(src_text)

                if dispatchers is not None and tool_name in dispatchers:
                    # AST 정확 비교 — _OP_DISPATCHERS[tool_name] 키 ↔ src.ops.values 키
                    handler_keys, _ = dispatchers[tool_name]
                    if handler_keys != src_op_keys:
                        only_src = sorted(src_op_keys - handler_keys)
                        only_handler = sorted(handler_keys - src_op_keys)
                        detail = []
                        if only_src:
                            detail.append(f"src만: {only_src}")
                        if only_handler:
                            detail.append(f"handler만: {only_handler}")
                        issues.append(
                            f"{qualified}: handler.py _OP_DISPATCHERS[{tool_name!r}] 키 불일치 "
                            f"({pkg_name}) — {'; '.join(detail)}"
                        )

                    # _OP_DEFAULTS 도 검사 (있을 때만)
                    defaults = _extract_op_defaults(src_text)
                    if defaults is not None:
                        handler_default = defaults.get(tool_name)
                        src_default = ops.get("default")
                        if handler_default != src_default:
                            issues.append(
                                f"{qualified}: _OP_DEFAULTS[{tool_name!r}] 불일치 "
                                f"({pkg_name}) — src={src_default!r} / handler={handler_default!r}"
                            )
                else:
                    # 폴백: substring 휴리스틱
                    missing = [
                        k
                        for k in src_op_keys
                        if f'"{k}"' not in src_text and f"'{k}'" not in src_text
                    ]
                    if missing:
                        issues.append(
                            f"{qualified}: handler.py {pkg_name} 에 op 문자열 미발견 — {missing} "
                            f"(_OP_DISPATCHERS 도입 권장)"
                        )

    return issues


# _file_read_keys / _dir_read_keys 는 backend/ibl_param_vocab.py 에서 import (iblbuild_common 경유).


def _load_corpus_param_keys(root: Path) -> dict[str, set[str]] | None:
    """학습 코퍼스를 실제 IBL 파서로 파싱 → {qualified: set(top-level param 키)}.
    파서/코퍼스 미가용 시 None (검사 건너뜀)."""
    backend = root / "backend"
    try:
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
        import ibl_parser  # type: ignore
    except Exception:
        return None

    def walk(obj):
        res = []
        if isinstance(obj, dict):
            if "_node" in obj and "action" in obj:
                res.append(obj)
            for v in obj.values():
                res += walk(v)
        elif isinstance(obj, list):
            for v in obj:
                res += walk(v)
        return res

    out: dict[str, set[str]] = {}
    found_any = False
    for rel in CORPUS_FILES:
        f = root / rel
        if not f.is_file():
            continue
        try:
            entries = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        found_any = True
        for e in entries:
            try:
                parsed = ibl_parser.parse(e.get("ibl_code", ""))
            except Exception:
                continue
            for st in walk(parsed):
                q = f"{st.get('_node')}:{st.get('action')}"
                out.setdefault(q, set()).update((st.get("params") or {}).keys())
    return out if found_any else None


def validate_corpus_params(data: dict, root: Path) -> list[str] | None:
    """코퍼스 param 키 ↔ (핸들러 읽기키 ∪ 액션 aliases 선언 ∪ 보편키 ∪ target_key) 대조.

    코퍼스가 자연어로 쓰는 키를 핸들러가 조용히 무시하는 신규 불일치를 검출한다.
    router:handler 액션은 패키지 .py 전체를, 그 외(system/engine/driver/trigger)는
    backend/*.py 전역 어휘를 핸들러 키 출처로 본다 (후자는 보수적 = 오탐 회피 우선).
    파서/코퍼스 미가용 시 None (검사 건너뜀)."""
    corpus = _load_corpus_param_keys(root)
    if corpus is None:
        return None
    aliases = _extract_action_param_aliases(data)
    tool_index = build_tool_index(root)
    backend_keys = _dir_read_keys((root / "backend").glob("*.py"))
    pkg_cache: dict[Path, set[str]] = {}

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
            known = set(UNIVERSAL_PARAM_KEYS)
            if action.get("target_key"):
                known.add(action["target_key"])
            known |= aliases.get(qualified, set())
            known |= CORPUS_PARAM_ALLOW.get(qualified, set())
            tool_name = action.get("tool")
            if action.get("router") == "handler" and tool_name and tool_name in tool_index:
                pkg_dir = tool_index[tool_name][0]
                if pkg_dir not in pkg_cache:
                    pkg_cache[pkg_dir] = _dir_read_keys(pkg_dir.rglob("*.py"))
                known |= pkg_cache[pkg_dir]
            else:
                known |= backend_keys
            unknown = sorted(used - known)
            if unknown:
                issues.append(
                    f"{qualified}: 코퍼스 param 키가 핸들러/별칭에 없음 — {unknown} "
                    f"(액션 정의처의 aliases: 블록에 별칭 추가 · 핸들러 폴백 · 코퍼스 정정 중 택1; "
                    f"의도된 노이즈면 build_ibl_nodes.CORPUS_PARAM_ALLOW 에 등록)"
                )
    return issues


def validate_runs_on(data: dict) -> list[str]:
    """모든 액션의 runs_on 값이 유효 enum 인지 검사 (미지정=anywhere 허용)."""
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict):
                continue
            ro = action.get("runs_on")
            if ro is not None and ro not in VALID_RUNS_ON:
                issues.append(
                    f"{node_name}:{action_name} — 잘못된 runs_on '{ro}' "
                    f"(허용: {', '.join(sorted(VALID_RUNS_ON))})"
                )
    return issues


def validate_transform_contract(data: dict) -> list[str]:
    """통화 변환자(group: transform) 계약 강제 — 닫힌-계급 문법/superstructure.

    변환자(filter/sort/groupby/join…)는 통화→통화 순수 함수다 — 몸 무관, 외부 자원 없음.
    *이름*(현재 engines:)이 아니라 **group 태그가 닫힌 계급의 단일 마커**다(설계 결정:
    비싼 노드 이전 대신 태그를 load-bearing 으로 — docs/ibl_design_philosophy.md). 계약:
      - scope: workspace  — 무프로젝트 파이프에서도 돌아야(project 기본이면 0ms 즉시 실패: 과거 버그)
      - runs_on: anywhere — 통화는 몸 무관(폰-로컬 통화도 그 몸에서 거르고 정렬)
    새 변환자가 이 계약을 빠뜨리면 침묵-실패가 재발 → 여기서 구조로 막는다.
    """
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict) or action.get("group") != "transform":
                continue
            q = f"{node_name}:{action_name}"
            if action.get("scope") != "workspace":
                issues.append(
                    f"{q} — 변환자(group:transform)는 scope: workspace 필수 "
                    f"(현재 '{action.get('scope') or '없음=project기본'}'). "
                    f"무프로젝트 파이프서 즉시 실패 방지."
                )
            if action.get("runs_on") != "anywhere":
                issues.append(
                    f"{q} — 변환자는 runs_on: anywhere 필수 "
                    f"(현재 '{action.get('runs_on') or '없음'}'). 통화는 몸 무관."
                )
    return issues


def validate_phone_reachability(data: dict, root: Path) -> list[str]:
    """runs_on 정직성: anywhere(기본) 액션인데 handler/driver 패키지가 PHONE_VERIFIED 가 아니면
    적발. 그런 액션은 폰서 _phone_runnable=False → 조용히 _forward_to_mac 된다(ibl_engine.py).
    즉 anywhere 와 pc_only 가 폰에서 행동이 같아 태그가 거짓 → silent-forward 라 self-check 가
    못 잡던 부류. 해소: 패키지를 PHONE_VERIFIED 에 넣거나(폰 로컬 실행) 액션에 runs_on: pc_only
    명시(허브 포워드 명시). 비-패키지(system/engine 등) 액션은 대상 아님(번들 모듈로 폰서 실행)."""
    issues: list[str] = []
    tool_index = build_tool_index(root)
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict):
                continue
            ro = action.get("runs_on", DEFAULT_RUNS_ON)
            if ro != "anywhere":
                continue  # pc_only/phone_only = 명시적(정직)
            tool = action.get("tool")
            if not tool or tool not in tool_index:
                continue  # 비-패키지 액션(system/engine 등) — 번들 모듈로 폰 실행
            pkg = tool_index[tool][0].name
            if pkg not in PHONE_VERIFIED_PACKAGES:
                issues.append(
                    f"{node_name}:{action_name} — runs_on=anywhere 인데 패키지 '{pkg}' 폰 미검증 "
                    f"→ 폰서 조용히 허브 포워드(태그 거짓). 패키지를 PHONE_VERIFIED_PACKAGES 에 넣거나 "
                    f"액션에 'runs_on: pc_only' 명시."
                )
    return issues


def validate_fixture_coverage(data: dict, root: Path) -> list[str]:
    """행동 건강 fixture 완전성 강제 — 신규 액션이 건강검사망을 빠져나갈 수 없게.

    실행 가능한(returns: items|scalar) 액션은 자기 정의에 `fixture:`(올바른 파라미터
    예 하나) 또는 `exempt:`(실행 인자 의존 — 사유) 필드를 반드시 가져야 한다.
    effect(부작용 — 실행 불가)·transform(골든파이프로 흐름검증)은 면제.

    필드는 액션이 사는 소스(패키지 ibl_actions.yaml / 코어 ibl_nodes_src)에 두고,
    build 가 ibl_fixtures.json 으로 파생한다. 파생물이라 *고아 fixture 는 구조적으로
    없다*(과거의 별도 orphan 검사 불필요). 이로써 "어휘를 만들면 fixture 한 줄도 같이"가
    권고가 아니라 커밋 게이트가 되고(new_action_checklist.md), 제거는 재빌드만으로
    fixture 가 함께 빠진다(action_removal.md).
    """
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions", {}) or {}).items():
            if not isinstance(action, dict):
                continue
            if action.get("returns") in ("items", "scalar"):
                if not action.get("fixture") and not action.get("exempt"):
                    issues.append(
                        f"{node_name}:{action_name}: returns:items|scalar 인데 "
                        f"fixture/exempt 필드 없음 — 액션 정의(패키지 ibl_actions.yaml "
                        f"또는 ibl_nodes_src)에 `fixture: '[...]'` 한 줄 추가 "
                        f"(실행 인자 의존이면 `exempt: '<사유>'`)"
                    )
            elif action.get("fixture") or action.get("exempt"):
                # 역방향 가드: 확률대상 밖(effect·transform) 액션의 fixture/exempt 는 잉여이고,
                # fixture 는 §1B 가 실제로 실행하므로 부작용 액션이면 점검마다 부작용을 낸다
                # (2026-07-19 실측: mkdir fixture 가 검진마다 폴더를 만들고 있었다).
                field = "fixture" if action.get("fixture") else "exempt"
                issues.append(
                    f"{node_name}:{action_name}: returns:{action.get('returns')} 인데 "
                    f"`{field}:` 필드 보유 — items/scalar 전용 필드다. 제거할 것"
                    + (" (부작용 액션 fixture 는 건강검진마다 부작용 실행)" if field == "fixture" else "")
                )
    return issues


def validate_node_guides(data: dict, root: Path) -> list[str]:
    """노드 레벨 guides: 목록이 data/guides/ 실존 파일을 가리키는지 검증.

    유령 등재는 의식 에이전트/read_guide 경로에서 침묵 실패(_load_guide_file 이
    빈 문자열 반환)로 이어지므로 빌드에서 막는다.
    """
    issues: list[str] = []
    guides_dir = root / "data" / "guides"
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for g in node.get("guides") or []:
            if not (guides_dir / str(g)).exists():
                issues.append(f"[{node_name}] guides 유령 등재: data/guides/{g} 실존하지 않음")
    return issues


# === 표준-코어 가드: IBL 표준(문법+기능어) 경계 통제 (2026-07-03, ibl.md '언어의 경계' 조항) ===
# IBL 표준 = 문법(연산자·[node:action]{params}·파이프 설탕) + 기능어 코어(아래 집합).
# 이 집합을 바꾸는 것은 '언어 개정'이다 — ibl.md 헌법 조항·파서 desugar·노드 yaml의
# always_on 플래그를 함께, 의식적으로 바꿔야 하며, 여기 선언을 갱신하지 않으면 빌드가 멈춘다.
# 내용어(그 외 노드의 액션)는 개인 사전: yaml+패키지 데이터만으로 추가·제거되어야 하고
# 파서·엔진 코드에 이름이 박히면 안 된다 (별칭·always_on 데이터화로 확립된 불변식).
STANDARD_CORE_NODES = {"self", "others", "table"}


def validate_standard_core(data: dict, root: Path) -> list[str]:
    """표준-코어 가드 — ①always_on 노드 집합이 STANDARD_CORE_NODES 선언과 일치하는지
    ②파서 파이프 설탕(_pipe_block)의 desugar 타깃(문법이 아는 유일한 어휘)이
    표준 코어 노드의 실존 액션인지 적발한다."""
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    on = {n for n, cfg in nodes.items()
          if isinstance(cfg, dict) and cfg.get("always_on") is True}
    if nodes and on != STANDARD_CORE_NODES:
        issues.append(
            f"표준-코어 가드: always_on 노드 집합 {sorted(on)} ≠ 선언 {sorted(STANDARD_CORE_NODES)} "
            "(STANDARD_CORE_NODES). 기능어 코어 변경은 언어 개정 — ibl.md '언어의 경계' 조항과 "
            "이 선언을 함께 갱신할 것."
        )
    parser_path = root / "backend" / "ibl_parser.py"
    try:
        src = parser_path.read_text(encoding="utf-8")
    except OSError:
        issues.append(f"표준-코어 가드: 파서를 읽지 못함 ({parser_path})")
        return issues
    m = re.search(r"def _pipe_block\(.*?(?=\ndef |\Z)", src, re.S)
    body = m.group(0) if m else ""
    targets = set(re.findall(r"\[(\w+):(\w+)\]", body))
    if not targets:
        issues.append(
            "표준-코어 가드: 파서 _pipe_block 에서 desugar 타깃([x:y] 코드젠 리터럴)을 찾지 못함 — "
            "함수 이동/개명 시 이 가드도 함께 갱신할 것"
        )
    for node_name, action_name in sorted(targets):
        if node_name not in STANDARD_CORE_NODES:
            issues.append(
                f"표준-코어 가드: 파서 desugar 가 비표준 노드 [{node_name}:{action_name}] 를 코드젠 — "
                "문법 설탕은 기능어 코어(STANDARD_CORE_NODES)로만 펼칠 수 있음"
            )
        elif action_name not in ((nodes.get(node_name) or {}).get("actions") or {}):
            issues.append(
                f"표준-코어 가드: 파서 desugar 타깃 [{node_name}:{action_name}] 가 레지스트리에 없음 — "
                "표준 코어 액션 개명 시 ibl_parser._pipe_block 도 함께 (언어 개정)"
            )
    return issues


def validate_always_on(data: dict) -> list[str]:
    """노드 레벨 always_on 플래그 검증 — 인프라/문법 노드 항상-on 의 단일 소스(2026-07-03 데이터화).

    ibl_access._always_allowed() 가 이 플래그로 항상-허용 노드 집합을 만든다.
    전부 사라지면 노드 선별(allowed_nodes) 시 self/others/table 파이프라인이
    침묵으로 깨지므로 빌드에서 막는다."""
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    on: list[str] = []
    for node_name, node in nodes.items():
        if not isinstance(node, dict) or "always_on" not in node:
            continue
        if not isinstance(node["always_on"], bool):
            issues.append(f"[{node_name}] always_on 은 불리언이어야 함 (현재 {node['always_on']!r})")
        elif node["always_on"]:
            on.append(node_name)
    if nodes and not on:
        issues.append(
            "always_on: true 노드가 하나도 없음 — 인프라/문법 노드(self/others/table)가 "
            "노드 선별에서 꺼지면 파이프라인이 깨짐 (노드 yaml 에 always_on: true 복구 필요)"
        )
    return issues


def validate(data: dict, root: Path) -> list[str]:
    """전체 yaml 데이터에 대해 삼각 검증 수행."""
    issues: list[str] = []
    tool_index = build_tool_index(root)
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        actions = node.get("actions", {}) or {}
        for action_name, action in actions.items():
            if not isinstance(action, dict):
                continue
            qualified = f"{node_name}:{action_name}"
            issues.extend(_check_action(qualified, action, tool_index))
    issues.extend(validate_app_blocks(data))
    issues.extend(validate_standalone_instruments(data))
    issues.extend(validate_runs_on(data))
    issues.extend(validate_transform_contract(data))
    issues.extend(validate_phone_reachability(data, root))
    issues.extend(validate_node_guides(data, root))
    issues.extend(validate_always_on(data))
    issues.extend(validate_standard_core(data, root))
    return issues
