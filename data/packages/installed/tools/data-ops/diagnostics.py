"""diagnostics.py — data-ops 변환자의 **정직한 거절** 층 (2026-08-23 분리, 1500줄 규칙)

handler.py 에서 verbatim 이동: 부재 판정(_observed_fields·_absent_fields)과 그것을
문장으로 바꾸는 필드 오류문(_field_missing_error).

왜 한 모듈인가: 이 몸이 반복해서 배운 것은 **틀린 답보다 틀린 진단이 비싸다**는 것이다
(⑧′ 침묵-삼킴 금지 · B28-1 "증거의 부재는 부재의 증거가 아니다" · 29회차 emitter 정직성). 그 규율이 여섯 변환자에 흩어져 있으면 한 자리만 좋아지고 나머지는
드리프트한다 — 좋은 거절의 기준("없는 것 + 있는 것 + **다음에 뭘 하라**")을 지키는 자리를
하나로 모은다.

경계: 봉투 수준의 진단(`_no_currency_error` — "통화 자체가 없다", 병렬 봉투 판별)은
handler 에 남는다. 그건 필드가 아니라 **봉투 모양**을 묻는 질문이라 handler 의
통화 추출기(_get_items·_parallel_envelope_shape)와 한 몸이다.

handler 가 load_sibling 으로 붙여 이름을 재수출하므로 기존 호출부는 그대로다.
"""
import json


def _observed_fields(rows=None, columns=None):
    """행/열에서 **실제로 관측된** 필드 이름 집합. 관측이 없으면 빈 집합."""
    if columns is not None:
        return {str(c) for c in columns}
    return {str(k) for r in (rows or []) if isinstance(r, dict) for k in r.keys()}


def _absent_fields(names, observed):
    """이름들 중 **부재를 주장할 수 있는** 것만 돌려준다 (B28-1, 상상훈련 28회차).

    ★증거의 부재는 부재의 증거가 아니다. 관측된 필드가 하나도 없으면(=행이 0개면)
    "그 필드는 없다"는 **주장할 수 없는 명제**다 — 스키마는 멀쩡한데 행만 비었을 수 있다.

    실측(2026-08-23):
        [self:body]{days: 3, limit: 5} >> [table:filter]{where: "존재하지않는값ZZZ"}
                                       >> [table:rename]{map: {"파일": "경로"}}
        → step1 columns: ['상태','시각','영역','요지','커밋','파일']   ← '파일' 은 실재한다
          step2 count: 0                                            ← 정당한 0행
          step3 "rename: 필드 ['파일'] 이(가) 없습니다. 행 필드 예: []"
    오류문이 스스로를 반박한다 — `행 필드 예: []` 는 *아무것도 못 봤다*는 말이지
    *없다*는 말이 아니다.

    ★왜 두 갈래가 생겼나: F17 이 빈손 계약을 **"verb 마다 심사"** 로 정해 두었기 때문이다.
    그래서 verb 마다 `not any(k in r for r in dict_recs)` 를 손으로 다시 적고, 빈손 보호는
    *호출자가 먼저 짧게 끊어 주는* 우연에 기댔다. 단항 9개 중 8개는 우연히 끊겼고
    rename 만 안 끊겨서 혼자 다른 답을 냈다(28회차 실측 행렬).
    → 갈래를 없애는 자리는 verb 가 아니라 **판정기**다. 판정기가 빈 관측에서 부재를
      주장하지 않으면, 앞으로 생길 verb 도 같은 실수를 할 수 없다.
      (같은 규율의 선례: 조건 평가의 "판정 불능은 거짓이 아니다" — 판정 불능이면 else 도 보류.)

    반환: 정말로 없는 이름 목록(관측 0이면 빈 목록 = 주장 없음).
    """
    if isinstance(names, (list, tuple, set)):
        names = [str(n) for n in names]
    else:
        names = [str(names)]
    if not observed:
        return []
    return [n for n in names if n not in observed]


