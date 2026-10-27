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


try:  # 제어 기반 사본은 common/ 패키지 없이 평면 사본(completion_contract.py)을 둔다(G6)
    from completion_contract import process_birth_time as _birth_time
except ImportError:
    from common.completion_contract import process_birth_time as _birth_time


def identity(pid):
    p = psutil.Process(pid)
    return {"pid": p.pid, "born": _birth_time(p)}


def alive(ident):
    if not ident:
        return False
    try:
        p = psutil.Process(ident["pid"])
        return _birth_time(p) == ident["born"] and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    # AccessDenied는 죽음이 아니다. 호출자에게 관측 실패를 알린다.


def tree(ident):
    if not alive(ident):
        return []
    try:
        p = psutil.Process(ident["pid"])
        if _birth_time(p) != ident["born"]:
            return []
        children = p.children(recursive=True)
    except psutil.NoSuchProcess:
        return []  # alive 확인과 자손 열람 사이의 정상 종료
    members = []
    for child in children:
        try:
            members.append({"pid": child.pid, "born": _birth_time(child)})
        except psutil.NoSuchProcess:
            continue  # 이미 끝난 자손은 UNKNOWN 실행이 아니다.
    return members + [ident]


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
        """워커를 봉인 세대(generation_dir)에서 띄운다. 세대가 없으면(옛 상태) 가변 checkout 에서."""
        gen_dir = state.get("generation_dir")
        root, python = self.code_root, sys.executable
        env = os.environ.copy()
        if gen_dir and Path(gen_dir).is_dir():
            import generation_store
            root = Path(gen_dir)
            python = generation_store.python_executable(root)
            cache = self.home / "pycache" / str(state.get("code_digest") or "unknown")
            env.update(INDIEBIZ_CODE_ROOT=str(root), INDIEBIZ_SOURCE_ROOT=str(self.code_root),
                       PYTHONPYCACHEPREFIX=str(cache))
            env.pop("PYTHONDONTWRITEBYTECODE", None)
        env.update(INDIEBIZ_BASE_PATH=str(self.base), INDIEBIZ_API_PORT=str(self.port),
                   INDIEBIZ_RUNTIME_GENERATION=state["generation"],
                   INDIEBIZ_RUNTIME_DIGEST=state["code_digest"],
                   INDIEBIZ_RUNTIME_CONTROL=state["control_token"],
                   INDIEBIZ_MANAGED_WORKER="1", PYTHONUNBUFFERED="1")
        logpath = self.base / "data/backend_runtime.log"
        with logpath.open("ab") as log:
            child = subprocess.Popen(
                [python, str(root / "backend/base/restart_child.py")],
                cwd=root / "backend", env=env, stdout=log, stderr=log,
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
        # 수행자는 제어자 자신의 기반(이 파일이 사는 트리)에서 뜨고, 나머지 코드는 현역 세대에서 읽는다.
        script = Path(__file__).resolve().parents[1] / "services/restart_helper.py"
        env = dict(os.environ, INDIEBIZ_BASE_PATH=str(self.base), INDIEBIZ_SOURCE_ROOT=str(self.code_root))
        gen_dir = state.get("generation_dir")
        if gen_dir and Path(gen_dir).is_dir():
            env["INDIEBIZ_CODE_ROOT"] = str(gen_dir)
        else:
            env.pop("INDIEBIZ_CODE_ROOT", None)
        with (self.base / "data/backend_runtime.log").open("ab") as log:
            child = subprocess.Popen([sys.executable, str(script), str(path)], env=env,
                                     stdout=log, stderr=log, start_new_session=not IS_WINDOWS)
        self.children[str(path)] = child
        return None, [identity(child.pid)]


_presence_cache = {}


def _state_cached(base):
    """state.json 을 mtime 기준으로 캐시해 읽는다(/health 같은 뜨거운 길에서 230KB 재파싱 방지)."""
    path = control_dir(base) / "state.json"
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return {}
    if _presence_cache.get("key") != (str(path), stamp):
        _presence_cache.update(key=(str(path), stamp), state=read_json(path, {}) or {})
    return _presence_cache["state"]


def controller_presence(base, state=None, now=None):
    """"워커는 살아 있으나 제어자가 없다"를 드러낸다 — 2026-10-26 제어자 pid 39960 무음 사망.

    판정은 pid+출생시각(`alive`)이다. 죽은 pid 를 그대로 보여 주던 `api.py status` 와 제어자를
    모르던 `/health` 가 같은 한 벌을 쓴다. 관측 실패(AccessDenied)는 죽음이 아니라 unknown 이다.
      verdict: controller_alive | controller_missing | stopped | no_state | unknown
      revive : 제어자를 다시 띄워야 하는가(STOPPED·의도적 종료 표식은 제외).
    """
    state = _state_cached(base) if state is None else state
    now = time.time() if now is None else now
    out = {"phase": state.get("phase"), "generation": state.get("generation"),
           "controller": state.get("controller"), "worker": state.get("worker"),
           "controller_alive": None, "worker_alive": None,
           "state_age_s": None, "verdict": "no_state", "revive": False}
    if not state.get("phase"):
        return out
    if state.get("updated_at"):
        out["state_age_s"] = round(max(0.0, now - float(state["updated_at"])), 1)
    for key in ("controller", "worker"):
        try:
            out[key + "_alive"] = alive(state.get(key))
        except Exception as exc:  # AccessDenied 등 — 관측 실패
            out[key + "_alive"] = None
            out.setdefault("errors", []).append(f"{key}: {type(exc).__name__}: {exc}")
    intentional = (Path(base) / "data/.intentional_shutdown").exists()
    if out["controller_alive"] is None:
        out["verdict"] = "unknown"
    elif out["controller_alive"]:
        out["verdict"] = "controller_alive"
    elif state.get("phase") == "STOPPED" or intentional:
        out["verdict"] = "stopped"
    else:
        out["verdict"] = "controller_missing"
        out["revive"] = True
    return out


_daemon_cache = {}


def adopted_daemons(base):
    """lifecycle_policy.yaml 의 adopted_daemons 선언. 읽지 못하면 빈 목록 = 아무도 입양하지 않는다."""
    path = Path(base) / "data" / "lifecycle_policy.yaml"
    try:
        stamp = path.stat().st_mtime_ns
        if _daemon_cache.get("key") != (str(path), stamp):
            import yaml
            with path.open(encoding="utf-8") as f:
                rows = (yaml.safe_load(f) or {}).get("adopted_daemons") or []
            rules = [(str(r["name"]), [str(a) for a in r["argv"]]) for r in rows
                     if isinstance(r, dict) and r.get("name") and r.get("argv")]
            _daemon_cache.update(key=(str(path), stamp), rules=rules)
        return _daemon_cache["rules"]
    except Exception:
        return []


def _is_adopted(ident, rules):
    """선언된 실행 파일 이름 + 연속 인자열과 일치할 때만. 관측 실패는 입양이 아니다."""
    if not rules:
        return False
    try:
        p = psutil.Process(ident["pid"])
        if _birth_time(p) != ident["born"]:
            return False
        argv = p.cmdline()
    except psutil.Error:
        return False
    if not argv:
        return False
    name, rest = Path(argv[0]).name, argv[1:]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return any(name == want and any(rest[i:i + len(seq)] == seq for i in range(len(rest) - len(seq) + 1))
               for want, seq in rules)


def _tool_descendants(ident, rules, adopted):
    """도구의 일을 하는 자손만 모은다. 입양 데몬과 그 아래는 데몬의 것이다."""
    try:
        p = psutil.Process(ident["pid"])
        if _birth_time(p) != ident["born"]:
            return []
        stack = p.children()
    except psutil.NoSuchProcess:
        return []
    found = []
    while stack:
        child = stack.pop()
        try:
            cid = {"pid": child.pid, "born": _birth_time(child)}
            if _is_adopted(cid, rules):
                adopted[(cid["pid"], cid["born"])] = cid
                continue
            found.append(cid)
            stack.extend(child.children())
        except psutil.NoSuchProcess:
            continue  # 이미 끝난 자손은 UNKNOWN 실행이 아니다.
    return found


TOOL_MARK = "INDIEBIZ_TOOL_PROCESS"


def marked_env(env, mark):
    """도구 프로세스 환경에 표식을 심는다. 자손은 부모가 죽어 떨어져 나가도 이를 물려받는다."""
    import os
    return dict(os.environ if env is None else env, **{TOOL_MARK: mark})


def _marked_strays(mark, since, rules, adopted, skip):
    """표식을 물려받은 살아 있는 프로세스. 부모가 관측 주기 안에 끝나 트리에서 사라진 자손을 찾는다.

    환경을 지웠거나 읽을 수 없는(다른 사용자) 프로세스는 찾지 못한다 — 그 한계는 남는다.
    """
    found = []
    for proc in psutil.process_iter():
        try:
            cid = {"pid": proc.pid, "born": _birth_time(proc)}
            key = (cid["pid"], cid["born"])
            if key in skip or key in adopted or cid["born"] < since:
                continue
            if proc.status() == psutil.STATUS_ZOMBIE or proc.environ().get(TOOL_MARK) != mark:
                continue
            if _is_adopted(cid, rules):
                adopted[key] = cid
                continue
            # 입양 데몬 아래는 데몬의 것이다(표식은 물려받았어도).
            if any(_is_adopted({"pid": a.pid, "born": _birth_time(a)}, rules) for a in proc.parents()):
                continue
            found.append(cid)
        except psutil.Error:
            continue
    return found


def tool_process_receipt(proc, base, generation, mark=None):
    """워커 밖에도 자식의 출생 신원을 남긴다. 부모 사망 뒤 고아가 된 도구를 회수한다."""
    ident = identity(proc.pid)
    path = control_dir(base) / "processes" / f"{generation}-{proc.pid}.json"
    record = {"generation": generation, "members": [ident]}
    atomic_json(path, record)
    return path, record, adopted_daemons(base), mark


def wait_tool_process(proc, path, record, rules=(), mark=None):
    """표면/부모 도구가 끝나도 발견한 실제 자손이 살아 있으면 완료로 세지 않는다.

    예외는 데이터로 선언된 입양 데몬뿐이다(adb 서버처럼 도구가 부수적으로 띄우고 영영
    끝나지 않는 상주 프로세스). 영수증의 adopted 로 옮겨 적고 members(=drain 대기·정지
    대상)에서 뺀다. 선언에 없는 자손은 떨어져 나가도 그대로 도구의 일로 센다.

    트리 열람은 부모가 살아 있을 때만 자손을 본다. 부모가 관측 주기(0.2초) 안에 자식을 띄우고
    끝나면 자식은 트리에서 사라지므로, 구성원이 죽을 때마다 환경 표식(mark)으로 다시 찾는다.
    """
    root = (record["members"][0]["pid"], record["members"][0]["born"])
    known = {(p["pid"], p["born"]): p for p in record["members"]}
    adopted = {}
    dead = set()
    while True:
        died = False
        for key, ident in list(known.items()):
            # fork 직후 exec 전에 잡힌 자손이 나중에 데몬이 되므로 매번 다시 본다.
            if key != root and _is_adopted(ident, rules):
                adopted[key] = known.pop(key)
            elif alive(ident):
                for child in _tool_descendants(ident, rules, adopted):
                    known[(child["pid"], child["born"])] = child
            elif key not in dead:
                dead.add(key)
                died = True
        if died and mark:
            for child in _marked_strays(mark, root[1], rules, adopted, known):
                known[(child["pid"], child["born"])] = child
        members = list(known.values())
        if members != record["members"] or list(adopted.values()) != record.get("adopted", []):
            record["members"] = members
            if adopted:
                record["adopted"] = list(adopted.values())
            atomic_json(path, record)
        proc.poll()
        if not any(alive(p) for p in members):
            return
        time.sleep(0.2)
