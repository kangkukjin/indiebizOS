# 긴 작업 접수증과 대기 — `[self:task]` (2026-10-05)

긴 작업(위임·script 백그라운드·guestpc 명령·신문 발행·강의 렌더·노트북 색인·시트 엔진 작업)은 **접수증** 하나를 즉시 돌려준다.
접수는 완료가 아니다. 접수증의 `task_ref` 를 `[self:task]` 에 넘겨 상태를 읽거나 끝날 때까지 기다린다. 명세는 `ibl.md` '작업 접수증과 대기'.

## 모양
- 접수증: `{success, accepted: true, task_ref: {kind, task_id[, owner]}, state: queued|running, accepted_at, …}`
- 투영(**항상 같은 칸**): `{task_ref, state, terminal, timed_out, result, failure, progress, accepted_at, elapsed_s}` — `result` 는 `succeeded` 일 때만 값(아니면 null), `failure` 는 작업의 실패 사유(아니면 null). `error` 칸은 없다 — 읽으면 검사에서 거절된다. 선택 칸(`raw`·`note`)은 `get($r,"note")`.
- **접수 기준 시계**: `accepted_at`(접수 시각)·`elapsed_s`(접수부터 지금까지, 끝난 작업은 종료까지의 초 — 종류가 시각을 모르면 null). `wait` 의 `timeout` 은 그 호출이 기다린 시간일 뿐이다.
  "접수 후 N초 안에 끝났는가"는 `$r.elapsed_s` 로 판정한다 — 접수와 대기를 다른 프로그램에 두면 그 사이 시간이 `timeout` 에 잡히지 않는다(한 프로그램에 두면 생기지 않는다).
- 한 턴에서 위임하고 같은 턴에서 `wait` 로 결과를 읽었으면 그 결과가 전부다 — 뒤따르는 완료 보고로 새 턴이 열리지 않는다. 읽지 않고 턴을 끝낸 위임만 보고가 새 턴으로 도착한다.
- 상태: `queued · running · waiting_children · cancel_requested · succeeded · failed · cancelled · interrupted · unknown`

## 쓰는 법
```
$job = [self:script]{op: "run", id: "나레이션생성", args: {lecture_id: "x"}, background: true}
$r = [self:task]{op: "wait", ref: $job.task_ref, timeout: 120}       # 끝나면 $r.result, 초과면 $r.timed_out == true(값 — 프로그램은 계속된다)
$r.result                                                            # 다음 낱말에 값으로 잇는다
```
```
$a = [others:delegate]{agent_id: "조사", message: "…"}               # 접수증(kind: delegation)
$b = [engines:newspaper]{}                                          # 접수증(kind: newspaper)
$ra = [self:task]{op: "wait", ref: $a.task_ref, timeout: 240}; $rb = [self:task]{op: "wait", ref: $b.task_ref, timeout: 120}
return {report: $ra.result, paper: $rb.result}                       # 둘을 기다려 합친다
```
- `status` 는 즉시 한 번 읽는다 — 실패한 작업도 **값**으로 답한다(`state: "failed"`, `failure`). 모르는 작업(`unknown`)만 호출 실패.
- `wait` 는 유한(기본 60초·상한 240초). 세 갈래: 성공 → `result` · **시간 초과 → 값**(`timed_out: true`, 같은 ref 로 다시 `wait`) ·
  작업이 실패·취소·유실로 끝남 → 이 호출이 실패(`[catch]` 의 `$error.details.state`·`.failure`·`.task_ref` 로 사정을 읽는다).
```
[def:관찰]($접수, $초) {                                              # 여러 작업 중 안 끝난 것·실패한 것을 갈라 보고할 때
  [try] {
    $r = [self:task]{op: "wait", ref: $접수.task_ref, timeout: $초}
    [if:$r.timed_out] { return {상태: "진행 중", task_ref: $r.task_ref} }
    return {상태: "완료", result: $r.result}
  }
  [catch] { return {상태: "오류", state: $error.details.state, 사유: $error.details.failure} }
}
```
- **작업을 시작한 프로그램이 뒤에서 실패했을 때**: 시작 낱말을 다시 부르면 작업이 중복된다. 실패 응답의 `result_ref.completed_calls[i].input_args`
  (시작 호출의 접수증 참조)를 다음 프로그램의 `inputs` 로 넘겨 **관찰부터** 이어간다. 길어질 일은 "시작만 하고 접수증을 반환하는 프로그램"과
  "접수증을 받아 기다리는 프로그램"으로 나누면 이 문제가 생기지 않는다.
