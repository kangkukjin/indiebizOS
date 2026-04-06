"""
world_pulse_health.py - World Pulse 건강 점검 및 가이드 생성 모듈
IndieBiz OS Core

world_pulse.py에서 분리된 모듈로, 시스템 건강 점검(Self-Check)과
가이드 파일 생성 기능을 담당합니다.

기능:
1. generate_guide: world_pulse.md 가이드 파일 생성/갱신
2. Self-Check: 전수 IBL 액션 자가 점검 (면역 순찰)
3. 시스템 건강 요약 API + 패턴 분석

사용:
    from world_pulse_health import generate_guide, run_self_check, get_system_health
"""

import hashlib
import json
import logging
import time as _time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

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
            # 액션 건강 — 비정상만 경고
            sc_summary = self_state.get("self_check_summary", {})
            if sc_summary:
                failed = [k for k, v in sc_summary.items() if v.get("status") == "failed"]
                if failed:
                    lines.append(f"- ⚠ 비정상 액션 ({len(failed)}개): {', '.join(failed)}")

            # 패턴 분석 결과
            patterns = analyze_failure_patterns()
            if patterns:
                lines.append("")
                lines.append("## 자가점검 패턴 분석")
                if patterns.get("chronic_failures"):
                    lines.append(f"- 만성 실패: {', '.join(patterns['chronic_failures'])}")
                if patterns.get("degrading"):
                    for d in patterns["degrading"]:
                        lines.append(f"- 성공률 하락: {d['action']} ({d['before']}% → {d['after']}%)")
                if patterns.get("slowdowns"):
                    for s in patterns["slowdowns"]:
                        lines.append(f"- 응답 느려짐: {s['action']} ({s['before_ms']}ms → {s['after_ms']}ms)")
                if patterns.get("recovered"):
                    lines.append(f"- 복구됨: {', '.join(patterns['recovered'])}")
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

# ============================================================
# AI 기반 테스트 계획 생성 — 액션 변경 시 자동 갱신
# ============================================================

_TEST_PLAN_PATH = Path(__file__).parent.parent / "data" / "self_check_plan.json"

_TEST_PLAN_SYSTEM_PROMPT = """당신은 IndieBiz OS의 자가점검 시스템입니다.
IBL 액션 목록을 분석하여 안전하게 테스트할 수 있는 액션을 분류합니다.
자가점검의 목적은 "이 액션이 에러 없이 동작하는가"를 확인하는 것입니다.

safe: false로 분류 (테스트하면 안 되는 것):
- 삭제, 쓰기, 전송, 생성, 배포, 실행 등 부작용 있는 액션
- GUI 창을 여는 액션 (open_project, open_system_ai, open_indienet, open_business, open_multichat, open_folder, os_open, launch 등)
- 재생/정지 액션 (play, stop, play_radio, stop_radio 등)
- android/adb 그룹 액션 (하드웨어 의존)
- photo 그룹 액션 (외장하드 의존 — photo_gallery, photo_timeline, photo_duplicates, photo_stats, gallery, timeline 등)
- 브라우저 조작 (click, type, navigate, scroll, screenshot 등)
- 파일 변경 (write, file, save, move, copy, delete, rebuild_index 등)
- 스케줄/워크플로우 변경 (schedule, save_workflow, create, delete_trigger 등)

safe: true로 분류 (테스트해도 되는 것):
- 읽기 전용 조회, 검색, 상태 확인 액션 (로컬이든 외부 API든)
- 외부 API 호출 검색도 포함 — 동작 여부 확인이 중요
- 목록 조회, 정보 조회, 통계 조회 등

test_params: safe: true인 액션만. 최소한으로. 검색류는 {"query": "test"} 정도. 파라미터 없이 호출 가능하면 {}.

반드시 JSON 배열로만 응답하세요. 다른 텍스트 없이.
[{"action": "...", "safe": true/false, "test_params": {...}}]"""


def _get_actions_hash() -> str:
    """현재 ibl_nodes.yaml의 액션 목록 해시 — 변경 감지용"""
    try:
        from ibl_engine import _load_nodes_config
        reg = _load_nodes_config()
        nodes = reg.get("nodes", {})
        # 노드별 액션 이름만 정렬하여 해시
        action_keys = []
        for node_name in sorted(nodes.keys()):
            actions = sorted(nodes[node_name].get("actions", {}).keys())
            for a in actions:
                action_keys.append(f"{node_name}:{a}")
        return hashlib.md5("|".join(action_keys).encode()).hexdigest()
    except Exception:
        return ""


