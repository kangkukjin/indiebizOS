"""join의 직접 입력은 파이프 입력과 같은 통화다 — 검사/실행 일치 회귀."""
import importlib.util
import json
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
from ibl_typecheck import typecheck_code

ROOT = Path(__file__).resolve().parents[1]
LEFT = '[{id: 1, tag: "a", x: 10}, {id: 1, tag: "b", x: 20}]'
RIGHT = '[{id: 1, tag: "a", y: 30}]'
CALL = f'[table:join]{{left: {LEFT}, right: {RIGHT}, on: ["id", "tag"]}}'








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
