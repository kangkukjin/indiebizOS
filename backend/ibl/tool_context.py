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

    # ── 산출 경로 해소기 — emitter 공통 정본 (2026-08-23 J29-1 판정) ──
    # 29회차 상상훈련 F29-2: 같은 파이프 끝에 무엇을 놓느냐에 따라 파일이 어디 떨어질지가
    # 달랐다. [table:spreadsheet] 는 준 경로를 지키고, [table:document] 는 디렉토리를 버리고
    # (고지는 했다), [table:chart] 는 말없이 버렸다. 셋이 서로 다른 해소기를 들고 있었다.
    #
    # 판정 = **주어진 경로는 지킨다**([self:write] 가 세운 몸의 오래된 규약에 맞춘다).
    # 반대안(모두 프로젝트 outputs 강제)은 `/tmp`·NAS 로 쓰던 문장을 조용히 딴 데로 보낸다 —
    # 침묵 이동은 이 몸이 금하는 부류다. 지금 규약을 바꿔도 **bare 파일명은 그대로
    # outputs/ 로 간다**(가장 흔한 경우 = 무변화). 달라지는 것은 사용자가 디렉토리를 적어
    # 준 경우뿐이고, 거기서 옛 동작(버린다)은 어느 쪽으로도 옳지 않았다.
    #
    # 해소기는 하나여야 한다(25회차 원칙) — 그래서 배치 규칙은 여기 한 곳에만 산다.
    # 확장자 보정은 emitter 마다 다르므로(format→확장자) 호출자가 미리 끝내고 부른다.
    def resolve_output_path(self, raw: Optional[str], *, stem: str = "output",
                            ext: str = "", guard=None) -> dict:
        """산출 경로를 몸의 단일 규약으로 해소한다.

        규약(= [self:write]·[table:spreadsheet] 가 이미 쓰던 것):
          ① raw 없음        → outputs/{stem}_{YYYYmmdd_HHMMSS}{ext}
          ② '~' 확장
          ③ 절대경로        → 그대로 (guard 가 범위를 판정)
          ④ 디렉토리 포함    → project_path 기준
          ⑤ bare 파일명      → outputs/ 로 리다이렉트 (프로젝트 루트에 같은 이름이
                              이미 있으면 그 파일을 쓴다 — 기존 write_file 규약)

        guard: (abs_path, project_path) -> 거부 메시지 | None.
               생략하면 쓰기 게이트(system_essentials)의 것을 빌린다. 게이트를 못 빌리면
               **fail-closed** — 프로젝트 밖 경로를 거절한다(있는 척하지 않는다).

        반환: {"path": 절대경로, "redirected": bool, "note": str}
              또는 {"error": 거부 메시지}
        """
        from datetime import datetime

        raw = (raw or "").strip()
        redirected = False
        if not raw:
            raw = f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        raw = os.path.expanduser(raw)

        path = os.path.join(self.project_path, raw)
        note = ""
        if (not os.path.isabs(raw)
                and os.sep not in raw and "/" not in raw
                and not os.path.exists(path)):
            raw = os.path.join("outputs", raw)
            path = os.path.join(self.project_path, raw)
            redirected = True

        err = self._scope_refusal(path, guard)
        if err:
            return {"error": err}

        os.makedirs(os.path.dirname(path) or self.project_path, exist_ok=True)
        return {"path": os.path.abspath(path), "redirected": redirected, "note": note}

    def _scope_refusal(self, path: str, guard=None) -> Optional[str]:
        """쓰기 범위 판정. 게이트를 빌리고, 못 빌리면 프로젝트 안으로 잠근다."""
        if guard is None:
            try:
                from tool_loader import load_tool_handler
                guard = getattr(load_tool_handler("write_file"),
                                "_validate_path_in_scope", None)
            except Exception:
                guard = None
        if guard is not None:
            return guard(path, self.project_path)
        # fail-closed: 게이트를 못 물었으면 프로젝트 밖으로 나가지 않는다.
        real = os.path.abspath(path)
        root = os.path.abspath(self.project_path)
        if real != root and not real.startswith(root + os.sep):
            return (f"Error: 쓰기 범위를 판정할 수 없어 프로젝트 밖 경로를 거절합니다: {path}\n"
                    f"(쓰기 게이트를 불러오지 못했습니다. 프로젝트 안 경로를 쓰거나 "
                    f">> [self:copy]{{destination: ...}} 로 옮기세요.)")
        return None

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
