# IBL 관리 매뉴얼 (IBL Maintenance Manual)

**목적**: IBL의 **어휘·문법·통화** 상태를 정기/온디맨드로 **점검 → 기록 → 문제 분류·처리**하는 단일 절차서.
이 문서를 보면서 검사를 돌리고, 결과를 남기고, 문제를 부류별로 처리한다.

> **★2026-06-27 단일 통화(items) 이행 완료**: 옛 2층 통화(records/table) + document/currency 가 **`items` 하나**로 흡수됐다. 컬렉션 통화는 이제 `{"items": [ {…열린 dict…} ]}` 하나뿐. `returns:` enum = `{items, transform, scalar, effect}`. 옛 형태는 생산자가 items 행dict로 내고 소비자가 view(table/prose/cards)로 재구성한다. 상세=`docs/SINGLE_CURRENCY_MIGRATION_HANDOFF.md` · `architecture_single_currency_items` 메모. 이 매뉴얼은 그에 맞춰 갱신됨(아래 records/table 표현은 전부 items로 읽을 것).

**왜 필요한가**: 정적 검사(`--check`)는 *어휘 삼각 정합성*만, world_pulse self-check(`_evaluate_result`)는 *error 키 유무*만 본다 — **"items 통화가 유효 모양으로 `>>` 흐른다"는 불변식은 둘 다 안 본다.** 이 공백을 메우는 게 **`scripts/ibl_health_check.py`**(§1B 통화 단언 + §1C 골든 파이프). 즉 통화 회귀 가드는 *이제 존재한다*(기계적·AI 0). 매뉴얼은 그 하니스를 언제·어떻게 돌리고 빨간 것을 어떻게 처리하는지의 절차서다. 남은 졸업 과제=하니스를 자동 카덴스에 배선(§5).

---

## 0. 점검 대상 = 3층 + 배치

| 층 | 무엇 | 자동 가드 현황 |
|---|---|---|
| **어휘(vocabulary)** | 액션 정의가 src↔tool.json↔handler 정합 | ✅ `--check` 삼각검증 |
| **문법(grammar)** | `>>`/`&`/`??` 파서·합성이 도는가 | ✅ `ibl_health_check` §1C 골든 파이프(흐름 단언) |
| **통화(currency)** | items가 유효 모양으로 생산·소비·흐르는가 | ✅ `ibl_health_check` §1B(returns 대비 단언) — *기계 하니스 존재* |
| **배치(allocation)** | 검사 수단이 비용 대비 옳게 놓였나 | — (§4) |

**단일 통화**: `items` = `[{…열린 dict…}]`. 가장 흔한 관습은 카드(`{title,meta,summary,url,image?}` → filter/take/document/newspaper/cards)이지만 *title조차 보장 아님*(열린 항목). 옛 table(수치/시계열)=items **행 dict**로(첫 키=x축, 나머지=수치 시리즈 → 소비자 `_get_table`/chart가 키 순서로 table 재구성). 옛 document=items **type+text 항목**(소비자 engines:document가 감지). 즉 생산자는 items 하나만 내고, *소비자가 자기 view로 재구성*한다.

---

## 1. 점검 (Inspect)

> **한 줄 실행**: `python scripts/ibl_health_check.py` — §1A~§1D를 한 번에 돌려 구조 건강을 판정(GREEN/YELLOW/RED + 골든파이프 + 런타임 실패율). 어휘 수정·신설 때마다 재실행. 외부 self-check 인프라 비의존(레지스트리 + `/ibl/execute`만). 아래는 그 절차의 명세이자 수동 실행법.

### 1A. 정적 정합성 — 커밋마다 + 온디맨드 (싸고 결정적)
```bash
python scripts/build_ibl_nodes.py --check
```
삼각(src↔tool.json↔handler `_OP_DISPATCHERS`)·op enum·코퍼스 param·app 블록·transform 태그·폰 매니페스트 정합. **한계: 정적·태그만. 통화 *모양*은 안 본다.**

