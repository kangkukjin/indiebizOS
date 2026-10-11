"""Publish completed files with an explicit collision policy; never erase first."""
import os
from pathlib import Path
import tempfile


def collision_policy(value, default='fail'):
    policy = default if value is None else value
    if policy not in ('fail', 'overwrite', 'rename'):
        raise ValueError('if_exists는 fail·overwrite·rename 중 하나입니다.')
    return policy


def publish_file(destination, writer, *, if_exists='fail', guard=None):
    """writer(temp) finishes before a link/replace publishes bytes in the same directory.

    Rename/fail never overwrite a racing writer. Overwrite is explicit and atomic
    per file, not a transaction over a directory or a whole workflow.
    """
    policy = collision_policy(if_exists)
    requested = Path(destination).absolute()

    def check(path):
        if guard:
            error = guard(str(path))
            if error:
                raise ValueError(str(error))
        if path.is_symlink() and policy != 'rename':
            raise ValueError('출력 대상의 심볼릭 링크는 교체하지 않습니다.')
        if path.is_dir():
            raise ValueError('파일 출력 대상이 폴더입니다.')

    check(requested)
    if policy == 'fail' and requested.exists():
        raise FileExistsError(f'output 파일이 이미 있습니다: {requested}. if_exists를 명시하세요.')
    requested.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.publish-', suffix=requested.suffix, dir=requested.parent)
    os.close(fd)
    temp = Path(name)
    try:
        value = writer(temp)
        if not temp.is_file() or temp.is_symlink():
            raise ValueError('작성기가 정상 결과 파일을 만들지 않았습니다.')
        with temp.open('rb') as stream:
            os.fsync(stream.fileno())
        target, index = requested, 1
        while True:
            check(target)
            replaced = target.exists()
            try:
                if policy == 'overwrite':
                    os.replace(temp, target)
                else:
                    os.link(temp, target)
                break
            except FileExistsError:
                if policy != 'rename':
                    raise
                index += 1
                target = requested.with_name(f'{requested.stem} ({index}){requested.suffix}')
        return value, {'path': str(target), 'requested_path': str(requested),
                       'if_exists': policy, 'replaced_existing': replaced,
                       'renamed': str(target) != str(requested)}
    finally:
        temp.unlink(missing_ok=True)
