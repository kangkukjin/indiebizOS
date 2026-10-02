"""코딩 실행 수명. 모델 루프는 기존 provider, 파일·명령은 과제 경계 안에서 실행한다."""
import contextvars
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from coding_git import CodingConflict, current_tree
from coding_process import CodingProcesses, available
from coding_store import fingerprint, identifier
from coding_workspace import CodingWorkspace
from logging_utils import mask_secret_data, mask_secrets

ACTIVE = {}
ACTIVE_LOCK = threading.RLock()


def tool(name, description, properties, required):
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": properties, "required": required}}


TEXT = {"type": "string"}
TOOLS = [
    tool("coding_read", "작업 공간 텍스트와 저장용 fingerprint를 읽습니다.", {"path": TEXT}, ["path"]),
    tool("coding_files", "작업 공간 파일 경로 목록을 읽습니다.", {}, []),
    tool("coding_edit", "읽은 fingerprint가 같은 파일만 저장합니다. 새 파일 expected=null.",
         {"path": TEXT, "content": TEXT, "expected": {"type": ["string", "null"]}},
         ["path", "content", "expected"]),
    tool("coding_command", "작업 공간 OS 샌드박스에서 셸 명령을 실행합니다. 정본·Git 메타 쓰기와 네트워크는 차단됩니다.",
         {"command": TEXT, "timeout": {"type": "integer", "minimum": 1, "maximum": 300},
          "verification": {"type": "boolean", "description": "실제 테스트·검사 명령일 때만 true"}}, ["command"]),
]


def choices():
    from model_resolver import resolve_compat_model
    from providers.codex import CodexProvider
    result = []
    for slot in ("system", "midtier", "lightweight"):
        config = resolve_compat_model(slot)
        if not config:
            continue
        provider = config["provider"]
        supported = provider in {"codex", "deepseek", "openai"}
        native = provider == "codex"
        ready = available() and supported and (bool(CodexProvider._find_binary()) if native else bool(config["api_key"]))
        result.append({"id": slot, "provider": provider, "model": config["model"], "ready": ready,
                       "kind": "native" if native else "api", "streaming": True,
                       "cancellation": ready, "path_restriction": ("실행자 자체 샌드박스" if native else "macOS sandbox") if ready else "unavailable",
                       "native_resume": False, "steering": "next_run",
                       "usage": "provider_observed", "reason": "" if ready else "미지원 실행자·몸 또는 인증 없음"})
    return result


