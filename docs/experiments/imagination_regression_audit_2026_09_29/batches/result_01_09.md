# 상상훈련 1~9회차 회귀 재검 결과 (2026-09-29, 읽기 전용)

- 백엔드: 가동 중(/health healthy). 재기동·편집 없음. 모든 실행은 `project_id:"컨텐츠", origin:"training"`.
- 원 문장은 레거시(판본 1) HTTP 경로로 그대로 돌렸고, 실패하면 현재 교재(`12_ibl_only.md`)·어휘(`ibl_nodes.yaml`)로 고쳐 다시 돌렸다.
- 파일 쓰기는 전부 `scratchpad/regress/tmp/r0109/` 로 경로를 바꿨다. 요청·응답 원문은 같은 폴더의 `R<회차>-<ID>.json`.
- 부작용 문장(트리거·스케줄·goal 등록, 워크플로 save, notebook add, notify, channel_send, others:ask, bulletin create, follow add, folder_note set, cctv capture, screen)은 validate와 check만 했다.

## 1. 회차별 요약

| 회차 | 재검 표현 | 정상 | 문법변화(정상) | 여전히 오류 | 검수만(부작용) |
|---|---|---|---|---|---|
| 1 | 13 | 7 | 2 (T8 restaurant lat/lng→x/y, T10 finance query_type) | 0 | 4 (T1·T3·T7·G1-② notebook) + F2·G2 check 정상 |
| 2 | 9 | 3 (P3·N4·N10) | 3 (N1·N6·N9) | 0 | 3 (N3 goal·N4 기본 path·N7 ask) |
| 3 | 16 | 11 | 0 | 0 | 5 (T1·T2 trigger, T3 goal, T4a/b save — B1은 즉석 run으로 실측) |
| 4 | 14 | 9 | 1 (W5 `$items.title`→문자열 칸) | 1 (W9, 경미) | 4 (W1a·W1c·W2·W12) |
| 5 | 16 | 12 | 3 (T5·T13 flatten 불요, T9 ledger→business) | 0 | 1 (F2-op: check가 정직 거절) |
| 6 | 13 | 12 | 0 | 0 | 1 (U3) |
| 7 | 12 | 10 | 1 (V5 discover 은퇴) | 0 | 1 (V3) |
| 8 | 10 | 3 (W7 identity 해소·W8·W9) | 1 (W5 icon 은퇴) | 2 (W1 환경 + W5 파생: 레거시 check 유령 통과) | 5 (W2·W2b·W3·W4·W6) |
| 9 | 12 | 9 | 1 (X6 cctv stats→self:cctv) | 1 (X7, 두 결함) | 2 (X8·X9) |

## 2. 여전히 오류

### R9-X7a: cloudflare_api 교재 예시 경로(선행 `/` 없음)가 깨진 URL을 만든다
- 원 회차: 9회차 X7 "내 클라우드플레어 존"(당시 zones 200 성공).
- 이번 문장:
  ```
  [limbs:cloudflare_api]{endpoint: "zones"}
  ```
- validate: valid, 경고 없음. / execute: `success:false, "10404: No route for that URI"` (status 404).
- 원인(읽기만): `tools/api.py` 가 `f"{CLOUDFLARE_API_BASE}{endpoint}"` 로 이어 붙여 `.../client/v4zones` 가 된다. 그런데 어휘의 target_description 예시가 `'zones/abc/dns_records'`(선행 `/` 없음)라서 **교재대로 쓰면 실패**한다. `endpoint: "/zones"` 이면 200·items 1행.
- 분류: 새 형태의 오류(교재 예시 ↔ 핸들러 계약 불일치, 정규화 없음).

### R9-X7b: cloudflare_api가 `returns: effect` 로 선언돼 `>> [table:take]` 직결이 실행 전 거절된다(실제로는 items를 냄)
- 원 회차: 9회차 관찰②(cloudflare result 목록 items 미방출, F8 부류)의 후속.
- 이번 문장:
  ```
  [limbs:cloudflare_api]{endpoint: "/zones"} >> [table:take]{n: 3} >> [table:select]{columns: ["name"]}
  ```
- validate: typecheck error "[limbs:cloudflare_api] 는 통화를 내지 않는 effect 인데 뒤의 [table:take] 는 변환자…" / execute: `실행 전 통화 검사 거절 — 문장 1 step 2 [pipeline]: … effect … 변환할 items 가 굶습니다.`
- 반증: 단독 실행하면 `items` 1행이 나오고, `$z = [limbs:cloudflare_api]{…}` 에 받은 뒤 `$z >> [table:take] >> [table:select]` 로 이으면 성공한다(name=kukjinkang.uk). 설명문에도 "성공 result 는 items 통화로도 방출 — each·변환자에 물린다"고 적혀 있다. **선언(`ibl_actions.yaml` returns: effect)과 실제 방출·설명이 어긋나** 직결 파이프를 잘못 막고 있다.
- 분류: 새 형태의 오류(선언 계약 불일치).

