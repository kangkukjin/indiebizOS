#!/usr/bin/env python3
"""Quiesce one checkout, guard mutations, and restore its previous running surface.

Called by remote_install's resumable plan, from an external helper/terminal.
Unknown/old desktop instances and interrupted launches are never force-killed or
silently relaunched. Receipts contain process identities, not credentials.
"""
import sys
import os
from pathlib import Path
_backend = Path(__file__).resolve().parents[1] / 'backend'
if not (_backend / 'boot_paths.py').is_file() and os.environ.get('INDIEBIZ_UPDATE_ROOT'):
    _backend = Path(os.environ['INDIEBIZ_UPDATE_ROOT']) / 'backend'
sys.path.insert(0, str(_backend))
import boot_paths  # noqa: F401,E402

import argparse
import json
import re
import subprocess
import time
import uuid

import psutil
from restart_process import alive, identity
from restart_protocol import atomic_json, control_dir, read_json, request
from update_maintenance import maintenance_path
from remote_boot import wait_for_boot


def desktop_path(root):
    return root / 'data/runtime/electron-update.json'


def _arg_paths(cwd, argv):
    """Resolve argv operands; skip ones the OS cannot resolve (e.g. Windows named pipes)."""
    paths = []
    for a in argv:
        if a.startswith('-'):
            continue
        try:
            paths.append(str((cwd / a).resolve()))
        except (OSError, ValueError):
            continue
    return paths


def processes(root):
    """Exact checkout paths/working directories, never process-name-wide kills."""
    frontend = root / 'frontend'
    found = []
    for p in psutil.process_iter():
        if p.pid == os.getpid():
            continue
        try:
            argv, cwd, exe = p.cmdline(), Path(p.cwd()).resolve(), Path(p.exe()).resolve()
            if not argv:
                continue
            args = _arg_paths(cwd, argv[1:])
            backend = str(root / 'backend/api.py') in args
            launcher = str(root / 'start.sh') in args
            desktop = (frontend / 'node_modules/electron') in exe.parents
            renderer = (cwd == frontend and (Path(argv[0]).name.lower() in {'node', 'node.exe', 'npm', 'npm.cmd'}))
            if backend or launcher or desktop or renderer:
                found.append({'identity': identity(p.pid), 'desktop': desktop or renderer, 'launcher': launcher})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    state = read_json(control_dir(root) / 'state.json', {})
    for key in ('controller', 'worker'):
        ident = state.get(key)
        if ident and alive(ident) and not any(row['identity'] == ident for row in found):
            found.append({'identity': ident, 'desktop': False, 'launcher': False})
    return found


def desktop_receipt(root, rows):
    value = read_json(desktop_path(root), {})
    matches = [r for r in rows if r['identity']['pid'] == value.get('pid') and r['desktop']]
    if (value.get('schema') != 1 or value.get('root') != str(root) or not value.get('nonce')
            or len(matches) != 1 or value.get('mode') not in {'dev', 'preview'}):
        raise ValueError('Running desktop has no update handshake; close this checkout normally, then retry')
    born = matches[0]['identity']['born']
    if not born <= value.get('started_at', 0) <= born + 120:
        raise ValueError('Desktop receipt is stale or process identity was reused')
    return value


def stopped(root):
    rows = processes(root)
    if rows:
        raise ValueError('Checkout still running; no files changed: ' + ','.join(str(r['identity']['pid']) for r in rows))


def journal_path(root, run_id):
    return root / 'data/runtime/remote_updates' / (run_id + '.json')


def load(root, run_id):
    value = read_json(journal_path(root, run_id), {})
    if value.get('root') != str(root) or value.get('run_id') != run_id:
        raise ValueError('Missing or mismatched update lifecycle receipt')
    return value


def save(root, value):
    atomic_json(journal_path(root, value['run_id']), value)


def marker(root, value):
    atomic_json(maintenance_path(root), {k: value[k] for k in ('run_id', 'token', 'phase')})


def own_marker(root, run_id):
    value = read_json(maintenance_path(root), {})
    if value.get('run_id') != run_id:
        raise ValueError('Update maintenance owner changed; refusing to continue')
    return value


