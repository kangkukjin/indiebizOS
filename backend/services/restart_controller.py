"""백엔드 밖의 단일 재기동 소유자. keeper의 감시 루프를 대체한다.

각 tick은 영속화된 의도를 먼저 읽고 같은 조치를 재시도한다. 실행 소유 관측 실패는
UNKNOWN이며 느린 현역을 죽이지 않는다. 두 현역의 동시 사용자 처리는 제공하지 않는다.

2026-10-27 세대 전환(docs/SELF_REPAIR_SYSTEM_REDESIGN_2026_10_27.md): 워커는 가변 checkout 이 아니라
봉인된 세대 폴더(generation_store)에서 돈다. 정본 편집은 현역의 바이트를 바꾸지 않고 다음 후보가
된다. 교체 전 실패는 현역 유지, 교체 후 실패는 직전 정상 세대 복구다. 자기수리의 정본 반영(red_apply)은
PUBLISHING 에서 현역을 살려 둔 채 수행·커밋한 뒤 그 정본으로 후보를 만들어 교체한다.
"""
import argparse
import os
import secrets
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

if __name__ == "__main__":  # 기반 사본(control_base)에서 스크립트로 기동되는 경로
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "base"))

from restart_protocol import (STATE_VERSION, OwnerLock, atomic_json, code_manifest,
                              control_dir, read_json, request)
from restart_process import ProcessAdapter, alive, controller_presence, identity, signal_owned

LOG_LIMIT = 2 * 1024 * 1024
PUBLISH_TIMEOUT_S = 1800
CONTROL_WATCH_S = 10
HANDOVER_WAIT_S = 30


def log(home, message):
    """제어자의 자기 수명 기록 — `data/restart_control/controller.log`.

    2026-10-26 제어자 pid 39960 이 06:40:04 ACTIVE 관측 저장 직후 소리 없이 사라졌다. stdout 은
    시작한 주체마다 달랐고(런처 파이프·세션 스크래치 파일·터미널), 종료 기록도 감시자도 없어서
    원인 지문이 하나도 남지 않았다. 그래서 시작·잠금 양보·tick 예외·신호·종료를 제어자 자신이
    한 파일에 남긴다. stdout 쓰기 실패(닫힌 파이프 EPIPE 등)는 제어자를 죽이지 않는다.
    """
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] pid={os.getpid()} {message}"
    try:
        path = Path(home) / "controller.log"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            if path.stat().st_size > LOG_LIMIT:
                os.replace(path, path.with_name("controller.log.old"))
        except OSError:
            pass
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    try:
        print(line, flush=True)
    except (OSError, ValueError):
        pass


def _candidate_of_state(state):
    """현역 세대를 다시 띄울 후보(크래시 복구·같은 세대 재기동)."""
    if not state.get("generation_dir"):
        return None
    return {"generation": state.get("code_digest"), "generation_dir": state["generation_dir"],
            "source_digest": state.get("source_digest"), "reason": "relaunch"}


