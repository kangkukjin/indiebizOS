"""ibl_distill_gates.py — 증류의 접지·구문 관문 (2026-09-06, ibl_usage_rag 에서 분할 · 1500줄 관문)

증류가 코퍼스에 넣기 전 묻는 것들 한 벌. 하나의 규약을 두 경로(낱말 = ibl_usage_rag,
관용구 = ibl_idiom)가 같이 쓰므로 문은 한 벌이어야 한다 — 관문이 두 벌이면 방언이 갈린다.

  · 머리 접지    이 주행에서 실제로 돈 액션인가
  · 합성 접지    >>·&·;·?? 가 실행 이력에 있던 합성인가 (증류=압축, 창작 아님)
  · 구문 관문    IBL 로 파싱되나 + 떨어진 `$이름 = ` 앞점 복원

이름은 ibl_usage_rag 가 다시 내보낸다(시험의 monkeypatch·기존 import 경로 존중).
"""

import re


# ── 합성 접지 게이트 (2026-08-16) ─────────────────────────────────────────
# 프롬프트 규칙 3("데이터가 흐를 때만 합성")을 경량 반성기가 어기고, 모델이
# 매개한 별개 호출들을 >> 로 이어 붙인 실사례가 나왔다(구 용례 3805·3806 —
# 다섯 >> 전부 통화가 흐르지 않는 죽은 파이프였고, 3805 는 old_string 앵커를
# new_string 이 삼킨 edit 라 재생 시 규칙 원장을 파괴한다). 프롬프트는 권고일
# 뿐이므로 기계로 막는다: **증류는 실행된 문장을 압축할 뿐, 새 문장을 창작하지
# 않는다** — 증류 코드의 합성(>>·&·;·??)은 실행 이력의 *단일 호출* 안에 그
# 액션들이 함께 합성돼 있던 경우에만 통과한다(압축=부분집합 허용, 별개 호출
# 봉합=차단). 거짓 파이프는 조합성 지표(파이프 비율·문형 수)까지 오염시킨다.

_QUOTED_STR_RE = re.compile(r'"(?:\\.|[^"\\])*"' + r"|'(?:\\.|[^'\\])*'")
_COMPOSE_OP_RE = re.compile(r'>>|\?\?|&|;')
_NODE_ACTION_RE = re.compile(r'\[([a-z_-]+:[a-z_0-9]+)\]')


def _strip_strings(code: str) -> str:
    """따옴표 문자열을 비운다 — 파라미터에 실려 가는 문장([self:trigger] pipeline,
    [table:each] do 등) 속 연산자를 최상위 합성으로 오인하지 않기 위해."""
    return _QUOTED_STR_RE.sub('""', code or "")


def _composed(code: str) -> bool:
    """따옴표 밖에 합성 연산자(>>·&·;·??)가 있는가."""
    return bool(_COMPOSE_OP_RE.search(_strip_strings(code)))


def _actions_of(code: str) -> set:
    """따옴표 밖 [node:action] 집합."""
    return set(_NODE_ACTION_RE.findall(_strip_strings(code)))


def _heads_grounded(code: str, ibl_calls: list) -> bool:
    """증류 코드의 액션 머리 집합이 실행된 호출들의 머리 집합 안에 있는가.

    반성기는 실행 경험을 *일반화*하지 새 액션을 *발명*하지 않는다 — 실행에서 성공한
    적 없는 머리는 검증 안 된 패턴이라 코퍼스에 못 들어온다(합성 접지의 머리판,
    프롬프트 규칙 6 의 기계판). 액션 실존 검사(_validate_ibl_actions)와는 다른 질문이다:
    그건 '사전에 있나', 이건 '이 주행에서 실제로 돌았나'.
    """
    acts = _actions_of(code)
    if not acts:
        return False
    executed = set()
    for call in ibl_calls:
        executed |= _actions_of(call)
    return acts <= executed


_FLOW_OP_RE = re.compile(r'>>|\?\?|;')


def _composition_grounded(code: str, ibl_calls: list) -> bool:
    """증류 코드가 합성문이면 실행 이력에 접지됐는지 판정. 단문 증류는 무조건 통과.

    두 갈래(2026-09-04 개정, ep2817 실측 — 그 턴의 가장 좋은 문장(지표 7개 `&`)이 버려졌다):
      · **흐름 합성**(`>>`·`??`·`;`): 데이터가 흐른다는 주장이므로, 실행된 어느 *한* 호출이
        그 액션들을 합성문으로 담고 있었어야 한다(별개 호출 봉합 = 거짓 관용구, 종전 규칙 그대로).
      · **병렬만의 합성**(`&` 뿐): "동시에 돌릴 수 있다"는 주장이지 흐름이 아니다 — 가지마다
        그 액션이 이 주행의 실행(어느 호출이든)에 있었으면 참이다. 08-28~09-04 합성 접지 스킵
        28건 중 약 3분의 1이 이 부류였다(별개로 성공한 조회들을 `&` 로 묶은 것).
    """
    if not _composed(code):
        return True
    acts = _actions_of(code)
    if not acts:
        return False
    stripped = _strip_strings(code)
    if not _FLOW_OP_RE.search(stripped):
        executed = set()
        for call in ibl_calls:
            executed |= _actions_of(call)
        return acts <= executed
    return any(_composed(call) and acts <= _actions_of(call) for call in ibl_calls)


