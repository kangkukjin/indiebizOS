"""Stable Python call boundaries for ordinary modules, installed before consumers.

A call captures one dispatch table. Publication swaps that table, never the
old function's globals. Classes retain identity; incompatible layouts require
an owner migration instead of silently restarting the shared worker.
"""
import ast
import contextvars
import functools
import importlib.abc
import importlib.machinery
import inspect
from pathlib import Path
import sys
import threading
import weakref
import types

from program_boundary import protected_reason

_LOCK = threading.RLock()
class Dispatch(dict):
    pass


_TABLE = Dispatch()
_PIN = contextvars.ContextVar('program_module_revision', default=None)
_OWNERS = {}
_FINDERS = []


def _invoke(table, function, args, kwargs):
    token = _PIN.set(table)
    try:
        return function(*args, **kwargs)
    finally:
        _PIN.reset(token)


def _wrapper(owner, key, function):
    def selected():
        with _LOCK:
            table = _PIN.get()
            table = _TABLE if table is None else table
        return table, table.get((owner, key), function)

    if inspect.isasyncgenfunction(function):
        async def call(*args, **kwargs):
            table, target = selected()
            stream = target(*args, **kwargs)
            sent, thrown = None, None
            try:
                while True:
                    token = _PIN.set(table)
                    try:
                        value = await stream.athrow(thrown) if thrown else await stream.asend(sent)
                    except StopAsyncIteration:
                        return
                    finally:
                        _PIN.reset(token)
                    try:
                        sent = yield value
                        thrown = None
                    except GeneratorExit:
                        return
                    except BaseException as error:
                        thrown = error
            finally:
                token = _PIN.set(table)
                try:
                    await stream.aclose()
                finally:
                    _PIN.reset(token)
    elif inspect.iscoroutinefunction(function):
        async def call(*args, **kwargs):
            table, target = selected()
            token = _PIN.set(table)
            try:
                return await target(*args, **kwargs)
            finally:
                _PIN.reset(token)
    elif inspect.isgeneratorfunction(function):
        def call(*args, **kwargs):
            table, target = selected()
            stream = target(*args, **kwargs)
            sent, thrown = None, None
            try:
                while True:
                    token = _PIN.set(table)
                    try:
                        value = stream.throw(*thrown) if thrown else stream.send(sent)
                    except StopIteration as stop:
                        return stop.value
                    finally:
                        _PIN.reset(token)
                    try:
                        sent = yield value
                        thrown = None
                    except GeneratorExit:
                        return
                    except BaseException:
                        thrown = sys.exc_info()
            finally:
                _invoke(table, stream.close, (), {})
    else:
        def call(*args, **kwargs):
            table, target = selected()
            return _invoke(table, target, args, kwargs)
    return functools.wraps(function)(call)


def _accessor(node):
    return next(('@' + d.attr for d in node.decorator_list if isinstance(d, ast.Attribute)
                 and d.attr in {'setter', 'deleter'}), '')


class Boundary(ast.NodeTransformer):
    """Decorate before API routers/cache decorators capture a function reference."""
    def __init__(self, previous=None):
        self.scope = []
        self.previous = previous or {}
        self.reused = set()
        self.signatures = {}

    def visit_ClassDef(self, node):
        self.scope.append(node.name)
        node = self.generic_visit(node)
        self.scope.pop()
        return node

    def visit_FunctionDef(self, node):
        key = '.'.join([*self.scope, node.name]) + _accessor(node)
        self.signatures[key] = (ast.dump(node.args), ast.dump(node.returns) if node.returns else None)
        old = self.previous.get(key)
        if old is not None and node.decorator_list:
            if [ast.dump(d) for d in old.decorator_list] != [ast.dump(d) for d in node.decorator_list]:
                raise ValueError('Decorator contract requires owner migration: ' + key)
            self.reused.add(key)
            node.decorator_list = []
        node.decorator_list.append(ast.Call(ast.Name('__program_bind__', ast.Load()),
                                            [ast.Constant(key)], []))
        return node  # Nested functions own invocation-local closures, not slots.

    visit_AsyncFunctionDef = visit_FunctionDef


def _assignments(tree):
    result = {}
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if len(targets) == 1 and isinstance(targets[0], ast.Name):
            result[targets[0].id] = ast.dump(node, include_attributes=False)
    return result


