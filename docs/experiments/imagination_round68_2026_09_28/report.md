# 상상 훈련 68회차 결과보고서 (2026-09-28) — 고친 프로그램의 재실행(reuse·resume)과 관측 필드 경고

훈련 턴 · **무수정**(가이드 §4-3: 훈련 턴은 라이브 코어를 고치지 않는다). 사용자 요청 "상상훈련을 해서 에러를 찾아줘".

## 축 선정

- 축 = **09-26~27 증분 실행 개정**(`e284f811` reuse·$ref·관측 경고, `81b0d410` 효과 미상 어휘의 재사용 자격, `5237aefb` 부분 재사용). 56~67회차 누구도 밟지 않은 밭이다. 교재가 이제 "스파이크 → 함수 하나 수리 → `reuse`로 재실행"을 가르치므로, 그 루프를 사용자 업무로 돌려 본 것이다.
- 축 선정 관문 질문("기계로 열거 가능한가"): 재사용 자격·장벽 규칙은 시험으로 열거돼 있다(`test_ibl_v2_incremental_2026_09_26.py`). 기계가 못 세는 것은 **업무 루프 안에서 재사용이 무엇을 뜻하게 되는가** — 읽고 덧붙여 쓰는 원장, 작성 시각, 복구된 실패 뒤의 실행 상태 — 이고, 이번 회차의 발견은 전부 거기서 나왔다.
- 도메인 접지: 가계부 원장 덧붙이기·강의 출석 파일·가족신문 원고·부동산 메모·주간 보고서 작성 시각·실제 `projects/` 폴더·몸의 원장(`world_pulse.db`·`ibl_usage.db`).
- 24과제(평소 8~12의 2배 — 재사용은 한 과제가 실행 2~3회라 과제당 검사가 두껍다). 발신·예약 2건은 check만.

## 지표 스냅샷 (훈련 전)

행동 미조합 140/168 · 파이프 길이 중앙값 3 · 문형 4(시간·발신 조합 0) — 67회차와 같다. 원본: [metrics.json](metrics.json). 지표는 몸의 현황이며 훈련 실측은 증류에 안 담긴다(§6).

## 과제 표

원문·판정식: [probe.py](probe.py) · 응답 전량: [before.json](before.json). 모든 요청 `edition:2`·`project_id:"컨텐츠"`·`origin:"training"`. 스크래치 = `outputs/IT68_*`(종료 시 삭제).
**24과제 중 11통과 · 13실패**(결함 9 · 마찰 4).

| # | 상상 의도 | 결과 | 분류 |
| --- | --- | --- | --- |
| T01 | 강의 자료 폴더 목록을 읽고 요약 문구만 고쳐 재실행 | reused 1, `폴더 29개` | 깨끗 |
| T02 | 원고 2편 읽기 → 1편 앞에 추가·문장부호 수정 재실행 | reused 2, 새 1편만 읽음, 순서 유지 | 깨끗 |
| T03 | 메모를 새로 쓴 뒤 읽기 (reuse) | 새 내용 `C`, reused 0 | 깨끗 |
| T04 | 기록 함수(쓰기) 호출 뒤 읽기 | 새 내용, reused 0 | 깨끗 |
| T05 | 쓰기 & 읽기 병렬 | reused 0 | 깨끗 |
| T06 | 실행 안 된 조건 가지의 쓰기 | reused 1 (장벽 아님) | 깨끗 |
| T07 | 월 가계부 파일이 없으면 `??` 기본 문구 | success **true** · run_status **interrupted** | 결함 B68-1 |
| T08 | 출석 파일 실패를 try/catch로 안내 | success **true** · run_status **interrupted** | 결함 B68-1 |
| T09 | T07 실행을 `/ibl/recover`로 조회 | `status:interrupted`·`resumable:true`·ended_at 있음·reason null | 결함 B68-1 |
| T10 | 없는 원고로 실패 → 파일 만든 뒤 고친 프로그램 reuse | 성공 읽기만 재사용, 실패는 새로 읽음 | 깨끗 |
| T11 | 고친 코드에 `resume`을 실음 | `RESUME_CHANGED` + **"구문 경계를 수정"** 안내 | 결함 B68-2 |
| T12 | 다른 프로젝트에서 reuse | `REUSE_NOT_FOUND` + **"구문 경계를 수정"** | 결함 B68-2 |
| T13 | resume·reuse 동시 | `REUSE_ARGUMENT` + **"구문 경계를 수정"** | 결함 B68-2 |
| T14 | check에 없는 핸들 reuse | `valid`·경고 0 (핸들 미검사) | 마찰 F68-2 |
| T15 | 보고서 "작성 시각" 줄만 고쳐 61초 뒤 재실행 | **61초 전 시각** 그대로 (reused 1) | 결함 B68-4 |
| T16 | 가계부 원장에 한 줄 덧붙이기 → 형식만 고쳐 reuse 재실행 | **1차가 덧붙인 줄 소실**, 경고 0 | 결함 B68-3 ★ |
| T17 | 폴더 이름 오타 — 직접·each·함수 | 셋 다 `UNOBSERVED_FIELD` | 깨끗 |
| T18 | 같은 오타 — filter 콜백·sort by·select columns·take 뒤 each | **넷 다 경고 0** | 마찰 F68-1 |
| T19 | 원장 최근 3건만 (`sense:sqlite` `limit:3`) | **`PARTIAL_SOURCE` 실패** | 결함 B68-5 |
| T20 | 원장 결과를 `$q[0]`으로 인덱싱 | 안내문이 **".items를 붙이지 말라"**(정답은 `.items`) | 마찰 F68-3 |
| T21 | 실행기억 FTS 표 한 행 보기 | **`bytes is not JSON serializable`** 통째 실패 | 결함 B68-6 |
| T22 | 재사용한 실행을 다시 reuse (사슬) | reused 1 | 깨끗 |
| T23 | 결석 안내 메일 (check만) | `incomplete`, issues 0 | 검수만 |
| T24 | 매일 아침 지출 요약 예약 (check만) | `incomplete`, issues 0 | 검수만 |

