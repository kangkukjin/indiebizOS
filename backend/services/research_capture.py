"""도구 결과를 축약 전에 보존한다. 외부 결과의 경로는 프로젝트 내부 파일만 허용한다."""
import json
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from research_store import ResearchStore, json_text
from research_library import ResearchLibrary
from research_context import install_capture

_locks = {}
_guard = threading.Lock()


def library(context):
    store = ResearchStore(context['path'])
    if store.uid != context['project_uid'] or store.epoch != context['epoch']:
        raise ValueError('자료 보존의 프로젝트 신원이 만료됐습니다')
    return ResearchLibrary(store)


def clean_url(value):
    try:
        p = urlsplit(value)
        if p.scheme not in {'http', 'https'}:
            return value
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                 if not re.search(r'token|secret|api.?key|signature|credential', k, re.I)]
        host = p.hostname or ''
        if p.port:
            host += ':' + str(p.port)
        return urlunsplit((p.scheme, host, p.path, urlencode(query), p.fragment))
    except ValueError:
        return ''


def sanitize(value):
    if isinstance(value, dict):
        return {k: ('[인증정보 제외]' if re.fullmatch(r'api_?key|token|access_token|refresh_token|authorization|cookie|headers|secret', str(k), re.I)
                    else sanitize(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str) and value.startswith(('https://', 'http://')):
        return clean_url(value)
    return value


def capture(context, config, params, result, call):
    lib = library(context)
    obj = result
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except (ValueError, TypeError):
            pass
    if isinstance(obj, dict) and (obj.get('success') is False or obj.get('error')):
        with lib.store.connect(True) as db:
            lib.store.event(db, 'capture.failed', {'tool': config.get('tool'), 'error': str(obj.get('error', ''))}, context['thread_id'], context['run_id'])
        return result
    obj = sanitize(obj)
    url = next((params[k] for k in ('url', 'path') if isinstance(params.get(k), str)), '')
    title = str(obj.get('title') or obj.get('name') or config.get('tool') or '조사 결과') if isinstance(obj, dict) else str(config.get('tool') or '조사 결과')
    coverage = 'partial' if isinstance(obj, dict) and (obj.get('truncated') or obj.get('partial')) else config.get('research_coverage', 'unknown')
    source = clean_url(url) if url else ''
    ctx = dict(thread=context['thread_id'], run=context['run_id'], call=call)
    paragraphs = None
    body = None
    if isinstance(obj, dict):
        from notebook_store import _paragraphs_with_loc
        body = next((obj[k] for k in ('content', 'text', 'body', 'markdown') if isinstance(obj.get(k), str) and obj[k]), None)
        if body:
            paragraphs = _paragraphs_with_loc(body)
    stable = {k: v for k, v in obj.items() if k not in {'cache', '_display', 'source_ref', '_preview'}} if isinstance(obj, dict) else obj
    receipt = lib.capture(body if body is not None else json_text(stable), acquired_result=obj, paragraphs=paragraphs,
                          title=title, origin=source, kind='tool:' + str(config.get('tool') or config.get('func') or '') + ':' + str(params.get('op') or ''),
                          mime='text/plain' if body is not None else 'application/json', coverage=coverage, **ctx)
    receipts = [receipt]
    # 호출자가 명시한 읽기 파일 또는 프로젝트 안의 실제 다운로드 파일만 스냅샷한다.
    paths = []
    if url and not url.startswith(('http://', 'https://')):
        p = Path(url).expanduser()
        paths.append(p if p.is_absolute() else lib.store.path / p)
    def artifacts(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'path', 'file_path', 'download_path', 'saved_path'} and isinstance(item, str):
                    p = Path(item).expanduser()
                    if p.is_absolute() and p.resolve().is_relative_to(lib.store.path):
                        paths.append(p)
                elif isinstance(item, (dict, list)):
                    artifacts(item)
        elif isinstance(value, list):
            for item in value:
                artifacts(item)
    artifacts(obj)
    if isinstance(obj, dict):
        from common.spill import spill_dir
        for refkey in ('source_ref', 'ref'):
            ref = obj.get(refkey)
            if isinstance(ref, dict) and isinstance(ref.get('path'), str):
                p = Path(ref['path']).resolve()
                if p.is_relative_to(Path(spill_dir()).resolve()):
                    paths.append(p)
    for index, path in enumerate(dict.fromkeys(paths)):
        if path.is_file() and not path.resolve().is_relative_to(lib.store.root):
            receipts.append(lib.add_file(path, item='file:' + str(index), **ctx))
    schedule_index(lib.store.path)
    if isinstance(obj, dict):
        obj['research_materials'] = receipts
        return json_text(obj) if isinstance(result, str) else obj
    # 원래 목록/스칼라의 계약은 바꾸지 않는다. 원장은 모든 영구 참조를 보존한다.
    return result


def schedule_index(path):
    key = str(Path(path).resolve())
    with _guard:
        lock = _locks.setdefault(key, threading.Lock())
    if not lock.acquire(False):
        return
    def work():
        try:
            from research_lifecycle import project_lock
            with project_lock(key):
                lib = ResearchLibrary(ResearchStore(key))
                lib.prepare_index()
            while True:
                with lib.store.connect() as db:
                    pending = db.execute("SELECT COUNT(*) FROM research_jobs WHERE state='pending'").fetchone()[0]
                if not pending:
                    break
                with project_lock(key):
                    with lib.store.connect() as db:
                        lib.store.check_epoch(db)
                    lib.index_pending()
        except Exception:
            import logging
            logging.getLogger(__name__).exception('연구 자료 색인 작업 실패')
        finally:
            lock.release()
    from execution_workers import create_executor
    # 작업 풀은 공용 런타임 수명으로 관리된다.
    _executor().submit(work)


_pool = None


def _executor():
    global _pool
    with _guard:
        if _pool is None:
            from execution_workers import create_executor
            _pool = create_executor('research-index', max_workers=2)
        return _pool


install_capture(capture)
