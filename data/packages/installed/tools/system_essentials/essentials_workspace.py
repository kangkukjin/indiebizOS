"""`[self:workspace]` — 범용 작업 공간 어휘의 얇은 입구 (2026-10-05).

op 는 의도 고도 11개(open/snapshot/read/propose/apply/save/export/versions/restore/close/capabilities).
세션 배관(session_id·epoch·expected·operation_id)은 backend/services/workspace_sessions.Workspace 가
해소한다. 이 파일은 인자 이름을 고르고, 쓰기 op 의 경로 관문(RED·범위)만 지킨다.
옛 `self:document` 세션 op 14개와 `self:sheet` 세션 op 11개를 흡수했다(어휘 순감).
"""
from pathlib import Path


def service():
    from workspace_sessions import Workspace
    return Workspace()


_ALLOWED = {
    "open": ("path", "encoding", "kind", "goal"),
    "snapshot": ("resource", "client", "wait"),
    "read": ("resource", "selector", "snapshot", "kind"),
    "propose": ("resource", "selector", "replacement", "values", "kind", "snapshot"),
    "apply": ("resource", "proposal", "client"),
    "save": ("resource", "client", "message", "verify"),
    "export": ("resource", "filename", "client"),
    "versions": ("resource",),
    "restore": ("resource", "revision", "client", "path"),
    "close": ("resource", "client"),
    "capabilities": ("resource",),
    "recover": ("resource",),
}


def _owner():
    import principal
    if not principal.is_owner():
        raise PermissionError("작업 공간은 소유자 전용입니다")


def _kwargs(p, op):
    args = p.get("args") if isinstance(p.get("args"), dict) else {}
    out = {}
    for name in _ALLOWED[op]:
        if name in p and name in args:
            raise ValueError(f"같은 인자({name})를 최상위와 args 에 중복 지정할 수 없습니다")
        if name in p:
            out[name] = p[name]
        elif name in args:
            out[name] = args[name]
    extra = set(args) - set(_ALLOWED[op])
    if extra:
        raise ValueError(f"{op} 가 받지 않는 인자: {sorted(extra)}")
    return out


def _guard_target(p, app, resource, filename=None):
    """저장·내보내기 대상 경로의 관문 — 실행 코드·사전 경로는 수리 격리 경로로, 범위 밖은 거절."""
    kind, _adapter, row = app.resolve(resource)
    if kind == "code":
        return
    target = Path(row["source_uri"])
    if filename:
        if not filename or Path(filename).name != filename or "/" in filename or chr(92) in filename:
            raise ValueError("새 파일명만 지정하세요")
        target = target.parent / filename
    if callable(p.get("_code_path")) and p["_code_path"](str(target)):
        raise PermissionError("실행 코드·사전 변경은 작업 공간 저장이 아니라 수리 격리 경로를 사용하세요")
    guard = p.get("_path_guard")
    if not callable(guard):
        raise PermissionError("파일 쓰기 범위 검증기가 필요합니다")
    error = guard(str(target), p.get("_project_path") or str(target.parent))
    if error:
        raise PermissionError(str(error))


def _wrap(result):
    if isinstance(result, list):
        return {"success": True, "items": result}
    items = result.get("items", [result]) if isinstance(result, dict) else [result]
    return {"success": True, **result, "items": items}


def _run(p, op):
    _owner()
    kwargs = _kwargs(p, op)
    app = service()
    if op == "open":
        from runtime_utils import expand_body_path
        path = kwargs.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("open 에는 path 가 필요합니다")
        expanded = Path(expand_body_path(path))
        if not expanded.is_absolute():
            if not p.get("_project_path"):
                raise ValueError("상대 경로에는 프로젝트 경로가 필요합니다")
            expanded = Path(p["_project_path"]) / expanded
        kwargs["path"] = str(expanded)
    if op == "read" and not kwargs.get("resource"):
        kwargs["root"] = p.get("_project_path")   # 자료 없는 읽기(코딩 프로젝트 목록)의 기본 폴더 기준
    if isinstance(p.get("selector"), str) and p.get("selector").strip().startswith("{"):
        import json
        kwargs["selector"] = json.loads(p.get("selector"))   # 판본 1 표면이 JSON 문자열로 보낸 selector
    if op in ("save", "export"):
        _guard_target(p, app, kwargs.get("resource"), kwargs.get("filename"))
    return _wrap(getattr(app, op)(**kwargs))


