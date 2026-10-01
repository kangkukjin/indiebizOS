# 상상훈련 70~75회차 회귀 재검 결과 (2026-09-29 22:10~22:40 KST, 읽기 전용 감사)

라이브 백엔드 healthy·state.json `ACTIVE` 상태에서 진행했다. 저장소 파일은 편집하지 않았다.
- 파일을 쓰는 탐침은 경로를 `scratchpad/regress/tmp/r7075/files/`로 바꿔 실행했다.
- 저장 함수(71)는 격리 프로세스에서 돌렸다. `workflow_store._get_workflows_path`를 스크래치 `tmp/r7075/wf`로 바꿨다. 라이브 `data/workflows`는 전후 모두 2개 파일로 변하지 않았다.
- 재무 절단·주체 탐침(72)은 격리 프로세스에서 돌렸다. `INDIEBIZ_USERDATA`는 스크래치로 돌렸다. `finance_records.db`의 mtime은 변하지 않았다.
- since 검침(75)은 격리 프로세스에서 돌렸다. `sqlite3.connect`가 `table_since.db`를 열면 스크래치 DB로 가도록 바꿨다. 라이브 `since_seen` 행 수는 전후 25로 같다.
- 발신·예약·트리거·이벤트 등록·폴더 메모·용량 스캔은 check만 하거나 재검하지 않았다.
- 원장(`self:ledger`) 경로는 "indiebizOS 저장소 안이어야" 해서 스크래치로 바꿀 수 없었다. 해당 과제는 원장 대신 리터럴 예산표로 바꿔 조합만 재검했다.

## 1. 회차별 요약

| 회차 | 재검 표현 | 정상 | 문법변화(정상) | 여전히 오류 | 검수만(부작용) |
|---|---|---|---|---|---|
| 70 (지역 함수·계약·병렬 쓰기) | 21 | 20 | 0 | 0 | 1 (T24 알림 함수 check) |
| 71 (저장 함수 수명주기, 격리 저장소) | 23 | 22 | 1 (op:"get" → "detail") | 0 | 0 (저장·삭제는 격리 스크래치 저장소에서 실행) |
| 72 (가계부·원장) | 21 | 17 | 1 (T20 예약 do 파이프 충돌 = 옳은 거절) | 1 (F72-1 기존 행 잔여) | 4 (T08·T11·T12·T20 check) |
| 73 (문서·표·차트) | 27 | 23 | 4 (T24 차트 낱말 series/hole/trendline/ma → 정직 거절+최근접 제안) | 0 (파이프→copy 건은 74에 기록) | 2 (T20 파이프형·B73-1 발신 소비자 check) |
| 74 (파일·저장소) | 24 | 22 | 0 | 1 (T24/B73-1 `>> [self:copy]` 실행 실패) | 2 (B74-4 set check, 스캔 불가) |
| 75 (일정·검침·발신) | 58 (check 30·격리 판정 16·격리 since 5·읽기 7) | 57 | 0 | 1 (F75-2 같은 실패 매시 알림) | 30 (예약·트리거·발신 check 전부) |

## 2. 여전히 오류

### R74-T24 (B73-1 재확인분) — `… >> [self:copy]{dest}`: 검사는 통과하고 실행은 전부 실패
- 원래 증상: 판본 2에서 `PIPE_COLLISION`으로 거절됐다. 수리(B73-1)로 `pipe_in`에서 파이프 자리가 생겼다. 74회차 탐침은 **check만** 판정했다.
- 이번에 돌린 문장(스크래치 폴더):
  ```
  [self:list]{path:"<scratch>/list", pattern:"*.pdf"} >> [self:copy]{dest:"<scratch>/bak2/a"}
  ```
  같은 결과가 난 변형:
  - `$l=[self:list]{…}; $l >> [self:copy]{…}`
  - `{items:$l} >> [self:copy]{…}`
  - `[self:list]{…} >> [table:take]{n:2} >> [self:copy]{…}`
- validate(check): `incomplete`, issues 0이다. `describe self:copy`는 `pipe_input:"items"`, 타입은 `items:"Unknown"`이다.
- execute: `success:false`, 파일 0개. 오류 원문:
  > "copy_path: `items` 에는 타입 선언이 없는 자리인데 1개짜리 목록이 왔습니다. 목록의 항목마다 실행하려면 [table:each]{do: "…$it.필드…"} 를 쓰세요 ($items 통짜 바인딩은 array 로 선언된 param 에만 들어갑니다)."
- 분류: **새 형태의 오류**(검사-실행 불일치)다.
  - 선언 target_description은 "src를 생략하고 앞 액션 결과를 >> 로 넘기면 그 items의 파일 전부를 dest 폴더로 복사"라고 가르친다. 판본 2 check도 통과시킨다.
  - 그런데 실행 경로의 옛 바인딩(`items` 타입 선언 없음)이 거절한다.
  - 같은 수리로 파이프 자리가 생긴 `table:document`·`self:sheet append`·`table:chart`·`table:spreadsheet`는 실행까지 된다.
