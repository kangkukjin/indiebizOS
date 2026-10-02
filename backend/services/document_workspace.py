"""Document sessions and exclusive copy saves. Source editing is implemented.
Conditional replacement of the original is unavailable and explicitly blocked.

Office/PDF/Hancom capabilities remain unavailable until real adapters pass the
engine acceptance contract. This service never converts those files silently.
"""
import codecs
import json
import os
import tempfile
import time
from pathlib import Path

import principal
from document_store import DocumentStore, digest, identifier, sync_directory

SOURCE_FORMATS = {"txt", "md", "markdown", "html", "htm", "tex", "typ"}
ENCODINGS = {"utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp949", "euc-kr"}
MAX_BYTES = 25 * 1024 * 1024


class DocumentConflict(ValueError):
    pass


class DocumentUnsupported(ValueError):
    pass


def owner():
    if not principal.is_owner():
        raise PermissionError("문서 작업 공간은 현재 소유자 전용입니다")


def read_bytes(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError("일반 문서 파일을 선택하세요")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise DocumentUnsupported("현재 작업 공간의 파일 상한은 25MB입니다")
    return data


def decode_source(data, encoding=None):
    if encoding is None:
        if data.startswith(codecs.BOM_UTF8):
            encoding = "utf-8-sig"
        elif data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            encoding = "utf-16"
        else:
            encoding = "utf-8"
    if encoding not in ENCODINGS:
        raise ValueError("지원하지 않는 인코딩입니다")
    try:
        text = data.decode(encoding, errors="strict")
    except UnicodeError as exc:
        raise DocumentUnsupported("인코딩을 확인하세요. CP949/EUC-KR는 직접 선택해야 합니다") from exc
    if "\x00" in text:
        raise DocumentUnsupported("바이너리 데이터를 소스 문서로 편집할 수 없습니다")
    # Python's UTF-16 encoder uses host byte order. Preserve the source order.
    if encoding == "utf-16":
        encoding = "utf-16-be" if data.startswith(codecs.BOM_UTF16_BE) else "utf-16-le"
        text = "\ufeff" + text
    return text, encoding


class DocumentWorkspace:
    def __init__(self, root=None):
        self.store = DocumentStore(root)

    def _doc(self, document_id):
        owner()
        row = self.store.get("document", document_id)
        if row["owner"] != principal.cache_key():
            raise PermissionError("이 문서의 소유자가 아닙니다")
        return row

    def list(self):
        owner()
        return [d for d in self.store.list("document") if d["owner"] == principal.cache_key()]

    def capabilities(self, document_id):
        d = self._doc(document_id)
        source = d["source_format"] in SOURCE_FORMATS
        engine = "source" if source else "hancom" if d["source_format"] in {"hwp", "hwpx"} else "office"
        reason = "소스 원문 편집" if source else "편집 엔진 연결·라이선스·실파일 왕복 검증 미확보"
        return {"engine": engine, "edit_native": source, "save": False, "export_copy": source,
                "ai_text_replace": source, "structural_edit": False,
                "reason": reason, "loss_report": {"status": "unverified", "items": []},
                "unavailable": ["office", "hancom", "pdf_edit", "ocr_correction", "compile", "format_export"]}

    def open(self, path, encoding=None):
        owner()
        original = Path(path).expanduser()
        if original.is_symlink():
            raise ValueError("심볼릭 링크 대신 실제 문서 경로를 선택하세요")
        path = original.resolve(strict=True)
        data = read_bytes(path)
        with self.store.lock():
            for row in self.list():
                if row["source_uri"] == str(path):
                    return self.detail(row["id"])
            extension = path.suffix.lower().lstrip(".")
            chosen = None
            if extension in SOURCE_FORMATS:
                _, chosen = decode_source(data, encoding)
            key = self.store.blob(data)
            revision = identifier()
            row = {"id": identifier(), "owner": principal.cache_key(), "title": path.name,
                   "source_uri": str(path), "source_format": extension, "source_sha256": key,
                   "revision_id": revision, "encoding": chosen, "session_id": None,
                   "created_at": time.time()}
            with self.store.connect() as conn:
                self.store.put("document", row, conn)
                self.store.put("revision", {"id": revision, "document_id": row["id"],
                    "parent_revision_id": None, "blob": key, "created_at": time.time()}, conn)
            return self.detail(row["id"])

    def detail(self, document_id):
        d = self._doc(document_id)
        session = self.store.get("session", d["session_id"]) if d["session_id"] else None
        result = {"document": d, "session": session, "capabilities": self.capabilities(document_id)}
        if session and d["encoding"]:
            result["text"] = self.store.bytes(session["blob"]).decode(d["encoding"])
        return result

    def acquire(self, document_id, client_id):
        if not isinstance(client_id, str) or not 1 <= len(client_id) <= 128:
            raise ValueError("작성 창 식별자가 필요합니다")
        with self.store.lock():
            d = self._doc(document_id)
            if not self.capabilities(document_id)["edit_native"]:
                raise DocumentUnsupported(self.capabilities(document_id)["reason"])
            if d["session_id"]:
                s = self.store.get("session", d["session_id"])
                if s["client_id"] != client_id:
                    raise DocumentConflict("다른 창이 작성 중입니다. 그 창에서 저장·닫기를 완료하세요")
            else:
                s = {"id": identifier(), "document_id": document_id, "client_id": client_id,
                     "engine_id": "source", "engine_epoch": identifier(), "session_revision": 0,
                     "blob": d["source_sha256"], "saved_blob": d["source_sha256"],
                     "state": "saved", "created_at": time.time()}
                d["session_id"] = s["id"]
                with self.store.connect() as conn:
                    self.store.put("session", s, conn)
                    self.store.put("document", d, conn)
            return self.detail(document_id)

    def reclaim(self, document_id, client_id, expected_epoch):
        """Explicit owner recovery fences the old window; it never overwrites bytes."""
        if not isinstance(client_id, str) or not 1 <= len(client_id) <= 128:
            raise ValueError("작성 창 식별자가 필요합니다")
        with self.store.lock():
            d = self._doc(document_id)
            if not d["session_id"]:
                raise DocumentConflict("복구할 활성 세션이 없습니다")
            s = self.store.get("session", d["session_id"])
            if s["engine_epoch"] != expected_epoch:
                raise DocumentConflict("이미 다른 창에서 세션을 복구했습니다")
            s.update(client_id=client_id, engine_epoch=identifier())
            self.store.put("session", s)
            return self.detail(document_id)

    def _session(self, document_id, session_id, client_id, epoch, expected):
        d = self._doc(document_id)
        if d["session_id"] != session_id:
            raise DocumentConflict("편집 세션이 바뀌었습니다")
        s = self.store.get("session", session_id)
        if s["client_id"] != client_id or s["engine_epoch"] != epoch:
            raise DocumentConflict("작성 창 또는 엔진 세대가 바뀌었습니다")
        if s["session_revision"] != expected:
            raise DocumentConflict("편집 버전이 바뀌었습니다. 현재 내용을 다시 읽으세요")
        return d, s

    def _operation(self, document_id, operation_id, payload):
        if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 128:
            raise ValueError("작업 식별자가 필요합니다")
        fingerprint = digest(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode())
        key = digest((document_id + ":" + operation_id).encode())
        try:
            op = self.store.get("operation", key)
        except ValueError:
            return {"id": key, "document_id": document_id, "fingerprint": fingerprint}, None
        if op["fingerprint"] != fingerprint:
            raise DocumentConflict("같은 작업 식별자가 다른 요청에 사용됐습니다")
        return op, op.get("result")

    def draft(self, document_id, session_id, client_id, epoch, expected, operation_id, text):
        owner()
        payload = ["draft", session_id, client_id, epoch, expected, text]
        with self.store.lock():
            self._doc(document_id)
            op, cached = self._operation(document_id, operation_id, payload)
            if cached is not None:
                return cached
            d, s = self._session(document_id, session_id, client_id, epoch, expected)
            data = text.encode(d["encoding"], errors="strict")
            if len(data) > MAX_BYTES:
                raise ValueError("문서 크기 상한을 초과했습니다")
            s.update(blob=self.store.blob(data), session_revision=expected + 1, state="draft")
            result = {"session": s, "source_sha256": d["source_sha256"]}
            op["result"] = result
            with self.store.connect() as conn:
                self.store.put("session", s, conn)
                self.store.put("operation", op, conn)
                self.store.event(document_id, {"type": "draft", "operation_id": operation_id,
                    "session_revision": s["session_revision"]}, conn)
            return result

    def snapshot(self, document_id, session_id, client_id, epoch, expected):
        # The browser must finish IME and acknowledge draft() before this barrier.
        # No endpoint claims to see characters that have not reached the server.
        with self.store.lock():
            d, s = self._session(document_id, session_id, client_id, epoch, expected)
            row = {"id": identifier(), "document_id": document_id, "session_id": session_id,
                   "engine_epoch": epoch, "session_revision": expected, "blob": s["blob"],
                   "revision_id": d["revision_id"], "created_at": time.time()}
            self.store.put("snapshot", row)
            return row

    def read(self, document_id, snapshot_id):
        d = self._doc(document_id)
        row = self.store.get("snapshot", snapshot_id)
        if row["document_id"] != document_id:
            raise PermissionError("다른 문서의 스냅샷입니다")
        return {"snapshot": row, "text": self.store.bytes(row["blob"]).decode(d["encoding"])}

    def propose(self, document_id, snapshot_id, start, end, selected_sha256, replacement):
        data = self.read(document_id, snapshot_id)
        text = data["text"]
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(text):
            raise ValueError("잘못된 선택 범위입니다")
        selected = text[start:end]
        if digest(selected.encode()) != selected_sha256:
            raise DocumentConflict("선택 내용의 해시가 일치하지 않습니다")
        row = {"id": identifier(), "document_id": document_id, "snapshot_id": snapshot_id,
               "start": start, "end": end, "selected_sha256": selected_sha256,
               "replacement": replacement, "created_at": time.time()}
        self.store.put("proposal", row)
        return row

    def apply(self, document_id, proposal_id, session_id, client_id, epoch, expected, operation_id):
        # Inline draft transaction avoids a nested process lock.
        with self.store.lock():
            self._doc(document_id)
            op, cached = self._operation(document_id, operation_id,
                ["apply", proposal_id, session_id, client_id, epoch, expected])
            if cached is not None:
                return cached
            d, s = self._session(document_id, session_id, client_id, epoch, expected)
            p = self.store.get("proposal", proposal_id)
            snap = self.store.get("snapshot", p["snapshot_id"])
            if (p["document_id"] != document_id or snap["session_id"] != session_id
                    or snap["engine_epoch"] != epoch or snap["session_revision"] != expected):
                raise DocumentConflict("제안 이후 문서가 바뀌었습니다. 제안을 다시 생성하세요")
            text = self.store.bytes(s["blob"]).decode(d["encoding"])
            if digest(text[p["start"]:p["end"]].encode()) != p["selected_sha256"]:
                raise DocumentConflict("선택 내용이 바뀌었습니다")
            changed = text[:p["start"]] + p["replacement"] + text[p["end"]:]
            data = changed.encode(d["encoding"], errors="strict")
            if len(data) > MAX_BYTES:
                raise ValueError("문서 크기 상한을 초과했습니다")
            before = s["blob"]
            s.update(blob=self.store.blob(data), session_revision=expected + 1, state="draft")
            result = {"session": s, "text": changed, "undo_blob": before}
            op["result"] = result
            with self.store.connect() as conn:
                self.store.put("session", s, conn)
                self.store.put("operation", op, conn)
                self.store.event(document_id, {"type": "proposal_applied", "proposal_id": proposal_id,
                    "operation_id": operation_id, "session_revision": s["session_revision"]}, conn)
            return result

    def save(self, document_id, session_id, client_id, epoch, expected, operation_id, expected_revision):
        self._session(document_id, session_id, client_id, epoch, expected)
        raise DocumentUnsupported(
            "외부 수정과 원자적으로 비교·교체할 수 없어 원본 저장을 차단했습니다. 사본 저장을 사용하세요")

    def export_copy(self, document_id, session_id, client_id, epoch, expected, operation_id, filename):
        if (not filename or Path(filename).name != filename or filename in {".", ".."}
                or "/" in filename or "\\" in filename):
            raise ValueError("같은 폴더에 저장할 새 파일명만 입력하세요")
        with self.store.lock():
            self._doc(document_id)
            op, cached = self._operation(document_id, operation_id,
                ["export_copy", session_id, client_id, epoch, expected, filename])
            if cached is not None:
                return cached
            d, s = self._session(document_id, session_id, client_id, epoch, expected)
            path = Path(d["source_uri"]).parent / filename
            if path.suffix.lower().lstrip(".") != d["source_format"]:  # vj-ok: 파일 확장자 식별 규약
                raise DocumentUnsupported("사본은 같은 형식으로 저장하세요. 형식 변환은 아직 지원하지 않습니다")
            if path.exists() or path.is_symlink():
                raise DocumentConflict("이미 있는 파일은 덮어쓰지 않습니다")
            data = self.store.bytes(s["blob"])
            data.decode(d["encoding"], errors="strict")
            op.update(status="prepared", blob=s["blob"], output=str(path), session_id=session_id)
            self.store.put("operation", op)
            fd, temporary = tempfile.mkstemp(prefix=".indiebiz-document-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Atomic, exclusive publication. A concurrent creator wins;
                # neither the original nor an existing destination is replaced.
                os.link(temporary, path)
                sync_directory(path.parent)
                if digest(read_bytes(path)) != s["blob"]:
                    raise DocumentConflict("생성된 사본이 외부에서 변경됐습니다. 초안을 보존했습니다")
                return self._finish_export(op)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def _finish_export(self, op):
        op.update(status="committed", result={"path": op["output"], "sha256": op["blob"],
                  "state": "copy_saved", "original_unchanged": True})
        with self.store.connect() as conn:
            self.store.put("operation", op, conn)
            self.store.event(op["document_id"], {"type": "copy_saved", "path": op["output"]}, conn)
        return op["result"]

    def recover(self, document_id):
        with self.store.lock():
            self._doc(document_id)
            results = []
            for op in self.store.list("operation"):
                if op["document_id"] != document_id or op.get("status") != "prepared":
                    continue
                path = Path(op["output"])
                if path.is_file() and not path.is_symlink() and digest(read_bytes(path)) == op["blob"]:
                    results.append(self._finish_export(op))
                else:
                    op["status"] = "conflict" if path.exists() else "not_written"
                    self.store.put("operation", op)
                    results.append({"state": op["status"], "draft_preserved": True})
            return {"items": results, "detail": self.detail(document_id)}

    def versions(self, document_id):
        self._doc(document_id)
        return [r for r in self.store.list("revision") if r["document_id"] == document_id]

    def restore(self, document_id, revision_id, session_id, client_id, epoch, expected, operation_id):
        d = self._doc(document_id)
        revision = self.store.get("revision", revision_id)
        if revision["document_id"] != document_id:
            raise PermissionError("다른 문서의 버전입니다")
        return self.draft(document_id, session_id, client_id, epoch, expected, operation_id,
                          self.store.bytes(revision["blob"]).decode(d["encoding"]))

    def close(self, document_id, session_id, client_id, epoch, expected):
        with self.store.lock():
            d, s = self._session(document_id, session_id, client_id, epoch, expected)
            if s["blob"] != d["source_sha256"]:
                raise DocumentConflict("초안이 남아 있습니다. 먼저 파일을 저장하세요")
            if any(o.get("status") == "prepared" and o["document_id"] == document_id
                   for o in self.store.list("operation")):
                raise DocumentConflict("미완료 저장을 먼저 복구하세요")
            d["session_id"] = None
            self.store.put("document", d)
            return {"closed": True}
