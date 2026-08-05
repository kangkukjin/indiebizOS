"""살아있는 에이전트 런너 등기부 — api_agents 에서 이동 (2026-08-05 감사 ⑦).

왜 분리: 프로젝트별 활성 AgentRunner 레지스트리를 calendar_actions(서비스층)·
api_nodes 등이 읽는데, 그것이 라우터 모듈(api_agents)에 살아 아래층→표면
역방향 import 를 만들었다. 상태는 데이터층의 것 — 라우터(시작/중지 엔드포인트)는
여기의 dict 를 가져다 조작만 한다(같은 객체 공유, 재바인딩 금지).
"""

from typing import Any, Dict

# 에이전트 런너 관리 (프로젝트별)
agent_runners: Dict[str, Dict[str, Any]] = {}


def get_agent_runners():
    """agent_runners 반환"""
    return agent_runners
