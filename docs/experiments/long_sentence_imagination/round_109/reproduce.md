# 109회차 재검증

정본 저장소 `/Users/kangkukjin/Desktop/AI/indiebizOS`에서 실행한다.

## 저장 증거와 비용 판정 재검증 — 모델 호출 없음

```bash
.venv/bin/python3 docs/experiments/long_sentence_imagination/round_109/check_counterexamples.py
.venv/bin/python3 docs/experiments/long_sentence_imagination/round_109/verify_evidence.py
.venv/bin/python3 docs/experiments/long_sentence_imagination/round_109/compare_results.py
```

첫 명령은 가상 반례의 산술을 검사하고 `counterexamples.json`을 다시 쓴다. 둘째는 저장된 증거를 검사한다. 셋째는 수동 의미 판정에 사전 채택 기준을 적용해 `comparison.json`을 다시 쓴다. 의미 판정을 자동으로 재현하거나 독립 채점하지는 않는다.

로컬 원자료와 당시 DB가 남아 있고 운영 소스가 당시 판본과 같으면 `verify_evidence.py --live`로 실제 입력·시스템 프롬프트 지문, A/B 차이, 에피소드 출처, 운영 소스 불변도 검사할 수 있다. 운영 파일이 이후 정당하게 바뀌면 live 검사의 당시 소스 동일성 조건은 실패한다. 이를 제품 회귀라고 해석하지 않는다.

## 후보 계약 검사 재현 — 모델 호출 없음

```bash
.venv/bin/python3 - <<'PY'
import importlib.util
import sys
from pathlib import Path
root = Path.cwd()
sys.path.insert(0, str(root / 'backend'))
import boot_paths
p = root / 'docs/experiments/long_sentence_imagination/round_109/candidate_research_planning.py'
spec = importlib.util.spec_from_file_location('research_planning', p)
module = importlib.util.module_from_spec(spec)
sys.modules['research_planning'] = module
spec.loader.exec_module(module)
import pytest
raise SystemExit(pytest.main(['backend/test_research_planning.py']))
PY
```

당시 결과는 41통과였다. 운영 파일에 후보를 덮어쓰지 않는다. 미래의 backend 계약 변경에 따라 검사 수나 호환성이 달라질 수 있다.

## 원 실행 구성

- 기준 HEAD: `fbc91fe4f20a55b064afaa441073c54781319d8f`.
- 실제 모델: consciousness의 현재 설정을 resolve한 `claude_code/opus`, 고급.
- 원 실행: `run_experiment_v0.py` 판본의 러너를 D1/H1/H3와 D2/H2/H4 두 묶음으로 시작했다. D1/D2 검토 응답 파싱에서 멈췄다.
- 수정 러너 `run_experiment.py`로 `--recover D1 D2`, `H1 H3`, `H2 H4`를 실행했다. 회복은 저장 검토 응답을 읽고 정정만 호출했다.
- 러너는 기존 출력 디렉터리가 있으면 덮어쓰지 않고 실패한다. 시한에 180초 미만 남으면 새 호출을 거절한다. 따라서 과거 러너를 지금 그대로 실행하는 것은 새 실험 절차가 아니다.
- 새 실제 모델 비교는 새 회차 경로·예산·메타데이터를 먼저 만들고 고정해야 한다. 과거 결과를 덮어쓰거나, 모델 출력을 본 뒤 후보·기준을 고쳐 같은 실험이라고 부르지 않는다.

## 증거 위치

- `results/*`: 규정·계획·검토·원 모델 응답·실패 영수증·선별 이벤트.
- `evidence.json`: 지문, 출처, 호출 사용량, 실제 사용량과 비교 경로 사용량.
- `review.json`: 수동 18개 결과 판정과 10개 검토 지적 감사, 판정 수정 이력.
- `comparison.json`: 고정 기준에 따른 채택/기각.
- `start.json`: 원문·기준·후보·운영 소스 지문과 보수적 시간 예산.
- `harness_recovery.json`: 실험 코드 실패와 응답 재사용 기록.
- 로컬 전체 입력·슈퍼비전 로그: `outputs/long_sentence_imagination/2026-11-01_109회차/`.

동적 전체 입력 원문은 로컬에 두고 git에는 지문과 결과를 보존했다. 로컬 원자료가 없으면 과거 전체 입력의 바이트 비교를 새로 수행할 수 없으며, 그때는 저장 증거 검증과 당시 확인 기록만 사용할 수 있다.
