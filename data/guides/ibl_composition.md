# IBL 조합 — 새 문제를 한 프로그램으로 풀기

목표는 도구마다 AI가 다음 호출을 작성하지 않고, 이미 정할 수 있는 데이터 흐름을
한 번의 `execute_ibl`로 보내는 것이다. 길이 자체가 목표는 아니다. 필요한 내용 판단과
검증은 남기고, 검색·선별·반복·대조·저장 사이의 불필요한 왕복을 줄인다.

문법 전문: `[self:read]{path:"data/common_prompts/fragments/12_ibl_only.md"}`.
액션 인자와 출력 열: `execute_ibl(code="", describe=["table:filter","table:each"])`처럼
이번 프로그램에 필요한 1~6개를 묶어 조회한다. 실제 이름·입출력은 조회 결과를 따른다.
이 가이드의 `ibl` 코드 블록은 회귀 시험이 그대로 추출해 실행한다. 웹 응답만 고정하며
실제 웹 내용·AI 판단의 품질을 검증하는 시험은 아니다.

## 작성 순서

1. 최종 산출물과 합격 조건을 정한다. 필요한 출처·ID·본문·판정 열을 적는다.
2. 생산자→변환→소비자의 입출력 열을 맞춘다. 모르는 열은 추측하지 않고 describe 또는
   기존 결과의 `turn_vars.types`를 본다. 명확한 규칙은 filter/sort/select/compute에 둔다.
3. 독립 작업은 `A & B`, 의존 작업은 `A >> B`, 여러 곳에서 쓸 결과는 `$이름=A`로 둔다.
   할당은 즉시 실행되므로 `$a=A; $b=B; $a & $b`가 A·B를 병렬 실행하지는 않는다.
4. 같은 구조는 지역 def로 묶고, 전제가 맞는 관용구를 fn으로 끼운다. 새 업무가 기존
   관용구에 맞지 않으면 필요한 부품만 조합한다. 바깥 값은 함수 인자로 전달한다.
5. 빈값·실패·입력 규모·재개 위치를 설계한 뒤 check:true로 검사하고 실행한다.
   실패하면 traceback·저장된 결과를 바탕으로 해당 경계만 수리한다.

## 1. 단발 호출들을 파이프로 바꾸기

점수 5 이상만 남겨 ID·점수를 반환한다. 매 단계 결과를 AI가 읽고 옮길 이유가 없다.

<!-- example:pipeline -->
```ibl
$접수 = [{id:"a",score:3},{id:"b",score:7},{id:"c",score:5}]
$접수 >> [table:filter]{where:{field:"score",op:"gte",value:5}}
>> [table:sort]{by:"score",desc:true}
>> [table:select]{columns:["id","score"]}
```

결과는 b(7), c(5) 순이다. 전건 처리가 목표면 임의의 take를 넣지 않는다.

## 2. 같은 과제를 함수·병렬·관용구로 확장하기

두 출처를 합쳐 중복 ID를 제거하고, 통과한 상위 2건에 가중 점수를 붙인다.
`정렬해추리기`는 현재 노출되는 관용구다. 고정된 보고서 한 건이 아니라 새로운
프로그램의 한 부분으로 쓰며, 뒤에 일반 each를 연결한다.

<!-- example:compose -->
```ibl
[def:통과점수]{
  $통과 = $목록 >> [table:filter]{where:{field:"score",op:"gte",value:$최소}}
  $상위 = [fn:정렬해추리기]{목록:$통과,기준:"score",내림차순:true,열:["id","score"],개수:2}
  $return = $상위 >> [table:each]{limit:$상위.count} {
    $return = [{id:$it.id,score:$it.score,weighted:($it.score * $배수)}]
  }
}
$합 = [table:take]{items:[{id:"a",score:3},{id:"b",score:7}],n:2}
& [table:take]{items:[{id:"b",score:7},{id:"c",score:5}],n:2}
>> [table:union] >> [table:dedup]{by:"id"}
[fn:통과점수]{목록:$합,최소:5,배수:2}
```

