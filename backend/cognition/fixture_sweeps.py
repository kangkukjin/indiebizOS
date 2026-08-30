"""fixture_sweeps.py — fixture 우주를 라이브 실행하는 주간 스윕 2종 (world_pulse_health 에서 분리, 2026-08-21 — 1500줄 규칙)

- run_returns_drift_sweep: returns 선언 ↔ 실측 통화 모양 대조 (scripts/returns_drift_sweep.py)
- run_shape_sweep: 실측 반환 열 관측 → data/ibl_return_shapes.json → 카탈로그 ⟨열: …⟩ (scripts/ibl_shape_sweep.py)
- run_partner_sweep: 실측 조합 파트너 관측 → data/ibl_partners.json → 카탈로그 ⟨동반: …⟩ (scripts/ibl_partner_sweep.py)
- run_honesty_sweep: 정직성 불변식 A/B/C(거짓 성공·통화 부재·0행 거짓) — 침묵 부류를 봉투 입구 하나에서 (scripts/honesty_invariants_sweep.py)
둘 다 subprocess(라이브 프로세스 무접촉)·주간 카덴스(상태 파일)·self_checks 기록. run_maintenance_bundle 이 부른다.
"""
import json
import logging
import sys
import time as _time
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


def run_returns_drift_sweep() -> Dict:
    """returns 선언 ↔ 실측 출력 대조 (주간 카덴스, §8.5) — scripts/returns_drift_sweep.py.

    fixture 를 라이브 실행(수 분·외부 API)하므로 주간만. subprocess = 라이브 프로세스
    무접촉(red_safety·ibl_health_check 선례). 결과는 @@RETURNS_DRIFT@@ 마커로 회수해
    self_checks 에 기록 — 드리프트는 실행을 안 죽이는 대신(이음매 derive_items 가 살림)
    건강 단언 사각을 만들므로, 깃발이 서면 선언 동기화가 대장장이 입력이 된다.
    """
    import subprocess
    from world_pulse_health import save_self_check
    _root = Path(__file__).parent.parent.parent
    state_path = _root / "data" / "returns_drift_state.json"
    now = _time.time()
    try:
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    except Exception:
        state = {}
    if now - float(state.get("last_run", 0)) < 7 * 86400:
        return {"skipped": "cadence", "last_run": state.get("last_run")}

    script = _root / "scripts" / "returns_drift_sweep.py"
    if not script.exists():
        return {"error": "scripts/returns_drift_sweep.py 없음"}
    try:
        proc = subprocess.run([sys.executable, str(script)], cwd=str(_root),
                              capture_output=True, text=True, timeout=600)
    except Exception as e:
        return {"error": f"스윕 실행 실패: {str(e)[:150]}"}

    marker = None
    for line in reversed((proc.stdout or "").splitlines()):
        if line.startswith("@@RETURNS_DRIFT@@"):
            marker = line[len("@@RETURNS_DRIFT@@"):].strip()
            break
    if proc.returncode != 0 or not marker:
        out = {"error": f"스윕 비정상 종료(rc={proc.returncode}, 마커 {'유' if marker else '무'})"}
    else:
        try:
            s = json.loads(marker)
        except Exception as e:
            s = None
            out = {"error": f"요약 파싱 실패: {str(e)[:100]}"}
        if s is not None:
            over, under = s.get("over") or [], s.get("under") or []
            unverified = s.get("op_unverified") or []
            out = {"checked": s.get("checked"), "over": over, "under": under,
                   "op_unverified": unverified}
            # 미검증 op 경로는 드리프트(약속 위반)가 아니라 '조용한 미검증' — 깃발은
            # 세우되(ok=False 아님) 노트로 자백해 fixture/exempt 정비를 대장장이 입력으로.
            ok = not over and not under
            parts = []
            if over:
                parts.append(f"선언 드리프트 — scalar/effect인데 통화 {len(over)}건: {', '.join(over[:5])}")
            if under:
                parts.append(f"통화 선언인데 scalar {len(under)}건: {', '.join(under[:3])}")
            if unverified:
                parts.append(f"미검증 op 경로 {len(unverified)}건(fixture/exempt 없음): {', '.join(unverified[:5])}")
            note = " / ".join(parts) if parts else None
            try:
                save_self_check({"node": "__ibl_health__", "action": "returns_drift",
                                 "success": ok, "response_ms": 0,
                                 "data_quality": "ok" if ok else "declaration_drift",
                                 "error_message": note and note[:220]})
            except Exception:
                pass
            if not ok:
                logger.warning(f"[Maintenance] returns 드리프트: over {len(over)} / under {len(under)}")

    state["last_run"] = now
    try:
        state_path.write_text(json.dumps(state, ensure_ascii=False))
    except Exception:
        pass
    return out


