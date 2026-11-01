# 107회차 재현·증거 읽기

정본 루트는 `/Users/kangkukjin/Desktop/AI/indiebizOS`다. 이 회차는 실제 의식의 문제규정·계획 작성 경로를 분리 호출했다. 실행자·평가자나 HTTP 채팅 전체를 실행한 시험이 아니다.

## 모델 없이 확인

```bash
cd /Users/kangkukjin/Desktop/AI/indiebizOS
.venv/bin/python3 docs/experiments/long_sentence_imagination/round_107/verify_evidence.py
```

현재 제품 소스의 시작 지문과 로컬 DB의 training 표식까지 확인할 때는 `--live`를 붙인다. 이후 제품 소스가 바뀌었으면 이 추가 검사는 실패할 수 있으며 과거 증거 자체의 실패와 구별한다.

Git 안의 증거는 `results/`, `invalid_attempts/`, `evidence.json`, `review.json`이다. 원래 호출 입력·시스템 프롬프트·감독 로그와 실제 저장 계획은 `outputs/long_sentence_imagination/2026-11-01_107회차/`에 있다. 검사기는 보존된 Git 증거를 확인하고, 로컬 원본이 있으면 그 입력·저장 계획·오류 시도도 대조한다. 로컬 원본이 없으면 없는 부분은 명시적으로 미검사로 남긴다.

`counterexample.py`는 C01의 집계/시점 반례를 계산한다. `counterexample.json`은 계산 결과, `handoff_probe.json`은 실제 `compile_user_command`의 전달 관측이다. 후자는 실행자 모델을 호출하지 않았다. 수동 의미 판정과 기계적 파일·계보 검증을 혼동하지 않는다.

## 이번 실행 방식

`run_cases_v0.py`로 C01을 실행한 뒤 C02~C10을 배치 실행했다. 후속 작업공간의 오류를 발견해 `run_cases.py`로 고쳤다. `LS107_ATTEMPT_SUFFIX=_recheck`를 지정한 C09·C10이 최종 후속 시험이다. 둘 모두 원래 C05에서 독립적으로 분기하며 서로의 결과를 받지 않는다.

`cases.json`의 `request`와 명시된 이전 모델 출력만 전달했다. `checks`와 운영자 보고서는 전달하지 않는다. 각 사례는 별도 신원과 `origin=training`, 별도 감독 디렉터리를 사용한다. `Supervisor.plan` 관측 래퍼는 입력/출력만 저장하며 실제 호출을 대체하지 않는다. 실행자 도구 콜백은 예외를 내도록 분리했고 관측 도구 호출은 0건이었다. 감독 계약/증거 기능을 포함한 모든 로그는 로컬 outputs에 보존했다.

연구 요청은 보통 `plan`과 가이드가 들어가는 `plan_completion` 두 호출을 거친다. 단순 설명과 핵심 맥락 부재는 첫 규정에서 `deep_research=false`가 되어 1회로 끝났다. 후속은 `previous_research_plan`을 명시적으로 제공했다. 실제 채팅의 자동 연구 주제 식별·기억 회수까지 재현한 것은 아니다.

## 모델을 다시 호출할 때

이 회차의 `start.json`은 고정된 과거 상한이다. 기존 실행기를 그대로 재실행하면 기존 폴더 또는 상한 검사에서 중단하도록 되어 있다. `prepare.py`는 최초 준비 기록이므로 다시 실행하지 않는다. 원장과 고정 입력을 덮어쓸 수 있다.

새 훈련을 요청받으면 새 원장 번호·시작/상한·출력 경로를 만들고 이 회차의 입력·실행기를 복사해 사용한다. 모델 해석은 확률적이고 소스·설정도 달라질 수 있으므로 새 소스 지문·모델 판본·호출 비용을 기록한다. 이번 결과와 다른 출력이 나오더라도 원본을 덮어쓰지 않는다. 다음 전이 시험에는 아직 사용하지 않은 요청도 포함한다.

현재 `capture_evidence.py`는 로컬 outputs와 읽기 전용 에피소드 DB에서 보존물을 복사한다. 이미 완료된 회차의 증거를 재포장할 이유가 있을 때만 실행하고 원본 변동 여부를 먼저 확인한다. 의미 판정은 `review.json`의 인용과 실제 문맥을 읽어 검토한다.
