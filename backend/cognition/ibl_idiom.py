"""
ibl_idiom.py — 해마 관용구 층(idiom tier): 접지 관문·슬롯 표기 정규화·회상 사용 판정·관용구 증류 (2026-09-04)

정본 docs/IBL_IDIOM_TIER_HANDOFF.md. 관용구 = 독립 문장 2~8개를 `;` 로 이은 골격 + `${슬롯}` — 낱말(용례 한 문장)과
얼린 워크플로 사이의 층. 이 모듈은 ibl_usage_rag 에서 분할(1500줄 관문) — 이름은 rag 가 다시 내보내므로
호출부(증류·되돌려 묻기 스크립트·시험)는 `ibl_usage_rag._phrase_grounded` 처럼 계속 부른다.
"""
import re
from typing import Optional

_QUOTED_STR_RE = re.compile(r'"(?:\\.|[^"\\])*"' + r"|'(?:\\.|[^'\\])*'")


def _strip_strings(code: str) -> str:
    """따옴표 문자열을 비운다 — 파라미터에 실려 가는 문장 속 연산자를 최상위 합성으로 오인하지 않기 위해."""
    return _QUOTED_STR_RE.sub('""', code or "")


# ── 관용구 접지 관문 (2026-09-04, docs/IBL_IDIOM_TIER_HANDOFF.md §2-b) ──────────────
# 관용구는 독립 문장 2~8개를 `;` 로 이은 골격 — 순서는 흐름이 아니므로 `>>` 접지(한 호출 안)가
# 아니라 **순서 보존 부분열** 접지를 받는다. 문장은 **서명**으로 비교한다(값은 비교하지 않는다 —
# 값만 추상화되는 자리이므로): 머리 열이 같고, 인자 키가 실행 호출의 부분집합이며, `op` 값(동사)이
# 같아야 한다. `&` 만의 병렬문은 가지의 부분집합이면 된다(가지마다 같은 규칙). 문장 순서는 실행
# 순서의 부분열. 프롬프트는 권고, 이 관문이 집행. (첫 판 '되돌린 문자열 정확 일치'는 09-04 저녁 되돌려
# 묻기 실측에서 모델이 인자 하나를 빼거나 `&` 가지 하나만 뽑아도 거절해 12건 중 7건을 잃었다.)

_SLOT_RE = re.compile(r'\$\{([^}]+)\}')
_BARE_VAR_RE = re.compile(r'\$([A-Za-z_\uac00-\ud7a3][\w\uac00-\ud7a3]*)')
_SIG_OP_RE = re.compile(r'>>|\?\?|&|\||;')
_KEY_RE = re.compile(r'(?:^|[{,])\s*([A-Za-z_][\w]*)\s*:')
_OP_VAL_RE = re.compile(r'(?:^|[{,])\s*op\s*:\s*"([^"]*)"')


def _blank_slots(code: str) -> str:
    return _BARE_VAR_RE.sub('""', _SLOT_RE.sub('""', code or ""))


def _scan_block(code: str, i: int) -> int:
    """code[i]=='{' 에서 짝 맞는 '}' 의 인덱스(따옴표 안 무시). 없으면 len(code)-1."""
    depth, q, n = 0, None, len(code)
    while i < n:
        ch = code[i]
        if q:
            if ch == '\\':
                i += 1
            elif ch == q:
                q = None
        elif ch in '"\'':
            q = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n - 1


def _flatten(inner: str) -> str:
    """블록 안쪽 1층만 남긴다 — 문자열은 `""` 로, 중첩 블록({}·[])은 통째로 비운다."""
    out, d, q, i, n = [], 0, None, 0, len(inner)
    while i < n:
        ch = inner[i]
        if q:
            if ch == '\\':
                i += 2; continue
            if ch == q:
                q = None; out.append('"') if d == 0 else None
            i += 1; continue
        if ch in '"\'':
            q = ch
            if d == 0:
                out.append('"')
        elif ch in '{[':
            d += 1
        elif ch in '}]':
            d = max(0, d - 1)
        elif d == 0:
            out.append(ch)
        i += 1
    return "".join(out)


