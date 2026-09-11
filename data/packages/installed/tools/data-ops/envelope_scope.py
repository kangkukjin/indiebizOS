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


def _restate_scope(out, prior_len, new_len, *, population=False):
    """현재 집합의 기수와 원천 잘림을 구분한다(2026-09-08 언어 개정).

    filter/dedup/groupby/since/flatten/중복 병합은 집합을 다시 정의하므로,
    기존 total이 있으면 결과 기수로 바꾼다. 그 자체로 truncated를 켜지 않는다.
    이미 켜진 상류 truncated는 보존한다. 불완전 입력에서 만든 결과의 total은
    관측된 결과 기수이며, 아직 수집하지 않은 원천의 결과 수를 뜻하지 않는다.
    take와 행 보존 변환은 기존 total을 유지한다. total 없는 봉투에 추정치를
    만들지 않으며, 상류가 total > 입력 행수인데 표지를 빠뜨렸으면 보완한다.
    """
    tot = out.get("total")
    known = isinstance(tot, int) and not isinstance(tot, bool)
    if population:
        if known:
            if prior_len is not None and tot > prior_len:  # vj-ok: 봉투 계수 비교
                out["truncated"] = True
            out["total"] = new_len
    elif known and tot > new_len:  # vj-ok: 봉투 계수 비교
        if not out.get("truncated") and prior_len == tot:
            # 온전한 입력을 요청한 개수로 줄인 표본. 수집 절단과 구분해 증류로 보낸다.
            out["truncations"] = [{"scope": "selection", "unit": "rows",
                                   "retained": new_len, "total": tot}]
        out["truncated"] = True
    if (population or (prior_len is not None and prior_len != new_len)) and isinstance(out.get("summary"), (dict, str)):
        out.pop("summary", None)
    return out


def invalidate_derived_checks(out, originals, new_rows):
    """Checks and AI row counters describe their own input revision, not later rows."""
    from common.value_semantics import values_equal
    original = next((o for o in originals if isinstance(o, list)), None)
    if original is None or values_equal(original, new_rows):
        return out
    fields = ("criteria_verdict", "criteria_feedback", "criteria_attempts", "rows_in",
              "rows_out", "rows_dropped", "_merge")
    upstream = {k: out.pop(k) for k in fields if k in out}
    if upstream:
        import hashlib
        import json
        revision = hashlib.sha256(json.dumps(original, ensure_ascii=False,
            sort_keys=True, default=str).encode()).hexdigest()
        out["_upstream_check"] = {"checks": upstream, "input_hash": revision,
                                  "applies_to": "previous_items"}
    return out
