"""다섯 번째 경계 실험: 반복 예산·빈 통화·파일 읽기 선택의 고정 100문장.

tail과 앞쪽 범위의 동시 지정은 이번에 명확히 하는 계약(오류)이며,
기존 문서 계약의 회귀와 별도로 센다. 기대값은 수리 전에 고정한다.
"""
from ibl_boundary_cases import literal as q


def cases():
    rows = []

    def add(name, code, expected=None, error=False, contract=False):
        rows.append(dict(id='r5_' + name, code=code, expected=expected,
                         error=error, contains=None, new_contract=contract))

    def wrap(code, named):
        return '[def:검증]{$return=' + code + '}\n[fn:검증]{}' if named else code

    for count in range(5):
        for cap in [None, 0, 1, 6]:
            n = count if cap is None else min(count, cap)
            header = str(count) + ('' if cap is None else ',max:' + str(cap))
            code = '[repeat:' + header + ',collect:true]{[table:take]{items:[{n:$i}],n:1}}'
            for named in [False, True]:
                add(f'count_{count}_{cap}_{named}', wrap(code, named),
                    [{'n': str(i)} for i in range(n)])

    for mode in ['while true', 'until false']:
        for collect in [False, True]:
            for named in [False, True]:
                # 실행하면 실패할 몸통. 상한 0이면 도구 호출도 없어야 한다.
                code = '[repeat:' + mode + ',max:0,collect:' + q(collect) + ']{[self:read]{path:"absent"}}'
                add(f'zero_{mode}_{collect}_{named}', wrap(code, named), [])

    def read(params, blocks, named):
        return wrap('[self:read]' + q(dict(path='note.txt', blocks=blocks, **params)), named)

    def expected_read(lines, blocks, first=1, ranged=True):
        if blocks:
            return [{'type': 'paragraph', 'text': '\n'.join(lines)}] if lines else []
        text = ''.join(line + '\n' for line in lines)
        if ranged:
            span = f'{first}-{first + len(lines) - 1}' if lines else '없음'
            text = f'[줄 {span} / 전체 2줄, 14바이트]\n' + text
        return text

    for tail in [1, 2, 3, '1']:
        lines = ['초안'] if int(tail) == 1 else ['제목', '초안']
        for blocks in [False, True]:
            for named in [False, True]:
                add(f'tail_{type(tail).__name__}_{tail}_{blocks}_{named}',
                    read({'tail': tail}, blocks, named), expected_read(lines, blocks, 3 - len(lines)))

    for i, (params, lines, first) in enumerate([
        ({'start_line': 2, 'end_line': 2}, ['초안'], 2),
        ({'start': 1, 'end': 2}, ['초안'], 2),
        ({'offset': 1, 'limit': 0}, [], 2),
        ({'start_line': 8, 'limit': 2}, [], 8),
    ]):
        for blocks in [False, True]:
            for named in [False, True]:
                add(f'range_{i}_{blocks}_{named}', read(params, blocks, named),
                    expected_read(lines, blocks, first))

    invalid = [{'tail': 1, key: value} for key, value in [
        ('offset', 0), ('start', 0), ('start_line', 1), ('end', 1), ('end_line', 1), ('limit', 0),
    ]] + [{'offset': True}, {'tail': True}, {'limit': False}, {'tail': 1.5}]
    for i, params in enumerate(invalid):
        for blocks in [False, True]:
            add(f'invalid_{i}_{blocks}', read(params, blocks, False), error=True, contract=i < 6)
    assert len(rows) == 100
    return rows
