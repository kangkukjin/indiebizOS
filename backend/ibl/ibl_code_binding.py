"""지연 IBL 코드의 값 치환. 파서/실행기가 공유하며 실행기 의존을 갖지 않는다."""
import json
import re
from common.ibl_vars import (
    ibl_escape as _each_escape, inside_ibl_string as _inside_string,
    ibl_literal as _each_literal,
)


def parse_binding_body(code):
    """자유 변수 검사용 AST. 값으로 운반한 Unicode dollar는 참조로 세지 않는다.

    실행할 원문/AST는 바꾸지 않는다. 검사에서만 전각 dollar로 바꿔 중첩 JSON을
    여러 번 디코딩해도 삽입된 데이터를 변수 참조로 다시 해석하지 않게 한다.
    """
    from ibl_parser import parse_function_body
    if isinstance(code, list) and all(isinstance(s, str) for s in code):
        code = '\n'.join(code)
    if not isinstance(code, str):
        return code
    return parse_function_body(code.replace('\\u0024', '\\uFF04'))


def bind_scoped_code(sentence, resolve, blocked=frozenset(), *, ref_re=None,
                     split=None, typed_paths=False):
    """지연 파싱되는 코드의 참조를 한 번 치환. resolve(name, path) → (found, value).

    each 행·함수 인자·제어문 값이 같은 문자열/스코프 규약을 쓴다. 삽입 값은
    다시 참조로 훑지 않으며, 중첩 do의 코드 깊이와 안쪽 이름을 보존한다.
    """
    from common.ibl_vars import REF_RE, split_ref
    ref_re, split = ref_re or REF_RE, split or split_ref
    options = dict(ref_re=ref_re, split=split, typed_paths=typed_paths)
    if isinstance(sentence, list):
        return [bind_scoped_code(s, resolve, blocked, **options) for s in sentence]
    if not isinstance(sentence, str):
        return sentence

    def replace_range(start, end):
        parts, pos = [], start
        for match in ref_re.finditer(sentence, start, end):
            name, path = split(match)
            found, value = (False, None) if name in blocked else resolve(name, path)
            rendered = match.group(0)
            if found:
                rendered = (_each_escape(value) if _inside_string(sentence, match.start())
                            else _each_literal(value))
            left, right = match.span()
            # 파이프의 통짜 .path 값은 따옴표로 감쌌어도 원형을 보존한다.
            # do를 다시 파싱할 때도 일반 param과 같은 계약이다.
            if (found and typed_paths and path and left > pos and right < end
                    and sentence[left - 1] in "\"'" and sentence[right] == sentence[left - 1]
                    and not _inside_string(sentence, left - 1)):
                left, right = left - 1, right + 1
                rendered = _each_literal(value)
            parts.extend((sentence[pos:left], rendered))
            pos = right
        return ''.join(parts) + sentence[pos:end]

    pieces, cursor = [], 0
    for start, end, inner, bound, encoded in _scoped_regions(sentence):
        pieces.append(replace_range(cursor, start))
        if inner is None:
            pieces.append(sentence[start:end])  # 닫힌 함수 몸은 호출자가 채운다.
        else:
            rewritten = bind_scoped_code(inner, resolve, blocked | bound, **options)
            pieces.append(json.dumps(rewritten, ensure_ascii=False) if encoded else rewritten)
        cursor = end
    pieces.append(replace_range(cursor, len(sentence)))
    return ''.join(pieces)


def _scoped_regions(sentence):
    """원문에서 별도 바인더가 소유하는 구간을 찾는다. 값/괄호 독해는 파서에 위임.

    AST를 다시 출력하면 '$it.n'과 $it.n의 문자열/숫자 구분이 없어지므로,
    원문을 보존하고 do·반복·오류 처리의 바인딩 범위와 주석/닫힌 정의를 다룬다.
    반환 (start, end, decoded_code|None, bound_names, JSON으로 인코딩할지).
    """
    from ibl_parser_values import _extract_value, _extract_string
    from ibl_parser_blocks import (_extract_bracket_raw, _block_header,
                                   _REPEAT_PREFIX, _repeat_options)
    regions, pos = [], 0
    while pos < len(sentence):
        if sentence[pos] == '#':
            end = sentence.find('\n', pos)
            end = len(sentence) if end < 0 else end
            regions.append((pos, end, None, set(), False))
            pos = end
            continue
        if sentence[pos] in '\"\'':
            _, pos = _extract_string(sentence, pos, sentence[pos])
            continue
        header = _block_header(sentence[pos:], _REPEAT_PREFIX) if sentence[pos] == '[' else None
        control = re.match(r'\[(catch|finally)\]\s*\{', sentence[pos:])
        if header is not None or control:
            brace = pos + (header[1] if header else control.end() - 1)
            raw, end = _extract_bracket_raw(sentence, brace, '{', '}')
            if raw is None:
                break
            bound = {_repeat_options(header[0])['var']} if header else {'error'}
            if header:
                start = pos + _REPEAT_PREFIX.match(sentence[pos:]).end()
                regions.append((start, brace, sentence[start:brace], bound, False))
            regions.append((brace + 1, end, raw, bound, False))
            pos = end + 1
            continue
        match = re.match(r'\[(table\s*:\s*each|def\s*:[^\]]+)\]\s*\{', sentence[pos:])
        if not match:
            pos += 1
            continue
        brace = pos + match.end() - 1
        raw, end = _extract_bracket_raw(sentence, brace, '{', '}')
        if raw is None:
            break  # 실제 파싱 단계가 닫히지 않은 블록을 진단한다.
        if match.group(1).startswith('def'):
            regions.append((pos, end + 1, None, set(), False))
        else:
            fields, idx = {}, brace + 1
            while idx < end:
                while idx < end and sentence[idx] in ' \t\r\n,':
                    idx += 1
                if idx >= end:
                    break
                if sentence[idx] in '\"\'':
                    key, idx = _extract_string(sentence, idx, sentence[idx])
                else:
                    key_match = re.match(r'\w+', sentence[idx:])
                    if not key_match:
                        break
                    key = key_match.group(0)
                    idx += len(key)
                while idx < end and sentence[idx].isspace():
                    idx += 1
                if idx >= end or sentence[idx] != ':':
                    break
                idx += 1
                while idx < end and sentence[idx].isspace():
                    idx += 1
                start = idx
                value, idx = _extract_value(sentence, idx)
                fields[key] = (start, idx, value)
            if 'do' in fields:
                start, stop, value = fields['do']
                alias = str(fields.get('as', (0, 0, 'it'))[2] or 'it').lstrip('$').strip()
                if isinstance(value, (str, list)):
                    regions.append((start, stop, value, {alias or 'it'}, True))
        pos = end + 1
    return regions
