"""Data-declared argument aliases, conditional contracts and boundary constraints."""
from common.value_semantics import values_equal, compare_order, order_matches
from ibl_v2_ir import Fault

UNRESOLVED = object()


def normalize(contract, args):
    out = dict(args)
    for alias, name in contract.get('aliases', {}).items():
        if alias in out:
            if name in out:
                raise Fault('ARGUMENT_ALIAS', f'{name}와 별칭 {alias}를 함께 지정할 수 없습니다.', kind='compile')
            out[name] = out.pop(alias)
    return out


def pipe_receiver(contract, present):
    """파이프 값이 들어갈 인자. `pipe_input_with:{명시 인자: 받는 자리}` 선언이 있고 그 인자가 명시됐으면
    그 자리가 받는다 — 예: join 은 right 를 명시하면 파이프 값이 left 다($왼쪽 >> [table:join]{right:…})."""
    for given, receiver in contract.get('pipe_input_with', {}).items():
        if given in present and receiver not in present:
            return receiver
    return contract.get('pipe_input')


def selected(contract, values):
    """Unknown selectors retain the conservative base contract."""
    result = dict(contract)
    effective = {**contract.get('defaults', {}), **values}
    for variant in contract.get('variants', []):
        if all(k in effective and effective[k] is not UNRESOLVED and values_equal(effective[k], v)
               for k, v in variant['when'].items()):
            result.update({k: v for k, v in variant.items() if k != 'when'})
    return result


def problems(contract, values):
    errors = []
    for group in contract.get('required_any', []):
        if not any(k in values for k in group):
            errors.append('다음 인자 중 하나가 필요합니다: ' + ', '.join(group))
    for key, companions in contract.get('requires', {}).items():
        if key in values and any(name not in values for name in companions):
            errors.append(f'{key}에는 함께 지정할 인자가 필요합니다: ' + ', '.join(companions))
    for group in contract.get('exclusive', []):
        if sum(key in values for key in group) > 1:
            errors.append('함께 지정할 수 없는 인자입니다: ' + ', '.join(group))
    forbidden = [key for key in contract.get('forbidden', []) if key in values]
    if forbidden:
        # 조건부 계약(param_support 투영)이 이 조합에서 받지 않는 인자 — 조용히 버리지 않는다(77회차 B77-1).
        errors.append('이 조합에서 지원하지 않는 인자: ' + ', '.join(forbidden))
    for key, value in values.items():
        if value is UNRESOLVED:
            continue
        choices = contract.get('enums', {}).get(key)
        if choices is not None and not any(values_equal(value, option) for option in choices):
            errors.append(f'{key}: 허용 값 {choices}')
        if key in contract.get('integers', []) and type(value) is not int:
            errors.append(f'{key}: 정수가 필요합니다')
        if key in contract.get('minimum', {}) and not order_matches(compare_order(value, contract['minimum'][key]), '>='):
            errors.append(f'{key}: 최소 {contract["minimum"][key]}입니다')
        if key in contract.get('maximum', {}) and not order_matches(compare_order(value, contract['maximum'][key]), '<='):
            errors.append(f'{key}: 최대 {contract["maximum"][key]}입니다')
        if key in contract.get('nonempty', []) and (not isinstance(value, (str, list, dict)) or not value):
            errors.append(f'{key}: 빈 값은 허용하지 않습니다')
    return errors


