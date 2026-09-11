"""백엔드 밖의 단일 재기동 소유자. keeper의 감시 루프를 대체한다.

각 tick은 영속화된 의도를 먼저 읽고 같은 조치를 재시도한다. 실행 소유 관측 실패는
UNKNOWN이며 느린 현역을 죽이지 않는다. 후보/동시 세대 실행은 제공하지 않는다.
"""
import argparse
import os
import secrets
import signal
import sys
import time
from pathlib import Path

from restart_protocol import (STATE_VERSION, OwnerLock, atomic_json, code_manifest,
                              control_dir, preflight, read_json, request)
from restart_process import ProcessAdapter, identity, signal_owned


class Controller:
    def __init__(self, base, code_root, adapter=None, clock=time.time, fault=None):
        self.base, self.code_root = Path(base), Path(code_root)
        self.home, self.clock, self.fault = control_dir(base), clock, fault
        self.adapter = adapter or ProcessAdapter(base, code_root, os.environ.get("INDIEBIZ_API_PORT", 8765))
        self.state = read_json(self.home / "state.json") or {
            "version": STATE_VERSION, "phase": "STOPPED", "generation": None,
            "worker": None, "code_digest": None, "request": None, "last_result": None}
        if self.state.get("version") != STATE_VERSION:
            raise ValueError("제어 상태 버전을 읽을 수 없습니다")
        self.lock = OwnerLock(self.home / "owner.lock")
        self.last_watch = 0
        self.spawn_attempted = 0

    def save(self, **changes):
        state = dict(self.state, **changes, updated_at=self.clock())
        if self.fault:
            self.fault("before", state["phase"])
        atomic_json(self.home / "state.json", state)
        self.state = state
        if self.fault:
            self.fault("after", state["phase"])

    def result(self, outcome, **details):
        req = self.state.get("request") or {}
        value = {"request_id": req.get("request_id"), "outcome": outcome,
                 "generation": self.state.get("generation"), "finished_at": self.clock(),
                 "owners": self.state.get("last_owners"),
                 "interrupted": self.state.get("interrupted_owners", []),
                 "effect_unknown": self.state.get("effect_unknown", False), **details}
        if value["request_id"]:
            atomic_json(self.home / "results" / (value["request_id"] + ".json"), value)
        return value

    def finish(self, outcome, phase="ACTIVE", **details):
        result = self.result(outcome, **details)
        # ACTIVE의 첫 조치는 activate 재전달이다. 이 저장 직후 죽어도 관문이 남지 않는다.
        self.save(phase=phase, request=None, last_result=result, resume_pending=False)

    def pending(self):
        folder = self.home / "requests"
        if not folder.exists():
            return []
        requests = []
        for path in folder.glob("*.json"):
            if (self.home / "results" / path.name).exists():
                continue
            try:
                req = read_json(path)
                if req and req.get("request_id") == path.stem:
                    requests.append(req)
            except (ValueError, OSError):
                continue
        return sorted(requests, key=lambda r: (r.get("created_at", 0), r["request_id"]))

    def start_generation(self, manifest):
        self.save(phase="STARTING", generation=secrets.token_hex(16),
                  code_digest=manifest["digest"], manifest=manifest, worker=None,
                  control_token=secrets.token_hex(32), deadline=self.clock() + 300,
                  spawn_after=self.clock(), stop_tree=[], process_tree=[], resume_pending=False, recovery_stopping=False,
                  legacy=False, serving_worker=None, legacy_keeper=None)
        self.spawn_attempted = 0

    def observe(self):
        snap = self.adapter.status(self.state)
        known = (snap.get("generation") == self.state["generation"]
                 and snap.get("code_digest") == self.state["code_digest"]
                 and snap.get("ownership") == "known"
                 and all(type(snap.get(k)) is int and snap[k] >= 0 for k in
                         ("active_roots", "active_children", "pending_finalizers")))
        if not known:
            return None
        self.save(last_owners=snap)
        return snap

    def begin_stop(self, *, intentional=False, force=False):
        members = self.adapter.tree(self.state.get("worker"))
        # 관측했던 자식도 남긴다. 부모 사망 뒤 고아가 된 도구를 잊지 않는다.
        old = self.state.get("process_tree", []) + self.state.get("helper_tree", [])
        for path in (self.home / "processes").glob(str(self.state.get("generation")) + "-*.json"):
            receipt = read_json(path)
            if receipt and receipt.get("generation") == self.state.get("generation"):
                old.extend(receipt["members"])
        unique = {(p["pid"], p["born"]): p for p in members + old}
        self.save(phase="STOPPING", stop_tree=list(unique.values()),
                  intentional=intentional, force=force, deadline=self.clock() + 30)

    def defer(self, note):
        self.save(resume_pending=True, defer_note=note)

    def tick(self):
        s = self.state
        phase = s["phase"]
        intentional = (self.base / "data/.intentional_shutdown").exists()
        if intentional and phase not in {"STOPPED", "STOPPING"}:
            self.begin_stop(intentional=True, force=True)
            return
        if phase == "STOPPED":
            return
        if phase == "FAILED":
            for pending in self.pending():
                if pending["operation"] != "restart":
                    continue
                if pending.get("expected_generation") != s.get("generation"):
                    continue
                if self.adapter.alive(s.get("worker")):
                    return
                manifest = code_manifest(self.code_root)
                if manifest["digest"] != pending.get("artifact_digest"):
                    return
                preflight(self.code_root, manifest)
                self.save(request=pending, rollback_attempted=False)
                self.start_generation(manifest)
                break
            return  # 자동 무한 재기동 금지. 명시적 요청만 재시도한다.
        if phase == "ACTIVE":
            if not self.adapter.alive(s.get("worker")):
                self.save(phase="RECOVERING", recovery_reason="active_crash", deadline=self.clock() + 30)
                return
            # 살아 있지만 느리면 여기서 멈춘다. health 3회 실패를 죽음으로 바꾸지 않는다.
            snap = self.observe()
            if snap is None:
                return
            self.adapter.command(self.state, "activate")
            members = self.adapter.tree(s["worker"])
            if members != s.get("process_tree"):
                self.save(process_tree=members)
            pending = self.pending()
            if pending:
                req = pending[0]
                self.save(request=req, phase="CHECKING", rollback_attempted=False,
                          recovery_stopping=False, red_outcome=None, force=False, intentional=False,
                          recovery_reason=None,
                          interrupted_owners=[], effect_unknown=False, previous_digest=s["code_digest"])
                return
            if os.environ.get("INDIEBIZ_PRODUCTION", "").lower() not in {"1", "true"}:
                if self.clock() - self.last_watch >= 2:
                    self.last_watch = self.clock()
                    manifest = code_manifest(self.code_root)
                    if manifest["digest"] != self.state["code_digest"]:
                        rid = "files-" + self.state["generation"] + "-" + manifest["digest"][:24]
                        request(self.base, "development_files", request_id=rid,
                                artifact_digest=manifest["digest"])
            return
        if phase == "CHECKING":
            req = s["request"]
            if req.get("version") != STATE_VERSION or req.get("expected_generation") != s["generation"]:
                self.finish("stale_generation")
                return
            if req["operation"] == "shutdown":
                atomic_json(self.base / "data/.intentional_shutdown", {"request_id": req["request_id"]})
                self.begin_stop(intentional=True, force=True)
                return
            if req["operation"] == "cancel":
                self.finish("nothing_to_cancel")
                return
            try:
                manifest = code_manifest(self.code_root)
                if manifest["digest"] != req["artifact_digest"]:
                    raise ValueError("요청한 코드와 현재 manifest가 다릅니다")
                preflight(self.code_root, manifest)
                if req["operation"] == "red_apply":
                    from restart_red import inspect_job
                    inspect_job(self.base, req["payload"]["job_path"])
            except Exception as exc:
                self.finish("check_failed", error=str(exc))
                return
            self.save(phase="DRAINING", target_manifest=manifest,
                      deadline=self.clock() + float(req["policy"].get("drain_timeout_s", 600)))
            return
        if phase == "DRAINING":
            # 취소는 drain까지만 허용. 이미 멈춘 뒤에는 복구를 끝내야 한다.
            cancellations = [r for r in self.pending() if r["operation"] == "cancel"
                             and r["payload"].get("request_id") == s["request"]["request_id"]
                             and r.get("expected_generation") == s["generation"]]
            if cancellations:
                self.defer("request_cancelled")
                for req in cancellations:
                    atomic_json(self.home / "results" / (req["request_id"] + ".json"),
                                {"outcome": "cancelled", "request_id": req["request_id"]})
            if self.state.get("resume_pending"):
                response = self.adapter.command(self.state, "activate")
                if response.get("accepting") is True:
                    self.finish("deferred", note=self.state.get("defer_note"))
                return
            if not self.adapter.alive(s.get("worker")):
                self.save(phase="RECOVERING", recovery_reason="active_crash", deadline=self.clock() + 30)
                return
            try:
                self.adapter.command(s, "drain")
                snap = self.observe()
            except Exception:
                snap = None
            if snap is not None and snap.get("accepting") is False and all(snap[k] == 0 for k in
                    ("active_roots", "active_children", "pending_finalizers")):
                if code_manifest(self.code_root) != s["target_manifest"]:
                    self.defer("artifact_changed_after_check")
                    return
                self.begin_stop()
            elif self.clock() >= s["deadline"]:
                if s["request"]["policy"].get("force") is True and snap is not None:
                    self.begin_stop(force=True)
                else:
                    self.defer("drain_deadline_or_unknown")
            return
        if phase == "STOPPING":
            self.adapter.stop(s, force=self.clock() >= s["deadline"])
            if not self.adapter.stopped(s):
                return
            if s.get("force"):
                from restart_red import record_interrupted
                snapshot = s.get("last_owners") or {}
                record_interrupted(self.base, snapshot, "intentional_shutdown" if intentional else "forced_restart")
                self.save(interrupted_owners=snapshot.get("owners", []),
                          effect_unknown=(s.get("recovery_reason") == "active_crash"
                                          or bool(snapshot.get("owners")) or not snapshot))
            if intentional or s.get("intentional"):
                for pending in self.pending():
                    atomic_json(self.home / "results" / (pending["request_id"] + ".json"),
                                {"outcome": "intentional_shutdown", "request_id": pending["request_id"]})
                self.finish("intentional_shutdown", phase="STOPPED")
                return
            req = s.get("request") or {}
            if req.get("operation") == "red_apply":
                # 적용 의도를 먼저 저장한다. 재실행은 RED 적용 기록과 대조한다.
                self.save(phase="RECOVERING", recovery_reason="red_apply", apply_started=False)
                return
            manifest = code_manifest(self.code_root)
            if req and manifest != s.get("target_manifest"):
                self.finish("artifact_changed_before_start", phase="FAILED")
                return
            try:
                preflight(self.code_root, manifest)
            except Exception as exc:
                self.finish("check_failed_after_stop", phase="FAILED", error=str(exc))
                return
            self.start_generation(manifest)
            return
        if phase == "STARTING":
            receipt = self.adapter.receipt(s)
            if receipt is None:
                record = read_json(self.home / "workers" / (s["generation"] + ".json"))
                if record and record.get("nonce") == s["generation"] and not self.adapter.alive(record):
                    self.save(phase="RECOVERING", worker=record, recovery_reason="boot_failed")
                    return
                if self.clock() >= s["deadline"]:
                    self.save(phase="RECOVERING", recovery_reason="boot_failed")
                    return
                # bootstrap은 worker.lock+receipt로 중복 spawn의 부작용을 막는다.
                if not self.spawn_attempted or self.clock() - self.spawn_attempted >= 10:
                    if not self.adapter.port_free():
                        self.finish("port_occupied", phase="FAILED")
                        return
                    if code_manifest(self.code_root) != s["manifest"]:
                        self.finish("artifact_changed_before_spawn", phase="FAILED")
                        return
                    self.spawn_attempted = self.clock()
                    self.adapter.spawn(s)
                return
            if receipt != s.get("worker"):
                self.save(worker=receipt)
            self.adapter.permit(self.state)
            snap = self.observe()
            if snap is not None and snap.get("readiness") in {"ready", "degraded"}:
                if code_manifest(self.code_root) != s["manifest"]:
                    self.save(phase="RECOVERING", recovery_reason="boot_artifact_changed")
                    return
                if (s.get("request") or {}).get("operation") in {"red_apply", "red_verify"}:
                    done, members = self.adapter.helper("verify", self.state)
                    self.save(helper_tree=members)
                    if done is None:
                        return
                    if not done.get("ok") or not done.get("result", {}).get("verified"):
                        self.save(phase="RECOVERING", recovery_reason="red_verification_failed")
                        return
                if (self.base / "data/.intentional_shutdown").exists():
                    return
                self.adapter.command(self.state, "activate")
                outcome = "rolled_back" if self.state.get("rollback_attempted") else "restarted"
                if ((self.state.get("request") or {}).get("operation") == "red_apply"
                        and not (self.state.get("red_outcome") or {}).get("applied")
                        and outcome == "restarted"):
                    outcome = "apply_rejected"
                self.finish(outcome)
            elif self.clock() >= s["deadline"] or (snap and snap.get("readiness") == "failed"):
                self.save(phase="RECOVERING", recovery_reason="boot_failed")
            return
        if phase == "RECOVERING":
            from restart_red import recover_code
            reason = s.get("recovery_reason")
            if reason == "red_apply":
                done, members = self.adapter.helper("apply", s)
                self.save(helper_tree=members)
                if done is None:
                    return
                if not done.get("ok"):
                    if not recover_code(self.base, self.state):
                        self.finish("apply_interrupted_manual_recovery", phase="FAILED", error=done.get("error"))
                        return
                    self.save(rollback_attempted=True)
                else:
                    self.save(red_outcome=done["result"])
                manifest = code_manifest(self.code_root)
                try:
                    preflight(self.code_root, manifest)
                except Exception:
                    if not recover_code(self.base, self.state):
                        self.finish("red_preflight_failed", phase="FAILED")
                        return
                    self.save(rollback_attempted=True)
                    manifest = code_manifest(self.code_root)
                    preflight(self.code_root, manifest)
                self.start_generation(manifest)
                return
            # 실제 사망을 확인한 경우에만 기록한 자식을 정리하고 복구한다.
            if reason == "active_crash":
                self.begin_stop(force=True)
                return
            if not s.get("recovery_stopping"):
                members = (self.adapter.tree(s.get("worker")) + s.get("process_tree", [])
                           + s.get("helper_tree", []))
                self.save(recovery_stopping=True, stop_tree=members, deadline=self.clock() + 30)
                return
            self.adapter.stop(s, force=self.clock() >= s["deadline"])
            if not self.adapter.stopped(s):
                return
            if s.get("rollback_attempted") or not recover_code(self.base, s):
                self.finish("recovery_unavailable", phase="FAILED", note=reason)
                return
            self.save(rollback_attempted=True, recovery_stopping=False)
            manifest = code_manifest(self.code_root)
            if manifest["digest"] != s.get("previous_digest"):
                self.finish("rollback_digest_mismatch", phase="FAILED")
                return
            preflight(self.code_root, manifest)
            self.start_generation(manifest)

    def run(self, start=False):
        acquire_deadline = time.monotonic() + 40
        while not self.lock.acquire():
            observed = read_json(self.home / "state.json", {})
            if not start or not (self.base / "data/.intentional_shutdown").exists():
                if start and observed.get("phase") == "FAILED":
                    request(self.base, "explicit_start_retry", artifact_digest=code_manifest(self.code_root)["digest"])
                return 0
            if time.monotonic() >= acquire_deadline:
                return 2
            time.sleep(0.05)
        # 잠금 대기 중 이전 제어자가 남긴 최종 상태를 다시 읽는다.
        self.state = read_json(self.home / "state.json") or self.state
        try:
            self.save(controller=identity(os.getpid()))
            legacy = read_json(self.home / "legacy.json")
            if (self.state["phase"] == "STOPPED" and legacy
                    and self.adapter.alive(legacy.get("worker"))
                    and self.adapter.alive(legacy.get("serving_worker"))):
                self.save(**legacy, phase="ACTIVE")
                manifest = code_manifest(self.code_root)
                request(self.base, "legacy_takeover", request_id="takeover-" + legacy["generation"],
                        artifact_digest=manifest["digest"])
            keeper = self.state.get("legacy_keeper")
            if keeper and self.adapter.alive(keeper):
                # 영수증의 출생 신원을 재검증한다. 포트/이름 전수 kill을 하지 않는다.
                signal_owned(keeper)
            if start and self.state["phase"] in {"STOPPED", "FAILED"}:
                if self.adapter.alive(self.state.get("worker")):
                    return 2
                marker = self.base / "data/.intentional_shutdown"
                marker.unlink(missing_ok=True)
                manifest = code_manifest(self.code_root)
                preflight(self.code_root, manifest)
                self.start_generation(manifest)
            def shutdown(signum, frame):
                atomic_json(self.base / "data/.intentional_shutdown", {"signal": signum})
            signal.signal(signal.SIGTERM, shutdown)
            signal.signal(signal.SIGINT, shutdown)
            while self.state["phase"] != "STOPPED":
                try:
                    self.tick()
                except Exception as exc:
                    # 관측/일시 I/O 실패는 재기동 권한이 아니다. 상태를 유지한다.
                    print(f"[restart_controller] {self.state['phase']}: {type(exc).__name__}: {exc}", flush=True)
                if self.state["phase"] != "STOPPED":
                    time.sleep(0.5)
            return 0
        finally:
            self.lock.close()