- `cancel` 은 확인된 사실만 말한다 — **`state` 로 읽는다**. `cancelled`(멈춘 것을 확인) · `cancel_requested`(요청만 남음 — 같은 ref 로 `status`/`wait`) ·
  **이미 끝난 작업은 값**(그 종료 투영 그대로: `succeeded` 면 `result` 도 있다. 늦어서 취소하려는 순간 끝나 있는 것은 실패가 아니다) ·
  살아 있는데 취소를 지원하지 않는 종류(렌더·신문·노트북)만 거절(`[catch]` 의 `$error.details.state` = 현재 상태).
  지원: `script`(러너가 스크립트와 그 자손을 끝내고 `cancelled` 기록, 보통 1~2초)·`guestpc`(아직 안 가져간 명령)·`delegation`(개별 작업의 실행 종료 확인)·`ibl_run`(보존된 프로그램).
```
$c = [self:task]{op: "cancel", ref: $job.task_ref}                     # 기다리다 늦은 일을 멈출 때
[if:$c.state == "succeeded"] { return {상태: "완료", result: $c.result} }   # 그 사이 끝났다 — 결과를 쓴다
return {상태: $c.state}                                                # cancelled | cancel_requested (| failed·interrupted)
```
- `unknown` 은 "이 몸이 모르는 작업"(유실·재기동·이미 회수됨·잠든 패키지)이지 실패가 아니다 — 새 작업을 다시 시작할지는 작업의 성격으로 판단.
- 같은 명령을 **다시 보내지 말 것** — 접수증이 있으면 그 ref 로 기다린다(이중 실행 방지). 목표(`self:goal`)는 다른 수명이라 이 낱말로 읽지 않는다.

## 새 긴 작업을 만들 때
- 시작 낱말은 `task_receipts.receipt(kind, task_id, state=..., ...)` 를 돌려준다(옛 키는 호환으로 함께 실어도 됨).
- 어댑터 `task_status(ref) -> task_receipts.view(...)` 를 그 패키지 모듈에 두고, `ibl_actions.yaml` 최상위 `task_kinds: {kind: "모듈:함수"}` 로 선언한다.
  취소를 지원하면 `<함수>_cancel`(끝난 작업이면 현재 투영을 그대로 돌려준다 — 등록부가 값으로 답한다). 상태 번역은 **한 벌 어휘**로만(밖의 값은 등록부가 unknown 으로 거절한다).

## HTTP 연결을 넘는 대기와 승인

현재 IBL에서 `[self:task]{op:"wait",ref:$job.task_ref,suspend:true}`는 기본 timeout 0으로
상태를 보고, 아직 실행 중이면 프로그램을 `suspended`로 보존한다. 반환된 `resume`과
`task_ref(kind:ibl_run)`를 유지한다. 주인 실행은 백엔드가 자식 종료를 관측하면 같은
원장으로 재개한다. 재기동해도 대기 기록이 남는다. 회원·손님 실행은 인증된 명시 resume을 사용한다.
승인 대기는 자동으로 승인하지 않는다. 화면은 호출별로 승인을 받고 같은 resume으로 이어간다.
완료 영수증이 있는 위임·쓰기는 반복하지 않으며, 응답 불명의 외부 효과는 재실행하지 않는다.
`catch`·`finally`는 승인/작업 대기 자체에서 실행되지 않고 이후 실제 완료·실패·취소에서 실행된다.

위임 완료 보고는 부모의 기존 delegation_context에 보존하고 처리 또는 명시 회수 뒤 확인한다.
부모가 동작 중이면 보고를 연기하며, 메모리 큐를 잃어도 미회수 보고를 다시 가져온다.
처리 중 프로세스가 죽으면 재전달될 수 있다. 원격 효과에 보편적인 exactly-once를 약속하지 않는다.
취소는 상주 에이전트 전체를 정지하지 않는다. 자식 작업을 취소하려면 그 자식의 접수증으로
별도 요청한다. 실행기가 실제로 종료를 확인하기 전에는 `cancel_requested`다.


