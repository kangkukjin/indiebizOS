# 상상훈련 1~81회차 회귀 재검 보고서 (2026-09-29)

> 읽기 전용 감사 — **수리 0건**. 과거 보고서의 갭 원장 최소 재현·실패 과제 문장을 라이브 백엔드(:8765)에
> 다시 돌려 **지금도 오류를 내는 것만** 모았다. 문법 개정(은퇴 액션·op/param 개명·판본 2)으로 옛 표현이
> 실패하더라도 **현재 형태로 고쳐 쓰면 정상인 것은 오류에서 제외**했다. 의도된 실패가 지금 정직하게
> 거절되는 것도 정상으로 셌다. 반대로 에러가 안 나도 원 결함(침묵 통과·거짓 성공)이 재현되면 오류로 셌다.
>
> - 실행: 읽기 전용 문장만 `/ibl/execute`(`project_id:"컨텐츠"`, `origin:"training"`). 부작용 문장(발신·알림·예약/트리거 등록·
>   사용자 데이터 쓰기)은 `/ibl/validate`·check 만 했다. 파일 쓰기는 scratchpad 경로로 바꿔서만 실행했다.
> - 저장 함수(71)·재무 원장(72)·since 검침(75)은 격리 저장소 프로세스로 재현했다. 라이브 `data/workflows`·`finance_records.db`·`table_since.db` 는 불변.
> - 묶음별 상세(문장 원문·응답 발췌·문법 변화 목록): `batches/result_*.md` 9개 파일.
> - 백엔드: 재검 전후 `restart_control` phase=ACTIVE.

## 0. 총괄

| 묶음 | 재검 표현(대략) | 여전히 오류 | 문법 변화로 정상 처리 |
|---|---|---|---|
| 1~9 | 115 | 5 | 12 |
| 10~17 | 118 | 2 | 7 |
| 18~25 | 49 | 0 | 2 |
| 26~35 | 43 | 2 (1건 판단 필요) | 5 |
| 36~52 | 약 110 (48·49 탐침 94칸 포함) | 3 | 3 |
| 53~60 | 약 250 (57~60 probe 원판 재실행) | 1 | 3 |
| 61~69 | 약 350 관측 (probe 원판) + 최소 재현 37 | 0 | 0 |
| 70~75 | 174 | 3 | 6 |
| 76~81 | 68 갭 | 5 | 2 |
| **합** | **약 1,300** | **21** | **약 40** |

81회차에 걸친 갭은 대부분 해소되어 있다. 남은 21건 중 **거짓 성공·침묵 부류가 7건**으로 가장 무겁다.
검사와 실행이 어긋나는 부류가 5건, 틀린 진단·기본값 실패가 4건이다. 나머지는 보고 누락 1, 운영 1, 데이터 잔여 2, 판단 필요 2 이다.

## 1. 거짓 성공·침묵 (가장 심각 — 사용자가 틀린 결과를 성공으로 받는다)

### E1. R29-B29-1a — 1열 표를 막대 차트로: 빈 차트가 `success:true` (**회귀**)
```
... >> [table:chart]{chart_type:"bar"}      # 입력 통화의 열이 하나뿐
```
- 결과: "막대 차트 생성 완료 (N개 항목, 1개 시리즈)". PNG 를 열면 막대 없는 빈 축뿐이다(`R29_one_column_bar_empty.png`, 눈으로 확인함).
- 29회차에 "값 열이 없습니다, 최소 2열 필요"로 거절하도록 고쳤던 것이 되돌아갔다. 판본 1·2 모두 같다.
- 추정 원인(코드 읽기): `visualization/handler.py` `_table_to_chart_data()` 가 1열 bar 를 line/scatter 갈래로 보내며 가짜 `"y"` 시리즈를 만든다. 그래서 `_diagnose_no_data` 거절에 닿지 못한다.

### E2. R52-N1 — `[table:document]` 가 렌더 못 하는 블록을 조용히 버리고 성공
- 해당 블록: `items` 를 준 table, 빈 table, title 없는 cards, `items:"$표.items"` table.
- 결과는 `success:true` 에 "1블록을 렌더했습니다". 실제 markdown 에는 표가 없거나 "-" 만 남는다. validate 도 경고가 없다.

