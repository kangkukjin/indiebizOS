"""RED 적용/검증/복구 기능. 실행/재기동 시점은 외부 제어자만 결정한다."""
import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path

from restart_protocol import atomic_json, read_json


def reservation(job):
    """요청이 승인받은 예약 판본. 같은 경로의 다음 예약과 구분한다."""
    return {k: job.get(k) for k in ("key", "task_id", "scheduled_at", "readiness_hash")}


def request_id(job):
    return "red-" + hashlib.sha256((job["key"] + job["scheduled_at"]).encode()).hexdigest()[:40]


def inspect_job(base, path, expected=None):
    root, path = Path(base).resolve(), Path(path).resolve()
    if not path.is_relative_to(root / "data/system_ai_state/repair_sessions"):
        raise ValueError("RED 잡이 예약 디렉토리 밖에 있습니다")
    job = read_json(path)
    if not isinstance(job, dict) or Path(job.get("repo", "")).resolve() != root:
        raise ValueError("RED 잡의 저장소가 일치하지 않습니다")
    if expected is not None and (reservation(job) != expected or not all(expected.values())):
        raise ValueError("RED 적용 요청의 예약 판본이 교체됐습니다")
    if expected is not None:
        session = read_json(path.with_name(job["key"] + ".json")) or {}
        if (session.get("scheduled_at") != job["scheduled_at"]
                or session.get("status") not in {"apply_scheduled", "applying", "applied"}):
            raise ValueError("RED 적용 세션의 예약 판본이 취소·교체됐습니다")
    return job


def manifest_path(base, req):
    payload = req.get("payload", {})
    if payload.get("manifest_path"):
        path = Path(payload["manifest_path"]).resolve()
        if not path.is_relative_to(Path(base).resolve() / "data/system_ai_state/red_backups"):
            raise ValueError("RED 백업 경로 오류")
        return path
    job = inspect_job(base, payload["job_path"], payload.get("reservation"))
    key = re.sub(r"[^A-Za-z0-9_-]", "_", job.get("task_id") or job["key"])[:48]
    return Path(base) / "data/system_ai_state/red_backups" / key / "manifest.json"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None


def apply_job(base, path, expected=None):
    from red_apply import _load_handler
    from red_grant import issue_grant
    from thread_context import actor_context
    job = inspect_job(base, path, expected)
    handler = _load_handler(job)
    staging = handler._staging_mod()
    session = staging.read_session(str(base), job["key"]) or {}
    if expected is not None and session.get("scheduled_at") != job["scheduled_at"]:
        return {"success": False, "applied": False, "error": "적용 세션의 예약 판본이 교체됐습니다"}
    if (not job.get("readiness_hash") or
            job["readiness_hash"] != staging._candidate.digest(session.get("readiness"))):
        return {"success": False, "applied": False, "error": "예약의 준비 판정이 없거나 변경됐습니다"}
    task_id, agent_id = job.get("task_id") or job["key"], job.get("agent_id") or "system_ai"
    with actor_context(agent_id=agent_id, task_id=task_id):
        issue_grant(agent_id=agent_id, task_id=task_id, reason=job.get("reason") or "예약 적용")
        def prepare(target, content=None):
            error = handler._red_write_prepare(target, content)
            if error:
                return error
            path = manifest_path(base, {"payload": {"job_path": str(path_job)}})
            manifest = read_json(path)
            if not manifest:
                return "RED 복구 manifest를 읽을 수 없습니다"
            manifest.setdefault("target_hashes", {})[str(Path(target).resolve())] = (
                hashlib.sha256(content.encode() if isinstance(content, str) else content).hexdigest() if content is not None else None)
            manifest["restart_controller"] = True
            atomic_json(path, manifest)
        path_job = Path(path)
        out = staging.perform_scheduled_apply(str(base), job["key"], prepare=prepare, finalize=lambda path: None)
        if out.get("applied"):
            # 2026-10-27 재설계: 각인은 활성 전에 한다 — 수리 델타 반영·커밋 → 그 정본으로 세대 봉인 → 교체.
            out["commit"] = staging.commit_applied(str(base), job["key"])
            sealed = (staging.read_session(str(base), job["key"]) or {}).get("sealed") or {}
            out["published_files"] = {rel: (item.get("after") or {}).get("sha") for rel, item in sealed.items()
                                      if item.get("after")}
            out["deleted_files"] = [rel for rel, item in sealed.items() if item.get("after") is None]
        # 적용 거절도 기록한다. 이미 적용된 잡은 staging의 기존 멱등 계약을 따른다.
        job.update(controller_apply=out, applied=bool(out.get("applied")))
        atomic_json(path_job, job)
        try:
            import repair_root
            repair_root.note_publish(base, job, out)
        except Exception as exc:  # 원장 전이 실패가 적용 영수증을 지우면 안 된다
            print(f"[restart_red] 수리 root 전이 실패(무시): {type(exc).__name__}: {exc}")
        return out