def run_shape_sweep() -> Dict:
    """반환 모양(열 이름) 관측 스윕 (주간 카덴스, §8.6) — scripts/ibl_shape_sweep.py.

    카탈로그의 ⟨열: …⟩ 은 fixture 실측이라 외부 API·수리로 썩는다 — 주간 재관측이 없으면
    모델이 옛 열 이름으로 filter/compute 를 쓰고 실패한다(조합의 1위 구조적 한계, 2026-08-21).
    returns_drift 와 같은 우주(fixture)·같은 규율(subprocess·주간)."""
    import subprocess
    from world_pulse_health import save_self_check
    _root = Path(__file__).parent.parent.parent
    state_path = _root / "data" / "ibl_shape_sweep_state.json"
    now = _time.time()
    try:
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    except Exception:
        state = {}
    if now - float(state.get("last_run", 0)) < 7 * 86400:
        return {"skipped": "cadence", "last_run": state.get("last_run")}
    script = _root / "scripts" / "ibl_shape_sweep.py"
    if not script.exists():
        return {"error": "scripts/ibl_shape_sweep.py 없음"}
    try:
        proc = subprocess.run([sys.executable, str(script)], cwd=str(_root),
                              capture_output=True, text=True, timeout=900)
    except Exception as e:
        return {"error": f"스윕 실행 실패: {str(e)[:150]}"}
    tail = (proc.stdout or "").strip().splitlines()[-1:] or [""]
    out = {"rc": proc.returncode, "summary": tail[0][:200]}
    try:
        save_self_check({"node": "__ibl_health__", "action": "shape_sweep",
                         "success": proc.returncode == 0, "response_ms": 0,
                         "data_quality": "ok" if proc.returncode == 0 else "sweep_failed",
                         "error_message": None if proc.returncode == 0 else (proc.stderr or "")[-200:]})
    except Exception:
        pass
    state["last_run"] = now
    try:
        state_path.write_text(json.dumps(state, ensure_ascii=False))
    except Exception:
        pass
    return out




def run_param_sweep() -> Dict:
    """입력 모양(인자 이름) 관측 스윕 (주간 카덴스, §8.6c) — scripts/ibl_param_sweep.py.

    카탈로그의 ⟨인자: …⟩ 는 교재·실행 실측이라 코퍼스 시딩·실사용이 쌓일수록 바뀐다 — 주간
    재관측이 없으면 새 낱말·새 인자가 카탈로그에 '인자 없음'으로 남는다(2026-08-23, ⟨열⟩의 거울).
    백엔드 API 를 두드리지 않는다(DB 만 읽음) — fixture 우주와 무관."""
    import subprocess
    from world_pulse_health import save_self_check
    _root = Path(__file__).parent.parent.parent
    state_path = _root / "data" / "ibl_param_sweep_state.json"
    now = _time.time()
    try:
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    except Exception:
        state = {}
    if now - float(state.get("last_run", 0)) < 7 * 86400:
        return {"skipped": "cadence", "last_run": state.get("last_run")}
    script = _root / "scripts" / "ibl_param_sweep.py"
    if not script.exists():
        return {"error": "scripts/ibl_param_sweep.py 없음"}
    try:
        proc = subprocess.run([sys.executable, str(script)], cwd=str(_root),
                              capture_output=True, text=True, timeout=600)
    except Exception as e:
        return {"error": f"스윕 실행 실패: {str(e)[:150]}"}
    tail = (proc.stdout or "").strip().splitlines()[-1:] or [""]
    out = {"rc": proc.returncode, "summary": tail[0][:200]}
    try:
        save_self_check({"node": "__ibl_health__", "action": "param_sweep",
                         "success": proc.returncode == 0, "response_ms": 0,
                         "data_quality": "ok" if proc.returncode == 0 else "sweep_failed",
                         "error_message": None if proc.returncode == 0 else (proc.stderr or "")[-200:]})
    except Exception:
        pass
    state["last_run"] = now
    try:
        state_path.write_text(json.dumps(state, ensure_ascii=False))
    except Exception:
        pass
    return out


def run_partner_sweep() -> Dict:
    """동반 낱말(조합 파트너) 관측 스윕 (주간 카덴스, §8.6d) — scripts/ibl_partner_sweep.py.

    카탈로그의 ⟨동반: …⟩ 은 교재·실행 실측이라 새 조합이 자리 잡을수록 바뀐다 — 주간 재관측이
    없으면 08-30 의 습관이 카탈로그에 화석으로 굳는다(⟨열⟩·⟨인자⟩의 형제). 광고가 처방이 되지
    않으려면 흔적이 계속 갱신돼야 한다. 백엔드 API 를 두드리지 않는다(DB 만 읽음)."""
    import subprocess
    from world_pulse_health import save_self_check
    _root = Path(__file__).parent.parent.parent
    state_path = _root / "data" / "ibl_partner_sweep_state.json"
    now = _time.time()
    try:
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    except Exception:
        state = {}
    if now - float(state.get("last_run", 0)) < 7 * 86400:
        return {"skipped": "cadence", "last_run": state.get("last_run")}
    script = _root / "scripts" / "ibl_partner_sweep.py"
    if not script.exists():
        return {"error": "scripts/ibl_partner_sweep.py 없음"}
    try:
        proc = subprocess.run([sys.executable, str(script)], cwd=str(_root),
                              capture_output=True, text=True, timeout=600)
    except Exception as e:
        return {"error": f"스윕 실행 실패: {str(e)[:150]}"}
    tail = (proc.stdout or "").strip().splitlines()[-1:] or [""]
    out = {"rc": proc.returncode, "summary": tail[0][:200]}
    try:
        save_self_check({"node": "__ibl_health__", "action": "partner_sweep",
                         "success": proc.returncode == 0, "response_ms": 0,
                         "data_quality": "ok" if proc.returncode == 0 else "sweep_failed",
                         "error_message": None if proc.returncode == 0 else (proc.stderr or "")[-200:]})
    except Exception:
        pass
    state["last_run"] = now
    try:
        state_path.write_text(json.dumps(state, ensure_ascii=False))
    except Exception:
        pass
    return out


