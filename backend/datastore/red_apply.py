"""
red_apply.py - 지연 적용 수행자 (분리 프로세스, 2026-08-19)

★왜: [self:patch]{op:"apply"} 가 backend/*.py 를 그 자리에서 쓰면 uvicorn 리로드
(reload_delay 2초)가 **그 턴을 실행 중인 워커를 죽인다** — 최종 응답, 주행기록의
로그 버퍼(END 저장 전까지 메모리에만 있다), 증류 데몬 스레드가 전부 그 워커 안에
산다. 검증(격리 워크트리)은 턴 안에서 이미 끝났으므로, 여기는 **쓰기만** 맡는다:

  ①턴이 완전히 닫히기를 기다린다 — 주행기록 ended_at(=응답 전송·버퍼 저장 완료)
    → 증류 재합류(cognitive_distill 의 finally 가 refresh_episode 로 log 를 한 번
    다시 쓴다 — 그 길이 변화가 신호)
  ②쓰기 직전 재검증한다 — 예약~수행 사이의 라이브 드리프트까지 live_sync 가 맞춘다
  ③라이브에 쓰고 워치독(red_watchdog)에게 헬스 판정·자동 롤백을 넘긴다

"자기 죽음 이후에 실행돼야 하는 단계는 죽음을 넘는 프로세스가 맡는다"(라이브 백엔드
편집 규약, 2026-08-17 개정)의 적용-단계 판이다. 판정 보고는 다음 턴(red_report).

★그랜트: red_grant 는 인메모리 싱글턴이라 이 프로세스에서의 재발급은 이 프로세스에만
존재한다 — 턴에서 검증된 그랜트가 잡 파일로 이월된 것이지 새 권한 발급이 아니다
(워치독이 그랜트 없이 백업을 복원하는 것과 같은 부류: 능력은 파일이 나른다).

사용: python3 red_apply.py <job.json>
잡: {"key","repo","episode_id","task_id","agent_id","reason","scheduled_at","handler_path"}
코드 루트=이 파일의 저장소(sys.path·handler 폴백) / 데이터 루트=job["repo"] — 테스트의
가짜 저장소에서 둘이 갈라진다(배터리 S10).
"""
import importlib.util
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent.parent.parent   # backend/datastore/ → repo

# 대기 상한 — 환경변수는 테스트 심(배터리가 유예 0으로 줄인다)
TURN_CLOSE_CAP_S = float(os.environ.get("RED_APPLY_TURN_CAP_S", 900))
DISTILL_GRACE_S = float(os.environ.get("RED_APPLY_DISTILL_GRACE_S", 120))
NO_EPISODE_GRACE_S = float(os.environ.get("RED_APPLY_NO_EPISODE_GRACE_S", 10))
SETTLE_S = float(os.environ.get("RED_APPLY_SETTLE_S", 2))


def _log(msg: str):
    print(f"[red_apply {datetime.now():%H:%M:%S}] {msg}", flush=True)


def _episode_row(db_path: str, eid):
    """(ended_at, log 길이) — 조회 실패는 None(재시도)."""
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        row = conn.execute(
            "SELECT ended_at, length(COALESCE(log,'')) FROM episode_log WHERE id=?",
            (eid,)).fetchone()
        conn.close()
        return row
    except Exception:
        return None


