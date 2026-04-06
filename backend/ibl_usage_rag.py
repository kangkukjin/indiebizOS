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
    DEFAULT_K = 5
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
        lines = ['<ibl_references note="아래는 유사한 과거 용례입니다. code의 IBL 코드를 참고하되, 반드시 execute_ibl 도구의 code 파라미터로 실행하세요. 절대 텍스트 응답에 IBL 코드를 포함하지 마세요. 분석/판단/정리가 필요한 작업은 파이프라인(>>)으로 엮지 말고 액션을 하나씩 호출하면서 중간에 생각하세요.">']
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
        """사용자 메시지에 IBL 참조를 주입한 새 메시지 반환

        참조가 있으면 메시지 앞에 XML 블록 추가.
        없으면 원본 메시지 그대로 반환.
        """
        if not user_message or not self._is_ibl_relevant(user_message):
            return user_message

        refs = self.get_references(user_message, allowed_nodes=allowed_nodes)
        if refs:
            ref_count = refs.count('<ref ')
            print(f"[IBL RAG] 참조 {ref_count}개 주입: \"{user_message[:40]}...\"")
            return f"{refs}\n\n{user_message}"

        print(f"[IBL RAG] 참조 없음: \"{user_message[:40]}\"")
        return user_message

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


# =========================================================================
# 실행기억 (Execution Memory) — 파이프라인 전체가 공유하는 통합 기억
# =========================================================================

def build_execution_memory(user_message: str, allowed_nodes: set = None) -> str:
    """사용자 명령에 대한 실행기억을 생성한다.

    실행기억 = 해마(과거 IBL 코드 사례) + 코드 사례에 등장하는 액션의 implementation.
    파이프라인의 모든 에이전트(무의식/의식/실행/평가)가 동일한 실행기억을 공유한다.

    Returns:
        <execution_memory> XML 블록 문자열. 내용이 없으면 빈 문자열.
    """
    rag = IBLUsageRAG()

    if not user_message or not rag._is_ibl_relevant(user_message):
        return ""

    sections = []

    # 1) 해마 — 과거 IBL 코드 사례 (fine-tuned 임베딩 + BM25 하이브리드)
    refs_xml = rag.get_references(user_message, allowed_nodes=allowed_nodes)
    if refs_xml:
        sections.append(refs_xml)

    # 2) 해마 결과에서 [node:action] 패턴 추출 → implementation 조회
    impl_xml = _extract_implementations_from_refs(refs_xml)
    if impl_xml:
        sections.append(impl_xml)

    if not sections:
        return ""

    inner = "\n".join(sections)
    result = (
        '<execution_memory note="실행기억: 과거 코드 사례 + 구현 상세. '
        '반드시 execute_ibl 도구로 실행하세요.">\n'
        f'{inner}\n'
        '</execution_memory>'
    )
    # 로그: 실행기억 내용 출력 (해마 참조 + implementation)
    print(f"[실행기억] 생성 완료: \"{user_message[:40]}...\"")
    print(f"[실행기억] 내용:\n{result}")
    return result


def _extract_implementations_from_refs(refs_xml: str) -> str:
    """해마 코드 사례에서 [node:action] 패턴을 추출하여 implementation을 조회한다."""
    if not refs_xml:
        return ""

    pattern = re.compile(r'\[([a-z_-]+):([a-z_-]+)\]')
    ref_actions = set(pattern.findall(refs_xml))

    if not ref_actions:
        return ""

    lines = ['<implementations note="코드 사례에 등장하는 도구의 구현 상세">']
    for node, action in sorted(ref_actions):
        impl = _lookup_implementation(node, action)
        if impl:
            impl_escaped = impl.replace('"', '&quot;')
            lines.append(f'  <impl action="[{node}:{action}]" implementation="{impl_escaped}"/>')
    lines.append('</implementations>')

    if len(lines) <= 2:
        return ""

    return '\n'.join(lines)


def _lookup_implementation(node: str, action: str) -> str:
    """ibl_nodes.yaml에서 특정 액션의 implementation을 조회한다."""
    try:
        from ibl_access import _load_nodes_data
        nodes_data = _load_nodes_data()
        if not nodes_data:
            return ""
        node_config = nodes_data.get("nodes", {}).get(node, {})
        action_config = node_config.get("actions", {}).get(action, {})
        return action_config.get("implementation", "")
    except Exception:
        return ""


# =========================================================================
# 경험 증류 (Experience Distillation)
# =========================================================================

# 증류 임계값: 해마 최고 점수가 이 값 미만이면 새로운 패턴으로 판단
DISTILL_THRESHOLD = 0.7


