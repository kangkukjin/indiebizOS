"""한 프로그램 격리 실행. 실 파서·fn·each·표/파일 도구, 외부 웹/요약만 fixture.
모델 생성 코드는 허용 잎 도구만 도달한다. 실 DB·스필·쓰기 원장은 임시 공간으로 격리.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import contextlib
import importlib.util
import io
import json
import tempfile
import time
from unittest.mock import patch
from idiom_experiment_cases import setup, judge, decoded

CATALOG = json.loads((ROOT / 'data/idioms/curated.json').read_text())
ENTRIES = {e['name']: e for e in CATALOG['idioms']}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_trial(code, case_id, named=True, catalog=None):
    entries = {e["name"]: e for e in (catalog or CATALOG)["idioms"]}
    import ibl_engine
    import ibl_usage_db
    import workflow_engine
    import ibl_typecheck
    import episode_logger
    import write_ledger
    import oneshot_facade
    from common import spill
    from ibl_parser import parse_with_vars
    from ibl_control_blocks import _execute_fn
    from ibl_executors import _execute_table_each
    from tool_context import ToolContext
    from thread_context import actor_context
    from contextlib import ExitStack

    observed = {'crawl': [], 'brief': 0, 'leaf_calls': [], 'fn_calls': []}
    dataops = load('_experiment_dataops', ROOT / 'data/packages/installed/tools/data-ops/handler.py')
    fs = load('_experiment_fs', ROOT / 'data/packages/installed/tools/system_essentials/handler.py')
    aiops = load('_experiment_aiops', ROOT / 'data/packages/installed/tools/ai-ops/handler.py')
    class DB:
        def find_phrase_by_alias(self, name):
            e = entries.get(name) if named else None
            return {'ibl_code': e['body'], 'alias': name} if e else None
        def update_success_by_code(self, *args, **kw):
            pass
        def phrase_aliases(self, *args):
            return list(entries) if named else []
    with tempfile.TemporaryDirectory(prefix='ibl_idiom_trial_') as tmp, ExitStack() as stack:
        root = Path(tmp).resolve()
        setup(root)
        stack.enter_context(patch.object(ibl_usage_db, 'IBLUsageDB', DB))
        stack.enter_context(patch.object(workflow_engine, 'get_workflow', lambda name: None))
        stack.enter_context(patch.object(ibl_typecheck, 'FN_CODE_SOURCES', [lambda n: entries[n]['body'] if named and n in entries else None]))
        stack.enter_context(patch.object(spill, '_root', lambda: str(root / '_spill')))
        stack.enter_context(patch.object(write_ledger, '_LEDGER_PATH', root / '_writes.jsonl'))
        stack.enter_context(patch.object(episode_logger, 'record_trajectory_event', lambda *a, **k: None))
        stack.enter_context(patch.object(oneshot_facade, 'execution_oneshot', lambda *a, **k: 'SUMMARY: fixture'))
        original = ibl_engine._execute_ibl_impl
        def leaf(ti, project, agent_id=None):
            agent = agent_id
            n, a = ti.get('_node'), ti.get('action')
            p = dict(ti.get('params') or {})
            if p.get('criteria'):
                return {'success': False, 'error': '이 fixture는 AI criteria 판정 대신 결과 오라클을 사용합니다'}
            if n == 'fn':
                observed['fn_calls'].append(a)
                return _execute_fn(ti, project, agent)
            if ti.get('_def') or any(ti.get(k) for k in ['_condition', '_case', '_try', '_repeat', '_var_emit', '_assign', '_parallel', '_fallback']):
                return original(ti, project, agent)
            observed['leaf_calls'].append(f'{n}:{a}')
            if n == 'table' and a == 'each':
                p['_depth'] = ti.get('_depth', 0)
                return _execute_table_each(p, project, agent_id=agent)
            if n == 'table' and 'data_' + str(a) in dataops._DISPATCH:
                return dataops.execute(p, ToolContext(project, 'data_' + a))
            if n == 'sense' and a == 'crawl':
                url = p.get('url', '')
                observed['crawl'].append(url)
                if url == 'https://fixture.test/bad':
                    return {'success': False, 'error': 'fixture source unavailable'}
                if url not in {'https://fixture.test/a', 'https://fixture.test/c', 'https://fixture.test/d'}:
                    return {'success': False, 'error': 'unknown fixture URL'}
                return {'success': True, 'text': 'SOURCE:' + url, 'items': [{'text': 'SOURCE:' + url}]}
            if n == 'table' and a == 'brief':
                observed['brief'] += 1
                return aiops._brief(p)
            mapped = {'read': 'read_op', 'file_find': 'glob_files', 'grep': 'grep_files', 'edit': 'edit_file', 'write': 'write_file'}
            if n == 'self' and a in mapped:
                ctx = ToolContext(project, mapped[a], agent_id='idiom-experiment')
                for key in ('path', 'file_path', 'directory'):
                    if p.get(key):
                        resolved = Path(ctx.resolve_path(str(p[key]))).resolve()
                        if not resolved.is_relative_to(root):
                            return {'success': False, 'error': 'fixture 밖 경로 거절'}
                return fs.execute(p, ctx)
            return {'success': False, 'error': f'fixture에서 허용하지 않는 도구 {n}:{a}'}
        # criteria 래퍼까지 격리해 어떤 생성 코드도 실제 모델을 부르지 않는다.
        stack.enter_context(patch.object(ibl_engine, '_execute_ibl_impl', leaf))
        stack.enter_context(patch.object(ibl_engine, 'execute_ibl', leaf))
        start = time.perf_counter()
        try:
            steps, variables = parse_with_vars(code)
            checked = ibl_typecheck.typecheck(steps, variables)
            if not checked['ok']:
                result = {'success': False, 'error': json.dumps(checked['issues'], ensure_ascii=False)}
            else:
                with actor_context(agent_id='idiom-experiment', origin='test'):
                    result = workflow_engine.execute_pipeline(steps, str(root))
            ok, verdict = judge(case_id, result, root, observed)
        except Exception as exc:
            result = {'success': False, 'error': f'{type(exc).__name__}: {exc}'}
            ok, verdict = False, result['error']
        return {'quality_ok': ok, 'verdict': verdict, 'result': result, 'observed': observed,
                'runtime_ms': round((time.perf_counter() - start) * 1000, 3)}


if __name__ == '__main__':
    req = json.loads(sys.stdin.read())
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_trial(req['code'], req['case_id'], req.get('named', True), req.get('catalog'))
    print(json.dumps(result, ensure_ascii=False))
