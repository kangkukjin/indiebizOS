"""Leaf output and goal-management exports; no language control-flow execution.

Edition-1 condition/case/each/assignment interpreters have been removed.
"""
from typing import Dict, Optional

# 통화 진단의 정본 — 2026-08-22 에 여기서 common/currency 로 이사했다(소비자가 셋이 되며
# ibl 층 안쪽에 두면 패키지 핸들러가 ibl 내부를 찔러야 했다). 옛 import 경로 보존용 재수출.
from common.currency import currency_shape_note  # noqa: F401


_nodes_cache: Optional[Dict] = None


def _load_nodes() -> Dict:
    """nodes: 섹션 로드 (캐싱)"""
    global _nodes_cache
    if _nodes_cache is not None:
        return _nodes_cache
    from ibl_registry import load_nodes_installed
    data = load_nodes_installed()
    _nodes_cache = data.get("nodes", {})
    return _nodes_cache


# (2026-08-05 감사 D11) 옛 노드타입 디스패치(_execute_node/_execute_info_node/
# _execute_store_node/_execute_exec_node)는 삭제 — 트리거 노드명 info/store/exec/output 이
# 레지스트리에 존재하지 않아 도달 불가였고, 도달해도 config type 부재로 오류만 반환했다.

# ============================================================
# Phase 13: 출력 노드 함수들
# ============================================================

# 출력·목표 관리 잎 도구는 형제 모듈에 산다.
#    공개 이름은 여기서 재수출 — 호출자·시험(`ex._x` monkeypatch 포함)은 무변경.
from ibl_exec_output import (  # noqa: F401
    _output_gui, extract_path_from_prev, _output_open, _output_clipboard, _output_download,
)
from ibl_exec_goal import (  # noqa: F401
    _goal_list, _goal_status, _goal_kill, _goal_delete,
    _log_attempt, _get_attempts, _summarize_attempts,
)
