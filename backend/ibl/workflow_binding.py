"""
workflow_binding.py — 파이프 이음매의 변수·통화 바인딩 (2026-08-22 분리)

workflow_engine.py 가 1500줄 규칙을 넘어, 형제 모듈 workflow_fallback.py 와 같은 방식으로
**이음매 헬퍼**를 떼어냈다. 실행 제어(순차·분기·중단)는 본체가 갖고, 여기 있는 것은
step 과 step 사이에서 값이 어떻게 옮겨 앉는가 하나다:

  · $var / $var.field  → 저장된 step 결과에서 값 꺼내기 (_extract_result_field·_v4_var_payload)
  · $items / $items.필드 → 직전 통화를 param 에 통째로 바인딩 (_bind_items_params)
  · 직전 결과 자동 주입 (_inject_prev_result·_auto_inject_prev·_has_prev_ref)
  · 통화 정규화·표시 (_to_prev_currency·_step_label·_to_string)

호출자(workflow_parallel·workflow_fallback·ibl_control_blocks·ibl_executors·테스트)는
지금까지처럼 `from workflow_engine import ...` 로 계속 집어간다 — 본체가 재수출한다.
"""

import re
import json
from typing import Any, Dict, Tuple


# $var 바인딩 참조 패턴 — 파서(_resolve_variables)가 $var 를 {{_step_N_result}} 로,
# $var.field.path 를 {{_step_N_result.field.path}} 로 치환한다 (G1, 2026-08-16).
from common.field_path import walk_path

# 경로부는 ibl_vars._XPATH 와 같은 확장(벡터 `*`·옵셔널 `?`, 2026-08-28) — 자리표 해석기가
# 참조 표기보다 좁으면 확장 경로가 리터럴 `{{_step_…}}` 로 하류에 새는 침묵 실패가 된다
# (라이브 실증이 적발 — 발견·치환·해석 세 자리의 경로 문법은 한 벌이어야 한다).
_STEP_RESULT_RE = re.compile(r"\{\{_step_(\d+)_result((?:\.(?:\w+|\*))*\??)\}\}")


def blank_step_refs(text: str, repl: str = "1") -> str:
    """아직 주입되지 않은 `{{_step_N_result[.path]}}` 자리를 더미로 메운다.

    ★B49-1(49회차 상상훈련): dry-run(`/ibl/validate`)은 실행 전이라 주입이 안 일어난
    상태에서 `do` 속 문장을 재파싱한다. 그런데 파서는 바깥에 `$n = …` 이 있으면 do
    문자열 안의 `$n` 을 **이미** 이 자리표로 바꿔 둔 뒤다 — `$` 로 훑는 재시도는 그
    모양을 못 보고 지나쳐, 멀쩡히 실행되는 문장에 검수가 `valid:false` 를 냈다.
    조종실은 번역→검수→실행이라 거짓 빨강이 곧 멀쩡한 문장의 차단이다.

    자리표 정규식을 호출부마다 다시 적으면 방언이 갈린다(ibl_vars.py 가 `$` 표기에
    대해 내린 판정과 같은 이유) — 이 자리표의 주인은 이 모듈이므로 걷어내는 굴절도
    여기서 낸다."""
    return _STEP_RESULT_RE.sub(repl, text or "")


def step_ref_indices(text: str) -> set:
    """텍스트가 참조하는 `{{_step_N_result}}` 의 인덱스 집합.

    자리표를 읽어야 하는 곳이 정규식을 손으로 다시 적으면 방언이 갈린다 — 실측으로
    세 벌이 있었다(이 모듈의 `_STEP_RESULT_RE`, api_ibl 의 재파싱 재시도, resume 진단의
    `r"\\{\\{_step_(\\d+)_result"`). 마지막 것은 닫는 괄호를 안 봐서 `{{_step_1_resultXYZ`
    같은 것도 집었다. 발견은 이 함수, 지우기는 `blank_step_refs` — 자리표의 주인은 하나다.
    """
    return {int(m.group(1)) for m in _STEP_RESULT_RE.finditer(text or "")}


_PROSE_PATHS = {"message", "text"}


