"""Public edition 2 boundary. Kept separate from the legacy execution path."""
from ibl_v2_ir import Fault, projection
from ibl_v2_parser import edition_of


from repair_execution_scope import scoped as repair_scoped


@repair_scoped
def handle_request(request, project_path=".", agent_id=None, cancel_check=None, *, input_evidence=None):
    from script_workspace import request_scope
    from ibl_run_journal import journal_root, recorded_file_scope
    resume = request.get('resume')
    stored_scope = (recorded_file_scope(journal_root(project_path), resume)
                    if isinstance(resume, dict) and 'run_id' in resume else None)
    with request_scope(project_path, agent_id, request.get('resume'), stored_scope):
        return _handle_request(request, project_path, agent_id, cancel_check,
                               input_evidence=input_evidence)


def _handle_request(request, project_path=".", agent_id=None, cancel_check=None, *, input_evidence=None):
    source = request.get("code") or request.get("pipeline") or ""
    try:
        if edition_of(source, request.get("edition")) != 2:
            if request.get('budget') is not None:
                raise Fault("EDITION_ARGUMENT", "budget은 판본 2에서만 사용할 수 있습니다.", kind="compile")
            if request.get("inputs") is not None:
                raise Fault("EDITION_ARGUMENT", "inputs는 판본 2에서만 사용할 수 있습니다.", kind="compile")
            if request.get("declared_inputs") is not None:
                raise Fault("EDITION_ARGUMENT", "declared_inputs는 판본 2에서만 사용할 수 있습니다.", kind="compile")
            return None
        incompatible = [k for k in ("files", "files_from") if request.get(k) is not None]
        if incompatible:
            raise Fault("EDITION_ARGUMENT", "판본 2는 명시 inputs를 사용합니다. 지원하지 않는 인자: " + ", ".join(incompatible), kind="compile")
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
        plan = compile_program(source, load_registry(project_path, agent_id), inputs, definitions(),
                               declared_inputs=declared)
        from ibl_run_journal import Journal, journal_root, identity, reusable_receipts, validate_resume
        if request.get("check"):
            if reuse:
                reusable_receipts(journal_root(project_path), reuse['run_id'])
            if request.get('resume') is not None:
                validate_resume(journal_root(project_path), request['resume'],
                                identity(plan, inputs, project_path, agent_id, input_evidence=input_evidence))
            from ibl_v2_analysis import compact_check
            checked = compact_check(plan)
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
            journal.announce(plan.fingerprint)
            from ibl_edition import source_context
            with source_context(2):
                result = Runtime(plan, inputs, cancel_check=cancel_check, journal=journal,
                                 budget=budget,
                                 reusable=reusable, reuse_run=reuse["run_id"] if reuse else None,
                                 input_evidence=input_evidence, value_protocols=protocols,
                                 reuse_models=reuse.get("models", True) if reuse else True).run()
        try:
            from ibl_v2_learning import record_functions
            record_functions(plan, result)
        except Exception:
            pass  # Usage accounting never retries an already executed program.
        return result
    except Fault as exc:
        from ibl_v2_analysis import syntax_report
        return projection(syntax_report(exc, source))
    except Exception as exc:
        # A compiler/infrastructure exception is never an affirmative check.
        return {"edition": 2, "ok": False, "success": False, "executed": False,
                "status": "failed", "error": f"판본 2 검사/실행 기반 오류: {type(exc).__name__}: {exc}"}


def capabilities():
    return {"editions": [1, 2], "default_edition": 1, "model_authoring_edition": 2, "value_protocols": ["ibl-value/1", "ibl-value/2"],
            "v2_resume": True, "resume_protocols": ["ibl-resume/1"], "v2_remote_script": True, "call_protocols": ["ibl-script-call/1"],
            "v2_budget": {"steps": 100000, "rows": 10000, "seconds": None, "depth": 64,
                          "request_max": {"steps": 1000000, "rows": 100000}}}
