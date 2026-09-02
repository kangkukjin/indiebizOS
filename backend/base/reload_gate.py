"""
reload_gate.py - 재기동 관문 (2026-09-02, 수리 턴 절단율 16% 의 뿌리 봉합)

★왜: 지연 적용 수행자(red_apply)는 **예약한 턴**이 닫히기만 기다렸다. 그 턴이 닫힌 뒤
사용자가 곧바로 다음 명령을 내리면(실측 ep1917 "#repair 수리가 적용된거야?") 수행자는
그 새 턴이 도는 줄 모르고 라이브에 썼고, 리로드가 **다음 턴**을 잘랐다. 08-05~09-02
실측: `#repair` 턴 59건 중 12건 절단(16%, 전체 턴 8.4%의 두 배).

봉합은 두 겹이다:
  ① 수행자는 "지금 도는 턴이 0" 일 때만 쓴다 (red_apply.wait_quiescent — /health 의
     live_turns 가 출처, 원장은 폴백). 도는 턴이 있으면 그 턴이 끝날 때까지 기다린다.
  ② 쓰기 직전 ~ 새 몸 부팅 사이의 몇 초는 **이 관문 파일**이 덮는다 — 그 창에 들어온 새
     턴은 파이프라인 진입점(cognitive_stream)이 일을 시작하지 않고 "재기동 중, 다시
     보내 달라"를 정직하게 돌려준다. 옛 몸 안에서 기다리게 하는 것은 답이 아니다 — 그
     기다림은 옛 몸과 함께 죽는다. 되돌려보내는 것이 유일하게 정직한 선택이다.

관문의 생애: raised(쓰기 전, TTL 짧음) → written(쓴 뒤, 리로드 대기) → 새 몸이 부팅하며
회수(EpisodeLogger.install → clear_at_boot). 수행자가 죽거나 쓰기가 실패하면 lower 또는
TTL 만료로 사라진다 — 어느 경로로도 영구히 닫히지 않는다(★관문이 영구화되면 그것이 곧
브릭이다. 그래서 TTL 은 폴백이 아니라 헌법이다).

파일: <base>/data/system_ai_state/reload_gate.json — 자리 하나. 수행자 둘이 겹치면 뒤의
것이 앞의 것을 보고 기다린다(red_apply 쪽 규약).
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
