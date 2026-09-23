"""Declarative per-row input/output coverage. Pure; no model or task knowledge.

IDs use the shared strict group identity (JSON strings only). Allowed values use
the shared conditional equality. Paths use field_path; no embedded code.
"""
import json

from common.field_path import MISSING, parse_path, walk_path
from common.value_semantics import group_identity, values_equal


class ContractError(ValueError):
    def __init__(self, message, *, phase="declaration", **details):
        super().__init__(message)
        self.details = {"phase": phase, **details}


def _path(value):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ContractError("contract 경로는 비어 있지 않은 점 경로여야 합니다(*·대괄호 제외).")
    parts = parse_path(value)
    if (".".join(parts) != value or any(part != part.strip() or part == "*"
                                       or any(c in part for c in "[]$") for part in parts)):
        raise ContractError("contract 경로는 비어 있지 않은 점 경로여야 합니다(*·대괄호 제외).")
    return parts


def validate_contract(contract, *, input_fields=None, fields=None, preserve_rows=None):
    """Same declaration check for static literals and resolved runtime values."""
    if contract is None:
        return
    if not isinstance(contract, dict) or set(contract) != {"covers"}:
        raise ContractError("contract는 covers 배열 하나를 가진 객체여야 합니다.")
    try:
        if len(json.dumps(contract, ensure_ascii=False, allow_nan=False)) > 16000:
            raise ContractError("contract는 최대 16000자입니다.")
    except (TypeError, ValueError) as exc:
        raise ContractError(f"contract JSON 선언 오류: {exc}") from exc
    for name, projection in (("input_fields", input_fields), ("fields", fields)):
        if projection is not None and (not isinstance(projection, list)
                                       or any(not isinstance(v, str) for v in projection)):
            raise ContractError(f"{name}는 문자열 배열이어야 합니다.")
    if preserve_rows is not None and type(preserve_rows) is not bool:
        raise ContractError("preserve_rows는 boolean이어야 합니다.")
    rules = contract["covers"]
    if not isinstance(rules, list) or not 1 <= len(rules) <= 16:
        raise ContractError("contract.covers는 1~16개 규칙이어야 합니다.")
    if preserve_rows is False:
        raise ContractError("contract는 입력 행 보존을 요구합니다(preserve_rows:false와 충돌).")
    for rule in rules:
        if (not isinstance(rule, dict) or not {"input", "output", "key"} <= set(rule)
                or set(rule) - {"input", "output", "key", "output_key", "required", "allowed"}):
            raise ContractError("covers 규칙: input, output, key 필수; output_key, required, allowed 선택.")
        for name in ("input", "output", "key", "output_key"):
            if name in rule:
                _path(rule[name])
        for name in ("input", "output"):
            root = _path(rule[name])[0]
            if root == "_i":
                raise ContractError("contract 경로에 내부 색인 _i를 사용할 수 없습니다.")
            if name == "input" and input_fields is not None and root not in input_fields:
                raise ContractError("input_fields가 contract 입력 경로를 숨깁니다.", path=rule[name])
            if name == "output" and fields and root not in fields:
                raise ContractError("fields가 contract 출력 경로를 제거합니다.", path=rule[name])
        required = rule.get("required", [])
        allowed = rule.get("allowed", {})
        if not isinstance(required, list) or len(required) > 32:
            raise ContractError("required는 최대 32개 필드 경로 배열이어야 합니다.")
        if not isinstance(allowed, dict) or len(allowed) > 32:
            raise ContractError("allowed는 필드 경로별 허용값 배열 객체여야 합니다.")
        for path in required:
            _path(path)
        for path, choices in allowed.items():
            _path(path)
            if (not isinstance(choices, list) or not 1 <= len(choices) <= 32
                    or any(not isinstance(v, (str, int, float, bool, type(None))) for v in choices)):
                raise ContractError("allowed의 허용값은 1~32개 JSON 스칼라 배열이어야 합니다.")


def _index(row, path, key, phase, row_index):
    records = walk_path(row, path)
    if not isinstance(records, list):
        raise ContractError("contract 대상은 배열이어야 합니다.", phase=phase, row=row_index, path=path)
    index = {}
    duplicates = []
    for position, record in enumerate(records):
        value = walk_path(record, key) if isinstance(record, dict) else MISSING
        if not isinstance(value, str) or not value.strip():
            raise ContractError("contract ID는 비어 있지 않은 문자열이어야 합니다.",
                                phase=phase, row=row_index, path=path, position=position, key=key)
        identity = group_identity(value)
        if identity in index:
            duplicates.append(value)
        index[identity] = (value, record)
    if duplicates:
        raise ContractError("contract ID 중복입니다.", phase=phase, row=row_index,
                            path=path, duplicate_count=len(duplicates), duplicate_ids=duplicates[:20])
    return index


def check_inputs(rows, contract, *, input_fields=None):
    if contract is not None:
        for i, row in enumerate(rows):
            for rule in contract["covers"]:
                _index(row, rule["input"], rule["key"], "input", i)
                output_root = parse_path(rule["output"])[0]
                if input_fields is not None and output_root in row and output_root not in input_fields:
                    raise ContractError("contract 출력이 input_fields로 숨긴 원본 열을 변경해야 합니다.",
                                        phase="input", row=i, path=rule["output"])


def check_outputs(inputs, outputs, contract):
    """Compare against original input, never a model-modified input snapshot."""
    if contract is None:
        return
    if len(inputs) != len(outputs):
        raise ContractError("contract 입력 행 누락 또는 추가입니다.", phase="output",
                            expected_rows=len(inputs), actual_rows=len(outputs))
    for i, (source, output) in enumerate(zip(inputs, outputs)):
        for rule in contract["covers"]:
            expected = _index(source, rule["input"], rule["key"], "input", i)
            actual = _index(output, rule["output"], rule.get("output_key", rule["key"]), "output", i)
            missing = [value for identity, (value, _) in expected.items() if identity not in actual]
            extra = [value for identity, (value, _) in actual.items() if identity not in expected]
            if missing or extra:
                raise ContractError("contract 입력 ID 전체를 정확히 한 번씩 반환해야 합니다.",
                                    phase="output", row=i, path=rule["output"],
                                    expected_count=len(expected), actual_count=len(actual),
                                    missing_count=len(missing), missing_ids=missing[:20],
                                    extra_count=len(extra), extra_ids=extra[:20])
            for value, record in actual.values():
                for path in rule.get("required", []):
                    found = walk_path(record, path)
                    if found is MISSING or found is None:
                        raise ContractError("contract 필수 필드가 없거나 null입니다.",
                                            phase="output", row=i, id=value, path=path)
                for path, choices in rule.get("allowed", {}).items():
                    found = walk_path(record, path)
                    if found is MISSING or not any(values_equal(found, c) for c in choices):
                        raise ContractError("contract 허용값 밖의 응답입니다.",
                                            phase="output", row=i, id=value, path=path,
                                            allowed=choices)
