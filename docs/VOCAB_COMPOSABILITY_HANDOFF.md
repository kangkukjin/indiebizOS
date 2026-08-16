# 어휘 조합성 재점검 핸드오프 (2026-08-15)

> **다음 세션 START HERE.** 1차 집행 완료(154→**151**, 커밋 `a38c2d8`) + 2차 집행 완료(151→**150** — §1b, 같은 날 후반).
> 남은 것: **2c(blog→notebook)는 기각 확정**(§2c), 스위치화·휴면 후보는 계수 숙성(§3), 판정 대기 표(§4).
> **★08-16 상상 훈련 신설·1회차 완료(§7)** — 미조합 목록=메뉴로 조합 훈련. 발견: G1 통화→param 바인딩 규약 부재(최대)·G2 schedule.do 검수 사각·F1 records/표형 칸 규격·F2 validate param 이름 미검사. **G1·G2·F1=사용자 판정 대기.**
> 자매 문서: `VOCAB_DEDUP_HANDOFF.md`(압축 전사·계수 인프라 — §(7)에 1차 실행 기록), 감사 원본 보고서는 에피소드 로그(2026-08-15, 전수 감사 세션).

---

## 0. 판정 원칙 (이 작업의 헌법 — 사용자와 합의됨)

1. **낱말 자격 = 가능성 공간에 새 차원을 더하는가.** 새 감각 표면(API·인증 캡슐화), 프로토콜, 원장(state), 미디어 생성 능력 → 낱말. 기존 낱말들의 호출 순서뿐(오케스트레이션)·순수 산술·URL 하드코딩 → **얼려야 할 것은 문장**(스크립트/파이프라인/앱 인스턴스).
2. **판별법 = 핸들러를 연다.** desc나 파이프 실적이 아니라 구현을 읽고 대체 경로를 실측한 뒤에만 은퇴. "파이프 0%"는 제거 근거가 아니다(API 캡슐화 낱말은 조회 결과를 사람이 바로 읽어서 0%).
3. **낱말/스위치/문장 3분법.** 사전 자격(프롬프트 상주·시딩·재학습)과 레지스트리 자격(실행 보장)은 다른 문제. 앱 전용 낱말=스위치(`prompt_hidden` 요금제), 절차=문장(스크립트). 스위치임은 본질이 아니라 상태 — 해마 회상이 부활 방아쇠.
4. **복합어 제거 시 보편어 신설이 최선.** pew_research→feed 가 모범: 사전 −1 +1 인데 차원은 늘고(어떤 피드든) 중복 파서도 수렴.
5. **휴면/스위치화 필터는 프롬프트 층(사전 렌더링)에만.** ibl_access·validate·실행 층이 활성 상태를 참조하면 앱이 깨진다 — 절대 금지.

## 1. 완료 (2026-08-15 1차, 미커밋)

- **계수 수리**: `_usage_origin()` — `__self_check__` → origin `'selfcheck'`. **08-15 이전 origin='agent' 는 ~55% 순찰 오염** — 은퇴 판단은 08-15 이후 데이터만. (`VOCAB_DEDUP_HANDOFF.md` §(0) 정정 참조)
- **`sense:feed`{url, limit} 신설**(web 패키지) ← `sense:pew_research` 은퇴. 라이브 실 RSS 검증.
- **`open_window`{app: files|photos}** ← `limbs:explorer`·`limbs:photo_manager` 은퇴. ibl_routing `_execute_launcher_command` 상단에 pending-queue 직결 분기. explorer desc 거짓말("Finder") 해소 — OS Finder 는 `os_open`.
- **등록 스크립트 "잔여추정"**(data/scripts/잔여추정.py) ← `self:residual` 은퇴. estimate(Wilson CI)+sample(file_index).
- 코퍼스: 이관 27행(★파인더 명시 intent 4행은 os_open 으로 정직 재배선) + 시드 9 + rebuild_index 3,175(벡터 누락 0). 연상 4/5 직행.
- 문서: open_window.md·disk_search.md·guide_db·양 README·CLAUDE.md 어휘 줄·VOCAB_DEDUP_HANDOFF §(7).
- 백업: `data/_backups/2026-08-15_vocab_feed_merge/`.
- ⏳ **커밋 안 됨** — git 에 다른 세션 변경(providers·agent_pipeline 등) 섞여 있음. **pathspec 으로 갈라 커밋할 것.**
- ⏳ 재학습 대기열: feed·open_window 흡수. "블로그 RSS"는 아직 self:blog 와 경쟁(→ §2c 가 풀면 자연 해소).

## 1b. 완료 (2026-08-15 2차 — 2a·2b 집행, 151→150)

- **2a 집행 = 최소 수술 채택**: `engines:newspaper` 에 `prompt_hidden: true`(스위치화). 심사 실측 —
  사용계수 11일간 0(agent·app 모두), 살아있는 호출자는 신문 계기 발행 버튼(`[engines:newspaper]{}@hub`)뿐
  (NewspaperInstrument.tsx 는 주석 언급만, `data/workflows/구글신문.yaml` 은 08-05 은퇴어
  `sense:search_gnews` 를 써 이미 죽은 워크플로). 레지스트리·핸들러 유지 = 앱 버튼 무손상(라이브
  validate 확인), 코퍼스 8행 보존(부활 방아쇠). 액션 수 불변(150 은 2b 때문).
- **2b 집행 = 완전 은퇴**: `sense:collect` + web-collector 패키지 + `backend/services/web_collector.py` 삭제.
  심사 실측 — 호출자 전수 grep 0(★`_exec_tool` 직접 호출도 0 — 08-05 함정 재점검), 계수 0/11일,
  프로필 1개(2월 예제), 축적 DB 21행(2월 이후 정지). ad-hoc 크롤=`sense:crawl` 상위호환,
  프로필 정기수집 수요=`[self:script]` 가 기본 답. **selectors 의 crawl 이식은 불채택**(사용 0인
  축의 상주비만 늘림 — 원칙 1 재적용: selectors 는 파라미터였지 차원이 아니었다).
  백업=`data/_backups/2026-08-15_collect_retire/`(패키지·backend 모듈·가이드·site_profiles·코퍼스 15행 덤프).
  LAYERS·node_registry 라우터 맵·guide_db·system_docs 4종 정리. 코퍼스 15행 삭제(전부 합성
  balanced_20260516·후계어 없음 — `_delete_examples` 행+벡터). 검증=build --check 전 가드·층 가드·
  /packages/reload 후 라이브(collect 반려·crawl/feed 회귀·newspaper validate 유지).
- **부수 수리**: 1차 커밋 시 층 가드가 잡은 `ibl_routing`(ibl)→`api_pcmanager`·`api_photo`(surface)
  위반 → `backend/base/window_requests.py` 단일 저장소로 의존 역전(창 열기 pending-queue,
  surface 두 라우터·ibl_routing 세 소비처 재배선, 인프로세스+라이브 검증).

## 2. 다음 작업 — 2차 후보 3건 (구현 심사 = 원칙 2 절차로)

