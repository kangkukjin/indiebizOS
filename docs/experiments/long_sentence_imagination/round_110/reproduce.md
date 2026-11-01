# 110회차 재검증

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS`에서 실행한다. 아래 명령은 모델을 호출하지 않는다.

```bash
.venv/bin/python3 -m pytest docs/experiments/long_sentence_imagination/round_110/test_gate_contract.py
.venv/bin/python3 docs/experiments/long_sentence_imagination/round_110/verify_evidence.py
.venv/bin/python3 docs/experiments/long_sentence_imagination/round_110/compare_results.py
```

첫 명령은 격리 후보의 계약22개를 검사한다. 둘째는 보존된 지문·응답·판본·정확한 인용·비용 합산을 검사한다. 셋째는 수동 품질 판정에 사전 기준을 적용하여 `comparison.json`을 다시 쓴다. 의미 판단을 독립 자동 채점하는 명령은 아니다.

로컬 `outputs/long_sentence_imagination/2026-11-01_110회차/`와 당시 DB가 남아 있으면 `verify_evidence.py --live`로 실제 입력·시스템 프롬프트 지문, 에피소드의 training 출처, 운영 세 파일의 당시 SHA 동일성을 추가 확인한다. 이후 운영 소스가 정당하게 바뀌면 이 마지막 조건은 실패할 수 있다. 과거 실험의 품질 퇴행으로 해석하지 않는다. 로컬 입력이 없을 때는 입력 원문 지문을 새로 계산할 수 없고 저장 기록만 남는다.

원 실행은 기준 HEAD `0aca5502f683859adf81d43aacf081ed4df16d47`, 현재 의식 설정 `claude_code/opus` 고급이었다. `run_experiment.py K1 N1`과 `run_experiment.py K2 N2`를 두 프로세스에서 실행했다. 각 사례 안에서는 S→A→R 순차이며 R은 정확한 A에서 시작한다. 점검 네 호출 중 하나가 수정과 재점검으로 이어져 총14호출이다. 실험 코드 오류나 회복 재호출은 없었다.

러너는 고정 파일과 당시 운영 소스를 검사하고 기존 출력 디렉터리를 덮어쓰지 않는다. 시한180초 전부터 새 호출을 거절한다. 과거 러너를 그대로 다시 실행하는 것은 새 실험 절차가 아니다. 새 호출을 하려면 새 회차 경로·예산·후보·과제를 먼저 고정해야 한다.

`capture_results.py`는 로컬 응답과 읽기 전용 DB 이벤트를 `results/` 및 `evidence.json`에 복사하는 수집 도구다. 보존 산출물을 불필요하게 다시 생성하지 않는다. `costs.json`은 evidence의 경로별 합과 호출별 phase를 집계한 요약이다. 원장 모델 사용량에서 cache/reasoning은 부분집합이므로 중복해서 더하지 않는다.

보존 파일:

- `start.json`, `task.md`, `cases.json`: 호출 전 지문·설계·기준·요청.
- `five_principle_gate.py`, `audit_system.txt`, `repair_instruction.txt`: 후보 구현·지시.
- `baseline_research_planning.py`, `consciousness_prompt.md`, `deep_research.md`: 당시 기준 소스.
- `results/`: 12단계 영수증·공개 결과·원 응답·선별 이벤트, R의 초안·수정안·판정과 판본 해시.
- `review.json`: 8개 계획의 비맹검 수동 판정과5번 점검 감사.
- `evidence.json`, `costs.json`, `comparison.json`: 계측·비교와 기각.
- `validation/`, `completion.json`: 검증 결과·완료 시각·범위.

미통과 차단은 단위 시험에서 확인했다. 이번 실제 모델은 모두 통과를 반환했으며 두 사례의 중요한 미탐지는 수동 감사에서 발견됐다. 이 차이를 숨기지 않는다.
