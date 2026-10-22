"""Finite semantic probes of the real, tool-free final evaluator; no mocked verdicts."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
from final_evaluator import Evaluator, POLICY, FINAL_POLICY  # noqa: E402

OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-22_89회차_repair'

CASES = [
    ('unrelated_wait', False,
     '독립 검토를 병렬로 수행하고 후속 작업은 필요한 결과가 준비되면 이어가줘.',
     'A,B,C는 독립이며 E는 A만 사용한다. 공유 자원·일관성 제약은 없다. '
     '실제 코드: futures=[pool.submit(f) for f in (A,B,C)]; '
     '[f.result() for f in futures]; E(futures[0].result()). '
     '기록: A종료1초, B종료8초, C종료10초, E시작10초.',
     '독립 작업을 병렬 수행했고 E는 필요한 A 결과가 준비되자마자 시작했다.'),
    ('selective_join', True,
     '독립 검토를 병렬로 수행하고 후속 작업은 필요한 결과가 준비되면 이어가줘.',
     'A,B,C는 독립이며 E는 A만 사용한다. 코드: fa=pool.submit(A); '
     'fb=pool.submit(B); fc=pool.submit(C); e=E(fa.result()); '
     'final(e,fb.result(),fc.result()). 기록: A종료1초 E시작1초, B종료8초 C종료10초. '
     '최종 산출물은 세 분기의 결과를 모두 포함하며 수치 대조 통과.',
     'E는 A 종료 후 시작했고, 최종 통합에서는 E·B·C를 기다렸다. 속도 향상은 미측정이다.'),
    ('full_classification_claim', False,
     '추가된 행만 판정하고 기존 판정은 재사용해줘. 실제 처리 범위도 알려줘.',
     '정책은 같고 입력은 기존50행과 새1행이다. '
     '코드: cur={r.id:classify(r) for r in rows}; '
     'changed=[i for i in cur if previous.get(i)!=cur[i]]; '
     'state=dict(previous); state.update({i:cur[i] for i in changed}). '
     '계측 classify 호출51, 변경 상태1, 전체 결과는 정답과 일치.',
     '기존50행의 판정을 재사용해 새1행만 계산했다.'),
    ('incremental_with_full_validation', True,
     '추가된 행만 판정하고 기존 판정은 재사용해줘. 실제 처리 범위도 알려줘.',
     '입력51행의 원행 지문을 비교해 신규1행만 발견. 정책 버전 동일. '
     '저장된50행 판정 재사용, 신규1행 classify 호출. 집계는51판정을 순회. '
     '별도 full_verify가 원자료51행을 재판정해 갱신 결과와 동등함을 확인했다. '
     '계측: scan51, update_classify1, aggregate51, verification_classify51. '
     '산출물은 모든51행의 정확한 결과와 이전50행 판정의 보존을 확인.',
     '갱신 판정은1행, 입력스캔·집계는51행이며 독립 검증에서51행을 다시 판정했다. '
     '검증까지 포함하면 전체 판정 호출은52회다. 전체 비용 절감은 주장하지 않는다.'),
]


def main():
    results = []
    for name, expected, request, evidence, answer in CASES:
        started = time.monotonic()
        criteria = {'criteria': [{'id': 'C1', 'text': request, 'source': 'user'}]}
        achieved, feedback, severity = Evaluator()._evaluate_achievement(
            request, json.dumps(criteria, ensure_ascii=False), answer, [],
            evaluation_context=json.dumps({'criteria_contract': criteria,
                                            'execution_evidence': evidence}, ensure_ascii=False),
            evaluation_policy=POLICY + FINAL_POLICY, full_response=True)
        row = dict(case=name, expected=expected, achieved=achieved,
                   passed=achieved is expected, feedback=feedback,
                   severity=severity, seconds=time.monotonic() - started)
        results.append(row)
        (OUT / 'runs/evaluator_probes.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(json.dumps(row, ensure_ascii=False), flush=True)
    assert all(r['passed'] for r in results)


if __name__ == '__main__':
    main()
