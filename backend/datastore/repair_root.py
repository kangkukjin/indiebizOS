"""수리 root 원장 — 요청 하나를 접수에서 완료까지 소유하는 단일 전이 계약(G3·G5).

설계 정본: docs/SELF_REPAIR_SYSTEM_REDESIGN_2026_10_27.md §7.1.

기존 repair_sessions(사본 상태)·repair_continuations(인계)·restart_control(제어자 결과)·red_backups(결과)는
각자 책임이 다른 증거로 남는다. 이 원장은 그 증거들을 다시 해석하는 소비자들을 대신해 **현재 단계·시도·
소유자·다음 행동·재개 조건**을 한 곳에 쓰고, 소비자는 projection() 을 읽는다.

단계: diagnose → prepare → check → publish → deploy_wait → activate → verify_active → complete
결과(outcomes)는 직교한다: repair(수리 자체) · service(서비스 건강) · delivery(사용자 전달).
전이는 파일 잠금 + revision 검사 + fencing token 으로 쓴다. 늦은 응답은 새 상태를 덮지 못한다.
"""
import hashlib
import json
import re
import time
from pathlib import Path

from restart_protocol import OwnerLock, atomic_json, read_json

STAGES = ["diagnose", "prepare", "check", "publish", "deploy_wait", "activate", "verify_active", "complete"]
TERMINAL = {"complete", "incomplete", "cancelled"}
HISTORY_LIMIT = 60


class StaleOwner(RuntimeError):
    """이전 소유자의 늦은 전이 — 현재 소유자의 상태를 덮지 않는다."""


class StaleRevision(RuntimeError):
    """기대한 revision 과 다르다 — 호출자는 다시 읽고 판단한다."""


def key(task):
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(task or ""))[:48] or "notask"


def directory(base):
    return Path(base) / "data" / "system_ai_state" / "repair_roots"


def path_of(base, root_id):
    return directory(base) / (key(root_id) + ".json")


def read(base, root_id):
    row = read_json(path_of(base, root_id))
    return row if row and row.get("root_id") == root_id else None


def _new(root_id, request):
    now = time.time()
    return {"version": 1, "root_id": root_id, "revision": 0, "created_at": now, "updated_at": now,
            "request": dict(request or {}), "stage": "diagnose", "stage_revision": 0, "attempt": 1,
            "owner": None, "candidate": {}, "artifact": {}, "criteria": {},
            "outcomes": {"repair": "in_progress", "service": "unknown", "delivery": "not_needed"},
            "evidence": {}, "next_action": "같은 사본에서 진단·수정·관련 검사를 진행한다",
            "resume_condition": None, "reason": None, "history": [], "cost": {"model_calls": 0, "resumes": 0}}


def _locked(base, root_id):
    lock = OwnerLock(path_of(base, root_id).with_suffix(".lock"))
    deadline = time.monotonic() + 10
    while not lock.acquire():
        if time.monotonic() > deadline:
            raise TimeoutError("수리 root 잠금 대기 초과: " + root_id)
        time.sleep(0.02)
    return lock


def open_root(base, root_id, request=None):
    """없으면 만든다(멱등). 있으면 요청 원문을 보존한 채 그대로 돌려준다."""
    lock = _locked(base, root_id)
    try:
        row = read(base, root_id)
        if row:
            return row
        row = _new(root_id, request)
        atomic_json(path_of(base, root_id), row)
        return row
    finally:
        lock.close()


def claim(base, root_id, kind, ttl_s=1800):
    """단계 소유권 — fencing token. 만료 전 다른 소유자의 전이는 StaleOwner."""
    token = hashlib.sha256(f"{root_id}:{kind}:{time.time()}:{id(object())}".encode()).hexdigest()[:24]
    transition(base, root_id, owner={"kind": kind, "token": token, "expires_at": time.time() + ttl_s})
    return token