### R8-W1: `[sense:here]@폰-9f2b` 가 여전히 "위치 null"
- 원 회차: 8회차 W1(라우팅은 완주, 폰 위치서비스 제약으로 정직 실패, "코드 밖").
- 이번 문장:
  ```
  [sense:here]@폰-9f2b
  ```
- validate: valid / execute: `{"success": false, "error": "위치 null", "_forwarded_to": ...}`
- 분류: 원 결함 재현. 외부 원천(폰 환경)으로 보인다. 오류문이 "위치 null" 한 마디뿐이라 원인(권한·위치서비스 꺼짐·GPS 미측정)을 가르지 못한다.
- 비고: 원 보고서도 코드 밖(환경)으로 분류했다.

### R8-W5x: 레거시(판본 1) `check:true` 가 없는 액션을 `ok:true` 로 통과시킨다
- 원 회차: 8회차 W5 `icon`(지금은 은퇴)을 재검하다 드러났다. 6회차 "검수기가 유령 액션을 잡음"의 대칭 구멍이다.
- 이번 문장(판본 1, `/ibl/execute` 에 `check:true`):
  ```
  [engines:icon]{prompt: "고양이"}
  [sense:nosuchaction]{query: "x"}
  ```
- `/ibl/validate`: `valid:false`, "'engines' 노드에 'icon' 액션이 없습니다." (정상)
- `/ibl/execute check:true`(레거시): `{"ok": true, "issues": []}`. 흔적은 preflight.unknowns 의 `unresolved_action` 뿐이다.
- 대조: 판본 2 check 는 `ok:false, UNSUPPORTED_ADAPTER` 로 정직하게 거절한다.
- 분류: 새 형태의 오류(검사 모드 침묵 통과). 레거시 check 경로에만 해당하고 심각도는 낮다.

### R4-W9: `[sense:commercial]{query: "청주 카페"}` 가 업종 낱말을 말없이 버린다
- 원 회차: 4회차 W9 "청주 카페 상권 상위 3곳"(깨끗·시드 후보였음).
- 이번 문장:
  ```
  [sense:commercial]{query: "청주 카페"} >> [table:take]{n: 3} >> [table:select]{columns: ["title","name","lat","lng"]}
  ```
- validate: valid, 경고 없음 / execute: success. 결과 3곳이 보노켐(가구 소매)·미래유통·극동유화역전주유소다. `query` 는 지명으로만 쓰여(조회지역 "청주역로358번길…") "카페"가 조용히 사라졌다.
- 분류: 판단 불가(경미). 어휘 계약상 query=지명이고 업종은 `indsLclsCd` 라서 결함이라기보다 사용 오류에 가깝다. 다만 경고 없이 엉뚱한 업종을 성공으로 돌려주고, 4회차 시드 문장 자체가 의미상 틀렸다.

## 3. 문법 변화로 정상 처리된 항목

