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


# 주인에게 *말을 거는* 글의 경어 수신 표지 — 저자가 사람이든 AI 든 주인의 자기 진술이 아니다
# (2026-09-16 ep3813: 붙여 넣은 사이트 평가문의 문체가 owner[habit/lexicon] 으로 들어갔다).
_ADDRESSED_RE = re.compile(r"(말씀드리|드리겠습니다|드립니다|짚으신|말씀하신|님께|께서|십시오)")
_FORMAL_END_RE = re.compile(r"(습니다|입니다|니다)[.!?]?\s*$")
_SENTENCE_SPLIT = r"(?<=[.?!。！？])\s+"
_DOCUMENT_CHARS = 600


def _formal_ratio(text):
    sentences = [x for x in re.split(_SENTENCE_SPLIT, text or "") if x.strip()]
    if not sentences:
        return 0.0
    return sum(1 for x in sentences if _FORMAL_END_RE.search(x.strip())) / len(sentences)


def durable_source_units(user):
    """전달자는 저자가 아니다. 사용자가 *전달한* 내용과 사용자를 *설명하는* 근거를 가른다.

    보류(eligible=false)하는 것:
      - 명시 인용(> 인용줄·코드펜스) → attribution "quoted"
      - 주인에게 말을 거는 경어 수신문(말씀드리·짚으신·님께…) → "conveyed" — 저자가 사람이든 AI 든
        주인의 자기 진술이 아니다
      - 출처 미상의 긴 답변형 문서(답변 첫마디, 또는 600자 이상·구조(마크다운/3문단+)·합니다체 과반)
        → "unresolved" — 짧은 독립 채택 선언(`나는 이 제안을 …`)만 예외
      - 질문·요청 문장
    각 단위에 basis(왜 그렇게 봤나)를 남겨 저장된 기억이 나중에 철회 가능하게 한다. 문체·표현은
    전달문에서 곧바로 주인의 것으로 뽑지 않는다 — 주인이 자기 말로 다시 하거나 다른 발화에서
    되풀이될 때(owner_model 의 재확인 결정화) 귀속된다.
    """
    text = user or ""
    paragraphs = re.split(r"\n\s*\n", text)
    framed_document = bool(re.search(
        r"(?:이건|이것은|다음은|아래는|이 글은).{0,80}(?:답변|의견|보고서|쓴 글|한 말)", text))
    structured = ("**" in text or bool(re.search(r"(?m)^#{1,6}\s", text))
                  or len([p for p in paragraphs if p.strip()]) >= 3)
    answer_document = (len(text) >= _DOCUMENT_CHARS and bool(re.match(
        r"\s*(?:맞습니다|좋습니다|결론부터|동의합니다|먼저 결론|직접 보고|좋은 .{0,20}입니다)[.!]", text))
        and ("**" in text or re.search(r"(?m)^#{1,6}\s", text)))
    formal_document = (len(text) >= _DOCUMENT_CHARS and structured and _formal_ratio(text) >= 0.5)
    # 한 문단이라도 주인에게 경어로 말을 걸면 그 글 전체가 전달문이다 — 사람은 자기 자신에게
    # "말씀드리겠습니다" 라고 쓰지 않는다. 짧은 채택 선언 문단만 주인의 목소리로 남긴다.
    addressed_document = any(_ADDRESSED_RE.search(p) for p in paragraphs)
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
        addressed = bool(_ADDRESSED_RE.search(paragraph)) or (addressed_document and not adoption)
        if answer_document:
            doc_basis = "answer_document"
        elif formal_document:
            doc_basis = "formal_document"
        elif framed_document and not adoption:
            doc_basis = "framed_document"
        else:
            doc_basis = ""
        uncertain = bool(doc_basis)
        for part in re.split(_SENTENCE_SPLIT, paragraph):
            _append_durable_unit(units, part, quoted, uncertain, addressed,
                                 doc_basis if uncertain else "")
    return units


def _append_durable_unit(units, part, quoted, uncertain, addressed=False, doc_basis=""):
    part = part.strip()
    if part:
        request = bool(re.search(r"[?？]|(?:해줘|해주세요|해\s*주세요|알려줘|봐줘|할까|있나|되나)[.!]?$", part))
        if quoted:
            attribution, basis = "quoted", "quoted_block"
        elif addressed:
            attribution, basis = "conveyed", "addressed_to_owner"
        elif uncertain:
            attribution, basis = "unresolved", doc_basis or "document"
        else:
            attribution, basis = "user_candidate", ("request" if request else "user_statement")
        units.append({"id": len(units) + 1, "role": "user", "text": part,
                      "attribution": attribution, "basis": basis,
                      "eligible": attribution == "user_candidate" and not request})

# 지시 대상 관문(2026-09-17 기억 재고 감사) — 원문 문장 단위 저장의 그림자: 떼어 놓으면 무엇에 관한
# 말인지 알 수 없는 조각("그런데 나는 그 차이가 중요하다고 생각하는거지."). 판단(이 말이 혼자 서는가)은
# 추출 모델 몫이고, 기계는 셀 수 있는 것만 본다: ①첫 선택 단위가 앞 문장에 기대는 머리로 시작
# ②단위 하나만 골랐는데 그 안에 지시 관형사·대명사가 있다(가리키는 문장을 함께 고르지 않았다).
# '이'는 뺀다 — "이 사이트"처럼 대화 장소가 곧 대상인 직시가 많다.
_DEPENDENT_HEAD_RE = re.compile(
    r"^\s*(?:그런데|근데|그래서|그러니까|그러면|그럼|그렇지만|그러나|하지만|그리고|또한|다시 말해|즉|왜냐하면)(?![가-힣])")
_DEMONSTRATIVE_RE = re.compile(
    r"(?:^|\s)(?:그런|이런|저런|그것[은이을도]?|그건|그게|그걸|이것[은이을도]?|이건|이게|이걸|그)(?=\s)")


def unresolved_reference(selected):
    """선택된 원문 단위가 자기 밖의 문장에 기대면 사유 문자열, 혼자 서면 None."""
    if not selected:
        return None
    first = selected[0]["text"]
    if _DEPENDENT_HEAD_RE.search(first):
        return "dependent_head"
    if _DEMONSTRATIVE_RE.match(first) and first.lstrip().startswith(("그", "이", "저")):
        return "dependent_head"
    if len(selected) == 1 and _DEMONSTRATIVE_RE.search(first):
        return "lone_demonstrative"
    return None


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
