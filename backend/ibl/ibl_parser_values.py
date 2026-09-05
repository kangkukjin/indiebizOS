"""IBL 파서 값/파라미터 추출 층 (2026-07-18 모듈화 — 1500줄 규칙)

ibl_parser.py 에서 verbatim 이동: {params} 파싱(_parse_params/_parse_relaxed_params)과
값 추출기(문자열·괄호·숫자·비인용). 리프 모듈(파서 내부 의존 없음) — IBLSyntaxError 도
여기 산다(blocks·본체가 공유, 순환 없는 최하층). 본체가 재수출하므로
`from ibl_parser import IBLSyntaxError` 경로 불변.
"""
import json
import re
from typing import Dict, Optional, Tuple


class IBLSyntaxError(Exception):
    """IBL 문법 오류"""
    pass


def _parse_params(text: str) -> dict:
    """
    파라미터 블록 파싱.

    JSON5(unquoted keys, single/double quotes, trailing commas, comments 등 허용)를
    우선 시도하고, 실패하면 표준 JSON → relaxed_params 순으로 폴백.

    JSON5는 사람이 손으로 쓰는 JSON-like 형식의 표준이고, 우리가 그동안 만들던
    헬퍼들(_quote_unquoted_keys, replace 변환)이 사실상 JSON5의 부분집합을
    재발명하는 것이었다. 표준에 위임하면 따옴표 변환·키 quote 같은 미봉책이
    모두 불필요해진다.
    """
    if not text:
        return {}

    # ★2026-08-22 (파서 계열 점검): 표준 밖 이스케이프가 있으면 JSON/JSON5 를 건너뛴다.
    # pyjson5 는 `"\d+"` 를 `d+` 로 **백슬래시째 먹는다**(실측). 그래서 아래 수동 파서가
    # "모르는 이스케이프는 원문 보존"으로 고쳐져 있어도 이 경로에서 통째로 무효가 됐고,
    # `[self:grep]{pattern: "\d+"}` 같은 정규식 param 이 조용히 다른 패턴으로 바뀌어
    # 0건을 돌려줬다(침묵 실패). 두 파서가 같은 입력에 다른 답을 내면 안 된다.
    if not _has_nonstandard_escape(text):
        # 1. JSON5 시도 — unquoted keys, 양쪽 따옴표, trailing comma 등 모두 처리
        try:
            import pyjson5
            result = pyjson5.loads(text)
            if isinstance(result, dict):
                return result
        except Exception:
            pass

        # 2. 표준 JSON (JSON5 라이브러리 부재 또는 파싱 실패 시 보험)
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # 3. 최후 폴백: 간단한 key: value 파싱
    return _parse_relaxed_params(text)


# JSON/JSON5 가 아는 이스케이프 — 이 밖의 `\x` 는 수동 파서만 원문대로 보존한다.
_STD_ESCAPES = set('"\\/bfnrtu\'\n')


def _has_nonstandard_escape(text: str) -> bool:
    """표준 밖 이스케이프(`\\d`·`\\s`·`\\q` 등)가 들어 있나 — JSON5 우회 판정."""
    i = 0
    n = len(text)
    while i < n - 1:
        if text[i] == '\\':
            if text[i + 1] not in _STD_ESCAPES:
                return True
            i += 2      # 이스케이프된 백슬래시·표준 이스케이프는 건너뛴다
            continue
        i += 1
    return False


