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


_SENTENCE_SPLIT = r"(?<=[.?!。！？])\s+"


def durable_source_units(user):
    """발화의 위치·인용 표시를 보존한다. 주체와 지속성은 기존 증류기가 문맥에서 판단한다."""
    text = user or ""
    quoted_ranges, offset, fenced = [], 0, False
    for line in text.splitlines(keepends=True):
        fence = bool(re.match(r"\s*(?:```|~~~)", line))
        if fenced or fence or line.lstrip().startswith(">"):
            quoted_ranges.append((offset, offset + len(line)))
        if fence:
            fenced = not fenced
        offset += len(line)
    units, cursor = [], 0
    for paragraph in re.split(r"\n\s*\n", text):
        for part in re.split(_SENTENCE_SPLIT, paragraph):
            part = part.strip()
            if not part:
                continue
            start = text.index(part, cursor)
            end = cursor = start + len(part)
            quoted = any(a < end and start < b for a, b in quoted_ranges)
            units.append({"id": len(units) + 1, "role": "user", "text": part,
                          "attribution": "quoted" if quoted else "user_candidate",
                          "basis": "quoted_block" if quoted else "user_utterance" if any(c.isalnum() for c in part) else "punctuation_only",
                          "eligible": any(c.isalnum() for c in part),
                          "start": start, "end": end,
                          "sha256": hashlib.sha256(part.encode()).hexdigest()})
    return units


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
