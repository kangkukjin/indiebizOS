# IBL 표현력 개정 — 구조 투영·관계 결합·코드 블록

2026-09-08 착수, 09-09 검증. 사용자 지시: “다 고쳐봐”. 작성 규칙은 [후속 정리](IBL_LEARNABILITY_2026_09_09.md)에서 일반 값 구성·each를 먼저 가르치는 방식으로 보완했다.

특정 보고서의 전용 관용구를 추가하지 않고, 임의의 데이터 흐름에서 반복되던 세 가지 우회를 언어에서 없앴다. 기존 노드·액션 수와 기존 문법은 유지한다. 변경은 표준 코어 안의 문법·기능어 계약 개정이며 AI 호출을 추가하지 않는다.

## 1. 구조를 한 번에 만드는 투영

기존 `select{columns:[...]}`는 그대로 동작한다. 객체를 주면 각 행에 대해 출력 구조를 구성한다.

```ibl
[table:select]{
  items:[{video_id:"007",title:"예제",url:"https://example.test",price:3,qty:2}],
  columns:{
    label:"title",
    source:{id:"video_id",url:"url"},
    prices:["price"],
    total:"price * qty"
  }
}
```

- 객체·목록은 출력 모양, 잎 문자열은 한 줄 식이다. 문자열 상수는 `"'고정 문자열'"`처럼 식 안에서 인용한다. 숫자·불리언·null 리터럴은 그대로 쓸 수 있다.
- 복사와 문자열 함수는 원형 타입을 보존한다. `"007"`은 문자열이다. 산술의 숫자 관측은 assign/compute/select/reduce가 공용 규칙을 쓴다(09-09 후속 정리).
- 이름 변경·계산·중첩 구성을 한 번에 처리한다. 필드 결측·식 실패는 행을 조용히 버리거나 null로 바꾸지 않고 전체 투영을 실패시킨다. 빈 입력은 빈 출력이다.
- 명시 표형 입력은 표형, items 입력은 items로 나온다.
- 한 줄 식 평가기 자체도 객체·목록 구성을 허용하므로 compute·reduce·변수 할당에서 쓸 수 있다. 객체 키는 중복 없는 문자열 상수다. 펼침·컴프리헨션·속성 접근·임의 함수 호출은 허용하지 않는다. 임의 실행문과 외부 라이브러리는 script의 영역이다.

정본 구현: `backend/common/safe_expr.py`, 패키지 `dataops_projection.py`. 정적 검사도 같은 식 컴파일러와 참조 필드 추출기를 쓴다.

## 2. 행 보존과 존재 결합

```ibl
$목록=[table:take]{items:[{id:"a"},{id:"b"}],n:2};
$건수=[table:take]{items:[{id:"a",n:3}],n:1};
$목록 & $건수 >> [table:join]{on:"id",how:"left",defaults:{n:0}}
```

| how | 결과 |
|---|---|
| inner | 기존 기본값. 일치하는 모든 쌍 |
| left | 모든 왼쪽 행과 일치하는 오른쪽 행 |
| right | 모든 오른쪽 행을 포함하는 결합 |
| full | 양쪽의 불일치 행까지 포함 |
| semi | 오른쪽에 짝이 있는 왼쪽 행. 오른쪽 중복으로 복제하지 않음 |
| anti | 오른쪽에 짝이 없는 왼쪽 행 |

`defaults`는 left/right/full에서 **짝이 없는 쪽**의 결과 열만 채운다. 실제 데이터의 null은 유지한다. 열 충돌은 기존 접미사 규약(`n_2` 등), defaults도 결과 열 이름을 쓴다. 스키마 없는 빈 items의 추가 열은 defaults로 선언할 수 있다. 잘못된 how/defaults/키는 오류다.

복합키·값 정규화·null/빈 키 판정은 기존 `group_keys`와 `common.value_semantics`를 공유한다. 빈 키끼리 일치시키지 않는다. 순서는 왼쪽 행 순서와 각 오른쪽 일치 행 순서이며, right/full의 오른쪽 불일치 행은 뒤에 붙는다. 결과를 특정 순서로 비교하려면 sort를 명시한다. inner의 기존 구현과 반환 형태는 보존했다.

정본 구현: 패키지 `dataops_join.py`. 타입 검사기의 결합 열 선택은 액션 이름이 아닌 `flow.columns_variants` 데이터로 선언한다.

## 3. 문자열로 감싸지 않는 반복 몸통

```ibl
[table:each]{items:[{id:1},{id:2}],parallel:2} {
  $행=[table:take]{items:[$it],n:1};
  [if: count($행.items) > 0] {
    $행 >> [table:compute]{set:{label:"'item ' + str(id)"}}
  }
}
```