class Controller:
    def __init__(self, base, code_root, adapter=None, clock=time.time, fault=None):
        self.base, self.code_root = Path(base), Path(code_root)
        self.home, self.clock, self.fault = control_dir(base), clock, fault
        self.adapter = adapter or ProcessAdapter(base, code_root, os.environ.get("INDIEBIZ_API_PORT", 8765))
        self.state = read_json(self.home / "state.json") or {
            "version": STATE_VERSION, "phase": "STOPPED", "generation": None,
            "code_digest": None, "generation_dir": None, "source_digest": None,
            "worker": None, "request": None, "last_result": None, "candidate": None,
            "previous": None, "failed_sources": {}, "watch": {}}
        self.lock = OwnerLock(self.home / "owner.lock")
        self.last_watch = 0
        self.last_control_watch = 0
        self.spawn_attempted = 0
        self._watcher = None
        try:
            import control_base
            self.control_base_id = control_base.running_from()
        except Exception:
            self.control_base_id = None

    # ── 상태 저장 ────────────────────────────────────────────────────────────
    def save(self, **changes):
        state = dict(self.state, **changes, updated_at=self.clock())
        if self.fault:
            self.fault("before", state["phase"])
        atomic_json(self.home / "state.json", state)
        self.state = state
        if self.fault:
            self.fault("after", state["phase"])

    def log_line(self, message):
        log(self.home, message)

    def result(self, outcome, **details):
        req = self.state.get("request") or {}
        value = {"request_id": req.get("request_id"), "outcome": outcome,
                 "generation": self.state.get("generation"), "code_digest": self.state.get("code_digest"),
                 "generation_dir": self.state.get("generation_dir"), "finished_at": self.clock(),
                 "owners": self.state.get("last_owners"),
                 "interrupted": self.state.get("interrupted_owners", []),
                 "effect_unknown": self.state.get("effect_unknown", False), **details}
        if value["request_id"]:
            atomic_json(self.home / "results" / (value["request_id"] + ".json"), value)
        return value

    def finish(self, outcome, phase="ACTIVE", **details):
        request = self.state.get("request") or {}
        result = self.result(outcome, **details)
        # ACTIVE의 첫 조치는 activate 재전달이다. 이 저장 직후 죽어도 관문이 남지 않는다.
        self.save(phase=phase, request=None, red_job_path=None, last_result=result, resume_pending=False,
                  preparing_start=False,
                  candidate=None if phase in {"ACTIVE", "FAILED", "STOPPED"} else self.state.get("candidate"))
        self._notify_repair_root(result, request)

    def _notify_repair_root(self, result, request):
        """red_apply 요청의 결말을 수리 root 원장에 전이한다(활성 단계의 소유자는 제어자다)."""
        if request.get("operation") != "red_apply":
            return
        job_path = (request.get("payload") or {}).get("job_path")
        if not job_path:
            return
        try:
            import repair_root
            repair_root.note_controller_result(self.base, job_path, result, self.state)
        except Exception as exc:
            log(self.home, f"수리 root 전이 실패(무시): {type(exc).__name__}: {exc}")

    def record_failed_source(self, source_digest, outcome, note=""):
        failed = dict(self.state.get("failed_sources") or {})
        failed[source_digest] = {"outcome": outcome, "note": str(note)[:600], "at": self.clock(),
                                 "active_code_digest": self.state.get("code_digest")}
        # 오래된 항목은 정리한다(정본이 바뀌면 지문도 바뀌어 다시 보지 않는다).
        if len(failed) > 20:
            for key in sorted(failed, key=lambda k: failed[k].get("at", 0))[:-20]:
                failed.pop(key)
        self.save(failed_sources=failed)
        log(self.home, f"원천 {source_digest[:12]} 후보 실패 — {outcome}: {str(note)[:300]}")

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

    # ── 세대 ────────────────────────────────────────────────────────────────
    def candidates(self):
        import restart_candidates
        return restart_candidates

    def prepare_candidate(self, reason, extra=None):
        return self.candidates().prepare(self.base, self.code_root, reason=reason, extra=extra)

    def start_generation(self, candidate, *, rollback=False):
        s = self.state
        if "generation" not in candidate and "digest" in candidate:
            # 옛 호출(코드 manifest) — 세대 폴더 없이 가변 checkout 에서 띄우는 이행 경로
            candidate = {"generation": candidate["digest"], "generation_dir": None, "source_digest": None,
                         "file_count": len(candidate.get("files") or {}) or None}
        previous = s.get("previous")
        if s.get("generation_dir") and s["generation_dir"] != candidate["generation_dir"] and not rollback:
            previous = {"code_digest": s.get("code_digest"), "generation_dir": s["generation_dir"],
                        "source_digest": s.get("source_digest")}
        if rollback:
            previous = None  # 실패한 후보는 복구 지점이 아니다
        self.save(phase="STARTING", generation=secrets.token_hex(16),
                  preparing_start=False,
                  code_digest=candidate["generation"], generation_dir=candidate["generation_dir"],
                  source_digest=candidate.get("source_digest"),
                  manifest={"digest": candidate["generation"], "files": candidate.get("file_count")},
                  previous=previous, candidate_verified=False, worker=None,
                  control_token=secrets.token_hex(32), deadline=self.clock() + 300,
                  spawn_after=self.clock(), stop_tree=[], process_tree=[], resume_pending=False,
                  recovery_stopping=False, legacy=False, serving_worker=None, legacy_keeper=None,
                  rollback_attempted=rollback or bool(s.get("rollback_attempted")) and rollback)
        self.spawn_attempted = 0

    def _prune_generations(self):
        try:
            keep = {self.state.get("generation_dir"), (self.state.get("previous") or {}).get("generation_dir"),
                    (self.state.get("candidate") or {}).get("generation_dir")}
            for req in self.pending():
                keep.add((req.get("payload") or {}).get("generation_dir"))
            removed = self.candidates().prune(self.base, self.code_root, keep, log=self.log_line)
            if removed:
                log(self.home, f"세대 정리: {removed}")
        except Exception as exc:
            log(self.home, f"세대 정리 실패(무시): {type(exc).__name__}: {exc}")

    # ── 관측 ────────────────────────────────────────────────────────────────
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

    def red_reservation_current(self):
        req = self.state.get("request") or {}
        if req.get("operation") != "red_apply":
            return True
        payload = req["payload"]
        try:
            from restart_red import inspect_job
            inspect_job(self.base, payload["job_path"], payload.get("reservation"))
            return True
        except (ValueError, OSError) as exc:
            self.defer("repair_reservation_changed: " + str(exc))
            return False

    # ── tick ────────────────────────────────────────────────────────────────
    def tick(self):
        s = self.state
        phase = s["phase"]
        intentional = (self.base / "data/.intentional_shutdown").exists()
        if intentional and phase not in {"STOPPED", "STOPPING"}:
            self.begin_stop(intentional=True, force=True)
            return
        if phase == "STOPPED":
            return
        handler = {"FAILED": self._tick_failed, "ACTIVE": self._tick_active, "PUBLISHING": self._tick_publishing,
                   "CHECKING": self._tick_checking, "DRAINING": self._tick_draining,
                   "STOPPING": self._tick_stopping, "STARTING": self._tick_starting,
                   "RECOVERING": self._tick_recovering}.get(phase)
        if handler:
            handler()

    def _tick_failed(self):
        s = self.state
        for pending in self.pending():
            if pending["operation"] != "restart":
                continue
            if pending.get("expected_generation") != s.get("generation"):
                continue
            if self.adapter.alive(s.get("worker")):
                return
            try:
                candidate = self._candidate_for(pending)
            except Exception as exc:
                self.save(request=pending)
                self.finish("check_failed", phase="FAILED", error=f"{type(exc).__name__}: {exc}")
                return
            if candidate is None:
                return
            self.save(request=pending, rollback_attempted=False, candidate=candidate)
            self.start_generation(candidate)
            break
        return  # 자동 무한 재기동 금지. 명시적 요청만 재시도한다.

    def _serve_tick(self):
        """현역을 지키는 공통 조치. 관측 불가면 False(아무것도 바꾸지 않는다)."""
        s = self.state
        if not self.adapter.alive(s.get("worker")):
            self.save(phase="RECOVERING", recovery_reason="active_crash", deadline=self.clock() + 30)
            return False
        # 살아 있지만 느리면 여기서 멈춘다. health 3회 실패를 죽음으로 바꾸지 않는다.
        snap = self.observe()
        if snap is None:
            return False
        self.adapter.command(self.state, "activate")
        members = self.adapter.tree(s["worker"])
        if members != s.get("process_tree"):
            self.save(process_tree=members)
        return True

    def _development(self):
        return os.environ.get("INDIEBIZ_PRODUCTION", "").lower() not in {"1", "true"}

    def _tick_active(self):
        if not self._serve_tick():
            return
        s = self.state
        pending = self.pending()
        if pending:
            req = pending[0]
            self.save(request=req, phase="CHECKING", rollback_attempted=False,
                      recovery_stopping=False, red_outcome=None, force=False, intentional=False,
                      recovery_reason=None, publish_attempts=0,
                      interrupted_owners=[], effect_unknown=False, previous_digest=s["code_digest"])
            return
        if self._development():
            self._control_watch()
            if self._watcher is None:
                self._watcher = self.candidates().Watcher(self)
            self._watcher.tick()

    def _candidate_for(self, req):
        """요청이 가리키는 봉인 후보를 확인하거나, 없으면 정본에서 지금 준비한다. None = 다음 tick 재시도."""
        import generation_store as gens
        payload = req.get("payload") or {}
        gen_dir = payload.get("generation_dir")
        if gen_dir:
            store = self.candidates().store_dir(self.base).resolve()
            path = Path(gen_dir).resolve()
            if not path.is_relative_to(store) or not gens.sealed(path):
                raise ValueError("요청한 후보 세대가 봉인되어 있지 않습니다: " + str(gen_dir))
            manifest = gens.verify(path)
            if manifest["generation"] != req.get("artifact_digest"):
                raise ValueError("요청한 세대 ID 와 봉인 manifest 가 다릅니다")
            gens.syntax_check(path, manifest)
            return {"generation": manifest["generation"], "generation_dir": str(path),
                    "source_digest": manifest["source_digest"], "reason": req.get("reason"),
                    "file_count": manifest.get("file_count"), "kind": payload.get("kind", "development")}
        try:
            prepared = self.prepare_candidate(req.get("reason", "restart"), extra={"request_id": req["request_id"]})
        except gens.CandidateChanged as exc:
            attempts = self.state.get("publish_attempts", 0) + 1
            self.save(publish_attempts=attempts)
            log(self.home, f"후보 준비 재시도({attempts}): {exc}")
            if attempts >= self.candidates().MAX_SNAPSHOT_RETRIES:
                raise ValueError("정본이 계속 바뀌어 후보를 봉인할 수 없습니다: " + str(exc))
            return None
        return {**prepared, "kind": payload.get("kind", "restart")}

    def _tick_checking(self):
        s = self.state
        req = s["request"]
        if req.get("version") != STATE_VERSION or req.get("expected_generation") != s["generation"]:
            self.finish("stale_generation")
            return
        if req["operation"] == "shutdown" and not req["policy"].get("drain_before_shutdown"):
            atomic_json(self.base / "data/.intentional_shutdown", {"request_id": req["request_id"]})
            self.begin_stop(intentional=True, force=True)
            return
        if req["operation"] == "cancel":
            self.finish("nothing_to_cancel")
            return
        if req["operation"] == "red_apply":
            try:
                from restart_red import inspect_job
                inspect_job(self.base, req["payload"]["job_path"], req["payload"].get("reservation"))
            except Exception as exc:
                self.finish("check_failed", error=str(exc))
                return
            # 현역을 살려 둔 채 정본 반영·각인부터 한다. 교체는 그 뒤 후보로.
            self.save(phase="PUBLISHING", apply_started=False, publish_attempts=0,
                      red_job_path=req["payload"]["job_path"], deadline=self.clock() + PUBLISH_TIMEOUT_S)
            return
        try:
            candidate = self._candidate_for(req)
        except Exception as exc:
            self.finish("check_failed", error=str(exc))
            return
        if candidate is None:
            return
        self.save(phase="DRAINING", candidate=candidate,
                  deadline=self.clock() + float(req["policy"].get("drain_timeout_s", 600)))

    def _tick_publishing(self):
        """현역은 계속 서비스한다. 정본 반영·커밋이 끝나면 그 정본에서 후보를 봉인해 교체로 넘긴다."""
        if not self._serve_tick():
            return
        s = self.state
        import generation_store as gens
        if not s.get("red_outcome"):
            done, members = self.adapter.helper("apply", s)
            self.save(helper_tree=members, apply_started=True)
            if done is None:
                if self.clock() >= s["deadline"]:
                    for member in members:
                        signal_owned(member, force=True)
                    self.finish("apply_timeout", error="정본 반영 수행자가 상한을 넘겼습니다")
                return
            if not done.get("ok"):
                from restart_red import recover_code
                recovered = recover_code(self.base, s)
                self.finish("apply_interrupted_recovered" if recovered else "apply_interrupted_manual_recovery",
                            error=done.get("error"), recovered=recovered)
                return
            result = done.get("result") or {}
            self.save(red_outcome=result)
            if not result.get("applied"):
                try:
                    from restart_red import close_rejected_job
                    close_rejected_job(self.base, s["request"]["payload"], self.state)
                except Exception as exc:
                    log(self.home, f"거절 잡 종결 표식 실패(무시): {type(exc).__name__}: {exc}")
                self.finish("apply_rejected")
                return
            s = self.state
        result = s["red_outcome"]
        if not (result.get("commit") or {}).get("success"):
            error = (result.get("commit") or {}).get("error") or "정본 반영 후 커밋 영수증이 없습니다"
            # 파일 감시가 같은 미각인 변경을 일반 개발 후보로 우회 배포하지 않게 한다.
            self.record_failed_source(gens.execution_inventory(self.code_root)["digest"], "publish_commit_failed", error)
            self.finish("publish_commit_failed", error=error)
            return
        try:
            candidate = self.prepare_candidate("red_apply", extra={"request_id": s["request"]["request_id"],
                                                                   "commit": (result.get("commit") or {}).get("commit")})
        except gens.CandidateChanged as exc:
            attempts = s.get("publish_attempts", 0) + 1
            self.save(publish_attempts=attempts)
            log(self.home, f"수리 후보 준비 재시도({attempts}): {exc}")
            if attempts >= self.candidates().MAX_SNAPSHOT_RETRIES:
                self.finish("candidate_unstable", error=str(exc))
            return
        except Exception as exc:
            self.finish("publish_check_failed", error=f"{type(exc).__name__}: {exc}")
            return
        mismatch = gens.publication_conflicts(candidate["generation_dir"], result.get("published_files") or {},
                                             result.get("deleted_files") or [])
        if mismatch:
            self.record_failed_source(candidate["source_digest"], "publish_conflict", ", ".join(mismatch))
            self.finish("publish_conflict", changed_files=mismatch,
                        error="정본 반영 뒤 같은 경로가 다시 바뀌어 후보가 수리 커밋과 다릅니다")
            return
        self.save(phase="DRAINING", candidate={**candidate, "kind": "repair"},
                  deadline=self.clock() + float(s["request"]["policy"].get("drain_timeout_s", 600)))

    def _tick_draining(self):
        s = self.state
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
        if not self.red_reservation_current():
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
            # 마지막 턴이 drain 응답 사이에 예약을 교체할 수 있다. 모든 작업이
            # 닫힌 뒤 다시 대조해야 옛 요청 때문에 현역을 멈추지 않는다.
            if not self.red_reservation_current():
                return
            shutting_down = s["request"]["operation"] == "shutdown"
            if shutting_down:
                atomic_json(self.base / "data/.intentional_shutdown", {"request_id": s["request"]["request_id"]})
            self.begin_stop(intentional=shutting_down)
        elif self.clock() >= s["deadline"]:
            if s["request"]["policy"].get("force") is True and snap is not None:
                self.begin_stop(force=True)
            else:
                self.defer("drain_deadline_or_unknown")

    def _tick_stopping(self):
        s = self.state
        intentional = (self.base / "data/.intentional_shutdown").exists()
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
        candidate = s.get("candidate") if s.get("recovery_reason") != "active_crash" else None
        if not candidate:
            candidate = _candidate_of_state(s)
        if candidate:
            import generation_store as gens
            if not gens.sealed(candidate["generation_dir"]):
                candidate = None  # 옛 체계(가변 checkout 실행)에서 넘어온 상태 — 정본에서 새로 봉인한다
        if not candidate:
            try:
                candidate = self.prepare_candidate("relaunch")
            except Exception as exc:
                self.finish("check_failed_after_stop", phase="FAILED", error=f"{type(exc).__name__}: {exc}")
                return
        self.start_generation(candidate)

    def _tick_starting(self):
        s = self.state
        import generation_store as gens
        if s.get("preparing_start"):
            try:
                candidate = self.prepare_candidate("start")
            except Exception as exc:
                self.finish("start_prepare_failed", phase="FAILED", error=f"{type(exc).__name__}: {exc}")
                return
            self.start_generation(candidate)
            return
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
                if not s.get("candidate_verified") and s.get("generation_dir"):
                    try:
                        gens.verify(s["generation_dir"])
                    except gens.GenerationCorrupt as exc:
                        self.save(phase="RECOVERING", recovery_reason="boot_artifact_changed", error=str(exc))
                        return
                    self.save(candidate_verified=True)
                self.spawn_attempted = self.clock()
                self.adapter.spawn(self.state)
            return
        if receipt != s.get("worker"):
            self.save(worker=receipt)
        self.adapter.permit(self.state)
        snap = self.observe()
        if snap is not None and snap.get("readiness") in {"ready", "degraded"}:
            if (s.get("request") or {}).get("operation") in {"red_apply", "red_verify"}:
                done, members = self.adapter.helper("verify", self.state)
                self.save(helper_tree=members)
                if done is None:
                    return
                verified = bool(done.get("ok") and done.get("result", {}).get("verified"))
                if not verified and not s.get("rollback_attempted"):
                    self.save(phase="RECOVERING", recovery_reason="red_verification_failed")
                    return
                if not verified:
                    # 직전 세대로 복구한 뒤의 검증 영수증은 기록용이다 — 복구 세대를 다시 복구하지 않는다.
                    log(self.home, f"복구 세대 검증 영수증 미확인(기록만): {done}")
            if (self.base / "data/.intentional_shutdown").exists():
                return
            self.adapter.command(self.state, "activate")
            outcome = "rolled_back" if self.state.get("rollback_attempted") else "restarted"
            self.finish(outcome)
            self._prune_generations()
        elif self.clock() >= s["deadline"] or (snap and snap.get("readiness") == "failed"):
            self.save(phase="RECOVERING", recovery_reason="boot_failed")

    def _tick_recovering(self):
        s = self.state
        reason = s.get("recovery_reason")
        # 실제 사망을 확인한 경우에만 기록한 자식을 정리하고 같은 세대를 다시 띄운다.
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
        failed = {"code_digest": s.get("code_digest"), "source_digest": s.get("source_digest"), "reason": reason}
        if s.get("rollback_attempted"):
            self.finish("recovery_unavailable", phase="FAILED", note=reason, failed_candidate=failed)
            return
        previous = s.get("previous") or {}
        import generation_store as gens
        try:
            usable = bool(previous.get("generation_dir")) and bool(gens.verify(previous["generation_dir"]))
        except gens.GenerationCorrupt as exc:
            log(self.home, f"직전 세대 손상: {exc}")
            usable = False
        if not usable:
            self.finish("recovery_unavailable", phase="FAILED", note=reason, failed_candidate=failed)
            return
        if s.get("source_digest"):
            self.record_failed_source(s["source_digest"], reason, "교체 후 실패 — 직전 세대로 복구")
        # 커밋되지 않은 직접 RED 쓰기(red_verify)는 백업에서 정본 바이트도 되돌린다(해시가 맞을 때만).
        # 각인된 수리(red_apply)는 되감지 않는다 — 정본 취소는 타인 변경을 보존하는 후속 커밋의 몫이다.
        canonical_recovered = None
        req = s.get("request") or {}
        committed = ((s.get("red_outcome") or {}).get("commit") or {}).get("success")
        if req.get("operation") == "red_verify" or (req.get("operation") == "red_apply" and not committed):
            from restart_red import recover_code
            canonical_recovered = recover_code(self.base, s)
        self.save(recovery_stopping=False, failed_candidate=failed, canonical_recovered=canonical_recovered)
        self.start_generation({"generation": previous["code_digest"], "generation_dir": previous["generation_dir"],
                               "source_digest": previous.get("source_digest"), "reason": "rollback"}, rollback=True)

    # ── 제어 기반 갱신(G6) ────────────────────────────────────────────────────
    def _control_watch(self):
        if self.clock() - self.last_control_watch < CONTROL_WATCH_S or not self.control_base_id:
            return
        self.last_control_watch = self.clock()
        try:
            import control_base
            inv = control_base.inventory(self.code_root)
        except Exception as exc:
            log(self.home, f"제어 기반 감시 실패(무시): {exc}")
            return
        if inv["digest"] == self.control_base_id:
            return
        update = self.state.get("control_update") or {}
        if update.get("digest") == inv["digest"] and update.get("status") in {"failed", "takeover_failed"}:
            return  # 같은 입력을 반복하지 않는다
        self.save(control_update={"digest": inv["digest"], "status": "preparing", "at": self.clock()})
        new_id, note = control_base.ensure(self.code_root, self.base, support_root=self.state.get("generation_dir") or self.code_root)
        if not new_id:
            self.save(control_update={"digest": inv["digest"], "status": "failed", "note": note, "at": self.clock()})
            log(self.home, f"제어 기반 갱신 실패 — 현재 기반 유지: {note[:300]}")
            return
        self.handover(new_id)

    def handover(self, new_id):
        """검증된 새 제어 기반에 소유권을 넘긴다. 새 제어자가 상태를 인수하지 못하면 내가 계속 소유한다."""
        import control_base
        token = secrets.token_hex(16)
        self.save(control_handover={"to": new_id, "from": self.control_base_id, "token": token, "at": self.clock()})
        script = control_base.base_dir(self.base, new_id) / "backend/services/restart_controller.py"
        env = dict(os.environ, INDIEBIZ_BASE_PATH=str(self.base))
        with (self.base / "data/backend_runtime.log").open("ab") as out:
            child = subprocess.Popen([sys.executable, str(script), "serve", "--code-root", str(self.code_root),
                                      "--takeover", token], stdout=out, stderr=out,
                                     start_new_session=os.name != "nt", env=env)
        log(self.home, f"제어 기반 인계 시작 → {new_id} pid={child.pid}")
        self.lock.close()
        deadline = time.monotonic() + HANDOVER_WAIT_S
        while time.monotonic() < deadline:
            observed = read_json(self.home / "state.json", {}) or {}
            if observed.get("control_base") == new_id and not observed.get("control_handover"):
                log(self.home, f"제어 기반 인계 완료 → {new_id}; 이전 제어자 종료")
                raise SystemExit(0)
            if child.poll() is not None:
                break
            time.sleep(0.2)
        # 인계 실패 — 잠금을 되찾고 계속 소유한다. 새 기반은 실패로 기록한다.
        while not self.lock.acquire():
            if child.poll() is None and time.monotonic() > deadline + HANDOVER_WAIT_S:
                log(self.home, "인계 대상이 잠금을 쥔 채 인수를 끝내지 않음 — 양보")
                raise SystemExit(0)
            time.sleep(0.1)
        self.state = read_json(self.home / "state.json") or self.state
        note = f"takeover_failed rc={child.poll()}"
        control_base.mark_failed(self.base, new_id, note)
        self.save(control_handover=None, controller=identity(os.getpid()),
                  control_update={"digest": new_id, "status": "takeover_failed", "note": note, "at": self.clock()})
        log(self.home, f"제어 기반 인계 실패 — 이전 기반 {self.control_base_id} 유지: {note}")

    def _takeover(self, token):
        handover = self.state.get("control_handover") or {}
        if not handover or handover.get("token") != token:
            log(self.home, "인계 토큰 불일치 — 인수 거절")
            return False
        if os.environ.get("INDIEBIZ_CONTROL_TAKEOVER_FAULT"):
            log(self.home, "인수 장애 주입(INDIEBIZ_CONTROL_TAKEOVER_FAULT) — 인수 거절")
            return False
        if self.state.get("version", STATE_VERSION) > STATE_VERSION:
            log(self.home, "상태 프로토콜이 이 제어자보다 새롭다 — 인수 거절")
            return False
        backup = self.home / f"state.pre-{handover.get('to')}.json"
        atomic_json(backup, self.state)
        import control_base
        current = control_base.read_current(self.base)
        if current.get("current") != handover.get("to"):
            control_base.write_current(self.base, {**current, "previous": current.get("current"),
                                                   "current": handover.get("to"), "updated_at": time.time()})
        self.save(control_handover=None, control_base=handover.get("to"),
                  control_update={"digest": handover.get("to"), "status": "active", "at": self.clock()})
        log(self.home, f"제어 기반 인수 완료 {handover.get('from')} → {handover.get('to')}; 상태 사본 {backup.name}")
        return True

    # ── 수명 ────────────────────────────────────────────────────────────────
    def run(self, start=False, takeover=None):
        acquire_deadline = time.monotonic() + 40
        while not self.lock.acquire():
            observed = read_json(self.home / "state.json", {})
            if takeover is None and (not start or not (self.base / "data/.intentional_shutdown").exists()):
                if start and observed.get("phase") == "FAILED":
                    request(self.base, "explicit_start_retry")
                log(self.home, f"owner.lock 보유자 있음 — 양보하고 종료(start={start}, phase={observed.get('phase')}, "
                               f"controller={observed.get('controller')})")
                return 0
            if time.monotonic() >= acquire_deadline:
                log(self.home, "owner.lock 대기 40초 초과 — 종료(2)")
                return 2
            time.sleep(0.05)
        # 잠금 대기 중 이전 제어자가 남긴 최종 상태를 다시 읽는다.
        self.state = read_json(self.home / "state.json") or self.state
        exit_note = "STOPPED 도달"
        try:
            if takeover is not None and not self._takeover(takeover):
                return 5
            previous = controller_presence(self.base, self.state)
            log(self.home, f"제어자 시작 start={start} phase={self.state.get('phase')} generation={self.state.get('generation')} "
                           f"기반={self.control_base_id} 이전 제어자={previous['controller']} 생존={previous['controller_alive']} "
                           f"상태 나이={previous['state_age_s']}s stdout={_stdout_target()}")
            if previous["verdict"] == "controller_missing":
                # 이전 제어자가 기록 없이 사라진 경우다. 영속 상태를 그대로 입양한다(새 세대 아님).
                log(self.home, f"이전 제어자 pid={previous['controller'].get('pid')} 가 종료 기록 없이 사라졌다 "
                               f"(마지막 상태 갱신 {previous['state_age_s']}s 전, 워커 생존={previous['worker_alive']}) — 입양")
            legacy = read_json(self.home / "legacy.json")
            adopt_legacy = (self.state["phase"] == "STOPPED" and legacy
                            and self.adapter.alive(legacy.get("worker"))
                            and self.adapter.alive(legacy.get("serving_worker")))
            owner = {"controller": identity(os.getpid()), "shutdown_drain": True,
                     "control_base": self.control_base_id or self.state.get("control_base")}
            if start and self.state["phase"] in {"STOPPED", "FAILED"} and not adopt_legacy:
                if self.adapter.alive(self.state.get("worker")):
                    return 2
                (self.base / "data/.intentional_shutdown").unlink(missing_ok=True)
                # New ownership and its boot intent are one observation. Old terminal
                # state/generation must never be attributed to the new controller.
                owner.update(phase="STARTING", generation=None, worker=None, request=None,
                             preparing_start=True, rollback_attempted=False)
            if adopt_legacy:
                owner = {**legacy, **owner, "phase": "ACTIVE"}
            self.save(**owner)
            if adopt_legacy:
                request(self.base, "legacy_takeover", request_id="takeover-" + legacy["generation"])
            keeper = self.state.get("legacy_keeper")
            if keeper and self.adapter.alive(keeper):
                # 영수증의 출생 신원을 재검증한다. 포트/이름 전수 kill을 하지 않는다.
                signal_owned(keeper)
            def shutdown(signum, frame):
                log(self.home, f"신호 {signal.Signals(signum).name} 수신 — 의도적 종료 표식 기록")
                atomic_json(self.base / "data/.intentional_shutdown", {"signal": signum})
            signal.signal(signal.SIGTERM, shutdown)
            signal.signal(signal.SIGINT, shutdown)
            if hasattr(signal, "SIGHUP"):
                # 시작한 터미널/세션이 닫혀도 제어자는 워커보다 오래 살아야 한다(워커는 새 세션이라 면역).
                # 기본 동작(무음 종료) 대신 기록하고 계속 돈다.
                signal.signal(signal.SIGHUP, lambda signum, frame: log(self.home, "신호 SIGHUP 수신 — 무시하고 계속"))
            while self.state["phase"] != "STOPPED":
                try:
                    self.tick()
                except SystemExit:
                    raise
                except Exception as exc:
                    # 관측/일시 I/O 실패는 재기동 권한이 아니다. 상태를 유지한다.
                    log(self.home, f"{self.state['phase']}: {type(exc).__name__}: {exc}\n{traceback.format_exc().rstrip()}")
                if self.state["phase"] != "STOPPED":
                    time.sleep(0.5)
            return 0
        except SystemExit as exc:
            exit_note = f"종료 요청 코드={exc.code}"
            return exc.code or 0
        except BaseException as exc:
            exit_note = f"루프 밖 예외 {type(exc).__name__}: {exc}\n{traceback.format_exc().rstrip()}"
            raise
        finally:
            log(self.home, f"제어자 종료 — {exit_note} phase={self.state.get('phase')}")
            self.lock.close()


