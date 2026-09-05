"""workflow_verdict.py — 도구 결과의 실패·빈손 판정과 사유 회수, 단일 소스.

2026-08-29 분리: err_reason_of 신설이 workflow_engine 을 1500줄 규칙 너머로 밀어서,
판정·사유 3형제(is_error_result·err_reason_of·_is_empty_result)를 규칙대로 형제
모듈로 옮겼다. 로직 이동 + 스필 봉투 빈손 가드 1건이며, 호출자는 workflow_engine
재수출로 기존 import 경로가 전부 유지된다.
"""


def is_error_result(result) -> bool:
    """도구 결과가 실패인지 판정한다 — `>>`·`??` 공용 **단일 소스**.

    도구가 실패를 알리는 방식이 **네 갈래**라 판정이 곳곳에 복제됐다가 갈라졌었다
    (2026-07-18: `??` 만 문자열 에러를 성공으로 세어, NameError 를 고친 뒤에도 폴백이 안 됨).
    새 소비자는 이 함수를 부를 것 — 판정을 다시 손으로 적지 말 것.

    실패로 치는 것:
      1. dict: `success is False`, 또는 최상위 `error` 키가 있고 success 가 참이 아님
      2. str `"Error:"`·`"오류:"` 접두 — system_essentials 계열(self:read/delete/copy).
         ★한글 접두는 2026-08-22 추가(B21-1): 영어판만 등록돼 있어 `"오류: …"` 를 내던
         media_producer 계열이 통째로 성공으로 샜다. 다만 이건 **그물**일 뿐이다 —
         같은 계열 26자리 중 10자리는 애초에 접두가 없었으므로(`FFmpeg 오류:`·
         `렌더링 중 오류 발생:`) 접두를 늘리는 것으로는 못 고친다. 진짜 수리는 그쪽
         핸들러를 error dict 계약으로 옮긴 것이고, 이 줄은 다음 위반자를 잡는 안전망이다.
      3. **JSON 문자열** — handler 라우터는 `format_json(...)` 으로 *문자열*을 돌려주므로
         `{"success": false, "message": …}` 가 문자열에 실려 온다. 파싱해서 1번 규칙 적용.
         ★이걸 안 보면 handler 도구의 실패가 전부 성공으로 샌다(2026-07-18 블로그 파이프에서
         실측: `[self:blog]` 가 실패했는데 파이프가 success=True 로 보고).
      4. 예외 — 호출부가 잡아서 별도 처리(이 함수 밖).

    실패로 치지 않는 것:
      - `status == "not_implemented"` — 미구현은 고장이 아님
      - `{"success": true, "error": null}` — 성공인데 error 키가 있는 모양
        (서킷 브레이커가 `verify.error: null` 로 성공을 실패로 오인했던 전례를 판정에 반영)

    ★한계: `"Error:"` 접두 판정은 **휴리스틱**이다. 본문이 그렇게 시작하는 정당한 콘텐츠
    (로그 요약·코드 스니펫)를 실패로 오인할 수 있다. 도구 반환 규약을 통화로 수렴시키기 전까지의
    잠정 규칙이며, **최상위 result 에만** 적용한다(중첩 dict 의 error 키는 보지 않는다).
    """
    if isinstance(result, dict):
        if result.get("status") == "not_implemented":
            return False
        if result.get("success") is False:
            return True
        return ("error" in result) and not result.get("success")
    if isinstance(result, str):
        s = result.lstrip()
        if s.startswith("Error:") or s.startswith("오류:"):
            return True
        # handler 라우터의 JSON 문자열 — 최상위만 파싱해 dict 규칙 재사용
        if s.startswith("{"):
            try:
                import json as _json
                parsed = _json.loads(s)
            except Exception:
                return False
            if isinstance(parsed, dict):
                return is_error_result(parsed)
        return False
    return False


