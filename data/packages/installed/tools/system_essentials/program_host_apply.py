"""Activate owned program candidates without replacing the host worker."""
from pathlib import Path

import program_modules
import program_publication as publication
from program_boundary import protected_reason


def apply(st, repo, session):
    from runtime_utils import get_code_root
    scope = session.get('program_scope') or {}
    owners = scope.get('programs') or []
    if not owners or any(p['kind'] not in {'module', 'vocabulary', 'package', 'script', 'managed', 'test', 'derived'} for p in owners):
        return None
    code = Path(get_code_root())
    if scope.get('protected') or scope.get('unmanaged'):
        return None
    st._candidate.validate(repo, session)
    previous = publication.read(repo)
    row = publication.snapshot(repo, code, session)
    root = publication.object_root(repo, row)
    changes = module_changes(session)
    # Load errors and incompatible interfaces fail before any live write.
    try:
        prepared = program_modules.prepare(changes, root)
    except program_modules.RestartRequired as exc:
        # No live source or dispatch table has changed. The verified candidate
        # can use the existing generation worker instead of being stranded.
        session['activation_route'] = {'mode': 'generation-restart', 'reason': str(exc)}
        st._save_session(repo, session)
        return None
    _validate_standard(code, root, session)
    session['module_previous'] = previous
    session['module_publication'] = row
    session['program_activation'] = [{'owner': p['owner'], 'activation': 'pending'} for p in owners]
    session['status'] = 'applying'
    st._save_session(repo, session)
    try:
        publication.publish(repo, row)
        result = st._perform_apply_locked(repo, session, session['readiness']['checks'], None, None)
        if not result.get('applied'):
            recover(st, repo, session)
            return result
    except BaseException:
        recover(st, repo, session)
        raise
    try:
        return finish(st, repo, session, prepared=prepared)
    except BaseException:
        if not (session.get('commit') or {}).get('success'):
            recover(st, repo, session)
        raise


def _validate_standard(code, root, session):
    if 'data/ibl_nodes.yaml' not in session['sealed']:
        return
    import yaml
    before = yaml.safe_load((code / 'data/ibl_nodes.yaml').read_text()) or {}
    after = yaml.safe_load((root / 'data/ibl_nodes.yaml').read_text()) or {}
    old, new = before.get('nodes', {}), after.get('nodes', {})
    if {n for n, v in old.items() if v.get('always_on')} != {n for n, v in new.items() if v.get('always_on')}:
        raise PermissionError('Publication cannot change standard node authority')
    # Protected functional definitions originate in protected source fragments;
    # their regenerated form may not be overridden by an ordinary fragment.
    for source in ('self', 'others', 'table'):
        path = code / 'data/ibl_nodes_src' / (source + '.yaml')
        if not path.is_file():
            continue
        for node, definition in (yaml.safe_load(path.read_text()) or {}).items():
            for action in definition.get('actions', {}):
                if old.get(node, {}).get('actions', {}).get(action) != new.get(node, {}).get('actions', {}).get(action):
                    raise PermissionError('Publication changed standard definition: ' + node + ':' + action)