def _stdout_target():
    """이 제어자의 stdout 이 어디로 가는지(파이프·파일·/dev/null) — 다음 무음 사망 때 시작 주체를 추적하는 지문."""
    try:
        if os.path.exists("/proc/self/fd/1"):
            return os.readlink("/proc/self/fd/1")
        import fcntl
        if hasattr(fcntl, "F_GETPATH"):
            return fcntl.fcntl(1, fcntl.F_GETPATH, b"\0" * 1024).rstrip(b"\0").decode(errors="replace")
        return "fd1"
    except Exception:
        return "closed"


def compact_status(state: dict) -> dict:
    """status 의 기본 출력 — 코드 매니페스트 두 벌은 지문과 파일 수로 접는다(전문은 --full).

    ep3855(2026-09-18): 수리 턴이 `api.py status` 한 번에 18만 자를 문맥으로 받았다 — 파일 791개의 해시 목록이
    manifest·target_manifest 로 두 번 실려 있었다. 판정에 쓰이는 것은 phase·last_result·defer_note·지문이다.
    """
    out = dict(state)
    for key in ("manifest", "target_manifest"):
        m = out.get(key)
        if isinstance(m, dict) and isinstance(m.get("files"), dict):
            out[key] = {"digest": m.get("digest"), "files": len(m.get("files") or {}), "omitted": "--full 로 전문"}
    failed = out.get("failed_sources") or {}
    if failed:
        out["failed_sources"] = {k[:12]: {"outcome": v.get("outcome"), "note": (v.get("note") or "")[:160]}
                                 for k, v in failed.items()}
    return out


