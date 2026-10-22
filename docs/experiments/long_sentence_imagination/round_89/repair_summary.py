"""Publish compact replay evidence without raw model prompts or credentials."""
import json
from pathlib import Path

import repair

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((repair.OUT / name).read_text())


def main():
    audit = read('runs/audit_summary.json')
    verification = read('runs/repair_verification.json')
    totals = {k: sum(u.get(k, 0) for turn in audit['turns'] for u in turn['usage'].values())
              for k in ('input', 'output', 'cache_read', 'cache_create')}
    result = {
        'start': read('start.json'), 'end': read('end.json'),
        'audit': audit,
        'totals': {**totals, 'seconds': sum(e['total_ms'] for t in audit['turns'] for e in t['episodes']) / 1000,
                   'execution_tools': sum(t['tool_count'] for t in audit['turns']),
                   'planning_tools': sum(t['planning_tool_count'] for t in audit['turns'])},
        'oracle': {'passed': verification['passed'], 'failed': verification['failed'],
                   'passed_names': [c['name'] for c in verification['checks'] if c['pass']],
                   'failures': [c for c in verification['checks'] if not c['pass']]},
        'behavior': read('runs/behavior_probes.json'),
        'evaluator': read('runs/evaluator_probes.json'),
        'assessment': {
            'L89-4': '보존 프로그램의 지연 이벤트 시험에서 무관한 예산 분기 대기 해소 확인.',
            'L89-5': '1행만 계산했다는 과장 제거. 검토 단위 재사용과 전량 자료 재판정을 정직하게 보고. 행 단위 증분 계산은 미구현.',
            'L89-6': '프로그램 복사·부분 수정으로 재사용했으나 설명 보완의 전체 재실행과 비용 증가는 잔존.',
            'scope': 'T2 실행도구15의 os.makedirs(/tmp/x) 성공, T4 도구2의 /tmp/x 출력 시도는 디렉터리라 실패. 지정 출력 범위 위반이며 합격 처리하지 않음.',
        },
        'limits': ['캐시 읽기/생성은 input과 중복 합산하지 않는다.',
                   '별도 검수 반례4회와 외부 훈련자 작성 비용은 네 턴 합계에 포함되지 않는다.',
                   '지연 주입은 의존 관계를 검사하며 실제 성능 향상 측정이 아니다.',
                   '정규 회귀는 선택230파일 3648통과·1건너뜀; backend 전체 전수는 미실행.'],
    }
    (HERE / 'repair_evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result['totals'], ensure_ascii=False))
    print(json.dumps({k: verification[k] for k in ('passed', 'failed')}))


if __name__ == '__main__':
    main()