### 1B. 통화 무결성 — ✅ fixture 기반 자동 단언
`ibl_health_check.py`가 **`data/ibl_fixtures.json`**(액션별 "올바른 파라미터 예 하나" — 단일 진실 소스)을 읽어 items/scalar 액션을 라이브 호출하고 산출 스키마를 단언한다. fixture 완전성은 `--check`가 강제하므로(items/scalar 액션은 fixture 또는 exempt 필수) **신규 액션이 검사망을 빠져나갈 수 없다**(effect=실행 불가 면제, transform=§1C 골든). 판정:
- **GREEN**: 결과(또는 `final_result`)에 `items`가 비어있지 않은 dict 리스트(title 불요 — 열린 항목).
- **YELLOW**: empty(데이터 의존)·전송오류·통화 없는 스칼라 응답·identity 등 환경 의존. *구조 결함 아님*.
- **RED**: items 선언인데 문자열 반환(통화 파괴) 또는 목록은 있는데 items 미부착(계약 위반).

수동 단발 probe(특정 액션 점검 시):
```bash
curl -s -X POST localhost:8765/ibl/execute -H 'Content-Type: application/json' \
  -d '{"code":"[sense:radio]{op:\"search\",query:\"jazz\"}","project_id":"<아무 프로젝트>"}' \
  | python3 -c "import sys,json;r=json.load(sys.stdin);d=r.get('result',r);d=json.loads(d) if isinstance(d,str) else d;print('items' in d, len(d.get('items',[])))"
```
핸들러가 `format_json`으로 JSON *문자열*을 반환해도 엔진이 파이프 때 파싱하므로 통화는 흐른다(probe는 문자열도 `json.loads`로 풀 것). 옛 records/table/blocks 키를 직독하지 말 것 — 전부 items로 흡수됐다.

### 1C. 문법·파이프 흐름 — 골든 파이프
스텝 간 통화가 실제 흐르는지 단발 단언으로는 못 본다. 고정 골든 파이프 몇 개를 돌려 *최종* 통화 스키마를 단언:
```
[sense:search_naver]{query:"AI"} >> [engines:filter]{where:"title != "} >> [engines:take]{n:3}
[sense:world_bank]{indicator:"GDP",country:"한국"} >> [engines:chart]{chart_type:"line"}
```
→ 최종 결과에 items(또는 chart/document 산출 success·path)가 살아있나. ★table·document 흡수 후에도 골든이 통과해야 함: `world_bank>>chart`(items 행dict→소비자가 table 재구성)·`crawl>>document`(items type/text→prose). 외부 API 의존 파이프는 flaky → *내용*이 아니라 *통화 모양*만 본다.

### 1D. 런타임 건강 — 이미 수집됨 (재호출 말 것)
- **x-ray** (`api_xray.py`): action_health 3단계(verified/assumed/failed)·펄스·인지·메모리·에피소드 집계. WebSocket/GET 온디맨드.
- **world_pulse.db**: `action_health`(실패율)·`self_checks`(점검 이력). 직접 조회 가능.

---

## 2. 기록 (Record)

- **점검 1회 = 보고서 1건.** 형식: `점검 시점 · 모드 · 근거(1차 소스) · 발견[우선순위 ★ · 확인가능성 · 난이도 · 제안 · 검증법 · 위험]`.
- **발견 분류 태그**: `[어휘진화]` / `[인지·빈도]` / `[대시보드]` / `[버그부류]` / `[통화]`.
- **저장 위치**: 자동 검사분 → `world_pulse.db self_checks`(자동) · 사람 판단/방향 → 본 문서 하단 **"점검 이력"** append.
- **어휘를 바꿨으면** [[feedback_vocab_change_docs]] 의무 준수: `--check` 통과 + 7표면 문서 갱신 + CLAUDE.md 푸터 changelog + memory.

---

## 3. 처리 (Fix Playbook)

