"""
ibl_usage_rag.py - IBL 용례 RAG 참조 모듈
IndieBiz OS Core

사용자 메시지를 기반으로 유사한 IBL 용례를 검색하여
AI 프롬프트에 "참고 사례"로 주입합니다.

핵심 원칙: AI가 용례를 기계적으로 복사하지 않고,
참조로 활용하여 새로운 상황에 맞게 IBL을 추론 생성하도록 유도.
"""

import re
import hashlib
import logging
import time
from typing import List, Optional, Set

logger = logging.getLogger(__name__)



class IBLUsageRAG:
    """IBL 용례 RAG 참조 시스템 (싱글톤)"""

    MAX_REFERENCES = 5
    DEFAULT_K = 3
    MIN_SCORE = 0.25
    CACHE_TTL = 300  # 5분

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = {}
            cls._instance._cache_times = {}
        return cls._instance

    def get_references(self, user_query: str,
                       k: int = None,
                       allowed_nodes: set = None) -> str:
        """사용자 쿼리에 대한 IBL 참조 용례 반환

        Args:
            user_query: 사용자 메시지 (자연어)
            k: 반환할 참조 수 (기본 3)
            allowed_nodes: 에이전트 허용 노드 집합

        Returns:
            XML 형식 참조 문자열 (프롬프트 주입용)
            빈 문자열이면 적합한 참조 없음
        """
        if not user_query or not self._is_ibl_relevant(user_query):
            return ""

        if k is None:
            k = self.DEFAULT_K
        k = min(k, self.MAX_REFERENCES)

        # 캐시 확인
        cache_key = hashlib.md5(
            f"{user_query}_{k}_{allowed_nodes}".encode()
        ).hexdigest()
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # DB 검색
        try:
            from ibl_usage_db import IBLUsageDB
            db = IBLUsageDB()
            results = db.search_hybrid(
                query=user_query,
                top_k=k,
                allowed_nodes=allowed_nodes
            )
        except Exception as e:
            logger.error(f"[IBL RAG] 검색 실패: {e}")
            return ""

        if not results:
            self._set_cached(cache_key, "")
            return ""

        # 최소 점수 필터
        filtered = [r for r in results if r.score >= self.MIN_SCORE]
        if not filtered:
            self._set_cached(cache_key, "")
            return ""

        xml = self._format_references(filtered)
        self._set_cached(cache_key, xml)
        return xml

    def _format_references(self, examples: list) -> str:
        """검색 결과를 프롬프트 주입용 XML로 포맷팅"""
        lines = ['<ibl_references note="아래는 유사한 과거 용례입니다. 참고만 하고 현재 요청에 맞게 변형하세요.">']
        for ex in examples:
            # XML 속성용 이스케이프
            intent = ex.intent.replace('"', '&quot;').replace("'", "&apos;")
            code = ex.ibl_code.replace('"', '&quot;')
            attrs = f'intent="{intent}" code=\'{ex.ibl_code}\' score="{ex.score}"'
            if ex.success_rate > 0:
                attrs += f' success_rate="{ex.success_rate}"'
            lines.append(f'  <ref {attrs}/>')
        lines.append('</ibl_references>')
        return '\n'.join(lines)

    def inject_references(self, user_message: str,
                          allowed_nodes: set = None) -> str:
        """사용자 메시지에 IBL 참조 + discover 결과를 주입한 새 메시지 반환

        참조가 있으면 메시지 앞에 XML 블록 추가.
        없으면 원본 메시지 그대로 반환.
        """
        if not user_message or not self._is_ibl_relevant(user_message):
            return user_message

        parts = []

        # 1) RAG 참조 (기존)
        refs = self.get_references(user_message, allowed_nodes=allowed_nodes)
        if refs:
            ref_count = refs.count('<ref ')
            parts.append(refs)
            print(f"[IBL RAG] 참조 {ref_count}개 주입: \"{user_message[:40]}...\"")

        # 2) discover 자동 주입 (키워드 기반 도구 추천, API 비용 없음)
        discover_xml = self._auto_discover(user_message, allowed_nodes)
        if discover_xml:
            parts.append(discover_xml)

        if parts:
            return "\n\n".join(parts) + f"\n\n{user_message}"

        print(f"[IBL RAG] 참조 없음: \"{user_message[:40]}\"")
        return user_message

    def _auto_discover(self, user_message: str,
                       allowed_nodes: set = None) -> str:
        """discover를 자동 호출하여 도구 추천 XML 생성 (API 비용 0)"""
        try:
            from node_registry import discover

            results = discover(user_message, limit=5)
            if not results:
                return ""

            # allowed_nodes 필터
            if allowed_nodes:
                results = [r for r in results if r["node"] in allowed_nodes]

            if not results:
                return ""

            # 최소 점수 필터 (너무 낮은 매칭 제외)
            results = [r for r in results if r["score"] >= 5]
            if not results:
                return ""

            # 상위 3개 노드, 각 노드당 상위 2개 액션만
            lines = ['<ibl_discover note="키워드 기반 추천 도구입니다. web_search 대신 전문 도구가 있으면 그것을 우선 사용하세요.">']
            for r in results[:3]:
                details = r.get("action_details", [])[:2]
                for d in details:
                    action = d["action"]
                    desc = d["description"]
                    example = d["example"]
                    lines.append(f'  <tool action="{action}" description="{desc}" example=\'{example}\'/>')
            lines.append('</ibl_discover>')

            if len(lines) <= 2:  # 헤더/푸터만 있으면 빈 결과
                return ""

            tool_count = len(lines) - 2
            print(f"[IBL Discover] 추천 {tool_count}개 주입: \"{user_message[:40]}...\"")
            return '\n'.join(lines)

        except Exception as e:
            logger.error(f"[IBL Discover] 실패 (무시): {e}")
            return ""

    def _is_ibl_relevant(self, query: str) -> bool:
        """메시지가 IBL 도구 사용이 필요한지 휴리스틱 판단

        제외 방식: 확실히 무관한 것만 걸러내고, 나머지는 통과.
        검색이 빈 결과를 반환하면 비용이 적으므로, 적극적으로 통과시킴.
        """
        query = query.strip()

        # 너무 짧은 메시지 (인사/감탄사)
        if len(query) < 4:
            return False

        # 순수 인사/감탄만으로 이루어진 메시지 제외
        _SKIP_PATTERNS = {
            "안녕", "안녕하세요", "안녕하십니까", "반갑습니다", "반가워",
            "ㅎㅇ", "ㅋㅋ", "ㅎㅎ", "ㅠㅠ", "ㄳ", "감사", "감사합니다",
            "고마워", "고맙습니다", "수고", "수고하세요",
            "네", "아니", "아니요", "응", "ㅇㅇ", "ㄴㄴ", "ok", "ㅂㅂ",
            "hi", "hello", "thanks", "bye", "yes", "no",
            "그래", "알겠어", "좋아", "됐어", "그만",
        }
        if query.lower() in _SKIP_PATTERNS:
            return False

        # 그 외는 전부 통과 — FTS5 검색 비용이 낮으므로
        return True

    # =========================================================================
    # 캐시
    # =========================================================================

    def _get_cached(self, key: str):
        if key in self._cache:
            cached_time = self._cache_times.get(key, 0)
            if time.time() - cached_time < self.CACHE_TTL:
                return self._cache[key]
            else:
                del self._cache[key]
                del self._cache_times[key]
        return None

    def _set_cached(self, key: str, value: str):
        self._cache[key] = value
        self._cache_times[key] = time.time()

    def clear_cache(self):
        """캐시 전체 초기화"""
        self._cache.clear()
        self._cache_times.clear()
