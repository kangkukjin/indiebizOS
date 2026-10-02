"""Owner-scoped file identities and immutable revisions shared by office apps.

The historical state.db location and object schema remain unchanged. A file's
path identifies registration; equal hashes never merge distinct resources.
"""
import time
from pathlib import Path

import principal
from office_store import identifier


class OfficeResources:
    def __init__(self, store):
        self.store = store

    def get(self, resource_id):
        if not principal.is_owner():
            raise PermissionError("자료 작업 공간은 소유자 전용입니다")
        row = self.store.get("document", resource_id)
        if row["owner"] != principal.cache_key():
            raise PermissionError("이 자료의 소유자가 아닙니다")
        return row

    def register(self, path, data, encoding=None):
        """Caller holds the shared writer lock and validates the file bytes."""
        if not principal.is_owner():
            raise PermissionError("자료 작업 공간은 소유자 전용입니다")
        path = Path(path)
        for row in self.store.list("document"):
            if row["owner"] == principal.cache_key() and row["source_uri"] == str(path):
                return row
        key, revision = self.store.blob(data), identifier()
        row = {"id": identifier(), "owner": principal.cache_key(), "title": path.name,
               "source_uri": str(path), "source_format": path.suffix.lower().lstrip("."),
               "source_sha256": key, "revision_id": revision, "encoding": encoding,
               "session_id": None, "created_at": time.time()}
        with self.store.connect() as conn:
            self.store.put("document", row, conn)
            self.store.put("revision", {"id": revision, "document_id": row["id"],
                "parent_revision_id": None, "blob": key, "created_at": time.time()}, conn)
        return row

    def revision(self, resource_id, revision_id):
        document = self.get(resource_id)
        revision = self.store.get("revision", revision_id)
        if revision["document_id"] != resource_id:
            raise PermissionError("다른 자료의 버전입니다")
        return document, revision, self.store.bytes(revision["blob"])
