"""render_gate.py — 렌더 예산·'변화 없음' 관문 (2026-09-06, ep2910 실측 뒤).

ep2910: 41분 · 렌더 27회 · 판정 11회 동안 그림이 거의 안 변했다. 에이전트가 스스로 지은 이진 채점표에
정확한 판정기가 "없음"을 되풀이했고, 멈출 조건이 없었다. 셀 수 있으면 관문이 실패시킨다(카운터로 두고 보지 않는다).

두 규칙(둘 다 원장 = data/render_assets/_render_ledger.json, 몸-사적):
  ① 예산 — 같은 설계를 최근 60분 안에 RENDER_BUDGET 회 넘게 렌더하면 거절(exit 3). --force 로만 강행.
  ② 변화 없음 — 같은 설계·같은 시점(view)의 직전 렌더와 평균 픽셀 차이가 DELTA_MIN 아래인 렌더가
     STILL_STREAK 회 연속이면 다음 렌더를 거절. "조절이 그림을 바꾸지 않는다 — 멈추고 현재 그림을 보여라".
bpy 에 기대지 않는다(시험 가능). 픽셀 읽기는 호출자가 loader 로 준다.
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable, Dict, List, Optional, Tuple

RENDER_BUDGET = 8          # 회 / 60분 / 설계 하나 (ep2910 은 40분에 27회)
BUDGET_WINDOW_S = 3600
DELTA_MIN = 0.02           # 0~1 평균 절대 차이 — 이 아래면 "같은 그림"
STILL_STREAK = 2           # 연속 '변화 없음' 허용 횟수
THUMB = (64, 36)

Loader = Callable[[str, Tuple[int, int]], Optional[List[float]]]   # (경로, (w,h)) → 회색 픽셀 0~1 목록


def ledger_path(base_dir: str) -> str:
    return os.path.join(base_dir, "_render_ledger.json")


def load_ledger(base_dir: str) -> Dict:
    p = ledger_path(base_dir)
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_ledger(base_dir: str, ledger: Dict) -> None:
    os.makedirs(base_dir, exist_ok=True)
    p = ledger_path(base_dir)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def _entries(ledger: Dict, design: str) -> List[Dict]:
    return [e for e in (ledger.get(design) or []) if isinstance(e, dict)]


def check_before(ledger: Dict, design: str, view: str, now: Optional[float] = None,
                 force: bool = False) -> Tuple[bool, str]:
    """렌더 전 판정 → (허용, 사유). 거절 사유는 다음 걸음을 말한다."""
    now = time.time() if now is None else now
    ents = _entries(ledger, design)
    recent = [e for e in ents if now - float(e.get("ts", 0)) <= BUDGET_WINDOW_S]
    if force:
        return True, f"--force: 예산 관문 우회 (최근 60분 {len(recent)}회)"
    if len(recent) >= RENDER_BUDGET:
        return False, (f"렌더 예산 초과 — 최근 60분에 이 설계를 {len(recent)}회 렌더했다(상한 {RENDER_BUDGET}). "
                       "조절을 멈추고 지금까지의 최선 그림을 사용자에게 보여 판정을 받아라. 정말 필요하면 --force.")
    same_view = [e for e in recent if e.get("view") == view]
    tail = same_view[-STILL_STREAK:]
    if len(tail) >= STILL_STREAK and all((e.get("delta") is not None and e["delta"] < DELTA_MIN) for e in tail):
        return False, (f"변화 없음 {STILL_STREAK}회 연속(Δ<{DELTA_MIN}) — 최근 조절이 그림을 바꾸지 않는다. "
                       "파라미터를 더 만지지 말고 현재 그림을 사용자에게 보여라. 다른 시점(--view)이나 다른 접근이면 --force.")
    return True, f"최근 60분 {len(recent)}회 / 상한 {RENDER_BUDGET}"


def image_delta(a: str, b: str, loader: Loader) -> Optional[float]:
    """두 이미지의 평균 절대 차이(0~1, 회색 썸네일). 못 읽으면 None."""
    pa, pb = loader(a, THUMB), loader(b, THUMB)
    if not pa or not pb or len(pa) != len(pb):
        return None
    return sum(abs(x - y) for x, y in zip(pa, pb)) / len(pa)


def record_after(ledger: Dict, design: str, view: str, out: str, loader: Loader,
                 now: Optional[float] = None) -> Dict:
    """렌더 뒤 원장에 적고, 직전 같은 시점 렌더와의 Δ 를 돌려준다."""
    now = time.time() if now is None else now
    ents = _entries(ledger, design)
    prev = next((e for e in reversed(ents) if e.get("view") == view and os.path.isfile(str(e.get("out", "")))), None)
    delta = image_delta(prev["out"], out, loader) if prev else None
    entry = {"ts": now, "view": view, "out": os.path.abspath(out), "delta": delta}
    ents.append(entry)
    ledger[design] = ents[-40:]
    return entry


def note(entry: Dict) -> str:
    """사람·에이전트가 읽을 한 줄 — 렌더러 표준출력과 CLI 봉투에 같이 실린다."""
    d = entry.get("delta")
    if d is None:
        return "[render_gate] 첫 렌더(같은 시점의 비교 대상 없음)"
    if d < DELTA_MIN:
        return (f"[render_gate] 변화 없음 Δ={d:.3f} < {DELTA_MIN} — 이 조절은 그림을 바꾸지 않았다. "
                "한 번 더 같으면 렌더가 막힌다. 멈추고 사용자에게 보여라.")
    return f"[render_gate] 직전 대비 변화 Δ={d:.3f}"
