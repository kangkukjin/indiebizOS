"""Real source bytes and fault injection; not Office/Hancom acceptance evidence."""
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

# Also works when this file is run through the registered test script against
# an isolated RED worktree; never accidentally test the live implementation.
HERE = Path(__file__).resolve().parent
for layer in ("datastore", "services", "surface"):
    sys.path.insert(0, str(HERE / layer))
import principal
import document_workspace as mod
from document_workspace import DocumentWorkspace, DocumentConflict, DocumentUnsupported
from document_store import digest


@pytest.fixture
def work(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_bytes("원본\r\n두번째\r\n".encode("cp949"))
    app = DocumentWorkspace(tmp_path / "workspace")
    d = app.open(path, "cp949")["document"]
    s = app.acquire(d["id"], "window-1")["session"]
    return app, path, d, s


def args(d, s):
    return dict(document_id=d["id"], session_id=s["id"], client_id=s["client_id"],
                epoch=s["engine_epoch"], expected=s["session_revision"])


def edit(work, text="고친 초안\r\n"):
    app, path, d, s = work
    changed = app.draft(**args(d, s), operation_id="draft-1", text=text)["session"]
    return app, path, d, changed


def test_native_encoding_crlf_and_no_original_write(work):
    app, path, d, s = edit(work)
    original = path.read_bytes()
    result = app.export_copy(**args(d, s), operation_id="copy-1", filename="result.txt")
    assert Path(result["path"]).read_bytes() == "고친 초안\r\n".encode("cp949")
    assert path.read_bytes() == original
    assert app.detail(d["id"])["document"]["source_sha256"] == digest(original)
    assert result["state"] == "copy_saved"
    assert app.detail(d["id"])["session"]["state"] == "draft"


def test_original_save_rejects_external_change(work):
    app, path, d, s = edit(work)
    path.write_bytes(b"external changed")
    with pytest.raises(DocumentConflict):
        app.save(**args(d, s), operation_id="save", expected_revision=d["revision_id"])
    assert path.read_bytes() == b"external changed"
    assert app.detail(d["id"])["text"] == "고친 초안\r\n"
    assert app.capabilities(d["id"])["save"] is True


def test_external_write_immediately_before_publication_preserved(work, monkeypatch):
    app, path, d, s = edit(work)
    link = mod.os.link
    def race(src, dst):
        path.write_bytes(b"external at last instant")
        return link(src, dst)
    monkeypatch.setattr(mod.os, "link", race)
    output = app.export_copy(**args(d, s), operation_id="race", filename="copy.txt")
    assert path.read_bytes() == b"external at last instant"
    assert Path(output["path"]).read_bytes() == "고친 초안\r\n".encode("cp949")
    assert app.detail(d["id"])["text"] == "고친 초안\r\n"


def test_destination_race_never_overwrites(work, monkeypatch):
    app, path, d, s = edit(work)
    link = mod.os.link
    def race(src, dst):
        Path(dst).write_bytes(b"other writer")
        return link(src, dst)
    monkeypatch.setattr(mod.os, "link", race)
    with pytest.raises(FileExistsError):
        app.export_copy(**args(d, s), operation_id="race", filename="copy.txt")
    assert path.with_name("copy.txt").read_bytes() == b"other writer"
    assert app.recover(d["id"])["items"][0]["state"] == "conflict"
    assert app.detail(d["id"])["text"] == "고친 초안\r\n"


def test_crash_after_publication_recovers_without_rewrite(work, monkeypatch):
    app, path, d, s = edit(work)
    def crash(op):
        raise OSError("simulated database outage")
    monkeypatch.setattr(app, "_finish_export", crash)
    with pytest.raises(OSError):
        app.export_copy(**args(d, s), operation_id="copy", filename="copy.txt")
    app = DocumentWorkspace(app.store.root)
    assert app.recover(d["id"])["items"][0]["state"] == "copy_saved"
    assert app.export_copy(**args(d, s), operation_id="copy", filename="copy.txt")["state"] == "copy_saved"
    assert len(app.store.events(d["id"])) == 2


def test_disk_failure_keeps_draft_and_original(work, monkeypatch):
    app, path, d, s = edit(work)
    original = path.read_bytes()
    def full(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr(mod.tempfile, "mkstemp", full)
    with pytest.raises(OSError):
        app.export_copy(**args(d, s), operation_id="copy", filename="copy.txt")
    assert path.read_bytes() == original
    assert app.recover(d["id"])["items"][0]["state"] == "not_written"
    assert app.detail(d["id"])["text"] == "고친 초안\r\n"


def test_idempotent_draft_and_reordered_requests(work):
    app, path, d, s = work
    call = dict(**args(d, s), operation_id="dup", text="새 글")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: app.draft(**call), range(2)))
    assert results[0] == results[1]
    with pytest.raises(DocumentConflict):
        app.draft(**args(d, s), operation_id="old", text="늦은 요청")
    with pytest.raises(DocumentConflict):
        app.draft(**{**call, "text": "다른 인자"})
    assert len(app.store.events(d["id"])) == 1


