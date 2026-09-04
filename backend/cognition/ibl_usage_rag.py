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


def _own_only(results: list) -> list:
    """몸 소유-필터(몸 독립, 2026-07-22): 내 몸이 실행 못 하는 어휘가 담긴 용례는
    회상하지 않는다 — 해마도 자기 사전만 배우고 떠올린다. 남의 능력은
    이웃 몸 명함(냄새) + [others:ask] 경로가 담당.
    ★모든 search_hybrid 호출 뒤에 적용할 것 — 참조 주입(get_references)뿐 아니라
    Reflex/증류 판정용 top-1(get_top_score·get_top·search_with_metadata)도
    남의 용례가 주도해선 안 된다(고점수 Reflex 는 top-1 코드를 그대로 실행)."""
    try:
        from ibl_registry import code_is_own
        return [r for r in results if code_is_own(r.ibl_code)]
    except Exception:
        return results


def _xml_attr(s: str) -> str:
    """XML 속성값 이스케이프 — `&`·`<` 를 **먼저**(엔티티 이중 이스케이프 방지) 그 다음 따옴표.

    ★2026-08-22: 옛 코드는 `"` 만(또는 `"`·`'` 만) 바꿔서 `&`·`<` 가 든 값이 들어오면
    블록 전체가 비적합 XML 이 됐다. 계기판(ManualMode.tsx)은 이 블록을 DOMParser 로
    진짜 파싱하므로, 비적합이면 예외가 아니라 **빈 목록**이 되어 '번역 근거' 패널이
    조용히 사라진다(침묵 실패).

    이 블록의 속성은 전부 **큰따옴표**라 `'` 는 이스케이프하지 않는다 — 모델이 읽는
    글이므로 불필요한 엔티티는 노이즈다(속성 인용부호를 바꾸려면 여기부터 고칠 것).
    """
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def _cdata(s: str) -> str:
    """CDATA 본문 — 안에서 유일한 금지 시퀀스 `]]>` 만 분할(표준 관용).

    코드를 엔티티로 escape 하지 않는 이유: 이 블록의 다른 소비자는 **모델**이고,
    모델은 본 대로 베낀다. `[A] & [B]` 가 `[A] &amp; [B]` 로 보이면 그대로 베껴
    파스 에러가 된다 — 코드는 원문이어야 한다.
    """
    return (s or "").replace("]]>", "]]]]><![CDATA[>")


