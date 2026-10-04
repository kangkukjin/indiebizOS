"""File execution, CLI reproduction and the edit→new-attempt IBL loop."""
import boot_paths  # noqa: F401
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest
import file_script
from script_workspace import request_scope, workspace

ROOT = Path(__file__).resolve().parents[1]
RESULT = '''import json, os, sys
from pathlib import Path
args = json.load(sys.stdin)
print("debug: 한글 · ${x} · {}")
print("stderr diagnostic", file=sys.stderr)
path = Path(os.environ['INDIEBIZ_SCRIPT_RESULT'])
tmp = path.with_suffix('.tmp')
tmp.write_text(json.dumps(args, ensure_ascii=False), encoding='utf-8')
tmp.replace(path)
'''


def create(tmp_path, code=RESULT):
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    source = work / '분석.py'
    source.write_bytes(code.encode())
    return work, source


def test_result_is_separate_from_print_and_reproduction(tmp_path):
    work, source = create(tmp_path)
    stdin = json.dumps({'text': '한글\t\\n ${x}', 'password': 'test-only-secret'}).encode()
    result = file_script.execute(source, stdin, work)
    assert result['ok'] and result['value'] == json.loads(stdin)
    record = Path(result['record'])
    assert (record / 'stdin.json').read_bytes() == stdin
    assert (record / 'source/분석.py').read_bytes() == source.read_bytes()
    assert 'debug:' in (record / 'stdout.log').read_text()
    assert 'stderr diagnostic' in (record / 'stderr.log').read_text()
    assert record.stat().st_mode & 0o077 == 0
    reproduced = file_script.reproduce(record)
    assert reproduced['ok'] and reproduced['value'] == result['value']
    assert reproduced['meta']['cwd'] == result['meta']['cwd']
    assert reproduced['meta']['parent_execution'] == result['meta']['execution_id']
    assert reproduced['record'] != result['record']


@pytest.mark.parametrize('tail,code', [
    ('print(123)', 'RESULT_MISSING'),
    ("Path(os.environ['INDIEBIZ_SCRIPT_RESULT']).write_text('oops')", 'RESULT_INVALID'),
    ("Path(os.environ['INDIEBIZ_SCRIPT_RESULT']).write_text('1e999')", 'RESULT_INVALID'),
    ('raise RuntimeError("broken")', 'SCRIPT_EXIT'),
])
def test_missing_invalid_and_failure_do_not_fall_back(tmp_path, tail, code):
    work, source = create(tmp_path, 'import os\nfrom pathlib import Path\n' + tail)
    out = file_script.execute(source, b'{}', work)
    assert not out['ok'] and out['error']['code'] == code
    assert len(list((work.parent / 'executions').iterdir())) == 1


def test_null_and_partial_value(tmp_path):
    work, source = create(tmp_path, "import os\nfrom pathlib import Path\nPath(os.environ['INDIEBIZ_SCRIPT_RESULT']).write_text('null')")
    out = file_script.execute(source, b'{}', work)
    assert out['ok'] and out['has_value'] and out['value'] is None
    source.write_text(source.read_text() + '\nraise ValueError("after result")')
    out = file_script.execute(source, b'{}', work)
    assert not out['ok'] and out['has_value'] and out['value'] is None


def test_failed_cli_preserves_original_traceback(tmp_path):
    work, source = create(tmp_path, 'raise ValueError("한글 실패")\n')
    out = file_script.execute(source, b'{}', work)
    proc = subprocess.run([sys.executable, str(ROOT / 'backend/file_script_cli.py'), out['record']], capture_output=True, text=True)
    assert proc.returncode == 1, proc.stderr
    new = json.loads(proc.stdout)
    trace = (Path(new['record']) / 'stderr.log').read_text()
    assert '분석.py", line 1' in trace and 'ValueError: 한글 실패' in trace
    assert file_script.inspect_record(new['record'])['source_hashes'] == out['meta']['source_hashes']


def test_timeout_and_cancel_stop_child(tmp_path):
    import psutil
    work, source = create(tmp_path, 'import time\ntime.sleep(30)')
    out = file_script.execute(source, b'{}', work, timeout=.1)
    assert out['error']['code'] == 'SCRIPT_TIMEOUT'
    assert not psutil.pid_exists(out['meta']['pid'])
    start = time.monotonic()
    def check():
        if time.monotonic() - start > .15:
            raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError, match='cancelled'):
        file_script.execute(source, b'{}', work, check=check)
    for meta_path in (work.parent / 'executions').glob('*/meta.json'):
        meta = json.loads(meta_path.read_text())
        # 취소가 자식 spawn 보다 먼저 닿으면 pid 없는 'interrupted' 가 정상이다(2026-10-04 병렬 부하 실측).
        # 보는 것은 하나 — 살아 있는 자식이 없다.
        if 'pid' in meta:
            assert not psutil.pid_exists(meta['pid'])
        else:
            assert meta['state'] == 'interrupted', meta['state']


