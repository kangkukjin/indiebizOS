"""사본의 코드·시험 데이터는 분리하고 모델·인증·네트워크 능력은 이어 쓴다."""
import os
import subprocess
import tempfile
import uuid
from contextlib import nullcontext
from pathlib import Path

from coding_process import sandbox_command


def prepare(command, workspace, *, env=None, runtime=None, readonly=False):
    """셸·등록/임시/세션 스크립트가 공유하는 자식 실행 환경."""
    from runtime_utils import get_base_path
    root = Path(workspace).resolve()
    runtime = Path(runtime) if runtime else root / "data/system_ai_state/process_runtime" / uuid.uuid4().hex
    runtime.mkdir(parents=True, exist_ok=True)
    source = dict(os.environ if env is None else env)
    model_root = Path(source.get("INDIEBIZ_MODEL_CONFIG_ROOT") or get_base_path()).resolve()
    # 키를 사본 파일로 복제하지 않는다. 기존 .env를 읽어 자식 환경에만 전달한다.
    from dotenv import dotenv_values
    clean = {k: v for k, v in dotenv_values(model_root / ".env").items() if v is not None}
    clean.update(source)
    # Git 대상은 cwd가 정한다. 호스트의 Git 디렉터리 override는 넘기지 않는다.
    for key in list(clean):
        if key.startswith("GIT_"):
            clean.pop(key)
    clean.update(TMPDIR=str(runtime), TMP=str(runtime), TEMP=str(runtime),
                 INDIEBIZ_BASE_PATH=str(root), INDIEBIZ_MODEL_CONFIG_ROOT=str(model_root),
                 INDIEBIZ_REPAIR_CHILD="1", PYTHONDONTWRITEBYTECODE="1",
                 XDG_CACHE_HOME=str(runtime / "cache"), ELECTRON_DISABLE_SANDBOX="1")
    # 로그인 자료는 읽고 CLI가 쓰는 세션/캐시는 작업별 런타임에 둔다.
    codex = Path(source.get("CODEX_HOME") or Path.home() / ".codex")
    claude = Path(source.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    for origin, name, variable, credentials in (
            (codex, "codex", "CODEX_HOME", ("auth.json",)),
            (claude, "claude", "CLAUDE_CONFIG_DIR", (".credentials.json", "settings.json"))):
        local = runtime / name
        local.mkdir(exist_ok=True)
        for filename in credentials:
            auth = origin / filename
            link = local / filename
            if auth.is_file() and not link.exists():
                link.symlink_to(auth.resolve())
        clean[variable] = str(local)
    browsers = Path.home() / "Library/Caches/ms-playwright"
    if browsers.is_dir():
        clean.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    from repair_runtime import node_runtime
    node = node_runtime(root, clean)
    if node:
        clean["PATH"] = str(Path(node).parent) + os.pathsep + clean.get("PATH", os.defpath)
    argv = sandbox_command(command, runtime if readonly else root, runtime,
                           local_network=True, external_network=True)
    return argv, clean


def run(command, workspace, *, timeout=300, env=None, text=True, readonly=False, live_read=False, **kwargs):
    if live_read and not readonly:
        raise ValueError("운영 읽기 통로는 읽기 전용 활성 검사에서만 사용합니다")
    root = Path(workspace).resolve()
    with tempfile.TemporaryDirectory(prefix="repair-run-", dir="/tmp") as runtime:
        argv, clean = prepare(command, root, env=env, runtime=runtime, readonly=readonly)
        from script_process import run_process
        check = kwargs.pop("check", None)
        cwd = kwargs.pop("cwd", str(root))
        from repair_live_probe import live_probe
        with live_probe() if live_read else nullcontext() as url:
            if url:
                clean["INDIEBIZ_VERIFY_BASE_URL"] = url
            result = run_process(argv, b"", cwd=cwd, env=clean, timeout=timeout,
                                 check=check, terminate_descendants=True)
        if result["timed_out"]:
            raise subprocess.TimeoutExpired(command, timeout, result.get("stdout"), result.get("stderr"))
        return subprocess.CompletedProcess(command, result["exit_code"],
                                           result.get("stdout", ""), result.get("stderr", ""))