class IBLUsageRAG:
    """IBL 용례 RAG 참조 시스템 (싱글톤)"""

    MAX_REFERENCES = 5
    DEFAULT_K = 5
    # 표시 임계값. 0.65 미만은 사례 매칭이 약해서 의식 에이전트에 노이즈로
    # 작용한다 (예: "라벨지 필요해" 쿼리에 clipboard/copy/write 사례가 0.68로
    # 매칭되어 잘못된 액션을 추천하는 사고). 증류 임계값(0.7)보다는 살짝
    # 낮춰서, 0.65~0.7 구간(증류 후보)은 ref로 보여 의식이 활용 가능하게.
    MIN_SCORE = 0.65
    # 저신뢰 바닥. MIN_SCORE 통과분이 하나도 없을 때만, 이 값 이상인 top-2를
    # '저신뢰 참고'로 넘긴다. 저사양 모델일수록 참조가 더 필요한데 정답 패턴이
    # 0.5대(애매 매칭) 구간에 몰려 MIN_SCORE에 잘리던 리콜 갭을 닫기 위함.
    # 0.45 미만은 무관 노이즈로 보고 넘기지 않는다.
    LOW_CONF_FLOOR = 0.45
    LOW_CONF_MAX = 2
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

        results = _own_only(results)
        if not results:
            self._set_cached(cache_key, "")
            return ""

        # 점수 게이트: 통과분(>=MIN_SCORE) 우선. 없으면 저신뢰 top-2(>=LOW_CONF_FLOOR).
        selected, low_conf = self._select_references(results)
        if not selected:
            self._set_cached(cache_key, "")
            return ""

        xml = self._format_references(selected, low_conf=low_conf)
        self._set_cached(cache_key, xml)
        return xml

    def _select_references(self, results: list) -> tuple:
        """참조로 보여줄 용례 선별.

        주 임계값(MIN_SCORE)을 넘는 게 있으면 그것만(고신뢰). 하나도 없으면
        LOW_CONF_FLOOR 이상인 상위 LOW_CONF_MAX건을 저신뢰 참고로 반환한다.
        Reflex/증류 판정은 호출 측이 top_score(results[0])로 따로 하므로 영향 없음 —
        여기는 '의식 에이전트에게 무엇을 보여줄지'만 결정한다.

        Returns:
            (selected: list, low_conf: bool)
        """
        if not results:
            return ([], False)
        filtered = [r for r in results if r.score >= self.MIN_SCORE]
        if filtered:
            return (filtered, False)
        low = [r for r in results if r.score >= self.LOW_CONF_FLOOR][:self.LOW_CONF_MAX]
        return (low, True)

    def _format_references(self, examples: list, low_conf: bool = False) -> str:
        """검색 결과를 프롬프트 주입용 XML로 포맷팅"""
        if low_conf:
            note = ("참고 용례(저신뢰: 정확히 일치하는 과거 사례가 없어 가장 가까운 후보만 보인다. "
                    "그대로 신뢰하지 말고 액션·파라미터를 직접 검증하라). "
                    "execute_ibl 도구로 실행하고, 텍스트 응답에 IBL 코드를 넣지 마라.")
        else:
            note = ("참고 용례. execute_ibl 도구로 실행하고, 텍스트 응답에 IBL 코드를 넣지 마라. "
                    "success_rate는 과거 실행 성공률(0~1)이니 낮으면 신중히 참고하라(없으면 미검증). "
                    "avg_ms는 과거 성공 실행의 평균 소요시간(ms), avg_tokens는 그 턴의 평균 모델 "
                    "토큰 소요 — 같은 목표를 같은 품질로 이룬다면 빠르고 싼 패턴이 좋다"
                    "(품질을 깎아 아끼는 것은 금물).")
        lines = [f'<ibl_references note="{_xml_attr(note)}">']
        for ex in examples:
            # ★코드는 속성이 아니라 CDATA 본문 — 속성에 넣으면 코드 안의 홑따옴표가
            # 속성을 그 자리에서 끊는다(실측: 코퍼스 3,539건 중 301건 8.5% 가
            # `'`·`&`·`<` 를 담고 있어 그 블록 전체가 비적합 XML 이었다).
            attrs = f'intent="{_xml_attr(ex.intent)}" score="{ex.score}"'
            # success_rate >= 0 이면 시도 이력 있음(0.0=전부 실패 포함) → 표시.
            # -1.0(미검증)은 표시하지 않아 노이즈를 줄인다. avg_ms 도 같은 규약(-1=미측정 숨김)
            # — 리랭킹이 아니라 표시로 AI가 판단한다(success_rate·last_seen 과 동일 철학).
            if ex.success_rate >= 0:
                attrs += f' success_rate="{ex.success_rate}"'
            if getattr(ex, "avg_ms", -1.0) >= 0:
                attrs += f' avg_ms="{int(ex.avg_ms)}"'
            if getattr(ex, "avg_tokens", -1.0) >= 0:
                attrs += f' avg_tokens="{int(ex.avg_tokens)}"'
            if getattr(ex, "topic", ""):
                attrs += f' topic="{_xml_attr(ex.topic)}"'
            lines.append(f'  <ref {attrs}><![CDATA[{_cdata(ex.ibl_code)}]]></ref>')
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

    # ★긴 붙여넣기 문서(에세이·기사·계약서 등)는 명령이 아니라 *내용*이다 — 본문 한가운데의
    #   표면 단어(예: 에세이 속 '도로교통법')가 무관 용례를 고신뢰(0.69)로 끌어온다(에피소드
    #   858/860 실측). 질의는 의도가 실리는 머리만 쓰고, 참조는 저신뢰로 강등하며,
    #   top_score 는 Reflex 임계(0.85) 아래로 눌러 표면 매칭 반사 실행을 차단한다.
    LONG_DOC_CHARS = 1200
    is_long_doc = len(user_message) > LONG_DOC_CHARS
    query = user_message[:400] if is_long_doc else user_message

    # 1) 해마 — 단일 검색으로 결과/최고 점수/최고 코드 모두 확보
    try:
        from ibl_usage_db import IBLUsageDB
        db = IBLUsageDB()
        results = db.search_hybrid(
            query=query,
            top_k=rag.DEFAULT_K,
            allowed_nodes=allowed_nodes,
        )
    except Exception as e:
        logger.error(f"[IBL RAG] 검색 실패: {e}")
        return ("", 0.0, "")

    # 소유-필터를 top_score 확정 전에 — 남의 용례가 Reflex/증류 판정을 주도하면 안 됨
    results = _own_only(results)
    top_score = results[0].score if results else 0.0
    top_code = results[0].ibl_code if results else ""
    if is_long_doc:
        top_score = min(top_score, 0.80)   # Reflex(≥0.85) 발동 금지 — 문서는 반사 대상이 아님

    # 점수 게이트 (get_references와 동일 정책): 통과분 없으면 저신뢰 top-2.
    # top_score는 위에서 results[0]로 이미 확정 — Reflex/증류 판정엔 영향 없음.
    selected, low_conf = rag._select_references(results)
    if is_long_doc and selected:
        # 문서 매칭은 표면 단어 우연일 가능성이 높다 — 저신뢰 라벨(직접 검증 지시)로 강등.
        selected, low_conf = selected[:rag.LOW_CONF_MAX], True

    sections = []
    refs_xml = rag._format_references(selected, low_conf=low_conf) if selected else ""
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
        from ibl_access import load_nodes_raw
        data = load_nodes_raw()
        action_config = (
            (data.get("nodes") or {}).get(node, {}).get("actions", {}).get(action, {})
        )
    except Exception:
        return ("", 0.0, "")

    if not action_config:
        return ("", 0.0, "")

    def _esc(s: str) -> str:
        return _xml_attr(s)   # `&`·`<` 도 — 실측 16건의 description 이 이 둘을 담고 있었다

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
            impl_escaped = _xml_attr(impl)   # 실측 8건의 implementation 이 `&`·`<` 를 담고 있었다
            lines.append(f'  <impl action="[{node}:{action}]" implementation="{impl_escaped}"/>')
    lines.append('</implementations>')

    if len(lines) <= 2:
        return ""

    return '\n'.join(lines)