def _resolve_open_episode(db_path: str, agent_id):
    """잡에 episode_id 가 없을 때 열린(ended_at 없는) 최신 행을 재해소한다.

    ★왜(2026-08-20 ep1265·1267): apply 가 claude_code 의 MCP→HTTP 재진입 스레드로
    들어오면 EpisodeLogger.current() 의 contextvar 가 끊겨 잡에 episode_id=null 이
    실렸고, 짧은 유예 후 라이브 쓰기 → 리로드가 **아직 열려 있는 턴**을 끊어
    최종 보고·주행기록이 유실됐다(고아 회수만 남음). 열린 최신 행 = 예약한 그 턴.

    ★agent 필터는 참고일 뿐 최종이 아니다(2026-08-20 ep1282): 잡의 agent_id 도
    같은 오염원(재진입 스레드 문맥)에서 온다 — 'agent_001' 이 실려 필터가 열린
    system_ai 턴을 놓치고, 10초 유예 뒤 쓰기가 그 턴을 끊었다. 필터 0건이면
    무필터로 한 번 더 — 틀린 대기(최대 상한)가 틀린 즉시 쓰기보다 싸다."""
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        row = None
        if agent_id:
            row = conn.execute(
                "SELECT id FROM episode_log WHERE ended_at IS NULL AND agent=? "
                "ORDER BY id DESC LIMIT 1", (agent_id,)).fetchone()
        if not row:
            row = conn.execute(
                "SELECT id FROM episode_log WHERE ended_at IS NULL "
                "ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def wait_turn_closed(repo: str, episode_id, agent_id=None):
    """예약한 턴이 완전히 닫힐 때까지 대기 — ①ended_at ②증류 재합류(log 재기록).

    상한 초과는 '턴이 죽었다'로 보고 진행한다(좌초보다 적용이 낫고, 주행기록은
    부팅 고아 회수가 닫는다). 에피소드 문맥이 없으면(REST 직접 호출 등) 짧은 유예만."""
    db_path = os.path.join(repo, "data", "world_pulse.db")
    if not episode_id and os.path.exists(db_path):
        episode_id = _resolve_open_episode(db_path, agent_id)
        if episode_id:
            _log(f"에피소드 문맥 없음 → 열린 턴 재해소 (episode {episode_id}"
                 f"{', agent=' + agent_id if agent_id else ''})")
    if not episode_id or not os.path.exists(db_path):
        _log(f"에피소드 문맥 없음 — {NO_EPISODE_GRACE_S:.0f}초 유예 후 진행")
        time.sleep(NO_EPISODE_GRACE_S)
        return
    t0 = time.time()
    row = None
    while time.time() - t0 < TURN_CLOSE_CAP_S:
        row = _episode_row(db_path, episode_id)
        if row is not None and row[0]:
            _log(f"턴 종료 감지 (episode {episode_id}, {int(time.time() - t0)}초)")
            break
        time.sleep(2)
    else:
        _log(f"턴 종료 대기 상한({TURN_CLOSE_CAP_S:.0f}초) — 턴이 끊긴 것으로 보고 진행")
        return
    # 증류 재합류: distill 스레드의 finally 가 refresh_episode 로 log 를 한 번 다시 쓴다.
    # 미감지=증류 생략/무변화/미배선 부류 — 상한 후 진행(적용을 볼모로 잡지 않는다).
    base_len = row[1] or 0
    t1 = time.time()
    while time.time() - t1 < DISTILL_GRACE_S:
        row = _episode_row(db_path, episode_id)
        if row is not None and (row[1] or 0) != base_len:
            _log(f"증류 재합류 감지 ({int(time.time() - t1)}초)")
            time.sleep(SETTLE_S)
            return
        time.sleep(3)
    _log(f"증류 재합류 미감지({DISTILL_GRACE_S:.0f}초) — 진행")


def _load_handler(job: dict):
    """system_essentials handler 로드 — 안전판(prepare/finalize)을 재사용하기 위해.
    _REPO_ROOT 는 대상 repo 로 맞춘다(가짜 저장소 테스트에서 코드 루트와 갈라진다)."""
    hpath = job.get("handler_path") or str(
        CODE_ROOT / "data" / "packages" / "installed" / "tools"
        / "system_essentials" / "handler.py")
    spec = importlib.util.spec_from_file_location("se_handler_deferred", hpath)
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    handler._REPO_ROOT = Path(job["repo"])
    return handler


def main() -> int:
    job_path = sys.argv[1]
    with open(job_path, encoding="utf-8") as f:
        job = json.load(f)
    repo = job["repo"]
    _log(f"기동 — key={job['key']} episode={job.get('episode_id')} repo={repo}")

    wait_turn_closed(repo, job.get("episode_id"), agent_id=job.get("agent_id"))

    # 코드 루트의 backend 를 sys.path 에 — red_grant/thread_context/episode_logger 등
    sys.path.insert(0, str(CODE_ROOT / "backend"))
    import boot_paths  # noqa: F401
    from red_grant import issue_grant
    from thread_context import set_current_task_id, set_current_agent_id

    task_id = job.get("task_id") or job["key"]
    agent_id = job.get("agent_id") or "system_ai"
    set_current_task_id(task_id)
    set_current_agent_id(agent_id)
    issue_grant(agent_id=agent_id, task_id=task_id,
                reason=f"지연 적용 수행: {job.get('reason') or job['key']}")

    handler = _load_handler(job)
    staging = handler._staging_mod()
    out = staging.perform_scheduled_apply(
        repo, job["key"],
        prepare=handler._red_write_prepare, finalize=handler._red_write_finalize)
    _log(f"결과: {json.dumps(out, ensure_ascii=False)[:500]}")

    try:
        job["done_at"] = datetime.now().isoformat()
        job["applied"] = bool(out.get("applied"))
        job["outcome_note"] = (out.get("error") or out.get("message") or out.get("note") or "")[:300]
        with open(job_path, "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _log(f"잡 파일 갱신 실패(계속): {e}")
    return 0 if out.get("applied") or out.get("success") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        _log(f"치명 오류: {e!r}")
        raise SystemExit(2)