class Owner:
    def __init__(self, relative, module, source):
        self.relative, self.module, self.source = relative, module, source
        self.wrappers = {}
        self.targets = {}
        self.classes = {}
        self.version = None
        self.namespace = module.__dict__.copy()

    def execute(self, source, path, initial=False, staging_table=None):
        tree = ast.parse(source, str(path))
        namespace = self.namespace if initial else {
            '__name__': self.module.__name__, '__package__': self.module.__package__,
            '__file__': str(path), '__builtins__': __builtins__,
        }
        namespace['__file__'] = str(path)
        functions = {}
        staging_table = dict(_TABLE) if staging_table is None else staging_table
        staging_table[('__namespace__', self.relative)] = namespace
        wrappers = dict(self.wrappers)
        def bind(key):
            def decorate(function):
                functions[key] = function
                staging_table[(self.relative, key)] = function
                if key not in wrappers:
                    wrappers[key] = _wrapper(self.relative, key, function)
                return wrappers[key]
            return decorate
        namespace['__program_bind__'] = bind
        if not initial:
            # Unchanged module-owned state retains identity, including sockets,
            # locks and caches. Never re-run its initializer on replacement.
            old = _assignments(ast.parse(self.source))
            new = _assignments(tree)
            changed_state = {k for k in old.keys() & new.keys() if old[k] != new[k]
                             and k in self.namespace and not isinstance(self.namespace[k],
                             (str, int, float, bool, tuple, frozenset, Path, type(None), types.ModuleType, type))
                             and not callable(self.namespace[k])}
            has_restore = any(isinstance(n, ast.FunctionDef) and n.name == '__program_restore__' for n in tree.body)
            if changed_state and not has_restore:
                raise ValueError('State initializer requires __program_restore__: ' + ', '.join(sorted(changed_state)))
            retained = {k for k in old.keys() & new.keys() if old[k] == new[k] and k in self.namespace}
            literal = {node.targets[0].id for node in tree.body if isinstance(node, ast.Assign)
                       and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                       and isinstance(node.value, ast.Constant)}
            retained = {k for k in retained if not hasattr(self.namespace[k], 'add_api_route')
                        and '__file__' not in old[k] and (k in literal or not isinstance(
                            self.namespace[k], (str, int, float, bool, tuple, frozenset, Path)))}
            namespace.update({k: self.namespace[k] for k in retained})
            body = []
            for node in tree.body:
                names = _assignments(ast.Module(body=[node], type_ignores=[]))
                if names and set(names) <= retained:
                    continue
                # Top-level registration/launch effects belong to the owner's
                # lifecycle. An unchanged effect has already happened.
                if isinstance(node, ast.Expr) and not isinstance(node.value, ast.Constant):
                    if any(ast.dump(node) == ast.dump(n) for n in ast.parse(self.source).body):
                        continue
                    raise ValueError('Changed import effect needs owner lifecycle: ' + self.relative)
                body.append(node)
            tree.body = body
        previous = {}
        def definitions(nodes, prefix=''):
            for node in nodes:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    previous[prefix + node.name + _accessor(node)] = node
                elif isinstance(node, ast.ClassDef):
                    definitions(node.body, prefix + node.name + '.')
        if not initial:
            definitions(ast.parse(self.source).body)
        boundary = Boundary(previous)
        tree = ast.fix_missing_locations(boundary.visit(tree))
        token = _PIN.set(staging_table)
        try:
            exec(compile(tree, str(path), 'exec'), namespace)
        finally:
            _PIN.reset(token)
        namespace.pop('__program_bind__', None)
        for key in boundary.reused:
            if '.' not in key:
                namespace[key] = self.namespace[key]
            else:
                parts = key.split('.')  # path-ok: Python qualname
                old_class = self.classes.get(parts[0])
                new_class = namespace.get(parts[0])
                if old_class and new_class and len(parts) == 2:
                    attribute = parts[1].split('@', 1)[0]
                    setattr(new_class, attribute, vars(old_class)[attribute])
        if not initial:
            for name, old_value in self.namespace.items():
                value = namespace.get(name)
                if hasattr(old_value, 'add_api_route') and hasattr(value, 'add_api_route') and value is not old_value:
                    value.routes[:] = [*old_value.routes, *value.routes]
            restore = functions.get('__program_restore__')
            if self.targets.get('__program_retire__') and not restore:
                raise ValueError('Resource retirement requires __program_restore__')
            if restore:
                export = self.targets.get('__program_export__')
                state = _invoke(_TABLE, export, (), {}) if export else dict(self.namespace)
                _invoke(staging_table, restore, (state,), {})
        classes = {k: v for k, v in namespace.items() if isinstance(v, type) and v.__module__ == self.module.__name__}
        if not initial:
            missing = set(self.targets) - set(functions)
            if missing:
                raise ValueError('Live callable removed; migrate its consumers first: ' + ', '.join(sorted(missing)))
            for key in self.targets.keys() & functions.keys():
                old_node = previous[key]
                declared = (ast.dump(old_node.args), ast.dump(old_node.returns) if old_node.returns else None)
                if declared != boundary.signatures[key]:
                    raise ValueError('Callable signature requires consumer migration: ' + key)
                original, following = self.targets[key], functions[key]
                old_params = inspect.signature(original).parameters
                new_params = inspect.signature(following).parameters
                for name, parameter in old_params.items():
                    old_default, new_default = parameter.default, new_params[name].default
                    if old_default is new_default:
                        continue
                    if isinstance(old_default, (str, int, float, bool, tuple, frozenset, type(None))):
                        if old_default != new_default:
                            raise ValueError('Callable default requires consumer migration: ' + key)
                    elif hasattr(old_default, '_attributes_set') and repr(old_default) != repr(new_default):
                        raise ValueError('Parameter metadata requires consumer migration: ' + key)
                # Decorator frameworks construct equivalent parameter objects on
                # every import. Keep the bound defaults/schema objects, including
                # mutable default state, when their declarations are unchanged.
                following.__defaults__ = original.__defaults__
                following.__kwdefaults__ = original.__kwdefaults__
                following.__annotations__ = dict(original.__annotations__)
            for name, original in self.classes.items():
                replacement = classes.get(name)
                if replacement is None or (original.__bases__ != tuple(self.classes.get(b.__name__, b) if b.__module__ == self.module.__name__ else b for b in replacement.__bases__) or
                        getattr(original, '__slots__', None) != getattr(replacement, '__slots__', None) or
                        getattr(original, '__annotations__', {}) != getattr(replacement, '__annotations__', {})):
                    raise ValueError('Class layout requires owner migration: ' + name)
                namespace[name] = original
                for function in functions.values():
                    if function.__closure__:
                        for cell in function.__closure__:
                            try:
                                if cell.cell_contents is replacement:
                                    cell.cell_contents = original
                            except ValueError:
                                pass
        return namespace, functions, wrappers, classes


