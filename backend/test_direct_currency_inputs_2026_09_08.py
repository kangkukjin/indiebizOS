"""join의 직접 입력은 파이프 입력과 같은 통화다 — 검사/실행 일치 회귀."""
import importlib.util
import json
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
from ibl_parser import parse
from ibl_typecheck import typecheck_code
from ibl_pipe_types import head_transform_error, seam_starvation_error

ROOT = Path(__file__).resolve().parents[1]
LEFT = '[{id: 1, tag: "a", x: 10}, {id: 1, tag: "b", x: 20}]'
RIGHT = '[{id: 1, tag: "a", y: 30}]'
CALL = f'[table:join]{{left: {LEFT}, right: {RIGHT}, on: ["id", "tag"]}}'


@pytest.mark.parametrize('prefix', ['', '$joined = '])
@pytest.mark.parametrize('key', ['"id"', '["id", "tag"]'])
def test_direct_join_checked_and_executed(monkeypatch, tmp_path, prefix, key):
    import ibl_engine
    import workflow_engine
    from tool_context import ToolContext
    spec = importlib.util.spec_from_file_location('_direct_dataops', ROOT / 'data/packages/installed/tools/data-ops/handler.py')
    dataops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dataops)

    def leaf(ti, project, agent=None):
        assert ti['_node'] == 'table'
        return dataops.execute(ti['params'], ToolContext(project, 'data_' + ti['action']))
    monkeypatch.setattr(ibl_engine, '_execute_ibl_impl', leaf)
    code = prefix + f'[table:join]{{left: {LEFT}, right: {RIGHT}, on: {key}}} >> [table:select]{{columns: ["x", "y"]}}'
    checked = typecheck_code(code)
    assert checked['ok'] and 'abstained' not in checked, checked
    out = workflow_engine.execute_pipeline(parse(code), str(tmp_path))
    assert out['success'], out
    result = out['final_result']
    result = json.loads(result) if isinstance(result, str) else result
    assert result['items'] == ([{'x': 10, 'y': 30}] if key.startswith('[') else [{'x': 10, 'y': 30}, {'x': 20, 'y': 30}])


def test_direct_inputs_override_effect_and_keep_missing_input_guard():
    code = '[self:write]{path: "unused", content: "x"} >> ' + CALL
    assert seam_starvation_error(parse(code)) is None
    assert typecheck_code(code)['ok']
    assert head_transform_error(parse(f'[table:join]{{left: {LEFT}, on: "id"}}'))
    assert head_transform_error(parse('[table:take]{left: [], right: [], n: 1}'))
    assert typecheck_code('[table:join]{left: [], right: [], on: "id"}')['ok']


def test_variable_inputs_are_typed_not_blindly_exempted():
    a = f'$a = [table:take]{{items: {LEFT}, n: 2}}; '
    b = f'$b = [table:take]{{items: {RIGHT}, n: 2}}; '
    call = '[table:join]{left: "$a", right: "$b", on: "id"}'
    assert typecheck_code(a + b + call)['ok']
    bad = typecheck_code(a + '$b = [self:write]{path:"unused", content:"x"}; ' + call)
    assert not bad['ok'], bad
    bad_col = typecheck_code(CALL + ' >> [table:select]{columns: ["missing"]}')
    assert not bad_col['ok'], bad_col
    # join의 동명 비키 열 접미사는 단순 union 선언만으로 확정할 수 없다.
    collision = f'[table:join]{{left: {LEFT}, right: {LEFT}, on: ["id", "tag"]}} >> [table:select]{{columns: ["x_2"]}}'
    assert typecheck_code(collision)['ok']


def test_shared_workspace_file_and_missing_ledger_hint(monkeypatch, tmp_path):
    from tool_context import ToolContext
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    spec = importlib.util.spec_from_file_location('_direct_ledger', ROOT / 'data/packages/installed/tools/system_essentials/ledger_ops.py')
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    monkeypatch.setattr(ledger, '_ROOT', tmp_path)
    ctx = ToolContext(str(tmp_path / 'data'), 'write_file')
    raw = '~workspace/outputs/shared.json'
    path = Path(ctx.resolve_path(raw))
    path.parent.mkdir(parents=True)
    path.write_text('[{"id": 1}]')
    assert ledger.op_select({'path': raw})['items'] == [{'id': 1}]
    # 기존의 상대경로 계약을 바꾸거나 다른 뿌리의 파일을 몰래 읽지 않는다.
    assert ctx.resolve_path('outputs/shared.json') != str(ledger._target_path('outputs/shared.json'))
    missing = ledger.op_select({'path': 'outputs/missing.json'})
    assert not missing['success'] and missing['path'] == str(tmp_path / 'outputs/missing.json')
    assert '~workspace/' in missing['hint']


def test_registered_nesting_script_paths_and_no_partial_write(monkeypatch, tmp_path):
    import subprocess
    import sys
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    script = ROOT / 'data/scripts/nest_tip_rows.py'
    row = {'tip': '팁', 'how': '방법', 'topic': '개발', 'video_id': 'v1', 'title': '제목',
           'channel': '채널', 'url': 'https://example.com/v1', 'date': '2026-10-01',
           'report': '다음 보고서', 'try_candidate': False}
    src = tmp_path / 'input.json'
    out = tmp_path / 'outputs/next.json'

    def run(rows):
        src.write_text(json.dumps({'items': rows}), encoding='utf-8')
        return subprocess.run([sys.executable, str(script)], cwd=tmp_path,
                              input=json.dumps({'src': '~workspace/input.json', 'out': '~workspace/outputs/next.json'}),
                              text=True, capture_output=True)
    r = run([row])
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(r.stdout)['path'] == str(out)
    saved = out.read_bytes()
    result = json.loads(saved)
    assert result['items'][0]['date'] == '2026-10-01'
    assert result['items'][0]['try_candidate'] is False
    assert result['items'][0]['source']['video_id'] == 'v1'
    r = run([row, {**row, 'try_candidate': 'false'}])
    assert r.returncode == 2 and not json.loads(r.stdout)['success']
    assert out.read_bytes() == saved
    r = subprocess.run([sys.executable, str(script)], input='{}', text=True, capture_output=True)
    assert r.returncode == 2 and '경로' in json.loads(r.stdout)['error']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
