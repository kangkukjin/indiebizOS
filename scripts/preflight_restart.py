#!/usr/bin/env python3
"""preflight_restart.py — 백엔드를 **의도적으로** 죽이기 전에 묻는다: 지금 도는 턴이 있나?

## 왜

2026-08-23 하루에 라이브 턴이 두 번 끊겼다. 원인이 서로 다르다.

  ① `backend/test_*.py` 신규 생성 → WatchFiles 리로드 → 30회차 상상훈련 턴 절단.
     → 봉했다: `api.py` 의 `reload_excludes`(서버는 자기가 import 하지 않는 파일로
       재기동하지 않는다). 가드 `test_reload_scope.py`.
  ② **해마 모델 교체 절차 자체.** 모델을 바꾸면 `rebuild_index()` 후 백엔드를 명시적으로
     kill/재기동해야 한다(cloud_training/README 함정 ②·③ — 재색인 없이 재시작하면 옛
     벡터와 새 모델이 섞여 조용히 망가진다). 그 절차에 **"지금 도는 턴이 있나"를 묻는
     단계가 없었다.** 10:48 재기동이 10:40 에 시작한 `#repair` 턴을 끊었다(episode 1673).

①은 서버가 막을 수 있지만 ②는 못 막는다 — 죽이는 쪽이 사람(또는 하네스)이기 때문이다.
그래서 방어는 **죽이기 전에 묻는 단계**로 선다. 이 스크립트가 그 단계다.

## 왜 그냥 "기다리면 되지" 가 아닌가

턴이 죽는 자리에 따라 결말이 갈린다(둘 다 같은 날 실측):
  · `[self:patch]{op:"apply"}` 를 **예약한 뒤** 죽으면 → 죽음을 넘는 수행자가 완주시킨다(무사).
  · **예약 전에** 죽으면 → 격리 사본에 **좌초**한다. 그리고 좌초한 *task* 세션을 되살릴
    동사가 없다 — `apply` 는 RED 그랜트 + *현재* 세션 키로만 동작하고, `proposal_id` 는
    제안 세션만 연다. 사람이 손으로 관문을 밟아 옮기는 수밖에 없었다.
따라서 "조금 기다리면 알아서 괜찮다"가 아니다. 묻고, 기다리거나, 알고 죽여야 한다.

## 무엇을 보는가 (전부 원장 실측 — 추측 없음)

  1) 진행 중인 턴: `episode_log.ended_at IS NULL` (부팅 회수 전 고아도 여기 걸린다)
  2) 좌초 위험: `data/system_ai_state/repair_sessions/*.json` 중 status=staging
     (= 아직 apply 예약 전 — 지금 죽이면 좌초한다)

종료코드: 0 = 죽여도 됨 · 1 = 도는 턴/미예약 스테이징 있음 · 2 = 판정 불능(원장 못 읽음)
★2 를 0 으로 뭉개지 않는다 — "못 봤다"와 "없다"는 다른 사건이다(B28-1).

실행: .venv/bin/python3 scripts/preflight_restart.py [--wait 초]
"""
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if ".worktrees" in ROOT.parts:
    ROOT = Path(*ROOT.parts[:ROOT.parts.index(".worktrees")])

PULSE_DB = ROOT / "data" / "world_pulse.db"
SESSIONS = ROOT / "data" / "system_ai_state" / "repair_sessions"


def running_turns():
    """(turns, error) — turns 는 [(id, started_at, agent, message)]."""
    if not PULSE_DB.exists():
        return None, f"원장이 없습니다: {PULSE_DB}"
    try:
        conn = sqlite3.connect(f"file:{PULSE_DB}?mode=ro", uri=True, timeout=5)
        rows = conn.execute(
            "SELECT id, started_at, agent, substr(replace(user_message, char(10), ' '), 1, 60) "
            "FROM episode_log WHERE ended_at IS NULL ORDER BY id DESC"
        ).fetchall()
        conn.close()
        return rows, None
    except Exception as e:                      # 잠김·손상 — 판정 불능이지 '없음'이 아니다
        return None, f"원장을 읽지 못했습니다: {e}"


def staged_sessions():
    """apply 예약 전 스테이징 — 지금 죽이면 좌초한다."""
    if not SESSIONS.is_dir():
        return []
    out = []
    for p in sorted(SESSIONS.glob("*.json")):
        if p.name.endswith(".apply.json"):
            continue
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if j.get("status") == "staging" and (j.get("files") or {}):
            out.append((p.stem, list(j.get("files") or {})))
    return out


def check(verbose=True):
    turns, err = running_turns()
    staged = staged_sessions()
    if err:
        if verbose:
            print(f"[preflight] ⚠ 판정 불능 — {err}")
            print("[preflight] '못 봤다'는 '없다'가 아닙니다. 확인 후 죽이세요.")
        return 2
    blocked = bool(turns) or bool(staged)
    if verbose:
        if turns:
            print(f"[preflight] ✗ 진행 중인 턴 {len(turns)}건 — 지금 죽이면 절단됩니다:")
            for i, started, agent, msg in turns:
                print(f"    episode {i} · {started} · {agent} · {msg!r}")
        if staged:
            print(f"[preflight] ✗ apply 예약 전 스테이징 {len(staged)}건 — 지금 죽이면 좌초합니다:")
            for key, files in staged:
                print(f"    {key}: {[os.path.basename(f) for f in files]}")
        if not blocked:
            print("[preflight] ✓ 도는 턴 없음 · 미예약 스테이징 없음 — 재기동해도 됩니다.")
    return 1 if blocked else 0


if __name__ == "__main__":
    wait = 0
    if "--wait" in sys.argv:
        try:
            wait = int(sys.argv[sys.argv.index("--wait") + 1])
        except (IndexError, ValueError):
            print("[preflight] --wait 뒤에 초를 주세요. 예: --wait 300")
            raise SystemExit(2)
    deadline = time.time() + wait
    while True:
        rc = check(verbose=True)
        if rc != 1 or time.time() >= deadline:
            raise SystemExit(rc)
        print(f"[preflight] … {int(deadline - time.time())}초까지 대기(20초 간격)")
        time.sleep(20)
