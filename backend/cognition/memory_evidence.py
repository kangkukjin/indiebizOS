"""Memory models select evidence; only the source owns stored factual wording."""
import hashlib
import json
import re


def source_units(user, response):
    units = []
    for role, text in (("user", user), ("assistant", response)):
        # Keep paragraph context (subject, denominator, qualifications) together.
        for paragraph in re.split(r"\n\s*\n", text or ""):
            if paragraph.strip():
                units.append({"id": len(units) + 1, "role": role,
                              "text": paragraph.strip()})
    return units


def select_units(ids, units):
    if (not isinstance(ids, list) or not ids
            or any(type(i) is not int or i < 1 or i > len(units) for i in ids)
            or ids != sorted(set(ids))):
        return []
    return [units[i - 1] for i in ids]


def durable_source_units(user):
    """전달자는 저자가 아니다. 명시 인용과 출처 미상 답변형 문서는 개인 사실 후보에서 뺀다.

    표지 없는 붙여넣기의 저자를 완벽히 판별하지는 못한다. 여기서는 명시적 인용과
    긴 답변형 문서를 보수적으로 보류하고, 나머지도 추출 모델이 저자를 확인한다.
    """
    text = user or ""
    paragraphs = re.split(r"\n\s*\n", text)
    framed_document = bool(re.search(
        r"(?:이건|이것은|다음은|아래는|이 글은).{0,80}(?:답변|의견|보고서|쓴 글|한 말)", text))
    answer_document = (len(text) >= 600 and bool(re.match(
        r"\s*(?:맞습니다|좋습니다|결론부터|동의합니다|좋은 .{0,20}입니다)[.!]", text))
        and ("**" in text or re.search(r"(?m)^#{1,6}\s", text)))
    units = []
    fenced = False
    for paragraph in paragraphs:
        quoted_lines = []
        for line in paragraph.splitlines():
            fence = bool(re.match(r"\s*(?:```|~~~)", line))
            quoted_lines.append(fenced or fence or line.lstrip().startswith(">"))
            if fence:
                fenced = not fenced
        quoted = any(quoted_lines)
        # 출처 표지 없는 문서의 저자를 사용자라고 확정하지 않는다. 짧은 독립 채택 선언은
        # 문서 밖 자기 발화로 남길 수 있지만, 인용문 속 '나는'에는 이 예외가 적용되지 않는다.
        adoption = (len(paragraph) < 250 and bool(re.match(
            r"\s*(?:나는|내가|앞으로(?:는)?|이 의견을|이 제안을)", paragraph)))
        uncertain = bool(answer_document or (framed_document and not adoption))
        for part in re.split(r"(?<=[.?!。！？])\s+", paragraph):
            _append_durable_unit(units, part, quoted, uncertain)
    return units


def _append_durable_unit(units, part, quoted, uncertain):
    part = part.strip()
    if part:
        request = bool(re.search(r"[?？]|(?:해줘|해주세요|해\s*주세요|알려줘|봐줘|할까|있나|되나)[.!]?$", part))
        units.append({"id": len(units) + 1, "role": "user", "text": part,
                      "attribution": "quoted" if quoted else "unresolved" if uncertain else "user_candidate",
                      "eligible": not (request or quoted or uncertain)})


def grounded_fact(fact, units, source_ref, *, durable_only=False):
    if not isinstance(fact, dict):
        return None
    selected = select_units(fact.get("source_ids"), units)
    if not selected:
        return None
    if durable_only and (fact.get("retention") not in {"user_fact", "user_preference", "user_decision"}
                         or not isinstance(fact.get("future_use"), str)
                         or not fact["future_use"].strip()
                         or any(u["role"] != "user" or not u.get("eligible", True) for u in selected)):
        return None
    category = str(fact.get("category") or "작업기록")
    if any(u["role"] == "assistant" for u in selected):
        category = "작업기록"  # An assistant's recommendation is not the user's decision.
    source = json.loads(source_ref)
    if durable_only:
        source["retention"] = fact["retention"]
    source["evidence"] = [{**u, "sha256": hashlib.sha256(u["text"].encode()).hexdigest()}
                          for u in selected]
    return {**fact, "category": category,
            "content": "\n\n".join(u["text"] for u in selected),
            "source_ref": json.dumps(source, ensure_ascii=False)}


def selected_content(ids, units):
    return "\n\n".join(u["text"] for u in select_units(ids, units))
