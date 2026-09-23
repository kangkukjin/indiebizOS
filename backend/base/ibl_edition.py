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
