"""workflow_contract.py — 워크플로우 호출 계약 (2026-08-22)

워크플로우를 "이름 붙은 문장" 에서 **함수** 쪽으로 한 칸 옮긴 두 조각.

  ① 재귀·순환 가드 — 워크플로우 호출 자체를 프레임으로 세어 순환·과중첩을 끊는다.
  ② 시그니처 — 몸통의 미할당 `$이름` = 호출자가 채워야 할 인자.

②를 판정하려면 "무엇이 주입되는가" 를 알아야 하므로, 2026-08-17 의 호출자 params
주입기(B8 수리)도 여기로 함께 옮겼다 — 시그니처와 주입은 같은 계약의 앞뒤다.
(workflow_engine 이 1500줄 규칙에 닿은 것이 분리의 계기.)
"""

import json
import re
from typing import List

from common.ibl_vars import REF_RE, split_ref, is_sole_ref, sub_ref


# === 워크플로우 재귀·순환 가드 (2026-08-22) ===
# 중첩 실행 깊이 상한(ibl_engine.MAX_NEST_DEPTH)은 "문장 안에 문장" 깊이만 센다. 그 상한
# 에러는 "긴 절차는 [self:workflow]에 저장해 id 로 참조하세요" 라고 안내해 왔는데, 정작
# workflow run 은 execute_pipeline 을 _depth 없이 새로 불러 카운터를 0으로 되돌렸다 —
# 안내된 탈출구가 가드 없는 유일한 통로였다(실측 2026-08-22). 자기 자신을 부르는
# 워크플로우 하나면 RecursionError 까지 내려가고, 그 전까지 각 층의 부수효과가 전부 실행된다.
#
# 설계: _depth 는 몸통에서 계속 0으로 재시작한다 — 탈출구 계약을 지키려면 그래야 한다.
# 대신 워크플로우 호출 *자체*를 프레임으로 세어 두 가지를 판정한다.
#   ① 같은 id 재진입 = 순환(직접·상호 모두) → 즉시 거절, 경로를 보여준다
#   ② 프레임 수 상한 = 과중첩 → 거절 (id 없는 즉석 실행의 자기중첩까지 덮는다)
# 스택은 밑줄-메타 관습(_depth·_node·_parallel)대로 step 에 찍혀 내려간다 — 스레드를 건너는
# 병렬 branch 도 따라가야 해서 contextvar 가 아니라 명시 스탬프다.
MAX_WORKFLOW_DEPTH = 5
_INLINE_FRAME = "<inline>"

# 스택을 물려줄 하위 문장 자리 — _stamp_depth(ibl_executors)와 같은 키 집합.
_WF_NEST_KEYS = ("branches", "_fallback_chain", "body", "catch", "finally", "_branch_steps")


def _wf_push(stack, frame: str) -> tuple:
    """호출 스택에 프레임을 밀어 넣는다. 반환: (새 스택, 오류문|None)."""
    stack = [str(x) for x in (stack or []) if str(x).strip()]
    if frame != _INLINE_FRAME and frame in stack:
        path = " → ".join(stack + [frame])
        return None, (f"워크플로우 순환 호출입니다: {path}. "
                      f"자기 자신을 (직접이든 다른 워크플로우를 거쳐서든) 부르는 워크플로우는 "
                      f"끝나지 않습니다 — 반복은 [repeat:]{{times: N}} 또는 [table:each] 로 쓰세요.")
    if len(stack) >= MAX_WORKFLOW_DEPTH:
        path = " → ".join(stack + [frame])
        return None, (f"워크플로우 중첩 깊이 상한({MAX_WORKFLOW_DEPTH})을 넘었습니다: {path}. "
                      f"워크플로우가 워크플로우를 부르는 사슬을 줄이거나, 반복이 필요하면 "
                      f"[repeat:]{{times: N}} / [table:each] 를 쓰세요.")
    return stack + [frame], None


def _stamp_wf_stack(steps, stack: list) -> None:
    """파싱된 step 들에 워크플로우 호출 스택을 찍는다(병렬 branches·블록 몸 포함)."""
    if not isinstance(steps, list):
        return
    for st in steps:
        if not isinstance(st, dict):
            continue
        st["_wf_stack"] = list(stack)
        for key in _WF_NEST_KEYS:
            v = st.get(key)
            _stamp_wf_stack(v if isinstance(v, list) else ([v] if isinstance(v, dict) else None), stack)


# === 시그니처 — 몸통의 자유 변수 (2026-08-22) ===
# 파서의 $var 기계장치는 *할당된* 변수만 {{_step_N_result}} 로 치환하고 미할당 $이름은
# 리터럴로 남긴다. 그러니 파스 후에 남은 $이름 = 정의상 이 문장의 자유 변수 = 호출자가
# 채워야 할 인자다. 이걸 아무도 적어두지 않아 W8(인자 없이 실행 → "$city 맛집" 이 그대로
# 검색어가 되어 success 로 완주)이 났다 — 스코프 문제가 아니라 시그니처 부재의 증상이다.
_SIGNATURE_EXTRA_RESERVED = {"return"}


