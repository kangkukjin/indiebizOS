"""oneshot_facade.py — 원샷 낱말(ai-ops)의 공용 관문.

원샷 AI 호출을 IBL 파이프 시민으로 승격한 세 낱말(입구 [self:struct] · 중간 [table:ai] ·
출구 [table:brief])이 공유하는 층. 정본 설계 = docs/ONESHOT_VOCAB_DESIGN.md.

원칙:
  · 모델 = 기어 **실행 축**(role="execution") — 하드코딩 금지, model_resolver 가 단독 결정
    (2026-08-19 사용자 판정: 원샷 낱말은 실행 에이전트와 같은 모델을 탄다. 경량 self:ask 와
    별개 — Reflex=경량의 근거가 "새 사고 없음"이었듯, 이 낱말은 새 의미 판단이라 실행 축).
  · 낱말의 자격 = AI 호출이 아니라 그 뒤의 **결정론 검증 관문**(설계 §5):
    스키마 파싱 + 실패 되먹임 재시도 1회 + 재실패=정직 실패(빈 결과 위장 금지),
    grounded 원문 대조(notebook 인용 후검증 부류), _ai provenance.
  · 이미지 입력은 이 파사드가 아니라 비전 패스스루(ingest_engine._gemini_vision_json) —
    모달리티는 기어 무관(model_gear _doc 원칙, 2026-08-13 경량 비전 부재 실측).
"""
import re

_WS = re.compile(r"\s+")


def execution_oneshot(prompt: str, system_prompt: str = None, images: list = None,
                      role: str = "execution"):
    """기어 실행 축 원샷 — oneshot 버킷(세션 비활성·thinking 차단)로 획득된다.

    role 기본값은 실행 축(ai-ops 세 낱말의 판정) — 다른 축의 기존 LLM 원자가 이 관문의
    검증(재시도 1회+정직 실패)만 빌릴 때는 자기 축을 명시해 넘긴다(축 변경은 판정감이라
    관문 이관이 기어를 조용히 바꾸면 안 된다 — 2026-08-20 F14-4, table:structure 이관).
    """
    from consciousness_agent import oneshot_ai_call
    return oneshot_ai_call(prompt, system_prompt=system_prompt,
                           images=images, role=role)


def _strip_json(raw):
    """모델 출력 → JSON 파싱 (코드펜스·잡말 관용) — ingest_engine 정본 재사용."""
    from ingest_engine import _strip_json as _s
    return _s(raw)


def oneshot_json(prompt: str, system_prompt: str, role: str = "execution"):
    """원샷 → JSON. 파싱 실패 시 오류를 되먹여 1회 재생성, 재실패=(None, err) 정직.

    반환 (parsed, err) — parsed 는 dict/list, err 는 사람이 읽는 실패 사유.
    role 은 execution_oneshot 참조(기본 실행 축, 기존 원자 이관 시 자기 축 명시).
    """
    raw = execution_oneshot(prompt, system_prompt=system_prompt, role=role)
    if raw:
        parsed = _strip_json(raw)
        if parsed is not None:
            return parsed, None
    err0 = ("모델 응답 없음(모델 미설정 가능)" if not raw
            else f"모델 출력을 JSON으로 못 읽음: {str(raw)[:200]}")
    retry = (f"{prompt}\n\n[재시도] 직전 출력이 실패했다({err0[:120]}). "
             "코드펜스·설명 없이 유효한 JSON만 다시 출력하라.")
    raw2 = execution_oneshot(retry, system_prompt=system_prompt, role=role)
    if raw2:
        parsed = _strip_json(raw2)
        if parsed is not None:
            return parsed, None
    return None, err0


def records_gate(parsed):
    """JSON → 레코드 리스트 정규화. {items|records: [...]} 봉투 승격, 단건 dict=[dict].

    반환 (records, err) — records 는 dict 만 남긴 리스트.
    """
    if isinstance(parsed, dict):
        inner = parsed.get("items")
        if not isinstance(inner, list):
            inner = parsed.get("records")
        parsed = inner if isinstance(inner, list) else [parsed]
    if not isinstance(parsed, list):
        return None, f"JSON 배열이 아님: {type(parsed).__name__}"
    return [r for r in parsed if isinstance(r, dict)], None


def _norm(s) -> str:
    return _WS.sub("", str(s or ""))


def grounded_filter(records: list, source_text: str, quote_field: str = "_quote"):
    """근거 고정 결정론 대조 — 원문 발췌(_quote)가 원문에 실존하는 레코드만 통과.

    공백 정규화 비교(줄바꿈·띄어쓰기 차이 무시). 반환 (kept, dropped_count) —
    탈락 수는 호출부가 결과에 신고한다(조용한 깎기 금지, silent-clamp 부류).
    """
    src = _norm(source_text)
    kept, dropped = [], 0
    for r in records:
        q = _norm(r.get(quote_field))
        if q and q in src:
            kept.append(r)
        else:
            dropped += 1
    return kept, dropped


def mark_ai(records: list) -> list:
    """AI 산출 provenance — 하류·증류·감사가 출처를 안다."""
    for r in records:
        if isinstance(r, dict):
            r["_ai"] = True
    return records
