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
        return f"목록({len(envelope)}행) — 봉투가 아니라 행 목록"
    if isinstance(envelope, dict):
        keys = list(envelope.keys())[:8]
        payload = envelope.get("items")
        if payload is not None and not isinstance(payload, list):
            preview = str(payload)
            if len(preview) > 60:
                preview = preview[:60] + "…"
            return (f"{keys} — items 자리에 목록이 아니라 "
                    f"{type(payload).__name__}({len(str(payload))}자)가 있습니다: {preview}")
        return str(keys)
    if isinstance(envelope, str):
        preview = envelope if len(envelope) <= 60 else envelope[:60] + "…"
        return f"str({len(envelope)}자): {preview}"
    return type(envelope).__name__


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