def _extract_result_field_obj(raw: str, path: str) -> Any:
    """저장된 step 결과 문자열에서 .field.path 를 **원형(list/dict/스칼라)** 으로 추출.

    ★통짜 참조의 원형 보존(언어 개정 2026-08-27, 사용자 판정)이 쓴다 — param 값이
    `$변수.path` 하나뿐이면 JSON *문자열*이 아니라 이 원형이 param 에 들어간다.
    실패는 조용한 빈 문자열이 아니라 ValueError — 없는 필드가 침묵히 "" 로 치환되면
    하류가 빈 param 으로 "성공"하는 침묵 실패 부류가 된다(P 시리즈 원칙).

    ★끝의 `?` = 옵셔널(언어 개정 2026-08-28, 괄호형 전용 — ibl_vars._XPATH): 결측·
    비구조 결과를 오류 대신 None 으로. P 원칙의 예외가 아니라 **선언된 관용**이다 —
    맨몸 경로는 종전대로 정직 오류이고, 물음표를 적은 자리만 "없으면 빈"을 뜻한다
    (조건부 문서 절 when·분기 미진입 변수 참조가 이걸 쓴다)."""
    if isinstance(path, str) and path.endswith("?"):
        try:
            return _extract_result_field_obj(raw, path[:-1])
        except ValueError:
            return None
    obj: Any = raw
    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                obj = json.loads(s)
            except (json.JSONDecodeError, ValueError):
                raise ValueError(
                    f"$변수 필드 추출 실패: 결과가 JSON 이 아니라 '{path}' 경로를 풀 수 없습니다.")
        elif path in _PROSE_PATHS:
            # 언어 개정 2026-09-04(사용자 판정): 산문 결과(brief·document 같은 문자열 통화)에 `.message`·`.text` 를
            # 물으면 그 산문이다 — dict 통화의 message 필드와 같은 이름으로 같은 것을 가리키게 해 `$본문.message`
            # 가 결과 모양(문자열/봉투)에 따라 죽고 살던 비대칭을 없앤다. 다른 경로는 종전대로 정직 오류.
            return obj
        else:
            raise ValueError(
                f"$변수 필드 추출 실패: 결과가 구조화 데이터가 아니라 '{path}' 경로를 풀 수 없습니다.")
    # ★2026-09-05(시스템 AI 보고, 다단 union 조합 차단): `.items` 는 **통화**를 묻는 것이다 —
    #   table(union·groupby·select)·blocks(document) 로 방출된 봉투에서 파이프 이음매는 derive_items
    #   로 items 를 파생해 주는데, 변수 경로 읽기는 원형을 그대로 읽어 "items 필드가 없습니다(사용
    #   가능: table, success)" 로 죽었다. 소비처 누락 — 같은 판정기(common.currency.derive_items)를
    #   여기서도 쓴다. 파생본은 사본에만(저장된 step 결과 원형은 불변, 토큰 중복 회피 규약 유지).
    #   효과·스칼라 봉투는 종전대로 정직 오류(통화가 아닌 것을 통화라 부르지 않는다).
    if (isinstance(obj, dict) and not isinstance(obj.get("items"), list)
            and str(path).split(".", 1)[0] == "items"):
        from common.currency import derive_items
        obj = derive_items(dict(obj))

    def _missing(cur, key):
        # 필드 힌트의 절단도 신고한다 (F18-1 부류 — 침묵 클램프 금지)
        if isinstance(cur, dict):
            _names = list(cur.keys())
            avail = (_names[:12] + [f"…외 {len(_names) - 12}개"]) if len(_names) > 12 else _names
        elif isinstance(cur, list):
            avail = f"목록(길이 {len(cur)})"
        else:
            avail = type(cur).__name__
        raise ValueError(
            f"$변수 필드 추출 실패: '{key}' 필드가 없습니다 (경로 {path}, 사용 가능: {avail}).")

    # 걷는 규칙의 정본은 common.field_path 한 벌 (2026-08-27 경로 방언 통일)
    return walk_path(obj, path, on_missing=_missing)


def _extract_result_field(raw: str, path: str) -> str:
    """문장 **속** 참조용 문자열판 — 통짜가 아니면 글자 자리이므로 문자열화가 맞다."""
    obj = _extract_result_field_obj(raw, path)
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False)
    return "" if obj is None else str(obj)


