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
        if key in contract.get('nonempty', []) and (not isinstance(value, (str, list)) or not value):
            errors.append(f'{key}: 빈 값은 허용하지 않습니다')
    return errors


def validate_extensions(contract):
    params = contract['params']
    for alias, key in contract.get('aliases', {}).items():
        if key not in params or alias in params or not isinstance(alias, str):
            raise ValueError('aliases는 별칭→정본 인자 이름입니다')
    for key in ('enums', 'minimum', 'defaults'):
        if not isinstance(contract.get(key, {}), dict) or set(contract.get(key, {})) - params.keys():
            raise ValueError(f'{key}는 선언 인자만 참조합니다')
    for key in ('integers', 'nonempty'):
        if not isinstance(contract.get(key, []), list) or set(contract.get(key, [])) - params.keys():
            raise ValueError(f'{key}는 선언 인자 목록입니다')
    for group in contract.get('required_any', []):
        if not isinstance(group, list) or not group or set(group) - params.keys():
            raise ValueError('required_any는 선언 인자들의 대안 목록입니다')
    for choices in contract.get('enums', {}).values():
        if not isinstance(choices, list) or not choices:
            raise ValueError('enums에는 하나 이상의 허용 값이 필요합니다')
    for variant in contract.get('variants', []):
        if not isinstance(variant.get('when'), dict) or not variant['when'] or set(variant['when']) - params.keys():
            raise ValueError('variants.when은 선언 인자의 리터럴 값입니다')
        if set(variant) - {'when', 'result', 'effects', 'required', 'required_any', 'enums', 'integers', 'minimum', 'nonempty'}:
            raise ValueError('조건부 계약의 변경 가능 필드가 아닙니다')
        from ibl_v2_adapters import validate_contract
        validate_contract({**{k:v for k,v in contract.items() if k!='variants'},
                           **{k:v for k,v in variant.items() if k!='when'}})
