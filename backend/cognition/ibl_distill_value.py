"""경험 증류의 비용·효용 관문. 기존 한 번의 반성 호출만 사용한다."""
import hashlib
import json

MAX_INPUT_CHARS = 24000


def known_examples(db):
    """임베딩·모델 호출 없이 현재 용례를 읽는다. 조회 실패는 호출측에서 보류한다."""
    with db._get_connection() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT id, intent, ibl_code FROM ibl_examples "
            "WHERE fail_count = 0 OR success_count > 0 ORDER BY id DESC")]


def url_only_head(code):
    """주소만 바뀐 원시 호출. 옵션·합성·질의·instruction의 차이는 지우지 않는다."""
    from ibl_parser import parse
    try:
        steps = parse(code)
        if len(steps) != 1:
            return None
        step = steps[0]
        if set(step) - {'_node', 'action', 'target', 'params', '_assign_name'}:
            return None
        params = step.get('params', {})
        if (set(params) == {'url'} and isinstance(params['url'], str)
                and params['url'].startswith(('https://', 'http://')) and '$' not in params['url']
                and not step.get('target')):
            return step.get('_node'), step.get('action')
    except Exception:
        pass
    return None


def redundant_reason(codes, known):
    """이미 있는 전체 절차와 URL만 교체한 원시 호출은 다시 증류하지 않는다."""
    def function_shape(source):
        from ibl_edition import source_edition
        from ibl_v2_parser import parse
        from ibl_v2_experience import structure
        try:
            if source_edition(source) != 2:
                return None
            body = parse(source).data['statements']
            if len(body) == 1 and body[0].kind == 'def':
                data = {k: v for k, v in body[0].data.items() if k != 'name'}
                return json.dumps(structure(data), ensure_ascii=False, sort_keys=True)
        except Exception:
            return None
    if len(codes) == 1:
        shape = function_shape(codes[0])
        if shape and any(function_shape(row['ibl_code']) == shape for row in known):
            return '이름을 제외한 같은 입력 함수가 이미 있음'
    existing = {r['ibl_code'].strip() for r in known}
    if '\n'.join(codes).strip() in existing:
        return '동일한 실행 절차가 이미 있음'
    # 각각을 안다고 해서 새로운 조합까지 안다고 판정하지 않는다.
    if len(codes) == 1 and codes[0].strip() in existing:
        return '동일한 실행 문장이 이미 있음'
    heads = {url_only_head(code) for code in codes}
    if heads and None not in heads:
        for row in known:
            heads.discard(url_only_head(row['ibl_code']))
            if not heads:
                return '기존 원시 호출의 URL만 바뀜'
    return None


def comparison_examples(codes, known):
    """같은 액션을 쓰는 기존 용례를 작은 비교 자료로 제공한다."""
    from ibl_distill_gates import _actions_of
    heads = set().union(*(_actions_of(code) for code in codes))
    scored = [(len(heads & _actions_of(row['ibl_code'])), row) for row in known]
    rows = [row for score, row in sorted(scored, key=lambda pair: pair[0], reverse=True) if score][:4]
    return [{'id': row['id'], 'intent': row['intent'][:200],
             'code': row['ibl_code'][:1000], 'code_truncated': len(row['ibl_code']) > 1000}
            for row in rows]


def value_reason(reply):
    """0건을 정상 응답으로 둔다. 효용 판단은 기존 반성 모델 한 번이 소유한다."""
    if reply.get('decision') != 'keep':
        return '새로 남길 경험 없음'
    for field in ('benefit', 'applicability'):
        if not isinstance(reply.get(field), str) or not reply[field].strip():
            return f'재사용 판단 근거 없음: {field}'
    if not isinstance(reply.get('source_ids'), list):
        return '실행 원문 번호 없음 — 코드 생성 응답은 저장하지 않음'
    return None


def applicability_note(raw):
    """회상에는 사적 출처 대신 짧은 적용 조건만 싣는다."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        condition = data.get('applicability')
        if isinstance(condition, str):
            return condition[:240] + ('…(조건 발췌)' if len(condition) > 240 else '')
    except (ValueError, TypeError, AttributeError):
        pass
    return ''


def source_rows(calls):
    """원문 문장 번호와 원 호출 번호를 한 번 부여해 증거·선택의 번호를 일치시킨다."""
    from hippo_tree import split_sentences
    rows = []
    for tool_index, tc in calls:
        from ibl_edition import source_edition, explicit_source
        source = explicit_source(tc['input']['code'], tc['input'].get('edition'))
        statements = [source] if source_edition(source) == 2 else split_sentences(source)
        for statement_index, code in enumerate(statements, 1):
            rows.append({'id': len(rows) + 1, 'code': code, 'tool_call_index': tool_index,
                         'statement_index': statement_index, 'edition': source_edition(code),
                         **({'abstraction': tc['_ibl_abstraction']} if tc.get('_ibl_abstraction') else {})})
    return rows


def outcome_evidence(calls, outcome):
    """성공 표식과 내용 검증을 구분한다. 호출당 결과 발췌는 한 번만 제공한다."""
    from cognitive_trace import _result_evidence
    records = []
    for index, tc in calls:
        result = tc.get('result')
        raw = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        excerpt = _result_evidence(raw) if result is not None else ''
        records.append({'tool_call_index': index, 'result_available': result is not None,
                        'excerpt': excerpt[:400], 'excerpt_truncated': len(excerpt) > 400})
    return json.dumps({'goal_evaluation': outcome, 'call_results': records}, ensure_ascii=False)


def provenance(reply, rows, code, outcome, turn_cost):
    from ibl_distill_gates import _close_source_dependencies
    from episode_logger import EpisodeLogger
    from thread_context import get_current_task_id
    selected, error = _close_source_dependencies(reply['source_ids'], [r['code'] for r in rows])
    if error:
        raise ValueError(error)
    episode = EpisodeLogger.current()
    return {'version': 1, 'task_id': get_current_task_id() or getattr(episode, 'task_id', None),
            'episode_id': getattr(episode, 'episode_id', None),
            'events_path': (turn_cost or {}).get('events_path'),
            'goal_evaluation': outcome, 'benefit': reply['benefit'].strip(),
            'applicability': reply['applicability'].strip(),
            'code_sha256': hashlib.sha256(code.encode()).hexdigest(),
            'sources': [{k: row[k] for k in ('id', 'tool_call_index', 'statement_index')} |
                       {'sha256': hashlib.sha256(row['code'].encode()).hexdigest(),
                        **({'abstraction': row['abstraction']} if row.get('abstraction') else {})}
                       for row in rows if row['id'] in selected]}


def note_selected_run(topic, intent, code, component, calls, reply, turn_cost, candidate_key=None):
    """검증·저장된 절차만 가지에 남긴다. 생략한 탐색은 원 실행 원장에서 찾는다."""
    import hippo_tree
    from cognitive_trace import ibl_call_cost
    statements = hippo_tree.split_sentences(code)
    if not topic or len(statements) < 2:
        return
    try:
        cost = ibl_call_cost(calls)
        label = ('부분 절차(전체 목표 성공 아님): ' if component else '') + intent
        hippo_tree.note_run(topic, label, statements, ok=True,
                           calls=cost['calls'], failed=cost['failed'], typed_chars=cost['typed_chars'],
                           missed={k: reply.get(k) or [] for k in ('retyped', 'mergeable')},
                           turn_cost=turn_cost, **({"candidate_key": candidate_key} if candidate_key else {}))
    except Exception as exc:
        if candidate_key:
            raise
        print(f'[경험증류] 선택 절차의 가지 기록 실패: {exc}')
