"""Explicit conversion copies and source compilation. Originals are never replaced."""
import json
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import jwt

from document_office import download, settings, validate
from office_sessions import DocumentConflict, DocumentUnsupported
from office_store import identifier

OUTPUTS = {"docx", "pdf", "odt", "rtf", "txt", "html", "epub"}
INPUTS = {"docx", "doc", "odt", "rtf", "txt", "html", "htm", "pdf", "pages", "hwp", "hwpx", "dotx", "ott", "epub", "md", "markdown", "typ"}


def convert(app, document_id, output_format, expected_revision, session_id=None, client_id=None,
            epoch=None, expected=None):
    if output_format not in OUTPUTS:
        raise ValueError("지원하지 않는 출력 형식입니다")
    with app.store.lock():
        d = app._doc(document_id)
        if d["revision_id"] != expected_revision:
            raise DocumentConflict("문서 버전이 바뀌었습니다")
        if d["source_format"] not in INPUTS:
            raise DocumentUnsupported("이 형식의 변환기는 아직 연결되지 않았습니다")
        if d["session_id"]:
            _, session = app._session(document_id, session_id, client_id, epoch, expected)
            blob = session["blob"]
        else:
            blob = d["source_sha256"]
        data = app.store.bytes(blob)
        source_format = d["source_format"]
    with tempfile.TemporaryDirectory(prefix="document-convert-") as folder:
        directory = Path(folder)
        if source_format == "typ":
            if output_format != "pdf":
                raise DocumentUnsupported("Typst는 PDF로 출력하세요")
            executable = shutil.which("typst")
            if not executable:
                raise DocumentUnsupported("Typst 컴파일러가 없습니다")
            source = directory / "main.typ"; source.write_bytes(data)
            result = subprocess.run([executable, "compile", "--root", str(directory), str(source), str(directory/"result.pdf")], capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise ValueError("컴파일 오류: " + result.stderr[-3000:])
            result_data = (directory/"result.pdf").read_bytes()
        else:
            if source_format in {"md", "markdown"}:
                executable = shutil.which("pandoc")
                if not executable:
                    raise DocumentUnsupported("Markdown 출력에는 Pandoc이 필요합니다")
                source = directory / "main.md"; source.write_bytes(data)
                result = subprocess.run([executable, "--sandbox", str(source), "-o", str(directory/"source.docx")], capture_output=True, text=True, timeout=60)
                if result.returncode:
                    raise ValueError("Markdown 변환 오류: " + result.stderr[-2000:])
                data = (directory/"source.docx").read_bytes(); source_format = "docx"
            if source_format == output_format:
                result_data = data
            else:
                cfg = settings()
                if not cfg:
                    raise DocumentUnsupported("로컬 문서 변환 엔진을 시작하세요")
                conversion = {"id": identifier(), "token": secrets.token_urlsafe(32),
                    "document_id": document_id, "blob": app.store.blob(data), "expires": time.time()+600}
                app.store.put("conversion", conversion)
                url = cfg["callback_origin"].rstrip("/")+"/documents/convert-io/"+conversion["id"]+"?ticket="+conversion["token"]
                request = {"async": False, "filetype": source_format, "outputtype": output_format,
                           "key": conversion["id"], "url": url, "title": d["title"]}
                request["token"] = jwt.encode(request, cfg["secret"], algorithm="HS256")
                response = httpx.post(cfg["url"].rstrip("/")+"/converter", json=request,
                    headers={"Accept":"application/json"}, timeout=180, trust_env=False)
                response.raise_for_status(); result = response.json()
                if not result.get("endConvert") or not result.get("fileUrl"):
                    raise DocumentUnsupported("변환 엔진이 이 문서를 출력하지 못했습니다: " + str(result.get("error", "변환 미완료")))
                result_data = download(result["fileUrl"], cfg)
    if output_format in {"docx", "pdf", "odt", "rtf"}:
        validate(result_data, output_format)
    from document_creation import import_bytes
    result = import_bytes(app, Path(d["title"]).stem+"_converted."+output_format, result_data)
    output = result["document"]
    output["provenance"] = {"resource_id": document_id, "revision_id": expected_revision,
        "snapshot_sha256": blob, "source_format": d["source_format"], "output_format": output_format,
        "original_preserved": True, "loss_report": "변환 후 쪽 배치·서식·주석을 확인하세요"}
    app.store.put("document", output)
    return result


def content(app, conversion_id, ticket):
    row = app.store.get("conversion", conversion_id)
    app._doc(row["document_id"])
    if row["expires"] < time.time() or not secrets.compare_digest(row["token"], ticket):
        raise PermissionError("변환 자료 접근 자격이 만료됐습니다")
    return app.store.bytes(row["blob"])