def main(argv=None, code_root=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "serve", "restart", "shutdown", "status", "wait"], nargs="?", default="start")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--request-id")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--drain-timeout", type=float, default=600)
    args = parser.parse_args(argv)
    code_root = Path(code_root) if code_root else Path(__file__).resolve().parents[2]
    base = Path(os.environ.get("INDIEBIZ_BASE_PATH", code_root))
    if args.action in {"start", "serve"}:
        return Controller(base, code_root).run(start=args.action == "start")
    if args.action == "wait":
        while read_json(control_dir(base) / "state.json", {}).get("phase") != "STOPPED":
            time.sleep(0.5)
        return 0
    if args.action == "status":
        state = read_json(control_dir(base) / "state.json", {})
        state.pop("control_token", None)
        print(state)
        return 0
    manifest = code_manifest(code_root)
    req = request(base, "cli_" + args.action, operation=args.action,
                  request_id=args.request_id, artifact_digest=manifest["digest"],
                  policy={"drain_timeout_s": args.drain_timeout, "force": args.force})
    if args.action == "shutdown":
        atomic_json(base / "data/.intentional_shutdown", {"request_id": req["request_id"]})
    print(req["request_id"])
    if args.wait and args.action == "restart":
        from restart_protocol import wait_result
        result = wait_result(base, req["request_id"], timeout=args.drain_timeout + 330)
        print(result)
        return 0 if result.get("outcome") == "restarted" else 2
    if args.wait:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            state = read_json(control_dir(base) / "state.json", {})
            if state.get("phase") == "STOPPED":
                return 0
            time.sleep(0.2)
        return 2
    return 0
