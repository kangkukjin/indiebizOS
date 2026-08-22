"""
ibl_exec_each.py — [table:each] 실행기(행마다 $it 치환 → 파이프 실행) + 입력 통화 추출.

2026-08-23 ibl_executors.py 에서 이사(1500줄 규칙). 재수출 = ibl_executors.
"""
import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from common.currency import currency_shape_note


# ── [table:each] — 문장을 값으로 받는 유일한 변환자 (2026-08-15 고차 문장 M2) ──────────
# 왜 이 낱말이 필요했나: table 의 다른 13 변환자는 전부 데이터→데이터라, "찾은 것 *각각에*
# 대해 ~해라"를 이 언어로 쓸 방법이 없었다. 그래서 문장이 늘 "가져와서 정리해 사람에게"
# 2단에서 끝났고(코퍼스 실측: 파이프 평균 길이 2.45·2단이 72%), 항목 단위 싱크
# (notify_user·channel_send·delegate·publish)는 파이프에 한 번도 들어오지 못했다
# (미조합 액션 68/150 의 다수가 이 부류). 설계 정본: docs/HIGHER_ORDER_SENTENCE_DESIGN.md
_EACH_DEFAULT_LIMIT = 20

# 스칼라 행(문자열·숫자)을 dict 로 감쌀 때 쓰는 필드 이름.
# ★출력 감싸기와 $it 치환이 *같은* 이름을 봐야 한다 — 두 자리가 어긋나면
#   결과 행이 `{"value": "가", "_error": "행에 없는 필드: value"}` 처럼
#   필드를 보여주면서 없다고 말하는 자기모순이 난다(2026-08-17 실측 버그).
_EACH_SCALAR_FIELD = "value"
_EACH_MAX_SUBSTEPS = 200


