"""Opaque, execution-scoped foreign values. Providers validate every dereference."""
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class ForeignRef:
    provider: str
    owner: str
    environment: str
    generation: str
    object_id: str
    type_name: str

    def fields(self):
        return asdict(self)

    def view(self):
        return {"$ibl": "foreign_ref", "provider": self.provider, "type": self.type_name,
                "environment": self.environment, "lifetime": "execution_only",
                "hint": "최상위 실행 종료 후 만료됩니다. 실행 안에서 값/파일로 export하세요."}


def contains_foreign(value):
    if isinstance(value, ForeignRef):
        return True
    if isinstance(value, dict):
        return any(contains_foreign(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_foreign(v) for v in value)
    from common.expression_ir import ResultValue
    if isinstance(value, ResultValue):
        return contains_foreign(value.value) or contains_foreign(value.error)
    return False


def wire_protocol(value):
    return 'ibl-value/2' if contains_foreign(value) else 'ibl-value/1'