| 증상 | 진단 | 처리 |
|---|---|---|
| `--check` 빨강(삼각 불일치) | src/tool.json/handler 키 어긋남 | 셋 **모두** 동기화 후 재빌드 (예: travel `poi` 폐기 시 enum·dispatcher·yaml 동시 제거) |
| 목록 내는데 items 없음(RED) | 핸들러가 items 미방출 | 핸들러가 `items`를 **직접 방출**(native dict 그대로). 옛 키(records/table/blocks/data)를 내고 있으면 `items`로 rename(카드 shape면 키만, 표면 행 dict로). app `from:`도 같이 items로 flip |
| `returns:items` 인데 비-items 키 방출 | 옛 통화 잔재 | records→items 순수 rename / table→items 행dict(`[{col:val}]`, 첫 키=x축) / document blocks→items(type+text) / native 키→items pop. **소비자가 view 재구성**하므로 생산자는 items만 |
| 과적 legacy items(raw+카드 동시 방출) | items-우선 소비자가 raw를 통화로 오독 | legacy raw items 제거, 카드/통화 shape만 items로. `grep '"items"' tool_*.py`로 점검(§7.5 photo·naver 선례) |
| 침묵 빈결과 / 스키마 깨짐 | `_evaluate_result`가 못 잡음(error 키만 봄) | §1B 하니스(`ibl_health_check`)가 RED로 잡음 → 핸들러 수정 |
| 핸들러 수정이 안 먹음(op 액션) | 동명 **레거시 도구** 분기를 고침 | 실제 `_<tool>_op` 디스패처 분기를 고쳐라 (예: collect는 `wc_query` 아니라 `_collect_op` query) |
| 싱글턴 핸들러 reload 무시 | `tool_radio` 등 모듈 싱글턴 | `touch backend/api.py` (dev 재기동) |
| bespoke 렌더러(STATIC escape) 빈 화면 | app `from:` 밖의 React/HTML이 옛 키 직독 | 그 소비자도 따로 flip(예: cctv `DirectionsInstrument.tsx` `r.cctvs`→`r.items`) |

**반영 규칙**:
- 핸들러 편집 → `POST /packages/reload` (싱글턴은 `touch backend/api.py`).
- 어휘(src yaml) 변경 → `build_ibl_nodes.py` → `--check`.
- 백엔드 코어(`ibl_engine.py` 등) → 백엔드 재시작. **★backend 자기 편집 = 자기-reload 자해 주의** → 동의 후 별도 세션.

---

## 4. 배치 원칙 (검사를 더 만들지 말고 재배치)

**건강은 두 가지뿐이고, 검사는 *어휘를 쓸 때* 와 *하루 한 번* 만 돈다 (폴링 없음, AI 0):**

| 검사 | 무엇 | 비용 | 언제 |
|---|---|---|---|
| **정적 `--check`** | 삼각 정합 + **fixture 완전성**(items/scalar 액션은 ibl_fixtures.json 에 fixture/exempt 필수) | 싸고 결정적 (AI 0) | **커밋마다** (pre-commit) — 어휘가 변하는 유일한 순간 |
| **일일 건강 점검** | `scripts/ibl_health_check.py` 1회 = §1A 정적 + §1B fixture 통화 + §1C 골든 | 싸고 결정적 (AI 0, 수 초) | **하루 1회** (`run_daily_health_check`, RED 면 알림) |
| 대시보드(x-ray) | self_checks/action_health 집계 | — | 온디맨드 |

**핵심**: IBL 구조 건강이 *변하는 건 어휘를 쓸 때뿐*이다 → 커밋 게이트가 본진. 일일 점검은 그 회귀 그물(외부 의존·우발 변경 검출)일 뿐. **읽기전용 liveness 를 폴링 sweep 이나 AI 턴으로 돌리지 않는다** — fixture(올바른 param 하나)면 기계가 결정론적으로 판정한다. AI 가 param 을 추론하거나 안전 액션을 고르는 일은 *영구히* 없다(fixture 가 그 지식을 한 번 담아 둠). 옛 배선(전수 sweep + 매일 AI 턴 + AI 테스트계획)은 2026-06-27 전부 은퇴.

---

## 5. 자동화 로드맵 (매뉴얼 → 하니스)