class LiveModule(types.ModuleType):
    def __getattribute__(self, name):
        raw = types.ModuleType.__getattribute__(self, '__dict__')
        owner = raw.get('__program_owner__')
        if owner is not None:
            pinned = _PIN.get()
            namespace = pinned.get(('__namespace__', owner.relative), owner.namespace) if pinned is not None else owner.namespace
            if name == '__dict__':
                return namespace
            if name in namespace:
                return namespace[name]
        return types.ModuleType.__getattribute__(self, name)

    def __setattr__(self, name, value):
        owner = types.ModuleType.__getattribute__(self, '__dict__').get('__program_owner__')
        if owner is not None and name not in {'__class__', '__program_owner__'}:
            pinned = _PIN.get()
            namespace = pinned.get(('__namespace__', owner.relative), owner.namespace) if pinned is not None else owner.namespace
            namespace[name] = value
        else:
            types.ModuleType.__setattr__(self, name, value)

    def __delattr__(self, name):
        owner = types.ModuleType.__getattribute__(self, '__dict__').get('__program_owner__')
        if owner is not None and name in owner.namespace:
            del owner.namespace[name]
        else:
            types.ModuleType.__delattr__(self, name)


def initialize(relative, module, source, path):
    global _TABLE
    with _LOCK:
        owner = Owner(relative, module, source)
        module.__program_owner__ = owner
        module.__class__ = LiveModule
        namespace, targets, wrappers, classes = owner.execute(source, path, initial=True)
        owner.targets, owner.wrappers, owner.classes = targets, wrappers, classes
        owner.namespace = namespace
        _OWNERS[relative] = owner
        _TABLE = Dispatch({**_TABLE, ('__namespace__', relative): namespace,
                  **{(relative, k): v for k, v in targets.items()}})
    return module