def recover_code(base, state):
    req = state.get("request") or {}
    if req.get("operation") not in {"red_apply", "red_verify"}:
        return False  # 가변 checkout의 옛 바이트를 상상해서 복원하지 않는다.
    try:
        path = manifest_path(base, req)
        manifest = read_json(path)
        if not manifest or not manifest.get("files"):
            return False
        root, backup_root = Path(base).resolve(), path.parent.resolve()
        plan = []
        for target, backup in manifest["files"].items():
            target = Path(target).resolve()
            if not target.is_relative_to(root):
                return False
            backup = Path(backup).resolve() if backup else None
            if backup and (not backup.is_relative_to(backup_root) or not backup.is_file()):
                return False
            before, now = digest(backup) if backup else None, digest(target)
            after = manifest.get("target_hashes", {}).get(str(target), "unknown")
            if now not in (before, after):
                return False  # 다른 편집자의 변경/부분 쓰기 — 자동 덮어쓰기 금지
            plan.append((target, backup))
        for target, backup in plan:
            if backup is None:
                target.unlink(missing_ok=True)
            else:
                fd, temp = tempfile.mkstemp(dir=target.parent, prefix=".restore-")
                try:
                    with os.fdopen(fd, "wb") as out:
                        out.write(backup.read_bytes())
                        out.flush()
                        os.fsync(out.fileno())
                    shutil.copymode(backup, temp)
                    os.replace(temp, target)
                finally:
                    if os.path.exists(temp):
                        os.unlink(temp)
        previous = read_json(path.with_name("result.json")) or {}
        atomic_json(path.with_name("result.json"), {**previous,
            "outcome": "rolled_back", "recovered": False, "owner": manifest.get("owner", "system_ai"),
            "note": "코드 복원 완료; 새 현역 준비 확인 전", "generation": state.get("generation")})
        return True
    except (OSError, ValueError, KeyError):
        return False


def close_rejected_job(base, payload, state):
    """쓰기 전 거절(라이브 무변경)의 잡을 종결 표식(done_at)으로 닫는다. 예약 신원과 거절 영수증을 대조한다."""
    job = inspect_job(base, payload["job_path"])
    expected = payload.get("reservation")
    if expected is not None and reservation(job) != expected:
        raise ValueError("RED 적용 요청의 예약 판본이 교체됐습니다")
    if (job.get("controller_apply") or {}).get("applied") is not False:
        raise ValueError("RED 적용 거절 영수증이 일치하지 않습니다")
    job["done_at"] = state.get("updated_at")
    atomic_json(payload["job_path"], job)
    return job


def verify_after_boot(base, state):
    req = state.get("request") or {}
    if req.get("operation") not in {"red_apply", "red_verify"}:
        return True
    if (req.get("operation") == "red_apply"
            and (state.get("red_outcome") or {}).get("applied") is False):
        # 쓰기 전 거절은 세션을 staging으로 되돌린다. 이때 활성 예약을 요구하는
        # manifest_path를 호출하면 거절이 예외로 바뀌고 정상 작업자까지 죽는다.
        # 예약의 신원과 실제 적용 영수증은 계속 대조하되 원래 거절을 보존한다.
        payload = req["payload"]
        job = inspect_job(base, payload["job_path"])
        expected = payload.get("reservation")
        if expected is not None and reservation(job) != expected:
            raise ValueError("RED 적용 요청의 예약 판본이 교체됐습니다")
        if (job.get("controller_apply") or {}).get("applied") is not False:
            raise ValueError("RED 적용 거절 영수증이 일치하지 않습니다")
        job["done_at"] = state.get("updated_at")
        atomic_json(payload["job_path"], job)
        return False
    from red_watchdog import _touches_safety, _run_safety_selftest
    path = manifest_path(base, req)
    manifest = read_json(path)
    if not manifest:
        return not (state.get("red_outcome") or {}).get("applied")
    if _touches_safety(manifest):
        ok, detail = _run_safety_selftest(str(base))
        if not ok:
            return False
    result = {"outcome": "rolled_back" if state.get("rollback_attempted") else "healthy",
              "recovered": True, "generation": state["generation"],
              "owner": manifest.get("owner", "system_ai"), "files": list(manifest.get("files", {}))}
    if req.get("operation") == "red_apply":
        from red_apply import _run_post_verify, _load_handler
        job = inspect_job(base, req["payload"]["job_path"], req["payload"].get("reservation"))
        applied = job.get("controller_apply") or {}
        if applied.get("verified") is False and not state.get("rollback_attempted"):
            atomic_json(path.with_name("result.json"), dict(
                result, outcome="verification_failed", recovered=False,
                error=applied.get("error"), checks=applied.get("checks", [])))
            return False
        cmd = job.get("verify_cmd", "").strip()
        # 롤백은 검증 실패를 없애지 않는다. 복구 부팅 때 None으로 덮어쓰면
        # 이어받은 실행자가 실패 원인을 읽을 수 없고 같은 수리를 반복하게 된다.
        post = (job.get("post_verify") if state.get("rollback_attempted") else
                _run_post_verify(str(base), cmd) if cmd else None)
        result["post_verify"] = post
        result["checks"] = applied.get("checks", [])
        result["error"] = applied.get("error")
        staging = _load_handler(job)._staging_mod()
        staging.write_followup(str(base), staging.task_key(job["key"]), {
            "wait_outcome": "controller_drained", "quiesce_outcome": "observed",
            "post_verify": post, "generation": state["generation"]})
        job.update(done_at=state.get("updated_at"), post_verify=post)
        atomic_json(req["payload"]["job_path"], job)
        if post is not None and post.get("exit_code") != 0 and not state.get("rollback_attempted"):
            atomic_json(path.with_name("result.json"), dict(
                result, outcome="verification_failed", recovered=False, post_verify=post))
            return False
    atomic_json(path.with_name("result.json"), result)
    return True


def record_interrupted(base, snapshot, reason):
    ids = snapshot.get("live_episode_ids") or []
    if not ids:
        return
    from episode_logger import close_cut_episodes
    close_cut_episodes(ids, reason, db_path=str(Path(base) / "data/world_pulse.db"))
