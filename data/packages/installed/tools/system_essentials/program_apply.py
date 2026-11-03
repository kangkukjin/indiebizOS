"""Apply ordinary package programs through the same verified candidate ledger."""
from pathlib import Path

import program_versions as versions
from program_boundary import protected_reason, generation_candidate


def apply(st, repo, session):
    if generation_candidate(session):
        return None  # the existing staged restart path owns this transaction
    from script_mutation import activation_scope
    with st._candidate.locked(repo, 'application'), activation_scope(repo, session):
        result = _apply(st, repo, session)
        if result is not None:
            return result
        from red_apply import _load_handler
        return _load_handler({'repo': str(repo)})._load_sibling('program_host_apply').apply(st, repo, session)


def _apply(st, repo, session):
    scope = session.get('program_scope') or {}
    programs = scope.get('programs') or []
    if not programs or scope.get('protected') or scope.get('unmanaged'):
        return None
    if any(p['kind'] != 'package' for p in programs):
        return None
    if any(not any(rel.startswith(p['root'] + '/') for p in programs)
           for rel in session.get('derived_files', {})):
        return None  # vocabulary/host artifacts activate through their existing owner
    from runtime_utils import get_code_root
    code = Path(get_code_root())
    prepared = []
    for program in programs:
        package = program['owner'].split(':', 1)[1]
        prefix = program['root']
        source = Path(repo) / session['worktree'] / prefix
        # A package containing the publication gate cannot replace its own
        # running gate. General submodules remain editable through its worker.
        if any(protected_reason(prefix + '/' + p) for p in versions.source_inventory(source) if p.endswith('.py')):
            return None
        manifest = versions.snapshot(repo, package, source, code_root=code)
        baseline = versions.source_inventory(code / prefix)
        prepared.append({'manifest': manifest, 'baseline': baseline, 'activation': 'pending'})
    st._candidate.validate(repo, session)
    session['program_activation'] = prepared
    session['program_previous'] = versions.read(repo)
    session['status'] = 'applying'
    st._save_session(repo, session)
    try:
        for row in prepared:
            versions.publish(repo, row['manifest'], row['baseline'], {'session': session['key'], 'phase': 'applying'})
        result = st._perform_apply_locked(repo, session, session['readiness']['checks'], None, None)
        if not result.get('applied'):
            recover(st, repo, session)
            return result
        return finish(st, repo, session)
    except BaseException:
        recover(st, repo, session)
        raise


def resume(st, repo, session):
    from script_mutation import activation_scope
    with st._candidate.locked(repo, 'application'), activation_scope(repo, session):
        try:
            return finish(st, repo, session)
        except BaseException:
            if not (session.get('commit') or {}).get('success'):
                recover(st, repo, session)
            raise


def finish(st, repo, session):
    if session.get('module_publication'):
        from red_apply import _load_handler
        return _load_handler({'repo': str(repo)})._load_sibling('program_host_apply').finish(st, repo, session)
    from red_apply import _load_handler
    from runtime_utils import get_code_root
    from program_runtime import load
    handler = _load_handler({'repo': str(repo)})
    for row in session['program_activation']:
        manifest = row['manifest']
        package = manifest['package']
        program = load(package, Path(get_code_root()) / 'data/packages/installed/tools' / package, repo)
        row['activation'] = 'active' if program.version == manifest['version'] else 'waiting_calls'
    active = all(r['activation'] == 'active' for r in session['program_activation'])
    if active:
        for field, command in (session['readiness'].get('activation_commands') or {}).items():
            if command and st._candidate.activation(repo, session, field, command, st._save_session).get('state') != 'passed':
                st._save_session(repo, session)
                return {'success': False, 'applied': True, 'activated': True,
                        'stage': 'activation', 'error': '프로그램 활성 검사 미통과', 'key': session['key']}
    committed = (st._candidate.commit(repo, session, handler._load_sibling('body_ops')) if active else
                 {'success': False, 'pending_activation': True})
    session['commit'] = committed
    for row in session['program_activation']:
        versions.publish(repo, row['manifest'], row['baseline'], {'session': session['key'], 'commit': committed})
    st._save_session(repo, session)
    if not active:
        from program_runtime import finish_later
        finish_later((str(repo), session['key']), lambda: resume(st, repo, session))
    return {'success': bool(committed.get('success') and active), 'applied': True,
            'activated': active, 'stage': 'complete' if active else 'activation', 'restart_required': False, 'key': session['key'], 'commit': committed,
            'programs': session['program_activation'],
            'message': ('프로그램 판본을 교체했습니다. 원래 업무를 새 호출로 확인하세요.' if active else
                        '해당 프로그램의 진행 호출이 끝나기를 기다립니다. 종료 후 자동으로 활성 확인·각인합니다.')}


def recover(st, repo, session):
    """Restore only our exact applied bytes; never overwrite a concurrent edit."""
    if session.get('module_publication'):
        from red_apply import _load_handler
        return _load_handler({'repo': str(repo)})._load_sibling('program_host_apply').recover(st, repo, session)
    import base64
    import os
    from tempfile import NamedTemporaryFile
    for rel, item in session['sealed'].items():
        current = st._candidate.fingerprint(st._candidate.target(repo, rel))
        if current not in (item['before'], item['after']):
            raise ValueError('프로그램 복구 중 정본 충돌: ' + rel)
    for rel, item in session['sealed'].items():
        path = st._candidate.target(repo, rel)
        if item['before'] is None:
            path.unlink(missing_ok=True)
        else:
            with NamedTemporaryFile(dir=path.parent, delete=False) as output:
                output.write(base64.b64decode(item['before_data']))
                temporary = output.name
            os.chmod(temporary, item['before']['mode'])
            os.replace(temporary, path)
    rows = versions.read(repo)
    for row in session['program_activation']:
        package = row['manifest']['package']
        if (rows.get(package) or {}).get('version') == row['manifest']['version']:
            previous = session.get('program_previous', {}).get(package)
            if previous:
                rows[package] = previous
            else:
                rows.pop(package, None)
    versions.atomic_json(versions.home(repo) / 'active.json', rows)
    session.update(status='staging', verified=False)
    session.pop('program_activation', None)
    st._candidate.invalidate(session)
    st._save_session(repo, session)
    return True