def _lookup_implementation(node: str, action: str) -> str:
    """ibl_nodes.yaml에서 특정 액션의 implementation을 조회한다."""
    try:
        from ibl_access import load_nodes_raw
        nodes_data = load_nodes_raw()
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
        from ibl_access import load_nodes_raw
        nodes_data = load_nodes_raw() or {}
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
        results = _own_only(db.search_hybrid(query=user_message, top_k=1, allowed_nodes=allowed_nodes))
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
        results = _own_only(db.search_hybrid(query=user_message, top_k=1, allowed_nodes=allowed_nodes))
        if results:
            return (results[0].score, results[0].ibl_code)
        return (0.0, "")
    except Exception:
        return (0.0, "")


# 피드백 귀속 임계값: 이 점수 이상(Reflex 경로)에서만 top-1 example에 실행 결과 귀속.
# 연상은 example을 '참고'로 주입하고 AI가 새 코드를 생성하므로 귀속이 흐릿하지만,
# 고점수 경로는 top-1이 사실상 코드를 주도하므로 깔끔히 귀속된다.
RECALL_RECORD_THRESHOLD = 0.85


def _ibl_elapsed_ms(tool_calls: list) -> Optional[int]:
    """성공한 execute_ibl 호출들의 소요시간 합(ms). 측정된 호출이 없으면 None.

    agent_pipeline._collect 가 tool_start→tool_result 이음매에서 도장 찍은 elapsed_ms 를
    합산한다 — 시간 선택압의 귀속 축. 실패 호출의 시간은 섞지 않는다(그 표현의 빠르기가
    아니라 실패 양상의 시간이다). 다른 진입 경로(스레드 수집 등)의 호출은 elapsed_ms 가
    없을 수 있고, 그 경우 미측정(None)으로 정직하게 비운다."""
    total, measured = 0, False
    for tc in tool_calls or []:
        if not isinstance(tc, dict) or tc.get("tool_name") != "execute_ibl":
            continue
        if not tc.get("success", True):
            continue
        ms = tc.get("elapsed_ms")
        if isinstance(ms, (int, float)) and ms > 0:
            total += int(ms)
            measured = True
    return total if measured else None


def record_recall_outcome(top_code: str, top_score: float, tool_calls: list,
                          turn_tokens: int = None) -> bool:
    """Reflex 경로에서 연상 top-1 example의 실행 성공/실패(+소요시간·토큰)를 해마에 피드백한다.

    이것이 해마의 강화-감쇠 루프다. 기록된 성공/실패는 success_rate로 환산되어
    이후 연상 시 참조 XML에 표시되고(검증된 사례 부상), 정리 패스의 가지치기
    신호로도 쓸 수 있다. 성공 실행의 소요시간(avg_ms)과 턴 토큰 소요(avg_tokens)는
    EWMA 로 누적되어 같은 목표의 표현들 사이에 비용 축(시간·토큰 선택압)을 만든다 —
    시간=IBL 실행의 빠르기, 토큰=그 표현을 두른 턴의 모델 소요(불필요한 서치·재시도가
    여기 찍힌다). 둘은 다른 낭비를 잰다.

    Args:
        top_code: 연상 최고점 항목의 ibl_code (build_execution_memory 반환)
        top_score: 해마 최고 점수
        tool_calls: 도구 실행 이력 [{tool_name, input, success, elapsed_ms?}, ...]
        turn_tokens: 이 턴의 모델 토큰 소요 합(providers.base 턴 원장, None=미측정)
    Returns:
        기록 여부 (귀속 불가/저점수 시 False)
    """
    if not top_code or top_score < RECALL_RECORD_THRESHOLD:
        return False
    if not tool_calls:
        return False

    # execute_ibl 호출들의 성공 여부 집계 (하나라도 실패하면 실패로 귀속)
    ibl_success = None
    ibl_codes = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        if tc.get("tool_name") != "execute_ibl":
            continue
        s = bool(tc.get("success", True))
        ibl_success = s if ibl_success is None else (ibl_success and s)
        code = (tc.get("input") or {}).get("code", "")
        if code:
            ibl_codes.append(code)

    if ibl_success is None:
        return False  # IBL 실행이 없었으면 귀속 불가

    # ★귀속 관문(2026-09-02): 회상 top-1 의 액션이 실행에 실제로 등장했을 때만 귀속.
    #   증류 쪽(distill_experience)은 이미 이 관문을 썼는데 귀속 쪽만 없어서, 표면 어휘만
    #   닮은 고점수 회상이 전혀 안 쓰인 턴의 성공/실패까지 흡수했다 — 잘못된 강화·감쇠.
    if not _recall_was_used(top_code, ibl_codes):
        print(f"[해마피드백] 회상 미사용 — 귀속 스킵 (score={top_score:.2f}): {top_code[:50]}")
        return False

    elapsed_ms = _ibl_elapsed_ms(tool_calls) if ibl_success else None
    tokens = turn_tokens if (ibl_success and turn_tokens and turn_tokens > 0) else None

    try:
        from ibl_usage_db import IBLUsageDB
        db = IBLUsageDB()
        ok = db.update_success_by_code(top_code, ibl_success,
                                       elapsed_ms=elapsed_ms, tokens=tokens)
        if ok:
            _t = (f", {elapsed_ms}ms" if elapsed_ms else "") + \
                 (f", {tokens}tok" if tokens else "")
            print(f"[해마피드백] top-1 {'성공' if ibl_success else '실패'} 기록 "
                  f"(score={top_score:.2f}{_t}): {top_code[:50]}")
            # 성공률이 바뀌었으니 연상 캐시 무효화
            IBLUsageRAG().clear_cache()
        return ok
    except Exception as e:
        print(f"[해마피드백] 실패 (무시): {e}")
        return False


