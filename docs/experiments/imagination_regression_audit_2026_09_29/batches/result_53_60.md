# 상상훈련 53~60회차 회귀 재검 결과 (2026-09-29 22:17~22:30 KST, 읽기 전용)

백엔드: `/health` healthy, restart_control `phase=ACTIVE`(재검 전후 동일). 저장소 편집 0 · git 쓰기 0.
전 요청 `project_id:"컨텐츠"`, `origin:"training"`. 파일 쓰기는 전부 `scratchpad/regress/tmp/` 아래로 경로를 바꿔서만 했다.
57~60회차는 원 `probe.py`·`verify.py` 를 scratch 로 복사해 그대로 돌렸다(HERE=scratch, 원 기대값 검사기 그대로).
53·54회차 옛 문장은 HTTP 기본값인 판본 1(호환)로, 56~60회차 문장은 원래대로 `edition:2` 로 돌렸다.

## 1. 회차별 요약

| 회차 | 재검한 표현 | 정상 | 문법변화(정상) | 여전히 오류 | 검수만(부작용)·재검 불가 |
|---|---|---|---|---|---|
| 53 | 27 (실행 25 + validate 2) | 25 | 1 (A2s: 텍스트 시드 → `format:"json"`) | 0 | 2건 검수만(C4 memory save, D1 trigger) + 실행 안 함 11셀(finance/ledger/memory/notebook 쓰기, Z 정리) |
| 54 | 22 (validate+check 16 · 순수 함수 호출 4 · 읽기 2) | 21 | 0 | **1** (R54-B54-8) | 등록·발화 셀 전부 검수만(A1·A2·B1~B7·C5·C6·D2 발화) |
| 55 | 6 (정적 선언 1 · validate 2 · 실행 1 · check 1 · 반환 모양 지식 1) | 5 | 1 (T17 `format:"md"` → 판본 2 에서 `"markdown"`) | 0 | **arch 과제 T1~T20 재검 불가**(house-designer 묶음 잠듦) |
| 56 | 45 요청 (round56/ 요청 json 재사용, H1 건강 조회 제외) | 44 | 1 (M3 `merge{items}` → 이제 `inputs`/`left` 계약으로 정직 거절) | 0 | T11·T12 검수만 |
| 57 | 18 요청 + 최소 재현 2 | 20 | 0 | 0 | T09·T10 검수만 |
| 58 | 44 요청 + 보충 1 + 최소 재현 2 | 47 | 0 | 0 | T13~T16 검수만 |
| 59 | 44 요청 + 보충 1 + 최소 재현 3 | 48 | 0 | 0 | T21~T24 검수만 |
| 60 | 44 요청 + 최소 재현 4 | 48 | 0 | 0 | T21~T24 검수만 |

검사기 결과: 57 `verify.py` "10 checks, 8 executions, 5 repaired evidence paths: passed" · 58 `all_passed: true`(24검사·20실행) · 59 44/44 · 60 44/44.

## 2. 여전히 오류

### R54-B54-8 — 트리거 `config` 직접 지정이 시각 없는 반복·`interval_hours` 를 받아들이고 말없이 "매일 09:00"으로 바꾼다
- 원 회차·갭: 54회차 B54-8. 원래 증상은 "config 직접 지정은 검증 없이 저장되고, 가이드가 가르치는 `repeat:"daily", interval_hours:6` 은 스케줄러가 못 읽는 형태"였다.
- 이번에 돌린 문장(등록은 하지 않았다. validate·check 와 순수 함수로만 확인):
```
[self:trigger]{op: "create", name: "IT54_cfg4", config: {repeat: "daily", interval_hours: 6}, do: "[sense:stock]{op: 'quote', ticker: '005930'}"}
```
- validate: `valid:true`. 판본 2 check: `status:"incomplete", issues:[]`.
- 코드 경로(읽기만): `trigger_engine._resolve_schedule_config` 가 `normalize_schedule_config(params["config"])` 를 **`executable=True` 없이** 부른다. 결과는 `{'config': {'repeat': 'daily', 'interval_hours': 6}}` 이고 오류가 없다(순수 함수 직접 호출로 확인). 이어서 `_sync_schedule_trigger` 가 `event_time=config.get("time", "09:00")` 로 시각을 채우고, `add_event` 는 `repeat=="interval"` 일 때만 `interval_hours` 를 싣는다. 결과적으로 "6시간마다"라는 뜻이 경고 없이 "매일 09:00"으로 등록된다.
- 대조: 같은 규칙 모듈의 `[self:schedule]`·`[self:manage_events]` 입구는 `executable=True` 로 판정한다. 같은 입력 `normalize_schedule_config({...}, executable=True)` 는 "실행 예약에는 time(HH:MM)이 필요합니다"로 거절한다. `calendar_rules.py` 머리말의 "한 벌 원칙"(trigger·schedule·manage_events 가 같은 함수로 판정)이 trigger config 입구에서는 지켜지지 않는다.
- 분류: **원 결함 부분 재현.** 이제 요일 이름·once·repeat 집합은 검증하고 가이드도 고쳐졌다. 남은 것은 시각 필수 여부와 repeat 과 맞지 않는 `interval_hours` 가 침묵 속에 강등되는 것이다. 발화 실측은 부작용이 있어 하지 않았다. 증거는 코드 경로와 순수 함수 호출이다.
- 비고: 54회차 수리 표에는 B54-8 이 "수리"로 적혀 있다. 판정 대기 항목은 아니었다.

