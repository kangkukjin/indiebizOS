"""Exact edits against the consciousness input snapshot; no model or tool calls."""
import hashlib


def apply_patch(patch, current):
    if not isinstance(patch, dict) or not current:
        raise ValueError('research_plan_patch와 기존 계획이 필요합니다')
    body = current['body']
    if patch.get('base_sha256') != hashlib.sha256(body.encode()).hexdigest():
        raise ValueError('연구계획 부분 수정의 기반 지문이 다릅니다')
    if not isinstance(patch.get('reason'), str) or not patch['reason'].strip():
        raise ValueError('연구계획 부분 수정의 reason이 필요합니다')
    edits = patch.get('edits')
    if not isinstance(edits, list) or not 1 <= len(edits) <= 32:
        raise ValueError('research_plan_patch.edits는 1~32개 수정 목록이어야 합니다')
    ranges = []
    for edit in edits:
        if not isinstance(edit, dict):
            raise ValueError('계획 수정은 old/new 문자열 객체여야 합니다')
        old, new = edit.get('old'), edit.get('new')
        if not isinstance(old, str) or not old or not isinstance(new, str) or old == new:
            raise ValueError('계획 수정에는 비어 있지 않은 old와 다른 new가 필요합니다')
        start = edit.get('start')
        if start is None:
            if body.count(old) != 1:
                raise ValueError('old가 유일하지 않습니다. Unicode 문자 좌표 start를 지정하세요')
            start = body.index(old)
        if type(start) is not int or start < 0 or body[start:start + len(old)] != old:
            raise ValueError('계획 수정의 좌표와 원문이 일치하지 않습니다')
        ranges.append((start, start + len(old), new))
    ranges.sort()
    if any(a[1] > b[0] for a, b in zip(ranges, ranges[1:])):
        raise ValueError('연구계획 수정 구간이 겹칩니다')
    for start, end, new in reversed(ranges):
        body = body[:start] + new + body[end:]
    if not body.strip() or len(body) > 64000:
        raise ValueError('수정한 연구계획은 비어 있지 않은 64000자 이내 본문이어야 합니다')
    return body


def prepare_patch(framing, topic, project_path, cancelled=lambda: False):
    from research_planning import _root, persist, read_current
    from research_plans import ResearchPlans
    from research_store import ResearchStore
    from research_lifecycle import project_lock
    from episode_logger import record_trajectory_event

    patch = framing['research_plan_patch']
    with project_lock(project_path):
        if cancelled():
            raise ValueError('연구계획 수정 전에 사용자가 취소했습니다')
        store = ResearchStore(project_path)
        if store.uid != topic['project_uid'] or store.epoch != topic['epoch']:
            raise ValueError('계획 수정 중 연구 프로젝트가 변경됐습니다')
        plans = ResearchPlans(store, _root(project_path))
        current = plans.current(topic['thread_id'])
        # A repeated application cannot publish a second revision.
        if current and current.get('patch_id') == patch_id(patch) and current.get('task_id') == topic['run_id']:
            plans.check_source(topic['thread_id'], topic['run_id'], current['revision'],
                               current['path'], current['sha256'])
            return {**current, 'body': read_current(current, project_path)['body']}
        source = read_current(topic['receipt'], project_path)
        body = apply_patch(patch, source)
        plans.check_source(topic['thread_id'], topic['run_id'], topic['revision'],
                           source['path'], source['sha256'])
        receipt = persist(body, '', project_path, source, exact=True,
                          metadata={'patch_id': patch_id(patch), 'task_id': topic['run_id'],
                                    'change_reason': patch['reason'],
                                    'guide_sha256': topic['receipt'].get('guide_sha256')})
        if cancelled():
            raise ValueError('연구계획 게시 전에 사용자가 취소했습니다')
        receipt = plans.bind(topic['thread_id'], topic['run_id'], receipt, topic['revision'],
                             expected_source=(source['path'], source['sha256']))
        record_trajectory_event('research.plan_patched', {
            'revision': receipt['revision'], 'sha256': receipt['sha256'],
            'base_sha256': source['sha256'], 'edit_count': len(patch['edits']), 'model_called': False})
        return receipt


def patch_id(patch):
    import json
    return hashlib.sha256(json.dumps(patch, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
