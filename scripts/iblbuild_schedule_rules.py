"""예약 규칙 관문 (2026-09-29, 상상훈련 75회차 B75-3·B75-4 밭 이관).

같은 속이 두 번 났다 — 규칙 판정이 입구마다 따로 있었다.
  B54-8 → B75-3: 반복 규칙 정규화가 트리거 config 에만 붙어, schedule·manage_events 는 "영원히 안 도는
      예약"을 성공으로 저장했다. 1차 수리 뒤에도 cron 경로와 world_pulse 직접 쓰기가 한 곳을 비켜 갔다.
  F54-1 → B75-4: 판본 2 check 가 등록 런타임과 다른 답을 냈다(레코드 config 미관측·시각 없는 반복).

질문 둘. 둘 다 사람이 고른 사례 목록이 아니라 코드 구조로 판정한다.
  규칙 A(쓰기 한 곳): 캘린더 이벤트의 **반복 규칙 키**를 쓰는 코드는 `normalized_event` 를 부르는 함수뿐인가?
      관리자 모듈 밖에서는 `.config["events"]` 를 고치거나 `_save_config()` 를 부르는 코드가 없어야 한다
      (읽기는 자유 — 쓰기는 add_event·update_event·delete_event·toggle_task 입구로).
  규칙 B(판정 한 벌): 어휘가 선언한 `value_validator` 마다 판본 2 check(`ibl_value_checks._validator_problem`)와
      등록 런타임 입구가 **같은 공유 함수**를 부르는가? 공유 함수가 읽는 인자 ⊆ check 의 `VALIDATOR_READS`
      (빠지면 check 가 모르는 값을 없는 값으로 보고 거짓 빨강을 낸다).
"""
from __future__ import annotations

import ast
from pathlib import Path

import yaml

# 반복 규칙 키 — 발화 판정(`_should_run_task`)이 읽는 모양. 실행 상태 키(last_run·enabled·failure_notice)는 밖.
RULE_KEYS = {"repeat", "date", "time", "weekdays", "month", "day", "interval_hours", "execute_at"}
MANAGER_MODULES = {"backend/datastore/calendar_manager.py", "backend/services/calendar_actions.py",
                   "backend/services/calendar_html.py"}

# 규칙 B — value_validator → (공유 판정 함수, 그 함수를 불러야 하는 런타임 입구[(파일, 함수)]).
VALIDATOR_ENTRIES = {
    "trigger": ("resolve_trigger_config", [("backend/ibl/trigger_engine.py", "_create_trigger"),
                                           ("backend/ibl/trigger_engine.py", "_update_trigger_locked")]),
    "schedule": ("schedule_request", [("backend/cognition/system_ai_plans.py", "_execute_schedule")]),
    "calendar": ("calendar_request", [("backend/cognition/system_ai_tools.py", "_execute_manage_events")]),
}
SHARED_MODULE = "backend/datastore/calendar_rules.py"
CHECK_MODULE = "backend/ibl/ibl_value_checks.py"


def _is_events_expr(node) -> bool:
    """캘린더 관리자 저장소의 이벤트 목록 자체인가 — `X.config["events"]`·`X.config.get/setdefault("events", …)`."""
    if isinstance(node, ast.Subscript):
        return (isinstance(node.value, ast.Attribute) and node.value.attr == "config"
                and isinstance(node.slice, ast.Constant) and node.slice.value == "events")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("get", "setdefault"):
        return (isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "config"
                and bool(node.args) and isinstance(node.args[0], ast.Constant) and node.args[0].value == "events")
    return False


def _list_names(fn) -> set[str]:
    return {n.targets[0].id for n in ast.walk(fn)
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
            and _is_events_expr(n.value)}


def _mentions_events(node, lists=frozenset()) -> bool:
    return _is_events_expr(node) or (isinstance(node, ast.Name) and node.id in lists)


def _called_names(fn) -> set[str]:
    out = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            out.add(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else "")
    return out


def _functions(tree):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n