## 3. 문법 변화로 정상 처리된 항목
- 53 A2s: `feed >> [self:write]{path}` 는 여전히 텍스트로 저장한다(11회차 규칙, V53-1 ⓑ 판정). 이제 note 가 `format:"json"` 을 처방한다. `>> [self:write]{path, format:"json"}` 로 쓰면 `{items,count}` JSON 원장이 되고, 되읽기 → 누적 → dedup → 되쓰기가 6행으로 선다.
- 55 T17: `[table:document]{format:"md"}` → 판본 2 에서는 `format:"markdown"` 이어야 한다(`md` 는 ARGUMENT_CONTRACT 거절, 판본 1 validate 는 아직 통과). `as:"images", src_field, caption_field` 판은 check 통과.
- 56 M3: `[table:merge]{items:[…], by}` → 이제 "다음 인자 중 하나가 필요합니다: inputs, left"로 정직하게 거절한다(merge 는 둘 이상의 출처가 필요하다). 같은 뜻은 `([…] & […]) >> [table:merge]{by}` 나 `merge{left, right}` 로 정상 동작한다(M1·M2·T04).

## 4. 재검 못 한 항목과 이유
- **55회차 arch 과제 전부(T1~T20, B55-1 라이브 라벨, F55-2)**: `[engines:arch_list]` → "'house-designer' 묶음의 낱말은 잠들어 있습니다. 런처의 내 어휘에서 깨워 주세요". 묶음을 깨우면 사용자 설정이 바뀌므로 하지 않았다. 대신 확인한 것은 다음과 같다. B55-1 은 `house-designer/ibl_actions.yaml` 에 `arch_create`·`arch_modify` 의 `side_effect: true` 선언이 있다(정적 확인). F55-1 은 `data/ibl_return_shapes.json` 에 `scalar` 종류가 58건 있다. G55-1 의 `[table:each]{collect:true}` 는 다른 액션(self:time, sense:stock)으로 실행해 결과 필드가 원 행에 붙는 것을 확인했다. G55-2 는 check 만 했다(document 는 산출 파일을 프로젝트 outputs 에 쓸 수 있어 실행하지 않았다).
- **53회차 쓰기 셀**: C1a·C2a(finance save), C3a~c(ledger save), C4a(memory save — B53-5 저장 쪽 `category_normalized` 신고), C5(notebook), Z1~Z6(삭제)는 사용자 데이터 쓰기라 실행하지 않았다. B53-5 는 검색 쪽만 실행했고 유효집합 밖 category 를 정직하게 거절했다. B53-6 은 기존 지출 query 로 확인했다. items 행에 `record_id·kind·date·category·counterparty·amount(숫자)` 가 있다(값은 기록하지 않음). 자산 쪽은 기록이 0건이라 행 모양을 확인하지 못했다(데이터 부재).
- **54회차 발화 경로**(B54-1 발화 프로젝트 문맥, B54-2 소유자, B54-3 결과 전달, B54-4 동시 발화, F54-2 따라잡기, B54-5 run_now): 트리거·스케줄·이벤트 등록과 알림이 필요해 실행하지 않았다. 간접 확인한 것은 다음과 같다. 기존 트리거 list 에서 `run_count`·`last_run`·`last_success` 가 채워져 있고(B54-6), 최근 트리거는 `project_id:'홍보'` 를 싣는다(B54-1). 실패 이력 행에 `error` 가 있다(F54-4). `count`·`shape` 는 items 결과일 때만 붙는 설계다. 지난 시각 `at:"00:01"` 거절, `minutes:1800` 거절, `date "YYYY-MM-DD HH:MM"` 분리는 `calendar_rules.schedule_request/calendar_request` 순수 함수와 판본 2 check 로 확인했다.
- 55·56~60회차의 저장·발신·예약·알림 과제는 원 보고서대로 검수만 했다(전부 check 통과).

## 5. 관찰 (오류로 세지 않음)
- 53 A2b1: 문자열 where `"url not_in ${본.items.*.url}"` 는 이제 정확히 안티조인한다(구조형 A2b2 와 같은 2행). 그런데 봉투 최상위에 `[목록→글자] … 산문 한 줄이 의도면 [table:brief], 행마다면 [table:each]` 경고가 붙는다. 결과가 맞는데 엉뚱한 처방을 내는 오탐성 경고다(문구에 "의도면 무시" 단서가 있다).
- 54: 판본 1 문장에 `/ibl/execute {check:true}` 를 주면 `status` 없이 `issues:[]` 만 온다. 같은 문장을 `/ibl/validate` 는 invalid 로 본다(예: `cron:"30 */2 * * *"`). 판본 1 에서 check 는 판정하지 않는 것으로 보이며, 판본 2 check 는 같은 문장을 invalid 로 잡는다.
- 54: `manage_events{event_action:"launch_rockets", date, time}` 는 판본 2 check 가 `incomplete` 로 통과시키고 런타임(`system_ai_tools`)에서만 거절한다. incomplete 는 보증이 아니므로 결함으로 세지 않았다.
