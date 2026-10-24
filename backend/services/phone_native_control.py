"""Fixed, installed Android controls. No caller-supplied code executes in the parent."""
import hashlib
import importlib.util
import json
import re
import threading
import time
from pathlib import Path

_cache = {}
_load_lock = threading.Lock()
SOURCES = ('phone_control.py', 'phone_device.py', 'phone_ui.py')


def _root():
    from runtime_utils import get_base_path
    return Path(get_base_path())


def _installed():
    root = _root()
    helper = root / 'data/scripts/android_control.py'
    paths = [helper, *(root / 'data/instruments' / name for name in SOURCES)]
    # Read known paths only. Cache executable definitions by actual bytes, not mtime.
    texts = [p.read_text(encoding='utf-8') for p in paths]
    hashes = tuple(hashlib.sha256(text.encode()).hexdigest() for text in texts)
    key = (str(root), hashes)
    with _load_lock:
        if key not in _cache:
            spec = importlib.util.spec_from_file_location('_installed_android_control', helper)
            driver = importlib.util.module_from_spec(spec)
            exec(compile(texts[0], str(helper), 'exec'), driver.__dict__)
            _cache.clear()
            _cache[key] = (driver, dict(zip(SOURCES, texts[1:])), {
                'contract': 1, 'helper_sha256': hashes[0], 'sources': dict(zip(SOURCES, hashes[1:]))})
        return _cache[key]


def capabilities():
    from phone_remote_execution import capabilities as execution_capabilities
    if execution_capabilities().get('native_control') != 1:
        return {}
    try:
        return {'android_control': _installed()[2]}
    except (OSError, ValueError):
        return {}


def validate(command):
    if not isinstance(command, dict) or command.get('op') != 'control':
        raise ValueError('invalid_control_command')
    if set(command) - {'op', 'inputs', 'timeout', 'mode', 'origin', 'screen_context'}:
        raise ValueError('control_accepts_no_code_or_environment')
    inputs = command.get('inputs')
    fields = {'request', 'request_id', 'source_sha256', 'helper_sha256'}
    if not isinstance(inputs, dict) or set(inputs) != fields:
        raise ValueError('invalid_control_inputs')
    for key, length in [('request_id', 32), ('source_sha256', 64), ('helper_sha256', 64)]:
        if not isinstance(inputs[key], str) or not re.fullmatch('[a-f0-9]{%d}' % length, inputs[key]):
            raise ValueError('invalid_control_' + key)
    timeout = command.get('timeout', 20)
    if type(timeout) is not int or not 1 <= timeout <= 30 or command.get('mode', 'background') != 'background':
        raise ValueError('invalid_control_timeout_or_mode')
    driver, _, _ = _installed()
    request = driver.validate(inputs['request'])
    if len(json.dumps(command, ensure_ascii=False).encode()) > 64 * 1024:
        raise ValueError('control_request_too_large')
    return {**command, 'timeout': timeout, 'mode': 'background', 'inputs': {**inputs, 'request': request}}


def require_screen(command, context=None):
    import control_conditions
    driver, _, _ = _installed()
    request = command['inputs']['request']
    failure = control_conditions.refusal(request['action'], driver.condition(request['action'], request),
                                         context if context is not None else control_conditions.screen_context(),
                                         surface='Android')
    if failure:
        raise PermissionError(failure['error'])


def execute(job_id, command, cancelled):
    from phone_remote_execution import bridge, require_owner
    from thread_context import ISOLATED_ORIGINS, actor_context
    acquired = False
    dispatched = False
    result = None
    impl = None
    start = time.monotonic()
    watcher_done = threading.Event()
    try:
        require_owner()
        command = {k: v for k, v in command.items() if k not in {'resident', 'generation'}}
        command = validate(command)
        driver, sources, caps = _installed()
        inputs = command['inputs']
        request = inputs['request']
        filename = ('phone_ui.py' if request['action'] in driver.UI else
                    'phone_control.py' if request['action'] in driver.AUDIO else 'phone_device.py')
        if (inputs['helper_sha256'] != caps['helper_sha256'] or
                inputs['source_sha256'] != caps['sources'][filename]):
            raise ValueError('CONTROL_VERSION_MISMATCH: installed control differs; no dispatch')
        impl = bridge()
        if impl is None or json.loads(str(impl.capabilities())).get('native_control') != 1:
            raise ValueError('unsupported_native_control')
        deadline = start + command['timeout']

        def check():
            if cancelled.is_set() or time.monotonic() >= deadline:
                raise InterruptedError('control_cancelled_or_deadline')
            if acquired and not impl.controlActive(job_id):
                raise InterruptedError('control_cancelled')

        def watch():
            while not watcher_done.wait(0.05):
                if cancelled.is_set() or time.monotonic() >= deadline:
                    impl.cancel(job_id)

        check()
        threading.Thread(target=watch, name='control-cancel', daemon=True).start()
        acquired = bool(impl.beginControl(job_id, command['timeout']))
        if not acquired:
            raise InterruptedError('control_busy_or_cancelled')
        check()
        from indiebiz_android import call

        def guarded_call(method, *args):
            check()
            return call(method, *args)

        origin = command.get('origin')
        with actor_context(agent_id='phone_control', origin=origin if origin in ISOLATED_ORIGINS else None):
            require_screen(command, command.get('screen_context') or {})
            check()
            dispatched = True
            value = driver.run_device(request, sources[filename], inputs['request_id'],
                                      inputs['source_sha256'], bridge=guarded_call)
            check()
        result = {'success': True, 'value': value, 'execution_mode': 'native_control'}
    except Exception as error:
        result = {'success': False, 'error': str(error), 'unknown': dispatched,
                  'side_effects_possible': dispatched, 'execution_mode': 'native_control'}
    finally:
        watcher_done.set()
        if acquired:
            try:
                if not impl.endControl(job_id):
                    result = {'success': False, 'unknown': dispatched, 'side_effects_possible': dispatched,
                              'error': 'control_cancelled', 'execution_mode': 'native_control'}
            except Exception:
                result = {'success': False, 'unknown': True, 'side_effects_possible': dispatched,
                          'error': 'control_release_unconfirmed', 'execution_mode': 'native_control'}
    return {**result, 'elapsed_ms': round((time.monotonic() - start) * 1000)}
