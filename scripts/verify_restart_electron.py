#!/usr/bin/env python3
"""실제 Electron 창 닫기→제어자 종료→다음 기동. 임시 몸/포트만 사용한다."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
from test_restart_process import SERVER
from restart_protocol import control_dir, read_json
from restart_process import signal_owned


HARNESS = '''import { app, BrowserWindow } from 'electron';
import fs from 'fs';
import path from 'path';
import { startPythonBackend, fullSystemCleanup, getBasePath } from './frontend/electron/backend-process.js';
app.on('window-all-closed', () => {
  fullSystemCleanup();
  const state = JSON.parse(fs.readFileSync(path.join(getBasePath(), 'data/restart_control/state.json'), 'utf8'));
  if (state.phase !== 'STOPPED') { console.error('NOT STOPPED', state.phase); app.exit(2); return; }
  console.log('ELECTRON_SHUTDOWN_OK');
  app.quit();
});
app.whenReady().then(async () => {
  await startPythonBackend();
  const state = JSON.parse(fs.readFileSync(path.join(getBasePath(), 'data/restart_control/state.json'), 'utf8'));
  if (state.phase !== 'ACTIVE') { app.exit(3); return; }
  console.log('ELECTRON_START_OK', state.generation);
  const window = new BrowserWindow({width: 400, height: 160, show: false});
  await window.loadURL('data:text/html,<p>IndieBiz restart lifecycle test</p>');
  window.close();
}).catch(e => { console.error(e); fullSystemCleanup(); app.exit(1); });
'''


def main():
    electron = ROOT / "frontend/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
    with tempfile.TemporaryDirectory(prefix="indiebiz-electron-restart-") as folder:
        base = Path(folder)
        backend = base / "backend"
        (backend / "base").mkdir(parents=True)
        shutil.copy(ROOT / "backend/base/restart_child.py", backend / "base/restart_child.py")
        backend.joinpath("boot_paths.py").write_text(
            "import sys\n" + "\n".join(f"sys.path.insert(0, {str(ROOT / 'backend' / d)!r})"
                                      for d in ("", "base", "datastore", "services", "surface")))
        backend.joinpath("api.py").write_text('''import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import boot_paths
if os.environ.get('INDIEBIZ_MANAGED_WORKER') != '1':
 from restart_controller import main
 raise SystemExit(main(code_root=Path(__file__).parent.parent))
''' + SERVER)
        module = base / "frontend/electron"
        module.mkdir(parents=True)
        for name in ("backend-process.js", "bootstrap.js", "userdata_sync.js"):
            shutil.copy(ROOT / "frontend/electron" / name, module / name)
        (base / ".venv").symlink_to(ROOT / ".venv", target_is_directory=True)
        (base / "package.json").write_text(json.dumps({"type": "module", "main": "harness.js", "name": "restart-fixture"}))
        (base / "harness.js").write_text(HARNESS)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        runs = []
        env = dict(os.environ, INDIEBIZ_API_PORT=str(port), NODE_ENV="development")
        env.pop("ELECTRON_RUN_AS_NODE", None)
        try:
            for _ in range(2):
                started = time.monotonic()
                proc = subprocess.run([str(electron), str(base)], env=env, capture_output=True,
                                      text=True, timeout=90)
                if proc.returncode != 0:
                    raise AssertionError((proc.returncode, proc.stdout[-2500:], proc.stderr[-1000:]))
                assert "ELECTRON_SHUTDOWN_OK" in proc.stdout
                state = read_json(control_dir(base) / "state.json")
                assert state["phase"] == "STOPPED"
                runs.append({"generation": state["generation"], "phase": state["phase"],
                             "elapsed_s": round(time.monotonic()-started, 3)})
            assert runs[0]["generation"] != runs[1]["generation"]
            print(json.dumps({"electron_window_close_restart": runs}, indent=2))
        except subprocess.TimeoutExpired as exc:
            print((exc.stdout or b"").decode(errors="replace")[-3000:])
            print((exc.stderr or b"").decode(errors="replace")[-1000:])
            log = base / "data/backend_runtime.log"
            if log.exists():
                print(log.read_text(errors="replace")[-3000:])
            raise
        finally:
            for path in (control_dir(base) / "workers").glob("*.json"):
                signal_owned(read_json(path), force=True)
            state = read_json(control_dir(base) / "state.json", {})
            if state.get("controller"):
                signal_owned(state["controller"], force=True)


if __name__ == "__main__":
    main()
