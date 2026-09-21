# 판정 전용 어휘 — [table:judge]

AI가 자료와 기준을 보고 IBL에 판정 단계를 직접 구성한다. 각 행의 참/거짓·분류·점수를
Jev에 묻고, filter/if/sort로 이어간다. 같은 입력에 대한 독립 질문은 `questions`에 묶는다.
질문 이름은 출력 경로일 뿐이다. `instruction`에 판단 대상을 포함한 완전한 기준을 쓴다.

## 어느 낱말을 쓰나

- 날짜·금액·정확한 중복 등 규칙 비교: 기존 table:filter/dedup와 IBL 조건식.
- 관련성·광고성·의도 분류 등 범위가 정해진 의미 판정: table:judge.
- 새 내용 추출·재작성: self:struct/table:ai. 산문 설명·요약·판정 이유: table:brief.
- 목표·기준 수립과 새 계획은 실행 AI가 한다. judge는 기준을 받아 판정한다.

## 상시 관용구로 부르기

- `검색 items >> [fn:관련자료골라읽기]{질문:"조사 질문",개수:4}`:
  url·title·summary 후보를 판정하고 관련·불확실 자료의 원문을 읽는다.
- `본문 items >> [fn:의미로본문찾기]{질문:"찾을 내용",문맥:1,개수:5}`:
  text·url 문단에서 관련 대목과 같은 URL의 앞뒤 문맥을 원문으로 반환한다.

파이프 대신 `목록` 인자로 items 봉투 또는 행 목록을 직접 전달할 수 있다.
반환형은 둘 다 items이며 생성형 요약은 하지 않는다. 명확한 false만 제외하고
unknown·미판정은 보존한다. 개수는 선별할 페이지/중심 문단 상한이며 문맥·실패 행은
그 상한 밖에서도 반환한다. 0이면 Jev·크롤을 호출하지 않지만 원천 실패 증거는 남긴다.
`judgment_audit`·`selection_info`로 판정 내역과 상한 생략을 확인하고,
`error_count`·`partial`로 원천/크롤 실패를 확인한다. 입력의 잘림도 보존한다.
정확한 문자열 검색이면 `본문에서찾기`, 모든 URL을 읽으려면 `주소마다읽기`를 쓴다.
절약 효과는 별도 비교 실험 대상이다.

등록 계약 유지보수: `scripts/register_idiom.py --refresh 이름`은 현재 본문에서
반환형·서명을 다시 계산하고 가지 문서를 갱신한다. 본문·실행 실적은 바꾸지 않는다.
기존 이름의 길이·슬롯 수에 신규 승격 정책을 재적용하지 않으며, 본문의 구문·액션·인자·타입 검증은 유지한다.
선정집 재적용도 파생 계약을 갱신한다. [수리 기록](../../docs/JUDGMENT_IDIOM_REGISTRATION_REPAIRS_2026_09_21.md).

## 참/거짓 → 바로 필터

```ibl
[table:judge]{items:[{text:"결제한 돈을 환불해 주세요."},{text:"배송일을 알려 주세요."}], instruction:"이 고객은 환불을 요청하는가?"}
>> [table:filter]{where:{field:"judgment_result_value",op:"eq",value:true}}
```

단일 질문 이름은 `result`, 결과 열 접두사는 `judgment`다. 원 행·순서·개수를 보존하며 판정 열만
추가한다. 같은 열이 이미 있으면 실패한다. 다시 판정하려면 `as:"재판정"`처럼 새 이름을 준다.
파이프 입력 또는 `items`를 받는다(명시 items 우선). 평문은 `items:[{text:"…"}]`로 감싼다.

## 선택·점수·여러 질문

```ibl
[table:judge]{items:[{text:"상품이 파손되어 왔습니다. 오늘 교환해 주세요."}], questions:{
  urgent:{type:"boolean",instruction:"오늘 또는 즉시 처리를 명시적으로 요청하는가?"},
  category:{type:"choice",instruction:"고객의 주된 요청은 무엇인가?",criteria:{refund:"환불",exchange:"교환",other:"기타 또는 정보 부족"}},
  severity:{type:"score",instruction:"상품 문제의 심각성은?",criteria:["문제 없음","사용 가능한 경미한 문제","파손 또는 사용 불가"]}
}}
```