def _escape_control_in_strings(raw: str) -> str:
    """리터럴 배열/객체 안 **문자열 안의 실제 개행·탭**을 JSON 이스케이프로 바꾼다.

    ★2026-08-22: `[table:each]{items: [{"code": "a<개행>    b"}]}` 처럼 값 안에 진짜
    개행이 있으면 JSON 규격상 제어문자라 파싱이 실패하고, 예전엔 그때 **원본 문자열을
    그대로 돌려줘**("배열이면 원본 문자열 반환") items 가 list 가 아닌 str 로 떨어졌다 —
    소비자는 "통화를 못 찾음"으로 죽고 원인은 안 보였다(F19-3 과 같은 '개행이 값을
    깨뜨린다' 계열). 이스케이프해 한 번 더 시도하면 그 부류가 통째로 산다.
    """
    out = []
    in_s = False
    quote = None
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if in_s:
            if ch == '\\' and i + 1 < n:
                out.append(ch)
                out.append(raw[i + 1])
                i += 2
                continue
            if ch == quote:
                in_s, quote = False, None
                out.append(ch)
            elif ch == '\n':
                out.append('\\n')
            elif ch == '\t':
                out.append('\\t')
            elif ch == '\r':
                out.append('\\r')
            else:
                out.append(ch)
        else:
            if ch in '"\'':
                in_s, quote = True, ch
            out.append(ch)
        i += 1
    return ''.join(out)


def _reject_residue(inner: str, pos: int, parsed: dict) -> None:
    """느슨한 파싱이 입력을 끝까지 소비하지 못했으면 정직하게 거절한다.

    2026-08-22 신설. 예전에는 여기서 그냥 break 해서, 값 문자열 안의
    이스케이프되지 않은 `"` 하나에 뒤 내용이 통째로 사라진 params 를
    **성공으로** 돌려줬다. `[self:write]` 는 그 잘린 본문을 정상 저장하고
    success:true 를 반환했으므로 하류에서 알아챌 방법이 없었다
    (침묵 절단 — pitfall silent_clamp 부류).

    잔여가 공백·쉼표뿐이면 정상 종료로 본다.

    ★2026-09-03: 진단이 원인을 빗나가던 자리. 예전에는 원인을 보지 않고 **항상**
    "값 문자열 안의 따옴표가 이스케이프되지 않았다"고 안내했다. 그래서 키 표기가
    깨진 문장(`old_string": "…"` — 키 뒤에 군더더기 따옴표)에도 같은 문구가 붙었고,
    그대로 믿은 작성자는 멀쩡한 값을 이스케이프하러 갔다. 틀린 진단은 침묵보다
    나쁘다 — 고치는 사람을 엉뚱한 곳으로 보내기 때문이다. 이제 멈춘 지점의 토큰을
    보고 원인을 갈라 말한다(_diagnose_residue).
    """
    residue = inner[pos:].strip(" \t\n\r,")
    if not residue:
        return
    snippet = residue if len(residue) <= 60 else residue[:60] + "…"
    keys = ", ".join(str(k) for k in parsed) or "없음"
    raise IBLSyntaxError(
        f"파라미터를 끝까지 읽지 못했습니다. 해석된 키: [{keys}] / 남은 조각: {snippet!r}\n"
        f"{_diagnose_residue(residue)}"
    )


# 멈춘 지점의 모양 → 원인. 위에서부터 좁은 것 먼저(키 표기 오류는 값 이스케이프보다
# 특징이 뚜렷하다). 어느 것도 안 맞으면 값 이스케이프로 안내한다 — 그때만 '가능성'이다.
_RESIDUE_CAUSES = (
    # old_string": "…"  — 키 이름 뒤에 따옴표가 붙었다 (실측 2026-09-03)
    (re.compile(r'^([A-Za-z_]\w*)\s*(["\'])\s*:'),
     lambda m: (f"→ 키 표기 오류입니다: 키 `{m.group(1)}` 뒤에 군더더기 따옴표 {m.group(2)} 가 "
                f"붙었습니다. `{m.group(1)}:` 로 쓰세요(키는 따옴표 없이, 또는 양쪽을 감싼 "
                f'`"{m.group(1)}":`). 값 이스케이프 문제가 아닙니다.')),
    # "old_string: "…"  — 키 앞 따옴표가 열리고 안 닫혔다
    (re.compile(r'^(["\'])([A-Za-z_]\w*)\s*:'),
     lambda m: (f"→ 키 표기 오류입니다: 키 `{m.group(2)}` 앞의 따옴표 {m.group(1)} 가 닫히지 "
                f'않았습니다. 양쪽을 감싸거나(`"{m.group(2)}":`) 둘 다 빼세요(`{m.group(2)}:`).')),
    # old_string = "…"  — 구분자가 = 다
    (re.compile(r'^([A-Za-z_]\w*)\s*='),
     lambda m: f"→ 키와 값 사이 구분자는 `=` 가 아니라 `:` 입니다: `{m.group(1)}: 값`."),
    # old_string "…"  — 구분자가 통째로 빠졌다
    (re.compile(r'^([A-Za-z_]\w*)\s+["\'\[{]'),
     lambda m: f"→ 키 `{m.group(1)}` 뒤에 `:` 가 빠졌습니다: `{m.group(1)}: 값`."),
)


