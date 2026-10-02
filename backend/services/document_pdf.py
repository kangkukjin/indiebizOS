"""Local scan OCR with editable text/coordinates and a searchable copy.
Original pages remain immutable. Correction never claims to edit image pixels.
"""
import csv
import io
import os
import subprocess
import tempfile
from pathlib import Path

import pymupdf

from office_store import identifier
from office_sessions import DocumentConflict, DocumentUnsupported


def change_pages(app, document_id, session_id, client_id, epoch, expected, pages, action):
    """Operate on an acknowledged engine snapshot and fence the old editor.

    The result is a recoverable draft; original publication remains in save().
    """
    if action not in {"rotate", "delete", "reorder"}:
        raise ValueError("지원하지 않는 쪽 작업입니다")
    if (not isinstance(pages, list) or not pages or len(pages) > 1000
            or any(type(p) is not int for p in pages) or len(set(pages)) != len(pages)):
        raise ValueError("중복 없는 쪽 번호를 입력하세요")
    with app.store.lock():
        d, s = app._session(document_id, session_id, client_id, epoch, expected)
        if d['source_format'] != 'pdf':
            raise DocumentUnsupported("PDF 문서를 선택하세요")
        with pymupdf.open(stream=app.store.bytes(s['blob']), filetype='pdf') as pdf:
            if min(pages) < 1 or max(pages) > len(pdf):
                raise ValueError("PDF 쪽 범위를 벗어났습니다")
            if action == 'rotate':
                for number in pages:
                    page = pdf[number - 1]; page.set_rotation((page.rotation + 90) % 360)
            elif action == 'delete':
                if len(pages) == len(pdf):
                    raise ValueError("최소 한 쪽은 남겨야 합니다")
                pdf.delete_pages([p - 1 for p in pages])
            else:
                if set(pages) != set(range(1, len(pdf) + 1)):
                    raise ValueError("재정렬은 모든 쪽을 한 번씩 지정하세요")
                pdf.select([p - 1 for p in pages])
            data = pdf.tobytes(garbage=4, deflate=True)
        app.validate_output(d, data)
        s.update(blob=app.store.blob(data), engine_epoch=identifier(),
                 session_revision=expected + 1, state='draft')
        with app.store.connect() as conn:
            app.store.put('session', s, conn)
            app.store.event(document_id, {'type': 'pdf_pages', 'action': action, 'pages': pages}, conn)
        return app.detail(document_id)


def ocr(app, document_id, expected_revision, pages, language="kor+eng"):
    d = app._doc(document_id)
    if d["source_format"] != "pdf":
        raise DocumentUnsupported("PDF 문서를 선택하세요")
    if d["revision_id"] != expected_revision:
        raise DocumentConflict("문서 버전이 바뀌었습니다")
    if d["session_id"] and app.store.get("session", d["session_id"])["state"] != "saved":
        raise DocumentConflict("편집 중인 PDF를 먼저 원본 저장하세요")
    if language not in {"kor", "eng", "kor+eng"}:
        raise ValueError("OCR 언어는 한국어·영어만 지원합니다")
    if not isinstance(pages, list) or not 1 <= len(pages) <= 20 or any(type(p) is not int for p in pages):
        raise ValueError("한 번에 1~20쪽을 선택하세요")
    data = app.store.bytes(d["source_sha256"])
    output = {"id": identifier(), "document_id": document_id, "revision_id": expected_revision,
              "blob": d["source_sha256"], "language": language, "pages": []}
    with pymupdf.open(stream=data, filetype="pdf") as pdf, tempfile.TemporaryDirectory(prefix="document-ocr-") as folder:
        for number in sorted(set(pages)):
            if not 1 <= number <= len(pdf):
                raise ValueError("PDF 쪽 범위를 벗어났습니다")
            page = pdf[number-1]
            pix = page.get_pixmap(dpi=160, alpha=False)
            image = Path(folder)/"page.png"; pix.save(image)
            env = dict(os.environ)
            if not Path(env.get("TESSDATA_PREFIX", "/missing")).is_dir():
                env.pop("TESSDATA_PREFIX", None)
            result = subprocess.run(["tesseract", str(image), "stdout", "-l", language, "tsv"],
                capture_output=True, text=True, timeout=90, env=env)
            if result.returncode:
                raise ValueError("OCR 오류: " + result.stderr[-1500:])
            words = []
            for item in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
                text = item.get("text", "").strip()
                if not text or item["level"] != "5":
                    continue
                x, y, w, h = (float(item[k]) for k in ("left", "top", "width", "height"))
                words.append({"id": len(words), "text": text, "confidence": float(item["conf"]),
                    "rect": [x/pix.width*page.rect.width, y/pix.height*page.rect.height,
                             (x+w)/pix.width*page.rect.width, (y+h)/pix.height*page.rect.height]})
            output["pages"].append({"number": number, "words": words, "width": page.rect.width, "height": page.rect.height})
    app.store.put("ocr", output)
    return output


def correct(app, document_id, ocr_id, edits):
    app._doc(document_id)
    row = app.store.get("ocr", ocr_id)
    if row["document_id"] != document_id:
        raise PermissionError("다른 문서의 OCR입니다")
    if not isinstance(edits, list) or len(edits) > 20000:
        raise ValueError("OCR 교정 목록을 확인하세요")
    mapping = {(p["number"], w["id"]): w for p in row["pages"] for w in p["words"]}
    for edit in edits:
        if not isinstance(edit.get("text"), str) or len(edit["text"]) > 200:
            raise ValueError("단어별 교정은 200자 이하입니다")
        word = mapping.get((edit.get("page"), edit.get("word")))
        if word is None:
            raise ValueError("존재하지 않는 OCR 단어입니다")
        word.setdefault("original_text", word["text"]); word["text"] = edit["text"]
    app.store.put("ocr", row)
    return row


def export(app, document_id, ocr_id):
    d = app._doc(document_id)
    row = app.store.get("ocr", ocr_id)
    if row["document_id"] != document_id:
        raise PermissionError("다른 문서의 OCR입니다")
    selected = {p["number"]: p for p in row["pages"]}
    with pymupdf.open(stream=app.store.bytes(row["blob"]), filetype="pdf") as original, pymupdf.open() as output:
        for index, page in enumerate(original):
            if index+1 not in selected:
                output.insert_pdf(original, from_page=index, to_page=index)
                continue
            # Rasterize selected scans: eliminates a stale/incorrect hidden text layer.
            new = output.new_page(width=page.rect.width, height=page.rect.height)
            new.insert_image(new.rect, stream=page.get_pixmap(dpi=160, alpha=False).tobytes("png"))
            for word in selected[index+1]["words"]:
                if not word["text"]:
                    continue
                rect = pymupdf.Rect(word["rect"])
                size = min(max(1, rect.height*.85), max(1, rect.width/max(1,len(word["text"]))))
                new.insert_text((rect.x0, rect.y1-rect.height*.12), word["text"], fontsize=size,
                                fontname="korea", render_mode=3)
        data = output.tobytes(garbage=4, deflate=True)
    from document_creation import import_bytes
    result = import_bytes(app, Path(d["title"]).stem+"_searchable.pdf", data)
    result["ocr"] = {"source_revision":row["revision_id"], "corrected":True,
        "selected_pages_rasterized":sorted(selected), "original_preserved":True}
    return result
