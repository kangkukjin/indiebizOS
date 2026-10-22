"""Prepare immutable synthetic fixtures and requests; no production task computation."""
import datetime
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BASE = ROOT / 'outputs/long_sentence_imagination/2026-10-22_88회차'
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-22_89회차'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    assert not (OUT / 'start.json').exists(), 'Never overwrite an existing round'
    for folder in ['inputs', 'trainer', 'ai', 'runs', 'reference', 'staged', 'snapshots']:
        (OUT / folder).mkdir(parents=True, exist_ok=True)
    if (BASE / 'reference/initial_inputs/records.json').exists():
        for name in ['project.json', 'tasks.json', 'records.json', 'options.json']:
            shutil.copyfile(BASE / 'reference/initial_inputs' / name, OUT / 'inputs' / name)
        shutil.copyfile(BASE / 'staged/receipts.json', OUT / 'inputs/receipts.json')
    else:
        seed = json.loads((HERE / 'seed.json').read_text())
        for name in ['project.json', 'tasks.json', 'options.json', 'receipts.json']:
            ending = '\n' if seed['final_newlines'][name] else ''
            (OUT / 'inputs' / name).write_text(json.dumps(seed[name], ensure_ascii=False, indent=2) + ending)
        rule = seed['records_rule']
        rows = [dict(id=f'D{i:04d}', collection=f'C{1+(i-1)//rule["collection_size"]}',
            consent='missing' if i % rule['consent_missing_every'] == 0 else 'yes',
            checksum='fail' if i % rule['checksum_fail_every'] == 0 else 'pass',
            searchable=i % rule['search_fail_every'] != 0, accessible=i % rule['access_fail_every'] != 0)
            for i in range(1, rule['count'] + 1)]
        save(OUT / 'inputs/records.json', {'version': 1, 'items': rows})
    records = json.loads((OUT / 'inputs/records.json').read_text())
    partial = {'version': 2, 'items': records['items'][:-1]}
    restored = {**records, 'version': 3}
    save(OUT / 'staged/records_partial.json', partial)
    save(OUT / 'staged/records_restored.json', restored)
    (OUT / 'inputs/README.txt').write_text(
        '88회차 합성 입력의 초기 판본 사본과 담당자 검증 영수증입니다. 자료는 D0001~D1800 전량, '
        '작업 72개입니다. reported_done과 verified가 모두 참일 때만 완료입니다. '
        '자료의 네 조건은 모두 필수이며 누락 항목은 미확인입니다. '
        'tasks.cost가 전체 작업비의 정본으로 options.cost는 중복 합산하지 않습니다. '
        '작업 hours는 선행관계에 따른 순수 작업시간이며 달력·인력 가용시간은 주어지지 않았습니다. '
        '기한 준수를 확정하지 말고 필요한 추가 정보를 명시하세요. '
        '최종 검토 완료와 실제 프로젝트 개통 완료는 다릅니다.\n')
    scope = (f'\n입력은 {OUT / "inputs"}, 출력은 {OUT / "ai"}입니다. '
        '출력은 턴별 T1~T4 하위 폴더에 보존하세요. 입력은 읽기만 하고 산출물·보조 프로그램은 지정 출력 안에만 쓰세요. '
        '본인의 이전 결과·중간 참조는 재사용해도 됩니다. 다른 실행자의 trainer·reference·staged·snapshots·runs 및 회차 docs는 읽지 마세요. '
        '다른 프로젝트 기억을 근거로 쓰지 마세요. 실제 발송·배포·구매·예약·운영 환경 변경은 하지 마세요. '
        '판정의 상세 내역과 근거를 기계가 읽을 수 있는 JSON, 사람이 읽을 수 있는 한국어 검토서로 남겨주세요.')
    task = ('지역자료실 이전과 검색 서비스 개통을 준비하고 있어. 제공한 자료 검증 결과, 작업 목록과 선행관계, 예산과 운영 조건을 검토해서 '
        '개통 준비 상태를 판단해줘. 서로 독립적인 검토는 나눠 동시에 진행하고, 다른 검토의 결과가 필요한 일은 그 결과를 받은 뒤 이어가줘. '
        '자료의 사용 가능 여부, 예산 충족 여부, 작업 순서와 병목, 운영 조건의 충족 여부를 근거와 함께 정리하고, '
        '이 결과를 합쳐 우선 조치 목록과 최종 인수 검토서를 만들어줘. 일부 자료를 읽지 못하거나 담당 작업이 실패하면 확인된 결과는 '
        '보존하면서 무엇이 막혔는지 밝혀줘. 이후 조건이 바뀌면 영향을 받는 부분을 다시 검토하되, 변하지 않은 결과는 이어서 사용해줘. '
        '실제로 병렬 처리한 작업과 합류 시점을 확인할 수 있게 작업별 입력 판본·시작·종료·산출물 근거도 남겨줘. '
        '이번 결과는 T1에 저장해줘.')
    turns = [task + scope,
        '예산을 320만원으로 줄이고 선택기능 W6 전체, 외부 SaaS와 얼굴 자동 분류는 이번 범위에서 제외할게. '
        '개인정보·접근성·전량 검증과 11월20일 기한은 그대로야. 달라진 비용·일정·조치안을 갱신하되 '
        '필수 작업을 임의로 취소하거나 검증 기준을 낮추지 마. 원자료는 바뀌지 않았으니 이전 자료 검증 결과를 재사용해줘. T2에 저장해줘.' + scope,
        'records.json이 새 판본으로 교체됐어. 최신 검증 자료 범위가 불완전하면 실패와 미확인을 구별하고 '
        '확인된 결과와 다른 검토 결과는 보존해줘. 정책은 T2 그대로야. 무엇을 다시 처리했는지도 남기고 T3에 저장해줘.' + scope,
        'records.json의 누락 자료가 복구됐어. 바뀐 부분과 그에 의존하는 결과만 갱신하고, 현재 조건에 따른 최종 인수 검토서를 T4에 저장해줘. '
        '이전 판본과 산출물은 보존하고 검토 작업 완료와 개통 가능 여부를 구별해줘.' + scope]
    save(OUT / 'reference/requests.json', {'turns': turns})
    save(OUT / 'start.json', {'start': '2026-10-22T13:22:00+09:00', 'deadline': '2026-10-22T14:22:00+09:00',
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'synthetic': True})
    shutil.copytree(OUT / 'inputs', OUT / 'reference/initial_inputs')
    save(OUT / 'reference/initial_hashes.json', {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (OUT / 'inputs').iterdir()})
    (HERE / 'request.txt').write_text(task + '\n\n입출력 위치와 접근 범위는 task.md 및 reference/requests.json에 보존한다.\n')
    print(OUT)


if __name__ == '__main__':
    main()
