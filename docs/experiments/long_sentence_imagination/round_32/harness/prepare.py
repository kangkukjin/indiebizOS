"""Synthetic fixtures and independent oracle; no task computation for IBL."""
import json
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-07_32회차'
DOC = Path(__file__).resolve().parents[1]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def generate(out):
    sites = ['서울', '부산', '대전']
    pairs = [('A|B', 'C'), ('A', 'B|C'), ('한글', '표준'),
             ('normal', 'x'), ('normal', 'y'), ('empty', '')]
    opening = [{'site': site, 'sku': sku, 'lot': lot, 'opening': 1000}
               for site in sites for sku, lot in pairs]
    for variant in ['base', 'missing']:
        source = out / 'source' / variant
        dump(source / 'opening.json', opening)
        dump(source / 'sites.json', [{'site': s, 'file': f'{s}.json'} for s in sites])
        totals = defaultdict(int)
        count = 0
        for si, site in enumerate(sites):
            if variant == 'missing' and site == '부산':
                continue
            rows = []
            for i in range(600):
                sku, lot = pairs[i % len(pairs)]
                # Canonically equivalent strings from different operating systems.
                if i % 12 == 2:
                    sku = unicodedata.normalize('NFD', sku)
                quantity = (i % 7) - 2
                rows.append({'event': f'{si}-{i}', 'site': site, 'sku': sku,
                             'lot': lot, 'quantity': quantity})
                totals[(site, unicodedata.normalize('NFC', sku), lot)] += quantity
            count += len(rows)
            dump(source / f'{site}.json', rows)
        expected = []
        for row in opening:
            missing = variant == 'missing' and row['site'] == '부산'
            qty = None if missing else totals[(row['site'], row['sku'], row['lot'])]
            expected.append({**row, 'movement': qty,
                             'closing': None if missing else row['opening'] + qty,
                             'status': '원천 누락' if missing else '확인'})
        dump(out / 'oracle' / f'{variant}.json', {'rows': expected, 'events': count})


def main():
    generate(OUT)
    request = '''세 지점의 기초재고와 이동기록을 대사해 줘. sites.json의 지점별 파일을 모두 읽고 site·sku·lot 조합별 quantity 합계를 opening.json의 기초재고와 연결해 마감재고를 계산해. sku의 유니코드 조합형/완성형은 같은 품목이야. lot의 빈 문자열도 정상 로트이며 | 문자는 실제 코드 일부야. 원천 파일이 없으면 해당 지점의 이동·마감재고는 null로 남기고 상태에 원천 누락을 표시해. 정상 원천에서 이동이 없는 품목만 이동량 0이야. 각 기초재고 행의 site,sku,lot,opening,movement,closing,status를 빠짐없이 JSON rows에 저장하고 events(읽은 이동 행수), missing_sites도 기록해. 지점별 기초·이동·마감 합계와 누락 여부를 Markdown 보고서에 써 줘. 입력은 바꾸지 말고 저장 결과를 재독해 전건과 합계가 원자료와 맞는지 검증해. 자료 생성기·oracle·trainer·다른 실행자의 코드나 결과는 열지 마. 자기 산출물은 후속 작업에서 재사용해도 돼.'''
    (DOC / 'request.txt').write_text(request)
    (DOC / 'variant_request.txt').write_text('조건이 바뀌었어. 같은 업무를 source/missing 자료로 다시 해 줘. 부산 파일이 없을 때 0이나 기존 값으로 추정하지 말고 null과 원천 누락으로 표시해. 앞 산출물은 보존하고 별도 폴더에 저장해. 자기 방법은 재사용해도 되지만 다른 실행자·oracle·생성기는 읽지 마.')
    (DOC / 'task.md').write_text('# 32회차 사전 과제\n\n' + request + '\n\n합성자료: 3지점×600이동=1800행, 기초18행. 원천 누락 변형은 부산 부재로 1200행·누락6행. 정상 그룹 이동 합계는 독립 oracle로 사전 계산. empty 로트도 정상 키. NFC/NFD·구분자 포함 복합키를 보존한다. 원자료 조회/집계/대사/쓰기/재독을 IBL로, Python은 자료 준비·운반·독립 대조만 한다. 공개 교재·describe만 보고 초안 작성. 시간상한60분, 최초 작성비용과 수리비용 분리.\n')
    code = (DOC / 'drafts/main_v0.ibl').read_text()
    for variant in ['base', 'missing']:
        inputs = {'source': str(OUT / 'source' / variant), 'out': str(OUT / 'trainer' / variant)}
        dump(OUT / f'{variant}_check.json', {'code': code, 'inputs': inputs, 'origin': 'training', 'project_path': str(ROOT), 'check': True})
        dump(OUT / f'{variant}_run.json', {'code': code, 'inputs': inputs, 'origin': 'training', 'project_path': str(ROOT)})
    dump(OUT / 'ai_base_request.json', {'message': request + f'\n입력: {OUT}/source/base\n저장: {OUT}/agent/base/result.json 및 report.md', 'origin': 'training', 'background': True})
    dump(OUT / 'ai_variant_request.json', {'message': (DOC / 'variant_request.txt').read_text() + f'\n입력: {OUT}/source/missing\n저장: {OUT}/agent/missing/result.json 및 report.md', 'origin': 'training', 'background': True})


if __name__ == '__main__':
    main()
