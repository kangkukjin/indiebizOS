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
    ★0행 계약(F20-3, 세 낱말 공통): 통화 없음=에러 / 0행=성공(빈손 + note).
      새 소비자 낱말을 더할 때 이 두 갈래를 반드시 갈라 심사한다.
  · ★파라미터 이름: 지시문 자리는 `instruction`(table:structure 선례) — `do` 는
    IBL *문장*을 나르는 자리(M1 통일)라 자연어 지시에 쓰면 개념이 흐려진다.

모듈레벨 = stdlib 만(폰 import-safe 불변식, data-ops 선례) — 무거운 것은 함수 안 지연 import.
"""
import json
import os
import re

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

def _resolve_spill(prev):
    """스필 참조 봉투({items:[], ref:{path}, _spilled})면 본문을 복원한다 — 파이프·파일 양쪽 입구 공용.

    2026-09-02 실측(유튜브 팁 06시 주행): 자막 4편을 & 로 뽑으면 가지 원형이 표시 한도를
    넘어 스필 참조로 내려오고, 모델은 그 ref.path(.json)를 struct 의 file 로 넘긴다 —
    옛 코드는 확장자만 보고 거절했다("지원하지 않는 형식: .json"). 참조는 소비자가
    투명하게 따라가야 한다는 스필 규약(common.spill)을 여기서도 지킨다."""
    try:
        from common.spill import resolve_ref_str
    except ImportError:
        return prev, None
    try:
        return resolve_ref_str(prev)
    except Exception as e:      # 참조 해소가 문장을 죽이면 안 된다 — 원형으로 계속
        return prev, str(e)


def _load_json_envelope(path: str):
    """.json 파일을 봉투로 읽는다. (obj, err). 스필 참조·중첩 봉투는 여기서 풀린다."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        return None, f"파일 읽기 실패: {e}"
    try:
        obj = json.loads(raw)
    except Exception:
        return raw, None         # JSON 이 아니면 평문 본문으로 본다
    obj, _ = _resolve_spill(obj)
    return obj, None


def _src_from_envelope(prev, label="파이프 본문"):
    """봉투(dict|str) → (src, pipe_note, body). src 가 None 이면 body 로 판단한다.

    외부화 봉투(saved_to_file+file_path)는 파일 전문을 따라가 타임스탬프·헤더를 걷고,
    본문 필드 사슬은 transcript·text·content·summary·preview, message 는 최후 폴백.
    """
    src, pipe_note, body = None, None, ""
    if isinstance(prev, str):
        body = prev.strip()
        return src, pipe_note, body
    if not isinstance(prev, dict):
        return src, pipe_note, body
    if prev.get("saved_to_file") and prev.get("file_path"):
        # 파일이 사라졌으면(24h 정리 등) 조용히 아래 본문 사슬(preview 폴백)로 —
        # 따라가기 실패가 문장을 죽이면 안 된다.
        try:
            from ingest_engine import extract_source
            _fsrc = extract_source(path=str(prev["file_path"]), text=None)
        except Exception:
            _fsrc = {"ok": False}
        if _fsrc.get("ok"):
            # 자막류 외부화 파일은 `[MM:SS] 문장` 병기 포맷이다 — 표식·헤더를 걷어 흐르는
            # 본문으로 정규화해야 grounded 대조(_quote 부분열)가 성립한다(2026-08-27 실측).
            if isinstance(_fsrc.get("text"), str):
                _lines = [re.sub(r"^\[[0-9:.]+\]\s*", "", ln)
                          for ln in _fsrc["text"].splitlines()
                          if not ln.lstrip().startswith("#")]
                _fsrc["text"] = re.sub(r"\s+", " ", " ".join(_lines)).strip()
            src = _fsrc
            pipe_note = "외부화 봉투(saved_to_file)를 따라가 파일 전문을 원문으로 썼습니다."
            return src, pipe_note, body
    body = str(prev.get("transcript") or prev.get("text") or prev.get("content")
               or prev.get("summary") or prev.get("preview")
               or prev.get("message") or "").strip()
    return src, pipe_note, body


