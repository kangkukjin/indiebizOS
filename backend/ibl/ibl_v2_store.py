"""Edition-aware reusable definitions in the existing workflow store.

No legacy asset is upgraded in place. Definition source is pinned by compilation;
subsequent edits cannot change a running plan's function bodies.
"""
import yaml
from ibl_v2_ir import Fault
from ibl_v2_parser import parse, edition_of


def definitions():
    from workflow_store import _get_workflows_path
    from member_runtime import is_member
    if is_member():
        from ibl_member_library import definitions as member_definitions
        return member_definitions()
    out = {}
    from ibl_usage_db import IBLUsageDB
    from ibl_edition import source_edition
    db = IBLUsageDB()
    with db._get_connection() as conn:
        for row in conn.execute("SELECT alias, ibl_code FROM ibl_examples WHERE COALESCE(alias,'') != '' ORDER BY updated_at"):
            if source_edition(row["ibl_code"]) == 2:
                out[row["alias"]] = row["ibl_code"]
    for path in sorted(_get_workflows_path().glob("*.yaml")):
        if path.is_symlink():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue  # Legacy store's list view reports corrupt files.
        if isinstance(data, dict) and data.get("edition") == 2:
            name = data.get("name")
            if name in out:
                raise Fault("DUPLICATE_LIBRARY", f"같은 판본 2 함수 이름이 두 개입니다: {name}", kind="compile")
            out[name] = data.get("code", "")
    return out


def definition_name(source):
    edition_of(source, 2)
    statements = parse(source).data["statements"]
    if len(statements) != 1 or statements[0].kind != "def":
        raise Fault("LIBRARY_FORM", "저장본은 하나의 [def:이름](명시 인자){몸통}이어야 합니다.", kind="compile")
    return statements[0].data["name"]


def action(action_name, params, project_path):
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
            known = definitions()
            known[name] = source
            plan = compile_program(source, load_registry(project_path), definitions=known)
            if plan.issues:
                return {"success": False, "error": "저장 전 검사 거절", **plan.report()}
            wf_id = params.get("workflow_id") or params.get("id") or name
            previous = get_workflow(wf_id)
            if previous and previous.get("edition", 1) != 2:
                raise Fault("MIGRATION_ID", "판본 1 저장본은 새 id로 명시 등록하세요. 기존 호출은 보존합니다.", kind="compile")
            saved = save_workflow({"id": wf_id, "name": name, "edition": 2,
                                   "code": source, "description": params.get("description", ""),
                                   "params_required": [k for k, v in plan.root.data["statements"][0].data["params"].items() if v is None],
                                   "plan_hash": plan.fingerprint})
            return {"success": True, "edition": 2, "workflow_id": saved, "name": name, "check": plan.report()}
        if action_name == "run":
            wf_id = params.get("workflow_id") or _resolve_workflow_id(params.get("name") or params.get("id") or "")
            wf = get_workflow(wf_id)
            if not wf or wf.get("edition") != 2:
                raise Fault("EDITION_BOUNDARY", "판본 2 저장본이 아닙니다.", kind="compile")
            name = definition_name(wf["code"])
            inputs = params.get("params") or {}
            if not isinstance(inputs, dict) or any(not isinstance(k, str) or not k.isidentifier() for k in inputs):
                raise Fault("INPUTS", "params는 명시 이름→값 Record입니다.", kind="compile")
            code = f'[fn:{name}]' + '{' + ','.join(f'{k}:${k}' for k in inputs) + '}'
            return handle_request({"edition": 2, "code": code, "inputs": inputs}, project_path)
        raise Fault("WORKFLOW_OPERATION", "edition:2는 save/run에 지정합니다. 조회·삭제는 기존 관리 경로입니다.", kind="compile")
    except Fault as exc:
        return {"success": False, "edition": 2, "error": str(exc), "diagnostic": exc.view()}
