"""개발 저장·수리 반영을 봉인 세대 후보로 바꾸는 준비 서비스. 현역 프로세스는 건드리지 않는다.

설계 정본: docs/SELF_REPAIR_SYSTEM_REDESIGN_2026_10_27.md §5.2 (일반 개발 자동 반영) · §5.3 (자기수리).

흐름: 파일 저장 → 변경 회수(정착 대기) → 스냅샷 봉인 → 사전검사(바이트·구문) → 교체 요청.
실패는 종류별로 다르게 남는다:
  - 복사 중 변경(CandidateChanged): 후보를 게시하지 않고 다음 tick 에 다시 회수한다.
  - 사전검사 실패: 그 원천 지문을 failed_sources 에 적고 현역을 유지한다. 같은 입력은 다시 시도하지 않는다.
"""
import time
from pathlib import Path

import generation_store as gens
from restart_protocol import control_dir

QUIET_S = 2.0            # 마지막 변경 관측 뒤 이만큼 조용해야 스냅샷한다(편집기의 다중 파일 저장 창)
WATCH_INTERVAL_S = 2.0   # 정본 재고 주기
MAX_SNAPSHOT_RETRIES = 10


def store_dir(base):
    return control_dir(base) / "generations"


def prepare(base, source_root, *, reason, inventory=None, extra=None):
    """정본 작업 트리 → 봉인 세대 + 사전검사. 반환 후보 dict. 예외는 호출자가 종류별로 처리한다."""
    manifest = gens.snapshot(source_root, store_dir(base), source_inventory=inventory,
                             extra={"reason": reason, **(extra or {})})
    gen_dir = store_dir(base) / manifest["generation"]
    gens.syntax_check(gen_dir, manifest)
    return {"generation": manifest["generation"], "generation_dir": str(gen_dir),
            "source_digest": manifest["source_digest"], "reason": reason,
            "file_count": manifest.get("file_count"), "prepared_at": time.time(),
            "environment": (manifest.get("environment") or {}).get("isolation")}


def verify_candidate(candidate, *, files=None):
    """교체 직전·spawn 직전 사본 바이트가 봉인 때와 같은지 확인한다."""
    return gens.verify(candidate["generation_dir"], files=files)


class Watcher:
    """ACTIVE 에서만 도는 정본 변경 감시. 상태는 제어자 state 의 watch 칸에 영속한다."""

    def __init__(self, controller):
        self.controller = controller
        self.last_scan = 0.0
        self.last_digest = None

    def tick(self):
        """변경이 정착했으면 후보를 준비해 교체 요청을 발급한다. 반환: 발급한 요청 또는 None."""
        ctl = self.controller
        now = ctl.clock()
        if now - self.last_scan < WATCH_INTERVAL_S:
            return None
        self.last_scan = now
        state = ctl.state
        inventory = gens.execution_inventory(ctl.code_root)
        digest = inventory["digest"]
        watch = dict(state.get("watch") or {})
        if digest == state.get("source_digest"):
            if watch:
                ctl.save(watch={})
            return None
        failed = (state.get("failed_sources") or {}).get(digest)
        candidate = state.get("candidate") or {}
        if failed or candidate.get("source_digest") == digest:
            return None  # 같은 입력의 실패를 반복하지 않는다 / 이미 준비한 후보다
        if watch.get("digest") != digest:
            ctl.save(watch={"digest": digest, "since": now, "attempts": 0})
            return None
        if now - watch["since"] < QUIET_S:
            return None
        try:
            prepared = prepare(ctl.base, ctl.code_root, reason="development_files", inventory=inventory)
        except gens.CandidateChanged as exc:
            attempts = watch.get("attempts", 0) + 1
            ctl.save(watch={"digest": digest, "since": now, "attempts": attempts})
            ctl.log_line(f"후보 준비 재시도({attempts}): {exc}")
            if attempts >= MAX_SNAPSHOT_RETRIES:
                ctl.record_failed_source(digest, "candidate_unstable", str(exc))
                ctl.save(watch={})
            return None
        except Exception as exc:  # 구문 오류·복사 실패 — 현역 유지, 같은 입력 재시도 금지
            ctl.record_failed_source(digest, "check_failed", f"{type(exc).__name__}: {exc}")
            ctl.save(watch={})
            return None
        from restart_protocol import request
        rid = "files-" + state["generation"] + "-" + prepared["generation"][:24]
        req = request(ctl.base, "development_files", request_id=rid,
                      artifact_digest=prepared["generation"],
                      payload={"generation_dir": prepared["generation_dir"],
                               "source_digest": prepared["source_digest"], "kind": "development"})
        ctl.save(candidate={**prepared, "kind": "development", "request_id": rid}, watch={})
        ctl.log_line(f"개발 후보 준비 완료 generation={prepared['generation']} 요청 {rid}")
        return req


def prune(base, source_root, keep, log=lambda m: None):
    return gens.prune(store_dir(base), keep, source_root=source_root, log=log)