def transition(base, root_id, *, expected_revision=None, fence=None, stage=None, outcome=None,
               service=None, delivery=None, evidence=None, next_action=None, resume_condition=None,
               reason=None, owner=None, candidate=None, artifact=None, criteria=None, cost=None,
               note=None, request=None):
    """원장 한 건의 원자 전이. 변경 내용은 history 에 남고 revision 이 1 오른다."""
    lock = _locked(base, root_id)
    try:
        row = read(base, root_id) or _new(root_id, request)
        if expected_revision is not None and row["revision"] != expected_revision:
            raise StaleRevision(f"revision {row['revision']} != {expected_revision}")
        current = row.get("owner") or {}
        if (current.get("token") and fence is not None and fence != current["token"]
                and current.get("expires_at", 0) > time.time()):
            raise StaleOwner("다른 소유자의 단계입니다: " + str(current.get("kind")))
        if row["stage"] in TERMINAL and stage and stage not in TERMINAL and stage != row["stage"]:
            # 종결 뒤 재개는 새 시도다(사용자 재요청·환경 복구 재개).
            row["attempt"] = row.get("attempt", 1) + 1
            row["cost"]["resumes"] = row.get("cost", {}).get("resumes", 0) + 1
        change = {}
        if stage and stage != row["stage"]:
            if stage not in STAGES and stage not in TERMINAL:
                raise ValueError("알 수 없는 단계: " + str(stage))
            row["stage"], row["stage_revision"] = stage, row.get("stage_revision", 0) + 1
            change["stage"] = stage
        if outcome is not None:
            row["outcomes"]["repair"] = outcome
            change["repair"] = outcome
        if service is not None:
            row["outcomes"]["service"] = service
            change["service"] = service
        if delivery is not None:
            row["outcomes"]["delivery"] = delivery
            change["delivery"] = delivery
        for name, value in (("candidate", candidate), ("artifact", artifact), ("criteria", criteria)):
            if value is not None:
                row[name] = {**row.get(name, {}), **value}
                change[name] = value
        if evidence is not None:
            row["evidence"] = {**row.get("evidence", {}), **evidence}
            change["evidence"] = sorted(evidence)
        if cost:
            for k, v in cost.items():
                row["cost"][k] = row["cost"].get(k, 0) + v
        if owner is not None:
            row["owner"] = owner or None
        if next_action is not None:
            row["next_action"] = next_action
        if stage == "complete":
            row["resume_condition"] = None  # 완료는 재개 조건을 남기지 않는다
        elif resume_condition is not None or (stage in TERMINAL and stage != "complete"):
            row["resume_condition"] = resume_condition
        if reason is not None:
            row["reason"] = reason
        row["revision"] += 1
        row["updated_at"] = time.time()
        row["history"] = (row.get("history") or [])[-(HISTORY_LIMIT - 1):] + [
            {"at": row["updated_at"], "revision": row["revision"], "change": change, "note": note,
             "fence": (fence or "")[:8] or None}]
        atomic_json(path_of(base, root_id), row)
        return row
    finally:
        lock.close()


def projection(base, root_id):
    """소비자가 읽는 투영. 자체 판정 대신 이 값을 쓴다."""
    row = read(base, root_id)
    if not row:
        return None
    outcomes = row.get("outcomes", {})
    stage = row.get("stage")
    return {"root_id": root_id, "stage": stage, "attempt": row.get("attempt"), "revision": row.get("revision"),
            "complete": stage == "complete", "terminal": stage in TERMINAL,
            "repair_outcome": outcomes.get("repair"), "service_health": outcomes.get("service"),
            "delivery_status": outcomes.get("delivery"), "next_action": row.get("next_action"),
            "resume_condition": row.get("resume_condition"), "reason": row.get("reason"),
            "artifact": row.get("artifact", {}), "candidate": row.get("candidate", {}),
            "symptom_recheck": (row.get("evidence") or {}).get("symptom_recheck"),
            "updated_at": row.get("updated_at")}


