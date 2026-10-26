"""health_probes.py — IBL 건강 점검 러너의 subprocess 순찰 4종 (world_pulse_health 에서 분리, 2026-10-26 — 1500줄 규칙)

- _run_import_coverage: 의존성 커버리지(§1F, scripts/check_import_coverage.py)
- _run_playwright_browsers: playwright 브라우저 주소 정합(§1G)
- _run_silent_failure_regression: 침묵-실패 회귀 스위트(§1E)
- _run_red_drift: RED 드리프트(§1H, scripts/check_red_drift.py)
모두 subprocess(라이브 프로세스 무접촉)이며 self_checks 형식의 행 하나를 돌려준다.
호출자는 world_pulse_health.run_ibl_health_check 하나다.
"""
import sys
import time as _time
from pathlib import Path
from typing import Dict

def _run_import_coverage(_root) -> Dict:
    """의존성 커버리지 순찰(§1F) — scripts/check_import_coverage.py 를 1회 실행.

    계약: 마지막 줄 '@@IMPORT_COVERAGE_JSON@@ {…}' (ibl_health_check 의
    @@HEALTH_JSON@@ 과 동형). rc·마커 부재·파싱 실패는 전부 명시적 fail —
    검사기가 죽었는데 옛 GREEN 이 남는 침묵 실패를 만들지 않는다.
    """
    import subprocess
    import json as _json
    key = {"node": "__static__", "action": "import_coverage", "response_ms": 0}
    script = _root / "scripts" / "check_import_coverage.py"
    if not script.exists():
        return {**key, "success": False, "data_quality": "error",
                "error_message": "scripts/check_import_coverage.py 없음"}
    try:
        proc = subprocess.run([sys.executable, str(script)], cwd=str(_root),
                              capture_output=True, text=True, timeout=600)
    except Exception as e:
        return {**key, "success": False, "data_quality": "error",
                "error_message": f"실행 실패: {str(e)[:150]}"}
    marker = None
    for line in reversed((proc.stdout or "").splitlines()):
        if line.startswith("@@IMPORT_COVERAGE_JSON@@"):
            marker = line[len("@@IMPORT_COVERAGE_JSON@@"):].strip()
            break
    if marker is None:
        tail = ((proc.stderr or "").strip() or (proc.stdout or "").strip())[-180:]
        return {**key, "success": False, "data_quality": "error",
                "error_message": f"요약 마커 없음(rc={proc.returncode}): {tail}"}
    try:
        s = _json.loads(marker)
    except Exception as e:
        return {**key, "success": False, "data_quality": "error",
                "error_message": f"요약 JSON 파싱 실패: {str(e)[:120]}"}
    ok = bool(s.get("ok"))
    if ok:
        return {**key, "success": True, "data_quality": "ok", "error_message": None}
    names = ", ".join(f.get("name", "?") for f in (s.get("failures") or [])[:6])
    return {**key, "success": False, "data_quality": "dependency_missing",
            "error_message": f"미선언/파손 의존성 {len(s.get('failures') or [])}건: {names}"[:220]}


def _run_playwright_browsers(_root) -> Dict:
    """playwright 브라우저 주소 순찰(§1G) — scripts/check_playwright_browsers.py 1회 실행.

    계약: 마지막 줄 '@@PLAYWRIGHT_BROWSERS_JSON@@ {…}' (§1F 와 동형). rc 는 보지 않고
    요약 JSON 의 ok 를 본다 — 마커 부재·파싱 실패는 명시적 fail(검사기가 죽었는데 옛
    GREEN 이 남는 침묵 실패를 만들지 않는다). playwright 미설치는 이 점검의 소관이
    아니므로(§1F 의존성 감사가 본다) 통과시킨다.

    ★sys.executable 로 도는 것이 핵심: '어느 playwright 가 어느 빌드를 기대하는가' 는
    백엔드가 실제로 쓰는 그 인터프리터에서만 참이다.
    """
    import subprocess
    import json as _json
    key = {"node": "__static__", "action": "playwright_browsers", "response_ms": 0}
    script = _root / "scripts" / "check_playwright_browsers.py"
    if not script.exists():
        return {**key, "success": False, "data_quality": "error",
                "error_message": "scripts/check_playwright_browsers.py 없음"}
    try:
        proc = subprocess.run([sys.executable, str(script), "--json"], cwd=str(_root),
                              capture_output=True, text=True, timeout=120)
    except Exception as e:
        return {**key, "success": False, "data_quality": "error",
                "error_message": f"실행 실패: {str(e)[:150]}"}
    marker = None
    for line in reversed((proc.stdout or "").splitlines()):
        if line.startswith("@@PLAYWRIGHT_BROWSERS_JSON@@"):
            marker = line[len("@@PLAYWRIGHT_BROWSERS_JSON@@"):].strip()
            break
    if marker is None:
        tail = ((proc.stderr or "").strip() or (proc.stdout or "").strip())[-180:]
        return {**key, "success": False, "data_quality": "error",
                "error_message": f"요약 마커 없음(rc={proc.returncode}): {tail}"}
    try:
        s = _json.loads(marker)
    except Exception as e:
        return {**key, "success": False, "data_quality": "error",
                "error_message": f"요약 JSON 파싱 실패: {str(e)[:120]}"}
    if s.get("ok"):
        return {**key, "success": True, "data_quality": "ok", "error_message": None}
    return {**key, "success": False, "data_quality": "browser_missing",
            "error_message": (s.get("note") or
                              f"기대 빌드 없음: {', '.join(s.get('missing') or [])}")[:220]}


