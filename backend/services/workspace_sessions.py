"""범용 작업 공간 — 자료 종류 무관의 열기·스냅샷·읽기·제안·적용·저장·버전·복구 (2026-10-05).

왜 (docs/APP_COMPOSITION_ON_IBL_PLAN_2026_10_05.md §3-a): 문서·스프레드시트·코딩 앱이 각자
작업 공간·저장소·HTTP 작업표를 가졌고 어휘는 그 서비스 메서드를 1:1 로 되비췄다. 이 모듈은
**하나의 작업 공간 계약** 아래 종류별 어댑터(document=소스/사무/한글/PDF · sheet · code=git
worktree)를 두고, 언어(`[self:workspace]`)에는 의도 고도의 op 만 보인다 —
`session_id·client_id·epoch·expected·operation_id` 같은 엔진 배관은 여기서 해소한다.

- 기존 `office_sessions`·`office_store`(문서·시트)와 `coding_workspace`·`coding_store`(코딩)를
  **그대로 재사용**한다. 새 저장소·새 잠금은 없다. 엔진(ONLYOFFICE·RHWP·시트 엔진·git)은 어댑터 밑.
- 작성 창(UI)이 세션을 쥐고 있으면 빼앗지 않는다. 읽기·제안은 세션 없이 되고, 적용·저장·내보내기·
  복구·닫기는 세션 소유 창의 `client` 로만 된다(인자 없으면 행위자 신원으로 세션을 얻되 다른 창이
  쥐고 있으면 거절). 시트 엔진의 비동기 접수(queued)는 그대로 알린다 — 접수는 완료가 아니다.
- 결과 통화: `{resource, kind, revision, ...}` 공통 머리 + op 별 본문(text/blocks/table/items).
"""
import json
import time
from pathlib import Path

from office_sessions import DocumentConflict, DocumentUnsupported
from office_store import digest, identifier

KINDS = ("document", "sheet", "code")
SHEET_SUFFIXES = {".xlsx", ".xlsm", ".xlsb", ".xls", ".ods", ".fods", ".csv", ".tsv", ".xltx", ".xltm", ".ots", ".numbers", ".cell", ".nxl"}
SNAPSHOT_WAIT_MAX = 30
WRITE_OPS = {"apply", "save", "export", "restore", "close"}


def actor_client() -> str:
    """세션을 얻을 때 쓰는 행위자 신원(작성 창 ID 가 없을 때). 모델이 임의로 바꾸지 않는다."""
    from thread_context import get_current_agent_id, get_current_task_id
    return f"ibl:{get_current_agent_id() or 'system_ai'}:{get_current_task_id() or '-'}"[:128]


def operation_key(op: str, resource: str, args: dict) -> str:
    """멱등 작업 ID — 같은 호출(같은 op·자료·인자)은 같은 ID. 호출자가 배관 ID 를 들고 다니지 않는다."""
    body = json.dumps({"op": op, "resource": resource, "args": args}, sort_keys=True, ensure_ascii=False, default=str)
    return "ws_" + digest(body.encode())[:40]


def kind_of_path(path: Path) -> str:
    if path.is_dir():
        for parent in (path, *path.parents):
            if (parent / ".git").exists():
                return "code"
        raise DocumentUnsupported("폴더는 git 저장소일 때만 코딩 작업 공간으로 엽니다")
    return "sheet" if path.suffix.lower() in SHEET_SUFFIXES else "document"


