"""Package-local module namespaces and call leases for independent replacement.

The public handler contract is unchanged. Each accepted package revision owns
its complete Python namespace; an in-flight call keeps its old namespace. A
replacement waits for that program's calls, never for unrelated programs.
"""
import builtins
from collections import ChainMap
from contextlib import contextmanager
import importlib.util
import inspect
from pathlib import Path
import sys
import subprocess
import threading
import types


class Namespace:
    def __init__(self, root, identity):
        self.root = Path(root)
        self.prefix = '_indiebiz_program_' + identity
        self.modules = {}
        self.builtins = {**vars(builtins), '__import__': self.import_module}
        self.sys = types.ModuleType('sys')
        self.sys.__dict__.update(vars(sys))
        self.sys.path = list(sys.path)
        self.sys.modules = ChainMap({}, sys.modules)
        self.importlib = types.ModuleType('importlib')
        self.importlib.__dict__.update(vars(importlib))
        self.importlib.util = types.ModuleType('importlib.util')
        self.importlib.util.__dict__.update(vars(importlib.util))
        self.importlib.util.spec_from_file_location = self.spec_from_file_location
        self.importlib.import_module = self.dynamic_import
        top = types.ModuleType(self.prefix)
        top.__path__ = [str(self.root)]
        top.__package__ = self.prefix
        self.modules[''] = top
        sys.modules[self.prefix] = top

    def close(self):
        for name in list(sys.modules):
            if name == self.prefix or name.startswith(self.prefix + '.'):
                sys.modules.pop(name, None)

    def dynamic_import(self, name, package=None):
        resolved = importlib.util.resolve_name(name, package) if name.startswith('.') else name
        local = resolved.removeprefix(self.prefix + '.')
        return self.load(local) if self.local_path(local)[0] else importlib.import_module(name, package)

    def spec_from_file_location(self, name, location, *args, **kwargs):
        path = Path(location).resolve()
        if not path.is_relative_to(self.root.resolve()) or path.suffix != '.py':
            return importlib.util.spec_from_file_location(name, location, *args, **kwargs)
        namespace = self
        class Loader:
            def create_module(self, spec):
                return None

            def exec_module(self, module):
                module.__file__ = str(path)
                module.__dict__['__builtins__'] = namespace.builtins
                sys.modules[module.__name__] = module
                namespace.modules[module.__name__.removeprefix(namespace.prefix + '.')] = module
                exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
        return importlib.util.spec_from_loader(self.prefix + '.' + name, Loader(), origin=str(path))

    def local_path(self, name):
        path = self.root.joinpath(*name.split('.'))  # path-ok: Python module import name, not IBL field path
        if path.with_suffix('.py').is_file():
            return path.with_suffix('.py'), False
        if (path / '__init__.py').is_file():
            return path / '__init__.py', True
        if path.is_dir():
            return path, True  # Python namespace package
        return None, False

    def load(self, name):
        if name in self.modules:
            return self.modules[name]
        path, package = self.local_path(name)
        if not path:
            raise ImportError(name)
        qualified = self.prefix + '.' + name
        module = types.ModuleType(qualified)
        module.__file__ = str(path)
        module.__package__ = qualified if package else qualified.rpartition('.')[0]
        module.__dict__['__builtins__'] = self.builtins
        if package:
            module.__path__ = [str(path if path.is_dir() else path.parent)]
        self.modules[name] = module
        sys.modules[qualified] = module  # unique identity; never replace another program's module
        try:
            if path.is_file():
                exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
            parent, _, leaf = name.rpartition('.')
            if parent:
                setattr(self.load(parent), leaf, module)
        except BaseException:
            self.modules.pop(name, None)
            sys.modules.pop(qualified, None)
            raise
        return module

    def import_module(self, name, globals=None, locals=None, fromlist=(), level=0):
        if not level and name == 'sys':
            return self.sys
        if not level and name in {'importlib', 'importlib.util'}:
            return self.importlib.util if name == 'importlib.util' and fromlist else self.importlib
        if level:
            parent = (globals or {}).get('__package__', self.prefix)
            resolved = importlib.util.resolve_name('.' * level + name, parent)
            name = '' if resolved == self.prefix else resolved.removeprefix(self.prefix + '.')
        path, _ = self.local_path(name)
        if path or name == '':
            module = self.load(name)
            for child in fromlist or ():
                target = name + '.' + child if name else child
                if child != '*' and not hasattr(module, child) and self.local_path(target)[0]:
                    setattr(module, child, self.load(target))
            if fromlist:
                return module
            top = name.split('.')[0]  # path-ok: Python module import name
            if top != name:
                return self.load(top)
            return module
        return builtins.__import__(name, globals, locals, fromlist, level if level and not path else 0)