결과는 b(7,14), c(5,10). 실제 수집에서는 두 take 생산자를 검색·조회 액션으로
교체하되 ID·score 계약을 맞춘다. 최소 점수를 99로 바꾸면 정상적인 빈 목록이다.
함수의 `$목록/$최소/$배수`는 명시 인자이고 `$통과/$상위`는 지역 결과다.
each는 원 행을 자동으로 모두 보존하지 않는다. 위처럼 ID를 반환하거나 keep을 쓴다.

관용구를 변형해야 하면
`[self:memory]{op:"recall",store:"실행",expand:"정렬해추리기"}`로 그 정의만 연다.
가령 개수 제한을 없애려면 sort→select로 지역 def를 작성하고 상위 제한을 제거한다.
전체 정의를 매번 펼치거나 같은 이름의 지역 def로 자신을 호출하지 않는다.
확인할 것은 입력/출력, 빈값/실패, 읽기·쓰기 효과, 내부 AI 호출이다. 정렬 관용구에는
AI가 없지만 이름에 '요약'·'판정'이 든 부품은 내부 비용을 따로 확인해야 한다.

## 3. 빈 결과와 장애를 구분하기

빈 후보는 정상적인 결과다. 그때만 다른 자료를 찾거나 '대상 없음'을 반환하려면 if를 쓴다.

<!-- example:empty -->
```ibl
$후보 = [table:take]{items:[],n:1}
$후보 >> [if:empty($items)]{
  [table:take]{items:[{status:"대상 없음"}],n:1}
} [else]{
  [table:select]{columns:["id"]}
}
```

`A ?? B`는 A의 실패뿐 아니라 0건에도 B를 실행한다. 검색 범위를 넓히는 등 그 두
상황을 모두 대체해도 될 때 쓴다. 장애만 처리할 때는 try/catch다.

<!-- example:catch -->
```ibl
[try]{
  [sense:crawl]{url:"https://example.org/bad"}
} [catch]{
  [table:take]{items:[{status:"원문 확인 실패"}],n:1}
}
```

이 URL은 시험에서 장애를 주입하는 예시다. 복구 뒤에도 `_caught` 진단을 확인하고
'원문을 읽었다'고 보고하지 않는다. catch에서 빈 행을 반환해 장애를 '대상 없음'으로
숨기지 않는다. 조건식 판정 불능도 false가 아니며 `condition_errors`를 확인한다.

## 4. 실패 항목만 한 번 더 읽기

기본 each는 성공 결과만 items로 흘리고 실패 원 행은 봉투 errors에 둔다.
`on_error:"keep"`을 선언하면 실패 원 행도 `_error`와 함께 items에 남는다.
성공 행에는 `_error`가 없으므로 이 열을 모든 행의 select에 넣지 않는다.
실패 0건이면 어느 행에도 없는 열이므로 filter도 바로 적용하지 않는다. 먼저 봉투의
error_count로 분기하고, 실패가 있는 가지에서만 성공/실패 행을 나눈다.

<!-- example:retry -->
```ibl
$주소 = [{id:"a",url:"https://example.org/one"},{id:"b",url:"https://example.org/bad"}]
$첫읽기 = $주소 >> [table:each]{keep:["id","url"],on_error:"keep",limit:2} {
  [sense:crawl]{url:$it.url}
}
$첫읽기 >> [if:$첫읽기.error_count == 0]{
  [table:take]{n:$첫읽기.count}
} [else]{
  $성공 = $첫읽기 >> [table:filter]{where:{field:"_error",op:"eq",value:null}}
  $실패 = $첫읽기 >> [table:filter]{where:{field:"_error",op:"ne",value:null}}
  $재시도 = $실패 >> [table:each]{keep:["id","url"],on_error:"keep",limit:$실패.count} {
    [sense:crawl]{url:$it.url}
  }
  $성공 & $재시도 >> [table:union]
}
```

