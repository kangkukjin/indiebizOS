"""Versioned app-UID execution contract, shared by hub and Android worker."""
import json

VERSION = 1
OPS = {"shell", "python"}
MAX_CODE = 64 * 1024
MAX_ENVELOPE = 256 * 1024
DEFAULT_TIMEOUT = 120


def validate(command):
    if not isinstance(command, dict) or command.get("op") not in OPS:
        raise ValueError("unsupported_phone_runtime")
    out = dict(command)
    op = out["op"]
    field = "cmd" if op == "shell" else "code"
    source = out.get(field)
    if not isinstance(source, str) or not source.strip():
        raise ValueError(field + "_required")
    if len(source.encode("utf-8")) > MAX_CODE:
        raise ValueError("program_too_large")
    timeout = out.get("timeout", DEFAULT_TIMEOUT)
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError("phone_timeout_must_be_1_to_3600")
    out["timeout"] = timeout
    if out.get("mode", "background") != "background":
        raise ValueError("unsupported_phone_mode")
    if out.get("elevate") not in (None, False) or "reset" in out:
        raise ValueError("unsupported_phone_privilege_or_session")
    if "cwd" in out and (not isinstance(out["cwd"], str) or "\0" in out["cwd"]):
        raise ValueError("invalid_cwd")
    if op == "shell":
        if out.get("shell", "sh") != "sh":
            raise ValueError("phone_shell_must_be_sh")
        if "inputs" in out or "code" in out:
            raise ValueError("unsupported_shell_field")
        if not isinstance(out.get("stdin", ""), str):
            raise ValueError("stdin_must_be_text")
        env = out.get("env", {})
        if not isinstance(env, dict) or any(
                not isinstance(k, str) or not k or "=" in k or "\0" in k
                or not isinstance(v, str) or "\0" in v for k, v in env.items()):
            raise ValueError("invalid_env")
    else:
        if any(k in out for k in ("cmd", "stdin", "env", "shell", "reset")):
            raise ValueError("unsupported_python_field")
        if not isinstance(out.get("inputs", {}), dict):
            raise ValueError("inputs_must_be_object")
    if len(json.dumps(out, ensure_ascii=False, allow_nan=False).encode()) > MAX_ENVELOPE:
        raise ValueError("command_too_large_use_transfer")
    return out
