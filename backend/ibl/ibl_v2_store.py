"""Edition-aware reusable definitions in the existing workflow store.

No legacy asset is upgraded in place. Definition source is pinned by compilation;
subsequent edits cannot change a running plan's function bodies.
"""
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
        self.references = {}

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


def definitions():
    from member_runtime import is_member
    if is_member():
        from ibl_member_library import definitions as member_definitions
        return Library(member_definitions())
    from function_library import definitions as current
    return current()


def installed_definitions():
    """Installed definitions are catalog entries, never a runtime file fallback."""
    import function_store
    return {r['name']: r['source'] for r in function_store.snapshot()['records'].values()
            if r.get('state') == 'active'
            and r.get('origin') == 'core' and not r.get('problem')}


def library():
    """definitions() 를 Library 로 — 시험·회원 경로가 평범한 사전을 돌려줘도 겹침 기록 자리가 있다."""
    known = definitions()
    return known if isinstance(known, Library) else Library(known)


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
            from function_library import register
            import function_store
            wf_id = params.get('workflow_id') or params.get('id') or name
            previous = get_workflow(wf_id)
            description = params.get('description', (previous or {}).get('description', ''))
            ref = register(name, source, description, edition=2,
                           function_id=(previous or {}).get('function_id'),
                           expected_revision=params.get('expected_revision', (previous or {}).get('revision')),
                           workflow_id=wf_id, request_id=params.get('request_id'), request_payload=params,
                           reason=params.get('reason', ''), state=params.get('state'))
            plan = compile_program(source, load_registry(project_path), definitions=definitions())
            return {'success': True, 'edition': 2, 'workflow_id': wf_id, 'name': name,
                    'function_ref': ref, 'check': plan.report()}
        if action_name == "run":
            wf_id = params.get("workflow_id") or _resolve_workflow_id(params.get("name") or params.get("id") or "")
            wf = get_workflow(wf_id)
            if not wf:
                raise Fault("FUNCTION_MISSING", "등록된 함수를 찾을 수 없습니다.", kind="compile")
            if wf.get('state') != 'active':
                raise Fault('FUNCTION_INACTIVE', '활성 함수만 실행할 수 있습니다.', kind='compile')
            name = definition_name(wf["code"])
            inputs = {} if params.get("params") is None else params["params"]
            if not isinstance(inputs, dict) or any(not isinstance(k, str) or not k.isidentifier() for k in inputs):
                raise Fault("INPUTS", "params는 명시 이름→값 Record입니다.", kind="compile")
            code = f'[fn:{name}]' + '{' + ','.join(f'{k}:${k}' for k in inputs) + '}'
            from thread_context import get_current_agent_id
            request = {"edition": 2, "code": code, "inputs": inputs}
            if params.get("function_refs") is not None:
                request["function_refs"] = params["function_refs"]
            return handle_request(request, project_path,
                                  agent_id=get_current_agent_id())
        raise Fault("WORKFLOW_OPERATION", "edition:2는 save/run에 지정합니다. 조회·삭제는 기존 관리 경로입니다.", kind="compile")
    except (Fault, ValueError) as exc:
        broken = getattr(exc, "broken_callers", None)
        if not isinstance(exc, Fault):
            exc = Fault("FUNCTION_MUTATION", str(exc), kind="compile")
        source = params.get("code") if action_name == "save" and isinstance(params.get("code"), str) else ""
        return {"success": False, "edition": 2, "error": str(exc), "diagnostic": exc.view(source),
                **({"broken_callers": broken} if broken else {})}


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
    from contextlib import nullcontext
    from member_runtime import is_member
    import function_store
    with nullcontext() if is_member() else function_store.using(function_store.snapshot()):
        return _describe(name, allowed_nodes)


def _describe(name, allowed_nodes=None):
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
    return {'function_ref': getattr(sources, "references", {}).get(name),
            'function_refs': ([sources.references[name]] if name in sources.references else []) +
                             plan.dependencies.get('function_refs', []),
            'callable_contract': plan.function_contracts[node.id],
            'status': report['status'], 'guards': report['guards'],
            'guards_total': report['guards_total'], 'guards_inner': report['guards_inner'],
            'plan_hash': plan.fingerprint,
            'source_hash': report['source_hash'], 'warnings': report['warnings']}
