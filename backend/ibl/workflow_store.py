"""
workflow_store.py - 통합 관용구 원장의 워크플로 호환 관리 표면

2026-09-05 workflow_engine 에서 분리(1500줄 규칙 — 연쇄 실패 뿌리 진단이 더해져 넘쳤다).
저장소는 실행기가 아니다: 여기엔 파이프 실행 코드가 없고, 실행기(workflow_engine)가
이 모듈을 재수출하므로 기존 `from workflow_engine import list_workflows` 경로는 그대로다.
실행기 쪽 의존(preflight_sentence)은 함수 안에서 늦게 가져온다(순환 import 회피).
"""
import os
import re
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional


def _get_workflows_path() -> Path:
    """워크플로우 저장 디렉토리"""
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        base = Path(env_path)
    else:
        base = Path(__file__).parent.parent.parent
    wf_path = base / "data" / "workflows"
    wf_path.mkdir(parents=True, exist_ok=True)
    return wf_path


@contextmanager
def workflow_transaction():
    """All public writers share the catalog's reentrant lock."""
    import function_store
    with function_store.transaction():
        yield


def serialized_mutation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with workflow_transaction():
            return function(*args, **kwargs)
    return wrapped


def _as_workflow(row):
    data = dict(row.get('legacy') or {})
    data.update({k: row[k] for k in ('name', 'edition', 'function_id', 'revision', 'description') if k in row})
    data['id'] = next(iter(row.get('legacy_ids') or []), row['function_id'])
    data['state'] = row.get('state')
    data['runnable'] = row.get('state') == 'active' and not row.get('problem')
    if row.get('problem'):
        data['problem'] = row['problem']
    data['code'] = row.get('source', '')
    from ibl_v2_parser import parse
    try:
        node = parse(data['code']).data['statements'][0]
        data['params_required'] = [k for k, v in node.data['params'].items() if v is None]
    except Exception as exc:
        data.update(runnable=False, problem=str(exc))
    return data


def list_workflows(*, history=False) -> List[Dict]:
    import function_store
    if history:
        return [{**r, 'runnable': False} for r in function_store.history_snapshot()['records'].values()]
    return [_as_workflow(r) for r in function_store.snapshot()['records'].values()]


def _resolve_workflow_id(name: str) -> str:
    """name(또는 id)을 저장된 워크플로우 id로 해소. 코퍼스/사용자가 이름으로 호출해도
    run/get/delete가 동작하도록 — id 정확일치 → 이름 일치 → slugify 순. 못 찾으면 입력 그대로."""
    name = str(name).strip()
    if not name:
        return ""
    wfs = list_workflows()
    ids = {w["id"] for w in wfs}
    if name in ids:
        return name
    for w in wfs:
        if w.get("name") == name:
            return w["id"]
    slug = _slugify(name)
    if slug in ids:
        return slug
    return name


def _workflow_path(workflow_id: str) -> Path:
    """원장의 id는 단일 파일 이름이며 외부 경로나 심볼릭 링크가 아니다."""
    if (not isinstance(workflow_id, str) or not workflow_id.strip()
            or workflow_id in (".", "..")
            or any(c in workflow_id for c in ("/", "\\", "\0"))):
        raise ValueError("workflow_id는 경로가 아닌 파일 이름이어야 합니다")
    path = _get_workflows_path() / f"{workflow_id}.yaml"
    if path.is_symlink():
        raise ValueError("워크플로 파일은 심볼릭 링크일 수 없습니다")
    return path


def get_workflow(workflow_id: str, *, history=False) -> Optional[Dict]:
    import function_store
    try:
        _workflow_path(workflow_id)
        if history:
            return next((r for r in list_workflows(history=True) if workflow_id in (r['function_id'], r['name'], *r.get('legacy_ids', []))), None)
        row = function_store.resolve(workflow_id, include_inactive=True)
        if row is None:
            row = function_store.resolve(function_id=workflow_id, include_inactive=True)
        return _as_workflow(row) if row else None
    except (ValueError, OSError) as exc:
        return {'id': workflow_id, 'runnable': False, 'problem': str(exc)}


@serialized_mutation
def save_workflow(workflow: dict) -> str:
    import function_store
    wf_id = workflow.get('id') or _slugify(workflow.get('name', 'workflow'))
    _workflow_path(wf_id)  # Retain identifier validation for legacy callers.
    old = get_workflow(wf_id)
    from ibl_edition import require_current
    edition = require_current(workflow.get('code'), workflow.get('edition'))
    source = workflow['code']
    function_store.register_memory(workflow.get('name') or wf_id, source, workflow.get('description', ''),
        edition=edition, workflow_id=wf_id,
        function_id=(old or {}).get('function_id'),
        expected_revision=workflow.get('expected_revision', (old or {}).get('revision')),
        state=workflow.get('state'), reason=workflow.get('reason', ''),
        request_id=workflow.get('request_id'), request_payload=workflow)
    return wf_id


@serialized_mutation
def delete_workflow(workflow_id: str) -> bool:
    from function_library import retire
    return retire(workflow_id)


# === 유틸리티 ===

def _slugify(text: str) -> str:
    """텍스트를 파일명에 적합한 slug로 변환"""
    # 한글은 유지, 특수문자 제거
    slug = re.sub(r'[^\w가-힣\s-]', '', text)
    slug = re.sub(r'[\s]+', '_', slug).strip('_')
    return slug or "workflow"
