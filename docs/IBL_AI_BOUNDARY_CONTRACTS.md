# AI 호출 경계의 입력 점검과 응답 계약

2026-09-23. [진화 목적](IBL_EVOLUTION_PURPOSE.md)에 따라 긴 일회성 문장과 관용구가 같은
검사를 이용한다. 새 어휘·문법 없이 `[table:ai]`에 선택 인자 `contract`, `inspect`를 추가했다.
기존 선언 없는 호출의 선별·행 추가 동작은 유지한다. AI 팁 관용구 본문·등록·업무 정책은 바꾸지 않았다.

## 검사 시점과 소유 위치

| 시점 | 검사 | 실행/비용 |
| --- | --- | --- |
| 코드만 있는 때 | 기존 타입/반복 분석 + 리터럴 contract 선언·입출력 투영 충돌 | 도구·모델 실행 없음 |
| 실제 입력이 준비된 때 | `inspect:batch/each`로 투영 후 요청 크기·요청 수·같은 중첩 배열의 반복량 | 로컬 직렬화·해시, 모델 호출 없음 |
| 모델 호출 직전 | 선언과 실제 입력 배열·문자열 ID의 존재·중복 검사 | contract를 쓴 호출만 |
| 각 모델 응답 직후 | 원본 입력 ID 전수 포함·중복/추가 없음·필수 필드·허용값·바깥 행 대응 | 결정론 검사, 추가 모델 호출·자동 수리 없음 |

선언과 관계 검증은 `backend/common/item_contract.py` 한 벌이다. 정적 검사기는 사전의
`row_contract_param`을 읽고 같은 선언 검증기를 부른다. 동적 선언은 실행 때 검사한다.
`ai_inspect_param`으로 점검 모드를 식별하며, 점검은 AI 방문 횟수에서 제외하고 원본 입력을 반환한다.
내용어 이름이나 보고서 정책을 파서·검사기에 넣지 않는다.
실제 입력 직렬화와 점검은 `common/ai_input_inspection.py`, 호출 경계 연결은 ai-ops handler가 맡는다.

## 사용 예: 번역 요청의 전수 응답

```text
$요청 = [{input:{lines:[{id:"a",text:"첫 문장"},{id:"b",text:"둘째 문장"}]}}]
$계약 = {covers:[{input:"input.lines",output:"result.lines",key:"id",
                  required:["text"],allowed:{status:["done"]}}]}
$점검 = $요청 >> [table:ai]{instruction:"모든 문장을 번역",input_fields:["input"],
                          contract:$계약,inspect:"each"}
```

여기까지 모델 호출은 없다. `$점검.inspection`을 보고 필요한 입력·분할을 결정한다.
실행할 때 동일한 input_fields·contract로 inspect를 뺀다. each 점검은 **한 행당 한 요청을 가정**하며,
실제 분할을 대신 수행하지 않는다. 요청 수와 반복 한도가 맞아야 한다.

```text
$요청 >> [table:each]{limit:$요청.count,parallel:4,collect:true,on_error:"stop"} {
  [table:ai]{items:[$it],instruction:"모든 문장을 번역",input_fields:["input"],contract:$계약}
}
```

`covers`는 1~16개 규칙, 선언 전체는 16,000자 이하다. input/output은 **각 바깥 행 기준 배열 경로**,
key는 그 배열 원소의 ID 경로다. `output_key`로 출력 ID 경로만 달리할 수 있다.
점 경로(숫자 인덱스 포함)를 쓰며 wildcard/대괄호 경로는 이 계약에서 지원하지 않는다.
ID는 비어 있지 않은 문자열이며 공통 `group_identity`의 엄격한 정체성을 쓴다(대소문자 보존,
Unicode NFC·날짜 의미는 공통 규약). `required`는 존재하고 null이 아닌 필드이며 빈 문자열이나
내용의 타당성까지 검사하지 않는다. `allowed`는 공통 조건 동등성으로 비교하는 JSON 스칼라 선택지다.
둘 다 최대 32개 경로, 각 허용값 목록도 1~32개다. 알 수 없는 선언 키는 오타로 거절한다.

contract는 바깥 행 보존을 자동 적용한다. 명시한 preserve_rows:false와 충돌한다.
출력 경로가 input_fields로 숨긴 기존 열에 있으면 새 응답 의무와 원본 보존이 충돌하므로 호출 전에 거절한다.
응답의 `_i`로 바깥 행 순서를 복원한 뒤 **병합 전의 새 응답**을 **호출 전 원본 입력**과 대조한다.
모델이 입력 ID를 바꾸거나 기존 result를 남겨 누락을 숨길 수 없다. 새 응답에 출력 경로가 있어야 한다.
오류는 `success:false,error_type:contract,phase:declaration|input|output`이며 위치와 누락·추가·중복
건수를 담는다(ID 예시는 최대 20개). 실패 응답에 성공 모양의 부분 items를 내지 않는다.
기존 each의 on_error:stop으로 후속 요청/소비를 막는다. 병렬 호출은 이미 시작한 요청까지 취소한다는
보장이 없으며, skip/continue/try 등 명시한 오류 처리 정책은 그대로 적용된다.

