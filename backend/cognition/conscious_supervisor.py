"""계획·조건부 관찰·최종 검수 한 역할. 시계/원장/작업 소유권은 코드가 책임진다."""
import json
import threading
import time
import uuid
import contextvars
from collections import deque
from pathlib import Path

from supervision_bus import current, register, unregister
from supervision_store import TurnStore, digest
from supervision_watch import JobWatch

DEFAULTS = {"enabled": True, "max_reviews": 2, "review_interval_s": 240,
            "stall_s": 180, "long_task_s": 480, "tick_s": 5,
            "call_timeout_s": 180, "max_tools_per_call": 10, "max_tools_total": 40,
            "final_tool_reserve": 12, "max_repairs": 2,
            "max_input_tokens": 300000, "max_output_tokens": 16000,
            "final_input_reserve": 80000, "final_output_reserve": 4000}


def open_supervisor(runner, message, history, cancel_check=None):
    from thread_context import get_current_task_id, get_current_agent_id
    from world_pulse import _load_config
    config = {**DEFAULTS, **_load_config().get("conscious_supervisor", {})}
    task = get_current_task_id()
    agent = get_current_agent_id() or getattr(runner.ai, "agent_id", None)
    # 내부 원샷 역할·신원 없는 호출은 사용자 턴 감독에 참여하지 않는다.
    if not config["enabled"] or not task or not agent:
        return None
    return Supervisor(runner, message, history, agent, task, config, cancel_check)


