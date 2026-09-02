"""봉투 범위·거울 재투영 — 변환자 병목의 잎 모듈 (2026-09-02, 1500줄 규칙으로 handler.py 에서 분리).

`_emit_items`/`_emit_table`(handler) 이 변환 뒤 봉투를 **정직하게** 만드는 데 쓰는 두 벌:
  · `_reproject_mirrors` — 거울 키 갱신 + 변환을 못 따라온 형제(리스트·행 모양 dict)의 자백(_untransformed)
  · `_restate_scope`    — truncated/summary 의 기수 재진술(B26-1·B26-2)
handler 가 load_sibling 으로 들여와 같은 이름으로 재수출한다(호출부 불변).
"""

_CURRENCY_KEYS = ("items", "table", "columns", "rows", "count")


def _reproject_mirrors(out, originals, new_rows):
    """거울 키(=통화를 도메인 이름으로 병기한 키)를 변환 결과로 함께 갱신한다.

    ★B15-1 (2026-08-20 상상훈련 15회차): `[self:trigger]{op:"list"}` 는 `items` 와
    `triggers` 에 **같은 리스트**를 병기한다(items 병행 방출 규약 — 그래야 `>> [table:*]`
    가 통화를 찾는다). 그런데 변환자는 `items` 만 갈아끼우고 `triggers` 는 그대로 두어,
    `take{n:1}` 뒤에도 `triggers` 에 전 건이 남았다 — **변환자는 일했는데 봉투가**
    **거짓말을 한다**(실측: items 1건/count 1 인데 triggers 3건, filter 전멸 뒤에도 3건).
    읽는 쪽(모델·사람·표면)은 도메인 이름을 먼저 믿으므로 "n개만 골라 알림"이 전량으로
    번진다. `message`/`text`/`table` 을 이미 여기서 떨어내는 것과 **같은 부류**이고,
    거울 키는 이름을 미리 알 수 없으므로 이름 목록이 아니라 **동일성**으로 찾는다.

    ★생산자 7곳(trigger list/history·switch·agents·guestpc limbs·pc-manager top·web
    sections)을 각각 고치지 않고 이 병목에서 닫는 이유: 8번째 병행 방출이 다시 감염된다
    (입구를 하나로 접은 `_get_items_for_fields` 선례, F6).

    판정 순서(오폭 방지): ①객체 동일성(is) 먼저 — 병기는 같은 객체를 두 키에 넣으므로
    대부분 여기서 잡힌다 ②값 동등(==) 폴백 — 복사본 병기(`list(x)`)용. 빈 리스트는
    값 동등을 건너뛴다(무관한 빈 리스트 오폭 방지). 원본과 **다른** 컬렉션은 손대지
    않는다 — 예: trigger list 의 `existing_schedules` 는 종류가 다른 원장이라 보존된다.

    `_mirrored` 는 순찰용 계수 표식이다(거울 키 증식 압력계 — 재투영이 "거울 키를
    마음껏 만들어도 된다"는 면허로 오독되지 않게. 하우스 교리는 단일 통화 {items}).
    """
    cands = [o for o in (originals or []) if isinstance(o, list)]
    mirrors = []
    for k, v in list(out.items()):
        if not cands or k in _CURRENCY_KEYS or not isinstance(v, list):
            continue
        hit = any(v is o for o in cands) or any(o and v == o for o in cands)
        if hit:
            out[k] = list(new_rows)
            mirrors.append(k)
    if mirrors:
        out["_mirrored"] = sorted(mirrors)

    # ★자백(2026-08-20 사용자 판정): 거울이 **아닌** 형제 컬렉션은 변환을 따라가지 못한다.
    #   두 부류가 있고 둘 다 기계가 대신 정할 수 없다 —
    #   ①종류가 다른 형제 원장(trigger list 의 existing_schedules): 애초에 다른 데이터라
    #     변환 대상이 아니다. 손대면 그건 통화 수리가 아니라 의미 결정이다.
    #   ②파생 원천(others:agents 의 projects 트리 — items 는 이걸 *펼쳐서* 만든 것):
    #     평평한 items 로는 되돌릴 수 없어 재투영이 원리적으로 불가능하다.
    #   그래서 드롭도 재투영도 아닌 **자백**을 택한다: 이 키들은 변환 전 상태라고 봉투에
    #   적어 둔다. 읽는 쪽(모델·사람)이 도메인 이름을 통화로 오독하는 것이 B15-1 의 실제
    #   피해였고, 자백은 그 오독만 막으면서 데이터는 하나도 안 버린다.
    untouched = [k for k, v in out.items()
                 if k not in _CURRENCY_KEYS and k not in mirrors and not str(k).startswith("_")
                 and isinstance(v, list) and v and any(isinstance(x, dict) for x in v)]
    # ★B53-3 (53회차 상상훈련, 2026-09-02): **행과 같은 열을 가진 형제 dict** 도 변환을 따라오지
    #   못한 것이다 — stock quote 는 items[0] 옆에 같은 행을 `data` 로 병기하고, select 가 열을
    #   골라내도 `data` 는 전 필드를 들고 갔다. 그 봉투를 `$변수` 로 파일에 쓰면 선별이 무효다
    #   (민감 열 제거가 헛일). 이름이 아니라 **열의 동일성**(행 키의 절반 이상 겹침)으로 판정한다
    #   — 위 리스트 규칙과 같은 원리(값·동일성으로 찾고, 이름 목록을 들지 않는다).
    _row0 = None
    for _o in (originals or []):
        if isinstance(_o, list):
            _row0 = next((x for x in _o if isinstance(x, dict)), None)
            if _row0 is not None:
                break
    if isinstance(_row0, dict) and len(_row0) >= 2:
        _rk = set(_row0.keys())
        for k, v in out.items():
            if (k in _CURRENCY_KEYS or k in mirrors or str(k).startswith("_") or k in untouched
                    or not isinstance(v, dict) or not v):
                continue
            if len(set(v.keys()) & _rk) >= max(2, (len(_rk) + 1) // 2):
                untouched.append(k)
    if untouched:
        out["_untransformed"] = sorted(untouched)
    return out


def _restate_scope(out, prior_len, new_len):
    """변환 뒤 봉투가 **자기 기수를 다시 말하게** 한다 (B26-1·B26-2, 상상훈련 26회차).

    이 시스템은 `truncated` 를 스스로 이렇게 정의해 둔다 — **truncated == total > len(items)**
    (`surface/portal_warehouse.py:304` · `test_body_vocab` T1/T5). 그런데 단항 변환자는
    `total` 을 그대로 물고 내려가면서 `truncated` 를 재계산하지 않아, 봉투가 자기
    불변식을 깨뜨렸다. 실측(2026-08-23):
        [self:grep]{…}                    → total 29 · items 29 · truncated false   (참)
        … >> [table:take]{n: 1}            → total 29 · items  1 · truncated false   (거짓)
        … >> [table:filter]{…}            → total 29 · items 27 · truncated false   (거짓)
        … >> [table:dedup]{by: "파일"}      → total 29 · items  1 · truncated false   (거짓)
    즐 "29건 전부를 보여준다"고 말하면서 1건을 낸다. ★이것은 새 부류가 아니라
    이미 세 번 봉한 '잘림 침묵'의 네 번째 자리다 — ⑥′(file_find `truncated/total` 봉투키)·
    ⑫(grep 전수 계수)·⑭(`_carry_flags` 로 이항 변환자 승계). 그 스윗이 **단항 경로에만**
    안 닿았고, 단항은 이 병목(`_emit_items`/`_emit_table`) 하나로 전부 통과한다.

    규칙은 전부 기존 계약에서 끌어왔다 — 새 의미를 만들지 않는다:
      ① `truncated` 는 **켜기만** 한다(단조). `total` 이 결과 기수보다 크면 True.
         끄지 않는 이유: 상류가 *다른 사유*로 잘렸을 수 있고, 그걸 지우면 새 거짓말이다
         (`_carry_flags` 의 truncated=OR 승계와 같은 방향).
      ② `total` 은 **지어내지 않는다** — 없으면 없는 채로 둔다. 이것은 `_carry_flags` 의
         join 조항("지어낸 total 은 또 다른 거짓말")을 단항에 그대로 적용한 것.
         그래서 take 가 아무 신고도 안 뿌리는 경우가 남는데, **침묵은 거짓말이 아니다** —
         고치는 것은 `truncated: false` 라는 *적극적 거짓 주장*뿐이다.
      ③ 기수가 **변한** 변환 뒤의 봉투 `summary` 는 변환 전 집계라 stale 이다.
         실측: `[sense:realty]{…} >> [table:groupby]{by: "법정동", agg: {평균가: ["avg", "거래금액"]}}`
         → items 는 법정동별 평균 14행인데 봉투는 `summary.평균가: "31,952만원"`(전체 평균)·
         `summary.총거래건수: 90` 을 그대로 들고 있다. `message`/`text` 를 여기서 떨어내는
         것과 **같은 부류**다(변환 전 집합을 서술하는 다이제스트).
         단, message/text 처럼 무조건이 아니라 **기수 변경 시에만** 지우는 이유:
         그 둘은 O(items) 산문이라 파이프 블로업까지 걸리지만, summary 는 작은 집계라
         유일한 문제가 stale 이고 그건 집합이 바뀌었을 때만 발생한다(sort·select 뒤엔 참).
         → 오폭을 피하면서 거짓말만 정확히 지운다.
    """
    tot = out.get("total")
    if isinstance(tot, int) and not isinstance(tot, bool) and tot > new_len:  # vj-ok: 봉투 계수 비교
        out["truncated"] = True
    if prior_len is not None and prior_len != new_len and isinstance(out.get("summary"), (dict, str)):  # vj-ok: 봉투 계수 비교
        out.pop("summary", None)
    return out
