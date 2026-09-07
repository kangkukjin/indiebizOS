"""currency.py — IBL 단일 통화 생성자.

통화는 하나뿐이다:

    {"items": [ { …열린 필드… }, … ]}

구조적으로 강제되는 계약은 **바깥 형태 하나** — "컬렉션은 items 목록이다" — 뿐이다.
항목 내부(title 포함)는 전부 *관습*이며 강제하지 않는다. (필수 필드 레지스트리·title 추측
같은 건 유지·동기화해야 할 상태를 늘리므로 일부러 두지 않는다 — 그게 통화가 N개로 늘던
병의 뿌리였다.)

왜 바깥 형태 하나면 충분한가: 통화의 목적은 "모든 소비자(take/filter/chart/map/document)가
컬렉션을 *어떻게 찾고 순회할지* 안다"이다. 그걸 보장하는 건 {items:[…]} 하나면 된다.
항목 안은 도메인마다 다르고, 달라도 된다 — 소비자는 아는 필드만 읽고 모르면 신호한다.

옛 형태는 전부 이 하나의 view 다:
  - records  → items (title은 가장 흔한 관습일 뿐)
  - table    → 같은 칸을 공유하는 items (소비자가 열로 봄)
  - map      → lat/lng 단 items (지도가 핀/선으로 봄; center/zoom은 bounds에서 유도)
  - document → type/text 단 items (depth 필드로 중첩)
  - 단일값   → items 길이 1

전환기(dual-emit) 사용법 — 옛 키를 유지하면서 items를 함께 낸다:
    return {**old_output, **items(rows)}
완전 컷오버 후 옛 키 분기를 삭제한다.
"""

import json
from typing import Any, Iterable


def items(rows: Iterable[Any] = (), **wrapper) -> dict:
    """행들을 단일 통화로 감싼다.

    Args:
        rows: 항목들(보통 dict). 비어도/1개여도 목록.
        **wrapper: success/message/source 등 래퍼 필드(선택). 통화 자체는 아님.

    Returns:
        {"items": [...], **wrapper}. 유일한 보장은 바깥의 items 목록.
        항목 내부는 손대지 않는다(열림).
    """
    out = {"items": list(rows) if rows is not None else []}
    if wrapper:
        out.update(wrapper)
    return out


def coerce_json_param(value: Any) -> Any:
    """param 자리의 JSON 문자열을 원형(list/dict)으로 — `$변수` 치환은 문자열을 넣는다.

    ★B19-2 부류의 범용 게이트 (2026-08-27): items 는 coerce_items_payload 가 맡지만,
    blocks 의 columns/rows 처럼 **items 가 아닌 구조 param** 도 같은 병을 앓는다
    (실측: `columns: "$표.columns"` 가 JSON 문자열로 들어가 렌더러가 문자 단위로
    쪼갰다). 판정은 보수적으로 — JSON 으로 안 읽히면 문자열 그대로(텍스트를 뺏지
    않는다). 호출자는 구조를 기대하는 자리에만 쓸 것."""
    if isinstance(value, str):
        s = value.strip()
        if s[:1] in "{[":
            try:
                return json.loads(s)
            except Exception:
                pass
    return value


