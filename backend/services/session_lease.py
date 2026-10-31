"""session_lease.py — 임시 세션의 공통 수명: 임대·멱등 종료·낡은 확인 거절 (2026-10-13).

설계 정본: docs/MEDIA_COMMUNICATION_DESIGN_2026_10_13.md §4 '수명과 복구', §10.
원래 resident_screen.py(20초)·resident_terminal.py(30초)에 각자 있던 `seen`/LEASE 논리를 한 곳으로
뽑았다. 화면 공유·터미널·미디어 세션이 전부 이 모듈을 쓰고, 수치는 data/session_lease_policy.yaml 이
정본이다(모듈 상수 금지).

규칙
- 시간은 단조 시계(time.monotonic)로만 잰다 — 벽시계 점프가 임대를 되살리거나 죽이지 않는다.
- 갱신(renew)은 **현재 세대·증가하는 순번**의 확인만 받는다. 늦게 재전달된 과거 확인은 임대를 되살리지 못한다.
- 종료(close)는 멱등 — 처음 한 번만 True. 닫힌 임대는 다시 열리지 않는다(종료된 세션 재사용 금지).
- 정책은 mtime 으로 캐시하고, 파일이 없거나 깨져도 기본값으로 산다(관문은 신선도만 본다).
"""
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

_DEFAULTS = {
    "screen": {"reconnect_s": 15, "lease_s": 20, "keepalive_s": 5, "closed_keep_s": 120},
    "terminal": {"lease_s": 30, "keepalive_s": 5, "closed_keep_s": 120},
    "media": {"lease_s": 20, "keepalive_s": 5, "reconnect_s": 30, "invite_s": 45, "closed_keep_s": 300},
}
_FIELDS = ("lease_s", "keepalive_s", "reconnect_s", "invite_s", "closed_keep_s")
_policy_cache = (None, None)   # (mtime_ns, profiles)
_policy_lock = threading.Lock()


def policy_path() -> Path:
    from runtime_utils import get_data_path
    return Path(get_data_path()) / "session_lease_policy.yaml"


def _load_profiles() -> Dict[str, Dict[str, float]]:
    global _policy_cache
    p = policy_path()
    try:
        mtime = p.stat().st_mtime_ns
    except OSError:
        mtime = None
    with _policy_lock:
        if _policy_cache[0] == mtime and _policy_cache[1] is not None:
            return _policy_cache[1]
        profiles = {k: dict(v) for k, v in _DEFAULTS.items()}
        if mtime is not None:
            try:
                import yaml
                doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                for name, row in (doc.get("profiles") or {}).items():
                    if not isinstance(row, dict):
                        continue
                    merged = dict(profiles.get(name) or _DEFAULTS["media"])
                    for key in _FIELDS:
                        v = row.get(key)
                        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                            merged[key] = float(v)
                    profiles[name] = merged
            except Exception:  # noqa: BLE001 — 깨진 정책 파일은 기본값으로 산다
                pass
        _policy_cache = (mtime, profiles)
        return profiles


def profile(name: str) -> Dict[str, float]:
    """프로필 한 벌(복사본). 모르는 이름은 media 기본값 — 새 소비자가 조용히 다른 수치를 갖지 못한다."""
    profiles = _load_profiles()
    return dict(profiles.get(name) or profiles["media"])


class Lease:
    """한 세션의 임대. 소유 객체가 `.lease` 로 품는다."""
    __slots__ = ("profile", "lease_s", "keepalive_s", "seen", "generation", "seq", "closed", "reason",
                 "closed_at", "_clock")

    def __init__(self, profile_name: str = "media", clock: Callable[[], float] = time.monotonic):
        row = profile(profile_name)
        self.profile = profile_name
        self.lease_s = float(row["lease_s"])
        self.keepalive_s = float(row.get("keepalive_s") or 5)
        self._clock = clock
        self.seen = clock()
        self.generation = 0
        self.seq = 0
        self.closed = False
        self.reason = ""
        self.closed_at: Optional[float] = None

    # ── 판정 ────────────────────────────────────────────────────────────────────
    def age(self) -> float:
        return self._clock() - self.seen

    def expired(self) -> bool:
        return not self.closed and self.age() > self.lease_s

    def remaining(self) -> float:
        return max(0.0, self.lease_s - self.age())

    def alive(self) -> bool:
        return not self.closed and not self.expired()

    # ── 갱신 ────────────────────────────────────────────────────────────────────
    def renew(self, generation: Optional[int] = None, seq: Optional[int] = None) -> bool:
        """유효 확인 — 닫혔거나, 다른 세대거나, 순번이 지난 것이면 False(임대를 건드리지 않는다)."""
        if self.closed or self.expired():
            return False
        if generation is not None and generation != self.generation:
            return False
        if seq is not None:
            if seq <= self.seq:
                return False
            self.seq = seq
        self.seen = self._clock()
        return True

    def advance_generation(self) -> int:
        """재협상·재접속 — 새 세대. 이전 세대의 늦은 확인은 renew 에서 거절된다."""
        if self.closed:
            return self.generation
        self.generation += 1
        self.seq = 0
        self.seen = self._clock()
        return self.generation

    # ── 종료 ────────────────────────────────────────────────────────────────────
    def close(self, reason: str = "") -> bool:
        """멱등 종료 — 처음 한 번만 True. 두 번째부터는 사유를 바꾸지 않는다."""
        if self.closed:
            return False
        self.closed = True
        self.reason = reason or self.reason
        self.closed_at = self._clock()
        return True

    def closed_age(self) -> float:
        return 0.0 if self.closed_at is None else self._clock() - self.closed_at

    def rewind(self, seconds: float) -> None:
        """시험용 — 마지막 확인 시각을 과거로 밀어 만료를 재현한다(운영 코드에서 호출 금지)."""
        self.seen -= float(seconds)

    def describe(self) -> Dict:
        return {"profile": self.profile, "lease_s": self.lease_s, "keepalive_s": self.keepalive_s,
                "generation": self.generation, "seq": self.seq, "remaining_s": round(self.remaining(), 3),
                "closed": self.closed, "reason": self.reason}


def sweep(sessions: Dict, on_expire: Callable, closed_keep_s: Optional[float] = None, profile_name: str = "media") -> int:
    """`sessions` 사전에서 만료 임대를 닫고, 닫힌 지 오래된 항목을 지운다. 호출자가 잠근 채 부른다.

    on_expire(obj) 는 소유 객체의 종료 처리(자원 해제·통지). 지워진 수를 돌려준다."""
    keep = float(closed_keep_s if closed_keep_s is not None else profile(profile_name).get("closed_keep_s") or 120)
    removed = 0
    for key, obj in list(sessions.items()):
        lease: Lease = obj.lease
        if lease.expired():
            on_expire(obj)
        if lease.closed and lease.closed_age() > keep:
            del sessions[key]
            removed += 1
    return removed