def _run_silent_failure_regression(_root) -> Dict:
    """침묵-실패 회귀 순찰(§1E) — 현행 언어·도구 회귀 파일을 백엔드 인터프리터로 실행해 한 항목으로 기록.

    성공=모든 스위트 rc 0. 실패 시 어느 파일의 어떤 케이스인지 출력 꼬리를 동반한다.
    """
    import subprocess
    suites = ["backend/test_ibl_v2_core.py", "backend/test_ibl_silent_failures.py",
              "backend/test_pipe_currency_failures.py"]
    t0 = _time.time()
    for rel in suites:
        script = _root / rel
        if not script.exists():
            return {"node": "__static__", "action": "silent_failure_regression",
                    "success": False, "response_ms": 0, "data_quality": "error",
                    "error_message": f"{rel} 없음"}
        try:
            proc = subprocess.run([sys.executable, "-m", "pytest", str(script)], cwd=str(_root),
                                  capture_output=True, text=True, timeout=180)
        except Exception as e:
            return {"node": "__static__", "action": "silent_failure_regression",
                    "success": False, "response_ms": int((_time.time() - t0) * 1000),
                    "data_quality": "error",
                    "error_message": f"{rel} 실행 실패: {str(e)[:150]}"}
        if proc.returncode != 0:
            tail = ((proc.stderr or "").strip() or (proc.stdout or "").strip())[-200:]
            return {"node": "__static__", "action": "silent_failure_regression",
                    "success": False, "response_ms": int((_time.time() - t0) * 1000),
                    "data_quality": "regression_failure",
                    "error_message": f"{Path(rel).name} rc={proc.returncode}: {tail}"}
    return {"node": "__static__", "action": "silent_failure_regression",
            "success": True, "response_ms": int((_time.time() - t0) * 1000),
            "data_quality": "ok", "error_message": None}


def _run_red_drift(_root) -> Dict:
    """RED 드리프트 순찰(§1H, 2026-08-18) — 격리를 안 지난 살아있는 기질 변경 가시화.

    08-17 워크트리 격리는 `[self:write]`/`[self:edit]` 문 하나에만 걸려 있다.
    아웃오브프로세스 편집자(Claude Code 세션)·`[self:script]`·`run_command` 는
    backend 를 라이브로 직행하고, 게이트는 repo 루트 미탐지 시 fail-open 이다.
    차단은 원리적으로 불가(그 손은 이 프로세스 밖) — 그래서 **가시성**만 맡는다.

    신호는 git 이 낸다: 미커밋 backend/*.py 인데 격리 세션이 안 붙잡은 것 + 고아 격리본.
    작업 중(24시간 이내)은 통과, 방치는 실패. 커밋(=사람 승인)하면 저절로 해소된다.
    """
    import subprocess
    script = _root / "scripts" / "check_red_drift.py"
    if not script.exists():
        return {"node": "__static__", "action": "red_drift", "success": False,
                "response_ms": 0, "data_quality": "error",
                "error_message": "scripts/check_red_drift.py 없음"}
    t0 = _time.time()
    try:
        proc = subprocess.run([sys.executable, str(script)], cwd=str(_root),
                              capture_output=True, text=True, timeout=120)
    except Exception as e:
        return {"node": "__static__", "action": "red_drift", "success": False,
                "response_ms": int((_time.time() - t0) * 1000), "data_quality": "error",
                "error_message": f"실행 실패: {str(e)[:150]}"}
    ms = int((_time.time() - t0) * 1000)
    if proc.returncode == 0:
        return {"node": "__static__", "action": "red_drift", "success": True,
                "response_ms": ms, "data_quality": "ok", "error_message": None}
    # 방치 항목 요약 — 어느 파일이 격리 밖에 떠 있는지가 곧 진단이다.
    stale = [l.strip() for l in (proc.stdout or "").splitlines() if "‼ 방치" in l]
    note = " / ".join(stale)[:220] or ((proc.stdout or proc.stderr or "").strip()[-220:])
    return {"node": "__static__", "action": "red_drift", "success": False,
            "response_ms": ms, "data_quality": "isolation_bypass", "error_message": note}
