"""Member-provided definitions, scoped to the current tool call only."""
import contextvars
from contextlib import contextmanager
from ibl_v2_ir import Fault, digest

_source = contextvars.ContextVar("ibl_member_library", default=())


@contextmanager
def library(source):
    token = _source.set([source] if isinstance(source, str) else (source or []))
    try:
        yield
    finally:
        _source.reset(token)


def definitions():
    from ibl_edition import source_edition
    from ibl_v2_parser import parse
    sources = [s for s in _source.get() if source_edition(s) == 2]
    source = "\n".join(sources)
    statements = parse(source).data["statements"]
    if any(s.kind != "def" for s in statements):
        raise Fault("MEMBER_LIBRARY", "저장 문장에는 함수 정의만 허용됩니다.", kind="compile")
    out = {}
    for s in statements:
        name = s.data["name"]
        if name in out:
            raise Fault("DUPLICATE_FUNCTION", f"중복 함수: {name}", kind="compile")
        out[name] = source[s.start:s.end]
    return out


def adapters(project_path, agent_id):
    from ibl_edition import source_edition
    from ibl_parser import parse
    from ibl_engine import execute_ibl
    from ibl_v2_adapters import Adapter, Adapted, decode_envelope
    from ibl_v2_compat import plain_arguments
    from workflow_contract import pipe_input_param
    source = "\n".join(s for s in _source.get() if source_edition(s) == 1)
    if not source:
        return {}
    statements = parse(source)
    if any(not s.get("_def") for s in statements):
        raise Fault("MEMBER_LIBRARY", "저장 문장에는 함수 정의만 허용됩니다.", kind="compile")
    result = {}
    for s in statements:
        name = s["name"]
        contract = {"version": 1, "params": {p: "Unknown" for p in s.get("signature", [])},
                    "result": "Record", "effects": ["unknown"],
                    "compatibility": "legacy-function/1", "implementation_fingerprint": digest(source),
                    "adapter": {"protocol": "legacy-envelope", "value_path": ""}}
        receiver = pipe_input_param(s.get("body"))
        if receiver in contract["params"]:
            contract["pipe_input"] = receiver
        def run(runtime, args, name=name, contract=contract):
            # Parse only the pinned definitions and a literal function name.
            # Arguments enter as values, never interpolated into source.
            call = parse(source + "\n[fn:" + name + "]{}")[-1]
            call["params"] = plain_arguments(args)
            raw = execute_ibl(call, project_path, agent_id=agent_id)
            value, evidence = decode_envelope(raw, contract["adapter"])
            evidence["compatibility"] = "legacy-function/1"
            return Adapted(value, evidence)
        result["fn:" + name] = Adapter(contract, run)
    return result
