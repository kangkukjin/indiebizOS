"""fixture_sweeps.py — fixture 우주를 라이브 실행하는 주간 스윕 2종 (world_pulse_health 에서 분리, 2026-08-21 — 1500줄 규칙)

- run_returns_drift_sweep: returns 선언 ↔ 실측 통화 모양 대조 (scripts/returns_drift_sweep.py)
- run_shape_sweep: 실측 반환 열 관측 → data/ibl_return_shapes.json → 카탈로그 ⟨열: …⟩ (scripts/ibl_shape_sweep.py)
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


