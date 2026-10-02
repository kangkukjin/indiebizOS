"""Snapshot-bound office proposals; edits stay in the official editor plugin."""
import time

from office_sessions import DocumentConflict
from office_store import digest, identifier


def propose(app, document_id, session_id, client_id, epoch, expected,
            bookmark, selected, instruction, operation_id, replacement=None):
    import re
    if not isinstance(bookmark, str) or not re.fullmatch(r"ib_[a-f0-9]{24}", bookmark):
        raise ValueError("선택 위치 식별자를 확인하세요")
    if not isinstance(selected, str) or not 1 <= len(selected) <= 20000:
        raise ValueError("선택은 1~20000자입니다")
    if not isinstance(instruction, str) or not 1 <= len(instruction) <= 4000:
        raise ValueError("수정 지시는 1~4000자입니다")
    with app.store.lock():
        d, s = app._session(document_id, session_id, client_id, epoch, expected)
        op, cached = app._operation(document_id, operation_id,
            ["office_proposal", session_id, epoch, expected, bookmark, selected, instruction, replacement])
        if cached is not None:
            return cached
        if op.get("status"):
            raise DocumentConflict("이미 시작한 AI 요청입니다. 자동으로 중복 호출하지 않습니다")
        if d["encoding"] or d["source_format"] == "pdf":
            raise ValueError("사무 문서의 선택 수정 전용입니다")
        if d["source_format"] == "docx":
            import io, zipfile
            from defusedxml.ElementTree import fromstring
            with zipfile.ZipFile(io.BytesIO(app.store.bytes(s["blob"]))) as archive:
                xml = fromstring(archive.read("word/document.xml"))
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            if not any(n.get(ns+"name") == bookmark for n in xml.iter(ns+"bookmarkStart")):
                raise DocumentConflict("선택 위치가 아직 저장되지 않았습니다. 편집기 저장 후 다시 시도하세요")
        row = {"id": identifier(), "document_id": document_id, "session_id": session_id,
               "epoch": epoch, "blob": s["blob"], "bookmark": bookmark, "selected": selected,
               "selected_sha256": digest(selected.encode()), "created_at": time.time()}
        op["status"] = "generating"; app.store.put("operation", op)
    try:
        if replacement is None:
            from document_workspace import generate_selection
            replacement, provenance = generate_selection(instruction, selected)
        else:
            provenance = {"kind": "manual"}
        if not isinstance(replacement, str) or len(replacement) > 40000:
            raise ValueError("수정 문구가 너무 큽니다")
        row.update(replacement=replacement, provenance=provenance)
        with app.store.lock(), app.store.connect() as conn:
            app.store.put("office_proposal", row, conn)
            op.update(status="completed", result=row); app.store.put("operation", op, conn)
        return row
    except Exception:
        op["status"] = "failed"; app.store.put("operation", op)
        raise


def approve(app, document_id, session_id, client_id, epoch, expected, proposal_id):
    d, s = app._session(document_id, session_id, client_id, epoch, expected)
    row = app.store.get("office_proposal", proposal_id)
    if (row["document_id"] != document_id or row["session_id"] != session_id
            or row["epoch"] != epoch or row["blob"] != s["blob"]):
        raise DocumentConflict("제안 이후 문서가 바뀌었습니다. 제안을 다시 만드세요")
    return row
