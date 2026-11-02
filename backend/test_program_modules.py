"""Stable consumer references, revision leases, state and failure isolation."""
import asyncio
import importlib
from pathlib import Path
import sys
import types

import boot_paths  # noqa: F401
import pytest
import program_modules as modules


@pytest.fixture
def owner(tmp_path):
    original = dict(modules._TABLE), dict(modules._OWNERS)
    def create(source, relative='backend/services/example.py'):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        module = types.ModuleType('test_live_example')
        module.__file__ = str(path)
        modules.initialize(relative, module, source, path)
        return module, path
    yield create
    modules._TABLE, modules._OWNERS = original


def replace(path, source):
    path.write_text(source)
    root = path.parents[2]
    prepared = modules.prepare([path.relative_to(root).as_posix()], root)
    modules.activate(prepared, 'test-version', root)


def test_captured_functions_instances_globals_and_old_generator(owner):
    source = '''state = []
FACTOR = 1
def helper(): return FACTOR
def run():
 state.append(1)
 return helper(), len(state)
def stream():
 yield helper()
 yield helper()
class Counter:
 def value(self): return helper()
'''
    module, path = owner(source)
    reference, instance = module.run, module.Counter()
    call = module.stream()
    assert next(call) == 1
    assert reference() == (1, 1)
    replace(path, source.replace('FACTOR = 1', 'FACTOR = 2'))
    assert reference() == (2, 2)
    assert instance.value() == 2
    assert next(call) == 1
    call.close()
    assert reference() == (2, 3)  # generator did not leak its ContextVar into caller
    assert module.state == [1, 1, 1]


def test_async_call_retains_revision_across_await(owner):
    source = '''FACTOR = 1
def helper(): return FACTOR
async def run(entered, resume):
 entered.set()
 await resume.wait()
 return helper()
'''
    module, path = owner(source)
    async def check():
        entered, resume = asyncio.Event(), asyncio.Event()
        call = asyncio.create_task(module.run(entered, resume))
        await entered.wait()
        replace(path, source.replace('FACTOR = 1', 'FACTOR = 9'))
        resume.set()
        assert await call == 1
        assert await module.run(entered, resume) == 9
    asyncio.run(check())


def test_registered_decorator_reference_changes_without_registration_again(owner):
    source = '''registered = []
def register(function):
 registered.append(function)
 return function
@register
def endpoint(): return 1
'''
    module, path = owner(source)
    captured = module.registered[0]
    replace(path, source.replace('return 1', 'return 2'))
    assert captured() == 2


def test_failed_load_never_changes_live_function_or_globals(owner):
    source = 'VALUE = 1\ndef run(): return VALUE\n'
    module, path = owner(source)
    with pytest.raises(RuntimeError, match='bad'):
        replace(path, source + '\nraise RuntimeError("bad")\n')
    assert module.run() == 1
    assert module.VALUE == 1


def test_layout_and_callable_removal_require_local_consumer_migration(owner):
    source = 'class Box:\n __slots__ = ("a",)\n def read(self): return 1\n'
    module, path = owner(source)
    box = module.Box()
    with pytest.raises(ValueError, match='layout'):
        replace(path, source.replace('("a",)', '("a", "b")'))
    assert box.read() == 1
    with pytest.raises(ValueError, match='removed'):
        replace(path, 'class Box:\n __slots__ = ("a",)\n')
    assert box.read() == 1


def test_zero_argument_super_and_module_assignment(owner):
    source = '''class Base:
 def read(self): return 1
class Child(Base):
 def read(self): return super().read() + 1
'''
    module, path = owner(source)
    instance = module.Child()
    replace(path, source.replace('return 1', 'return 2'))
    assert instance.read() == 3


def test_finder_instruments_before_from_import_or_router_capture(tmp_path):
    root = tmp_path / 'code'
    path = root / 'backend/services'
    path.mkdir(parents=True)
    (path / 'fresh_feature.py').write_text('def result(): return 1\n')
    sys.path.insert(0, str(path))
    before = list(sys.meta_path), list(modules._FINDERS), dict(modules._OWNERS), dict(modules._TABLE)
    try:
        modules.install(root, root)
        module = importlib.import_module('fresh_feature')
        captured = module.result
        (path / 'fresh_feature.py').write_text('def result(): return 2\n')
        modules.activate(modules.prepare(['backend/services/fresh_feature.py'], root), 'v2')
        assert captured() == 2
    finally:
        sys.path.remove(str(path))
        sys.modules.pop('fresh_feature', None)
        sys.meta_path[:], modules._FINDERS[:], modules._OWNERS, modules._TABLE = before


def test_property_getter_and_setter_have_distinct_slots(owner):
    source = '''class Box:
 def __init__(self): self._value = 1
 @property
 def value(self): return self._value + 1
 @value.setter
 def value(self, value): self._value = value
'''
    module, path = owner(source)
    instance = module.Box()
    instance.value = 4
    assert instance.value == 5
    replace(path, source.replace('self._value + 1', 'self._value + 2'))
    instance.value = 5
    assert instance.value == 7