def _v4_var_payload(raw: str) -> str:
    """bare `$var` 치환의 기본값 — v4 추출 계약 합류 (2026-08-20 상상훈련 17회차 F17-3 판정).

    옛 동작: 결과 봉투 JSON 전체를 문자열화 → write content 에 success 같은 배관 키까지
    박혔다(파이프 싱크의 v4 추출과 비대칭). 새 규약: message(산문 정본)/items(통화) 우선,
    폴백=봉투 원형. 명시 경로($var.field.path)는 불변 — 정밀 추출은 경로가 정본.
    규칙은 write v4(system_essentials)와 같은 게이트를 쓴다: 오분류는 항상 안전 방향
    (봉투=구조 보존)으로 떨어진다."""
    s = (raw or "").strip()
    if not s.startswith("{"):
        return raw
    try:
        obj = json.loads(s)
    except Exception:
        return raw
    if not isinstance(obj, dict):
        return raw
    # ★B53-3 (53회차 상상훈련, 2026-09-02): `$변수` 가 **파이프 결과**를 담고 있으면 슬롯엔
    #   변환자 봉투 원형(columns/rows + 생산자 형제 `data`)이 있고 items 가 없다(B51-1 속).
    #   그 원형을 그대로 문자열화하면 `[self:write]{content:"$s"}` 파일에 select 가 버린
    #   전 필드(data)가 실려 선별이 무효가 되고, 되읽으면 통화도 아니다. 판정 전에
    #   ①변환자가 자백한 형제(`_untransformed`)와 `_`메타는 값이 아니므로 뺀다,
    #   ②columns/rows·table 봉투는 몸의 단일 게이트(derive_items)로 items 를 파생한다,
    #   ③table/columns/rows/summary/count/success 는 같은 통화의 다른 얼굴·다이제스트라
    #     "다른 페이로드"로 세지 않는다. 오분류는 여전히 안전 방향(봉투 원형)으로.
    _skip = set(obj.get("_untransformed") or [])
    obj = {k: v for k, v in obj.items() if k not in _skip and not str(k).startswith("_")}
    if not isinstance(obj.get("items"), list):
        try:
            from common.currency import derive_items as _derive_items
            obj = _derive_items(obj)
        except ImportError:
            pass
    msg = obj.get("message")
    has_msg = isinstance(msg, str) and bool(msg.strip())
    items = obj.get("items")
    items_nonempty = isinstance(items, list) and bool(items)
    _same_face = ("items", "message", "table", "columns", "rows", "summary", "count", "success")
    other_payload = any(isinstance(v, (dict, list)) and v
                        for k, v in obj.items() if k not in _same_face)
    if has_msg and not other_payload:
        doc_shaped = ("\n" in msg.strip()) or (len(msg) >= 200)
        if doc_shaped or not items_nonempty:
            return msg
    if items_nonempty and not other_payload:
        return json.dumps(items, ensure_ascii=False)
    return raw


def _mark_list_in_text(step: dict, param: str, ref: str, rows: int) -> None:
    """step 표식 `_list_in_text` — **목록이 글자 자리에 JSON 으로 들어갔다**는 사실.

    ★G31-1 판정(2026-08-23, 사용자): 문장 *속* 집합/변수 참조는 거절하지 않고 **치환 + 신고**
      로 통일한다. 근거 셋 — ①규칙이 둘이었다(`$변수`=조용한 JSON, `$items`=조용한 거절),
      ②깨질 문장이 없다(코퍼스 3,594 중 문장 속 `$변수` 61건 전부 스칼라·저장 워크플로우 0),
      ③거절로 통일하면 **두 목록을 한 AI 지시문에 넣는 길**이 닫힌다(파이프는 하나만 나른다).
    표식은 사실만 싣는다(어느 param 에 어느 참조가 몇 행). 번역(경고문)은 엔진이 한 번 —
    `$items`·`$변수`·파이프·블록 몸 어디서 왔든 같은 표식, 같은 문장.
    """
    lst = step.get("_list_in_text")
    if not isinstance(lst, list):
        lst = []
        step["_list_in_text"] = lst
    lst.append({"param": param, "ref": ref, "rows": rows})


def _is_json_list(text: str):
    """치환된 텍스트가 JSON 목록이면 그 목록, 아니면 None (모양으로만 판정)."""
    t = (text or "").lstrip()
    if not t.startswith("["):
        return None
    try:
        v = json.loads(t)
    except Exception:
        return None
    return v if isinstance(v, list) else None


