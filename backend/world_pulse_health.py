"""
world_pulse_health.py - World Pulse 건강 점검 및 가이드 생성 모듈
IndieBiz OS Core

world_pulse.py에서 분리된 모듈로, 시스템 건강 점검(Self-Check)과
가이드 파일 생성 기능을 담당합니다.

기능:
1. generate_guide: world_pulse.md 가이드 파일 생성/갱신
2. Self-Check: 주기적 IBL 액션 자가 점검 (면역 순찰)
3. 시스템 건강 요약 API

사용:
    from world_pulse_health import generate_guide, run_self_check, get_system_health
"""

import logging
import random
import time as _time
from datetime import datetime, timedelta
from typing import Dict, List

logger = logging.getLogger(__name__)


# ============================================================
# 가이드 파일 생성
# ============================================================

def generate_guide():
    """world_pulse.md 가이드 파일 생성/갱신

    오늘의 스냅샷 + 최근 추이를 마크다운으로 저장합니다.
    에이전트가 대화 시작 시 이 파일을 읽으면 세계 맥락을 알 수 있습니다.
    """
    from world_pulse import (
        get_today_pulse, get_pulse_trend, PULSE_GUIDE_PATH,
        _collect_user_profile, _collect_system_status, _collect_self_state,
        _load_config,
    )

    today = get_today_pulse()
    if not today:
        return

    lines = [
        "# World Pulse — 오늘의 세계와 나 (자동 주입)",
        f"수집 시각: {today.get('collected_at', '?')[:16]}",
        "",
        "> 이 정보는 대화 시작 시 시스템 프롬프트에 자동 포함됩니다.",
        "> 사용자가 '요즘 세상은 어때', '오늘 경제 상황' 등을 물으면",
        "> 아래 데이터를 바로 활용하여 답하세요.",
        "> [sense:world_refresh]나 read_guide 호출은 불필요합니다.",
        "",
    ]

    # ── 사용자 프로필 ──
    profile = _collect_user_profile()
    if profile:
        lines.append("## 사용자")
        label_map = {"name": "이름", "occupation": "직업", "interests": "관심사", "memo": "메모"}
        for key, val in profile.items():
            label = label_map.get(key, key)
            lines.append(f"- {label}: {val}")
        # location도 포함
        config = _load_config()
        loc = config.get("location", "")
        if loc:
            lines.append(f"- 위치: {loc}")
        lines.append("")

    # ── 시스템 상태 ──
    sys_status = _collect_system_status()
    if sys_status:
        lines.append("## 시스템 상태")
        if "projects" in sys_status:
            agents_str = f", 에이전트 {sys_status['agents']}개" if sys_status.get("agents") else ""
            lines.append(f"- 프로젝트 {sys_status['projects']}개{agents_str} 활성")
        if sys_status.get("recent_topics"):
            topics = " / ".join(sys_status["recent_topics"])
            lines.append(f"- 최근 대화: {topics}")
        if sys_status.get("today_events"):
            events = ", ".join(sys_status["today_events"])
            lines.append(f"- 오늘 예정: {events}")
        else:
            lines.append("- 오늘 예정: 없음")
        if "disk_free_gb" in sys_status:
            lines.append(f"- 저장소 여유: {sys_status['disk_free_gb']}GB")
        lines.append("")

    # ── 시스템 건강 (World Pulse) ──
    try:
        self_state = _collect_self_state()
        services = self_state.get("services", {})
        if services:
            lines.append("## 시스템 건강")
            for svc, alive in services.items():
                mark = "정상" if alive else "중단"
                lines.append(f"- {svc}: {mark}")
            # 자가점검 요약
            sc_summary = self_state.get("self_check_summary", {})
            if sc_summary:
                ok_count = sum(1 for v in sc_summary.values() if v.get("success_rate", 0) >= 80)
                lines.append(f"- 자가점검: {ok_count}/{len(sc_summary)}개 액션 정상")
                failing = [k for k, v in sc_summary.items() if v.get("success_rate", 100) < 80]
                if failing:
                    lines.append(f"- 주의 필요: {', '.join(failing)}")
            # Digital Proprioception (body schema)
            proprio = self_state.get("proprioception", {})
            if proprio:
                lines.append("")
                lines.append("## Digital Proprioception")
                if "memory_mb" in proprio:
                    lines.append(f"- 메모리: {proprio['memory_mb']}MB")
                if "cpu_percent" in proprio:
                    lines.append(f"- CPU: {proprio['cpu_percent']}%")
                if "threads" in proprio:
                    lines.append(f"- 스레드: {proprio['threads']}개")
                if "active_tasks" in proprio or "pending_tasks" in proprio:
                    active = proprio.get("active_tasks", 0)
                    pending = proprio.get("pending_tasks", 0)
                    lines.append(f"- 태스크: 실행 {active}개 / 대기 {pending}개")
                if "ibl_executions_today" in proprio:
                    lines.append(f"- 오늘 IBL 실행: {proprio['ibl_executions_today']}회")
                lines.append("")
    except Exception:
        pass

    # 경제
    economy = today.get("economy", {})
    if economy:
        lines.append("## 경제")
        label_map = {
            "kospi": "코스피", "kosdaq": "코스닥",
            "sp500": "S&P500", "nasdaq": "나스닥",
            "usd_krw": "원/달러", "gold": "금", "wti": "유가"
        }
        for key, data in economy.items():
            if isinstance(data, dict):
                price = data.get("price", "?")
                pct = data.get("change_pct")
                pct_str = f" ({pct:+.1f}%)" if isinstance(pct, (int, float)) else ""
                label = label_map.get(key, key)
                # 실제 데이터 날짜 표시 (수집일과 다를 수 있음)
                data_date = data.get("data_date", "")
                date_str = f" [{data_date}]" if data_date else ""
                lines.append(f"- {label}: {price}{pct_str}{date_str}")
        lines.append("")

    # 날씨
    weather = today.get("weather", "")
    if weather:
        lines.append(f"## 날씨\n{weather}")
        lines.append("")

    # 주요 뉴스, 기술 동향, 최근 추이 — 제거됨
    # 뉴스는 제목만 있고 실질 정보 없음, 기술 동향은 사이트명만, 추이는 경제 숫자 반복.
    # 필요 시 [sense:search_news]로 직접 조회.

    # 파일 저장
    PULSE_GUIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PULSE_GUIDE_PATH.write_text("\n".join(lines), encoding="utf-8")
    logger.info("[WorldPulse] 가이드 파일 갱신 완료")