def _struct(tool_input: dict) -> str:
    schema = str(tool_input.get("schema") or "").strip()
    if not schema:
        return _fail('schema(출력 레코드 계약)가 필요합니다 — 자유 라벨(예 "finance") '
                     '또는 필드 명세 텍스트(예 "date, item, amount(원)").')

    file_path = str(tool_input.get("file") or "").strip()
    text = str(tool_input.get("text") or "").strip()

    # 입력 획득: file/text 우선, 없으면 >> 파이프 본문(예: [sense:crawl] 결과)
    pipe_note = None
    prev = None
    label = "파이프 본문"
    if file_path and file_path.lower().endswith((".json", ".jsonl")):
        # ★.json 은 문서가 아니라 봉투다 — 스필 참조·자막 봉투·외부화 봉투를 파이프와
        #   같은 눈으로 읽는다(2026-09-02 이음매 수리). ingest_engine 은 문서 형식 전용이라
        #   여기서 갈라 보낸다.
        prev, _err = _load_json_envelope(file_path)
        if _err:
            return _fail(_err)
        label = os.path.basename(file_path)
        file_path = ""
        if isinstance(prev, list):
            prev = {"items": prev}
        pipe_note = f"JSON 봉투 파일({label})을 파이프 본문과 같은 규약으로 읽었습니다."
    if file_path or text:
        from ingest_engine import extract_source
        src = extract_source(path=file_path or None, text=text or None)
    else:
        if prev is None:
            prev = _parse_prev(tool_input.get("_prev_result"))
            prev, _ = _resolve_spill(prev)
        src, _note, body = _src_from_envelope(prev, label)
        if _note:
            pipe_note = (pipe_note + " " + _note) if pipe_note else _note
        if src is None and isinstance(prev, dict) and isinstance(prev.get("items"), list):
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
                _n = (f"파이프 봉투의 items {len(prev['items'])}건은 부속(링크 목록 등)으로 "
                      "보고 본문 텍스트를 원문으로 썼습니다.")
                pipe_note = (pipe_note + " " + _n) if pipe_note else _n
        if src is None:
            if not body:
                return _fail("입력이 없습니다 — file(경로)·text(본문)·>> 파이프 본문 중 하나를 주세요.")
            src = {"ok": True, "kind": "text", "text": body[:_ITEMS_CAP],
                   "images": None, "label": label}
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
        from ingest_engine import _vision_json, _strip_json
        prompt = system + "\n\n[이미지에서 추출]"
        if src.get("text"):
            prompt += f"\n[사용자 메모] {src['text']}"
        raw, err = _vision_json(prompt, src["images"])
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
    fields = tool_input.get("fields")
    if fields is not None and not isinstance(fields, list):
        return _fail("fields 는 문자열 배열이어야 합니다.")

    # ★색인 병합 계약(2026-09-06, ep2882 실측): 옛 계약은 모델이 **행 전체**를 다시 쓰게 했다 —
    #   fields 에 title·summary·url 이 있으면 규칙 ⑤가 입력을 되받아쓰게 만들어, 출력 글자의 76%
    #   (title 36·summary 23·url 9·date 8%)가 입력 echo 였고 새 정보(delta·label)는 13% 였다.
    #   [table:ai] 한 호출 140초의 4분의 3이 그 echo 의 출력 토큰. 새 계약: 입력 행에 색인 `_i`
    #   를 달아 보내고, 모델은 행마다 `{_i, 새로 만들거나 바꾼 필드}` 만 돌려준다 — 코드가 원 행에
    #   병합한다(값 보존·순서 = 반환 순서·뺀 _i = 제거·_i 없는 행 = 신규). 모델이 계약을 어기고
    #   _i 없이 전 행을 돌려주면 옛 계약(전체 행)으로 정직 폴백하고 `_merge: "full"` 로 신고한다.
    dict_items = [r if isinstance(r, dict) else {"value": r} for r in items]
    payload, perr = _items_payload([{"_i": i, **r} for i, r in enumerate(dict_items)])
    if perr:
        return _fail(perr)

    system = (
        "너는 통화 변환자다. 입력 items(JSON 배열, 각 행에 색인 _i)를 지시대로 변환한다. "
        "출력은 JSON 배열만: 행마다 {\"_i\": 색인, 새로 만들거나 값을 바꾼 필드…}. "
        "규칙: ①입력에 없는 사실·수치를 지어내지 말 것 ②지시가 행을 줄이거나 늘리라는 것이 "
        "아니면 모든 _i 를 돌려줄 것(뺀 _i = 제거된 행, _i 없는 행 = 새 행) "
        "③입력에 이미 있는 필드는 다시 쓰지 말 것 — 코드가 원 행에 병합한다(값을 바꿀 때만 그 필드를 적는다) "
        "④JSON 밖에 다른 글자를 쓰지 말 것."
    )
    if fields:
        system += (f" ⑤병합 뒤 각 행은 다음 필드만 남는다: {[str(f) for f in fields]} — "
                   "이 중 입력에 없는 필드만 채워라.")

    from oneshot_facade import oneshot_json, records_gate, mark_ai
    parsed, err = oneshot_json(f"[items]\n{payload}\n\n[지시]\n{instruction}", system)
    if err:
        return _fail(f"변환 실패: {err}")
    out, gerr = records_gate(parsed)
    if gerr:
        return _fail(f"변환 실패: {gerr}")
    out, merge_mode, bad_idx = _merge_by_index(dict_items, out)
    if fields:
        keys = [str(f) for f in fields]
        out = [{k: r.get(k) for k in keys} for r in out]

    result = {"items": mark_ai(out), "rows_in": len(items), "rows_out": len(out),
              "_merge": merge_mode}
    if bad_idx:
        result["note"] = f"모델이 돌려준 _i {bad_idx} 은(는) 입력 범위 밖이라 새 행으로 받았습니다."
    if len(out) < len(items):
        # 조용한 깎기 금지 — 지시가 시킨 축소인지 하류가 판단할 수 있게 수를 신고한다.
        result["rows_dropped"] = len(items) - len(out)
    return _ok(result)