def err_reason_of(result) -> str:
    """실패 결과에서 사람이 읽을 **사유**를 건진다 — 봉투 조립 공용 단일 소스.

    is_error_result 의 짝: 판정은 저기, 사유 추출은 여기. 계약상 사유 자리는 최상위
    `error` 지만, 실측(2026-08-29 friction 보고: youtube transcript 실패)에서 최상위가
    `"Step 1 에러: "` 빈 문자열이었고 진짜 사유는 message·중첩 봉투에만 있었다.
    스윕해 보니 `{"success": False, "message": …}` 모양이 89자리 — 위반이 아니라 관례다.
    89개 리터럴을 고치는 대신 읽는 쪽이 관례를 인정한다: error → message → 중첩
    results[] 의 실패 항목 → final_result 순. 실패 판정이 끝난 결과에만 부를 것
    (성공 결과의 message 는 사유가 아니다).
    """
    if not isinstance(result, dict):
        return str(result)
    for k in ("error", "message"):
        v = result.get(k)
        if isinstance(v, str) and v.strip():
            return v
    # errors[] 관례(외부 API 봉투 — Cloudflare 등)도 사유다(2026-09-05 ep2833: error "" 로 신고된 분기 실패).
    errs = result.get("errors")
    if isinstance(errs, list) and errs:
        parts = []
        for e in errs[:3]:
            if isinstance(e, dict):
                msg = e.get("message") or e.get("error") or ""
                code = e.get("code")
                parts.append(f"{code}: {msg}" if code is not None and msg else (msg or str(e)[:120]))
            elif isinstance(e, str) and e.strip():
                parts.append(e.strip())
        if parts:
            return "; ".join(parts)
    subs = result.get("results")
    if isinstance(subs, list):
        for sub in subs:
            if isinstance(sub, dict) and is_error_result(sub):
                v = sub.get("error") or sub.get("message")
                if isinstance(v, str) and v.strip():
                    return v
    fr = result.get("final_result")
    if isinstance(fr, dict) and is_error_result(fr):
        v = fr.get("error") or fr.get("message")
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _is_empty_result(result) -> bool:
    """도구 결과가 **빈손**인지 판정한다 — `??` 전용 보조 술어 (2026-08-08, 실험 7 ⑯).

    두 연산자의 술어는 원래 다르다:
      - `>>` 순차: "앞이 죽었으면 멈춰라" → 고장(is_error_result)만. 0건은 죽음이
        아니고, 0건 위의 take/filter 가 0건을 내는 것이 정답이다.
      - `??` 폴백: "원하는 걸 못 얻었으면 딴 데로" → **빈손도 못 얻은 것**.
        폴백을 거는 대상은 대개 검색이고 목록형 검색의 흔한 실패 모드가 0건이라,
        고장 판정만으로는 발동해야 할 자리의 다수를 통과시킨다(실측: [sense:used]
        total:0 이 status ok 로 기록되고 뒤의 웹 검색이 손도 안 대진 채 남았다).
    2026-07-18 의 판정 통일(is_error_result 단일 소스)은 유지 — 이 술어는 or 로만 얹는다.

    빈손 판정은 **구조 신호만** (산문 휴리스틱 없음):
      - dict(또는 JSON 문자열)의 items == [] (빈 리스트)
      - total == 0 / count == 0 (명시된 0 — 키 부재는 판정 밖)
      - 표 통화의 rows == [] (columns 가 함께 있을 때만 — 우연한 rows 키 오판 방지)
    """
    if isinstance(result, str):
        s = result.lstrip()
        if not s.startswith("{"):
            return False
        try:
            import json as _json
            result = _json.loads(s)
        except Exception:
            return False
    if not isinstance(result, dict):
        return False
    # 스필 참조 봉투는 빈손이 아니다 — items:[] 는 "없음"이 아니라 "외부화됨"
    # (2026-08-29: 긴 자막이 참조 봉투로 나가면서 `transcript ?? X` 가 오발할 자리).
    if (result.get("_spilled") or result.get("spilled")) and isinstance(result.get("ref"), dict):
        return False
    items = result.get("items")
    if isinstance(items, list) and not items:
        return True
    for k in ("total", "count"):
        v = result.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0:
            return True
    t = result.get("table")
    holder = t if isinstance(t, dict) else result
    rows = holder.get("rows")
    if isinstance(rows, list) and not rows and isinstance(holder.get("columns"), list):
        return True
    return False
