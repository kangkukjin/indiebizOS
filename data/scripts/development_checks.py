"""Development script adapters. Evidence production/reuse belongs to repair owners.

plan returns commands to the parent; observe projects supplied owner receipts.
No session files, grant objects or acceptance records are read or written here.
"""
import hashlib
import json
import os
import shlex
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
from logging_utils import mask_secrets
from python_environment_lock import fingerprint as environment_fingerprint
from repair_test_results import invocation, summary


def save_output(root, text):
    text = mask_secrets(text)
    directory = Path(root) / 'data/spill/test_outputs'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (uuid.uuid4().hex + '.log')
    path.write_text(text, encoding='utf-8')
    excerpt = text if len(text) <= 6000 else text[:3000] + '\n… output_path에 전체 보존 …\n' + text[-3000:]
    return {'output': excerpt, 'output_path': str(path), 'truncated': len(text) > 6000}


def identity(root, files):
    hashes = {}
    for name in files:
        path = Path(root) / name.split('::', 1)[0]
        try:
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        except OSError:
            hashes[name] = None
    return {'workspace': str(Path(root).resolve()), 'selected_source_hashes': hashes,
            'environment_hash': environment_fingerprint(Path(root)),
            'scope': 'selected sources and environment; not an official repair candidate'}


def independent_test(root, files, k, timeout):
    cmd = [sys.executable, '-m', 'pytest', '-p', 'no:warnings', '-rf', *files]
    if k:
        cmd += ['-k', k]
    command = shlex.join(cmd)
    spec = invocation(command, root)
    before = identity(root, files)
    env = {**os.environ, **spec['env'], **spec.get('observer_env', {})}
    failure_kind = None
    try:
        result = subprocess.run(spec['argv'], cwd=root, env=env, capture_output=True,
                                text=True, timeout=timeout)
        code, output = result.returncode, result.stdout + '\n' + result.stderr
    except subprocess.TimeoutExpired as exc:
        code, failure_kind = 124, 'timeout'
        output = '\n'.join(v.decode(errors='replace') if isinstance(v, bytes) else v
                           for v in (exc.stdout, exc.stderr, str(exc)) if v)
    except OSError as exc:
        code, failure_kind, output = 126, 'environment', str(exc)
    report = summary(spec, output, code)
    after = identity(root, files)
    if before != after:
        failure_kind = 'candidate_changed'
    scope = report.get('scope') or {}
    counts = {name: len(scope.get(name, [])) for name in ('passed', 'failed', 'skipped', 'not_run')}
    counts.update(errors=int(bool(report.get('error'))), collected=len(scope.get('collected', [])),
                  executed=len(scope.get('passed', [])) + len(scope.get('failed', [])),
                  test_report=report, command=command, evidence_kind='independent_execution',
                  official_receipt=False, before_identity=before, identity=after,
                  failure_kind=failure_kind, scope_observed=scope.get('observed', False))
    # Keep _run's established tuple interface for its consumers.
    return counts, scope.get('failed', []), code, output


def plan(commands):
    return {'items': [{'command': command, 'state': 'not_run'} for command in commands],
            'commands': commands, 'ok': False, 'state': 'planned',
            'official_receipt': False, 'executor': 'parent run_command',
            'message': '명령을 부모 run_command로 실행한 뒤 verification 영수증을 op:observe에 전달하세요. 빌드는 기능 시험 영수증이 아닙니다.'}


def observe(args, commands):
    receipts = args.get('receipts', [])
    current = args.get('current') or {}
    rows = []
    for command in commands:
        matches = [r for r in receipts if r.get('command') == command]
        receipt = matches[-1] if matches else None
        if receipt is None:
            rows.append({'command': command, 'state': 'not_run', 'ok': False})
            continue
        # This is a display comparison, never the owner's reuse/acceptance decision.
        known = bool(current.get('candidate_hash') and current.get('environment_hash'))
        same = (receipt.get('candidate_hash') == receipt.get('before_hash') == current.get('candidate_hash')
                and receipt.get('environment_hash') == current.get('environment_hash')) if known else None
        rows.append({'command': command, 'state': receipt.get('status', 'unknown'),
                     'ok': same is True and receipt.get('status') == 'passed',
                     'matches_supplied_current': same, 'receipt': receipt,
                     'evidence_kind': 'supplied_owner_receipt', 'observed_now': False,
                     'reuse_authority': 'repair_check_runner.check'})
    ok = bool(rows) and all(row['ok'] for row in rows)
    return {'items': rows, 'ok': ok, 'commands': commands,
            'remaining': [row['command'] for row in rows if not row['ok']],
            'history': receipts, 'current_basis': current,
            'message': '전달받은 영수증 관측입니다. 현재 후보·환경 조회와 재사용 판정은 기존 검사 소유자가 합니다. 이 결과는 공식 검사 영수증을 새로 발급하지 않습니다.'}


def mode(args, commands):
    op = args.get('op', 'run')
    if op == 'plan':
        return plan(commands)
    if op == 'observe':
        return observe(args, commands)
    if op != 'run':
        raise ValueError('op는 run, plan, observe 중 하나입니다')
    return None