def test_expired_or_changed_record_never_uses_display_copy(tmp_path):
    work, source = create(tmp_path)
    out = file_script.execute(source, b'{}', work)
    record = Path(out['record'])
    (record / 'stdin.json').write_text('{"password":"****"}')
    with pytest.raises(file_script.ScriptError, match='지문'):
        file_script.reproduce(record)
    (record / 'stdin.json').write_bytes(b'{}')
    meta = out['meta'] | {'expires_at': 0}
    file_script.atomic_json(record / 'meta.json', meta)
    with pytest.raises(file_script.ScriptError, match='보존 기간'):
        file_script.reproduce(record)


@pytest.fixture
def ibl(tmp_path, monkeypatch):
    import script_workspace
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    registry = load_registry(str(ROOT))
    monkeypatch.setattr(script_workspace, 'storage_root', lambda: tmp_path / 'transient')
    with request_scope(ROOT, 'file-test'):
        def run(code, inputs=None, **kwargs):
            plan = compile_program(code, registry, inputs)
            assert not plan.issues, plan.report()
            return Runtime(plan, inputs, **kwargs).run()
        yield run


def test_ibl_write_edit_new_attempt_and_following_composition(ibl):
    bad = RESULT.replace('args = json.load(sys.stdin)', 'args = json.load(sys.stdin)\nraise ValueError("fix me")')
    first = ibl('$f=[self:write]{path:"~turn/분석.py",content:$code}\nreturn [self:script]{path:$f.path,args:$data}',
                {'code': bad, 'data': {'items': [{'n': 2}, {'n': 4}]}})
    assert not first['success'] and first['diagnostic']['code'] == 'SCRIPT_EXIT', first
    edited = ibl('[self:edit]{path:"~turn/분석.py",old_string:$old,new_string:$new}',
                 {'old': 'raise ValueError("fix me")\n', 'new': ''})
    assert edited['success'], edited
    second = ibl('$v=[self:script]{path:"~turn/분석.py",args:$data}\nreturn $v.items >> [table:filter]{where:($r)=>$r.n>2}',
                 {'data': {'items': [{'n': 2}, {'n': 4}]}})
    assert second['success'] and second['value'] == [{'n': 4}], second
    assert (workspace() / '분석.py').read_bytes() == RESULT.encode()


def test_nonowner_and_restricted_scope_denied(ibl):
    import principal
    from thread_context import set_allowed_nodes
    with principal.narrow(principal.ANONYMOUS):
        out = ibl('[self:script]{path:"~turn/a.py"}')
        assert not out['success']
    set_allowed_nodes(['self'])
    try:
        out = ibl('[self:script]{path:"~turn/a.py"}')
        assert not out['success']
    finally:
        set_allowed_nodes(None)


def test_links_and_foreign_turn_paths_are_rejected(ibl, tmp_path):
    work = workspace()
    work.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / 'outside.py'
    outside.write_text(RESULT)
    (work / 'link.py').symlink_to(outside)
    for path in (str(outside), '~turn/link.py', '~turn/../outside.py'):
        out = ibl('[self:script]{path:$path}', {'path': path})
        assert not out['success'], out


def test_retention_deletes_raw_record_and_work_but_skips_active(tmp_path):
    from filelock import FileLock
    root = tmp_path / 'transient'
    scope = root / ('a' * 64)
    scope.mkdir(parents=True)
    work, source = create(scope)
    out = file_script.execute(source, b'{"private":"test-only"}', work)
    later = time.time() + file_script.RETENTION_SECONDS + 1
    with FileLock(str(scope / '.execution.lock')):
        assert file_script.prune(root, later) == 0
        assert Path(out['record']).exists()
    assert file_script.prune(root, later) >= 1
    assert not Path(out['record']).exists() and not work.exists()


def test_completed_script_receipt_is_restored_and_changed_source_is_rejected(ibl, tmp_path):
    from ibl_run_journal import Journal, reusable_receipts
    source = RESULT + '\n'
    assert ibl('[self:write]{path:"~turn/분석.py",content:$code}', {'code': source})['success']
    code = 'return [self:script]{path:"~turn/분석.py",args:{n:2}}'
    with Journal(tmp_path / 'journal', 'test') as journal:
        run_id = journal.run_id
        first = ibl(code, journal=journal)
    assert first['success'], first
    before = len(list((workspace().parent / 'executions').iterdir()))
    assert reusable_receipts(tmp_path / 'journal', run_id) == {}
    with Journal(tmp_path / 'journal', 'test', {'run_id': run_id}) as journal:
        again = ibl(code, journal=journal)
    assert again['success'] and again['value'] == {'n': 2}, again
    assert len(list((workspace().parent / 'executions').iterdir())) == before
    (workspace() / '분석.py').write_text(source + '# changed\n')
    with Journal(tmp_path / 'journal', 'test', {'run_id': run_id}) as journal:
        changed = ibl(code, journal=journal)
    assert not changed['success'] and changed['diagnostic']['code'] == 'RESUME_DIVERGED', changed
    assert changed['diagnostic']['details']['changed'] == ['invocation_dependency.source_hashes']
    assert len(list((workspace().parent / 'executions').iterdir())) == before