def _merge_by_index(src: list, out: list):
    """모델 반환(행마다 `_i` + 새/바뀐 필드)을 원 행에 병합. 반환 (rows, mode, bad_idx).

    mode = "index"(계약 준수 — 하나라도 _i 를 달고 왔다) | "full"(옛 계약 폴백 — _i 전무, 전 행 그대로).
    _i 가 있으면 원 행 사본 위에 반환 필드를 덮는다(키가 같으면 모델 값이 이긴다 — 값 수정 통로),
    _i 가 없거나 범위 밖이면 새 행. 순서는 반환 순서. `_i` 는 출력에서 벗긴다."""
    if not any(isinstance(r, dict) and "_i" in r for r in out):
        return out, "full", []
    rows, bad = [], []
    for r in out:
        if not isinstance(r, dict):
            continue
        r = dict(r)
        i = r.pop("_i", None)
        try:
            i = int(i) if i is not None else None
        except (TypeError, ValueError):
            i = None
        if i is not None and 0 <= i < len(src):
            base = dict(src[i])
            base.update(r)
            rows.append(base)
        else:
            if i is not None:
                bad.append(i)
            rows.append(r)
    return rows, "index", bad


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
        # ★F20-3 판정 (2026-08-22): 0행은 고장이 아니라 정당한 빈손이다.
        # 같은 몸의 F17 계약(each·flatten·groupby·filter·take·table:ai 전부 0행 통과)에
        # brief 하나만 예외로 남아 있었고, 그 예외가 감시자 문형의 자연스러운 꼬리
        # (`[table:since] >> [table:brief]`)를 **첫 실행마다 error 로 끝내고** 있었다.
        # 우회(`[if: empty($items)]`·`[on_error: skip]`)를 관용구로 승인하지 않은 이유:
        # 감시자 문장마다 가드를 다는 문법 세금이고, on_error:skip 은 진짜 실패까지
        # 삼켜 침묵 실패 습관을 함께 가르친다.
        # 구분은 유지한다 — 통화 없음(위 _fail)=에러 / 0행=성공. 조용한 성공이 아니라
        # **말하는 빈손**이 되도록 rows_in 과 note 를 반드시 싣는다(seeded:true 와 함께
        # 읽으면 "첫 회라 0행"과 "고장이라 0행"이 구별된다).
        # message(산문 정본) 키는 넣지 않는다 — 행이 없으면 산문도 없다. 빈 문자열로
        # 위장하면 write 싱크가 빈 파일을 쓰고, `??` 폴백도 빈손을 못 알아본다.
        return _ok({"items": [], "rows_in": 0,
                    "note": "입력 0행 — 종합할 내용이 없어 AI 호출 생략(비용 0)."})
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