def _event_names(fn) -> set[str]:
    """이벤트 dict 에 묶인 이름 — `for evt in <이벤트 목록>` · `next(e for e in <이벤트 목록> …)`."""
    lists = _list_names(fn)
    names = set()
    for n in ast.walk(fn):
        if isinstance(n, (ast.For, ast.comprehension)) and _mentions_events(n.iter, lists) and isinstance(n.target, ast.Name):
            names.add(n.target.id)
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and n.value.func.id == "next" \
                and n.value.args and isinstance(n.value.args[0], ast.GeneratorExp) \
                and any(_mentions_events(g.iter, lists) for g in n.value.args[0].generators):
            names.add(n.targets[0].id)
    return names


def _rule_writes(fn, names) -> list[tuple[int, str]]:
    """이벤트 이름에 반복 규칙 키(또는 동적 키)를 쓰는 자리."""
    hits = []
    for n in ast.walk(fn):
        targets = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, ast.AugAssign) else []
        for t in targets:
            if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id in names:
                key = t.slice.value if isinstance(t.slice, ast.Constant) else None
                if key is None or key in RULE_KEYS:
                    hits.append((n.lineno, f"{t.value.id}[{key!r}]"))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "update" \
                and isinstance(n.func.value, ast.Name) and n.func.value.id in names:
            hits.append((n.lineno, f"{n.func.value.id}.update(…)"))
    return hits


def _list_mutations(fn) -> list[tuple[int, str]]:
    lists = _list_names(fn)
    hits = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr in ("append", "extend", "insert") and _mentions_events(n.func.value, lists):
            hits.append((n.lineno, ast.unparse(n.func)[:60]))
    return hits


def _scan_files(root: Path):
    for base in (root / "backend", root / "data/packages/installed/tools"):
        for path in sorted(base.rglob("*.py")):
            if path.name.startswith("test_") or "__pycache__" in path.parts:
                continue
            yield path


def validate_calendar_write_path(root: Path) -> list[str]:
    issues = []
    for path in _scan_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        manager = rel in MANAGER_MODULES
        for fn in _functions(tree):
            names = _event_names(fn)
            writes = _rule_writes(fn, names)
            appends = _list_mutations(fn)
            normalizes = "normalized_event" in _called_names(fn)
            if manager:
                for line, what in writes + appends:
                    if not normalizes:
                        issues.append(f"{rel}:{line} {fn.name} — 이벤트 반복 규칙을 `normalized_event` 없이 씁니다: {what}")
                continue
            for line, what in writes + appends:
                issues.append(f"{rel}:{line} {fn.name} — 캘린더 이벤트를 관리자 입구 밖에서 고칩니다: {what} "
                              "(add_event/update_event 로)")
            for n in ast.walk(fn):
                if isinstance(n, ast.Assign):
                    for t in n.targets:
                        if isinstance(t, ast.Subscript) and _mentions_events(t):
                            issues.append(f"{rel}:{n.lineno} {fn.name} — 캘린더 이벤트 목록을 통째로 바꿉니다")
                        elif isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id in names:
                            key = t.slice.value if isinstance(t.slice, ast.Constant) else None
                            if key is not None and key not in RULE_KEYS:   # 규칙 키·동적 키는 위 _rule_writes 가 셌다
                                issues.append(f"{rel}:{n.lineno} {fn.name} — 캘린더 이벤트를 관리자 입구 밖에서 고칩니다: "
                                              f"{t.value.id}[{key!r}] (update_event 로)")
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "_save_config" \
                        and not (isinstance(n.func.value, ast.Name) and n.func.value.id == "self"):
                    issues.append(f"{rel}:{n.lineno} {fn.name} — 캘린더 저장소를 관리자 밖에서 직접 저장합니다(_save_config)")
    return issues


def _module_functions(root: Path, rel: str) -> dict:
    path = root / rel
    if not path.exists():   # 관문 고장 = 무검사가 아니라 실패 (fail-closed) — 호출자가 빈 표를 실패로 센다
        return {}, ast.Module(body=[], type_ignores=[])
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {fn.name: fn for fn in _functions(tree)}, tree