재사용 핵심(키·장벽·사슬·실패 제외·값 충실도)은 튼튼했다: 쓰기 장벽은 함수·병렬·each 안에서도 섰고, 목록·CSV 읽기의 재사용 값은 새로 읽은 `value_wire`와 바이트 단위로 같았다. 키는 보수적이다(`1.5`↔`1.50`·`3/2`, `2`↔`2.0`, 상대↔절대 경로는 재사용 안 함 — 새로 읽을 뿐이라 결함 아님).

## 갭의 원장

### B68-3 ★최우선 — 원 실행이 **스스로 바꾼 상태 이전의 읽기**를 재사용해 앞 실행의 쓰기가 **조용히 소실**

- **요약**: 장벽 규칙("상태 변경 가능 효과 뒤의 읽기는 과거 영수증을 쓰지 않는다")은 *현재* 실행에만 걸린다. 원 실행이 읽기 **뒤에** 같은 파일을 썼다는 사실은 저널에 있는데도(같은 run의 쓰기 영수증), 그 읽기 영수증이 재사용 후보가 된다. 읽고→고쳐→쓰는 원장 루프를 고쳐 재실행하면 1차의 쓰기가 덮인다. 1차 실행 봉투는 `continuation.reuse_args`로 재사용을 **권한다**.
- **최소 재현**: 파일 `L` = `"09-01 식비 12000\n"` 에서
  `$old=[self:read]{path:L}; $new=$old.text+"09-02 교통 3000\n"; [self:write]{path:L,content:$new}; $chk=[self:read]{path:L}; return $chk.text` → 1차.
  덧붙이는 줄만 `09-03 식비 8000`으로 고치고 `reuse:{run_id:1차}`로 재실행.
- **실측**: 2차 `reused_calls:1`, 파일 = `"09-01 식비 12000\n09-03 식비 8000\n"` — `09-02 교통 3000` 소실. 봉투 `warnings`·`reuse`에 신호 0. 1차 `continuation.reuse_args` 있음.
- **제안(수리성)**: 원 실행에서 **상태 변경 가능 효과보다 앞에 기록된 읽기 영수증**은 재사용 후보에서 뺀다(현재 실행의 장벽과 같은 규칙을 원 실행의 영수증 순서에도 — 저널 `calls` rowid가 이미 순서를 가진다). 원 실행이 쓰기를 했다면 `continuation`에 그 사실과 재사용 가능 읽기 수를 정직하게 적는다. 가드: 원 실행 {읽기→쓰기, 쓰기→읽기, 함수/each/병렬 안 쓰기} × 재실행.
  - 부수 판정 없음: "고친 프로그램을 원래 상태에서 다시 하고 싶다"는 의도는 사용자가 파일을 되돌린 뒤 reuse 없이 실행하면 된다 — 재사용이 사용자 모르게 세계를 되감을 이유는 없다.

