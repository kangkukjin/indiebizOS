"""쓰기 관문 원장 (write_ledger) — 몸 원장 4기둥의 ③ (2026-08-21 신설)

런타임 쓰기(git 이 못 보는 data/·outputs/ 층)가 좁은 관문(safe_store·[self:write] +
2026-08-21 ④: 보안·설정·공개쓰기 가족의 개별 저장 관문 — limb_keys·device_registry·
model_gear·calendar·portal_state·bulletin·family_news·webapp_registry·package·config)을
지날 때 append-only 원장에 한 줄을 남긴다 — 행위자(agent·task·origin)가 실리므로
episode 주행기록과 task_id 로 조인해 "이 파일 왜 바뀌었나"가 닫힌다.

원칙:
  - **전수 감시 데몬 금지** — 관문 훅만(worker-thread-dies-on-reload 부류 회피,
    osquery FIM 도 선언 경로만). 관문 밖 직접 open() 쓰기는 **원리적으로 미기록** —
    소비자([self:body]{op:"writes"})는 이 부분성을 정직하게 광고해야 한다(B8 회피).
  - **원장 ≠ 진실 소스** — 사건 기록일 뿐, 현재 상태의 권위가 아니다.
  - **절대 실패를 만들지 않는다** — 원장 기록 실패가 본 쓰기를 깨면 배보다 배꼽.
    모든 예외는 삼킨다(원장=관측, 쓰기=본업).

저장: data/write_ledger.jsonl (O_APPEND 단일행 — 소규모 동시 append 안전),
8MB 초과 시 .jsonl.1 로 1세대 로테이션. 소유 선언=ledger(data_ownership).

심장박동 압축 (2026-08-21 첫날 실측 후): device_registry.json 폴링이 하루 ~350행
(전체의 93%)을 차지해 원장이 provenance 기록이 아니라 폴링 로그가 됐다. 선언된
심장박동 가족의 **행위자 없는** 쓰기만 _HB_WINDOW_S 당 1건으로 압축(hb=True 표식)
— 행위자(agent·task·origin)가 실린 쓰기는 진짜 사건(기기 등록 등)이라 전부 기록.
소비자([self:body]{op:"writes"})는 이 압축도 부분성 광고에 포함해야 한다.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
_LEDGER_PATH = _ROOT / "data" / "write_ledger.jsonl"
_ROTATE_BYTES = 8 * 1024 * 1024   # 1세대 로테이션 (~40k행)

# 심장박동 가족 — 폴링·상태 갱신이 분 단위로 두드리는 파일(상대경로). 행위자 없는
# 쓰기만 압축 대상. 프로세스 내 메모리 창이라 리로드 시 초기화(추가 몇 행 무해).
_HEARTBEAT_PATHS = {"data/device_registry.json"}
_HB_WINDOW_S = 6 * 3600
_hb_last: dict = {}   # rel path -> 마지막 기록 epoch


def _actor() -> dict:
    """행위자 — thread_context 전파값. 없으면 빈 값(스케줄러·부팅 등 무맥락 쓰기)."""
    try:
        import thread_context as tc
        a = {
            "agent": tc.get_current_agent_id() or "",
            "task": tc.get_current_task_id() or "",
            "origin": tc.get_task_origin() or "",
        }
        if tc.is_health_check_mode():
            a["hc"] = True   # 자가점검 순찰의 쓰기 — 계수 오염 방지 표식(selfcheck 선례)
        return a
    except Exception:
        return {"agent": "", "task": "", "origin": ""}


def _rel(path) -> str:
    # ★양쪽 다 resolve — macOS /var→/private/var 심링크로 한쪽만 풀면 상대화가 어긋난다
    try:
        return str(Path(path).resolve().relative_to(Path(_ROOT).resolve()))
    except Exception:
        return str(path)


def log_write(path, event: str = "write", gate: str = "", size=None) -> None:
    """관문 훅 — 성공한 쓰기 직후 한 줄. 어떤 예외도 밖으로 내지 않는다."""
    try:
        rel = _rel(path)
        # 자기 자신(원장·로테이션)의 쓰기는 기록하지 않는다 — 자기지시 루프 차단
        # (경로 비교가 어긋나도 파일명으로 이중 차단 — 상대화 실패 시 안전판)
        if rel.startswith("data/write_ledger.jsonl") or \
                Path(path).name.startswith("write_ledger.jsonl"):
            return
        actor = _actor()
        hb = False
        if rel in _HEARTBEAT_PATHS and not (actor.get("agent") or actor.get("task")
                                            or actor.get("origin")):
            now = time.time()
            if now - _hb_last.get(rel, 0.0) < _HB_WINDOW_S:
                return
            _hb_last[rel] = now
            hb = True
        row = {"ts": datetime.now().isoformat(timespec="seconds"),
               "path": rel, "event": event, "gate": gate, **actor}
        if hb:
            row["hb"] = True
        if size is not None:
            row["size"] = int(size)
        line = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            if _LEDGER_PATH.stat().st_size > _ROTATE_BYTES:
                os.replace(_LEDGER_PATH, str(_LEDGER_PATH) + ".1")
        except OSError:
            pass
        fd = os.open(_LEDGER_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except Exception:
        pass  # 원장은 관측이다 — 본 쓰기를 절대 깨지 않는다


def read_rows(days: int = 7):
    """원장 읽기(현재+로테이션 1세대) — 최근 days 일, 신순 정렬. 소비자=body_ops."""
    cutoff = None
    try:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    except Exception:
        pass
    rows = []
    for p in (str(_LEDGER_PATH) + ".1", str(_LEDGER_PATH)):
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if cutoff and (row.get("ts") or "") < cutoff:
                        continue
                    rows.append(row)
        except OSError:
            continue
    rows.sort(key=lambda r: r.get("ts") or "", reverse=True)
    return rows
