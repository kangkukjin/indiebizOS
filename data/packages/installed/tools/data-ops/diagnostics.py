"""diagnostics.py — data-ops 변환자의 **정직한 거절** 층 (2026-08-23 분리, 1500줄 규칙)

handler.py 에서 verbatim 이동: 부재 판정(_observed_fields·_absent_fields)과 그것을
문장으로 바꾸는 필드 오류문(_field_missing_error) + each 봉투 처방(_each_envelope_remedy).

왜 한 모듈인가: 이 몸이 반복해서 배운 것은 **틀린 답보다 틀린 진단이 비싸다**는 것이다
(⑧′ 침묵-삼킴 금지 · B28-1 "증거의 부재는 부재의 증거가 아니다" · 29회차 emitter 정직성 ·
08-23 each 봉투 처방). 그 규율이 여섯 변환자에 흩어져 있으면 한 자리만 좋아지고 나머지는
드리프트한다 — 좋은 거절의 기준("없는 것 + 있는 것 + **다음에 뭘 하라**")을 지키는 자리를
하나로 모은다.

경계: 봉투 수준의 진단(`_no_currency_error` — "통화 자체가 없다", 병렬 봉투 판별)은
handler 에 남는다. 그건 필드가 아니라 **봉투 모양**을 묻는 질문이라 handler 의
통화 추출기(_get_items·_parallel_envelope_shape)와 한 몸이다.

handler 가 load_sibling 으로 붙여 이름을 재수출하므로 기존 호출부는 그대로다.
"""

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


def _each_envelope_remedy(avail) -> str:
    """들어온 통화가 `[table:each]` 의 행별 봉투 모양이면 **다음에 뭘 하라**를 알려준다.

    each 는 통화를 그대로 내지 않는다 — 행별 성패를 신고해야 하므로 원 행에
    `_ok`/`_result`(또는 `_error`)를 씌운 봉투를 낸다. 이건 버그가 아니라 의도된
    설계다(그걸 없애면 어느 행이 실패했는지 말할 수 없다). 문제는 그 다음이다:
    뒤에 붙는 변환자가 전부 "그 필드 없다"로 끊기는데, 오류문이 *없는 것*과
    *있는 것*까지만 말하고 **다음에 뭘 하라**를 안 말했다. 그래서 사용자는 자기
    문장이 틀린 줄 알고 each 를 버리고 같은 액션을 N번 부르는 쪽으로 돌아간다.

    실측(2026-08-23): 8일간 each 실사용 **7건** vs "한 문장으로 접힐 수 있었던"
    연속 동일 액션 반복 **700여 건**. 29회차 상상훈련도 이걸 두 번 밟고
    *자기 저작 오류*로 계상해 갭 원장에 못 올렸다 — 정직한 오류문이 불완전하면
    마찰이 사용자 탓으로 계상된다.

    ★판정은 **모양으로만** 한다(헌법 '명사의 자리') — 앞 액션의 이름을 묻지 않고
    봉투 표식 키의 존재만 본다. `[table:flatten]` 이 이미 같은 표식으로 자동
    승격하므로 처방도 그것 하나다.
    """
    names = {str(a) for a in (avail or [])}
    if "_ok" in names and ("_result" in names or "_error" in names):
        return (" ★이건 [table:each] 의 행별 봉투입니다(통화가 아닙니다) — each 는 행별 성패를 "
                "신고하려고 원 행에 _ok/_result 를 씌웁니다. 원래 필드는 _result 안에 있으니 "
                "먼저 펴세요: >> [table:flatten] >> …")
    return ""


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
    hint += _each_envelope_remedy(avail)
    if verb == "filter":
        # 워드 연산자 합류(B19-1) 뒤엔 "필드 op 값" 문자열이 조건으로 읽히므로, 전-필드
        # 검색을 의도했던 문장이 여기로 온다 — 그 갈림길을 오류문이 직접 안내한다.
        hint += " (모든 필드에서 그냥 찾으려면 연산자 없는 문자열을 주세요: where: \"자이\")"
    return {"success": False, "error": f"{verb}: '{miss}' 필드가 어느 행에도 없습니다.{hint}"}
