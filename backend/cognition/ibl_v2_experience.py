"""Keep successful v2 programs intact across memory selection boundaries."""
import json
from ibl_edition import explicit_source, source_edition
from ibl_v2_ir import Fault, Node, digest


def straight_calls(source, strict=False):
    """정적으로 확실한 호출만 읽는다. 분기·정의·지연 본문을 실행으로 세지 않는다."""
    from ibl_v2_parser import parse
    calls = []

    def visit(node):
        if node is None:
            return
        if node.kind == 'sequence':
            for statement in node.data['statements']:
                visit(statement)
                if statement.kind == 'return':
                    break
        elif node.kind in {'bind', 'return'}:
            visit(node.data['value'])
        elif node.kind in {'pipe', 'parallel'}:
            visit(node.data['left'])
            visit(node.data['right'])
        elif node.kind == 'call' and node.data.get('body') is None:
            calls.append(node)
        elif node.kind == 'def' and not strict:
            return
        elif node.kind not in {'literal', 'ref'}:
            raise ValueError('conditional_or_delayed_execution')

    try:
        visit(parse(source))
        return calls
    except (Fault, ValueError, TypeError, KeyError):
        return []


def recall_signatures(source, strict=False):
    """판본 1과 같은 동작 선택 인자. 동적 선택 인자는 추측해서 귀속하지 않는다."""
    result = []
    for call in straight_calls(source, strict):
        params = {}
        for key, value in call.data['params'].data['fields'].items():
            if key in {'op', 'mode', 'source', 'store', 'format', 'do'}:
                if value.kind != 'literal':
                    return []
                params[key] = value.data['value']
        result.append((call.data['node'], call.data['action'], params))
    return result


def url_only_head(source):
    from ibl_v2_parser import parse
    try:
        statements = parse(source).data['statements']
        if len(statements) != 1:
            return None
        node = statements[0]
        if node.kind in {'return', 'bind'}:
            node = node.data['value']
        if node.kind != 'call' or node.data.get('body') is not None:
            return None
        fields = node.data['params'].data['fields']
        if set(fields) == {'url'} and fields['url'].kind == 'literal':
            url = fields['url'].data['value']
            if isinstance(url, str) and url.startswith(('https://', 'http://')) and '$' not in url:
                return node.data['node'], node.data['action']
    except (Fault, ValueError, TypeError, KeyError, AttributeError):
        pass
    return None


def closed_call(tc, *, turn_cost=None):
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
            return abstract_call(tc, request, result, turn_cost=turn_cost)
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


def _learning_store(turn_cost):
    """Restarted distillation reads only the recorded turn's existing evidence directory."""
    from pathlib import Path
    from runtime_utils import get_base_path
    from supervision_store import TurnStore, trace_directory
    from trace_read import ReadFault
    path = (turn_cost or {}).get('events_path')
    if not path:
        return None
    from common.spill import spill_dir
    root = Path(spill_dir()) / 'supervision'   # 스필 루트 시임(2026-10-04)
    path = Path(path)
    try:
        directory = trace_directory(root, path.parent.name)
        if path != directory / 'events.jsonl' or not directory.is_dir():
            raise ValueError('원 실행 증거 저장소 경로를 확인할 수 없습니다.')
    except ReadFault as exc:
        raise ValueError('원 실행 증거 저장소 경로를 확인할 수 없습니다.') from exc
    return TurnStore(directory)


def abstract_call(tc, request, result, *, turn_cost=None):
    from ibl_v2_parser import parse
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    from ibl_v2_store import definitions
    source = explicit_source(request['code'], 2)
    original = parse(source)
    inputs = request['inputs']
    if not isinstance(inputs, dict):
        raise ValueError('inputs must be a record')
    from model_result_view import resolve_input_refs
    store = _learning_store(turn_cost) if result.get('inputs_resolved') else None
    inputs, notes = resolve_input_refs(inputs, store=store)
    if notes or result.get('inputs_resolved'):
        if not result.get('plan_hash') or digest(notes) != digest(result.get('inputs_resolved')):
            raise ValueError('원 실행 입력 참조의 근거가 없거나 변경되었습니다.')
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
