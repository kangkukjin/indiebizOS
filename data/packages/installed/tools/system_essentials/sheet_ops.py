"""[self:sheet] — 살아있는 엑셀 장부 부분 편집 (find / append / update).

시장 실측(ep951)의 수요 실체는 새 파일 생성이 아니라 **기존 장부**(재고·입출고·근태·연차)에
행을 더하고 셀을 고치는 일이다. [table:spreadsheet]는 통째 새로 쓰기라 기존 파일에 쓰면
수식·서식·다른 시트가 날아간다. 여기는 openpyxl 로 열어 부분만 만지고 원자 교체로 저장 —
수식·서식·병합·다른 시트가 보존된다. .xlsm 은 keep_vba 로 매크로도 보존.

★한계(가이드 sheet.md 명기): openpyxl 은 차트·이미지를 저장 시 유실한다. 차트가 든 장부는
데이터 시트와 차트 시트를 분리해 두는 것이 안전하다.

핸들러 계약: handler.py 의 op 디스패처가 tool_input 에 _project_path(상대경로 해석)와
_path_guard(쓰기 범위 검증 함수)를 주입해 부른다. 반환은 JSON 직렬화 가능한 dict.
"""
import os
from datetime import date, datetime, time
from pathlib import Path


# ── 공통 ──────────────────────────────────────────────────────────

def _resolve(tool_input):
    """(Path, err) — path 파라미터 해석. 상대경로는 _project_path 기준."""
    raw = tool_input.get("path") or tool_input.get("file_path") or ""
    if not raw:
        return None, {"success": False, "error": "path 가 필요합니다 — 대상 xlsx/xlsm 파일 경로."}
    p = Path(str(raw))
    if not p.is_absolute():
        p = Path(tool_input.get("_project_path") or ".") / p
    if not p.exists():
        return None, {"success": False, "error": f"파일을 찾을 수 없습니다: {p}"}
    if p.suffix.lower() not in (".xlsx", ".xlsm"):
        return None, {"success": False,
                      "error": f"xlsx/xlsm 만 지원합니다: {p.name} — 새 파일 생성은 [table:spreadsheet], 읽기는 [self:read]."}
    return p, None


def _open(p):
    import openpyxl
    # data_only=False(기본) — 수식 원문 보존이 이 액션의 존재 이유
    return openpyxl.load_workbook(str(p), keep_vba=(p.suffix.lower() == ".xlsm"))


def _pick_sheet(wb, tool_input):
    sn = tool_input.get("sheet")
    if sn:
        if sn not in wb.sheetnames:
            return None, {"success": False,
                          "error": f"시트가 없습니다: {sn} — 이 파일의 시트: {', '.join(wb.sheetnames)}"}
        return wb[sn], None
    return wb.active, None


def _headers(ws, header_row):
    """{헤더명: 열번호} — header_row 의 비어있지 않은 셀."""
    hmap = {}
    for c in range(1, (ws.max_column or 0) + 1):
        v = ws.cell(row=header_row, column=c).value
        if v is not None and str(v).strip():
            hmap[str(v).strip()] = c
    return hmap


def _last_data_row(ws, hmap, header_row):
    """매핑된 열 기준 마지막 값 행 — max_row 는 서식만 있는 유령 행도 세므로 직접 훑는다."""
    last = header_row
    for r in range(header_row + 1, (ws.max_row or header_row) + 1):
        if any(ws.cell(row=r, column=c).value is not None for c in hmap.values()):
            last = r
    return last


def _match(cell_val, want):
    """문자열 정규화 동치 + 숫자 동치(쉼표 허용) — '3500' == 3500 == '3,500'."""
    a = "" if cell_val is None else str(cell_val).strip()
    b = "" if want is None else str(want).strip()
    if a == b:
        return True
    try:
        return float(a.replace(",", "")) == float(b.replace(",", ""))
    except (ValueError, TypeError):
        return False


def _jsonable(v):
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    return v


def _validate_keys(keys, hmap, what):
    unknown = [k for k in keys if k not in hmap]
    if unknown:
        return {"success": False,
                "error": f"{what}에 없는 열: {', '.join(unknown)} — 이 시트의 열: {', '.join(hmap)} "
                         f"(header_row 가 다르면 header_row 파라미터로 지정)"}
    return None


def _guard(tool_input, p):
    """쓰기 op 경로 가드 — handler 의 _validate_path_in_scope 주입분."""
    g = tool_input.get("_path_guard")
    if callable(g):
        err = g(str(p), tool_input.get("_project_path") or str(p.parent))
        if err:
            return {"success": False, "error": err}
    return None


def _save(wb, p):
    """원자 교체 저장 — 살아있는 장부를 반쪽 파일로 만들지 않는다."""
    tmp = p.with_name(p.name + ".tmp~")
    wb.save(str(tmp))
    os.replace(tmp, p)


def _prep(tool_input, need_where=False):
    """(ctx dict, err) — 공통 준비: 경로/워크북/시트/헤더/where 검증."""
    p, err = _resolve(tool_input)
    if err:
        return None, err
    try:
        header_row = int(tool_input.get("header_row", 1) or 1)
    except (TypeError, ValueError):
        header_row = 1
    wb = _open(p)
    ws, err = _pick_sheet(wb, tool_input)
    if err:
        wb.close()
        return None, err
    hmap = _headers(ws, header_row)
    if not hmap:
        wb.close()
        return None, {"success": False,
                      "error": f"{header_row}행에 헤더가 없습니다 — 헤더가 다른 행이면 header_row 로 지정."}
    where = tool_input.get("where") or {}
    if not isinstance(where, dict):
        wb.close()
        return None, {"success": False, "error": "where 는 {열이름: 값} 형태의 객체여야 합니다."}
    if need_where and not where:
        wb.close()
        return None, {"success": False,
                      "error": "update 는 where({열: 값})가 필수입니다 — 전행 갱신 사고 방지. 먼저 op:find 로 대상 행을 확인하세요."}
    err = _validate_keys(where.keys(), hmap, "where")
    if err:
        wb.close()
        return None, err
    return {"p": p, "wb": wb, "ws": ws, "hmap": hmap, "header_row": header_row, "where": where}, None


