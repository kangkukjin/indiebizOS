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
  살아 있는데 취소를 지원하지 않는 종류(위임·렌더·신문·노트북)만 거절(`[catch]` 의 `$error.details.state` = 현재 상태).
  지원: `script`(러너가 스크립트와 그 자손을 끝내고 `cancelled` 기록, 보통 1~2초)·`guestpc`(아직 안 가져간 명령).
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
