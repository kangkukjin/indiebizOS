"""은퇴한 셸→IBL 강제 관문의 호환 입구.

IBL은 도구 사이의 값·실패·재개를 조합해 모델 왕복을 줄이는 언어다.
비슷한 어휘가 있다는 이유로 셸/네이티브 호출을 거절하거나 번역하지 않는다.
이미 실행 중인 CLI의 옛 PreToolUse 설정도 다음 호출부터 통과시킨다.
자기수리 격리·위험 명령 승인·감독 경계는 각 소유자가 계속 검사한다.
"""
from typing import Any, Dict, List, Optional


def judge_shell(command: str, cwd: Optional[str] = None, root: Optional[str] = None,
                table: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """기존 호출자의 호환 함수. 언어 선택은 실행 거절 사유가 아니다."""
    return None


def judge_native(tool_name: str, tool_input: Dict[str, Any], cwd: Optional[str] = None,
                 root: Optional[str] = None, table: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """네이티브 도구도 IBL 중복 여부로 거절하지 않는다."""
    return None


def judge_hook_event(event: Dict[str, Any], root: Optional[str] = None) -> Optional[str]:
    """이미 시작된 CLI의 구형 훅 설정을 호환한다."""
    return None


def main(argv: Optional[List[str]] = None) -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
