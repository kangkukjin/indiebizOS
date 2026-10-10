"""Bounded Pages snapshots. Package folders are documents, never repositories."""
import io
import os
import stat
import zipfile
from pathlib import Path, PurePosixPath

from office_sessions import DocumentUnsupported, MAX_BYTES, read_bytes

MAX_EXPANDED = 200 * 1024 * 1024
MAX_ENTRIES = 10000


class ImportFailure(DocumentUnsupported):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


def validate_pages(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [e.filename for e in entries]
            if len(entries) > MAX_ENTRIES or len(names) != len(set(names)):
                raise ImportFailure("invalid_pages", "Pages 압축 항목 수 또는 중복 경로를 확인하세요")
            if sum(e.file_size for e in entries) > MAX_EXPANDED:
                raise ImportFailure("input_too_large", "Pages 압축 해제 크기 상한은 200MiB입니다")
            for e in entries:
                parts = PurePosixPath(e.filename)
                if (parts.is_absolute() or '..' in parts.parts or '\\' in e.filename
                        or ':' in e.filename or stat.S_ISLNK(e.external_attr >> 16)):
                    raise ImportFailure("invalid_pages", "Pages 내부 경로가 올바르지 않습니다")
                if e.flag_bits & 1:
                    raise ImportFailure("password_required", "암호 문서는 Pages에서 DOCX로 내보낸 뒤 여세요")
            known = ('Index/Document.iwa' in names or 'index.xml' in names
                     or 'index.xml.gz' in names)
            if not known:
                if any('Encryption' in n or n.endswith('.iwpv2') for n in names):
                    raise ImportFailure("password_required", "암호 문서는 Pages에서 DOCX로 내보낸 뒤 여세요")
                raise ImportFailure("unsupported_pages", "Pages 구조를 확인할 수 없습니다. Pages에서 DOCX로 내보낸 뒤 여세요")
            # Read all members to check CRCs and actual expansion without extraction.
            for e in entries:
                with archive.open(e) as stream:
                    consumed = 0
                    while chunk := stream.read(1024 * 1024):
                        consumed += len(chunk)
                        if consumed > e.file_size or consumed > MAX_EXPANDED:
                            raise ImportFailure("input_too_large", "Pages 압축 크기 상한을 초과했습니다")
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError) as exc:
        raise ImportFailure("invalid_pages", "손상되었거나 지원하지 않는 Pages 파일입니다") from exc


def _members(root):
    found = {}
    count = 0
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            count += 1
            if count > MAX_ENTRIES:
                raise ImportFailure("input_too_large", "Pages 패키지 항목이 너무 많습니다")
            path = Path(base) / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ImportFailure("invalid_pages", "Pages 패키지에 링크나 특수 파일이 있습니다")
            if stat.S_ISREG(info.st_mode):
                found[path.relative_to(root).as_posix()] = (info.st_size, info.st_mtime_ns, info.st_ino)
            if len(found) > MAX_ENTRIES:
                raise ImportFailure("input_too_large", "Pages 패키지 항목이 너무 많습니다")
    if sum(info[0] for info in found.values()) > MAX_BYTES:
        raise ImportFailure("input_too_large", "Pages 패키지 전체 크기 상한은 25MiB입니다")
    return found


def snapshot(path):
    path = Path(path)
    if path.is_symlink():
        raise ImportFailure("invalid_pages", "링크 대신 실제 Pages 문서를 선택하세요")
    if path.is_dir():
        before = _members(path)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            total = 0
            for name in sorted(before):
                data = read_bytes(path / name)
                total += len(data)
                if total > MAX_BYTES:
                    raise ImportFailure("input_too_large", "Pages 패키지 전체 크기 상한은 25MiB입니다")
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, data)
        if before != _members(path):
            raise ImportFailure("source_changed_during_read", "읽는 동안 Pages 원본이 바뀌었습니다. 다시 여세요")
        data = buffer.getvalue()
    else:
        before = path.stat()
        data = read_bytes(path)
        after = path.stat()
        if (before.st_ino, before.st_mtime_ns, before.st_size) != (after.st_ino, after.st_mtime_ns, after.st_size):
            raise ImportFailure("source_changed_during_read", "읽는 동안 Pages 원본이 바뀌었습니다. 다시 여세요")
    if len(data) > MAX_BYTES:
        raise ImportFailure("input_too_large", "Pages 입력 상한은 25MiB입니다")
    validate_pages(data)
    return data
