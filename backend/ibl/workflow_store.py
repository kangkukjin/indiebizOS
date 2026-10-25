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
    data['runnable'] = row.get('edition') == 2 and row.get('state') == 'active' and not row.get('problem')
    if row.get('edition') == 1:
        data['problem'] = 'EDITION_RETIRED: 판본 1 기록은 열람만 가능합니다.'
    if row.get('problem'):
        data['problem'] = row['problem']
    if row.get('edition') == 2:
        data['code'] = row.get('source', '')
        from ibl_v2_parser import parse
        try:
            node = parse(data['code']).data['statements'][0]
            data['params_required'] = [k for k, v in node.data['params'].items() if v is None]
        except Exception as exc:
            data.update(runnable=False, problem=str(exc))
    elif 'legacy' not in row:
        data['do'] = row.get('source', '')
    return data


def list_workflows() -> List[Dict]:
    import function_store
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


def get_workflow(workflow_id: str) -> Optional[Dict]:
    import function_store
    try:
        _workflow_path(workflow_id)
        row = function_store.resolve(workflow_id, include_inactive=True)
        if row is None:
            row = function_store.resolve(function_id=workflow_id, include_inactive=True)
        return _as_workflow(row) if row else None
    except (ValueError, OSError) as exc:
        return {'id': workflow_id, 'runnable': False, 'problem': str(exc)}


# === 등록 시점 문법 관문 (2026-08-17) ===
# save 가 do 를 검증 없이 저장해 "저장은 됐는데 돌리면 깨지는" 지연 실패를 냈다
# (실측: 따옴표가 잘린 do — `[self:read]{path: "` — 가 success:true 로 저장되고
# run 에서야 엉뚱하게 실행됐다). [self:script]{op:"register"} 의 pre-flight 선례를
# 문장에 적용한다: 등록=문법 관문, 실행 가능성은 런타임 몫이라 파싱만 하고 실행 안 함.
#
# ★파서만으로는 못 잡는다(실측): 파서는 닫히지 않은 따옴표·중괄호를 관대하게 흡수해
#   위 잘린 문장을 query:"" 로 통과시킨다(_extract_bracket 의 "닫는 bracket 못 찾으면
#   원본 반환"). 그 관대함은 실행 경로의 기존 계약이라 건드리지 않고, 등록 관문에서만
#   균형을 따로 본다.

_SENTENCE_KEYS = ("steps", "pipeline", "do")


def _unclosed_reason(code: str) -> Optional[str]:
    """따옴표·중괄호 균형 검사. 반환: 오류 사유|None.

    문자열 상태를 줄 경계 너머로 승계하는 파서의 스캐너를 그대로 쓴다
    (주석 줄을 스캔에서 빼는 규칙도 _preprocess 와 동일 — 주석 속 따옴표가
    상태를 오염시키지 않게)."""
    from ibl_parser import _scan_line_state
    depth, in_string, string_char = 0, False, None
    for line in str(code).split('\n'):
        stripped = line.strip()
        if not in_string and (not stripped or stripped.startswith('#')):
            continue
        d, in_string, string_char = _scan_line_state(stripped, in_string, string_char)
        depth += d
    if in_string:
        return f"따옴표({string_char})가 닫히지 않았습니다"
    if depth > 0:
        return "중괄호 {가 닫히지 않았습니다"
    if depth < 0:
        return "여는 중괄호 없이 }가 있습니다"
    return None


def _validate_sentence(raw) -> Optional[str]:
    """저장 전 do(문장 또는 문장 배열) 문법 검사. 반환: 오류문|None.

    미할당 $변수는 합법(호출자 params 주입 자리)이라 파서가 리터럴로 통과시킨다.
    이미 파싱된 dict step 은 파서를 지나온 값이므로 통과."""
    from ibl_parser import parse as ibl_parse, IBLSyntaxError
    sentences = raw if isinstance(raw, list) else [raw]
    if not sentences:
        return "do 가 비어 있습니다 — 저장할 IBL 문장이 필요합니다."
    for one in sentences:
        if isinstance(one, dict):
            continue
        if not isinstance(one, str) or not one.strip():
            return "do 에 빈 문장이 있습니다 — 저장할 IBL 문장이 필요합니다."
        reason = _unclosed_reason(one)
        if reason:
            return f"do 문법 오류 — {reason}: {one[:120]}"
        try:
            ibl_parse(one)
        except IBLSyntaxError as e:
            return f"do 문법 오류 — {e}"
    return None


@serialized_mutation
def save_workflow(workflow: dict) -> str:
    import function_store
    wf_id = workflow.get('id') or _slugify(workflow.get('name', 'workflow'))
    _workflow_path(wf_id)  # Retain identifier validation for legacy callers.
    old = get_workflow(wf_id)
    from ibl_edition import require_current
    edition = require_current(workflow.get('code'), workflow.get('edition'))
    if old and old.get('edition', 1) != edition:
        raise ValueError('다른 언어 판본은 새 ID로 저장하세요.')
    source = workflow.get('code', '') if edition == 2 else ''
    legacy = None if edition == 2 else {k: v for k, v in workflow.items() if k != 'id'}
    function_store.register_memory(workflow.get('name') or wf_id, source, workflow.get('description', ''),
        edition=edition, legacy=legacy, workflow_id=wf_id,
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
