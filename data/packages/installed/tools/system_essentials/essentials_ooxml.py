"""Office ZIP의 비대상 파트를 보존하는 입출력. 산출물은 새 파일에만 원자 게시한다."""
import hashlib
import io
import os
from pathlib import Path
import tempfile
import zipfile

from lxml import etree
from runtime_utils import expand_body_path


def xml(data):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False)
    root = etree.fromstring(data, parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError('DTD가 든 Office XML은 지원하지 않습니다.')
    return root


def encoded(root):
    return etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)


def resolve(params, name='path'):
    raw = params.get(name)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f'{name} 파일 경로가 필요합니다.')
    p = Path(expand_body_path(raw))
    return (p if p.is_absolute() else Path(params.get('_project_path') or '.') / p).resolve()


def load(params, suffixes):
    path = resolve(params)
    if path.suffix.lower() not in suffixes:  # vj-ok: Office 파일 형식 확장자 프로토콜
        raise ValueError(f'지원 형식: {", ".join(suffixes)}')
    if path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError('Office 파일 상한은 100MB입니다.')
    raw = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if len(infos) > 20000 or sum(i.file_size for i in infos) > 300 * 1024 * 1024:
            raise ValueError('압축 해제 크기/파트 수 상한을 초과했습니다.')
        if len({i.filename for i in infos}) != len(infos):
            raise ValueError('중복 ZIP 파트가 있습니다.')
        if any(i.filename.startswith('_xmlsignatures/') for i in infos):
            raise ValueError('서명된 Office 파일은 편집하면 서명이 무효화되므로 지원하지 않습니다.')
        parts = {i.filename: archive.read(i) for i in infos}
        comment = archive.comment
    return path, hashlib.sha256(raw).hexdigest(), parts, infos, comment


def output_path(params, source, suffix):
    dest = resolve(params, 'output') if params.get('output') else source.with_name(source.stem + suffix + source.suffix)
    if dest == source or dest.suffix.lower() != source.suffix.lower():  # vj-ok: 출력 파일 형식 확장자 프로토콜
        raise ValueError('output은 원본과 다른 같은 확장자의 파일이어야 합니다.')
    if dest.exists():
        raise ValueError('output 파일이 이미 있습니다. 새 출력 경로를 지정하세요.')
    guard = params.get('_path_guard')
    if not callable(guard):
        raise ValueError('쓰기 범위 검증기를 사용할 수 없습니다.')
    error = guard(str(dest), params.get('_project_path') or '.')
    if error:
        raise ValueError(str(error))
    return dest


def save(source, digest, dest, parts, infos, comment):
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise ValueError('원본이 실행 중 변경되었습니다. 다시 조회하세요.')
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.office-', suffix=dest.suffix, dir=dest.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.comment = comment
                for info in infos:
                    if info.filename in parts:
                        archive.writestr(info, parts[info.filename])
                old = {i.filename for i in infos}
                for name, data in parts.items():
                    if name not in old:
                        archive.writestr(name, data)
            stream.flush()
            os.fsync(stream.fileno())
        # 경합 중 같은 이름의 출력을 덮어쓰지 않는다. 링크 생성이 원자 게시 경계다.
        os.link(temp, dest)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return str(dest)
