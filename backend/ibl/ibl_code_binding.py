"""지연 IBL 코드의 값 치환. 파서/실행기가 공유하며 실행기 의존을 갖지 않는다."""
import json
import re
from common.ibl_vars import (
    ibl_escape as _each_escape, inside_ibl_string as _inside_string,
    ibl_literal as _each_literal,
)


def bind_scoped_code(sentence, resolve, blocked=frozenset()):
    """지연 파싱되는 코드의 참조를 한 번 치환. resolve(name, path) → (found, value).

    each 행·함수 인자·제어문 값이 같은 문자열/스코프 규약을 쓴다. 삽입 값은
    다시 참조로 훑지 않으며, 중첩 do의 코드 깊이와 안쪽 이름을 보존한다.
    """
    from common.ibl_vars import REF_RE, split_ref
    if isinstance(sentence, list):
        return [bind_scoped_code(s, resolve, blocked) for s in sentence]
    if not isinstance(sentence, str):
        return sentence

    def replace_range(start, end):
        parts, pos = [], start
        for match in REF_RE.finditer(sentence, start, end):
            name, path = split_ref(match)
            found, value = (False, None) if name in blocked else resolve(name, path)
            rendered = match.group(0)
            if found:
                rendered = (_each_escape(value) if _inside_string(sentence, match.start())
                            else _each_literal(value))
            parts.extend((sentence[pos:match.start()], rendered))
            pos = match.end()
        return ''.join(parts) + sentence[pos:end]

    pieces, cursor = [], 0
    for start, end, inner, bound in _scoped_regions(sentence):
        pieces.append(replace_range(cursor, start))
        if inner is None:
            pieces.append(sentence[start:end])  # 닫힌 함수 몸은 호출자가 채운다.
        else:
            rewritten = bind_scoped_code(inner, resolve, blocked | bound)
            pieces.append(json.dumps(rewritten, ensure_ascii=False))
        cursor = end
    pieces.append(replace_range(cursor, len(sentence)))
    return ''.join(pieces)


def _scoped_regions(sentence):
    """원문에서 별도 바인더가 소유하는 구간을 찾는다. 값/괄호 독해는 파서에 위임.

    AST를 다시 출력하면 '$it.n'과 $it.n의 문자열/숫자 구분이 없어지므로,
    원문을 보존하고 중첩 each의 do 및 닫힌 함수 정의만 구간으로 다룬다.
    반환 (start, end, decoded_code|None, bound_names).
    """
    from ibl_parser_values import _extract_value, _extract_string
    from ibl_parser_blocks import _extract_bracket_raw
    regions, pos = [], 0
    while pos < len(sentence):
        if sentence[pos] in '\"\'':
            _, pos = _extract_string(sentence, pos, sentence[pos])
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
            regions.append((pos, end + 1, None, set()))
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
                    regions.append((start, stop, value, {alias or 'it'}))
        pos = end + 1
    return regions