### 2a. `engines:newspaper` → 문장화 — ✅ 집행됨(§1b, 스위치화 채택)
- 근거: tool_newspaper.py 가 handler 의 search_gnews 배치를 **콜러블로 받아 호출** — 타 낱말 오케스트레이션 + 조판 템플릿 + 상태 파일. 실전 8건 파이프 0%.
- 심사할 것: ①호출자 전수 — **newspaper.yaml 앱 버튼**(`[engines:newspaper]{}@hub`)·스케줄러·원격/폰 표면. ②스크립트화 시 gnews 배치 경로 재사용 방법(스크립트는 아웃오브프로세스라 handler 콜러블 못 받음 — `/ibl/execute` 로 `[sense:search]{source:"gnews", queries:...}` 를 부르거나 web 패키지 함수 직접 import). ③앱 블록이 액션을 참조하는 한 액션 완전 제거는 계기 개편 동반 — **최소 수술 = 액션 유지 + `prompt_hidden: true`(스위치화)** 가 1단계로 충분할 수 있음. 사전에서 빠지는 것만으로 언어적 해악(학습 분포 오염·상주비)은 제거된다.
- ★주의: 코퍼스에 newspaper 용례 있음 — 스위치화면 코퍼스 유지(부활 방아쇠), 완전 은퇴면 이관 필요.

### 2b. `sense:collect` → `crawl` 흡수 (web-collector 패키지) — ✅ 집행됨(§1b, 완전 은퇴)
- 근거: collect = crawl + selectors + 수집 프로필. crawl 이 이미 에스컬레이션 크롤 보유. 코퍼스 15행 파이프 0%.
- 심사할 것: ①`collect_with_profile`/`collect_ad_hoc` 의 **tool 이름 직접 호출자** grep(★08-05 함정 — `_exec_tool("...")` 는 IBL grep 에 안 걸림. world_pulse_collectors 등). ②selectors 를 crawl 파라미터로 이식할 때 tool_webcrawl 과의 이음매. ③프로필 원장(정기 수집)은 스크립트/스케줄러로. ④ibl_health_check 픽스처. ⑤코퍼스 15행 이관 + web-collector 패키지 은퇴 여부(다른 액션 있는지 확인).

### 2c. `self:blog` → `notebook` 흡수 — ❌ 기각 (2026-08-15 사용자 판정: **별개 정체로 유지**)
> 판정: 블로그=내 저작물 원장(Obsidian vault)이라는 별개 정체 유지. 실사용 있는 산 어휘이고
> notebook Phase 3 도 보류 판정이라 서두를 이유 없음. 9월 초 보정 계수 숙성 후 재검토 가능.
> **다음 세션: 이 항목에 착수하지 말 것.**
> 2026-08-15 심사 참고 실측: blog 계수 58/11일(agent) 중 매일 3회는 자가점검 순찰 패턴(08-15 이후
> 'selfcheck' 로 분리됨) — 순찰 제외해도 실사용 존재(특히 08-05~07). collect·newspaper 와 달리
> **산 어휘**라 흡수는 데이터 이관+인용 계약 설계가 필요한 진짜 수술이 맞다.
- 근거: notebook 이 blog RAG 의 "이식 일반화"(같은 ko-sroberta+sqlite-vec+FTS5)라고 시스템 스스로 기록. 일반어가 생겼으니 특수어는 용례가 되는 게 원칙.
- 심사할 것: ①blog 7 ops 분해 — 검색/질의 → `[self:notebook]{op:ask}`(vault 를 노트북으로 등재), 관리(vault_rebuild 등) → 스크립트, 인사이트 분석 op 는 어디로? ②**데이터 이관 설계**: blog 인덱스 DB → notebook DB(재색인 비용·인용 계약 차이). ③Obsidian vault 가 진실 소스라는 계약 유지. ④★착수 전 **사용자 판정**: 블로그를 노트북의 하나로 볼지, 별개 정체(내 저작물 원장)로 남길지 — Phase 3 보류 판정(notebook 메모리)과의 관계도 확인.

## 3-A. 스위치화 후보 조사 — ❌ 프레임째 기각 (2026-08-15 사용자 판정)

> **판정: 사용 빈도로 스위치화를 결정하지 않는다.** 목표는 좋은 언어(작은 어휘의 조합) — 나쁜 언어=
> 조합 안 되는 복합어(명사만 있는 언어)=그게 스위치. 미사용은 "어휘가 아직 좋은 언어가 못 돼
> AI가 쓸 생각을 못 하는 상태"일 수 있으며, 그 상태를 스위치로 못 박으면 실패의 비준이다.
> **실측 확인**: 아래 A군 어휘 대부분 통화(items)는 올바르나 코퍼스 조합 용례 0%(book 45행 중
> 파이프 0)인 반면, 실사용 어휘(search 44%·stock 41%·weather 36%)는 조합 용례가 두텁다 —
> 코퍼스가 이 어휘들을 단발 명사로만 가르쳐 왔다. **처방 = 강등이 아니라 품질 개선**(조합 용례
> 시딩+재학습·desc 조합 초대) 후 사용 변화 재측정. 스위치화가 정당한 경우는 실체가 문장인 것
> (newspaper=구조 판정)과 앱 전용 운영 패널뿐. §3 의 "계수 숙성 후 스위치화" 계획도 같은 이유로
> 폐기 — 계수는 품질 개선의 전후 측정 도구로만 쓴다.
> 아래 원문은 조사 데이터로 보존(A군 목록 = **품질 개선 1순위 후보 목록**으로 재해석).

### 3-A-1. 품질 개선 1차 집행 (2026-08-15 — 사용자 승인)

- **조합 용례 시딩 48건**: A군 21어휘 전부에 파이프(>>)·병렬(&)·순차(;) 문장 용례 —
  전부 **라이브 실측 필드명** 기반(book=loan_count·publication_year / music=year·genre·duration /
  messages=unread·favorite / webapp=alive / stay=price·rating / cctv=playable / bulletin=post_count /
  family_news=is_draft 등, 액션별 items 를 실제 실행해 수집). 상류 조합(sense:radio→take→limbs:radio play,
  sense:cctv→take→limbs:cctv open)으로 effect 낱말도 문장에 합류. `/ibl/validate` 전수 통과
  (병렬 3건 제외 — 아래 결함), 해마 add_examples_batch(manual_seed·category=composition, 벡터 누락 0,
  총 용례 3,208) + ibl_distilled 803→851. 회상 실측 6문 중 3문 조합 시드 직행, 잔여=재학습 대기열.
- **desc 조합 초대 보강 7어휘**: book·performance·exhibit(culture)·health·webapp·messages(+music 은
  target_description 필드 목록 보강 — desc 200자 한도 실측). 실측 필드명을 desc 에 박아 조합을 초대.