def _read_keys(fn, tree) -> set[str]:
    """공유 함수가 인자 dict 에서 읽는 키 — `.get("k")`·`x["k"]`·`x[k] for k in <모듈 상수 튜플>`."""
    params = {a.arg for a in fn.args.args[:1]}
    for n in ast.walk(fn):   # p = dict(params) 같은 사본
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and n.value.func.id == "dict" \
                and n.value.args and isinstance(n.value.args[0], ast.Name) and n.value.args[0].id in params:
            params.add(n.targets[0].id)
    consts = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                and isinstance(n.value, ast.Tuple) and all(isinstance(e, ast.Constant) for e in n.value.elts):
            consts[n.targets[0].id] = {e.value for e in n.value.elts}
    keys = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get" \
                and isinstance(n.func.value, ast.Name) and n.func.value.id in params \
                and n.args and isinstance(n.args[0], ast.Constant):
            keys.add(n.args[0].value)
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id in params \
                and isinstance(n.slice, ast.Constant):
            keys.add(n.slice.value)
        if isinstance(n, (ast.DictComp, ast.ListComp, ast.GeneratorExp)):
            for gen in n.generators:
                if isinstance(gen.iter, ast.Name) and gen.iter.id in consts \
                        and any(isinstance(x, ast.Name) and x.id in params for x in ast.walk(n)):
                    keys |= consts[gen.iter.id]
    return {k for k in keys if isinstance(k, str)}


def _declared_validators(data: dict) -> set[str]:
    out = set()

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("value_validator"), str):
                out.add(x["value_validator"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(data)
    return out


def validate_validator_parity(data: dict, root: Path) -> list[str]:
    issues = []
    declared = _declared_validators(data)
    check_fns, check_tree = _module_functions(root, CHECK_MODULE)
    reads = {}
    for n in check_tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "VALIDATOR_READS" for t in n.targets):
            reads = ast.literal_eval(n.value)
    if not reads:
        return [f"{CHECK_MODULE}: VALIDATOR_READS 표가 없습니다 — check 가 어떤 인자로 판정하는지 알 수 없습니다"]
    for name in sorted(declared - VALIDATOR_ENTRIES.keys()):
        issues.append(f"어휘가 value_validator '{name}' 를 선언했지만 관문 표(VALIDATOR_ENTRIES)에 공유 판정 함수가 없습니다")
    for name in sorted(declared - reads.keys()):
        issues.append(f"어휘가 value_validator '{name}' 를 선언했지만 check 의 VALIDATOR_READS 에 없습니다")
    checker = check_fns.get("_validator_problem")
    check_calls = _called_names(checker) if checker else set()
    shared_fns, shared_tree = _module_functions(root, SHARED_MODULE)
    for name, (shared, entries) in sorted(VALIDATOR_ENTRIES.items()):
        if name not in declared:
            continue
        if shared not in check_calls:
            issues.append(f"check({CHECK_MODULE}._validator_problem)가 '{name}' 판정에 공유 함수 {shared} 를 부르지 않습니다")
        for rel, fn_name in entries:
            fns, _ = _module_functions(root, rel)
            fn = fns.get(fn_name)
            if fn is None:
                issues.append(f"{rel}: 런타임 입구 {fn_name} 가 없습니다(관문 표 갱신 필요)")
            elif shared not in _called_names(fn):
                issues.append(f"{rel}:{fn.lineno} {fn_name} — 등록 런타임이 check 와 같은 {shared} 를 부르지 않습니다")
        if shared in shared_fns:
            missing = _read_keys(shared_fns[shared], shared_tree) - set(reads.get(name, ()))
            if missing:
                issues.append(f"{SHARED_MODULE}.{shared} 가 읽는 인자 {sorted(missing)} 가 check 의 "
                              f"VALIDATOR_READS['{name}'] 에 없습니다 — 변수로 준 값을 없는 값으로 보고 거짓 빨강을 냅니다")
    return issues


def validate_schedule_rules(data: dict, root: Path) -> list[str]:
    return validate_calendar_write_path(root) + validate_validator_parity(data, root)


if __name__ == "__main__":   # 단독 실행: python3 scripts/iblbuild_schedule_rules.py [root]
    import sys
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    data = yaml.safe_load((root / "data/ibl_nodes.yaml").read_text(encoding="utf-8"))
    found = validate_schedule_rules(data, root)
    for issue in found:
        print("✗", issue)
    print(f"{len(found)}건")
    sys.exit(1 if found else 0)
