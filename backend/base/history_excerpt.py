"""대화 원문을 훼손하지 않는, 길이가 제한된 읽기용 발췌.

주제 관련성·내용의 중요도는 판단하지 않는다. 보통 답변은 본문 그대로,
긴 답변은 도입 일부와 더 넓은 끝부분을 원문 그대로 남겨 결과 유실을 줄인다.
"""

HISTORY_TEXT_CHARS = 6000
# DB 발췌 + 체크포인트(최대 4000자) + 시각/안내를 다시 잘라내지 않을 여유.
CONSCIOUSNESS_HISTORY_CHARS = 2 * HISTORY_TEXT_CHARS


def history_excerpt(content: str, limit: int = HISTORY_TEXT_CHARS) -> str:
    """본문은 한도 이하면 그대로. 초과 시 앞 1/4·뒤 3/4, 생략량을 표시한다.

    이미 같은 한도로 발췌한 문자열은 재절단하지 않는다. 출력은 의미 요약이
    아니므로 생략한 중간 내용을 없었던 사실이나 완료의 증거로 해석하면 안 된다.
    """
    if limit < 128:
        raise ValueError("히스토리 발췌 한도는 128자 이상이어야 합니다")
    if len(content) <= limit:
        return content
    kept = limit - 100  # 원문 길이·생략량 표식의 공간도 한도에 포함한다.
    head = kept // 4
    tail = kept - head
    omitted = len(content) - kept
    marker = f"\n\n[중간 {omitted}자 생략 — 원문 {len(content)}자의 앞·뒤 발췌]\n\n"
    return content[:head] + marker + content[-tail:]
