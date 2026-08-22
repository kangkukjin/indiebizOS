"""ai-ops — 원샷 낱말: 통화 대수 세 자리의 AI 원자.

정본 설계 = docs/ONESHOT_VOCAB_DESIGN.md. 세 낱말이 파이프의 머리·몸통·꼬리에
의미론적 이음매를 놓는다(앱 개발 관행 — 결정론 배관 + 이음매의 원샷 — 의 어휘화):

  입구  [self:struct]{file|text, schema}  비정형 → items 구조화     (returns: items)
  중간  [table:ai]{instruction}           items → items 의미 변환   (returns: transform)
  출구  [table:brief]{instruction}        items → 산문 종합         (returns: scalar)

원칙(전 낱말 공통 — oneshot_facade 가 집행):
  · 모델 = 기어 실행 축(role="execution"). 이미지 = 비전 패스스루(ingest_engine).
  · 검증 관문 = JSON 파싱+재시도 1회+정직 실패 / 행 수 신고(rows_in/out) /
    grounded 원문 대조 / _ai provenance.
  · 비용 통제 = 집합 단위 호출(items 전체 한 번, 편집장 curate 선례).
    입력 상한 초과=정직 거절(take/filter 안내). 0행=AI 호출 생략(비용 0).
  · ★파라미터 이름: 지시문 자리는 `instruction`(table:structure 선례) — `do` 는
    IBL *문장*을 나르는 자리(M1 통일)라 자연어 지시에 쓰면 개념이 흐려진다.

모듈레벨 = stdlib 만(폰 import-safe 불변식, data-ops 선례) — 무거운 것은 함수 안 지연 import.
"""
import json

_ITEMS_CAP = 60_000       # items 직렬화 상한(자) — ingest_engine._TEXT_CAP 과 동률
# grounded 기본 on 스키마 = 원장 적재 부류(2026-08-19 판정 4: 환각 레코드의 원장 오염이
# 가장 비싼 침묵 실패). finance/health 는 이 몸의 원장 어휘 이름(몸의 명사=코드 — 헌법 정합).
_GROUNDED_DEFAULT_SCHEMAS = {"finance", "health", "재무", "건강"}


def _fail(msg: str, **extra) -> str:
    d = {"success": False, "error": msg}
    d.update(extra)
    return json.dumps(d, ensure_ascii=False)


def _ok(d: dict) -> str:
    d.setdefault("success", True)
    return json.dumps(d, ensure_ascii=False)


def _parse_prev(prev):
    """_prev_result(JSON 문자열 또는 dict/list) → 파이썬 객체 (data-ops 동형)."""
    if prev is None:
        return None
    if isinstance(prev, (dict, list)):
        return prev
    if isinstance(prev, str):
        try:
            return json.loads(prev)
        except Exception:
            return prev          # JSON 아니면 평문 그대로(struct 의 본문 입력이 될 수 있다)
    return None


try:
    from common.currency import coerce_items_payload as _coerce_items
except ImportError:      # 백엔드 공용 모듈이 없는 환경(패키지 단독 시험) — 옛 동작 유지
    def _coerce_items(v):
        return v if isinstance(v, list) else None


def _prev_items(tool_input):
    """파이프(_prev_result) 또는 직접 param(items)에서 items 통화 추출.

    반환 (items|None, prev_obj) — items 가 None 이면 통화가 아님(prev_obj 로 사유 판단).
    """
    prev = _parse_prev(tool_input.get("_prev_result"))
    if isinstance(prev, dict) and isinstance(prev.get("items"), list):
        return prev["items"], prev
    if isinstance(prev, list):
        return prev, prev
    if tool_input.get("items") is not None:
        # ★B19-2 (2026-08-22 상상훈련 19회차): `items: "$r.items"` 는 변수 치환이 통화를
        # JSON 문자열로 넣는다 — list 만 받던 옛 코드는 어휘가 약속한 입력을 거절했다.
        # 정본 = common.currency.coerce_items_payload (each·reduce·data-ops 와 같은 눈).
        rows = _coerce_items(tool_input["items"])
        if rows is not None:
            return rows, None
    return None, prev


def _items_payload(items):
    """items 직렬화 + 상한 검사 → (payload, err)."""
    payload = json.dumps(items, ensure_ascii=False)
    if len(payload) > _ITEMS_CAP:
        return None, (f"입력이 너무 큽니다({len(payload):,}자 > {_ITEMS_CAP:,}) — "
                      "앞에 [table:take]/[table:filter] 로 줄이거나 [table:each] 로 나누세요 "
                      "(병렬 & 결과면 [table:union]/[table:merge] 가 먼저 — take 는 병렬 봉투를 직접 받지 않는다).")
    return payload, None


def execute(tool_input: dict, context) -> str:
    name = getattr(context, "tool_name", None)
    if name == "ai_struct":
        return _struct(tool_input or {})
    if name == "ai_transform":
        return _transform(tool_input or {})
    if name == "ai_brief":
        return _brief(tool_input or {})
    return _fail(f"ai-ops: 알 수 없는 도구 '{name}'.")