## 실제 입력 점검이 뜻하는 것

- `batch`: 투영한 전체 행을 한 요청으로 직렬화. `each`: 매 행을 `_i:0`인 단독 요청으로 직렬화.
- `inspection`: planned_requests, total_payload_chars/bytes, max_payload_chars,
  oversized_count/requests, repeated_fields/groups, repetition_scan. model_calls는 0.
- 직렬화는 실제 모델 입력과 같은 함수다. 60,000자 상한을 넘는 요청이 있으면 input_size 실패와 점검을
  함께 반환한다. oversized_requests는 최대 32개 예시, oversized_count는 전체다. 0행은 요청 0개.
- 반복 검사는 객체를 깊이 6·20,000개 값까지 걷고 배열에서 멈춘다. 같은 경로의 같은 비어 있지 않은
  배열(JSON 객체 키 순서는 무시)을 찾는다. 모든 중복을 찾는 범용 압축 분석이 아니다.
  순회 한도에 도달하면 partial, 표시 그룹은 최대 32개다. 점검 입력은 최대 10,000행이다.
- repeated_chars는 첫 한 번을 뺀 동일 배열의 JSON 문자량이다. 절감 가능 토큰이나 불필요한 자료라는
  판정이 아니다. 정확한 비교를 위해 반복 맥락이 필요할 수도 있다. 자동 요약·절단·샘플링하지 않는다.
- 크기는 items JSON만 포함한다. 지시·system·schema·contract 및 모델 토큰·캐시·실제 비용은 포함하지
  않는다. 원본 items를 그대로 반환하므로 검사 결과 재사용이 가능하다.
- `inspect`와 `criteria`는 양립하지 않는다. 정적 검사와 실행 경계에서 거절하며 심사 모델을 호출하지
  않는다. 보통 실행의 criteria는 기존대로 동작한다. 입력 점검 앞에 둔 다른 생산자까지 무료 실행으로
  만드는 것은 아니므로, 이미 준비된 자료를 사용한다.

## 저장된 실패 사례의 재현

모델·보고서 실행 없이 기존 live-v3 자료를 읽었다. 업무별 계약은 평가 스크립트에만 있다.
재현 명령(경로는 저장소 기준):

```sh
.venv/bin/python3 scripts/evaluate_ibl_ai_boundary.py \
  --run-dir outputs/idiom_trials/ai_tips_rebuild_20260923/_runs/live-v3 \
  --output outputs/experiments/ibl_boundary_evaluation_20260923.json
```

| 관측 | 원문 맥락 추가 전 | 추가 후 |
| --- | ---: | ---: |
| 행별 요청 수 | 4 | 27 |
| items JSON 합계(문자) | 185,740 | 1,532,983 |
| 최대 요청(문자) | 56,908 | 56,986 |
| 동일 후보 배열의 첫 회 이후 반복량(문자) | 11,814 | 1,297,738 |

각 요청은 상한 아래지만 전체 전달량은 크게 늘었다. 이 점검은 그 차이를 호출 전에 보여준다.
추가 후 b19는 입력 19건 중 응답 1건, 누락 18건으로 거절됐다. 나머지 26개 응답은 c14의
verdict=unknown이 완료 조건(novel/duplicate) 밖이어서 거절됐다. 계약은 기존 소비자가 마지막에
하던 검사의 일부를 응답 직후에도 사용할 수 있게 한다. 입력만 보고 근거의 부족을 미리 알아냈다는
뜻이 아니며 unknown을 허용값으로 바꾸거나 확정 판단으로 꾸며 성공시키지 않는다.

`backend/test_ai_boundary_contract.py`는 번역·청구 항목 대조·빈 집합·여러 관계·다른 ID 열·입력 변조·
이전 결과 재사용·투영·상한·criteria 충돌을 검사한다. 순차 each의 모의 응답 시험에서는 첫 부분 응답
직후 1회 호출에서 멈추고 남은 두 요청과 후속 소비자를 실행하지 않았다. 실제 모델 호출은 0회다.

품질/비용 효과의 현재 근거는 실패 조기 탐지와 모델 없는 점검, 호환성 회귀다. 최종 보고서의 의미 품질,
실제 전체 실행 시간·전체 토큰 절감은 재실행하지 않아 미측정이다. 허용된 형태로 그럴듯하게 틀린
응답은 별도의 근거 대조·업무 검증·필요한 의미 검수 영역이다. 모든 호출에 자동 심사 모델을 붙이지 않는다.
