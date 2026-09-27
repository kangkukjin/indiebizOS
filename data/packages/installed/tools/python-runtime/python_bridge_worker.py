"""Private JSON-wire worker. Library stdout is never the transport."""
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import boot_paths  # noqa: E402
if Path(sys.argv[2]).is_dir():
    sys.path.insert(0, sys.argv[2])
sys.path.insert(0, str(Path(__file__).parent))
import asyncio
import contextlib
import importlib
import inspect
import io
import json
import os
import time
from common.expression_ir import Fault, UNIT, pack, unpack, projection
from python_bridge_values import Objects, export_value
from python_bridge_environment import fingerprint, modules


class Capture(io.TextIOBase):
    def __init__(self):
        self.text = ''

    def write(self, value):
        self.text += value[:max(0, 4000 - len(self.text))]
        return len(value)

    def flush(self):
        pass


def safe_signature(obj):
    if not (inspect.isfunction(obj) or inspect.isbuiltin(obj) or inspect.ismethod(obj) or type(obj) is type):
        raise ValueError('unknown callable signature')
    return inspect.signature(obj, eval_str=False, follow_wrapped=False)


def signature_view(obj):
    try:
        sig = safe_signature(obj)
    except (ValueError, TypeError):
        return {'signature': 'unknown'}
    # Never repr defaults/annotations: those can execute arbitrary object code.
    return {'signature': [{'name': p.name, 'kind': p.kind.name,
                           'required': p.default is inspect.Parameter.empty
                           and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)}
                          for p in sig.parameters.values()], 'returns': 'Unknown'}