def _sub_step_refs(text: str, step_results: Dict[int, str], names: Dict[int, str],
                   sink, param_key):
    """문자열 하나의 {{_step_N_result[.path]}} 를 치환. sink 가 있으면 **문장 속**(통짜가
    아닌) 참조가 목록을 JSON 으로 넣은 경우를 표식 후보로 모은다.

    ★언어 개정 (2026-08-27, 사용자 판정 — 치환 의미론): 값이 **통짜 `.path` 참조 하나**면
    문자열 치환이 아니라 **원형(list/dict/스칼라)** 을 돌려준다. 옛 동작(항상 JSON 문자열)은
    같은 병을 소비자마다 되읽기로 때우게 했다(B19-2 items → P30 파이프 원형 → B52 blocks —
    세 번째 문에서 뿌리를 뽑는다). bare `$var`(경로 없음)는 v4 추출 계약(F17-3) 그대로 —
    산문 정본을 뽑는 그 계약은 이 개정과 다른 사건이다. 문장 **속** 참조는 글자 자리이므로
    종전대로 문자열화(+G31-1 목록 표식)."""
    _m_sole = _STEP_RESULT_RE.fullmatch(text.strip())
    if _m_sole is not None and _m_sole.group(2):
        return _extract_result_field_obj(step_results.get(int(_m_sole.group(1)), ""),
                                         _m_sole.group(2))
    sole = _m_sole is not None

    def _sub(m):
        n = int(m.group(1))
        base = step_results.get(n, "")
        p = m.group(2)
        val = _extract_result_field(base, p) if p else _v4_var_payload(base)
        if sink is not None and not sole:
            lst = _is_json_list(val)
            if lst is not None:
                label = names.get(n) if names else None
                sink.append((param_key, f"${label or f'step{n + 1}'}{p}", len(lst)))
        return val
    return _STEP_RESULT_RE.sub(_sub, text)


def _inject_step_results(obj: Any, step_results: Dict[int, str], _names: Dict[int, str] = None) -> Any:
    """{{_step_N_result[.path]}} 참조를 저장된 step 별 결과로 치환 (재귀 — branches/체인 포함).

    변수 바인딩($var)의 실제 구현(D4, 2026-08-05): 예전엔 $var 가 전부 {{_prev_result}} 로
    뭉개졌고, 문장 경계(_seq_boundary)가 prev_result 를 비워 문서화된 예제가 빈 문자열을
    치환받았다. 아직 실행되지 않았거나 예외로 결과가 없는 인덱스는 빈 문자열로 치환한다.
    .path 가 붙으면 결과(JSON)에서 그 필드를 추출한다 — 실패는 ValueError(정직 실패).
    bare 참조는 v4 추출(_v4_var_payload)을 태운다 (F17-3).
    ★문장 속 참조가 목록을 JSON 으로 넣으면 step 에 `_list_in_text` 표식(G31-1) — 통짜 참조
      (`content: "$곡"`)는 의도된 목록 전달이라 표식 없음. `_vars`(이름→인덱스)가 있으면
      표식에 변수 이름을 쓰고, 없으면 step 번호로 말한다(추측 금지).
    """
    if isinstance(obj, str):
        return _sub_step_refs(obj, step_results, _names or {}, None, None)
    if isinstance(obj, dict):
        # 블록은 건드리지 않는다 (M6): 몸은 안쪽 파이프의 인덱스 공간 — 바깥 치환은 실행기가 _vars/_var_values 로.
        if any(obj.get(k) for k in ("_condition", "_case", "_try", "_repeat", "_assign", "_goal")):
            return obj
        names = _names
        _nm = {}
        for _k in ("_vars", "_ref_vars"):          # 블록(_vars)·일반 step(_ref_vars, 파서가 남긴 이름)
            if isinstance(obj.get(_k), dict):
                _nm.update({int(ix): n for n, ix in obj[_k].items() if str(ix).isdigit()})
        if _nm:
            names = {**(_names or {}), **_nm}
        params = obj.get("params")
        if not isinstance(params, dict):
            return {k: _inject_step_results(v, step_results, names) for k, v in obj.items()}
        sink = []
        new = {}
        for k, v in obj.items():
            if k == "params":
                new[k] = {pk: (_sub_step_refs(pv, step_results, names or {}, sink, pk)
                               if isinstance(pv, str)
                               else _inject_step_results(pv, step_results, names))
                          for pk, pv in v.items()}
            else:
                new[k] = _inject_step_results(v, step_results, names)
        for pk, ref, rows in sink:
            _mark_list_in_text(new, pk, ref, rows)
        return new
    if isinstance(obj, list):
        return [_inject_step_results(v, step_results, _names) for v in obj]
    return obj


# $items 집합 바인딩 행 수 상한 — 초과는 침묵 절단 대신 정직 거절(take 로 줄이라고 안내).
ITEMS_BIND_CAP = 500

# `$items` / `${items}` / `$items.열` — 집합 바인딩 예약어 (표기는 common.ibl_vars 규약)
_ITEMS_REF = re.compile(r'^\$(?:\{\s*items(?:\.(\w+))?\s*\}|items(?:\.(\w+))?)$')