def _matched_rows(ctx):
    ws, hmap, where = ctx["ws"], ctx["hmap"], ctx["where"]
    last = _last_data_row(ws, hmap, ctx["header_row"])
    for r in range(ctx["header_row"] + 1, last + 1):
        if all(_match(ws.cell(row=r, column=hmap[k]).value, v) for k, v in where.items()):
            yield r


# ── op 구현 ───────────────────────────────────────────────────────

def op_find(tool_input):
    """조건으로 행 검색 — where 생략 시 전체 (limit 기본 50). items 에 _row(행 번호) 포함."""
    ctx, err = _prep(tool_input)
    if err:
        return err
    try:
        limit = int(tool_input.get("limit", 50) or 50)
    except (TypeError, ValueError):
        limit = 50
    ws, hmap = ctx["ws"], ctx["hmap"]
    items, matched = [], 0
    for r in _matched_rows(ctx):
        matched += 1
        if len(items) < limit:
            item = {"_row": r}
            for name, c in hmap.items():
                item[name] = _jsonable(ws.cell(row=r, column=c).value)
            items.append(item)
    ctx["wb"].close()
    return {"success": True, "sheet": ws.title, "columns": list(hmap),
            "matched": matched, "items": items,
            **({"note": f"{matched}건 중 {limit}건만 (limit 로 조정)"} if matched > limit else {})}


def _items_from_prev(tool_input):
    """파이프 결합: items 미지정 시 직전 step 결과에서 items 또는 table{columns,rows}를 취한다."""
    import json as _json
    prev = tool_input.get("_prev_result") or ""
    if not prev:
        return None
    try:
        data = _json.loads(prev) if isinstance(prev, str) else prev
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("items"), list) and data["items"]:
        return [it for it in data["items"] if isinstance(it, dict)]
    tbl = data.get("table")
    if isinstance(tbl, dict) and tbl.get("columns") and isinstance(tbl.get("rows"), list):
        cols = [str(c) for c in tbl["columns"]]
        return [dict(zip(cols, row)) for row in tbl["rows"]]
    return None


def op_append(tool_input):
    """마지막 데이터 행 뒤에 행 추가 — 기존 수식·서식 불변. 값이 "=..." 문자열이면 수식으로 들어간다."""
    items = tool_input.get("items")
    if isinstance(items, dict):
        items = [items]
    if not items:
        items = _items_from_prev(tool_input)
    if not items or not isinstance(items, list):
        return {"success": False,
                "error": "items 가 필요합니다 — [{열이름: 값}, …] 목록 (또는 파이프 직전 step 의 items/table 자동 사용)."}
    items = [it for it in items if isinstance(it, dict) and it]
    if not items:
        return {"success": False, "error": "items 에 유효한 행({열이름: 값})이 없습니다."}

    ctx, err = _prep(tool_input)
    if err:
        return err
    p, wb, ws, hmap = ctx["p"], ctx["wb"], ctx["ws"], ctx["hmap"]
    err = _guard(tool_input, p)
    if err:
        wb.close()
        return err
    all_keys = {k for it in items for k in it if not str(k).startswith("_")}
    err = _validate_keys(all_keys, hmap, "items")
    if err:
        wb.close()
        return err

    start = _last_data_row(ws, hmap, ctx["header_row"]) + 1
    for i, it in enumerate(items):
        for k, v in it.items():
            if str(k).startswith("_"):
                continue
            ws.cell(row=start + i, column=hmap[k], value=v)
    _save(wb, p)
    wb.close()
    return {"success": True, "sheet": ws.title, "appended": len(items),
            "rows": f"{start}~{start + len(items) - 1}", "path": str(p)}


def op_update(tool_input):
    """where 로 찾은 행들의 set({열: 값}) 셀 수정 — where 필수(전행 갱신 방지)."""
    set_map = tool_input.get("set") or {}
    if not isinstance(set_map, dict) or not set_map:
        return {"success": False, "error": "set 이 필요합니다 — {열이름: 새값}."}

    ctx, err = _prep(tool_input, need_where=True)
    if err:
        return err
    p, wb, ws, hmap = ctx["p"], ctx["wb"], ctx["ws"], ctx["hmap"]
    err = _guard(tool_input, p)
    if err:
        wb.close()
        return err
    err = _validate_keys(set_map.keys(), hmap, "set")
    if err:
        wb.close()
        return err

    rows = list(_matched_rows(ctx))
    if not rows:
        wb.close()
        return {"success": False, "matched": 0,
                "error": f"일치하는 행이 없습니다 — op:find 로 where 값을 먼저 확인하세요. 이 시트의 열: {', '.join(hmap)}"}
    for r in rows:
        for k, v in set_map.items():
            ws.cell(row=r, column=hmap[k], value=v)
    _save(wb, p)
    wb.close()
    return {"success": True, "sheet": ws.title, "matched": len(rows),
            "updated_rows": rows[:20], "set": {k: _jsonable(v) for k, v in set_map.items()},
            "path": str(p)}