1. ~~**키스톤**: src yaml 각 액션에 `returns:` 추가~~ ✅ **완료(2026-06-26)**.
2. ~~**단일 통화(items) 이행**~~ ✅ **완료(2026-06-27, Phase 1~3h)**. records/table/document/currency 전부 items로 흡수, `_RETURNS_ENUM={items,transform,scalar,effect}`, 소비자가 view 재구성. `ibl_health_check.py §1B` 가 returns:items 대비 단언(GREEN 50/Y2/R0).
3. ~~**통화 계약 하니스**: 안전 액션 직접 호출 → `returns` 대비 스키마 단언 + 골든 파이프~~ ✅ **존재(`ibl_health_check.py` §1B+§1C)**. 수동 실행. (compress 액션은 이행 중 대부분 은퇴.)
6. ~~**폴링·AI 은퇴 + fixture 단일화**~~ ✅ **완료(2026-06-27, 10차)**. 전수 sweep(`run_self_check`)·AI 테스트계획(`generate_test_plan`)·매일 AI 턴(`trigger_ai_health_check`) 전부 삭제. 일일 경로 = `run_daily_health_check`(= `ibl_health_check.py` 1회 + RED 면 알림, AI 0). fixture 는 `data/ibl_fixtures.json` 단일 소스로 분리, `--check`가 items/scalar 완전성 강제. 어휘 생성/삭제 가이드(`new_action_checklist.md` 2.5단계 · `action_removal.md`)에 fixture 단계 합류.

4. ~~**배치(자동 카덴스)**~~ ✅ **완료(2026-06-27, 9차)**. `run_self_check`(world_pulse_health.py)가 사이클 끝에서 **`run_ibl_currency_check()`** 로 `scripts/ibl_health_check.py` 를 subprocess 호출 → §1B 통화 + §1C 골든 결과를 `self_checks`(node=`__ibl_health__`, action=`currency`/`golden_pipes`)에 기록 → x-ray 노출. 카덴스=`world_pulse_config.self_check.interval_hours`(**24h=하루 1회**). RED 통화 결함이 하루 1회 자동 감지. **★중요 교훈: 통화 단언은 liveness sweep에 얹으면 안 됨** — sweep의 최소 test_params(예: world_bank에 indicator 없이 query)는 통화-유효하지 않아 false-positive 투성이. 통화 검사는 *curated 좋은 params + 렌더러 경로*가 필요 → 단일 소스 `ibl_health_check.py`(probe 목록 1곳)를 그대로 호출(§2 거버넌스: probe 중복 0). 액션 liveness(sweep)와 통화 정합성(ibl_health_check)은 *다른 params·다른 경로*라 같은 sweep으로 못 합침.
5. **검증(회귀 가드 작동 증명)**: 일부러 items 미방출하는 액션을 만들어 §1B가 RED로 잡는지 확인. (남은 옵션 과제.)

---

## 점검 이력 (append-only)