def _bind_items_params(tool_input: dict, prev_result: str):
    """★$items 집합 바인딩 (2026-08-16 상상훈련 G1-③ 판정).

    step 파라미터 *값*이 정확히 "$items"(전체 행) 또는 "$items.필드"(각 행에서 그 필드만)
    이면, 이전 step 결과의 items 리스트를 **실행 시점에 값으로** 바인딩한다.

    - 텍스트 치환이 아니다 — 데이터가 문장 텍스트를 통과하면 이스케이프·페이로드가
      깨진다(옛 shell-IBL 은퇴 사유와 동류). $it(each, 행 단위)의 짝인 집합 단위 규약.
    - 행동 액션(show_map 등)이 **핸들러 수정 없이** 파이프 하류에 서는 길:
        [sense:restaurant]{query:"청주 맛집"} >> [table:take]{n:3} >> [limbs:show_map]{markers: "$items"}
      (verb 마다 _prev_result 소비를 붙이면 F6 비대칭이 재생산된다 — 규약은 언어에 한 번.)
    - 상한 ITEMS_BIND_CAP 초과는 침묵 절단 대신 정직 거절: 앞에 take 를 끼우라고 안내.
    - ★파서의 $var 할당과 공존: `$items = ...` 로 직접 할당하면 파서 치환이 먼저라
      여기 도달하지 않는다 — $items 는 예약어로 쓰지 않기를 권장(가이드 명기).

    반환: (tool_input, error_str|None) — 참조가 없으면 원본 그대로, 바인딩 실패는 정직 에러.
    """
    params = tool_input.get("params")
    if not isinstance(params, dict):
        return tool_input, None
    refs = {k: m for k, v in params.items()
            if isinstance(v, str) and (m := _ITEMS_REF.match(v.strip()))}

    # ★문장 *속* `$items`/`$items.필드` (31회차 B31-2 → G31-1 판정, 2026-08-23):
    #   실측(31회차): `[self:memory]{content: '… $items.title'}` 이 success:true 로 **글자 그대로**
    #   `$items.title` 을 저장했다(12건) — 치환도 경고도 실패도 없었다. 그날 거절로 막았고,
    #   사용자 판정으로 **치환 + 신고**로 개정했다: 값 전체 참조와 같은 자료(전체 행 / 필드
    #   목록)를 JSON 으로 문장에 넣고 `_list_in_text` 표식을 남긴다. 산문이 필요한 사람은
    #   엔진의 경고가 [table:brief]/[table:each] 로 안내하고, 데이터를 AI 지시문에 먹이려는
    #   사람(두 목록 → 한 지시문)은 그대로 쓴다. 규칙은 `$변수`와 동일 — 예약어 특수 취급 없음.
    from common.ibl_vars import ref_pattern
    _in_text = re.compile(ref_pattern("items"))
    mixed = {k: v for k, v in params.items()
             if isinstance(v, str) and k not in refs and _in_text.search(v)}

    if not refs and not mixed:
        return tool_input, None

    # 이전 결과에서 items 통화 추출 (prev_result 는 _to_prev_currency 가 이미 items 파생을 마친 JSON)
    items = None
    s = (prev_result or "").strip()
    if s:
        try:
            obj = json.loads(s)
        except Exception:
            obj = None
        # 스필 참조 봉투면 본문으로 (M5)
        from common.spill import resolve_ref
        obj, _ref_err = resolve_ref(obj)
        if _ref_err:
            return tool_input, f"$items 바인딩 실패: {_ref_err}"
        if isinstance(obj, list):
            items = obj
        elif isinstance(obj, dict) and isinstance(obj.get("items"), list):
            items = obj["items"]
    if items is None:
        return tool_input, ("$items 바인딩 실패: 이전 step 결과에 items 통화가 없습니다. "
                            "앞 액션이 통화를 내는 생산자/변환자인지 확인하세요.")
    if len(items) > ITEMS_BIND_CAP:
        return tool_input, (f"$items 바인딩 거절: 행 {len(items)}개 — 상한 {ITEMS_BIND_CAP}. "
                            f"앞에 [table:take]{{n: ...}} 또는 filter 로 줄여 주세요(침묵 절단 금지).")

    out = dict(tool_input)
    out["params"] = dict(params)
    for key, m in refs.items():
        field = m.group(1) or m.group(2)   # 괄호형 `${items.열}` / 맨몸 `$items.열`
        if field:
            missing = [1 for r in items if not (isinstance(r, dict) and field in r)]
            if items and len(missing) == len(items):
                return tool_input, (f"$items.{field} 바인딩 실패: '{field}' 필드가 어느 행에도 없습니다. "
                                    f"실제 필드: {sorted(items[0].keys()) if isinstance(items[0], dict) else '비-dict 행'}")
            out["params"][key] = [r.get(field) for r in items if isinstance(r, dict)]
        else:
            out["params"][key] = items

    for key, text in mixed.items():
        notes = []

        def _repl(path, _notes=notes):
            if not path:
                payload = items
            else:
                seg = path.lstrip(".").split(".")  # path-ok: $items 행별 벡터 치환 — 단일 객체 걷기가 아니라 행 사상(M 시리즈 검증 계약)
                if len(seg) == 1 and not seg[0].isdigit():
                    field = seg[0]
                    missing = [1 for r in items if not (isinstance(r, dict) and field in r)]
                    if items and len(missing) == len(items):
                        raise ValueError(
                            f"$items.{field} 치환 실패: '{field}' 필드가 어느 행에도 없습니다. 실제 필드: "
                            f"{sorted(items[0].keys()) if isinstance(items[0], dict) else '비-dict 행'}")
                    payload = [r.get(field) for r in items if isinstance(r, dict)]
                else:
                    val = _extract_result_field(json.dumps(items, ensure_ascii=False), path)
                    lst = _is_json_list(val)
                    if lst is not None:
                        _notes.append((f"$items{path}", len(lst)))
                    return val
            _notes.append((f"$items{path}", len(payload)))
            return json.dumps(payload, ensure_ascii=False)
        try:
            out["params"][key] = _in_text.sub(lambda m: _repl(m.group(1) if m.group(1) is not None
                                                               else (m.group(2) or "")), text)
        except ValueError as e:
            return tool_input, str(e)
        for ref, rows in notes:
            _mark_list_in_text(out, key, ref, rows)
    # ★B31-1 (31회차): 무엇이 집합으로 바인딩됐는지 표식을 남긴다.
    #   이 step 이 실패하면 _items_bound_note 가 그 사실을 오류문에 실어 준다 — 아래 참조.
    if refs:   # 문장 속 치환만 있던 step 에 빈 바인딩 표식을 남기지 않는다(번역 오탐 방지)
        out["_items_bound"] = {k: (len(out["params"][k]) if isinstance(out["params"][k], list) else 1)
                               for k in refs}
    return out, None


