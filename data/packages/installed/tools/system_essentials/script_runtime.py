"""등록 스크립트 동기/분리 러너가 공유하는 출력 판정·원자 파일 쓰기."""
import json
import os
import tempfile
import threading

STATE_LOCK = threading.RLock()


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def parse_output(stdout):
    """종료 코드와 별개로 JSON 결과의 명시적 실패를 보존한다."""
    try:
        parsed = json.loads(stdout)
    except (ValueError, TypeError):
        return None, None
    if not isinstance(parsed, dict):
        return None, None
    error = parsed.get('error')
    if parsed.get('success') is False or error:
        return {**parsed, 'success': False}, str(error or '스크립트가 실패 결과를 반환했습니다.')
    if isinstance(parsed.get('items'), list) or isinstance(parsed.get('table'), dict):
        return parsed, None
    return None, None


def validate_v2_contract(contract):
    from ibl_v2_adapters import validate_contract
    validate_contract(contract)
    if contract["adapter"]["protocol"] != "ibl-script/2":
        raise ValueError("등록 script의 새 프로토콜은 ibl-script/2입니다.")
    return contract


def _v2_json_safe(value):
    """This script protocol uses plain JSON; reject values needing tagged wire."""
    from ibl_v2_ir import pack
    def visit(wire):
        if wire[0] == "scalar":
            return
        if wire[0] == "list":
            for child in wire[1]:
                visit(child)
            return
        if wire[0] == "record":
            for _, child in wire[1]:
                visit(child)
            return
        raise ValueError("ibl-script/2의 일반 JSON은 안전 정수 범위·유한 숫자·일반 데이터만 지원합니다.")
    visit(pack(value))


def v2_input(entry, args, context=None):
    from ibl_v2_types import guard
    contract = validate_v2_contract(entry.get("callable_contract"))
    if not isinstance(args, dict):
        raise ValueError("script args는 Record입니다.")
    params = contract["params"]
    required = contract.get("required", list(params))
    if any(k not in args for k in required) or any(k not in params for k in args):
        raise ValueError("script의 명시 인자 계약과 args가 다릅니다.")
    for key, value in args.items():
        guard(value, params[key], key)
    _v2_json_safe(args)
    return {"protocol": "ibl-script/2", "args": args,
            "context": {"edition": 2, **(context or {})}}


def v2_output(stdout, contract):
    from ibl_v2_types import guard
    from ibl_v2_ir import pack
    try:
        envelope = json.loads(stdout)
        if not isinstance(envelope, dict) or envelope.get("protocol") != "ibl-script/2":
            raise ValueError("stdout에 ibl-script/2 봉투가 필요합니다.")
        if type(envelope.get("ok")) is not bool:
            raise ValueError("stdout.ok는 Bool입니다.")
        if not envelope["ok"]:
            return None, str(envelope.get("error") or "script 실패")
        if "value" not in envelope:
            raise ValueError("stdout.value가 없습니다(null은 값으로 허용).")
        value = guard(envelope["value"], contract["result"], "script 반환")
        _v2_json_safe(value)
        return value, None
    except Exception as exc:
        return None, f"script 출력 계약 위반: {exc}"


def legacy_value_output(stdout):
    """Adapt a registered JSON/stdout script without changing its stdin ABI.

    JSON remains its entire value, never a guessed items/message projection.
    Plain output is complete Text. Legacy failure markers remain failures.
    """
    try:
        value = json.loads(stdout)
    except ValueError:
        return stdout, None
    _v2_json_safe(value)
    if isinstance(value, dict) and (value.get("success") is False or value.get("error")):
        return value, str(value.get("error") or "스크립트가 실패 결과를 반환했습니다.")
    return value, None


def member_value_script(params, command, exchange):
    """Negotiate with the member device; stdin and stdout retain their values."""
    if params.get("args_file") or params.get("background"):
        return {"success": False, "error": "회원 스크립트는 명시 args와 동기 실행을 사용합니다."}
    catalogue = exchange({"op": "script", "action": "list"})
    if catalogue.get("success") is False:
        return catalogue
    if "ibl-script/2" not in catalogue.get("script_protocols", []):
        return {"success": False, "error_type": "capability", "error": "회원 기기의 스크립트 프로토콜 업데이트가 필요합니다."}
    op = params.get("op", "run" if params.get("id") else "list")
    if op == "list":
        return catalogue
    command = {**command, "timeout": params.get("timeout", 120)}
    if op == "register":
        contract = params.get("callable_contract")
        if contract:
            validate_v2_contract(contract)
            command["callable_contract"] = contract
        return exchange(command)
    if op != "run":
        return exchange(command)
    entry = next((r for r in catalogue.get("items", []) if r.get("id") == params.get("id")), None)
    if entry is None:
        return {"success": False, "error": "회원 기기에 등록되지 않은 스크립트입니다."}
    contract = entry.get("callable_contract")
    args = params.get("args") or {}
    command["args"] = v2_input(entry, args) if contract else args
    command["script_protocol"] = "ibl-script/2" if contract else "registered-json/1"
    result = exchange(command)
    if result.get("success") is False or result.get("error"):
        return result
    if result.get("truncated"):
        return {**result, "success": False, "error": "스크립트 stdout이 잘려 값으로 읽을 수 없습니다."}
    value, error = v2_output(result.get("stdout", ""), contract) if contract else legacy_value_output(result.get("stdout", ""))
    if error:
        details = {k: value[k] for k in ("blocked", "denied", "permission_denied", "error_type")
                   if not contract and isinstance(value, dict) and k in value}
        return {**result, **details, "success": False, "error": error}
    out = {**result, "value": value, "script_protocol": command["script_protocol"]}
    if not contract:
        from ibl_honesty import merge_into
        merge_into(value, out)
    return out
