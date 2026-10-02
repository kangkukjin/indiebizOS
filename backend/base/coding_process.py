"""코딩 실행의 OS 쓰기 경계와 소유 프로세스. 지원 없는 몸에서는 실행을 거절한다."""
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path


def available():
    return sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file()


def sandbox_command(command, workspace, runtime):
    if not available():
        raise RuntimeError("이 몸의 코딩 쓰기 샌드박스는 미지원입니다(macOS 필요)")
    workspace, runtime = Path(workspace).resolve(), Path(runtime).resolve()
    quote = lambda p: json.dumps(str(p))
    policy = ["(version 1)", "(allow default)", "(deny file-write*)",
              f"(allow file-write* (subpath {quote(workspace)}) (subpath {quote(runtime)}))",
              f"(deny file-write* (literal {quote(workspace / '.git')}))",
              f"(deny file-write* (subpath {quote(workspace / '.git')}))",
              "(deny network*)"]
    return ["/usr/bin/sandbox-exec", "-p", "\n".join(policy), *command]


class CodingProcesses:
    def __init__(self, workspace, runtime, own_sandbox=False, on_spawn=None):
        """own_sandbox: 실행자가 자기 명령을 같은 OS 샌드박스로 가두는 네이티브 CLI.

        macOS 는 샌드박스 안에서 샌드박스를 다시 걸 수 없다(sandbox_apply 거절) — 바깥을
        씌우면 실행자의 모든 명령이 실패한다. 이때 쓰기 경계는 실행자 쪽 한 겹이 소유한다."""
        self.workspace = str(Path(workspace).resolve())
        self.runtime = str(Path(runtime).resolve())
        Path(self.runtime).mkdir(parents=True, exist_ok=True)
        self.own_sandbox = own_sandbox
        self.on_spawn = on_spawn
        self.processes = []
        self.lock = threading.RLock()
        self.cancelled = threading.Event()

    def spawn(self, command, env=None, **kwargs):
        with self.lock:
            if self.cancelled.is_set():
                raise RuntimeError("실행이 취소되었습니다")
            clean = {k: v for k, v in (env or os.environ).items()
                     if not any(word in k.upper() for word in ("TOKEN", "API_KEY", "SECRET", "PASSWORD"))
                     and not k.startswith("INDIEBIZOS_") and not k.startswith("GIT_")}
            clean.update({"TMPDIR": self.runtime, "PYTHONDONTWRITEBYTECODE": "1"})
            if not self.own_sandbox:
                command = sandbox_command(command, self.workspace, self.runtime)
            kwargs.pop("cwd", None)
            proc = subprocess.Popen(command, cwd=self.workspace, env=clean,
                                    start_new_session=True, **kwargs)
            self.processes.append(proc)
            if self.on_spawn:
                self.on_spawn(proc)
            return proc

    def terminate(self, proc):
        # 모든 정상 자손은 전용 세션의 process group을 상속한다.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=10)

    def close(self):
        with self.lock:
            self.cancelled.set()
            for proc in self.processes:
                self.terminate(proc)

    def cancel(self):
        self.close()