def op_open(p): return _run(p, "open")
def op_snapshot(p): return _run(p, "snapshot")
def op_read(p): return _run(p, "read")
def op_propose(p): return _run(p, "propose")
def op_apply(p): return _run(p, "apply")
def op_save(p): return _run(p, "save")
def op_export(p): return _run(p, "export")
def op_versions(p): return _run(p, "versions")
def op_restore(p): return _run(p, "restore")
def op_close(p): return _run(p, "close")
def op_capabilities(p): return _run(p, "capabilities")
def op_recover(p): return _run(p, "recover")


# ── ③ 접수증 어댑터(kind=sheet_op) — 시트 엔진 작업(apply/save 접수)의 투영. owner = 자료 id ──
_SHEET_TASK_STATES = {"queued": "queued", "creating": "running", "completed": "succeeded", "committed": "succeeded",
                      "failed": "failed", "interrupted": "interrupted"}


def sheet_task_status(ref: dict) -> dict:
    import task_receipts as T
    doc = ref.get("owner")
    if not doc:
        return T.view(ref, T.UNKNOWN, error="sheet_op 접수증에는 owner(자료 id)가 있어야 합니다")
    try:
        st = service().sheets().operation_status(doc, ref["task_id"])
    except KeyError:
        return T.view(ref, T.UNKNOWN, error=f"시트 작업 {ref['task_id']} 을(를) 찾지 못했습니다")
    state = _SHEET_TASK_STATES.get(st.get("status"), T.UNKNOWN)
    return T.view(ref, state, result=st.get("result"), error=st.get("reason") if state != T.SUCCEEDED else None, raw=st)


# ── ③ 접수증 어댑터(kind=coding_run) — 코딩 프로젝트의 실행(샌드박스 프로세스). owner = 프로젝트 자료 id ──
_RUN_STATES = {"running": "running", "passed": "succeeded", "failed": "failed", "cancelled": "cancelled", "interrupted": "interrupted"}


def _projects():
    return service().code().projects


def coding_run_status(ref: dict) -> dict:
    import task_receipts as T
    try:
        rec = _projects().run_status(ref["task_id"])
    except (ValueError, KeyError):
        return T.view(ref, T.UNKNOWN, error=f"코딩 실행 {ref.get('task_id')} 을(를) 찾지 못했습니다")
    state = _RUN_STATES.get(rec.get("state"), T.UNKNOWN)
    tail = _projects().output(rec["id"], max(0, _size(rec) - 4000)).get("text", "")
    result = {"exit_code": rec.get("exit_code"), "command": rec.get("command")} if state == T.SUCCEEDED else None
    error = f"종료 코드 {rec.get('exit_code')}" if state == T.FAILED else None
    return T.view(ref, state, progress={"output_tail": tail[-4000:], "started_at": rec.get("started_at")}, result=result, error=error)


def coding_run_status_cancel(ref: dict) -> dict:
    import task_receipts as T
    try:
        rec = _projects().stop(ref["task_id"])
    except (ValueError, KeyError):
        return T.view(ref, T.UNKNOWN, error=f"코딩 실행 {ref.get('task_id')} 을(를) 찾지 못했습니다")
    return T.view(ref, _RUN_STATES.get(rec.get("state"), T.UNKNOWN))


def _size(rec: dict) -> int:
    try:
        return Path(rec["output"]).stat().st_size
    except (OSError, KeyError, TypeError):
        return 0