def _recall_was_used(top_code: str, ibl_calls: list) -> bool:
    """회상 top-1 의 [node:action]이 실행 궤적에 실제로 등장했는지 판정.

    고점수 회상이라도 실행이 그 액션을 전혀 안 썼다면 표면 어휘만 닮은 가짜
    유사도다(ep949: "자동화 조사" 질의에 [self:read] 회상 0.717 → 실행은 전부
    sense:freelance/search — 임계만 넘겨 학습이 통째로 스킵됨). 이 경우 경험은
    새 패턴이므로 증류를 막으면 안 된다. 판정은 node:action 쌍 교집합."""
    top_pairs = set(re.findall(r'\[([a-z_-]+):([a-z_-]+)\]', top_code or ""))
    if not top_pairs:
        return False
    for code in ibl_calls:
        if top_pairs & set(re.findall(r'\[([a-z_-]+):([a-z_-]+)\]', code or "")):
            return True
    return False


# ── 합성 접지 게이트 (2026-08-16) ─────────────────────────────────────────
# 프롬프트 규칙 3("데이터가 흐를 때만 합성")을 경량 반성기가 어기고, 모델이
# 매개한 별개 호출들을 >> 로 이어 붙인 실사례가 나왔다(구 용례 3805·3806 —
# 다섯 >> 전부 통화가 흐르지 않는 죽은 파이프였고, 3805 는 old_string 앵커를
# new_string 이 삼킨 edit 라 재생 시 규칙 원장을 파괴한다). 프롬프트는 권고일
# 뿐이므로 기계로 막는다: **증류는 실행된 문장을 압축할 뿐, 새 문장을 창작하지
# 않는다** — 증류 코드의 합성(>>·&·;·??)은 실행 이력의 *단일 호출* 안에 그
# 액션들이 함께 합성돼 있던 경우에만 통과한다(압축=부분집합 허용, 별개 호출
# 봉합=차단). 거짓 파이프는 조합성 지표(파이프 비율·문형 수)까지 오염시킨다.

_QUOTED_STR_RE = re.compile(r'"(?:\\.|[^"\\])*"' + r"|'(?:\\.|[^'\\])*'")
_COMPOSE_OP_RE = re.compile(r'>>|\?\?|&|;')
_NODE_ACTION_RE = re.compile(r'\[([a-z_-]+:[a-z_0-9]+)\]')


def _strip_strings(code: str) -> str:
    """따옴표 문자열을 비운다 — 파라미터에 실려 가는 문장([self:trigger] pipeline,
    [table:each] do 등) 속 연산자를 최상위 합성으로 오인하지 않기 위해."""
    return _QUOTED_STR_RE.sub('""', code or "")


def _composed(code: str) -> bool:
    """따옴표 밖에 합성 연산자(>>·&·;·??)가 있는가."""
    return bool(_COMPOSE_OP_RE.search(_strip_strings(code)))


def _actions_of(code: str) -> set:
    """따옴표 밖 [node:action] 집합."""
    return set(_NODE_ACTION_RE.findall(_strip_strings(code)))


def _heads_grounded(code: str, ibl_calls: list) -> bool:
    """증류 코드의 액션 머리 집합이 실행된 호출들의 머리 집합 안에 있는가.

    반성기는 실행 경험을 *일반화*하지 새 액션을 *발명*하지 않는다 — 실행에서 성공한
    적 없는 머리는 검증 안 된 패턴이라 코퍼스에 못 들어온다(합성 접지의 머리판,
    프롬프트 규칙 6 의 기계판). 액션 실존 검사(_validate_ibl_actions)와는 다른 질문이다:
    그건 '사전에 있나', 이건 '이 주행에서 실제로 돌았나'.
    """
    acts = _actions_of(code)
    if not acts:
        return False
    executed = set()
    for call in ibl_calls:
        executed |= _actions_of(call)
    return acts <= executed


_FLOW_OP_RE = re.compile(r'>>|\?\?|;')


def _composition_grounded(code: str, ibl_calls: list) -> bool:
    """증류 코드가 합성문이면 실행 이력에 접지됐는지 판정. 단문 증류는 무조건 통과.

    두 갈래(2026-09-04 개정, ep2817 실측 — 그 턴의 가장 좋은 문장(지표 7개 `&`)이 버려졌다):
      · **흐름 합성**(`>>`·`??`·`;`): 데이터가 흐른다는 주장이므로, 실행된 어느 *한* 호출이
        그 액션들을 합성문으로 담고 있었어야 한다(별개 호출 봉합 = 거짓 관용구, 종전 규칙 그대로).
      · **병렬만의 합성**(`&` 뿐): "동시에 돌릴 수 있다"는 주장이지 흐름이 아니다 — 가지마다
        그 액션이 이 주행의 실행(어느 호출이든)에 있었으면 참이다. 08-28~09-04 합성 접지 스킵
        28건 중 약 3분의 1이 이 부류였다(별개로 성공한 조회들을 `&` 로 묶은 것).
    """
    if not _composed(code):
        return True
    acts = _actions_of(code)
    if not acts:
        return False
    stripped = _strip_strings(code)
    if not _FLOW_OP_RE.search(stripped):
        executed = set()
        for call in ibl_calls:
            executed |= _actions_of(call)
        return acts <= executed
    return any(_composed(call) and acts <= _actions_of(call) for call in ibl_calls)


