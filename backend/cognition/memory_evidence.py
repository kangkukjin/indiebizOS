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
    """관계 기억 후보는 사용자 발화만. AI 결과는 에피소드/산출물에 이미 남는다."""
    units = []
    for part in re.split(r"\n\s*\n|(?<=[.?!。！？])\s+", user or ""):
        part = part.strip()
        if part:
            request = bool(re.search(r"[?？]|(?:해줘|해주세요|해\s*주세요|알려줘|봐줘|할까|있나|되나)[.!]?$", part))
            units.append({"id": len(units) + 1, "role": "user", "text": part,
                          "eligible": not request})
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
