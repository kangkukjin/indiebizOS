"""
agent_goals.py - Goal 실행 Mixin for AgentRunner

AgentRunner에서 분리된 Goal 실행 관련 메서드들을 포함하는 Mixin 클래스.
Phase 26 목표/시간/조건 시스템의 핵심 로직을 담당한다.
"""

import os
from datetime import datetime
from typing import Any, Optional


class AgentGoalsMixin:
    """
    Goal 실행 Mixin — AgentRunner에 믹스인하여 Goal 관련 기능 제공

    - Goal 생성/승인/활성화
    - 판단 루프 (judgment loop)
    - 전략 분기 (strategy resolve)
    - 조건 평가 (sense 노드 실행)
    - AI 기반 IBL 생성/실행
    - 비용 추정 및 결과 보고
    - 스케줄 등록 및 복구
    """

    # ============ Goal 실행 (Phase 26) ============

    def _get_goals_db(self):
        """Goal 관리용 ConversationDB 인스턴스"""
        from conversation_db import ConversationDB
        db_path = os.path.join(self.project_path, "conversations.db")
        return ConversationDB(db_path)

    def execute_goal(self, goal_data: dict) -> dict:
        """
        Goal Block 실행 (파서 출력을 받아 Goal 생성 → 활성화 → 판단 루프)

        Args:
            goal_data: 파싱된 goal dict (_goal=True, name, success_condition, ...)

        Returns:
            {"goal_id": "...", "status": "...", "message": "..."}
        """
        import uuid
        from goal_evaluator import (
            estimate_goal_cost, format_cost_confirmation, check_termination
        )

        db = self._get_goals_db()
        goal_id = f"goal_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # 1. Goal 생성
        db.create_goal(goal_id, goal_data)

        # 2. 비용 산출
        model_name = self.config.get("model", "default")
        estimated_cost = estimate_goal_cost(goal_data, model_name)

        # 3. 사용자 확인 (every/schedule이 있는 장기 Goal만)
        needs_confirmation = (
            goal_data.get("every") or goal_data.get("schedule") or
            estimated_cost > 1.0 or
            goal_data.get("max_rounds", 0) > 10
        )

        if needs_confirmation:
            msg = format_cost_confirmation(
                goal_data.get("name", ""),
                estimated_cost,
                goal_data.get("max_rounds", 100),
                goal_data.get("every")
            )
            self._log(f"[Goal] 사용자 확인 필요: {msg}")
            # 확인을 기다리지 않고 pending 상태로 반환
            # (실제 확인은 GUI/API에서 approve_goal 호출)
            return {
                "goal_id": goal_id,
                "status": "pending_approval",
                "estimated_cost": estimated_cost,
                "message": msg
            }

        # 4. 즉시 실행 (단순 Goal)
        return self._activate_and_run_goal(goal_id)

    def approve_goal(self, goal_id: str) -> dict:
        """
        사용자 승인 후 Goal 활성화

        pending_approval 상태의 Goal을 승인하여 실행/스케줄링한다.
        GUI/API에서 호출된다.
        """
        db = self._get_goals_db()
        goal = db.get_goal(goal_id)
        if not goal:
            return {"error": f"Goal not found: {goal_id}"}

        if goal['status'] != 'pending':
            return {"error": f"Goal is not pending: {goal['status']}"}

        return self._activate_and_run_goal(goal_id)

    def _activate_and_run_goal(self, goal_id: str) -> dict:
        """Goal을 active로 전환하고 판단 루프 실행 (또는 스케줄 등록)"""
        from goal_evaluator import check_termination

        db = self._get_goals_db()
        goal = db.get_goal(goal_id)
        if not goal:
            return {"error": f"Goal not found: {goal_id}"}

        # active로 전환
        db.update_goal_status(goal_id, "active")
        self._log(f"[Goal] 활성화: {goal['name']} ({goal_id})")

        # every/schedule이 있는 Goal은 calendar_manager에 등록
        every = goal.get('every_frequency')
        schedule_at = goal.get('schedule_at')

        if every or schedule_at:
            schedule_result = self._register_goal_schedule(goal_id, goal)
            if schedule_result.get("error"):
                self._log(f"[Goal] 스케줄 등록 실패: {schedule_result['error']}")
            else:
                self._log(f"[Goal] 스케줄 등록: {schedule_result.get('event_id', '')}")

        # 즉시 첫 라운드 실행 (schedule-only Goal 제외)
        if schedule_at and not every:
            # 일회성 예약: 즉시 실행하지 않고 스케줄 대기
            return {
                "goal_id": goal_id,
                "status": "active",
                "message": f"Goal 예약됨: {schedule_at}에 실행 예정"
            }

        # 판단 루프 실행
        result = self._judgment_loop(goal_id)
        return result

    def _register_goal_schedule(self, goal_id: str, goal: dict) -> dict:
        """
        Goal의 every/schedule을 calendar_manager에 등록

        Args:
            goal_id: 목표 ID
            goal: goal dict

        Returns:
            {"event_id": "...", "message": "..."} 또는 {"error": "..."}
        """
        try:
            from calendar_manager import get_calendar_manager

            cm = get_calendar_manager(log_callback=lambda msg: self._log(f"[Goal Schedule] {msg}"))

            every = goal.get('every_frequency', '')
            schedule_at = goal.get('schedule_at', '')
            goal_name = goal.get('name', 'unnamed')

            # every 파싱: "매일 08:00", "매주 월요일 09:00", "daily 08:00" 등
            repeat_type, event_time, weekdays = self._parse_every_frequency(every)

            if schedule_at and not every:
                # 일회성 예약
                result = cm.add_event(
                    title=f"[Goal] {goal_name}",
                    event_date=schedule_at.split(" ")[0] if " " in schedule_at else schedule_at,
                    event_type="goal",
                    repeat="none",
                    event_time=schedule_at.split(" ")[1] if " " in schedule_at else "09:00",
                    action="run_goal",
                    action_params={"goal_id": goal_id},
                    description=f"Goal 예약 실행: {goal_name}"
                )
            else:
                # 반복 실행
                result = cm.add_event(
                    title=f"[Goal] {goal_name}",
                    event_type="goal",
                    repeat=repeat_type,
                    event_time=event_time,
                    weekdays=weekdays,
                    action="run_goal",
                    action_params={"goal_id": goal_id},
                    description=f"Goal 반복 실행: {goal_name} ({every})"
                )

            return result if isinstance(result, dict) else {"event_id": str(result)}
        except Exception as e:
            self._log(f"[Goal] 스케줄 등록 오류: {e}")
            return {"error": str(e)}

    def _parse_every_frequency(self, every: str) -> tuple:
        """
        every 문자열을 calendar_manager 파라미터로 변환

        Args:
            every: "매일 08:00", "매주 월요일 09:00", "daily 08:00", "매시간" 등

        Returns:
            (repeat_type, event_time, weekdays)
        """
        import re

        if not every:
            return "daily", "09:00", None

        every_lower = every.lower().strip()

        # 시간 추출
        time_match = re.search(r'(\d{1,2}:\d{2})', every)
        event_time = time_match.group(1) if time_match else "09:00"

        # 요일 매핑
        day_map = {
            '월': 0, '화': 1, '수': 2, '목': 3, '금': 4, '토': 5, '일': 6,
            'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6,
            '월요일': 0, '화요일': 1, '수요일': 2, '목요일': 3,
            '금요일': 4, '토요일': 5, '일요일': 6,
        }

        weekdays = None

        if '매시간' in every or 'hourly' in every_lower:
            return "hourly", event_time, None
        elif '매일' in every or 'daily' in every_lower or '매일' in every:
            return "daily", event_time, None
        elif '매주' in every or 'weekly' in every_lower:
            # 요일 추출
            for day_name, day_num in day_map.items():
                if day_name in every:
                    weekdays = [day_num]
                    break
            return "weekly", event_time, weekdays or [0]  # 기본 월요일
        elif '매월' in every or 'monthly' in every_lower:
            return "monthly", event_time, None

        return "daily", event_time, None

    def _judgment_loop(self, goal_id: str) -> dict:
        """
        판단 루프 실행

        1. 종료 조건 체크 (until > deadline > max_rounds/max_cost)
        2. success_condition 평가 (AI 판단)
        3. strategy 내 조건 평가 (sense 노드 실행)
        4. IBL 생성 → 실행 → 결과 기록
        5. 반복
        """
        from goal_evaluator import check_termination
        from ibl_engine import execute_ibl

        db = self._get_goals_db()
        accumulated_results = []  # 라운드별 결과 누적 (AI 판단용 컨텍스트)

        while self.running:
            goal = db.get_goal(goal_id)
            if not goal or goal['status'] != 'active':
                break

            # 종료 조건 체크
            termination = check_termination(goal)
            if termination:
                if termination == "expired":
                    db.update_goal_status(goal_id, "expired")
                else:
                    db.update_goal_status(goal_id, "limit_reached")
                self._log(f"[Goal] 종료: {goal['name']} - {termination}")
                return self._report_goal_result(goal_id, termination)

            # 다음 라운드 실행
            round_num = goal['current_round'] + 1
            self._log(f"[Goal] 라운드 {round_num}/{goal['max_rounds']}: {goal['name']}")

            # success_condition 평가 (라운드 2 이상부터, 누적 결과가 있을 때)
            if round_num > 1 and accumulated_results and goal.get('success_condition'):
                achieved, judgment = self._evaluate_success_condition(goal, accumulated_results)
                self._log(f"[Goal] success_condition 평가: achieved={achieved}")
                if achieved:
                    db.update_goal_status(goal_id, "achieved")
                    self._log(f"[Goal] 달성: {goal['name']}")
                    return self._report_goal_result(goal_id, "achieved")

            # strategy가 있으면 조건에 따라 분기
            strategy = goal.get('strategy')
            if strategy and isinstance(strategy, dict):
                action = self._resolve_strategy(strategy, goal)
            else:
                action = None

            # IBL 실행
            round_cost = 0.0
            round_result = ""

            if action and isinstance(action, dict) and action.get("_node"):
                # 직접 실행 가능한 IBL step
                try:
                    result = execute_ibl(action, self.project_path, self.config.get("id", ""))
                    round_result = str(result)[:500] if result else "실행 완료"
                    round_cost = self._estimate_action_cost(action)
                except Exception as e:
                    round_result = f"실행 오류: {str(e)}"
                    round_cost = 0.005
            elif action and isinstance(action, dict) and action.get("_goal"):
                # 중첩 Goal (strategy 분기에서 Goal이 나온 경우)
                round_result = f"하위 Goal 생성: {action.get('name', 'unnamed')}"
                round_cost = 0.001
            else:
                # AI에게 판단 위임: success_condition 달성을 위한 IBL 생성 + 실행
                ai_result, ai_cost = self._ai_generate_and_execute(goal, accumulated_results)
                round_result = ai_result
                round_cost = ai_cost

            accumulated_results.append({
                "round": round_num,
                "result": round_result[:300]
            })
            # 최근 10개만 유지 (컨텍스트 크기 제한)
            if len(accumulated_results) > 10:
                accumulated_results = accumulated_results[-10:]

            # 비용 산출
            judgment_cost = self._estimate_judgment_cost()
            total_round_cost = round_cost + judgment_cost

            # 라운드 결과 기록
            db.add_goal_round(goal_id, round_num, total_round_cost, round_result)

            # 빈도 실행 Goal이면 이 라운드 후 대기 (다음 every 주기)
            if goal.get('every_frequency'):
                self._log(f"[Goal] 라운드 완료, 다음 주기 대기: {goal['every_frequency']}")
                return {
                    "goal_id": goal_id,
                    "status": "active",
                    "round": round_num,
                    "result": round_result,
                    "message": f"라운드 {round_num} 완료. 다음 실행: {goal['every_frequency']}"
                }

        # 루프 종료 (running=False 등)
        goal = db.get_goal(goal_id)
        return {
            "goal_id": goal_id,
            "status": goal.get("status", "unknown") if goal else "unknown",
            "message": "판단 루프 종료"
        }

    def _resolve_strategy(self, strategy: dict, goal: dict = None) -> Optional[dict]:
        """
        strategy 내 조건/case 평가하여 실행할 action 반환

        실제 sense 노드를 실행하여 조건을 평가한다.

        Args:
            strategy: _condition 또는 _case dict
            goal: 현재 goal dict (컨텍스트용)

        Returns:
            실행할 action dict 또는 None
        """
        from goal_evaluator import select_case_branch
        from ibl_engine import execute_ibl
        import re

        if strategy.get("_condition"):
            # if/else 조건문 — sense 실행 후 조건 평가
            for branch in strategy.get("branches", []):
                condition = branch.get("condition")
                if condition is None:
                    # else 분기
                    return branch.get("action")

                # 조건 파싱: "sense:field < 100" 형태
                sense_value = self._execute_condition_sense(condition)
                if sense_value is not None:
                    # 비교 연산자 추출 및 평가
                    if self._evaluate_condition_expr(condition, sense_value):
                        return branch.get("action")
                else:
                    # sense 실행 실패 시 다음 분기로
                    self._log(f"[Goal] 조건 평가 실패, 건너뜀: {condition}")
                    continue

            return None

        elif strategy.get("_case"):
            # case문 — sense 노드 실행 후 분기 선택
            source = strategy.get("source", "")
            branches = strategy.get("branches", [])
            default = strategy.get("default")

            # source에서 sense 값 가져오기
            sense_value = self._execute_sense_source(source)

            if sense_value is not None:
                result = select_case_branch(sense_value, branches, default)
                if result:
                    return result

            # sense 실패 시 default
            return default

        return None

    def _execute_condition_sense(self, condition: str) -> Any:
        """
        조건문에서 sense 부분을 실행하여 값 가져오기

        Args:
            condition: "sense:kospi < 2400", "sense:weather == '비'" 등

        Returns:
            sense 실행 결과 값 또는 None
        """
        import re
        from ibl_engine import execute_ibl

        # "sense:field" 부분 추출
        match = re.match(r'(sense:\w+)', condition)
        if not match:
            return None

        sense_ref = match.group(1)
        parts = sense_ref.split(":")
        if len(parts) != 2:
            return None

        node, action = parts[0], parts[1]

        try:
            step = {"_node": node, "action": action, "params": {}}
            result = execute_ibl(step, self.project_path, self.config.get("id", ""))

            # 결과에서 핵심 값 추출
            if isinstance(result, dict):
                return result.get("value", result.get("result", str(result)))
            return result
        except Exception as e:
            self._log(f"[Goal] sense 실행 오류: {sense_ref} - {e}")
            return None

    def _evaluate_condition_expr(self, condition: str, sense_value: Any) -> bool:
        """
        조건 표현식 평가

        Args:
            condition: "sense:kospi < 2400"
            sense_value: sense 실행 결과

        Returns:
            조건 충족 여부
        """
        import re

        # 연산자와 비교값 추출: "sense:xxx OP VALUE"
        match = re.search(r'(==|!=|>=|<=|>|<)\s*(.+)$', condition)
        if not match:
            # 연산자 없으면 truthy 판단
            return bool(sense_value)

        op = match.group(1)
        compare_raw = match.group(2).strip().strip("'\"")

        try:
            # 숫자 비교 시도
            sense_num = float(sense_value)
            compare_num = float(compare_raw)

            if op == "==": return sense_num == compare_num
            if op == "!=": return sense_num != compare_num
            if op == ">":  return sense_num > compare_num
            if op == ">=": return sense_num >= compare_num
            if op == "<":  return sense_num < compare_num
            if op == "<=": return sense_num <= compare_num
        except (ValueError, TypeError):
            # 문자열 비교
            sense_str = str(sense_value)
            if op == "==": return sense_str == compare_raw
            if op == "!=": return sense_str != compare_raw

        return False

    def _execute_sense_source(self, source: str) -> Any:
        """
        case문의 source (예: "sense:market_status")에서 값 가져오기

        Args:
            source: "sense:field" 형태

        Returns:
            sense 결과 값 또는 None
        """
        from ibl_engine import execute_ibl

        parts = source.split(":")
        if len(parts) != 2:
            return None

        node, action = parts[0], parts[1]

        try:
            step = {"_node": node, "action": action, "params": {}}
            result = execute_ibl(step, self.project_path, self.config.get("id", ""))

            if isinstance(result, dict):
                return result.get("value", result.get("result", str(result)))
            return result
        except Exception as e:
            self._log(f"[Goal] sense source 실행 오류: {source} - {e}")
            return None

    def _evaluate_success_condition(self, goal: dict, accumulated_results: list) -> tuple:
        """
        AI를 사용하여 success_condition 달성 여부 판단

        Args:
            goal: 현재 goal dict
            accumulated_results: 지금까지 라운드 결과 목록

        Returns:
            (achieved: bool, judgment: str)
        """
        if not self.ai:
            return False, "AI 미초기화"

        success_condition = goal.get('success_condition', '')
        goal_name = goal.get('name', '')

        # 최근 결과를 요약
        results_summary = "\n".join([
            f"라운드 {r['round']}: {r['result']}"
            for r in accumulated_results[-5:]  # 최근 5개
        ])

        prompt = (
            f"당신은 목표 달성 여부를 판단하는 평가자입니다.\n\n"
            f"목표: {goal_name}\n"
            f"달성 조건: {success_condition}\n\n"
            f"지금까지의 실행 결과:\n{results_summary}\n\n"
            f"위 결과를 바탕으로 달성 조건이 충족되었는지 판단하세요.\n"
            f"반드시 첫 줄에 ACHIEVED 또는 NOT_ACHIEVED 중 하나만 적고,\n"
            f"둘째 줄부터 간단한 판단 근거를 적으세요."
        )

        try:
            response = self.ai.process_message_with_history(
                message_content=prompt,
                history=[],
                task_id=f"goal_eval_{goal.get('goal_id', '')}"
            )

            first_line = response.strip().split('\n')[0].strip().upper()
            achieved = "ACHIEVED" in first_line and "NOT" not in first_line
            return achieved, response
        except Exception as e:
            self._log(f"[Goal] success_condition 평가 오류: {e}")
            return False, str(e)

    def _ai_generate_and_execute(self, goal: dict, accumulated_results: list) -> tuple:
        """
        AI에게 목표 달성을 위한 IBL을 생성하게 하고 실행

        Args:
            goal: 현재 goal dict
            accumulated_results: 지금까지 라운드 결과 목록

        Returns:
            (result_text: str, cost: float)
        """
        from ibl_parser import parse
        from ibl_engine import execute_ibl

        if not self.ai:
            return "AI 미초기화", 0.0

        goal_name = goal.get('name', '')
        success_condition = goal.get('success_condition', '')
        current_round = goal.get('current_round', 0)
        max_rounds = goal.get('max_rounds', 100)

        # 이전 결과 요약
        prev_summary = ""
        if accumulated_results:
            prev_summary = "\n".join([
                f"라운드 {r['round']}: {r['result']}"
                for r in accumulated_results[-3:]
            ])
            prev_summary = f"\n이전 실행 결과:\n{prev_summary}\n"

        prompt = (
            f"당신은 목표를 달성하기 위해 IBL 액션을 선택하는 에이전트입니다.\n\n"
            f"목표: {goal_name}\n"
            f"달성 조건: {success_condition}\n"
            f"현재 라운드: {current_round + 1}/{max_rounds}\n"
            f"{prev_summary}\n"
            f"목표 달성을 위해 지금 실행해야 할 IBL 액션을 하나 작성하세요.\n"
            f"IBL 형식: [node:action]{{param: \"value\"}}\n"
            f"반드시 실행 가능한 IBL 코드 한 줄만 작성하세요. 설명은 불필요합니다."
        )

        try:
            response = self.ai.process_message_with_history(
                message_content=prompt,
                history=[],
                task_id=f"goal_act_{goal.get('goal_id', '')}"
            )

            # AI 응답에서 IBL 추출 (정규식으로 [node:action]{...} 패턴 찾기)
            import re
            ibl_match = re.search(r'\[[\w]+:[\w]+\]\{[^}]*\}', response)
            if not ibl_match:
                # 간단한 형태도 시도: [node:action]
                ibl_match = re.search(r'\[[\w]+:[\w]+\]', response)

            if ibl_match:
                ibl_code = ibl_match.group(0)
                self._log(f"[Goal] AI 생성 IBL: {ibl_code}")

                # 파싱 + 실행
                parsed = parse(ibl_code)
                if parsed:
                    step = parsed[0]
                    result = execute_ibl(step, self.project_path, self.config.get("id", ""))
                    result_text = str(result)[:500] if result else "실행 완료"
                    cost = self._estimate_action_cost(step)
                    return f"IBL: {ibl_code} → {result_text}", cost + 0.02
                else:
                    return f"IBL 파싱 실패: {ibl_code}", 0.02
            else:
                # IBL 코드 없이 텍스트 응답만 온 경우
                return f"AI 응답 (IBL 미포함): {response[:300]}", 0.02

        except Exception as e:
            self._log(f"[Goal] AI 생성/실행 오류: {e}")
            return f"AI 생성 오류: {str(e)}", 0.02

    def _estimate_action_cost(self, step: dict) -> float:
        """
        IBL 액션 실행 비용 추정 (토큰 기반)

        Args:
            step: 파싱된 IBL step dict

        Returns:
            추정 비용 (USD)
        """
        from goal_evaluator import MODEL_COSTS, TOKENS_PER_ACTION

        model_name = self.config.get("model", "default") if hasattr(self, 'config') else "default"
        costs = MODEL_COSTS.get(model_name, MODEL_COSTS.get("default", {"input_per_1k": 0.003, "output_per_1k": 0.015}))

        cost = (
            (TOKENS_PER_ACTION["input"] * costs["input_per_1k"] / 1000) +
            (TOKENS_PER_ACTION["output"] * costs["output_per_1k"] / 1000)
        )
        return round(cost, 6)

    def _estimate_judgment_cost(self) -> float:
        """
        판단 루프 자체 비용 추정 (success_condition 평가)

        Returns:
            추정 비용 (USD)
        """
        from goal_evaluator import MODEL_COSTS, TOKENS_PER_JUDGMENT

        model_name = self.config.get("model", "default") if hasattr(self, 'config') else "default"
        costs = MODEL_COSTS.get(model_name, MODEL_COSTS.get("default", {"input_per_1k": 0.003, "output_per_1k": 0.015}))

        cost = (
            (TOKENS_PER_JUDGMENT["input"] * costs["input_per_1k"] / 1000) +
            (TOKENS_PER_JUDGMENT["output"] * costs["output_per_1k"] / 1000)
        )
        return round(cost, 6)

    def _report_goal_result(self, goal_id: str, reason: str) -> dict:
        """Goal 결과 보고"""
        db = self._get_goals_db()
        goal = db.get_goal(goal_id)
        if not goal:
            return {"error": f"Goal not found: {goal_id}"}

        rounds_data = goal.get("rounds_data", [])
        last_rounds = rounds_data[-3:] if isinstance(rounds_data, list) else []

        return {
            "goal_id": goal_id,
            "name": goal.get("name"),
            "status": goal.get("status"),
            "reason": reason,
            "total_rounds": goal.get("current_round", 0),
            "total_cost": f"${goal.get('cumulative_cost', 0):.2f}",
            "last_rounds": last_rounds,
            "message": f"목표 '{goal.get('name')}' {reason}으로 종료됨. "
                       f"{goal.get('current_round', 0)}라운드 실행, "
                       f"비용 ${goal.get('cumulative_cost', 0):.2f}"
        }

    def recover_active_goals(self):
        """
        시스템 재시작 시 활성 Goal 복구

        - every가 있는 Goal: 다음 주기를 기다림 (현재 라운드 포기)
        - every가 없는 일회성 Goal: 재개
        """
        try:
            db = self._get_goals_db()
            active_goals = db.list_goals(status="active")

            for goal in active_goals:
                if goal.get("every_frequency"):
                    self._log(f"[Goal 복구] '{goal['name']}' 다음 스케줄 대기")
                else:
                    self._log(f"[Goal 복구] '{goal['name']}' 재개 예정")
                    # 일회성 Goal은 다음 루프에서 재개
        except Exception as e:
            self._log(f"[Goal 복구] 오류: {e}")
