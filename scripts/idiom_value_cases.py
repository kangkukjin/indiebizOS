"""관용구 가치 3차: 사전 고정 과제와 결과 오라클. 모델에 정답 코드는 주지 않는다."""
import json
from idiom_experiment_cases import setup as legacy_setup, decoded

CASES = [
    dict(id='five_contexts', candidates=['위치마다읽기'], task='notes/*.txt의 NEEDLE 일치를 파일명 순서로 정렬해 앞 5곳을 일치 줄부터 7줄씩 읽어라. 파일·줄번호·본문을 함께 반환하라. 뒤의 위치는 읽지 마라.'),
    dict(id='partial_contexts', candidates=['위치마다읽기'], task='hits.json은 파일(경로 문자열)·줄번호(1부터 시작하는 정수) 열을 가진 JSON 행 목록이다. 위치 3곳을 순서대로 각각 해당 줄부터 4줄씩 읽어라. 파일·줄번호와 본문을 함께 반환하고, 없는 파일은 그 위치와 오류를 가진 행으로 남겨라. 한 곳의 실패 때문에 나머지를 빼지 마라.'),
    dict(id='latest_full', candidates=['최신범위읽기'], task='reports/*.md 중 수정시각이 최신인 파일의 1~220줄 전체 본문을 반환하라. 파일명 순서로 고르지 마라. 후보는 2개이고 최신 파일은 220줄이다.'),
    dict(id='latest_window', candidates=['최신범위읽기'], task='reports/*.md 중 수정시각이 최신인 파일의 25~31줄 본문만 반환하라. 24줄 이전이나 32줄 이후 본문은 반환하지 마라. 후보는 2개이며 파일명 순서로 고르면 틀린다.'),
    dict(id='empty_latest', candidates=['최신범위읽기'], task='reports/*.rst 중 수정시각이 최신인 파일의 앞 10줄을 반환하라. 해당 파일이 없으면 정상 빈 items를 반환하고 파일 읽기는 시도하지 마라.'),
    dict(id='composite_ledger', candidates=['원장에누적'], task='old.json과 new.json을 읽어 id와 kind 둘이 모두 같을 때만 중복으로 보고 기존 행을 보존해 누적하라. outputs/ledger.json에 JSON으로 저장하라. 같은 id라도 kind가 다르면 별개 행이다.'),
    dict(id='all_locations', candidates=[], task='notes/*.txt에서 NEEDLE의 전체 9곳 위치만 반환하라. 파일·줄번호·일치 내용을 보존하고 주변 본문은 읽지 마라.'),
    dict(id='oldest_window', candidates=[], task='reports/*.md 중 수정시각이 가장 오래된 파일의 전체 본문을 반환하라. 후보 2개 중 오래된 파일은 1줄이다. 최신 파일을 읽으면 실패다.'),
]


def setup(root):
    legacy_setup(root)
    for i in range(9):
        (root / f'notes/{i:02d}.txt').write_text(''.join(
            f'{"NEEDLE " if n == 3 else ""}DOC{i}-LINE{n}\n' for n in range(1, 41)))
    (root / 'hits.json').write_text(json.dumps([
        {'파일': 'notes/00.txt', '줄번호': 3}, {'파일': 'missing.txt', '줄번호': 2},
        {'파일': 'notes/01.txt', '줄번호': 8}], ensure_ascii=False))
    for file, rows in [('old.json', [{'id': 1, 'kind': 'a', 'v': 'old'}]),
                       ('new.json', [{'id': 1, 'kind': 'a', 'v': 'replace'}, {'id': 1, 'kind': 'b', 'v': 'new'}])]:
        (root / file).write_text(json.dumps(rows))


def final_value(result):
    value = decoded(result)
    for _ in range(20):
        if isinstance(value, dict) and 'final_result' in value:
            value = decoded(value['final_result'])
        else:
            return value
    raise ValueError('결과 봉투 깊이 초과')