## IBL의 다음 호출 인자 변경

실행 중인 `ibl_run`의 `status.progress`는 `root_task`, `plan_hash`, `boundaries`,
`requests`를 제공한다. boundary의 `node_id`, `revision`, `next_ordinal`을 그대로 사용한다.
지원 대상이 없으면 boundaries는 빈 목록이다. 시작한 호출을 바꾸거나 재실행하지 않는다.
읽기·순수 호출과 **자원 선언이 있는 아직 시작하지 않은 쓰기**를 지원한다.
쓰기 변경은 선언된 읽기/쓰기 자원 신원이 그대로일 때만 적용하며, 경로·수신자 등 자원을
바꾸는 요청과 자원 신원 미상은 적용하지 않는다. 부품의 기존 권한·원문 판본 검사는 유지한다.
모든 쓰기에 새로운 원문 판본 조건을 만들어 주는 계약은 아니다.
병렬과 `table:each`도 읽기/순수/쓰기 효과가 알려지고 쓰기 자원이 선언된 범위에서 지원한다.
공유 함수·람다와 반복 항목의 같은 코드 위치는 아래의 실행 `scope`로 구별한다. 병렬 진입의
기존 자원 충돌 검사를 통과해야 하며, 조향 후에도 확인된 분기별 접근 범위를 유지한다.
효과 미상·쓰기 자원 선언 누락·동적 의존 부품·실행 중인 호출·정의 교체는 조향하지 않는다.

조향 후 정의를 수정하려면 실행이 종료된 뒤 기존 `repair`의 check/plan_hash 경로를 사용한다.
효과 의존성과 완료 의무를 유지하는 수정만 가능하다. 검사 결과의 `inherited_controls`는
계승할 request_id와 기존 call_id를 보여 준다. 완료된 읽기·쓰기의 적용 인자를 원래 호출 ID로
복원하여 영수증을 재사용하며, 원래 조향의 `applied`·call_ref 이력은 유지한다.
반환 불명 효과는 `EFFECT_UNCERTAIN`, 원장 호출이 없는 적용 조향(순수 어댑터 포함)은
`REPAIR_UNSUPPORTED`로 검사에서 거절한다. 후자는 같은 정의의 일반 resume 지원과 별개다.
수리 검사 뒤 적용 기록이 바뀌면 plan_hash가 무효가 되며, 실행 중 정의를 교체하지 않는다.

`[self:task]{op:"steer",ref:$ref,request_id:"고유 요청 ID",message:$json}`의 message는
다음 필드가 있는 JSON 문자열이다. boundary에 `scope`가 있으면 그 필드도 필수로 복사한다. 기대 인자는 파이프 주입/별칭 정규화 뒤의 값이다.
Python 연결에서는 `ibl_v2_ir.digest(expected_args)`로 동일 값 지문을 만든다.

```json
{"root_task":"status에서 받은 값","plan_hash":"status에서 받은 값",
 "node_id":"boundary의 값","revision":"boundary의 값","ordinal":1,
 "expected_args_hash":"기대 인자의 digest","changes":{"변경할인자":"새 값"}}
```

`delivery:accepted`는 접수만 뜻한다. 적용 후 `status.progress.requests`의 state는
`applied`, 입력/판본 불일치·취소·미도달이면 `not_applied`와 reason이다.
같은 request_id와 같은 요청은 기존 상태를 반환하고 다른 요청의 재사용은 거절한다.
`status.result`와 대기·완료·취소의 뜻은 기존 접수증 계약을 유지한다.

