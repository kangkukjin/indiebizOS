"""문서/SQLite 쌍 백업 후 근거 형식을 이관한다. PYTHONPATH=backend 로 실행.

원천 자료를 읽거나 과거 판본을 추측하지 않는다. 백업은 덮어쓰지 않으며
실패 뒤 자동 복원하지 않는다(동시 사용자 편집을 지우지 않기 위해서).
"""
import boot_paths  # noqa: F401
import argparse
import json
import shutil
import sqlite3
from pathlib import Path

import forage_doc as fd
import forage_memory as fm
from distill_receipts import fingerprint, projection_pending


def archived_roots():
    return [marker for p in Path(fd.DOC_DIR).rglob(fd.DOC_NAME)
            if fd.GONE_DIR in p.relative_to(fd.DOC_DIR).parts
            and (marker := fd._read_marker(str(p)))]


def is_archived(row, roots):
    return any(fd._covers(body, root, row['locus']) for body, root in roots)


def project_active(roots):
    if not roots:
        return fd.migrate_all()
    # Archived documents remain paired with their original index records. Never
    # recreate a live node or copy its claims into a live ancestor during migration.
    original = fd.rows_for_doc
    fd.rows_for_doc = lambda body, root: [r for r in original(body, root) if not is_archived(r, roots)]
    try:
        conn = fm._connect()
        try:
            rows = [dict(r) for r in conn.execute('SELECT * FROM forage_map')]
        finally:
            conn.close()
        for row in rows:
            if not is_archived(row, roots):
                fd.refresh_doc_for(row['body'], row['locus'], own_node=bool(row['territory']))
        fd.refresh_all_docs()
    finally:
        fd.rows_for_doc = original


def migrate(backup):
    backup = Path(backup)
    if backup.exists():
        raise ValueError('backup destination already exists; choose a fresh paired backup')
    roots = archived_roots()
    if projection_pending(fm._DB_PATH):
        raise ValueError('pending_distill_projection')
    paths = [Path(p) for p, _, _ in fd._scan_docs()]
    snapshot = {str(p): fingerprint(p.read_text()) for p in paths}
    for p in paths:
        fd.parse_section(p.read_text())  # fail before the first write
    backup.mkdir(parents=True)
    src = sqlite3.connect(fm._DB_PATH)
    dst = sqlite3.connect(backup / 'forage_memory.db')
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    if Path(fd.DOC_DIR).exists():
        shutil.copytree(fd.DOC_DIR, backup / 'forage_surveys')
    manifest = {'format': 1, 'state': 'backed_up', 'documents': len(paths),
                'rollback': 'Stop writers. Restore forage_memory.db and forage_surveys together before using an older binary.'}
    (backup / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    if any(fingerprint(p.read_text()) != snapshot[str(p)] for p in paths):
        raise ValueError('documents_changed_during_backup')
    # Human edits remain authoritative. Existing DB detail survives unchanged legacy lines.
    for p in paths:
        if fd.SECTION in p.read_text() and fd.tree_doc.is_stale(str(p), fm.get_meta(fd._stamp_key(str(p)))):
            result = fd.sync_doc_to_db(str(p))
            if not result.get('success'):
                raise ValueError(result)
    fd.migrate_layout()
    snapshot = {p: fingerprint(Path(p).read_text()) for p, _, _ in fd._scan_docs()}
    from forage_evidence_doc import document_guard
    with document_guard(snapshot):
        project_active(roots)
    original_rows = fd.rows_for_doc
    try:
        if roots:
            fd.rows_for_doc = lambda body, root: [r for r in original_rows(body, root) if not is_archived(r, roots)]
        for p, _, _ in fd._scan_docs():
            synced = fd.sync_doc_to_db(p)
            if not synced.get('success'):
                raise ValueError(synced)
    finally:
        fd.rows_for_doc = original_rows
    conn = fm._connect()
    try:
        count = conn.execute('SELECT count(*) FROM forage_map').fetchone()[0]
        unversioned = [dict(r) for r in conn.execute("SELECT * FROM forage_map WHERE json_extract(provenance, '$.evidence.schema_version') IS NULL")]
        missing = sum(not is_archived(r, roots) for r in unversioned)
    finally:
        conn.close()
    if missing:
        raise ValueError('unprojected_evidence_rows')
    manifest.update(state='complete', claims=count, documents=len(fd._scan_docs()), archived_roots_held=len(roots))
    (backup / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return {k: manifest[k] for k in ('state', 'claims', 'documents')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'data' / '_backups'
    if not Path(args.backup).resolve().is_relative_to(root):
        parser.error('--backup must be under data/_backups/YYYY-MM-DD_name/')
    print(json.dumps(migrate(args.backup), ensure_ascii=False))
