"""Local MIT RHWP adapter; the shared office session owns publication.

본 제품은 한컴의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다.
Container validation is not a claim of visual fidelity to Hancom Office.
"""
import io
import struct
import zipfile
from pathlib import Path

from defusedxml.ElementTree import fromstring, ParseError
from defusedxml.common import DefusedXmlException

from office_sessions import DocumentUnsupported, MAX_BYTES
from office_store import digest

FORMATS = {"hwp", "hwpx"}
ASSETS = Path(__file__).resolve().parents[1] / "static" / "rhwp"
NOTICE = "본 제품은 한컴의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다."


def available():
    return (ASSETS / "index.html").is_file() and (ASSETS / "indiebiz-build.json").is_file()


def validate(data, format):
    if len(data) > MAX_BYTES:
        raise ValueError("문서 크기 상한은 25MB입니다")
    if format == "hwp":
        import olefile
        try:
            with olefile.OleFileIO(io.BytesIO(data)) as doc:
                header = doc.openstream("FileHeader").read(256)
                if len(header) != 256 or not header.startswith(b"HWP Document File\x00") or header[35] != 5:
                    raise ValueError("HWP 5.x 파일이 아닙니다")
                flags = struct.unpack_from("<I", header, 36)[0]
                # HWP 5.0 FileHeader table 3: password, distribution, DRM, certificate encryption/DRM.
                if flags & (2 | 4 | 16 | 256 | 1024):
                    raise DocumentUnsupported("암호·배포용·DRM HWP는 이 편집기에서 지원하지 않습니다")
                if not doc.exists("DocInfo") or not doc.exists("BodyText/Section0"):
                    raise ValueError("HWP 본문 구조가 없습니다")
        except (OSError, IOError) as exc:
            raise ValueError("올바른 HWP 파일이 아닙니다") from exc
    elif format == "hwpx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as doc:
                names = doc.namelist()
                if len(names) > 10000 or len(set(names)) != len(names):
                    raise ValueError("HWPX 압축 항목이 중복되거나 너무 많습니다")
                if sum(i.file_size for i in doc.infolist()) > 200 * 1024 * 1024:
                    raise ValueError("HWPX 압축 해제 크기 상한을 초과했습니다")
                if doc.read("mimetype") != b"application/hwp+zip":
                    raise ValueError("HWPX 미디어 유형이 일치하지 않습니다")
                for name in ("Contents/content.hpf", "Contents/header.xml", "Contents/section0.xml"):
                    fromstring(doc.read(name))
        except (zipfile.BadZipFile, KeyError, RuntimeError, ParseError, DefusedXmlException) as exc:
            raise ValueError("올바른 HWPX 파일이 아닙니다") from exc
    else:
        raise DocumentUnsupported("HWP/HWPX 문서를 선택하세요")


def content(app, document_id, session_id, client_id, epoch, expected):
    with app.store.lock():
        d, s = app._session(document_id, session_id, client_id, epoch, expected)
        if d["source_format"] not in FORMATS:
            raise DocumentUnsupported("HWP/HWPX 문서를 선택하세요")
        return app.store.bytes(s["blob"])


def draft(app, document_id, session_id, client_id, epoch, expected, operation_id, data):
    """Idempotent binary draft; never writes the user's original file."""
    with app.store.lock():
        d = app._doc(document_id)
        op, cached = app._operation(document_id, operation_id,
            ["hwp-draft", session_id, client_id, epoch, expected, digest(data)])
        if cached is not None:
            return cached
        d, s = app._session(document_id, session_id, client_id, epoch, expected)
        validate(data, d["source_format"])
        blob = app.store.blob(data)
        if blob != s["blob"]:
            s.update(blob=blob, session_revision=expected + 1, state="draft")
        op["result"] = {"session": s}
        with app.store.connect() as conn:
            app.store.put("session", s, conn)
            app.store.put("operation", op, conn)
            app.store.event(document_id, {"type": "hwp_draft", "operation_id": operation_id,
                "session_revision": s["session_revision"]}, conn)
        return op["result"]
