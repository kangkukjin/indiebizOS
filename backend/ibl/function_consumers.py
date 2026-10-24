"""Read persistent callers from their existing owners for function mutations."""
import json
from pathlib import Path

import function_store


def stored_programs():
    # Runtime state and repair workspaces must not inspect the live owner's tree.
    root = function_store.storage_root().parent.parent
    paths = [root / 'data' / 'calendar_events.json']
    paths.extend((root / 'data' / 'instruments').glob('*.yaml'))
    paths.extend((root / 'projects').glob('*/schedules.json'))
    import yaml

    def walk(value, location):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('code', 'pipeline', 'do', 'action', 'load', 'options_action') and isinstance(item, str):
                    if not isinstance(value.get('function_refs'), list):
                        yield location, item
                elif key == 'workflow_id' and isinstance(item, str):
                    yield location, {'workflow_id': item}
                elif key == 'function_refs' and isinstance(item, list):
                    for ref in item:
                        if isinstance(ref, dict):
                            yield location, ref
                elif key == 'function_ref' and isinstance(item, dict):
                    yield location, item
                else:
                    yield from walk(item, location + '.' + str(key))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                yield from walk(item, location + f'[{i}]')

    for path in paths:
        if path.is_file() and not path.is_symlink():
            value = yaml.safe_load(path.read_text()) if path.suffix == '.yaml' else json.loads(path.read_text())
            yield from walk(value, str(path))


def validate_consumers(before, after, changed, registry, prior_registry=None):
    from function_library import definitions
    from ibl_v2_compile import compile_program
    from ibl_v2_ir import Fault
    from ibl_edition import source_edition
    old, new = definitions(before), definitions(after)
    from ibl_v2_parser import parse
    from ibl_v2_ir import Node
    from ibl_v2_types import UNKNOWN

    def input_types(program):
        names, pending = set(), [parse(program)]
        while pending:
            item = pending.pop()
            if isinstance(item, Node):
                if item.kind == 'ref':
                    names.add(item.data['name'])
                pending.append(item.data)
            elif isinstance(item, dict):
                pending.extend(item.values())
            elif isinstance(item, (list, tuple)):
                pending.extend(item)
        return {name: UNKNOWN for name in names if name not in ('it', 'i', 'error')}

    for location, program in stored_programs():
        if isinstance(program, dict):
            for fid in changed:
                previous = before['records'].get(fid)
                following = after['records'][fid]
                if not previous:
                    continue
                names = [previous['name'], *previous.get('legacy_ids', [])]
                matches = program.get('function_id') == fid or program.get('workflow_id') in names
                if matches and (following['state'] != 'active' or previous['name'] != following['name']):
                    raise ValueError(f'저장 소비자가 관용구를 참조합니다: {location}')
            continue
        if source_edition(program) == 1:
            row = {'source': program}
            previous_errors = legacy_issues(row, before)
            errors = legacy_issues(row, after)
            if not previous_errors and errors:
                raise ValueError(f'저장 소비자가 깨집니다: {location}: {errors[0]}')
        try:
            types = input_types(program)
            if compile_program(program, prior_registry if prior_registry is not None else registry, definitions=old, input_types=types).issues:
                continue
        except Fault:
            continue
        try:
            errors = compile_program(program, registry, definitions=new, input_types=types).issues
        except Fault as exc:
            errors = [{"message": str(exc)}]
        if errors:
            raise ValueError(f'저장 소비자가 깨집니다: {location}: {errors[0]["message"]}')


def legacy_issues(row, view):
    """Check statically named legacy calls using parser-owned bindings/signatures."""
    from ibl_parser import parse_function_body, IBLSyntaxError
    from workflow_contract import call_signature, _signature_of, normalize_steps_for_injection, pipe_input_param
    contracts = {}
    for target in view['records'].values():
        if target.get('state') != 'active' or target.get('problem'):
            continue
        try:
            if target['edition'] == 2:
                from ibl_v2_parser import parse
                node = parse(target['source']).data['statements'][0]
                params = node.data['params']
                required = {k for k, v in params.items() if v is None}
                receiver = next(iter(params), None)
            else:
                wf = target.get('legacy') or {}
                body = wf.get('do') or wf.get('steps') or wf.get('pipeline') or target['source']
                params = _signature_of(body) if wf else call_signature(body)
                defaults = wf.get('params_default') or {}
                required = set(params) - defaults.keys()
                params = set(params) | defaults.keys()
                steps, why = normalize_steps_for_injection(body) if wf else (parse_function_body(body), None)
                receiver = pipe_input_param(steps) if not why else None
            for name in [target['name'], *target.get('legacy_ids', [])]:
                contracts[name] = (set(params), required, receiver)
        except (ValueError, TypeError, KeyError, IBLSyntaxError):
            continue
    problems, parsed_strings = [], set()

    def scan(value, piped=False):
        if isinstance(value, list):
            for i, item in enumerate(value):
                scan(item, i > 0 and isinstance(item, dict) and not item.get('_seq_boundary'))
        elif isinstance(value, dict):
            if value.get('_node') == 'fn' and not value.get('_fn_ref'):
                name = value.get('action')
                if name not in contracts:
                    problems.append(f'관용구 참조를 찾을 수 없습니다: {name}')
                else:
                    allowed, required, receiver = contracts[name]
                    supplied = set(value.get('params') or {})
                    if piped and receiver:
                        supplied.add(receiver)
                    if required - supplied or supplied - allowed:
                        problems.append(f'{name}: 호출 인자와 현재 서명이 다릅니다')
            for child in value.values():
                scan(child)
        elif isinstance(value, str) and '[' in value and ':' in value and value not in parsed_strings:
            parsed_strings.add(value)
            try:
                scan(parse_function_body(value))
            except (ValueError, IBLSyntaxError):
                pass
    wf = row.get('legacy') or {}
    body = wf.get('do') or wf.get('steps') or wf.get('pipeline') or row['source']
    if isinstance(body, str):
        try:
            scan(parse_function_body(body))
        except (ValueError, IBLSyntaxError):
            return []  # The syntax gate reports malformed definitions separately.
    else:
        scan(body)
    return problems