def test_transitive_from_constant_consumer_gets_new_namespace(owner, tmp_path):
    source, path = owner('VALUE = 1\ndef run(): return VALUE\n')
    # Register actual module identity so Python's normal from-import sees it.
    sys.modules['test_live_example'] = source
    relative = 'backend/services/consumer.py'
    cp = tmp_path / relative
    cp.write_text('from test_live_example import VALUE\ndef run(): return VALUE * 2\n')
    consumer = types.ModuleType('live_consumer')
    try:
        modules.initialize(relative, consumer, cp.read_text(), cp)
        captured = consumer.run
        assert captured() == 2
        replace(path, 'VALUE = 4\ndef run(): return VALUE\n')
        assert captured() == 8
    finally:
        sys.modules.pop('test_live_example', None)


def test_failed_pointer_write_restores_code_and_existing_instance(owner):
    source = 'class Box:\n def read(self): return 1\n'
    module, path = owner(source)
    instance = module.Box()
    path.write_text(source.replace('return 1', 'return 2'))
    prepared = modules.prepare(['backend/services/example.py'], path.parents[2])
    def failed():
        raise OSError('publication failed')
    with pytest.raises(OSError):
        modules.publish(prepared, 'bad', path.parents[2], failed)
    assert instance.read() == 1


def test_mounted_api_keeps_existing_endpoint_and_accepts_new_route(owner):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    source = '''from fastapi import APIRouter, Query
router = APIRouter()
@router.get('/old')
def endpoint(amount: int = Query(1, ge=0)): return {'value': amount * 1}
'''
    module, path = owner(source)
    app = FastAPI()
    before_mounts = list(modules._MOUNTS)
    modules.bind_app(app)
    app.include_router(module.router, prefix='/feature')
    try:
        client = TestClient(app)
        assert client.get('/feature/old').json() == {'value': 1}
        path.write_text(source.replace("amount * 1", "amount * 2") +
                        "\n@router.get('/new')\ndef new_endpoint(): return {'new': True}\n")
        prepared = modules.prepare(['backend/services/example.py'], path.parents[2])
        modules.publish(prepared, 'api-v2', path.parents[2], lambda: None)
        assert client.get('/feature/old').json() == {'value': 2}
        assert client.get('/feature/new').json() == {'new': True}
        modules.rollback('api-v2')
        assert client.get('/feature/old').json() == {'value': 1}
        assert client.get('/feature/new').status_code == 404
    finally:
        modules._MOUNTS[:] = before_mounts


def test_changed_owned_state_requires_and_uses_migration_contract(owner):
    source = '''state = {'count': 0}
def run():
 state['count'] += 1
 return state['count']
def __program_export__(): return state['count']
'''
    module, path = owner(source)
    assert module.run() == 1
    changed = source.replace("{'count': 0}", "{'count': 0, 'format': 2}")
    with pytest.raises(ValueError, match='State initializer'):
        replace(path, changed)
    replace(path, changed + "\ndef __program_restore__(old): state['count'] = old\n")
    assert module.run() == 2
    assert module.state['format'] == 2


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


def test_old_resource_retires_only_after_inflight_generator_finishes(owner):
    import gc
    source = '''retired = False
VALUE = 1
def stream():
 assert not retired
 yield VALUE
 assert not retired
 yield VALUE
def __program_export__(): return None
def __program_restore__(state): pass
def __program_retire__():
 global retired
 retired = True
'''
    module, path = owner(source)
    previous = module.__dict__
    stream = module.stream()
    assert next(stream) == 1
    path.write_text(source.replace('VALUE = 1', 'VALUE = 2'))
    prepared = modules.prepare(['backend/services/example.py'], path.parents[2])
    modules.publish(prepared, 'resource-v2', path.parents[2], lambda: None)
    modules.accept('resource-v2')
    gc.collect()
    assert not previous['retired']
    assert next(stream) == 1
    stream.close()
    gc.collect()
    assert previous['retired']
    assert not module.retired


def test_async_generator_keeps_send_throw_and_revision_contract(owner):
    source = '''VALUE = 1
async def stream():
 try:
  amount = yield VALUE
  yield amount + VALUE
 except LookupError:
  yield VALUE + 10
'''
    module, path = owner(source)
    async def check():
        old = module.stream()
        assert await old.__anext__() == 1
        replace(path, source.replace('VALUE = 1', 'VALUE = 2'))
        assert await old.asend(3) == 4
        assert await old.athrow(LookupError('test')) == 11
        await old.aclose()
        current = module.stream()
        assert await current.__anext__() == 2
        assert await current.asend(3) == 5
        await current.aclose()
    asyncio.run(check())