### E3. R77-B1n — arXiv 최신순 + 여러 낱말 질의 → 무관 논문이 성공으로 나옴 (새 형태)
```
[sense:paper]{query:"LLM reasoning limitations", sort_by:"recent", ...}
```
- 8편 중 5~6편이 무관했다(Dark Matter, Fingers of God 등). `all:` 질의가 OR 처럼 매칭된다. 관련도순은 정상이다(study/handler.py 63행 부근).

### E4. R54-B54-8 — 트리거 config 입구만 "시각 없는 반복"을 09:00 으로 조용히 바꿈
```
config: {repeat:"daily", interval_hours:6}     # 트리거 등록 config
```
- validate `valid:true`, 판본 2 check `incomplete`. 등록하면 경고 없이 "매일 09:00"이 되고 `interval_hours` 는 버려진다.
- 원인(코드·순수 함수 직접 호출로 확인, 등록은 안 함): `trigger_engine._resolve_schedule_config` 가 `normalize_schedule_config` 를 `executable=True` 없이 부른다. 이어서 `_sync_schedule_trigger` 가 "09:00"을 채운다.
- 같은 입력을 `schedule`·`manage_events` 는 "실행 예약에는 time(HH:MM)이 필요합니다"로 거절한다. calendar_rules 의 "한 벌 원칙"이 이 입구에서만 깨져 있다.

### E5. R17-F17-3 — `"$변수"` 통짜 치환에서 0건이면 봉투 전체가 파일에 저장됨
```
$주석 = [self:folder_note]{op:"detail", path:"…"} ; [self:write]{path:"…/주석.md", content:"$주석"}
```
- 파일 내용: `{"success": true, "annotations": [], "items": [], "count": 0}`. 목록이 비어 있지 않으면 items 만 저장되어 정상이다.
- 원인: `backend/ibl/workflow_binding.py:183` 의 `items_nonempty = … and bool(items)` 때문에 빈 목록이 통화로 인정되지 않고 봉투 원형으로 떨어진다.

### E6. R81-B3 — `self:photo` 기본 '사진'에 워크스페이스 이미지가 섞임
- backend/assets 아이콘, projects/study/images, HomePages public 이 섞인다. 수리 문서가 한계로 명시한 잔여다.
- 기본 호출 자체도 candidate_limit 때문에 `PARTIAL_SOURCE` 로 실패한다(→ C 부류와 겹침).

### E7. R4-W9 — `[sense:commercial]{query:"청주 카페"}` 가 "카페"를 경고 없이 버림 (판단 필요, 경미)
- 가구점·주유소를 성공으로 돌려준다. 어휘 계약상 query 는 지명이라 사용 오류에 가깝다. 다만 4회차 시드 문장이 의미상 틀린 채 남아 있고, 버려진 낱말에 대한 경고가 없다.

## 2. 검사(validate/check)와 실행의 불일치

### E8. R74-T24 — `… >> [self:copy]{dest}`: check 는 이슈 0, 실행은 전부 실패
```
[self:list]{path:"<scratch>/list", pattern:"*.pdf"} >> [self:copy]{dest:"<scratch>/bak2/a"}
```
- 오류 원문: "copy_path: `items` 에는 타입 선언이 없는 자리인데 1개짜리 목록이 왔습니다 …". 복사된 파일은 0개다. 변형 4가지(`$l >>`, `{items:$l} >>`, take 경유)가 모두 같다.
- `describe self:copy` 는 `pipe_input:"items"` 인데 타입은 `items:"Unknown"` 이다. 같은 수리(B73-1)로 파이프 자리가 생긴 chart·document·spreadsheet·sheet append 는 실행까지 된다.
- 74회차 탐침이 check 만 판정해서 수리 뒤에도 드러나지 않았다.

### E9. R9-X7b — `[limbs:cloudflare_api]` 가 `returns: effect` 로 선언됐는데 실제로는 items 를 냄
- `>> [table:take]` 로 바로 이으면 실행 전 검사가 거절한다. `$z` 에 받아서 이으면 성공한다. 선언과 실제 동작이 어긋나 있다.

### E10. R8-W5x — 판본 1 `/ibl/execute` + `check:true` 가 없는 액션을 통과시킴 (경미)
- `[engines:icon]`, `[sense:nosuchaction]` 에 `ok:true, issues:[]` 가 나온다. `/ibl/validate` 와 판본 2 check 는 정직하게 거절한다.

### E11. R79-B2c — 계약에 enum 이 투영되지 않아 check 가 못 잡음 (경미)
- 공연 region "청주"·genre "어린이극", 당근 region 누락이 check 에서 incomplete·경고 0 이다. 실행에서야 `TOOL` 로 정직하게 거절된다. tts engine·photo kind 는 투영되어 있다.

