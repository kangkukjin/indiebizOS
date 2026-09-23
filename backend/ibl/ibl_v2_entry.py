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
        incompatible = [k for k in ("resume", "files", "files_from") if request.get(k) is not None]
        if incompatible:
            raise Fault("EDITION_ARGUMENT", "판본 2는 명시 inputs를 사용합니다. 지원하지 않는 인자: " + ", ".join(incompatible), kind="compile")
        inputs = request.get("inputs") or {}
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
        return Runtime(plan, inputs, cancel_check=cancel_check).run()
    except Fault as exc:
        return {"edition": 2, "ok": False, "success": False, "executed": False,
                "status": "invalid" if exc.kind == "compile" else "failed",
                "error": str(exc), "diagnostic": projection(exc.view(source))}
    except Exception as exc:
        # A compiler/infrastructure exception is never an affirmative check.
        return {"edition": 2, "ok": False, "success": False, "executed": False,
                "status": "failed", "error": f"판본 2 검사/실행 기반 오류: {type(exc).__name__}: {exc}"}


def capabilities():
    return {"editions": [1, 2], "default_edition": 1, "value_protocols": ["ibl-value/1"],
            "v2_resume": False, "v2_remote_script": False,
            "v2_budget": {"steps": 100000, "rows": 10000, "seconds": 120, "depth": 64}}
