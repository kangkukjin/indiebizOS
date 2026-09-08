#!/usr/bin/env python3
"""평탄 팁 행의 출처를 중첩한다. stdin JSON 인자: src, out (경로 필수)."""
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import boot_paths  # noqa: E402,F401
from runtime_utils import expand_body_path, get_base_path  # noqa: E402


def resolve_path(raw):
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError('src와 out은 비어 있지 않은 경로 문자열이어야 합니다.')
    path = Path(expand_body_path(raw))
    return (path if path.is_absolute() else get_base_path() / path).resolve()


def convert(rows):
    if not isinstance(rows, list):
        raise ValueError('입력은 배열 또는 {items: 배열}이어야 합니다.')
    out = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f'{i + 1}행이 객체가 아닙니다.')
        required = ('tip', 'how', 'topic', 'video_id', 'title', 'channel', 'url', 'date', 'report', 'try_candidate')
        missing = [k for k in required if k not in row]
        if missing:
            raise ValueError(f'{i + 1}행 필드 누락: {", ".join(missing)}')
        if not isinstance(row['try_candidate'], bool):
            raise ValueError(f'{i + 1}행 try_candidate는 true/false여야 합니다.')
        item = {k: row[k] for k in ('tip', 'how', 'topic', 'date', 'report', 'try_candidate')}
        item['source'] = {k: row[k] for k in ('video_id', 'title', 'channel', 'url')}
        out.append(item)
    return {'items': out, 'count': len(out)}


def main():
    try:
        args = json.loads(sys.stdin.read() or '{}')
        if not isinstance(args, dict):
            raise ValueError('인자는 JSON 객체여야 합니다.')
        src, dst = resolve_path(args.get('src')), resolve_path(args.get('out'))
        data = json.loads(src.read_text(encoding='utf-8'))
        result = convert(data.get('items') if isinstance(data, dict) else data)
        dst.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=dst.name + '.', suffix='.tmp', dir=dst.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
                f.write('\n')
            os.replace(temp, dst)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        print(json.dumps({'success': True, 'path': str(dst), 'count': result['count']}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'success': False, 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
