"""Change plans are ordinary IBL programs; owners still perform every mutation.

The returned source and inputs live in the existing execution journal. This module
does not publish definitions, grant authority, commit files, or keep a task store.
"""
import copy
import hashlib
import json
import os
from pathlib import Path

import yaml


def digest(value):
    from function_store import digest as hash_value
    return hash_value(value)


def roots():
    from runtime_utils import get_base_path
    from thread_context import get_repair_workspace
    import function_store
    code = Path(get_repair_workspace() or get_base_path()).resolve()
    functions = Path(os.environ.get('INDIEBIZ_FUNCTION_STORE_ROOT') or function_store.storage_root()).resolve()
    return code, functions


def read_registry(root):
    path = root / 'data/scripts/registry.yaml'
    value = yaml.safe_load(path.read_text()) if path.is_file() else {}
    if not isinstance(value, dict) or any(not isinstance(v, dict) for v in value.values()):
        raise ValueError('스크립트 등록부 형식이 잘못되었습니다.')
    return value


def source_path(root, raw):
    from runtime_utils import expand_body_path
    path = Path(expand_body_path(str(raw)))
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(root):
        raise ValueError('변경 소스는 현재 코드 작업 범위 안에 있어야 합니다.')
    return path


def observe(kind, target, root, functions):
    if kind == 'idiom':
        import function_store
        row = function_store.resolve(target, root=functions, include_inactive=True)
        if row is None:
            row = function_store.resolve(function_id=target, root=functions, include_inactive=True)
        return {'present': bool(row and row.get('state') == 'active'),
                'revision': (row or {}).get('revision', ''), 'record': row}
    if kind == 'script':
        from script_mutation import revision
        entry = read_registry(root).get(target)
        return {'present': entry is not None, 'revision': revision(entry, root / 'data/scripts'),
                'record': entry}
    if kind != 'action' or target.count(':') != 1:
        raise ValueError('kind는 idiom/script/action, 어휘 target은 node:action입니다.')
    from ibl_registry import load_nodes_owned
    node, action = target.split(':')
    record = load_nodes_owned().get('nodes', {}).get(node, {}).get('actions', {}).get(action)
    return {'present': record is not None, 'revision': digest(record) if record else '', 'record': record}