def _bound_names(steps) -> set:
    """몸통이 **스스로 묶는** 이름 — 시그니처(자유 변수)에서 빼야 할 집합.

    B22-1(22회차 상상훈련 실측): 아래 주석의 전제 "파스 후 남은 $이름 = 자유 변수" 는
    **식 할당의 우변에서만 거짓**이다. 파서의 치환기는 *param 값* 자리만 치환하고
    `$return = $r` / `$avg = $total.value / 10` / `[repeat: while $n < 3]` 의 식·조건
    자리는 리터럴로 남긴다. 그래서 몸통이 방금 할당한 이름이 "호출자가 채워야 할 인자" 로
    계산돼, 교재가 M6 에서 가르치는 `do: '…$return = …'` 저장본이 **저장은 되고 실행은
    거절**됐다(`params_required: ['r']` → run 에서 '인자 누락: $r').

    즉 시그니처는 `사용` 이 아니라 `사용 − 할당` 이다. 묶는 자리 셋:
      · `_assign_name`  — 파이프/액션 할당의 대상(`$r = [self:time]`, `$t = A >> B`)
      · `_assign` step 의 `name` — 식 할당(`$avg = $total.value / 10`, `$return = $avg`)
      · `_repeat` 의 `var` — 회차 변수(기본 `i`)
    중첩 몸(body·branches·catch·finally)까지 훑는다 — `_reserved_row_names` 와 같은 순회.

    ★위치가 아니라 집합으로 뺀다(할당 *전* 참조도 인자로 안 센다). 그 방향이 안전한 쪽이다 —
    W8(미할당 `$city` 가 리터럴로 흘러 "$city 맛집" 이 검색어가 되던 침묵 실패)이 막으려던
    것은 **한 번도 할당되지 않는** 이름이고, 그건 이 차집합 뒤에도 그대로 걸린다."""
    names: set = set()

    def _walk(obj):
        if isinstance(obj, dict):
            n = obj.get("_assign_name")
            if isinstance(n, str) and n.strip():
                names.add(n.strip())
            if obj.get("_assign"):
                n2 = obj.get("name")
                if isinstance(n2, str) and n2.strip():
                    names.add(n2.strip())
            if obj.get("_repeat"):
                v = obj.get("var")
                names.add(v.strip() if isinstance(v, str) and v.strip() else "i")
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(steps)
    return names


def _free_vars(steps) -> List[str]:
    """파스 후에도 리터럴로 남은 `$이름` 목록 = 이 워크플로우의 시그니처.

    행 참조($it/each as)·집합 바인딩($items)·$return 은 런타임 바인더 소유라 제외.
    표기는 맨몸 `$이름` 과 괄호 `${이름}` 둘 다(common.ibl_vars).
    `$100` 처럼 숫자로 시작하는 이름은 인자로 세지 않는다 — 파서는 변수로 읽지만
    가격·금액 리터럴일 확률이 훨씬 높고, 잘못 세면 멀쩡한 저장본이 거절된다."""
    reserved = _reserved_row_names(steps) | _SIGNATURE_EXTRA_RESERVED | _bound_names(steps)
    found: List[str] = []

    def _walk(obj):
        if isinstance(obj, str):
            for m in REF_RE.finditer(obj):
                name, _path = split_ref(m)
                if name in reserved or name in found or name[0].isdigit():
                    continue
                # `$file:0` 은 변수가 아니라 파서의 파일 참조 플레이스홀더다(files 인자가
                # 붙지 않은 채 남으면 여기까지 온다) — 인자로 세면 "인자 누락: $file" 이라는
                # 엉뚱한 거절이 된다.
                if re.match(r":\d", obj[m.end():m.end() + 2]):
                    continue
                found.append(name)
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(steps)
    return found


def _signature_of(raw_body) -> List[str]:
    """저장 원문(문장·문장 배열·dict step 배열)에서 시그니처를 뽑는다. 실패하면 빈 목록."""
    try:
        steps, err = _normalize_steps_for_injection(raw_body)
        if err or not steps:
            return []
        return _free_vars(steps)
    except Exception:
        return []


# === 호출자 params → $변수 주입 (2026-08-17 B8 수리) ===
# desc 는 "run — … + params 옵션(문장 안 $변수에 주입)" 을 선언해 왔지만 구현이 없어
# 호출자 params 가 침묵 유실됐다(워크플로우는 고정값으로 돌아 거짓 정상을 냈다).
# 주입 자리: 파서의 $var 기계장치는 *할당된* 변수만 {{_step_N_result}} 로 치환하고
# 미할당 $이름은 리터럴로 남긴다 — 그 리터럴 자리가 호출자 params 의 자리다.
# 파스 *후* dict 값 층에서 주입하므로 ①문장 안 할당($x = …)이 항상 이기고
# ②값에 따옴표·개행이 들어도 IBL 문법을 깨뜨리지 않는다.