def prepare(changes, root):
    """Rebind transitive `from` consumers as part of the selected publication."""
    prepared = []
    with _LOCK:
        selected = set(changes)
        by_name = {o.module.__name__: p for p, o in _OWNERS.items()}
        dependencies = {p: {by_name[n.module] for n in ast.walk(ast.parse(o.source))
                            if isinstance(n, ast.ImportFrom) and n.module in by_name}
                        for p, o in _OWNERS.items()}
        while True:
            added = {p for p, deps in dependencies.items() if deps & selected} - selected
            if not added:
                break
            selected.update(added)
        ordered, visiting = [], set()
        def visit(relative):
            if relative in ordered or relative in visiting:
                return
            visiting.add(relative)
            for dep in dependencies.get(relative, set()) & selected:
                visit(dep)
            ordered.append(relative)
        for relative in sorted(selected):
            visit(relative)
        staging = dict(_TABLE)
        for relative in ordered:
            owner = _OWNERS.get(relative)
            if owner is None:
                if not relative.startswith('backend/'):
                    continue  # package namespaces have their own call leases
                for loaded in list(sys.modules.values()):
                    file = getattr(loaded, '__file__', None)
                    if file and Path(file).as_posix().endswith('/' + relative):
                        raise ValueError('Loaded owner has no call boundary: ' + relative)
                continue  # first import is selected by the finder
            path = Path(root) / relative
            if not path.is_file():
                raise ValueError('Loaded module removal requires consumer migration: ' + relative)
            source = path.read_text()
            prepared.append((owner, source, *owner.execute(source, path, staging_table=staging)))
    return prepared


def activate(prepared, version, root=None):
    global _TABLE
    with _LOCK:
        table = Dispatch(_TABLE)
        if root is not None:
            table[('__publication__', 'root')] = Path(root)
        for owner, source, namespace, targets, wrappers, classes in prepared:
            table.update({(owner.relative, k): v for k, v in targets.items()})
            table[('__namespace__', owner.relative)] = namespace
            # Stable class objects preserve every existing instance/reference.
            for name, original in owner.classes.items():
                for key, value in vars(classes[name]).items():
                    if key not in {'__dict__', '__weakref__', '__module__', '__slots__'}:
                        setattr(original, key, value)
            for value in owner.namespace.values():
                clear = getattr(value, 'cache_clear', None)
                if callable(clear):
                    clear()
            owner.namespace = namespace
            owner.source, owner.targets, owner.wrappers = source, targets, wrappers
            owner.classes = {k: namespace[k] for k in classes}
            owner.version = version
        _TABLE = table


def load_file(name, path, relative):
    """Spec-loaded mixed packages use the same boundary as ordinary imports."""
    if protected_reason(relative):
        spec = __import__('importlib.util', fromlist=['util']).spec_from_file_location(name, path)
        module = __import__('importlib.util', fromlist=['util']).module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    with _LOCK:
        if relative in _OWNERS:
            return _OWNERS[relative].module
        module = types.ModuleType(name)
        module.__file__, module.__package__ = str(path), ''
        return initialize(relative, module, Path(path).read_text(), path)


class Finder(importlib.abc.MetaPathFinder):
    def __init__(self, code, source):
        self.code, self.source = Path(code).resolve(), Path(source).resolve()

    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None:
            from program_publication import selected
            overlay, row = selected(self.source, self.code)
            if row:
                for directory in path or sys.path:
                    try:
                        relative_dir = Path(directory).resolve().relative_to(self.code)
                    except ValueError:
                        continue
                    candidate = overlay / relative_dir / (fullname.rpartition('.')[2] + '.py')
                    if candidate.is_file():
                        spec = importlib.util.spec_from_file_location(fullname, candidate)
                        break
        if not spec or not spec.origin or not spec.origin.endswith('.py'):
            return None
        origin = Path(spec.origin).resolve()
        try:
            relative = origin.relative_to(self.code).as_posix()
        except ValueError:
            from program_publication import selected
            overlay, row = selected(self.source, self.code)
            if not row or not origin.is_relative_to(overlay):
                return None
            relative = origin.relative_to(overlay).as_posix()
        if not relative.startswith('backend/') or protected_reason(relative):
            return None
        source = self.source
        class Loader(importlib.abc.Loader):
            def create_module(self, spec):
                return None

            def exec_module(self, module):
                from program_publication import selected_path
                selected = selected_path(source, self_code, relative)
                initialize(relative, module, selected.read_text(), selected)
        self_code = self.code
        spec.loader = Loader()
        return spec


def install(code, source):
    global _TABLE
    code = Path(code).resolve()
    if any(f.code == code for f in _FINDERS):
        return
    from program_publication import selected
    active_root, _ = selected(source, code)
    _TABLE = Dispatch({**_TABLE, ('__publication__', 'root'): active_root})
    finder = Finder(code, source)
    _FINDERS.append(finder)
    sys.meta_path.insert(0, finder)


def pinned_root():
    table = _PIN.get()
    return table.get(('__publication__', 'root')) if table is not None else None


