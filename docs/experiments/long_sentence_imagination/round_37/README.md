# 37회차 재현 안내

정본 저장소에서 실행한 연구·보고 훈련이다. 제품 수리 코드는 없다.
[보고서](report.md), [사전 조건](task.md), [자연어 요청](request_base.txt), [변형](request_variant.txt).
`artifacts/`는 최초 완료 산출물 사본이다. **발견한 오류를 보존한 평가 증거이며, 검수 완료된 업무 지침이 아니다.**

## 프로그램과 입력

`replay_manifest.json`은 실제 성공한 프로그램 경로와 요청의 inputs/origin/project_id/budget을 보존한다.
순서는 search → collect → extract_v3 → report_v1 → variant이다. 탐색 후 원문 선택과 추출 범위 선택은 훈련자가 했다.
원문 수집 결과는 trainer/base/source_index.json과 sources/에, 추출 입력은 extraction_inputs/에,
연구별 결과는 extracted/ 및 evidence.json에 보존됐다. 웹 원문은 변할 수 있어 재실행이 동일 판본을 보장하지 않는다.

`harness/transport.py`는 JSON 요청 전달·응답 기록만 한다. 핵심 조사·추출·종합·저장·재독은 IBL이다.
실행할 항목의 manifest.payload에 해당 program 파일의 본문을 code로 넣어 JSON 파일로 저장한 뒤:

```sh
python3 docs/experiments/long_sentence_imagination/round_37/harness/transport.py LABEL --payload PAYLOAD.json
```

- `check:true`를 추가하면 검사만 한다. 최초 실패 초안도 `drafts/`에 보존했다.
- 반복 실행 전 출력 경로를 새 시험 폴더로 바꾼다. 첫 실행 증거를 덮어쓰지 않는다.
- 모델 호출·웹 요청이 실제 발생한다. 자동 실행/예약/등록은 하지 않았다.
- AI 독립 실행의 실제 요청들은 `evidence/ai_calls.json`, 상태와 오류는 `ai_results.json`에 있다.
  자연어 요청을 다시 보내는 것은 별도 실행이다. 기존 작업 회수는 아래 task_id를 사용한다.
- `collect.py`와 `preserve.py`는 읽기 전용 DB 계측과 기존 증거 보존용이다. 현재 머신의 원자료가 있어야 한다.

## 최소 재현

`repro/inspect_oversize.ibl`에 `inputs:{text:"x"를 60010회 반복한 문자열}`을 주면
모델 호출 없이 input_size 오류가 나지만 inspection/limit_chars/초과량은 응답에서 소실된다.
실제 결과는 `evidence/repro_results.json`에 있다.

`repro/scope_counterexample.ibl`은 외부 호출 없는 합성 산술이다.
유지보수 시간 900·다른 업무 100, 유지보수만 20% 절감 → 회사 전체 절감은 18%다.
이는 두 변형 메모의 '일부 집단 실험 → 회사 계획 20%' 추론이 충분하지 않다는 반례다.

## 종료 작업

- 기본: `task_sysai_e98dcb65`, ep4441, succeeded.
- 변형: `task_sysai_7524061e`, ep4442, succeeded.
- trainer의 search/collect/extract_v3/report_v1/variant: completed.
- 실패한 검사/inspect/report_v0: 기록 보존, 뒤에서 실행 중인 모델 작업 없음.
- 진행 중 작업, 적용 예약, 외부 발송·공개 없음.