class Workspace:
    def __init__(self, root=None, coding_store=None):
        self.root = root
        self._documents = self._sheets = self._code = None
        self._coding_store = coding_store

    # ── 어댑터 ──────────────────────────────────────────────────────────────
    def documents(self):
        if self._documents is None:
            from document_workspace import DocumentWorkspace
            self._documents = DocumentWorkspace(self.root)
        return self._documents

    def sheets(self):
        if self._sheets is None:
            from spreadsheet_workspace import SpreadsheetWorkspace
            self._sheets = SpreadsheetWorkspace(self.root)
        return self._sheets

    def code(self):
        if self._code is None:
            self._code = CodeAdapter(self._coding_store)
        return self._code

    def resolve(self, resource: str):
        """자료 ID → (kind, 어댑터, 행). 종류는 저장소가 안다 — 호출자가 kind 를 들고 다니지 않는다."""
        if not isinstance(resource, str) or not resource:
            raise ValueError("resource(자료 ID)가 필요합니다 — open 의 반환값")
        if resource.startswith("coding_"):
            return "code", self.code(), self.code().task(resource)
        store = self.documents().store
        try:
            row = store.get("document", resource)
        except ValueError:
            raise ValueError(f"작업 공간에 없는 자료입니다: {resource}. open 으로 먼저 등록하세요")
        if row.get("app") == "spreadsheet":
            return "sheet", self.sheets(), self.sheets()._doc(resource)
        return "document", self.documents(), self.documents()._doc(resource)

    # ── 공통 머리 ──────────────────────────────────────────────────────────
    @staticmethod
    def _sheet_receipt(row, result):
        """③ 시트 엔진 접수 → 공통 접수증 필드(task_ref{kind: sheet_op, owner: 자료 id}). 접수는 완료가 아니다."""
        import task_receipts
        op_id = (result or {}).get("operation_id")
        if not op_id:
            return {}
        return {"accepted": True, "state": task_receipts.QUEUED, "task_ref": task_receipts.ref("sheet_op", op_id, row["id"])}

    @staticmethod
    def head(kind, row, **extra):
        out = {"resource": row["id"], "kind": kind, "revision": row.get("revision_id"),
               "title": row.get("title"), "path": row.get("source_uri") or row.get("workspace")}
        out.update(extra)
        return out

    # ── open ────────────────────────────────────────────────────────────────
    def open(self, path, encoding=None, kind=None, goal=None):
        target = Path(path).expanduser()
        kind = kind or kind_of_path(target)
        if kind not in KINDS:
            raise ValueError("kind 는 document/sheet/code 입니다")
        if kind == "code":
            task = self.code().open(target, goal)
            return self.head("code", task, capabilities=self.code().capabilities(task))
        app = self.sheets() if kind == "sheet" else self.documents()
        detail = app.open(target) if kind == "sheet" else app.open(target, encoding)
        row = detail["document"]
        return self.head(kind, row, capabilities=self.capabilities(row["id"]), session=self._session_summary(detail.get("session")))

    @staticmethod
    def _session_summary(session):
        if not session:
            return None
        return {"held_by": session.get("client_id"), "state": session.get("state"),
                "session_revision": session.get("session_revision")}

    def capabilities(self, resource):
        kind, app, row = self.resolve(resource)
        if kind == "code":
            return app.capabilities(row)
        caps = dict(app.capabilities(resource))
        caps["read_projection"] = True            # 저장본·초안 바이트를 기존 읽기 어휘로 투영(편집 주소 아님)
        caps["propose"] = bool(row.get("encoding")) if kind == "document" else caps.get("edit_native", False)
        caps["restore"] = True
        caps["close"] = True
        return caps

    # ── 세션 배관 해소 ──────────────────────────────────────────────────────
    def _session_args(self, kind, app, row, client, op):
        """세션 인자 5개를 만든다. 쓰기 op 는 세션 소유 창만. 읽기 op 는 세션 없이도 된다."""
        store = app.store
        session = store.get("session", row["session_id"]) if row.get("session_id") else None
        client = client or actor_client()
        if session is None:
            if op not in WRITE_OPS:
                return None
            detail = app.acquire(row["id"], client)
            session = detail["session"]
        elif session["client_id"] != client:
            if op in WRITE_OPS:
                raise DocumentConflict(f"다른 창('{session['client_id']}')이 작성 중입니다. 그 창에서 {op} 하거나 저장·닫기를 완료하세요")
            return None
        return {"session_id": session["id"], "client_id": session["client_id"],
                "epoch": session["engine_epoch"], "expected": session["session_revision"]}

    # ── snapshot ────────────────────────────────────────────────────────────
    def snapshot(self, resource, client=None, wait=None):
        kind, app, row = self.resolve(resource)
        if kind == "code":
            return self.head(kind, row, snapshot=app.snapshot(row))
        if kind == "sheet":
            return self._sheet_snapshot(app, row, wait)
        snap = self._document_snapshot(app, row)
        return self.head(kind, row, snapshot=snap["id"], session_revision=snap["session_revision"], unsaved=snap["unsaved"])

    def _document_snapshot(self, app, row):
        """현재 초안(세션 blob)이나 저장본의 고정 스냅샷. 읽기 증거이므로 작성 창 검사를 요구하지 않는다."""
        store = app.store
        with store.lock():
            session = store.get("session", row["session_id"]) if row.get("session_id") else None
            blob = session["blob"] if session else row["source_sha256"]
            snap = {"id": identifier(), "document_id": row["id"], "session_id": session["id"] if session else None,
                    "engine_epoch": session["engine_epoch"] if session else None,
                    "session_revision": session["session_revision"] if session else 0,
                    "blob": blob, "revision_id": row["revision_id"], "created_at": time.time(),
                    "unsaved": bool(session) and blob != row["source_sha256"]}
            store.put("snapshot", snap)
        return snap

    def _sheet_snapshot(self, app, row, wait):
        if not row.get("session_id"):
            # 닫힌 파일 — 저장본에서 고정 투영 스냅샷을 만든다(엔진 없음, 계산 상태는 저장 캐시).
            snap = self._sheet_saved_snapshot(app, row)
            return self.head("sheet", row, snapshot=snap["id"], unsaved=False, source="saved_file")
        key = operation_key("snapshot", row["id"], {"revision": row["revision_id"], "t": int(time.time())})
        receipt = app.request_snapshot(row["id"], key)
        deadline = time.monotonic() + max(0.0, min(float(wait if wait is not None else 10), SNAPSHOT_WAIT_MAX))
        status = app.operation_status(row["id"], receipt["operation_id"])
        while not status.get("completed") and status.get("status") == "queued" and time.monotonic() < deadline:
            time.sleep(0.3)
            status = app.operation_status(row["id"], receipt["operation_id"])
        result = status.get("result") or {}
        snap = result.get("snapshot") if isinstance(result, dict) else None
        return self.head("sheet", row, operation_id=receipt["operation_id"], state=status.get("status"),
                         completed=bool(status.get("completed")),
                         snapshot=(snap or {}).get("id") if isinstance(snap, dict) else None,
                         note=None if status.get("completed") else "편집창의 엔진이 응답해야 스냅샷이 완성됩니다. 접수는 완료가 아닙니다")

    def _sheet_saved_snapshot(self, app, row):
        import spreadsheet_files as files
        data = app.store.bytes(row["source_sha256"])
        report = files.calculation_state(data) if row["source_format"] == "xlsx" else {"status": "unsupported"}
        snap = {"id": identifier(), "document_id": row["id"], "resource_id": row["id"], "revision_id": row["revision_id"],
                "session_id": None, "engine_epoch": None, "session_revision": 0, "blob": row["source_sha256"],
                "engine_state": "", "engine_state_sha256": "", "calc_revision": 0,
                "calc_status": report.get("status", "unsupported"), "calculation_report": report,
                "engine_id": "saved_file", "created_at": time.time(), "unsaved": False}
        app.store.put("sheet_snapshot", snap)
        return snap

    @staticmethod
    def _sheet_id(app, blob, sheet):
        """selector.sheet — 순번(0부터)·시트 이름·sheet_id 어느 것이든 저장소의 sheet_id 로 해소."""
        import spreadsheet_files as files
        sheets = files.inspect(app.store.bytes(blob))["sheets"]
        if isinstance(sheet, int) and not isinstance(sheet, bool):
            if not 0 <= sheet < len(sheets):
                raise ValueError(f"시트 순번 {sheet} 이 범위를 벗어났습니다(시트 {len(sheets)}개)")
            return sheets[sheet]["sheet_id"]
        for s in sheets:
            if str(sheet) in (s["sheet_id"], s["name"]):
                return s["sheet_id"]
        raise ValueError(f"시트를 찾을 수 없습니다: {sheet} (있는 시트: {[s['name'] for s in sheets]})")

    def _latest_sheet_snapshot(self, app, row):
        rows = [s for s in app.store.list("sheet_snapshot") if s.get("document_id") == row["id"]]
        return rows[0] if rows else self._sheet_saved_snapshot(app, row)

    # ── read ────────────────────────────────────────────────────────────────
    def read(self, resource, selector=None, snapshot=None):
        selector = selector or {}
        kind, app, row = self.resolve(resource)
        if kind == "code":
            return self.head(kind, row, **app.read(row, selector))
        if kind == "sheet":
            snap = app.store.get("sheet_snapshot", snapshot) if snapshot else self._latest_sheet_snapshot(app, row)
            sheet_id = self._sheet_id(app, snap["blob"], selector.get("sheet", 0))
            address = selector.get("range", "A1:Z200")
            table = app.read(row["id"], snap["id"], sheet_id, address)
            return self.head(kind, row, snapshot=snap["id"], selector={"sheet": sheet_id, "range": address},
                             unsaved=snap.get("unsaved", False), calc_status=table.get("calc_status"), table=table)
        snap = app.store.get("snapshot", snapshot) if snapshot else self._document_snapshot(app, row)
        if snap["document_id"] != row["id"]:
            raise PermissionError("다른 자료의 스냅샷입니다")
        data = app.store.bytes(snap["blob"])
        if row.get("encoding"):
            text = data.decode(row["encoding"])
            start, end = selector.get("start"), selector.get("end")
            if start is not None or end is not None:
                start = int(start or 0); end = int(end if end is not None else len(text))
                if not 0 <= start <= end <= len(text):
                    raise ValueError("선택 범위가 본문을 벗어났습니다")
                piece = text[start:end]
                return self.head(kind, row, snapshot=snap["id"], selector={"start": start, "end": end},
                                 selected_sha256=digest(piece.encode()), text=piece, length=len(text), unsaved=snap.get("unsaved", False))
            return self.head(kind, row, snapshot=snap["id"], text=text, length=len(text), unsaved=snap.get("unsaved", False))
        return self.head(kind, row, snapshot=snap["id"], unsaved=snap.get("unsaved", False),
                         **self._office_projection(row, data, selector))

    def _office_projection(self, row, data, selector):
        """사무·PDF·한글 바이트를 기존 읽기 어휘(self:read 와 같은 읽기기)로 투영 — 편집 주소가 아니라 열람."""
        import tempfile
        from resource_links import package_module
        fmt = row["source_format"]
        readers = {"docx": ("office_ops", "read_docx"), "pdf": ("office_ops", "read_pdf"),
                   "hwp": ("doc_read_extra", "read_hwp"), "hwpx": ("doc_read_extra", "read_hwpx")}
        if fmt not in readers:
            raise DocumentUnsupported(f"{fmt} 의 서버 측 읽기 투영은 아직 없습니다 — 편집기에서 선택 읽기를 사용하세요")
        module, func = readers[fmt]
        with tempfile.NamedTemporaryFile(suffix="." + fmt, delete=True) as tmp:
            tmp.write(data); tmp.flush()
            args = {"path": tmp.name, **{k: v for k, v in selector.items() if k in ("offset", "limit", "max_blocks", "pages", "tables")}}
            raw = getattr(package_module("system_essentials", module), func)(args, str(Path(tmp.name).parent))
        try:
            out = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            out = {"text": raw}
        if isinstance(out, dict) and out.get("success") is False:
            raise DocumentUnsupported(str(out.get("error") or "읽기 투영 실패"))
        return {"projection": True, **{k: v for k, v in (out or {}).items() if k != "success"}}

    # ── propose ─────────────────────────────────────────────────────────────
    def propose(self, resource, selector=None, replacement=None, values=None, kind=None, snapshot=None):
        selector = selector or {}
        rkind, app, row = self.resolve(resource)
        if rkind == "code":
            return self.head(rkind, row, **app.propose(row, selector, replacement))
        if rkind == "sheet":
            snap = app.store.get("sheet_snapshot", snapshot) if snapshot else self._latest_sheet_snapshot(app, row)
            if values is None:
                raise ValueError("시트 제안에는 values(범위와 같은 행·열의 2차원 배열)가 필요합니다")
            p = app.propose(row["id"], snap["id"], self._sheet_id(app, snap["blob"], selector.get("sheet", 0)),
                            selector.get("range"), values, kind or "set_values")
            return self.head(rkind, row, proposal=p["id"], snapshot=snap["id"], selector=selector, affected_cells=p.get("affected_cells"))
        if not row.get("encoding"):
            raise DocumentUnsupported("사무 문서의 선택 수정은 활성 편집기의 선택 고정(bookmark)으로 — 앱의 편집 표면에서 제안하세요")
        if not isinstance(replacement, str):
            raise ValueError("replacement(교체 문구)가 필요합니다")
        snap = app.store.get("snapshot", snapshot) if snapshot else self._document_snapshot(app, row)
        text = app.store.bytes(snap["blob"]).decode(row["encoding"])
        start = int(selector.get("start", 0)); end = int(selector.get("end", len(text)))
        if not 0 <= start <= end <= len(text):
            raise ValueError("선택 범위가 본문을 벗어났습니다")
        selected = text[start:end]
        if selector.get("selected_sha256") and selector["selected_sha256"] != digest(selected.encode()):
            raise DocumentConflict("선택 내용이 바뀌었습니다. 다시 읽고 제안하세요")
        p = app.propose(row["id"], snap["id"], start, end, digest(selected.encode()), replacement)
        return self.head(rkind, row, proposal=p["id"], snapshot=snap["id"], selector={"start": start, "end": end})

    # ── apply ───────────────────────────────────────────────────────────────
    def apply(self, resource, proposal, client=None):
        kind, app, row = self.resolve(resource)
        if kind == "code":
            return self.head(kind, row, **app.apply(row, proposal))
        args = self._session_args(kind, app, row, client, "apply")
        done = self._applied(app, row, proposal)
        if done is not None:
            return self.head(kind, row, proposal=proposal, **done, cached=True)
        if kind == "document":
            self._bind_sessionless_snapshot(app, row, proposal, args)
        key = operation_key("apply", row["id"], {"proposal": proposal, "expected": args["expected"]})
        result = app.apply(row["id"], proposal, **args, operation_id=key)
        self._mark_applied(app, row, key, proposal)
        if kind == "sheet":
            return self.head(kind, row, proposal=proposal, **result, **self._sheet_receipt(row, result),
                             note="편집기에 전달된 접수입니다. 완료는 [self:task]{op: \"wait\", ref: $r.task_ref} 로 확인됩니다")
        return self.head(kind, row, proposal=proposal, applied=True, session_revision=result["session"]["session_revision"],
                         text=result.get("text"))

    @staticmethod
    def _mark_applied(app, row, key, proposal):
        store = app.store
        with store.connect() as conn:
            try:
                op = store.get("operation", digest((row["id"] + ":" + key).encode()))
            except ValueError:
                return
            if isinstance(op.get("result"), dict):
                op["result"]["_proposal"] = proposal
                store.put("operation", op, conn)

    @staticmethod
    def _applied(app, row, proposal):
        """같은 제안을 두 번 적용하지 않는다 — 이미 적용된 제안은 그 결과를 돌려준다(멱등)."""
        for op in app.store.list("operation"):
            if op.get("document_id") == row["id"] and isinstance(op.get("result"), dict) \
                    and op.get("proposal_id", (op.get("fingerprint") and None)) == proposal:
                return {"applied": True, "session_revision": (op["result"].get("session") or {}).get("session_revision"),
                        "text": op["result"].get("text")}
            res = op.get("result")
            if isinstance(res, dict) and op.get("document_id") == row["id"] and res.get("_proposal") == proposal:
                return {"applied": True, "session_revision": (res.get("session") or {}).get("session_revision"),
                        "text": res.get("text")}
        return None

    @staticmethod
    def _bind_sessionless_snapshot(app, row, proposal, args):
        """세션 없이(저장본에서) 만든 제안을 방금 얻은 세션에 묶는다 — 바이트가 같을 때만.

        제안은 스냅샷에 고정된다. 스냅샷이 세션 밖에서 찍혔고 세션의 초안이 그 바이트 그대로라면
        내용은 동일하므로 세션 표식만 채운다. 바이트가 다르면 손대지 않아 apply 가 충돌로 거절한다."""
        store = app.store
        with store.lock():
            p = store.get("proposal", proposal)
            snap = store.get("snapshot", p["snapshot_id"])
            if snap.get("session_id") or snap["document_id"] != row["id"]:
                return
            session = store.get("session", args["session_id"])
            if session["blob"] != snap["blob"]:
                return
            snap.update(session_id=session["id"], engine_epoch=session["engine_epoch"],
                        session_revision=session["session_revision"])
            store.put("snapshot", snap)

    # ── save / export ───────────────────────────────────────────────────────
    def save(self, resource, client=None, message=None, verify=None):
        kind, app, row = self.resolve(resource)
        if kind == "code":
            return self.head(kind, row, **app.save(row, message, verify))
        if kind == "sheet":
            key = operation_key("save", row["id"], {"revision": row["revision_id"]})
            receipt = app.request_save(row["id"], key, row["revision_id"])
            return self.head(kind, row, **receipt, **self._sheet_receipt(row, receipt),
                             note="편집창 포획 뒤 저장이 접수됐습니다. 완료는 [self:task]{op: \"wait\", ref: $r.task_ref} 로 확인됩니다")
        args = self._session_args(kind, app, row, client, "save")
        key = operation_key("save", row["id"], {"revision": row["revision_id"], "expected": args["expected"]})
        result = app.save(row["id"], **args, operation_id=key, expected_revision=row["revision_id"])
        fresh = app._doc(row["id"])
        return self.head(kind, fresh, state=result["state"], saved_path=result["path"], sha256=result["sha256"])

    def export(self, resource, filename, client=None):
        kind, app, row = self.resolve(resource)
        if kind == "code":
            raise DocumentUnsupported("코딩 작업 공간의 사본 내보내기는 없습니다 — save(반영·커밋)를 사용하세요")
        args = self._session_args(kind, app, row, client, "export")
        key = operation_key("export", row["id"], {"filename": filename, "expected": args["expected"]})
        result = app.export_copy(row["id"], **args, operation_id=key, filename=filename)
        return self.head(kind, row, **result)

    # ── versions / restore / close ──────────────────────────────────────────
    def versions(self, resource):
        kind, app, row = self.resolve(resource)
        if kind == "code":
            return self.head(kind, row, items=app.versions(row))
        items = [{"id": v["id"], "created_at": v.get("created_at"), "label": v.get("label") or "저장 버전",
                  "parent": v.get("parent_revision_id"), "recovery": bool(v.get("is_recovery"))}
                 for v in app.versions(resource)]
        return self.head(kind, row, items=items)

    def restore(self, resource, revision, client=None):
        kind, app, row = self.resolve(resource)
        if kind == "code":
            raise DocumentUnsupported("코딩 작업 공간의 버전 복구는 git 으로 — [self:body]{op:\"file\"} 로 이력을 보고 파일을 다시 제안하세요")
        args = self._session_args(kind, app, row, client, "restore")
        key = operation_key("restore", row["id"], {"revision": revision, "expected": args["expected"]})
        result = app.restore(row["id"], revision, **args, operation_id=key)
        return self.head(kind, row, restored=revision, session_revision=result["session"]["session_revision"])

    def close(self, resource, client=None):
        kind, app, row = self.resolve(resource)
        if kind == "code":
            return self.head(kind, row, **app.close(row))
        args = self._session_args(kind, app, row, client, "close")
        return self.head(kind, row, **app.close(row["id"], **args))

    def recover(self, resource):
        kind, app, row = self.resolve(resource)
        if kind == "code":
            raise DocumentUnsupported("코딩 작업 공간은 복구할 미완료 저장이 없습니다")
        return self.head(kind, row, **app.recover(resource))