def _build_distill_prompt(user_message: str, tool_log: str, retry_block: str, topic_map: str) -> str:
    """반성기(경량 모델)에 주는 증류 프롬프트.

    ★JSON 스키마에 `[node:action]{params}` 같은 *형태 자리표*를 두지 않는다 (2026-09-04,
    ep2777·2806 실측): 경량 모델이 자리표를 글자 그대로 베껴 `[node:self:edit]{…}` 를 내거나,
    실행 코드의 `node: "가족/어머니"` 인자를 자리표의 node 자리에 대입해 `[가족/어머니:memory]`
    를 냈다. 09-03 부터 `node` 가 [self:memory] 의 인자 이름이 되면서 자리표의 낱말과 충돌한
    것이 뿌리 — 구문 관문이 막아 원장은 깨끗했지만 실사용 첫 recall 용례가 유실됐다.
    자리표 대신 '실행된 머리를 그대로'를 규칙으로 말하고, 시험이 이 문자열에 `[node:` 가
    없음을 고정한다(test_hippo_syntax_gate G5).
    """
    return f"""다음은 사용자 명령과 그에 대해 실행된 IBL 코드 목록이다.
이 경험에서 핵심 패턴을 추출하여 용례로 만들어라.

사용자 명령: {user_message}

실행된 IBL 코드:
{tool_log}{retry_block}

규칙:
1. 사용자 명령을 일반화하라 (고유명사는 유지하되, 패턴으로서 재사용 가능하게)
2. 실행된 코드에서 중복/탐색성 호출을 제거하고 핵심만 남겨라
3. 액션 합성(>> 또는 &)은 *데이터가 실제로 흐를 때만* 하라:
   - 한 액션의 출력이 다음 액션의 입력으로 흐르면(예: 조회 → 변환 → 차트) `>>`,
     한 동작으로 동시에 묶이면 `&`. 이때만 합성이 *참된 관용구*다.
   - ★실행된 코드 가운데 **합성문**(`&`·`>>` 가 든 문장)이 있으면 **그 문장을 대표로** 남겨라
     (그대로 또는 압축) — 실행에서 함께 돌았던 문장이 가장 참된 관용구다. 단일 액션으로
     줄이지 마라(2026-09-04: 대표를 단일 액션으로 접던 규칙이 코퍼스를 1액션 문장 80% 로 굳혔다).
   - 별개로 하나씩 호출한 단계를 `>>` 로 봉합하지 마라 — `>>` 는 데이터 흐름을 뜻하므로
     흐르지 않는 단계를 이으면 *거짓 관용구*다. `&` 로 묶는 것은 각 가지가 이 주행에서
     실제로 성공했을 때만. 합성문이 하나도 없었으면 가장 핵심(load-bearing)인 단일 액션
     하나로 대표하라.
   - ★단, 남은 후보가 *꼬리*뿐이면 대표를 세우지 마라 — 등기·알림·저장·검증처럼 일이
     끝난 뒤 딸려 붙는 부산물, 실패한 탐색, 준비 단계가 그렇다. 실작업이 IBL 밖
     (셸·파일 편집·긴 추론)에서 이뤄진 주행이 이 모양이 된다. 이때는 규칙 4 로 간다.
4. **대표 코드를 확정하기 전에 시험하라**: 「이 code 만 실행하면 사용자의 intent 가
   충족되는가?」 — 아니면(더 큰 일의 한 조각·부산물일 뿐이면) 억지로 대표 코드를
   지어내지 말고 code 를 빈 문자열("")로 두어 증류를 건너뛰게 하라.
   ★카테고리로 판정하지 마라('순수 분석이냐 빌드냐' 따위) — 카테고리는 예상한 경우만
   덮고 예상 못 한 모양을 조용히 통과시킨다. 시험은 언제나 위 한 문장이다.
   통과 못 하면 스킵이 옳다 — 없는 용례보다 *틀린* 용례가 해롭다(단발 오시드가 반사로
   굳으면 다음번 같은 요청을 그 한 줄로 끝내 버린다).
5. **topic(주제 가지)** 을 적어라 — 아래 실행기억 지도에서 이 용례가 속할 가지를 고른다. 기존 가지 우선,
   정말 새 주제면 새 경로(`상위/하위`, 최대 2단, 한국어 명사). 한두 건짜리 가지는 만들지 마라.
[실행기억 지도]
{topic_map or "(아직 가지 없음)"}
6. **code 의 대괄호 머리는 실행된 코드의 머리를 글자 그대로 옮겨라** — 머리를 새로 짓거나,
   인자 값(node·path 따위)을 머리 안에 넣지 마라. 머리가 실행에 없던 것이면 그 용례는 버려진다.
7. 결과는 반드시 JSON으로만 응답:

{{"intent": "일반화된 사용자 의도", "code": "IBL 코드 원문 (재사용 패턴 없으면 빈 문자열)", "topic": "가지/경로"}}"""