# $it(each 행 참조)·$items(집합 바인딩) — 런타임 바인더 소유라 주입 금지.
_CALLER_VAR_RESERVED = {"it", "items"}


def _coerce_caller_params(raw) -> tuple:
    """run 의 params 를 dict 로 강제. 반환: (dict|None, 오류문|None).

    모델이 JSON *문자열*로 넘기는 경우를 관용 수용하되, 객체가 아니면
    침묵 무시 대신 정직 거절(B8 부류 재발 방지)."""
    if raw is None:
        return None, None
    if isinstance(raw, dict):
        return (raw or None), None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None, None
        try:
            loaded = json.loads(s)
        except Exception:
            loaded = None
        if isinstance(loaded, dict):
            return (loaded or None), None
    return None, (f"params 는 {{변수명: 값}} 객체여야 합니다 (받은 형: {type(raw).__name__}). "
                  '예: [self:workflow]{op:"run", workflow_id:"x", params:{city:"청주"}}')


def _normalize_steps_for_injection(steps) -> tuple:
    """문자열 step 을 파싱해 dict 로 — 주입은 파싱된 값 층에서만 안전하다.
    execute_pipeline 입구 정규화와 같은 규칙(통짜 문자열 감싸기 + 원소별 파싱).
    반환: (steps|None, 오류문|None)."""
    if isinstance(steps, str):
        steps = [steps] if steps.strip() else []
    if not steps:
        return None, "steps가 비어있습니다."
    if not any(isinstance(s, str) for s in steps):
        return steps, None
    from ibl_parser import parse as ibl_parse, IBLSyntaxError
    normalized = []
    for s in steps:
        if isinstance(s, str):
            if not s.strip():
                continue
            try:
                normalized.extend(ibl_parse(s))
            except IBLSyntaxError as e:
                return None, f"IBL 문법 오류: {s} → {str(e)}"
        else:
            normalized.append(s)
    if not normalized:
        return None, "steps가 비어있습니다."
    return normalized, None


def _reserved_row_names(steps) -> set:
    """주입 금지 이름 — $it/$items + 문장 안 each 가 as 로 정한 커스텀 행 이름."""
    names = set(_CALLER_VAR_RESERVED)

    def _walk(obj):
        if isinstance(obj, dict):
            a = obj.get("as")
            if isinstance(a, str) and a.strip():
                names.add(a.strip())
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(steps)
    return names


def _apply_caller_params(steps: list, caller: dict) -> tuple:
    """호출자 params 를 steps 의 $변수 자리에 주입. 반환: (새 steps, 정직 메타 dict).

    치환 규칙(파서 _resolve_variables 와 동일한 이름 경계):
      - 값이 정확히 "$key" 하나면 원시 타입 보존(숫자·리스트·dict 그대로)
      - 문자열 속에 섞여 있으면 문자열 임베드(dict/list 는 JSON)
    메타: params_injected(주입된 키) / params_warning(대응 $변수 없는 키·예약 이름 —
    조용히 버리지 않고 알린다)."""
    reserved = _reserved_row_names(steps)
    hits = set()

    def _embed(value) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _sub_str(s: str):
        for key, value in caller.items():
            if key in reserved:
                continue
            if is_sole_ref(s, key):
                hits.add(key)
                return value  # 통짜 참조 — 원시 타입 보존
            before = s
            # 경로(`$r.file`)는 이름만 갈아끼우고 뒤에 그대로 붙인다 — 주입값은 step 결과가
            # 아니라 평범한 값이라, 경로 해석은 하류(파라미터 소비자)의 몫이다.
            s = sub_ref(s, key, lambda path, _v=value: _embed(_v) + path)
            if s != before:
                hits.add(key)
        return s

    def _walk(obj):
        if isinstance(obj, str):
            return _sub_str(obj)
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(v) for v in obj]
        return obj

    new_steps = _walk(steps)
    meta = {}
    if hits:
        meta["params_injected"] = sorted(hits)
    unmatched = sorted(set(caller) - hits - reserved)
    skipped = sorted(set(caller) & reserved)
    warnings = []
    if unmatched:
        warnings.append(f"params {unmatched} 에 대응하는 $변수가 문장에 없어 주입되지 않았습니다.")
    if skipped:
        warnings.append(f"params {skipped} 는 예약 이름($it/$items/each as)이라 주입하지 않습니다.")
    if warnings:
        meta["params_warning"] = " ".join(warnings)
    return new_steps, meta