# ── 할당 앞점 복원 (2026-09-06, ep2905 `$실패`·ep2943 `$fx` 실측) ─────────
# 반성기가 실행된 `$fx = A & B >> [table:union]` 을 옮기면서 좌변 `$fx = ` 만 떨어뜨리고
# 뒷문장의 `$fx >> [table:select]` 는 그대로 남기는 부류가 있다. 구문 관문은 "변수 $fx 이(가)
# 앞에서 할당되지 않았습니다" 로 정직하게 거절하지만, 그 대가로 GoalEval ACHIEVED 인 주행이
# 학습 0건이 됐다(관용구도 낱말도 못 남김).
#
# 프롬프트에 "할당을 빠뜨리지 마라"를 한 줄 더 쓰는 것은 관문이 아니다 — 좌변은 이 주행의
# 실행 이력에 그대로 남아 있으므로 기계가 되살린다. 창작이 아닌 이유 셋:
#   · 이름은 *실행된* 할당문의 좌변에서만 온다(지어내지 않는다).
#   · 같은 문장인지는 접지 게이트와 같은 자로 묻는다 — 머리 열의 순서 보존 부분열
#     (증류=압축이므로 부분집합을 허용하는 _composition_grounded 와 같은 규약).
#   · 후보 이름이 갈리면 손대지 않는다. 실행에 없던 할당도 되살리지 않는다 — 그 자리는
#     거절이 정직하다.
# 복원 뒤에도 접지·인자·액션 실존 게이트는 그대로 다 지난다(관문을 여는 게 아니라, 관문
# 앞까지 못 오던 문장을 데려다 놓을 뿐이다).


def _head_seq(code: str) -> tuple:
    """따옴표 밖 [node:action] 을 등장 순서대로 — 접지 판정이 쓰는 자."""
    return tuple(_NODE_ACTION_RE.findall(_strip_strings(code or "")))


def _is_subseq(small: tuple, big: tuple) -> bool:
    """small 이 big 의 순서 보존 부분열인가 (증류=압축 허용)."""
    it = iter(big)
    return all(x in it for x in small)


def _restore_var_assignments(code: str, ibl_calls: list):
    """떨어진 `$이름 = ` 을 실행 이력에서 되살린다 → (코드, 복원한 이름 목록).

    되살릴 게 없으면 코드를 그대로 돌려준다(무해). 삽입은 원문 오프셋에 하므로
    줄바꿈·`;` 등 원래 표기는 보존된다.
    """
    from common.ibl_vars import ASSIGN_RE, find_names
    import hippo_tree
    try:
        stmts = hippo_tree.split_sentences(code)
    except Exception:
        return code, []
    if len(stmts) < 2:
        return code, []

    def _assign_of(s):
        m = ASSIGN_RE.match((s or "").strip())
        return (m.group(1) or m.group(2), m.group(3)) if m else (None, None)

    assigned = {n for n, _ in (_assign_of(s) for s in stmts) if n}
    missing = [n for n in find_names(code) if n != "items" and n not in assigned]
    if not missing:
        return code, []
    # 이름이 처음 쓰이는 문장 — 복원은 그 앞에서만(할당이 참조보다 뒤면 여전히 미할당이다)
    first_use = {}
    for i, s in enumerate(stmts):
        for n in find_names(s):
            first_use.setdefault(n, i)
    # 실행 이력의 할당문: 우변 머리 열 → 좌변 이름들
    executed = []
    for call in ibl_calls or []:
        try:
            call_stmts = hippo_tree.split_sentences(call or "")
        except Exception:
            continue
        for s in call_stmts:
            n, rhs = _assign_of(s)
            if n in missing:
                executed.append((n, _head_seq(rhs)))
    if not executed:
        return code, []

    out, cursor, restored, taken = [], 0, [], set()
    for i, s in enumerate(stmts):
        idx = code.index(s, cursor)
        out.append(code[cursor:idx])
        heads = _head_seq(s)
        if _assign_of(s)[0] or not heads:
            out.append(s)
        else:
            cands = {n for n, rhs_heads in executed
                     if n not in taken and first_use.get(n, i) >= i and _is_subseq(heads, rhs_heads)}
            if len(cands) == 1:              # 후보가 갈리면 손대지 않는다
                name = cands.pop()
                taken.add(name)
                restored.append(name)
                out.append(f"${name} = {s}")
            else:
                out.append(s)
        cursor = idx + len(s)
    out.append(code[cursor:])
    return "".join(out), restored


def _syntax_gate_with_restore(code: str, ibl_calls: list, tag: str):
    """구문 관문 + 할당 앞점 복원 → (코드, 사유 or None). 두 증류 경로의 단일 주인."""
    from ibl_param_vocab import code_syntax_error
    err = code_syntax_error(code)
    if err and "할당되지 않았습니다" in err:
        fixed, restored = _restore_var_assignments(code, ibl_calls)
        if restored and code_syntax_error(fixed) is None:
            print(f"{tag} 할당 앞점 복원(실행 이력 접지): "
                  + " · ".join(f"${n}" for n in restored))
            return fixed, None
    return code, err