class Program:
    _HOST_FIELDS = frozenset({'package', 'baseline', 'repo', 'condition', 'version',
                              'namespace', 'module', 'calls', 'pending', 'execute'})

    def __setattr__(self, name, value):
        module = self.__dict__.get('module')
        if name in self._HOST_FIELDS or module is None:
            object.__setattr__(self, name, value)
        else:
            # Preserve handler configuration/hooks: its functions read their
            # module globals, not the proxy's attribute dictionary.
            setattr(module, name, value)

    def __delattr__(self, name):
        if name in self.__dict__:
            object.__delattr__(self, name)
        else:
            delattr(self.module, name)

    def __init__(self, package, baseline, repo):
        self.package, self.baseline, self.repo = package, baseline, repo
        self.condition = threading.Condition(threading.RLock())
        self.version, self.namespace, self.module = None, None, None
        self.calls = 0
        self.pending = None

    def select(self, root, version):
        with self.condition:
            if self.version == version:
                return True
            if self.calls or (self._background_alive() and not callable(getattr(self.module, '__program_close__', None))):
                self.pending = version
                return False
            namespace = Namespace(root, self.package.replace('-', '_') + '_' + version)
            try:
                module = namespace.load('handler')
                if not callable(getattr(module, 'execute', None)):
                    raise ValueError('Program has no execute(tool_input, context) entry point')
                # Durable state stays in its owner store; transient owned state
                # can explicitly transfer before the old implementation closes.
                export = getattr(self.module, '__program_export__', None)
                restore = getattr(module, '__program_restore__', None)
                if export:
                    if not restore:
                        raise ValueError('Stateful program replacement requires __program_restore__')
                    restore(export())
                close = getattr(self.module, '__program_close__', None)
                if close:
                    close()
            except BaseException:
                namespace.close()
                raise
            previous = self.namespace
            self.version, self.namespace, self.module = version, namespace, module
            self.pending = None
            if previous:
                previous.close()
            return True

    def _background_alive(self):
        """Known owned background work must drain or provide its own close hook."""
        modules = self.namespace.modules.values() if self.namespace else [self.module]
        for module in modules:
            for value in vars(module).values() if module else ():
                if isinstance(value, threading.Thread) and value.is_alive():
                    return True
                if isinstance(value, subprocess.Popen) and value.poll() is None:
                    return True
        return False

    @contextmanager
    def lease(self):
        with self.condition:
            self.calls += 1
            module = self.module
        try:
            yield module
        finally:
            with self.condition:
                self.calls -= 1
                self.condition.notify_all()

    def execute(self, tool_input, context):
        with self.condition:
            load(self.package, self.baseline, self.repo)
            self.calls += 1
            module = self.module
        def release():
            with self.condition:
                self.calls -= 1
                self.condition.notify_all()
        try:
            result = module.execute(tool_input, context)
        except BaseException:
            release()
            raise
        if inspect.isawaitable(result):
            async def awaited():
                try:
                    return await result
                finally:
                    release()
            return awaited()
        if inspect.isgenerator(result):
            def generated():
                try:
                    yield from result
                finally:
                    release()
            return generated()
        if inspect.isasyncgen(result):
            async def generated_async():
                try:
                    async for item in result:
                        yield item
                finally:
                    release()
            return generated_async()
        release()
        return result

    def __getattr__(self, name):
        module = self.__dict__.get('module')
        if module is None:
            raise AttributeError(name)
        return getattr(module, name)


_programs = {}
_lock = threading.RLock()


def load(package, baseline, repo):
    from program_versions import selected, digest, source_inventory
    root, row = selected(repo, package, baseline)
    key = (str(Path(repo).resolve()), package)
    with _lock:
        program = _programs.get(key)
        if not row and program is None:
            return None  # preserve the deployed loader until an independently published revision exists
        if not row and program.namespace is None:
            return program
        if program is None:
            program = _programs[key] = Program(package, baseline, repo)
    version = row['version'] if row else digest(source_inventory(root))
    program.select(root, version)
    return program


def wrap(package, baseline, repo, module):
    """Track calls from the first deployed revision, before any repair exists."""
    from program_versions import digest, source_inventory
    key = (str(Path(repo).resolve()), package)
    with _lock:
        program = _programs.get(key)
        if program is None:
            program = _programs[key] = Program(package, baseline, repo)
    with program.condition:
        if program.module is None:
            program.module = module
            program.version = digest(source_inventory(baseline))
        elif program.namespace is None and not program.calls:
            program.baseline = baseline
            program.module = module
            program.version = digest(source_inventory(baseline))
        return program


def clear_idle():
    with _lock:
        items = list(_programs.items())
    for key, program in items:
        with program.condition:
            if not program.calls and program.namespace is None:
                with _lock:
                    if _programs.get(key) is program:
                        _programs.pop(key, None)


_pending_finishes = set()


def finish_later(key, callback):
    """Drain-driven completion belongs to the runtime, not to another AI turn."""
    with _lock:
        if key in _pending_finishes:
            return
        _pending_finishes.add(key)
    def run():
        import time
        try:
            while True:
                time.sleep(0.2)
                result = callback()
                if result.get('activated') or result.get('error') or result.get('stage') != 'activation':
                    return
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Program completion failed: %s', key)
        finally:
            with _lock:
                _pending_finishes.discard(key)
    threading.Thread(target=run, name='program-finish', daemon=True).start()
