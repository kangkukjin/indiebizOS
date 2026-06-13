#!/usr/bin/env python3
"""ibl_nodes.yaml 빌드 — 편집용 소스 6개를 단일 yaml로 병합 + 삼각 검증.

편집 워크플로:
1) `data/ibl_nodes_src/<name>.yaml` 중 하나를 편집
2) `python scripts/build_ibl_nodes.py` 실행
3) `data/ibl_nodes.yaml`이 갱신됨 (런타임이 읽는 단일 파일)

런타임 코드는 단일 ibl_nodes.yaml만 읽는다 (ibl_access / tool_loader /
tool_selector / system_tools).

병합 방식: 바이트-단위 연결. 소스 파일들의 내용은 원본 yaml의 해당 span에서
잘라낸 바이트 그대로이므로, 정상 워크플로에서는 byte-identical 라운드트립이
보장된다 (소스 편집 후엔 그 부분만 달라짐).

검증 (2026-05-28 추가) — router:handler 액션에 대해 삼각 일치 확인:
  src.tool       ↔  packages/.../tool.json 의 name
  src.ops.values ↔  tool.json input_schema.properties.op.enum
  src.ops.default ↔ tool.json input_schema.properties.op.default
  src.ops.values ↔  handler.py 의 _OP_DISPATCHERS[tool_name] 키 (AST, 정확)
                       또는 _OP_DISPATCHERS 없으면 op 문자열 substring (폴백)
  src.ops.default ↔ handler.py 의 _OP_DEFAULTS[tool_name] (AST, _OP_DISPATCHERS 있을 때만)
실패하면 `--check`는 비0 종료, 일반 빌드는 경고만 출력.

코퍼스 param 정합 (2026-06-04 추가, --check/--validate 전용):
  학습 코퍼스의 액션별 param 키 ↔ (핸들러 읽기키 ∪ ACTION_PARAM_ALIASES ∪ 보편키 ∪ target_key).
  코퍼스가 자연어로 쓰는 키를 핸들러가 조용히 무시하는 신규 불일치를 검출 (silent-ignore 회귀 방지).
  의도된 노이즈는 CORPUS_PARAM_ALLOW 에 등록. 파서/코퍼스 미가용 시 건너뜀.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path


# 순서가 중요 — 원본 yaml의 노드 순서와 동일해야 함.
NODE_ORDER = ["sense", "self", "limbs", "others", "engines"]

# 패키지 탐색 경로 — installed/tools 가 표준, extensions 도 함께 스캔.
PACKAGE_DIRS = [
    "data/packages/installed/tools",
    "data/packages/installed/extensions",
]

# === runs_on 능력 태그 (2026-06-11, #3 폰 네이티브) ===
# 액션이 어디서 도는가: anywhere(기본·이식가능 로직/HTTP) / home_only(집 PC 하드웨어·
# 무거운 의존·미검증 패키지) / phone_only(폰 하드웨어=알림·센서, 미래 M3).
VALID_RUNS_ON = {"anywhere", "home_only", "phone_only"}
DEFAULT_RUNS_ON = "anywhere"

# 실기기(Galaxy A36)에서 import+종단 실행이 검증된 폰안전 패키지 — 폰 프로파일의 단일 진실 소스.
# (옛 build.gradle 의 하드코딩 _PHONE_PACKAGES 를 여기로 승격. phone_manifest.json 으로 파생.)
# handler 라우터 액션의 폰 실행가능성은 이 집합으로 결정(미검증 패키지=폰서 제외).
# 새 패키지를 폰서 검증하면 여기 추가.
PHONE_VERIFIED_PACKAGES = {
    "location-services",
    "investment",
    "culture",
    "radio",
    "web",
    "real-estate",
    "android",   # M3: [sense:phone] 폰 로컬 알림. limbs:android(android_op)은 home_only 태그로 제외.
    "business",  # 메신저(others:messages/neighbor/contact)+비즈니스 CRM(self:business*). business.db 폰 머지 토대 위. auto_response 는 home_only 로 제외(PC 전용 폴러).
    "cctv",      # CCTV 검색(sense:cctv search) — 모듈 import importlib.util(stdlib)뿐, HLS는 WebView <video>+hls.js 재생.
}

# === 코퍼스 param 정합 검사 (2026-06-04) ===
# 모든 액션이 자연히 받는 보편 키 (op 디스패치/레거시 target).
UNIVERSAL_PARAM_KEYS = {"op", "target"}

# 코퍼스가 쓰지만 핸들러/별칭에 의도적으로 없는 키 (문서화된 예외).
# 목적: 신규 불일치만 잡고 알려진 노이즈는 통과. 코퍼스 정제/별칭으로 해소되면 여기서 제거할 것.
CORPUS_PARAM_ALLOW: dict[str, set[str]] = {
    # browser_op은 2차 selector 'mode'를 _OP_SELECTOR로 동적 pop(handler.py) —
    # 정적 리터럴이 아니라 검출 불가. 핸들러가 실제로 읽으므로 의도된 예외.
    "limbs:browser": {"mode"},
}
# 정리됨(2026-06-04): pew_research:topic / blog:sort / web_site:reference / web:font
#   (migrate_allowlist_cleanup.py — 군더더기 제거) + self:trigger:cron
#   (trigger_engine._cron_to_config 로 내부 해소 — 핸들러가 cron 직접 읽음).

# 학습 코퍼스 (param 키 추출 대상).
CORPUS_FILES = [
    "data/training/ibl_training_balanced_20260516.json",
    "data/training/ibl_distilled.json",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def build_tool_index(root: Path) -> dict[str, tuple[Path, dict]]:
    """모든 패키지 tool.json 을 스캔해 {tool_name: (pkg_dir, tool_def)} 사전 구축."""
    index: dict[str, tuple[Path, dict]] = {}
    for rel in PACKAGE_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for pkg_dir in sorted(base.iterdir()):
            if not pkg_dir.is_dir():
                continue
            tool_json = pkg_dir / "tool.json"
            if not tool_json.is_file():
                continue
            try:
                data = json.loads(tool_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(
                    f"[build_ibl_nodes] tool.json 파싱 실패 ({pkg_dir.name}): {e}",
                    file=sys.stderr,
                )
                continue
            for tool in data.get("tools", []) or []:
                name = tool.get("name")
                if name:
                    if name in index:
                        # 충돌 — 다른 패키지에서 같은 이름 재등록.
                        prev_pkg = index[name][0].name
                        print(
                            f"[build_ibl_nodes] WARN tool 이름 충돌: {name} "
                            f"({prev_pkg} vs {pkg_dir.name})",
                            file=sys.stderr,
                        )
                    index[name] = (pkg_dir, tool)
    return index


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

    # target_key:op 인데 ops 없음 — 모든 라우터에서 강제 (IBL 어휘 일관성).
    # handler 가 아닌 라우터(system/workflow_engine/trigger_engine 등)는 tool.json 삼각 검증은 못 하지만
    # ops 블록 자체는 어휘 완성을 위해 필수.
    if target_key == "op" and ops is None:
        issues.append(f"{qualified}: target_key:op 인데 ops 블록 없음 ({router or 'unknown'} 라우터)")

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


def _file_read_keys(text: str) -> set[str]:
    """파이썬 소스에서 '핸들러가 읽는 키' 후보를 AST로 추출.
    함수 파라미터명 + .get/_arg/pop 문자열 인자 + call 키워드 인자 + 문자열 subscript."""
    keys: set[str] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return keys
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = n.args
            for arg in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
                keys.add(arg.arg)
        elif isinstance(n, ast.Call):
            for kw in n.keywords:
                if kw.arg:
                    keys.add(kw.arg)
            func = n.func
            fname = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
            if fname in ("_arg", "get", "pop"):
                for arg in n.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        keys.add(arg.value)
        elif isinstance(n, ast.Subscript):
            sl = n.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                keys.add(sl.value)
    keys.discard(None)
    return keys


def _dir_read_keys(paths) -> set[str]:
    """여러 .py 파일에서 읽기키 합집합."""
    keys: set[str] = set()
    for py in paths:
        try:
            keys |= _file_read_keys(py.read_text(encoding="utf-8"))
        except Exception:
            continue
    return keys


def _extract_action_param_aliases(root: Path) -> dict[str, set[str]]:
    """backend/ibl_routing.py 의 ACTION_PARAM_ALIASES → {qualified: {정규키 ∪ 별칭들}} (AST)."""
    path = root / "backend" / "ibl_routing.py"
    out: dict[str, set[str]] = {}
    if not path.is_file():
        return out
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return out
    for node in tree.body:
        # 일반 대입과 주석 대입(`X: T = {...}`) 둘 다.
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "ACTION_PARAM_ALIASES" for t in targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for k_node, v_node in zip(node.value.keys, node.value.values):
            if not (isinstance(k_node, ast.Constant) and isinstance(k_node.value, str)):
                continue
            ks: set[str] = set()
            if isinstance(v_node, ast.Dict):
                for ck, cv in zip(v_node.keys, v_node.values):
                    if isinstance(ck, ast.Constant) and isinstance(ck.value, str):
                        ks.add(ck.value)
                    if isinstance(cv, ast.List):
                        for el in cv.elts:
                            if isinstance(el, ast.Constant) and isinstance(el.value, str):
                                ks.add(el.value)
            out[k_node.value] = ks
    return out


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
    """코퍼스 param 키 ↔ (핸들러 읽기키 ∪ ACTION_PARAM_ALIASES ∪ 보편키 ∪ target_key) 대조.

    코퍼스가 자연어로 쓰는 키를 핸들러가 조용히 무시하는 신규 불일치를 검출한다.
    router:handler 액션은 패키지 .py 전체를, 그 외(system/engine/driver/trigger)는
    backend/*.py 전역 어휘를 핸들러 키 출처로 본다 (후자는 보수적 = 오탐 회피 우선).
    파서/코퍼스 미가용 시 None (검사 건너뜀)."""
    corpus = _load_corpus_param_keys(root)
    if corpus is None:
        return None
    aliases = _extract_action_param_aliases(root)
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
                    f"(ibl_routing.ACTION_PARAM_ALIASES 별칭 추가 · 핸들러 폴백 · 코퍼스 정정 중 택1; "
                    f"의도된 노이즈면 build_ibl_nodes.CORPUS_PARAM_ALLOW 에 등록)"
                )
    return issues


# === app: 블록 검증 (2026-06-11, 원격 앱 표면 제네릭화 2단계) ===
# 액션이 자기 앱 표면(inputs/action 템플릿/view)을 선언하면 원격 런처가 자동 파생.
# 어휘 명세: docs/REMOTE_APP_GENERIC_RENDERER_PLAN.md. 소비자: api_launcher_web._derive_instruments.
APP_VIEW_TYPES = {"metric", "kv", "kv_list", "card_list", "image_grid", "sparkline", "list_action", "thread", "form", "editable_list", "map", "calendar"}
APP_INPUT_TYPES = {"text", "select"}
APP_FORM_FIELD_TYPES = {"text", "select", "toggle", "textarea", "images"}
APP_KEYS = {"instrument", "icon", "name", "order", "mode", "mode_order", "modes",
            "note", "auto_run", "inputs", "buttons", "action", "view", "renderer", "compose", "filter",
            "phone_render"}
APP_TPL_FILTERS = {"round", "num", "abs", "arrow"}  # + 'opt:' / 'trunc:' 접두 허용


def _app_action_templates(app: dict) -> list[str]:
    """app 블록에서 IBL 액션 템플릿 문자열 전부 수집 (참조 존재 검증용)."""
    import re as _re  # noqa: F401 (지역 사용 명시)
    out: list[str] = []
    if isinstance(app.get("action"), str):
        out.append(app["action"])
    cmp = app.get("compose")  # 블록 레벨 작성바(채팅/피드) — $text + {행필드} 템플릿
    if isinstance(cmp, dict) and isinstance(cmp.get("action"), str):
        out.append(cmp["action"])
    for b in app.get("buttons") or []:
        if isinstance(b, dict) and isinstance(b.get("action"), str):
            out.append(b["action"])
    for inp in app.get("inputs") or []:
        if isinstance(inp, dict) and isinstance(inp.get("options_action"), str):
            out.append(inp["options_action"])

    def walk_view(view):
        for p in view or []:
            if not isinstance(p, dict):
                continue
            # form(저장) / editable_list(추가·삭제) 액션
            if p.get("type") == "form" and isinstance(p.get("action"), str):
                out.append(p["action"])
            if p.get("type") == "form":  # 보조 액션(즐겨찾기 토글·삭제 등)
                for a in p.get("actions") or []:
                    if isinstance(a, dict) and isinstance(a.get("action"), str):
                        out.append(a["action"])
                for f in p.get("fields") or []:  # images 필드의 add_image/remove_image 템플릿
                    if isinstance(f, dict) and f.get("type") == "images":
                        for k in ("add_action", "remove_action"):
                            if isinstance(f.get(k), str):
                                out.append(f[k])
            if p.get("type") in ("editable_list", "calendar"):
                if isinstance(p.get("delete_action"), str):
                    out.append(p["delete_action"])
                add = p.get("add")
                if isinstance(add, dict) and isinstance(add.get("action"), str):
                    out.append(add["action"])
            for _bk in ("button", "button2"):  # list_action 행 버튼(▶ 재생 / ⬇ 다운로드)
                btn = p.get(_bk)
                if isinstance(btn, dict) and isinstance(btn.get("action"), str):
                    out.append(btn["action"])
            drill = p.get("item_click")
            if isinstance(drill, dict):
                if isinstance(drill.get("action"), str):
                    out.append(drill["action"])
                dcmp = drill.get("compose")  # 드릴(스레드) 레벨 작성바
                if isinstance(dcmp, dict) and isinstance(dcmp.get("action"), str):
                    out.append(dcmp["action"])
                walk_view(drill.get("view"))
                for tab in drill.get("tabs") or []:  # 드릴 상세 탭(대화/정보)
                    if isinstance(tab, dict):
                        tcmp = tab.get("compose")
                        if isinstance(tcmp, dict) and isinstance(tcmp.get("action"), str):
                            out.append(tcmp["action"])
                        walk_view(tab.get("view"))

    walk_view(app.get("view"))
    return out


def _block_local_keys(blk: dict) -> set:
    """블록 내 암묵 입력 키 집합 — compose($text), form 필드, editable_list add 필드.
    드릴 view·tabs 까지 재귀. validate 의 $key↔input 검사에 합류."""
    keys: set = set()

    def from_compose(c):
        if isinstance(c, dict) and c.get("action"):
            keys.add("text")
            if isinstance(c.get("channels"), dict):  # 채널 선택 → action 의 $channel_type/$to 주입
                keys.update(("channel_type", "to"))

    def from_fields(fields):
        for f in fields or []:
            if isinstance(f, dict) and f.get("key"):
                keys.add(f["key"])
            if isinstance(f, dict) and f.get("type") == "images":  # add/remove_image 가 $path 런타임 주입
                keys.add("path")

    def walk(view):
        for p in view or []:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "form":
                from_fields(p.get("fields"))
            if p.get("type") == "editable_list" and isinstance(p.get("add"), dict):
                from_fields(p["add"].get("fields"))
            if p.get("type") == "calendar" and isinstance(p.get("add"), dict):
                keys.update(("title", "date"))  # 렌더러가 제목 입력 + 선택일 date 를 add 액션에 주입
            drill = p.get("item_click")
            if isinstance(drill, dict):
                from_compose(drill.get("compose"))
                walk(drill.get("view"))
                for tab in drill.get("tabs") or []:
                    if isinstance(tab, dict):
                        from_compose(tab.get("compose"))
                        walk(tab.get("view"))

    from_compose(blk.get("compose"))
    walk(blk.get("view"))
    return keys


def _check_compose_channels(where: str, cmp) -> list[str]:
    """compose.channels(발신 채널 선택) 스키마 검증 — from/type/value 필수, sendable 은 리스트."""
    issues: list[str] = []
    if not isinstance(cmp, dict):
        return issues
    ch = cmp.get("channels")
    if ch is None:
        return issues
    if not isinstance(ch, dict):
        issues.append(f"{where}: compose.channels 는 매핑")
        return issues
    for k in ("from", "type", "value"):
        if not isinstance(ch.get(k), str) or not ch.get(k):
            issues.append(f"{where}: compose.channels.{k}(필드명) 필수")
    if ch.get("sendable") is not None and not isinstance(ch.get("sendable"), list):
        issues.append(f"{where}: compose.channels.sendable 은 채널 타입 리스트")
    return issues


def _app_check_view(qualified: str, view, depth: int = 0) -> list[str]:
    """view 프리미티브 배열 구조 검증 (드릴 뷰 재귀 포함)."""
    issues: list[str] = []
    if not isinstance(view, list) or not view:
        issues.append(f"{qualified}: app.view 는 비어있지 않은 리스트여야 함")
        return issues
    for i, p in enumerate(view):
        where = f"{qualified}: app.view[{i}]" + (" (드릴)" if depth else "")
        if not isinstance(p, dict):
            issues.append(f"{where} 가 매핑이 아님")
            continue
        ptype = p.get("type")
        if ptype not in APP_VIEW_TYPES:
            issues.append(f"{where}: 미지의 프리미티브 type={ptype!r} (어휘: {sorted(APP_VIEW_TYPES)})")
            continue
        if ptype in ("kv_list", "card_list", "image_grid", "sparkline", "list_action", "thread", "editable_list") and not p.get("from"):
            issues.append(f"{where}: {ptype} 는 from(데이터 경로) 필수")
        if ptype == "card_list" and not isinstance(p.get("card"), dict):
            issues.append(f"{where}: card_list 는 card 매핑 필수")
        if ptype == "thread" and not p.get("text"):
            issues.append(f"{where}: thread 는 text(버블 본문 템플릿) 필수")
        if ptype == "form":
            if not isinstance(p.get("action"), str):
                issues.append(f"{where}: form 은 action(저장 IBL 템플릿) 필수")
            fields = p.get("fields")
            if not isinstance(fields, list) or not fields:
                issues.append(f"{where}: form 은 fields(필드 리스트) 필수")
            else:
                for fi, f in enumerate(fields):
                    if not isinstance(f, dict) or not f.get("key"):
                        issues.append(f"{where}: form.fields[{fi}] key 필수")
                    elif f.get("type") not in APP_FORM_FIELD_TYPES:
                        issues.append(f"{where}: form.fields[{fi}] type={f.get('type')!r} (허용: {sorted(APP_FORM_FIELD_TYPES)})")
            # 보조 액션(즐겨찾기 토글·삭제 등) — label + action 필수, style 은 danger 만
            acts = p.get("actions")
            if acts is not None:
                if not isinstance(acts, list):
                    issues.append(f"{where}: form.actions 는 리스트")
                else:
                    for ai, a in enumerate(acts):
                        if not isinstance(a, dict) or not a.get("label") or not isinstance(a.get("action"), str):
                            issues.append(f"{where}: form.actions[{ai}] label·action(IBL 템플릿) 필수")
                        elif a.get("style") not in (None, "danger"):
                            issues.append(f"{where}: form.actions[{ai}] style={a.get('style')!r} (허용: danger)")
        if ptype == "editable_list":
            if not p.get("display"):
                issues.append(f"{where}: editable_list 는 display(행 표시 템플릿) 필수")
            add = p.get("add")
            if add is not None and (not isinstance(add, dict) or not isinstance(add.get("action"), str)):
                issues.append(f"{where}: editable_list.add 는 action(IBL 템플릿) 필수")
            if p.get("delete_action") is not None and not isinstance(p.get("delete_action"), str):
                issues.append(f"{where}: editable_list.delete_action 은 IBL 템플릿 문자열")
        drill = p.get("item_click")
        if drill is not None:
            if ptype != "card_list":
                issues.append(f"{where}: item_click 은 card_list 전용")
            elif not isinstance(drill, dict) or not isinstance(drill.get("action"), str):
                issues.append(f"{where}: item_click 은 action 템플릿 필수")
            else:
                tabs = drill.get("tabs")
                if isinstance(tabs, list) and tabs:  # 상세 탭(대화/정보)
                    for ti, tab in enumerate(tabs):
                        if not isinstance(tab, dict) or not tab.get("name"):
                            issues.append(f"{where}: item_click.tabs[{ti}] name 필수")
                            continue
                        issues.extend(_app_check_view(qualified, tab.get("view"), depth + 1))
                        tcmp = tab.get("compose")
                        if tcmp is not None and (not isinstance(tcmp, dict) or not isinstance(tcmp.get("action"), str)):
                            issues.append(f"{where}: item_click.tabs[{ti}].compose 는 action 필수")
                        issues.extend(_check_compose_channels(where, tcmp))
                elif "tabs" in drill:
                    issues.append(f"{where}: item_click.tabs 는 비어있지 않은 리스트여야 함")
                else:
                    issues.extend(_app_check_view(qualified, drill.get("view"), depth + 1))
                    dcmp = drill.get("compose")
                    if dcmp is not None and (not isinstance(dcmp, dict) or not isinstance(dcmp.get("action"), str)):
                        issues.append(f"{where}: item_click.compose 는 action(IBL 템플릿) 필수")
                    issues.extend(_check_compose_channels(where, dcmp))
        # button: list_action 은 {action} 행 버튼. form/editable_list 의 button 은 라벨 문자열이라 제외.
        btn = p.get("button")
        if ptype not in ("form", "editable_list") and btn is not None and (not isinstance(btn, dict) or not isinstance(btn.get("action"), str)):
            issues.append(f"{where}: button 은 action 템플릿 필수")
    return issues


def _app_check_filters(qualified: str, app: dict) -> list[str]:
    """표시 템플릿 '{path|filter}' 의 필터 오타 검출."""
    import re
    issues: list[str] = []
    strings: list[str] = []

    def walk(o):
        if isinstance(o, str):
            strings.append(o)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)

    walk(app.get("view"))
    for m in app.get("modes") or []:          # 명시적 modes 각 탭의 view 도 검사
        if isinstance(m, dict):
            walk(m.get("view"))
    for s in strings:
        for expr in re.findall(r"\{([^{}]+)\}", s):
            for f in [x.strip() for x in expr.split("|")[1:]]:
                if f in APP_TPL_FILTERS or f.startswith("opt:") or f.startswith("trunc:"):
                    continue
                issues.append(f"{qualified}: 미지의 템플릿 필터 {f!r} (in {s!r})")
    return issues


def validate_app_blocks(data: dict) -> list[str]:
    """app: 블록 정합성 — 액션 템플릿의 [node:action] 실존, $key↔inputs, view 어휘, 계기 그룹."""
    import re
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    qualified_set = {
        f"{n}:{a}"
        for n, nd in nodes.items() if isinstance(nd, dict)
        for a in (nd.get("actions") or {})
    }
    groups: dict[str, list[tuple[str, dict]]] = {}

    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict) or "app" not in action:
                continue
            qualified = f"{node_name}:{action_name}"
            app = action["app"]
            if not isinstance(app, dict):
                issues.append(f"{qualified}: app 은 매핑이어야 함")
                continue

            unknown = set(app.keys()) - APP_KEYS
            if unknown:
                issues.append(f"{qualified}: app 미지의 키 {sorted(unknown)} (허용: {sorted(APP_KEYS)})")

            # io(action/view/inputs/템플릿)는 블록 단위로 검증.
            # 명시적 modes(탭)면 각 탭이 독립 블록, 아니면 app 자신이 단일 블록.
            mode_list = app.get("modes")
            if isinstance(mode_list, list) and mode_list:
                blocks: list[tuple[str, dict]] = []
                for mi, m in enumerate(mode_list):
                    if not isinstance(m, dict):
                        issues.append(f"{qualified}: app.modes[{mi}] 가 매핑이 아님")
                        continue
                    if not m.get("name"):
                        issues.append(f"{qualified}: app.modes[{mi}] name(탭 이름) 필수")
                    blocks.append((f"{qualified} modes[{mi}]", m))
            elif "modes" in app:
                issues.append(f"{qualified}: app.modes 는 비어있지 않은 리스트여야 함")
                blocks = []
            else:
                blocks = [(qualified, app)]

            for blabel, blk in blocks:
                if not isinstance(blk.get("action"), str):
                    issues.append(f"{blabel}: app.action(IBL 템플릿) 필수")
                issues.extend(_app_check_view(blabel, blk.get("view")))
                _cmp = blk.get("compose")
                if _cmp is not None and (not isinstance(_cmp, dict) or not isinstance(_cmp.get("action"), str)):
                    issues.append(f"{blabel}: app.compose 는 action(IBL 템플릿) 필수")
                issues.extend(_check_compose_channels(blabel, _cmp))
                input_keys: set[str] = set()
                # 암묵 입력 키: compose($text)/form 필드/editable_list add 필드
                input_keys |= _block_local_keys(blk)
                # 필터 칩(filter, 기간·레벨 양용)도 액션 $key 의 출처 — input_keys 에 합류
                _pd = blk.get("filter")
                if isinstance(_pd, dict):
                    input_keys.add(_pd.get("key") or "filter")
                for j, inp in enumerate(blk.get("inputs") or []):
                    if not isinstance(inp, dict) or not inp.get("key"):
                        issues.append(f"{blabel}: app.inputs[{j}] 에 key 없음")
                        continue
                    input_keys.add(inp["key"])
                    itype = inp.get("type")
                    if itype not in APP_INPUT_TYPES:
                        issues.append(f"{blabel}: app.inputs[{j}] type={itype!r} (허용: {sorted(APP_INPUT_TYPES)})")
                    if itype == "select":
                        if inp.get("options"):
                            opts = inp["options"]
                            if not isinstance(opts, list) or not all(
                                isinstance(o, dict) and "value" in o and "label" in o for o in opts
                            ):
                                issues.append(f"{blabel}: app.inputs[{j}] 정적 options 는 [{{value,label}}] 배열")
                        elif inp.get("options_action"):
                            if not inp.get("options_from"):
                                issues.append(f"{blabel}: app.inputs[{j}] select options_action 에 options_from 필수")
                        else:
                            issues.append(f"{blabel}: app.inputs[{j}] select 는 정적 options 또는 options_action 필수")
                for t in _app_action_templates(blk):
                    for ref_node, ref_action in re.findall(r"\[(\w+):(\w+)\]", t):
                        if f"{ref_node}:{ref_action}" not in qualified_set:
                            issues.append(f"{blabel}: app 템플릿이 미존재 액션 [{ref_node}:{ref_action}] 참조 ({t!r})")
                    for key in re.findall(r"\$(\w+)", t):
                        if key not in input_keys:
                            issues.append(f"{blabel}: app 템플릿 $%s 에 대응하는 input 없음 ({t!r})" % key)

            issues.extend(_app_check_filters(qualified, app))

            gid = app.get("instrument") or action_name
            groups.setdefault(gid, []).append((qualified, app))

    # 계기 그룹 정합
    for gid, members in groups.items():
        partial = [q for q, a in members if bool(a.get("icon")) != bool(a.get("name"))]
        if partial:
            issues.append(f"계기 {gid!r}: icon/name 은 함께 선언해야 함 — 반쪽 선언 {partial}")
        primaries = [q for q, a in members if a.get("icon") and a.get("name")]
        if len(members) == 1:
            q, a = members[0]
            if not (a.get("icon") and a.get("name")):
                issues.append(f"{q}: 단독 계기 {gid!r} 는 icon+name 필수")
        else:
            if len(primaries) != 1:
                issues.append(
                    f"계기 {gid!r}: icon+name 선언 멤버(primary)가 정확히 1개여야 함 (현재 {len(primaries)}: {primaries})"
                )
            no_mode = [q for q, a in members if not a.get("mode")]
            if no_mode:
                issues.append(f"계기 {gid!r}: 복수 멤버는 전원 mode(탭 이름) 필수 — 누락 {no_mode}")
            mode_names = [a.get("mode") for _, a in members if a.get("mode")]
            if len(mode_names) != len(set(mode_names)):
                issues.append(f"계기 {gid!r}: mode 이름 중복 {mode_names}")
    return issues


# === runs_on 검증 + 폰 매니페스트 파생 (2026-06-11, #3) ===

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


def derive_phone_manifest(data: dict, root: Path) -> dict:
    """runs_on + 검증된 폰 패키지 → 폰 프로파일 매니페스트.

    runnable_actions(폰서 실행 가능):
      - runs_on == phone_only  → 폰 전용 하드웨어 액션(항상 포함)
      - runs_on == home_only   → 제외
      - runs_on == anywhere(기본):
          · handler/driver 라우터(패키지 보유) → 패키지가 PHONE_VERIFIED 일 때만
          · 비-패키지(system/engine 등) → 기본 포함(home_only 로 명시 태그 안 한 한)
    packages: 폰에 번들할 패키지 = PHONE_VERIFIED (Gradle 이 읽음).
    """
    tool_index = build_tool_index(root)
    runnable: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict):
                continue
            qualified = f"{node_name}:{action_name}"
            ro = action.get("runs_on", DEFAULT_RUNS_ON)
            if ro == "home_only":
                continue
            if ro == "phone_only":
                runnable.append(qualified)
                continue
            # anywhere
            tool = action.get("tool")
            pkg = None
            if tool and tool in tool_index:
                pkg = tool_index[tool][0].name
            if pkg is None:
                runnable.append(qualified)          # 비-패키지 액션: 기본 폰가능
            elif pkg in PHONE_VERIFIED_PACKAGES:
                runnable.append(qualified)          # 검증된 폰 패키지
            # else: 미검증 패키지 → 폰서 제외
    return {
        "_comment": "GENERATED by build_ibl_nodes.py — 폰 프로파일(어디서 도는가) 단일 진실 소스. 직접 수정 금지.",
        "packages": sorted(PHONE_VERIFIED_PACKAGES),
        "runnable_actions": sorted(runnable),
    }


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
    issues.extend(validate_runs_on(data))
    return issues


def build(check: bool = False, validate_only: bool = False) -> int:
    root = repo_root()
    src_dir = root / "data" / "ibl_nodes_src"
    target = root / "data" / "ibl_nodes.yaml"

    if not src_dir.is_dir():
        print(f"[build_ibl_nodes] 소스 디렉토리 없음: {src_dir}", file=sys.stderr)
        return 2

    header = (
        "# GENERATED — DO NOT EDIT\n"
        "# Source : data/ibl_nodes_src/{meta,sense,self,limbs,others,engines}.yaml\n"
        "# Rebuild: python3 scripts/build_ibl_nodes.py\n"
        "# Check  : python3 scripts/build_ibl_nodes.py --check\n"
        "\n"
    )
    parts: list[str] = [header]

    meta_path = src_dir / "meta.yaml"
    if not meta_path.is_file():
        print(f"[build_ibl_nodes] 누락: {meta_path}", file=sys.stderr)
        return 2
    parts.append(meta_path.read_text(encoding="utf-8"))

    # `nodes:` 헤더를 명시적으로 삽입 (소스 파일 어디에도 두지 않는다).
    parts.append("nodes:\n")

    for node in NODE_ORDER:
        node_path = src_dir / f"{node}.yaml"
        if not node_path.is_file():
            print(f"[build_ibl_nodes] 누락: {node_path}", file=sys.stderr)
            return 2
        parts.append(node_path.read_text(encoding="utf-8"))

    merged = "".join(parts)

    # YAML 파싱으로 sanity check — 노드/액션 수가 정상인지 + 검증.
    try:
        import yaml as _yaml
    except ImportError:
        print(
            "[build_ibl_nodes] PyYAML 없음 — 검증 건너뜀 (sanity check 불가)",
            file=sys.stderr,
        )
        _yaml = None

    data: dict | None = None
    if _yaml is not None:
        data = _yaml.safe_load(merged)
        nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
        total_actions = sum(
            len(n.get("actions", {})) for n in nodes.values() if isinstance(n, dict)
        )
        print(
            f"[build_ibl_nodes] 노드 {len(nodes)}개, 액션 {total_actions}개 "
            f"({sum(1 for _ in merged.splitlines())}줄, {len(merged.encode('utf-8'))}바이트)"
        )

    # --- 삼각 검증 ---
    validation_failed = False
    if data is not None:
        issues = validate(data, root)
        if issues:
            validation_failed = True
            print(
                f"[build_ibl_nodes] 검증 실패: {len(issues)}건",
                file=sys.stderr,
            )
            for issue in issues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] 검증 통과 ✓ (등록·op enum·default·handler 분기)")

    # --- 코퍼스 param 정합 검사 (--check/--validate 전용) ---
    # 코퍼스 드리프트가 평소 yaml 빌드를 막지 않도록, 게이트(check/validate)에서만 평가.
    corpus_failed = False
    if data is not None and (check or validate_only):
        cissues = validate_corpus_params(data, root)
        if cissues is None:
            print(
                "[build_ibl_nodes] 코퍼스/파서 미가용 — param 정합 검사 건너뜀",
                file=sys.stderr,
            )
        elif cissues:
            corpus_failed = True
            print(
                f"[build_ibl_nodes] 코퍼스 param 정합 실패: {len(cissues)}건",
                file=sys.stderr,
            )
            for issue in cissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] 코퍼스 param 정합 통과 ✓")

    if validate_only:
        return 1 if (validation_failed or corpus_failed) else 0

    # 폰 매니페스트 파생 (runs_on + 검증된 폰 패키지). data 파싱 성공 시에만.
    manifest_path = root / "data" / "phone_manifest.json"
    manifest_text = None
    if data is not None:
        manifest = derive_phone_manifest(data, root)
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"

    if check:
        if not target.is_file():
            print(f"[build_ibl_nodes] check: 타깃 부재 — {target}", file=sys.stderr)
            return 1
        current = target.read_text(encoding="utf-8")
        bytes_ok = current == merged
        if not bytes_ok:
            h_cur = hashlib.sha256(current.encode("utf-8")).hexdigest()[:12]
            h_new = hashlib.sha256(merged.encode("utf-8")).hexdigest()[:12]
            print(
                f"[build_ibl_nodes] check: 바이트 불일치 — 빌드 결과가 현재 yaml과 다름\n"
                f"  현재 {h_cur} / 빌드 {h_new}",
                file=sys.stderr,
            )
        else:
            print("[build_ibl_nodes] check: 바이트 일치 ✓")
        # 폰 매니페스트 정합 (드리프트 방지)
        manifest_ok = True
        if manifest_text is not None:
            on_disk = manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else None
            manifest_ok = on_disk == manifest_text
            if not manifest_ok:
                print(
                    f"[build_ibl_nodes] check: phone_manifest.json 불일치 — "
                    f"`python3 scripts/build_ibl_nodes.py` 로 재생성 필요",
                    file=sys.stderr,
                )
            else:
                print("[build_ibl_nodes] check: phone_manifest.json 일치 ✓")
        return 0 if (bytes_ok and manifest_ok and not validation_failed and not corpus_failed) else 1

    if validation_failed:
        print(
            "[build_ibl_nodes] 빌드는 수행했지만 검증 실패 — "
            "ibl_nodes.yaml 작성 보류. --validate 로 재확인하세요.",
            file=sys.stderr,
        )
        return 1

    target.write_text(merged, encoding="utf-8")
    print(f"[build_ibl_nodes] 작성: {target}")
    if manifest_text is not None:
        manifest_path.write_text(manifest_text, encoding="utf-8")
        print(f"[build_ibl_nodes] 작성: {manifest_path} "
              f"(폰 패키지 {len(PHONE_VERIFIED_PACKAGES)}, runnable {manifest_text.count(':')})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--check",
        action="store_true",
        help="작성하지 않고 현재 data/ibl_nodes.yaml과 일치 + 검증 통과 확인 (CI/pre-commit용)",
    )
    ap.add_argument(
        "--validate",
        action="store_true",
        help="삼각 검증만 수행 (yaml 작성·바이트 비교 없음)",
    )
    args = ap.parse_args(argv)
    return build(check=args.check, validate_only=args.validate)


if __name__ == "__main__":
    raise SystemExit(main())