def _op_value(inner: str) -> Optional[str]:
    """블록 1층의 `op: "값"` — 문자열을 살린 채 중첩 블록만 비운 본문에서 읽는다."""
    out, d, q, i, n = [], 0, None, 0, len(inner)
    while i < n:
        ch = inner[i]
        if q:
            if d == 0:
                out.append(ch)
            if ch == '\\' and i + 1 < n:
                if d == 0:
                    out.append(inner[i + 1])
                i += 2; continue
            if ch == q:
                q = None
            i += 1; continue
        if ch in '"\'':
            q = ch
            if d == 0:
                out.append(ch)
        elif ch in '{[':
            d += 1
        elif ch in '}]':
            d = max(0, d - 1)
        elif d == 0:
            out.append(ch)
        i += 1
    m = re.search(r'(?:^|[{,])\s*op\s*:\s*["\']([^"\']*)["\']', "{" + "".join(out))
    return m.group(1) if m else None


def _sig(code: str) -> list:
    """문장의 서명: [('act', head, keys, op_value) | ('op', 연산자)] 의 열. 값은 op 만 본다."""
    s = re.sub(r'^\s*\$[\w\uac00-\ud7a3.]+\s*=\s*', '', code or "")      # `$var = …` 할당 머리
    items, i, n, q = [], 0, len(s), None
    while i < n:
        ch = s[i]
        if q:
            if ch == '\\':
                i += 1
            elif ch == q:
                q = None
            i += 1; continue
        if ch in '"\'':
            q = ch; i += 1; continue
        if ch == '[':
            j = s.find(']', i)
            if j < 0:
                break
            head = s[i + 1:j].strip()
            i = j + 1
            keys, opv = frozenset(), None
            while i < n and s[i].isspace():
                i += 1
            if i < n and s[i] == '{':
                k = _scan_block(s, i)
                inner = s[i + 1:k]
                keys = frozenset(_KEY_RE.findall("{" + _flatten(inner)))
                opv = _op_value(inner)
                i = k + 1
            items.append(('act', head, keys, opv))
            continue
        m = _SIG_OP_RE.match(s, i)
        if m:
            items.append(('op', m.group(0)))
            i = m.end(); continue
        i += 1
    return items


def _act_matches(p, c) -> bool:
    return p[1] == c[1] and p[2] <= c[2] and (p[3] is None or c[3] is None or p[3] == c[3])


def _sentence_matches(psig: list, csig: list) -> bool:
    """관용구 문장이 실행 호출에 접지되는가 — 서명 비교."""
    if not psig or not csig:
        return False
    p_ops = [x[1] for x in psig if x[0] == 'op']
    c_ops = [x[1] for x in csig if x[0] == 'op']
    p_acts = [x for x in psig if x[0] == 'act']
    c_acts = [x for x in csig if x[0] == 'act']
    if set(p_ops) <= {'&'} and set(c_ops) <= {'&'}:
        # 병렬만: 가지의 부분집합(가지마다 머리·키·op 규칙)
        used = set()
        for pa in p_acts:
            j = next((k for k, ca in enumerate(c_acts) if k not in used and _act_matches(pa, ca)), None)
            if j is None:
                return False
            used.add(j)
        return True
    if p_ops != c_ops or len(p_acts) != len(c_acts):
        return False
    return all(_act_matches(pa, ca) for pa, ca in zip(p_acts, c_acts))


