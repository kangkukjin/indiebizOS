"""
드라이버 기본 클래스

모든 IBL 드라이버가 공유하는 인터페이스.
리눅스 VFS처럼 read()가 디바이스를 감추듯,
Driver.execute()가 프로토콜을 감춘다.
"""
from abc import ABC, abstractmethod
from typing import Any


class Driver(ABC):
    """IBL 드라이버 기본 인터페이스"""

    @abstractmethod
    def execute(self, action: str, target: str, params: dict) -> dict:
        """
        정보 소스에 요청을 보내고 결과를 반환한다.

        Args:
            action: 수행할 동작 (search, query, get, list 등)
            target: 대상 (검색어, ID, 경로 등)
            params: 추가 파라미터

        Returns:
            {"success": True, "data": ..., "summary": "..."}
            또는
            {"success": False, "error": "..."}
        """
        ...

    @abstractmethod
    def list_actions(self) -> list:
        """이 드라이버가 지원하는 액션 목록"""
        ...

    def _ok(self, data: Any, summary: str = "") -> dict:
        """성공 응답 헬퍼"""
        result = {"success": True, "data": data}
        if summary:
            result["summary"] = summary
        return result

    def _err(self, message: str) -> dict:
        """에러 응답 헬퍼"""
        return {"success": False, "error": message}
