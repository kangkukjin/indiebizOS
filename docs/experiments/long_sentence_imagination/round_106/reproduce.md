# 106회차 증거와 재현

이 폴더는 완료된 훈련 기록이다. `ai/`의 보고서·프로그램은 시스템 AI가 쓴 원본이며 운영자 검토는 `report.md`가 정본이다. 코드 원본에 발견 사항을 소급 수정하지 않았다. `ai/variant/compare_base_variant.json`만 1500줄 규칙을 위해 JSON 공백을 줄였다. 그 원본 바이트 SHA는 evidence.json에 있다. 외부 논문·웹 본문과 전체 대화 원본은 git에 복제하지 않았다.

## 저장 증거 확인

정본 저장소 루트에서:

```bash
python3 docs/experiments/long_sentence_imagination/round_106/verify_evidence.py
```

이 검사는 동결한 파일 SHA·행수·실험 설정·Q01 반례·판본 변경·선택 재사용의 일관성 검사다. 의미 판정의 독립 검증은 아니다. `capture_evidence.py`는 원래 로컬 outputs와 영수증 DB가 남아 있을 때만 보고용 사본을 다시 추출한다. 완료된 증거를 감사할 때 실행할 필요는 없다.

## 입력 재구성

```bash
python3 docs/experiments/long_sentence_imagination/round_106/restore_inputs.py --output /tmp/ls106-repro-inputs
```

새 폴더만 허용한다. 시작 커밋 `9d7900f4a29bfa60b00c043a0130dce0a01c4910`에서 실제 문서 8개를 가져오고, 저장한 합성 문서 4개를 붙인다. 기본·변형 24개 사본 모두 manifest SHA를 검사한다. `gold.json`은 운영자 판정 자료이며 AI에 노출한 자료가 아니다. 보류 질문은 방법 고정 후 사용했다.

## AI가 작성한 검색 프로그램 재실행

```bash
.venv/bin/python3 -I docs/experiments/long_sentence_imagination/round_106/ai/base/run_experiment.py --input /tmp/ls106-repro-inputs/base --queries /tmp/ls106-repro-inputs/heldout.json --output /tmp/ls106-heldout-result.json
```

정상 전체 실험 조건은 48행·skipped 빈 목록·config_unchanged=true이다. 프로세스 exit 0만으로 판단하지 않는다. 원래 기본 셸의 python3는 3.12.4였고 의존성 import 실패로 24행만 생성했다. 같은 머신의 저장소 `.venv` 3.13.5에서는 48행이 생성됐다. 두 결과 모두 `heldout/`에 보존했다.

라이브러리와 로컬 모델 캐시는 `runtime_observed.json`을 참고한다. 실행 당시 모델 revision 영수증이 없으므로 향후 캐시·환경 변경 뒤 수치까지 자동 동일하다고 보장하지 않는다. 프로그램은 오프라인 캐시 사용을 설정하며 모델 다운로드를 요구하지 않는다. 모델이 없으면 실패 내용을 skipped에 기록한다.

보조 분석은 별도 절차다:

```bash
.venv/bin/python3 -I docs/experiments/long_sentence_imagination/round_106/ai/base/analyze_passages.py --input /tmp/ls106-repro-inputs/base --queries /tmp/ls106-repro-inputs/base/queries.json --anchors docs/experiments/long_sentence_imagination/round_106/ai/base/anchors.json --output /tmp/ls106-passage-ranks.json
```

이 결과의 문단 RRF 순위를 주 프로그램이 반환한 대표 문단 순위로 취급하지 않는다. `evidence.json` L106_1이 서로 다른 두 출력을 함께 보존한다.

## IBL 전체 조합

`requests/`에 실제 `/ibl/execute` 요청 19개를 보존했다. `*_check`는 검사, 나머지는 실행이다. `sources_v0.ibl`·`retrieve_v0.ibl`·`answer_v0.ibl`·`followup_v3.ibl`이 원문 확보→검색→판단→근거 보완·재사용을 구성한다. v0·v2의 실패판도 남겼다. 운송만 `transport.py`가 담당했다.

요청의 절대 입력·출력 경로는 원실행 위치다. 새 실행은 기존 결과를 덮어쓰지 않도록 새 자료 폴더를 만들고 요청의 해당 경로를 바꿔야 한다. 읽기 결과·이전 보완 결과도 새 작업에 맞춰 넘긴다. origin=training을 유지하고 새 ticket으로 제출한다. 모델 호출은 유료이며 외부 원문 재획득은 당시 결과와 달라질 수 있다. 이번 기록을 검토하기 위해 재호출할 필요는 없다.

## 판정과 보존 한계

`trainer/*answers.jsonl`·`*followup.jsonl`은 중복 원문 필드를 제외한 판단 사본이다. 전체 문맥·원문·요청/응답은 정본의 `outputs/long_sentence_imagination/2026-11-01_106회차/`에 남아 있다. 이 폴더는 git 밖이므로 장기 보존은 이 문서 폴더의 재구성 입력·프로그램·검증 결과를 기준으로 한다. 시스템 AI가 삭제한 잘못된 입력 폴더 실행의 중간 JSON은 복구했다고 주장하지 않는다. 오류 영수증은 evidence.json에 있다.