### E12. R50-N1 — 양쪽 분기가 모두 할당한 변수를 "분기 안에서만 태어남"으로 거짓 경고 (경미)
- if/else 또는 try/catch 양쪽이 모두 `$k` 를 할당해도 실행 전 검사가 경고한다. 실행 결과 자체는 옳다.

## 3. 틀린 진단·기본값 실패 (정직하게 실패하지만 이유나 기본값이 틀림)

### E13. R48-F6 — `[table:chart]` 가 입력 문제의 원인을 틀리게 말하고 `rows_in` 도 없음
- 스칼라 입력에는 "데이터가 비어있습니다. data 또는 data_file을 제공하세요", 0행 입력에는 "x/y 열을 찾을 수 없습니다"라고 답한다.
- 형제인 document·spreadsheet 는 `rows_in:0`·"입력 0행"을 정확히 낸다. 49회차 후속이 "chart 는 이미 고쳐져 있었다"며 닫았지만 실측과 맞지 않는다.

### E14. R76-B4 — `sense:stock` history 기본값(max_points 10)으로 `PARTIAL_SOURCE` 실패
```
[sense:stock]{op:"history", ticker:"AAPL", start_date:"2026-01-01"}
```
- 교재 `data/guides/investment.md` 33행 예문 그대로가 실패한다. 전량 요청(1500)은 수리되어 성공한다.

### E15. R9-X7a — `cloudflare_api` 설명문 예시 경로에 앞 `/` 가 없음
- 예시 `'zones/abc/dns_records'` 를 그대로 쓰면 `.../client/v4zones` 가 되어 404 "No route for that URI". `"/zones"` 로 쓰면 성공한다.
- 핸들러가 경로를 정규화하지 않고 이어 붙인다.

### E16. (E6 의 다른 면) R81-B3 기본 호출 `PARTIAL_SOURCE` — 위 E6 참조.

## 4. 보고 누락

### E17. R15-F15-1 — if 가 else 로 떨어지면 `matched_value` 가 null
- case 와 if 참 분기는 좌변 실측값을 싣는다(예: case 157.34, if 5.2). else 분기에서는 좌변을 실제로 측정했는데도 null 이다. R13-K7·R16-T5·R17-T4 가 이 항목으로 합쳐진다.

## 5. 운영 (지금 사용자에게 피해가 가는 중)

### E18. R75-F75-2 — 같은 실패 알림이 억제 수리 뒤에도 매시간 나감
- `AI시대_보고서출처_뉴스갱신` 트리거가 계속 실패한다. 억제 수리 커밋 `1de0df53`(16:09) 뒤에도 16:21~22:24 매시간 "스케줄 실행 실패 — 홍보/" 알림이 나갔다(오늘 24통).
- 원인: 실패 원문에 매번 바뀌는 epoch 실수 `"prepare": {"time": 1790688273.01…}` 가 남는다. `calendar_actions._failure_signature`(backend/services/calendar_actions.py:19) 의 정규식은 uuid·ISO 시각·duration_ms·단위 붙은 수만 지우고, 단위 없는 epoch 는 지우지 못해 매번 "다른 실패"로 판정된다(코드 대조로 확인).
- 트리거 자체의 실패 사유는 "원문 제목 확인 실패" 3건이며, 외부 원천 문제일 가능성이 섞여 있다.

## 6. 데이터 잔여

### E19. R72-F72-1 — 재무 원장에 수리 이전 가맹점 잔여물 10행
- 예: `더홀릭영통점 / ( ,2*9*) / / 이용금액`, `LG U+ 통신요금 자동] …`, `매출 안내] 27일 / - / 구글플레이_TOSS`. 같은 가게가 여러 키로 쪼개진다.
- 파서는 고쳐졌다. 원문 메모가 없는 옛 행이라 보정에서 빠졌다. 보정 여부는 사용자 결정이다.

### E20. R77-F1 — 도서 nl 칸 표기 혼재 (경미)
- `publication_year` 가 "2012"와 "20120208"로 섞이고, `publisher` 에 "서울 : 하다, 20120208"처럼 발행지·날짜가 섞인다.

## 7. 환경·판단 필요

### E21. R8-W1 — `[sense:here]@폰-9f2b` 가 여전히 "위치 null"
- 폰 환경 쪽 원인으로 보인다(외부 원천). 다만 오류문이 한 마디뿐이라 원인(권한·GPS·전송)을 가를 수 없다.