def root_of_session(session):
    return (session or {}).get("root_task_id") or (session or {}).get("key")


# ── 생산자별 이음새 ──────────────────────────────────────────────────────────

def note_prepared(base, session, approval):
    """op_apply: 준비(prepare)·검사(check) 결과."""
    root_id = root_of_session(session)
    if not root_id:
        return None
    open_root(base, root_id, {"task_id": session.get("key"), "owner": session.get("owner"),
                              "goal": (session.get("readiness") or {}).get("criteria", {}).get("user_goal")})
    ready = session.get("readiness") or {}
    if approval.get("success"):
        return transition(base, root_id, stage="check", outcome="checks_passed",
                          candidate={"session_key": session.get("key"), "candidate_hash": ready.get("candidate_hash"),
                                     "bundle_hash": ready.get("bundle_hash"), "worktree": session.get("worktree")},
                          criteria={"hash": ready.get("criteria_hash"), "coverage": (ready.get("decision") or {}).get("workspace_coverage")},
                          evidence={"regression": ready.get("regression_evidence"),
                                    "test_weakening": ready.get("test_weakening")},
                          next_action="검증한 묶음을 정본에 반영한다(예약 또는 즉시)")
    return transition(base, root_id, stage="prepare", outcome="check_failed",
                      reason=approval.get("error"), evidence={"preparation": {k: approval.get(k) for k in
                                                                           ("stage", "missing_criteria", "changed_files") if k in approval}},
                      next_action="같은 사본에서 실패 부분을 고치고 영향 검사를 다시 실행한다")


def note_scheduled(base, session, job):
    root_id = root_of_session(session)
    if not root_id:
        return None
    return transition(base, root_id, stage="deploy_wait", outcome="scheduled",
                      candidate={"job_path": str(job.get("_path") or ""), "scheduled_at": job.get("scheduled_at"),
                                 "restart_request_id": job.get("restart_request_id")},
                      next_action="실행 구간을 닫는다. 제어자가 정본 반영·각인·세대 교체를 소유한다")


def _read_session(base, task_key):
    """수리 세션 원장 한 줄 읽기 — 패키지 handler 를 적재하지 않는다(층 가드: data 층은 ibl/services 를 모른다)."""
    return read_json(Path(base) / "data" / "system_ai_state" / "repair_sessions" / (key(task_key) + ".json"), {}) or {}


def note_publish(base, job, out):
    """restart_red.apply_job: 정본 반영·각인 결과."""
    session = _read_session(base, job["key"])
    root_id = root_of_session(session) or job.get("task_id") or job["key"]
    commit = (out.get("commit") or {})
    if out.get("applied") and commit.get("success"):
        return transition(base, root_id, stage="publish", outcome="published",
                          artifact={"commit": commit.get("commit"), "published_files": out.get("published_files")},
                          evidence={"apply": {"files": out.get("files"), "removed": out.get("removed")}},
                          next_action="제어자가 이 정본으로 세대를 봉인하고 교체한다")
    if out.get("applied"):
        return transition(base, root_id, stage="publish", outcome="published_uncommitted",
                          reason=str(commit.get("error") or commit.get("message") or "각인 영수증 없음"),
                          evidence={"apply": {"files": out.get("files")}},
                          next_action="각인만 회수한다. 정본 반영은 유지한다")
    return transition(base, root_id, stage="check", outcome="apply_rejected", reason=out.get("error"),
                      next_action="거절 사유를 보고 같은 후보를 재조정한 뒤 다시 검증한다")