class Supervisor:
    def __init__(self, runner, message, history, agent, task, config=None, cancel_check=None, directory=None):
        from thread_context import snapshot
        from runtime_utils import get_base_path
        self.runner, self.message, self.history = runner, message, list(history or [])
        self.owner, self.task = agent, task
        self.turn_id = uuid.uuid4().hex
        self.supervisor_id = f"{agent}:conscious:{self.turn_id}"
        self.config = {**DEFAULTS, **(config or {})}
        self.cancel_check = cancel_check
        self.project_path = getattr(runner.ai, "project_path", ".")
        self.context = snapshot()
        from episode_logger import EpisodeLogger
        self.episode_id = getattr(EpisodeLogger.current(), "episode_id", None)
        self.store = TurnStore(directory or (get_base_path() / "data" / "spill" / "supervision" / self.turn_id))
        from supervision_delivery import DeliveryQueue
        self.delivery = DeliveryQueue(self.store.directory / "delivery", get_base_path() / "공유창고", self.log)
        self.history_ref = self.store.evidence(self.history)
        self.lock = threading.RLock()
        self.review_lock = threading.Lock()
        self.stopped = threading.Event()
        self.started = self.last_progress = self.last_review = time.monotonic()
        self.active = {}
        self.recent = deque(maxlen=24)
        self.jobs = {}
        self.framing = None
        self.enabled = False
        self.reviews = self.failures = self.repeats = self.tools_used = self.call_tools = 0
        self.last_signature = ""
        self.last_result = ""
        self.trigger = ""
        self.pending = None
        self.phase = "plan"
        self.call_deadline = 0
        self.finalizing = False
        self.done_request = None
        self.repair_kept = False
        self.exec_revision = 0
        self.completed_calls = 0
        self.unknown_calls = 0
        self.review_cursor = 0
        self.original_pursuit = None
        self.pursuit = None
        self.repair_granted = False
        self.usage = {"input": 0, "output": 0}
        self.call_metrics = None
        self.call_usage = {}
        self.state_cursor = 0
        self.job_states = {}
        self.executor_paused = True
        self.cli_executor = hasattr(getattr(runner.ai, "_provider", None), "disable_session_persistence")
        self.final_images = None
        self._native = {}
        self._execute = getattr(runner.ai, "_custom_execute_tool", None)
        if self._execute is None:
            from system_tools import execute_tool
            self._execute = execute_tool
        self.catalog = {t["name"]: t for t in getattr(runner.ai, "tools", []) if isinstance(t, dict) and t.get("name")}
        register(self, [agent, getattr(runner.ai, "agent_id", None), self.supervisor_id])
        self.log("turn.opened", role="harness")
        ctx = contextvars.copy_context()  # 토큰 원장·에피소드 객체도 같은 턴에 합산한다.
        self.thread = threading.Thread(target=lambda: ctx.run(self._watch), name=f"conscious-watch-{self.turn_id[:8]}", daemon=True)
        self.thread.start()

    def log(self, kind, role=None, **fields):
        from supervision_bus import identity
        role = role or ("consciousness" if identity()[0] == self.supervisor_id else "execution")
        row = self.store.log(kind, **{"role": role, "phase": self.phase, "time": time.time(), "task_id": self.task, **fields})
        # 큰 도구 본문은 한 파일, 사건 척추에는 손잡이만 보낸다.
        try:
            from episode_logger import record_trajectory_event
            record_trajectory_event("supervision." + kind, {**row, "store": str(self.store.directory)})
        except Exception:
            pass
        return row

    def close(self):
        self.stopped.set()
        unregister(self)
        self.log("turn.closed", role="harness", reviews=self.reviews, tools=self.tools_used)
        # 모델/원격 도구를 기다리느라 사용자 턴 종료를 붙잡지 않는다. 늦은 판정은 폐기된다.

    def cancelled(self):
        return self.stopped.is_set() or bool(self.cancel_check and self.cancel_check())

    def call_cancelled(self):
        return self.cancelled() or time.monotonic() >= self.call_deadline or not self.model_budget_available()

    def model_budget_available(self):
        for key in ("input", "output"):
            in_flight = getattr(self.call_metrics, f"total_{key}_tokens", 0) if self.call_metrics else 0
            in_flight = max(in_flight, self.call_usage.get(key, 0))
            reserve = 0 if self.finalizing else self.config[f"final_{key}_reserve"]
            if self.usage[key] + in_flight >= self.config[f"max_{key}_tokens"] - reserve:
                return False
        return True

    def plan(self, prompt, system_prompt, revision=None):
        from supervisor_runtime import invoke, ROLE_PROMPT
        with self.review_lock:
            if revision:
                if self.reviews >= self.config["max_reviews"]:
                    return ""
                self.reviews += 1
            self.enabled = True
            return invoke(self, prompt, planning_prompt=system_prompt + "\n\n" + ROLE_PROMPT.split("판정은 JSON 하나:")[0]
                          + "\n이번 계획 호출은 앞에서 지정한 계획 JSON 형식으로 답하라.",
                          phase="reframe" if revision else "plan")

    def configure(self, framing, repair=False):
        self.framing = framing
        self.enabled = bool(framing) or self.enabled
        self.phase = "execute"
        self.executor_paused = False
        self.context = __import__("thread_context").snapshot()
        from pursuit_bind import current as pursuit_current
        binding = pursuit_current()
        self.pursuit = binding
        self.repair_granted = repair
        if binding and binding.row:
            self.original_pursuit = {k: binding.row[k] for k in ("id", "version", "goal_criteria")}
        self.log("framing", role="consciousness", evidence=self.store.evidence(framing or {}))

    def reframe(self, payload):
        from reframe import TurnChannel, _revise, render_for_executor
        from thread_context import snapshot, restore
        previous = snapshot()
        try:
            restore(self.context)
            if not payload.get("broken_assumption") or not payload.get("evidence"):
                raise ValueError("broken_assumption과 evidence가 필요합니다")
            ch = TurnChannel(self.owner, self.runner, self.message, self.history, "",
                             self.framing or {}, self.repair_granted, self.owner)
            ch.pursuit = self.pursuit
            env = _revise(ch, "executor", payload["broken_assumption"], payload["evidence"],
                          payload.get("progress", ""), payload.get("kind", "other"))
            if env.get("revised"):
                self.framing = ch.current
            self.log("premise.challenged", role="execution", input=self.store.evidence(payload), result=self.store.evidence(env))
            return render_for_executor(env)
        except Exception as exc:
            return json.dumps({"revised": False, "reason": str(exc)}, ensure_ascii=False)
        finally:
            restore(previous)
            self.phase = "execute"

    def state(self, *, delta=False, offset=None, mark=True):
        now = time.monotonic()
        with self.lock:
            cursor = self.state_cursor if offset is None else offset
            events = [e for e in self.recent if e["seq"] > (cursor if delta else self.review_cursor)]
            state = {"original_goal": self.message, "framing": self.framing,
                    "conversation_evidence": {k: self.history_ref[k] for k in ("id", "chars")},
                    "phase": self.phase, "elapsed_s": round(now - self.started),
                    "active": [{**{k: x for k, x in v.items() if not k.startswith("_")},
                                "elapsed_s": round(now - v["started"])} for v in self.active.values()],
                    "events": events,
                    "earlier_events": "evidence id=events, offset=사건 seq로 이전 원문을 읽을 수 있습니다",
                    "jobs": list(self.job_states.values()),
                    "tools": list(self.catalog), "response": self.store.manifest() if self.store.version else None,
                    "pending_delivery": self.delivery.manifest(),
                    "pursuit_completion_request": self.done_request,
                    "original_pursuit": self.original_pursuit,
                    "tools_remaining": self.config["max_tools_total"] - self.tools_used, "usage": dict(self.usage),
                    "cursor": self.store.sequence,
                    "budget_remaining": {k: max(0, self.config[f"max_{k}_tokens"] - self.usage[k]
                                                   - self.call_usage.get(k, 0)) for k in ("input", "output")}}
            if mark:
                self.state_cursor = state["cursor"]
            if delta:
                for key in ("original_goal", "framing", "conversation_evidence", "tools", "original_pursuit"):
                    state.pop(key, None)  # 같은 모델 호출의 최초 snapshot에 이미 제공했다.
                state.update(since=cursor, changed=bool(events),
                             hint="최초 snapshot 이후 변경분. 과거 원문은 evidence id=events로 읽으세요")
            return state

    def progress(self, detail):
        if __import__("supervision_bus").identity()[0] == self.supervisor_id:
            return
        with self.lock:
            signature = digest(str(detail))
            if signature != getattr(self, "progress_signature", None):
                self.progress_signature = signature
                self.last_progress = time.monotonic()
                self.repeats = 0
                self.exec_revision += 1
                self.recent.append(self.log("progress", role="execution", detail=str(detail)[:800]))

    def _start(self, name, payload):
        key = uuid.uuid4().hex
        with self.lock:
            self.active[key] = {"name": name, "started": time.monotonic(), "input": self.store.evidence(payload), "_payload": payload}
            self.recent.append(self.log("tool.started", id=key, name=name, input=self.active[key]["input"]))
        return key

    def _finish(self, key, result, error=False):
        with self.lock:
            call = self.active.pop(key, {})
            self.completed_calls += 1
            from cognitive_trace import should_self_reflect, _classify_call, _ibl_safety_map, _ibl_op_safety_map
            trace = {"name": call.get("name", ""), "input": call.get("_payload", {}), "result": result, "is_error": error}
            kind, _ = _classify_call(trace, _ibl_safety_map(), _ibl_op_safety_map())
            self.unknown_calls += int(kind == "unknown")
            # 응답을 쓰기 전에 승격한다. 빠른 읽기 경로는 모델 호출 0회 그대로다.
            if should_self_reflect([trace], min_tool_calls=3)[0] or (self.unknown_calls and self.completed_calls >= 3):
                self.enabled = True
            ref = self.store.evidence(result)
            job_observation = _job_observation(result)
            result_signature = digest(json.dumps(job_observation, sort_keys=True, ensure_ascii=False)) if job_observation else ref["id"]
            self.recent.append(self.log("tool.finished", id=key, name=call.get("name"), evidence=ref,
                                        is_error=error, elapsed_s=round(time.monotonic() - call.get("started", time.monotonic()), 3)))
            sig = call.get("name", "") + call.get("input", {}).get("id", "")
            self.repeats = self.repeats + 1 if sig == self.last_signature and result_signature == self.last_result else 1
            self.last_signature, self.last_result = sig, result_signature
            self.failures = self.failures + 1 if error else 0
            if self.repeats == 1 and not error and not job_observation:
                self.last_progress = time.monotonic()
                self.exec_revision += 1  # 시작 예고·실패·같은 status 반복은 진척이 아니다.
                if self.trigger in {"repeated_failure", "unchanged_repeat", "tool_stalled", "long_task_checkpoint"}:
                    self.trigger = ""
            if self.failures >= 2 or self.repeats >= 3:
                self.trigger = "repeated_failure" if self.failures >= 2 else "unchanged_repeat"
            self._discover_jobs(result)

    def run_tool(self, name, payload, execute):
        from supervision_bus import identity
        if identity()[0] == self.supervisor_id:
            return json.dumps({"success": False, "not_executed": True,
                               "error": "의식의 직접 도구는 supervision execute 작업대를 통해 호출하세요"}, ensure_ascii=False)
        notice = self.boundary()
        if notice:
            # 아직 실행하지 않았다. 새 지시를 읽은 모델이 다시 선택한 호출만 실행한다.
            return json.dumps({"success": False, "not_executed": True, "supervisor_instruction": notice}, ensure_ascii=False)
        # 모델 관찰 잠금은 실행을 막지 않는다. 지시 전달과 실제 작업 등록만 원자적으로 한다.
        with self.lock:
            if self.pending:
                notice = self._take_pending()
                if notice:
                    return json.dumps({"success": False, "not_executed": True, "supervisor_instruction": notice}, ensure_ascii=False)
            key = self._start(name, payload)
        try:
            result = execute()
        except BaseException as exc:
            self._finish(key, {"error": str(exc)}, True)
            raise
        self._finish(key, result, _failed(result))
        return result

    def observe_native(self, event):
        name = event.get("name") or event.get("tool") or ""
        if name in {"mcp__indiebizos__execute_ibl", "mcp__indiebizos__supervision"} or name in self.catalog or name == "supervision":
            return  # API/MCP 브리지가 이미 실제 실행을 기록했다.
        if event.get("type") == "tool_start":
            self._native[event.get("id") or name] = self._start(name, event.get("input", {}))
        elif event.get("type") == "tool_result":
            key = self._native.pop(event.get("id") or name, None)
            if key:
                self._finish(key, event.get("result", event.get("content", "")), event.get("is_error", False))

    def boundary(self):
        if self.cancelled():
            return "이 실행은 종료 또는 중단됐습니다. 새 작업을 시작하지 마세요."
        if self.finalizing and self.phase == "repair":
            return None  # 최종 검수 잠금을 가진 하네스가 실행자에게 명시적으로 인계했다.
        # 관찰 호출은 watcher가 맡는다. 훅/API 스레드는 확정된 개입만 다음 행동 전에 전달한다.
        with self.lock:
            return self._take_pending()

    def _take_pending(self):
        notice, self.pending = self.pending, None
        if notice and notice.get("revision", self.exec_revision) != self.exec_revision:
            self.log("decision.stale", role="harness", reviewed_revision=notice["revision"], current_revision=self.exec_revision)
            return None
        if notice:
            self.log("instruction.delivered", role="harness", instruction=notice)
        return notice

    def _discover_jobs(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return
        if isinstance(value, list):
            for item in value:
                self._discover_jobs(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key in {"log", "log_path", "log_file"} and isinstance(item, str):
                    # 도구 결과가 가리킨 로컬 script_runs 로그만 감시. 임의 파일을 스캔하지 않는다.
                    from runtime_utils import get_base_path
                    path = Path(item).resolve()
                    if path.is_relative_to((get_base_path() / "data" / "script_runs").resolve()):
                        self.jobs.setdefault(str(path), JobWatch(path))
                elif isinstance(item, (dict, list)):
                    self._discover_jobs(item)

    def _watch(self):
        from thread_context import restore
        restore(self.context)
        while not self.stopped.wait(self.config["tick_s"]):
            try:
                self.tick()
            except Exception as exc:
                self.log("watch.error", role="harness", error=str(exc))

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        if self.finalizing or self.phase in {"plan", "reframe"} or self.cancelled():
            return
        with self.lock:
            for job in self.jobs.values():
                observed = job.poll(now)
                self.job_states[str(job.path)] = observed
                if observed["changed"]:
                    self.last_progress = now
                    self.repeats = 0
                    self.exec_revision += 1
                    self.recent.append(self.log("job.progress", role="harness", **observed))
                    if observed.get("job_status") in {"failed", "timeout", "lost"} or observed.get("cleanup") == "failed":
                        self.trigger = "job_failed"
                elif observed["stalled_s"] >= observed.get("stall_after_s", self.config["stall_s"]) and observed["phase"] != "complete":
                    self.trigger = "job_stalled"
            if self.active and now - self.last_progress >= self.config["stall_s"]:
                self.trigger = self.trigger or "tool_stalled"
            waiting_on_job = any(j.phase != "complete" for j in self.jobs.values())
            if (now - self.last_review >= self.config["long_task_s"] and self.recent and not waiting_on_job
                    and now - self.last_progress >= self.config["stall_s"]):
                self.trigger = self.trigger or "long_task_checkpoint"
            trigger = self.trigger
        if trigger:
            self.review(trigger)

    def review(self, reason, paused=False):
        from supervisor_runtime import invoke, parse_decision
        if not self.review_lock.acquire(blocking=False):
            return
        try:
            now = time.monotonic()
            if (self.finalizing or self.cancelled() or self.reviews >= self.config["max_reviews"]
                    or not self.model_budget_available()
                    or (self.reviews and now - self.last_review < self.config["review_interval_s"])):
                return
            self.reviews += 1
            self.executor_paused = False  # 중간 호출은 관찰 전용. 직접 실행은 계획/최종 검수에서만.
            self.last_review = now
            self.trigger = ""
            self.enabled = True  # 긴 EXECUTE도 이상 신호가 있으면 의식 감독으로 승격한다.
            revision = self.exec_revision
            cursor = self.store.sequence
            decision = parse_decision(invoke(self, json.dumps({"trigger": reason, **self.state()}, ensure_ascii=False), phase="review"))
            if self.cancelled():
                return
            self.log("decision", role="consciousness", trigger=reason, decision=decision)
            self.review_cursor = cursor
            if decision["status"] in {"REWORK", "UNKNOWN"} and decision.get("instruction"):
                with self.lock:
                    if revision != self.exec_revision:
                        self.log("decision.stale", role="harness", reviewed_revision=revision, current_revision=self.exec_revision)
                        return  # 관찰 중 실제로 회복한 작업에는 옛 정체 지시를 주지 않는다.
                    self.pending = {"id": uuid.uuid4().hex, "reason": decision["reason"],
                                    "instruction": decision["instruction"], "review": self.reviews, "revision": revision}
        except Exception as exc:
            self.log("review.error", role="consciousness", error=str(exc))
        finally:
            self.phase = "execute"
            self.executor_paused = False
            self.review_lock.release()

    def tool(self, payload, multimedia=False):
        from supervision_bus import identity
        is_manager = identity()[0] == self.supervisor_id
        op = payload.get("op")
        try:
            if self.cancelled():
                raise ValueError("이 감독 턴은 닫혔습니다")
            if is_manager:
                reserve = 0 if self.finalizing else self.config["final_tool_reserve"]
                if (self.call_cancelled() or self.call_tools >= self.config["max_tools_per_call"]
                        or self.tools_used >= self.config["max_tools_total"] - reserve):
                    raise ValueError("감독 도구 예산 소진. 가능한 근거만으로 UNKNOWN/실행 위임을 판정하세요")
                self.call_tools += 1
                self.tools_used += 1
            elif op not in {"state", "response", "evidence", "patch", "keep"}:
                raise ValueError("실행자는 자신의 기존 도구를 직접 사용하세요")
            offset, limit = int(payload.get("offset", 0)), int(payload.get("limit", 12000))
            if offset < 0 or not 1 <= limit <= 24000:
                raise ValueError("offset은 0 이상, limit은 1~24000이어야 합니다")
            if op == "state":
                result = self.state(delta=is_manager and bool(self.state_cursor), offset=offset or None, mark=is_manager)
            elif op == "evidence":
                key = payload.get("id", "")
                if key == "events":
                    result = self.store.read_events(offset, limit)
                elif key.startswith("ibl:"):
                    from supervisor_runtime import action_schema
                    result = action_schema(key[4:])
                else:
                    result = self.catalog[key[5:]] if key.startswith("tool:") else self.store.read_evidence(key, offset, limit)
            elif op == "response":
                result = self.store.read_response(offset, limit, mark=is_manager)
            elif op in {"patch", "keep"}:
                if not self.finalizing or (not is_manager and self.phase != "repair"):
                    raise ValueError("응답 패치는 검수·보완 단계에만 가능합니다")
                if op == "patch":
                    result = self.store.patch(payload.get("version"), payload.get("patches", []))
                else:
                    self.repair_kept = True
                    result = self.store.manifest()
            elif op == "execute":
                name, args = payload.get("name"), payload.get("input", {})
                if name not in self.catalog or name in {"reframe", "pursuit", "supervision"}:
                    raise ValueError("실행자에게 부여된 실제 작업 도구만 사용할 수 있습니다")
                # 도구는 임의 코드/워크플로우를 품을 수 있다. 이름 추측으로 read-only 판정하지 않고
                # 실행 중인 동작이 하나라도 있으면 직접 실행 전체를 막아 단일 작성자를 지킨다.
                with self.lock:
                    if self.active or not self.executor_paused:
                        raise ValueError("실행자가 아직 작업 중입니다. 기록을 관찰하고 다음 정지 경계에서 필요한 지시를 남기세요")
                    if any(j.phase != "complete" for j in self.jobs.values()):
                        from cognitive_trace import _classify_call, _ibl_safety_map, _ibl_op_safety_map
                        kind, _ = _classify_call({"name": name, "input": args}, _ibl_safety_map(), _ibl_op_safety_map())
                        if kind != "read":
                            raise ValueError("백그라운드 작성자가 남아 있습니다. 자원·산출물 회수 후 수정하세요")
                self.log("ownership.acquired", role="consciousness", name=name)
                try:
                    result = self._execute(name, args, project_path=self.project_path, agent_id=self.owner)
                finally:
                    self.log("ownership.released", role="consciousness", name=name)
            else:
                raise ValueError("알 수 없는 감독 작업")
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except ValueError:
                    pass
            self.log("tool.supervisor" if is_manager else "response.operation", role="consciousness" if is_manager else "execution",
                     operation=op, input=self.store.evidence(payload), result=self.store.evidence(result),
                     is_error=_failed(result) or (isinstance(result, dict) and bool(result.get("requires_approval"))))
            if multimedia and isinstance(result, dict) and result.get("images"):
                return {"content": json.dumps({"success": True, "result": result.get("content", "")}, ensure_ascii=False),
                        "images": result["images"], "details": result.get("details")}
            # 문자열 JSON을 다시 문자열 안에 감싸지 않는다. 실제 거절/오류도 바깥에 전파한다.
            blocked = isinstance(result, dict) and bool(result.get("requires_approval"))
            return json.dumps({"success": not (_failed(result) or blocked), "result": result}, ensure_ascii=False, default=str)
        except Exception as exc:
            self.log("tool.error", role="consciousness" if is_manager else "execution", operation=op, error=str(exc))
            return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)

    def request_done(self, binding, why):
        self.enabled = True
        self.done_request = {"id": binding.row["id"], "version": binding.row["version"],
                             "goal_criteria": binding.row["goal_criteria"], "why": why}
        if self.original_pursuit and self.original_pursuit["id"] == binding.row["id"]:
            self.done_request["original_goal_criteria"] = self.original_pursuit["goal_criteria"]
        self.log("pursuit.completion_requested", evidence=self.store.evidence(self.done_request))
        return {"status": "completion_requested", "message": "전체 목표 달성 근거를 의식이 최종 검수한 뒤 완료 처리합니다"}

    def finalize(self, response, history, collect, cancel_check=None, tool_calls=None):
        from supervisor_runtime import invoke, parse_decision, repair_message
        from thread_context import set_goal_eval_outcome
        set_goal_eval_outcome(False, 2)  # 저장·증거 수집부터 실패하면 성공 경험으로 증류하지 않는다.
        self.finalizing = True
        self.review_cursor = 0  # 최종 검수는 이번 턴 전체 궤적과 원래 전체 목표를 다시 대조한다.
        self.store.put_response(response)
        decision = {"status": "UNKNOWN", "reason": "검수가 완료되지 않았습니다"}
        with self.review_lock:
            self.executor_paused = True
            for attempt in range(self.config["max_repairs"] + 1):
                if self.cancelled():
                    break
                yield {"type": "thinking", "content": "의식이 목표 달성 근거와 저장된 응답을 검수하고 있습니다."}
                self.store.coverage.clear()
                if hasattr(self.runner, "_collect_visual_artifacts"):
                    self.final_images = self.runner._collect_visual_artifacts(self.store.text, tool_calls=tool_calls or []) or None
                prompt = json.dumps({"phase": "final", **self.state()}, ensure_ascii=False)
                # 짧은 후보는 첫 호출에 그대로 제공. 장문은 범위 도구로 끝까지 읽는다.
                page = self.store.read_response(0, 12000, mark=True)
                prompt += "\nresponse_first_page=" + json.dumps(page, ensure_ascii=False)
                try:
                    decision = parse_decision(invoke(self, prompt, phase="final"))
                except Exception as exc:
                    decision = {"status": "UNKNOWN", "reason": str(exc)}
                if decision["status"] == "CONTINUE":
                    decision = {"status": "UNKNOWN", "reason": "최종 검수에서 완료 판정 대신 계속 진행 신호를 받았습니다"}
                manifest = self.store.manifest()
                if decision["status"] == "APPROVED" and (
                    not self.store.fully_read() or decision.get("response_version") != manifest["version"]
                    or decision.get("response_hash") != manifest["hash"] or self.cancelled()
                ):
                    decision = {"status": "UNKNOWN", "reason": "본문 검수 범위 또는 승인 버전·지문이 일치하지 않습니다"}
                if decision["status"] == "APPROVED" and self.done_request and decision.get("pursuit_status") != "APPROVED":
                    decision = {"status": "UNKNOWN", "reason": "이번 턴과 별개인 전체 과제의 목표 달성이 승인되지 않았습니다"}
                delivery = self.delivery.manifest()
                if decision["status"] == "APPROVED" and delivery and decision.get("delivery_hash") != delivery["hash"]:
                    decision = {"status": "UNKNOWN", "reason": "공개 산출물·알림의 승인 지문이 현재 초안과 다릅니다"}
                self.log("decision", role="consciousness", decision=decision, response=manifest)
                from episode_logger import record_trajectory_event
                record_trajectory_event("validation.completed", {
                    "validator": "conscious_supervisor", "round": attempt + 1,
                    "status": decision["status"], "achieved": decision["status"] == "APPROVED",
                    "feedback_text": decision.get("reason", ""), "response_hash": manifest["hash"],
                    "response_version": manifest["version"], "store": str(self.store.directory),
                })
                if decision["status"] != "REWORK" or attempt >= self.config["max_repairs"]:
                    break
                self.phase = "repair"
                self.executor_paused = False
                self.repair_kept = False
                before_version = self.store.version
                self.log("ownership.handoff", role="harness", to="execution", instruction=decision.get("instruction"))
                # 같은 실행 세션을 이어받는다. 모든 사용자용 본문은 patch 도구가 저장하며 재타이핑하지 않는다.
                for event in self.runner.ai.process_message_stream(repair_message(self, decision), history=history,
                                                                   images=None, cancel_check=cancel_check):
                    collect(event)
                    self.observe_native(event)
                    if event.get("type") not in {"text", "final"}:
                        yield event
                self.log("ownership.handoff", role="harness", to="consciousness")
                self.executor_paused = True
                if self.store.version == before_version and not self.repair_kept:
                    decision = {"status": "UNKNOWN", "reason": "실행자의 보완 결과가 patch/keep로 확정되지 않았습니다"}
                    self.log("repair.unconfirmed", role="harness", decision=decision)
                    break
        approved = decision["status"] == "APPROVED"
        completion_binding = None
        if approved and self.done_request:
            try:
                from pursuit_bind import resolve_session
                completion_binding = resolve_session(self.owner, self.task)
                if (completion_binding.row["id"] != self.done_request["id"]
                        or completion_binding.row["version"] != self.done_request["version"]):
                    raise ValueError("검수 중 과제 버전이 바뀌었습니다")
            except Exception as exc:
                self.log("pursuit.approval_conflict", role="harness", error=str(exc))
                approved = False
                decision = {"status": "UNKNOWN", "reason": "검수 중 전체 과제가 변경되어 완료 승인을 적용하지 못했습니다"}
        if approved:
            try:
                self.delivery.deliver(decision.get("delivery_hash"), self.cancelled)
            except Exception as exc:
                self.log("delivery.failed", role="harness", error=str(exc))
                approved = False
                decision = {"status": "UNKNOWN", "reason": f"검수한 산출물·알림을 전달하지 못했습니다: {exc}"}
                record_trajectory_event("validation.completed", {
                    "validator": "conscious_supervisor", "status": "UNKNOWN", "achieved": False,
                    "feedback_text": decision["reason"], "stage": "delivery"})
        if approved and self.done_request and decision.get("pursuit_status") == "APPROVED":
            try:
                completion_binding.write({"status": "done"}, kind="supervisor.approved",
                                         why=decision["reason"], key=self.turn_id)
            except Exception as exc:
                self.log("pursuit.approval_conflict", role="harness", error=str(exc))
                approved = False
                decision = {"status": "UNKNOWN", "reason": "검수 중 전체 과제가 변경되어 완료 승인을 적용하지 못했습니다"}
        set_goal_eval_outcome(approved, 0 if approved else 2)
        print(f"[ConsciousSupervisor] 최종 판정: {decision['status']}")
        final = self.store.text
        if not approved:
            final += "\n\n[의식 검수 미승인] " + str(decision.get("reason", "검수 미완료"))
        self.log("response.delivered", role="harness", status=decision["status"], response=self.store.manifest())
        yield {"type": "text", "content": final}
        yield {"type": "final", "content": final}
        return final


def _failed(value):
    from workflow_engine import is_error_result
    from ibl_honesty import completion_evidence
    return is_error_result(value) or bool(completion_evidence(value))


def _job_observation(value):
    """실행 시간 숫자만 변하는 status 폴링을 진척으로 세지 않는다. 뜻은 실제 job 필드에서 온다."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if isinstance(value, dict):
        if value.get("job_id") and value.get("status"):
            return [{"job_id": value["job_id"], "status": value["status"]}]
        rows = []
        for item in value.values():
            if isinstance(item, (dict, list)):
                rows.extend(_job_observation(item))
        return rows
    if isinstance(value, list):
        return [row for item in value for row in _job_observation(item)]
    return []
