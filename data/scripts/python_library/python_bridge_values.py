"""Lossless value conversion and explicit, type-specific exports."""
from decimal import Decimal
import math
import sys
import uuid
from common.expression_ir import Fault, UNIT, pack
from common.foreign_ref import ForeignRef
from common.value_semantics import decimal_json_number

MAX_ITEMS = 100000
MAX_BYTES = 8 * 1024 * 1024


def value_copy(value, seen=None, budget=None, depth=0):
    seen = set() if seen is None else seen
    budget = [MAX_ITEMS, MAX_BYTES] if budget is None else budget
    budget[0] -= 1
    budget[1] -= 8
    if depth > 64 or budget[0] < 0 or budget[1] < 0:
        raise ValueError('값 변환 한도 초과')
    from common.value_semantics import native_numeric_scalar
    value = native_numeric_scalar(value)
    typ = type(value)
    if value is None or typ in (bool, int):
        if typ is int:
            budget[1] -= len(str(value))
            if budget[1] < 0:
                raise ValueError('숫자 전송 크기 초과')
        return value
    if typ is str:
        budget[1] -= len(value.encode('utf-8'))
        if budget[1] < 0:
            raise ValueError('문자열 크기 초과')
        return value
    if typ is float and math.isfinite(value):
        return value
    if typ is Decimal and value.is_finite():
        budget[1] -= len(str(value))
        if budget[1] < 0:
            raise ValueError('숫자 전송 크기 초과')
        return value
    if typ not in (list, dict) or id(value) in seen:
        raise ValueError('IBL 값으로 손실 없이 표현할 수 없는 객체')
    seen.add(id(value))
    try:
        if typ is list:
            return [value_copy(v, seen, budget, depth + 1) for v in value]
        if any(type(k) is not str for k in value):
            raise ValueError('레코드 키는 문자열이어야 합니다')
        return {value_copy(k, seen, budget, depth + 1): value_copy(v, seen, budget, depth + 1)
                for k, v in value.items()}
    finally:
        seen.remove(id(value))


class Objects:
    def __init__(self, owner, environment, generation):
        self.owner, self.environment, self.generation = owner, environment, generation
        self.objects, self.released = {}, set()

    def keep(self, value):
        if len(self.objects) >= 4096:
            raise Fault('PY_OBJECT_BUDGET', '실행의 객체 참조 한도 4096개를 넘었습니다.', kind='budget')
        key = uuid.uuid4().hex
        typ = type(value)
        ref = ForeignRef('python', self.owner, self.environment, self.generation, key,
                         f'{typ.__module__}.{typ.__qualname__}')
        self.objects[key] = (ref, value)
        return ref

    def validate(self, ref, released=False):
        if (not isinstance(ref, ForeignRef) or ref.provider != 'python' or ref.owner != self.owner
                or ref.environment != self.environment or ref.generation != self.generation):
            raise Fault('PY_REFERENCE_SCOPE', '위조·타 실행·만료된 객체 참조입니다.', kind='permission')
        stored = self.objects.get(ref.object_id)
        if stored and stored[0] == ref:
            return stored[1]
        if released and ref in self.released:
            return UNIT
        raise Fault('PY_STATE_EXPIRED', '이미 해제했거나 만료된 객체 참조입니다.', kind='protocol')

    def release(self, ref):
        self.validate(ref, released=True)
        self.objects.pop(ref.object_id, None)
        self.released.add(ref)
        return UNIT

    def inputs(self, value):
        if isinstance(value, ForeignRef):
            return self.validate(value)
        if isinstance(value, Decimal):
            try:
                return decimal_json_number(value)
            except ValueError as error:
                raise Fault('PY_INPUT', str(error)) from error
        if isinstance(value, list):
            return [self.inputs(v) for v in value]
        if isinstance(value, dict):
            return {k: self.inputs(v) for k, v in value.items()}
        if value is UNIT:
            raise Fault('PY_INPUT', 'Unit은 Python 인자로 변환할 수 없습니다.')
        return value

    def output(self, value, mode='auto'):
        if mode == 'ref':
            return self.keep(value)
        try:
            return value_copy(value)
        except (ValueError, RecursionError) as exc:
            ref = self.keep(value)
            if mode == 'value':
                raise Fault('PY_VALUE_CONVERSION', str(exc), partial=ref,
                            details={'stage': 'convert', 'result_preserved': True}) from exc
            return ref


def export_value(value, fmt, options):
    if set(options) - ({'path'} if fmt == 'bytes' else set()):
        raise Fault('PY_EXPORT_OPTIONS', '이 export 형식이 지원하지 않는 options입니다.')
    typ = type(value)
    if fmt == 'list' and typ in (tuple, set, list):
        return list(value), {'conversion': {'format': fmt, 'ordering': 'unspecified' if typ is set else 'preserved'}}
    if fmt == 'list' and typ.__module__ == 'numpy' and typ.__name__ == 'ndarray':
        return value.tolist(), {'conversion': {'format': fmt, 'dtype': str(value.dtype), 'shape': list(value.shape)}}
    # pandas 3는 공개 클래스의 __module__을 'pandas'로 노출한다. 내부 경로가
    # 아니라 공개 타입의 신원을 검사하며, 선택 라이브러리를 새로 import하지 않는다.
    pandas = sys.modules.get('pandas')
    if fmt == 'records' and typ is getattr(pandas, 'DataFrame', None):
        if not value.columns.is_unique or any(type(c) is not str for c in value.columns):
            raise Fault('PY_EXPORT_SCHEMA', 'records는 중복 없는 문자열 열 이름이 필요합니다.')
        return {'items': value.to_dict(orient='records'),
                'schema': {'columns': list(value.columns), 'dtypes': [str(d) for d in value.dtypes],
                           'index': 'omitted', 'timezone': 'preserved_in_cells'}}, {'conversion': {'format': fmt, 'index': 'omitted'}}
    if fmt == 'bytes' and typ is bytes:
        if len(value) > MAX_BYTES:
            raise Fault('PY_EXPORT_BUDGET', '바이너리 export는 8MiB 이하입니다.', kind='budget')
        import base64
        return {'base64': base64.b64encode(value).decode('ascii')}, {'conversion': {'format': 'bytes'}}
    raise Fault('PY_EXPORT_TYPE', '지원하지 않는 자료형/format 조합입니다. 객체 메서드로 명시 변환하세요.')
