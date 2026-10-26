"""Repair-training evidence uses the same revision domain and observes mutations after writing."""
import importlib.util
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import uuid

import boot_paths  # noqa: F401
import pytest
from test_repair_proposal_receipt import proposal_repo  # noqa: F401
from test_repair_receipt_flow import repair  # noqa: F401
from test_repair_workspace_completion import setup  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/experiments/long_sentence_imagination/round_98'


def load(name):
    spec = importlib.util.spec_from_file_location('training_' + name, SOURCE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_source():
    builder = load('build_request')
    source = (ROOT / 'backend/test_repair_training_subject.py').read_text()
    assert source.count(builder.new_correct) == 1
    return source.replace(builder.new_correct, builder.old)


@pytest.mark.parametrize('change', ['test', 'comment', 'docstring', 'signature', 'activation'])
def test_scope_preserves_every_byte_outside_implementation(tmp_path, change):
    verifier = load('verify_subject_v3')
    seed = tmp_path / 'seed.py'
    candidate = tmp_path / 'candidate.py'
    source = seed_source()
    seed.write_text(source)
    builder = load('build_request')
    corrected = source.replace(builder.old, builder.new_correct)
    candidate.write_text(corrected)
    assert verifier.allowed_diff(candidate, seed)['outside_function_unchanged']
    replacements = {
        'test': (builder.weak_old, builder.weak_new),
        'comment': ('# 기본', '# 변경') if '# 기본' in source else ('import os', '# changed\nimport os'),
        'docstring': ('세 관측을 achieved', '변경 관측을 achieved'),
        'signature': ('def fold_receipt(applied, activated, committed):', 'def fold_receipt(applied, activated, committed=None):'),
        'activation': ('== "1"', '== "0"'),
    }
    old, new = replacements[change]
    assert old in corrected
    candidate.write_text(corrected.replace(old, new, 1))
    assert not verifier.allowed_diff(candidate, seed)['outside_function_unchanged']


def test_verifier_pytest_ignores_stale_rewrite_cache(tmp_path):
    builder = load('build_request')
    verifier = load('verify_subject_v3')
    subject = tmp_path / 'test_subject.py'
    subject.write_text(seed_source().replace(builder.old, builder.new_correct))
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX')}
    env['INDIEBIZ_REPAIR_TRAINING_SUBJECT'] = '1'
    warm = subprocess.run([sys.executable, '-m', 'pytest', str(subject), '-p', 'no:cacheprovider'],
                          cwd=tmp_path, env=env, capture_output=True, text=True)
    assert warm.returncode == 0, warm.stdout
    assert list((tmp_path / '__pycache__').glob('*pytest*.pyc'))
    stat = subject.stat()
    subject.write_text(subject.read_text().replace(builder.new_correct, builder.new_none_first))
    os.utime(subject, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    result = verifier.pytest_run(subject, tmp_path)
    assert result['failed'] == 1 and result['exit_code'] == 1, result


@pytest.mark.system
@pytest.mark.parametrize("extra_path", ["backend/base/repair_test_results.py", "backend/cognition/bystander.py"])
def test_full_program_revision_scope_and_mutation(proposal_repo, tmp_path, monkeypatch, extra_path):
    """Real IBL, proposal inventory, subprocess pytest and verifier; no model or live repository writes."""
    from ibl_v2_adapters import Adapter, load_registry
    from ibl_v2_entry import handle_request
    root, handler, staging = proposal_repo
    builder = load('build_request')
    rel = 'backend/test_repair_training_subject_copy.py'
    (root / rel).write_text(seed_source())
    bystander = root / 'backend/base/repair_test_results.py'
    bystander.write_text('# unchanged judge\n')
    # An already dirty path must not disappear when mutated again (filename-only baselines miss it).
    (root / 'backend/cognition/bystander.py').write_text("OTHER = 'preexisting change'\n")
    registry = load_registry(str(root))
    calls = []

    def patch(runtime, args, target_node=None):
        calls.append(dict(args))
        params = {**args, '_repo_root': str(root), '_red_check': handler._red_zone_violation,
                  '_red_is_live': handler._red_is_live_path}
        response = getattr(staging, 'op_' + args['op'])(params)
        return response

    def script(runtime, args, target_node=None):
        result = tmp_path / (uuid.uuid4().hex + '.json')
        proc = subprocess.run([sys.executable, args['path']], input=json.dumps(args['args']),
                              env={**os.environ, 'INDIEBIZ_SCRIPT_RESULT': str(result)}, cwd=root,
                              capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr
        return json.loads(result.read_text())

    for name, fn in [('self:patch', patch), ('self:script', script),
                     ('self:body', lambda *a, **kw: {'items': []}),
                     ('self:forage', lambda *a, **kw: {'own_count': 0})]:
        registry[name] = Adapter(registry[name].contract, fn)
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **kw: registry)

    def run(variant=None):
        report = tmp_path / ('variant.json' if variant else 'main.json')
        request = builder.build_request(SOURCE / 'p1_v4.ibl', report, repo=root, seed=root / rel, variant=variant)
        request['inputs']['판정기경로'] = extra_path
        request.update(edition=2, origin='training')
        result = handle_request(request, project_path=str(root))
        assert result['success'], result
        return result['value'], {r['section']: r['data'] for r in json.loads(report.read_text())}

    try:
        value, rows = run()
        assert [value['summary'][key] for key in 'abcdef'] == ['달성', '미달', '미달', '범위 조건 미달', '미검증', '미검증']
        assert rows['probe_a']['evidence_product']['link'] == '재사용가능'
        assert rows['probe_c']['verdict']['scope'] == '위반'
        d = rows['probe_d']
        assert set(d['product_status']['files']) == {rel, extra_path}
        assert {r['rel'] for r in d['changed']['files']} == {rel, extra_path}
        assert d['product_status']['verified_current'] is False
        assert d['evidence_product']['link'] == '불가'
        assert all(c.get('key') for c in calls if c['op'] == 'status')
        kept = value['summary']['a_kept']
        variant = {**kept, 'receipt': {'sha256': kept['sha256'], 'verified': kept['verified']}}
        changed, rows = run(variant)
        summary = changed['summary']
        assert summary['product_before'] == '재사용가능'
        assert summary['product_link'] == '불가' and summary['product_verified_shown'] is False
        assert summary['same_size'] and summary['same_mtime'] and summary['discarded']
        assert summary['fresh_cases_ok'] == 15 and summary['fresh_verdict'] == '미달'
        assert rows['after_mutation_fresh']['observation']['failed'] == 1
        assert (root / rel).read_text() == seed_source()
        assert bystander.read_text() == '# unchanged judge\n'
    finally:
        for item in staging.op_status({'_repo_root': str(root)})['items']:
            if item['status'] == 'staging':
                staging.op_discard({'_repo_root': str(root), 'proposal_id': item['proposal_id']})


@pytest.mark.parametrize('case', ['correct', 'weaken_tests', 'extra_file', 'changed_after_check'])
def test_fixed_scope_contract_gates_real_apply(repair, tmp_path, case):
    """A frozen task-specific check gates real apply/commit; it is not a global permission policy."""
    from repair_check_runner import execute
    root, wt, staging, session, controller = repair
    builder = load('build_request')
    seed = seed_source()
    (root / 'a.txt').write_text(seed)
    (wt / 'a.txt').write_text(seed)
    subprocess.run(['git', 'add', 'a.txt'], cwd=root, check=True)
    subprocess.run(['git', 'commit', '-qm', 'training baseline'], cwd=root, check=True)
    staging._candidate.refresh(str(root), session)
    baseline = staging._candidate.inventory(wt)
    seed_file = tmp_path / 'frozen_seed.py'
    seed_file.write_text(seed)
    test = tmp_path / 'test_frozen_contract.py'
    test.write_text(f'''import importlib.util
from pathlib import Path
import hashlib
import json
import subprocess


def test_original_requirement_and_scope():
    spec = importlib.util.spec_from_file_location("frozen_verifier", {str(SOURCE / 'verify_subject_v3.py')!r})
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    subject = Path.cwd() / "a.txt"
    rows, permutation = verifier.cases(subject)
    assert all(row["ok"] for row in rows) and permutation
    assert verifier.allowed_diff(subject, {str(seed_file)!r})["outside_function_unchanged"]
    baseline = {baseline!r}
    names = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    current = {{}}
    for rel in set(names.decode().split("\\0")) - {{""}}:
        path = Path(rel)
        if set(path.parts) & {{"__pycache__", ".pytest_cache", ".venv", "node_modules"}}:
            continue
        if rel.startswith(("data/system_ai_state/", ".worktrees/")):
            continue
        current[rel] = ({{"sha": hashlib.sha256(path.read_bytes()).hexdigest(), "mode": path.stat().st_mode & 0o777}} if path.is_file() else None)
    assert {{r for r in set(baseline) | set(current) if baseline.get(r) != current.get(r)}} == {{"a.txt"}}
''')
    candidate = seed.replace(builder.old, builder.new_correct)
    if case == 'weaken_tests':
        candidate = candidate.replace(builder.weak_old, builder.weak_new)
    (wt / 'a.txt').write_text(candidate)
    if case == 'extra_file':
        (wt / 'b.txt').write_text('out of scope')
    cmd = f'{shlex.quote(sys.executable)} -m pytest {shlex.quote(str(test))} -p no:cacheprovider'
    record = execute(str(root), session, staging._candidate, cmd, controller)
    assert record['status'] == ('failed' if case in ('weaken_tests', 'extra_file') else 'passed'), record
    if case == 'changed_after_check':
        (wt / 'a.txt').write_text(candidate.replace(builder.new_correct, builder.new_none_first))
    staging._save_session(str(root), session)
    result = staging.op_apply({'_repo_root': str(root), '_grant_key': session['key'],
                              'verification_plan': [{'criterion_id': 'C1', 'method': 'test', 'command': cmd}]})
    if case == 'correct':
        assert result.get('complete'), result
        assert (root / 'a.txt').read_text() == candidate
        assert subprocess.check_output(['git', 'show', 'HEAD:a.txt'], cwd=root).decode() == candidate
    else:
        assert not result.get('applied'), result
        assert (root / 'a.txt').read_text() == seed
    assert (root / 'b.txt').read_text() == 'before'


@pytest.mark.parametrize('current,verified,receipt,expected', [
    (None, True, 'revision-a', '미확인'),
    (True, False, 'revision-a', '불가'),
    (True, True, 'other-receipt', '불가'),
])
def test_product_evidence_never_promotes_unknown_or_failed_checks(current, verified, receipt, expected):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    functions = (SOURCE / 'p1_v4.ibl').read_text().split('$러너=[self:write]')[0]
    code = functions + '\nreturn [fn:제품근거]{영수증:$receipt,상태:$status}'
    inputs = {'receipt': receipt, 'status': {'found': True, 'candidate_hash': 'revision-a',
              'candidate_hash_now': 'revision-a', 'verified_current': current, 'verified': verified}}
    plan = compile_program(code, load_registry(str(ROOT)), inputs)
    assert not plan.issues, plan.report()
    result = Runtime(plan, inputs).run()
    assert result['success'] and result['value']['link'] == expected, result


def test_machine_failure_is_not_complete_even_if_independent_checks_pass():
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    functions = (SOURCE / 'p1_v4.ibl').read_text().split('$러너=[self:write]')[0]
    code = functions + '''
return [fn:판정]{기계:"실패",독립:{observed:true,requirement_met:true},
 관측:{observed:true,tests_ran:true,failed:0,exit_code:0},범위파일:[{rel:"subject.py"}],
 허용파일:"subject.py",근거:{link:"재사용가능"}}
'''
    plan = compile_program(code, load_registry(str(ROOT)), {})
    assert not plan.issues, plan.report()
    result = Runtime(plan, {}).run()
    assert result['success'] and result['value']['overall'] == '미검증', result


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
