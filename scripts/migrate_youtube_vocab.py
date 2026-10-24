#!/usr/bin/env python3
"""YouTube 실행 용례를 limbs:youtube의 op로 이관한다.

기본은 dry-run, --apply는 SQLite backup과 파일 사본을 data/_backups에 남긴다.
--reindex는 그 백업과 달라진 용례만 재색인한다(모델 로딩 필요).
과거 사건 로그·보고서는 수정하지 않는다. 실행 예제와 저장 프로그램만 옮긴다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: F401,E402

import argparse
import ast
import json
import re
import shutil
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
# retired-ok: 이전 실행 계약을 새 계약으로 옮기는 입력 이름이다.
OLD = {'sense:video': 'info', 'sense:search_youtube': 'search', 'limbs:music': 'play'}  # retired-ok: 이관 입력
PATTERN = re.compile(r'\[(' + '|'.join(map(re.escape, OLD)) + r')\]')


def _parts(text, start):
    """괄호·문자열을 보존하며 호출 인자의 최상위 쉼표만 나눈다."""
    quote = None
    escape = False
    stack = ['{']
    begin = start + 1
    parts = []
    for i in range(begin, len(text)):
        ch = text[i]
        if quote:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in '\"\'':
            quote = ch
        elif ch in '{[(':
            stack.append(ch)
        elif ch in '}])':
            stack.pop()
            if not stack:
                parts.append(text[begin:i])
                return parts, i + 1
        elif ch == ',' and len(stack) == 1:
            parts.append(text[begin:i])
            begin = i + 1
    raise ValueError('닫히지 않은 IBL 인자 — 자동 이관하지 않음')


def transform(code):
    if not isinstance(code, str):
        return code
    edits = []
    # 예약·원격 실행의 code/do는 문자열이지만 실행 프로그램이다.
    # 일반 본문/인용 문자열은 그대로 두고, 이 두 계약만 재귀 이관한다.
    literals = re.compile(r'''(?P<prefix>\b(?:code|do)\s*:\s*)(?P<value>"""(?:\\.|(?!""")[\s\S])*"""|''' + "'''(?:\\\\.|(?!''')[\\s\\S])*'''" + r'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''')
    for literal in literals.finditer(code):
        value = ast.literal_eval(literal["value"])
        updated = transform(value)
        if updated != value:
            edits.append((literal.start("value"), literal.end("value"),
                          json.dumps(updated, ensure_ascii=False)))
    # 호출 인자에 실린 원문·문자열은 실행 코드가 아니다.
    quoted = set()
    quote = None
    escape = False
    for i, char in enumerate(code):
        if quote:
            quoted.add(i)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
    for match in PATTERN.finditer(code):
        if match.start() in quoted:
            continue
        name = match[1]
        start = match.end()
        while start < len(code) and code[start].isspace():
            start += 1
        parts, end = _parts(code, start) if start < len(code) and code[start] == '{' else ([], match.end())
        default = OLD[name]
        has_op = any(re.match(r'\s*["\']?op["\']?\s*:', p) for p in parts)
        # 이름과 생략된 기본값만 바꾼다. 기존 인자/공백/문자열을 보존한다.
        edits.append((match.start(), match.end(), '[limbs:youtube]'))
        if not has_op:
            if start < len(code) and code[start] == '{':
                prefix = f'op: "{default}"' + (', ' if code[start + 1:end - 1].strip() else '')
                edits.append((start + 1, start + 1, prefix))
            else:
                edits.append((match.end(), match.end(), '{op: "' + default + '"}'))
    for start, end, replacement in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        code = code[:start] + replacement + code[end:]
    return code


def _walk(value):
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, list):
        return [_walk(v) for v in value]
    if isinstance(value, dict):
        result = {k: _walk(v) for k, v in value.items()}
        code = result.get('ibl_code') or result.get('code')
        if isinstance(code, str) and 'nodes' in value and result != value:
            result['nodes'] = ','.join(sorted(set(re.findall(r'\[(\w+):\w+\]', code))))
        return result
    return value


def migrate(root=ROOT, apply=False):
    if apply and (root / 'data/workflows/catalog.json').exists():
        raise ValueError('이 구형 일회성 이관기는 은퇴했습니다. 관용구는 공통 개정 관문으로 수정하세요.')
    backup = root / 'data/_backups/2026-10-20_youtube_vocab'
    stats = {}
    db_path = root / 'data/ibl_usage.db'
    if db_path.exists():
        with sqlite3.connect(db_path, timeout=30) as db:
            changes = []
            for rid, code in db.execute('SELECT id, ibl_code FROM ibl_examples'):
                new = transform(code)
                if new != code:
                    nodes = ','.join(sorted(set(re.findall(r'\[(\w+):\w+\]', new))))
                    changes.append((new, nodes, rid, code))
            stats['examples'] = len(changes)
            if changes and apply:
                backup.mkdir(parents=True, exist_ok=True)
                snapshot = backup / 'ibl_usage.db'
                if not snapshot.exists():
                    with sqlite3.connect(snapshot) as dest:
                        db.backup(dest)
                db.executemany('UPDATE ibl_examples SET ibl_code=?, nodes=? WHERE id=? AND ibl_code=?', changes)
                db.commit()
    paths = list((root / 'data/training').glob('*.json'))
    paths += list((root / 'data/workflows').glob('*.yaml'))
    paths += list((root / 'data/instruments').glob('*.yaml'))
    paths += list((root / 'data/idioms').glob('*.json'))
    paths += list((root / 'data/idioms').glob('*.ibl'))
    # 등록된 프로그램 원천만: 결과·사건 원문에는 치환을 적용하지 않는다.
    paths += [root / 'data/scripts/registry.yaml']
    paths += [root / 'data/calendar_events.json']
    import yaml
    for path in paths:
        if not path.exists():
            continue
        original = path.read_text()
        data = (original if path.suffix == '.ibl' else json.loads(original)
                if path.suffix == '.json' else yaml.safe_load(original))
        updated = _walk(data)
        if path.name == 'calendar_events.json':
            # 완료된 사건 원문은 보존하고 재실행될 활성 예약만 이관한다.
            updated = {**data, "events": [
                _walk(event) if event.get("enabled", True) else event
                for event in data.get("events", [])]}
        if updated == data:
            continue
        stats[str(path.relative_to(root))] = 1
        if apply:
            dest = backup / path.relative_to(root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(path, dest)
            output = (updated if path.suffix == '.ibl' else json.dumps(updated, ensure_ascii=False, indent=2) + '\n'
                      if path.suffix == '.json' else yaml.safe_dump(updated, allow_unicode=True, sort_keys=False))
            path.write_text(output)
    # 원 관측 날짜·필드·원천은 그대로 둔다. 모든 op가 섞인 재생 집계는
    # 특정 op의 관측으로 가장하지 않고 백업에 보존한다.
    observation_path = root / 'data/ibl_return_shapes.json'
    if observation_path.exists():
        shapes = json.loads(observation_path.read_text()).get('shapes', {})
        mapping = {}
        for key in shapes:
            name, sep, op = key.partition('#')
            if name not in OLD:
                continue
            target_op = op if sep else OLD[name]
            mapping[key] = ('limbs:youtube#' + target_op
                            if target_op not in ('feed', 'watch', 'history')
                            and (sep or OLD[name] != 'play') else None)
        if mapping:
            stats['observations'] = len(mapping)
            if apply:
                dest = backup / 'ibl_return_shapes.json'
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    shutil.copy2(observation_path, dest)
                from ibl_shape_sweep import rekey_catalog
                rekey_catalog(mapping, observation_path)
    return stats


def reindex():
    from ibl_usage_db import IBLUsageDB
    snapshot = ROOT / 'data/_backups/2026-10-20_youtube_vocab/ibl_usage.db'
    if not snapshot.exists():
        return 0
    with sqlite3.connect(snapshot) as old, sqlite3.connect(ROOT / 'data/ibl_usage.db') as live:
        previous = dict(old.execute('SELECT id, ibl_code FROM ibl_examples'))
        rows = [(i, intent, code) for i, intent, code in
                live.execute('SELECT id, intent, ibl_code FROM ibl_examples')
                if i in previous and code != previous[i]]
    if not rows:
        return 0
    db = IBLUsageDB()
    if not db._load_model_sync():
        raise RuntimeError('용례 이관 완료, 임베딩 모델 부재로 재색인 미완료')
    # vec0의 갱신은 DELETE→INSERT여야 한다. strict 경로가 실패를 숨기지 않는다.
    for rid, intent, code in rows:
        db._index_single(rid, intent, code, strict=True)
    return len(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--reindex', action='store_true')
    args = parser.parse_args()
    print(json.dumps(migrate(apply=args.apply), ensure_ascii=False))
    if args.reindex:
        print(json.dumps({'reindexed_rows': reindex()}))