def _items_bound_note(tool_input: dict, err_msg: str) -> str:
    """실패한 step 의 오류문에 **집합 참조로 무엇이 몇 건 들어갔는지**를 덧붙인다.

    ★31회차 실측 결함: `[sense:realty]{…} >> [table:take]{n:3} >> [self:notify_user]{message: "$items.title"}`
      → `'list' object has no attribute 'strip'`. 글자 하나를 받는 자리에 집합 3건이 들어가
      핸들러가 파이썬 예외로 터졌고, 사용자에게는 **그 예외문이 그대로** 나갔다. 무엇이
      잘못됐는지도, 어떻게 고치는지도 없는 문장이다.

    ★왜 핸들러를 고치지 않나(임시방편 배제): `.strip()` 하는 자리는 액션마다 있고 앞으로도
      늘어난다 — 열거 목록은 반드시 뒤처진다(28·30회차가 같은 교훈). 또 코어 액션
      (router=system)은 tool.json 스키마가 없어 param 타입으로 미리 막는 길도 닫혀 있다.
      대신 **맥락을 아는 유일한 자리**(바인딩)가 표식을 남기고, **오류를 내보내는 유일한
      자리**(파이프의 step 실패)가 그 표식을 번역한다. 액션 수와 무관하게 한 번만 산다.

    사실만 싣는다(추측 금지) — 무엇이 몇 건 들어갔는지, 그리고 두 갈래 출구.
    """
    bound = tool_input.get("_items_bound") if isinstance(tool_input, dict) else None
    lit = tool_input.get("_list_in_text") if isinstance(tool_input, dict) else None
    if isinstance(bound, dict) and bound:
        parts = ", ".join(f"{k}={n}건" for k, n in bound.items())
        err_msg = (f"{err_msg} ★이 step 의 파라미터에 집합 참조($items)로 목록이 들어갔습니다({parts}). "
                   f"받는 자리가 값 하나를 기대하면 이렇게 실패합니다 — 한 줄로 만들려면 "
                   f"[table:brief], 행마다 따로 실행하려면 [table:each]{{do: \"…$it.필드…\"}} 를 쓰세요.")
    if isinstance(lit, list) and lit:
        parts = ", ".join(f"{e.get('param')}←{e.get('ref')} {e.get('rows')}행" for e in lit)
        err_msg = (f"{err_msg} ★이 step 의 문장 속에 목록이 JSON 으로 들어갔습니다({parts}) — "
                   f"받는 자리가 그 모양을 못 받으면 이렇게 실패합니다. 산문이면 [table:brief], "
                   f"행마다면 [table:each]{{do: \"…$it.필드…\"}}.")
    return err_msg