### B68-1 복구된 실패 뒤 **성공으로 끝난 실행이 `interrupted`로 기록** — 정리 대상에서 영구 제외

- **요약**: `Journal.complete`(`backend/ibl/ibl_run_journal.py:154`)가 `success and source_complete`일 때만 `completed`를 준다. `??`·try/catch로 실패를 복구해 **정상 반환한** 실행은 `source_complete:false`라서 `interrupted`가 된다. 두 축(실행이 끝났는가 / 원천이 완전한가)이 한 칸에 겹쳤다.
- **최소 재현**: `$n=[self:read]{path:"없는 파일"} ?? {text:"기본"}; return $n.text`
- **실측**: 봉투 `success:true`·`run_status:"interrupted"`. `/ibl/recover` → `status:"interrupted"`·`resumable:true`·`ended_at` 있음·`reason:null`. try/catch(T08)도 같다(단 `assert` 실패 복구는 `completed` — 도구 실패만 해당).
- **실물 규모**: `data/ibl_runs` 5,328건 중 `interrupted` 1,036건(51.6MB), 그중 **reason 없는(= 성공 반환) 183건**. 정리(`cleanup_runs`)는 `completed`만 지우므로 이 183건과 앞으로의 모든 폴백 실행은 30일이 지나도 남는다(512MiB 상한은 신고만).
- **영향**: ①보존 정책 우회(무한 누적) ②연결이 끊긴 클라이언트가 recover로 "중단"을 보고 재개를 시도 ③문서 계약(`ibl.md` "완료한 기록만 30일 보존 후 정리") 위반.
- **제안(수리성)**: 실행 상태는 실행 종결로 판정(`success`면 `completed`), 원천 불완전은 별도 필드(`source_complete`)로 저널·recover에 싣는다. 기존 183건은 lifecycle 갱신 이주(reason null + ended_at 있음 + 모든 calls 영수증 있음 → completed). 가드: `??`·try/catch·each collect·truncated 원천 × 상태·정리 대상.

### B68-2 실행 전 프로토콜·권한 거절에 **"표시된 구문 경계를 수정"** 안내 — 틀린 첫 처방

- **요약**: `syntax_report`(`backend/ibl/ibl_v2_analysis.py:89`)가 `HINTS.get(code, HINTS['SYNTAX'])`라, 힌트 표에 없는 코드는 전부 구문 오류 처방을 받는다. `RESUME_CHANGED`·`RESUME_NOT_FOUND`·`REUSE_NOT_FOUND`·`REUSE_ARGUMENT` 모두 해당. `kind`는 `protocol`/`permission`인데 처방은 "코드를 고쳐라".
- **최소 재현**: 실행 후 코드 한 글자를 바꿔 `resume:{run_id}`로 재요청.
- **실측**: `{"code":"RESUME_CHANGED","kind":"protocol","hint":"표시된 구문 경계를 수정한 뒤 프로그램 전체를 다시 검사하세요."}`. 이 상황의 올바른 처방은 "고친 프로그램은 `reuse`, 같은 프로그램만 `resume`"(메시지에도 없음).
- **범위(census)**: backend가 던지는 Fault 코드 81종 중 힌트 표에 있는 것은 10종. 힌트 없는 71종 가운데 실행 전 경로(`ibl_v2_entry` → `syntax_report`)로 나가는 것은 전부 구문 처방을 받는다 — 실측 4종 외에 `EDITION_ARGUMENT`·`JOURNAL_IO`·`RESUME_BUSY`·`REUSE_BUSY` 등이 같은 자리. ★"거절 문구의 첫 처방" 부류(pitfall grounded-judge…)의 재발.
- **제안(수리성)**: 폴백을 kind별로(compile만 SYNTAX, protocol/permission은 각자 또는 중립 문구) + RESUME_CHANGED·REUSE_NOT_FOUND·REUSE_ARGUMENT·RESUME_NOT_FOUND 전용 힌트. 관문: 실행 전 경로로 나갈 수 있는 모든 Fault 코드가 kind에 맞는 힌트를 갖는지 AST census(새 코드 탄생 차단).

### B68-4 **시계 읽기(`self:time`)가 재사용**돼 옛 시각을 "지금"으로 반환