def _each_escape(value: Any) -> str:
    """치환 값을 IBL 문자열 리터럴 안에 안전하게 넣을 형태로 만든다.

    파서(`ibl_parser_values._extract_string`)는 따옴표 안에서 `\\` 다음 글자를 리터럴로
    받으므로, 백슬래시와 양쪽 따옴표만 이스케이프하면 '…' / "…" 어느 쪽에 놓여도 문자열이
    조기 종료되지 않는다(제목에 따옴표가 든 행이 문장을 깨뜨리던 부류의 차단).
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        s = json.dumps(value, ensure_ascii=False)
    else:
        s = str(value)
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")


def _each_substitute(sentence: str, row: Any, var: str) -> Tuple[str, list]:
    """문장 안의 `$it.필드` / `$it` 를 행 값으로 치환. 반환: (치환된 문장, 없는 필드 목록).

    ★없는 필드는 조용히 빈 값으로 만들지 않고 목록으로 돌려준다 — 호출자가 그 행을
    실패로 표시한다(빈 문자열로 밀어 넣으면 "성공처럼 보이는 오동작"이 된다).
    ★필드 패턴은 유니코드(`[^\\W\\d]\\w*`) — 옛 `[A-Za-z_]` 전용은 `$it.없는필드` 같은
    한글 필드가 매칭 밖이라 `$it` 만 치환되고 `.필드` 가 리터럴 잔존했다(F14-1, 14회차 실측:
    빈/쓰레기 쿼리가 _ok:true 로 완주).
    """
    missing: list = []

    def _sub(m):
        # group(1)=괄호형 경로(`${it.title}`), group(2)=맨몸 경로(`$it.title`)
        field = ((m.group(1) if m.group(1) is not None else m.group(2)) or "").lstrip(".")
        if not field:
            return _each_escape(row)
        if isinstance(row, dict):
            if field not in row:
                missing.append(field)
                return m.group(0)
            return _each_escape(row.get(field))
        # 스칼라 행: 호출자가 출력에서 {_EACH_SCALAR_FIELD: row} 로 감싸므로
        # `$it.value` 도 그 값 자체로 푼다(`$it` 와 같은 뜻). 그 밖의 필드는 정직하게 없음.
        if field == _EACH_SCALAR_FIELD:
            return _each_escape(row)
        missing.append(field)
        return m.group(0)

    from common.ibl_vars import ref_pattern
    pattern = re.compile(ref_pattern(var))
    return pattern.sub(_sub, sentence), missing


def _each_foreign_vars(do: str, var: str) -> list:
    """do 문장 안에서 **해석되지 않을** `$변수` 이름 목록 (F14-1, 2026-08-20 14회차).

    행 참조(`$<var>`)·예약어 `$items`·do 안에서 자기 할당된 변수는 정상.
    그 밖의 `$이름` 은 어떤 행에서도 치환되지 않고 리터럴로 하류에 흘러간다 —
    14회차 실측: `as:"google"` 지정 후 `$it.title` 이 통째로 구글 검색어가 되어
    무관한 결과 30건이 success 로 완주했다(유령 변수의 침묵 통과).
    ★외부 파이프의 `$변수` 는 each 실행 전에 상위 해석기가 이미 치환하므로,
    여기 남은 것은 전부 오타/참조명 불일치다.
    """
    from common.ibl_vars import REF_RE, split_ref
    # 자기 할당(`$x = …`) — 경계 판정만 표기 모듈로 옮기고, "= 뒤가 오면 할당" 이라는
    # 옛 규칙은 그대로 둔다(`==` 도 할당으로 세는 관용까지 포함 — 무회귀).
    assigned = set()
    for m in REF_RE.finditer(do):
        name, path = split_ref(m)
        if not path and re.match(r"\s*=", do[m.end():]):
            assigned.add(name)
    foreign = []
    for name, _path in (split_ref(m) for m in REF_RE.finditer(do)):
        if name == var or name == "items" or name in assigned or name[0].isdigit():
            continue
        if name not in foreign:
            foreign.append(name)
    return foreign


def _stamp_depth(steps: Any, depth: int) -> None:
    """파싱된 step 들에 중첩 깊이를 찍는다(병렬 branches·폴백 체인 포함)."""
    if not isinstance(steps, list):
        return
    for st in steps:
        if not isinstance(st, dict):
            continue
        st["_depth"] = depth
        for key in ("branches", "_fallback_chain", "body", "catch", "finally", "_branch_steps"):
            v = st.get(key)
            _stamp_depth(v if isinstance(v, list) else ([v] if isinstance(v, dict) else None), depth)


def _each_input_rows(params: dict) -> Tuple[Optional[list], Any]:
    """입력 통화(items)를 꺼낸다. 반환: (행 목록 또는 None, 파싱된 봉투).

    규약은 data-ops 변환자와 **같다**(2026-08-15 대칭 수리): 파이프 입력(`_prev_result`)이
    먼저이고, 그게 없을 때만 params 에서 통화를 직접 받는다 — 단독 호출·자가점검·
    리터럴 씨앗 지원. 옛 each 는 `_prev_result` 만 읽어, 다른 13 변환자가 전부 받는
    `items: [...]` 리터럴을 혼자 거부했다("받은 봉투: str"). 하필 문형을 곱셈으로 바꾸는
    유일한 고차 변환자가 항상 앞에 생산자를 요구하던 셈이다.
    """
    prev = params.get("_prev_result")
    # 스필 참조 봉투면 본문으로 (M5 자동 스필 — 소비자는 투명하게 읽는다)
    from common.spill import resolve_ref_str
    prev, _ref_err = resolve_ref_str(prev)
    if _ref_err:
        return None, {"error": _ref_err}
    obj = prev
    if isinstance(prev, str):
        s = prev.strip()
        obj = None
        if s.startswith("{") or s.startswith("["):
            try:
                obj = json.loads(s)
            except Exception:
                obj = prev          # JSON 아닌 문자열 — 아래에서 통화 없음으로 진단된다
        elif s:
            obj = prev
    if obj is None:                  # 파이프 입력 없음 → params 에서 통화 수용
        if params.get("items") is not None:
            # ★B19-2 (2026-08-22 상상훈련 19회차): `items: "$r.items"` 는 변수 치환이
            # 통화를 **JSON 문자열**로 넣는다. 옛 코드는 그 문자열을 그대로 items 자리에
            # 담아 "items 를 찾지 못했습니다 — 받은 봉투: ['items']" 라는 자기모순 거절이
            # 났다(같은 문장이 take 에선 통과 — 읽는 쪽이 갈렸다). 정본 =
            # common.currency.coerce_items_payload — data-ops·ai-ops 도 같은 눈을 쓴다.
            from common.currency import coerce_items_payload
            _rows = coerce_items_payload(params["items"])
            obj = {"items": _rows if _rows is not None else params["items"]}
        elif params.get("table") is not None:
            obj = {"table": params["table"]}

    if isinstance(obj, dict):
        from common.currency import derive_items
        obj = derive_items(obj)
        rows = obj.get("items")
        return (rows if isinstance(rows, list) else None), obj
    if isinstance(obj, list):
        return obj, obj
    return None, obj


def _execute_table_each(params: dict, project_path: str, agent_id: str = None) -> Any:
    """[table:each]{do, as, limit, on_error} — items 의 각 행에 IBL 문장을 적용.

    통화 계약: items → items. 각 출력 행 = 원 행 + `_ok` + (`_error` | `_result`).
    원 행을 보존하므로 `>> [table:filter]{where: {_ok: false}}` 로 실패만 추릴 수 있다.
    """
    from ibl_parser import parse as ibl_parse, IBLSyntaxError
    from workflow_engine import execute_pipeline

    do = params.get("do")
    if isinstance(do, list):
        do = "\n".join(str(x) for x in do if str(x).strip())
    if not do or not str(do).strip():
        return {"success": False, "items": [], "count": 0,
                "error": "each: do(각 행에 적용할 IBL 문장)가 필요합니다. "
                         "예) [table:each]{do: \"[self:notify_user]{message: '$it.title'}\"}"}
    do = str(do)
    var = (str(params.get("as") or "it").lstrip("$").strip()) or "it"

    # ★유령 변수 사전 차단 (F14-1): 어떤 행에서도 치환되지 않을 `$이름` 은 저작 오류라
    # 행 단위가 아니라 문장 단위로 즉시 거절한다 — 모든 행이 같은 이유로 실패할 운명이고,
    # 옛 동작(리터럴 잔존→하류 실행)은 "성공처럼 보이는 오동작"이었다.
    foreign = _each_foreign_vars(do, var)
    if foreign:
        return {"success": False, "items": [], "count": 0,
                "error": (f"each: do 안에 해석되지 않는 변수 "
                          f"{', '.join('$' + f for f in foreign)} — 행 참조 이름은 '${var}'"
                          f"{' (as 로 지정됨)' if var != 'it' else ''} 입니다. "
                          f"행 값은 '${var}.필드' 로 참조하세요.")}

    rows, envelope = _each_input_rows(params)
    if rows is None:
        shape = currency_shape_note(envelope)
        return {"success": False, "items": [], "count": 0,
                "error": f"each: 입력에서 items 통화를 찾지 못했습니다. 받은 봉투: {shape} — "
                         f"each 는 목록의 각 행에 문장을 적용합니다. 파이프(>>) 뒤에 놓거나, "
                         f"단독으로 쓰려면 items 를 직접 주세요. "
                         f'예: [table:each]{{items: [{{"city": "서울"}}], do: "[sense:weather]{{city: \'$it.city\'}}"}}'}

    try:
        limit = int(params.get("limit") if params.get("limit") is not None else _EACH_DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = _EACH_DEFAULT_LIMIT
    if limit < 0:
        limit = _EACH_DEFAULT_LIMIT
    on_error = str(params.get("on_error") or "continue").strip().lower()
    depth = int(params.get("_depth") or 0)

    target = rows[:limit]
    skipped = max(0, len(rows) - len(target))
    out_items: list = []
    ok_n = err_n = substeps = 0
    halted: Optional[str] = None

    for idx, row in enumerate(target):
        base = dict(row) if isinstance(row, dict) else {_EACH_SCALAR_FIELD: row}

        sentence, missing = _each_substitute(do, row, var)
        if missing:
            err_n += 1
            # 필드 힌트도 잘렸으면 잘렸다고 말한다 (F18-1 부류 — 침묵 클램프 금지):
            # 12개에서 끊긴 목록을 전부로 읽으면 있는 필드를 없다고 오판한다.
            if isinstance(row, dict):
                _names = sorted(row.keys())
                avail = (_names[:12] + [f"…외 {len(_names) - 12}개"]) if len(_names) > 12 else _names
            else:
                avail = [_EACH_SCALAR_FIELD]
            out_items.append({**base, "_ok": False,
                              "_error": (f"행에 없는 필드: {', '.join(sorted(set(missing)))} "
                                         f"(행 필드: {avail})")})
            if on_error == "stop":
                halted = "on_error"
                break
            continue

        try:
            steps = ibl_parse(sentence)
        except IBLSyntaxError as e:
            err_n += 1
            out_items.append({**base, "_ok": False, "_error": f"IBL 문법 오류: {e}"})
            if on_error == "stop":
                halted = "on_error"
                break
            continue

        substeps += len(steps)
        if substeps > _EACH_MAX_SUBSTEPS:
            halted = "budget"
            break

        _stamp_depth(steps, depth + 1)
        # each 의 do 는 *문자열*이라 행마다 새로 파싱된다 — 바깥에서 찍힌 워크플로우 호출
        # 스택이 여기서 끊기면, 워크플로우 → each → 자기 워크플로우 사슬이 가드를 우회한다.
        _wf_stack = params.get("_wf_stack")
        if _wf_stack:
            from workflow_contract import _stamp_wf_stack
            _stamp_wf_stack(steps, _wf_stack)
        try:
            res = execute_pipeline(steps, project_path, agent_id=agent_id)
        except Exception as e:  # 실행기 자체가 터진 경우도 행 단위로 정직하게
            res = {"success": False, "error": f"{type(e).__name__}: {e}"}

        final = res.get("final_result") if isinstance(res, dict) else res
        if isinstance(final, str):
            s2 = final.strip()
            if s2.startswith("{") or s2.startswith("["):
                try:
                    final = json.loads(s2)
                except Exception:
                    pass

        if isinstance(res, dict) and not res.get("success", True):
            err_n += 1
            out_items.append({**base, "_ok": False,
                              "_error": res.get("error") or "실행 실패",
                              "_result": final})
            if on_error == "stop":
                halted = "on_error"
                break
        else:
            ok_n += 1
            out_items.append({**base, "_ok": True, "_result": final})

    # 중단 시 남은 행은 '처리 안 함'으로 정직하게 집계 (조용히 사라지지 않게)
    if halted:
        skipped += len(target) - len(out_items)

    out: Dict[str, Any] = {
        "items": out_items,
        "count": len(out_items),
        "ok_count": ok_n,
        "error_count": err_n,
    }
    notes = []
    if params.get("collect") and out_items:
        # collect:true (M4 설계 §2.3-1) — 회차 결과(_result 의 items)를 이어붙인 하나의 items 로(= flatten 내장).
        flat: list = []
        for r in out_items:
            if not r.get("_ok"):
                continue
            fr = r.get("_result")
            if isinstance(fr, dict) and isinstance(fr.get("items"), list):
                flat.extend(fr["items"])
            elif isinstance(fr, list):
                flat.extend(fr)
            elif fr is not None:
                flat.append(fr)
        out["items"] = flat
        out["count"] = len(flat)
        out["rows_processed"] = len(out_items)
        if err_n:
            notes.append(f"collect: 실패 {err_n}행은 제외(원 행 단위 결과는 collect 없이 실행해 확인)")
    if skipped:
        if halted == "budget":
            notes.append(f"하위 스텝 예산({_EACH_MAX_SUBSTEPS}) 초과로 중단 — {skipped}건 미처리")
        elif halted == "on_error":
            notes.append(f"on_error=stop 으로 중단 — {skipped}건 미처리")
        else:
            notes.append(f"limit={limit} 로 앞에서 잘랐습니다 — {skipped}건 미처리")
        out["skipped"] = skipped
    # 전 행 실패만 상위로 전파한다. 부분 실패는 파이프를 끊지 않되 반드시 보이게 한다.
    if out_items and ok_n == 0:
        out["success"] = False
        out["error"] = (f"each: {err_n}건 전부 실패 — 첫 오류: "
                        f"{out_items[0].get('_error')}")
    elif not out_items:
        if not rows:
            # ★F17 (2026-08-17 상상훈련 12회차): 입력 0행은 실수가 아니라 정당한 빈손 —
            # 0회 실행=성공(공허 참)으로 0건 통화를 내려 파이프가 완주하게 한다.
            # take/filter 는 빈손을 통과시키는데 each 만 실패로 파이프를 끊던 비대칭
            # (검색 0건 >> each >> flatten 이 step 3 에서 죽던 실측, P14 빈손 계약 정합).
            out["success"] = True
            out["message"] = "each: 입력 0행 — 실행 0회 (빈 목록)"
        else:
            out["success"] = False
            out["error"] = f"each: limit={limit} 로 처리한 행이 없습니다 — limit 을 확인하세요."
    else:
        out["success"] = True
        if err_n:
            notes.append(f"{err_n}/{len(out_items)}건 실패 (성공 {ok_n}) — _ok:false 행의 _error 참조")
    if notes:
        out["message"] = " / ".join(notes)
    return out