def test_second_window_cannot_write(work):
    app, path, d, s = work
    with pytest.raises(DocumentConflict):
        app.acquire(d["id"], "window-2")
    assert app.acquire(d["id"], "window-1")["session"] == s
    with pytest.raises(DocumentConflict):
        app.draft(**{**args(d, s), "epoch": "old"}, operation_id="bad", text="bad")


def test_snapshot_unsaved_and_stale_proposal_rejected(work):
    app, path, d, s = edit(work, "선택한 문장")
    snap = app.snapshot(**args(d, s))
    assert app.read(d["id"], snap["id"])["text"] == "선택한 문장"
    p = app.propose(d["id"], snap["id"], 0, 3, digest("선택한".encode()), "고쳐진")
    newer = app.draft(**args(d, s), operation_id="human", text="사람의 다음 문장")["session"]
    with pytest.raises(DocumentConflict):
        app.apply(**args(d, newer), proposal_id=p["id"], operation_id="ai")
    assert app.detail(d["id"])["text"] == "사람의 다음 문장"


def test_proposal_applies_once_and_preserves_source(work):
    app, path, d, s = edit(work, "선택한 문장")
    original = path.read_bytes()
    snap = app.snapshot(**args(d, s))
    p = app.propose(d["id"], snap["id"], 0, 3, digest("선택한".encode()), "고쳐진")
    call = dict(**args(d, s), proposal_id=p["id"], operation_id="ai")
    assert app.apply(**call)["text"] == "고쳐진 문장"
    assert app.apply(**call)["text"] == "고쳐진 문장"
    assert path.read_bytes() == original


@pytest.mark.parametrize("encoding,bom", [("utf-8-sig", b""), ("utf-16-be", b"\xfe\xff"),
                                          ("utf-16-le", b"\xff\xfe"), ("euc-kr", b"")])
def test_encoding_roundtrip(tmp_path, encoding, bom):
    path = tmp_path / "sample.txt"
    original = bom + "한글\r\n".encode(encoding)
    path.write_bytes(original)
    app = DocumentWorkspace(tmp_path / "state")
    d = app.open(path, "euc-kr" if encoding == "euc-kr" else None)["document"]
    s = app.acquire(d["id"], "w")["session"]
    exported = app.export_copy(**args(d, s), operation_id="copy", filename="copy.txt")
    assert Path(exported["path"]).read_bytes() == original


def test_unencodable_draft_does_not_replace_recovery(work):
    app, path, d, s = work
    with pytest.raises(UnicodeError):
        app.draft(**args(d, s), operation_id="emoji", text="🙂")
    assert app.detail(d["id"])["session"] == s


def test_office_not_falsely_reported_supported(tmp_path):
    file = tmp_path / "form.hwpx"
    file.write_bytes(b"not a real office document")
    app = DocumentWorkspace(tmp_path / "state")
    d = app.open(file)["document"]
    assert not app.capabilities(d["id"])["edit_native"]
    with pytest.raises(DocumentUnsupported):
        app.acquire(d["id"], "w")


def test_reclaim_preserves_draft_and_fences_old_writer(work):
    app, path, d, s = edit(work)
    next_session = app.reclaim(d["id"], "window-2", s["engine_epoch"])["session"]
    assert next_session["blob"] == s["blob"]
    with pytest.raises(DocumentConflict):
        app.draft(**args(d, s), operation_id="late", text="old window")
    assert app.detail(d["id"])["text"] == "고친 초안\r\n"


def test_nonowner_denied(work):
    app, path, d, s = work
    with principal.narrow(principal.ANONYMOUS):
        with pytest.raises(PermissionError):
            app.detail(d["id"])
        with pytest.raises(PermissionError):
            app.open(path)


