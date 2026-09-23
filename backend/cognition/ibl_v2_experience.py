"""Keep successful v2 programs intact across memory selection boundaries."""
import json
from ibl_edition import explicit_source, source_edition
from ibl_v2_ir import Fault, Node, digest


def closed_call(tc):
    request = tc.get("input") or {}
    source = request.get("code", "")
    if source_edition(source, request.get("edition")) != 2:
        return tc
    result = tc.get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            return None
    if (not isinstance(result, dict) or
            result.get("success") is not True or result.get("executed") is not True or
            result.get("source_complete") is not True):
        return None
    if request.get("inputs"):
        try:
            return abstract_call(tc, request, result)
        except (ValueError, Fault) as exc:
            tc["reuse_excluded"] = str(exc)
            from episode_logger import record_trajectory_event
            record_trajectory_event("memory.reuse_excluded", {"source_sha256": digest(source), "reason": str(exc)})
            return None
    code = explicit_source(source, 2)
    from ibl_v2_learning import check_source
    if check_source(code):
        return None
    return {**tc, "input": {**request, "code": code}}


def select_program(ids, calls):
    selected = [calls[i - 1] for i in ids]
    if not any(source_edition(code) == 2 for code in selected):
        return None
    if len(selected) != 1:
        return (None, "판본 2 프로그램은 반환·범위가 닫힌 한 실행 단위로 선택하세요. 판본 혼합·호출 연결은 자동 생성하지 않습니다.")
    from ibl_v2_learning import check_source
    why = check_source(selected[0])
    return (None, why) if why else (selected[0], f"판본 2 원문 호출 {ids[0]}")


def structure(value):
    """Compare syntax, never compiler annotations or source offsets."""
    if isinstance(value, Node):
        return [value.kind, structure(value.data)]
    if isinstance(value, dict):
        return {k: structure(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [structure(v) for v in value]
    return value


def abstract_call(tc, request, result):
    from ibl_v2_parser import parse
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    from ibl_v2_store import definitions
    source = explicit_source(request['code'], 2)
    original = parse(source)
    inputs = request['inputs']
    if not isinstance(inputs, dict):
        raise ValueError('inputs must be a record')
    used = set()
    def visit(value):
        if isinstance(value, Node):
            if value.kind == 'ref' and value.data['name'] in inputs:
                used.add(value.data['name'])
            visit(value.data)
        elif isinstance(value, dict):
            for v in value.values():
                visit(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                visit(v)
    visit(original)
    if not used:
        raise ValueError('명시 입력을 쓰지 않은 프로그램은 입력 함수 후보로 만들지 않습니다.')
    registry, library = load_registry(), definitions()
    plan = compile_program(request["code"], registry, inputs, library)
    if plan.issues:
        raise ValueError('원 실행 의존성을 현재 해소할 수 없습니다.')
    # A changed dependency must not be credited with an earlier success.
    if result.get('plan_hash') and result['plan_hash'] != plan.fingerprint:
        raise ValueError('원 실행 이후 소스 또는 의존성이 변경되었습니다.')
    names = sorted(used)
    body = source.split('\n', 1)[1]
    name = '절차_' + digest([structure(original), names])[:9]
    code = '#!ibl edition=2\n[def:' + name + '](' + ','.join('$'+n for n in names) + '){\n' + body + '\n}'
    parsed = parse(code).data['statements'][0]
    if structure(parsed.data['body']) != structure(original):
        raise ValueError('입력 추출이 본문 구조를 바꿨습니다.')
    candidate = compile_program(code, registry, definitions=library)
    if candidate.issues:
        raise ValueError('명시 인자로 닫을 수 없는 자유 변수 또는 정의가 있습니다.')
    proof = {'protocol': 'ibl-input-abstraction/1', 'name': name, 'inputs': names,
             'source_sha256': digest(source), 'candidate_sha256': digest(code),
             'body_sha256': digest(structure(original)), 'original_plan_hash': result.get('plan_hash'),
             'candidate_plan_hash': candidate.fingerprint,
             'dependencies': {k: digest(v) for k, v in plan.dependencies.items()},
             'referenced_functions': [entry['name'] for entry in plan.dependencies['source_map'][1:]],
             'effects': sorted(plan.effects), 'new_input_successes': 0}
    # The prepared candidate carries names/proof only, never the original values.
    return {**tc, 'input': {'code': code, 'edition': 2}, '_ibl_abstraction': proof}


def finalize_candidate(row, proposed_name=''):
    """The reflection model may name a verified wrapper, never edit its body."""
    from ibl_v2_parser import parse
    from ibl_v2_learning import check_source
    from ibl_v2_store import definitions
    code, proof = row['code'], row.get('abstraction')
    if not proof:
        return code, '', ''
    if digest(code) != proof['candidate_sha256']:
        raise ValueError('함수 후보 출처가 달라졌습니다.')
    node = parse(code).data['statements'][0]
    if (node.kind != 'def' or node.data['name'] != proof['name'] or
            sorted(node.data['params']) != proof['inputs'] or
            digest(structure(node.data['body'])) != proof['body_sha256']):
        raise ValueError('허용된 입력 추출이 아닙니다.')
    name = proposed_name if isinstance(proposed_name, str) else ''
    if not name.isidentifier() or len(name) > 12 or name in {'it', 'i', 'error'}:
        name = proof['name']
    from ibl_v2_adapters import load_registry
    registry, library = load_registry(), definitions()
    from ibl_v2_compile import compile_program
    if compile_program(code, registry, definitions=library).fingerprint != proof['candidate_plan_hash']:
        raise ValueError('후보 생성 이후 의존성이 변경되었습니다.')
    if name in library or 'fn:' + name in registry:
        name = proof['name']
    if name in library or 'fn:' + name in registry:
        raise ValueError('이미 같은 이름의 함수가 있습니다.')
    code = code.replace('[def:' + proof['name'] + ']', '[def:' + name + ']', 1)
    from ibl_idiom import _phrase_private_reason
    if _phrase_private_reason(code):
        raise ValueError('개인 명사가 남은 함수는 재사용 자산으로 저장하지 않습니다.')
    renamed = parse(code).data['statements'][0]
    if structure(renamed.data['body']) != structure(node.data['body']) or check_source(code, True):
        raise ValueError('저장 전 함수 동일성 검사 실패')
    from ibl_v2_compile import compile_program
    plan = compile_program(code, registry, definitions=library)
    contract = plan.function_contracts[plan.root.data['statements'][0].id]
    return code, name, contract['result']
