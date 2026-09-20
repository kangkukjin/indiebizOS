"""불변 첨부와 일관된 공간 내보내기. 파일 경로는 외부 입력으로 받지 않는다."""
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

from common.record_contract import fail, dump
from record_policy import check_auth, require_owner, roles, can_use_artifact
from record_store import space_path, transaction, definition, uid, decode_record, put_meta

MAX_ASSET = 20 * 1024 * 1024


def upload(space, content, filename, auth, root=None):
    check_auth(auth, space)
    if not isinstance(content, bytes) or len(content) > MAX_ASSET:
        fail('validation', '첨부 파일은 20MiB 이하여야 합니다.')
    with transaction(space, root, write=True) as conn:
        roles(conn, auth)
        folder = space_path(space, root) / 'assets'
        folder.mkdir(exist_ok=True)
        ident = uid('asset')
        path = folder / ident
        with path.open('xb') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        directory_fd = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        hash_value = hashlib.sha256(content).hexdigest()
        conn.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)',
                     (ident, hash_value, len(content), Path(filename).name[:160], auth.subject, time.time()))
        return {'success': True, 'items': [{'id': ident, 'hash': hash_value, 'size': len(content)}]}


def download(space, ident, auth, root=None):
    check_auth(auth, space)
    with transaction(space, root) as conn:
        member_roles = roles(conn, auth)
        defn, _ = definition(conn)
        row = conn.execute('SELECT * FROM artifacts WHERE id=?', (ident,)).fetchone()
        if not row:
            fail('not_found', '첨부를 찾을 수 없습니다.')
        if not can_use_artifact(conn, ident, defn, auth, member_roles):
            fail('not_found', '첨부를 찾을 수 없습니다.')
        content = (space_path(space, root) / 'assets' / row['id']).read_bytes()
        if hashlib.sha256(content).hexdigest() != row['hash']:
            fail('validation', '첨부 내용이 저장된 지문과 다릅니다.')
        return content, row['filename']


def export_space(space, auth, root=None):
    require_owner(auth)
    folder = space_path(space, root)
    with transaction(space, root) as source:
        roles(source, auth)
        with tempfile.TemporaryDirectory(prefix='record-export-', dir=folder) as tmp:
            target = sqlite3.connect(str(Path(tmp) / 'records.db'), timeout=2)
            try:
                source.backup(target)
                # 확인 증표는 사용 권한이므로 내보내지 않는다.
                target.execute('DELETE FROM confirmations')
                target.commit()
                refs = target.execute('SELECT id,hash FROM artifacts').fetchall()
            finally:
                target.close()
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('format.json', dump({'format': 'indiebiz-record-space', 'version': 1}))
                archive.write(Path(tmp) / 'records.db', 'records.db')
                for ident, hash_value in refs:
                    content = (folder / 'assets' / ident).read_bytes()
                    if hashlib.sha256(content).hexdigest() != hash_value:
                        fail('validation', '첨부 검증에 실패해 내보내기를 중단했습니다.')
                    archive.writestr('assets/' + ident, content)
            return output.getvalue()


def import_space(space, content, auth, root=None):
    """새 공간에만 복원한다. 기존 원장 덮어쓰기와 효과 자동 재전송을 금지한다."""
    require_owner(auth)
    folder = space_path(space, root)
    if folder.exists():
        fail('conflict', '복원은 새 공간 이름으로만 가능합니다.')
    if len(content) > 100 * 1024 * 1024:
        fail('validation', '복원 파일은 100MiB 이하여야 합니다.')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        if len(entries) > 5000 or sum(e.file_size for e in entries) > 200 * 1024 * 1024:
            fail('validation', '복원 크기 상한을 넘었습니다.')
        if len({e.filename for e in entries}) != len(entries):
            fail('validation', '중복된 복원 파일 이름입니다.')
        for entry in entries:
            if entry.filename not in {'format.json', 'records.db'} and not (entry.filename.startswith('assets/asset_') and '/' not in entry.filename[7:] and '\\' not in entry.filename):
                fail('validation', '허용되지 않는 복원 파일 경로입니다.')
        manifest = json.loads(archive.read('format.json'))
        if manifest != {'format': 'indiebiz-record-space', 'version': 1}:
            fail('validation', '지원하지 않는 공간 내보내기 형식입니다.')
        folder.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.record-import-', dir=folder.parent) as tmp:
            tmp_path = Path(tmp)
            (tmp_path / 'assets').mkdir()
            for entry in entries:
                if entry.filename != 'format.json':
                    (tmp_path / entry.filename).write_bytes(archive.read(entry))
            conn = sqlite3.connect(str(tmp_path / 'records.db'), timeout=2)
            try:
                conn.execute('PRAGMA trusted_schema=OFF')
                if conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1").fetchone():
                    fail('validation', '실행 스키마가 포함된 DB는 반입할 수 없습니다.')
                if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    fail('validation', '복원 DB 무결성 오류')
                from common.record_contract import validate_definition
                for (raw,) in conn.execute('SELECT body FROM definitions'):
                    validate_definition(json.loads(raw))
                for ident, hash_value in conn.execute('SELECT id,hash FROM artifacts'):
                    if not isinstance(ident, str) or not ident.startswith('asset_') or '/' in ident or '\\' in ident:
                        fail('validation', '첨부 식별자가 잘못되었습니다.')
                    if hashlib.sha256((tmp_path / 'assets' / ident).read_bytes()).hexdigest() != hash_value:
                        fail('validation', '복원 첨부의 지문이 다릅니다.')
                put_meta(conn, 'uuid', uid('space'))
                put_meta(conn, 'recovery_required', True)
                put_meta(conn, 'paused', True)
                conn.execute('DELETE FROM confirmations')
                conn.execute("UPDATE deliveries SET state='unknown',lease_until=0 WHERE kind='effect' AND state IN ('pending','leased')")
                conn.execute("UPDATE deliveries SET state='blocked',lease_until=0 WHERE kind='command' AND state IN ('pending','leased')")
                conn.execute('DELETE FROM memberships')
                conn.execute('INSERT INTO memberships VALUES (?,?,1)', (auth.subject, dump(['admin'])))
                conn.commit()
            finally:
                conn.close()
            os.rename(tmp_path, folder)
    return {'success': True, 'space': space, 'recovery_required': True, 'paused': True}