def quiesce(root, run_id, timeout=600):
    existing = read_json(maintenance_path(root), {})
    if existing and existing.get('run_id') != run_id:
        raise ValueError('Another update owns this checkout; resume its existing plan')
    state = read_json(control_dir(root) / 'state.json', {})
    rows = processes(root)
    ancestors = {p.pid for p in psutil.Process().parents()}
    if any(r['identity']['pid'] in ancestors for r in rows):
        raise ValueError('Updater belongs to the app being stopped; run through an external PC helper')
    value = read_json(journal_path(root, run_id))
    if value and value['phase'] in {'stopped', 'starting', 'complete'}:
        if value['phase'] == 'stopped':
            own_marker(root, run_id)
            stopped(root)
        return value
    backend = alive(state.get('controller'))
    desktop_present = any(r['desktop'] for r in rows)
    # Capture before any admission rejection asks the caller to close the app.
    # Retrying after that closure must not redefine the original state as stopped.
    if value is None:
        value = {'schema': 1, 'root': str(root), 'run_id': run_id, 'token': uuid.uuid4().hex,
                 'phase': 'preparing', 'backend': backend, 'desktop': None,
                 'desktop_unresolved': desktop_present, 'before': rows,
                 'first_observed_at': time.time(), 'shutdown_id': uuid.uuid4().hex}
        save(root, value)
    desktop = desktop_receipt(root, rows) if desktop_present else None
    if desktop and value.get('desktop_unresolved'):
        value.update(desktop=desktop, desktop_unresolved=False)
        save(root, value)
    if backend and not state.get('shutdown_drain'):
        raise ValueError('Running controller lacks graceful update shutdown; close the app normally, then retry')
    if rows and not desktop and not backend:
        raise ValueError('Unmanaged checkout processes remain; close them normally, then retry')
    # Exclusive ownership creation: an existing journal is not an OS lock.
    path = maintenance_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open('x', encoding='utf-8') as stream:
            json.dump({k: value[k] for k in ('run_id', 'token', 'phase')}, stream)
    own_marker(root, run_id)
    deadline = time.monotonic() + timeout
    if backend:
        prior = read_json(control_dir(root) / 'results' / (value['shutdown_id'] + '.json'))
        if prior and prior.get('outcome') != 'intentional_shutdown':
            # quiesce is retried explicitly by remote_steps --retry. A pending
            # request is always observed; only a settled rejection gets a new ID.
            value['shutdown_id'] = uuid.uuid4().hex
            save(root, value)
        request(root, 'source_update', request_id=value['shutdown_id'], operation='shutdown',
                expected_generation=state['generation'], artifact_digest=state['code_digest'],
                policy={'drain_before_shutdown': True, 'drain_timeout_s': timeout - 30, 'force': False})
        result_path = control_dir(root) / 'results' / (value['shutdown_id'] + '.json')
        while time.monotonic() < deadline:
            result = read_json(result_path)
            if result:
                if result.get('outcome') != 'intentional_shutdown' or result.get('effect_unknown'):
                    raise ValueError('Graceful shutdown not completed: ' + str(result.get('outcome')))
                break
            time.sleep(.2)
        else:
            raise TimeoutError('Graceful shutdown still pending; inspect the existing request')
    if desktop:
        atomic_json(root / 'data/runtime/electron-update-request.json',
                    {'op': 'close', 'nonce': desktop['nonce'], 'id': uuid.uuid4().hex})
    while time.monotonic() < deadline:
        if not processes(root):
            value['phase'] = 'stopped'
            save(root, value)
            marker(root, value)
            return value
        time.sleep(.2)
    raise TimeoutError('App did not close (possibly unsaved edits); no source/dependency changes allowed')


def guard(root, run_id):
    value = load(root, run_id)
    if value['phase'] != 'stopped' or own_marker(root, run_id).get('phase') != 'stopped':
        raise ValueError('Update has not quiesced this checkout')
    stopped(root)