def _field_missing_error(verb, missing, rows):
    """명시 파라미터가 가리키는 필드가 어느 행에도 없을 때의 정직한 에러.

    침묵-삼킴 금지 계약(2026-08-08, 3방식 실험 ⑧′): 잘못된 필드/형식을 조용히
    기본값으로 위장하면 '그럴듯하게 틀린' 결과가 나가고, 진짜 비용은 틀린 답이
    아니라 틀린 진단이다(실험자가 '기능이 없다'고 오진). sort 의 가드를 계열 전체로.
    """
    avail = []
    for r in rows or []:
        if isinstance(r, dict):
            avail = list(r.keys())
            break
    miss = "', '".join(str(m) for m in missing) if isinstance(missing, (list, tuple)) else str(missing)
    hint = f" 사용 가능한 필드: {avail}" if avail else ""
    if verb == "filter":
        # 워드 연산자 합류(B19-1) 뒤엔 "필드 op 값" 문자열이 조건으로 읽히므로, 전-필드
        # 검색을 의도했던 문장이 여기로 온다 — 그 갈림길을 오류문이 직접 안내한다.
        hint += " (모든 필드에서 그냥 찾으려면 연산자 없는 문자열을 주세요: where: \"자이\")"
        # ★F53-4 (53회차 상상훈련): `where: "url not_in ${본.items.*.url}"` — 열 벡터가 문자열
        #   where 에 JSON 목록으로 박혀 "필드"가 통째로 여기 온다. 정답(구조형 where)을 오류문이
        #   직접 가리켜야 자가교정이 된다(종전 처방 brief/each 는 이 경우의 답이 아니었다).
        if any(tok in miss for tok in (" in [", " not_in [", " in {", " not_in {")):
            hint += (" ★목록 값(배열·${x.items.*.f} 열 벡터)은 문자열 where 에 못 들어갑니다 — "
                     "구조형으로 적으세요: where: {field: \"url\", op: \"not_in\", value: \"${본.items.*.url}\"}")
    return {"success": False, "error": f"{verb}: '{miss}' 필드가 어느 행에도 없습니다.{hint}"}


def _empty_filter_note(out, where, rows, fields):
    """filter 가 N>0 행에서 0행을 냈을 때 봉투가 **무엇을 어디서 찾았는지** 말한다 (2026-09-06, ep2882).

    실측: `[sense:search]{…} >> [table:filter]{where: "lambda.ai"}` 가 0행 — 봉투는 count:0 만 말했다.
    모델은 "where 가 url 필드를 보지 않는다"로 오진해 수리 신호를 올렸다. 실제로는 전-필드 부분일치가
    8행의 title·url·summary 를 전부 봤고, 검색 결과에 그 도메인이 없었다(정당한 0행).
    0행은 옳다 — 없던 것은 진단이다. 빈손이 자기 기준(조건·본 필드·입력 행수)을 말하지 않으면
    정당한 0행과 고장이 같은 모양이 된다(ai-ops 0행 note·union effect note 와 같은 규율).
    입력 0행은 여기서 말하지 않는다 — 그건 상류의 빈손이고 상류가 말한다.
    """
    if not isinstance(out, dict) or not out.get("success", True):
        return out
    kept = out.get("items")
    if kept is None:
        t = out.get("table")
        kept = t.get("rows") if isinstance(t, dict) else out.get("rows")
    if kept or not isinstance(kept, list):
        return out
    n = len([r for r in (rows or []) if isinstance(r, dict)])
    if n == 0:
        return out
    observed = sorted(_observed_fields(rows=rows))
    out["rows_in"] = n
    if isinstance(where, str) and not fields:
        out["note"] = (f"filter: 연산자 없는 문자열 {where!r} 은(는) 전-필드 부분일치 — 입력 {n}행의 필드 "
                       f"{observed} 어느 문자열 값에도 그 글자가 없어 0행입니다(조건은 모든 필드를 봤음). "
                       f"값이 정말 있는지 그 필드를 먼저 확인하고, 한 필드만 보려면 \"필드 contains 값\" 으로.")
    else:
        out["note"] = (f"filter: 조건 {json.dumps(where, ensure_ascii=False)} 에 맞는 행이 입력 {n}행 중 0행입니다"
                       f"(지목 필드 {list(fields or [])} 는 있음 — 값이 조건을 만족하지 않음).")
    return out