- **★결함 발견**: `/ibl/validate` 가 병렬(&) 문장을 전부 반려(빈 노드 스텝 — "노드가 지정되지
  않았습니다"). `/ibl/execute` 는 정상(type:parallel branches:2 실측) = 조종실 dry-run 만 병렬 불능.
  별도 태스크 칩 발행됨.
- **다음 측정**: 재학습(feed·open_window 와 함께) 후 조합률·사용 변화 재측정 — 계수는 개선 효과의
  전후 측정 도구로만.

### (원문) 스위치화 후보 조사 결과 (사용자 요청으로 §3 일정 앞당겨 조사만 실행)

**방법**: action_usage_daily 11일(08-05~15) 전수 + 순찰 지문 차감. 자가점검 순찰은 전 액션 공통
일별 기저 [2,4,3,1,1,1,1,1,2,1,1]×k(k=액션별 프로브 수)로 나타남(실측) — 이 기저의 정수배와 정확히
일치하면 "에이전트 실사용 0"으로 판정(잔차=실사용 추정). ★selfcheck origin 분리는 08-15 커밋이라
다음 순찰부터 데이터가 깨끗해짐. 표본 11일 한계 유의.

**A군 — 앱 계기 어휘, 순찰 잔차 0 + 조종실 0 (스위치화 추천, 21개 ≈ 13,200자 = 카탈로그 33%)**:
공개면 4종 others:portal(1570자)·family_news(1290)·showcase(1132)·bulletin(922) /
cctv 3종 sense:cctv(416)·limbs:cctv(259)·self:cctv(250) / 라디오 3종 sense:radio(311)·limbs:radio(324)·
radio_favorite(355) / 음악 2종 self:music(1248)·limbs:music(647 — 앱사용 52 활발, 에이전트 경로만 0) /
문화 4종 sense:book(831)·performance(298)·exhibit(85)·stay(677) / self:health(731 — 앱 43)·
self:photo(492)·self:webapp(503)·others:messages(317 — 앱 19)·limbs:launch(115).
유보 쟁점: messages·health 는 "메시지 확인해줘"·"혈압 기록해줘" 자연어 경로가 회상 의존이 됨.

**B군 — 몸·상황성 어휘 (유지 추천 — 빈도 아닌 가용성)**: guestpc(2717자)·browser(1572, 코퍼스 267)·
android(792)·limbs:phone(998)·screen(779)·self:limb(674)·폰 감각(listen/see/here)·sense:phone·phone_sync.
상황(USB·브라우저 자동화·폰)이 와야 쓰는 어휘 — 11일 미사용은 신호가 아님.

**C군 — 시스템 배관·기능어 (스위치화 부적절)**: delegate·schedule·workflow·goal·switch·trigger·
manage_events(§4 스케줄 6형제 설계 태스크로)·agents·self_check·propose_patch(REPAIR 헌법)·forage·
folder_note·storage·output·package·auto_response·table:*(표준 코어).

**D군 — 앱 없는 저사용 감각·콘텐츠 어휘 (9월 계수 숙성 후 개별 판정)**: researcher·entity·classic·
devdocs·world_bank·kosis·legal·company·crypto·search_local/local_query/local_save·reverse_geocode·
search_shopping·used·neighbor·business_item/business_document/work_guideline·engines:web(845)/web_site/
web_component·mkdir·volume·show_map·player_status 등. 신설 관찰 중(notebook·finance)과 실사용 검출
(stock·realty·video·weather·navigate_route·freelance·restaurant 등)은 후보 아님.

## 3. 보류 — 스위치화·휴면 (계수 숙성까지)

- **재개 조건: 보정된 계수(origin='agent', 08-15 이후) 2~4주 숙성** — 9월 초 이후.
- 후보(감사 합의): `others:family_news`·`portal`·`showcase`·`bulletin`, cctv 3종, `limbs:radio_favorite` 등 "산출 표면 사용 0 + 앱/원장 보유" 군. 제거 아님 — `prompt_hidden` 동적화(사전 퇴거만).
- 휴면 설계 합의사항: 히스테리시스(내릴 땐 수 주, 올릴 땐 즉시)·사전 개편은 세션 경계 배치(캐시 진동 방지)·이름 한 줄 창고 목록은 상주(발견성)·**코퍼스는 보존**(해마 회상=부활 방아쇠)·판정 신호는 산출 표면(에이전트+조종실)만(앱 사용량은 사전 상주 근거 아님).

## 4. 판정 대기 (사용자 결정 사안 — 착수 전 물을 것)

| 항목 | 실측 | 질문 |
|---|---|---|
| 스케줄 6형제 (schedule/trigger/workflow/goal/manage_events/switch) | 전부 파이프 0%, 유의어 분산 | "예약은 낱말 1+축, 내용물은 문장 참조"로 통합? (VOCAB_DEDUP (6) 설계 태스크) |
| 상거래 3형제 (search_shopping/used/freelance) | 각자 source 축 보유 | `[sense:market]`{kind}로 접나 — "한 단어=한 개념" 경계 판정 |
| search_local vs local_query | 이름만으로 구분 불가 | desc 드리프트 감사 대상 |
| local_save vs write vs download | write 가 파이프 싱크 겸용 | local_save 존재 이유 |
| limbs:player_status ↔ limbs:music | overlap flags cos 0.96 | music/radio 에 op:status 2벌 vs 유지 |
| self:mkdir | write 가 부모 폴더 자동 생성(실측) | 중복 원시어 — 이득 작아 관찰만 |

## 5. 함정 (이번 세션 실측 — 반복 금지)

1. **yaml 블록 제거는 정규식 금지, 구조 인식으로.** `\n      [a-z_]+:` 가 tool_json 내부 6칸 키를 삼켜 pc-manager yaml 파손 → git 복원 후 재수술. 빌드의 파싱 가드가 잡아줬다 — 수술 후 즉시 `build --check`.
2. **시딩 = `.venv` 파이썬 + `_load_model_sync()` 선행 + `add_examples_batch`** (시스템 python3 = sqlite_vec 없음, 모델 백그라운드 로딩 중 벡터 미부착). 이관 후 `rebuild_index()`. 검증은 db 자신의 API 로(`search_hybrid` — 반환은 UsageExample 객체).
3. **코퍼스 param 가드**: 증류가 엔진 내부 플래그(`_raw` 등)를 코퍼스에 흘리면 빌드가 막힌다 — 코퍼스 정정이 정답(allowlist 아님).
4. handler 분기 제거 시 **첫 `elif` 고아** 주의(py_compile 로 4개 핸들러 전수 확인).
5. keeper 규약(backend .py 편집 전 `touch data/backend_keeper_off`), tool.json = 파생(직접 편집 금지), `/packages/reload` 는 handler.py 만(tool_*.py 는 backend touch).
6. 커밋은 **pathspec** — 동시 세션 변경이 섞여 있다.

## 6. 검증 체크리스트 (각 은퇴/신설마다)

```bash
python3 scripts/build_ibl_nodes.py && python3 scripts/build_ibl_nodes.py --check   # 전 가드
# 라이브: /packages/reload → /ibl/execute 신어 실측 → /ibl/validate 은퇴어 반려 확인
# 코퍼스: 이관 + 시드(.venv) + rebuild_index + 연상 실측 / 배포 후 grep: 액션명 + tool 이름 둘 다
```

## 7. 상상 훈련 (2026-08-16 신설 — 1회차 실행 기록)

> **취지**(vision.md 언어 철학 §상상 훈련): 실제 명령의 분포는 현 표현력에 검열되어 있다 — 관찰만 따라가면 닫힌 고리.
> 운동선수의 심상 훈련처럼 **복잡한 과제를 상상 → IBL 문장을 실제 조합 → dry-run/실행으로 검증 → 갭의 원장이 산출물**.
> 관문 2: ①문법은 상상으로 벼리고, 어휘는 현실이 인준(상상 갭=후보일 뿐) ②해마 시드는 **실행 검증 통과 문장만**.

### 절차 — **정본 = `data/guides/imagination_training.md`** (2026-08-16 가이드화, guide_db 등록 `id: imagination_training`)
> 요약: `--list-never` 메뉴 → 도메인 접지 과제 상상(6문형 커버) → 조합 → validate 전수 → 부작용 없는 것만 실측(스크래치 원상복구) → 3분류(깨끗/꼬임/불가) → **결과보고서 의무**(`outputs/imagination_training/YYYY-MM-DD_N회차.md` — 갭 원장에 최소 재현·실측 증거·수리성/판정성 구분) → §7에 갭 요약 누적. 훈련 세션은 수리·어휘 신설을 직접 하지 않는다(보고서→대장장이).
> 1회차 보고서: `outputs/imagination_training/2026-08-16_1회차.md`

### 1회차 원장 (과제 10건 — validate 10/10 통과, 실행 프로브 4건)

**갭 (언어 개정 후보 — 사용자 판정 대상):**
- **G1. 통화→파라미터 바인딩 규약 부재** (2건 실측으로 수렴, 이번 훈련 최대 발견):
  - `$변수.field` 필드 추출 없음 — `$위치 = [sense:here]` 후 `{lat: "$위치.lat"}` 는 **전체 JSON 통짜 치환 + `.lat` 리터럴 잔존**(실측). 필드 추출은 each 의 `$it.field` 뿐.
  - 산출물→축적 미개통 — `[table:document]` 가 `{path:...}` 를 정직하게 내는데(실측), 파이프 후속 `[self:notebook]{op:"add"}` 는 그 path 를 안 받고 "path 또는 text 필요" 거절(실측). items→items 변환자 체인만 흐르고, **통화→param 주입은 규약이 없어 핸들러 재량**.
  - 기존 "남은 판정: 통화 조건(언어 개정급)"과 같은 계열 — 함께 판정할 것.
- **G2. 시간 문형의 검수 사각**: validate 가 `each.do` 는 펼쳐 `[each 속]` 으로 보여주는데(08-16 수리), `schedule.do`(pipeline) 는 **안 펼침**(step 1개, 실측). 시간 문형 조합 0회와 정합 — 고유수용감각 없는 곳은 훈련이 안 된다. → 검수기 재귀를 M1 `do` 통일 자리 전부(schedule/trigger/workflow/manage_events/delegate)로 확장.

**마찰 (통화 규격):**
- **F1. records형 vs 표형 칸 규격 불일치**: 다나와(name/price 수치) & 번개장터(title/meta — 가격이 "80만원 · 지역" **텍스트**) union 은 기계적으로 성공하나 sort/비교가 반쪽(실측). rename 으로 못 고침 — **파생 열(derive) 판정에 구체 증거 1건 추가** 또는 sense:used 계열 수치 필드 정비.
- **F2. validate 가 param 이름을 검사 안 함**: `notebook:` (정답 `name:`) 오타 문장을 validate 가 ✓ 통과, 실행 오류도 `"'' 노트북이 없습니다"` (틀린 param 명 지목 없음, _param_hint 는 사용법 전문 재인쇄뿐). **틀린 근육 명령이 조용히 무시되는 팔** — validate 에 스키마 기반 param 대조 경고 후보. (★이 발견 자체가 교훈: 처음엔 "파이프 속 param 소실 결함"으로 오진 → 단독 호출 격리로 반증. 결함 단정 전 격리 필수.)

**깨끗한 조합 (실행까지 통과):** union 5단 체인(T2a — F1 제약부), rename→변수→join(T2b, validate). **시드는 보류** — F1/G1 판정 후 (관문 ②).

**미실측 (validate 만 통과 — 부작용이라 실행 보류):** 이웃 팬아웃 each+channel_send / crypto 조건 알림 / schedule 속 파이프+each(따옴표 2중 중첩 — 시간 문형 실전 시 마찰 예상) / cctv each capture / freelance→spreadsheet / finance groupby→chart.

### 2회차 (2026-08-16 — 보고서 `outputs/imagination_training/2026-08-16_2회차.md`)
- 승격 실측 P1~P3 + 새 과제 7 + 격리 9. 성공 2(N6 변수+union{left,right} 라이브 / N10 ?? 폴백 라이브) — 시드 후보.
- **신규**: F3 파이프에 요약 통화가 흐름(비-_raw 기본 — 수치 칸 소실, 자동 _raw 후보) · F4 emitter 기본 path 비대칭(spreadsheet만 필수) · F5 코퍼스 param 드리프트(navigate_route `to:` 죽은 이름 — 가드 구멍 조사 동반).
- **갱신**: G1 증거 ③(show_map 파이프 items 미소비) · G2 정밀화(goal.strategy는 펼쳐짐 — 사각은 do-나르는 액션들만) · F1 증거 추가(freelance 평점=meta 텍스트 · 제목 칸 name/title 계열 비통일).
- 긍정: filter/sort 오류문이 "사용 가능한 필드 목록" 동반(침묵 실패 수리의 열매), each $it 치환·폴백·이항 문법 3종 라이브 실증.

### ✅ 통합 수리 집행 완료 (2026-08-16 같은 날 — 사용자 판정 7건 전부 승인 → 7/7 라이브 검증)
> 상세=2회차 보고서 부록. **R6** $변수.field 치환(파서+실행기, 정직 실패) / **R1** 검수 재귀 do-액션 5종 확장 / **R2** param 소프트 경고(코퍼스=관용 사전 — 스키마 단독은 94키 오탐 측정으로 기각) / **R5** filter 원천 행 파고들기(★F3 재진단: 자동 _raw 는 이미 있었음 — 기전=카드 투영 vs 원천 행) / **R3** spreadsheet 기본 path / **R4** navigate_route origin 기본값=몸 위치(★F5 재진단: to 는 읽히고 있었음 — 코퍼스 수술 불요) / **R7** 칸 규약 병기(price·rating·title + ibl.md 명문화). build --check·P1~P19 전부 통과. 막혔던 T4·T6·T8·N9·N4·P2·T2a 전부 개통 재검.

### 3회차 (2026-08-16 — 보고서 `outputs/imagination_training/2026-08-16_3회차.md`)
- **중점=시간 문형**(행동 조합 0). 과제 11 · validate **11/11** · 실행 프로브 13(격리 6). 스크래치 전량 원상복구(사용자 트리거 3건 무손상).
- **★B1 신규·최중대(결함)**: `[self:workflow]` 의 `do` 가 **문자열이면 글자 단위로 쪼개져** run 실패 — `steps_total` 이 글자 수와 정확히 일치(11/27/73 세 케이스), **배열이면 정상**. 저장은 멀쩡(get 이 원문 보존), 깨진 곳은 읽는 쪽. `target_description` 은 문자열을 명시 허용 = **문서가 약속한 입력이 코드에서 깨짐**. 아무도 못 밟은 이유=저장본 0건(닫힌 고리의 실례). → 수리성(str 이면 `[do]` 로 감싸기).
- **★F6 신규(마찰)**: 변환자가 보는 층이 갈림 — **filter·sort=원천 행 / select·dedup=카드 투영**. 기전=응답이 `data`(원천)+`items`(카드) 2층 동시 운반, 2회차 R5 가 filter·sort 에만 적용. filter 를 먼저 걸면 items 가 원천 기준 재구성되어 뒤의 select 통과(격리 C·F). → 수리성(R5 동형 확장) + **판정성(정본 층 단일화 = 언어 개정급)**.
- **F7 신규(경미)**: `/ibl/execute` 봉투 비대칭 — 단일 액션=핸들러 원문, 파이프=`final_result` 래퍼. 이번 회차에 훈련자가 2회 오독(격리로 반증) = §3-5 오진 격리 의무의 3회차 실증.
- **G1-③ 재현**: `restaurant >> take >> show_map` 이 "위치 정보가 필요합니다" 로 거절 — 판정 후보에 증거 1건 추가.
- **F1 확장(증거 3)**: legal 시행일이 `meta` 텍스트에 묻힘(정렬 불가) · kosis 원천 열이 카드로 뭉개짐 · performance/exhibit union 은 21열 패딩이나 같은 개념이 다른 이름(`prfpdfrom/prfpdto` vs `startDate/endDate`). → R7 칸 규약 확장 대상=**날짜(시작/종료)·기관/지역**.
- **긍정(이전 수리 검증)**: G2 해소 실증 — trigger `do` 재귀 검수가 **파이프 3단+`each.do` 중첩까지 펼침**(T2 steps 5). cron 해소 정확(`0 7 * * 1`→weekly/월/07:00). pipeline 원문이 중첩 따옴표까지 무손상(1회차 우려 마찰 미발생). select/dedup 오류문이 실제 열 목록 동반 → F6 을 한 번에 격리시킴.

### ✅ 3회차 판정·수리 집행 완료 (2026-08-16 같은 날 — 사용자 판정 4건 승인 → 전부 라이브 검증)
> 원칙 하나로 수렴: **구제를 개별 자리가 아니라 계약 입구에** (B1·F6·G1 셋 다 이 부류).
- **B1 수리**: `run` 진입이 아니라 **`execute_pipeline` 입구**에서 `steps` 문자열을 `[steps]` 로 정규화(관문 `any(isinstance(s,str))` 을 str 자체가 iterable 로 통과하던 것 — "관문<언어" 부류) + `list_workflows` `steps_count` 동형(글자 수 오표시). 라이브: save(문자열 do)→run `steps_total` 11→**1**·결과 정상.
- **F6 수리=(c) 입구 접기**: (a)R5 복사도 (b)정본 층 단일화도 아닌 **`_get_items_for_fields(prev, field_hint)` 신설** — 파고들기를 계약 입구로 접어 filter·sort·select·dedup 이 상속, 새 verb 는 자동 상속(비대칭 생산기 제거). "필드가 items 에 없을 때만" 규약 유지. 라이브: `kosis >> select{org_id}` 통과·순서 무관. (b)정본 층 단일화는 불채택 — 병존 유지.
- **F1 판정: 날짜+위치 채택 / ★기관 기각**(발행기관·소관부처·회신기관=다른 명사, 표준 칸 강제="명사의 자리" 위반. 위치는 시간과 같은 **몸의 축**이라 채택 — here/show_map 정합). 규약: 단일 시점=`date`, 기간=`start_date`/`end_date`(전부 YYYY-MM-DD 병기·원명 보존), 좌표=`lat`/`lng`. 집행: legal `date_keys`(시행일자 우선)+culture 공연/전시 `_attach_period` — 라이브: legal 시행일 정렬·performance start_date 정렬 개통. ibl.md 칸 규약 3·4·5항 명문화.
- **G1-③ 판정=`$items` 집합 참조**(핸들러별 파이프 수용 규약 대신 **언어에 한 번**): param 값 `"$items"`/`"$items.필드"` 를 실행 시점에 **값으로** 바인딩(텍스트 치환 금지=shell-IBL 은퇴 사유 회피), 상한 500행(초과=take 안내 거절), items 부재·없는 필드=정직 에러. `$it`(행)의 짝=집합. + show_map 자기 계약 완결(markers-only 시 첫 마커=중심·마커 정규화·좌표 없는 행 수 정직 신고). 라이브: `restaurant >> take{3} >> show_map{markers:"$items"}` = 마커 3개 지도 1장. 문법 등재: 12_ibl_only.md·ibl.md($items 는 변수 할당 예약).
- 검증: build --check 전 가드·P1~P19 전부 통과·라이브 5종(B1 왕복·kosis select·legal date 정렬·performance 기간·$items 지도)·스크래치 원상복구.

### 4회차 (2026-08-16 저녁 — 보고서 `outputs/imagination_training/2026-08-16_4회차.md`)
- **중점=오후 수리 4건 개통 재검**. 과제 13 · validate **13/13** · 실행 프로브 12+격리 6. 6문형 전부 커버. 스크래치 전량 원상복구(사용자 트리거 3·워크플로 1 무손상).
- **★갭 원장의 이동 실측(수리됨 확인)**: B1→**T4 축적 종단 완결**(save 병렬 합성 문자열→run 실데이터→트리거가 저장본 참조) / F6→kosis dedup+select 개통(3회차 꼬임→깨끗) / F1→공연·전시 **교차 계열 start_date 정렬**(N5 꼬임→깨끗) / $items→둘째 도메인(직방 지도)+`.title` 필드 추출. **goal 이월 프로브**: 등록 즉시 라운드 시작 우려=반증(pending 대기), max_rounds:1·kill 왕복 정상.
- **F8 신규(수리성)**: crypto 가 items 미방출(`data` 단일 dict) — `crypto & crypto >> union` 정직 거절. stock quote 는 1행 items 병기(P4/P11) = 같은 "시세"의 비대칭. 수리=stock 선례 동형 병기.
- **F1-title 증거 2 추가**: performance `prfnm`·commercial `name` — R7 title 병기 미적용 소스. union 후 교차 dedup 불가 실증.
- **F9 신규(경미)**: goal list 기본=cancelled 포함(desc "활성/대기 중"과 드리프트, status:"active" 필터는 정상) + goal 정리 op 부재(스크래치 복구=DB 직접 삭제뿐) — ①desc/기본필터=수리성 ②정리 op=판정성.
- **F10 신규(개선)**: `each` side_effect:true 고정(의도된 보수 — src 주석 실존)인데 검수기가 do 를 펼치는 지금은 "펼친 속 실제 부작용의 OR"로 정밀화 가능. 조회-only each 가 dry-run 초록을 받게.
- **F7 증거 추가**: 블록(if/else)·workflow run 봉투=핸들러 원문 — 훈련자 오독 1회(W3), 격리로 반증(조건 평가는 정확).
- 관찰(기록만): `$items.field`→문자열 param=JSON 배열 직렬화 착지(정직). "줄바꿈 텍스트" 조판 변환자 부재 — 어휘 후보 아님, 반복 관찰 대상.
- 시드 후보 10건(표는 보고서) — 3회차 대기분과 **판정 후 일괄**.

### ✅ 4회차 수리 집행 완료 (2026-08-16 같은 날 — 사용자 승인 → 전부 라이브 검증)
- **F8**: `_attach_quote_items` 가격 게이트를 current_price_usd/krw 로 확장 + crypto_price 경로에 부착(선례 함수 재사용) — 라이브: `crypto & crypto >> union` 2행 + **`crypto & stock >> union` 교차 자산 한 표** 개통.
- **F1-title**: performance(prfnm)·commercial(name)에 title 병기(exhibit 는 이미 보유·수리 불요 실측) — 라이브: `union >> dedup{by:"title"}` 교차 계열 개통. ★잔여 한계(기록): "죽여주는 이야기 [청주]" vs "[청주] 죽여주는 이야기"처럼 **어순이 다른 표기 변형**은 기계 dedup 밖(의미 동일성 판단 필요 — 갭 아님·관찰).
- **F9**: ①list desc 정직화("전체 — 종결 포함, status 필터") ②**delete op 신설**(`[self:goal]{op:"delete"}` — 종결 상태만, 살아있으면 "kill 먼저" 명시 거절. conversation_db.delete_goal + _goal_delete + goal_op 라우팅 + yaml ops + goal.md·교재) — 라이브: 거절→kill→delete→원장 깨끗 왕복. ★가드 실증: op 설명 80자 제한이 빌드에서 잡음.
- **F10**: 검수기 each 라벨 정밀화 — do 를 펼쳐 **속이 전부 read·유효하면 컨테이너도 read**(속을 못 읽으면 보수 유지·trigger/schedule/workflow 는 등록 자체가 부작용이라 제외) — 라이브 5케이스: 순수 sense each=False·notify each=True·빈 do=True·trigger=True·조회 파이프=False. 조회-only each 가 이제 dry-run 초록.
- 검증: build+--check 전 가드·P1~P19·라이브 종단 전부. 스크래치 goal 2건(셸 오류로 이중 등록된 것 포함) delete op 로 정리 — **새 op 가 자기 검증의 청소 도구가 됐다**.

### 5회차 (2026-08-16 밤 — 보고서 `outputs/imagination_training/2026-08-16_5회차.md`, 훈련+수리 통합 세션·사용자 지시)
- **중점=4회차 수리 재검 + table 미조합 편입**. 과제 13 · validate 13/13 · 실행 프로브 15+격리 5. 스크래치 0(전 과제 읽기 전용). **미조합 편입 9종**: merge·flatten·structure(table 5종 중 4 개통)+feed·startup·ledger·classic·radio·neighbor.
- **개통 실증**: F1-title(T2 — union→dedup{title}→sort 7스텝 완주) / F8(T1 통화 층) / F10(T5 — each+crawl 이 dry-run **read 초록**) / **flatten↔structure 합성**(T13 — feed→each crawl→flatten→structure 5단, 문서 IR↔행 통화 왕복 = closure 실증).
- **★같은 세션 수리 6건 전부 라이브 검증**: ①**F1-스냅샷** `_attach_quote_items` canonical 병기(current_price·change_percent·name/title) → 비트코인·코스피가 한 표 같은 칸 ②**F1-naver** `_article_to_item` 에 name(단지명)·price(원)·rent 병기 → **실거래-호가 join 개통**(가경자이: 체결 6.5억 vs 호가 7억/6.3억 — 교재의 rename+변수+join 예문이 처음 실전 완주) ③**F1-molit** 거래금액(콤마 문자열·만원)에 price(원) 병기 → 수치 정렬 ④**F1-date** startup end_date 병기 → 마감순 정렬 ⑤**F8-host** status 1행 items 병기(중첩→평평 수치 칸) ⑥**F2-op** 검수기 op 값 소프트 경고(`ops.values` 대조 — radio search 오호출이 dry-run 에서 미리 소리남).
- **판정성 잔존**: world 통화 층(중첩 복합을 어느 층에서 행으로 볼지) · 발신 문형 실측 방법.
- 관찰: T4 의 0행 join=결함 아닌 데이터 현실(molit 최근 체결 단지와 naver 현재 매물 단지의 표본 교집합 없음 — 격리로 확정, 단지 직조회로 양성 증명) / 훈련자 오진 1(sense:radio vs limbs:radio 노드 축 — 실행 오류문의 op 목록이 격리를 도움).
- ★함정 재확인: 패키지 서브모듈(tool_naver·tool_apt_trade_range)은 /packages/reload 밖 — backend touch 재기동 필요(이번에도 실측).

### ✅ 잔여 판정 2건 확정 (2026-08-16 — 사용자가 장기 관점 선택을 위임)
- **world 통화 층**: snapshot=**접지 않음**(정체=브리핑 한 장 — 목록 질의는 전용 감각이 이미 있고 억지 1행은 거짓 통화) / **trend=items 병기**(일별 시계열=자연 행 — date+경제 지표 평평한 수치 칸, news·중첩은 원형 trend 에 비파괴 보존). 라이브 검증(행은 서나 오늘 스냅샷 데이터 얇음 — Pulse DB 현실, 기전은 정상). "지난 일주일 경제 흐름 차트로"가 파이프에 섬.
- **발신 문형 실측**: **어휘 신설 없음**(훈련 도구를 위해 언어를 늘리지 않는다) — `[self:notify_user]` 자기 수신 1건까지 실측 허용+알림함 REST 정리, `others:channel_send` 등 외부 발신=항상 검수만(이웃에게 닿는 되돌릴 수 없는 행동). 규약=imagination_training.md §3-5 명시.

### 시드·재학습 집행 (2026-08-16 밤 — 사용자 승인)
- **시드 31건 입고**(3·4·5회차 누적 — add_examples_batch 단일 경로·`_load_model_sync` 선행·source=manual_seed·category=imagination_training_r345). 코퍼스 3,243→**3,274**. ★3회차 시드 표의 `[sense:realty]{op:'query'}` 오류는 입고 시 교정(realty 에 op 없음).
- 입고 직후 프로브: 조합 시드 2/5 직행(트리거 참조·ledger), 3/5 는 옛 단발이 이김 → 재학습 흡수 대상(예상 상태).
- ★새벽(05:09) 재학습의 epoch_1~9 잔재(9×423MB≈3.8GB)가 라이브 모델 폴더에 남아 있던 것 발견·정리(절차의 "epoch_* 정리" 단계 누락 — 다음 재학습 시 주의).
- **재학습 완료·채택**(로컬 M4, epoch 5 최적·검증 0.884·조기종료): 사과대사과 게이트 — aggregate 동급(desc-T5 +0.4p·code-T5 +0.0·desc-T1 -1.1p) + **신어휘 프로브 33→35/36(+2: "웹에서 검색해줘"·"해커뉴스" — 잃은 프로브 0)** → 채택. rebuild_index 3,275·명시 재기동·워밍업·keeper 재개·P1~P19 통과. 라이브 translate: "저장한 브리핑 매일 아침"→schedule+workflow run 참조 / "비트코인·코스피 비교"→`&`+table 조합 / "공연·전시 시작일 순"→union+sort — **조합 문형이 번역기에 흡수됨**(세부 param 드리프트는 조종실 dry-run 자가교정 자리). 백업=`ibl_embedding.bak.20260816_223052`(롤백 경로).
- ★재기동 함정 실측 2: ①구 리스너 해제 전 재바인딩=Address already in use(2초 대기 부족 — 죽음 확인 후 기동) ②감시 스크립트의 `pgrep -f`가 패턴 문자열을 품은 자기 자신을 매칭해 종료 오탐(모니터 행).
- **다음**: 지표 재측정은 **실사용 축적 후**(행동 지표=증류만 먹으므로 시드로는 안 움직임 — 새 번역기가 조합을 생산하기 시작했으니 몇 주 관찰) · 6회차는 F8/F1-title 재검 과제 + world trend 차트(Pulse 데이터 두터워진 뒤).

### 6회차 (2026-08-16 밤 — 보고서 `outputs/imagination_training/2026-08-16_6회차.md`, 훈련+수리 통합)
- **중점=미실측 문형 2 + 발신 규약 첫 적용 + 편입 9**. 과제 12 · 실행 14+격리 3 · 스크래치 전량 원상복구(memory 2·알림 1·파일 1).
- **문형 개통**: `??` 폴백 첫 실측(1차 성공 경로) · **case 범위 매칭**("0~50" 적중 분기) · **발신 실측 왕복**(조건+notify 실발사→알림함 REST 정리 — 판정 규약이 실제로 작동, 어휘 신설 0).
- **편입 9**: photo($items 지도 셋째 소비자)·memory·entity(qid)·devdocs·youtube·storage·cctv·agents·download.
- **★같은 세션 수리 5건 전부 라이브 검증**: **B2** memory search 카드에 memory_id 병기(desc 계약 "search 결과의 id"가 끊겨 있었음 — read/delete 사슬 복원) / **F1-위치** cctv `lon`→`lng` 병기(규약 첫 위반 실측, show_map 직결 개통) / **F8-agents** 평평한 행 items 병기(중첩 projects만이었음) / **F8-storage** volumes=items 병기(볼륨별 정렬 개통) / **B3** download UA 부재 403(한겨레 실측)→브라우저 UA+스트리밍 저장.
- 검수기가 두 번 값을 함(유령 액션·오호출 dry-run 차단 — F2-op 수리의 열매). P1~P19 통과·keeper 규약 준수.
- 시드 후보 10건 — 다음 배치(어젯밤 31건 직후라 숙성 후 일괄).
- 잔여 관찰: `??` **1차 실패 유도 실측**(폴백 발동 경로) · world trend 차트(Pulse 축적 후).

### 7회차 (2026-08-16 심야 — 보고서 `outputs/imagination_training/2026-08-16_7회차.md`, 커밋 `d59a478` 직후)
- **문형 개통 2**: `??` **폴백 발동 경로**(1차 DNS 고장→2차 완주 — 6회차는 성공 경로만) · **@몸 라우팅 첫 실측**(`[self:time]@폰-9f2b` → 폰 실행 `_forwarded_to: phone`, 유령 별칭=정직 에러+라이브 노드 목록). bulletin 쓰기 왕복(create 공개주소→delete)·switch·discover·showcase·forage·world-trend 재검 편입.
- **★수리 3+근본 1 (같은 세션)**: **B4** feed가 네트워크 죽음을 "빈 피드 success"로 위장(feedparser bozo 미검사 — 오류/빈 피드/있음 세 상태가 둘로 접힘)→bozo+status 부재=정직 실패 / **B5** discover 전멸의 진범=**재기동 인터프리터**(재학습 채택 후 맨 `python3` 재기동→시맨틱 판정 갈려 **해마 렌트 강등** — search_hybrid 설계상 빈손. start.sh 정본=`.venv` 우선)→침묵 except 정직화+정본 재기동 / **B6** render_html chromium 1208 부재=**B5와 같은 뿌리**(homebrew playwright rev 불일치)→재기동으로 자동 해소.
- ★★교훈(재기동 표준 절차 개정): 모델 교체 재기동은 keeper_off→재기동→워밍업→keeper_on 에 **"인터프리터=start.sh 정본(.venv/bin/python3)"** 을 추가 — 어제 밤~오늘 라이브 해마가 렌트로 강등된 채 돌았다(번역은 렌트 인덱스로 작동해 증상이 숨었음).
- 커밋 게이트 실증: 코퍼스-param 가드가 증류 오염(`_raw` 배관 키)을 커밋 직전 검출 → 증류기 스크럽+오염 1행 정정(커밋에 포함).
- 관찰(판정 후보): contest=Kaggle 단일 소스라 한국어 질의 0건(소스 추가 or desc 정직화) · forage 3층 통화=규약 밖(의도 여부).
- 시드 후보 5건 — 다음 배치.

### 8회차 (2026-08-16 심야 — 보고서 `outputs/imagination_training/2026-08-16_8회차.md`, 커밋 `ba7b10a` 직후)
- **★몸 축 개통 2**: **몸간 자연어 부탁(ask) 첫 완주** — `[others:ask]{to:"폰-9f2b", message:"지금 몇 시야?"}` → 폰 gemini 가 `[self:time]` 컴파일·실행·회신(1.3초). 못하는 부탁(배터리)=**"내 어휘로 수행 불가" 정직 거절** — 명함-부탁 프로토콜 두 얼굴 실측. / **시간 문형 실발화 첫 실측** — schedule 15초 지연이 실제 알림으로 도달(등록 검증만 있던 축이 발화까지 닫힘).
- 편입 6: screen(스크린샷 이미지 봉투)·icon(hidden 도 실행 계약 열림)·board·video 짝(youtube→each info)·channel_read(identity 거절 실측)·folder_note.
- **F11 수리**: folder_note "스캔 데이터가 없습니다" → 행동지시화("먼저 [self:storage]{op:scan}…"). ★서브모듈=backend touch 재기동 필요(함정 재확인).
- 관찰(판정 후보 +3): ①폰 사전에 상태 감각(battery) 부재 — 폰 자기수용감각 판정 ②hidden 액션 실행 계약=의도 확인 ③앱 경로 채널 identity 미배선(channel_read email 거절).
- @몸 감각(here@폰)=라우팅 완주·값은 폰 위치서비스 제약(정직 실패·코드 밖). 시드 후보 5건.

### 9회차 (2026-08-16 심야 — 보고서 `outputs/imagination_training/2026-08-16_9회차.md`)
- **★X1(if 속 파이프) 격리 사슬이 결함 4개를 차례로 벗김 — 전부 같은 세션 수리·라이브 검증**:
  **D1** goal.md 조건 예시 3곳이 낡은 경로(`.current_price` — 실봉투는 `.data.current_price`) → 교정. ★5회차 "조건 평가 정확" 판정은 **오판**(else 실행=거짓의 증거일 뿐 — 낡은 경로가 항상-거짓이었다) /
  **B8** 좌변 읽기 실패=조용한 거짓(`None→False`) — 낡은 경로가 몇 달 산 이유. 비교 연산 시 cond_errors 정직 채널로 예외+경로 힌트(불리언 평가는 None=falsy 유지) /
  **B7** 분기 몸이 파이프면 실행기 크래시(`'list' has no get`) — `_run_branch` 신설(if 참/else/case 공용·깊이 전파) /
  **F12** 검수기도 분기 파이프 미펼침(opaque·steps 1) — `_walk_branch`(조건·case·default 공용, steps 1→2).
  재검: if 참 분기 파이프 완주(뉴스 2)·else 파이프 완주·옛 경로=정직 에러·P1~P19 통과.
- **문형 개통**: case 문자열 값 매칭("Mac" 적중) · `;` 독립 문장(사용률 2.8% 축 실측). 편입 5: blog(시맨틱)·package·cctv·cloudflare·self:ask.
- 관찰(판정 후보): **ask 결과 비통화**(`ask >> take` 정직 거절 — 자연어 응답이라 원리적일 수 있으나 상대 items 승계는 설계 판단) · cctv sources/cloudflare result 목록 items 미방출(경미).
- 시드 후보 5건 — 다음 배치.

### ★10회차 (2026-08-17 — 보고서 `outputs/imagination_training/2026-08-17_10회차.md`) — **문법 축 한 바퀴 완주 선언**
- 남은 미실측 소진: **3항 병렬**(코인 2+지수 1 한 표) · **중첩 each 깊이 2**(검수 7스텝 펼침·실행 내층 결과) · **if 속 goal**(가이드 문형 첫 실측 — 조건 참→등록→kill·delete) · **병렬 가지 @몸**(`[self:time] & [self:time]@폰` — 맥·폰 동시 실행 295ms).
- **B9 수리**: cron `* * * * *`(매분)→`interval_hours: 1`(매시간) **침묵 60배 성김** — 매시간 분기가 minute `*` 미검사. minute `*`/`*/N`=정직 거절+schedule 안내. 회귀(매시 m분·매일) 무손상. trigger 분 단위 실발화=원리적 불가(최소 해상도 시간) — schedule 실발화(8회차)로 레일 간접 검증 수용.
- 의도적 보류: goal 실라운드(활성 에이전트 전제=실사용 영역)·폰 카메라/마이크(사용 맥락 필요).
- **다음 모드**: 회차 반복 종료 → ①6~10회차 시드 일괄(~30건)+재학습 ②실사용 증류 관찰(수 주)→행동 지표 재측정 ③분기별 재점검 회차. (가이드 §6 "같은 갭 재발견=제자리 뛰기" 기준.)

### 11회차 (2026-08-17 — 보고서 `outputs/imagination_training/2026-08-17_11회차.md`) — 미조합 어휘 축 (사용자 지시로 수리 동세션)
- **편입 11**: company(병렬 union 31행)·entity(2항 union canonical)·search_shopping(**문자열 price 수치 강제 filter 정확**)·devdocs(→write 축적)·host(if 조건 좌변)·storage(에러 경로)·switch·manage_events·trigger(**시간 문형 조합 첫 실측** — cron do 파이프 등록→삭제, B9 회귀 무손상)·feed(read)·agents(project 열 평탄 items). 검수 12/12·실측 11·스크래치 전량 원상복구.
- **★B10 수리**: 조건 평가 실패(cond_errors)가 **else 로 위장** — B8이 한 층 위에서 재발(정직 채널이 "분기 미실행"일 때만 발화, else 있으면 영원히 침묵). else 도달 시 cond_errors 있으면 보류·정직 실패. 야생 회귀 I6b가 검출.
- **F14 수리**: 8회차 F11이 get_summary 오류문에 folder_note 지시를 복붙 이식(문맥 불일치) → 중립화. 교훈=오류문 행동지시화는 호출 문맥별로.
- **★판정 3건 같은 날 집행 완료**(사용자 위임 "장기적으로 바람직한 쪽" — 상세=11회차 보고서 판정 절): ①B10-case=`_get_sense_value_checked` 검침판(`_FIELD_MISSING` 표지 — 판정 불능=정직 에러 / 값 null=default 유지, battery 용법 보존) ②union=공유 *유효* 칸 0 → 비차단 경고 앞머리(null-패딩 칸 제외, table·items 공용) ③write 싱크=message(str) 실존 시 산문 정본 추출+`extracted`·동반 items 신고(집안 계약: _emit_items 의 message pop=산문 정본 규약. 변환 뒤·명시 content 회귀 무손상). 라이브 전 경로 검증+P1~P19 통과. ★오진 자백: "핸들러 캐시 스테일"로 오진했다가 dual-emit(devdocs message+items) 가드 정상 차단으로 반증 — /packages/reload 는 handler.py 에 문서대로 작동.
- 시드 후보 9건 — 6~10회차 일괄 배치에 합류.

### ★12회차 (2026-08-17 — 보고서 `outputs/imagination_training/2026-08-17_12회차.md`) — 2배 회차(사용자 지시), 발견 7건 동세션 수리
- 과제 24(11회차의 2배)·검수 24/24·실측 21·스크래치 전량 복구(+8회차 잔재 스케줄 이벤트 1건 추가 청소). 편입 ~20(kosis·exhibit·performance·classic·book·world·messages·neighbor·finance·download·forage·render_html·follow·nostr·sense:phone·cctv·auto_response·limb + table:dedup·flatten).
- **B11 수리**: download 가 코퍼스 교본의 `path` 를 침묵 무시(repo outputs/download 로 뭉개짐 — 교재-실행 드리프트) → path 1순위(상대=프로젝트 기준, write 규약).
- **F15 수리**: 다른 몸 어휘(limbs:phone)를 검수·실행이 "액션이 없습니다"로 거짓 보고 → prune 기록(`_pruned_foreign`)+`pruned_reason()` 로 "폰 전용 어휘 — [others:ask] 로 부탁" 정직화. @몸 반출은 판정 안 함(no-privileged-rails 정합).
- **F17 수리**: 빈손 적대 연쇄 — 0건 입력에 each 실패→고치니 flatten 이 같은 모양으로 또 실패. 둘 다 공허 성공(0건 통화)으로, limit=0·"행 있는데 목록 아님"은 명시 에러 유지. ★교훈: 빈손 계약은 verb 마다 심사 — 하나 고치면 다음 verb 가 기다린다.
- **W-정련(11회차 판정 보정)**: book 의 message="조회했습니다" 스텁을 추출해 실데이터 유실 실측 → v3: items 외 비어있지 않은 dict/list 페이로드 동반 시 추출 안 함(구조 보존). devdocs 추출 유지.
- **F16·F18 소품**: messages 오류문에 op:"inbox" 안내 / manage_events `aliases: event_id: [id]`(trigger 선례).
- 판정 후보: **message 스텁 생산자 전수 감사**(book 부류 — "message=산문 정본" 계약 위반 순찰) 여부. 시드 후보 15건.
