"""Generate synthetic cases; no legal answer generation or core work here."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-11_54회차'
HERE = Path(__file__).resolve().parent.parent


def prepare():
    patterns = [('주택임대차보호법', n) for n in ('제3조', '제3조의3', '제6조의3', '제7조')]
    patterns += [('상가건물 임대차보호법', '제10조'), ('상가건물 임대차보호법', '제10조의4'),
                 ('민법', '제623조'), ('민법', '제99999조'), ('가상임대차자동승소법', '제1조'),
                 ('주택임대차보호법', '제6조의3')]
    cases = []
    for n in range(120):
        law, no = patterns[n % len(patterns)]
        cases.append(dict(id=f'L{n+1:03}', law=law, no=no,
                          event_date='2018-01-10' if n % 10 == 9 else '2026-10-10',
                          required_documents=['계약서', '차임 내역', '통지 증거'],
                          documents=['계약서', '차임 내역', '통지 증거'][:n % 4],
                          statement=f'합성 상담 {n+1}. 고객은 {law} {no}를 근거로 갱신 또는 반환 가능 여부를 묻습니다. 사실과 당시 적용법 확인이 필요합니다.'))
    variants = {'base': cases, 'variant': [dict(c, documents=[], event_date='2010-01-01') for c in reversed(cases[:30])]}
    variants['variant'][0]['no'] = '제88888조'
    variants['new'] = [dict(cases[0], id='W1', law='근로기준법', no='제23조'),
                       dict(cases[0], id='W2', law='근로기준법', no='제28조', documents=['계약서'])]
    variants['empty'] = []
    for who in ('trainer', 'ai'):
        for name, rows in variants.items():
            if who == 'ai' and name in ('new', 'empty'):
                continue
            folder = OUT / who / name
            (folder / 'out').mkdir(parents=True, exist_ok=True)
            data = dict(as_of='2026-10-11', cases=rows,
                        supplements=[dict(key='english', target='eng_law', query='주택임대차보호법'),
                                     dict(key='term', target='law_term', query='대항력')])
            (folder / 'input.json').write_text(json.dumps(data, ensure_ascii=False, indent=2))
    task = (HERE / 'task.md').read_text().split('## 자연어 요청 원문\n')[1].split('\n## 입력과 변형')[0]
    for name in ('base', 'variant'):
        folder = OUT / 'ai' / name
        prompt = task + f'\n입력: {folder / "input.json"}\n출력: {folder / "out"}\n'
        if name == 'variant':
            prompt = '같은 과제의 조건이 바뀌었습니다. 새 입력 30건에 동일한 작업을 수행하세요.\n' + prompt
        (OUT / f'ai_{name}.txt').write_text(prompt)
    print(OUT)


if __name__ == '__main__':
    prepare()