쓰기 조향의 `applied`는 **인자 적용**이다. 외부 효과의 성공이나 취소를 뜻하지 않는다.
요청에 연결된 기존 원장 호출은 `call_ref`로 표시하고 `effect_state`를 구분한다:
`not_started`(효과 시작 기록 없음/승인 대기), `returned`(값 영수증이 반환됨),
`unknown`(시작 기록은 있으나 결과·효과를 확정할 수 없음).
`returned`도 목표 달성 판정은 아니다. 취소 뒤 늦은 반환의 영수증도 보존한다.
완료 효과는 같은 영수증으로 재사용하고 효과 불명 쓰기는 재전송하지 않는다.
기존 호출 순번에 새 request_id를 붙여 이미 시작한 쓰기를 다시 조향할 수 없다.

### 반복 항목·공유 함수의 실행 scope

`addressing:"scope"`인 boundary는 현재 열린 실행 프레임에서만 제공한다. `scope`는
기존 실행 경로·본문 위치·해당 진입 순번에 묶인 불투명 주소다. 직접 계산하거나 다른
프로그램/실행의 값을 재사용하지 않고 해당 `status.progress.boundaries`의 값을 그대로 보낸다.
`scope_context`는 `route`, `body_id`, `entry_ordinal`을 보여 준다. route의 반복 인덱스는
0부터 시작하며, 함수 호출과 중첩 반복의 경로도 보존한다. 입력 본문은 이 좌표에 싣지 않는다.

한 반복 항목에서 접수한 변경은 그 항목의 다음 호출에만 적용한다. 같은 본문을 실행하는
다른 항목·함수 호출에는 적용하지 않는다. 아직 시작하지 않아 scope가 없는 항목은 조향하지
않으며, 프레임이 종료되면 미도달 요청은 `not_applied` / `scope_closed`가 된다.
종료된 scope·다른 위치의 scope·scope 누락은 거절한다. 새 작업이나 효과 소유자를 만들지 않는다.

동일 계획을 재개하면 같은 실행 좌표와 적용된 인자를 복원하여 기존 영수증을 재사용한다.
이전 버전의 전역 node 주소로 접수한 요청은 같은 계획의 재개에서도 그 주소를 유지한다.
병렬 분기의 취소 검사 간격은 서로 공유하지 않으며, 한 번 관측한 취소는 그 실행에서 유지한다.

### 쓰기를 포함한 병렬·each의 자원 경계

쓰기 인자의 `resource_policy:"unchanged"`는 대상 자원 신원을 유지한다는 뜻이다.
같은 계획의 읽기·순수 부품에는 `resource_policy:"admitted"`가 표시될 수 있다.
병렬 진입 때 해석한 분기별 읽기/쓰기 자원 목록을 중첩 실행에도 전달한다. 변경할 호출이
그 범위를 벗어나면 `not_applied / PARALLEL_RESOURCE_CHANGED`로 남기고 원래 인자로 진행한다.
쓰기 대상을 바꾸는 요청은 기존 `write_resource_changed_or_unknown`으로 적용하지 않는다.

조향 결과가 다음 호출의 자원에 영향을 주는 경우도 효과 전에 검사한다. 후속 호출이
입장 때 확인한 자원 신원·접근 방식 밖으로 나가거나, 알려진 범위가 미상으로 바뀌면
`PARALLEL_RESOURCE_CHANGED`로 중단한다. 중첩 병렬은 바깥과 안쪽의 범위를 모두 지켜야 한다.
기존 입장 검사에서 미상으로 처리한 접근 범위를 새로 좁혔다고 주장하지 않으며,
미상 자원 사이의 병렬 충돌을 허용하도록 입장 검사를 완화하지 않는다.

이 검사는 외부 프로세스의 파일 변경을 잠그는 전역 잠금이나 모든 어댑터의 공통 CAS가 아니다.
파일의 원자적 교체로 inode가 바뀌어도 같은 경로 신원은 유지한다. symlink가 다른 대상으로
바뀌어 확인된 자원에서 벗어나면 조향 이후 호출은 시작하지 않는다. 원래 권한·판본 검사는 유지한다.

마지막 호출 중 취소가 들어와도 실행 완료 직전에 다시 확인한다. 이미 반환된 값은
`partial_wire`에, 외부 효과는 기존 영수증에 보존하며 전체 실행을 성공으로 보고하지 않는다.
취소가 완료된 쓰기를 되돌렸다는 뜻은 아니다.