def load_sibling(name, directory):
    path = Path(directory) / (name + '.py')
    relative = 'data/packages/installed/tools/system_essentials/' + name + '.py'
    managed = any(path.resolve().is_relative_to(f.code) for f in _FINDERS)
    if managed and not protected_reason(relative):
        from program_publication import selected_path
        from runtime_utils import get_code_root, get_source_root
        path = selected_path(get_source_root(), get_code_root(), relative)
        return load_file(name, path, relative)
    spec = __import__('importlib.util', fromlist=['util']).spec_from_file_location(name, path)
    module = __import__('importlib.util', fromlist=['util']).module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CHECKPOINTS = {}


def publish(prepared, version, root, publication):
    """Keep dispatch and disk pointer behind one activation lock, with undo."""
    with _LOCK:
        states = [(o, o.source, o.namespace, o.targets, o.wrappers, o.classes, o.version,
                   {name: dict(vars(cls)) for name, cls in o.classes.items()})
                  for o, *_ in prepared]
        _CHECKPOINTS[version] = (_TABLE, states, [(m, list(m['app'].router.routes), m['router'], list(m['routes'])) for m in _MOUNTS], Path(root))
        try:
            activate(prepared, version, root)
            refresh_mounts(prepared)
            publication()
        except BaseException:
            rollback(version)
            raise


def rollback(version):
    global _TABLE
    with _LOCK:
        checkpoint = _CHECKPOINTS.get(version)
        if checkpoint is None:
            return
        active = _TABLE.get(('__publication__', 'root'))
        if _TABLE is not checkpoint[0] and active is not None and active != checkpoint[3]:
            raise ValueError('A newer publication is active; refusing to overwrite its dispatch table')
        _CHECKPOINTS.pop(version, None)
        table, states, mounts, root = checkpoint
        for mount, routes, router, installed in mounts:
            mount['app'].router.routes = routes
            mount['app'].openapi_schema = None
            mount['router'], mount['routes'] = router, installed
        for owner, source, namespace, targets, wrappers, classes, old_version, attributes in states:
            for name, values in attributes.items():
                for key, value in values.items():
                    if key not in {'__dict__', '__weakref__', '__slots__', '__module__'}:
                        setattr(classes[name], key, value)
            owner.source, owner.namespace, owner.targets = source, namespace, targets
            owner.wrappers, owner.classes, owner.version = wrappers, classes, old_version
        _TABLE = table


def accept(version):
    with _LOCK:
        checkpoint = _CHECKPOINTS.pop(version, None)
        if checkpoint:
            table, states, _, root = checkpoint
            for owner, source, namespace, targets, wrappers, classes, old_version, attributes in states:
                retire = targets.get('__program_retire__')
                if retire and isinstance(table, Dispatch):
                    weakref.finalize(table, retire)


_MOUNTS = []


def bind_app(app):
    """Composition-root hook; every ordinary router gets the same mount contract."""
    original = app.include_router
    def include(router, **kwargs):
        before = {id(r) for r in app.router.routes}
        result = original(router, **kwargs)
        _MOUNTS.append({'app': app, 'router': router, 'kwargs': kwargs,
                        'routes': [r for r in app.router.routes if id(r) not in before]})
        return result
    app.include_router = include


def refresh_mounts(prepared):
    import copy
    for owner, source, namespace, targets, wrappers, classes in prepared:
        for mount in _MOUNTS:
            # Match by exported router identity from the rollback checkpoint,
            # since activation has already switched owner.namespace.
            checkpoint = _CHECKPOINTS.get(owner.version)
            old_namespace = next((s[2] for s in checkpoint[1] if s[0] is owner), {}) if checkpoint else {}
            name = next((k for k, v in old_namespace.items() if v is mount['router']), None)
            if name is None or namespace.get(name) is mount['router']:
                continue
            router = namespace.get(name)
            if not hasattr(router, 'add_api_route'):
                raise ValueError('Mounted router removed: ' + name)
            app = mount['app']
            shadow = copy.copy(app.router)
            shadow.routes = []
            shadow.include_router(router, **mount['kwargs'])
            old_ids = {id(r) for r in mount['routes']}
            positions = [i for i, r in enumerate(app.router.routes) if id(r) in old_ids]
            insertion = min(positions) if positions else len(app.router.routes)
            routes = [r for r in app.router.routes if id(r) not in old_ids]
            routes[insertion:insertion] = shadow.routes
            app.router.routes = routes
            app.openapi_schema = None
            mount['router'], mount['routes'] = router, list(shadow.routes)