def note_controller_result(base, job_path, result, state):
    """제어자 finish(): 활성/복구/거절 결말. 서비스 건강은 독립 결과다."""
    job = read_json(job_path) or {}
    if not job:
        return None
    root_id = job.get("root_task_id") or job.get("task_id") or job.get("key")
    session = _read_session(base, job.get("key") or "")
    root_id = root_of_session(session) or root_id
    outcome = result.get("outcome")
    artifact = {"generation": result.get("code_digest"), "generation_dir": result.get("generation_dir"),
                "runtime_generation": result.get("generation")}
    if outcome == "restarted":
        return transition(base, root_id, stage="activate", outcome="active", service="active_new_generation",
                          artifact=artifact, next_action="활성 세대에서 원 증상·활성 확인을 수행한다")
    if outcome == "rolled_back":
        return transition(base, root_id, stage="activate", outcome="activation_failed", service="recovered_previous",
                          artifact=artifact, reason=result.get("note") or "새 세대 활성 실패 — 직전 세대 복구",
                          next_action="보존된 검사 출력과 실패 후보를 보고 같은 사본에서 수정한다",
                          resume_condition="후보를 수정해 다시 검증·적용하면 재개")
    if outcome in {"apply_rejected", "publish_conflict", "candidate_unstable", "publish_check_failed"}:
        return transition(base, root_id, stage="check", outcome=outcome, service="unchanged_active",
                          reason=result.get("error"), next_action="거절 사유에 따라 같은 후보를 재조정한다",
                          resume_condition="정본 충돌·입력 변경이 해소되면 재검증")
    if outcome == "publish_commit_failed":
        return transition(base, root_id, stage="publish", outcome=outcome, service="unchanged_active",
                          reason=result.get("error"), next_action="커밋 실패 원인을 해소하고 기존 반영 영수증에서 각인만 회수한다",
                          resume_condition="수리 델타의 커밋 성공 후 후보를 다시 준비한다")
    if outcome in {"apply_interrupted_recovered", "apply_interrupted_manual_recovery", "apply_timeout"}:
        return transition(base, root_id, stage="publish", outcome=outcome, service="unchanged_active",
                          reason=result.get("error"),
                          next_action="실제 파일·커밋 영수증을 대조한 뒤 필요한 단계만 다시 한다",
                          resume_condition="수행자 재실행은 영수증 대조 후에만")
    if outcome in {"deferred", "stale_generation", "check_failed"}:
        return transition(base, root_id, stage="deploy_wait", outcome=outcome, reason=result.get("error") or result.get("note"),
                          next_action="제어자 결과를 보고 재예약 또는 재검증한다")
    return transition(base, root_id, outcome=outcome, reason=result.get("error"))


def note_active_check(base, root_id, field, record):
    state = (record or {}).get("state")
    return transition(base, root_id, stage="verify_active",
                      outcome="active_checks_passed" if state == "passed" else "active_check_failed",
                      evidence={"active_" + field: {k: (record or {}).get(k) for k in ("state", "command_sha256", "output_path")}},
                      next_action="완료 영수증을 조합한다" if state == "passed" else "실패한 활성 검사의 출력을 보고 수정한다")


def close(base, root_id, *, complete, reason, symptom_recheck=None, resume_condition=None, evidence=None):
    """완료 또는 명시적 미완료로 닫는다. 전달은 별도 결과다."""
    return transition(base, root_id, stage="complete" if complete else "incomplete",
                      outcome="completed" if complete else "incomplete", reason=reason,
                      evidence={**(evidence or {}), **({"symptom_recheck": symptom_recheck} if symptom_recheck else {})},
                      resume_condition=None if complete else (resume_condition or "원인을 해소한 뒤 같은 root 로 재개"),
                      next_action="없음" if complete else "재개 조건을 충족한 뒤 필요한 단계만 재개")


def note_delivery(base, root_id, status, event_id=None, error=None):
    """전달 결과만 바꾼다. 완료 기록을 되돌리지 않는다."""
    return transition(base, root_id, delivery=status,
                      evidence={"delivery": {"event_id": event_id, "error": (error or "")[:300], "at": time.time()}},
                      note="delivery:" + status)


def delivery_event_id(root_id, text):
    return hashlib.sha256((root_id + ":" + text).encode()).hexdigest()[:24]
