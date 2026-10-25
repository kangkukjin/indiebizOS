"""Public boundary for the sole executable IBL edition."""
from ibl_v2_ir import Fault, projection


from repair_execution_scope import scoped as repair_scoped


@repair_scoped
def handle_request(request, project_path=".", agent_id=None, cancel_check=None, *, input_evidence=None):
    from script_workspace import request_scope
    from ibl_run_journal import journal_root, recorded_file_scope
    resume = request.get('resume')
    stored_scope = (recorded_file_scope(journal_root(project_path), resume)
                    if isinstance(resume, dict) and 'run_id' in resume else None)
    from thread_context import get_approval, set_approval
    previous = get_approval()
    try:
        if 'approval' in request:
            from approval_tokens import request_digest
            set_approval(request.get('approval'), request_digest(request.get('code'), request.get('inputs'), request.get('declared_inputs'), request.get('function_refs')))
        with request_scope(project_path, agent_id, request.get('resume'), stored_scope):
            return _handle_request(request, project_path, agent_id, cancel_check,
                                   input_evidence=input_evidence)
    finally:
        set_approval(*previous)


def _handle_request(request, project_path=".", agent_id=None, cancel_check=None, *, input_evidence=None):
    source = request.get("code") or request.get("pipeline") or ""
    try:
        fields = {'code', 'pipeline', 'edition', 'inputs', 'declared_inputs', 'check', 'resume',
                  'reuse', 'budget', 'value_protocols', 'function_refs', 'approval', 'origin'}
        unknown = set(request) - fields
        if unknown:
            raise Fault('REQUEST_FIELDS', '지원하지 않는 요청 필드: ' + ', '.join(sorted(unknown)), kind='compile')
        from ibl_edition import require_current
        try:
            require_current(source, request.get("edition"))
        except ValueError as exc:
            raise Fault(str(exc).split(':', 1)[0], str(exc), kind='compile') from exc
        if request.get('resume') is not None:
            from ibl_run_journal import Journal
            Journal('.', '', request['resume'])  # Validate the handle before loading tools.
        protocols = request.get('value_protocols')
        if protocols is not None and (not isinstance(protocols, list) or not protocols
                or any(p not in ('ibl-value/1', 'ibl-value/2') for p in protocols)):
            raise Fault('VALUE_PROTOCOL', 'value_protocols는 지원하는 값 프로토콜 목록입니다.', kind='protocol')
        inputs = {} if request.get("inputs") is None else request["inputs"]
        if not isinstance(inputs, dict) or any(not isinstance(k, str) or not k.isidentifier() or k in {"it", "i", "error"} for k in inputs):
            raise Fault("INPUTS", "inputs는 예약 이름을 제외한 이름→값 Record입니다.", kind="compile")
        from ibl_v2_ir import pack
        pack(inputs)
        # declared_inputs(표면 바인딩 2026-10-05): 템플릿이 참조하는 입력 이름 전부. inputs 에 없는 이름은
        # '미지정'으로 컴파일된다 — 인자 자리 생략·보간 "". 모델 저술 프로그램은 보내지 않는다(없으면 종전과 같다).
        declared = request.get("declared_inputs")
        if declared is not None and (not isinstance(declared, list) or any(
                not isinstance(k, str) or not k.isidentifier() or k in {"it", "i", "error"} for k in declared)):
            raise Fault("INPUTS", "declared_inputs는 예약 이름을 제외한 입력 이름 목록입니다.", kind="compile")
        reuse = request.get("reuse")
        if reuse is not None:
            if request.get("resume") is not None:
                raise Fault("REUSE_ARGUMENT", "resume과 reuse는 함께 쓸 수 없습니다. 같은 프로그램은 resume, 고친 프로그램은 reuse입니다.", kind="compile")
            if (not isinstance(reuse, dict) or "run_id" not in reuse or set(reuse) - {"run_id", "models"}
                    or ("models" in reuse and type(reuse["models"]) is not bool)):
                raise Fault("REUSE_ARGUMENT", "reuse에는 이전 run_id와 선택 models(Bool)를 지정하세요.", kind="compile")
        from ibl_v2_adapters import load_registry
        from ibl_v2_compile import compile_program
        from ibl_v2_runtime import Runtime, Budget
        budget = Budget.from_request(request.get("budget"))
        from ibl_v2_store import definitions
        from tool_batch import prepared_plan
        plan = prepared_plan(source, inputs, project_path, agent_id)
        from member_runtime import is_member
        from ibl_run_journal import recorded_function_refs, journal_root
        refs = request.get('function_refs')
        if request.get('resume'):
            recorded = recorded_function_refs(journal_root(project_path), request['resume'])
            if recorded is not None:
                if refs is not None and refs != recorded:
                    raise Fault('RESUME_CHANGED', '함수 참조가 원 실행과 다릅니다.', kind='protocol')
                refs = recorded
        if is_member() and refs:
            raise Fault('MEMBER_LIBRARY', '회원은 동봉한 함수 정의만 사용할 수 있습니다.', kind='permission')
        if plan is None or refs is not None:
            if is_member():
                plan = compile_program(source, load_registry(project_path, agent_id), inputs, definitions(),
                                       declared_inputs=declared)
            else:
                import function_store
                from function_library import reference_library
                pinned = reference_library(refs) if refs is not None else None
                view = pinned.pinned_view if pinned is not None else function_store.snapshot()
                with function_store.using(view):
                    plan = compile_program(source, load_registry(project_path, agent_id), inputs,
                                           pinned if pinned is not None else definitions(), declared_inputs=declared)
        from approval_tokens import request_digest
        from thread_context import get_approval, set_approval
        used_refs = plan.dependencies.get('function_refs') or None
        set_approval(get_approval()[0], request_digest(source, inputs, declared, used_refs))
        from ibl_run_journal import Journal, journal_root, identity, reusable_receipts, validate_resume
        if request.get("check"):
            if reuse:
                reusable_receipts(journal_root(project_path), reuse['run_id'])
            if request.get('resume') is not None:
                validate_resume(journal_root(project_path), request['resume'],
                                identity(plan, inputs, project_path, agent_id, input_evidence=input_evidence))
            from ibl_v2_analysis import compact_check
            checked = compact_check(plan)
            checked['function_refs'] = plan.dependencies.get('function_refs', [])
            checked['budget'] = {'steps': budget.steps, 'rows': budget.rows}
            from ibl_v2_analysis import project_context_warning
            context_warning = project_context_warning(plan, project_path)
            if context_warning:
                checked['warnings'] = list(checked.get('warnings') or []) + [context_warning]
            return checked
        if plan.issues:
            return Runtime(plan, inputs).run()
        root = journal_root(project_path)
        reusable = reusable_receipts(root, reuse["run_id"]) if reuse else None
        with Journal(root, identity(plan, inputs, project_path, agent_id, input_evidence=input_evidence), request.get("resume")) as journal:
            from script_workspace import current_scope
            journal.db.execute('CREATE TABLE IF NOT EXISTS file_workspace(scope TEXT)')
            if not request.get('resume'):
                journal.db.execute('INSERT INTO file_workspace VALUES(?)', (current_scope(),))
                journal.db.commit()
            journal.db.execute('CREATE TABLE IF NOT EXISTS function_snapshot(refs TEXT,access_scope TEXT)')
            if not journal.resuming:
                import json
                from ibl_run_journal import receipt_access_scope
                journal.db.execute('INSERT INTO function_snapshot VALUES(?,?)',
                                   (json.dumps(plan.dependencies.get('function_refs', [])), receipt_access_scope()))
                journal.db.commit()
            journal.announce(plan.fingerprint)
            from ibl_continuations import remember, finished
            remember(journal, request, project_path, agent_id, input_evidence)
            original_cancel = cancel_check
            cancelled = lambda: (journal.root / (journal.run_id + '.cancel')).is_file() or bool(original_cancel and original_cancel())
            result = Runtime(plan, inputs, cancel_check=cancelled, journal=journal,
                             budget=budget,
                             reusable=reusable, reuse_run=reuse["run_id"] if reuse else None,
                             input_evidence=input_evidence, value_protocols=protocols,
                             reuse_models=reuse.get("models", True) if reuse else True).run()
            finished(journal, result, project_path)
        try:
            from ibl_v2_learning import record_functions
            record_functions(plan, result)
        except Exception:
            pass  # Usage accounting never retries an already executed program.
        return result
    except (Fault, ValueError, OSError) as exc:
        if not isinstance(exc, Fault):
            exc = Fault('FUNCTION_LIBRARY', str(exc), kind='protocol')
        from ibl_v2_analysis import syntax_report
        return projection(syntax_report(exc, source))
    except Exception as exc:
        # A compiler/infrastructure exception is never an affirmative check.
        # 68회차: 응답엔 한 줄만 남고 로그엔 아무것도 없어 어느 구문이 죽였는지 이분 탐색해야 했다 — 스택을 남긴다.
        import logging
        logging.getLogger("ibl_v2_entry").exception("판본 2 검사/실행 기반 오류: %s: %s", type(exc).__name__, exc)
        return {"edition": 2, "ok": False, "success": False, "executed": False,
                "status": "failed", "error": f"판본 2 검사/실행 기반 오류: {type(exc).__name__}: {exc}"}


def capabilities():
    from ibl_v2_runtime import Budget
    return {"editions": [2], "default_edition": 2, "explicit_edition_required": True, "model_authoring_edition": 2, "value_protocols": ["ibl-value/1", "ibl-value/2"],
            "v2_resume": True, "resume_protocols": ["ibl-resume/1"], "v2_remote_script": True, "call_protocols": ["ibl-script-call/1"],
            "v2_budget": {"steps": 100000, "rows": 10000, "seconds": None, "depth": 64,
                          "request_max": dict(Budget.REQUEST_LIMITS)}}
