# 긴 작업 접수증과 대기 — `[self:task]` (2026-10-05)

긴 작업(위임·script 백그라운드·guestpc 명령·신문 발행·강의 렌더·노트북 색인·시트 엔진 작업)은 **접수증** 하나를 즉시 돌려준다.
접수는 완료가 아니다. 접수증의 `task_ref` 를 `[self:task]` 에 넘겨 상태를 읽거나 끝날 때까지 기다린다. 명세는 `ibl.md` '작업 접수증과 대기'.

## 모양
- 접수증: `{success, accepted: true, task_ref: {kind, task_id[, owner]}, state: queued|running, …}`
- 투영: `{task_ref, state, terminal, progress?, result?, error?}` — `result` 는 `succeeded` 일 때만.
- 상태: `queued · running · waiting_children · cancel_requested · succeeded · failed · cancelled · interrupted · unknown`

## 쓰는 법
```
$job = [self:script]{op: "run", id: "나레이션생성", args: {lecture_id: "x"}, background: true}
$r = [self:task]{op: "wait", ref: $job.task_ref, timeout: 120}       # 끝나면 $r.result, 초과면 timed_out(실패 아님)
$r.result                                                            # 다음 낱말에 값으로 잇는다
```
```
$a = [others:delegate]{agent_id: "조사", message: "…"}               # 접수증(kind: delegation)
$b = [engines:newspaper]{}                                          # 접수증(kind: newspaper)
$ra = [self:task]{op: "wait", ref: $a.task_ref, timeout: 240}; $rb = [self:task]{op: "wait", ref: $b.task_ref, timeout: 120}
return {report: $ra.result, paper: $rb.result}                       # 둘을 기다려 합친다
```
- `status` 는 즉시 한 번 읽는다. `wait` 는 유한(기본 60초·상한 240초) — 더 긴 작업은 같은 ref 로 다시 `wait`.
- `cancel` 은 확인된 사실만 말한다(`cancel_requested` ≠ `cancelled`). 미지원 종류(위임·script·렌더)는 현재 상태와 함께 거절된다.
- `unknown` 은 "이 몸이 모르는 작업"(유실·재기동·이미 회수됨·잠든 패키지)이지 실패가 아니다 — 새 작업을 다시 시작할지는 작업의 성격으로 판단.
- 같은 명령을 **다시 보내지 말 것** — 접수증이 있으면 그 ref 로 기다린다(이중 실행 방지). 목표(`self:goal`)는 다른 수명이라 이 낱말로 읽지 않는다.

## 새 긴 작업을 만들 때
- 시작 낱말은 `task_receipts.receipt(kind, task_id, state=..., ...)` 를 돌려준다(옛 키는 호환으로 함께 실어도 됨).
- 어댑터 `task_status(ref) -> task_receipts.view(...)` 를 그 패키지 모듈에 두고, `ibl_actions.yaml` 최상위 `task_kinds: {kind: "모듈:함수"}` 로 선언한다.
  취소를 지원하면 `<함수>_cancel`. 상태 번역은 **한 벌 어휘**로만(밖의 값은 등록부가 unknown 으로 거절한다).
