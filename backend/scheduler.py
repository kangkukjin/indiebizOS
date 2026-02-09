"""
scheduler.py - 하위 호환 래퍼
IndieBiz OS Core

이 파일은 calendar_manager.py의 CalendarManager로 리다이렉트합니다.
기존에 `from scheduler import get_scheduler`를 사용하는 코드의 호환성을 유지합니다.

모든 스케줄/캘린더 기능은 calendar_manager.py에서 관리됩니다.
"""

from calendar_manager import get_calendar_manager


def get_scheduler(log_callback=None):
    """하위 호환 - CalendarManager를 스케줄러로 사용"""
    return get_calendar_manager(log_callback)