- 비고: `$f >> [table:each]{ [self:copy]{src:$it.path, dest:…} }` 우회는 성공한다. 74회차 보고서의 T24 판정식이 check만 봐서 수리 뒤에도 드러나지 않았다.

### R75-F75-2 — 같은 영구 실패가 여전히 **매시** 경고 알림
- 원래 증상: 트리거 `AI시대_보고서출처_뉴스갱신`이 새 일 없이 매시 실패했다. `스케줄 실행 실패 — 홍보/` 알림이 11일에 273통 나갔다.
- 수리 주장: 같은 실패는 하루 1통으로 요약한다(75회차 후속 16:09 `1de0df53`: `_failure_signature`가 실행 id·시각·소요 시간을 지운 서명으로 비교). 뿌리인 스크립트 표기 판독도 수리했다고 한다.
- 이번에 확인한 것(읽기만):
  ```
  $t = [self:trigger]{op:"list"}
  return $t.items >> [table:filter]{where:($r)=> $r.enabled == true && $r.last_success == false} >> [table:select]{columns:["name","run_count","last_run"]}
  ```
  - 결과: `AI시대_보고서출처_뉴스갱신` run_count 326, last_run 22:24:42. 이력 최근 5건이 전부 `success:false`다.
  - `notify_log`(ro)의 09-29 `스케줄 실행 실패 — 홍보/`는 24통이고, **16:09 수리 커밋 뒤에도 16:21·17:22·18:22·19:22·20:23·21:23·22:24 매시** 나갔다. 백엔드 재기동 22:14 이후인 22:24에도 나갔다.
- 뿌리(읽기 판독): 캘린더 이벤트 `evt_4664f140069b`에 저장된 `failure_notice.error` 서명에 `"prepare": {"time": 1790688273.0185301, …}`이 남아 있다.
  - 이 값은 매 실행 바뀌는 epoch 실수다. `_failure_signature`의 정규식(uuid·16진 id·ISO 시각·duration_ms·ms/초)이 이 값을 지우지 않는다.
  - 그래서 매번 `repeated:1`, 곧 "다른 실패"로 판정되고 즉시 알림이 나간다.
- 트리거 자체의 실패 사유도 바뀌었을 뿐 계속된다: `candidates 102 · done 99 · pending_count 3`, 3건 모두 `"원문 제목 확인 실패"`(nytimes 등 원문 제목 확인)다. 이 사유는 외부 원천 성격이 섞였다.
- 분류: **원 결함 재현**(알림 억제 실패). 트리거 실패 사유는 **외부 원천** 가능성이 있다.
- 비고: 사용자 작업의 자동 비활성화는 하지 않는 설계다. 알림함을 계속 채운다.

### R72-F72-1 — 가맹점 키 잔여물이 원장에 남아 같은 가게가 쪼개진다(기존 행)
- 원래 증상: 하나카드 `/ ( ,2*9*) / / 이용금액`, 청주페이 `시 인센티브 (2) 총 보유` 잔여물이 가맹점 키로 들어가 groupby 키가 오염됐다.
- 이번에 돌린 문장(읽기):
  ```
  $t = [self:finance]{op:"query", query_type:"지출", days:120}
  return $t.items >> [table:filter]{where:($r)=>contains($r.counterparty,"이용금액") || contains($r.counterparty,"총 보유") || contains($r.counterparty,"인센티브") || contains($r.counterparty,"]") || $r.counterparty == ""} >> [table:select]{columns:["record_id","date","counterparty","amount","source"]}
  ```
- execute: 10행이 나왔다.
  - `더홀릭영통점 / ( ,2*9*) / / 이용금액`×2, `모시울 / ( ,2*9*) / / 이용금액`×2, `아이파킹주식회사 / …`, `LG전자구독료 / …`, `주식회사탄탄코어 / …`, `점핑배틀(수원영통) / …`
  - `LG U+ 통신요금 자동] 자동납부 요금 정상 안내`
  - `매출 안내] 27일 / - / 구글플레이_TOSS`(-159,000, 취소)
  - `[table:chart]{…, data:$t.items, x:"counterparty", y:"amount"}` 그림의 x 라벨에 이 잔여물이 그대로 찍힌다(T04 재검 그림으로 확인).
- 분류: **원 결함 재현(기존 데이터 잔여)**. 파서(`finance_sync._merchant_from`·`_clean_merchant`)는 수리됐고, 새 알림 경로는 재현하지 못했다. 10행 모두 `created_at` 09-18·09-28, 곧 수리(09-29 01:06) 이전 행이다.
- 비고: 수리 문서(`IMAGINATION_72_76_REPAIRS.md` "기존 원장 보정과 남은 제약")가 "원문 메모 또는 명백한 인센티브 꼬리 문구를 근거로 27행만 보정"이라고 한계를 밝혔다. 이 10행은 note에 원문이 없다. 보정 여부는 사용자 판단 몫이다(재무 원장 쓰기라 이번 감사에서는 손대지 않았다).

