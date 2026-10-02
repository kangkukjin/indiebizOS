"""Shared writer fencing, idempotency, atomic publication and crash recovery.

Format adapters supply _doc, _session, capabilities and validated draft bytes.
External writers do not share this lock; hash checks are best effort, not CAS.
"""
import json
import os
import tempfile
import time
from pathlib import Path

import principal
from office_store import digest, identifier, sync_directory

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



class OfficeSessions:
    def versions(self, document_id):
        self._doc(document_id)
        revisions = [r for r in self.store.list("revision") if r["document_id"] == document_id]
        recovery = [r for r in self.store.list("engine_recovery") if r["document_id"] == document_id]
        return revisions + recovery

    def restore(self, document_id, revision_id, session_id, client_id, epoch, expected, operation_id):
        d = self._doc(document_id)
        try:
            revision = self.store.get("revision", revision_id)
        except ValueError:
            revision = self.store.get("engine_recovery", revision_id)
        if revision["document_id"] != document_id:
            raise PermissionError("다른 문서의 버전입니다")
        if d["encoding"]:
            return self.draft(document_id, session_id, client_id, epoch, expected, operation_id,
                              self.store.bytes(revision["blob"]).decode(d["encoding"]))
        with self.store.lock():
            op, cached = self._operation(document_id, operation_id,
                ["restore", revision_id, session_id, client_id, epoch, expected])
            if cached is not None:
                return cached
            d, s = self._session(document_id, session_id, client_id, epoch, expected)
            self.validate_output(d, self.store.bytes(revision["blob"]))
            s.update(blob=revision["blob"], engine_epoch=identifier(), session_revision=expected + 1,
                     state="draft", engine_closed=False)
            op["result"] = {"session": s}
            with self.store.connect() as conn:
                self.store.put("session", s, conn)
                self.store.put("operation", op, conn)
            return op["result"]

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
                     "engine_id": "source" if d["encoding"] else "office", "engine_epoch": identifier(), "session_revision": 0,
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

    def save(self, document_id, session_id, client_id, epoch, expected, operation_id, expected_revision):
        """One writer inside this service; external writers require hash rechecks.

        A prepared intent is never replayed against the filesystem. Recovery
        observes the output hash and only finalizes metadata, or reports a
        conflict. Immutable blobs retain both the base and the edited bytes.
        """
        with self.store.lock():
            self._doc(document_id)
            op, cached = self._operation(document_id, operation_id,
                ["save", session_id, client_id, epoch, expected, expected_revision])
            if cached is not None:
                return cached
            d, s = self._session(document_id, session_id, client_id, epoch, expected)
            if s.get("state") == "recovering":
                raise DocumentConflict("엔진 종료 복구본과 확인된 초안을 비교하고 버전 이력에서 복구를 선택하세요")
            if d["revision_id"] != expected_revision:
                raise DocumentConflict("원본 버전이 바뀌었습니다. 현재 버전을 확인하세요")
            if any(o.get("status") == "prepared" and o["document_id"] == document_id
                   for o in self.store.list("operation")):
                raise DocumentConflict("미완료 저장을 먼저 복구하세요. 원본을 다시 쓰지 않습니다")
            if not self.capabilities(document_id)["save"]:
                raise DocumentUnsupported("이 형식의 원본 저장은 아직 지원하지 않습니다")
            path = Path(d["source_uri"])
            original = read_bytes(path)
            if digest(original) != d["source_sha256"]:
                raise DocumentConflict("외부에서 원본이 바뀌었습니다. 초안을 보존했습니다. 사본 저장을 사용하세요")
            # Retain the confirmed base even if publication or metadata fails.
            self.store.blob(original)
            data = self.store.bytes(s["blob"])
            self.validate_output(d, data)
            op.update(kind="save", status="prepared", blob=s["blob"], output=str(path),
                      session_id=session_id, parent_revision_id=expected_revision,
                      base_sha256=d["source_sha256"], revision_id=identifier(),
                      created_at=time.time())
            self.store.put("operation", op)
            fd, temporary = tempfile.mkstemp(prefix=".indiebiz-document-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, path.stat().st_mode & 0o777)
                if digest(read_bytes(path)) != op["base_sha256"]:
                    op["status"] = "conflict"
                    self.store.put("operation", op)
                    raise DocumentConflict("저장 직전 외부 수정이 발견됐습니다. 원본과 초안을 보존했습니다")
                # This is atomic publication, not an OS compare-and-swap with
                # arbitrary external writers. The UI states that limitation.
                os.replace(temporary, path)
                sync_directory(path.parent)
                if digest(read_bytes(path)) != op["blob"]:
                    raise DocumentConflict("저장 후 원본이 바뀌었습니다. 초안을 보존하고 복구를 기다립니다")
                return self._finish_save(op)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def _finish_save(self, op):
        d = self._doc(op["document_id"])
        if d["revision_id"] != op["parent_revision_id"]:
            raise DocumentConflict("저장 확정 기준이 바뀌었습니다. 원본은 다시 쓰지 않습니다")
        d.update(source_sha256=op["blob"], revision_id=op["revision_id"])
        s = self.store.get("session", op["session_id"])
        s.update(saved_blob=op["blob"], state="saved" if s["blob"] == op["blob"] else "draft")
        result = {"state": "saved", "path": op["output"], "sha256": op["blob"],
                  "revision_id": op["revision_id"], "session": s}
        op.update(status="committed", result=result)
        with self.store.connect() as conn:
            self.store.put("document", d, conn)
            self.store.put("session", s, conn)
            self.store.put("revision", {"id": op["revision_id"], "document_id": d["id"],
                "parent_revision_id": op["parent_revision_id"], "blob": op["blob"],
                "created_at": op["created_at"]}, conn)
            self.store.put("operation", op, conn)
            self.store.event(d["id"], {"type": "saved", "operation_id": op["id"],
                "revision_id": op["revision_id"]}, conn)
        return result

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
                raise DocumentUnsupported("사본은 같은 형식으로 저장하세요. 형식 변환은 내보내기를 사용하세요")
            if path.exists() or path.is_symlink():
                raise DocumentConflict("이미 있는 파일은 덮어쓰지 않습니다")
            data = self.store.bytes(s["blob"])
            self.validate_output(d, data)
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
                    sync_directory(path.parent)
                    results.append(self._finish_save(op) if op.get("kind") == "save" else self._finish_export(op))
                else:
                    op["status"] = "conflict" if path.exists() else "not_written"
                    self.store.put("operation", op)
                    results.append({"state": op["status"], "draft_preserved": True})
            return {"items": results, "detail": self.detail(document_id)}

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
