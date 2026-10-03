"""호스트 도구·IBL 호출의 사본 작업 문맥. 일반 능력의 권한은 바꾸지 않는다."""
from functools import wraps
from pathlib import Path
from threading import Lock
from repair_context import active, activation_only


def scoped(function):
    """직결/MCP/IBL 모두 같은 사본을 선택하고 호출 뒤 이전 문맥을 복원한다."""
    @wraps(function)
    def invoke(*args, **kwargs):
        from thread_context import get_repair_workspace, repair_workspace_scope
        if get_repair_workspace(resolve=False) or not active() or activation_only():
            return function(*args, **kwargs)
        from tool_loader import load_tool_handler
        handler = load_tool_handler("patch_op")
        staging, repo = handler._staging_mod(), str(handler._REPO_ROOT)
        lock, selected = Lock(), []

        def select(*, create=True):
            # 조회만으로 예약을 재개봉하거나 닫힌 사본을 다시 만들지 않는다.
            session = staging.read_session(repo, handler._staging_key())
            if not session or not (Path(repo) / session['worktree']).is_dir():
                if not create:
                    return None
                session = staging.ensure_session(repo, handler._staging_key())
            if not session:
                raise RuntimeError("수리 사본을 확보하지 못했습니다")
            return str(Path(repo) / session['worktree'])
        def workspace(*, create=True):
            with lock:
                if selected:
                    return selected[0]
                path = select(create=create)
                if path is not None:
                    selected.append(path)
                return path

        with repair_workspace_scope(workspace):
            return function(*args, **kwargs)
    return invoke