def validate_extensions(contract):
    params = contract['params']
    hint = contract.get('unknown_param_hint')
    if hint is not None and (not isinstance(hint, str) or not hint.strip()):
        raise ValueError('unknown_param_hint는 받지 않는 인자에 대한 안내 문장입니다')
    for alias, key in contract.get('aliases', {}).items():
        if key not in params or alias in params or not isinstance(alias, str):
            raise ValueError('aliases는 별칭→정본 인자 이름입니다')
    with_pipe = contract.get('pipe_input_with', {})
    if not isinstance(with_pipe, dict) or set(with_pipe) - params.keys() or set(with_pipe.values()) - params.keys():
        raise ValueError('pipe_input_with는 명시 인자→파이프가 받을 인자(둘 다 선언 인자)입니다')
    for key in ('enums', 'minimum', 'maximum', 'defaults'):
        if not isinstance(contract.get(key, {}), dict) or set(contract.get(key, {})) - params.keys():
            raise ValueError(f'{key}는 선언 인자만 참조합니다')
    for key in ('integers', 'nonempty', 'forbidden'):
        if not isinstance(contract.get(key, []), list) or set(contract.get(key, [])) - params.keys():
            raise ValueError(f'{key}는 선언 인자 목록입니다')
    for group in contract.get('required_any', []):
        if not isinstance(group, list) or not group or set(group) - params.keys():
            raise ValueError('required_any는 선언 인자들의 대안 목록입니다')
    dependencies = contract.get('requires', {})
    if not isinstance(dependencies, dict) or set(dependencies) - params.keys():
        raise ValueError('requires는 선언 인자→함께 필요한 인자 목록입니다')
    for key, companions in dependencies.items():
        if (not isinstance(companions, list) or not companions or key in companions
                or set(companions) - params.keys()):
            raise ValueError('requires는 자기 자신을 제외한 선언 인자들을 참조합니다')
    for group in contract.get('exclusive', []):
        if (not isinstance(group, list) or len(set(group)) < 2
                or len(set(group)) != len(group) or set(group) - params.keys()):
            raise ValueError('exclusive는 함께 지정할 수 없는 선언 인자들의 목록입니다')
    for choices in contract.get('enums', {}).values():
        if not isinstance(choices, list) or not choices:
            raise ValueError('enums에는 하나 이상의 허용 값이 필요합니다')
    for variant in contract.get('variants', []):
        if not isinstance(variant.get('when'), dict) or not variant['when'] or set(variant['when']) - params.keys():
            raise ValueError('variants.when은 선언 인자의 리터럴 값입니다')
        if set(variant) - {'when', 'result', 'effects', 'required', 'required_any', 'enums', 'integers', 'minimum', 'maximum', 'nonempty', 'forbidden', 'exclusive'}:
            raise ValueError('조건부 계약의 변경 가능 필드가 아닙니다')
        from ibl_v2_adapters import validate_contract
        validate_contract({**{k:v for k,v in contract.items() if k!='variants'},
                           **{k:v for k,v in variant.items() if k!='when'}})


def checked_values(contract, args):
    """Resolve aliases/defaults/variants and validate a complete boundary input."""
    from ibl_v2_types import guard
    if not isinstance(args, dict):
        raise ValueError('입력은 Record입니다.')
    values = {**contract.get('defaults', {}), **normalize(contract, args)}
    effective = selected(contract, values)
    errors = problems(effective, values)
    params = effective['params']
    errors += [f'필수 인자 누락: {k}' for k in effective.get('required', params) if k not in values]
    errors += [f'알 수 없는 인자: {k}' for k in values if k not in params]
    if errors:
        raise ValueError('; '.join(errors))
    for key, value in values.items():
        guard(value, params[key], key)
    return effective, values


def validate_resources(resources, params):
    """Resource declarations: a path parameter, compound external key, or parent scope."""
    if not isinstance(resources, dict):
        raise ValueError('자원 선언은 자원 종류→인자 선언입니다.')
    for realm, item in resources.items():
        if isinstance(item, str):
            names = [item]
        elif isinstance(item, list) and realm != 'file' and item:
            names = item
        elif isinstance(item, dict) and realm == 'file' and set(item) <= {'param', 'fallback', 'parent'}:
            names = [item.get('param')] + ([item['fallback']] if 'fallback' in item else [])
            if 'parent' in item and type(item['parent']) is not bool:
                raise ValueError('자원 parent는 Bool입니다.')
        else:
            raise ValueError('파일 자원은 인자 또는 {param,fallback,parent}, 외부 자원은 인자 또는 인자 목록입니다.')
        if any(not isinstance(n, str) or n not in params for n in names):
            raise ValueError('자원은 선언된 인자를 참조해야 합니다.')


def resource_values(declaration, args, identity=None, *, allow_bare=True):
    """Resolve declared values identically for compiler and journal; missing is unknown."""
    import os
    from ibl_v2_ir import digest
    result = []
    for realm, item in declaration.items():
        if isinstance(item, list):
            values = {k: args[k] for k in item if k in args}
            if not values or any(v is UNRESOLVED for v in values.values()):
                return None
            result.append((realm, digest(values)))
            continue
        key = item if isinstance(item, str) else item['param']
        value = args.get(key)
        if value in (None, '') and isinstance(item, dict):
            value = args.get(item.get('fallback'))
        if not isinstance(value, str) or not value.strip():
            return None
        if realm == 'file' and '/' not in value and not allow_bare:
            return None  # A bare output may be redirected by the output-path policy.
        value = identity(realm, value) if identity else value
        if not isinstance(value, str) or not value:
            return None
        if isinstance(item, dict) and item.get('parent'):
            value = os.path.dirname(value) or '.'
        result.append((realm, value))
    return result


def resource_conflicts(left, right):
    """Named resource overlap shared by static and runtime checks (inodes add at runtime)."""
    return {a for a in left for b in right if a[0] == b[0] and
            (a[1] == b[1] or a[0] == 'file' and
             (a[1].startswith(b[1].rstrip('/') + '/') or b[1].startswith(a[1].rstrip('/') + '/')))}
