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
    # 표시 임계값. 0.65 미만은 사례 매칭이 약해서 의식 에이전트에 노이즈로
    # 작용한다 (예: "라벨지 필요해" 쿼리에 clipboard/copy/write 사례가 0.68로
    # 매칭되어 잘못된 액션을 추천하는 사고). 증류 임계값(0.7)보다는 살짝
    # 낮춰서, 0.65~0.7 구간(증류 후보)은 ref로 보여 의식이 활용 가능하게.
    MIN_SCORE = 0.65
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
        lines = ['<ibl_references note="참고 용례. execute_ibl 도구로 실행하고, 텍스트 응답에 IBL 코드를 넣지 마라. success_rate는 과거 실행 성공률(0~1)이니 낮으면 신중히 참고하라(없으면 미검증).">']
        for ex in examples:
            # XML 속성용 이스케이프
            intent = ex.intent.replace('"', '&quot;').replace("'", "&apos;")
            code = ex.ibl_code.replace('"', '&quot;')
            attrs = f'intent="{intent}" code=\'{ex.ibl_code}\' score="{ex.score}"'
            # success_rate >= 0 이면 시도 이력 있음(0.0=전부 실패 포함) → 표시.
            # -1.0(미검증)은 표시하지 않아 노이즈를 줄인다.
            if ex.success_rate >= 0:
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

def build_execution_memory(user_message: str, allowed_nodes: set = None) -> tuple:
    """사용자 명령에 대한 실행기억을 생성한다.

    실행기억 = 해마(과거 IBL 코드 사례) + 코드 사례에 등장하는 액션의 implementation.
    파이프라인의 모든 에이전트(무의식/의식/실행/평가)가 동일한 실행기억을 공유한다.

    해마 검색은 여기서 단 한 번만 일어난다. 호출 측은 반환된 top_score를
    그대로 사용해 Reflex 분기, 경험 증류 등에서 추가 검색을 피한다.

    Returns:
        (xml: str, top_score: float, top_code: str)
        - xml: <execution_memory> 블록 문자열 (내용 없으면 빈 문자열)
        - top_score: 해마 최고 점수 (없으면 0.0)
        - top_code: 해마 최고 점수 항목의 ibl_code (없으면 빈 문자열)
    """
    rag = IBLUsageRAG()

    if not user_message or not rag._is_ibl_relevant(user_message):
        return ("", 0.0, "")

    # 1) 해마 — 단일 검색으로 결과/최고 점수/최고 코드 모두 확보
    try:
        from ibl_usage_db import IBLUsageDB
        db = IBLUsageDB()
        results = db.search_hybrid(
            query=user_message,
            top_k=rag.DEFAULT_K,
            allowed_nodes=allowed_nodes,
        )
    except Exception as e:
        logger.error(f"[IBL RAG] 검색 실패: {e}")
        return ("", 0.0, "")

    top_score = results[0].score if results else 0.0
    top_code = results[0].ibl_code if results else ""

    # 최소 점수 필터
    filtered = [r for r in results if r.score >= rag.MIN_SCORE]

    sections = []
    refs_xml = rag._format_references(filtered) if filtered else ""
    if refs_xml:
        sections.append(refs_xml)

    # 2) 해마 결과에서 [node:action] 패턴 추출 → implementation 조회
    impl_xml = _extract_implementations_from_refs(refs_xml)
    if impl_xml:
        sections.append(impl_xml)

    if not sections:
        return ("", top_score, top_code)

    inner = "\n".join(sections)
    result = (
        '<execution_memory note="과거 코드 사례 + 구현 상세">\n'
        f'{inner}\n'
        '</execution_memory>'
    )
    # 로그
    print(f"[연상:실행기억] 생성 완료 (top_score={top_score:.3f}): \"{user_message[:40]}...\"")
    print(f"[연상:실행기억] 내용:\n{result}")
    return (result, top_score, top_code)


def build_execution_memory_from_hint(action_hint: str) -> tuple:
    """사용자가 마법책에서 명시적으로 선택한 액션을 Top-1로 <execution_memory> 합성.

    해마 시맨틱 검색을 건너뛰고, ibl_nodes.yaml에서 해당 액션의 메타와 implementation을
    직접 조회하여 의식 에이전트가 그 액션 중심으로 task_framing/capability_focus를 짤 수 있게 한다.

    Args:
        action_hint: "sense:price" 같은 [node:action] 형태의 액션 ID

    Returns:
        (xml, top_score, top_code)
        - 유효한 액션: 합성된 <execution_memory> XML, top_score=1.0, top_code="[node:action]"
        - 유효하지 않으면: ("", 0.0, "") — 호출 측에서 해마 검색으로 폴백 가능
    """
    if not action_hint or ":" not in action_hint:
        return ("", 0.0, "")

    node, action = action_hint.split(":", 1)
    node = node.strip()
    action = action.strip()
    if not node or not action:
        return ("", 0.0, "")

    try:
        from ibl_access import _load_nodes_data
        data = _load_nodes_data()
        action_config = (
            (data.get("nodes") or {}).get(node, {}).get("actions", {}).get(action, {})
        )
    except Exception:
        return ("", 0.0, "")

    if not action_config:
        return ("", 0.0, "")

    def _esc(s: str) -> str:
        return (s or "").replace('"', '&quot;')

    action_id = f"[{node}:{action}]"
    description = _esc(action_config.get("description", ""))
    target_description = _esc(action_config.get("target_description", ""))
    target_key = action_config.get("target_key", "")
    implementation = _esc(action_config.get("implementation", ""))

    sections = [
        f'  <user_selected_action action="{action_id}" '
        f'description="{description}" '
        f'target_description="{target_description}" '
        f'target_key="{target_key}"/>'
    ]
    if implementation:
        sections.append(
            '  <implementations note="구현 상세">\n'
            f'    <impl action="{action_id}" implementation="{implementation}"/>\n'
            '  </implementations>'
        )

    inner = "\n".join(sections)
    xml = (
        '<execution_memory note="사용자가 마법책에서 명시적으로 선택한 액션. 해마 검색 결과 대신 이 액션이 Top-1.">\n'
        f'{inner}\n'
        '</execution_memory>'
    )

    print(f"[연상:실행기억] 사용자 선택 액션 주입: {action_id}")
    return (xml, 1.0, action_id)


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


