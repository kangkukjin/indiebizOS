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
    from ibl_v2_parser import parse
    from ibl_edition import require_current
    sources = list(_source.get())
    for item in sources:
        try:
            require_current(item)
        except ValueError as exc:
            raise Fault('LIBRARY_FORMAT', str(exc), kind='compile') from exc
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
