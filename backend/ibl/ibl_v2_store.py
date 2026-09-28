"""Edition-aware reusable definitions in the existing workflow store.

No legacy asset is upgraded in place. Definition source is pinned by compilation;
subsequent edits cannot change a running plan's function bodies.
"""
import yaml
from ibl_v2_ir import Fault
from ibl_v2_parser import parse, edition_of

class Library(dict):
    """이름→원문 해소 사전. 겹친 이름은 싣지 않고 `conflicts`에 출처를 남긴다(71회차 B71-1).

    이름 하나에 정의 하나는 저장(쓰기)에서 막는다. 손 복사 등으로 그래도 겹치면 그 이름을
    부르는 호출 자리만 DUPLICATE_LIBRARY 로 진단하고 무관한 프로그램은 계속 돈다 — 원장
    항목 하나가 언어 전체를 멈추지 않는다(list_workflows 의 깨진 항목 규율과 같다).
    `origins`는 이름마다 "관용구:별칭" 또는 "저장본:저장 ID"."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.origins, self.conflicts = {}, {}

    def add(self, name, source, origin):
        if name in self.conflicts:
            self.conflicts[name].append(origin)
        elif name in self:
            self.conflicts[name] = [self.origins[name], origin]
            del self[name]
        else:
            self[name] = source
            self.origins[name] = origin

    def owners(self, name):
        return list(self.conflicts.get(name) or ([self.origins[name]] if name in self.origins and name in self else []))

    def revised(self, name, source):
        """name 을 source 로 바꾼(None 이면 뺀) 사본 — 개정 전/후 대조용."""
        out = Library(self)
        out.origins, out.conflicts = dict(self.origins), {k: list(v) for k, v in self.conflicts.items()}
        if source is None:
            out.pop(name, None)
        else:
            out[name] = source
        return out


def definitions():
    from workflow_store import _get_workflows_path
    from member_runtime import is_member
    if is_member():
        from ibl_member_library import definitions as member_definitions
        return Library(member_definitions())
    out = Library()
    from ibl_usage_db import IBLUsageDB
    from ibl_edition import source_edition
    db = IBLUsageDB()
    with db._get_connection() as conn:
        for row in conn.execute("SELECT alias, ibl_code FROM ibl_examples WHERE COALESCE(alias,'') != '' ORDER BY updated_at, id"):
            if source_edition(row["ibl_code"]) == 2:
                # 같은 별칭의 행은 최신 행이 이긴다(색인의 갱신) — 겹침은 별칭과 저장본 사이의 일이다.
                out.pop(row["alias"], None)
                out.add(row["alias"], row["ibl_code"], f"관용구:{row['alias']}")
    for path in sorted(_get_workflows_path().glob("*.yaml")):
        if path.is_symlink():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue  # Legacy store's list view reports corrupt files.
        if isinstance(data, dict) and data.get("edition") == 2:
            out.add(data.get("name"), data.get("code", ""), f"저장본:{path.stem}")
    return out


def library():
    """definitions() 를 Library 로 — 시험·회원 경로가 평범한 사전을 돌려줘도 겹침 기록 자리가 있다."""
    known = definitions()
    return known if isinstance(known, Library) else Library(known)


def callers(known, name, registry=None):
    """Compiler-resolved external dependencies, including lexical shadowing.

    The parser/compiler owns calls; whitespace, comments, strings and local
    functions must not create a second, regex-based version of the language.
    """
    from ibl_v2_compile import compile_program
    if registry is None:
        from ibl_v2_adapters import load_registry
        registry = load_registry()
    found = []
    for caller, source in known.items():
        if caller == name:
            continue
        try:
            plan = compile_program(source, registry, definitions=known)
            if name in {entry['name'] for entry in plan.dependencies['source_map'][1:]}:
                found.append(caller)
        except Fault:
            continue
    return sorted(found)


def broken_callers(known, name, source, registry, *, after=None):
    """개정(source) 또는 삭제(source=None) 뒤에 **새로** 깨지는 호출자 (71회차 B71-2).

    전에는 검사를 통과하던 호출자가 후에 거절되면 그 개정·삭제의 탓이다. 이미 깨져 있던
    호출자는 이 쓰기를 막지 않는다(다른 수리를 볼모로 잡지 않는다)."""
    from ibl_v2_compile import compile_program
    after = known.revised(name, source) if after is None else after

    def issues(library, caller):
        try:
            return compile_program(known[caller], registry, definitions=library).issues
        except Fault as exc:
            return [{"code": exc.code, "message": str(exc)}]

    out = []
    # Validate the actual resulting namespace, not a hypothetical single-name
    # edit. Renames remove the old binding AND install the new one together.
    for caller in sorted(known):
        if caller not in after or after[caller] != known[caller]:
            continue
        if issues(known, caller):
            continue
        now = issues(after, caller)
        if now:
            out.append({"name": caller, "origin": known.origins.get(caller),
                        "code": now[0]["code"], "message": now[0]["message"]})
    return out


def _broken_message(name, clause, broken):
    rows = "; ".join(f"{b['name']}({b['origin']}) — {b['code']}: {b['message']}" for b in broken[:5])
    more = f" 외 {len(broken) - 5}개" if len(broken) > 5 else ""
    return (f"{clause} '{name}'을(를) 부르는 저장 정의가 깨집니다: {rows}{more}. "
            f"호출자를 두고 바꾸려면 새 이름으로 저장(예: [def:{name}2])한 뒤 호출자를 하나씩 "
            f"새 이름으로 다시 저장하고, 호출자가 없어진 다음 옛 정의를 지우세요.")


def _stored_name(wf):
    if not wf or wf.get("edition") != 2:
        return None
    try:
        return definition_name(wf.get("code", ""))
    except Fault:
        return None


def delete_blockers(workflow_id, project_path):
    """판본 2 저장본 삭제 전 확인 — 부르는 저장 정의가 있으면 거절 문구, 없으면 None."""
    from workflow_store import get_workflow
    from ibl_v2_adapters import load_registry
    name = _stored_name(get_workflow(workflow_id))
    if name is None:
        return None  # 판본 2가 아니거나 이름조차 없는 깨진 저장본은 아무도 부를 수 없다.
    known = library()
    if name in known.conflicts:
        return None  # 겹친 이름은 해소되지 않았다 — 지우는 것이 겹침을 푸는 길이다.
    broken = broken_callers(known, name, None, load_registry(project_path))
    return _broken_message(name, f"'{name}'을(를) 지우면", broken) if broken else None


def definition_name(source):
    edition_of(source, 2)
    statements = parse(source).data["statements"]
    if len(statements) != 1 or statements[0].kind != "def":
        names = [s.data["name"] for s in statements if s.kind == "def"]
        if len(names) > 1 and len(names) == len(statements):
            # 교재의 기본 작성법(지역 함수 분해)을 그대로 저장하려는 예측 가능한 다음 행동 (71회차 F71-2).
            helpers = [n for n in names if any(f"[fn:{n}]" in source[s.start:s.end]
                                                for s in statements if s.data["name"] != n)]
            first = ", ".join(helpers or names[:-1])
            raise Fault("LIBRARY_FORM", f"저장본은 정의 하나입니다 — 받은 정의 {len(names)}개: {', '.join(names)}. "
                        f"다른 정의가 부르는 보조 함수({first})부터 먼저 하나씩 저장하세요. 저장 함수끼리는 "
                        f"[fn:이름]으로 부를 수 있으므로 마지막 정의를 그대로 저장하면 됩니다.", kind="compile")
        raise Fault("LIBRARY_FORM", "저장본은 하나의 [def:이름](명시 인자){몸통}이어야 합니다.", kind="compile")
    return statements[0].data["name"]


def action(action_name, params, project_path):
    if action_name == "save":
        from workflow_store import workflow_transaction
        with workflow_transaction():
            return _action(action_name, params, project_path)
    return _action(action_name, params, project_path)


def _action(action_name, params, project_path):
    from workflow_store import save_workflow, get_workflow, _resolve_workflow_id
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_entry import handle_request
    try:
        if action_name == "save":
            source = params.get("code")
            if not isinstance(source, str):
                raise Fault("LIBRARY_FORM", "edition:2 저장에는 code가 필요합니다.", kind="compile")
            name = definition_name(source)
            known = library()
            owners = known.owners(name)
            wf_id = params.get("workflow_id") or params.get("id")
            if not wf_id:
                # 저장 ID를 안 주면 그 이름을 가진 저장본의 개정이다(run 이 이름으로 해소하는 것과 같은 방향).
                stored = [o.split(":", 1)[1] for o in owners if o.startswith("저장본:")]
                wf_id = stored[0] if len(owners) == 1 and stored else name
            others = [o for o in owners if o != f"저장본:{wf_id}"]
            if others:
                # 이름 하나에 정의 하나 — 읽을 때 전역으로 터지던 불변식을 쓰는 자리에서 막는다 (71회차 B71-1).
                stored = [o.split(":", 1)[1] for o in others if o.startswith("저장본:")]
                fix = (f"같은 함수를 고치려면 workflow_id:\"{stored[0]}\"로 저장하고, 새 판을 따로 두려면 "
                       if len(stored) == 1 and len(others) == 1 else "관용구·여러 저장본이 가진 이름은 덮어쓸 수 없으니 ")
                raise Fault("DUPLICATE_LIBRARY", f"함수 이름 '{name}'은(는) 이미 {', '.join(others)}에 있습니다. "
                            f"{fix}정의 이름을 바꾸세요(예: [def:{name}2]). 함수 이름은 저장 정의·관용구 전체에서 하나입니다.",
                            kind="compile")
            previous = get_workflow(wf_id)
            if previous and previous.get("edition", 1) != 2:
                raise Fault("MIGRATION_ID", "판본 1 저장본은 새 id로 명시 등록하세요. 기존 호출은 보존합니다.", kind="compile")
            registry = load_registry(project_path)
            renamed = _stored_name(previous)
            after = known.revised(renamed, None) if renamed and renamed != name else known
            after = after.revised(name, source)
            plan = compile_program(source, registry, definitions=after)
            if plan.issues:
                from ibl_v2_analysis import rejection_message
                return {**plan.report(), "success": False, "error": rejection_message("저장 전 검사 거절", plan.issues)}
            broken = broken_callers(known, name, source, registry, after=after)
            gone, clause = name, f"'{name}'을(를) 이렇게 개정하면"
            if renamed and renamed != name:
                # 같은 저장 ID에 다른 이름을 저장하면 옛 이름이 사라진다 — 삭제와 같은 확인.
                gone, clause = renamed, f"저장 ID '{wf_id}'에 다른 이름({name})을 저장해 '{renamed}'이(가) 사라지면"
            if broken:
                return {"success": False, "edition": 2, "error": _broken_message(gone, clause, broken),
                        "broken_callers": broken}
            # 설명을 주지 않은 재저장은 기존 설명을 지우지 않는다 — "안 줌"과 "비움"은 다르다 (71회차 F71-1).
            description = params["description"] if "description" in params else (previous or {}).get("description", "")
            saved = save_workflow({"id": wf_id, "name": name, "edition": 2,
                                   "code": source, "description": description,
                                   "params_required": [k for k, v in plan.root.data["statements"][0].data["params"].items() if v is None],
                                   "plan_hash": plan.fingerprint})
            return {"success": True, "edition": 2, "workflow_id": saved, "name": name, "check": plan.report()}
        if action_name == "run":
            wf_id = params.get("workflow_id") or _resolve_workflow_id(params.get("name") or params.get("id") or "")
            wf = get_workflow(wf_id)
            if not wf or wf.get("edition") != 2:
                raise Fault("EDITION_BOUNDARY", "판본 2 저장본이 아닙니다.", kind="compile")
            name = definition_name(wf["code"])
            inputs = {} if params.get("params") is None else params["params"]
            if not isinstance(inputs, dict) or any(not isinstance(k, str) or not k.isidentifier() for k in inputs):
                raise Fault("INPUTS", "params는 명시 이름→값 Record입니다.", kind="compile")
            code = f'[fn:{name}]' + '{' + ','.join(f'{k}:${k}' for k in inputs) + '}'
            from thread_context import get_current_agent_id
            return handle_request({"edition": 2, "code": code, "inputs": inputs}, project_path,
                                  agent_id=get_current_agent_id())
        raise Fault("WORKFLOW_OPERATION", "edition:2는 save/run에 지정합니다. 조회·삭제는 기존 관리 경로입니다.", kind="compile")
    except Fault as exc:
        source = params.get("code") if action_name == "save" and isinstance(params.get("code"), str) else ""
        return {"success": False, "edition": 2, "error": str(exc), "diagnostic": exc.view(source)}


def program_functions(code, allowed_nodes=None):
    """Contracts of the definitions written in a submitted program (70회차 B70-1).

    `describe` with code must answer the same names the executor resolves: a
    program's own definition shadows a stored one. The program is compiled,
    never run; unrelated issues elsewhere in it do not hide its signatures.
    """
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_parser import edition_of
    if not isinstance(code, str) or '[def:' not in code or edition_of(code, 2) != 2:
        return {}
    registry = load_registry()
    if allowed_nodes is not None:
        registry = {key: value for key, value in registry.items()
                    if key.split(':')[0] in allowed_nodes or key.startswith('fn:')}
    try:
        plan = compile_program(code, registry, definitions=definitions())
    except Exception:
        return {}  # 구문 오류는 실행 경로가 정직하게 보고한다.
    out = {}
    for contract in plan.function_contracts.values():
        if (contract.get('definition') or {}).get('source') == '<program>':
            out.setdefault(contract['name'], {'callable_contract': contract, 'source': 'program',
                                              'status': 'invalid' if plan.issues else 'valid'})
    return out


def describe(name, allowed_nodes=None):
    """Expose compiler-owned function signatures without publishing every body."""
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    registry = load_registry()
    if allowed_nodes is not None:
        registry = {key:value for key,value in registry.items()
                    if key.split(':')[0] in allowed_nodes or key.startswith('fn:')}
    sources = library()
    if name in sources.conflicts:
        return {'error': f"같은 이름의 저장 정의가 여럿이라 고를 수 없습니다: {', '.join(sources.conflicts[name])}"}
    if name not in sources:
        adapter = registry.get('fn:'+name)
        return {'callable_contract': adapter.contract} if adapter else {'error':'등록된 함수가 없습니다'}
    plan = compile_program(sources[name], registry, definitions=sources)
    report = plan.report()
    node = next((n for n in plan.root.data['statements'] if n.kind == 'def' and n.data['name'] == name), None)
    if node is None or plan.issues:
        return {'error':'함수 계약 검사 실패', 'issues':plan.issues}
    return {'callable_contract': plan.function_contracts[node.id],
            'status': report['status'], 'guards': report['guards'],
            'guards_total': report['guards_total'], 'guards_inner': report['guards_inner'],
            'plan_hash': plan.fingerprint,
            'source_hash': report['source_hash'], 'warnings': report['warnings']}