def test_public_boundary_completed_ref_edit_and_new_attempt(tmp_path, monkeypatch):
    import ibl_run_journal
    import ibl_v2_store
    import ibl_v2_learning
    import model_result_view
    import script_workspace
    from supervision_store import TurnStore
    from system_tools_ibl import _execute_ibl_unified_impl
    from thread_context import actor_context
    store = TurnStore(tmp_path / 'evidence')
    monkeypatch.setattr(model_result_view, 'evidence_store', lambda: store)
    monkeypatch.setattr(ibl_run_journal, 'journal_root', lambda _: tmp_path / 'runs')
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {})
    monkeypatch.setattr(ibl_v2_learning, 'record_functions', lambda *a: None)
    monkeypatch.setattr(script_workspace, 'storage_root', lambda: tmp_path / 'transient')
    def run(code, inputs=None, **options):
        return json.loads(_execute_ibl_unified_impl({'edition': 2, 'code': code, 'inputs': inputs or {}, **options}, str(ROOT)))
    with actor_context(agent_id='file-test', task_id='file-debug-turn'):
        bad = RESULT.replace('args = json.load(sys.stdin)', 'args = json.load(sys.stdin)\nraise ValueError("fix me")')
        first = run('$f=[self:write]{path:"~turn/분석.py",content:$code}\n$v=[self:time]{format:"%Y"}\nreturn [self:script]{path:$f.path,args:{year:$v}}', {'code': bad})
        assert not first['success'], first
        completed = first['result_ref']['completed_calls']
        time_call = next(c for c in completed if c['action'] == 'self:time')
        patched = run('[self:edit]{path:"~turn/분석.py",old_string:$old,new_string:$new}', {'old': 'raise ValueError("fix me")\n', 'new': ''})
        assert patched['success'], patched
        fixed = run('$r=[self:script]{path:"~turn/분석.py",args:{year:$입력}}\nreturn $r.year', time_call['input_args'])
        assert fixed['success'] and isinstance(fixed['value'], str), fixed
        assert first['resume']['run_id'] != fixed['resume']['run_id']
    # A taskless request still resumes its original workspace, without rewriting it.
    code = '$f=[self:write]{path:"~turn/a.py",content:$code}\nreturn [self:script]{path:$f.path}'
    first = run(code, {'code': RESULT})
    assert first['success'], first
    before = len(list((tmp_path / 'transient').glob('*/executions/*')))
    resumed = run(code, {'code': RESULT}, resume=first['resume'])
    assert resumed['success'] and resumed['resumed'], resumed
    assert len(list((tmp_path / 'transient').glob('*/executions/*'))) == before


def test_unfinished_receipt_never_reexecutes(ibl, tmp_path):
    from ibl_run_journal import Journal
    assert ibl('[self:write]{path:"~turn/a.py",content:$code}', {'code': RESULT})['success']
    code = 'return [self:script]{path:"~turn/a.py"}'
    with Journal(tmp_path / 'journal', 'test') as journal:
        run_id = journal.run_id
        assert ibl(code, journal=journal)['success']
        journal.db.execute('UPDATE calls SET receipt=NULL')
        journal.db.commit()
    before = len(list((workspace().parent / 'executions').iterdir()))
    with Journal(tmp_path / 'journal', 'test', {'run_id': run_id}) as journal:
        out = ibl(code, journal=journal)
    assert not out['success'] and out['diagnostic']['code'] == 'EFFECT_UNCERTAIN', out
    assert len(list((workspace().parent / 'executions').iterdir())) == before


def test_turn_scope_does_not_restrict_unrelated_writes(ibl, tmp_path):
    from script_workspace import prepare_path
    import principal
    with principal.narrow(principal.ANONYMOUS):
        prepare_path(tmp_path / 'unrelated.txt')
        with pytest.raises(PermissionError):
            from script_workspace import expand
            expand('~turn/a.py')


def test_input_text_and_triple_quote_source_preserve_bytes(ibl):
    raw = RESULT + "# quotes: ''' \"\"\" · 역슬래시 \\ · 탭\t · ${이름}\n"
    written = ibl('[self:write]{path:"~turn/정확.py",content:$code}', {'code': raw})
    assert written['success'], written
    assert (workspace() / '정확.py').read_bytes() == raw.encode('utf-8')
    raw_literal = "# 한글\t\\n $이름 {} ' \"\nprint('ok')\n"
    written = ibl('[self:write]{path:"~turn/리터럴.py",content:"""' + raw_literal.replace('\\', '\\\\') + '"""}')
    assert written['success'], written
    assert (workspace() / '리터럴.py').read_bytes() == raw_literal.encode('utf-8')


def test_parallel_calls_keep_turn_context_and_independent_results(ibl):
    assert ibl('[self:write]{path:"~turn/a.py",content:$code}', {'code': RESULT})['success']
    out = ibl('[1,2] >> [table:each]{parallel:2}{return [self:script]{path:"~turn/a.py",args:{n:$it}}}')
    assert out['success'] and out['value'] == [{'n': 1}, {'n': 2}], out
    records = list((workspace().parent / 'executions').glob('*/result.json'))
    assert len(records) == 2
    assert sorted(json.loads(p.read_text())['n'] for p in records) == [1, 2]


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