def content(text):
    # self:read의 줄 범위 메타 헤더만 제외. 본문 줄의 실제 내용과 순서를 비교한다.
    if not isinstance(text, str):
        return None
    lines = text.splitlines()
    if lines and lines[0].startswith('[줄 '):
        lines = lines[1:]
    return lines


def judge(case_id, result, root, observed):
    if not result.get('success'):
        return False, 'runtime: ' + str(result.get('error'))[:1800]
    final = final_value(result)
    rows = final.get('items', []) if isinstance(final, dict) else []
    reads = observed['leaf_calls'].count('self:read')
    if case_id in ('five_contexts', 'partial_contexts'):
        targets = [(f'notes/{i:02d}.txt', 3) for i in range(5)] if case_id == 'five_contexts' else [
            ('notes/00.txt', 3), ('missing.txt', 2), ('notes/01.txt', 8)]
        width = 7 if case_id == 'five_contexts' else 4
        ok = len(rows) == len(targets)
        for row, (file, line) in zip(rows, targets):
            ok = ok and row.get('파일') == file and row.get('줄번호') == line
            if file == 'missing.txt':
                ok = ok and bool(row.get('_error') or row.get('error'))
            else:
                expected = (root / file).read_text().splitlines()[line - 1:line - 1 + width]
                ok = ok and any(content(v) == expected for v in row.values())
        ok = ok and reads == len(targets) + (case_id == 'partial_contexts')
    elif case_id in ('latest_full', 'latest_window', 'oldest_window'):
        file = 'reports/z.md' if case_id == 'oldest_window' else 'reports/a.md'
        expected = (root / file).read_text().splitlines()
        if case_id == 'latest_window':
            expected = expected[24:31]
        ok = content(final) == expected and reads == 1
    elif case_id == 'empty_latest':
        ok = isinstance(final, dict) and final.get('items') == [] and reads == 0
    elif case_id == 'composite_ledger':
        file = root / 'outputs/ledger.json'
        value = decoded(file.read_text()) if file.exists() else None
        if isinstance(value, dict):
            value = value.get('items')
        ok = value == [{'id': 1, 'kind': 'a', 'v': 'old'}, {'id': 1, 'kind': 'b', 'v': 'new'}]
    elif case_id == 'all_locations':
        ok = len(rows) == 9 and reads == 0 and sorted(
            (r.get('파일'), r.get('줄번호'), r.get('내용')) for r in rows) == [
                (f'notes/{i:02d}.txt', 3, f'NEEDLE DOC{i}-LINE3') for i in range(9)]
    else:
        raise ValueError(case_id)
    return bool(ok), '품질 기준 통과' if ok else '품질 기준 미달: ' + next(c['task'] for c in CASES if c['id'] == case_id)


GOLD = {
    'five_contexts': '[self:grep]{path:"notes",pattern:"NEEDLE",file_pattern:"*.txt",limit:20} >> [table:sort]{by:"파일"} >> [fn:위치마다읽기]{개수:5,줄수:7}',
    'partial_contexts': '[self:read]{path:"hits.json"} >> [fn:위치마다읽기]{개수:3,줄수:4}',
    'latest_full': '[fn:최신범위읽기]{폴더:"reports",패턴:"*.md",시작줄:1,줄수:220}',
    'latest_window': '[fn:최신범위읽기]{폴더:"reports",패턴:"*.md",시작줄:25,줄수:7}',
    'empty_latest': '[fn:최신범위읽기]{폴더:"reports",패턴:"*.rst",시작줄:1,줄수:10}',
    'composite_ledger': '$a=[self:read]{path:"old.json"}\n$b=[self:read]{path:"new.json"}\n[fn:원장에누적]{옛것:"$a",새것:"$b",키:["id","kind"],원장:"outputs/ledger.json"}',
    'all_locations': '[self:grep]{path:"notes",pattern:"NEEDLE",file_pattern:"*.txt",limit:20}',
    'oldest_window': '[self:file_find]{path:"reports",pattern:"*.md"} >> [table:sort]{by:"mtime"} >> [table:take]{n:1} >> [self:read]{limit:2}',
}