첫 성공 a는 다시 읽지 않으며 b만 최대 한 번 더 읽는다. b가 계속 실패하면 실패 행이
남는다. 성공으로 바뀌어도 앞 실패의 진단은 이력으로 남을 수 있으므로 최종 items의
미해결 실패와 이전 `errors/error_count`를 구분해 보고한다. 큰 목록은 요청 수·시간
예산도 정한다. 업로드·결제·누적 저장처럼 부작용이 있는 동작에 이 패턴을 무조건
적용하지 않는다. 해당 액션의 멱등 키·상태 조회·영수증 규약을 먼저 확인한다.

## 5. 큰 원문은 분할 단위와 통합 규칙부터 정하기

다음 예제는 AI 없이 분할→행별 처리→통합을 실행한다. 각 조각의 위치와 원문을 보존한다.

<!-- example:chunk -->
```ibl
$원문 = "가나다라마바사아자차카타파하"
$덩이 = [if:$원문 == ""]{
  [table:take]{items:[],n:0}
} [else]{
  $원문 >> [table:chunk]{size:5,by:"chars",overlap:0}
}
$덩이 >> [table:each]{limit:$덩이.count,on_error:"stop"} {
  $return = [{index:$it.index,start:$it.start,text:$it.text,chars:$it.chars}]
}
>> [table:sort]{by:"index",desc:false}
```

빈 문자열은 먼저 빈 목록으로 처리한다. 위 원문에서는 3조각의 text를 순서대로 이어 붙이면 원문과 같다. `limit:$덩이.count`는 일부 조각만
처리하는 실수를 막는다. 실행 시간·용량 예산으로 멈출 수 있으므로 결과의 미처리 수도
확인한다. 실제 AI를 연결할 때는 each 안에 필요한 struct/ai/brief를 넣는다.

- 분할 크기는 원문만이 아니라 지시·스키마·비교 자료를 합친 실제 입력 상한에 맞춘다.
  개별 조각이 맞아도 마지막 통합 입력은 다시 커질 수 있다.
- 요약은 손실 변환이다. 정확한 중복 판정에 전체 과거 기록의 요약을 대신 넣지 않는다.
  ID·필수 필드로 정확히 대조할 수 있는 부분을 먼저 처리한다.
- 의미 비교가 필요한 후보와 과거 기록은 ID를 유지한 묶음으로 비교하고, 후보별
  '어느 묶음에서라도 중복'인지 합친다. '새 항목' 판정은 필요한 모든 묶음의 비교가
  끝났을 때만 가능하다. 유사도 검색으로 범위를 줄였다면 누락 위험을 별도로 검증한다.
- 누적 자료가 0건인 시험만 통과해서는 부족하다. 빈 자료·충분히 큰 누적 자료·하나의
  과대 행·마지막 통합 초과·일부 실패를 넣어 본다. ID·원문 근거는 계속 보존한다.
- 덩이 수가 N이면 내부 AI가 최소 N회 늘 수 있다. 바깥 모델 왕복만 줄었다고 비용
  감소로 결론내리지 않는다. 내부·외부 모델의 입력/출력/캐시 토큰과 시간을 합산한다.

## 6. 검증하고 작은 범위에서 재개하기

check:true는 문법과 알려진 타입을 검사하며 데이터 크기·웹 응답·내용 품질을 보증하지
않는다. 고정된 작은 입력으로 결과 열과 분기를 확인한 뒤 실제 규모를 검증한다.
단, 운영 데이터로 시험한다며 쓰기·발행을 반복하지 않는다.

단일 액션은 결과 객체, 파이프는 final_result가 최종값이고 results는 단계 상태다.
`success` 외에 `partial`, `errors/error_count`, `rows_unprocessed`, `truncated`,
`branches_failed`, `_caught`, `_fallback_used`를 확인한다. 모델 표시의 `_preview`는
실제 누락과 다르다. result_ref·변수로 원본을 읽으며 수집이나 생성부터 다시 실행하지 않는다.

