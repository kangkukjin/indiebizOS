"""YouTube 통합 계약·기기 라우팅·용례 이관. 외부 호출/재생 없이 기존 동작을 검증한다."""
import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import yaml
from common.pkg_utils import load_sibling
from ibl_ops import op_returns, op_runs_on, op_side_effect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
PACKAGE = ROOT / 'data/packages/installed/tools/youtube'
CONFIG = yaml.safe_load((PACKAGE / 'ibl_actions.yaml').read_text())['nodes']['limbs']['actions']['youtube']
OLD = ('sense:video', 'sense:search_youtube', 'limbs:music')
OPS = {'search', 'info', 'transcript', 'languages', 'channel', 'summarize',
       'play', 'add', 'skip', 'seek', 'queue', 'stop', 'download', 'relay'}
PC_OPS = {'info', 'transcript', 'languages', 'channel', 'summarize', 'download', 'relay'}
READ_OPS = {'search', 'info', 'transcript', 'languages', 'channel', 'queue', 'relay'}


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('op,method', [
    ('search', 'search_youtube'), ('info', 'get_youtube_info'),
    ('transcript', 'get_youtube_transcript'), ('languages', 'list_available_transcripts'),
    ('channel', 'get_youtube_channel'), ('summarize', 'summarize_youtube'),
    ('play', 'play_youtube'), ('add', 'add_to_queue'), ('skip', 'skip_youtube'),
    ('seek', 'seek_youtube'), ('queue', 'get_queue'), ('stop', 'stop_youtube'),
    ('download', 'download_youtube_music'), ('relay', 'relay_youtube'),
])
def test_every_op_preserves_underlying_implementation(monkeypatch, op, method):
    handler = load_sibling(str(PACKAGE / 'handler.py'), 'handler')
    calls = []
    response = {'success': True, 'upload_date': '20261020', 'title': 'fixture',
                'results': [{'video_id': 'test', 'title': 'fixture'}], 'source_evidence': 'kept'}

    def call(*args, **kwargs):
        calls.append((args, kwargs))
        return copy.deepcopy(response)

    yt = SimpleNamespace(_phone=SimpleNamespace(is_phone=lambda: False), **{method: call})
    monkeypatch.setattr(handler, 'load_tool_youtube', lambda: yt)
    params = {'op': op, 'video_id': 'test', 'url': 'https://youtube.com/watch?v=test',
              'query': 'fixture', 'limit': 3, 'language': 'ko', 'handle': '@test', 'position': 12}
    original = dict(params)
    result = handler.execute(params, SimpleNamespace(tool_name='youtube_op'))
    assert params == original  # 재사용되는 입력을 pop으로 훼손하지 않는다.
    assert len(calls) == 1 and result['success']
    assert result['source_evidence'] == 'kept'
    if op == 'search':
        assert result['items'][0]['video_id'] == 'test' and calls[0][1]['count'] == 3
    if op == 'info':
        assert result['items'][0]['upload_date'] == '2026-10-20'
    if op in {'transcript', 'summarize'}:
        assert calls[0][1]['languages'] == ['ko']
    if op == 'seek':
        assert calls[0][0] == (12,)


def test_default_search_and_unknown_op_never_play(monkeypatch):
    handler = load_sibling(str(PACKAGE / 'handler.py'), 'handler')
    yt = SimpleNamespace(_phone=SimpleNamespace(is_phone=lambda: False),
                         search_youtube=lambda **kw: {'success': True, 'results': []})
    monkeypatch.setattr(handler, 'load_tool_youtube', lambda: yt)
    assert handler.execute({'query': 'empty'}, SimpleNamespace(tool_name='youtube_op'))['items'] == []
    assert not handler.execute({'op': 'missing'}, SimpleNamespace(tool_name='youtube_op'))['success']


def test_one_public_word_and_per_op_effect_return_contracts():
    nodes = yaml.safe_load((ROOT / 'data/ibl_nodes.yaml').read_text())['nodes']
    for q in OLD:
        node, name = q.split(':')
        assert name not in nodes[node]['actions']
    assert 'music' in nodes['self']['actions']
    assert set(CONFIG['ops']['values']) == OPS
    assert {op for op in OPS if not op_side_effect(CONFIG, op)} == READ_OPS
    assert {op for op in OPS if op_runs_on(CONFIG, op) == 'pc_only'} == PC_OPS
    assert op_returns(CONFIG, 'search') == op_returns(CONFIG, 'info') == 'items'
    assert op_returns(CONFIG, 'transcript') == 'scalar'
    assert op_returns(CONFIG, 'play') == 'effect'
    tools = json.loads((PACKAGE / 'tool.json').read_text())['tools']
    assert [t['name'] for t in tools] == ['youtube_op']
    assert set(tools[0]['input_schema']['properties']['op']['enum']) == OPS


