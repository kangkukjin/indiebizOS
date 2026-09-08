"""고정 과제·정답. 모델 호출 전에 동결하며, 정답은 모델 프롬프트에 넣지 않는다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: E402,F401

import json
import os

CASES = [
    {'id': 'dedup', 'candidates': ['중복빼고추리기'],
     'task': 'input.json의 목록을 읽어 url 중복은 첫 행을 남기고 제거한 뒤 앞 3개를 반환하라. title과 url을 보존하라.'},
    {'id': 'read_each', 'candidates': ['중복빼고추리기', '각각읽고요약'],
     'task': 'input.json을 읽고 url 중복은 첫 행을 남겨 제거한 뒤 앞 3개 URL만 각각 크롤·요약하라. title·url·요약을 반환하고, 크롤 실패도 해당 title·url과 오류를 가진 행으로 남겨라. 더 뒤의 URL은 읽지 마라.'},
    {'id': 'accumulate', 'candidates': ['원장에누적'],
     'task': 'old.json과 new.json을 읽어 id 기준으로 합쳐 outputs/ledger.json에 JSON으로 저장하라. 같은 id면 기존 행을 유지하고 새 id만 덧붙인다. 결과 파일을 만든 뒤 저장 결과를 반환하라.'},
    {'id': 'latest', 'candidates': ['최신파일읽기'],
     'task': 'reports 폴더의 *.md 중 수정시각이 가장 최근인 파일의 앞 160줄을 읽어 반환하라. 파일명의 사전순으로 고르지 마라.'},
    {'id': 'snippets', 'candidates': ['좁혀서읽기'],
     'task': 'notes 폴더의 *.txt에서 NEEDLE을 찾고 앞 3곳을 일치 줄부터 30줄씩 읽어 반환하라. 파일과 줄 위치를 보존하라.'},
    {'id': 'edit', 'candidates': ['고치고확인하기'],
     'task': 'note.txt의 초안을 완료로 바꾸고, 완료가 실제로 들어간 줄 위치를 반환하라.'},
    {'id': 'all_hits', 'candidates': ['좁혀서읽기'],
     'task': 'notes 폴더의 *.txt에서 NEEDLE이 등장하는 모든 위치를 반환하라. 전체 9곳이며 3곳만 반환하면 실패다. 파일·줄번호·일치 내용을 반환하라.'},
    {'id': 'latest_tail', 'candidates': ['최신파일읽기'],
     'task': 'reports 폴더의 *.md 중 수정시각이 가장 최근인 파일을 찾아 끝의 LAST_MARKER가 있는 줄까지 포함해 전체 내용을 반환하라. 최신 파일은 220줄이다.'},
]


def setup(root):
    root.mkdir(parents=True, exist_ok=True)
    rows = [{'title': 'first', 'url': 'https://fixture.test/a'},
            {'title': 'duplicate', 'url': 'https://fixture.test/a'},
            {'title': 'broken', 'url': 'https://fixture.test/bad'},
            {'title': 'third', 'url': 'https://fixture.test/c'},
            {'title': 'excluded', 'url': 'https://fixture.test/d'}]
    for name, payload in [('input.json', rows), ('old.json', [{'id': 1, 'value': 'old'}]),
                          ('new.json', [{'id': 1, 'value': 'replacement'}, {'id': 2, 'value': 'new'}])]:
        (root / name).write_text(json.dumps(payload), encoding='utf-8')
    (root / 'note.txt').write_text('제목\n초안\n', encoding='utf-8')
    (root / 'reports').mkdir()
    (root / 'reports/z.md').write_text('OLD_REPORT\n', encoding='utf-8')
    (root / 'reports/a.md').write_text('NEW_REPORT\n' + ''.join(f'line {i}\n' for i in range(2, 220)) + 'LAST_MARKER\n', encoding='utf-8')
    os.utime(root / 'reports/z.md', (1000000000, 1000000000))
    os.utime(root / 'reports/a.md', (1100000000, 1100000000))
    (root / 'notes').mkdir()
    for i in range(9):
        (root / f'notes/{i:02d}.txt').write_text(f'NEEDLE evidence-{i}\n' + 'context\n' * 29, encoding='utf-8')


def decoded(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def judge(case_id, result, root, observed):
    """코드 모양/함수 호출 여부를 보지 않는 결과 오라클."""
    if not result.get('success'):
        return False, 'runtime: ' + str(result.get('error', '실행 실패'))[:1800]
    final = decoded(result.get('final_result', result))
    text = json.dumps(final, ensure_ascii=False)
    rows = final.get('items', []) if isinstance(final, dict) else []
    if case_id == 'dedup':
        ok = [(r.get('title'), r.get('url')) for r in rows] == [
            ('first', 'https://fixture.test/a'), ('broken', 'https://fixture.test/bad'), ('third', 'https://fixture.test/c')]
    elif case_id == 'read_each':
        ok = (len(rows) == 3 and {r.get('title') for r in rows} == {'first', 'broken', 'third'}
              and any(r.get('title') == 'broken' and (r.get('_error') or r.get('error')) for r in rows)
              and all(r.get('url') and ('SUMMARY:' in json.dumps(r) or r.get('title') == 'broken') for r in rows)
              and sorted(observed['crawl']) == ['https://fixture.test/a', 'https://fixture.test/bad', 'https://fixture.test/c'])
    elif case_id == 'accumulate':
        p = root / 'outputs/ledger.json'
        v = decoded(p.read_text()) if p.exists() else None
        if isinstance(v, dict):
            v = v.get('items')
        ok = v == [{'id': 1, 'value': 'old'}, {'id': 2, 'value': 'new'}]
    elif case_id == 'latest':
        ok = 'NEW_REPORT' in text and 'line 160' in text and 'OLD_REPORT' not in text and 'LAST_MARKER' not in text
    elif case_id == 'snippets':
        ok = len(rows) == 3 and all('evidence-' in json.dumps(r) and 'context' in json.dumps(r) for r in rows)
        ok = ok and all(('파일' in r or 'path' in r) and ('줄번호' in r or 'line' in r) for r in rows)
    elif case_id == 'edit':
        ok = (root / 'note.txt').read_text() == '제목\n완료\n' and '완료' in text and ('줄번호' in text or 'line' in text)
    elif case_id == 'all_hits':
        ok = len(rows) == 9 and all(f'evidence-{i}' in text for i in range(9))
    elif case_id == 'latest_tail':
        ok = 'NEW_REPORT' in text and 'LAST_MARKER' in text and 'line 160' in text and 'OLD_REPORT' not in text
    else:
        raise ValueError(case_id)
    return bool(ok), '품질 기준 통과' if ok else '품질 기준 미달: ' + next(c['task'] for c in CASES if c['id'] == case_id)


GOLD = {
    'dedup': '[self:read]{path:"input.json"} >> [fn:중복빼고추리기]{키:"url",개수:3}',
    'read_each': '[self:read]{path:"input.json"} >> [fn:중복빼고추리기]{키:"url",개수:3} >> [fn:각각읽고요약]{개수:3,지시:"짧게 요약"}',
    'accumulate': '$a = [self:read]{path:"old.json"}\n$b = [self:read]{path:"new.json"}\n[fn:원장에누적]{옛것:"$a",새것:"$b",키:"id",원장:"outputs/ledger.json"}',
    'latest': '[fn:최신파일읽기]{폴더:"reports",패턴:"*.md"}',
    'snippets': '[self:grep]{pattern:"NEEDLE",path:"notes",file_pattern:"*.txt",limit:6} >> [table:take]{n:3} >> [table:each]{do:"[self:read]{path: \'$it.파일\', start_line: $it.줄번호, limit:30}",keep:["파일","줄번호"],collect:true}',
    'edit': '[fn:고치고확인하기]{파일:"note.txt",앞:"초안",뒤:"완료",확인:"완료"}',
    'all_hits': '[self:grep]{path:"notes",pattern:"NEEDLE",file_pattern:"*.txt",limit:100}',
    'latest_tail': '[self:file_find]{path:"reports",pattern:"*.md"} >> [table:sort]{by:"mtime",desc:true} >> [table:take]{n:1} >> [self:read]{limit:300}',
}