def finish(st, repo, session, prepared=None):
    from red_apply import _load_handler
    row = session['module_publication']
    if row['activation'] != 'active':
        current = publication.read(repo)
        if current.get('version') != row['version']:
            # Another independent program may complete while this one drains.
            from runtime_utils import get_code_root
            session['module_previous'] = current
            row = publication.snapshot(repo, get_code_root(), session)
            session['module_publication'] = row
            prepared = None
        from contextlib import ExitStack
        import program_runtime
        from program_versions import digest, source_inventory
        root = publication.object_root(repo, row)
        packages = []
        for owner in session['program_scope']['programs']:
            if owner['kind'] != 'package':
                continue
            prefix = owner['root']
            from runtime_utils import get_code_root
            package = owner['owner'].split(':', 1)[1]
            files = publication.package_files(repo, get_code_root(), row, package)
            if any(protected_reason(prefix + '/' + p) for p in files if p.endswith('.py')):
                continue
            package = owner['owner'].split(':', 1)[1]
            packages.append((package, prefix, digest(files)))
        with ExitStack() as stack:
            for package, prefix, version in packages:
                program = program_runtime._programs.get((str(Path(repo).resolve()), package))
                if program:
                    stack.enter_context(program.condition)
                    if program.calls or program._background_alive():
                        _after_calls(st, repo, session)
                        return {'success': False, 'applied': True, 'activated': False, 'restart_required': False,
                                'key': session['key'], 'stage': 'activation', 'message': '해당 부품의 호출 종료 후 자동 활성화합니다.'}
            if session.get('baseline') is not None:
                activated_baseline = {**session['baseline'], **{p: item['after'] for p, item in session['sealed'].items()}}
                drift = st._candidate.conflicts(repo, {**session, 'baseline': activated_baseline})
                if drift:
                    raise ValueError('Activation dependency changed: ' + ', '.join(drift[:8]))
            if prepared is None:
                prepared = program_modules.prepare(module_changes(session), root)
            row['activation'] = 'active'
            try:
                program_modules.publish(prepared, row['version'], root, lambda: publication.publish(repo, row))
                for package, prefix, version in packages:
                    from runtime_utils import get_code_root
                    program = program_runtime.load(package, Path(get_code_root()) / prefix, repo)
                    if not program or program.version != version:
                        raise ValueError('Package activation did not reach the published version: ' + package)
            except BaseException:
                program_modules.rollback(row['version'])
                row['activation'] = 'prepared'
                publication.publish(repo, row)
                raise
    # Registry/catalog loaders key on the published path; derived UI caches use
    # the existing owner invalidation procedure and must acknowledge it.
    if any(p['kind'] in {'vocabulary', 'package', 'derived'} for p in session['program_scope']['programs']):
        from ibl_routing import invalidate_runtime_caches
        token = program_modules._PIN.set(None)
        try:
            failures = invalidate_runtime_caches()
        finally:
            program_modules._PIN.reset(token)
        if failures:
            st._save_session(repo, session)
            return {'success': False, 'applied': True, 'activated': False, 'stage': 'activation',
                    'error': '캐시 활성 확인 실패: ' + ', '.join(failures), 'key': session['key']}
    for entry in session['program_activation']:
        entry['activation'] = 'active'
    row['activation'] = 'active'
    if publication.read(repo).get('version') == row['version']:
        publication.publish(repo, row)
    handler = _load_handler({'repo': str(repo)})
    result = handler._load_sibling('program_apply').complete(st, repo, session)
    if result.get('rolled_back') or result.get('stage') == 'activation':
        return result
    committed = result['commit']
    if committed.get('success'):
        program_modules.accept(row['version'])
    row['receipt']['commit'] = committed
    if publication.read(repo).get('version') == row['version']:
        publication.publish(repo, row)
    st._save_session(repo, session)
    return {'success': bool(committed.get('success')), 'applied': True, 'activated': True,
            'restart_required': False, 'key': session['key'], 'commit': committed,
            'programs': session['program_activation'],
            'message': ('검증한 프로그램·등록 판본의 적용·활성 확인·커밋을 마쳤습니다.' if committed.get('success')
                        else '프로그램은 활성화됐지만 커밋을 마치지 못했습니다. 같은 적용을 재개하세요.')}


def recover(st, repo, session):
    # The existing byte recovery owns conflicts and exact before-images.
    from red_apply import _load_handler
    handler = _load_handler({'repo': str(repo)})
    program_modules.rollback(session['module_publication']['version'])
    if publication.read(repo).get('receipt', {}).get('session') == session['key']:
        publication.atomic_json(publication.home(repo) / 'modules.json', session.get('module_previous', {}))
    import program_runtime
    from runtime_utils import get_code_root
    for owner in session['program_scope']['programs']:
        if owner['kind'] == 'package':
            package = owner['owner'].split(':', 1)[1]
            program_runtime.load(package, Path(get_code_root()) / owner['root'], repo)
    session.pop('module_publication', None)
    session['program_activation'] = []
    return handler._load_sibling('program_apply').recover(st, repo, session)


def _after_calls(st, repo, session):
    import program_runtime
    def finish_later():
        from red_apply import _load_handler
        return _load_handler({'repo': str(repo)})._load_sibling('program_apply').resume(st, repo, session)
    program_runtime.finish_later((str(repo), session['key']), finish_later)


def module_changes(session):
    """Scripts and tests use their file/registry owner, never Python hot imports."""
    return [p for owner in session['program_scope']['programs']
            if owner['kind'] in {'module', 'package'}
            for p in owner['files'] if p.endswith('.py') and not protected_reason(p)]
