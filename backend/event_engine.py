"""
event_engine.py - 하위 호환 래퍼
trigger_engine.py로 이전되었습니다.
"""
from trigger_engine import execute_trigger as execute_event, _add_history

__all__ = ["execute_event", "_add_history"]