def test_api_rejects_foreign_origin_and_remote_paths(work, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api_documents
    workspace, path, d, s = work
    monkeypatch.setattr(api_documents, "service", lambda: workspace)
    app = FastAPI()
    app.include_router(api_documents.router)
    with TestClient(app) as client:
        assert client.get("/documents", headers={"origin": "https://evil.example"}).status_code == 403
        assert client.post("/documents/open", json={"path": str(path)},
                           headers={"x-forwarded-for": "203.0.113.1"}).status_code == 403
        response = client.post(f"/documents/{d['id']}/draft", json={"args": {
            **{k: v for k, v in args(d, s).items() if k != "document_id"},
            "operation_id": "http", "text": "HTTP 작업"}})
        assert response.status_code == 200, response.text
        with principal.narrow(principal.ANONYMOUS):
            assert client.get("/documents").status_code == 403


def test_paths_and_cross_document_snapshot_denied(work, tmp_path):
    app, path, d, s = work
    for filename in ("../escape.txt", "a/b.txt", "a\\b.txt", "copy.docx", "sample.txt"):
        with pytest.raises((ValueError, DocumentConflict, DocumentUnsupported)):
            app.export_copy(**args(d, s), operation_id=filename, filename=filename)
    other = tmp_path / "other.txt"
    other.write_text("other")
    d2 = app.open(other)["document"]
    snap = app.snapshot(**args(d, s))
    with pytest.raises(PermissionError):
        app.read(d2["id"], snap["id"])


def test_conditional_save_versions_and_duplicate(work):
    app, path, d, s = edit(work)
    original = path.read_bytes()
    call = dict(**args(d, s), operation_id="save", expected_revision=d["revision_id"])
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: app.save(**call), range(2)))
    assert results[0] == results[1]
    assert path.read_bytes() == "고친 초안\r\n".encode("cp949")
    assert app.store.bytes(d["source_sha256"]) == original
    assert len(app.versions(d["id"])) == 2
    assert app.detail(d["id"])["session"]["state"] == "saved"
    with pytest.raises(DocumentConflict):
        app.save(**{**call, "operation_id": "stale"})
    restored = app.restore(**args(d, s), revision_id=d["revision_id"], operation_id="restore")
    assert restored["session"]["state"] == "draft"
    assert path.read_bytes() != original  # Restore is a draft, not a disk write.


def test_save_rechecks_hash_after_temporary_write(work, monkeypatch):
    app, path, d, s = edit(work)
    chmod = mod.os.chmod
    def race(*a, **kw):
        path.write_bytes(b"external during save")
        return chmod(*a, **kw)
    monkeypatch.setattr(mod.os, "chmod", race)
    with pytest.raises(DocumentConflict):
        app.save(**args(d, s), operation_id="save", expected_revision=d["revision_id"])
    assert path.read_bytes() == b"external during save"
    assert app.detail(d["id"])["text"] == "고친 초안\r\n"


@pytest.mark.parametrize("failure", ["disk", "replace", "directory_sync", "database"])
def test_save_fault_recovery_never_republishes(work, monkeypatch, failure):
    app, path, d, s = edit(work)
    original = path.read_bytes()
    def crash(*a, **kw):
        raise OSError("injected " + failure)
    with monkeypatch.context() as patch:
        if failure == "disk":
            patch.setattr(mod.tempfile, "mkstemp", crash)
        elif failure == "replace":
            patch.setattr(mod.os, "replace", crash)
        elif failure == "directory_sync":
            patch.setattr(mod, "sync_directory", crash)
        else:
            patch.setattr(app, "_finish_save", crash)
        with pytest.raises(OSError):
            app.save(**args(d, s), operation_id="save", expected_revision=d["revision_id"])
    app = DocumentWorkspace(app.store.root)
    with monkeypatch.context() as patch:
        patch.setattr(mod.os, "replace", crash)
        recovered = app.recover(d["id"])["items"][0]
    if failure in {"directory_sync", "database"}:
        assert recovered["state"] == "saved"
        assert path.read_bytes() == "고친 초안\r\n".encode("cp949")
        assert len(app.versions(d["id"])) == 2
    else:
        assert recovered["draft_preserved"]
        assert path.read_bytes() == original
    assert app.detail(d["id"])["text"] == "고친 초안\r\n"
    assert app.store.bytes(d["source_sha256"]) == original


def test_unfinished_save_blocks_rewrite_and_keeps_later_draft(work, monkeypatch):
    app, path, d, s = edit(work)
    def crash(op):
        raise OSError("database failed after replace")
    with monkeypatch.context() as patch:
        patch.setattr(app, "_finish_save", crash)
        with pytest.raises(OSError):
            app.save(**args(d, s), operation_id="save", expected_revision=d["revision_id"])
    with pytest.raises(DocumentConflict):
        app.save(**args(d, s), operation_id="save", expected_revision=d["revision_id"])
    newer = app.draft(**args(d, s), operation_id="later", text="이후 사람 입력")["session"]
    app.recover(d["id"])
    detail = app.detail(d["id"])
    assert detail["text"] == "이후 사람 입력"
    assert detail["session"]["session_revision"] == newer["session_revision"]
    assert detail["session"]["state"] == "draft"
    assert path.read_bytes() == "고친 초안\r\n".encode("cp949")