def _list_in_text_warning(entries: list) -> str:
    """봉투 최상위 경고 한 줄 — `_seq["list_in_text"]` 의 번역(G31-1). 사실 + 두 갈래 출구 + 무시 허가."""
    parts = " / ".join(
        f"step {e['step']}[{e['action']}] " +
        ", ".join(f"{r.get('param')}←{r.get('ref')} {r.get('rows')}행" for r in (e.get("refs") or []))
        for e in entries)
    return (f"[목록→글자] {parts} 이 JSON 으로 문장에 들어갔습니다 — 산문 한 줄이 의도면 [table:brief], "
            f"행마다면 [table:each]{{do: \"…$it.필드…\"}}. 목록 그대로(AI 지시문에 데이터 먹이기)가 "
            f"의도면 이 경고는 무시하세요.")


def _inject_prev_result(tool_input: dict, prev_result: str) -> dict:
    """{{_prev_result}} 템플릿을 이전 결과로 치환"""
    injected = {}
    for key, val in tool_input.items():
        if isinstance(val, str):
            injected[key] = val.replace("{{_prev_result}}", prev_result)
        elif isinstance(val, dict):
            injected[key] = _inject_prev_result(val, prev_result)
        else:
            injected[key] = val
    return injected


def _has_prev_ref(tool_input: dict) -> bool:
    """tool_input 어디에든 {{_prev_result}} 참조가 남아있는지 확인"""
    for key, val in tool_input.items():
        if isinstance(val, str) and "{{_prev_result}}" in val:
            return True
        elif isinstance(val, dict) and _has_prev_ref(val):
            return True
    return False


def _resolve_spill_for_injection(prev: Any) -> Any:
    """스필 참조를 **주입 이음매 하나에서** 본문으로 되돌린다 (B27-2, 27회차).

    교재가 스필을 이렇게 약속한다 — *"step 봉투엔 참조만 실리지만 **뒤 step 은 그 참조를
    투명하게 해소해 원래 데이터를 그대로 본다**(파이프 흐름 불변 · 가벼워지는 건 results[]·
    모델 컨텍스트뿐)"*. 그런데 해소기가 **입구가 아니라 소비처마다** 흩어져 있었다:
      · workflow_binding `$items` 바인딩 · ibl_exec_each · ibl_exec_output `_sink_content`
      · data-ops `_get_items`
    네 곳을 두고도 구멍이 남는다. 실측(2026-08-23):
        [self:body]{days: 2, limit: 20} >> [self:write]{path: …, spill: true} >> [table:groupby]{by: "영역"}
        → "groupby: 입력에서 items 통화를 찾지 못했습니다"
    `_op_groupby` 는 `_rows_for_field` 로 들어가는데 해소기는 형제 입구인 `_get_items` 에만
    있었다 — **한 파일 안에서도 입구가 둘**이었다. 게다가 `_prev_result` 를 읽는 7개 패키지 중
    해소기를 가진 것은 둘뿐이라(ai-ops·visualization·media_producer·blog·android 는 없음),
    자동 스필(`_spill_if_large`)이 큰 결과를 참조로 바꾸는 순간 — 즉 **데이터가 클수록** —
    그 다섯은 0행을 보게 된다.

    25회차가 같은 모양의 결함에 내린 판정을 그대로 적용한다: **해소기는 하나여야 한다.**
    `_prev_result` 가 핸들러에 닿는 자리는 `_auto_inject_prev` 하나뿐이므로 여기서 푼다 —
    그러면 7개 패키지 전부와 앞으로 생길 패키지가 계약을 공짜로 상속한다.
    소비처의 기존 해소기는 지우지 않는다: 파이프가 아닌 입구(리터럴 씨앗·params 직접 통화)는
    이 이음매를 지나지 않으므로 중복이 아니라 **다른 입구의 담당**이다(resolve_ref 는 멱등).

    ★만료·부재는 여기서 삼키지 않고 참조를 **그대로 흘려보낸다** — 소비처의 기존 정직 오류가
    그대로 신고한다(이 수리가 새로 만드는 침묵 경로 0).
    """
    if not isinstance(prev, str):
        return prev
    s = prev.strip()
    if not (s.startswith("{") and '"ref"' in s):
        return prev                      # 빠른 경로 — 스필 봉투가 아닌 절대다수는 무비용
    try:
        obj = json.loads(s)
    except Exception:
        return prev
    try:
        from common.spill import is_ref, resolve_ref
        if not is_ref(obj):
            return prev
        resolved, err = resolve_ref(obj)
    except Exception:
        return prev
    if err or resolved is obj:
        return prev
    return _to_string(resolved)