- **요약**: `self:time`은 계약상 `effects:[read_external]`·`nondeterministic:true`라 재사용 후보다. 보고서의 "작성 시각"을 고쳐 재실행하면 이전 실행 시각이 들어간다. `self:list`의 재사용은 "같은 세계를 다시 보지 않겠다"는 뜻이 되지만, 시계는 *실행하는 순간* 자체가 값이라 재사용하면 값의 의미가 틀린다.
- **최소 재현**: `return [self:time]{}` → 61초 뒤 `$t=[self:time]{}; return f"작성: ${$t}"` + reuse.
- **실측**: 1차 `14:49:42`, 61초 뒤 재실행 `작성: 2026-09-28 14:49:42`, `reused_calls:1`.
- **제안(수리성)**: 실행 순간을 값으로 삼는 계약(시계·난수류)을 재사용 자격에서 뺀다 — 계약 데이터 한 칸(예: `per_run: true`)이면 되고 어휘·문법 증가 0. 가드: 시각 읽기 × reuse/resume(resume은 같은 실행의 계속이므로 기록 시각 복원이 맞다 — 둘을 가른다).

### B68-5 `sense:sqlite`의 **작성자 `limit`이 절단으로 판정돼 `PARTIAL_SOURCE` 실패** — 같은 속 세 번째

- **요약**: `limit:3`은 작성자가 정한 표본인데 `sqlite_ops`가 `truncated:true`만 남기고 `scope:"selection"`을 안 적어 어댑터(`ibl_v2_adapters.py:166`)가 불완전 원천으로 거절한다. SQL 안의 `LIMIT 3`은 통과 — 같은 뜻의 두 표기가 다르게 판정된다.
- **최소 재현**: `$r=[sense:sqlite]{path:"~workspace/data/world_pulse.db", query:"select source from action_health", limit:3}; return len($r.items)`
- **실측**: `PARTIAL_SOURCE` "도구의 원천 결과가 불완전합니다", `truncations:[{scope:"unknown"}]`.
- **★밭 이관 규약 발동**: 4079 한메일 → 4083 원장 select(`918fc1ee`, ledger_ops만 scope 표기) → 이번 sqlite. 같은 속의 **세 번째** 발견이다. `truncated`를 내는 도구 파일 39개 중 `scope:"selection"`을 아는 것은 9개. 처방 = **도구 `limit`류 인자의 선택/절단 census → 일괄 표기 → 탄생 차단 관문**(작성자 인자가 절단 상한과 같을 때는 selection, 기본값에 걸린 것만 unknown). 개별 수리 요청이 아니다.

### B68-6 `sense:sqlite`가 BLOB 열 하나에 **질의 전체 실패**

- **요약**: `select x'00ff'` 또는 BLOB 열을 가진 표의 `select *` → `sqlite_op 오류: Object of type bytes is not JSON serializable`. 정직한 실패지만 한 열 때문에 전 행을 못 본다. 몸의 원장 중 `ibl_usage.db`의 FTS·벡터 표 4개가 BLOB.
- **최소 재현**: `[sense:sqlite]{path:"~workspace/data/world_pulse.db", query:"select 1 as a, x'00ff' as d"}`
- **제안(수리성)**: BLOB 값을 크기·앞부분 hex를 담은 표기(`{"$blob":{bytes:N, head:"00ff"}}` 류)로 내보내고 `markers`에 blob 열 신고. 가드: BLOB·NULL·정수·실수·텍스트 혼합 행.

### F68-1 관측 필드 경고가 **콜백·열 이름 인자·통과 변환자에서 끊김**

- 직접 접근·each `$it`·함수 인자는 `UNOBSERVED_FIELD`를 낸다(T17). 같은 오타가 `[table:filter]{where:($r)=>$r.nmae…}`·`[table:sort]{by:"nmae"}`·`[table:select]{columns:["nmae"]}`·`>> [table:take]{n:1} >> [table:each]{$it.nmae}`에서는 **경고 0**(check `valid`/`incomplete`). 실행하면 filter·select는 `MISSING_FIELD`로 죽는다 — check가 잡을 수 있던 것을 실행이 잡는다.
- 뿌리: 관측 표식(`Type(observed=True)`)이 filter/take/sort 통과 뒤 원소 타입에 보존되지 않고, 열 이름 문자열 인자는 관측 열과 대조하지 않는다.
- 제안(수리성, census): 행을 바꾸지 않는 변환자(filter·take·sort·dedup)는 원소 관측 타입을 보존, `by`/`columns`/`where` 콜백 인자는 관측 열과 대조. 표 변환자 전수 × {콜백 필드, 열 이름 인자} 격자로 관문.

