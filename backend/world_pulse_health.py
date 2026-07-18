"""
world_pulse_health.py - World Pulse 건강 점검 및 가이드 생성 모듈
IndieBiz OS Core

world_pulse.py에서 분리된 모듈로, 시스템 건강 점검(Self-Check)과
가이드 파일 생성 기능을 담당합니다.

기능:
1. generate_guide: world_pulse.md 가이드 파일 생성/갱신
2. 일일 건강 점검: ibl_health_check.py(정적+fixture+골든) 1회 + RED 면 알림 (AI 0)
3. 시스템 건강 요약 API + 패턴 분석

사용:
    from world_pulse_health import generate_guide, run_daily_health_check, get_system_health
"""

import json
import logging
import sys
import time as _time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 가이드 파일 생성
# ============================================================

def generate_guide():
    """world_pulse.md 생성 — 현재 위치 + 금주 일정만 (2026-06-28 단순화).

    의식 에이전트 입력 전용. 나머지(경제·날씨·뉴스·시스템상태·proprioception)는
    정기 수집 폐지 → on-demand 감각(sense:here/host/world)·계기판 live pull 로 이관.
    위치·일정은 매번 fresh 로 당긴다(스냅샷 의존 없음).
    """
    from world_pulse import PULSE_GUIDE_PATH
    from world_pulse_collectors import _collect_location, _collect_week_schedule
    from datetime import datetime as _dt

    lines = [
        "# World Pulse — 지금의 나와 세계 (자동 주입)",
        f"측정 시각: {_dt.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # 현재 위치 (폰 [sense:here] 위임 — 폰이 꺼져 있거나 닿지 않으면 생략)
    loc = _collect_location()
    if loc:
        lines.append("## 현재 위치")
        lines.append(f"- {loc}")
        lines.append("")

    # 금주 일정 (오늘~이번 주 일요일)
    events = _collect_week_schedule()
    if events:
        lines.append("## 금주 일정")
        for ev in events:
            lines.append(f"- {ev}")
        lines.append("")

    PULSE_GUIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PULSE_GUIDE_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    logger.info("[WorldPulse] 가이드 갱신 완료 (위치+금주일정)")

    # 진단 리포트도 함께 갱신 (Pulse 주기 편승, AI 비용 0)
    try:
        save_diagnostic_report()
    except Exception as e:
        logger.debug(f"[WorldPulse] 진단 리포트 갱신 실패 (무시): {e}")


# ============================================================
# Self-Check — 주기적 IBL 액션 자가 점검 (면역 순찰)
# ============================================================

# 【제거됨 2026-07-18】 AI 기반 테스트 계획 생성
# 경량 LLM 이 액션을 훑어 부작용을 분류하고 data/self_check_plan.json 에 캐시하던 층.
# 생성 함수는 2026-06-27(065c5a9)에 self-check 가 fixture 방식으로 바뀌며 삭제됐는데,
# 헬퍼(_load_test_plan/_save_test_plan/_get_actions_hash)와 캐시 파일만 남아
# 3주 넘게 118개짜리 낡은 목록이 조종실 dry-run 의 부작용 라벨을 대신해 왔다(당시 157개).
# → 분류는 backend/ibl_safety.py 가 레지스트리 `returns:` 선언에서 파생한다(캐시 없음).

def run_ibl_health_check() -> List[Dict]:
    """IBL 건강검사의 단일 소스 — scripts/ibl_health_check.py 를 subprocess 1회 실행하고
    §1A 정적 정합성 + §1B 통화(fixture) + §1C 골든파이프 결과를 self_checks 형식으로 반환.

    구조 건강이 변하는 건 어휘를 쓸 때뿐이고(그건 커밋 시 --check 가 막는다), 이건 그 정적
    검사 + fixture 행동검사 + 흐름검사를 하루 1회 회귀 그물로 한 번 더 돌리는 것. AI 0.

    ★계약(검증자 튼튼화, 2026-07-03): 스크립트가 마지막에 '@@HEALTH_JSON@@ {…}' 한 줄로
    기계 판독 요약을 내놓는다. 옛 방식(사람용 한국어 stdout 정규식 스크레이핑 + returncode
    무시)은 문구가 바뀌거나 스크립트가 죽으면 이벤트가 조용히 사라져 대시보드가 옛 GREEN 을
    계속 보여주는 침묵 실패 구조였다. 이제 returncode·마커 부재·파싱 실패는 전부
    __ibl_health__:ibl_health_check 의 명시적 fail 이벤트가 된다(대시보드가 이 키도 읽는다).
    """
    import subprocess
    import json as _json
    _root = Path(__file__).parent.parent
    _script = _root / "scripts" / "ibl_health_check.py"

    def _runner_fail(msg: str) -> List[Dict]:
        return [{"node": "__ibl_health__", "action": "ibl_health_check", "success": False,
                 "response_ms": 0, "data_quality": "error", "error_message": msg[:220]}]

    if not _script.exists():
        return _runner_fail("scripts/ibl_health_check.py 없음")
    try:
        proc = subprocess.run(
            [sys.executable, str(_script)],
            cwd=str(_root), capture_output=True, text=True, timeout=300,
        )
    except Exception as e:
        return _runner_fail(f"ibl_health_check 실행 실패: {str(e)[:150]}")

    text = proc.stdout or ""
    marker = None
    for line in reversed(text.splitlines()):
        if line.startswith("@@HEALTH_JSON@@"):
            marker = line[len("@@HEALTH_JSON@@"):].strip()
            break
    if proc.returncode != 0 or not marker:
        tail = ((proc.stderr or "").strip() or text.strip())[-180:]
        return _runner_fail(
            f"점검 스크립트 비정상 종료(rc={proc.returncode}, 요약마커 {'유' if marker else '무'}): {tail}")
    try:
        s = _json.loads(marker)
    except Exception as e:
        return _runner_fail(f"요약 JSON 파싱 실패: {str(e)[:120]}")

    out = []
    # §1A 정적 정합성
    static_ok = bool(s.get("static_ok"))
    out.append({"node": "__static__", "action": "ibl_consistency",
                "success": static_ok, "response_ms": 0,
                "data_quality": "ok" if static_ok else "consistency_failure",
                "error_message": None if static_ok else "build --check 불일치 — src↔tool.json↔handler/fixture"})
    # §1B 통화
    cur = s.get("currency") or {}
    g, y, r = int(cur.get("green", 0)), int(cur.get("yellow", 0)), int(cur.get("red", 0))
    note = f"GREEN {g} / YELLOW {y} / RED {r}"
    reds = cur.get("reds") or []
    if reds:
        note += " — " + "; ".join(f"{d.get('name')}:{str(d.get('reason'))[:60]}" for d in reds[:5])
    out.append({"node": "__ibl_health__", "action": "currency",
                "success": r == 0, "response_ms": 0,
                "data_quality": "ok" if r == 0 else "currency_broken",
                "error_message": None if r == 0 else note})
    # §1C 골든파이프
    gp = s.get("golden_pipes") or {}
    passed, total = int(gp.get("passed", 0)), int(gp.get("total", 0))
    gp_ok = total > 0 and passed == total
    out.append({"node": "__ibl_health__", "action": "golden_pipes",
                "success": gp_ok, "response_ms": 0,
                "data_quality": "ok" if gp_ok else "error",
                "error_message": None if gp_ok else f"{passed}/{total} PASS"})
    # §1C-2 연산자(?? · &) — 골든파이프가 못 보는 문법층. 이 항목이 없던 동안 `??` 가
    # NameError 로 죽은 채 몇 달을 버텼다(문서·프롬프트는 가르치는데 아무도 검사 안 함).
    # 옛 요약(operators 키 없음)은 total=0 → 스킵하고 항목을 남기지 않는다.
    op = s.get("operators") or {}
    op_passed, op_total = int(op.get("passed", 0)), int(op.get("total", 0))
    if op_total > 0:
        op_ok = op_passed == op_total
        out.append({"node": "__ibl_health__", "action": "operators",
                    "success": op_ok, "response_ms": 0,
                    "data_quality": "ok" if op_ok else "error",
                    "error_message": None if op_ok else f"{op_passed}/{op_total} PASS"})
    # 러너 자신의 성공 기록 — 대시보드의 '점검 실행 실패' 항목을 초록으로 되돌리는 짝
    out.append({"node": "__ibl_health__", "action": "ibl_health_check", "success": True,
                "response_ms": 0, "data_quality": "ok", "error_message": None})
    return out


def run_maintenance_bundle() -> Dict:
    """기계적 유지보수 번들 — 일일 건강 점검(run_daily_health_check) 끝에서 호출한다.
    IBL 건강과는 별개(forage 정리·메모리/해마 정리·연속실패 알림). 각 항목은 자체 카덴스
    게이트/저비용이라 매일 호출돼도 안전하다(대부분 즉시 스킵).
    """
    result: Dict[str, Any] = {}

    # 1) 만성 실패 능동 알림
    try:
        from world_pulse import _load_config
        threshold = _load_config().get("self_check", {}).get("failure_alert_threshold", 3)
        _check_failure_alerts(threshold)
    except Exception as e:
        logger.warning(f"[Maintenance] 실패 알림 실패 (무시): {e}")

    # 2) 심층메모리 정리 패스 (DB별 24h 카덴스)
    try:
        from memory_consolidation import run_memory_consolidation
        mc = run_memory_consolidation()
        result["memory"] = mc
        if mc.get("consolidated"):
            logger.info(f"[Maintenance] 기억 정리: {mc['consolidated']}/{mc['databases']} DB 처리")
    except Exception as e:
        logger.warning(f"[Maintenance] 기억 정리 실패 (무시): {e}")

    # 3) 해마 정리 패스 (24h 카덴스)
    try:
        from ibl_usage_rag import run_hippocampus_consolidation
        hp = run_hippocampus_consolidation()
        result["hippocampus"] = hp
        if hp.get("deleted_total") or hp.get("json_removed"):
            logger.info(
                f"[Maintenance] 해마 정리: 증류물 삭제 {hp.get('deleted_total', 0)} / "
                f"json {hp.get('json_removed', 0)}"
            )
    except Exception as e:
        logger.warning(f"[Maintenance] 해마 정리 실패 (무시): {e}")

    # 4) 포식 기억 정리 패스 (24h 카덴스) — 냄새지도 의미적 근접중복 병합
    try:
        from forage_consolidation import run_forage_consolidation
        fc = run_forage_consolidation()
        result["forage"] = fc
        if fc.get("map_merged") or fc.get("owner_merged") or fc.get("pruned_map"):
            logger.info(
                f"[Maintenance] 포식 정리: map 병합 {fc.get('map_merged', 0)} / "
                f"owner 병합 {fc.get('owner_merged', 0)} / 가지치기 {fc.get('pruned_map', 0)}"
            )
    except Exception as e:
        logger.warning(f"[Maintenance] 포식 정리 실패 (무시): {e}")

    # 5) IBL 설명 의미 드리프트 점검 (주간 카덴스) — `--check`의 *의미* 판.
    #    구조 --check가 못 보는 description 산문의 stale 어휘·끊긴 참조를 경량 LLM이 플래그.
    try:
        from ibl_description_audit import run_description_drift_check
        dd = run_description_drift_check()
        result["description_drift"] = dd
        if dd.get("flags"):
            logger.warning(f"[Maintenance] IBL 설명 드리프트 {len(dd['flags'])}건 — ibl_description_flags.json")
        # 실제 실행됐으면 성공/실패 무관하게 기록 — 깃발 있을 때만 저장하면 깨끗해진 뒤에도
        # 옛 fail 이 '마지막 기록'으로 영구 잔존한다(조종실 유령 빨간불).
        if dd.get("node"):
            try:
                save_self_check(dd)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[Maintenance] 설명 드리프트 점검 실패 (무시): {e}")

    # 6) 어휘 결정화 감지 (주간 카덴스) — §4 마찰 신호 텔레메트리.
    #    raw-코드 추락(카탈로그 굶주림 경보 겸용)·IBL 실패→쉘 폴백·반복 다단 조합을
    #    에피소드 로그에서 세어 승격 후보를 깃발로 표출. 감지는 시스템, 결정은 사용자.
    try:
        from vocab_crystallization import run_crystallization_scan
        cz = run_crystallization_scan()
        result["crystallization"] = cz
        if cz.get("node"):  # 실제 실행됨 (카덴스 스킵이 아님)
            try:
                save_self_check(cz)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[Maintenance] 결정화 감지 실패 (무시): {e}")

    # 7) 좀비 건강기록 청소 — 은퇴·이동한 어휘의 self_checks/action_health 잔재 제거.
    #    저비용(SELECT DISTINCT + 드문 DELETE)이라 매일 호출해도 안전.
    try:
        zp = purge_zombie_health_records()
        result["zombie_purge"] = zp
        rows = sum((v or {}).get("rows", 0) for v in (zp.get("removed") or {}).values())
        if rows:
            logger.info(f"[Maintenance] 좀비 건강기록 청소: {rows}행 제거")
    except Exception as e:
        logger.warning(f"[Maintenance] 좀비 건강기록 청소 실패 (무시): {e}")

    return result


def purge_zombie_health_records() -> Dict:
    """은퇴·이동한 어휘의 건강 기록 청소 — 어휘 생애주기 대칭(어휘 제거가 기록도 지운다).

    self_checks/action_health 의 (node, action) 중 현존 어휘(data/ibl_nodes.yaml)에 없는
    액션의 행을 지운다. 남겨두면 '마지막 기록=fail'이 영구 잔존해 유령 경고등이 된다
    (실례: table 분리로 이사간 engines:filter 9종, 은퇴한 others:neighbors).
    __static__/__ibl_health__ 같은 시스템 네임스페이스(__ 접두)는 보존.
    """
    import yaml
    from world_pulse import _get_pulse_db

    nodes_path = Path(__file__).parent.parent / "data" / "ibl_nodes.yaml"
    try:
        with open(nodes_path, encoding="utf-8") as f:
            nodes = (yaml.safe_load(f) or {}).get("nodes", {})
    except Exception as e:
        return {"error": f"ibl_nodes.yaml 로드 실패: {e}"}
    valid = {(n, a) for n, nd in nodes.items() for a in ((nd or {}).get("actions") or {})}
    if not valid:
        return {"error": "어휘 레지스트리가 비어 있음 — 청소 중단(안전판)"}

    removed = {}
    try:
        conn = _get_pulse_db()
        for table in ("self_checks", "action_health"):
            try:
                pairs = conn.execute(f"SELECT DISTINCT node, action FROM {table}").fetchall()
            except Exception:
                continue  # 테이블 없으면 스킵
            zombies = [(r["node"], r["action"]) for r in pairs
                       if r["node"] and not str(r["node"]).startswith("__")
                       and (r["node"], r["action"]) not in valid]
            cnt = 0
            for n, a in zombies:
                cur = conn.execute(f"DELETE FROM {table} WHERE node=? AND action=?", (n, a))
                cnt += cur.rowcount
            if cnt:
                conn.commit()
            removed[table] = {"pairs": len(zombies), "rows": cnt}
        conn.close()
    except Exception as e:
        return {"error": str(e), "removed": removed}
    return {"removed": removed}


def save_self_check(result: Dict):
    """자가점검 결과 저장"""
    from world_pulse import _get_pulse_db

    try:
        conn = _get_pulse_db()
        conn.execute(
            "INSERT INTO self_checks (timestamp, node, action, success, response_ms, error_message, data_quality) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(),
                result.get("node", ""),
                result.get("action", ""),
                1 if result.get("success") else 0,
                result.get("response_ms"),
                result.get("error_message"),
                result.get("data_quality"),
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[SelfCheck] 저장 실패: {e}")


def purge_action_records(actions: List[str]) -> Dict:
    """제거된 액션의 건강기록을 world_pulse.db에서 삭제한다.

    action_health / self_checks 두 테이블의 `action` 컬럼은 `node:` 없는 **맨
    액션명**(예: 'chart', 'filter')이다. 액션을 제거하고도 이 기록을 남기면
    X-Ray에 존재하지 않는 액션이 계속 비정상으로 표시된다(action_removal.md 5번).
    패키지 제거 경로가 호출한다. 반환: {"action_health": n, "self_checks": n}.
    """
    result = {"action_health": 0, "self_checks": 0}
    names = [a for a in (actions or []) if a]
    if not names:
        return result
    from world_pulse import _get_pulse_db
    ph = ",".join("?" * len(names))
    try:
        conn = _get_pulse_db()
        for table in ("action_health", "self_checks"):
            try:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE action IN ({ph})", names
                )
                result[table] = cur.rowcount
            except Exception as e:
                logger.warning(f"[SelfCheck] {table} 정리 실패: {e}")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[SelfCheck] 건강기록 정리 실패: {e}")
    return result


def _check_failure_alerts(threshold: int = 3):
    """연속 실패 액션 감지 및 알림"""
    from world_pulse import _get_pulse_db

    try:
        conn = _get_pulse_db()
        # 각 액션의 최근 N회 결과 확인
        rows = conn.execute("""
            SELECT node, action, GROUP_CONCAT(success) as recent
            FROM (
                SELECT node, action, success,
                       ROW_NUMBER() OVER (PARTITION BY node, action ORDER BY id DESC) as rn
                FROM self_checks
            ) WHERE rn <= ?
            GROUP BY node, action
        """, (threshold,)).fetchall()
        conn.close()

        failing = []
        for row in rows:
            recent = row["recent"]  # e.g. "0,0,0"
            if recent:
                successes = [int(x) for x in recent.split(",")]
                if len(successes) >= threshold and all(s == 0 for s in successes):
                    failing.append(f"[{row['node']}:{row['action']}]")

        if failing:
            try:
                from notification_manager import get_notification_manager
                nm = get_notification_manager()
                nm.create(
                    title="자가점검 경고",
                    message=f"연속 {threshold}회 실패: {', '.join(failing)}",
                    type="warning",
                    source="self_check"
                )
            except Exception as e:
                logger.warning(f"[SelfCheck] 알림 발송 실패: {e}")
    except Exception as e:
        logger.debug(f"[SelfCheck] 실패 알림 체크 오류: {e}")


def analyze_failure_patterns() -> Dict:
    """자가점검 결과에서 패턴을 분석 — 반복 실패, 성능 저하 추이 감지

    Returns:
        chronic_failures: 최근 3회 연속 실패한 액션
        degrading: 성공률이 하락 추세인 액션
        slowdowns: 응답 시간이 증가 추세인 액션
        recovered: 이전에 실패했다가 최근 복구된 액션
    """
    from world_pulse import _get_pulse_db

    try:
        conn = _get_pulse_db()
        cutoff_7d = (datetime.now() - timedelta(days=7)).isoformat()
        cutoff_3d = (datetime.now() - timedelta(days=3)).isoformat()

        # 최근 7일 실사용 데이터만 — 건강 체크(self_check) 실패는 제외
        # 건강 체크 실패는 테스트 환경 문제(파라미터/컨텍스트 부족)일 수 있으므로
        # 실사용 실패만으로 패턴을 판단해야 정확하다.
        rows = conn.execute("""
            SELECT node, action, success, response_ms, timestamp, 'usage' as data_quality
            FROM action_health
            WHERE timestamp >= ? AND source = 'usage'
            ORDER BY node, action, timestamp
        """, (cutoff_7d,)).fetchall()
        if not rows:
            rows = conn.execute("""
                SELECT node, action, success, response_ms, timestamp, data_quality
                FROM self_checks
                WHERE timestamp >= ?
                ORDER BY node, action, timestamp
            """, (cutoff_7d,)).fetchall()
        conn.close()

        if not rows:
            return {}

        # 액션별 그룹핑
        action_data = {}
        for r in rows:
            key = f"{r['node']}:{r['action']}"
            if key not in action_data:
                action_data[key] = []
            action_data[key].append({
                "success": r["success"],
                "response_ms": r["response_ms"],
                "timestamp": r["timestamp"],
                "data_quality": r["data_quality"],
            })

        chronic_failures = []  # 최근 3회 연속 실패
        degrading = []         # 성공률 하락 추세
        slowdowns = []         # 응답 시간 증가 추세
        recovered = []         # 실패 후 복구

        for key, checks in action_data.items():
            if len(checks) < 2:
                continue

            # 연속 실패 감지
            recent = checks[-3:] if len(checks) >= 3 else checks
            if all(c["success"] == 0 for c in recent):
                chronic_failures.append(key)

            # 성공률 추이 (전반 vs 후반)
            mid = len(checks) // 2
            if mid > 0:
                first_half_rate = sum(c["success"] for c in checks[:mid]) / mid
                second_half_rate = sum(c["success"] for c in checks[mid:]) / (len(checks) - mid)
                if first_half_rate >= 0.8 and second_half_rate < 0.6:
                    degrading.append({"action": key, "before": round(first_half_rate * 100), "after": round(second_half_rate * 100)})

            # 응답 시간 추이
            times = [c["response_ms"] for c in checks if c["response_ms"] is not None]
            if len(times) >= 4:
                mid_t = len(times) // 2
                avg_first = sum(times[:mid_t]) / mid_t
                avg_second = sum(times[mid_t:]) / (len(times) - mid_t)
                if avg_first > 0 and avg_second / avg_first > 2.0:
                    slowdowns.append({"action": key, "before_ms": round(avg_first), "after_ms": round(avg_second)})

            # 복구 감지 (이전 실패 → 최근 성공)
            if len(checks) >= 3:
                had_failures = any(c["success"] == 0 for c in checks[:-2])
                recent_ok = all(c["success"] == 1 for c in checks[-2:])
                if had_failures and recent_ok:
                    recovered.append(key)

        result = {}
        if chronic_failures:
            result["chronic_failures"] = chronic_failures
        if degrading:
            result["degrading"] = degrading
        if slowdowns:
            result["slowdowns"] = slowdowns
        if recovered:
            result["recovered"] = recovered

        # 알림 생성 — 만성 실패나 성능 저하가 있을 때
        alerts = []
        if chronic_failures:
            alerts.append(f"만성 실패: {', '.join(chronic_failures)}")
        if degrading:
            alerts.append(f"성공률 하락: {', '.join(d['action'] for d in degrading)}")
        if slowdowns:
            alerts.append(f"응답 느려짐: {', '.join(s['action'] for s in slowdowns)}")

        if alerts:
            try:
                from notification_manager import get_notification_manager
                nm = get_notification_manager()
                nm.create(
                    title="자가점검 패턴 분석",
                    message=" / ".join(alerts),
                    type="warning" if chronic_failures else "info",
                    source="self_check_pattern"
                )
            except Exception:
                pass

        return result
    except Exception as e:
        logger.debug(f"[SelfCheck] 패턴 분석 실패: {e}")
        return {}


def get_action_health_summary() -> Dict:
    """액션별 건강 상태 요약 — action_health 테이블 기반

    상태 판정 기준:
    - verified: 실사용(usage)에서 최근 성공 기록 있음
    - failed: 실사용(usage)에서 최근 실패 기록 있고 그 이후 성공 없음
    - assumed: 실사용 기록 없음 (건강 체크 전용 실패는 failed로 올리지 않음)
    """
    from world_pulse import _get_pulse_db

    try:
        conn = _get_pulse_db()
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()

        # 실사용(usage) 기록으로 상태 판정
        rows = conn.execute("""
            SELECT node, action,
                   COUNT(*) as total,
                   SUM(success) as successes,
                   AVG(response_ms) as avg_ms,
                   MAX(CASE WHEN success = 1 THEN timestamp END) as last_success,
                   MAX(CASE WHEN success = 0 AND source = 'usage' THEN timestamp END) as last_usage_failure
            FROM action_health
            WHERE timestamp >= ?
            GROUP BY node, action
        """, (cutoff,)).fetchall()

        # action_health가 비어있으면 기존 self_checks에서 폴백
        if not rows:
            rows = conn.execute("""
                SELECT node, action,
                       COUNT(*) as total,
                       SUM(success) as successes,
                       AVG(response_ms) as avg_ms,
                       MAX(CASE WHEN success = 1 THEN timestamp END) as last_success,
                       MAX(CASE WHEN success = 0 THEN timestamp END) as last_usage_failure
                FROM self_checks
                WHERE timestamp >= ?
                GROUP BY node, action
            """, (cutoff,)).fetchall()

        conn.close()

        summary = {}
        for row in rows:
            key = f"{row['node']}:{row['action']}"
            total = row["total"]
            successes = row["successes"] or 0
            last_success = row["last_success"]
            last_usage_failure = row["last_usage_failure"]

            # 3단계 상태 결정: verified / assumed / failed
            # 실사용 성공 있으면 verified, 실사용 실패만 있으면 failed
            if last_success and (not last_usage_failure or last_success > last_usage_failure):
                status = "verified"
            elif last_usage_failure and (not last_success or last_usage_failure >= last_success):
                status = "failed"
            else:
                status = "assumed"

            summary[key] = {
                "total": total,
                "success_rate": round(successes / total * 100, 1) if total > 0 else 0,
                "avg_response_ms": round(row["avg_ms"]) if row["avg_ms"] else None,
                "status": status,
            }
        return summary
    except Exception as e:
        logger.debug(f"[ActionHealth] 요약 조회 실패: {e}")
        return {}


def record_action_health(node: str, action: str, success: bool, response_ms: int = None, source: str = "usage"):
    """액션 실행 결과를 action_health 테이블에 기록 — 경량, 실패 시 무시"""
    from world_pulse import _get_pulse_db

    try:
        conn = _get_pulse_db()
        conn.execute(
            "INSERT INTO action_health (node, action, success, response_ms, source, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (node, action, 1 if success else 0, response_ms, source, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # 기록 실패가 액션 실행에 영향 주면 안 됨


def get_recent_self_checks(limit: int = 20) -> List[Dict]:
    """최근 자가점검 결과 조회"""
    from world_pulse import _get_pulse_db

    try:
        conn = _get_pulse_db()
        rows = conn.execute(
            "SELECT * FROM self_checks ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"[SelfCheck] 조회 실패: {e}")
        return []


def get_system_health() -> Dict:
    """시스템 전체 건강 요약 — API용"""
    from world_pulse import _collect_self_state, get_recent_pulses

    self_state = _collect_self_state()
    health_summary = get_action_health_summary()
    recent_pulses = get_recent_pulses(hours=6)

    # 전체 상태 판정
    services = self_state.get("services", {})
    all_services_ok = all(services.values()) if services else True

    # 자가점검 성공률
    if health_summary:
        avg_rate = sum(v["success_rate"] for v in health_summary.values()) / len(health_summary)
    else:
        avg_rate = 100.0

    if not all_services_ok:
        overall = "degraded"
    elif avg_rate < 80:
        overall = "warning"
    else:
        overall = "healthy"

    # 패턴 분석
    patterns = analyze_failure_patterns()

    return {
        "overall": overall,
        "services": services,
        "disk_free_gb": self_state.get("disk_free_gb"),
        "self_check_avg_success_rate": round(avg_rate, 1),
        "self_check_actions": health_summary,
        "self_check_patterns": patterns,
        "pulse_count_6h": len(recent_pulses),
        "last_pulse": recent_pulses[0]["timestamp"] if recent_pulses else None,
    }


def get_ibl_health_status() -> Dict:
    """조종실용 — self_checks 에 마지막으로 기록된 IBL 건강을 읽는다.

    검사를 *실행하지 않는다* (수십 초 걸리는 ibl_health_check.py 호출 X). 마지막 일일/수동
    점검 결과를 SQL 한 번으로 즉시 돌려준다 — 조종실이 열릴 때마다 가볍게 표시하기 위한 것.
    아직 한 번도 점검 안 됐으면 ok=None('미점검').

    항목 4 + 러너 감시 1:
      · 어휘 정합/통화 규약/파이프 흐름 = '지금 점검'·일일 점검이 갱신
      · 설명 정합(description_drift) = 주 1회 감사가 갱신 (주기가 달라 checked_at 이 뒤질 수 있음)
      · 점검 러너 자체가 실패하면(스크립트 죽음·계약 위반) 맨 앞에 빨간 항목으로 표면화 —
        옛 구조는 이때 옛 GREEN 이 말없이 유지되는 침묵 실패였다.
    stale: 마지막 점검이 STALE_HOURS(48h) 를 넘으면 True — 초록 배지를 바래게 할 근거.
    """
    from world_pulse import _get_pulse_db

    KEYS = [
        ("__static__", "ibl_consistency", "어휘 정합 — 선언·구현·도구 일치"),
        ("__ibl_health__", "currency", "통화 규약 — 실행 결과 형태"),
        ("__ibl_health__", "golden_pipes", "파이프 흐름 — 액션 조합(>>)"),
        ("__ibl_health__", "description_drift", "설명 정합 — 어휘 설명 최신성"),
    ]
    STALE_HOURS = 48
    items = []
    checked_at = None
    runner_row = None
    try:
        conn = _get_pulse_db()
        for node, action, label in KEYS:
            row = conn.execute(
                "SELECT success, error_message, timestamp FROM self_checks "
                "WHERE node=? AND action=? ORDER BY id DESC LIMIT 1",
                (node, action),
            ).fetchone()
            if row:
                items.append({
                    "key": action, "label": label, "ok": bool(row["success"]),
                    "detail": row["error_message"], "checked_at": row["timestamp"],
                })
                if not checked_at or (row["timestamp"] or "") > checked_at:
                    checked_at = row["timestamp"]
            else:
                items.append({"key": action, "label": label, "ok": None, "detail": None, "checked_at": None})
        # 점검 러너 감시 — 최신 기록이 fail 이고 위 항목들보다 새로우면 표면화
        runner_row = conn.execute(
            "SELECT success, error_message, timestamp FROM self_checks "
            "WHERE node='__ibl_health__' AND action='ibl_health_check' ORDER BY id DESC LIMIT 1",
        ).fetchone()
        conn.close()
    except Exception as e:
        logger.warning(f"[Dashboard] IBL 건강 조회 실패: {e}")

    if runner_row is not None and not bool(runner_row["success"]) \
            and (runner_row["timestamp"] or "") >= (checked_at or ""):
        items.insert(0, {
            "key": "ibl_health_check", "label": "점검 실행 — 검사기 자체", "ok": False,
            "detail": runner_row["error_message"], "checked_at": runner_row["timestamp"],
        })
        checked_at = runner_row["timestamp"]

    stale = False
    if checked_at:
        try:
            dt = datetime.fromisoformat(checked_at)
            stale = (datetime.now() - dt) > timedelta(hours=STALE_HOURS)
        except Exception:
            pass

    known = [i for i in items if i["ok"] is not None]
    return {
        "checked_at": checked_at,
        "healthy": (all(i["ok"] for i in known) if known else None),
        "stale": stale,
        "items": items,
        "action_count": _count_all_actions(),
    }


# ============ 일일 건강 체크 (단일 검사 1회 · AI 0) ============

def run_daily_health_check() -> Dict:
    """매일 1회 IBL 건강 점검 — 단일 검사(ibl_health_check.py) 1회 + RED 면 알림. AI 0.

    IBL 구조 건강이 변하는 건 *어휘를 쓸 때뿐*이고, 그건 커밋 시 `--check`(fixture 완전성
    포함)가 막는다. 이 일일 잡은 그 정적·fixture·골든 검사를 회귀 그물로 한 번 더 돌리는 것 —
    폴링 sweep 도, AI 턴도 없다(옛 배선은 매일 AI 로 assumed 액션을 routine polling 했다).

    1) ibl_health_check.py 1회 → §1A 정적 + §1B fixture 통화 + §1C 골든 (전부 AI 0)
    2) 결과를 self_checks 에 기록 (x-ray 노출)
    3) RED 있으면 알림 한 통 (notification_manager — 사람이 본다. AI 아님)
    4) 기계적 유지보수 번들(forage 정리·메모리·연속실패 알림) — IBL 건강과 무관, 항상
    """
    from world_pulse import _load_config
    if not _load_config().get("self_check", {}).get("enabled", True):
        return {"status": "disabled"}

    reds = []
    try:
        for ev in run_ibl_health_check():
            save_self_check(ev)
            if not ev.get("success"):
                reds.append(f"[{ev['node']}:{ev['action']}] {ev.get('error_message') or ''}".strip())
    except Exception as e:
        logger.warning(f"[HealthCheck] ibl_health_check 실행 실패: {e}")

    if reds:
        logger.warning(f"[HealthCheck] IBL 건강 RED {len(reds)}건: {' / '.join(reds)[:300]}")
        try:
            from notification_manager import get_notification_manager
            get_notification_manager().create(
                title="IBL 건강 경고",
                message="구조/통화/흐름 결함: " + " / ".join(reds)[:400],
                type="warning",
                source="ibl_health",
            )
        except Exception as e:
            logger.warning(f"[HealthCheck] 알림 발송 실패: {e}")
    else:
        logger.info("[HealthCheck] IBL 건강 ✅ (정적+fixture+골든 GREEN) — AI 0")

    # 일반 유지보수 (IBL 건강과 별개 — forage 정리·메모리·연속실패 알림)
    try:
        run_maintenance_bundle()
    except Exception as e:
        logger.warning(f"[HealthCheck] 유지보수 번들 실패 (무시): {e}")

    return {"status": "completed", "red": reds, "ai": False}


# ============================================================
# 통합 진단 리포트 (AI 비용 0 — 순수 SQL + Python)
# ============================================================

DIAGNOSTIC_REPORT_PATH = Path(__file__).parent.parent / "data" / "diagnostic_report.md"


def _count_all_actions() -> int:
    """ibl_nodes.yaml에서 전체 액션 수 카운트"""
    import yaml as _yaml
    nodes_path = Path(__file__).parent.parent / "data" / "ibl_nodes.yaml"
    if not nodes_path.exists():
        return 0
    try:
        with open(nodes_path, "r", encoding="utf-8") as f:
            data = _yaml.safe_load(f) or {}
        count = 0
        for section_key in ("nodes", "actions"):
            section = data.get(section_key, {})
            if isinstance(section, dict):
                for node_val in section.values():
                    if isinstance(node_val, dict):
                        acts = node_val.get("actions", node_val)
                        if isinstance(acts, dict):
                            count += len(acts)
        return count
    except Exception:
        return 0


def _calculate_action_coverage() -> Dict:
    """전체 액션 중 verified/assumed/failed 비율 계산"""
    total = _count_all_actions()
    summary = get_action_health_summary()

    verified = sum(1 for v in summary.values() if v["status"] == "verified")
    failed = sum(1 for v in summary.values() if v["status"] == "failed")
    # assumed = 전체 - DB에 기록이 있는 것
    recorded = len(summary)
    assumed = total - recorded if total > recorded else 0

    return {
        "total": total,
        "verified": verified,
        "assumed": assumed,
        "failed": failed,
        "recorded_other": recorded - verified - failed,  # DB에 있지만 verified/failed 아닌 것
    }


def _get_recent_errors(days: int = 7, limit: int = 10) -> List[Dict]:
    """최근 N일간 실패 빈도 높은 액션 top N"""
    from world_pulse import _get_pulse_db

    try:
        conn = _get_pulse_db()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT node, action, COUNT(*) as fail_count,
                   MAX(timestamp) as last_failure
            FROM action_health
            WHERE success = 0 AND source = 'usage' AND timestamp >= ?
            GROUP BY node, action
            ORDER BY fail_count DESC
            LIMIT ?
        """, (cutoff, limit)).fetchall()
        conn.close()
        return [{"action": f"[{r['node']}:{r['action']}]",
                 "fail_count": r["fail_count"],
                 "last_failure": r["last_failure"]} for r in rows]
    except Exception:
        return []


def _build_recommendations(patterns: Dict, cognitive: Dict, coverage: Dict) -> List[Dict]:
    """규칙 기반 추천 생성 (AI 없이)"""
    recs = []

    # 만성 실패 액션
    chronic = patterns.get("chronic_failures", [])
    if chronic:
        recs.append({
            "severity": "high",
            "area": "action_health",
            "message": f"만성 실패 액션 {len(chronic)}개: {', '.join(chronic[:5])}",
            "action": "해당 패키지 handler.py 점검 필요",
        })

    # 성능 저하 액션
    degrading = patterns.get("degrading", [])
    if degrading:
        names = [d["action"] if isinstance(d, dict) else str(d) for d in degrading[:3]]
        recs.append({
            "severity": "medium",
            "area": "action_health",
            "message": f"성능 저하 감지 {len(degrading)}개: {', '.join(names)}",
            "action": "API 소스 또는 네트워크 상태 확인",
        })

    # 속도 저하 액션
    slowdowns = patterns.get("slowdowns", [])
    if slowdowns:
        names = [s["action"] if isinstance(s, dict) else str(s) for s in slowdowns[:3]]
        recs.append({
            "severity": "low",
            "area": "action_health",
            "message": f"응답 속도 저하 {len(slowdowns)}개: {', '.join(names)}",
            "action": "외부 API 지연 또는 내부 병목 확인",
        })

    # 인지 품질 추세
    trends = cognitive.get("trends", {})
    if trends.get("hippocampus") == "declining":
        recs.append({
            "severity": "medium",
            "area": "cognitive",
            "message": "해마 점수 하락 추세 — 용례 사전 보강 또는 재학습 검토",
            "action": "ibl_usage_db 용례 확인, 필요시 ibl_embedding_trainer.py 실행",
        })
    if trends.get("efficiency") == "declining":
        recs.append({
            "severity": "medium",
            "area": "cognitive",
            "message": "실행 라운드 증가 추세 — 에이전트 효율 저하",
            "action": "프롬프트 또는 도구 설명 점검",
        })

    # 커버리지
    total = coverage.get("total", 0)
    assumed = coverage.get("assumed", 0)
    if total > 0 and assumed / total > 0.5:
        recs.append({
            "severity": "low",
            "area": "coverage",
            "message": f"미확인 액션 {assumed}개 ({assumed * 100 // total}%) — 절반 이상 미검증",
            "action": "건강 체크 확대 또는 수동 테스트 실행",
        })

    return recs


def generate_diagnostic_report() -> Dict:
    """통합 진단 리포트 생성 (AI 비용 0, 순수 SQL + Python)

    Returns: 시스템 상태, 액션 건강, 인지 품질, 추천 조치를 포함하는 dict
    """
    from episode_logger import get_cognitive_trends

    health = get_system_health()
    cognitive = get_cognitive_trends(days=7)
    coverage = _calculate_action_coverage()
    recent_errors = _get_recent_errors(days=7, limit=10)
    patterns = health.get("self_check_patterns", {})
    recommendations = _build_recommendations(patterns, cognitive, coverage)

    return {
        "generated_at": datetime.now().isoformat(),
        "system": {
            "overall": health.get("overall", "unknown"),
            "services": health.get("services", {}),
            "disk_free_gb": health.get("disk_free_gb"),
            "pulse_count_6h": health.get("pulse_count_6h"),
            "last_pulse": health.get("last_pulse"),
        },
        "action_health": {
            "coverage": coverage,
            "avg_success_rate": health.get("self_check_avg_success_rate"),
            "patterns": patterns,
            "recent_errors": recent_errors,
        },
        "cognitive_quality": cognitive,
        "recommendations": recommendations,
    }


def format_diagnostic_report_md(report: Dict = None) -> str:
    """진단 리포트를 마크다운 문자열로 변환"""
    if report is None:
        report = generate_diagnostic_report()

    lines = []
    gen_at = report.get("generated_at", "?")[:16]
    lines.append(f"# IndieBiz OS 진단 리포트\n생성: {gen_at}\n")

    # 시스템 상태
    sys = report.get("system", {})
    overall = sys.get("overall", "unknown")
    lines.append(f"## 시스템 상태: {overall}")
    services = sys.get("services", {})
    if services:
        svc_parts = [f"{k} {'✅' if v else '❌'}" for k, v in services.items()]
        lines.append(f"- 서비스: {' | '.join(svc_parts)}")
    disk = sys.get("disk_free_gb")
    if disk is not None:
        lines.append(f"- 디스크: {disk}GB 여유")
    pulse_6h = sys.get("pulse_count_6h")
    last_pulse = sys.get("last_pulse")
    if pulse_6h is not None:
        lines.append(f"- 최근 6시간 펄스: {pulse_6h}회 (마지막: {(last_pulse or '?')[:16]})")
    lines.append("")

    # 액션 건강
    ah = report.get("action_health", {})
    cov = ah.get("coverage", {})
    lines.append("## 액션 건강")
    lines.append(f"- 전체 {cov.get('total', '?')}개: "
                 f"verified {cov.get('verified', '?')} | "
                 f"assumed {cov.get('assumed', '?')} | "
                 f"failed {cov.get('failed', '?')}")
    avg_rate = ah.get("avg_success_rate")
    if avg_rate is not None:
        lines.append(f"- 평균 성공률: {avg_rate}%")

    patterns = ah.get("patterns", {})
    chronic = patterns.get("chronic_failures", [])
    if chronic:
        lines.append(f"- 만성 실패: {', '.join(chronic[:5])}")
    degrading = patterns.get("degrading", [])
    if degrading:
        names = [d["action"] if isinstance(d, dict) else str(d) for d in degrading[:3]]
        lines.append(f"- 성능 저하: {', '.join(names)}")
    slowdowns = patterns.get("slowdowns", [])
    if slowdowns:
        names = [s["action"] if isinstance(s, dict) else str(s) for s in slowdowns[:3]]
        lines.append(f"- 속도 저하: {', '.join(names)}")
    recovered = patterns.get("recovered", [])
    if recovered:
        lines.append(f"- 회복됨: {', '.join(recovered[:5])}")

    errors = ah.get("recent_errors", [])
    if errors:
        lines.append(f"\n### 최근 7일 실패 빈도 Top")
        for e in errors[:5]:
            lines.append(f"- {e['action']}: {e['fail_count']}회 (마지막: {(e.get('last_failure') or '?')[:16]})")
    lines.append("")

    # 인지 품질
    cq = report.get("cognitive_quality", {})
    recent = cq.get("recent", {})
    previous = cq.get("previous", {})
    trends = cq.get("trends", {})
    lines.append("## 인지 품질 (최근 7일 vs 이전 7일)")
    r_cnt = recent.get("episode_count", 0)
    p_cnt = previous.get("episode_count", 0)
    lines.append(f"- 에피소드: {p_cnt}회 → {r_cnt}회")

    def _trend_mark(t):
        if t == "improving": return "✅ improving"
        if t == "declining": return "⚠ declining"
        if t == "stable": return "stable"
        return "데이터 부족"

    r_hippo = recent.get("avg_hippocampus_score")
    p_hippo = previous.get("avg_hippocampus_score")
    if r_hippo is not None or p_hippo is not None:
        lines.append(f"- 해마 점수: {p_hippo or '?'} → {r_hippo or '?'} {_trend_mark(trends.get('hippocampus', ''))}")

    r_exec = recent.get("execute_ratio")
    p_exec = previous.get("execute_ratio")
    if r_exec is not None or p_exec is not None:
        fmt = lambda v: f"{v*100:.0f}%" if v is not None else "?"
        lines.append(f"- EXECUTE 비율: {fmt(p_exec)} → {fmt(r_exec)}")

    r_rounds = recent.get("avg_execution_rounds")
    p_rounds = previous.get("avg_execution_rounds")
    if r_rounds is not None or p_rounds is not None:
        lines.append(f"- 평균 실행 라운드: {p_rounds or '?'} → {r_rounds or '?'} {_trend_mark(trends.get('efficiency', ''))}")

    r_ms = recent.get("avg_total_ms")
    p_ms = previous.get("avg_total_ms")
    if r_ms is not None or p_ms is not None:
        fmt_ms = lambda v: f"{v/1000:.1f}s" if v is not None else "?"
        lines.append(f"- 평균 소요시간: {fmt_ms(p_ms)} → {fmt_ms(r_ms)} {_trend_mark(trends.get('speed', ''))}")

    r_eval = recent.get("evaluation_achieved_ratio")
    p_eval = previous.get("evaluation_achieved_ratio")
    if r_eval is not None or p_eval is not None:
        fmt = lambda v: f"{v*100:.0f}%" if v is not None else "?"
        lines.append(f"- 평가 달성률: {fmt(p_eval)} → {fmt(r_eval)}")
    lines.append("")

    # 추천 조치
    recs = report.get("recommendations", [])
    if recs:
        lines.append("## 추천 조치")
        for i, r in enumerate(recs, 1):
            sev = r.get("severity", "").upper()
            lines.append(f"{i}. [{sev}] {r['message']}")
            if r.get("action"):
                lines.append(f"   → {r['action']}")
    else:
        lines.append("## 추천 조치\n특이사항 없음 ✅")
    lines.append("")

    return "\n".join(lines)


def save_diagnostic_report():
    """진단 리포트를 data/diagnostic_report.md로 저장 (Pulse 주기에 편승)"""
    try:
        report = generate_diagnostic_report()
        md = format_diagnostic_report_md(report)
        DIAGNOSTIC_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        DIAGNOSTIC_REPORT_PATH.write_text(md, encoding="utf-8")
        logger.info("[DiagnosticReport] 진단 리포트 갱신 완료")
    except Exception as e:
        logger.warning(f"[DiagnosticReport] 리포트 저장 실패: {e}")
