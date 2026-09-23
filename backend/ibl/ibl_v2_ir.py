"""Edition 2 core values, source locations and lossless boundary protocol.

Business records never double as execution envelopes. The codec tags *every*
container, so even a user record spelling a protocol tag remains ordinary data.
"""
from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import json
import math


@dataclass(frozen=True)
class Unit:
    pass


UNIT = Unit()


@dataclass(frozen=True)
class ResultValue:
    ok: bool
    value: object = UNIT
    error: object = None


@dataclass(frozen=True)
class Node:
    kind: str
    start: int
    end: int
    data: dict = field(default_factory=dict)

    @property
    def id(self):
        return f"{self.kind}:{self.start}:{self.end}"


class Fault(Exception):
    """Only catchable execution faults participate in catch/fallback."""
    def __init__(self, code, message, node=None, *, kind="runtime", partial=UNIT,
                 details=None):
        super().__init__(message)
        self.code, self.kind, self.node = code, kind, node
        self.partial, self.details = partial, details or {}
        self.frames = []
        self.evidence = []

    @property
    def catchable(self):
        return self.kind not in {"cancelled", "permission", "budget", "compile", "protocol"}

    def view(self, source=""):
        out = {"code": self.code, "kind": self.kind, "message": str(self),
               "frames": self.frames, "has_partial": self.partial is not UNIT,
               "partial": self.partial if self.partial is not UNIT else None,
               "evidence": self.evidence, "details": self.details}
        if self.node:
            out["source_span"] = span(source, self.node)
        return out


def span(source, node):
    return {"source_hash": digest(source), "start": node.start, "end": node.end,
            "line": source.count("\n", 0, node.start) + 1,
            "column": node.start - source.rfind("\n", 0, node.start)}


def digest(value):
    if not isinstance(value, str):
        value = json.dumps(pack(value), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(value.encode()).hexdigest()


def pack(value):
    if isinstance(value, Unit):
        return ["unit"]
    if isinstance(value, ResultValue):
        return ["result", value.ok, pack(value.value), pack(value.error)]
    if type(value) is int and abs(value) > 2**53 - 1:
        return ["integer", str(value)]
    if value is None or type(value) in (bool, str, int):
        return ["scalar", value]
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise Fault("NONFINITE", "유한한 숫자만 전송할 수 있습니다.", kind="protocol")
        return ["decimal", str(value)]
    if type(value) is float and math.isfinite(value):
        return ["scalar", value]
    if isinstance(value, (list, tuple)):
        return ["list", [pack(v) for v in value]]
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return ["record", [[k, pack(v)] for k, v in value.items()]]
    raise Fault("VALUE_PROTOCOL", f"전송할 수 없는 값: {type(value).__name__}", kind="protocol")


def unpack(value):
    try:
        tag = value[0]
        if tag == "unit" and len(value) == 1:
            return UNIT
        if tag == "scalar" and len(value) == 2:
            raw = value[1]
            if raw is None or type(raw) in (str, bool, int) or (type(raw) is float and math.isfinite(raw)):
                return raw
        if tag == "integer" and len(value) == 2 and isinstance(value[1], str):
            raw = int(value[1])
            if str(raw) == value[1]:
                return raw
        if tag == "decimal" and len(value) == 2 and isinstance(value[1], str):
            raw = Decimal(value[1])
            if raw.is_finite():
                return raw
        if tag == "list" and len(value) == 2:
            return [unpack(v) for v in value[1]]
        if tag == "record" and len(value) == 2:
            out = {}
            for key, v in value[1]:
                if not isinstance(key, str) or key in out:
                    raise ValueError("duplicate/non-text key")
                out[key] = unpack(v)
            return out
        if tag == "result" and len(value) == 4 and type(value[1]) is bool:
            return ResultValue(value[1], unpack(value[2]), unpack(value[3]))
    except (ValueError, TypeError, IndexError, KeyError):
        pass
    raise Fault("VALUE_PROTOCOL", "올바른 ibl-value/1 값이 아닙니다.", kind="protocol")


def projection(value):
    """Human-readable view. `value_wire` is the authoritative typed value."""
    if isinstance(value, Unit):
        return {"$ibl": "unit"}
    if isinstance(value, ResultValue):
        return {"$ibl": "result", "ok": value.ok, "value": projection(value.value),
                "error": projection(value.error)}
    if isinstance(value, Decimal):
        return {"$ibl": "decimal", "text": str(value)}
    if type(value) is int and abs(value) > 2**53 - 1:
        return {"$ibl": "integer", "text": str(value)}
    if isinstance(value, (list, tuple)):
        return [projection(v) for v in value]
    if isinstance(value, dict):
        return {k: projection(v) for k, v in value.items()}
    return value
