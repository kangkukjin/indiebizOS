"""Public edition 2 boundary. Kept separate from the legacy execution path."""
from ibl_v2_ir import Fault, projection
from ibl_v2_parser import edition_of


def handle_request(request, project_path=".", agent_id=None, cancel_check=None):
    source = request.get("code") or request.get("pipeline") or ""
    try:
        if edition_of(source, request.get("edition")) != 2:
            if request.get("inputs") is not None:
                raise Fault("EDITION_ARGUMENT", "inputs는 판본 2에서만 사용할 수 있습니다.", kind="compile")
            return None
        incompatible = [k for k in ("files", "files_from") if request.get(k) is not None]
        if incompatible:
            raise Fault("EDITION_ARGUMENT", "판본 2는 명시 inputs를 사용합니다. 지원하지 않는 인자: " + ", ".join(incompatible), kind="compile")
        inputs = {} if request.get("inputs") is None else request["inputs"]
        if not isinstance(inputs, dict) or any(not isinstance(k, str) or not k.isidentifier() or k in {"it", "i", "error"} for k in inputs):
            raise Fault("INPUTS", "inputs는 예약 이름을 제외한 이름→값 Record입니다.", kind="compile")
        from ibl_v2_ir import pack
        pack(inputs)
        from ibl_v2_adapters import load_registry
        from ibl_v2_compile import compile_program
        from ibl_v2_runtime import Runtime
        from ibl_v2_store import definitions
        plan = compile_program(source, load_registry(project_path, agent_id), inputs, definitions())
        if request.get("check"):
            return plan.report()
        if plan.issues:
            return Runtime(plan, inputs).run()
        from ibl_run_journal import Journal, journal_root, identity
        with Journal(journal_root(project_path), identity(plan, inputs, project_path, agent_id), request.get("resume")) as journal:
            journal.announce(plan.fingerprint)
            from ibl_edition import source_context
            with source_context(2):
                result = Runtime(plan, inputs, cancel_check=cancel_check, journal=journal).run()
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
    return {"editions": [1, 2], "default_edition": 1, "model_authoring_edition": 2, "value_protocols": ["ibl-value/1"],
            "v2_resume": True, "resume_protocols": ["ibl-resume/1"], "v2_remote_script": True, "call_protocols": ["ibl-script-call/1"],
            "v2_budget": {"steps": 100000, "rows": 10000, "seconds": None, "depth": 64}}
