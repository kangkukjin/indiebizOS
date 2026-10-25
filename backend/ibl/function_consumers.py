"""Read persistent callers from their existing owners for function mutations."""
import json
from pathlib import Path

import function_store


def stored_programs():
    # Runtime state and repair workspaces must not inspect the live owner's tree.
    root = function_store.storage_root().parent.parent
    paths = [root / 'data' / 'calendar_events.json', root / 'data' / 'event_triggers.json']
    paths.extend((root / 'data' / 'instruments').glob('*.yaml'))
    paths.extend((root / 'projects').glob('*/schedules.json'))
    paths.extend((root / 'data/ibl_nodes_src').glob('*.yaml'))
    paths.extend((root / 'data/packages/installed/tools').glob('*/ibl_actions.yaml'))
    import yaml

    def walk(value, location, inherited=None):
        if isinstance(value, dict):
            if value.get('enabled') is False or value.get('state') in ('retired', 'hold', 'quarantine'):
                return
            edition = value.get('edition', inherited)
            for key, item in value.items():
                if key in ('code', 'pipeline', 'do', 'action', 'load', 'options_action') and isinstance(item, str):
                    if not isinstance(value.get('function_refs'), list):
                        from ibl_edition import source_edition, pin_source
                        try:
                            current = source_edition(item, edition) == 2
                        except ValueError:
                            current = False
                        yield location, pin_source(item, 2) if current else item
                elif key == 'workflow_id' and isinstance(item, str):
                    yield location, {'workflow_id': item}
                elif key == 'function_refs' and isinstance(item, list):
                    for ref in item:
                        if isinstance(ref, dict):
                            yield location, ref
                elif key == 'function_ref' and isinstance(item, dict):
                    yield location, item
                else:
                    yield from walk(item, location + '.' + str(key), edition)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                yield from walk(item, location + f'[{i}]', inherited)

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