### F68-2 `check:true`가 `reuse`/`resume` 핸들을 보지 않는다

- 없는 run_id(`'0'*32`)를 실어도 `valid`·경고 0. 실행하면 `REUSE_NOT_FOUND`. 핸들 존재·문맥 일치는 효과 없는 조회(`inspect_run`/`reusable_receipts` 읽기 전용)라 check가 볼 수 있다. 수리성: check가 핸들을 조회해 경고(또는 실행과 같은 거절)로 신고.

### F68-3 `FIELD_TYPE` 안내가 호환 봉투 어휘에서 **정답의 반대를 처방**

- `$q=[sense:sqlite]{…}; return $q[0].n` → 힌트 첫 문장 "List 반환은 값 자체가 목록입니다. **.items나 .value를 붙이지 말고**…". sqlite는 `legacy-envelope`(value_path `""`)라 정답이 `$q.items[0].n`이다. `returns: items`이면서 네이티브 계약이 없는 어휘 **71개**(168개 중)가 같은 봉투를 돌려준다.
- 수리성: 힌트를 실제 타입으로 분기(Record인데 `items` 필드가 있으면 "`.items`로 행 목록에 접근"). B68-2와 같은 "안내문이 실제 계약을 모른다" 부류 — 한 수리 턴에서 같이.

## 시드 후보 (실행 검증 통과만 — 자동 등록 안 함)

T01(목록 읽기 → 요약만 고쳐 reuse) · T02(each 원소별 reuse: 추가된 원소만 새로 읽음) · T10(실패 원고를 고친 뒤 reuse — 성공 읽기만 재사용). 셋 다 교재 6단계("함수 하나 수리 → reuse 재실행")의 실측 용례. **B68-3 수리 전에는 읽기→쓰기 원장 루프를 reuse 용례로 심지 말 것.**

## 판정 요청 (언어 개정·파괴적 변경 2종만)

없음. 여섯 결함과 세 마찰은 전부 수리성이다 — 재사용 자격(B68-3·B68-4)은 09-26 개정이 이미 정한 원칙("쓰기 뒤 읽기는 재사용 안 함", "최신 상태가 필요하면 새로 조회")을 원 실행 순서와 시계 계약까지 일관되게 적용하는 것이지 새 의미가 아니다.

수리 턴 순서 권고: ①B68-3(데이터 소실) ②B68-1(+183건 이주) ③B68-2·F68-3(안내문 census+관문) ④B68-5는 **census 이관**(개별 수리 금지 — 세 번째 발견) ⑤B68-4·B68-6·F68-1·F68-2.

## 위생

- 회차 창(14:34~14:52) `action_health`: 제 요청분은 `training|app` 135행. 같은 창의 `test` 595행·`usage` 5행(`here` 4·`write` 1)은 source가 다르다 — 같은 시각 다른 세션이 pytest를 돌리고 있었다(작업 트리의 미커밋 변경도 그 세션 것, 손대지 않음).
- 스크래치: `outputs/IT68_{memo,a,b,c,new,ledger}.txt`·탐색용 `IT68_scores.csv` 전부 삭제, 잔존 0 확인. 사용자 데이터 무변경(`projects/` 목록·원장 읽기만). 실행 저널에 훈련 실행 기록이 남는다(30일 보존 정책 대상 — 단 B68-1 때문에 폴백 탐침 3건은 정리되지 않는다).
- 발신·예약·알림 실측 0. 라이브 코어 편집 0. 해마 시딩 0. 회귀 배터리는 수정이 없어 돌리지 않았다.

## 집행 완료

2026-09-28 정본 main에서 수리. 결함 6종·마찰 3종 모두 해결했고 같은 탐침이 **24/24 통과**했다([after.json](after.json)).

