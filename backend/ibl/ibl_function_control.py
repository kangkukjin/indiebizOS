"""Next-call pure function body edits, using the existing compiler and runtime.

This is an invocation override, not a function-store revision or stack mutation.
Only statically named, pure, unannotated functions are exposed. Replacement code
can use the existing value language and parameters, but cannot capture callables,
call tools, introduce definitions, or change completion/permission contracts.
"""
from ibl_v2_ir import Fault, Node, digest


def function_spec(plan, node):
    from ibl_v2_adapters import Adapter
    if node.kind != 'call' or node.data.get('node') != 'fn':
        return None
    symbol = node.data.get('symbol')
    definition = plan.functions.get(symbol)
    summary = plan.function_contracts.get(symbol, {})
    if (definition is None or summary.get('effects') != ['pure']
            or definition.data.get('annotations') or definition.data.get('contract')
            or node.data.get('target')
            or summary.get('result_contract', {}).get('type') in {'Union', 'Callable', 'ForeignRef'}):
        return None
    return Adapter({'version': 1, 'params': {k: 'Unknown' for k in definition.data['params']},
                    'result': summary['result_contract']['type'], 'effects': ['pure'],
                    'implementation_fingerprint': summary['source_hash'],
                    'result_contract': summary['result_contract']}, None)


def replacement_plan(source, contract):
    from ibl_v2_compile import compile_program
    from ibl_v2_repair_graph import walk
    from ibl_v2_types import UNKNOWN
    if not isinstance(source, str) or not source.strip() or len(source) > 65536:
        raise ValueError('함수 본문은 1~65536자의 IBL 코드여야 합니다')
    try:
        plan = compile_program(source, {}, definitions={},
                               input_types={k: UNKNOWN for k in contract['params']})
    except Fault as exc:
        raise ValueError('교체 본문을 컴파일할 수 없습니다: ' + str(exc)) from exc
    # Returning closures would move replacement IR into the caller's definition
    # namespace. Keep the first contract to values, without hidden code capture.
    forbidden = {'call', 'named_call', 'lambda', 'def', 'callable_ref'}
    if (plan.issues or plan.effects - {'pure'}
            or any(n.kind in forbidden for n in walk([plan.root, plan.functions]))):
        raise ValueError('교체 본문은 인자만 사용하는 순수 값 계산이어야 합니다 (외부 호출·정의·람다 불가)')
    return plan


def prepare(runtime, node, definition, local):
    from common.expression_eval import Binding
    from ibl_run_control import boundary, bind_invocation
    original = lambda: runtime.frame(definition.data['body'], local)
    if (runtime.journal is None
            or node.id not in getattr(runtime.journal, 'control', {}).get('targets', {})):
        return original
    spec = function_spec(runtime.plan, node)
    if spec is None:
        return original
    args = boundary(runtime, node, Binding.record(local), spec)
    source = getattr(runtime.local, 'control_definition', None)
    _, _, call_id = runtime.call_coordinate(node, advance=True)
    bind_invocation(runtime, node, call_id)
    if source is None:
        return original
    return lambda: evaluate(runtime, node, source, spec.contract, args)


def evaluate(runtime, node, source, contract, args):
    from ibl_v2_runtime import Runtime, span
    from ibl_v2_types import guard
    plan = replacement_plan(source, contract)
    child = Runtime(plan, budget=runtime.budget, cancel_check=runtime.cancel_check,
                    value_protocols=runtime.value_protocols)
    # A frame of the same value evaluator, not a second run/task/effect owner.
    # Shared budget, cancellation, trace and input bindings preserve the original
    # operation's resource limit and field evidence. Namespace only trace nodes.
    child.local, child.lock = runtime.local, runtime.lock
    child.trace, child.source_map = runtime.trace, runtime.source_map
    child.evidence = runtime.evidence
    revision = digest(source)

    def event(current, kind, parents=(), **extra):
        namespace = 'steer-' + revision + '-' + node.id.replace(':', '_') + '-'
        mapped = Node(namespace + current.kind, current.start, current.end, {})
        with runtime.lock:
            runtime.source_map.setdefault(mapped.id, {**span(source, current), 'definition_revision': revision,
                                                     'controlled_call': node.id})
        return runtime.event(mapped, kind, parents, **extra)

    child.event = event
    previous = getattr(child.local, 'pure_required', False)
    child.local.pure_required = True
    try:
        result = child.frame(child.plan.root, {k: args.select(k) for k in args.value})
        guard(result.value, contract['result'], 'steered function result')
        runtime.check_cancelled(force=True)
        return result.controlled(args.control)
    except Fault as exc:
        # Preserve the replacement's source coordinate in the parent trace.
        eid = event(exc.node or child.plan.root, 'steer_definition_failure', exc.evidence,
                    code=exc.code, controlled_call=node.id)
        exc.evidence = [eid]
        raise
    finally:
        child.local.pure_required = previous
        child.resources.close()
