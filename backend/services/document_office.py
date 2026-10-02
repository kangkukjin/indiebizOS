"""Local ONLYOFFICE adapter. Engine callbacks persist drafts; only owner saves publish.

A ticket is bound to one writer generation and expires. Engine downloads are
restricted to the configured origin, with redirects disabled and bounded bytes.
"""
import io
import json
import secrets
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import jwt

from office_store import digest, identifier
from office_sessions import DocumentConflict, DocumentUnsupported, MAX_BYTES
from runtime_utils import get_base_path

NATIVE = {"docx", "odt", "rtf", "pdf"}


def settings():
    path = Path(get_base_path()) / "data/document_workspace/engine.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    for name in ("url", "callback_origin"):
        uri = urlsplit(value[name])
        if uri.scheme not in {"http", "https"} or not uri.hostname or uri.username or uri.password:
            raise ValueError("문서 엔진 주소가 올바르지 않습니다")
    if len(value.get("secret", "")) < 32:
        raise ValueError("문서 엔진 인증 설정이 필요합니다")
    return value


def available():
    return settings() is not None


def validate(data, format):
    if len(data) > MAX_BYTES:
        raise ValueError("문서 크기 상한을 초과했습니다")
    if format == "pdf":
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.is_encrypted or not doc.page_count:
                raise DocumentUnsupported("암호 또는 빈 PDF는 먼저 확인하세요")
    elif format == "rtf":
        if not data.lstrip().startswith(b"{\\rtf"):
            raise ValueError("RTF 출력 형식이 일치하지 않습니다")
    elif format in {"docx", "odt"}:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 200 * 1024 * 1024:
                raise ValueError("문서 압축 해제 크기 상한을 초과했습니다")
            required = "word/document.xml" if format == "docx" else "content.xml"
            if required not in archive.namelist():
                raise ValueError("문서 출력 형식이 일치하지 않습니다")
            from defusedxml.ElementTree import fromstring
            fromstring(archive.read(required))
            if format == "odt" and archive.read("mimetype") != b"application/vnd.oasis.opendocument.text":
                raise ValueError("ODT 미디어 유형이 일치하지 않습니다")
    else:
        raise DocumentUnsupported("원형 저장이 검증되지 않은 형식입니다")


def _origin(url):
    p = urlsplit(url)
    return p.scheme, p.hostname, p.port or (443 if p.scheme == "https" else 80)


def download(url, config):
    if _origin(url) != _origin(config["url"]) or urlsplit(url).username:
        raise PermissionError("허용되지 않은 편집 엔진 다운로드 주소입니다")
    with httpx.stream("GET", url, timeout=60, follow_redirects=False, trust_env=False) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ValueError("문서 크기 상한을 초과했습니다")
    return bytes(data)