def coerce_items_payload(value: Any) -> Any:
    """params 로 **직접 받은** 통화 페이로드를 행 목록으로 되읽는다 (없으면 None).

    `[table:reduce]{items: "$r.items"}` 처럼 변수 치환이 통화를 **JSON 문자열**로 넣는
    경로가 있어서, 소비자마다 문자열을 읽고/못 읽고가 갈렸다 — 같은 문장이 take 에서는
    통과하고 reduce·brief 에서는 "통화를 찾지 못했습니다" 로 죽었다(2026-08-22 상상훈련
    19회차 B19-2). 어휘가 약속한 입력은 모든 소비자가 **같은 눈**으로 읽어야 한다.

    받는 모양: list(그대로) · {"items": [...]} 봉투 · 그 둘의 JSON 문자열.
    그 밖(빈 문자열·JSON 아님·스칼라)은 None — 호출자의 기존 진단 경로를 그대로 둔다.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        rows = value.get("items")
        if isinstance(rows, list):
            return rows
        # ★2026-08-27: `$변수` 가 **파이프 결과**를 담고 있으면 items 가 없다.
        #   파이프 이음매만 통화를 파생하고(`_to_prev_currency`) step_results 는 "원형 유지
        #   = 토큰 중복 0" 인데, 그 저장소가 $변수 슬롯을 겸하기 때문이다. 실측:
        #     $표 = [sense:host]{…} >> [table:select]{columns:["cpu_percent"]}
        #     [table:brief]{items: "$표"}   → "입력 통화가 없습니다"  (변수엔 columns/rows 만)
        #     $단일 = [sense:host]{…}
        #     [table:brief]{items: "$단일"} → 정상            (생산자가 items 를 직접 방출)
        #   같은 문장이 앞 단계의 모양에 따라 되고 안 되는 것은 통화의 약속이 아니다.
        #   모양 판정은 여기서 다시 알아보지 않고 **몸의 단일 게이트**에 위임한다.
        derived = derive_items(dict(value)).get("items")
        return derived if isinstance(derived, list) else None
    if isinstance(value, str):
        s = value.strip()
        if not s or s[0] not in "[{":
            return None
        try:
            import json as _json
            return coerce_items_payload(_json.loads(s))
        except Exception:
            return None
    return None


def stamp_success(value: Any) -> Any:
    """봉투에 `success` 를 채운다 — **모든 라우터가 공유하는 결과 계약** (2026-09-07, 사용자 판정).

    비대칭이 있었다: 실패는 `success: false` 를 말하는데 성공은 아무 말도 안 하는 낱말이
    많았다(정적 스윕 42함수 · 실측 `shape="dict"` 성공 봉투 296건/10액션). 그래서
    `resp.get("success")` 로 판정한 쪽은 **성공을 실패로 읽는다** — 실측 사고: 성공한
    `[self:memory]{op:"save"}` 를 실패로 읽고 같은 요청을 다시 보내 기억 원장에 같은
    내용이 두 행 생겼다(2026-09-07 추적).

    엔진 경계와 패키지가 **같은 한 벌**을 쓴다(판정기는 하나) — 규약 넷:
      · 딕셔너리 봉투는 success 를 **맨 앞에** — 사람도 모델도 첫 줄에서 결과를 본다
      · 이미 success 가 있으면 손대지 않는다(제 값을 가진 낱말이 이긴다)
      · `error` 가 실려 있으면 false — 엔진의 성공 판정(`result.get("error")` 참이면 실패)과
        같은 규칙이라 두 곳이 갈라지지 않는다
      · **산문·목록 통화는 감싸지 않는다** — 통화가 문자열·배열인 자리를 봉투로 바꾸면
        통화 모양이 달라지고 하류가 받는 것이 바뀐다

    ★이 함수는 **실패를 참으로 물들이면 안 된다**: 다른 필드로만 실패를 말하는 봉투
    (`{"deleted": false, "message": "삭제 실패"}` 류)는 낱말 쪽에서 error 로 고쳐야 한다.
    경계 실측으로 그런 자리를 훑어 memory:delete 하나를 먼저 닫았다(2026-09-07).
    """
    if isinstance(value, dict):
        if "success" in value:
            return value
        stamped = {"success": not value.get("error")}
        stamped.update(value)
        return stamped
    if isinstance(value, str):
        text = value.lstrip()
        if not text.startswith("{"):
            return value                    # 산문·목록 통화 — 봉투가 아니다
        import json as _json
        try:
            obj = _json.loads(value)
        except Exception:
            return value
        if not isinstance(obj, dict) or "success" in obj:
            return value
        stamped = {"success": not obj.get("error")}
        stamped.update(obj)
        return _json.dumps(stamped, ensure_ascii=False)
    return value


def effect_row(envelope: Any, drop: Iterable[str] = ()) -> dict:
    """효과·스칼라 봉투 → **행 하나** (2026-09-06 언어 개정 G55-1, 단일 승격기).

    `[a] & [b] >> [table:union]` 은 효과 봉투(items/table 없는 success dict — write·notify·
    arch_report 의 결과)를 분기당 1행으로 받았는데(09-05, effect_rows), 같은 봉투를
    `[table:each]` 는 버리고 원 행만 흘렸다(55회차 실측 — 면적표 2건·도면 4장을 계산·생성하고
    값만 폐기). 두 조합자가 같은 봉투를 정반대로 다루던 자리라, 승격 규칙을 **한 함수**로
    두고 둘이 함께 부른다: 내부 표지(`_…`)는 행이 아니다 · 출처를 지어내지 않는다 ·
    dict 가 아닌 스칼라(문자열·수)는 `value` 한 칸.
    `drop` — 소비자가 자기 계약상 잉여인 키를 뺀다(each 는 성공·실패를 봉투가 이미 가르므로 success).
    """
    if isinstance(envelope, dict):
        skip = set(drop)
        return {k: v for k, v in envelope.items()
                if not str(k).startswith("_") and k not in skip}
    return {"value": envelope}


def currency_shape_note(envelope: Any) -> str:
    """'받은 봉투' 진단 문자열 — each·reduce 가 공유한다 (B19-2).

    키만 찍으면 "items 통화를 찾지 못했습니다. 받은 봉투: ['items']" 라는 자기모순이 난다.
    items 자리에 무엇이 왔는지(타입·미리보기)까지 말해야 진단이 사람·모델에게 닿는다.

    ★2026-08-22 (F20-3 후속, 세 번째 소비자가 붙으며 드러남): **JSON 문자열도 판다**.
    each·reduce 는 이미 파싱한 봉투를 넘겨서 안 드러났지만, `_prev_result` 를 날것으로
    쥔 소비자(system_essentials copy)가 부르면 진단이 통째로 `str` 한 글자였다 — 진단이
    "무엇이 왔는지"를 말해야 하는데 "문자열이 왔다"만 말하는 건 안 판 것과 같다.
    """
    if isinstance(envelope, str):
        s = envelope.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                envelope = json.loads(s)
            except Exception:
                pass                      # JSON 아닌 문자열 — 아래 타입 이름 경로로
    if isinstance(envelope, list):
        return f"목록({len(envelope)}행) — 봉투가 아니라 행 목록" + _non_row_note(envelope)
    if isinstance(envelope, dict):
        keys = list(envelope.keys())[:8]
        payload = envelope.get("items")
        if payload is not None and not isinstance(payload, list):
            preview = str(payload)
            if len(preview) > 60:
                preview = preview[:60] + "…"
            return (f"{keys} — items 자리에 목록이 아니라 "
                    f"{type(payload).__name__}({len(str(payload))}자)가 있습니다: {preview}")
        if isinstance(payload, list):
            return str(keys) + _non_row_note(payload)
        return str(keys)
    if isinstance(envelope, str):
        preview = envelope if len(envelope) <= 60 else envelope[:60] + "…"
        return f"str({len(envelope)}자): {preview}"
    return type(envelope).__name__


def _non_row_note(rows: list) -> str:
    """목록은 왔는데 행이 dict 가 아닐 때(스칼라 목록 등) 그 사실을 덧붙인다 (2026-09-03).

    `$본.names >> [table:spreadsheet]` 처럼 스칼라 배열 필드를 통화로 방출하면 봉투는
    `{items:["a","b"]}` 로 멀쩡해 보이지만 표 소비자는 dict 행만 읽어 0행이 된다. 그때
    진단이 "받은 입력: ['items']" 로 끝나면 자기모순이다 — 키가 아니라 행의 타입을 말해야
    사람·모델이 앞 단계를 고칠 수 있다.
    """
    if not rows:
        return ""
    bad = [r for r in rows if not isinstance(r, dict)]
    if not bad:
        return ""
    kinds = sorted({type(r).__name__ for r in bad})
    preview = str(bad[:3])
    if len(preview) > 60:
        preview = preview[:60] + "…"
    return (f" — items {len(rows)}행 중 {len(bad)}행이 행(dict)이 아니라 "
            f"{'/'.join(kinds)} 입니다: {preview}")


def derive_items(result: Any) -> Any:
    """옛 통화 형태에서 단일 통화 `items`를 파생한다 (전환기 choke-point 정규화).

    ★호출처 3곳 (2026-08-05 감사 D13에서 문서 정정 — 옛 문서는 _route_handler 한 곳이라
    적었으나 실제로 그곳엔 없었고, 일부러 안 둔다):
      1) api_ibl /ibl/execute — 렌더러 경계(앱/수동/원격/폰 표면)
      2) body_ask — 몸 간 부탁 통화
      3) workflow_engine._to_prev_currency — **파이프 이음매**(prev_result 로 다음 step 에
         물릴 때만). table/blocks 생산자가 `>> [table:*]` 소비자에 바로 물리게 한다.
      4) ibl_envelope._derived_items — 봉투 요약의 **shape 판정에만**(2026-08-23 B27-1).
         파생본은 봉투에 싣지 않으므로 위 토큰 중복 회피와 충돌하지 않는다: 3)이 items 를
         파생해 줄 봉투를 요약이 "effect" 라 부르던 자기모순을 없앤다.
    _route_handler(에이전트 최종 tool-result 포함 전체)에 두지 않는 이유: 파생본이 모델에게
    가는 결과에도 실려 토큰이 중복된다 — 에이전트 경로의 의도된 회피(api_ibl 주석 참조).

    이미 items(list)면 보존(생산자 직접 방출 우선). 그 외엔 아래 순서로 *단방향* 파생:
      1) table(columns+rows / table봉투) → items = 행 dict들 (소비자가 열로도 봄)
      2) blocks (document)              → items = blocks (type/text 항목)
    어느 것도 없으면 무동작(효과·스칼라는 통화 아님).
    ★records 분기는 제거됨(2026-06-27 컷오버 완료 — records 생산자 0). 잔존 table/blocks 파생은
    returns:scalar/effect 인데 부가로 table(stock)·blocks(read/report) 방출하는 straggler 표시용.

    ★map_data는 일부러 제외: 봉투 구조가 생산자마다 다르다(위치=markers / 경로=origin·
    destination·route geometry). 균일 파생이 불가하고, 지도 위젯이 봉투를 직접 읽으므로
    여기서 손대지 않는다(핸드오프 §3이 map을 특수 케이스로 인정).

    ★역방향 금지(items→records 등): `items`는 일부 생산자가 *비통화 raw*로 쓰는 과적
    키라(§7.5) 통화로 신뢰할 수 없다. records/table/blocks는 명백한 통화라 안전.

    무상태·파생이므로 컷오버(생산자가 items 직접 방출, 옛 키 제거) 후 이 함수는 무동작이
    되고 제거된다.
    """
    if not isinstance(result, dict):
        return result
    if isinstance(result.get("items"), list):
        return result  # 생산자 직접 방출 items 보존

    # 1) table — top-level columns/rows 또는 table 봉투 → 행 dict들 (stock 등 scalar 부가)
    cols = result.get("columns")
    rows = result.get("rows")
    t = result.get("table")
    if isinstance(t, dict):
        cols = t.get("columns")
        rows = t.get("rows")
    if isinstance(cols, list) and isinstance(rows, list):
        result["items"] = [
            {str(c): (row[i] if i < len(row) else None) for i, c in enumerate(cols)}
            for row in rows if isinstance(row, (list, tuple))
        ]
        return result

    # 2) blocks — document 통화(type/text 항목 목록, read/report 등 scalar/effect 부가)
    b = result.get("blocks")
    if isinstance(b, list):
        result["items"] = b
        return result

    return result


def normalize_cell(v: Any, none: Any = None) -> Any:
    """표 셀 값의 타입 정규화 **한 벌** — 독자들이 같은 눈으로 (F53-3, 2026-09-02).

    같은 xlsx 셀 "92,000" 을 `[self:read]` 는 92000(숫자)으로, `[self:sheet]{find}` 는 문자열로
    냈다(53회차 실측) — filter 는 수치 강제로 둘 다 통과했지만 compute/reduce 는 갈린다.
    규칙(read_xlsx 의 옛 `_num` 을 승격): 숫자는 그대로 · 날짜류는 isoformat · 쉼표 있는 숫자
    문자열은 int→float 순으로 · 수식("=…")·그 밖의 문자열은 그대로. `none` = 결측의 표기
    (표형 rows 는 "" 를, 행 dict 는 None 을 쓴다 — 호출부 규약 유지).
    """
    if v is None:
        return none
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if s and (s[0].isdigit() or (s[0] in "-+." and len(s) > 1 and s[1].isdigit())):
            try:
                return int(s)
            except ValueError:
                try:
                    return float(s)
                except ValueError:
                    pass
    return v