def test_external_change_after_failed_commit_is_never_overwritten(work, monkeypatch):
    app, path, d, s = edit(work)
    def crash(op):
        raise OSError("database failed")
    with monkeypatch.context() as patch:
        patch.setattr(app, "_finish_save", crash)
        with pytest.raises(OSError):
            app.save(**args(d, s), operation_id="save", expected_revision=d["revision_id"])
    path.write_bytes(b"new external bytes")
    assert app.recover(d["id"])["items"][0]["state"] == "conflict"
    assert path.read_bytes() == b"new external bytes"
    assert app.detail(d["id"])["session"]["state"] == "draft"


def ai_args(app, d, s, text):
    snap = app.snapshot(**args(d, s))
    return dict(**args(d, s), snapshot_id=snap["id"], start=0, end=len(text),
                selected_sha256=digest(text.encode()), instruction="자연스럽게 수정", operation_id="ai-1")


def test_ai_reads_unsaved_selection_and_never_writes_source(work, monkeypatch):
    text = "미저장 선택 문장"
    app, path, d, s = edit(work, text)
    original = path.read_bytes()
    calls = []
    def generate(instruction, selected):
        calls.append(selected)
        return "다듬은 문장", {"kind": "ai"}
    monkeypatch.setattr(mod, "generate_selection", generate)
    call = ai_args(app, d, s, text)
    proposal = app.generate_proposal(**call)
    assert app.generate_proposal(**call) == proposal
    assert calls == [text]
    assert proposal["provenance"]["kind"] == "ai"
    assert app.detail(d["id"])["text"] == text
    changed = app.apply(**args(d, s), proposal_id=proposal["id"], operation_id="apply-ai")
    assert changed["text"] == "다듬은 문장"
    assert path.read_bytes() == original


def test_human_edit_while_ai_runs_fences_proposal(work, monkeypatch):
    text = "선택한 문장"
    app, path, d, s = edit(work, text)
    def generate(instruction, selected):
        app.draft(**args(d, s), text="사람이 나중에 수정", operation_id="human")
        return "AI의 늦은 응답", {"kind": "ai"}
    monkeypatch.setattr(mod, "generate_selection", generate)
    proposal = app.generate_proposal(**ai_args(app, d, s, text))
    latest = app.detail(d["id"])["session"]
    with pytest.raises(DocumentConflict):
        app.apply(**args(d, latest), proposal_id=proposal["id"], operation_id="late-ai")
    assert app.detail(d["id"])["text"] == "사람이 나중에 수정"


def test_failed_ai_preserves_draft_and_does_not_repeat_call(work, monkeypatch):
    app, path, d, s = edit(work, "선택")
    def failure(*args):
        raise DocumentUnsupported("model failed")
    monkeypatch.setattr(mod, "generate_selection", failure)
    call = ai_args(app, d, s, "선택")
    with pytest.raises(DocumentUnsupported):
        app.generate_proposal(**call)
    with pytest.raises(DocumentConflict):
        app.generate_proposal(**call)
    assert app.detail(d["id"])["text"] == "선택"


def test_database_transaction_failure_rolls_back_metadata(work, monkeypatch):
    app, path, d, s = edit(work)
    put = app.store.put
    def failing_put(kind, row, conn=None):
        if kind == "revision" and conn is not None:
            raise OSError("database transaction failure")
        return put(kind, row, conn)
    with monkeypatch.context() as patch:
        patch.setattr(app.store, "put", failing_put)
        with pytest.raises(OSError):
            app.save(**args(d, s), operation_id="save", expected_revision=d["revision_id"])
    assert app.detail(d["id"])["document"]["revision_id"] == d["revision_id"]
    assert len(app.versions(d["id"])) == 1
    assert app.recover(d["id"])["items"][0]["state"] == "saved"
    assert len(app.versions(d["id"])) == 2


def test_process_exit_after_replace_recovers_confirmed_bytes(work):
    import json
    import subprocess
    app, path, d, s = edit(work)
    call = dict(**args(d, s), operation_id="save", expected_revision=d["revision_id"])
    program = """
import os, sys, json
import boot_paths
from document_workspace import DocumentWorkspace
app = DocumentWorkspace(sys.argv[1])
app._finish_save = lambda operation: os._exit(17)
app.save(**json.loads(sys.argv[2]))
"""
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(HERE), str(HERE / "services"),
                                        str(HERE / "datastore"), env.get("PYTHONPATH", "")])
    result = subprocess.run([sys.executable, "-c", program, str(app.store.root), json.dumps(call)],
                            env=env, capture_output=True, timeout=30)
    assert result.returncode == 17, result.stderr
    restored = DocumentWorkspace(app.store.root)
    assert restored.recover(d["id"])["items"][0]["state"] == "saved"
    assert path.read_bytes() == "고친 초안\r\n".encode("cp949")
    assert restored.detail(d["id"])["text"] == "고친 초안\r\n"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
