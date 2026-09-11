"""이전 RED 파일 관문의 호환 읽기/회수 계약.

관리되는 데스크탑 현역은 runtime_work의 원자적 접수 관문과 restart_controller
상태를 사용한다. TTL 파일은 이전 기록/미관리 도구의 호환용이며 재기동 권한이 아니다.
"""
import json
import os
import time

GATE_REL = os.path.join("data", "system_ai_state", "reload_gate.json")
# 쓰기 전 관문 — 수행자가 여기서 죽으면 이만큼만 새 턴을 되돌린다.
RAISED_TTL_S = float(os.environ.get("RELOAD_GATE_RAISED_TTL_S", 60))
# 쓴 뒤 관문 — 리로드(2초)+부팅(수 초)을 덮는다. 새 몸이 부팅에서 회수하므로 폴백일 뿐.
WRITTEN_TTL_S = float(os.environ.get("RELOAD_GATE_WRITTEN_TTL_S", 120))


def gate_path(base) -> str:
    return os.path.join(str(base), GATE_REL)


def _ttl_for(phase: str) -> float:
    return WRITTEN_TTL_S if phase == "written" else RAISED_TTL_S


def read_gate(base):
    """살아 있는 관문 → dict, 없거나 만료 → None (만료분은 기회주의적으로 지운다)."""
    p = gate_path(base)
    try:
        with open(p, encoding="utf-8") as f:
            g = json.load(f)
    except Exception:
        return None
    if not isinstance(g, dict):
        return None
    try:
        age = time.time() - float(g.get("at") or 0)
        ttl = float(g.get("ttl_s") or _ttl_for(g.get("phase") or "raised"))
    except (TypeError, ValueError):
        return None
    if age > ttl or age < -300:      # 미래 시각도 신뢰하지 않는다(시계 역행)
        try:
            os.remove(p)
        except OSError:
            pass
        return None
    return g


def raise_gate(base, key: str, phase: str = "raised", ttl_s: float = None) -> dict:
    """관문을 세운다(덮어쓰기). 반환 = 기록한 내용."""
    p = gate_path(base)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    g = {"key": key, "phase": phase, "at": time.time(), "pid": os.getpid(),
         "ttl_s": float(ttl_s if ttl_s is not None else _ttl_for(phase))}
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False)
    os.replace(tmp, p)
    return g


def mark_written(base, key: str) -> dict:
    """쓰기 완료 — 관문을 written 단계로 올린다(부팅 회수 대상이 된다)."""
    return raise_gate(base, key, phase="written")


def lower_gate(base, key: str = None) -> bool:
    """관문 회수. key 를 주면 **내 관문일 때만** 지운다(남의 관문을 걷어차지 않는다)."""
    p = gate_path(base)
    if key is not None:
        g = read_gate(base)
        if g is None:
            return False
        if g.get("key") != key:
            return False
    try:
        os.remove(p)
        return True
    except OSError:
        return False


def clear_at_boot(base) -> bool:
    """새 몸의 부팅 — written 관문은 임무 완료(리로드가 일어났다)이므로 회수한다.
    raised 관문(수행자가 아직 쓰기 전)은 남긴다 — 그 수행자가 곧 쓰거나 TTL 로 사라진다.
    만료분은 read_gate 가 이미 지운다."""
    g = read_gate(base)
    if g is None:
        return False
    if g.get("phase") == "written":
        return lower_gate(base)
    return False


def bounce_notice(base) -> str:
    """턴 진입점이 묻는다: 지금 새 일을 시작하면 안 되는가? → 안내문 / "" (정상)."""
    g = read_gate(base)
    if g is None:
        return ""
    key = str(g.get("key") or "")
    left = 0
    try:
        left = max(0, int(float(g.get("ttl_s") or 0) - (time.time() - float(g.get("at") or 0))))
    except (TypeError, ValueError):
        pass
    return (f"⏸ 자기수리 적용으로 백엔드가 재기동 중입니다(적용 세션 {key or '?'}, "
            f"길어야 {left}초). 이 메시지는 **처리되지 않았습니다** — 재기동이 끝나면 같은 "
            f"내용을 그대로 다시 보내 주세요. (도중에 시작한 일이 리로드에 잘리는 것보다 "
            f"정직하게 되돌려 드리는 쪽을 택했습니다.)")