- **2026-06-27 (10차, 건강 시스템 단순화 — 폴링·AI 은퇴 + fixture 단일화)** — 사용자 지시("IBL은 단순한데 건강체크가 왜 복잡·비싸·느린가")로 *뺄셈*. **진단**: 건강은 두 가지뿐(①구조=정적, 어휘 쓸 때만 변함 ②행동=좋은 param 하나로 도나)인데 같은 두 개념이 5곳/4곳에 중복 구현돼 있었고(정적 래퍼·sweep·AI 테스트계획·AI 턴), 변하지도 않는 구조를 매일 *폴링* + fixture 없어 *AI 로 때움* = 복잡·비싸·느림의 원인. **조치**: (a) `data/ibl_fixtures.json` 신설 — 액션별 올바른 param 하나의 단일 소스(fixtures 68 + exempt 8 = items/scalar 76 전수). (b) `build_ibl_nodes.py`에 `validate_fixture_coverage` 추가 → `--check`가 items/scalar 액션의 fixture 완전성 강제(신규 액션이 검사망을 못 빠져나감 + 삭제 시 고아 fixture 검출). (c) `ibl_health_check.py`가 하드코딩 PRODUCERS 대신 fixtures 파일을 읽음 + scalar liveness 분기(통화 면제하되 에러는 YELLOW). (d) 백엔드 삭제: `run_self_check`(sweep)·`run_static_ibl_check`·`generate_test_plan`(AI)·`_get_safe_actions`·`_evaluate_result`·`trigger_ai_health_check`(매일 AI 턴). 일일 경로 = `run_daily_health_check`(= `run_ibl_health_check` 1회[§1A+§1B+§1C 파싱] + RED 면 notification + maintenance, **AI 0**). (e) `[*:self_check]` IBL 액션·`/world-pulse/run-self-check`·스케줄러 lambda 전부 `run_daily_health_check`로 repoint. (f) 가이드 정비: `new_action_checklist.md`(통화 records/table→items, **2.5단계 fixture 추가**, 주기 정정)·`action_removal.md`(fixture 제거 단계 + stale self_check_plan 삭제)·`self_inspection_guide.md`(self_check_log→self_checks). **검증**: `--check` 통과(삼각+fixture 완전성+코퍼스+가드)·음성테스트(누락 액션·고아 둘 다 적발)·`ibl_health_check.py` 종단 GREEN(§1A ✅ / §1B GREEN 51·YELLOW 3·RED 0 / §1C 5/5)·전 모듈 컴파일·import 해소(죽은 함수 6개 제거 확인). **★백엔드 재시작 후 라이브**(스케줄러 reconcile + 새 코드 로드). **결과: 건강 시스템 = 가이드(절차) + `--check`(커밋 강제, fixture 완전성 포함) + `ibl_health_check.py`(일일 1회·AI 0). 폴링 0, AI 0, 중복 0, 새 액션 시 fixture 한 줄.**
- **2026-06-27 (9차, 통화 회귀 가드 자동 카덴스 배선 — §5#4 졸업)** — 사용자 지시로 `ibl_health_check`(통화)를 `run_self_check`에 합류, **하루 1회 자동**. **설계 여정(중요 교훈 포함)**: ①먼저 통화 단언을 liveness sweep의 `_evaluate_result`에 인라인(+골든 in-process)으로 얹음 → 트리거하니 **7건 currency_broken false-positive**(world_bank·travel·messages·grep·file_find·health·researcher). ②원인 진단=**sweep의 test_params가 통화-유효하지 않음**(world_bank에 `indicator` 없이 `query`, messages `{}`→thread는 neighbor_id 필요 등) → 좋은 params 주면 전부 items 정상(world_bank items[49]·messages items[8] 실측). **liveness sweep ≠ 통화 검사**(전자=최소 params로 살았나, 후자=curated params로 유효통화). ③해법=인라인 단언 전부 revert, 대신 **`run_ibl_currency_check()`가 단일 소스 `scripts/ibl_health_check.py`를 subprocess 호출**(curated params+렌더러 경로·probe 중복 0=§2 거버넌스) → 요약(§1B GREEN/YELLOW/RED·§1C 골든) 파싱해 `self_checks`(node=`__ibl_health__`)에 기록. ④카덴스 **12h→24h**(config) + 등록 로직을 **reconcile**로 수정(기존 "있으면 skip"이 config 변경을 막던 드리프트 → interval 다르면 자동 갱신). 검증: 격리 테스트로 `run_ibl_currency_check`→currency ok·golden_pipes ok(RED 0·5/5), false-positive 기록 삭제, syntax·임포트 OK, 카덴스 24h reconcile 확인(calendar_events). **★백엔드 재시작 1회 더 필요**(clean 버전 로드). **교훈: 회귀 가드를 *어느 호출 경로/어느 params*에 얹느냐가 본질 — 통화는 curated+렌더러, liveness는 최소+엔진.**
- **2026-06-27 (8차, 단일통화 이행 완료 후 첫 점검 + 가이드 갱신)** — 단일 통화(items) 이행 완료(Phase 1~3h) 직후, **가이드 절차대로 전체 점검을 실제 실행해 작동 확인**. **①점검 가능성 검증**: `--check`(§1A) + `ibl_health_check.py`(§1B~§1D) 전부 정상 실행, 외부 self-check 비의존(레지스트리+`/ibl/execute`만). **②결과 GREEN**: §1A 정적 ✅ · §1B **GREEN 51/YELLOW 2/RED 0**(통화 생산자 53개 전수 items 단언) · §1C 골든 5/5(items 흐름, world_bank>>chart·crawl>>document 포함) · 구조 건강 ✅. **③회귀 의심 직접 검증**: §1D 런타임 실패율 상위(groupby 56%·select 50%)가 단일통화 회귀인지 라이브 확인 → `legal>>select`·`world_bank>>groupby`·`naver>>filter>>sort` 전부 items 정상 흐름 = **실패율은 이력 누적/외부 입력, 회귀 아님**(여기·channel_read·video 등도 device/identity/외부 의존). **④갭 폐쇄**: `sense:crawl`이 probe 목록 밖(미검증 1)이던 걸 probe 추가(example.com) → **미검증 0개**(GREEN items[2]). **⑤가이드 갱신**: 이 매뉴얼 전체를 옛 2층 통화(records/table)+document/currency 표현 → **단일 통화(items)**로 정정(왜필요한가·§0 3층표·§1B·§1C·§3 playbook·§5 로드맵). `ibl_health_check.py` 커버리지 라벨도 `items 선언`으로. 통화 회귀 가드는 *이제 존재*(§1B/§1C 하니스)이며 남은 졸업=자동 카덴스 배선(§5#4). **YELLOW 2=양성**(business_item=default op list 무인자 빈 items·channel_read=gmail identity 환경). 142 액션 불변·build 일치.
- **2026-06-27 (7차, 통화 가장자리 = 2층 통화 모델)** — records/table로 안 떨어지는 가장자리 3종을 *비대칭 근거*로 결정. **판단 축=소비자가 파이프 변환자냐 렌더러냐.** ①**단일 시세**(stock·crypto·route·here)=scalar 유지(명사곱 부적합, 메모리 명시). ②**지도 마커**=흡수, geo 통화 **안 만듦** — map_data는 지도 렌더링(앱 계기)만 소비·변환자 없음 → records가 통화·map_data는 *렌더링 봉투*(장소목록 restaurant·realty·cctv 등 이미 records+map_data GREEN). ③**문서IR blocks**=통화 인정 — 다생산자(crawl·read[docx/pdf])→풍부한 1소비자 engines:document(5포맷) = 변환자 → `returns` enum에 **`document`** 신설(`_RETURNS_ENUM`), classify_currency가 `{blocks}` 인정, `sense:crawl` effect→document(실측 crawl→blocks[heading,paragraph]). 미검증 1=crawl(네트워크). **GREEN 50/RED 0·142 액션 불변·골든파이프 5/5.** ★잔여=`self:read`(다중모달, xlsx→table 보편통화를 scalar로 숨김 → currency 승격은 probe전략 필요).
- **2026-06-27 (6차, grep 형제 정정 + param 버그)** — `self:grep` 역방향 불일치(`scalar` 선언인데 3 op모드[content/files_with_matches/count] 전부 `{text,table}` 산출)를 `returns: table` 승격(src). probe RED이 노출한 **잠재 param 버그 동시 수정**: grep 핸들러가 `root_path` 키만 읽어 src가 광고하는 `path`를 silent-무시(`project_ibl_param_name_mismatch` 부류)였음 → glob_files와 동일(`path > root_path > project_path` + 절대경로). probe `path:"."`로 교정. **GREEN 50/YELLOW 2/RED 0 · 142 액션 불변.** ★재분류 전 라이브 확인=올바로 호출 시 table cols[파일,줄번호,내용] 69행 산출 → table 승격이 정직(분류 추측 아닌 실측 근거).
- **2026-06-26 (5차, P2 #3 선언 mismatch 정정)** — `self:list`·`self:file_find`가 `records` 선언인데 `table` 산출이던 불일치(GREEN이나 계약 거짓)를 **records 부착으로 정정**(선언을 참으로 — table 강등 아님). 근거: 파일=명사→records가 보편통화·document/messages 흐름, table은 dataops용 비파괴 유지. system_essentials/handler.py `list_directory`·`glob_files`에 records[{title,meta:크기·수정일,url:절대경로}] 부착. health `records[24]`·`records[5]`(전 "table N행"), 종단 `file_find>>take 3`=records 3·table 5 동시. **GREEN 49 유지·구조 건강 ✅·142 액션 불변.** 잔여 형제=`self:grep`(역방향: scalar 선언인데 table 산출 — table 승격이 정직하나 키스톤 의도 결정이라 동의 후).
- **2026-06-26 (4차, P1 통화 갭 폐쇄)** — 3차 키스톤이 노출한 RED 7개+YELLOW를 비파괴 records 부착으로 폐쇄(radio/zigbang 선례). `self:business`·`business_document`·`work_guideline`·`business_item`(business handler `_to_records`/`_doc_records`)·`self:lecture`·`sense:local_query`(handler 중앙 부착)·`sense:phone`(android notifications)·`sense:researcher`(study→guardian 패턴 `{message,records}` dict)·`self:manage_events`(backend/system_ai_tools.py — 백엔드 재시작 후 라이브, records[22] 확인)·`sense:company`(P2 가장자리 선취 — DART `disclosures` 20건에 records 부착, investment/tool_dart.py). +`sense:video` 오분류 정정(`records`→`scalar`: 단일 영상 텍스트 읽기, records 생산자는 별개 search_youtube). +probe 정직화 2건(manage_events `op:list`→`action:list`·company financials→disclosures — 핸들러 키/op 불일치로 인한 false-YELLOW 제거). **재실행: GREEN 49/YELLOW 2/RED 0 · 구조 건강 ✅.** 남은 YELLOW 2=통화 부착 불가능한 정직 advisory(business_item=데이터의존 빈결과·channel_read=gmail identity 환경). 라이브 종단=business records[7]·manage_events records[22]·company records[20].

- **2026-06-26 (3차, 통화 형식화 — 키스톤)** — 142개 액션에 `returns:` 통화 역할 기입(records 51·table 5·transform 9·scalar 19·effect 58). `build_ibl_nodes._check_action` 에 returns 검증(필수·enum·transform 정합) 추가 → `--check` 강제. `ibl_health_check.py` 를 선언-기준 단언으로 전환(scalar/effect=면제 → heuristic 거짓 RED 제거, 생산자 56개 중 30 probe·26 미검증 명시). 재실행 GREEN 29/YELLOW 1/RED 0·파이프 5/5·정적 ✅. **★다중-op 액션은 action-level returns가 근사**(kosis=table선언/기본op records·company·health) — GREEN 허용(통화-둘다-OK)이라 비파괴, 정밀화는 per-op 후속. **A급 아이디어→A급 강제 전환.**

- **2026-06-26 (2차, 매뉴얼 실행 검증)** — `scripts/ibl_health_check.py` 신설(매뉴얼 §1 결정화). 첫 실행이 `sense:cctv`를 RED로 적발(`cctvs` 마커는 있으나 records 미부착) → 비파괴 records 부착(지도용 cctvs 유지). **재실행 결과: §1A 정적 ✅ · §1B 통화 GREEN 29/YELLOW 4(company[probe op오류]·crypto·stock·goal=스칼라 N/A)/RED 0 · §1C 골든파이프 5/5 · ▶ 구조 건강 ✅.** §1D 런타임 관찰(2차 triage 대상, 구조 아님): channel_read 89%·run_pipeline 86%·kosis 82%·commercial 60%·groupby/select 50% 실패율(상당수 외부 API·device offline·테스트입력 추정). phone/here 100%=폰 오프라인 정상.
- **2026-06-26 (1차)** — 통화 감사(이 매뉴얼의 모태). compress×records 누수 **8건** 수정(travel·guardian + search_ddg/naver/news/shopping/devdocs/crawl) / 생산자 갭 **4건** 수정(radio·collect·kosis·health, 비파괴 records·table 부착) / 소비자측(변환자 9종·document·chart·spreadsheet) 전부 정상 확인. **회귀 가드 0** 발견 → 본 매뉴얼 작성. 근거: `_evaluate_result`(error 키만)·`validate_transform_contract`(태그만) 1차 소스 확인.