def verify(root, value, timeout=300):
    if value.get('desktop_unresolved'):
        raise ValueError('Original desktop was running but its launch mode is unknown; restoration is unverified')
    if not value['backend'] and not value['desktop']:
        if value.get('before'):
            raise ValueError('Original checkout had unmanaged processes; restoration is unverified')
        stopped(root)
        return {'status': 'succeeded', 'surface': 'stopped', 'scope': 'installation only; app was not running'}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = read_json(control_dir(root) / 'state.json', {})
        if alive(state.get('controller')):
            expected = value.get('controller')
            if expected and state['controller'] != expected:
                raise ValueError('Restored controller changed; inspect before retrying')
            if not expected:
                # A fresh controller must be a descendant of our recorded launcher.
                from restart_process import tree
                if state['controller'] not in tree(value.get('launch')):
                    raise ValueError('Controller is unrelated to the update launch')
                value['controller'] = state['controller']
                save(root, value)
            result = wait_for_boot(root, root, state['controller'], generation=state.get('generation'),
                                   port=int(os.environ.get('INDIEBIZ_API_PORT', '8765')),
                                   timeout=max(1, deadline-time.monotonic()), interval=.5)
            if result['status'] != 'succeeded':
                raise ValueError('Restored backend failed verification: ' + result.get('reason', result['status']))
            if not value['desktop']:
                return result
            desktop = desktop_receipt(root, processes(root))
            head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True, encoding='utf-8').strip()
            if desktop['nonce'] == value['desktop']['nonce'] or desktop.get('git_head') != head:
                raise ValueError('Desktop did not load the updated checkout')
            if desktop.get('ready'):
                return {**result, 'desktop': 'loaded', 'head': head, 'scope': 'backend and Electron page load; model query not tested'}
        time.sleep(.2)
    raise TimeoutError('Updated app has not become ready; observe the existing launch, do not relaunch')


def resume(root, run_id, npm, timeout=300):
    value = load(root, run_id)
    if value.get('desktop_unresolved'):
        raise ValueError('Original desktop launch mode is unknown; inspect its saved before observation before restoration')
    if value.get('before') and not value['backend'] and not value['desktop']:
        raise ValueError('Original unmanaged checkout processes need an explicit restoration method')
    if value['phase'] == 'complete':
        return verify(root, value, timeout)
    if value['phase'] == 'stopped':
        guard(root, run_id)
        value['phase'] = 'starting'
        save(root, value)
        marker(root, value)
        if value['backend'] or value['desktop']:
            env = dict(os.environ, INDIEBIZ_UPDATE_TOKEN=value['token'], PYTHONUTF8='1')
            desktop = value['desktop']
            vpy = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python3')
            argv = ([npm, 'run', 'electron:dev' if desktop['mode'] == 'dev' else 'electron:preview'] if desktop
                    else [str(vpy) if vpy.exists() else sys.executable, str(root / 'backend/api.py'), 'start'])
            with (journal_path(root, run_id).with_suffix('.log')).open('ab') as log:
                process = subprocess.Popen(argv, cwd=root / 'frontend' if desktop else root,
                                           env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                           start_new_session=os.name != 'nt')
            value['launch'] = identity(process.pid)
            save(root, value)
    elif value['phase'] != 'starting':
        raise ValueError('Update must finish quiescing before restart')
    own_marker(root, run_id)
    result = verify(root, value, timeout)
    value.update(phase='complete', result=result)
    save(root, value)
    own_marker(root, run_id)
    maintenance_path(root).unlink()
    return result


def retry_start(root, run_id, npm, timeout=300):
    """Explicit recovery only after all checkout processes have actually exited."""
    value = load(root, run_id)
    own_marker(root, run_id)
    if value['phase'] != 'starting':
        raise ValueError('retry-start only applies to an interrupted/failed launch')
    stopped(root)
    value.setdefault('previous_launches', []).append(value.get('launch'))
    value.pop('controller', None)
    value.pop('launch', None)
    value['phase'] = 'stopped'
    save(root, value)
    marker(root, value)
    return resume(root, run_id, npm, timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('op', choices=['quiesce', 'guard-run', 'resume', 'verify', 'retry-start'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--npm', default='')
    parser.add_argument('--timeout', type=float, default=600)
    args, command = parser.parse_known_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.run_id) or not 30 <= args.timeout <= 3600:
        parser.error('valid run-id and timeout 30..3600 required')
    root = args.root.resolve()
    try:
        if args.op == 'quiesce':
            result = quiesce(root, args.run_id, args.timeout)
            result = {k: result[k] for k in ('phase', 'backend', 'run_id')}
        elif args.op == 'guard-run':
            guard(root, args.run_id)
            if not command or command[0] != '--' or len(command) < 2:
                raise ValueError('guard-run requires -- argv')
            return subprocess.call(command[1:])
        elif args.op == 'resume':
            result = resume(root, args.run_id, args.npm, args.timeout)
        elif args.op == 'retry-start':
            result = retry_start(root, args.run_id, args.npm, args.timeout)
        else:
            result = verify(root, load(root, args.run_id), args.timeout)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, psutil.Error, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
