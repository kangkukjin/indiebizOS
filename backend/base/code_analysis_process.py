"""Language server subprocess boundary; caches only, no network, owned lifetime."""
import subprocess
from pathlib import Path


def spawn_factory(runtime, *, confined=False):
    from coding_process import available, sandbox_command
    runtime = Path(runtime).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    if confined and not available():
        raise RuntimeError('이 플랫폼에는 작업 사본 분석의 OS 격리가 없습니다')

    def spawn(command, **kwargs):
        # Normal desktop analysis also forbids source writes when the OS boundary is available.
        if available():
            command = sandbox_command(command, runtime, runtime)
        return subprocess.Popen(command, start_new_session=True, **kwargs)
    return spawn
