# 목표 관리·조건·반복·예약

새 IBL은 현재 값·함수 문법으로 작성한다. `[goal: "이름"]` 선언은 구판 저장 프로그램의
문법이며 현재 새 코드에서는 지원하지 않는다. 이 문서를 읽고 새 goal 블록을 만들지 않는다.
문법 정본은 `data/system_docs/ibl.md`, 작성 교재는 `ibl_composition.md`다.

목표 관리, 한 프로그램 안의 반복, 시간이 지난 뒤의 실행을 구분한다.

| 의도 | 현재 경로 |
| --- | --- |
| 진행 중인 목표의 상태·종료·시도 이력 관리 | `[self:goal]{op:...}` |
| 읽은 값에 따라 분기·유한 반복 | `[if:]`, `[case:]`, `[repeat:]` |
| 나중에 또는 정기적으로 프로그램 실행 | `self:schedule`, `self:trigger`, `self:manage_events` |
| 매번 새로운 조사·판단이 필요한 목표 | 사용자 요구·달성 기준을 실행 에이전트에 전달하고 실행·검수 경로 사용 |

## 값을 먼저 읽고 조건으로 분기

조건에는 순수 Bool 식을 쓴다. 외부 도구 호출은 앞 문장에서 받고 실제 반환 필드를 확인한다.
다음은 입력값만 사용하는 실행 가능한 예제다. 실제 시세의 필드명·단위는 조회 계약을 따른다.

<!-- example:goal_condition -->
```ibl
#!ibl edition=2
$지수=2350
[if:$지수 < 2400] {
  return {판단:"방어 전략 검토",관측:$지수}
} [else] {
  return {판단:"추가 관측",관측:$지수}
}
```

`case`는 같은 값인 첫 `[when:식]` 가지를 고른다. 구간 비교는 if나 먼저 계산한 분류로 표현한다.

<!-- example:goal_case -->
```ibl
#!ibl edition=2
$지수=2700
$구간=$지수 > 3000 ? "높음" : $지수 < 2400 ? "낮음" : "중간"
[case:$구간] {
  [when:"높음"] { return "위험과 기대수익 비교" }
  [when:"낮음"] { return "손실 위험 점검" }
  [else] { return "추가 비교" }
}
```

## 프로그램 안의 반복과 시간 예약

`[repeat:횟수]`, `[repeat:while Bool식]`, `[repeat:until Bool식]`은 프로그램 안의 반복이다.
공유 실행 예산을 사용하며 대기 주기 `every` 인자는 없다. 횟수·종료 조건을 명시한다.

<!-- example:goal_repeat -->
```ibl
#!ibl edition=2
$합=0
[repeat:3] { $합=$합+$i }
return $합
```

매일 08시 같은 실행은 트리거로 등록한다. 아래 예제는 등록 시 캘린더 작업을 만든다.

<!-- example:goal_schedule -->
```ibl
#!ibl edition=2
[self:trigger]{op:"create",name:"매일 목표 확인",cron:"0 8 * * *",
  do:"[self:goal]{op:'list',status:'active'}"}
```

저장 원문은 현재 작성 문맥의 판본으로 고정된다. 외부 값을 보존할 때는 `inputs`를 사용하며,
실행 시점의 새 값은 저장 코드 안에서 조회한다. 자세한 등록·해제·결과 확인은 `trigger.md`,
`scheduler_guide.md`를 따른다. 예약 등록 성공은 목표 달성이나 실제 작업 완료가 아니다.

## 목표 프로세스 관리

`self:goal`은 기존 목표의 관리 액션이며 새 목표 생성 op는 없다.
실제 ID는 목록 응답에서 선택한다. 아래 `goal_001`, `T1`은 그 ID로 교체한다.

```ibl
[self:goal]{op:"list",status:"active"}
[self:goal]{op:"status",goal_id:"goal_001"}
[self:goal]{op:"attempts",task_id:"T1",limit:10}
```

- `kill`: `goal_id` 필수. 목표를 종료하고 스케줄을 제거한다.
- `delete`: `goal_id` 필수. 종결 목표 원장만 삭제하며 살아있는 목표는 먼저 kill한다.
- `log`: `task_id`, `approach_category`, `description` 필수, `result`·`lesson` 선택.
- `attempts`: `task_id` 필수, `limit` 선택. 과거 시도와 실패 범주를 확인한다.

같은 접근이 반복 실패하면 이력과 실패 근거를 확인해 다른 접근을 선택한다.
해결되지 않은 실패를 성공으로 바꾸거나 목표·품질 기준을 임의로 낮추지 않는다.