기존 `do:"…"`와 같은 코드 IR·실행 경로를 사용한다. 두 표기를 동시에 쓰거나 비어 있거나 닫히지 않은 몸을 주면 오류다. 기존 as/parallel/limit/keep/collect/on_error 계약은 유지한다. 정적 검사도 실제 실행과 같은 IR을 읽고, 확정된 몸통 구문 오류를 실행 전에 거절한다.

단순히 괄호만 추가하지 않았다. 새 조합 시험에서 다음 공백도 수리했다.

- if/case/try/repeat의 몸은 바깥 변수를 파이프 머리로 읽는다. 안쪽에 바깥 step 번호를 복사하지 않고 이름과 값을 연결한다. 파서의 범위는 ContextVar로 격리·회수한다.
- 최상위·일반 블록에서 미할당 이름은 오류다. 함수는 바깥 변수를 암묵적으로 캡처하지 않고 닫힌 인자 범위를 유지한다.
- 지연 몸 안의 변수 방출도 외부 슬롯 캡처를 IR로 운반한다. JSON 전송 왕복 후에도 값으로 바인딩한다.
- 분기가 여러 단계의 파이프로 끝나도 결과 items를 바깥 반복문에 전달한다. 진단 봉투 때문에 결과 대신 원 행이 흐르던 결함을 수정했다.
- case의 갈래는 첫 액션만 읽는 대신 전체 파이프를 읽는다. 알 수 없는 문자를 조용히 건너뛰지 않으며 패턴은 기존대로 따옴표를 쓴다.

## 검증과 실측

전체 backend 회귀 **3,125 passed / 2 skipped**(113.03초), 신규 기능 검사 51건 통과. 어휘/파생물 검사, 은퇴 계약 검사, backend 층·순수 코어 폐포 검사와 Android 번들 재생성을 완료했다.

신규 회귀는 구조 값·문자열 식별자 보존, 계산·결측 실패, 빈 입력, 중복/복합/빈 키, 6개 결합 방식의 items/표형 일치, 함수/반복/분기/병렬 조합, 잘못된 몸통, 스코프 회수, IR 전송을 검사한다. 기존의 객체 생성 금지 시험은 새 허용 계약 및 컴프리헨션 거절 시험으로 개정했다.

`scripts/experiment_ibl_expressiveness.py`는 같은 입력·기대 결과를 두 표기로 실제 실행한다. 입력 리터럴과 정렬까지 포함한 소스 길이이며 두 표기는 모두 개정 엔진에서 실행한다.

| 비교 프로그램 | 기존 표기 | 새 표기 | 감소 |
|---|---:|---:|---:|
| 구조 투영 | 154자 | 127자 | 17.5% |
| 보존 결합 | 314자 | 194자 | 38.2% |
| 반복 코드 블록 | 165자 | 160자 | 3.0% |

세 쌍 모두 결과와 실행 전 검사가 일치한다. 실행 중 앱 `/ibl/execute`에서도 새 표기 3건을 실행해 기대 결과와 일치했다. AI 호출 0회다. 블록 표기의 주된 이득은 글자 수보다 이스케이프와 조합 오류 감소다.

앞선 AI 팁 실험의 저장 자료도 실제 앱에서 다시 변환했다. 조회 49행에 팁 건수를 left join으로 붙이고, 평탄한 팁 13행을 select로 중첩했다. 이전의 수리 완료 원장 49행과 필드 값이 같고(행 순서 제외), 스크립트로 만든 중첩 팁 13행과 순서·필드·값이 완전히 같았다. 1,081자 프로그램, 0.1184초, AI 0회. 입력 파일 해시는 기록에 남겼다. 기존 파일을 수정하거나 검색·모델 호출을 재실행하지 않았다.

이 수치는 **전체 13,797자 보고서 프로그램의 절감률이나 보고서 생성 속도가 아니다**. 전체 보고서의 의미 판단·프롬프트·AI 비용은 별도 비교가 필요하다. 문자열 몸통을 허용 블록으로 바꾸는 것만으로 내부 AI 호출 수가 줄지는 않는다. 폰 번들은 재생성했지만 물리 기기 실행은 확인하지 않았다.

원시 기록: [비교 결과](experiments/ibl_expression_revision_2026_09_08/comparison.json), [앱 실행](experiments/ibl_expression_revision_2026_09_08/live.json), [보고서 자료 재실행](experiments/ibl_expression_revision_2026_09_08/report_data_replay.json), [해당 IBL](experiments/ibl_expression_revision_2026_09_08/report_data_replay.ibl).

재현:

```sh
PYTHONPATH=backend:scripts .venv/bin/python scripts/experiment_ibl_expressiveness.py --out outputs/ibl_expression_comparison
.venv/bin/python -m pytest backend/test_ibl_expression_revision_2026_09_08.py -q
```
