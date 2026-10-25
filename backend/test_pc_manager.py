"""포식 도구는 현재 선언과 장소 단언/항목 ID 계약을 따른다."""
import boot_paths  # noqa: F401
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def handler(monkeypatch):
    monkeypatch.setattr(sys, 'path', sys.path[:])
    path = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/pc-manager/handler.py'
    return runpy.run_path(str(path))


def test_forage_declared_arguments_checked_before_execution(tmp_path):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    registry = load_registry(str(tmp_path))
    source = '[self:forage]{op:"note",locus:"/fixture",kind:"identity",claim:"fixture"}'
    assert not compile_program(source, registry).issues
    invalid = source[:-1] + ',unprovided_field:1}'
    plan = compile_program(invalid, registry)
    assert any(i['code'] == 'UNKNOWN_ARGUMENT' for i in plan.issues)


def test_forage_note_requires_place_kind_and_claim(handler, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, 'forage_memory', SimpleNamespace(
        note_map=lambda **kw: calls.append(kw) or {'success': True}))
    execute = handler['execute']
    context = SimpleNamespace(tool_name='forage_op')
    for missing in ('locus', 'kind', 'claim'):
        args = {'op': 'note', 'body': 'test', 'locus': '/fixture', 'kind': 'identity', 'claim': 'fixture'}
        args.pop(missing)
        assert json.loads(execute(args, context))['success'] is False
    assert not calls
    args = {'op': 'note', 'body': 'test', 'locus': '/fixture', 'kind': 'identity', 'claim': 'fixture'}
    assert json.loads(execute(args, context))['success']
    assert len(calls) == 1 and calls[0]['locus'] == '/fixture'


def test_forage_forget_uses_item_id(handler, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, 'forage_memory', SimpleNamespace(
        forget=lambda **kw: calls.append(kw) or {'success': True, 'deleted': 1}))
    execute = handler['execute']
    context = SimpleNamespace(tool_name='forage_op')
    for args in ({'op': 'forget'}, {'op': 'forget', 'id': 'bad'}):
        assert json.loads(execute(args, context))['success'] is False
    assert not calls
    assert json.loads(execute({'op': 'forget', 'id': '12'}, context))['deleted'] == 1
    assert calls == [{'entry_id': 12}]


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