def _diagnose_residue(residue: str) -> str:
    """남은 조각의 첫 토큰으로 원인을 판별해 한 줄 안내를 만든다."""
    for rx, render in _RESIDUE_CAUSES:
        m = rx.match(residue)
        if m:
            return render(m)
    return ('→ 값 문자열 안의 따옴표가 이스케이프되지 않았을 가능성이 큽니다. '
            '자유 텍스트(content 등) 안의 " 는 \\" 로 쓰세요. '
            '(키 표기 오류로 보이지는 않습니다 — 위 "남은 조각"이 시작되는 자리를 보세요.)')


# 맨몸 키를 끝내는 구조 문자 — 이 밖의 모든 글자(기호·한글·유니코드)는 키의 일부다.
_KEY_STOP = frozenset(' \t\n\r:,{}[]"\'=')


def _parse_relaxed_params(text: str) -> dict:
    """
    느슨한 파라미터 파싱 — 배열 [...], 중첩 객체 {...} 포함 지원

    { query: "임대차", page: 1 }                      → {"query": "임대차", "page": 1}
    { data: [1, 2, 3], nested: {a: 1} }               → {"data": [1,2,3], "nested": {"a": 1}}
    { items: [{name: "A"}, {name: "B"}], count: 2 }   → {"items": [...], "count": 2}
    """
    # 중괄호 제거
    inner = text.strip()
    if inner.startswith('{'):
        inner = inner[1:]
    if inner.endswith('}'):
        inner = inner[:-1]
    inner = inner.strip()

    if not inner:
        return {}

    params = {}
    i = 0
    n = len(inner)

    while i < n:
        # 공백, 쉼표 건너뛰기
        while i < n and inner[i] in ' \t\n\r,':
            i += 1
        if i >= n:
            break

        # key 추출 — 따옴표 키는 문자열로, 맨몸 키는 **구조 문자가 아닌 글자의 연속**으로(2026-09-05 언어 개정,
        # 사용자 판정): 열 이름은 세계의 명사라 `㎡당만원`·`%비율`·`₩` 처럼 단어 문자로 시작하지 않는 것이 흔한데,
        # 옛 판(알파벳·숫자·_ 만)은 `{set: {㎡당만원: "…"}}` 를 "해석된 키: [없음]" 으로 거절했고 진단은 값
        # 이스케이프를 가리켰다(시스템 AI 보고 — 열 이름을 바꿔 우회). 값 자리(`columns: ["㎡당만원"]`)는
        # 원래 받던 이름이 키 자리에서만 막히던 비대칭. JSON5 가 식별자 규칙으로 거절해도 이 폴백이 받는다.
        key_start = i
        if inner[i] in '"\'':
            key, i = _extract_string(inner, i, inner[i])
        else:
            while i < n and inner[i] not in _KEY_STOP:
                i += 1
            key = inner[key_start:i]
        if not key:
            _reject_residue(inner, i, params)
            break

        # 공백 건너뛰기
        while i < n and inner[i] in ' \t':
            i += 1

        # : 건너뛰기
        if i < n and inner[i] == ':':
            i += 1
        else:
            _reject_residue(inner, key_start, params)
            break

        # 공백 건너뛰기
        while i < n and inner[i] in ' \t':
            i += 1

        if i >= n:
            break

        # value 추출
        value, i = _extract_value(inner, i)
        params[key] = value

    return params


