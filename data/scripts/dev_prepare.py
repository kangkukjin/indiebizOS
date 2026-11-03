#!/usr/bin/env python3
"""개발준비: 현재 작업 사본의 신원·소유자·영향·검사 선택 근거를 읽는다.

files는 저장소 상대 경로. previous는 앞 호출의 identity로만 비교한다.
정적 분석은 영향의 하한이며 권한·검사 통과·활성화를 부여하지 않는다.
"""
import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
from program_boundary import canonical, describe
from program_dependencies import analyse


def fingerprint(path):
    try:
        return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'state': 'read'}
    except OSError as exc:
        return {'sha256': None, 'state': 'unread', 'error': str(exc)}


def git_value(root, *args):
    try:
        out = subprocess.run(['git', *args], cwd=root, capture_output=True,
                             text=True, timeout=20)
        return {'value': out.stdout.strip() if out.returncode == 0 else None,
                'error': out.stderr.strip() if out.returncode else None}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'value': None, 'error': str(exc)}


def select_tests(root, files):
    spec = importlib.util.spec_from_file_location('development_test_selector', root / 'scripts/select_tests.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.select(files, root=root)
    paths = result.pop('paths')
    result['pytest_args'] = ['backend/'] if result['full'] else [
        paths[name].relative_to(root).as_posix() for name in result['selected']]
    result['owner'] = 'scripts/select_tests.py'
    return result


def prepare(args, root=ROOT):
    root = Path(root).resolve()
    files = args.get('files')
    if not isinstance(files, list) or not files or any(canonical(p) is None for p in files):
        raise ValueError('files에 저장소 상대 파일 경로 목록을 명시하세요')
    files = list(dict.fromkeys(files))
    if any(not (root / p).resolve().is_relative_to(root) for p in files):
        raise ValueError('대상 링크가 현재 작업 사본 밖입니다')
    unknown, items = [], []
    before = {p: fingerprint(root / p) for p in files}
    for name in files:
        row = {'path': name, **before[name], 'owner': describe(name), 'symbols': []}
        if before[name]['state'] != 'read':
            unknown.append({'path': name, 'reason': before[name]['error']})
        elif name.endswith('.py'):
            try:
                tree = ast.parse((root / name).read_text(encoding='utf-8'))
                row['symbols'] = [{'name': n.name, 'line': n.lineno, 'end_line': n.end_lineno}
                                  for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            except (OSError, ValueError, SyntaxError) as exc:
                unknown.append({'path': name, 'reason': str(exc)})
        items.append(row)
    analyses = {}
    for name, fn in [('dependencies', analyse), ('tests', select_tests)]:
        try:
            analyses[name] = fn(root, files)
        except (OSError, ValueError, SyntaxError, subprocess.SubprocessError) as exc:
            analyses[name] = None
            unknown.append({'owner': name, 'reason': str(exc)})
    deps = analyses.get('dependencies') or {}
    # The existing inventory does not scan registered scripts. Never claim full closure.
    if any(p.startswith('data/scripts/') for p in files):
        unknown.append({'owner': 'program_dependencies', 'reason': '등록 스크립트 본문은 기존 재고의 SOURCE_ROOTS 밖입니다. 지역 import·등록 소비자를 별도 확인하세요.'})
    unknown.extend({'path': p, 'reason': why} for p, why in deps.get('unresolved', {}).items())
    sources = ['backend/base/program_boundary.py', 'backend/base/program_dependencies.py',
               'scripts/select_tests.py', 'AGENTS.md', 'docs/REGRESSION_TESTING.md']
    refs = [{'path': p, **fingerprint(root / p), 'body_read': p in sources[:3]} for p in sources]
    builds = []
    if any(p.startswith('backend/') for p in files):
        builds.append({'command': 'python3 scripts/build_body_bundle.py android', 'basis': 'AGENTS.md §2'})
    if any(p.startswith('data/ibl_nodes_src/') or p.endswith('/ibl_actions.yaml') for p in files):
        builds.extend({'command': command, 'basis': 'AGENTS.md §2'} for command in
                      ['python3 scripts/build_ibl_nodes.py', 'python3 scripts/build_ibl_nodes.py --check'])
    if any(p.startswith('frontend/') for p in files):
        builds.append({'command': 'cd frontend && npx tsc -p tsconfig.app.json', 'basis': 'AGENTS.md §3'})
    after = {p: fingerprint(root / p) for p in files}
    identity = {'workspace': str(root), 'head': git_value(root, 'rev-parse', 'HEAD'),
                'git_common_dir': git_value(root, 'rev-parse', '--path-format=absolute', '--git-common-dir'),
                'files': after, 'observed_at': datetime.now(timezone.utc).isoformat()}
    previous = args.get('previous')
    drift = None if previous is None else {
        'workspace_changed': previous.get('workspace') != identity['workspace'],
        'head_changed': previous.get('head') != identity['head'],
        'files_changed': sorted(p for p in set(previous.get('files', {})) | set(after)
                                if previous.get('files', {}).get(p) != after.get(p))}
    changed = sorted(p for p in files if before[p] != after[p])
    if changed:
        unknown.append({'reason': '조회 중 대상 변경', 'files': changed})
    return {'items': items, 'identity': identity, **analyses, 'required_builds': builds,
            'references': refs, 'unknown': unknown, 'previous_comparison': drift,
            'stable': not changed, 'source_complete': not unknown,
            'message': '읽기 관측입니다. 정적 분석은 영향의 하한이며 검사 선택은 수정 후 다시 확인합니다.'}


def main():
    try:
        result = prepare(json.load(sys.stdin))
    except (ValueError, TypeError) as exc:
        result = {'success': False, 'error': str(exc), 'items': []}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
