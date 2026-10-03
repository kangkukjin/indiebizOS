"""수리 사본에서 실행하는 명령의 OS 경계. 부모의 모델 통신과 분리한다."""
import os
import subprocess
import tempfile
from contextlib import nullcontext
from pathlib import Path

from coding_process import sandbox_command


def run(command, workspace, *, timeout=300, env=None, text=True, readonly=False, live_read=False, **kwargs):
    if live_read and not readonly:
        raise ValueError("운영 읽기 통로는 읽기 전용 활성 검사에서만 사용합니다")
    root = Path(workspace).resolve()
    with tempfile.TemporaryDirectory(prefix="repair-run-", dir="/tmp") as runtime:
        clean = {k: v for k, v in (env or os.environ).items()
                 if not any(word in k.upper() for word in ("TOKEN", "API_KEY", "SECRET", "PASSWORD"))
                 and not k.startswith(("INDIEBIZOS_", "GIT_"))}
        home = Path(runtime) / "home"
        home.mkdir()
        browsers = Path.home() / "Library/Caches/ms-playwright"
        if browsers.is_dir():
            clean.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
        clean.update(HOME=str(home), TMPDIR=runtime, TMP=runtime, TEMP=runtime,
                     INDIEBIZ_BASE_PATH=str(root), PYTHONDONTWRITEBYTECODE="1",
                     XDG_CACHE_HOME=str(Path(runtime) / "cache"))
        from repair_runtime import node_runtime
        node = node_runtime(root, clean)
        if node:
            clean["PATH"] = str(Path(node).parent) + os.pathsep + clean.get("PATH", os.defpath)
        # macOS는 중첩 sandbox_apply를 허용하지 않는다. Electron 자식도 아래의
        # 바깥 OS 경계를 상속하므로 그 안쪽 Chromium 샌드박스만 중복 적용하지 않는다.
        clean["ELECTRON_DISABLE_SANDBOX"] = "1"
        argv = sandbox_command(command, runtime if readonly else root, runtime, local_network=True)
        # stdout은 부모가 회수한다. 시간 초과/취소에는 자식 프로세스도 함께 종료한다.
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