- R1-T8: `$위치.lat` 치환은 정상이다. 재구성할 때 쓴 `lat/lng` 는 restaurant 의 param 이 아니어서(경고) → `x:"$위치.lng", y:"$위치.lat"` 로 고치자 오송 반경 결과가 나왔다.
- R1-T10 / R2-P3: `[self:finance]{op:"query"}` 기본은 summary(가맹점 items) → `query_type:"지출"` 이면 groupby·chart 가 성공한다. category 가 전부 빈값인 건 사용자 데이터가 미분류 상태라서다.
- R1-T5 / R2-P1: kosis `query` 는 통계표 검색이라 `year` 열이 없다. 원 보고서도 "과제 설계 오류"로 분류했다. 필드 목록과 함께 정직하게 거절된다.
- R1-G2: 재구성 문장의 `cron` 은 schedule 의 param 이 아니다(경고). 검수는 schedule 속 feed→take→each 까지 5스텝을 펼친다.
- R2-N1: show_map 이 bare 이음매로는 파이프를 받지 않는다(typecheck 가 미리 경고) → `markers:"$items"` 로 성공. 장소명은 좌표로 바꾸고, 못 찾은 2건은 정직하게 보고한다.
- R2-N6: rename 인자 `columns` → `map:{name:"title"}` 로 성공.
- R2-N9: each 가 do 결과를 흘리지 않고 원 행을 통과시킨다(정직 표지) → `collect:true` 로 경로 20.3km 가 보존된다. navigate_route `to:` 단독(origin 기본값)도 작동한다.
- R2-N3 / R3-T3: `[self:goal]{op:"create"}` 은 은퇴 → `[goal:"…"]{max_rounds,…, strategy:…}` 블록. check ok.
- R4-W5: `content:"$items.title"`(목록→문자열 칸)은 지금 정직한 타입 거절이다(옛날엔 JSON 배열로 착지). 판본 2 `$m.items >> take >> select` 뒤 `json($t)` 로 쓰면 성공한다.
- R5-T5 / R5-T13: each 가 이미 평탄한 통화를 내므로 `[table:flatten]` 이 "이미 평탄합니다"로 거절 → flatten 을 빼면 crawl→structure 5단이 성공한다.
- R5-T9: `[self:ledger]{store:"business", op:"list"}` → `[self:business]{op:"list"}` (ledger 는 경로 기반 select/append 로 재정의됨).
- R7-V5: `[self:discover]` 은 은퇴(커밋 `3ef4768f`, 사용자 판정·언어 개정).
- R7-V6: render_html → `[engines:render]{html, output_path}` 로 png 가 생성된다.
- R8-W5: icon 액션 은퇴. validate 가 "액션 없음"으로 정직하게 거절한다(레거시 check 의 침묵은 §2 R8-W5x).
- R9-X6: `[sense:cctv]{op:"stats"}` 는 선언 밖(check 가 정직하게 거절) → `[self:cctv]{op:"stats"}` 로 소스별 items.

### 원 결함이 해소된 것(참고)
G1-① `$변수.field`, G1-② 산출물→변수→read, G2·F12 do/분기 펼침, F1 가격·평점·날짜·title 병기, F2/F2-op 경고, F3/F6 원천 행(select·dedup), B1 워크플로 문자열 do(즉석 run), G1-③ show_map `$items`, F8 crypto·host items, F1-스냅샷 canonical, F1-naver name/price, F1-date(startup end_date, legal date), B2 memory_id, F1-위치 cctv lng, F8-agents·storage volumes, B3 download UA(135KB 저장), B4 feed 죽음=정직 실패(단독·폴백 전멸 모두), @몸 정직 에러와 `@폰` 실라우팅, D1/B8(경로가 틀리면 else 를 보류하고 condition_errors, 옛 `.current_price` 는 자동 해소), B7 if/else 속 파이프 완주, case 범위·값 매칭, `;` 독립 문장, F9-②(goal delete op 신설), contest 한국어 0건에 정직한 안내(hint/empty_notes), W7 channel_read email identity 해소.

## 4. 재검 못 한 항목

- 부작용이라 check 만 한 것: R1-T1(channel_send), R1-T3·R6-U3·R4-W12(notify), R1-T7(cctv capture), R1-G1② notebook add, R1-F2(notebook add 잘못된 param; validate 경고는 확인), R3-T1/T2·R4-W1c(trigger create), R3-T4a·R4-W1a(workflow save), R3-T4b·R4-W1b(저장본 run; 즉석 `do` run 으로 대체 실측), R2-N3·R3-T3·R4-W2(goal 등록), R2-N7·R8-W2/W2b·R9-X9(others:ask), R7-V3(bulletin create/delete), R8-W3(schedule 15초), R8-W4(screen screenshot), R8-W6(folder_note set: F11 오류문은 쓰기가 필요해 미확인), R9-X8(follow add), R9-X10(클립보드 덮어쓰기: 액션 미특정, 미실행).
- R7-V5 의 진범(해마 렌트 모드 강등)은 discover 은퇴로 같은 문장이 없어 확인하지 못했다.
- R2-N4 기본 path(F4): 파일이 프로젝트 outputs 에 생기므로 check 만 했다. path 를 지정한 실행은 성공.

## 5. 관찰(오류 아님, 참고)

- R6-U5: `[self:memory]{op:"search"} >> … select{memory_id}` 는 성공하는데, typecheck 가 "'memory_id' 은 관측된 열에 없다"는 거짓 경고를 낸다. 관측 열 목록에는 없는 conversation_id 가 있다(76회차 F76-2 와 같은 부류).
- R1-F1: 다나와 `price` 는 문자열("1037660"), 번개장터는 정수다. sort 는 수치로 인식해 섞어도 정렬되지만 칸 타입이 통일돼 있지 않다.
- R8-W7: email 행에 `title` 병기가 없다(subject 만 있음). F1-title 규약이 적용되지 않은 소스다.
- R5-T8: world 스냅샷이 중첩 1행으로 union 된다(원 보고서의 '판정성 보류' 층위 선택이 기본 1행으로 굳었다).
