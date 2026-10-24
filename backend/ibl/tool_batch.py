"""API tool batches: isolated raw outcomes, ordered publication, serial barriers.

Only a declared reentrant read, or a checked program consisting entirely of such
calls, may overlap. Provider mutable buffers are touched only by the consumer.
Native CLI providers own their own scheduling and do not enter this boundary.
"""
import copy
import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from execution_capacity import fanout, scope


_prepared = ContextVar("tool_batch_prepared_plan", default=None)


@dataclass
class Outcome:
    raw: object = None
    error: Exception | None = None
    started: bool = True

    def unwrap(self):
        if self.error:
            raise self.error
        return json.dumps(self.raw, ensure_ascii=False) if not self.started else self.raw

    def stops(self):
        from ibl_result_transport import tool_result_is_error
        content = self.raw.get('content') if isinstance(self.raw, dict) and 'content' in self.raw else self.raw
        return (self.error is not None or not self.started or content is None or isinstance(content, str) and not content.strip()
                or isinstance(content, str) and content.startswith('[[APPROVAL_REQUESTED]]')
                or tool_result_is_error(content))


def prepared_plan(source, inputs, project_path, agent_id):
    saved = _prepared.get()
    if saved is None:
        return None
    key, plan = saved
    if key != (source, inputs, str(project_path), agent_id):
        raise ValueError('병렬 실행 전 검사한 프로그램과 실행 입력이 다릅니다')
    return plan


@contextmanager
def checked_read_program(args, project_path, agent_id):
    """Read-only execution boundary for an isolated coding worker's IBL tools."""
    if set(args) - {'code', 'edition', 'inputs', 'budget', 'value_protocols'} or args.get('edition', 2) != 2:
        raise ValueError('작업 사본에서는 직접 작성한 판본 2 읽기 프로그램만 실행합니다')
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_store import definitions
    from function_library import compile_current
    plan = compile_current(args.get('code', ''), project_path, agent_id, args.get('inputs'))
    if plan.issues or not plan.effects <= {'pure', 'read_external'}:
        raise ValueError('작업 사본의 변경은 격리된 run_command로 실행하세요. IBL은 확인된 읽기만 허용됩니다')
    token = _prepared.set(((args.get('code', ''), args.get('inputs') or {}, str(project_path), agent_id), plan))
    try:
        yield
    finally:
        _prepared.reset(token)


def _eligibility(schema, args, project_path, agent_id):
    contract = schema.get('execution') or {}
    if contract.get('protocol') == 'ibl-program/2':
        # References, dynamic code and recovery first resolve through the normal
        # serial entry. Never guess the effects hidden behind an opaque handle.
        if (set(args) - {'code', 'edition', 'inputs', 'budget', 'value_protocols'}
                or args.get('edition', 2) != 2 or not isinstance(args.get('code'), str)
                or args['code'].startswith('$')):
            return False, None
        from ibl_v2_adapters import load_registry
        from ibl_v2_compile import compile_program
        from ibl_v2_store import definitions
        from function_library import compile_current
        plan = compile_current(args['code'], project_path, agent_id, args.get('inputs'))
        if plan.issues or not plan.effects <= {'pure', 'read_external'}:
            return False, None
        for action in plan.preflight.get('actions', []):
            c = plan.registry[action].contract
            if (c.get('execution', {}).get('concurrency') != 'reentrant'
                    or c.get('adapter', {}).get('stateful') or c.get('code_params')):
                return False, None
        key = (args['code'], args.get('inputs') or {}, str(project_path), agent_id)
        return True, (key, plan)
    return (contract.get('concurrency') == 'reentrant'
            and bool(contract.get('effects'))
            and set(contract['effects']) <= {'pure', 'read_external'}), None


def execute(calls, schemas, invoke, *, project_path='.', agent_id=None, cancel_check=None):
    """Yield (original call, outcome) in source order, with bounded read segments.

Calls contain name/input, and may carry opaque provider ids. Parsing failures
stay serial and fail inside invoke. A failure stops new submissions; all already
started outcomes are published, and unstarted calls receive explicit results.
"""
    schemas = {s['name']: s for s in schemas}
    calls = list(calls)
    stopped = False
    index = 0
    with scope():
        while index < len(calls):
            if stopped or cancel_check and cancel_check():
                yield calls[index], Outcome({'success': False, 'execution_status': 'not_started',
                                            'error': '앞선 도구 실패·승인 대기 또는 취소로 실행하지 않았습니다'}, started=False)
                index += 1
                continue
            group = []
            def potential(call):
                c = schemas.get(call['name'], {}).get('execution', {})
                return c.get('protocol') == 'ibl-program/2' or c.get('concurrency') == 'reentrant'
            stop = min(len(calls), index + 8)
            # A solitary call, or a call adjacent to a known barrier, cannot
            # benefit from classification. Avoid compiling it a second time.
            if index + 1 == len(calls) or not potential(calls[index]) or not potential(calls[index + 1]):
                stop = index + 1
            for offset in range(index, stop):
                call = calls[offset]
                try:
                    eligible, prepared = (_eligibility(schemas.get(call['name'], {}), call['input'], project_path, agent_id)
                                          if stop > index + 1 else (False, None))
                except Exception:
                    eligible, prepared = False, None
                if group and not eligible:
                    break
                group.append((call, prepared))
                if not eligible:
                    break
            outcomes = {}

            def run(i):
                call, prepared = group[i]
                if cancel_check and cancel_check():
                    return Outcome({'success': False, 'execution_status': 'not_started', 'error': '도구 제출 전 취소됨'}, started=False)
                token = _prepared.set(prepared)
                try:
                    return Outcome(copy.deepcopy(invoke(call)))
                except Exception as exc:
                    return Outcome(error=exc)
                finally:
                    _prepared.reset(token)

            def accept(i, future):
                outcomes[i] = future.result()
                return not outcomes[i].stops()

            fanout(len(group), len(group), run, accept, role='api_tools')
            for i, (call, _) in enumerate(group):
                out = outcomes.get(i, Outcome({'success': False, 'execution_status': 'not_started',
                                               'error': '앞선 병렬 가지의 실패로 미실행'}, started=False))
                stopped |= out.stops()
                yield call, out
            index += len(group)