def _literal(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _call(action, args):
    return '[' + action + ']' + _literal(args)


def _files(request, root):
    from capability_change_checks import changed_files
    files = request.get('files')
    if files is None:
        meta = root / 'data/package_meta.json'
        owners = json.loads(meta.read_text()).get('action_owner', {}) if meta.is_file() else {}
        owner = owners.get(request['target'])
        prefix = ('data/packages/installed/tools/' + owner + '/' if owner else
                  'data/ibl_nodes_src/' + request['target'].split(':')[0] + '.yaml')
        files = [p for p in changed_files(root) if p.startswith(prefix)]
    if not isinstance(files, list) or any(not isinstance(p, str) for p in files):
        raise ValueError('files는 현재 변경 파일 목록입니다.')
    result = {}
    for name in sorted(set(files)):
        path = source_path(root, name)
        rel = path.relative_to(root).as_posix()
        if rel.startswith(('.git/', 'data/_backups/')) or path.name == '.env':
            raise ValueError('변경 검사에 포함할 수 없는 경로입니다.')
        result[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return result


def plan(request):
    if not isinstance(request, dict):
        raise ValueError('request는 변경 요청 객체입니다.')
    request = copy.deepcopy(request)
    if set(request) == {'changes'}:
        return batch(request['changes'])
    extra = set(request) - {'kind', 'target', 'operation', 'source', 'code', 'description',
                            'registration', 'expected_revision', 'probes', 'files', 'reason', 'request_id', 'apply'}
    if extra:
        raise ValueError('알 수 없는 변경 인자: ' + ', '.join(sorted(extra)))
    kind, target, operation = (request.get(k) for k in ('kind', 'target', 'operation'))
    if kind not in {'idiom', 'script', 'action'} or operation not in {'add', 'update', 'remove'}:
        raise ValueError('kind: idiom/script/action; operation: add/update/remove')
    if not isinstance(target, str) or not target.strip():
        raise ValueError('target을 지정하세요.')
    root, functions = roots()
    old = observe(kind, target, root, functions)
    if 'expected_revision' in request and request['expected_revision'] != old['revision']:
        raise ValueError('변경 계획의 판본이 오래됐습니다. 현재 대상을 다시 읽으세요.')
    if kind != 'action':
        if operation == 'add' and old['present']:
            raise ValueError('이미 등록된 대상입니다. update를 사용하세요.')
        if operation != 'add' and not old['present']:
            raise ValueError('변경할 활성 대상이 없습니다.')
    mutation, expected = None, None
    impact = {'callers': [], 'unknown': []}
    files = {}
    if kind == 'idiom':
        import function_store
        from function_library import definitions
        from ibl_v2_adapters import load_registry
        from ibl_v2_compile import compile_program
        from ibl_v2_store import definition_name
        if operation == 'remove':
            mutation = ('self:workflow', {'op': 'delete', 'workflow_id': target,
                                         'expected_revision': old['revision']})
        else:
            source = request.get('code')
            if source is None and request.get('source'):
                source = source_path(root, request['source']).read_text()
            if not isinstance(source, str) or definition_name(source) != target:
                raise ValueError('code/source의 함수 이름과 target이 일치해야 합니다.')
            library = definitions(function_store.snapshot(functions))
            library[target] = source
            # A candidate never borrows the old certified interface.
            library.interfaces.pop(target, None)
            report = compile_program(source, load_registry(), definitions=library).report()
            if not report['ok']:
                raise ValueError('관용구 후보 검사 실패: ' + str(report['issues']))
            expected = source
            mutation = ('self:workflow', {'op': 'save', 'code': source, 'workflow_id': target,
                                         'expected_revision': old['revision'] or None,
                                         'description': request.get('description', (old['record'] or {}).get('description', '')),
                                         'reason': request.get('reason', '')})
    elif kind == 'script':
        from capability_consumers import validate_script_change
        from script_mutation import FIELDS
        before = read_registry(root)
        after = copy.deepcopy(before)
        if operation == 'remove':
            after.pop(target)
            mutation = ('self:script', {'op': 'remove', 'id': target, 'expected_revision': old['revision']})
        else:
            path = source_path(root, request.get('source') or 'data/scripts/' + (old['record'] or {}).get('file', ''))
            directory = (root / 'data/scripts').resolve()
            if not path.is_file() or not path.is_relative_to(directory):
                raise ValueError('등록할 실존 파일을 data/scripts 안에 준비하세요.')
            registration = request.get('registration') or {}
            if not isinstance(registration, dict) or set(registration) - {'interpreter', 'timeout', 'callable_contract'}:
                raise ValueError('registration: interpreter/timeout/callable_contract만 지원합니다.')
            entry = {**(old['record'] or {}), **registration, 'file': path.relative_to(directory).as_posix()}
            entry.setdefault('interpreter', {'.py': 'python', '.sh': 'bash', '.js': 'node'}.get(path.suffix))
            entry.setdefault('timeout', 300)
            entry['description'] = request.get('description', entry.get('description', ''))
            if path.suffix == '.py':
                import ast
                ast.parse(path.read_text(), filename=str(path))
            if entry.get('callable_contract'):
                from ibl_v2_adapters import validate_contract
                validate_contract(entry['callable_contract'])
            after[target] = entry
            expected = {k: entry.get(k) for k in FIELDS}
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            mutation = ('self:script', {'op': 'register', 'id': target, 'path': str(path),
                                       **{k: entry[k] for k in ('interpreter', 'timeout', 'callable_contract') if k in entry},
                                       'description': entry['description'],
                                       'expected_source_hash': files[path.relative_to(root).as_posix()],
                                       'expected_revision': old['revision']})
        if request.get('files') is not None:
            files.update(_files(request, root))
        impact = validate_script_change(root, root / 'data/scripts/registry.yaml', before, after, target, functions)
    else:
        from capability_consumers import references
        if operation == 'update' and not old['present']:
            raise ValueError('수정할 어휘가 없습니다. 추가는 add를 사용하세요.')
        files = _files(request, root)
        if not files:
            raise ValueError('어휘 변경은 기존 편집 경로로 준비한 파일 변경이 필요합니다.')
        impact = references('action', target, root, functions)
        if operation == 'remove' and impact['callers']:
            raise ValueError('어휘 호출자를 먼저 전환하세요: ' + ', '.join(r['location'] for r in impact['callers']))
    probes = request.get('probes', [])
    if not isinstance(probes, list):
        raise ValueError('probes는 code/inputs/expected를 가진 검사 목록입니다.')
    for probe in probes:
        if (not isinstance(probe, dict) or not isinstance(probe.get('code'), str)
                or 'expected' not in probe or set(probe) - {'code', 'inputs', 'expected'}):
            raise ValueError('각 probe에는 code와 expected, 선택 inputs만 지정하세요.')
    apply_args = request.get('apply', {})
    if not isinstance(apply_args, dict) or set(apply_args) - {'verification_plan', 'verify_cmd', 'active_verify_cmd'}:
        raise ValueError('apply는 기존 수리의 verification_plan/verify_cmd/active_verify_cmd만 받습니다.')
    details = {'version': 1, 'kind': kind, 'target': target, 'operation': operation,
               'root': str(root), 'functions': str(functions), 'before': old['revision'],
               'expected': expected, 'expected_description': mutation[1].get('description') if mutation else None, 'files': files, 'probes': probes, 'apply': apply_args,
               'impact': {**impact, 'callers': [r['location'] for r in impact['callers']]}}
    from thread_context import get_repair_workspace
    details['repair'] = bool(get_repair_workspace() or os.environ.get('INDIEBIZ_REPAIR_CHILD') == '1')
    if kind == 'script':
        details['other_registrations'] = digest({k: v for k, v in read_registry(root).items() if k != target})
    details['request_id'] = request.get('request_id') or digest(details)
    if mutation and kind == 'idiom' and operation != 'remove':
        mutation[1]['request_id'] = details['request_id']
    code = _program(details, mutation)
    return {'success': True, 'plan': details, 'program': code, 'edition': 2,
            'completion': 'existing IBL receipt + fresh observation; no new change store'}


def batch(requests):
    """Order explicit changes by current IBL references; journal each child separately."""
    from capability_consumers import nodes
    root, functions = roots()
    if not isinstance(requests, list) or not requests or len(requests) > 50:
        raise ValueError('changes는 1~50개 변경 요청 목록입니다.')
    identities = [(r.get('kind'), r.get('target')) for r in requests if isinstance(r, dict)]
    if len(identities) != len(requests) or len(set(identities)) != len(requests):
        raise ValueError('한 묶음에는 같은 대상을 한 번만 지정하세요.')
    dependencies = {i: set() for i in range(len(requests))}
    for i, request in enumerate(requests):
        if request.get('kind') not in {'idiom', 'script', 'action'} or request.get('operation') not in {'add', 'update', 'remove'}:
            raise ValueError('각 변경의 kind/operation을 확인하세요.')
        if request['kind'] != 'idiom':
            continue
        source = request.get('code')
        if source is None and request.get('source'):
            source = source_path(root, request['source']).read_text()
        if source is None:
            source = (observe('idiom', request['target'], root, functions)['record'] or {}).get('source')
        for node in nodes(source or ''):
            if node.kind != 'call':
                continue
            data = node.data
            identity = ('action', data['node'] + ':' + data['action'])
            if data['node'] == 'fn':
                identity = ('idiom', data['action'])
            if (data['node'], data['action']) == ('self', 'script'):
                sid = data['params'].data.get('fields', {}).get('id')
                if sid is not None and sid.kind == 'literal':
                    identity = ('script', sid.data['value'])
            if identity not in identities or identities.index(identity) == i:
                continue
            j = identities.index(identity)
            if requests[j]['operation'] == 'remove':
                dependencies[j].add(i)
            else:
                dependencies[i].add(j)
    ordered = []
    while dependencies:
        ready = sorted(i for i, parents in dependencies.items() if not parents)
        if not ready:
            raise ValueError('변경 사이 순환 의존이 있습니다. 기존 묶음 게시 또는 새 이름 이행을 사용하세요.')
        ordered.extend(ready)
        for i in ready:
            dependencies.pop(i)
        for parents in dependencies.values():
            parents.difference_update(ready)
    lines = ['#!ibl edition=2']
    for n, i in enumerate(ordered):
        lines.append(f'$plan{n} = ' + _call('self:script', {'id': '능력변경', 'args': {'op': 'plan', 'request': requests[i]}}))
        lines.append(f'$change{n} = [self:workflow]{{op:"run",edition:2,pipeline:$plan{n}.program}}')
    lines.append('return {changes:[' + ','.join(f'$change{n}.value' for n in range(len(ordered))) + ']}')
    return {'success': True, 'edition': 2, 'program': '\n'.join(lines),
            'plan': {'root': str(root), 'functions': str(functions), 'order': [identities[i] for i in ordered]},
            'atomic': False, 'completion': 'each child is preserved by existing execution receipts'}


def _program(plan, mutation, *, verify_only=False):
    control = lambda op: '[self:script]{id:"능력변경",args:{op:' + _literal(op) + ',plan:$plan}}'
    lines = ['#!ibl edition=2', '$plan = ' + _literal(plan)]
    if verify_only:
        lines.append('$applied = {reconciled:true}')
    else:
        lines.extend(['$pre = ' + control('check'), 'assert $pre.ok, "변경 전 검사 실패", $pre'])
    if verify_only:
        pass
    elif mutation:
        lines.append('$applied = ' + _call(*mutation))
    else:
        # The current repair owner chooses and persists candidate/apply/activation.
        # Do not impersonate its authority from the registered script subprocess.
        lines.append('$applied = ' + _call('self:patch', {'op': 'apply', **plan['apply']}))
    if plan['kind'] == 'action':
        lines.extend(['$stage = [self:script]{id:"능력변경",args:{op:"completion",receipt:$applied}}',
                      '[if:not $stage.complete] { return $stage }'])
        lines.append('$observed = [self:script]{id:"능력변경",args:{op:"status",plan:$plan,candidate_revision:$pre.candidate_revision}}')
    else:
        lines.append('$observed = ' + control('status'))
    lines.append('assert $observed.matches, "반영 판본 확인 실패", $observed')
    for index, probe in enumerate(plan['probes']):
        lines.append(f'$probe{index} = ' + _call('self:workflow', {'op': 'run', 'edition': 2,
                     'pipeline': probe['code'], 'inputs': probe.get('inputs', {})}))
        lines.append(f'assert $probe{index}.value == ' + _literal(probe['expected']) + ', "변경 후 동작 검사 실패"')
    if plan['kind'] == 'script':
        lines.append('$finish = ' + control('finish_plan'))
        lines.append('$source_change = [self:workflow]{op:"run",edition:2,pipeline:$finish.program}')
    else:
        lines.append('$source_change = {value:{required:false,completed:true}}')
    verified = bool(plan['probes']) or plan['operation'] == 'remove'
    # Full compilation/apply diagnostics remain in the original call receipt.
    # The reusable value carries only identity and completion evidence.
    lines.append('return {complete:($source_change.value.completed and ' + ('true' if verified else 'false') + '), '
                 'applied:{function_ref:get($applied,"function_ref",null),reconciled:get($applied,"reconciled",false)}, observed:$observed, '
                 'verified_probes:' + str(len(plan['probes'])) + ', request_id:' + _literal(plan['request_id']) +
                 ', source_change:$source_change.value, behavior_verified:' + ('true' if plan['probes'] else 'false') + '}')
    return '\n'.join(lines)


def validate_plan(plan):
    root, functions = roots()
    if plan.get('version') != 1 or str(root) != plan.get('root') or str(functions) != plan.get('functions'):
        raise ValueError('계획의 코드/원장 범위가 현재 실행과 다릅니다.')
    for name, expected in plan['files'].items():
        path = source_path(root, name)
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if actual != expected:
            raise ValueError('검사 후보가 바뀌었습니다: ' + name)
    return root, functions


def status(plan, candidate_revision=None):
    root, functions = validate_plan(plan)
    state = observe(plan['kind'], plan['target'], root, functions)
    if plan['operation'] == 'remove':
        matches = not state['present']
    elif plan['kind'] == 'idiom':
        matches = bool(state['present'] and state['record']['source'] == plan['expected']
                       and (plan.get('expected_description') is None
                            or state['record'].get('description', '') == plan['expected_description']))
    elif plan['kind'] == 'script':
        from script_mutation import FIELDS
        matches = bool(state['present'] and {k: state['record'].get(k) for k in FIELDS} == plan['expected'])
    else:
        matches = bool(state['present'] and candidate_revision and state['revision'] == candidate_revision)
    return {'success': True, 'matches': matches, 'revision': state['revision'],
            'kind': plan['kind'], 'target': plan['target'], 'behavior_verified': False,
            'scope': {'code': str(root), 'functions': str(functions)}}


def finish_plan(plan):
    """Return a parent-owned imprint/apply call; the child never performs it."""
    root, _ = validate_plan(plan)
    others = {k: v for k, v in read_registry(root).items() if k != plan['target']}
    if digest(others) != plan.get('other_registrations'):
        raise ValueError('다른 등록 변경이 겹쳤습니다. 등록부 전체를 함께 커밋하지 않습니다.')
    if plan.get('repair'):
        program = ('$receipt = ' + _call('self:patch', {'op': 'apply', **plan['apply']}) +
                   '\nreturn [self:script]{id:"능력변경",args:{op:"completion",receipt:$receipt}}')
    else:
        from capability_change_checks import changed_files
        if not (root / '.git').exists():
            return {'success': True, 'program': 'return {required:true,completed:false,reason:"source repository unavailable"}'}
        paths = ['data/scripts/registry.yaml', *plan['files']]
        import subprocess
        previous = subprocess.run(['git', 'show', 'HEAD:data/scripts/registry.yaml'],
                                  cwd=root, capture_output=True, text=True)
        if previous.returncode == 0:
            old = yaml.safe_load(previous.stdout) or {}
            if {k: v for k, v in old.items() if k != plan['target']} != others:
                raise ValueError('다른 스크립트의 미커밋 등록 변경이 있습니다. 함께 커밋하지 않습니다.')
        changed = set(changed_files(root))
        paths = [p for p in paths if p in changed]
        program = ('$receipt = ' + _call('self:body', {'op': 'commit', 'paths': paths,
                    'message': '등록 스크립트 ' + plan['target'] + ' ' + plan['operation']}) +
                    '\nreturn {required:true,completed:true,receipt:$receipt}'
                   if paths else 'return {required:false,completed:true}')
    return {'success': True, 'program': program}


def operate(args):
    import principal
    if not principal.is_owner():
        raise ValueError('능력 변경은 소유자 문맥에서 실행합니다.')
    op = args.get('op', 'plan')
    if op == 'plan':
        return plan(args['request'])
    if op == 'status':
        return status(args['plan'], args.get('candidate_revision'))
    if op == 'completion':
        receipt = args['receipt']
        complete = receipt.get('complete') is True
        return {'success': True, 'complete': complete, 'completed': complete, 'required': True,
                'receipt': receipt, 'next': 'none' if complete else 'existing repair recovery'}
    if op == 'verify':
        saved = copy.deepcopy(args['plan'])
        validate_plan(saved)
        if saved['kind'] == 'action':
            raise ValueError('어휘 반영 재개는 기존 self:patch의 recovery 영수증을 사용하세요.')
        if not status(saved)['matches']:
            raise ValueError('반영된 상태가 계획과 다릅니다. 검증만 이어갈 수 없습니다.')
        probes = args.get('probes')
        if not isinstance(probes, list) or any(not isinstance(p, dict) or not isinstance(p.get('code'), str)
                or 'expected' not in p or set(p) - {'code', 'inputs', 'expected'} for p in probes):
            raise ValueError('다시 실행할 probes 목록을 명시하세요. 완료한 외부 효과는 넣지 마세요.')
        saved['probes'] = probes
        return {'success': True, 'plan': saved, 'edition': 2,
                'program': _program(saved, None, verify_only=True)}
    if op == 'finish_plan':
        return finish_plan(args['plan'])
    if op == 'check':
        plan_data = args['plan']
        root, functions = validate_plan(plan_data)
        current = observe(plan_data['kind'], plan_data['target'], root, functions)
        if current['revision'] != plan_data['before']:
            raise ValueError('변경 전 판본이 달라졌습니다. 새 계획을 만드세요.')
        if plan_data['kind'] == 'action':
            from capability_change_checks import check
            result = check(root, list(plan_data['files']), prepare=True)
            if result['ok']:
                catalog = yaml.safe_load((root / 'data/ibl_nodes.yaml').read_text())
                node, action = plan_data['target'].split(':')
                present = action in catalog.get('nodes', {}).get(node, {}).get('actions', {})
                record = catalog.get('nodes', {}).get(node, {}).get('actions', {}).get(action)
                result['candidate_revision'] = digest(record) if record else ''
                if present != (plan_data['operation'] != 'remove'):
                    raise ValueError('빌드된 어휘가 요청한 추가/수정/제거 상태와 다릅니다.')
            return result
        return {'success': True, 'ok': True, 'revision': current['revision']}
    raise ValueError('op는 plan/check/status/verify/finish_plan/completion입니다.')
