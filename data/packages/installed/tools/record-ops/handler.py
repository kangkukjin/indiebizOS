"""관리 기록: 인증된 주체로 선언된 업무 명령만 실행한다."""
from common.record_contract import RecordError
from record_policy import from_principal
from record_facade import execute as record_execute


def _call(args):
    try:
        return record_execute(args, from_principal())
    except RecordError as exc:
        return exc.result()


_OP_DISPATCHERS = {'record_op': {'describe': _call, 'query': _call, 'detail': _call,
                                'apply': _call, 'history': _call, 'inbox': _call, 'receipt': _call}}
_OP_DEFAULTS = {'record_op': 'describe'}


def execute(tool_input, context):
    # IBL 실행기가 넣는 내부 전달 값은 업무 입력 계약 밖이다.
    args = {k: v for k, v in tool_input.items() if not k.startswith('_')}
    args.setdefault('op', 'describe')
    fn = _OP_DISPATCHERS['record_op'].get(args['op'])
    if fn is None:
        return {'success': False, 'error': '지원 op: describe/query/detail/apply/history/inbox/receipt'}
    return fn(args)
