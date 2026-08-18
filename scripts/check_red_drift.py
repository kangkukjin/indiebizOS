#!/usr/bin/env python3
"""RED 드리프트 순찰 — 격리를 지나지 않은 살아있는 기질(backend/*.py) 변경 탐지.

★왜 (2026-08-18): 08-17 의 REPAIR 워크트리 격리는 **문 하나**에만 걸려 있다.
게이트(`system_essentials/handler.py` `_red_zone_write_block`)는 `[self:write]`/
`[self:edit]` 가 지나는 자리이고, 그랜트는 인지 파이프라인의 REPAIR 경로만 발급한다.
그 문을 안 쓰는 편집자 — 아웃오브프로세스 Claude Code 세션, `[self:script]{op:run}`
이 돌리는 스크립트, `run_command`, 패키지 핸들러 자신의 `open()` — 는 backend 를
**라이브로 직행**한다. 게이트는 `_find_repo_root()` 미탐지 시 fail-open 이기도 하다.

즉 실제 불변식은 "backend 는 격리를 거쳐야 바뀐다"가 아니라
"REPAIR 경로는 격리를 쓴다" 이다. 차단은 아웃오브프로세스 편집자를 원리적으로 못 막으므로
(그 손은 이 프로세스 밖에 있다), 이 순찰은 **차단이 아니라 가시성**을 맡는다.

원장은 새로 만들지 않는다 — **git 이 이미 그 원장이다**:
  · 커밋됨            = 사람이 승인함
  · 격리 세션에 있음  = 검증 층을 지나는 중
  · 미커밋 + 세션 없음 = **격리 밖에서 살아있는 몸이 바뀐 상태** ← 이것만 본다
커밋하면 저절로 해소되므로 상태가 쌓이지 않는다.

작업 중인 변경까지 알람으로 울리면 순찰이 곧 무시된다. 그래서 **나이**로 가른다:
  · STALE_HOURS 이내  = 작업 중 → 보고만, 통과(rc 0)
  · 그보다 오래됨      = 방치 → 실패(rc 1)

둘째 검사 — 고아 워크트리: `.worktrees/` 아래에 세션 원장이 없는 격리본.
(2026-08-18 실측: `.worktrees/selfpatch-20260817_094955` 가 미적용
`backend/surface/api_showcase.py` 편집을 품은 채 하루 넘게 떠 있었다. 개명 전
`propose_patch` 세대라 현행 청소 대상에도 안 잡혔다.)

대상은 backend/**/*.py 뿐이다 — 편집자를 죽이는 리로드를 부르는 것이 이것이라서다.
frontend/·scripts/ 는 RED 구역이지만 이 프로세스를 리로드시키지 않으므로 뺀다(잡음).

호출: world_pulse_health.run_daily_health_check 의 자가점검 항목 + 수동.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION_DIR = ROOT / "data" / "system_ai_state" / "repair_sessions"
WORKTREE_DIR = ROOT / ".worktrees"
STALE_HOURS = 24
GIT_TIMEOUT = 30


def _git(args):
    try:
        p = subprocess.run(["git"] + args, cwd=str(ROOT), capture_output=True,
                           text=True, timeout=GIT_TIMEOUT)
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""


def _staged_in_isolation() -> set:
    """열린 격리 세션이 붙잡고 있는 라이브 경로들 — 이건 드리프트가 아니다."""
    held = set()
    if not SESSION_DIR.is_dir():
        return held
    for f in SESSION_DIR.glob("*.json"):
        try:
            sess = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for live_abs in (sess.get("files") or {}):
            try:
                held.add(str(Path(live_abs).resolve()))
            except Exception:
                held.add(str(live_abs))
    return held


def _age_hours(p: Path) -> float:
    try:
        return (time.time() - p.stat().st_mtime) / 3600.0
    except OSError:
        return 0.0


def find_uncommitted_red():
    """미커밋 backend/**/*.py 중 격리 세션이 안 붙잡은 것."""
    held = _staged_in_isolation()
    out = []
    for line in _git(["status", "--porcelain", "--", "backend"]).splitlines():
        if len(line) < 4:
            continue
        status, rel = line[:2], line[3:].strip()
        if " -> " in rel:                      # 이름 변경: 도착지를 본다
            rel = rel.split(" -> ", 1)[1]
        rel = rel.strip('"')
        if not rel.endswith(".py"):
            continue
        abs_p = ROOT / rel
        if str(abs_p.resolve() if abs_p.exists() else abs_p) in held:
            continue
        out.append((rel, status.strip() or "?", _age_hours(abs_p)))
    return sorted(out, key=lambda x: -x[2])


def find_orphan_worktrees():
    """.worktrees/ 아래 격리본 중 세션 원장이 없는 것 (개명 전 세대 포함)."""
    out = []
    if not WORKTREE_DIR.is_dir():
        return out
    for wt in sorted(WORKTREE_DIR.iterdir()):
        if not wt.is_dir():
            continue
        key = wt.name[len("repair-"):] if wt.name.startswith("repair-") else None
        if key and (SESSION_DIR / f"{key}.json").exists():
            continue                            # 살아있는 세션의 격리본
        # ★진짜 워크트리인지 먼저 확인한다 — 아니면 `git -C` 가 **부모 저장소**의 상태를
        #   반환해서, 저장소 전체의 미커밋 변경이 그 격리본 것인 양 보고된다(실측).
        if not (wt / ".git").exists():
            out.append((wt.name, _age_hours(wt), None))   # None = 워크트리 아님(빈 잔재)
            continue
        dirty = [l for l in _git(["-C", str(wt), "status", "--porcelain"]).splitlines() if l.strip()]
        out.append((wt.name, _age_hours(wt), dirty))
    return out


def main() -> int:
    hours = STALE_HOURS
    for i, a in enumerate(sys.argv):
        if a == "--hours" and i + 1 < len(sys.argv):
            hours = float(sys.argv[i + 1])

    drift = find_uncommitted_red()
    orphans = find_orphan_worktrees()

    if not drift and not orphans:
        print(f"✓ RED 드리프트 없음 (격리 밖 미커밋 backend/*.py 0건, 고아 격리본 0건)")
        return 0

    stale = [d for d in drift if d[2] >= hours] + [o for o in orphans if o[1] >= hours]

    if drift:
        print(f"격리 밖 backend/*.py 변경 {len(drift)}건 — 살아있는 기질이 검증 층을 안 지났습니다:")
        for rel, st, age in drift:
            mark = "‼ 방치" if age >= hours else "· 작업 중"
            print(f"  {mark}  {rel}  [{st}] {age:.1f}시간")
    if orphans:
        print(f"고아 격리본 {len(orphans)}건 — 세션 원장이 없습니다:")
        for name, age, dirty in orphans:
            mark = "‼ 방치" if age >= hours else "·"
            if dirty is None:
                print(f"  {mark}  .worktrees/{name}  {age:.1f}시간 — git 워크트리가 아닌 잔재 디렉토리")
                continue
            print(f"  {mark}  .worktrees/{name}  {age:.1f}시간, 미적용 변경 {len(dirty)}건")
            for d in dirty[:5]:
                print(f"          {d}")

    print()
    if stale:
        print(f"[FAIL] {hours:.0f}시간 넘게 방치된 항목 {len(stale)}건.")
        print("  · 살릴 것이면 커밋(=사람 승인), 버릴 것이면 되돌리기/격리본 제거")
        print("  · 고아 격리본: 내용 확인 후 `git worktree remove --force .worktrees/<이름>`")
        print("  · ★차단이 아니라 가시성 순찰입니다 — 아웃오브프로세스 편집자는 원리적으로 못 막습니다")
        return 1

    print(f"[OK] 전부 {hours:.0f}시간 이내 = 작업 중으로 봅니다(커밋하면 해소).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
