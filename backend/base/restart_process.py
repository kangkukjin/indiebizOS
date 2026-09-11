"""재기동 제어자의 OS/HTTP 어댑터. PID+출생시각으로만 신호 대상을 확인한다."""
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil
from restart_protocol import atomic_json, control_dir, read_json

IS_WINDOWS = os.name == "nt"


def identity(pid):
    p = psutil.Process(pid)
    return {"pid": p.pid, "born": p.create_time()}


def alive(ident):
    if not ident:
        return False
    try:
        p = psutil.Process(ident["pid"])
        return p.create_time() == ident["born"] and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    # AccessDenied는 죽음이 아니다. 호출자에게 관측 실패를 알린다.


def tree(ident):
    if not alive(ident):
        return []
    p = psutil.Process(ident["pid"])
    return [identity(c.pid) for c in p.children(recursive=True)] + [ident]


def signal_owned(ident, force=False):
    if alive(ident):
        p = psutil.Process(ident["pid"])
        p.kill() if force else p.terminate()


class ProcessAdapter:
    def __init__(self, base, code_root, port=8765):
        self.base, self.code_root, self.port = Path(base), Path(code_root), int(port)
        self.home = control_dir(base)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.children = {}  # 직접 spawn한 자식은 poll로 회수; 복귀 후에는 출생 신원으로 판정

    def status(self, state):
        try:
            return self.command(state, "status")
        except Exception as exc:
            return {"ownership": "unknown", "readiness": "unknown", "errors": [str(exc)],
                    "active_roots": None, "active_children": None, "pending_finalizers": None}

    def command(self, state, action):
        generation = state.get("generation")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/runtime/{action}",
            data=None if action == "status" else json.dumps({"generation": generation}).encode(),
            headers={"X-Runtime-Control": state["control_token"], "Content-Type": "application/json"})
        with self.opener.open(req, timeout=3) as response:
            return json.load(response)

    def alive(self, ident):
        child = self.children.get((ident or {}).get("pid"))
        if child is not None:
            child.poll()
        return alive(ident)

    def tree(self, ident):
        return tree(ident)

    def port_free(self):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((os.environ.get("INDIEBIZ_BIND_HOST", "127.0.0.1"), self.port))
                return True
            except OSError:
                return False

    def receipt(self, state):
        r = read_json(self.home / "workers" / (state["generation"] + ".json"))
        if r and r.get("nonce") == state["generation"] and self.alive(r):
            return r
        return None

    def spawn(self, state):
        env = os.environ.copy()
        env.update(INDIEBIZ_BASE_PATH=str(self.base), INDIEBIZ_API_PORT=str(self.port),
                   INDIEBIZ_RUNTIME_GENERATION=state["generation"],
                   INDIEBIZ_RUNTIME_DIGEST=state["code_digest"],
                   INDIEBIZ_RUNTIME_CONTROL=state["control_token"],
                   INDIEBIZ_MANAGED_WORKER="1", PYTHONUNBUFFERED="1")
        logpath = self.base / "data/backend_runtime.log"
        with logpath.open("ab") as log:
            child = subprocess.Popen(
                [sys.executable, str(self.code_root / "backend/base/restart_child.py")],
                cwd=self.code_root / "backend", env=env, stdout=log, stderr=log,
                start_new_session=not IS_WINDOWS)
        self.children[child.pid] = child

    def permit(self, state):
        atomic_json(self.home / "permits" / (state["generation"] + ".json"),
                    {"nonce": state["generation"]})

    def stop(self, state, force=False):
        for ident in state.get("stop_tree", []):
            signal_owned(ident, force=force)

    def stopped(self, state):
        return not any(self.alive(p) for p in state.get("stop_tree", []))

    def helper(self, action, state):
        """기록된 한 RED 수행자를 재채택한다. 응답 유실/사망 후 재적용하지 않는다."""
        rid = state["request"]["request_id"]
        suffix = "-rollback" if state.get("rollback_attempted") else ""
        path = self.home / "helpers" / (rid + "-" + action + suffix + ".json")
        child = self.children.get(str(path))
        if child is not None:
            child.poll()
        receipt = read_json(path.with_suffix(".process"))
        done = read_json(path.with_suffix(".done"))
        if receipt and self.alive(receipt):
            return None, self.tree(receipt)
        # 수행자가 먼저 죽어도 마지막으로 관측한 자식을 놓치지 않는다. 복원과
        # 새 세대 활성화 전에 이들이 실제로 끝나야 한다.
        remaining = [p for p in state.get("helper_tree", []) if self.alive(p)]
        if remaining:
            for member in remaining:
                signal_owned(member, force=True)
            return None, remaining
        if done:
            return done, []
        if receipt:
            return {"ok": False, "error": "RED 수행자 사망; 자동 재실행하지 않음"}, []
        if not path.exists():
            atomic_json(path, {"base": str(self.base), "action": action, "state": state})
        last = self.children.get(str(path))
        if last and last.poll() is None:
            return None, [identity(last.pid)]
        if last:
            return {"ok": False, "error": "RED 수행자 bootstrap 실패"}, []
        # 파일별 커널 잠금/receipt로 spawn-저장 사이 제어자 사망도 멱등이다.
        script = Path(__file__).resolve().parents[1] / "services/restart_helper.py"
        with (self.base / "data/backend_runtime.log").open("ab") as log:
            child = subprocess.Popen([sys.executable, str(script), str(path)],
                                     stdout=log, stderr=log, start_new_session=not IS_WINDOWS)
        self.children[str(path)] = child
        return None, [identity(child.pid)]


def tool_process_receipt(proc, base, generation):
    """워커 밖에도 자식의 출생 신원을 남긴다. 부모 사망 뒤 고아가 된 도구를 회수한다."""
    ident = identity(proc.pid)
    path = control_dir(base) / "processes" / f"{generation}-{proc.pid}.json"
    record = {"generation": generation, "members": [ident]}
    atomic_json(path, record)
    return path, record


def wait_tool_process(proc, path, record):
    """표면/부모 도구가 끝나도 발견한 실제 자손이 살아 있으면 완료로 세지 않는다."""
    known = {(p["pid"], p["born"]): p for p in record["members"]}
    while True:
        for ident in list(known.values()):
            if alive(ident):
                for child in tree(ident):
                    known[(child["pid"], child["born"])] = child
        members = list(known.values())
        if members != record["members"]:
            record["members"] = members
            atomic_json(path, record)
        proc.poll()
        if not any(alive(p) for p in members):
            return
        time.sleep(0.2)
