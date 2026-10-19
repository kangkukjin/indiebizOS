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


def conversation_excerpt(history: list, limit: int = 16000) -> str:
    """발화자·순서와 짧은 중간 정정을 보존하는 예산 내 대화 발췌.

    긴 assistant 답 하나가 뒤의 사용자 정정을 밀어내지 않도록 메시지별로
    공간을 나눈다. 관련성 요약은 하지 않으며 생략은 명시한다.
    """
    if limit < 512:
        raise ValueError("대화 발췌 한도는 512자 이상이어야 합니다")
    rows = []
    for index, message in enumerate(history or [], 1):
        if not isinstance(message, dict):
            continue
        content = message.get("content", "")
        if isinstance(content, list):
            content = "\n".join(part.get("text", "") for part in content
                                if isinstance(part, dict) and isinstance(part.get("text"), str))
        if not isinstance(content, str) or not content:
            continue
        role = message.get("role")
        role = role if role in {"user", "assistant", "system", "tool"} else "unknown"
        rows.append((f"[{index} {role}]\n", content))
    if not rows:
        return ""
    maximum = max(1, (limit - 256) // 160)
    prefix = ""
    if len(rows) > maximum:
        omitted = len(rows) - maximum
        rows = [rows[0]] + rows[-(maximum - 1):] if maximum > 1 else rows[-1:]
        prefix = f"[중간 {omitted}개 메시지 생략 — 제공된 대화의 일부 발췌]\n\n"
    budget = limit - len(prefix) - sum(len(header) + 2 for header, _ in rows)
    sizes = [min(len(content), 128) for _, content in rows]
    remaining = budget - sum(sizes)
    while remaining > 0:
        growing = [i for i, (_, content) in enumerate(rows) if sizes[i] < len(content)]
        if not growing:
            break
        share = max(1, remaining // len(growing))
        for i in growing:
            added = min(share, remaining, len(rows[i][1]) - sizes[i])
            sizes[i] += added
            remaining -= added
    return prefix + "\n\n".join(header + history_excerpt(content, max(128, size))
                                for (header, content), size in zip(rows, sizes))
