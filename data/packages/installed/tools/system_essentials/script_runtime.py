"""등록 스크립트 동기/분리 러너가 공유하는 출력 판정·원자 파일 쓰기."""
import json
import os
import tempfile
import threading

STATE_LOCK = threading.RLock()


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def parse_output(stdout):
    """종료 코드와 별개로 JSON 결과의 명시적 실패를 보존한다."""
    try:
        parsed = json.loads(stdout)
    except (ValueError, TypeError):
        return None, None
    if not isinstance(parsed, dict):
        return None, None
    error = parsed.get('error')
    if parsed.get('success') is False or error:
        return {**parsed, 'success': False}, str(error or '스크립트가 실패 결과를 반환했습니다.')
    if isinstance(parsed.get('items'), list) or isinstance(parsed.get('table'), dict):
        return parsed, None
    return None, None
