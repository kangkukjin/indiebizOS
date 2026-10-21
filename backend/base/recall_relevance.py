"""자동 소개의 글자 근거. 부분 문자열 하나로 후보 수를 채우지 않는다."""
import re
import unicodedata

from korean_utils import strip_particle


def _tokens(text):
    # 복합어의 모든 부분 문자열을 만들면 서로 다른 작업도 같은 말로 잡힌다.
    raw = re.findall(r"\w+", unicodedata.normalize("NFKC", text or "").casefold())
    return [word for word in raw if len(word) >= 2]


def terms(text):
    # '보고서'처럼 조사와 같은 글자로 끝나는 명사도 원형 일치로 찾는다.
    return {form for word in _tokens(text) for form in (word, strip_particle(word))}


def lexical_evidence(query, text):
    """단일 검색어는 한 어절, 문장은 연속 여섯 어절 안의 서로 다른 두 어절 이상 일치.

    긴 복합 요청도 해당 부분 작업으로 찾는다. 반복 단어·조사 변형은 한 근거로 센다.
    명시 검색의 재현율 정책과 별개인 자동 소개의 보수적 하한이다.
    조사만 정규화하며, 문장의 뜻을 이해했다고 간주하지 않는다.
    """
    wanted = _tokens(query)
    known = terms(text)
    hits = [strip_particle(word) if {word, strip_particle(word)} & known else None
            for word in wanted]
    required = min(2, len({strip_particle(word) for word in wanted}))
    if not wanted or not any(len({h for h in hits[i:i + 6] if h}) >= required
                             for i in range(len(hits))):
        return 0
    return sum(len(word) for word in set(hits) if word)