def _validate_ibl_actions(code: str) -> bool:
    """증류된 IBL 코드의 모든 [node:action]이 ibl_nodes.yaml에 실재하는지 검증.

    경량 AI 반성이 환각한 액션(없는 node:action)이 해마 코퍼스에 진입하면
    이후 연상으로 추천되어 실패를 유발한다. add_example 전에 정적으로 거른다.
    하나라도 미존재 액션이 있으면 False (증류 폐기)."""
    pairs = re.findall(r'\[([a-z_-]+):([a-z_-]+)\]', code or "")
    if not pairs:
        return False  # 액션 패턴이 없으면 용례로서 무의미
    try:
        from ibl_access import _load_nodes_data
        nodes_data = _load_nodes_data() or {}
        nodes = nodes_data.get("nodes", {})
    except Exception:
        # 노드 데이터 로드 실패 시 검증 불가 → 보수적으로 통과(기존 동작 유지)
        return True
    for node, action in pairs:
        actions = (nodes.get(node, {}) or {}).get("actions", {}) or {}
        if action not in actions:
            print(f"[경험증류] 검증 실패 — 미존재 액션 [{node}:{action}], 증류 폐기")
            return False
    return True


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


def get_top(user_message: str, allowed_nodes: set = None) -> tuple:
    """해마 최고 점수와 그 항목의 ibl_code를 함께 반환한다 (score, code).

    피드백 귀속(record_recall_outcome)에 top_code가 필요한 경로용."""
    try:
        from ibl_usage_db import IBLUsageDB
        db = IBLUsageDB()
        results = db.search_hybrid(query=user_message, top_k=1, allowed_nodes=allowed_nodes)
        if results:
            return (results[0].score, results[0].ibl_code)
        return (0.0, "")
    except Exception:
        return (0.0, "")


# 피드백 귀속 임계값: 이 점수 이상(Reflex 경로)에서만 top-1 example에 실행 결과 귀속.
# 연상은 example을 '참고'로 주입하고 AI가 새 코드를 생성하므로 귀속이 흐릿하지만,
# 고점수 경로는 top-1이 사실상 코드를 주도하므로 깔끔히 귀속된다.
RECALL_RECORD_THRESHOLD = 0.85


def record_recall_outcome(top_code: str, top_score: float, tool_calls: list) -> bool:
    """Reflex 경로에서 연상 top-1 example의 실행 성공/실패를 해마에 피드백한다.

    이것이 해마의 강화-감쇠 루프다. 기록된 성공/실패는 success_rate로 환산되어
    이후 연상 시 참조 XML에 표시되고(검증된 사례 부상), 정리 패스의 가지치기
    신호로도 쓸 수 있다.

    Args:
        top_code: 연상 최고점 항목의 ibl_code (build_execution_memory 반환)
        top_score: 해마 최고 점수
        tool_calls: 도구 실행 이력 [{tool_name, input, success}, ...]
    Returns:
        기록 여부 (귀속 불가/저점수 시 False)
    """
    if not top_code or top_score < RECALL_RECORD_THRESHOLD:
        return False
    if not tool_calls:
        return False

    # execute_ibl 호출들의 성공 여부 집계 (하나라도 실패하면 실패로 귀속)
    ibl_success = None
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        if tc.get("tool_name") != "execute_ibl":
            continue
        s = bool(tc.get("success", True))
        ibl_success = s if ibl_success is None else (ibl_success and s)

    if ibl_success is None:
        return False  # IBL 실행이 없었으면 귀속 불가

    try:
        from ibl_usage_db import IBLUsageDB
        db = IBLUsageDB()
        ok = db.update_success_by_code(top_code, ibl_success)
        if ok:
            print(f"[해마피드백] top-1 {'성공' if ibl_success else '실패'} 기록 "
                  f"(score={top_score:.2f}): {top_code[:50]}")
            # 성공률이 바뀌었으니 연상 캐시 무효화
            IBLUsageRAG().clear_cache()
        return ok
    except Exception as e:
        print(f"[해마피드백] 실패 (무시): {e}")
        return False


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
    # 해마 비활성(폰 기본)이면 증류도 건너뜀 — 안 그러면 top_score=0.0 이 매 명령마다 증류
    # LLM 호출을 켜서 오히려 더 느려진다(해마 끄기의 목적 무력화). search 와 한 쌍으로 게이트.
    from ibl_usage_db import IBLUsageDB
    if IBLUsageDB.hippo_disabled():
        return False

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
        # ```json ... ``` 래핑 제거 + JSON 객체 추출
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        # JSON 객체가 텍스트 안에 섞여 있을 때 추출
        if not cleaned.startswith("{"):
            json_start = cleaned.find("{")
            json_end = cleaned.rfind("}")
            if json_start >= 0 and json_end > json_start:
                cleaned = cleaned[json_start:json_end + 1]
            else:
                print(f"[경험증류] JSON 추출 실패: {cleaned[:100]}")
                return False

        distilled = json.loads(cleaned)
        intent = distilled.get("intent", "").strip()
        code = distilled.get("code", "").strip()

        if not intent or not code:
            return False

        # 검증 게이트: 환각된(미존재) 액션이 코퍼스에 진입하지 못하도록 정적 검증
        if not _validate_ibl_actions(code):
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