def distill_experience(user_message: str, tool_calls: list, top_score: float,
                       top_code: str = None, turn_tokens: int = None) -> bool:
    """실행 경험을 증류하여 해마에 저장한다.

    조건: 도구 호출이 있었고, 해마 점수가 DISTILL_THRESHOLD 미만일 때 — 단
    점수가 임계 이상이어도 회상 top-1 액션이 실행에 실제 사용되지 않았으면
    (top_code 전달 경로 한정) 가짜 유사도로 보고 증류를 진행한다.
    top_code 미전달 경로(조종실 /ibl/distill 등)는 기존 점수 게이트 그대로.
    무의식 에이전트와 같은 경량 AI로 경험을 반성하여 일반화된 용례로 변환한다.

    Args:
        user_message: 사용자 원본 메시지
        tool_calls: 도구 실행 이력 [{tool_name, input, success}, ...]
        top_score: 해마 최고 점수 (build_execution_memory 시점)
        top_code: 해마 최고 점수 항목의 ibl_code (회상 사용 여부 판정용, 선택)

    Returns:
        증류 성공 여부
    """
    # 목표 평가 게이트: 평가가 NOT_ACHIEVED로 끝난 실행(=목표 미달성)은 학습하지 않는다.
    # 실패한 실행의 IBL 패턴이 해마에 누적되면 시간이 갈수록 추천 품질을 깎는다(복리 출혈).
    # 판정은 메시지당 1회만 소비 — 읽고 즉시 비워 평가 없는 다음 메시지로 새지 않게 한다.
    from thread_context import get_goal_eval_outcome, clear_goal_eval_outcome
    _ge = get_goal_eval_outcome()
    clear_goal_eval_outcome()
    if _ge is not None and not _ge.get("achieved", True):
        print(f"[경험증류] 목표 미달성(severity={_ge.get('severity')}) — 증류 스킵: \"{user_message[:40]}\"")
        return False

    # 해마 비활성(폰 기본)이면 증류도 건너뜀 — 안 그러면 top_score=0.0 이 매 명령마다 증류
    # LLM 호출을 켜서 오히려 더 느려진다(해마 끄기의 목적 무력화). search 와 한 쌍으로 게이트.
    from ibl_usage_db import IBLUsageDB
    if IBLUsageDB.hippo_disabled():
        return False

    if not tool_calls:
        return False

    # 성공한 IBL 호출만 필터 (점수 게이트의 회상 사용 판정도 이 목록을 씀)
    # ★품질 계약(criteria)과의 접속: 미달(fail) 호출은 봉투 success:false 라
    #   이 필터가 이미 거른다(agent_pipeline 이 is_error_result 로 재판정).
    #   재시도-통과(pass_after_retry)는 성공이지만 *첫 지시가 약했다* 는 사실 —
    #   그대로 증류하면 약한 지시가 코퍼스에 들어가므로, 반성 프롬프트에 미달
    #   사유를 먹여 개선된 지시로 일반화하게 한다(품질 계약 셋째 신호,
    #   docs/IBL_QUALITY_CONTRACT_HANDOFF.md §6).
    ibl_calls = []
    retry_notes = []
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
            if tc.get("quality") == "pass_after_retry":
                fb = tc.get("quality_feedback")
                retry_notes.append(f"  - {code[:200]}" + (f" — 첫 미달 사유: {fb}" if fb else ""))

    if not ibl_calls:
        return False

    # 점수 게이트: 임계 이상이면 원칙적으로 "이미 아는 패턴"이라 스킵. 단 그 판정은
    # 회상이 실행에 실제 사용됐을 때만 신뢰한다 — 무관한 회상이 점수만 높은 경우
    # (표면 어휘 유사)는 새 패턴이므로 증류를 진행한다. top_code 없는 경로(조종실)는
    # 사용 여부를 알 수 없으므로 기존 점수 게이트 유지.
    if (top_score or 0.0) >= DISTILL_THRESHOLD:
        if not top_code or _recall_was_used(top_code, ibl_calls):
            return False
        print(f"[경험증류] 고점수 회상(top={top_score:.2f})이 실행에 미사용 — 새 패턴으로 증류 진행")

    # 증류: 실행 에이전트와 같은 모델로 반성
    try:
        tool_log = "\n".join(f"  {i+1}. {code}" for i, code in enumerate(ibl_calls))
        retry_block = ""
        if retry_notes:
            retry_block = ("\n\n다음 코드는 첫 실행이 criteria 기준 미달로 판정돼 "
                           "재시도 후에야 통과했다:\n" + "\n".join(retry_notes) +
                           "\n→ 용례를 만들 때 instruction 을 미달 사유가 재발하지 않게 "
                           "다듬어라 — 재시도 비용을 물지 않는 지시가 좋은 용례다. "
                           "criteria 파라미터 자체는 보존하라(품질 계약).")

        try:
            import hippo_tree
            _topic_map = hippo_tree.map_text()
        except Exception:
            _topic_map = ""
        prompt = _build_distill_prompt(user_message, tool_log, retry_block, _topic_map)

        # 반성 에이전트 프롬프트 로드
        from pathlib import Path
        _prompt_path = Path(__file__).parent.parent.parent / "data" / "common_prompts" / "reflection_prompt.md"
        system_prompt = _prompt_path.read_text(encoding="utf-8").strip() if _prompt_path.exists() else ""

        # 반성 에이전트: 무의식 에이전트와 같은 경량 AI 사용 (도구 없음, 단순 텍스트)
        from consciousness_agent import oneshot_ai_call
        result = oneshot_ai_call(prompt=prompt, system_prompt=system_prompt, role="background")

        if not result:
            return False

        # JSON 파싱 — 첫 JSON 값만 안전 추출(뒤에 잡담·중복 JSON 이 붙어도 살림.
        # 옛 find/rfind 방식은 '{...}잡담' 을 통째로 loads 해 Extra data 로 전체 유실 — ep855).
        from runtime_utils import parse_first_json
        distilled = parse_first_json(result)
        if not isinstance(distilled, dict):
            print(f"[경험증류] JSON 추출 실패: {result.strip()[:100]}")
            return False
        intent = distilled.get("intent", "").strip()
        code = distilled.get("code", "").strip()
        _topic = str(distilled.get("topic", "") or "").strip()

        # 주행 기록 (2026-09-04, 사용자 판정): 대표 문장이 있든 없든, 이 주행에서 성공한 문장들을
        # 주제 가지 문서의 `## 주행` 절에 실행 순서대로 남긴다 — 프로그램급 주행이 '재사용 패턴 없음'
        # 으로 학습 0건이 되던 자리. 코퍼스(유사도)와 별개로 지도→가지 회상이 읽는 자리다.
        if _topic and len(ibl_calls) >= 2:
            try:
                import hippo_tree
                _run = hippo_tree.note_run(_topic, intent or user_message[:80], ibl_calls, ok=True)
                if _run.get("success"):
                    print(f"[경험증류] 주행 기록 → 가지 '{_topic}' ({_run['sentences']}문장"
                          + (", 절단" if _run.get("truncated") else "") + ")")
            except Exception as _e:
                print(f"[경험증류] 주행 기록 실패: {_e}")

        if not intent or not code:
            # code 빈 문자열 = 반성기가 "재사용 IBL 패턴 없음"으로 판단한 의도적 스킵
            # (분석·판단 등). 거짓 >> 관용구를 박제하느니 증류 안 함.
            if intent and not code:
                print(f"[경험증류] 재사용 IBL 패턴 없음 — 증류 스킵: \"{user_message[:40]}\"")
            return False

        # 구문 관문 (2026-09-02): 포장을 벗기고, 그래도 IBL 로 파싱 안 되면 적재하지 않는다.
        # ★이 관문이 없어서 반성기가 JSON 을 이중으로 감싼 출력이 그대로 code 칸에 박혔고
        #   (실측 id 4374), 아래 게이트들은 전부 정규식 수준이라 그걸 통과시켰다 —
        #   그 행 하나가 pre-commit 코퍼스 검사를 막아 저장소 전체의 커밋을 세웠다.
        #   순서가 중요하다: 아래 인자 게이트(check_code_params)는 파싱 실패를 [] 로
        #   돌려주므로, 구문은 반드시 그보다 먼저 묻는다.
        from ibl_param_vocab import normalize_corpus_code, code_syntax_error
        code = normalize_corpus_code(code)
        _syntax_err = code_syntax_error(code)
        if _syntax_err:
            print(f"[경험증류] 파싱 불가 — 증류 스킵: {_syntax_err} / {code[:80]}")
            return False

        # 머리 접지 게이트 (2026-09-04): 실행에 없던 액션 머리는 코퍼스에 못 들어온다.
        if not _heads_grounded(code, ibl_calls):
            print(f"[경험증류] 머리 접지 실패(실행에 없던 액션) — 증류 스킵: {code[:80]}")
            return False

        # 합성 접지 게이트: 실행에 없던 >>·&·; 합성(거짓 관용구)은 코퍼스에 못 들어온다.
        # 규칙 3 의 기계판 — 반성기가 별개 호출들을 파이프로 봉합한 경우 여기서 잡힌다.
        if not _composition_grounded(code, ibl_calls):
            print(f"[경험증류] 합성 접지 실패(실행에 없던 합성) — 증류 스킵: {code[:80]}")
            return False

        # 배관 키 스크럽 (2026-08-16): `_raw`(파이프 중간 압축 억제)는 workflow_engine 이
        # 주입하는 내부 배관이지 어휘가 아니다 — 파이프 안 실행이 증류될 때 코드에 박혀
        # 코퍼스를 오염시킨 실측(빌드의 코퍼스-param 가드가 검출). 언어 표면에 없는 키는
        # 여기서 벗긴다.
        code = re.sub(r',\s*_raw:\s*(?:true|false)', '', code)
        code = re.sub(r'\{\s*_raw:\s*(?:true|false)\s*,\s*', '{', code)
        code = re.sub(r'\{\s*_raw:\s*(?:true|false)\s*\}', '{}', code)

        # 검증 게이트: 환각된(미존재) 액션이 코퍼스에 진입하지 못하도록 정적 검증
        if not _validate_ibl_actions(code):
            return False

        # 인자 게이트 (2026-07-03): 핸들러가 읽지 않는 키가 박힌 코드는 증류하지 않는다.
        # 침묵 인자 드리프트가 "성공"으로 위장한 채 코퍼스(몸)에 들어가면 Reflex 가
        # 틀린 인자명을 영구 재생산한다 — 경고(실행 층)의 짝인 쓰기 층 위생 장치.
        try:
            from ibl_param_vocab import check_code_params
            _param_issues = check_code_params(code)
            if _param_issues:
                print(f"[경험증류] 미인식 파라미터 — 증류 스킵: "
                      f"{[(i['action'], i['unknown']) for i in _param_issues]}")
                return False
        except Exception:
            pass  # 검사기 문제로 증류 자체를 막지는 않는다

        # 노드 추출
        node_pattern = re.compile(r'\[([a-z_-]+):')
        nodes = ",".join(sorted(set(node_pattern.findall(code))))

        # 파이프라인 여부
        category = "pipeline" if (">>" in code or "&" in code) else "single"

        # 해마에 저장 (임베딩도 즉시 생성). avg_ms/avg_tokens=출생 실측 — 이 용례가 압축한
        # 원 실행의 소요시간 합·그 턴의 모델 토큰 소요를 첫 관측으로 심는다(없으면 -1,
        # 이후 Reflex 귀속이 채움). 근접중복 정리에서 싸고 빠른 표현이 살아남는
        # 시간·토큰 선택압의 시작점.
        from ibl_usage_db import IBLUsageDB
        db = IBLUsageDB()
        _birth_ms = _ibl_elapsed_ms(tool_calls)
        example_id = db.add_example(
            intent=intent,
            ibl_code=code,
            nodes=nodes,
            category=category,
            difficulty=1,
            source="distilled",
            tags="auto",
            avg_ms=float(_birth_ms) if _birth_ms else -1.0,
            avg_tokens=float(turn_tokens) if (turn_tokens and turn_tokens > 0) else -1.0,
            topic=_topic,
        )

        # 원장의 판정을 존중한다 (2026-09-02): add_example 은 입구 게이트에 걸리면 0 을
        # 돌려준다. 예전엔 그 반환값을 안 보고 학습 파일에는 그대로 append 해서, DB 가
        # 거부한 코드가 ibl_distilled.json 에만 남아 두 원장이 어긋났다 — 빌드의 코퍼스
        # 검사는 파일 쪽도 읽으므로 거부당한 코드가 계속 커밋을 막는다.
        if not example_id:
            print(f"[경험증류] 원장이 거부 — 학습 파일에도 적재하지 않음: {code[:60]}")
            return False

        # 학습용 JSON 파일에 누적 (재학습 시 기존 데이터와 합쳐서 사용)
        from pathlib import Path
        import json as _json
        distilled_path = Path(__file__).parent.parent.parent / "data" / "training" / "ibl_distilled.json"
        try:
            existing = _json.loads(distilled_path.read_text(encoding="utf-8")) if distilled_path.exists() else []
            existing.append({"intent": intent, "ibl_code": code})
            distilled_path.write_text(_json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            # 두 원장 어긋남의 형제 — DB 엔 들어갔는데 학습 파일에 못 남았으면 침묵이 아니라 소리.
            print(f"[경험증류] 학습 파일 적재 실패(DB id={example_id}) — 재학습 원장 어긋남: {e}")

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
    return Path(__file__).parent.parent.parent / "data" / "training" / ".hippocampus_consolidated"


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
    path = Path(__file__).parent.parent.parent / "data" / "training" / "ibl_distilled.json"
    if not path.exists():
        return {"json": 0}
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"json": 0, "error": "parse"}
    if not isinstance(data, list):
        return {"json": 0}

    n_before = len(data)

    # ── 어휘·문법 재검증 (자동 staleness GC) ─────────────────────────────
    # 증류물은 *증류 시점*에만 _validate_ibl_actions 를 거친다. 이후 어휘(액션 이름)나 문법이
    # 바뀌면 옛 항목이 깨진 채 남아 재학습 시드를 오염시킨다. 지금까진 어휘 변경 시 마이그레이션
    # 스크립트를 손으로 돌려 막아왔으나(빠뜨리면 조용히 새는 구조), 정리 카덴스마다 ①현재
    # ibl_nodes.yaml 에 액션이 실재하고 ②현재 문법으로 파싱되는 항목만 남겨 자동화한다. AST·파서
    # 라 LLM 0. ★시간이 아니라 *현재 유효성*이 축 — 오래돼도 유효하면 보존, 최근이라도 깨지면 폐기.
    # ★fail-safe: _validate_ibl_actions 는 레지스트리 로드 실패 시 True(보수 통과)라 전수 폐기 안 됨.
    def _still_valid(e):
        code = e.get("ibl_code", "") or ""
        if not code or not _validate_ibl_actions(code):
            return False
        try:
            from ibl_parser import parse as _ibl_parse
            _ibl_parse(code)
        except Exception:
            return False
        return True

    data = [e for e in data if _still_valid(e)]
    stale_removed = n_before - len(data)
    if stale_removed:
        print(f"[해마정리] 어휘·문법 미부합 증류물 {stale_removed}건 폐기 (현재 어휘/문법 기준)")

    # 최신 우선 dedup (뒤에서부터 보존), 그 후 최근 cap건
    seen, kept_rev = set(), []
    for e in reversed(data):
        k = (e.get("intent", ""), e.get("ibl_code", ""))
        if k in seen:
            continue
        seen.add(k)
        kept_rev.append(e)
    kept = list(reversed(kept_rev))[-cap:]

    removed = n_before - len(kept)
    if removed > 0:
        try:
            path.write_text(_json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return {"json": len(kept), "json_removed": removed, "json_stale_removed": stale_removed}


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