class CodingRuns:
    def __init__(self, workspace=None):
        self.workspace = workspace or CodingWorkspace()
        self.store = self.workspace.store

    def start(self, task_id, message, executor, command_id, selection=None, *, background=True, command=None):
        if not command_id or not message.strip():
            raise ValueError("명령 ID와 지시가 필요합니다")
        run_id = "run_" + fingerprint([task_id, command_id])[:32]
        request = {"message": message, "executor": executor, "selection": selection, "command": command}
        with self.store.lock(task_id):
            previous = next((r for r in self.store.list("run") if r["id"] == run_id), None)
            if previous:
                if previous["request_hash"] != fingerprint(request):
                    raise CodingConflict("이미 사용한 명령 ID의 내용이 다릅니다")
                return previous
            task = self.store.get("task", task_id)
            self.workspace.idle(task)
            if not available():
                raise ValueError("쓰기 경계를 보장할 수 없는 몸입니다")
            selected = next((c for c in choices() if c["id"] == executor and c["ready"]), None)
            if command is None and selected is None:
                raise ValueError("실행자를 사용할 수 없습니다")
            frozen = None
            if selection:
                opened = self.workspace.read_file(task_id, selection["path"])
                if opened["fingerprint"] != selection["fingerprint"]:
                    raise CodingConflict("선택한 파일이 바뀌었습니다")
                start, end = selection.get("start_line", 1), selection.get("end_line", 200)
                if not 1 <= start <= end or end - start > 500:
                    raise ValueError("선택 범위는 최대 500줄입니다")
                frozen = {**selection, "text": "\n".join(opened["text"].splitlines()[start - 1:end])}
            row = {"id": run_id, "task_id": task_id, "request_hash": fingerprint(request),
                   "message": mask_secrets(message), "executor": selected, "selection": frozen,
                   "state": "running", "started_at": time.time(), "finished_at": None,
                   "owner_pid": os.getpid(), "children": [], "response": ""}
            self.store.save("run", row)
            task["active_run"] = run_id
            task["review_id"] = None
            self.store.save("task", task)
            controller = CodingProcesses(task["workspace"], self.store.root / "runtime" / run_id,
                                         own_sandbox=bool(selected and selected["kind"] == "native"),
                                         on_spawn=lambda p: self._spawned(row, p))
            with ACTIVE_LOCK:
                ACTIVE[run_id] = controller
        if background:
            ctx = contextvars.copy_context()
            thread = threading.Thread(target=lambda: ctx.run(self._execute, task, row, controller, message, command),
                                      daemon=True, name="coding-" + run_id)
            thread.start()
            return row
        self._execute(task, row, controller, message, command)
        return self.store.get("run", run_id)

    def _spawned(self, row, proc):
        import psutil
        try:
            created = psutil.Process(proc.pid).create_time()
        except psutil.NoSuchProcess:
            return  # 기록 전에 이미 끝난 짧은 명령 — 재기동 뒤 정리할 자식이 없다
        row["children"].append({"pid": proc.pid, "created": created})
        self.store.save("run", row)

    def cancel(self, task_id):
        task = self.store.get("task", task_id)
        run_id = task.get("active_run")
        if not run_id:
            return {"state": "idle"}
        with ACTIVE_LOCK:
            controller = ACTIVE.get(run_id)
        if controller:
            controller.cancel()
            return {"state": "cancelling", "run_id": run_id}
        # 워커 재기동 후에는 PID+출생 신원으로 남은 자식을 확인한다.
        import psutil
        import signal
        row = self.store.get("run", run_id)
        for child in row["children"]:
            try:
                proc = psutil.Process(child["pid"])
                if proc.create_time() == child["created"]:
                    os.killpg(child["pid"], signal.SIGKILL)
                    proc.wait(timeout=10)
            except psutil.NoSuchProcess:
                continue
        row["state"] = "interrupted"
        row["finished_at"] = time.time()
        self.store.save("run", row)
        task["active_run"] = None
        self.store.save("task", task)
        self.store.event(task_id, run_id, "run.interrupted", {"reason": "worker_recovery"})
        return row

    def command(self, task, row, controller, command, timeout=120, verification=False):
        if not isinstance(timeout, int) or not 1 <= timeout <= 300:
            raise ValueError("명령 시한은 1~300초입니다")
        before = current_tree(task["workspace"])
        started = time.time()
        self.store.event(task["id"], row["id"], "command.started", {"command": command, "cwd": task["workspace"]})
        proc = controller.spawn(["/bin/sh", "-c", command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            output = proc.communicate(timeout=timeout)[0]
            state = "cancelled" if controller.cancelled.is_set() else "passed" if proc.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            controller.terminate(proc)
            output = proc.communicate(timeout=10)[0]
            state = "interrupted"
        # 셸이 정상 종료해도 같은 그룹에 남은 백그라운드 명령을 제거한다.
        controller.terminate(proc)
        result = {"id": identifier("verification"), "task_id": task["id"], "run_id": row["id"],
                  "command": mask_secrets(command), "cwd": task["workspace"], "state": state,
                  "exit_code": proc.returncode, "started_at": started, "finished_at": time.time(),
                  "fingerprint": before, "output": mask_secrets(output.decode(errors="replace")),
                  "unchanged": before == current_tree(task["workspace"])}
        if verification:
            self.store.save("verification", result)
        self.store.event(task["id"], row["id"], "command.finished", result)
        return result

    def _execute(self, task, row, controller, message, command):
        from episode_logger import EpisodeLogger
        from providers import create_initialized_provider
        from providers.base import turn_token_scope
        from providers.coding_profile import configure
        from model_resolver import resolve_compat_model
        EpisodeLogger.start_episode("coding", message, "coding", task_id=row["id"])
        ep = EpisodeLogger.current()
        row["episode_id"] = ep.episode_id
        self.store.save("run", row)
        self.workspace.ledger.begin_turn(task["pursuit_id"], row["id"], message, ep.episode_id, execution=True)
        response = ""
        tool_lock = threading.RLock()
        try:
            self.store.event(task["id"], row["id"], "run.started", {"executor": row["executor"], "selection": row["selection"]})
            if command is not None:
                result = self.command(task, row, controller, command, verification=True)
                response = result["output"]
                row["state"] = "completed" if result["state"] == "passed" else result["state"]
                return
            config = resolve_compat_model(row["executor"]["id"])
            config["model"] = row["executor"]["model"]
            config["provider"] = row["executor"]["provider"]
            prompt = ("You are the coding executor for this isolated task. Use native tools or the supplied coding tools; "
                      "IBL is optional, not required. Modify only the workspace. Do not commit, apply to the canonical "
                      "repository, access credentials, launch detached processes, or call external local services. "
                      "Read repository instructions. Run relevant tests. Report evidence and unfinished work.\n"
                      "Goal: " + task["goal"])
            history = [{"role": "assistant", "content": r["response"]} for r in reversed(self.store.list("run"))
                       if r["task_id"] == task["id"] and r["id"] != row["id"] and r.get("response")][-6:]
            provider = create_initialized_provider(config["provider"], isolated_session=True,
                api_key=config["api_key"], model=config["model"], system_prompt=prompt,
                tools=TOOLS, project_path=task["workspace"], agent_id=row["id"], agent_name="coding")
            if not provider.is_ready:
                raise RuntimeError("모델 인증 또는 초기화 실패")
            configure(provider, task, controller)
            provider.coding_event_sink = lambda event: self.store.event(task["id"], row["id"], "provider.raw", event)

            def execute(name, args, *_unused, **_kwargs):
                with tool_lock:
                    if controller.cancelled.is_set():
                        raise RuntimeError("실행 취소됨")
                    if name == "coding_read":
                        result = self.workspace.read_file(task["id"], args["path"])
                    elif name == "coding_files":
                        result = self.workspace.files(task["id"])
                    elif name == "coding_edit":
                        result = self.workspace.save_file(task["id"], args["path"], args["content"],
                                                          args["expected"], run_id=row["id"])
                    elif name == "coding_command":
                        result = self.command(task, row, controller, args["command"], args.get("timeout", 120), args.get("verification", False))
                    else:
                        raise ValueError("허용되지 않은 코딩 도구")
                    return json.dumps(result, ensure_ascii=False)

            with turn_token_scope("coding", row["id"], hard_token_limit=200000, deadline_s=1800):
                for event in provider.process_message_stream(
                        message + ("\nSelected context:\n" + json.dumps(row["selection"], ensure_ascii=False) if row["selection"] else ""),
                        history=history, execute_tool=execute, cancel_check=controller.cancelled.is_set):
                    self.store.event(task["id"], row["id"], "provider." + event["type"], event)
                    if event["type"] == "final":
                        response = event.get("content", "")
                    if event["type"] == "error":
                        raise RuntimeError(event.get("content", "모델 실행 실패"))
            row["state"] = "cancelled" if controller.cancelled.is_set() else "completed"
        except Exception as exc:
            row["state"] = "cancelled" if controller.cancelled.is_set() else "failed"
            row["error"] = mask_secrets(str(exc))
        finally:
            controller.close()
            row["response"] = mask_secrets(response)
            row["finished_at"] = time.time()
            self.store.save("run", row)
            self.workspace.ledger.finish_turn(task["pursuit_id"], row["id"], row["response"],
                [{"coding_run_id": row["id"], "state": row["state"], "episode_id": row["episode_id"]}],
                interrupted=row["state"] != "completed")
            with self.store.lock(task["id"]):
                current = self.store.get("task", task["id"])
                current["active_run"] = None
                self.store.save("task", current)
            self.store.event(task["id"], row["id"], "run." + row["state"], {"error": row.get("error"), "response": row["response"]})
            with ACTIVE_LOCK:
                ACTIVE.pop(row["id"], None)
            EpisodeLogger.end_episode()
