"""문법이 맞는 문장들의 조합 경계 시험. 기대값은 실행 결과와 독립적으로 정의."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: E402,F401
import json


def literal(value):
    return json.dumps(value, ensure_ascii=False)


def cases():
    out = []

    def add(name, code, expected=None, error=False, contains=None):
        out.append(dict(id=name, code=code, expected=expected, error=error, contains=contains))

    for i, value in enumerate(['서울', '007', '따옴표"와\'작은따옴표', '줄1\n줄2\\경로', 0, 7, True, False]):
        add(f'fn_identity_{i}', '[def:항등]{$return = $값}\n[fn:항등]{값:' + literal(value) + '}', value)
        add(f'fn_quoted_{i}', '[def:문자]{$return = "값=${값}"}\n[fn:문자]{값:' + literal(value) + '}', '값=' + str(value))
        body = '[table:take]{items:[{got:\'$it.v\'}],n:1}'
        add(f'each_text_{i}', '[table:each]{items:' + literal([{'v': value}]) + ',do:' + literal(body) + '}', [{'got': str(value)}])

    for i, value in enumerate(['서울', 0, False, None]):
        row = {'user': {'value': value}, 'rows': [{'name': value}]}
        for path in ['user.value', 'rows.0.name']:
            body = '[table:take]{items:[{got:$it.' + path + '}],n:1}'
            add(f'each_path_{i}_{path}', '[table:each]{items:' + literal([row]) + ',do:' + literal(body) + '}', [{'got': value}])
        add(f'fn_path_{i}', '[def:행]{$return = [table:take]{items:[{got:"$자료.user.value"}],n:1}}\n[fn:행]{자료:' + literal(row) + '}', [{'got': value}])

    for parallel in [1, 2]:
        for var in ['it', '행']:
            body = '[try]{[self:read]{path:\'없는파일.txt\'}} [catch]{[table:take]{items:[{id:$' + var + '.id,why:\'$error.summary\'}],n:1}}'
            add(f'each_catch_{parallel}_{var}', '[table:each]{items:[{id:1},{id:2}],as:' + literal(var) + ',parallel:' + str(parallel) + ',do:' + literal(body) + '}', contains='없는파일')
            body = '[repeat:2]{[table:take]{items:[{id:$' + var + '.id,n:$i}],n:1}}'
            # 기존 repeat 계약: i는 0부터 시작하고 param 값 치환은 문자열이다.
            add(f'each_repeat_{parallel}_{var}', '[table:each]{items:[{id:1}],as:' + literal(var) + ',parallel:' + str(parallel) + ',do:' + literal(body) + '}', [{'id': 1, 'n': '1'}])

    add('each_literal_dotted_key', '[table:each]{items:[{"a.b":7,a:{b:8}}],do:"[table:take]{items:[{got:$it.a.b}],n:1}"}', [{'got': 7}])
    add('empty_each', '[table:each]{items:[],do:"[self:read]{path:\'없는파일.txt\'}"}', [])
    add('empty_fn', '[def:빈것]{$return = [table:take]{items:[],n:3}}\n[fn:빈것]{}', [])
    add('fn_arithmetic', '[def:계산]{$return = $n * 2 + 1}\n[fn:계산]{n:4}', 9)
    add('pipeline_dedup', '[table:dedup]{items:[{n:1},{n:1},{n:2}],by:"n"} >> [table:take]{n:1}', [{'n': 1}])
    add('fn_data_is_not_code', '[def:문자]{$return = "${a}/${b}"}\n[fn:문자]{a:"$b",b:"끝"}', '$b/끝')
    add('fn_field_missing', '[def:행]{$return = [table:take]{items:[{got:"$자료.missing"}],n:1}}\n[fn:행]{자료:{id:1}}', error=True)
    add('each_field_missing', '[table:each]{items:[{id:1}],do:"[table:take]{items:[{got:\'$it.missing\'}],n:1}"}', error=True)
    add('each_unbound_error', '[table:each]{items:[{id:1}],do:"[table:take]{items:[{got:\'$error.summary\'}],n:1}"}', error=True)
    add('each_unbound_iteration', '[table:each]{items:[{id:1}],do:"[table:take]{items:[{got:\'$i\'}],n:1}"}', error=True)
    add('fn_missing_argument', '[def:계산]{$return=$n+1}\n[fn:계산]{}', error=True)
    add('each_wrong_alias', '[table:each]{items:[{id:1}],as:"행",do:"[table:take]{items:[{got:\'$it.id\'}],n:1}"}', error=True)
    return out


def payload(result):
    value = result
    for _ in range(15):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return value
        elif isinstance(value, dict) and 'final_result' in value:
            value = value['final_result']
        elif isinstance(value, dict) and isinstance(value.get('items'), list):
            return value['items']
        elif isinstance(value, dict) and 'assigned' in value and 'value' in value:
            return value['value']
        else:
            return value
    raise ValueError('반환 봉투 깊이 초과')


def additional_cases():
    """첫 수리 뒤 선택한 추가 검증. 기존 56건 성적과 따로 센다."""
    specs = [
        ('fn_null', '[def:그대로]{$return=$v}\n[fn:그대로]{v:null}', None),
        ('fn_condition_true', '[def:분기]{[if:$v == "서울"]{$return=1}[else]{$return=0}}\n[fn:분기]{v:"서울"}', 1),
        ('fn_condition_false', '[def:분기]{[if:$v == "서울"]{$return=1}[else]{$return=0}}\n[fn:분기]{v:"부산"}', 0),
        ('fn_condition_field', '[def:분기]{[if:$v.city == "서울"]{$return=1}[else]{$return=0}}\n[fn:분기]{v:{city:"서울"}}', 1),
        ('fn_optional_field', '[def:그대로]{$return=[table:take]{items:[{v:"${r.missing?}"}],n:1}}\n[fn:그대로]{r:{x:1}}', [{'v': None}]),
        ('fn_action_data_reference', '[def:그대로]{$return=[table:take]{items:[{a:"$a",b:"$b"}],n:1}}\n[fn:그대로]{a:"$b",b:"끝"}', [{'a': '$b', 'b': '끝'}]),
        ('fn_list_identity', '[def:그대로]{$return=$v}\n[fn:그대로]{v:[{n:1}]}', [{'n': 1}]),
    ]
    return [dict(id=name, code=code, expected=value, error=False, contains=None)
            for name, code, value in specs]


def check(case, result):
    if case['error']:
        return result.get('success') is False
    if result.get('success') is not True:
        return False
    value = payload(result)
    if case['contains']:
        return (isinstance(value, list) and len(value) == 2
                and [r.get('id') for r in value] == [1, 2]
                and all(case['contains'] in r.get('why', '') for r in value))
    # Python의 False==0과 같은 비교로 타입 오류를 숨기지 않는다.
    return json.dumps(value, ensure_ascii=False, sort_keys=True) == json.dumps(case['expected'], ensure_ascii=False, sort_keys=True)
