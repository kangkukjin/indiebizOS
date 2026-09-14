"""회원 문서 어댑터: 명시된 path만 기기에서 받고, 출력은 확인된 기기 파일만 반환.

감사 범위: office_ops의 읽기·fill 함수, fs_read_range, doc_ir. 모델이 준
허브 경로/출력 경로/컨텍스트는 기존 핸들러에 전달하지 않는다. ZIP은 크기와
외부 relationship을 검사하고 DOCX 이미지 추출은 끈다. 코드 실행/셸 없음.
"""
import base64
import importlib.util
import json
import re
import zipfile
from pathlib import Path

MAX_BYTES = 32 * 1024 * 1024


def _sibling(name):
    spec = importlib.util.spec_from_file_location('_member_doc_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _receive(params, exchange, workspace):
    raw = params.get('path')
    if not isinstance(raw, str) or not raw or raw.startswith('member-file:'):
        raise ValueError('명시된 회원 파일 path 필요')
    result = exchange({'op': 'read', 'path': raw, 'encoding': 'base64'})
    if result.get('success') is not True:
        return None, result
    content = result.get('content', '')
    if not isinstance(content, str) or len(content) > (MAX_BYTES + 2) // 3 * 4:
        raise ValueError('파일 크기 초과')
    data = base64.b64decode(content, validate=True)
    if len(data) > MAX_BYTES:
        raise ValueError('파일 크기 초과')
    suffix = Path(raw).suffix.lower()
    if params.get('format') in ('pdf', 'docx', 'xlsx', 'xls', 'xlsm'):
        suffix = '.' + params['format']
    if suffix not in ('.pdf', '.docx', '.xlsx', '.xls', '.xlsm'):
        suffix = '.txt'
    path = workspace / ('input' + suffix)
    path.write_bytes(data)
    if suffix in ('.docx', '.xlsx', '.xlsm'):
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(e.file_size for e in entries) > 128*1024*1024:
                raise ValueError('압축 해제 한도 초과')
            # 외부 파일·템플릿 참조가 파서의 추가 입력이 되지 않게 한다.
            from xml.etree import ElementTree
            for e in entries:
                if e.filename.endswith('.rels'):
                    for rel in ElementTree.fromstring(archive.read(e)):
                        if rel.get('TargetMode') == 'External' and not rel.get('Type', '').endswith('/hyperlink'):
                            raise ValueError('외부 자원 연결 문서')
    return path, None


def read_document(params, command, exchange, workspace):
    ranges = _sibling('fs_read_range')
    p = ranges.normalize_read_range({k: v for k, v in params.items() if k in (
        'offset', 'start', 'limit', 'tail', 'start_line', 'end_line', 'end', 'numbered',
        'blocks', 'tables', 'sheet', 'max_rows', 'max_blocks', 'pages')})
    path, failure = _receive(params, exchange, workspace)
    if failure is not None:
        return failure
    fmt = params.get('format') or path.suffix.lstrip('.')
    if fmt not in ('pdf', 'docx', 'xlsx', 'xls', 'xlsm', 'txt', 'text', 'md', 'json', 'csv'):
        raise ValueError('지원하지 않는 형식')
    if fmt in ('pdf', 'docx', 'xlsx', 'xls', 'xlsm'):
        p.update(path=str(path), extract_images=False)
        if fmt == 'pdf' and isinstance(p.get('pages'), str):
            pages = []
            for part in p['pages'].split(','):
                match = re.fullmatch(r'\s*(\d+)(?:-(\d+))?\s*', part)
                if not match:
                    raise ValueError('페이지 범위 오류')
                start, end = int(match[1]), int(match[2] or match[1])
                if start < 1 or end < start or end - start > 10000:
                    raise ValueError('페이지 범위 오류')
                pages.extend(range(start - 1, end))
            p['pages'] = pages
        office = _sibling('office_ops')
        fn = office.read_pdf if fmt == 'pdf' else office.read_docx if fmt == 'docx' else office.read_xlsx
        result = json.loads(fn(p, str(workspace)))
        if result.get('success') is False:
            raise ValueError('문서 읽기 실패')
        # 명시적인 문서 경로 필드만 기기의 원본으로 되돌린다. 본문은 검색/치환하지 않는다.
        for key in ('path', 'file_path'):
            if key in result:
                result[key] = params['path']
        return result
    lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
    start, end, ranged = ranges.text_read_bounds(p, len(lines))
    text = ''.join(lines[start:end])
    if p.get('blocks'):
        from doc_ir import markdown_to_blocks
        items = markdown_to_blocks(text)
        return {'success': True, 'items': items, 'count': len(items), 'message': text,
                'start_line': start + 1 if text else None, 'end_line': end if text else None,
                'total_lines': len(lines), 'path': params['path']}
    if p.get('numbered'):
        text = ''.join(f'{n}\t{line}' for n, line in enumerate(lines[start:end], start + 1))
    if len(text) > 1000000:
        return {'success': True, 'text': text[:1000000], 'truncated': True, 'total_lines': len(lines)}
    return text


def fill_document(params, command, exchange, workspace):
    path, failure = _receive(params, exchange, workspace)
    if failure is not None:
        return failure
    if path.suffix not in ('.pdf', '.docx'):
        raise ValueError('PDF/DOCX 양식 필요')
    data = params.get('data') or {}
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise ValueError('필드 매핑 필요')
    output = workspace / ('output' + path.suffix)
    result = json.loads(_sibling('office_ops').fill_op(
        {'path': str(path), 'output': str(output), 'data': data, 'flatten': bool(params.get('flatten'))}, str(workspace)))
    if result.get('success') is not True:
        raise ValueError('양식 변환 실패')
    if not data:
        result['path'] = params['path']
        return result
    raw = params['path']
    dest = params.get('output') or str(Path(raw).with_name(Path(raw).stem + '_filled' + path.suffix))
    if not isinstance(dest, str) or not dest or output.stat().st_size > MAX_BYTES:
        raise ValueError('출력 크기/경로 오류')
    receipt = exchange({'op': 'write', 'path': dest, 'encoding': 'base64',
                        'content': base64.b64encode(output.read_bytes()).decode('ascii')})
    if receipt.get('success') is not True:
        return receipt  # 승인 거절·시간 초과를 성공으로 바꾸지 않는다.
    result['path'] = receipt.get('path', dest)
    result['files'] = [{'path': result['path'], 'bytes': output.stat().st_size, 'on': 'body'}]
    result['saved'] = True
    return result
