"""IBL entry points to the same owner-scoped document service as the UI.

inspect/edit stay in docx_edit_ops with their original protection and copy-only
contract. Session operations never bypass window ownership or revision checks.
"""
from functools import lru_cache


@lru_cache(maxsize=1)
def service():
    from document_workspace import DocumentWorkspace
    return DocumentWorkspace()


def _call(params, method, names):
    import principal
    if not principal.is_owner():
        raise PermissionError("문서 작업 공간은 소유자 전용입니다")
    args = params.get("args", {})
    if not isinstance(args, dict) or set(args) - set(names):
        raise ValueError("args에 허용되지 않은 문서 작업 인자가 있습니다")
    kwargs = dict(args)
    for name in names:
        if name in params:
            if name in kwargs:
                raise ValueError("같은 인자를 최상위와 args에 중복 지정할 수 없습니다")
            kwargs[name] = params[name]
    app = service()
    if method.__name__ in {"save", "export_copy"}:
        from pathlib import Path
        document = app._doc(kwargs.get("document_id"))
        target = Path(document["source_uri"])
        if method.__name__ == "export_copy":
            filename = kwargs.get("filename", "")
            if not filename or Path(filename).name != filename or "/" in filename or chr(92) in filename:
                raise ValueError("새 파일명만 지정하세요")
            target = target.parent / filename
        if callable(params.get("_code_path")) and params["_code_path"](str(target)):
            raise PermissionError("실행 코드·사전 변경은 문서 저장이 아니라 수리 격리 경로를 사용하세요")
        guard = params.get("_path_guard")
        if not callable(guard):
            raise PermissionError("파일 쓰기 범위 검증기가 필요합니다")
        error = guard(str(target), params.get("_project_path") or str(target.parent))
        if error:
            raise PermissionError(str(error))
    result = method(app, **kwargs)
    if isinstance(result, list):
        return {"success": True, "items": result}
    return {"success": True, **result, "items": result.get("items", [result])}


def _method(params, name, names):
    from document_workspace import DocumentWorkspace
    return _call(params, getattr(DocumentWorkspace, name), names)


SESSION = ("document_id", "session_id", "client_id", "epoch", "expected")


def op_open(p):
    from pathlib import Path
    from runtime_utils import expand_body_path
    args = p.get("args", {})
    if not isinstance(args, dict):
        raise ValueError("args는 객체여야 합니다")
    path = p.get("path", args.get("path"))
    if not isinstance(path, str) or not path:
        raise ValueError("open에는 path가 필요합니다")
    expanded = Path(expand_body_path(path))
    if not expanded.is_absolute():
        if not p.get("_project_path"):
            raise ValueError("상대 경로에는 프로젝트 경로가 필요합니다")
        expanded = Path(p["_project_path"]) / expanded
    p = dict(p)
    if "path" in p:
        p["path"] = str(expanded)
    else:
        p["args"] = {**args, "path": str(expanded)}
    return _method(p, "open", ("path", "encoding"))


def op_session(p):
    return _method(p, "acquire", ("document_id", "client_id"))


def op_draft(p):
    return _method(p, "draft", SESSION + ("operation_id", "text"))


def op_snapshot(p):
    return _method(p, "snapshot", SESSION)


def op_read(p):
    return _method(p, "read", ("document_id", "snapshot_id"))


def op_propose(p):
    return _method(p, "propose", ("document_id", "snapshot_id", "start", "end", "selected_sha256", "replacement"))


def op_apply(p):
    return _method(p, "apply", SESSION + ("operation_id", "proposal_id"))


def op_save(p):
    return _method(p, "save", SESSION + ("operation_id", "expected_revision"))


def op_export(p):
    return _method(p, "export_copy", SESSION + ("operation_id", "filename"))


def op_versions(p):
    return _method(p, "versions", ("document_id",))


def op_restore(p):
    return _method(p, "restore", SESSION + ("operation_id", "revision_id"))


def op_capabilities(p):
    return _method(p, "capabilities", ("document_id",))


def op_recover(p):
    return _method(p, "recover", ("document_id",))


def op_close(p):
    return _method(p, "close", SESSION)