def main(argv=None, code_root=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "serve", "restart", "shutdown", "status", "wait"], nargs="?", default="start")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--request-id")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--drain-timeout", type=float, default=600)
    parser.add_argument("--full", action="store_true", help="status: 코드 매니페스트 전문까지 전부")
    parser.add_argument("--code-root", help="정본(편집·git) 저장소 — 기반 사본에서 돌 때 필수")
    parser.add_argument("--takeover", help="제어 기반 인계 토큰(내부용)")
    args = parser.parse_args(argv)
    code_root = Path(args.code_root) if args.code_root else (Path(code_root) if code_root else Path(__file__).resolve().parents[2])
    base = Path(os.environ.get("INDIEBIZ_BASE_PATH", code_root))
    if args.action in {"start", "serve"}:
        from update_maintenance import check_start
        try:
            check_start(base)
        except ValueError as exc:
            log(control_dir(base), f"{args.action} 거절 — {exc}")
            raise
        return Controller(base, code_root).run(start=args.action == "start", takeover=args.takeover)
    if args.action == "wait":
        while read_json(control_dir(base) / "state.json", {}).get("phase") != "STOPPED":
            time.sleep(0.5)
        return 0
    if args.action == "status":
        state = read_json(control_dir(base) / "state.json", {})
        state.pop("control_token", None)
        # 죽은 pid 를 그대로 보여 주던 status — 제어자 생존을 pid+출생시각으로 판정해 맨 앞에 말한다.
        presence = controller_presence(base, state)
        state["presence"] = presence
        if presence["verdict"] == "controller_missing":
            print(f"[restart_controller] 제어자 부재: pid={(presence['controller'] or {}).get('pid')} 죽음, 워커 생존={presence['worker_alive']}, "
                  f"상태 {presence['state_age_s']}s 전 멈춤 — 요청은 처리되지 않는다. "
                  f"복구: {sys.executable} backend/api.py start (런처가 떠 있으면 자동)")
        else:
            print(f"[restart_controller] 제어자 {presence['verdict']} pid={(presence['controller'] or {}).get('pid')} "
                  f"phase={presence['phase']} 상태 나이={presence['state_age_s']}s 세대={state.get('code_digest')} "
                  f"기반={state.get('control_base')}")
        print(state if args.full else compact_status(state))
        return 3 if presence["verdict"] == "controller_missing" else 0
    req = request(base, "cli_" + args.action, operation=args.action, request_id=args.request_id,
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


if __name__ == "__main__":
    _root = Path(__file__).resolve().parents[2]
    _source = os.environ.get("INDIEBIZ_SOURCE_ROOT") or next((a for i, a in enumerate(sys.argv) if i and sys.argv[i - 1] == "--code-root"), None)
    try:
        import control_base as _cb
        _state = read_json(control_dir(Path(os.environ.get("INDIEBIZ_BASE_PATH", _source or _root))) / "state.json", {}) or {}
        _support = _state.get("generation_dir") if _state.get("generation_dir") and Path(_state["generation_dir"]).is_dir() else (_source or _root)
        _cb.install_support_path(_root, _support)
    except Exception:
        pass
    import boot_paths  # noqa: E402,F401
    raise SystemExit(main())