class Worker:
    def __init__(self, request):
        self.environment = fingerprint()
        self.objects = Objects(request['owner'], self.environment, request['generation'])
        self.loop = asyncio.new_event_loop()
        self.receipts = {}
        self.loaded = {}
        self.stage, self.invoked = 'resolve', False

    def module_state(self):
        changed = False
        for module in list(sys.modules.values()):
            path = vars(module).get('__file__') if module is not None else None
            if not isinstance(path, str) or not Path(path).is_file():
                continue
            p = Path(path)
            st = p.stat()
            stamp = (st.st_size, st.st_mtime_ns)
            if path in self.loaded and self.loaded[path] != stamp:
                changed = True
            self.loaded[path] = stamp
        return changed

    def target(self, params, passive=False):
        if 'target' in params:
            target = params['target']
            module, sep, name = target.partition(':')
            if not sep or not module or not name or any(not part.isidentifier() for part in (module + '.' + name).split('.')):  # path-ok: Python import/속성 식별자 문법이며 IBL 자료 경로가 아님
                raise Fault('PY_TARGET', 'target은 모듈:qualified.name 형식입니다.')
            self.stage = 'import'
            try:
                obj = importlib.import_module(module)
            except ModuleNotFoundError as exc:
                code = 'PY_MODULE_MISSING' if exc.name == module or module.startswith(str(exc.name) + '.') else 'PY_IMPORT_FAILED'
                raise Fault(code, str(exc), details={'exception_type': type(exc).__name__}) from exc
            except Exception as exc:
                raise Fault('PY_IMPORT_FAILED', str(exc), details={'exception_type': type(exc).__name__}) from exc
            self.stage = 'resolve'
            names = name.split('.')  # path-ok: Python qualified-name 해소, IBL 레코드 경로 아님
        else:
            obj = self.objects.validate(params['receiver'])
            names = [params['name']] if params.get('name') else []
        for name in names:
            if not name.isidentifier():
                raise Fault('PY_MEMBER', '속성 이름은 단일 식별자여야 합니다.')
            if not passive and params.get('op') == 'getattr':
                # A property getter can have effects and fail before conversion.
                self.stage, self.invoked = 'invoke', True
            obj = inspect.getattr_static(obj, name) if passive else getattr(obj, name)
        return obj

    def dispatch(self, params):
        op = params.get('op', 'modules')
        if op == 'modules':
            return modules(params.get('query', ''), params.get('offset', 0), params.get('limit', 50)), {}
        if op == 'release':
            return self.objects.release(params['receiver']), {}
        if op == 'export':
            self.stage = 'export'
            value, evidence = export_value(self.objects.validate(params['receiver']), params['format'], params.get('options', {}))
            return self.objects.output(value, 'value'), evidence
        obj = self.target(params, passive=op == 'describe')
        if op == 'describe':
            # Properties remain descriptors. Listing does not run their getter.
            doc = inspect.getattr_static(obj, '__doc__', None)
            return {'target': params.get('target'), 'type': type(obj).__name__,
                    'doc': doc[:4000] if type(doc) is str else None,
                    'effects': ['unknown'], **signature_view(obj)}, {}
        if op == 'call':
            self.stage = 'bind'
            args = self.objects.inputs(params.get('args', []))
            kwargs = self.objects.inputs(params.get('kwargs', {}))
            try:
                sig = safe_signature(obj)
            except (ValueError, TypeError):
                sig = None
            if sig is not None:
                sig.bind(*args, **kwargs)
            self.stage, self.invoked = 'invoke', True
            obj = obj(*args, **kwargs)
            if inspect.isawaitable(obj):
                obj = self.loop.run_until_complete(obj)
        self.stage = 'convert'
        return self.objects.output(obj, params.get('result', 'auto')), {}

    def request(self, req):
        invocation = req['id']
        if invocation in self.receipts:
            return self.receipts[invocation]
        self.stage, self.invoked = 'environment', False
        capture = Capture()
        started = time.monotonic()
        try:
            if fingerprint() != self.environment or self.module_state():
                raise Fault('PY_ENV_CHANGED', '실행 도중 Python 환경이 변경되었습니다.', kind='protocol')
            with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                value, evidence = self.dispatch(unpack(req['params']))
            if fingerprint() != self.environment or self.module_state():
                raise Fault('PY_ENV_CHANGED', '호출 중 환경 변경: 결과 일관성을 보장할 수 없습니다.', kind='protocol')
            result = {'ok': True, 'value': pack(value), 'evidence': evidence}
        except BaseException as exc:
            fault = exc if isinstance(exc, Fault) else Fault('PY_EXCEPTION', str(exc), details={'exception_type': type(exc).__name__})
            chain, current = [], exc
            while current is not None and len(chain) < 6:
                chain.append({'type': type(current).__name__, 'message': str(current)[:1500]})
                current = current.__cause__ or current.__context__
            result = {'ok': False, 'error': {'code': fault.code, 'kind': fault.kind, 'message': str(fault)[:2000],
                      'details': {**fault.details, 'stage': self.stage, 'invoked': self.invoked,
                                  'effect_status': 'unknown', 'causes': chain}}, 'partial': pack(fault.partial)}
        result.update(environment=self.environment, elapsed_ms=round((time.monotonic() - started) * 1000), diagnostics=capture.text)
        self.receipts[invocation] = result
        return result


def main():
    # Save transport before hiding native printf/os.write output from the protocol.
    transport = os.fdopen(os.dup(sys.stdout.fileno()), 'w', buffering=1)
    null = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null, 1); os.dup2(null, 2); os.close(null)
    # A dead backend must not leave an unbounded library call running forever.
    import threading
    import psutil
    parent = psutil.Process(os.getppid())
    def watch_parent():
        while parent.is_running():
            time.sleep(.25)
        os._exit(70)
    threading.Thread(target=watch_parent, daemon=True).start()  # cc-ok: 독립 워커 안의 부모 생존 감시; 워커 종료와 함께 끝남
    worker = Worker(json.loads(sys.stdin.readline()))
    transport.write(json.dumps({'ready': True, 'environment': worker.environment}) + '\n')
    for line in sys.stdin:
        req = json.loads(line)
        transport.write(json.dumps(worker.request(req), ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
