"""Strict, bounded multi-file patch parsing. No fuzzy matches or shell execution."""
MAX_BYTES = 8 * 1024 * 1024


def parse(patch, format='indiebiz-patch/1'):
    if format not in ('indiebiz-patch/1', 'codex-patch'):
        raise ValueError('지원 형식: indiebiz-patch/1, codex-patch (V4A와 다릅니다)')
    if not isinstance(patch, str) or len(patch.encode()) > MAX_BYTES:
        raise ValueError('patch는 8MiB 이하 문자열이어야 합니다')
    lines = patch.splitlines()
    if len(lines) < 3 or lines[0] != '*** Begin Patch' or lines[-1] != '*** End Patch':
        raise ValueError('*** Begin Patch / *** End Patch가 필요합니다')
    entries, entry = [], None
    for line in lines[1:-1]:
        found = False
        for op in ('Add', 'Update', 'Delete'):
            prefix = '*** ' + op + ' File: '
            if line.startswith(prefix):
                entry = {'op': op.lower(), 'path': line[len(prefix):], 'body': []}
                entries.append(entry); found = True; break
        if found:
            continue
        if entry is None:
            raise ValueError('파일 헤더 없는 패치')
        if line.startswith('*** Move to: ') and entry['op'] == 'update':
            if entry.get('move') or entry['body']:
                raise ValueError('Move to는 Update 헤더 바로 뒤 한 번만 사용합니다')
            entry['move'] = line[len('*** Move to: '):]
        else:
            entry['body'].append(line)
    if not entries:
        raise ValueError('빈 패치')
    names = [e['path'] for e in entries] + [e['move'] for e in entries if 'move' in e]
    if len(set(names)) != len(names):
        raise ValueError('같은 경로를 한 패치에서 중복 변경할 수 없습니다')
    return entries


def update(text, body):
    if not body:
        return text
    newline = '\r\n' if '\r\n' in text and '\n' not in text.replace('\r\n', '') else '\n'
    if '\r' in text.replace('\r\n', '') or ('\r\n' in text and newline == '\n'):
        raise ValueError('혼합 줄바꿈은 패치로 수정할 수 없습니다')
    final_newline = text.endswith('\n')
    source = text.replace('\r\n', '\n').splitlines()
    groups, group = [], None
    for line in body:
        if line == '@@' or line.startswith('@@ '):
            group = {'old': [], 'new': [], 'end': False}
            groups.append(group)
        elif line == '*** End of File' and group is not None:
            group['end'] = True
        elif group is not None and line and line[0] in ' +-':
            if line[0] in ' -': group['old'].append(line[1:])
            if line[0] in ' +': group['new'].append(line[1:])
        else:
            raise ValueError('유효하지 않은 hunk: ' + line[:80])
    cursor = 0
    for group in groups:
        old, new = group['old'], group['new']
        if not old:
            if source or len(groups) != 1:
                raise ValueError('빈 문맥 삽입은 빈 파일에만 허용됩니다')
            source = new; continue
        positions = [i for i in range(cursor, len(source) - len(old) + 1)
                     if source[i:i + len(old)] == old and (not group['end'] or i + len(old) == len(source))]
        if len(positions) != 1:
            raise ValueError(f'hunk 문맥은 정확히 한 곳이어야 합니다(일치 {len(positions)}개)')
        i = positions[0]
        source[i:i + len(old)] = new
        cursor = i + len(new)
    return newline.join(source) + (newline if final_newline and source else '')