@pytest.mark.parametrize('op', sorted(OPS))
def test_phone_routes_only_pc_ops_to_hub(monkeypatch, op):
    import ibl_engine as engine
    import device_registry
    monkeypatch.setenv('INDIEBIZ_PROFILE', 'phone')
    monkeypatch.setattr(engine, '_phone_runnable', lambda *a: True)
    monkeypatch.setattr(device_registry, 'live_with_capability', lambda *a: [])
    calls = []

    def forward(node, action, params, **kw):
        calls.append((node, action, params))
        return {'forwarded': True}

    monkeypatch.setattr(engine, '_forward_to_mac', forward)
    result = engine._resolve_and_maybe_forward('limbs', 'youtube', CONFIG, {'op': op}, None, None)
    assert bool(calls) == (op in PC_OPS)
    assert result == ({'forwarded': True} if op in PC_OPS else None)


def test_routing_override_is_generic_and_invalid_declarations_rejected():
    action = {'runs_on': 'anywhere', 'ops': {'values': {'read': 'Read'}, 'default': 'read',
                                            'runs_on': {'missing': 'elsewhere'}}}
    assert op_runs_on({'runs_on': 'pc_only'}, None) == 'pc_only'
    assert op_runs_on(action, 'read') == 'anywhere'
    # op 검증은 실제 빌드에서도 실행한다.
    from iblbuild_validators import _check_op_axis
    issues = _check_op_axis('limbs:fixture', action, action['ops'], action['ops']['values'])
    assert any('유령 op' in i for i in issues)
    assert any('elsewhere' in i for i in issues)
    action['runs_on'] = 'pc_only'
    assert any('기본 runs_on' in i for i in
               _check_op_axis('limbs:fixture', action, action['ops'], action['ops']['values']))


@pytest.mark.parametrize('old,op', [('sense:video', 'info'), ('sense:search_youtube', 'search'), ('limbs:music', 'play')])
def test_migration_makes_previous_default_explicit(old, op):
    migrate = script('migrate_youtube_vocab')
    for code in [f'[{old}]{{query:"x"}}', f'[{old}]{{}}', f'[{old}]']:
        new = migrate.transform(code)
        assert f'op: "{op}"' in new and f'[{old}]' not in new
        assert migrate.transform(new) == new


def test_nested_schedule_and_remote_programs_migrate_but_text_stays():
    migrate = script('migrate_youtube_vocab')
    source = '[self:schedule]{code:' + json.dumps('[limbs:guestpc]{code:' + json.dumps('[limbs:music]{op:"stop"}') + '}') + '}'
    result = migrate.transform(source)
    assert 'limbs:music' not in result and 'limbs:youtube' in result
    assert migrate.transform('[self:write]{content:"[limbs:music]{op:play}"}') == '[self:write]{content:"[limbs:music]{op:play}"}'


def test_prompt_has_only_canonical_youtube_name():
    from ibl_access import build_environment
    prompt = build_environment(allowed_nodes=['sense', 'limbs'], compact=True)
    assert '[limbs:youtube]' in prompt
    assert all(f'[{q}]' not in prompt for q in OLD)


def test_rekey_keeps_observation_date_and_rejects_collisions():
    sweep = script('ibl_shape_sweep')
    evidence = {'keys': ['video_id'], 'observed': '2026-10-19', 'source': 'fixture'}
    assert sweep.rekey_observations({'old': evidence}, {'old': 'new'}) == {'new': evidence}
    with pytest.raises(ValueError, match='충돌'):
        sweep.rekey_observations({'old': evidence, 'new': {}}, {'old': 'new'})


def test_migration_rekeys_observations_with_backup(tmp_path):
    migrate = script('migrate_youtube_vocab')
    data = tmp_path / 'data'
    data.mkdir()
    evidence = {'keys': ['video_id'], 'observed': '2026-10-19', 'source': 'fixture'}
    original = {'shapes': {'sense:video': evidence, 'limbs:music': {'source': 'usage'}}}
    path = data / 'ibl_return_shapes.json'
    path.write_text(json.dumps(original))
    assert migrate.migrate(tmp_path)['observations'] == 2
    assert json.loads(path.read_text()) == original
    migrate.migrate(tmp_path, apply=True)
    assert json.loads(path.read_text())['shapes'] == {'limbs:youtube#info': evidence}
    backup = data / '_backups/2026-10-20_youtube_vocab/ibl_return_shapes.json'
    assert json.loads(backup.read_text()) == original
    assert not migrate.migrate(tmp_path)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