# ============================================================
# Self-Check — 주기적 IBL 액션 자가 점검 (면역 순찰)
# ============================================================

def _get_safe_actions() -> List[Dict]:
    """부작용 없는 안전한 테스트용 액션 목록"""
    from world_pulse import _load_config

    config = _load_config()
    sc_config = config.get("self_check", {})
    safe_nodes = sc_config.get("safe_nodes", ["sense"])
    excluded = set(sc_config.get("excluded_actions", ["world_refresh"]))

    actions = []
    try:
        from ibl_engine import list_actions
        for node in safe_nodes:
            for action_info in list_actions(node):
                name = action_info.get("action", "")
                if name and name not in excluded:
                    actions.append({"node": node, "action": name, **action_info})
    except Exception as e:
        logger.warning(f"[SelfCheck] 액션 목록 조회 실패: {e}")

    return actions


def _evaluate_result(result, elapsed_ms: int) -> Dict:
    """LLM 없이 결과 평가"""
    is_error = isinstance(result, dict) and "error" in result
    is_empty = (result is None or result == "" or result == {} or result == [])

    if is_error:
        return {
            "success": False,
            "response_ms": elapsed_ms,
            "data_quality": "error",
            "error_message": str(result.get("error", ""))[:200],
        }
    elif is_empty:
        return {
            "success": True,
            "response_ms": elapsed_ms,
            "data_quality": "empty",
            "error_message": None,
        }
    else:
        return {
            "success": True,
            "response_ms": elapsed_ms,
            "data_quality": "ok",
            "error_message": None,
        }


def run_self_check() -> Dict:
    """랜덤 IBL 액션 자가 점검 (면역 순찰)"""
    from world_pulse import _load_config

    config = _load_config()
    sc_config = config.get("self_check", {})
    if not sc_config.get("enabled", True):
        return {"status": "disabled"}

    actions_per_check = sc_config.get("actions_per_check", 2)
    failure_threshold = sc_config.get("failure_alert_threshold", 3)

    safe_actions = _get_safe_actions()
    if not safe_actions:
        return {"status": "no_safe_actions"}

    # 랜덤 선택
    selected = random.sample(safe_actions, min(actions_per_check, len(safe_actions)))
    results = []

    # 액션별 테스트 파라미터 로드
    test_params_map = sc_config.get("test_params", {})

    for action_info in selected:
        node = action_info["node"]
        action = action_info["action"]

        # 설정에 테스트 파라미터가 있으면 사용, 없으면 빈 dict
        params = dict(test_params_map.get(action, {}))

        logger.info(f"[SelfCheck] 점검 중: [{node}:{action}]" + (f" (params: {params})" if params else ""))

        start = _time.time()
        try:
            from ibl_engine import execute_ibl
            result = execute_ibl(
                {"_node": node, "action": action, "params": params},
                ".",
                agent_id="__self_check__"
            )
        except Exception as e:
            result = {"error": str(e)}

        elapsed_ms = int((_time.time() - start) * 1000)
        evaluation = _evaluate_result(result, elapsed_ms)
        evaluation["node"] = node
        evaluation["action"] = action

        # DB 저장
        save_self_check(evaluation)
        results.append(evaluation)

        logger.info(
            f"[SelfCheck] [{node}:{action}] "
            f"{'OK' if evaluation['success'] else 'FAIL'} "
            f"({elapsed_ms}ms, {evaluation['data_quality']})"
        )

    # 연속 실패 알림 체크
    _check_failure_alerts(failure_threshold)

    return {
        "status": "completed",
        "checked": len(results),
        "results": results,
    }


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


def get_action_health_summary() -> Dict:
    """액션별 건강 상태 요약"""
    from world_pulse import _get_pulse_db

    try:
        conn = _get_pulse_db()
        rows = conn.execute("""
            SELECT node, action,
                   COUNT(*) as total,
                   SUM(success) as successes,
                   AVG(response_ms) as avg_ms
            FROM self_checks
            WHERE timestamp >= ?
            GROUP BY node, action
        """, ((datetime.now() - timedelta(days=7)).isoformat(),)).fetchall()
        conn.close()

        summary = {}
        for row in rows:
            key = f"{row['node']}:{row['action']}"
            total = row["total"]
            successes = row["successes"] or 0
            summary[key] = {
                "total": total,
                "success_rate": round(successes / total * 100, 1) if total > 0 else 0,
                "avg_response_ms": round(row["avg_ms"]) if row["avg_ms"] else None,
            }
        return summary
    except Exception as e:
        logger.debug(f"[SelfCheck] 요약 조회 실패: {e}")
        return {}


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

    return {
        "overall": overall,
        "services": services,
        "disk_free_gb": self_state.get("disk_free_gb"),
        "self_check_avg_success_rate": round(avg_rate, 1),
        "self_check_actions": health_summary,
        "pulse_count_6h": len(recent_pulses),
        "last_pulse": recent_pulses[0]["timestamp"] if recent_pulses else None,
    }