def run_honesty_sweep() -> Dict:
    """정직성 불변식 스윕 (주간 카덴스, §8.6b) — scripts/honesty_invariants_sweep.py.

    왜 (2026-08-23, 상상훈련 21회차 평가): 침묵/거짓 성공 **부류**가 자리만 바꿔 7회 재발했다
    (B8→B10→F14-1→B15-1→F18-1→B19-1→B21-1). 자리별 수리는 부류를 못 막는다 — 성공 봉투의
    정직성을 fixture 우주 전체에서 한 입구로 단언해, 다음 위반자가 어느 핸들러에서 나오든
    여기서 잡히게 한다. 위반 = 판정 대기가 아니라 **수리 대상**(대장장이 입력).
    returns_drift 와 같은 우주·같은 규율(subprocess·주간·self_checks 기록)."""
    import subprocess
    from world_pulse_health import save_self_check
    _root = Path(__file__).parent.parent.parent
    state_path = _root / "data" / "honesty_sweep_state.json"
    now = _time.time()
    try:
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    except Exception:
        state = {}
    if now - float(state.get("last_run", 0)) < 7 * 86400:
        return {"skipped": "cadence", "last_run": state.get("last_run")}
    script = _root / "scripts" / "honesty_invariants_sweep.py"
    if not script.exists():
        return {"error": "scripts/honesty_invariants_sweep.py 없음"}
    try:
        proc = subprocess.run([sys.executable, str(script)], cwd=str(_root),
                              capture_output=True, text=True, timeout=900)
    except Exception as e:
        return {"error": f"스윕 실행 실패: {str(e)[:150]}"}
    marker = None
    for line in reversed((proc.stdout or "").splitlines()):
        if line.startswith("@@HONESTY@@"):
            marker = line[len("@@HONESTY@@"):].strip()
            break
    if proc.returncode != 0 or not marker:
        out = {"error": f"스윕 비정상 종료(rc={proc.returncode}, 마커 {'유' if marker else '무'})"}
    else:
        try:
            s = json.loads(marker)
        except Exception as e:
            s, out = None, {"error": f"요약 파싱 실패: {str(e)[:100]}"}
        if s is not None:
            viol = s.get("violations") or []
            out = {"checked": s.get("checked"), "violations": viol,
                   "prefix_contract_sites": s.get("prefix_contract_sites")}
            ok = not viol
            by = {}
            for v in viol:
                by.setdefault(v.get("inv"), []).append(v.get("name"))
            note = " / ".join(f"{k} {len(v)}건: {', '.join(v[:4])}" for k, v in sorted(by.items())) or None
            try:
                save_self_check({"node": "__ibl_health__", "action": "honesty_invariants",
                                 "success": ok, "response_ms": 0,
                                 "data_quality": "ok" if ok else "dishonest_envelope",
                                 "error_message": note and note[:220]})
            except Exception:
                pass
            if not ok:
                logger.warning(f"[Maintenance] 정직성 불변식 위반 {len(viol)}건: {note}")
    state["last_run"] = now
    try:
        state_path.write_text(json.dumps(state, ensure_ascii=False))
    except Exception:
        pass
    return out


def run_all_sweeps() -> Dict:
    """주간 스윕 다섯을 한 입구로 — 호출부(world_pulse_health §8.5~8.6b)가 스윕마다
    자라지 않게(2026-08-30). 하나가 죽어도 나머지는 돈다(개별 격리, 옛 호출부와 같은 규율).

    반환 키는 옛 호출부와 동일하다 — 유지보수 번들 결과를 읽는 쪽(계기판·로그)이 그대로 산다."""
    import logging
    log = logging.getLogger(__name__)
    out: Dict = {}
    for key, fn_name, label in (
        ("returns_drift", "run_returns_drift_sweep", "returns 드리프트"),
        ("shape_sweep", "run_shape_sweep", "반환 모양"),
        ("param_sweep", "run_param_sweep", "입력 모양"),
        ("partner_sweep", "run_partner_sweep", "동반 낱말"),
        ("honesty_sweep", "run_honesty_sweep", "정직성"),
    ):
        try:
            out[key] = globals()[fn_name]()
        except Exception as e:  # noqa: BLE001 — 한 스윕의 죽음이 나머지를 끌고 가지 않는다
            log.warning(f"[Maintenance] {label} 스윕 실패 (무시): {e}")
    return out