- B68-3: 영수증별 재사용 자격·상태 변경 가능성을 SQLite에 기록한다. 원 실행의 쓰기 전/동시 읽기는 제외하고 안전한 이후 읽기는 유지한다. continuation에 state_change_possible/read_calls를 신고하며 후보 0건이면 reuse_args를 권하지 않는다. 순서 증거 없는 옛 저널은 후보에서 제외한다. 가계부 A→AB→ABC 보존과 병렬 겹침 양방향을 검사했다.
- B68-1: 성공 반환은 completed, source_complete는 독립 필드다. reason 없음+ended 있음+모든 호출 영수증 있음+blocked 없음 조건의 **191건**을 SQLite backup 후 이주했다. 보고서 시점 183건에서 수리 시점 191건으로 증가했다. 백업은 data/_backups/2026-09-28_round68_completed_journals/이며 원천 완전성은 false로 보존했다. 상세 [migration.json](migration.json).
- B68-2/F68-3: 종류별 중립 안내와 핸들 오류 전용 처방, 실제 타입에 따른 필드 접근 안내. production Fault 코드 **81종** 및 미지의 향후 코드까지 SYNTAX 처방으로 떨어지지 않는 검사 추가. 기존 무조건 목록 안내는 은퇴 등록부에 기록했다.
- B68-4: self:time 계약 per_run:true. 새 실행은 현재 시각을 읽고 동일 실행 resume은 원 시각을 복원한다. 라이브 61초 간격 재실행에서 재사용 0건.
- B68-5: [전수 조사](truncation_census.md)로 실제 truncated 생산자 **34파일·59곳**을 분류했다(단순 지역 변수·소비자는 제외하여 훈련 시 grep 39파일과 범위가 다름). SQLite·검색·갤러리·시세 표본·월별 부동산·문서·렌더링·기존 원장/grep/장소 선택을 공통 경계 판정으로 정렬했다. 작성자 요청=실효 상한이고 수량을 채웠을 때만 selection; 기본값·안전캡·미충족·수집 오류는 source를 유지한다. 기존 check_honesty_propagation.py에 생산 위치별 분류·사유 관문 C 추가.
- B68-6: BLOB을 {$blob:{bytes,hex}} **무손실** JSON 값으로 반환하고 markers.blob_columns/blob_encoding을 신고한다. NULL·정수·실수·문자열과 혼합해도 다른 행이 사라지지 않는다.
- F68-1: 어휘의 기존 flow 선언에서 행 관측 타입을 전달한다. filter/take/sort/dedup, select/compute의 콜백·열 이름·투영을 검사하고 관측 밖 이름은 경고로 유지한다. legacy Record 반환은 .items로 이어 간다.
- F68-2: check가 핸들 형태·존재·잠금·문맥과 resume 동일 실행 지문을 읽기 전용 검사한다. 검사 전후 SQLite 바이트가 동일함을 테스트했다.

수리 중 라이브 재기동이 새 요청을 거절한 첫 탐침은 유효한 검증으로 계산하지 않았다. 건강 상태 회복 후 같은 원문 전체를 재실행한 최종 after.json은 24/24다. 회원 경로 재감사에서는 변경이 결과 표현·범위 메타데이터에 한정됨을 확인했고 경로 해소·읽기 전용 authorizer·공개 URL 접근 제한·사적 문서 경로는 유지했다. 그 소스 지문과 파생 매니페스트를 재생성하고 회원 관련 133개 검사도 통과했다.

검증 결과는 repair_metrics.json과 아래 최종 회귀 기록을 따른다. 발신·예약은 끝까지 check만 수행했다. 스크래치는 탐침 종료 시 삭제했다.

전체 회귀에서 관측 전파가 희소 행의 누락 필드까지 정적 오류로 승격하는 회귀를 발견했다. flow의 필드 존재 진단은 관측 표식이 있는 행의 경고에 한정하여 기존 정렬·flatten의 런타임 오류 및 catch/?? 복구를 보존했다. SQLite 계약 설명에 연결된 기존 해마 용례 10건도 읽고 현재 범위 선택·BLOB 표기와 호환됨을 확인한 뒤 해당 액션만 재검토 원장에 반영했다.

최종 회귀: 전체 backend 초회 **7,271 통과·21 실패·1 스킵**. 실패 원인은 동시성 timeout 선언, SQLite 용례 재검토 원장, 희소 행 진단 회귀, 수정 중 회원 경로 지문 차이였다. 모두 수정 후 실패 파일 전체+새 수리 배터리 **168/168 통과**. 초회와 최종 재검사를 합치면 서로 다른 **7,298건 통과·1건 스킵**, 미해결 실패 0건이다. 별도 관련 회귀 163건, 회원 관련 133건, 정합성·값 의미·경로·정직 표지·동시성·파일 크기·Windows 이식성 관문도 통과했다.