# ───────────────────────── 입구: [self:struct] ─────────────────────────

def _struct(tool_input: dict) -> str:
    schema = str(tool_input.get("schema") or "").strip()
    if not schema:
        return _fail('schema(출력 레코드 계약)가 필요합니다 — 자유 라벨(예 "finance") '
                     '또는 필드 명세 텍스트(예 "date, item, amount(원)").')

    file_path = str(tool_input.get("file") or "").strip()
    text = str(tool_input.get("text") or "").strip()

    # 입력 획득: file/text 우선, 없으면 >> 파이프 본문(예: [sense:crawl] 결과)
    pipe_note = None
    if file_path or text:
        from ingest_engine import extract_source
        src = extract_source(path=file_path or None, text=text or None)
    else:
        prev = _parse_prev(tool_input.get("_prev_result"))
        body = ""
        if isinstance(prev, str):
            body = prev.strip()
        elif isinstance(prev, dict):
            body = str(prev.get("text") or prev.get("content") or prev.get("summary")
                       or prev.get("message") or "").strip()
        if isinstance(prev, dict) and isinstance(prev.get("items"), list):
            # 본문 병기 봉투(crawl: text=본문 + items=링크 부속)는 본문을 원문으로 쓴다 —
            # "이미 items 통화" 거절은 쓸 본문이 없거나 요약 한 줄뿐일 때만 (2026-08-20
            # ep1325 야생 실측: 대표 용례 crawl>>struct 가 이 거절로 죽어 있었다).
            # 문서-모양 게이트는 write v4 와 같은 규율 — 오분류는 통화 보존(거절) 쪽으로.
            doc_shaped = ("\n" in body) or (len(body) >= 200)
            if not doc_shaped:
                return _fail("입력이 이미 items 통화입니다 — 통화의 의미 변환은 [table:ai], "
                             "산문 종합은 [table:brief] 를 쓰세요. (본문 텍스트가 함께 오는 "
                             "봉투면 본문을 원문으로 씁니다 — 이 봉투엔 쓸 본문이 없습니다.)")
            if prev["items"]:
                pipe_note = (f"파이프 봉투의 items {len(prev['items'])}건은 부속(링크 목록 등)으로 "
                             "보고 본문 텍스트를 원문으로 썼습니다.")
        if not body:
            return _fail("입력이 없습니다 — file(경로)·text(본문)·>> 파이프 본문 중 하나를 주세요.")
        src = {"ok": True, "kind": "text", "text": body[:_ITEMS_CAP],
               "images": None, "label": "파이프 본문"}
    if not src.get("ok"):
        return _fail(src.get("error") or "원문 추출 실패")

    # grounded 기본값: 원장 스키마=on, 그 외=off, 파라미터로 양방향 오버라이드 (판정 4)
    g = tool_input.get("grounded")
    grounded = (schema.lower() in _GROUNDED_DEFAULT_SCHEMAS) if g is None else bool(g)
    grounded_note = None
    if src.get("kind") == "image" and grounded:
        grounded = False          # 이미지=원문 텍스트가 없어 대조가 원리상 불가
        grounded_note = "이미지 입력은 원문 대조가 불가해 grounded 를 해제했습니다."

    system = (
        f"너는 구조화 추출기다. 원문에서 '{schema}' 계약에 맞는 기록을 추출해 JSON 배열로만 출력한다. "
        "규칙: ①원문에 없는 수치·날짜·항목을 지어내지 말 것 ②확실치 않은 필드는 생략 "
        "③날짜는 YYYY-MM-DD ④JSON 밖에 다른 글자를 쓰지 말 것."
    )
    if grounded:
        system += (" ⑤각 기록에 _quote 필드로 그 기록의 근거가 되는 원문 발췌"
                   "(원문 표기 그대로, 한 구절)를 넣을 것.")
    system += f"\n\n[출력 계약]\n{schema}"

    if src.get("kind") == "image":
        # 비전 패스스루(ingest_engine 정본 — 모달리티는 기어 무관, 2026-08-13 원칙)
        from ingest_engine import _gemini_vision_json, _strip_json
        prompt = system + "\n\n[이미지에서 추출]"
        if src.get("text"):
            prompt += f"\n[사용자 메모] {src['text']}"
        raw, err = _gemini_vision_json(prompt, src["images"])
        parsed = _strip_json(raw) if not err else None
        if err or parsed is None:
            return _fail(f"구조화 실패: {err or f'모델 출력을 JSON으로 못 읽음: {str(raw)[:200]}'}")
    else:
        from oneshot_facade import oneshot_json
        parsed, err = oneshot_json(f"[원문]\n{src['text']}", system)
        if err:
            return _fail(f"구조화 실패: {err}")

    from oneshot_facade import records_gate, grounded_filter, mark_ai
    records, gerr = records_gate(parsed)
    if gerr:
        return _fail(f"구조화 실패: {gerr}")

    result = {"source": src.get("label"), "model_axis": "execution"}
    if grounded:
        kept, dropped = grounded_filter(records, src["text"])
        if records and not kept:
            return _fail(f"근거 대조 전멸 — 추출 {len(records)}건 모두 원문 발췌(_quote)가 "
                         "원문과 불일치합니다(환각 의심). grounded:false 로 재시도하거나 원문을 확인하세요.")
        result["grounded"] = True
        if dropped:
            result["dropped_ungrounded"] = dropped
        records = kept
    _notes = [n for n in (grounded_note, pipe_note) if n]
    if _notes:
        result["note"] = " ".join(_notes)
    result["items"] = mark_ai(records)
    result["count"] = len(records)
    return _ok(result)


