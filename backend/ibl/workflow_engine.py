"""Stored function management and current-edition execution.

Historical source is readable through workflow_store. Parsed edition-1 steps
have no interpreter; the old entry point is a diagnostic-only tombstone.
"""
from workflow_store import list_workflows, get_workflow, _resolve_workflow_id
from ibl_edition import retired_result


def execute_pipeline(steps, project_path='.', context=None, agent_id=None):
    """Retired Python entry point; never interprets steps or invokes a tool."""
    return retired_result()


def preflight_sentence(code, inputs=None):
    from ibl_v2_entry import handle_request
    report = handle_request({'code': code, 'inputs': inputs, 'check': True})
    return {'runnable': bool(report.get('ok')), 'dead_vocab': [],
            'problem': None if report.get('ok') else str(report.get('issues') or report.get('error'))}


def execute_workflow(workflow_id, project_path='.', params=None, stack=None,
                     definition=None, function_refs=None):
    wf = definition if definition is not None else get_workflow(workflow_id)
    if not wf:
        return {'success': False, 'error': f'워크플로우를 찾을 수 없습니다: {workflow_id}'}
    if wf.get('edition', 1) != 2:
        return retired_result()
    if wf.get('state') not in (None, 'active'):
        return {'success': False, 'executed': False, 'error': '관용구가 활성 상태가 아닙니다.', 'state': wf['state']}
    from ibl_v2_store import action
    return action('run', {'workflow_id': workflow_id, 'params': params,
                         'function_refs': function_refs}, project_path)


def execute_workflow_action(action, params, project_path):
    if action == 'workflow':
        action = (params.get('op') or '').strip()
    action = {'list_workflows': 'list', 'get_workflow': 'detail', 'get': 'detail',
              'save_workflow': 'save', 'delete_workflow': 'delete'}.get(action, action)
    workflow_id = params.get('workflow_id') or _resolve_workflow_id(params.get('name') or params.get('id') or '')
    if action == 'list':
        rows = list_workflows()
        return {'items': rows, 'workflows': rows, 'count': len(rows)}
    if action == 'detail':
        return get_workflow(workflow_id) or {'success': False, 'error': '워크플로우를 찾을 수 없습니다.'}
    if action == 'delete':
        from workflow_store import delete_workflow
        try:
            return {'success': delete_workflow(workflow_id), 'workflow_id': workflow_id}
        except (ValueError, OSError) as exc:
            return {'success': False, 'error': str(exc),
                    **({'broken_callers': exc.broken_callers} if hasattr(exc, 'broken_callers') else {})}
    if action == 'save':
        if params.get('edition') == 1 or not isinstance(params.get('code'), str):
            return retired_result()
        from ibl_v2_store import action as current_action
        return current_action('save', params, project_path)
    if action in ('run', 'run_pipeline'):
        if workflow_id and action == 'run':
            return execute_workflow(workflow_id, project_path, params.get('params'),
                                    function_refs=params.get('function_refs'))
        from ibl_v2_entry import handle_request
        source = params.get('code') or params.get('pipeline') or params.get('steps')
        if not isinstance(source, str):
            return retired_result()
        return handle_request({'code': source, 'edition': params.get('edition'),
                               'inputs': params.get('inputs'),
                               'function_refs': params.get('function_refs')}, project_path)
    return {'success': False, 'error': 'op는 list|detail|save|delete|run 중 하나입니다.'}
