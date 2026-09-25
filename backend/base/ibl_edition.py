"""Source edition identity shared by storage, recall and execution boundaries."""
import hashlib
import re


def source_edition(source, requested=None):
    header = re.match(r"\A\s*#!ibl[ \t]+edition=(\d+)[ \t]*(?:\n|$)", source)
    if source.lstrip().startswith("#!ibl") and not header:
        raise ValueError("EDITION_HEADER: 파일 헤더는 #!ibl edition=1 또는 2입니다.")
    declared = int(header[1]) if header else None
    if requested is not None and (type(requested) is not int or requested not in (1, 2)):
        raise ValueError("EDITION: 지원 판본은 1과 2입니다.")
    if declared is not None and declared not in (1, 2):
        raise ValueError("EDITION: 지원하지 않는 파일 판본입니다.")
    if declared is not None and requested is not None and declared != requested:
        raise ValueError("EDITION_CONFLICT: 파일 헤더와 API edition이 다릅니다.")
    return requested or declared or 1


def explicit_source(source, requested=None):
    edition = source_edition(source, requested)
    if edition == 2 and not source.lstrip().startswith("#!ibl"):
        return "#!ibl edition=2\n" + source
    return source


def program_hash(source, edition=1):
    # Preserve every v1 trajectory join; distinguish identical text interpreted
    # under another edition. Source text itself remains unchanged in storage.
    identity = source if edition == 1 else f"ibl-edition:{edition}\0{source}"
    return hashlib.sha256(identity.encode("utf-8", "replace")).hexdigest()


def authoring_request(request):
    """New model-authored code uses current IBL; stored source keeps its edition.

    Do not call this from saved workflow/schedule readers. A header or explicit
    edition is authoritative; syntax errors never trigger legacy execution.
    """
    source = request.get("code") or request.get("pipeline") or ""
    if request.get("edition") is not None or source.lstrip().startswith("#!ibl"):
        return request
    return {**request, "edition": 2}


from contextlib import contextmanager
from contextvars import ContextVar
_current_edition = ContextVar("ibl_source_edition", default=1)


@contextmanager
def source_context(edition):
    token = _current_edition.set(edition)
    try:
        yield
    finally:
        _current_edition.reset(token)


def text_result(text):
    """Wrap a producer-confirmed text success before envelope heuristics run.

    Legacy programs keep their exact string. Current callers receive an explicit
    envelope, so JSON-looking business text cannot turn into status or fields.
    Failures must not pass through this helper.
    """
    return {"success": True, "message": text} if _current_edition.get() == 2 else text


def pin_source(source, requested=None):
    """새 저장 코드만 작성 문맥에 고정한다. 기존 원문 조회에는 사용하지 않는다."""
    if not isinstance(source, str) or not source.strip():
        return source
    declared = source_edition(source, requested) if requested is not None or source.lstrip().startswith("#!ibl") else _current_edition.get()
    return explicit_source(source, declared)