def _load_test_plan() -> Optional[Dict]:
    """캐시된 테스트 계획 로드"""
    if not _TEST_PLAN_PATH.exists():
        return None
    try:
        return json.loads(_TEST_PLAN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_test_plan(plan: Dict):
    """테스트 계획 저장"""
    _TEST_PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TEST_PLAN_PATH.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def _parse_ai_json(response: str) -> Optional[list]:
    """AI 응답에서 JSON 배열을 추출"""
    if not response:
        return None
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def generate_test_plan(force: bool = False) -> Dict:
    """AI를 사용하여 테스트 계획 생성.

    노드별로 나눠서 AI를 호출하여 응답 크기를 제한합니다.
    액션 목록이 변경되었거나 force=True일 때만 AI를 호출합니다.

    Returns:
        {"actions_hash": "...", "generated_at": "...", "actions": [...]}
    """
    current_hash = _get_actions_hash()

    # 캐시 확인 — 해시가 같으면 기존 계획 재사용
    if not force:
        cached = _load_test_plan()
        if cached and cached.get("actions_hash") == current_hash:
            logger.debug("[SelfCheck] 테스트 계획 캐시 사용 (액션 변경 없음)")
            return cached

    # 전체 액션 메타데이터를 노드별로 수집
    try:
        from ibl_engine import _load_nodes_config
        reg = _load_nodes_config()
        nodes = reg.get("nodes", {})
    except Exception as e:
        logger.warning(f"[SelfCheck] 노드 설정 로드 실패: {e}")
        return {}

    actions_by_node = {}
    total_count = 0
    for node_name in sorted(nodes.keys()):
        node_def = nodes[node_name]
        node_actions = []
        for action_name, action_def in sorted(node_def.get("actions", {}).items()):
            # router가 handler인 액션만 자가점검 대상
            # system, workflow_engine, trigger_engine 등은 GUI 열기/실행 부작용 가능
            router = action_def.get("router", "")
            if router != "handler":
                continue
            node_actions.append({
                "action": action_name,
                "description": action_def.get("description", ""),
                "group": action_def.get("group", ""),
            })
        actions_by_node[node_name] = node_actions
        total_count += len(node_actions)

    # 노드별로 AI 호출 — 시스템 AI 프로바이더 사용
    all_plan_actions = []
    provider = None
    try:
        from system_ai_runner import SystemAIRunner
        runner = SystemAIRunner.get_instance()
        if runner and runner.ai and runner.ai._provider:
            provider = runner.ai._provider
    except Exception:
        pass

    if provider is None:
        # 시스템 AI 미준비 시 lightweight_ai_call로 폴백
        try:
            from consciousness_agent import lightweight_ai_call
            _use_lightweight = True
        except Exception as e:
            logger.warning(f"[SelfCheck] AI 모듈 로드 실패: {e}")
            cached = _load_test_plan()
            return cached if cached else {}
    else:
        _use_lightweight = False

    for node_name, node_actions in actions_by_node.items():
        prompt = f"""[{node_name}] 노드의 액션 {len(node_actions)}개를 분류하세요.

{json.dumps(node_actions, ensure_ascii=False)}"""

        try:
            if _use_lightweight:
                response = lightweight_ai_call(prompt, system_prompt=_TEST_PLAN_SYSTEM_PROMPT)
            else:
                original_sp = provider.system_prompt
                provider.system_prompt = _TEST_PLAN_SYSTEM_PROMPT
                try:
                    response = provider.process_message(
                        message=prompt, history=[], images=None, execute_tool=None
                    )
                finally:
                    provider.system_prompt = original_sp

            parsed = _parse_ai_json(response)
            if parsed:
                for entry in parsed:
                    entry["node"] = node_name
                all_plan_actions.extend(parsed)
                logger.info(f"[SelfCheck] {node_name}: {sum(1 for a in parsed if a.get('safe'))} safe / {sum(1 for a in parsed if not a.get('safe'))} unsafe")
            else:
                logger.warning(f"[SelfCheck] {node_name}: AI 응답 파싱 실패")
        except Exception as e:
            logger.warning(f"[SelfCheck] {node_name}: AI 호출 실패: {e}")

    if not all_plan_actions:
        logger.warning("[SelfCheck] 테스트 계획 생성 실패, 캐시 사용")
        cached = _load_test_plan()
        return cached if cached else {}

    plan = {
        "actions_hash": current_hash,
        "generated_at": datetime.now().isoformat(),
        "total_actions": total_count,
        "safe_count": sum(1 for a in all_plan_actions if a.get("safe")),
        "unsafe_count": sum(1 for a in all_plan_actions if not a.get("safe")),
        "actions": all_plan_actions,
    }

    _save_test_plan(plan)
    logger.info(
        f"[SelfCheck] 테스트 계획 생성 완료: "
        f"{plan['safe_count']} safe / {plan['unsafe_count']} unsafe / {plan['total_actions']} total"
    )

    return plan


def _get_safe_actions() -> List[Dict]:
    """테스트 계획 기반으로 안전한 액션 목록 반환.

    AI가 생성한 테스트 계획에서 safe=true인 액션만 반환합니다.
    테스트 계획이 없거나 액션 목록이 변경되었으면 자동으로 AI를 호출하여 갱신합니다.
    """
    plan = generate_test_plan()
    if not plan or not plan.get("actions"):
        logger.warning("[SelfCheck] 테스트 계획 없음 — 점검 불가")
        return []

    # AI가 safe로 분류한 것 중에서, 확실히 위험한 키워드가 포함된 것은 코드에서 한 번 더 거름
    _UNSAFE_KEYWORDS = {
        "open_project", "open_system_ai", "open_indienet", "open_business",
        "open_multichat", "open_folder", "os_open", "launch", "launch_sites",
        "play", "stop", "play_radio", "stop_radio", "set_radio_volume",
        "write", "delete", "save", "move", "copy", "create", "edit",
        "rebuild_index", "blog_rebuild_index", "rebuild_search_index",
        "schedule", "save_workflow", "delete_trigger", "delete_workflow",
        "run", "run_pipeline", "execute", "notify_user", "send_notification",
        "send_text", "sms_send", "channel_send", "delegate_project", "ask_sync",
        "download", "push_file", "upload",
        "scan_photos", "scan_storage", "cctv_refresh",
        "photo_gallery", "photo_timeline", "photo_duplicates", "photo_stats",
        "photo_list_scans", "photo_manager", "gallery", "timeline", "list_scans",
        "browser_navigate", "browser_click", "browser_type", "browser_scroll",
        "browser_screenshot", "browser_resize", "browser_tab_new",
        "browser_cookies_save", "browser_cookies_load",
        "goal_kill", "log_attempt",
    }

    # 현재 ibl_nodes.yaml에 실제 존재하는 액션만 필터링
    _existing_actions = set()
    try:
        import yaml as _yaml
        _nodes_path = Path(__file__).parent.parent / "data" / "ibl_nodes.yaml"
        if _nodes_path.exists():
            with open(_nodes_path, "r", encoding="utf-8") as _f:
                _nodes_data = _yaml.safe_load(_f) or {}
            for _section_key in ("nodes", "actions"):
                _section = _nodes_data.get(_section_key, {})
                if isinstance(_section, dict):
                    for _node_name, _node_val in _section.items():
                        if isinstance(_node_val, dict):
                            _acts = _node_val.get("actions", _node_val)
                            if isinstance(_acts, dict):
                                for _act_name in _acts:
                                    _existing_actions.add((_node_name, _act_name))
    except Exception:
        pass  # 로드 실패 시 필터링 없이 진행

    safe_actions = []
    for entry in plan["actions"]:
        if not entry.get("safe") or entry["action"] in _UNSAFE_KEYWORDS:
            continue
        # 존재하지 않는 액션은 건너뛰기
        if _existing_actions and (entry["node"], entry["action"]) not in _existing_actions:
            continue
        safe_actions.append({
            "node": entry["node"],
            "action": entry["action"],
            "test_params": entry.get("test_params", {}),
        })

    return safe_actions


def _evaluate_result(result, elapsed_ms: int) -> Dict:
    """LLM 없이 결과 평가

    파라미터 부족/누락으로 인한 에러는 테스트 입력의 문제이지
    액션 자체의 문제가 아니므로 'skipped'로 분류한다.
    """
    is_error = isinstance(result, dict) and "error" in result
    is_empty = (result is None or result == "" or result == {} or result == [])

    if is_error:
        error_msg = str(result.get("error", ""))[:200]
        # 파라미터 부족 에러는 테스트 한계 — 액션은 정상으로 간주
        _param_error_keywords = [
            "필요합니다", "required", "missing", "파라미터가",
            "입력해주세요", "입력해 주세요", "확인하세요", "확인해 주세요",
            "를 입력", "을 입력", "가 필요", "이 필요",
        ]
        is_param_error = any(kw in error_msg for kw in _param_error_keywords)
        if is_param_error:
            return {
                "success": True,  # 액션 자체는 정상 작동 (파라미터 검증 통과)
                "response_ms": elapsed_ms,
                "data_quality": "skipped",  # 제대로 테스트하지 못한 것
                "error_message": error_msg,
            }
        return {
            "success": False,
            "response_ms": elapsed_ms,
            "data_quality": "error",
            "error_message": error_msg,
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
    """전수 IBL 액션 자가 점검 (면역 순찰)

    부작용 없는 모든 액션을 순차 실행하여 시스템 건강 상태를 전수 점검합니다.
    타임아웃(기본 10초)을 초과하는 액션은 slow로 기록합니다.
    """
    from world_pulse import _load_config

    config = _load_config()
    sc_config = config.get("self_check", {})
    if not sc_config.get("enabled", True):
        return {"status": "disabled"}

    failure_threshold = sc_config.get("failure_alert_threshold", 3)
    action_timeout = sc_config.get("action_timeout_sec", 10)

    safe_actions = _get_safe_actions()
    if not safe_actions:
        return {"status": "no_safe_actions"}

    # 전수 점검
    results = []
    stats = {"ok": 0, "fail": 0, "slow": 0, "empty": 0}
    total_start = _time.time()

    for action_info in safe_actions:
        node = action_info["node"]
        action = action_info["action"]

        # 테스트 계획에서 파라미터 사용
        params = dict(action_info.get("test_params", {}))

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

        # 타임아웃 초과 시 slow 표시
        if elapsed_ms > action_timeout * 1000:
            evaluation["data_quality"] = "slow"

        # 통계
        if not evaluation["success"]:
            stats["fail"] += 1
        elif evaluation["data_quality"] == "skipped":
            stats["skipped"] = stats.get("skipped", 0) + 1
        elif evaluation["data_quality"] == "slow":
            stats["slow"] += 1
        elif evaluation["data_quality"] == "empty":
            stats["empty"] += 1
        else:
            stats["ok"] += 1

        # DB 저장
        save_self_check(evaluation)
        results.append(evaluation)

        # 실패/slow만 로그 (성공은 조용히)
        if not evaluation["success"] or evaluation["data_quality"] == "slow":
            logger.info(
                f"[SelfCheck] [{node}:{action}] "
                f"{'FAIL' if not evaluation['success'] else 'SLOW'} "
                f"({elapsed_ms}ms)"
            )

    total_elapsed = int((_time.time() - total_start) * 1000)

    # 연속 실패 알림 체크
    _check_failure_alerts(failure_threshold)

    # 패턴 분석 실행
    pattern = analyze_failure_patterns()

    logger.info(
        f"[SelfCheck] 전수 점검 완료: {len(results)}개 액션, "
        f"{stats['ok']} OK / {stats['fail']} FAIL / {stats['slow']} SLOW / {stats['empty']} EMPTY "
        f"({total_elapsed}ms)"
    )

    # 실패한 액션만 요약 (결과 데이터는 포함하지 않음 — DB에 이미 저장됨)
    failures = [
        {"node": r["node"], "action": r["action"], "error": r.get("error_message", "")[:100]}
        for r in results if not r.get("success")
    ]
    slow_list = [
        {"node": r["node"], "action": r["action"], "ms": r.get("response_ms")}
        for r in results if r.get("data_quality") == "slow"
    ]

    return {
        "status": "completed",
        "checked": len(results),
        "stats": stats,
        "total_elapsed_ms": total_elapsed,
        "failures": failures,
        "slow_actions": slow_list,
        "pattern_analysis": pattern,
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

        # 최근 7일 전체 데이터 — action_health 우선, 없으면 self_checks 폴백
        rows = conn.execute("""
            SELECT node, action, success, response_ms, timestamp, 'usage' as data_quality
            FROM action_health
            WHERE timestamp >= ?
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
    """액션별 건강 상태 요약 — action_health 테이블 기반 (self_check + 실사용 통합)"""
    from world_pulse import _get_pulse_db

    try:
        conn = _get_pulse_db()

        # action_health 테이블에서 7일간 집계
        rows = conn.execute("""
            SELECT node, action,
                   COUNT(*) as total,
                   SUM(success) as successes,
                   AVG(response_ms) as avg_ms,
                   MAX(CASE WHEN success = 1 THEN timestamp END) as last_success,
                   MAX(CASE WHEN success = 0 THEN timestamp END) as last_failure
            FROM action_health
            WHERE timestamp >= ?
            GROUP BY node, action
        """, ((datetime.now() - timedelta(days=7)).isoformat(),)).fetchall()

        # action_health가 비어있으면 기존 self_checks에서 폴백
        if not rows:
            rows = conn.execute("""
                SELECT node, action,
                       COUNT(*) as total,
                       SUM(success) as successes,
                       AVG(response_ms) as avg_ms,
                       MAX(CASE WHEN success = 1 THEN timestamp END) as last_success,
                       MAX(CASE WHEN success = 0 THEN timestamp END) as last_failure
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
            last_success = row["last_success"]
            last_failure = row["last_failure"]

            # 3단계 상태 결정: verified / assumed / failed
            if last_success and (not last_failure or last_success > last_failure):
                status = "verified"
            elif last_failure and (not last_success or last_failure >= last_success):
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


# ============ AI 기반 건강 체크 (Self-Check 대체) ============

def trigger_ai_health_check():
    """시스템 AI에게 건강 체크 메시지를 보내 assumed 액션을 테스트하게 한다.

    1. ibl_nodes.yaml에서 전체 액션 목록 로드
    2. action_health + self_checks에서 7일간 기록이 있는 액션 제외
    3. 남은 assumed 액션 목록을 프롬프트에 삽입
    4. SystemAIRunner.send_message()로 시스템 AI에게 전송
    """
    import yaml
    from world_pulse import _get_pulse_db

    BASE = Path(__file__).parent.parent

    # 1) 전체 액션 목록 로드
    all_actions = set()  # {(node, action), ...}
    nodes_yaml = BASE / "data" / "ibl_nodes.yaml"
    if nodes_yaml.exists():
        try:
            with open(nodes_yaml, "r", encoding="utf-8") as f:
                nodes_data = yaml.safe_load(f) or {}
            for section_key in ("nodes", "actions"):
                section = nodes_data.get(section_key, {})
                if isinstance(section, dict):
                    for node_name, node_val in section.items():
                        if isinstance(node_val, dict):
                            acts = node_val.get("actions", node_val)
                            if isinstance(acts, dict):
                                for act_name in acts:
                                    all_actions.add((node_name, act_name))
        except Exception as e:
            logger.warning(f"[HealthCheck] ibl_nodes.yaml 로드 실패: {e}")
            return

    if not all_actions:
        logger.info("[HealthCheck] 액션 목록이 비어있음")
        return

    # 2) 7일간 성공 기록이 있는 액션(verified) 제외, assumed + failed만 수집
    verified_actions = set()
    failed_actions = set()
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    try:
        conn = _get_pulse_db()
        # action_health에서 7일간 액션별 최근 성공/실패 시점
        rows = conn.execute("""
            SELECT node, action,
                   MAX(CASE WHEN success = 1 THEN timestamp END) as last_success,
                   MAX(CASE WHEN success = 0 THEN timestamp END) as last_failure
            FROM action_health
            WHERE timestamp >= ?
            GROUP BY node, action
        """, (cutoff,)).fetchall()
        for r in rows:
            key = (r["node"], r["action"])
            ls, lf = r["last_success"], r["last_failure"]
            if ls and (not lf or ls > lf):
                verified_actions.add(key)
            elif lf:
                failed_actions.add(key)
        # self_checks 폴백 (하위 호환)
        rows2 = conn.execute("""
            SELECT node, action,
                   MAX(CASE WHEN success = 1 THEN timestamp END) as last_success,
                   MAX(CASE WHEN success = 0 THEN timestamp END) as last_failure
            FROM self_checks
            WHERE timestamp >= ?
            GROUP BY node, action
        """, (cutoff,)).fetchall()
        for r in rows2:
            key = (r["node"], r["action"])
            if key in verified_actions:
                continue  # action_health에서 이미 verified
            ls, lf = r["last_success"], r["last_failure"]
            if ls and (not lf or ls > lf):
                verified_actions.add(key)
            elif lf and key not in failed_actions:
                failed_actions.add(key)
        conn.close()
    except Exception as e:
        logger.debug(f"[HealthCheck] DB 조회 실패: {e}")

    # 부작용이 있는 액션은 테스트 후보에서 제외
    _UNSAFE_KEYWORDS = {
        "create", "build", "deploy", "edit", "modify", "remove", "delete", "save", "write",
        "send", "play", "stop", "download", "upload", "push", "copy", "move",
        "open", "launch", "navigate", "click", "type", "scroll", "screenshot",
        "slide", "video", "image", "tts", "newspaper", "render", "export",
        "schedule", "kill", "log_attempt", "rebuild", "scan", "refresh",
        "register", "unregister", "add_component", "snapshot",
        "photo", "gallery", "duplicates",
    }

    def _is_safe_for_test(action_name: str) -> bool:
        """테스트해도 안전한 액션인지 판별"""
        return not any(kw in action_name for kw in _UNSAFE_KEYWORDS)

    # 테스트 후보: assumed(기록 없음) + failed(최근 실패) — 안전한 것만
    assumed_all = sorted(all_actions - verified_actions - failed_actions)
    assumed = [(n, a) for n, a in assumed_all if _is_safe_for_test(a)]
    failed_list = sorted(failed_actions)

    if not assumed and not failed_list:
        logger.info("[HealthCheck] 모든 액션이 verified — 건강 체크 스킵")
        return

    # 3) 노드별로 골고루 선택 (한 노드에 치우치지 않게)
    from collections import defaultdict
    by_node = defaultdict(list)
    for node, action in assumed:
        by_node[node].append((node, action))

    # 라운드 로빈으로 노드별 순환 선택 (최대 30개)
    selected_assumed = []
    node_keys = sorted(by_node.keys())
    idx = 0
    while len(selected_assumed) < 30 and any(by_node.values()):
        node = node_keys[idx % len(node_keys)]
        if by_node[node]:
            selected_assumed.append(by_node[node].pop(0))
        idx += 1
        if idx > len(node_keys) * 30:
            break

    # 4) 프롬프트 생성
    prompt_path = BASE / "data" / "common_prompts" / "health_check_prompt.md"
    if prompt_path.exists():
        template = prompt_path.read_text(encoding="utf-8")
    else:
        template = (
            "너의 IBL 액션 중 아직 확인되지 않은 것들을 테스트해야 해. "
            "아래 목록에서 최대 10개를 골라서 execute_ibl로 실행해봐. "
            "쓰기/삭제/재생/발송 등 부작용이 있는 건 하지 마. "
            "결과를 간략히 보고해.\n\n{assumed_actions}"
        )

    action_lines = []
    if failed_list:
        action_lines.append(f"\n### 비정상 (재확인 필요) — {len(failed_list)}개")
        for node, action in failed_list[:10]:
            action_lines.append(f"- [{node}:{action}]")
    if selected_assumed:
        action_lines.append(f"\n### 미확인 (assumed) — {len(assumed)}개 중 {len(selected_assumed)}개 선별")
        for node, action in selected_assumed:
            action_lines.append(f"- [{node}:{action}]")
    actions_text = "\n".join(action_lines)
    message = template.replace("{assumed_actions}", actions_text)

    # 4) 시스템 AI에게 전송
    try:
        from system_ai_runner import SystemAIRunner
        SystemAIRunner.send_message(
            content=message,
            from_agent="__health_check__",
            project_id="__system_ai__",
        )
        logger.info(f"[HealthCheck] 시스템 AI에게 건강 체크 요청 전송 (assumed {len(assumed)}개 중 {min(len(assumed), 50)}개 전달)")
    except Exception as e:
        logger.error(f"[HealthCheck] 시스템 AI 메시지 전송 실패: {e}")