실패가 `resume`을 주면 코드를 수리하고 그 값을 execute_ibl의 resume 인자로 전달한다.
`resume_vars`·`turn_vars.live/types`로 살아 있는 값도 확인한다. 성공 결과를 재사용하되
입력·판정 기준·앞 단계 코드가 바뀌면 영향받은 결과부터 무효화한다. 읽은 것·추출한 것의
성공 확정과 다음 요청 구성을 분리해야 다음 입력이 커서 실패해도 추출을 다시 하지 않는다.
재개 손잡이가 없다면 이전 코드 전체를 반복하지 말고 실제 남은 변수·파일·영수증으로
재개 가능한 위치를 확인한다. 보고서 본문·요약·건수는 동일한 최종 검수 행에서 만든다.

## AI 단계의 품질 계약

**criteria — AI step 의 품질 계약**: 원샷 AI 낱말(`[table:ai]`·`[table:brief]`·`[self:struct]`)은 실패 대신 *그럴듯하지만 나쁜 결과*를 낸다. 출력이 표면(write·notify·발행)으로 직행하면 `criteria` 로 기준을 선언하라 — 엔진이 심사하고, 미달이면 사유를 얹어 1회 재시도, 그래도 미달이면 `error_type: "quality"` 실패(`rejected_result` 에 미달 출력 동봉). 판정 최대 2회+재실행 1회의 추가 비용 — 규칙으로 적을 수 있으면 filter/take 가 먼저다. 예: `criteria: "종목명·수치 포함, items 에 없는 주장 없음"`. ★`[engines:image_read]{op:"critic"}` 의 criteria 는 그 도구 자신의 입력 — 이 계약이 아니다.

## AI 입력과 보존할 원본을 나누기

`[table:ai]{instruction:"각 문서에 요약 추가",input_fields:["title","text"],preserve_rows:true}`는
모델에 title·text·색인만 보내고 경로·출처 등 다른 열은 코드가 보존한다.
`fields`는 병합한 **출력**의 열을 줄이는 옵션이며 입력 비용을 줄이지 않는다.
input_fields는 최상위 열 이름의 중복 없는 비어 있지 않은 목록이다. 모든 행에 없는 열은
호출 전에 오류이며, 일부 행의 결측은 null로 채우지 않는다. 숨긴 기존 열을 모델이 수정하면 거절한다.
투영 출력은 유효한 `_i`가 필요하다. preserve_rows=true는 모든 색인의 정확히 한 번 반환을
검사하고 입력 순서로 복원한다. 기본 false의 선별·신규 행 동작은 그대로다.

행 보존·ID 집합·필드 존재는 이 계약과 결정론 소비자에 맡긴다. 중첩 result의 값 형식은
해당 소비자가 검사해야 한다. 근거의 충분성·과장·해석 품질은 독립 검수/criteria로 남긴다.
criteria를 자연어 모양이나 빈 행만 보고 자동 생략하지 않는다.

등록 스크립트로 결과를 인계할 때는 `input_as`를 쓴다([가이드](script.md)).
여러 단계의 절차는 검증한 결과를 먼저 영수증과 함께 원자 저장한 후 다음 요청을 준비한다.
준비 실패에는 완료된 근거와 재개 위치를 반환한다. 같은 run·설정·입력 지문으로 재개할 때만
완료된 모델/API 호출을 생략하고, 수정된 내용은 영향을 받는 검수부터 다시 실행한다.
이는 모든 외부 부작용의 exactly-once 보장이 아니다.

전체 자료 비교가 상한을 넘으면 ID를 붙여 분할하고 모든 배치·모든 대상 ID의 판정을 합친다.
unknown은 통과가 아니며 검색 상위 몇 건을 전건 검토로 부르지 않는다. 후속 편집에는 비교 범위·
판정 이유·연결된 근거를 재사용한다. 분할은 호출을 늘릴 수 있으므로 전체 입력·출력·캐시와
재시도까지 합쳐 비용을 평가한다.
