"""
cognitive_recall.py - 0단계 연상 회상 믹스인 (러너 쪽 입구)
IndieBiz OS Core

연상의 흐름(주체 관문·정책·조립·기록)은 backend/cognition/associative_recall.py 가 맡는다(2026-09-18 공통 흐름).
이 믹스인은 러너가 그 흐름을 부르는 한 자리(`_associate`)와, 증류가 함께 쓰는 포식 의도 단서만 남긴다.
회원 러너는 `_associate` 를 덮어써 주인 기억을 돌지 않게 한다(member_runner).
"""

from typing import Optional


class CognitiveRecallMixin:
    """0단계 연상 — 공통 흐름의 러너 쪽 입구."""

    def _associate(self, message: str, *, history: Optional[list] = None, channel: str = "pipeline",
                   action_hint: Optional[str] = None, deep: bool = True):
        """1상 회상. 반환된 Recall 은 반드시 `.route(request_type)` 로 닫은 뒤 `.text()` 로 읽는다.

        Args:
            action_hint: 마법책에서 사용자가 명시적으로 고른 액션 ID — 해마 검색을 건너뛰고 그 액션을 Top-1 로 합성.
            deep: 심층기억(지도·선택) 자동 주입 — 포식 표면은 False(필터버블 드리프트 방지, 2026-09-18 판정).
        """
        from associative_recall import begin
        return begin(self, message, history=history, channel=channel, action_hint=action_hint, deep=deep)

    _FORAGE_CUES = (
        "찾", "검색", "어디", "뒤져", "뒤지", "파일", "사진", "자료", "폴더",
        "문서", "디스크", "볼륨", "찍은", "받은", "저장한", "예전", "지난",
        "코드", "코드베이스", "함수", "클래스", "구현", "정의", "모듈", "리포",
        "웹", "온라인", "인터넷", "구글", "논문", "기사",
        "find", "search", "where", "locate", "file", "photo", "folder",
        "document", "disk", "volume", "code", "codebase", "function",
        "implement", "module", "repo", "defined", "web", "online", "scholar", "arxiv",
    )
