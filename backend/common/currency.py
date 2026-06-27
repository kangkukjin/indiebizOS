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


def derive_items(result: Any) -> Any:
    """옛 통화 형태에서 단일 통화 `items`를 파생한다 (전환기 choke-point 정규화).

    모든 패키지 핸들러 결과가 거치는 한 곳(ibl_routing._route_handler)에서 호출되어,
    ~22개 records 생산자 + table/blocks 생산자가 *생산자를 건드리지 않고* items를 함께
    노출하게 한다(핸드오프 §8.1 "일괄 dual-emit"을 choke point 한 곳에서 = §2 거버넌스:
    동기화 지점 N→0; 생산자는 옛 키만, items는 파생; 컷오버 후 무동작→제거).

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
