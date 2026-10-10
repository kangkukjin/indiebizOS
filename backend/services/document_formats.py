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
                result_data = convert_bytes(app, document_id, data, source_format,
                                            output_format, d["title"])
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


def convert_bytes(app, document_id, data, source_format, output_format, title, metadata=None):
    """Shared engine transport for explicit exports and automatic import copies."""
    from document_pages import ImportFailure
    cfg = settings()
    if not cfg:
        raise ImportFailure("engine_unconfigured", "로컬 문서 엔진 설치가 필요합니다")
    if metadata is not None:
        metadata.update(probe_engine(cfg))
        if not metadata['engine_ready']:
            raise ImportFailure("engine_unreachable", "문서 엔진에 연결하지 못했습니다. 편집 서버 시작 후 다시 시도하세요")
    conversion = {"id": identifier(), "token": secrets.token_urlsafe(32),
                  "document_id": document_id, "blob": app.store.blob(data),
                  "expires": time.time() + 600}
    app.store.put("conversion", conversion)
    url = (cfg["callback_origin"].rstrip("/") + "/documents/convert-io/"
           + conversion["id"] + "?ticket=" + conversion["token"])
    request = {"async": False, "filetype": source_format, "outputtype": output_format,
               "key": conversion["id"], "url": url, "title": title}
    request["token"] = jwt.encode(request, cfg["secret"], algorithm="HS256")
    try:
        response = httpx.post(cfg["url"].rstrip("/") + "/converter", json=request,
                              headers={"Accept": "application/json"}, timeout=180, trust_env=False)
        response.raise_for_status()
        result = response.json()
        if not result.get("endConvert") or not result.get("fileUrl"):
            error = result.get("error")
            if error == -5:
                raise ImportFailure("password_required", "암호 문서는 Pages에서 DOCX로 내보낸 뒤 여세요")
            if error == -10:
                raise ImportFailure("input_too_large", "문서 엔진의 변환 크기 상한을 초과했습니다")
            if error == -2:
                raise ImportFailure("conversion_timeout", "문서 변환 시간이 초과됐습니다. 다시 시도하세요")
            raise ImportFailure("conversion_failed", f"문서 엔진이 변환하지 못했습니다 (코드 {error})")
        output = download(result["fileUrl"], cfg)
    except httpx.TimeoutException as exc:
        raise ImportFailure("conversion_timeout", "문서 변환 시간이 초과됐습니다. 다시 시도하세요") from exc
    except httpx.HTTPError as exc:
        raise ImportFailure("engine_unreachable", "문서 엔진에 연결하지 못했습니다. 편집 서버 시작 후 다시 시도하세요") from exc
    return output


_ENGINE_STATUS = {}


def probe_engine(cfg):
    """Version command is also a readiness probe; no document bytes are sent."""
    key = cfg['url']
    command = {'c': 'version'}
    command['token'] = jwt.encode(command, cfg['secret'], algorithm='HS256')
    try:
        response = httpx.post(key.rstrip('/') + '/command', json=command,
                              timeout=5, trust_env=False)
        response.raise_for_status()
        value = response.json()
        ready = value.get('error') == 0
        result = {'engine_ready': ready, 'engine_version': value.get('version', 'unknown'),
                  'engine_checked_at': time.time()}
    except (httpx.HTTPError, ValueError):
        result = {'engine_ready': False, 'engine_version': 'unknown', 'engine_checked_at': time.time()}
    _ENGINE_STATUS[key] = result
    return result


def engine_status():
    cfg = settings()
    if not cfg:
        return {'engine_ready': False}
    last = _ENGINE_STATUS.get(cfg['url'], {})
    return last if time.time() - last.get('engine_checked_at', 0) < 30 else {'engine_ready': None}