class OfficeEngine:
    native_formats = NATIVE
    namespace = 'documents'
    editor_type = 'word'
    plugin_guid = 'asc.{49DC913A-68D4-44AA-8A07-88107E1F9012}'

    def __init__(self, app):
        self.app, self.store = app, app.store

    def config(self, document_id, session_id, client_id, epoch, expected, browser_origin, browser_api_origin):
        cfg = settings()
        if not cfg:
            raise DocumentUnsupported("로컬 문서 엔진을 시작하세요")
        with self.store.lock():
            d, s = self.app._session(document_id, session_id, client_id, epoch, expected)
            if d["source_format"] not in self.native_formats:
                raise DocumentUnsupported("이 형식의 원형 편집 엔진이 없습니다")
            if s.get("engine_closed"):
                s.update(engine_epoch=identifier(), engine_closed=False)
            if (not s.get("ticket") or s.get("key_epoch") != s["engine_epoch"]
                    or s.get("ticket_expires", 0) < time.time()):
                s.update(ticket=secrets.token_urlsafe(32), ticket_expires=time.time() + 8 * 3600)
            if not s.get("engine_key") or s.get("key_epoch") != s["engine_epoch"]:
                s.update(engine_key=identifier(), key_epoch=s["engine_epoch"], engine_base_blob=s["blob"])
            self.store.put("session", s)
            base = cfg["callback_origin"].rstrip("/") + "/" + self.namespace + "/engine-io/" + s["id"]
            token = s["ticket"]
            options = {"documentType": "pdf" if d["source_format"] == "pdf" else self.editor_type,
                "width": "100%", "height": "100%", "type": "desktop",
                "document": {"fileType": d["source_format"], "key": s["engine_key"],
                    "title": d["title"], "url": base + "/content?ticket=" + token,
                    "permissions": {"edit": True, "download": True, "print": True, "review": True}},
                "editorConfig": {"lang": "ko", "mode": "edit",
                    "callbackUrl": base + "/callback?ticket=" + token,
                    "user": {"id": client_id, "name": "문서 작성자"},
                    "customization": {"forcesave": False, "autosave": True, "macros": False, "macrosMode": "disable",
                        "close": {"visible": True}},
                    "coEditing": {"mode": "fast", "change": False}}}
            if d["source_format"] != "pdf":
                from urllib.parse import urlencode
                s["plugin_parent"] = browser_origin
                self.store.put("session", s)
                plugin = browser_api_origin.rstrip("/") + "/" + self.namespace + "/engine-io/" + s["id"] + "/plugin/" + token + "/config.json"
                options["editorConfig"]["plugins"] = {"autostart": [self.plugin_guid], "pluginsData": [plugin]}
            options["token"] = jwt.encode(options, cfg["secret"], algorithm="HS256")
            return {"url": cfg["url"], "config": options, "session": s, "plugin": {"channel": token, "origin": browser_api_origin}}

    def ticket(self, session_id, token):
        s = self.store.get("session", session_id)
        if (not isinstance(token, str) or not secrets.compare_digest(s.get("ticket", ""), token)
                or not token or s.get("ticket_expires", 0) < time.time()):
            raise PermissionError("문서 엔진 접근 자격이 만료됐습니다")
        d = self.store.get("document", s["document_id"])
        if (d["session_id"] != session_id or s.get("key_epoch") != s["engine_epoch"]
                or s.get("engine_closed")):
            raise DocumentConflict("종료되거나 교체된 편집 세션입니다")
        return d, s

    def content(self, session_id, token):
        d, s = self.ticket(session_id, token)
        return self.store.bytes(s["engine_base_blob"]), d["title"]

    def callback(self, session_id, token, body, authorization=""):
        cfg = settings()
        signed = body.get("token") or authorization.removeprefix("Bearer ")
        try:
            claims = jwt.decode(signed, cfg["secret"], algorithms=["HS256"], leeway=5)
        except (jwt.PyJWTError, TypeError) as exc:
            raise PermissionError("문서 엔진 서명이 올바르지 않습니다") from exc
        payload = claims.get("payload", claims)
        if any(payload.get(k) != v for k, v in body.items() if k != "token"):
            raise PermissionError("서명과 콜백 내용이 다릅니다")
        body = payload
        d, s = self.ticket(session_id, token)
        if body.get("key") != s["engine_key"]:
            raise DocumentConflict("편집 세대가 다른 콜백입니다")
        status = body.get("status")
        if status in {3, 7}:
            raise DocumentConflict("편집 엔진이 저장 실패를 보고했습니다")
        if status not in {2, 6}:
            return {"error": 0}
        if body.get("filetype") != d["source_format"]:
            raise DocumentUnsupported("엔진 출력 형식이 원본과 다릅니다. 원본을 보존했습니다")
        data = download(body["url"], cfg)
        self.app.validate_output(d, data)
        with self.store.lock():
            d, s = self.ticket(session_id, token)  # Fence again after network I/O.
            signature = digest(json.dumps(body, sort_keys=True).encode())
            if signature in s.get("callbacks", []):
                return {"error": 0}
            sequence = s.get("capture_requests", {}).get(body.get("userdata"), 0)
            if status == 6 and s.get("capture_requests") and sequence <= s.get("captured_sequence", 0):
                # A slow older force-save must not roll a newer draft backward.
                # Keep its receipt so the old waiter can finish against the
                # current revision, whose conditional publication is separate.
                s["capture_ids"] = (s.get("capture_ids", []) + [body.get("userdata")])[-64:]
                self.store.put("session", s)
                return {"error": 0}
            key = self.store.blob(data)
            if status == 2 and s.get('captured_sequence', 0) and key != s['blob']:
                # Terminal callbacks have no force-save sequence. Never let an
                # unorderable close overwrite the last confirmed capture.
                recovery = {'id': digest((session_id+':'+key).encode()), 'document_id':d['id'],
                            'blob':key, 'created_at':time.time(), 'is_recovery':True,
                            'engine_epoch':s['engine_epoch'], 'confirmed_blob':s['blob'], 'label':'엔진 종료 복구 후보'}
                confirmed={**recovery,'id':digest((session_id+':confirmed:'+s['blob']).encode()),
                           'blob':s['blob'],'label':'마지막 확인 초안'}
                s.update(engine_closed=True, state='recovering',
                         callbacks=(s.get('callbacks', [])+[signature])[-64:])
                with self.store.connect() as conn:
                    self.store.put('engine_recovery', recovery, conn)
                    self.store.put('engine_recovery', confirmed, conn)
                    self.store.put('session', s, conn)
                    self.store.event(d['id'], {'type':'engine_recovery_available','recovery_id':recovery['id']}, conn)
                return {'error':0}
            s.update(blob=key, session_revision=s["session_revision"] + 1,
                     state="recovering" if s.get("state") == "recovering" else "saved" if key == d["source_sha256"] else "draft",
                     capture_id=body.get("userdata"), captured_at=time.time(),
                     capture_ids=(s.get("capture_ids", []) + [body.get("userdata")])[-64:],
                     captured_sequence=max(sequence, s.get("captured_sequence", 0)),
                     callbacks=(s.get("callbacks", []) + [signature])[-64:])
            if status == 2:
                s["engine_closed"] = True
            with self.store.connect() as conn:
                self.store.put("session", s, conn)
                self.store.event(d["id"], {"type": "engine_draft", "session_revision": s["session_revision"]}, conn)
        return {"error": 0}

    def capture(self, document_id, session_id, client_id, epoch, expected, operation_id):
        if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 128:
            raise ValueError("저장 작업 식별자를 확인하세요")
        cfg = settings()
        with self.store.lock():
            d, s = self.app._session(document_id, session_id, client_id, epoch, expected)
            if s.get("engine_closed"):
                return {"session": s}
            key = s.get("engine_key")
            if not key:
                raise DocumentConflict("편집 엔진이 아직 연결되지 않았습니다")
            sequence = s.get("command_sequence", 0) + 1
            requests = s.get("capture_requests", {})
            requests[operation_id] = sequence
            s.update(command_sequence=sequence, capture_requests=dict(list(requests.items())[-64:]))
            self.store.put("session", s)
        command = {"c": "forcesave", "key": key, "userdata": operation_id}
        command["token"] = jwt.encode(command, cfg["secret"], algorithm="HS256")
        response = httpx.post(cfg["url"].rstrip("/") + "/coauthoring/CommandService.ashx",
                              json=command, timeout=20, trust_env=False)
        response.raise_for_status()
        result = response.json()
        if result.get("error") == 4:  # No server-side changes; client still owns unsent keystrokes.
            return {"session": self.store.get("session", session_id), "unchanged": True}
        if result.get("error") != 0:
            raise DocumentConflict("문서 엔진 저장 요청 실패: " + str(result.get("error")))
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            s = self.store.get("session", session_id)
            if s["engine_epoch"] != epoch:
                raise DocumentConflict("저장 대기 중 편집 세대가 바뀌었습니다")
            if operation_id in s.get("capture_ids", []):
                return {"session": s}
            time.sleep(.2)
        raise DocumentConflict("편집 엔진의 저장 확인이 지연됐습니다. 원본 저장 완료로 처리하지 않습니다")