### E22. R33-B33-2 — `do:"$n = $n + 1"` 가 바깥 `$n` 유무와 상관없이 거절됨 (판단 필요)
- 원 결함(`0 = 0 + 1` 파싱 붕괴)은 사라졌다. 지금은 `[table:each]` 나 `[self:workflow]{op:"run"}` 의 do 속 누적 할당이 "변수 $n 이 앞에서 할당되지 않았습니다"로 거절된다.
- 거절은 정직하다. 다만 do 몸이 바깥 변수를 못 읽는 것이 설계(스코프 격리)인지 결함인지는 판단이 필요하다.

(E7 R4-W9 도 판단 필요 부류에 걸친다.)

## 8. 오류로 세지 않은 관찰 (참고)

- **validate `valid:true` + `typecheck` error 가 공존**: 유령 op(`[self:finance]{op:"summary"}`, `[sense:book]{op:"detail"}`, `[self:folder_note]{op:"get"}`)와 병렬 뒤 rename→merge. 실행은 사전 검사로 거절되고 사유도 응답에 있다. 하지만 `valid` 만 보는 소비자에게는 "통과인데 실행 거절"로 보인다. 두 필드를 일부러 분리했는지 확인이 필요하다.
- **B30-1 잔여**: 판본 2 에서는 `[try]{A & B}[catch]` 가 정상이다. 헤더 없는 판본 1 HTTP 경로(저장 프로그램·스케줄이 쓰는 경로)에서는 가지 하나가 실패하면 결과가 `{"result": "<파이썬 repr 문자열>"}` 이다. JSON 으로 파싱되지 않고 `branches_failed`·`warning` 표지도 없다.
- 35회차 `city: 123` → "라말라(요르단강 서안)"로 지오코딩된다. `[sense:world_bank]` required 누락 시 오류문이 "지표 'None'"이라 누락된 인자 이름을 말하지 않는다.
- 20회차 T9 `[self:forage]{op:"recall"} & [sense:paper] >> [table:union]` 이 이제 성공한다. recall 봉투 전체가 "효과 봉투" note 와 함께 1행으로 합쳐진다(읽기 액션이 "부수효과 결과"로 불림, `84265b8d` 개정 이후 설계로 보임).
- 블록 문장의 최상위 `results` 는 핸들러 원문 배열인데, 파이프의 단계 요약 `results[]` 와 키 이름이 같다.
- 53~60 묶음: 문자열 where 의 오탐성 경고, 판본 1 check 의 무판정, `event_action` 을 check 가 못 잡음(상세는 `batches/result_53_60.md`).

## 9. 재검하지 못한 것

- **55회차 arch 과제 T1~T20**: `house-designer` 묶음이 잠들어 있고, 깨우면 사용자 설정이 바뀐다.
- **부작용이라 검수만 한 것**(모두 validate/check 는 정상 또는 incomplete): 트리거·스케줄·goal 등록, 워크플로 save, notebook add, notify(F20-5 알림 제목 빈칸 포함), others 발신, 피드 게시, 즐겨찾기, folder_note set, 원장 쓰기, 캡처·렌더 산출(B73-4), 발화가 필요한 B75-2(지연 예약 이중 발화)·16회차 차단기.
- **재현 조건 부재**: F77-2(429), F51-1(MCP 장시간), B46-6(응답 필터 표면), F75-1(수리 전 잘린 이력), B81-2 폰 경로, 7회차 V5(`[self:discover]` 은퇴로 같은 문장 불가), 72회차 T15·T22(원장 경로가 저장소 안만 허용), B74-3·B74-4(스캔 쓰기).

## 10. 감사 과정 고지

- 26~35 묶음에서 `[self:workflow]{op:"run", do:"$n = $n + 1"}` 를 1회 실제로 실행했다(validate 가 write 로 표시한 문장). 즉석 do 실행이었고 1단계에서 실패했으며 등록 동작은 아니다.
- 격리 프로세스 재현(71·72·75)이 실행 저널 같은 시스템 부산물을 `data/` 아래에 남겼을 수 있다(라이브 HTTP 탐침과 같은 부류). `git status` 상 이번 감사가 만든 추적 대상 변경은 없다.
- 이 폴더(`docs/experiments/imagination_regression_audit_2026_09_29/`)는 미커밋이다.