class CodeAdapter:
    """git worktree 를 작업 공간 계약에 맞춘다 — 자료=저장소 과제, 스냅샷=트리 지문, 저장=검토·반영(커밋)."""

    def __init__(self, store=None):
        from coding_workspace import CodingWorkspace
        self.app = CodingWorkspace(store)
        self.store = self.app.store

    def task(self, task_id):
        return self.store.get("task", task_id)

    def open(self, path, goal=None):
        repo = self.app.open_repository(path)
        for task in self.store.list("task"):
            if task["repository_id"] == repo["id"] and task.get("kind") != "done" and (goal is None or task["goal"] == goal):
                return task
        return self.app.create_task(repo["id"], goal or f"{Path(repo['path']).name} 작업 공간")

    def capabilities(self, task):
        from coding_process import available
        return {"engine": "git", "edit_native": True, "save": True, "export_copy": False, "restore": False,
                "close": True, "read_projection": True, "propose": True, "verify": available(),
                "reason": "git worktree 작업 공간 — 저장은 검토·승인·커밋 반영"}

    def snapshot(self, task):
        from coding_git import current_tree
        return current_tree(task["workspace"])

    def read(self, task, selector):
        if selector.get("diff"):
            from coding_git import current_tree, delta
            paths, patch = delta(task["workspace"], task["start_tree"], current_tree(task["workspace"]))
            return {"selector": {"diff": True}, "paths": paths, "patch": patch.decode(errors="replace")}
        if selector.get("files") or not selector.get("path"):
            return {"selector": {"files": True}, "items": [{"path": p} for p in self.app.files(task["id"])]}
        opened = self.app.read_file(task["id"], selector["path"])
        lines = opened["text"].splitlines()
        start = int(selector.get("start_line", 1)); end = int(selector.get("end_line", len(lines)))
        if not 1 <= start <= max(end, 1):
            raise ValueError("줄 범위를 확인하세요")
        piece = "\n".join(lines[start - 1:end])
        return {"selector": {"path": selector["path"], "start_line": start, "end_line": min(end, len(lines))},
                "fingerprint": opened["fingerprint"], "binary": opened["binary"], "text": piece, "lines": len(lines)}

    def propose(self, task, selector, replacement):
        path = selector.get("path")
        if not path or not isinstance(replacement, str):
            raise ValueError("코딩 제안에는 selector.path 와 replacement(전체 본문 또는 줄 범위 교체문)가 필요합니다")
        target = Path(task["workspace"]) / path
        opened = self.app.read_file(task["id"], path) if target.exists() else {"fingerprint": None, "text": ""}
        if selector.get("start_line") is not None:
            lines = opened["text"].splitlines()
            start = int(selector["start_line"]); end = int(selector.get("end_line", start))
            if not 1 <= start <= end <= max(len(lines), 1):
                raise ValueError("줄 범위를 확인하세요")
            content = "\n".join(lines[:start - 1] + replacement.splitlines() + lines[end:]) + ("\n" if opened["text"].endswith("\n") else "")
        else:
            content = replacement
        row = {"id": identifier(), "task_id": task["id"], "path": path, "expected": opened["fingerprint"],
               "content": content, "selector": selector, "created_at": time.time()}
        self.store.save("workspace_proposal", row)
        return {"proposal": row["id"], "selector": {"path": path}, "expected": opened["fingerprint"]}

    def apply(self, task, proposal):
        row = self.store.get("workspace_proposal", proposal)
        if row["task_id"] != task["id"]:
            raise PermissionError("다른 과제의 제안입니다")
        saved = self.app.save_file(task["id"], row["path"], row["content"], row["expected"])
        return {"proposal": proposal, "applied": True, "path": row["path"], "fingerprint": saved["fingerprint"]}

    def save(self, task, message, verify=None):
        if not message or not str(message).strip():
            raise ValueError("코딩 작업 공간의 save 는 반영(커밋)입니다 — message 가 필요합니다")
        if verify:
            from coding_runs import CodingRuns
            CodingRuns(self.app).start(task["id"], "검증: " + verify, "", operation_key("verify", task["id"], {"cmd": verify}),
                                       background=False, command=verify)
        review = self.app.review(task["id"], [])
        self.app.approve(task["id"], review["id"], review["fingerprint"])
        operation = self.app.apply(task["id"], review["id"], review["fingerprint"],
                                   operation_key("commit", task["id"], {"review": review["id"]}), message)
        return {"state": operation["state"], "commit": operation.get("commit"), "paths": review["paths"],
                "error": operation.get("error")}

    def versions(self, task):
        """반영(save)은 정본 저장소에 커밋되므로 이력은 저장소 쪽을 읽는다(작업 공간은 시작점에 머문다)."""
        from coding_git import text_git
        repo = self.store.get("repository", task["repository_id"])
        log = text_git(repo["path"], "log", "--format=%H%x1f%ct%x1f%s", "-20")
        items = []
        for line in log.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 3:
                items.append({"id": parts[0], "created_at": int(parts[1]), "label": parts[2]})
        return items

    def close(self, task):
        self.app.idle(task)
        task["kind"] = "done"
        self.store.save("task", task)
        return {"closed": True}