`choice`는 선택지→설명(문자열/null) 맵(2~255개), `score`는 낮은 순 등급 목록(2~10개)을
받는다. 점수는 **0부터 N-1까지의 실수**이며 확률이 아니다. 질문마다 서로 다른 형식을 섞을 수 있다.
행별 판정은 독립이며 각 질문에는 해당 행의 경로가 명시된다. 다른 행과 함께 비교하려면
`items:[{candidate:…,reference:…}]`처럼 비교할 자료를 같은 행에 넣는다.

## 불명은 거짓이 아니다

결과는 `judgment_<질문이름>_<필드>`라는 평평한 열이다. 예: `judgment_result_value`,
`judgment_result_status`. 아래 필드 이름에는 모두 이 접두사가 붙는다.

- 공통: `value`(확정 값 또는 null), `status`(`decided`/`unknown`).
- boolean: `probability`(참 확률). 별도 confidence를 만들어 내지 않는다.
- choice: `choice`(원 선택), `confidence`, `probabilities`(선택지별 확률).
- score: `score`(원 점수), `confidence`, `probabilities`, `legend`(0부터 등급표).

`threshold` 기본 0.8: boolean은 참 확률≥0.8이면 true, ≤0.2면 false, 그 사이면 unknown.
choice/score는 제공자 confidence가 threshold 이상일 때만 value를 확정한다. 원 선택/점수와
확률분포는 unknown이어도 남긴다. **confidence는 정답률이 아니라 확률분포의 집중도**다.
임계값은 업무 사례로 조정해야 한다. 높은 확률도 증거의 존재나 사실의 진위를 보증하지 않는다.

```ibl
$r = [table:judge]{items:[{text:"검토 중입니다."}], instruction:"승인을 명시했는가?"}
[if: $r.items.0.judgment_result_status == "unknown"] {
  $return = {status:"추가 확인 필요"}
} [else] {
  $return = {approved:$r.items.0.judgment_result_value}
}
```

후속 LLM 호출은 IBL 작성자가 unknown 분기에 명시한다. 자동으로 호출하지 않는다.
통신·인증·응답 계약 실패는 `success:false`이며 unknown이나 false로 바꾸지 않는다.
권한·금액 계산·업무 확정 규칙은 기존 코드가 소유한다.

## 호출·인증·한계

- `.env`의 `TYPESAFE_API_KEY` 사용. 런타임 환경변수 우선, 없으면 몸의 `.env`에서 읽는다.
- 제공자 어댑터는 TypeSafe `POST https://api.typesafe.ai/v1/systemone`, 모델 `jev-latest`.
  생성형 기어와 독립된 직접 API이며 키·실제 제공자 모델명은 IBL 문장에 넣지 않는다.
- **행 수×질문 수≤100**, 전체 JSON 요청≤60,000자(로컬 상한, 토큰 상한 보장은 아님).
  초과는 자르지 않고 거절한다. 입력을 filter/take로 줄이거나 묶음으로 나눈다.
- 비어 있는 items는 호출 0, 정상 입력은 API 요청 1회. 질문별·행별 개별 호출이 아니다.
  오류 때 자동 재시도/생성형 LLM 폴백도 없다. 요청 대기는 연결 10초·응답 60초.
- 봉투에 `api_calls`, `questions_evaluated`, `unknown_count`, `usage`, `latency_ms`, `model`을
  기록한다. ProviderMetrics로 활성 턴 토큰 원장에도 합산한다. 금액을 0으로 주장하지 않는다.
- 입력 행은 TypeSafe API로 전송된다. 판정 단계는 선택·점수·확률만 반환하며 이유 문장을 생성하지 않는다.
- 한 요청의 질문들은 앞 질문의 답을 볼 수 없다. 새 증거나 이전 답이 필요하면 다음 IBL 단계에서 호출한다.

실행 가능한 용례: `data/packages/installed/tools/ai-ops/judge_examples.json`.
설계와 검증: `docs/JEV_JUDGMENT_2026_09_21.md`.
공식 계약: https://docs.typesafe.ai/api · https://docs.typesafe.ai/confidence
