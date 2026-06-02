"""
tool_context.py - 도구 핸들러가 받는 실행 컨텍스트
IndieBiz OS Core

도구 핸들러의 새 시그니처:
    def execute(tool_input: dict, context: ToolContext) -> str

ToolContext는 디스패처(ibl_routing._route_handler)가 항상 주입한다.
- project_path 필수, '.' 또는 None 불가 (구조적으로 cwd 의존 차단)
- output_dir(name)은 항상 절대경로 반환
- resolve_path(path)는 상대경로를 project_path 기준 절대경로로 정규화

마이그레이션 기간에는 디스패처가 inspect.signature로 신규/구 시그니처를
판별하여 양립한다. 모든 도구 마이그레이션이 끝나면 구 시그니처 지원은 제거한다.
"""

from __future__ import annotations

import os
from typing import Optional


class ToolContextError(ValueError):
    """ToolContext 생성/사용 시 발생하는 컨트랙트 위반."""


class ToolContext:
    """도구 실행 컨텍스트.

    디스패처가 활성 프로젝트/에이전트/태스크 정보를 묶어 도구에 주입한다.
    도구는 이 컨텍스트를 통해서만 외부 경로를 결정한다 — cwd 의존 금지.
    """

    def __init__(
        self,
        project_path: str,
        tool_name: str,
        project_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ):
        if not project_path or project_path == "." or project_path.strip() == "":
            raise ToolContextError(
                "ToolContext.project_path는 필수다. '.', 빈 값, None 모두 불가. "
                "디스패처가 활성 프로젝트의 절대경로를 주입해야 한다. "
                f"(tool_name={tool_name!r})"
            )
        if not tool_name:
            raise ToolContextError("ToolContext.tool_name은 필수다.")

        self.project_path: str = os.path.abspath(project_path)
        self.tool_name: str = tool_name
        self.project_id: Optional[str] = project_id
        self.agent_id: Optional[str] = agent_id
        self.task_id: Optional[str] = task_id

    def output_dir(self, name: Optional[str] = None) -> str:
        """프로젝트 outputs 디렉토리 (항상 절대경로, mkdir 자동).

        name을 주면 outputs/<name> 하위 디렉토리를 만들어 반환.
        """
        base = os.path.join(self.project_path, "outputs")
        path = os.path.join(base, name) if name else base
        os.makedirs(path, exist_ok=True)
        return os.path.abspath(path)

    def resolve_path(self, path: str) -> str:
        """상대경로면 project_path 기준 절대경로로, 절대경로면 그대로."""
        if os.path.isabs(path):
            return path
        return os.path.abspath(os.path.join(self.project_path, path))

    @classmethod
    def from_thread_context(cls, project_path: str, tool_name: str) -> "ToolContext":
        """thread_context에서 project_id/agent_id/task_id를 자동 채워서 생성.

        디스패처가 도구를 호출하기 직전에 사용하는 표준 팩토리.
        """
        try:
            from thread_context import (
                get_current_project_id,
                get_current_agent_id,
                get_current_task_id,
            )
            project_id = get_current_project_id()
            agent_id = get_current_agent_id()
            task_id = get_current_task_id()
        except Exception:
            project_id = agent_id = task_id = None

        return cls(
            project_path=project_path,
            tool_name=tool_name,
            project_id=project_id,
            agent_id=agent_id,
            task_id=task_id,
        )

    def __repr__(self) -> str:
        return (
            f"ToolContext(tool={self.tool_name!r}, project={self.project_id!r}, "
            f"agent={self.agent_id!r}, path={self.project_path!r})"
        )
