"""`api.py start|serve` 런처 — 승인된 제어 기반(control_base)에서 제어자를 기동한다(G6).

런처 자체는 정본 checkout 의 코드다(사람이 앱을 실행하는 자리). 그래서 작게 둔다: 정본의 제어 파일을
봉인·검증해 기반을 고르고, 그 기반의 restart_controller 를 실행한다(Windows는 자식 종료까지 대기). 기반을 하나도 승인하지 못하면
정본에서 직접 돈다(초기 도입·기반 저장소 손상의 비상 경로). status/restart/shutdown/wait 같은 CLI
요청은 기반이 필요 없어 정본에서 처리한다.
"""
import os
import sys
import subprocess
from pathlib import Path


def launch(code_root, argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    code_root = Path(code_root).resolve()
    action = next((a for a in argv if not a.startswith("-")), "start")
    base = Path(os.environ.get("INDIEBIZ_BASE_PATH", code_root))
    if action not in {"start", "serve"} or "--takeover" in argv or os.environ.get("INDIEBIZ_CONTROL_NO_BASE"):
        from restart_controller import main
        return main(argv, code_root=code_root)
    import control_base
    from restart_protocol import control_dir, read_json
    state = read_json(control_dir(base) / "state.json", {}) or {}
    support = state.get("generation_dir") if state.get("generation_dir") and Path(state["generation_dir"]).is_dir() else code_root
    path, cid, note = control_base.select(code_root, base, support_root=support)
    if path is None:
        from restart_controller import log
        log(control_dir(base), f"승인된 제어 기반 없음({note}) — 정본에서 직접 기동")
        from restart_controller import main
        return main(argv, code_root=code_root)
    script = path / "backend/services/restart_controller.py"
    # 선택한 정상 기반을 실행하기 전에 손상됐을 수 있는 checkout 제어자를 import하지 않는다.
    try:
        print(f"제어 기반 {cid}({note}) 에서 제어자 기동: {script}", flush=True)
    except (OSError, ValueError):
        pass
    env = dict(os.environ, INDIEBIZ_BASE_PATH=str(base), INDIEBIZ_SOURCE_ROOT=str(code_root))
    args = [sys.executable, str(script), *argv]
    if "--code-root" not in argv:
        args += ["--code-root", str(code_root)]
    _exec_controller(sys.executable, args, env)


def _exec_controller(executable, args, env):
    if os.name == "nt":
        # Node/Electron의 파이프를 상속한 CRT exec는 접근 위반으로 종료될 수 있다.
        # CreateProcess로 원래 argv·환경·표준입출력을 넘기고 자식 종료를 기다린다.
        raise SystemExit(subprocess.call(args, executable=executable, env=env))
    os.execve(executable, args, env)