def _extract_value(text: str, pos: int):
    """
    위치 pos에서 value를 추출. (value, new_pos) 반환.

    지원 타입: "string", 'string', [array], {object}, number, true/false/null, 미따옴표 문자열
    """
    if pos >= len(text):
        return "", pos

    ch = text[pos]

    # 문자열 (큰따옴표)
    if ch == '"':
        return _extract_string(text, pos, '"')

    # 문자열 (작은따옴표)
    if ch == "'":
        return _extract_string(text, pos, "'")

    # 배열
    if ch == '[':
        return _extract_bracket(text, pos, '[', ']')

    # 중첩 객체
    if ch == '{':
        return _extract_bracket(text, pos, '{', '}')

    # 숫자 (음수 포함)
    if ch in '-0123456789':
        return _extract_number(text, pos)

    # 변수 참조 `${이름.경로}` (언어 개정 2026-09-04, 사용자 판정): 따옴표 밖에서도 `$이름` 과 같다.
    # 옛 판은 `$` 를 미따옴표 문자열로 읽다가 `{` 에서 끊겨 "파라미터를 끝까지 읽지 못했습니다" 로 죽었다 —
    # 모델은 수치 자리에도 `${x}` 를 쓴다(관용구 되돌려 묻기 12건 중 2건). 반환은 `${…}` 원문 그대로 —
    # 치환기(REF_RE)가 괄호형·맨몸형을 같은 참조로 본다.
    if ch == '$' and text[pos + 1:pos + 2] == '{':
        j = text.find('}', pos + 2)
        if j != -1:
            return text[pos:j + 1], j + 1

    # boolean / null
    if text[pos:pos + 4] == 'true':
        return True, pos + 4
    if text[pos:pos + 5] == 'false':
        return False, pos + 5
    if text[pos:pos + 4] == 'null':
        return None, pos + 4

    # 따옴표 없는 문자열 (다음 , 또는 } 까지)
    return _extract_unquoted(text, pos)


# 표준 이스케이프 표 (JSON/JSON5 공통). 이 표에 없는 것은 백슬래시째 보존한다.
_SIMPLE_ESCAPES = {
    'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f', 'v': '\v',
    '0': '\0', '"': '"', "'": "'", '\\': '\\', '/': '/',
    '\n': '', '\r': '',  # 줄 이음(JSON5 line continuation)
}
_HEX = '0123456789abcdefABCDEF'


def _extract_string(text: str, pos: int, quote: str):
    r"""따옴표 문자열 추출 — 표준 이스케이프를 해석한다.

    2026-08-22 수리: 예전에는 백슬래시를 버리고 다음 글자를 그대로 넣어서
    `\n` 이 글자 `n` 으로 박혔다. 보고서 본문이 한 줄로 뭉개지던 원인
    (data/guides/youtube_ai_tips_report.md 2026-08-20 실측 ①).

    모르는 이스케이프는 **백슬래시째 보존**한다 — `[self:grep]{pattern: "\d+"}`
    의 `\d` 가 글자 `d` 로 뭉개지던 같은 부류의 손실을 막는다.
    """
    i = pos + 1  # 여는 따옴표 건너뛰기
    result = []
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '\\' and i + 1 < n:
            esc = text[i + 1]
            # \uXXXX / \xXX — 코드포인트
            if esc == 'u' and i + 6 <= n and all(c in _HEX for c in text[i + 2:i + 6]):
                result.append(chr(int(text[i + 2:i + 6], 16)))
                i += 6
                continue
            if esc == 'x' and i + 4 <= n and all(c in _HEX for c in text[i + 2:i + 4]):
                result.append(chr(int(text[i + 2:i + 4], 16)))
                i += 4
                continue
            if esc in _SIMPLE_ESCAPES:
                result.append(_SIMPLE_ESCAPES[esc])
            else:
                result.append('\\')   # 모르는 이스케이프는 원문 보존
                result.append(esc)
            i += 2
        elif ch == quote:
            i += 1  # 닫는 따옴표 건너뛰기
            return ''.join(result), i
        else:
            result.append(ch)
            i += 1
    return ''.join(result), i