def get_top_score(user_message: str, allowed_nodes: set = None) -> float:
    """사용자 메시지에 대한 해마 최고 점수를 반환한다."""
    try:
        from ibl_usage_db import IBLUsageDB
        db = IBLUsageDB()
        results = db.search_hybrid(query=user_message, top_k=1, allowed_nodes=allowed_nodes)
        if results:
            return results[0].score
        return 0.0
    except Exception:
        return 0.0


def distill_experience(user_message: str, tool_calls: list, top_score: float) -> bool:
    """실행 경험을 증류하여 해마에 저장한다.

    조건: 해마 점수가 DISTILL_THRESHOLD 미만이고, 도구 호출이 있었을 때만 실행.
    무의식 에이전트와 같은 경량 AI로 경험을 반성하여 일반화된 용례로 변환한다.

    Args:
        user_message: 사용자 원본 메시지
        tool_calls: 도구 실행 이력 [{tool_name, input, success}, ...]
        top_score: 해마 최고 점수 (build_execution_memory 시점)

    Returns:
        증류 성공 여부
    """
    if top_score >= DISTILL_THRESHOLD:
        return False

    if not tool_calls:
        return False

    # 성공한 IBL 호출만 필터
    ibl_calls = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        tool_name = tc.get("tool_name", "")
        if tool_name != "execute_ibl":
            continue
        if not tc.get("success", True):
            continue
        code = tc.get("input", {}).get("code", "")
        if code:
            ibl_calls.append(code)

    if not ibl_calls:
        return False

    # 증류: 실행 에이전트와 같은 모델로 반성
    try:
        tool_log = "\n".join(f"  {i+1}. {code}" for i, code in enumerate(ibl_calls))

        prompt = f"""다음은 사용자 명령과 그에 대해 실행된 IBL 코드 목록이다.
이 경험에서 핵심 패턴을 추출하여 용례로 만들어라.

사용자 명령: {user_message}

실행된 IBL 코드:
{tool_log}

규칙:
1. 사용자 명령을 일반화하라 (고유명사는 유지하되, 패턴으로서 재사용 가능하게)
2. 실행된 코드에서 중복/탐색성 호출을 제거하고 핵심만 남겨라
3. 단일 액션이면 그대로, 여러 액션이면 & 또는 >>로 조합하라
4. 결과는 반드시 JSON으로만 응답:

{{"intent": "일반화된 사용자 의도", "code": "[node:action]{{params}} 형태의 IBL 코드"}}"""

        # 반성 에이전트 프롬프트 로드
        from pathlib import Path
        _prompt_path = Path(__file__).parent.parent / "data" / "common_prompts" / "reflection_prompt.md"
        system_prompt = _prompt_path.read_text(encoding="utf-8").strip() if _prompt_path.exists() else ""

        # 반성 에이전트: 무의식 에이전트와 같은 경량 AI 사용 (도구 없음, 단순 텍스트)
        from consciousness_agent import lightweight_ai_call
        result = lightweight_ai_call(prompt=prompt, system_prompt=system_prompt)

        if not result:
            return False

        # JSON 파싱
        import json
        # ```json ... ``` 래핑 제거
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        distilled = json.loads(cleaned)
        intent = distilled.get("intent", "").strip()
        code = distilled.get("code", "").strip()

        if not intent or not code:
            return False

        # 노드 추출
        node_pattern = re.compile(r'\[([a-z_-]+):')
        nodes = ",".join(sorted(set(node_pattern.findall(code))))

        # 파이프라인 여부
        category = "pipeline" if (">>" in code or "&" in code) else "single"

        # 해마에 저장 (임베딩도 즉시 생성)
        from ibl_usage_db import IBLUsageDB
        db = IBLUsageDB()
        example_id = db.add_example(
            intent=intent,
            ibl_code=code,
            nodes=nodes,
            category=category,
            difficulty=1,
            source="distilled",
            tags="auto",
        )

        # 학습용 JSON 파일에 누적 (재학습 시 기존 데이터와 합쳐서 사용)
        from pathlib import Path
        import json as _json
        distilled_path = Path(__file__).parent.parent / "data" / "training" / "ibl_distilled.json"
        try:
            existing = _json.loads(distilled_path.read_text(encoding="utf-8")) if distilled_path.exists() else []
            existing.append({"intent": intent, "ibl_code": code})
            distilled_path.write_text(_json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        # RAG 캐시 무효화
        rag = IBLUsageRAG()
        rag.clear_cache()

        print(f"[경험증류] 저장 완료 (id={example_id}, score={top_score:.2f}/학습): "
              f"\"{intent[:40]}\" → {code[:60]}")
        return True

    except Exception as e:
        print(f"[경험증류] 실패: {e}")
        return False