def _is_numeric(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    return bool(re.fullmatch(r'-?\d+(?:\.\d+)?', str(v).strip()))


def _normalize_slot_quoting(sentence: str, slots: dict) -> str:
    """따옴표 밖의 `${이름}` 을 표기 규약으로: 수치 슬롯 → `$이름`, 문자열 슬롯 → `"${이름}"`.
    표현의 정규화일 뿐 문장을 창작하지 않는다(파서는 따옴표 밖 `${…}` 를 못 읽는다)."""
    out, i, n, q = [], 0, len(sentence or ""), None
    while i < n:
        ch = sentence[i]
        if q:
            out.append(ch)
            if ch == '\\' and i + 1 < n:
                out.append(sentence[i + 1]); i += 2; continue
            if ch == q:
                q = None
            i += 1
            continue
        if ch in '"\'':
            q = ch; out.append(ch); i += 1; continue
        m = _SLOT_RE.match(sentence, i)
        if m:
            name = m.group(1).strip()
            val = (slots or {}).get(name)
            out.append(f'${name}' if _is_numeric(val) else f'"${{{name}}}"')
            i = m.end(); continue
        out.append(ch); i += 1
    return "".join(out)


def _phrase_grounded(phrase: list, slots: dict, ibl_calls: list) -> Optional[str]:
    """관용구가 이 주행에 접지됐는가. 통과=None, 아니면 사유 한 줄."""
    csigs = [_sig(_blank_slots(c)) for c in ibl_calls]     # 양쪽을 같은 규칙으로 비운다(변수·슬롯은 값이 아니라 자리)
    pos = 0
    for i, sent in enumerate(phrase, 1):
        psig = _sig(_blank_slots(sent))
        if not psig or not any(x[0] == 'act' for x in psig):
            return f"문장 {i} 액션 없음: {sent[:60]}"
        j = next((k for k in range(pos, len(csigs)) if _sentence_matches(psig, csigs[k])), None)
        if j is None:
            if any(_sentence_matches(psig, csigs[k]) for k in range(0, pos)):
                return f"문장 {i} 순서 어긋남(실행 순서의 부분열이 아님): {sent[:60]}"
            return f"문장 {i} 실행에 없음(머리 열·인자 키·op 불일치): {sent[:60]}"
        pos = j + 1
    return None


def _phrase_private_reason(code: str) -> Optional[str]:
    """관용구 본문의 개인 명사 — 슬롯으로 비우지 못한 홈 경로·개인 명사 목록(data/private_nouns.txt, gitignore) 적발."""
    m = re.search(r'(?:/Users/|/home/|[A-Za-z]:\\Users\\)[^/\\"\'\s]+', code or "")
    if m:
        return f"홈 경로가 남아 있음(슬롯으로 비울 것): {m.group(0)}"
    try:
        from pathlib import Path as _P
        lst = _P(__file__).parent.parent.parent / "data" / "private_nouns.txt"
        if lst.exists():
            for raw in lst.read_text(encoding="utf-8").splitlines():
                t = raw.strip()
                if not t or t.startswith("#") or t.lower().startswith("allow:"):
                    continue
                try:
                    if re.search(t, code, re.IGNORECASE):
                        return "개인 명사 목록에 걸림(슬롯으로 비울 것)"
                except re.error:
                    continue
    except Exception:
        pass
    return None


def _phrase_used(phrase_code: str, ibl_calls: list) -> bool:
    """회상된 관용구가 실행 궤적에 쓰였는가 — 문장 머리 열의 순서 보존 부분열이 절반 이상 등장."""
    import hippo_tree
    sents = hippo_tree.split_sentences(phrase_code or "")
    if not sents:
        return False
    heads = [re.findall(r'\[([a-z_-]+:[a-z_0-9]+)\]', _strip_strings(s)) for s in sents]
    exec_heads = [re.findall(r'\[([a-z_-]+:[a-z_0-9]+)\]', _strip_strings(c)) for c in ibl_calls]
    pos, hit = 0, 0
    for h in heads:
        if not h:
            continue
        j = next((k for k in range(pos, len(exec_heads)) if exec_heads[k] == h), None)
        if j is not None:
            hit += 1
            pos = j + 1
    need = (len(sents) + 1) // 2
    return hit >= need


_FN_NAME_RE = re.compile(r'^[\w\uac00-\ud7a3][\w\uac00-\ud7a3.-]*$')
_FN_NAME_RESERVED = {"if", "else", "case", "goal", "repeat", "try", "catch", "finally", "on_error", "def", "fn"}


def same_program(code: str, phrase: list) -> bool:
    """대표 code 와 관용구(phrase 문장 목록)가 **같은 프로그램**인가 — 슬롯·값을 비운 서명 열이 같으면 같다.
    (2026-09-05 ep2847: 두 문장 프로그램이 관용구 `수리제안적용하기` 와 낱말 `수리제안적용하기2` 로 두 번 저장됐다 —
    이름이 갈리면 회상이 둘을 다른 함수로 보여 준다. 한 프로그램은 한 이름.)"""
    try:
        import hippo_tree
        cs = [_sig(_blank_slots(s)) for s in hippo_tree.split_sentences(code or "")]
        ps = [_sig(_blank_slots(s)) for s in (phrase or []) if isinstance(s, str) and s.strip()]
    except Exception:
        return False
    return bool(cs) and cs == ps


def sanitize_fn_name(name, fallback: str = "") -> str:
    """관용구 이름 → `[fn:이름]`/`[def: 이름]` 에 설 수 있는 이름. 공백·기호는 지우고, 비면 의도에서 만든다."""
    s = re.sub(r"[^\w\uac00-\ud7a3.-]", "", str(name or "").strip())
    if not s or s in _FN_NAME_RESERVED or not _FN_NAME_RE.match(s) or s[0].isdigit():
        base = re.sub(r"[^\w\uac00-\ud7a3]", "", str(fallback or ""))[:12]
        s = ("관용구" + base) if (not base or base[0].isdigit()) else base
    return s[:40]


def unique_fn_name(name: str, db, code: str) -> str:
    """같은 이름이 다른 골격에 이미 있으면 숫자 접미(이름2, 이름3…). 같은 골격이면 그 이름 그대로."""
    base, n = name, 1
    while True:
        try:
            row = db.find_phrase_by_alias(name)
        except Exception:
            return name
        if not row or (row.get("ibl_code") == code):
            return name
        n += 1
        name = f"{base}{n}"


def _phrase_code_by_alias(name: str):
    """검사기(ibl_typecheck)에 관용구 몸을 내주는 소스 — `[fn:이름]` 의 반환 모양 추론용(2026-09-05, 의존 역전 등록)."""
    from ibl_usage_db import IBLUsageDB
    row = IBLUsageDB().find_phrase_by_alias(name)
    return (row or {}).get("ibl_code") or None


def _workflow_code_by_name(name: str):
    """저장 워크플로의 몸(원장) — `[fn:이름]` 해소 둘째 길(정의 → 워크플로 → 관용구)."""
    from workflow_store import get_workflow
    wf = get_workflow(name)
    if not isinstance(wf, dict) or wf.get("problem"):
        return None
    for k in ("do", "steps", "pipeline"):
        v = wf.get(k)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            return "\n".join(v)
    return None


try:
    from ibl_typecheck import register_fn_code_source as _reg_fn_src
    _reg_fn_src(_workflow_code_by_name)
    _reg_fn_src(_phrase_code_by_alias)
except Exception:
    pass


def _distill_phrase(intent: str, distilled: dict, ibl_calls: list, topic: str,
                    tool_calls: list, turn_tokens: int = None) -> bool:
    """반성기의 두 번째 답(phrase·slots)을 관문에 통과시켜 `category='phrase'` 로 저장한다. 낱말 증류와 독립."""
    import hippo_tree
    phrase = distilled.get("phrase")
    slots = distilled.get("slots") or {}
    if not isinstance(phrase, list) or not phrase:
        return False
    phrase = [p.strip() for p in phrase if isinstance(p, str) and p.strip()]
    if not isinstance(slots, dict):
        slots = {}
    tag = "[경험증류:관용구]"
    n = len(phrase)
    if not (hippo_tree.PHRASE_MIN_SENTENCES <= n <= hippo_tree.PHRASE_MAX_SENTENCES):
        print(f"{tag} 문장 수 {n} — 스킵(허용 {hippo_tree.PHRASE_MIN_SENTENCES}~{hippo_tree.PHRASE_MAX_SENTENCES})")
        return False
    if not topic:
        print(f"{tag} topic 없음 — 스킵")
        return False
    # 이미 아는 관용구가 이 턴에 쓰였으면 다시 뽑지 않는다(근접 중복 축적 방지)
    try:
        from thread_context import get_phrase_recall
        for known in get_phrase_recall():
            if _phrase_used(known, ibl_calls):
                print(f"{tag} 회상된 관용구가 실행에 쓰임 — 새 관용구 스킵: {known[:60]}")
                return False
    except Exception:
        pass
    phrase = [_normalize_slot_quoting(p, slots) for p in phrase]
    why = _phrase_grounded(phrase, slots, ibl_calls)
    if why:
        print(f"{tag} 접지 실패 — 스킵: {why}")
        return False
    code = hippo_tree.join_sentences(phrase)
    from ibl_param_vocab import code_syntax_error, check_code_params
    err = code_syntax_error(code)
    if err:
        print(f"{tag} 파싱 불가 — 스킵: {err} / {code[:80]}")
        return False
    from ibl_usage_rag import _validate_ibl_actions, _ibl_elapsed_ms, IBLUsageRAG   # 지연 import(순환 방지·시험의 monkeypatch 존중)
    if not _validate_ibl_actions(code):
        print(f"{tag} 미존재 액션 — 스킵: {code[:80]}")
        return False
    try:
        issues = check_code_params(code)
        if issues:
            print(f"{tag} 미인식 파라미터 — 스킵: {[(i['action'], i['unknown']) for i in issues]}")
            return False
    except Exception:
        pass
    why = _phrase_private_reason(code)
    if why:
        print(f"{tag} 개인 명사 — 스킵: {why}")
        return False
    code = re.sub(r',\s*_raw:\s*(?:true|false)', '', code)
    nodes = ",".join(sorted(set(re.findall(r'\[([a-z_-]+):', code))))
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    birth_ms = _ibl_elapsed_ms(tool_calls)
    # 관용구 = 이름 붙은 함수(2026-09-05): 반성기의 phrase_name → 정리·유일화. `[fn:이름]{슬롯}` 으로 불린다.
    alias = unique_fn_name(sanitize_fn_name(distilled.get("phrase_name"), intent), db, code)
    try:
        from ibl_typecheck import return_type_of
        _returns = return_type_of(code)                     # 서명의 반환 모양(2026-09-05) — 슬롯은 미상으로 두고 몸을 타입
    except Exception:
        _returns = "?"
    example_id = db.add_example(
        intent=intent, ibl_code=code, nodes=nodes, category=hippo_tree.PHRASE_CATEGORY,
        difficulty=2, source="distilled", tags="auto,phrase",
        avg_ms=float(birth_ms) if birth_ms else -1.0,
        avg_tokens=float(turn_tokens) if (turn_tokens and turn_tokens > 0) else -1.0,
        topic=topic, alias=alias, returns=_returns)
    if not example_id:
        print(f"{tag} 원장이 거부 — 학습 파일에도 적재하지 않음: {code[:60]}")
        return False
    from pathlib import Path
    import json as _json
    distilled_path = Path(__file__).parent.parent.parent / "data" / "training" / "ibl_distilled.json"
    try:
        existing = _json.loads(distilled_path.read_text(encoding="utf-8")) if distilled_path.exists() else []
        existing.append({"intent": intent, "ibl_code": code, "category": hippo_tree.PHRASE_CATEGORY})
        distilled_path.write_text(_json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"{tag} 학습 파일 적재 실패(DB id={example_id}) — 재학습 원장 어긋남: {e}")
    IBLUsageRAG().clear_cache()
    print(f"{tag} 저장 완료 (id={example_id}, 이름 [fn:{alias}], 문장 {n}, 슬롯 {len(hippo_tree.slot_names(code))}, 가지 '{topic}'): \"{intent[:40]}\"")
    return True