def _extract_bracket(text: str, pos: int, open_br: str, close_br: str):
    """bracket 매칭으로 배열/객체 추출. JSON 파싱 시도 후 실패하면 재귀."""
    depth = 0
    i = pos
    while i < len(text):
        ch = text[i]
        if ch == open_br:
            depth += 1
        elif ch == close_br:
            depth -= 1
            if depth == 0:
                raw = text[pos:i + 1]
                # 표준 밖 이스케이프(`\d` 등)는 JSON5 가 백슬래시째 먹으므로 우회 (위 주석 참조)
                if not _has_nonstandard_escape(raw):
                    # 1. JSON5 시도 — 모든 JSON-like 입력의 표준 해석기
                    try:
                        import pyjson5
                        return pyjson5.loads(raw), i + 1
                    except Exception:
                        pass
                    # 2. 표준 JSON (JSON5 부재 시 보험)
                    try:
                        return json.loads(raw), i + 1
                    except (json.JSONDecodeError, ValueError):
                        pass
                    # 3. 값 안의 진짜 개행·탭만 이스케이프해 한 번 더 — 실패=원본 문자열 폴백은
                    #    소비자에게 통화 아닌 str 을 조용히 넘긴다(침묵). 살릴 수 있으면 살린다.
                    _esc = _escape_control_in_strings(raw)
                    if _esc != raw:
                        try:
                            import pyjson5
                            return pyjson5.loads(_esc), i + 1
                        except Exception:
                            pass
                        try:
                            return json.loads(_esc), i + 1
                        except (json.JSONDecodeError, ValueError):
                            pass
                # 3. 중첩 객체면 재귀적 relaxed 파싱
                if open_br == '{':
                    return _parse_relaxed_params(raw), i + 1
                # 배열이면 원본 문자열 반환 (최선)
                return raw, i + 1
        elif ch in '"\'':
            # 문자열 리터럴 내부 건너뛰기
            quote = ch
            i += 1
            while i < len(text) and text[i] != quote:
                if text[i] == '\\':
                    i += 1
                i += 1
        i += 1
    # 닫는 bracket을 못 찾으면 원본 반환
    return text[pos:], len(text)


def _extract_number(text: str, pos: int):
    """숫자 추출 (정수/실수, 음수 포함)"""
    i = pos
    if i < len(text) and text[i] == '-':
        i += 1
    while i < len(text) and text[i].isdigit():
        i += 1
    if i < len(text) and text[i] == '.':
        i += 1
        while i < len(text) and text[i].isdigit():
            i += 1
    raw = text[pos:i]
    # ★B35-1 2단계 (2026-08-24 #repair): 앞자리가 0 인 정수 리터럴은 **수량이 아니라 식별자**다.
    #   앞 0 을 붙여 쓰는 수는 세상에 없고, 그렇게 쓰는 건 전부 코드다 — 종목(005930)·
    #   우편번호·계좌·법정동코드. int() 는 그 0 을 지우고, 지워진 뒤에는 아무도 되살릴 수
    #   없다: 35회차가 `ticker: 005930` → 5930 을 실측하고 "str() 변환도 불가"라며 관문
    #   수리를 막다른 길로 판정한 근거가 이것이었다. 정보가 사라지는 자리는 관문이 아니라
    #   **여기**이므로 여기서 지키지 않으면 아래층 어디서도 못 고친다.
    #   파급 실측: 코퍼스 3,610 문장의 파스 트리를 이 규칙 적용 전후로 대조해 **변화 0건**
    #   (앞 0 리터럴은 전부 따옴표 안 시각·날짜라 이 함수에 오지도 않는다).
    _digits = raw[1:] if raw[:1] == '-' else raw
    if '.' not in raw and len(_digits) > 1 and _digits[:1] == '0':
        return raw, i
    try:
        return float(raw) if '.' in raw else int(raw), i
    except ValueError:
        return raw, i


def _extract_unquoted(text: str, pos: int):
    """따옴표 없는 문자열: 다음 , 또는 } 또는 ] 까지"""
    i = pos
    while i < len(text) and text[i] not in ',}]':
        i += 1
    return text[pos:i].strip(), i
