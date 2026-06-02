"""
goal_evaluator.py - 목표 조건 평가 및 비용 산출 (Phase 26)

기능:
- 범위 표현식 매칭 (case문)
- if/case 조건 분기 선택
- 종료 조건 판단 (until > deadline > max_rounds/max_cost)
- 비용 산출 및 확인 메시지 생성
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import re


# ============ 모델별 토큰 단가 (USD) ============

MODEL_COSTS = {
    "claude-sonnet-4-6": {
        "input_per_1k": 0.003,
        "output_per_1k": 0.015,
    },
    "claude-opus-4-6": {
        "input_per_1k": 0.015,
        "output_per_1k": 0.075,
    },
    "claude-haiku-4-5": {
        "input_per_1k": 0.0008,
        "output_per_1k": 0.004,
    },
    # 기본값 (모델 미지정 시)
    "default": {
        "input_per_1k": 0.003,
        "output_per_1k": 0.015,
    }
}

# 라운드당 평균 토큰 추정
TOKENS_PER_JUDGMENT = {
    "input": 2000,   # success_condition 평가용 프롬프트
    "output": 500,   # 판단 결과
}

TOKENS_PER_ACTION = {
    "input": 1500,   # 액션 실행 프롬프트
    "output": 1000,  # 액션 결과
}


# ============ 범위 표현식 매칭 ============

def evaluate_range(value: float, range_expr: Dict) -> bool:
    """
    범위 표현식에 대해 값 매칭

    Args:
        value: 비교할 숫자 값
        range_expr: 파서에서 생성한 범위 dict
            {"op": "gt", "value": 20.0, "unit": "%"}
            {"op": "range", "min": 10.0, "max": 20.0, "unit": "%"}

    Returns:
        True if value matches range
    """
    op = range_expr.get("op")

    if op == "gt":
        return value > range_expr["value"]
    elif op == "gte":
        return value >= range_expr["value"]
    elif op == "lt":
        return value < range_expr["value"]
    elif op == "lte":
        return value <= range_expr["value"]
    elif op == "eq":
        return value == range_expr["value"]
    elif op == "range":
        return range_expr["min"] <= value <= range_expr["max"]

    return False


# ============ Case 분기 선택 ============

def select_case_branch(sense_value: Any, branches: List[Dict],
                       default: Optional[Dict] = None) -> Optional[Dict]:
    """
    case문에서 sense 값에 맞는 분기 선택

    Args:
        sense_value: sense 노드에서 가져온 값 (문자열 또는 숫자)
        branches: [{"pattern": "...", "range": {...}, "action": {...}}, ...]
        default: 기본 분기 action

    Returns:
        매칭된 action dict 또는 default
    """
    for branch in branches:
        pattern = branch.get("pattern", "")
        range_expr = branch.get("range")

        # range가 없으면 pattern 문자열에서 동적 파싱 시도
        if not range_expr and pattern and _is_numeric(sense_value):
            try:
                from ibl_parser import parse_range_expression
                range_expr = parse_range_expression(pattern)
            except Exception:
                pass

        # 범위 표현식 매칭 (숫자)
        if range_expr and _is_numeric(sense_value):
            num_value = float(sense_value)
            if evaluate_range(num_value, range_expr):
                return branch.get("action")

        # 문자열 매칭
        elif str(sense_value) == pattern:
            return branch.get("action")

    return default


def _is_numeric(value: Any) -> bool:
    """값이 숫자로 변환 가능한지 확인"""
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


# ============ 종료 조건 판단 ============

def check_termination(goal: Dict) -> Optional[str]:
    """
    목표의 종료 조건 체크 (우선순위: until > deadline > max_rounds/max_cost)

    Args:
        goal: DB에서 가져온 goal dict

    Returns:
        종료 사유 문자열 또는 None (계속 진행)
        - "achieved": until 조건 충족 (외부에서 판단 후 호출)
        - "expired": deadline 도달
        - "limit_reached_rounds": max_rounds 도달
        - "limit_reached_cost": max_cost 도달
    """
    # deadline 체크
    deadline = goal.get("deadline")
    if deadline:
        try:
            deadline_dt = _parse_datetime(deadline)
            if deadline_dt and datetime.now() >= deadline_dt:
                return "expired"
        except (ValueError, TypeError):
            pass

    # max_rounds 체크
    current_round = goal.get("current_round", 0)
    max_rounds = goal.get("max_rounds")
    if max_rounds and current_round >= max_rounds:
        return "limit_reached_rounds"

    # max_cost 체크
    cumulative_cost = goal.get("cumulative_cost", 0.0)
    max_cost = goal.get("max_cost")
    if max_cost and cumulative_cost >= max_cost:
        return "limit_reached_cost"

    return None


def _parse_datetime(text: str) -> Optional[datetime]:
    """다양한 형식의 날짜/시간 문자열 파싱"""
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


# ============ within 기한 계산 ============

def parse_within_duration(within_str: str) -> Optional[timedelta]:
    """
    within 기한 문자열 파싱

    Args:
        within_str: "2h", "30m", "1d", "3h30m" 등

    Returns:
        timedelta 또는 None
    """
    if not within_str:
        return None

    total_seconds = 0
    # 시간
    h_match = re.search(r'(\d+)\s*h', within_str)
    if h_match:
        total_seconds += int(h_match.group(1)) * 3600
    # 분
    m_match = re.search(r'(\d+)\s*m', within_str)
    if m_match:
        total_seconds += int(m_match.group(1)) * 60
    # 일
    d_match = re.search(r'(\d+)\s*d', within_str)
    if d_match:
        total_seconds += int(d_match.group(1)) * 86400

    return timedelta(seconds=total_seconds) if total_seconds > 0 else None


# ============ 비용 산출 ============

def estimate_goal_cost(goal_data: Dict, model_name: str = "default") -> float:
    """
    목표 실행 예상 비용 산출 (USD)

    Args:
        goal_data: 파싱된 goal dict
        model_name: 사용 모델 이름

    Returns:
        예상 비용 (USD)
    """
    costs = MODEL_COSTS.get(model_name, MODEL_COSTS["default"])

    max_rounds = goal_data.get("max_rounds", 100)

    # 라운드당 판단 비용 (success_condition 평가)
    judgment_cost_per_round = (
        (TOKENS_PER_JUDGMENT["input"] * costs["input_per_1k"] / 1000) +
        (TOKENS_PER_JUDGMENT["output"] * costs["output_per_1k"] / 1000)
    )

    # 라운드당 액션 실행 비용
    action_cost_per_round = (
        (TOKENS_PER_ACTION["input"] * costs["input_per_1k"] / 1000) +
        (TOKENS_PER_ACTION["output"] * costs["output_per_1k"] / 1000)
    )

    # 조건 평가 추가 비용 (strategy에 if/case 있을 때)
    condition_cost = 0
    strategy = goal_data.get("strategy")
    if strategy:
        if isinstance(strategy, dict):
            num_conditions = _count_conditions(strategy)
        else:
            num_conditions = str(strategy).count("[if:") + str(strategy).count("[case:")
        condition_cost = num_conditions * judgment_cost_per_round * 0.3  # 조건 평가는 판단의 30%

    total_per_round = judgment_cost_per_round + action_cost_per_round + condition_cost
    total = total_per_round * max_rounds

    # max_cost가 있으면 그 값으로 상한
    max_cost = goal_data.get("max_cost")
    if max_cost:
        total = min(total, float(max_cost))

    return round(total, 2)


def _count_conditions(strategy: Dict) -> int:
    """strategy dict 내 조건 블록 수 세기"""
    count = 0
    if isinstance(strategy, dict):
        if strategy.get("_condition"):
            count += len(strategy.get("branches", []))
        elif strategy.get("_case"):
            count += len(strategy.get("branches", []))
    return max(count, 1)


def format_cost_confirmation(goal_name: str, estimated_cost: float,
                             max_rounds: int, every: str = None) -> str:
    """
    사용자 확인 메시지 생성

    Returns:
        "이 Goal은 ... 예상 비용은 약 $X.XX입니다. 진행하시겠습니까?"
    """
    parts = [f"목표 '{goal_name}'을(를) 실행합니다."]

    if every:
        parts.append(f"실행 빈도: {every}")

    parts.append(f"최대 {max_rounds}라운드")
    parts.append(f"예상 비용: 약 ${estimated_cost:.2f}")
    parts.append("진행하시겠습니까?")

    return "\n".join(parts)