def _auto_inject_prev(tool_input: dict, prev_result: str) -> dict:
    """
    파이프라인 자동 데이터 전달.

    prev_result가 있고, step에 {{_prev_result}} 명시 참조가 없으면
    params._prev_result로 자동 주입.

    이를 통해 [sense:web_search]{query: "A"} >> [engines:newspaper]{query: "B"} 같은 파이프라인에서
    step 2가 step 1의 결과를 자동으로 받을 수 있다.
    """
    if not prev_result:
        return tool_input

    prev_result = _resolve_spill_for_injection(prev_result)   # 스필 해소는 입구 하나에서 (B27-2)

    # 이미 {{_prev_result}} 템플릿 치환이 끝난 후이므로,
    # 원본에 참조가 있었다면 이미 치환됨 → 자동 주입 불필요
    # 참조가 없었던 경우에만 자동 주입
    # (치환 전 원본을 검사하는 것이 이상적이나, 현재 구조에서는
    #  치환 후에 호출하므로 params에 _prev_result가 이미 있는지 확인)
    params = tool_input.get("params", {})
    if isinstance(params, dict) and "_prev_result" not in params:
        tool_input = dict(tool_input)
        tool_input["params"] = dict(params)
        tool_input["params"]["_prev_result"] = prev_result

    return tool_input


def _to_prev_currency(result: Any) -> str:
    """다음 step 주입용 문자열 — **파이프 이음매에서만** 단일 통화(items)를 파생한다.

    감사 D13(2026-08-05): currency.py 문서는 파생 관문을 _route_handler 로 적었지만 실제
    호출처는 렌더러 경계(api_ibl)와 body_ask 뿐이라, table/blocks 만 내는 생산자가
    `>> [table:sort]` 파이프 안에서 items 를 못 찾고 깨졌다. 관문을 _route_handler 로 옮기면
    에이전트 최종 tool-result 에도 파생본이 실려 토큰이 중복된다(api_ibl 주석의 의도된 회피).
    → 진짜 갭은 파이프 이음매: prev_result 로 다음 step 에 물릴 때만 파생한다.
    results[]/step_results(모델·호출자에게 보이는 쪽)는 원형 유지 = 토큰 중복 0.

    JSON 문자열 결과(대다수 핸들러)도 파싱→파생→재직렬화로 커버. 파싱 불가면 원형 그대로.
    """
    from common.currency import derive_items
    r = result
    if isinstance(r, str):
        s = r.strip()
        if not (s.startswith("{") and s.endswith("}")):
            return _to_string(result)
        try:
            r = json.loads(s)
        except Exception:
            return _to_string(result)
    if isinstance(r, dict):
        return _to_string(derive_items(r))
    return _to_string(result)


def _step_label(step: Any) -> Tuple[str, str]:
    """봉투 results[] 의 (node, action) 라벨 — 블록 step 은 if/case/goal + "block" (옛 "?").
    긴 문장이 "어느 step 에서 왜" 죽었는지 읽으려면 블록도 이름이 있어야 한다(2026-08-22 M2)."""
    if not isinstance(step, dict):
        return "?", "?"
    if step.get("_condition"):
        return "if", "block"
    if step.get("_case"):
        return "case", "block"
    if step.get("_goal"):
        return "goal", "block"
    if step.get("_try"):
        return "try", "block"
    if step.get("_repeat"):
        return "repeat", "block"
    if step.get("_assign"):
        return "assign", f"${step.get('name')}"
    return step.get("_node", step.get("node", "?")), step.get("action", "?")


def _to_string(result: Any) -> str:
    """결과를 문자열로 변환 (다음 step 의 _prev_result 로 주입)."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        # 포워드된 결과 봉투 벗기기 — @hub/@노드 로 원격 실행된 bare-string 읽기는
        # {"result": "<본문>", "_forwarded_to": ...} 로 감싸져 온다. 다음 step 은 전송 봉투가
        # 아니라 *본문*을 원하므로 내부 본문만 넘긴다(크로스노드 이음매).
        # ★단 통화(items/table)가 있으면 벗기지 않는다 — 변환자(table:sort 등)가 통화를 소비해야
        #   하는데, text 같은 요약 문자열로 벗기면 통화가 사라진다(file_find@hub >> sort 회귀).
        if result.get("_forwarded_to") and "items" not in result and "table" not in result:
            for _k in ("result", "message", "markdown", "text", "content"):
                _v = result.get(_k)
                if isinstance(_v, str):
                    return _v
        return json.dumps(result, ensure_ascii=False)
    if isinstance(result, (list, tuple)):
        return json.dumps(result, ensure_ascii=False)
    return str(result)