# ───────────────────────── 중간: [table:ai] ─────────────────────────

def _transform(tool_input: dict) -> str:
    instruction = str(tool_input.get("instruction") or "").strip()
    if not instruction:
        return _fail('instruction(자연어 지시)이 필요합니다 — 예 "광고성 행 제거", '
                     '"각 행에 한 줄 요약 summary 필드 추가".')
    items, prev = _prev_items(tool_input)
    if items is None:
        return _fail("입력 통화가 없습니다 — >> 파이프로 앞 액션의 items 를 받습니다. "
                     "예: [sense:search]{...} >> [table:ai]{instruction: ...}")
    if not items:
        return _ok({"items": [], "rows_in": 0, "rows_out": 0,
                    "note": "입력 0행 — AI 호출 생략(비용 0)."})
    payload, perr = _items_payload(items)
    if perr:
        return _fail(perr)

    fields = tool_input.get("fields")
    if fields is not None and not isinstance(fields, list):
        return _fail("fields 는 문자열 배열이어야 합니다.")

    system = (
        "너는 통화 변환자다. 입력 items(JSON 배열)를 지시대로 변환해 JSON 배열로만 출력한다. "
        "규칙: ①입력에 없는 사실·수치를 지어내지 말 것 ②지시가 행을 줄이거나 늘리라는 것이 "
        "아니면 행 수를 보존할 것 ③기존 필드는 보존하고 필요한 필드만 추가·수정 "
        "④JSON 밖에 다른 글자를 쓰지 말 것."
    )
    if fields:
        system += f" ⑤각 행은 다음 필드만 갖는다: {[str(f) for f in fields]}"

    from oneshot_facade import oneshot_json, records_gate, mark_ai
    parsed, err = oneshot_json(f"[items]\n{payload}\n\n[지시]\n{instruction}", system)
    if err:
        return _fail(f"변환 실패: {err}")
    out, gerr = records_gate(parsed)
    if gerr:
        return _fail(f"변환 실패: {gerr}")
    if fields:
        keys = [str(f) for f in fields]
        out = [{k: r.get(k) for k in keys} for r in out]

    result = {"items": mark_ai(out), "rows_in": len(items), "rows_out": len(out)}
    if len(out) < len(items):
        # 조용한 깎기 금지 — 지시가 시킨 축소인지 하류가 판단할 수 있게 수를 신고한다.
        result["rows_dropped"] = len(items) - len(out)
    return _ok(result)


# ───────────────────────── 출구: [table:brief] ─────────────────────────

def _brief(tool_input: dict) -> str:
    instruction = str(tool_input.get("instruction") or "").strip()
    if not instruction:
        return _fail('instruction(산문 지시)이 필요합니다 — 예 "급변 종목 중심 3문장 보고".')
    items, prev = _prev_items(tool_input)
    if items is None:
        if isinstance(prev, str) and prev.strip():
            return _fail("입력이 평문 텍스트입니다 — 텍스트 요약·질문은 [self:ask]{prompt} 를 "
                         "쓰세요. brief 는 items 통화 전용입니다.")
        return _fail("입력 통화가 없습니다 — >> 파이프로 앞 액션의 items 를 받습니다. "
                     "예: [sense:stock]{...} >> [table:brief]{instruction: ...}")
    if not items:
        return _fail("입력 items 가 0행 — 종합할 근거가 없습니다(앞 단계 결과를 확인하세요).")
    payload, perr = _items_payload(items)
    if perr:
        return _fail(perr)

    system = (
        "너는 데이터 보고자다. 입력 items(JSON 배열)에 있는 내용만 근거로 지시대로 산문을 쓴다. "
        "규칙: ①items 에 없는 사실·수치를 지어내지 말 것 ②서론·맺음말 없이 요청한 산문만 "
        "③기본 한국어(지시가 다른 언어·형식을 요구하면 그대로)."
    )
    from oneshot_facade import execution_oneshot
    prompt = f"[items]\n{payload}\n\n[지시]\n{instruction}"
    answer = execution_oneshot(prompt, system_prompt=system)
    if not (answer or "").strip():
        answer = execution_oneshot(prompt, system_prompt=system)   # 빈 응답만 1회 재시도
    if not (answer or "").strip():
        return _fail("모델 응답을 받지 못했습니다(모델 미설정 가능).")
    # message = 산문 정본 — write 싱크의 산문 추출 계약(2026-08-17 v4)과 접속:
    # 문서 모양 message + items 밖 dict/list 페이로드 없음 → 파일에 산문이 저장된다.
    return _ok({"message": answer.strip(), "rows_in": len(items), "_ai": True})
