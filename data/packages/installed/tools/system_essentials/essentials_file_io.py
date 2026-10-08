"""일반 파일의 저장 경계: 동일 경로 직렬화, 실패 시 원본 보존, 제한된 텍스트 읽기."""
from collections import deque
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid
from runtime_utils import file_resource_identity


@contextmanager
def file_lock(path):
    """교체되는 inode 대신 정규화 경로를 잠근다(스레드·프로세스·핸들러 재로드 공용).

    잠금 파일은 삭제하지 않는다. 대기자가 잡은 inode와 새 호출의 inode가 갈라지지 않게 한다.
    도구 밖 편집기는 이 협력 잠금에 참여하지 않는다.
    """
    key = file_resource_identity(path)
    owner = str(os.getuid()) if hasattr(os, 'getuid') else os.environ.get('USERNAME', 'user')
    folder = Path(tempfile.gettempdir()) / ('indiebiz-file-locks-' + owner)
    folder.mkdir(mode=0o700, exist_ok=True)
    lock_path = folder / hashlib.sha256(os.fsencode(key)).hexdigest()
    with open(lock_path, 'a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            if lock.tell() == 0:
                lock.write(b'\0')
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def atomic_write_text(path, content):
    """호출자가 file_lock을 보유해야 한다. 쓰기·flush 실패는 기존 바이트를 건드리지 않는다."""
    target = Path(os.path.realpath(path))  # 심볼릭 링크 자체 대신 기존 대상에 쓴다.
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else None
    temp = target.with_name('.' + target.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        # x는 충돌 시 실패하며, 신규 파일 권한은 종전 open(w)처럼 umask를 따른다.
        with open(temp, 'x', encoding='utf-8', newline='') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


TEXT_PREVIEW_CHARS = 1_000_000


def read_text_window(path, params, bounds, max_chars=TEXT_PREVIEW_CHARS):
    """행 범위/텍스트 미리보기. max_chars=None은 구조 파싱용 완전한 원문이다.

    구조화 자료의 처리량을 모델 표시량으로 자르지 않는다. 완전한 값은 기존
    결과 저장·참조 경계가 보존하고, 모델 전달 경계에서만 미리보기를 제한한다.
    텍스트와 CSV/TSV 모두 CR/LF/CRLF를 원문 그대로 보존한다.
    """
    tail = params.get('tail')
    offset = params.get('offset') or 0
    limit = params.get('limit')
    ranged = tail is not None or offset > 0 or limit is not None
    selected = deque(maxlen=tail) if tail is not None else []
    total, chars, truncated = 0, 0, False
    numbered = bool(params.get('numbered')) and not params.get('blocks')
    with open(path, 'r', encoding='utf-8', newline='') as stream:
        for i, line in enumerate(stream):
            total = i + 1
            if tail is not None:
                selected.append(line)
            elif i >= offset and (limit is None or i < offset + limit):
                text = f'{i + 1}\t{line}' if numbered else line
                if ranged or max_chars is None:
                    selected.append(text)
                else:
                    room = max(0, max_chars - chars)
                    if len(text) > room:
                        truncated = True
                    if room:
                        selected.append(text[:room])
                        chars += len(text[:room])
    start, end, ranged = bounds(params, total)
    if tail is not None and numbered:
        selected = [f'{n}\t{line}' for n, line in enumerate(selected, start + 1)]
    return ''.join(selected), total, start, end, ranged, truncated


def structured_data(content, data_format, path):
    """전체 원문만 받는다. 주인/회원 읽기가 같은 원천 검증과 구조를 쓴다."""
    if data_format != 'json':
        return delimited_data(content, '\t' if data_format == 'tsv' else ',')
    from common.value_semantics import public_result
    try:
        public_result(content, strict=True)
        return json.loads(content)
    except ValueError as exc:
        raise ValueError(f"{path}: JSON 원문 오류: {exc}") from exc


def delimited_data(content, delimiter):
    """CSV/TSV preserves quoted delimiters/newlines and missing/zero cells."""
    import csv
    import io
    reader = csv.reader(io.StringIO(content.lstrip("\ufeff"), newline=''),
                        delimiter=delimiter, strict=True)
    columns = next(reader, None)
    if columns is None:
        return {"items": [], "table": {"columns": [], "rows": []}}
    seen = {}
    for index, name in enumerate(columns, 1):
        if not name or name in seen:
            reason = f"열 {seen[name]}와 중복" if name in seen else "빈 이름"
            raise ValueError(f"CSV/TSV 헤더 열 {index}: {reason}. 비어 있지 않은 고유한 이름이어야 합니다.")
        seen[name] = index
    values = []
    for record, row in enumerate(reader, 2):
        if len(row) != len(columns):
            raise ValueError(
                f"CSV/TSV 레코드 {record} (물리 줄 {reader.line_num})의 셀 수가 헤더와 다릅니다: "
                f"기대 {len(columns)}, 실제 {len(row)}.")
        values.append(row)
    return {"items": [dict(zip(columns, row)) for row in values],
            "table": {"columns": columns, "rows": values}}