## 3. 문법 변화·옳은 거절로 정상 처리한 항목

- R71 F71-3: `[self:workflow]{op:"get", name:…}` → 이제 `ARGUMENT_CONTRACT: op 허용 값 [list, detail, save, delete, run]`이다. 현재 형태 `op:"detail"`은 정상이다. `retired_contracts.yaml`의 `workflow-get-op`에 은퇴가 기록돼 있다.
- R72 T20: `[self:manage_events]{…, do:"[self:finance]{…} >> [self:notify_user]{message:\"지출 요약\"}"}` → 등록 시점 `PIPE_COLLISION`은 옳은 거절이다. 교정형 `$s = …; [self:notify_user]{message: $s.text}`는 check `incomplete`, 이슈 0이다.
- R72 T25: 코퍼스 4787의 `desc:true`는 더 이상 거절되지 않는다. `groupby` 결과 Record→List는 `TYPE`으로 거절하되 ".items로 꺼내 전달하세요"라고 안내한다(정상).
- R73 T24/F73-2: `series`·`hole`·`trendline`·`ma` → `UNKNOWN_ARGUMENT`와 함께 "비슷한 인자: series_names / show_trendline …"을 안내한다. 현재 이름은 `series_names`·`donut`·`show_trendline`·`ma_periods`다. 교재(visualization ibl_actions.yaml)도 `show_trendline`으로 교정돼 있다.
- R75 T04/T22 guide pipe: `… >> [self:notify_user]{message:…}` → `PIPE_COLLISION`은 옳은 거절이다(명시 message 제거 또는 `$x = …`를 안내). `channel:"gmail"` → `UNKNOWN_ARGUMENT`("비슷한 인자: channel_type")이다. 가이드 trigger.md는 `channel_type:'email'` 형태로 교정돼 있다.
- R75 T08/T12/T13: cron `L`·`28-31`·`30 */2`·`* * * * *`, repeat `매일`·`weekday`, `2026-02-29`/`2027-02-29`, weekly의 weekdays 누락, monthly의 day 누락 → 판본 2 check가 모두 정직하게 거절한다(정상). `0 21 31 * *`는 짧은 달을 건너뛴다. 수리 문서가 정책으로 명시한 동작이다.

## 4. 재검 못 한 항목과 이유

- **R75 B75-2**(T14 지연 예약 취소 후 발화, T15 틱·타이머 이중 발화): 실제 예약 발화가 필요한 부작용이라 실행하지 않았다. check `incomplete`만 확인했다.
- **R75 T16·T17**(스크래치 트리거·이벤트 등록/수정/삭제): 등록물 생성 금지. 원래도 깨끗했다.
- **R75 F75-1**: `forage_resurvey_부동산`은 run_count 4인데 이력은 1행이다. 수리(트리거별 보존) 이전에 잘린 과거 이력이라 새로 판정할 수 없다. 전역 이력은 지금 226행(>200)으로 트리거별 보존이 작동하는 것으로 보인다.
- **R74 B74-3**(I6 잠긴 폴더·I7 깨진 링크 스캔, T22 폴더 롤업): `self:storage scan`은 저장소 색인에 볼륨을 등록하는 쓰기라 재검하지 않았다. 기존 스캔 위 summary(`~/Downloads`·저장소 하위)는 "접근 실패 기록 이전 스캔 — 누락 여부를 알 수 없음, 다시 스캔하세요"로 **정직하게 거절**된다(PARTIAL_SOURCE). 폴더 롤업 열은 재스캔 없이 확인할 수 없다.
- **R74 B74-4**(folder_note set 정규화·유령 폴더 거절): 색인 쓰기라 check만 했다(`incomplete`). 실행 판정은 하지 못했다.
- **R72 T15·T22**(ledger upsert/select): 원장 경로가 저장소 안만 허용돼 스크래치로 돌릴 수 없어 건너뛰었다. 원래도 깨끗했고, T16은 리터럴 예산표로 조합만 재검했다(정상). T17(table:judge, LLM 호출)은 갭이 아니라 건너뛰었다. T19는 peek 검침만 했다.
- **R71 T22**(예약 run_workflow check): 원래 검수만이던 항목이라 생략했다.
- **R73 B73-6**: 토큰 경로 재검은 스크래치에 `~workspace` 파일을 만들 수 없어 기존 `outputs/live_ledger.pdf` 읽기와, 없는 파일 경로의 해소 결과로 대신했다. 경로는 `/Users/.../indiebizOS/outputs/…`로 올바르게 펼쳐졌다(정상).
- 참고로 격리 프로세스(71·72·75)는 `handle_request`를 프로세스 안에서 부른다. 실행 저널·증거 스필 같은 시스템 부산물이 `data/` 아래 생겼을 수 있다(라이브 HTTP 탐침과 같은 부류).