# =========================================================================
# 해마 정리 패스 (Hippocampus Consolidation) — 증류물 위생
# 심층메모리 정리 패스의 대칭. 증류(입력)는 쓰기 시점에, 정리(위생)는 배치로.
# 증류물(source='distilled')에만 적용하고 학습 코퍼스는 보호한다.
# =========================================================================

HIPPO_CADENCE_HOURS = 24
HIPPO_DISTILLED_CAP = 200
HIPPO_JSON_CAP = 800


def _hippo_marker_path():
    from pathlib import Path
    return Path(__file__).parent.parent / "data" / "training" / ".hippocampus_consolidated"


def _hippo_is_due(force: bool = False) -> bool:
    """마지막 정리 후 HIPPO_CADENCE_HOURS 경과했는지 (마커 파일 기반)."""
    if force:
        return True
    try:
        marker = _hippo_marker_path()
        if not marker.exists():
            return True
        from datetime import datetime, timedelta
        last = datetime.fromisoformat(marker.read_text(encoding="utf-8").strip())
        return datetime.now() - last >= timedelta(hours=HIPPO_CADENCE_HOURS)
    except Exception:
        return True


def _hippo_touch_marker():
    try:
        from datetime import datetime
        _hippo_marker_path().write_text(datetime.now().isoformat(), encoding="utf-8")
    except Exception:
        pass


def _consolidate_distilled_json(cap: int = HIPPO_JSON_CAP) -> dict:
    """ibl_distilled.json 정리: 완전중복(intent+code) 제거 + 최신 cap건만 유지.

    재학습 입력 파일이라 중복이 쌓이면 학습 편향이 된다. 최근 항목을 보존."""
    from pathlib import Path
    import json as _json
    path = Path(__file__).parent.parent / "data" / "training" / "ibl_distilled.json"
    if not path.exists():
        return {"json": 0}
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"json": 0, "error": "parse"}
    if not isinstance(data, list):
        return {"json": 0}

    # 최신 우선 dedup (뒤에서부터 보존), 그 후 최근 cap건
    seen, kept_rev = set(), []
    for e in reversed(data):
        k = (e.get("intent", ""), e.get("ibl_code", ""))
        if k in seen:
            continue
        seen.add(k)
        kept_rev.append(e)
    kept = list(reversed(kept_rev))[-cap:]

    removed = len(data) - len(kept)
    if removed > 0:
        try:
            path.write_text(_json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return {"json": len(kept), "json_removed": removed}


def run_hippocampus_consolidation(force: bool = False) -> dict:
    """해마 정리 패스 — 증류물 가지치기/중복제거/상한 + json 정리.

    self-check(면역 순찰)에 합류하되 24h 카덴스 게이트로 자기 페이싱.
    dirty하지 않으면 즉시 스킵(싸다)."""
    if not _hippo_is_due(force):
        return {"skipped": "cadence"}

    result = {}
    try:
        from ibl_usage_db import IBLUsageDB
        db = IBLUsageDB()
        result.update(db.consolidate_distilled(cap=HIPPO_DISTILLED_CAP))
    except Exception as e:
        print(f"[해마정리] DB 정리 실패 (무시): {e}")
        result["db_error"] = str(e)

    result.update(_consolidate_distilled_json())

    # 변경이 있었으면 연상 캐시 무효화
    if result.get("deleted_total") or result.get("json_removed"):
        try:
            IBLUsageRAG().clear_cache()
        except Exception:
            pass
        print(f"[해마정리] 증류물 가지치기 {result.get('pruned_bad',0)} / "
              f"중복제거 {result.get('deduped',0)} / 상한 {result.get('pruned_cap',0)} / "
              f"json정리 {result.get('json_removed',0)}")

    _hippo_touch_marker()
    return result
