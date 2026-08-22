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
manage_events(§4 스케줄 6형제 설계 태스크로)·agents·self_check·patch(REPAIR 헌법)·forage·
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
5. keeper 표식은 **손대지 않는다**(2026-08-17 개정 — 기계가 세우고 워치독이 회수, 놓쳐도 만료. 상세=CLAUDE.md '라이브 백엔드 편집 규약'), tool.json = 파생(직접 편집 금지), `/packages/reload` 는 handler.py 만(tool_*.py 는 backend touch).
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

### ★사이클 종결 (2026-08-17 — 판정 7건 집행 `5d0b48e` + 시드 51 일괄 + 재학습 채택 `ca3d414`)
- **판정 집행**(사용자 위임 "장기 방향"): contest=desc 정직화(Kaggle 영문 명시·소스 추가 기각) / forage=3층 인지 기억 유지+desc "통화 밖" 명시 / 폰 battery=실수요 인준 대기 / hidden 실행 계약=의도 확정 / **앱 채널 identity=미배선 아님 실증**(시스템 프로젝트[앱모드]로 email 10건 실수신 — 8회차 관찰은 일반 프로젝트 프로브의 산물. 신원 규약: 시스템 프로젝트만 system_ai 부여=의도) / ask 결과=자연어 유지(구조 반출=사전 결합 뒷문) / **message 스텁=생산자 관례 판정**(픽스처 스윕 74액션·의심 13 분석 — 한줄 요약+items는 계약 위반 아님. write 싱크 v4로 종결: 추출=message가 문서 모양[다행 또는 200자+]+items 외 페이로드 없음. 오분류는 항상 JSON 보존 방향).
- **시드 51건**: `scripts/seed_imagination_rounds_6_12.py` — 6~12회차 실행 검증 통과분, 해마 3,326 용례(벡터 누락 0)·ibl_distilled 949.
- **재학습 채택**: 로컬 M4, 5,813쌍·epoch 4 최적(검증 0.878), 백업 `.bak.20260817_090211`. compare 보류 권고를 뒤집은 근거 2: ①회귀 프로브(self:read PDF 표)=desc-공간 인공물 — 코퍼스 인출은 1.000 완벽 ②조합 문장 인출 우세(공연+전시→병렬 union 문장 직행, 이번 사이클의 목적 축). 재색인 3,310·hippo 재수출·keeper_off 재기동·워밍업 완료. 라이브 일반화 실증: "공기청정기 20만원 이하 5개"→filter 4단 변주 / "매주 금요일 저녁 7시"→cron `0 19 * * 5`.
- **다음 모드**: 실사용 증류 관찰(수 주) → `vocab_composition_metrics.py` 행동 지표 재측정 → 분기별 재점검 회차.

### ★실사용 관찰 1 (2026-08-17 — ep1180 홈페이지 갱신, 사이클 종결 후 첫 관찰)

**측정 대상을 바꿔야 한다는 관찰.** 조합률로 재면 ep1180 은 IBL 28문장 중 파이프 1건(3.6%)으로 처참해 보인다. 그런데 그 숫자는 아무것도 말해주지 않았다 — 파고들어 보니 세 층이 순서대로 드러났다.

**① "셸로도 되는 일을 IBL 로 했나"는 무의미한 질문이다** (사용자 판정). IBL 이 존재할 이유는 *셸이 번거롭거나 못 하는 일*을 해내는 데 있다. 셸이 이미 잘 하는 일(로컬 파일 grep·cat·텍스트 파이프)을 IBL 로 옮기는 것은 이득이 없고, 그걸 안 했다고 문법 미사용으로 세면 지표가 거짓말을 한다.

**② 그 기준으로 다시 세면 도구 선택은 옳았다.** ep1180 의 33 호출 분류:
- *셸 대체 불가* 16건 — `limbs:browser`(navigate·screenshot·evaluate) 6 · `engines:image_read` 5 · `engines:web`(build·deploy·check) 3 · `web_site` 1 · `os_open` 1 → **전부 IBL**
- *셸로도 되는 일* 17건 — `self:edit` 5 · `read` 4 · `grep` 2 · `list` 1 + 네이티브 `Write` 2 · `Bash` 3 → IBL 12 / 셸 5 로 갈림(이 갈림은 중요하지 않다)

즉 에이전트는 대체 불가 영역에선 100% IBL, 대체 가능 영역에선 편한 쪽을 골랐다. **정확한 라우팅이다.** 그리고 이번 주행의 오류(엉뚱한 스크린샷)를 잡아낸 것도 셸이 원리적으로 못 하는 `image_read` 였다.

**③ 진짜 비용은 셸-대-IBL 이 아니라 왕복 횟수다.** 실행 단계 362초 / 32 호출 = **호출당 11.3초**. 검증 루프가 이렇게 8왕복이었다:
```
navigate → screenshot → image_read → (navigate >> screenshot) → image_read"아니요"
→ evaluate(scrollIntoView) → screenshot → image_read
```
문법으로는 **3문장**이다(`navigate >> screenshot >> image_read` ×2 + 재시도 1). 5왕복 ≈ **56초** 절감. ★에이전트가 3단 중 2단(`navigate >> screenshot`)까지는 실제로 이었고 한 칸에서 멈췄다 — 조합 능력이 없는 게 아니라 끝까지 잇지 않았다.

**⇒ 지표 제안**: 조합률(전체 문장 대비 파이프 비율)이 아니라 **셸 대체 불가 액션 시퀀스 안에서의 왕복 수**로 잰다. 대체 가능 영역의 문장은 분모에서 빼야 한다 — 거기서 IBL 을 안 쓰는 것은 결함이 아니다. `vocab_composition_metrics.py` 재측정 시 이 분모 정의를 반영할 것.

**부수 발견 — 조합이 안 쓰인 자리가 실은 고장이었다**(둘 다 이 관찰에서 처음 드러남):
- **`table:each` 스칼라 행 불가**(수리 완료 `3a04151`): `{"value": row}` 로 감싸는 자리와 `$it` 치환하는 자리가 어긋나 `{"value":"가","_error":"행에 없는 필드: value"}` 라는 자기모순을 냈다. 목록 각각을 다루는 **유일한** 고차 어휘가 문자열 배열에서 못 쓰였다. 교훈=같은 것을 두 자리가 각자 하드코딩하면 어긋난다(상수 공유로 봉함).
- **`sense:crawl` 오진**(미수리): 자기 홈페이지를 `bot_blocked` 로 거부. 실측하니 **가져오기는 완벽**(200 · 254KB · 본문 11,841자 정상 추출, curl_cffi 0.07초). 원인은 `_diagnose` 의 `_BLOCK_TEXT_SIGNS` 부분문자열 매칭 — 본문의 "그래서 **CAPTCHA**도 없습니다"에 걸렸다. **CAPTCHA 가 없다고 자랑하는 페이지를 CAPTCHA 챌린지로 판정**한 것. 오진 후 불필요한 Playwright 렌더까지 돌아 30초를 쓰고 "봇 차단으로 본문을 가져오지 못했습니다"라는 거짓 사유를 반환했다. 부류=**언급을 존재로 착각하는 부분문자열 판정**(챌린지 페이지는 본문이 거의 없다는 점을 안 봄 — 판정에 길이 조건이 빠졌다).

### 13회차 (2026-08-19 — 보고서 `outputs/imagination_training/2026-08-19_13회차.md`) — 원샷 낱말 첫 행동 조합 + 시간 문형
- 과제 12(검수 12/12)·실측 11+격리 3·스크래치 전량 복구(파일·트리거·`table_since.db` 0행 검증). 지표(훈련 전): 미조합 108/148·파이프 중앙값 3·문형 5(시간 0)·스냅샷 JSON 보존.
- **원샷 3낱말 계약 전부 야생 이행**: struct `_quote` 접지 3/3 / ai `rows_in/out/dropped` 신고 / brief 산문+`_ai` / **trigger.do 안 ai_call이 상위 has_ai_call 로 전파**(시간 문형 관통). 병렬→union→brief·검색→ai→take→write 4단·feed→since(peek 정직)→take·each `$it.url`·중첩 필드 조건(`.disk_root.percent`)+else 전부 완주.
- **B10 검침판 야생 첫 발화**: 추측 필드(`disk_percent`) 조건이 "판정 불능 — else 보류" 정직 실패(거짓 단정 0). 단 오류문에 필드 목록이 없어 자가교정 1왕복 추가 → **F13-4**(수리성 소품: filter/sort 선례 이식).
- **V13-1**(수리성): 통화 미준수 생산자 2건 — `goal list`→`goals` 키·`storage volumes`→`volumes` 키, items 병기 없어 table 변환자 전부 굶음(오류문은 정직). sense:host status=병기 모범. 같은 부류 전수 스윕 여부는 판정.
- **G13-1**(판정성): 분기별 전처리 표현 불가 — `A & (B >> rename) >> merge` invalid(괄호 묶기 부재). 실수요=교차 소스 키 정합(다나와 name vs 번개장터 title, K10 merge 무력 실측=F1 증거 추가). 기존 '괄호 묶기' 판정 대기와 병합.
- **F13-2**(수리성): `A & B >> rename >> merge` 검수 valid 인데 실행에서 rename 이 병렬 봉투 받고 즉사 — 오류문("행 필드 예: []")이 진짜 원인 미지목. 검수 경고("병렬 뒤 첫 변환자는 이항") + 변환자의 병렬 봉투 감지 안내 후보.
- **F13-3**(판정성 소품): sort `order:"desc"` — R2 소프트 경고는 발화하나 **오름차순 결과가 success 로** 나감(의미 반전 부류). `order` 값-해석 별칭 수용 여부.
- 시드 후보 7(K1·K3·K4·K5·K6·K7b·K8, 실행 검증 통과만). 판정 요청 3: G13-1 괄호 / F13-3 order 별칭 / V13-1 병기+스윕 범위.

### ✅ 13회차 판정·수리 집행 완료 (2026-08-19 같은 날 — 사용자 판정 3건 전부 승인 → 5건 수리·라이브 검증)
> 상세=13회차 보고서 부록. **G13-1**=병렬 괄호 분기 파이프 문법 개정: 파서 `_parse_paren_branch`→`{_branch_steps}`(괄호 깊이=중괄호 밖만·단일 step 언랩·단독 괄호/중첩 병렬=명시 에러)+엔진 분기 순차 실행(중간 `_raw`·실패 정직 전파)+검수 `[병렬 i/n · 분기 파이프 j/m]` 라벨+역변환+교재("괄호 묶기는 없다" 조항 개정)·ibl.md 등재. 라이브=K10 실수요 그대로 새상품·중고 가격 비교가 한 문장(분기 rename→merge by name→sort asc→take 5). / **F13-2**=data-ops `_get_items` 병렬 봉투 감지(`_parallel_envelope_shape`)로 items 오인 채택 차단+`_no_currency_error` 병렬 안내(rename 폴백도 공용화)+검수 인접 경고. / **F13-3**=sort `order` 값-해석(desc 우선)+yaml 스키마 등재(경고 소멸). / **V13-1**=goal list·storage volumes items 병기(title 칸 규약·원명 보존)+**`scripts/currency_items_sweep.py` 신설**(fixture 우주 전수 측정 — 같은 부류 상설 스윕). / **F13-4**=조건 판정 불능 오류문에 `_field_path_hints`(최상위+1단 경로) 동반, if 경로를 검침판으로 교체(사유 관통). 검증=build --check 전 가드·파서 자기시험+신규 7케이스·P1~P20·라이브 재검 7종(K9·K11·order·힌트·괄호 개통·비괄호 정직 거절·병렬→merge 회귀). **스윕 결과**: 125 fixture 중 준수 119·깃발 6 — 수리 1(`host#apps` items 병기·라이브 개통) / 판정 후보 4(`host#resources` 복합 봉투·`nostr#profile` 부속 목록·`video#transcript` 페이로드 배가·`video#languages` 이중 목록) / 기판정 준수 1(`forage`=통화 밖 유지).

### returns 선언 드리프트 조사 (2026-08-19 — `scripts/returns_drift_sweep.py` 신설, fixture 우주 125 실측 + 정적 3)
- **[A] 선언 scalar/effect 인데 통화(items) 실측 — 라이브 11건**: others:agents(33행)·sense:host(status 1행)·sense:host#apps(12행)·sense:crypto(1행)·self:limb#list(12행)·self:goal·self:storage(volumes·summary 각 1행)·sense:video#feed/#history(각 5행)·sense:world#trend(3행). **+정적 3건**(fixture 밖): self:read(tables:true 모드={text,table,items} 완전 통화)·table:structure({blocks} document 통화)·limbs:guestpc#list(items 직방출).
- **원인 귀속**: ①과거 통화 축 정정 캠페인(07-28~29)·신설(yttv 08-04)이 **방출은 고치고 선언은 안 따라감** ②**V13-1 병기 수리(08-19)도 같은 드리프트 3건을 새로 만듦**(goal·storage#volumes·host#apps — 병기+선언 갱신이 한 몸이어야 한다는 교훈).
- **[B] 선언 items 인데 scalar 실측 — 1건(약속 위반)**: sense:stock#info={success,data} 단일 dict. 형제 op(quote·crypto)는 1행 items 병기 관례.
- **실행은 안 죽는 이유**: 생산자 직방출+이음매 derive_items(table/blocks→items)가 파이프를 실제로 살림 → 이 드리프트는 실행 결함이 아니라 **선언 신뢰성 결함**. 실제 비용 3: ①건강 단언 사각(순찰은 선언=items 만 통화 단언 — scalar 선언 11건의 items 는 깨져도 GREEN) ②진단 처방 오도(오류문 "returns 선언 확인"·대장장이 진단이 선언을 믿음 — 13회차 K9 진단이 그 사례) ③[B]는 소비자 실제 굶김. 카탈로그엔 returns 미노출이라 모델 직접 오도는 아님.
- **★1차 스윕 오탐 교훈**: fixture 키에 #op 이 없어도 기본 op 이 실행됨 — ops.default 의 op 레벨 선언까지 해소해야(sense:stock 기본 quote=items 를 액션 scalar 로 읽어 오인). 스크립트에 반영 완료.
- **제안(집행 대기)**: ①[A] 14건 선언 갱신(src yaml returns/ops.returns — 안전 축은 side_effect 분리라 무영향, self:limb 는 op 레벨로만) ②[B] 판정: info 1행 items 병기(quote 선례, 권고) vs 선언 scalar 정정 ③read/structure 부류=모드-조건부 통화는 returns 단일 값으로 표현 불가(현행 straggler 관행 유지 권고, 표현 확장은 언어 개정급) ④스윕 상설화(유지보수 번들 합류).

### ✅ returns 드리프트 수리 집행 (2026-08-19 같은 날 — 사용자 승인 "제안대로 다")
- **오탐 정정 2건(정직 기록)**: ①self:limb=스윕 해소 버그(픽스처 코드의 명시 `op:"list"` 를 이름 기반 default(issue=effect)로 오독 — 액션 returns:items 가 이미 정답이었다. 2단계 수리: op-code 해소 추가 후에도 "코드 명시 op 에 op 레벨 선언 없으면 default 의 *다른 op* 선언으로 떨어지는" 잔여 버그 재발견→액션 상속으로 봉합) ②limbs:guestpc#list=귀속 오류(items 방출 647행은 limb list — 이미 items 선언 정합. guestpc list 는 릴레이 봉투=scalar 정합). **실 드리프트=[A] 10건+[B] 1건**.
- **선언 동기화 7어휘**(src yaml — others:agents·sense:crypto 액션 returns items / self:goal#list·sense:world#trend·self:storage#summary+volumes·sense:host#status+apps·sense:video#feed+history 는 ops.returns): 전부 실측 주석 동반.
- **stock#info items 1행 병기**(quote·crypto 관례, data 키 보존) + **NaN/Inf 위생**: 검증 중 yfinance 간헐 NaN 이 FastAPI(allow_nan=False) 500 을 내는 잠복 결함 실측 — 정직 null 로 봉합(병기와 무관하게 터질 부류였음).
- **상설화**: `run_maintenance_bundle` §8.5 신설 — 주간 카덴스(`data/returns_drift_state.json`)·subprocess(무접촉)·`@@RETURNS_DRIFT@@` 마커 회수·self_checks `returns_drift` 기록. 첫 실기동으로 배관 전체 검증(125 실측·마커·기록·카덴스 스탬프).
- 검증: 해소 단위 13케이스 전부 items 정합(=다음 주간 런 드리프트 0 예상)·stock info 파이프 select 라이브·build --check 20 가드.

### 14회차 (2026-08-20 — 보고서 `outputs/imagination_training/2026-08-20_14회차.md`) — 미조합 짝 개척 + 13회차 수리 열매 야생 검증
- 12과제(검수 12/12·실행 11+격리 6): legal·kosis·book·freelance·restaurant·radio·notebook·performance·exhibit 미조합 짝 개척. 시간 문형(trigger cron+do 안 feed→since→notify 검침 3단)·적용(each)·조건(weather 중첩 필드)·`;`·`$변수` 커버. **이중 괄호 분기** `(A>>rename) & (B>>rename) >> union` 야생 완주(G13-1 개정이 설계보다 넓게 작동).
- **F14-1(침묵 — 수리성·우선 권고)**: each 내부 `$` 치환이 미정의 변수/없는 필드를 **빈 문자열로 침묵 치환** → 빈 쿼리 하류 실행이 `_ok:true` success(`as` 지정 시 `$it`=유령 변수 무경고). 문장 간 `$st.items.0.x` 치환은 정직 실패+필드 힌트로 **같은 `$` 치환이 두 규율** — each 쪽을 정직 규율로 통일 제안. silent-clamp 부류.
- **F14-2(수리성 소품)**: flatten `keep` 미실존 필드 침묵 무시(dedup 힌트 이식 제안). **F14-3(판정성)**: 상대경로 기준 불일치 — write=프로젝트 outputs / notebook add=backend cwd. **F14-4(수리성)**: table:structure 재시도 부재(간헐 LLM JSON 잘림 실측)+**ai_call 고지 누락**(매 실행 모델 호출인데 has_ai_call=false — oneshot_facade 이전 세대, 같은 부류 전수 감사 제안). **V14-1(판정성 소품)**: radio_favorite 통화 비소비+korean 행 stream_url 부재. **B14-1(깃발)**: sense:world economy 빈 dict + pulse_log 0행 — 경제 수집기 정지 의심(대장장이 진단 대상).
- 긍정: 13회차 수리 5건 전부 야생 실증(괄호 분기·order:"desc"·조건 필드 힌트·dedup 힌트·병렬 봉투 — I11/I7/I4a/P3) + $변수 인덱스 경로 `.items.0.필드` 지원 확정(실패 시 행 필드 힌트). 시드 후보 11건(승인 대기). 스크래치 전량 원상복구.

### ✅ 14회차 판정·수리 집행 완료 (2026-08-20 같은 날 — 사용자 판정 3건 전부 승인 → 수리 5건+진단 1건, 상세=14회차 보고서 부록)
- **R-F14-1**(ibl_executors): each 진범 2겹 재진단 — 정직 코드는 있었으나 ①필드 정규식 `[A-Za-z_]` 전용=한글 필드 매칭 밖 ②`as` 지정 시 `$it`=패턴 밖 유령 변수. 수리=패턴 유니코드화+`_each_foreign_vars`(해석 불능 `$이름` 문장 단위 즉시 거절, `$items`·자기 할당 제외)+행 오류에 필드 힌트.
- **R-F14-2**(data-ops): flatten keep 전무=오류+필드 힌트 / 일부 전무=`keep_missing`+warning.
- **R-F14-3**(notebook): add 상대경로=프로젝트 기준(집 규약 합류)→저장소 루트 폴백, 실패 시 시도 경로 명시. yaml desc 명기.
- **R-F14-4**: structure→oneshot_facade 이관(facade `role` 매개변수 신설 — 기존 경량 축 보존, 축 변경=판정감). ★동반 수리: `ingest_engine._strip_json`이 `[` 위치 무관 우선이라 {title,blocks:[…]}에서 blocks만 뽑던 드리프트→위치 우선+폴백. ai_call 고지 3어휘(structure·self:ask 액션 / notebook **op 레벨 신설** `ops.ai_call:{ask:true}` — api_ibl `_resolve_op` 해소+빌드 검증기 op 축 합류). ★경계 판정 기록: engines 미디어 생성기는 의도적 제외(🎨 아이콘 계기가 포털 대여 중 — 플래그=즉사).
- **R-V14-1 오탐 정정**(정직 기록): add는 이미 station_id(권장)+aliases(url·title) 완비 — 진범=코퍼스 편향. 수리=station_id 파이프라인 시드 3건(벡터 부착)+오염 행 제거(id 2925 `op:"삼성전자"` 유령 op). 라이브 왕복 개통.
- **B14-1 진단 완결+수리**: economy·weather 공백의 진범=`_exec_tool` 죽은 이름 2건(yf_stock_price→stock_op{op:quote} / get_api_ninjas_data→get_weather) — **08-05 "직접 도구 호출은 grep에 안 걸린다" 함정 재발**. 재배선 후 라이브 economy 7지표+weather 수집. pulse_log 0행=06-28 정기 수집 폐지의 휴면 잔재(save_pulse·_collect_world_delta 호출자 0 — 유령 테이블, 정리=판정감).
- 검증=build --check 전 가드·P1~P20·ai-ops 배터리 25/25·each 스칼라/flatten/dedup/병렬 회귀·포털 게이트(structure 거부·weather 대조). ⏳커밋·시드 후보 11건(별도 승인)·재학습 대기열·판정 후보 2(engines ai_call 경계·pulse_log 정리).
- **15회차 (2026-08-20)** — 중점=문형 '시간'(행동 조합 0회). 과제 11건 전수 validate 통과, 실측 11건.
  - `B15-1` **발견/수리대상** — 변환자가 비-통화 봉투를 침묵 무변환 통과: `[self:trigger]{op:"list"} >> [table:take]{n:1}` 이 success:true 로 **전체** 반환(filter 도 동일). 대조군 `[sense:host]{op:"resources"} >> take` 는 정직 거절 → 규율이 봉투에 따라 갈림. "골라서 알림"이 전량 발송이 되는 부류.
  - `B15-2` **발견** — `table:since` 첫 호출이 baseline 을 삼켜 0행(feed·realty 양쪽 확정). 트리거 첫 실행 침묵. 창고 폴러 `seed` 선례 제안.
  - `V15-1` **판정대기** — 디스크 여유공간이 items 통화로 나오는 경로 부재(storage volumes=칸 없음 / host resources=통화 아님).
  - `F15-1` **판정대기** — if/case 응답이 선택 분기·좌변값을 안 보고(`{"result":...}` 뿐, success/steps 없음).
  - `F14-1` **수리됨 확인** — each 내부 치환이 정직 실패+필드 힌트로 전환.
  - 오진 격리 1건: "since 가 같은 행을 반복 통과" → `since_seen` 키=URL 안정, 시각별 적재 +30/+2/+2 로 **진짜 새 URL**임이 확인돼 반증. 남는 사실=회전 창 소스에 since 를 걸면 알림이 잦다(소스 성질).
  - 보고서: `outputs/imagination_training/2026-08-20_15회차.md`
- **16회차 (2026-08-20)** — 중점=축적·적용 문형 + 순수 미조합 짝 개척(goal·webapp·script·render_html·notebook each·book&classic). 과제 12(검수 12/12)·실측 11+격리 5·스크래치 전량 복구.
  - **개통 ★**: 검색→brief(HTML)→`$카드.message` 문장 간 반출→render_html PNG 4단 사슬(engines:render_html 첫 행동 편입 — 여러 줄 HTML 페이로드가 $변수 값-바인딩으로 무손상 통과=shell-IBL 은퇴 사유의 반대 실증) · `$위치.lat/lng`→restaurant 새 짝 · notebook list→each sources · 조건 양분기 실측(else 정당성 격리+반전 알림 실도달) · **schedule.do 안 ai_call 상위 전파 확인**(F14-4 부류 건강) · 괄호 분기 rename 우회 야생 재실증(G13-1).
  - `F16-1` **수리됨** — if/else 중괄호 누락의 두 실패 경로 모두 정답 형태 힌트 동반(오도 처방 제거). 라이브 검증.
  - `F16-2` **재진단 후 수리됨** — 진범=finance 아닌 **groupby**(`_rows_for_field` 가 빈 리스트를 후보 제외 → 통화 실존·0행과 통화 부재가 접힘. finance 는 items:[] 기병기=오진 격리). 빈손=0행 흐름·비통화=정직 거절 유지. F17 잔여 verb 소진.
  - `F16-3` **수리됨** — script list 에 `last_status`·`last_run` 칸 병기. `filter{last_status=='error'}` 라이브 1건 적중.
  - `F16-4` **수리됨** — book(정보나루 단일 관문+gbooks) title 병기. rename 없이 `book & classic >> union >> dedup{title}` 완주.
  - `V16-1` **오탐 정정** — lecture list 는 items 기병기(500자 절단 출력 오독 — 키 부재 단언은 전체 봉투로). 수리 불요.
  - `V16-2` **판정·집행 완료** — material **list op 신설**(원장은 자기 list 를 가진다). items에 exists 파일 실존 pre-flight 동반, ops.returns/side_effect/exempt 동시 선언. `list >> take >> each` 문형 개통. 액션 148 불변.
  - **차단기 판정·집행 완료** — 파라미터를 바꾼 **교정 호출은 open 창당 1회 즉시 허용**(`_params_sig`+`trial_used` — 동일 호출 반복 차단은 보존, 교정 시험 실패=재-open 후 그 창 봉쇄). 라이브 전 경로 검증.
  - 관찰: F7 봉투 비대칭 3·4번째 오독 표본(단일 액션=final_result 키 없음 — 훈련자도 반복해 밟음).
  - 검증=build --check·파서 자기시험·P1~P20·ai-ops 25/25. 시드 후보 7건(승인 대기)·⏳커밋·재학습 대기열. 보고서: `outputs/imagination_training/2026-08-20_16회차.md`(부록=집행 상세)
- **17회차 (2026-08-20)** — 중점=순수 미조합 개척(patch·switch·follow·channel_read·crypto·freelance·host·output) + 15회차 수리 야생 검증. 과제 12(검수 12/12)·실측 11(격리 5)·스크래치 전량 복구(파일·트리거·알림).
  - **개통 ★**: patch status>>take(자기수리 원장 첫 조합) · host resources>>filter{free_gb<100}>>select(**V15-1 수리 야생 확인** — items+거울 키) · trigger list>>filter(**B15-1 수리 야생 확인** 2표본: patch·trigger) · freelance gigs&experts>>union>>sort>>take 5단 자기결합(rename 불요 — experts title 기병기) · crypto ?? search 폴백 양경로(성공+유령 코인 발동) · trigger create(cron→weekly 해소)→검증→delete 왕복 · if/else host 조건 양분기 실발화(else 정당·알림 도달).
  - `F17-1` **발견(수리성)** — 프로젝트 컨텍스트 채널 2중 비대칭: 문장 param project_id는 each/가지 **미전파**+일부 액션(patch)선 "문서화 안 된 키" 경고(요구하며 나무람), body project_id는 each 안까지 전파(격리 실측). 오류 처방이 param 채널만 안내 — 처방대로 하면 each에서 또 죽음. 제안=오류문에 body 채널 병기+공용 컨텍스트 키 검증 면제.
  - `F17-2` **발견(수리성 소품)** — `??` 전 가지 전멸 시 마지막 가지 오류만 남고 1차 실패 사유 소실(`_branch_errors` 병기 제안).
  - `F17-3` **발견(판정성 소품)** — $변수 값-바인딩이 봉투째 문자열화(write 파일에 success 키까지 박힘) — 파이프 v4 추출 계약과 비대칭.
  - `V17-1` **판정대기** — 자가점검 **결과 조회** 어휘 부재(sense:self_check=실행 effect만, 결과=REST 전용) — "실패 항목만 알림" 표현 불가. 수요 실증=self_check_pattern 알림이 이미 흐름. 제안=op:results(items) — V16-2 "원장은 자기 list를 가진다" 선례.
  - `F15-1` 증거 추가(3표본째: if/else 응답에 분기·좌변값 없음) · **8회차 관찰③ 좁혀짐** — channel identity는 body agent_id로 완주(배선 실존, 갭=직접 경로 기본 신원 부재 — 판정성).
  - 검증=validate 전수·실측 격리·발신 규약 준수(notify 자기수신 1건 후 정리). 시드 후보 8건(승인 대기)·⏳판정 4건. 보고서: `outputs/imagination_training/2026-08-20_17회차.md`

### ✅ 17회차 판정·수리 집행 완료 (2026-08-20 같은 날 — 사용자 판정 "제안대로 다" → 수리 5건+시드 9건, 상세=17회차 보고서 부록)
- **R-F17-1(a)** 컨텍스트 오류문에 body 채널 병기(system_tools·ibl_routing 두 발생지) / **R-F17-1(b)** `_CONTEXT_KEYS={project_id, agent_id}` 어휘 검사 면제(ibl_param_vocab — 요구하며 나무라는 자기모순 해소).
- **R-F17-2** 폴백: 가지별 실패 사유 attempts 보존+전멸 시 `_branch_errors`+발동 시 `_fallback_used` — ★핸들러 대다수=JSON 문자열 반환이라 dict 검사만으론 마커 안 붙음(실측)→문자열 봉투도 파싱·마킹.
- **R-F17-3** bare `$var` 치환 v4 추출 합류(`_v4_var_payload` — message/items 우선·폴백=봉투·명시 경로 불변). 교재 `$변수→join{left,right}` 회귀 무손상 실측(join `_get_items`=bare 리스트 수용). ★한계: 무 message·무 items 봉투(folder_note 빈 주석)는 봉투 유지 — 그 액션의 통화 문제로 분리.
- **R-V17-1** self_check op 패턴화(run|results) — results=self_checks DB items 투영(limit 50·상한 500), fixture 등재. 라이브 `results >> filter{success==false}` 실패 1건 적중(returns_drift 깃발 — self:limb 별도 진단감).
- **R-신원** /ibl/execute 기본 agent_id=system_ai 전 직접 호출 확장(8회차 관찰③ 종결) — 도달 경로 전부 소유자 게이트 뒤.
- 검증=build --check 20 가드(액션 148 불변)·P1~P20·ai-ops 25/25·py_compile. **시드 9건**(후보 8+V17-1 개통 시드 1, tags=imagination-round17, 벡터 누락 0, 코퍼스 3,432) — T8은 보류 유지(body 채널이 정본). ⏳커밋·재학습 대기열.
- **17회차 사이클 종결 (2026-08-20)**: 수리 배치 커밋 `4675fce` push(층 가드·침묵 클램프 가드가 집행 코드를 2회 잡아 교정 — self_check results=_cap 의존 역전·limit 클램프 신고) + **재학습 채택**(epoch 7·검증 0.864, 코퍼스 3,436 — A/B aggregate 전 지표 동급 이상, round17 시드 파이프 번역 직행 실증). 관찰 항목: "네이버 블로그 후기"(무주제 표현) 경계 임베딩 기움 — 대조 시드 2건 보강, 근본 레버=하이브리드 결합.
- **야생 관찰 (2026-08-20 저녁, ep1325~1329 에피소드 분석 — 수리 대기)**: `B-crawl-struct` — **crawl >> struct 대표 용례가 죽어 있다**: crawl 봉투가 본문 text 와 함께 items(링크 목록)를 병기 → struct 통화 감지가 "입력이 이미 items 통화입니다" 거절. 핸들러 자신의 주석("파이프 본문(예: [sense:crawl] 결과)")과 모순. ep1325 실전에서 에이전트가 소스 직독(grep 6·read 5)으로 진단 후 `crawl >> write /tmp` → `struct{file}` 2문장 우회(라운드 419초). 라이브 최소 재현 확정. 수리 방향=struct 파이프 입력에서 text-본문 봉투(text 있음+items=부속) 우선 소비. 부수 관찰: world_bank param 계약을 handler 역공학으로 알아냄(F1 desc 부류)·어휘 탐색이 discover 아닌 ibl_nodes_src grep 동선·`_raw:true` 라이브 6회.
- **✅ B-crawl-struct 수리 완료 (2026-08-20 같은 날 — 사용자 지시)**: `_struct` 파이프 입력이 본문 병기 봉투(text=본문+items=부속)에서 **본문을 원문으로 채택**, items 는 note 로 신고(침묵 변형 금지). 거절은 쓸 본문이 없거나 요약 한 줄뿐일 때만(문서-모양 게이트 = write v4 동일 규율 — 오분류는 거절 쪽). yaml target_desc 동기화. 검증=ai-ops 배터리 25/25·라이브 양방향(crawl>>struct>>take 3단 완주+note / webapp list>>take>>struct 거절 보존·오류문에 본문 조건 안내 추가)·build --check 20 가드. 시드 1건(crawl-struct-seam-v17). ★handler.py 수리라 /packages/reload 로 라이브. ⏳커밋.
- **✅ 수리 신호 보고 의무 교재 등재 (2026-08-20 — 사용자 제안)**: 12_ibl_only.md Key Principles 8 신설 — "문법·파라미터가 맞는 문장이 실행에서 거절·실패하면, 우회해서 일을 끝내더라도 최종 응답에 그 문장과 오류문을 그대로 보고하라(조용한 우회는 언어의 구멍을 숨긴다). 오류문이 교정을 안내하면 그건 화자 실수 — 교정 재시도가 먼저." ep1325(crawl>>struct 419초 침묵 우회)가 계기 — guide_feedback '쓴 놈이 고친다'의 앞 절반(발화 의무)을 교재에 박음. 라이브 확인=프롬프트 빌더(mtime 캐시)·번역기 spec 양쪽 포함. 교재-가드 통과. ⏳커밋·실효 관찰(다음 에피소드 분석 때 침묵 우회가 보고로 바뀌는지).
- **18회차 (2026-08-22)** — 중점=문형 '축적'(행동 조합 1회로 최저) + 계산 어휘 개척(compute·reduce 둘 다 미조합). 과제 13(검수 13/13)·실측 11+격리 7·스크래치 전량 복구(notify 는 규약 1건 대비 2건 발화 후 전량 삭제 — 같은 문장 재실행분)(플레이리스트·노트북·트리거·xlsx·알림).
  - **개통 ★**: `table:reduce`·`table:compute` 첫 행동 편입(realty 90행→287.6억 / 평당가 파생 열) · **compute 식 안에서 문장 간 `$변수` 참조 작동**(`$합 = …reduce` → `compute{set:{비중: "price / $합.value * 100"}}` = 집계값→행별 비중 2문장 관용구 개통) · music library→each playlist_add 축적 완주(+**스필 자동 발동** 328KB>200KB, each가 참조를 투명하게 읽음) · storage volumes→each folder_note · entity resolve→each detail · researcher find→each coauthor · notebook 축적→인용 답변→삭제 왕복 · trigger do 안 compute+since 4단이 검수에서 steps 5로 펼쳐짐(G2 해소 재확인).
  - `F18-1` **발견(수리성)** — 봉투 `columns` 신고가 `KEYS_MAX=12` **침묵 클램프**(`ibl_envelope.py:60`). `sorted()`가 ASCII→한글 순이라 **한글 열과 방금 만든 파생 열이 먼저 잘린다**(실측: 실제 14키 중 `층`·`평당가만원` 소실, 행 1건이어도 재현). columns 는 AI 가 다음 step 필드를 고르는 눈 — 파생 열이 안 보이면 없는 줄 안다. 제안=절단 신고 또는 파생 열 우선 정렬.
  - `F18-2` **발견(수리성·우선)** — `_untransformed` 자백(2026-08-20 판정된 설계)을 **write 싱크가 안 읽는다**: `trigger list >> filter >> write` 가 필터 밖 항목(WorldPulse)을 파일에 그대로 박음(2,132자 실측). 변환자 쪽은 정직(거울 키 `triggers` 동반 변환·형제 `existing_schedules` 자백) — 구멍은 소비자 쪽. B15-1("골라서 알림"→전량 발송)의 저장판. 제안=싱크가 `_untransformed` 키 제외 또는 경고 병기, emitter 동형 여부는 판정감.
  - `V18-1` **발견(수리성)** — `[self:workflow]{op:"list"}` 통화 미방출(봉투 `['count','workflows']`, items 없음 → take 정직 거절). 16회차 V16-2 "원장은 자기 list 를 가진다" 미적용 자리이자 **축적 문형의 심장**(3회차 B1 이 났던, 저장본 0건이라 아무도 안 밟는 그 구간).
  - `V18-2` **발견(수리성)** — 자가점검 **경보의 근거에 어휘로 도달 불가**: 알림은 "만성 실패: self:workflow" 인데 17회차 신설 `[sense:self_check]{op:"results"}` 로 500건 훑어 0건. 진범=원장 이원화(results=`self_checks` 투영 / 만성실패 판정=`action_health`, world_pulse_health.py:817). 훈련자는 DB 직독으로만 근거 도달. 제안=results 에 source 파라미터 또는 두 원장 통합 투영.
  - `B18-1` **발견(수리성)** — **자기시험 픽스처의 의도된 실패가 건강 원장을 오염**: 재귀 깊이 상한 시험(`_t_rec_chain0…5`)의 실패 4건이 `action_health` 에 `source='usage'` 로 적재되어 거짓 "만성 실패" 경보 생성(같은 날 실사용 2건은 success=1). 제안=`source='test'` 분리 또는 `_t_` 접두 집계 제외.
  - `F18-3` **발견(소품)** — 훈련 메뉴(`--list-never` 115건)에 `prompt_hidden: true` 어휘 2건(engines:icon·newspaper) 포함 = 훈련자가 카탈로그에서 볼 수 없어 **상상 자체가 불가능한 도달 불가 바닥**. 제안=메뉴에서 제외 + "도달 가능 미조합 113" 병기.
  - `F15-1` **4번째 표본** — `[if:]` 응답에 분기·좌변값 없음(`{node:"if", keys:[success, delivered_to_launcher]}`). 오늘 else 판별의 유일한 근거가 "두 분기 알림 문구를 일부러 다르게 씀"이었다. 조건 문형 고유수용감각 부재와 조합 3회가 정합.
  - 관찰(결함 단정 안 함): 자가점검 원장의 실패 2건(`golden_pipes: paper>>take>>document`·`silent_failure_regression rc=1`)이 **원문 재실행에서 둘 다 통과** → 일시 블립 판정, 결함 미등재 · `self` 노드가 프로젝트 컨텍스트 요구(단 **R-F17-1 오류문의 body 채널 안내가 훈련자를 실제로 즉시 구제** — 수리의 열매 실증) · groupby 봉투 `shape:"effect"` 신고 드리프트(소비는 정상).
  - 시드 후보 8건(승인 대기)·판정 요청 4건. 보고서: `outputs/imagination_training/2026-08-22_18회차.md`
  - **수리(2026-08-22, 대장장이 세션)** — 원장 4건 전수 재현 확인 후 수리, 각각 수리 후 실측으로 증상 소멸 확인:
    - `F18-1` **수리됨** — 절단 신고(`columns_truncated`/`columns_total`)를 `ibl_envelope._clamp_names` 로 도입, `keys`·`columns` 양쪽 적용. **부류 단위 확장**: 같은 침묵 절단이던 필드 힌트 2자리(`ibl_executors.py` each 행 필드, `workflow_engine.py` $변수 경로)도 `…외 n개` 로. 실측: 14열 입력 → `columns_truncated: 2`·`columns_total: 14`.
    - `F18-2` **수리됨(제외안 채택)** — write 파이프 싱크가 `_untransformed` 키를 저장에서 제외하고 `excluded_untransformed` 로 신고. 실측: 원 유출 봉투 재저장 시 2,132자→1,413자, `existing_schedules`·`WorldPulse` 소멸, `items`·`triggers` 1건 보존. ※emitter(document·spreadsheet) 동형 적용은 미착수(판정감으로 남김).
    - `V18-1` **수리됨** — `workflow list` 가 `items` 병기(`items is workflows` 동일성 → 거울 키 판정 동반 변환). `self.yaml` `ops.returns.list: items` 선언 동반, 삼각 검증 통과.
    - `B18-1` **수리됨(프로세스 정체 판정)** — `pulse_db._in_test_process()`(pytest 로드 또는 진입점 `test_*.py`)로 시험의 의도된 실패를 `source='test'` 로 격리. 픽스처 이름(`_t_`) 대신 프로세스로 판정해 **모든 시험 스위트가 한 번에** 격리된다. 실측: 임시 DB 적재행 `source='test'`. ※기존 오염행 115건은 미삭제(7일 창 밖으로 자연 소멸).
    - `V18-2`·`F18-3` **수리 안 함** — V18-2 는 액션에 새 파라미터(`source`) 추가 = 어휘 확장이라 판정 대상, F18-3 은 훈련 도구(`vocab_composition_metrics.py`) 소품으로 코어 오작동 아님.
- **19회차 (2026-08-22)** — 중점=문형 '조건'(행동 조합 3회). 과제 14(검수 14/14)·실측 13+격리 8·스크래치 복구(forage note 966 forget, notify 0건). 지표: 미조합 115→113(**도달 가능 111** — F18-3 수리가 처음 인쇄), 조합 27→29, 조회 15→17, 축적 1 불변.
  - `B19-1` **발견(결함·우선)** — **`table:filter` 문자열 where 가 워드 연산자를 침묵 강등**: `contains`·`in`·`matches` 가 연산자로 파싱되지 않고 **문장 전체가 전-필드 substring 검색어**가 되어 조용히 0건(실측: `"아파트명 matches 자이"` 0건 vs 구조형 `{field,op,value}` 7건 / `"title contains workflow"` 0건 vs 구조형 2건). 기전 ①`_CMP_RE` 가 `>= <= > < == != =` 만 파싱, 나머지는 else 의 전-필드 substring ②구조형도 `_OPS.get(op, _OPS["=="])` 라 **모르는 op 은 침묵 `==` 폴백**(`matches` 는 `_OPS` 에 없음). 아픈 이유: 액션 target_description 이 `op=…/contains/in` 을 약속하는데 **모델이 압도적으로 쓰는 문자열 형태에서 그 약속이 안 지켜지고**, 같은 몸의 `[if:]` 조건 언어는 `matches` 를 워드 연산자로 지원해 **두 조건 언어의 문법이 갈린다**. `_match` docstring 이 "침묵 부분일치로 삼키지 않는다"고 의도를 적어 뒀으나 비교 연산자에만 적용됐다. 제안=워드 연산자 `_CMP_RE` 합류 + 모르는 op 정직 거절(지원 목록 동반), `matches` 합류는 판정감(두 조건 언어 통일 여부).
    - ★**18회차 소급 정정**: V18-2 최소 재현선이 `where: "title contains workflow"` 였다 — 그 0건에 이 침묵이 섞여 있었다. V18-2 판정 자체는 sqlite 직독으로 독립 확인돼 유효(수리 후 `source:"usage"` 로 80건 도달이 증거).
  - `B19-2` **발견(결함)** — **`items:` 파라미터 직접 주입을 reduce·brief 가 안 받는다**. 어휘가 "items(앞 통화 없이 직접 줄 때)"를 약속하는데 `[table:reduce]{items:"$r.items"}` 거절, 에러문이 **자기모순**("찾지 못했습니다. 받은 봉투: ['items']"). 대조군: `[table:take]{items:"$r.items"}` 통과(치환은 되고 있다·data-ops 계열은 읽음) · 파이프 경유 reduce 통과 · `[table:brief]{items:…}` 는 items 를 아예 안 봄(">> 파이프로" 안내). 기전=`ibl_control_blocks.py:357` `_each_input_rows` 가 문자열 페이로드 미수용 — **`ibl_executors.py:989` 주석에 같은 부류 선행 수리 기록**(리터럴 `items:[...]` 가 "받은 봉투: str" 로 거부되던 건)이 있는데 `$변수` 치환 경로까지 안 왔다. 3회차 B1("문서가 약속한 입력이 코드에서 깨짐") 부류. 제안=선행 수리 동형 확장 + 에러문에 받은 것의 타입·길이 명시. brief 의 items 부재는 문서/코드 정본 판정.
  - `F19-1` **발견(마찰)** — `[case:]` 가 매칭 정보를 안 낸다(`{"result": …}` 뿐). **`[if:]` 는 이제 `matched`·`matched_value` 를 낸다 = F15-1 이 if 쪽에서 닫힌 것 확인**(15·16·17·18회차 4표본의 해소) — 같은 조건 문형 안에서 두 블록의 신고 수준이 갈린다. 제안=if 규약 case 동형.
  - `F19-2` **기록** — F7 봉투 비대칭 **5번째 오독 표본**: 단일 액션엔 `final_result` 키가 없어 훈련자가 finance·nostr 를 "빈 봉투"로 2회 오진 → 원문 대조로 반증(둘 다 정상). 훈련자가 반복해 밟는다는 것 자체가 신호.
  - 긍정(어제 수리 야생 검증): **V18-2**(`source:"usage"` → self:workflow 실패 80건 도달, 수리 전 0) · **F18-3**(메뉴 "도달 가능 111 · 비노출 2 제외") · **F18-1**(`columns_truncated:1 · columns_total:13`) · V16-2(goal·switch·board·follow items 병기) · each 빈손 정직("입력 0행 — 실행 0회") · case 소스 오류의 필드 목록 힌트(1회 교정으로 통과).
  - 관찰(판정 후보) — **훈련 실측이 지표를 못 움직인다**: 18회차가 축적 문형에서 reduce·compute 를 실제 조합했는데 오늘 축적 여전히 1이고 두 어휘가 미조합 목록에 그대로. 증류는 에이전트 주행 경로에서 일어나고 훈련은 `/ibl/execute` 직접 호출이라 안 담기는 것으로 보인다 — 가이드 §6("성공의 척도=회차 간 지표 이동")이 훈련 자체를 반영 못 하는 구조.
  - 시드 후보 5건(승인 대기) — ★B19-1 이 살아 있는 동안 **문자열 워드 연산자 문장은 시드 금지**. 보고서: `outputs/imagination_training/2026-08-22_19회차.md`
  - **수리(2026-08-22, 대장장이 세션 — 원장 5건 전건 처리)** — 각 항목 원 재현선을 다시 실행해 증상 소멸 확인:
    - `B19-1` **수리됨** — where 미니 DSL 이 **워드 연산자를 기호 연산자와 같은 계약으로** 판다: `_parse_where_str` 단일 소스(`_match`·`_where_fields` 가 같은 눈으로 읽음) + `_WORD_CMP_RE`(contains/in/matches/startswith/endswith/eq/ne/lt/le/gt/ge, 양쪽 공백 요구라 'startswith' 속 'in' 오인 없음). **판정 채택: `matches` 를 `_OPS` 에 합류**(re.search — `[if:]` 술어와 같은 뜻) → 두 조건 언어의 문법 통일. 침묵 폴백 제거: 모르는 op 은 `_apply_op` 가 지원 목록과 함께 정직 거절(`_WhereError` → filter 겉옷이 에러 봉투로), 깨진 정규식도 정직 거절. 워드 연산자 합류로 "필드 op 값" 문자열이 조건으로 읽히므로 필드 부재 오류문에 "전-필드 검색은 연산자 없는 문자열" 갈림길 안내 동반. 실측: `"아파트명 matches 자이"` 0→**7건**(구조형과 동수) · `"title contains workflow"` 문자열=구조형=**4건**(같은 창) · `{op:"비슷하다"}` → 지원 목록 동반 거절 · `"아파트명 matches ["` → 정규식 오류 신고. 어휘 표면(`ibl_actions.yaml` ×3 자리) 갱신 후 `build_ibl_nodes.py --check` 삼각·문서 파생 일치 통과. ※부작용(의도): `where: "Made in Korea"` 처럼 영어 전-필드 문장은 이제 조용한 substring 이 아니라 "'Made' 필드 없음 + 갈림길 안내"로 **크게 실패**한다 — 코퍼스 실측 충돌 0건(워드 연산자 문자열 표본은 `title contains workflow` 하나뿐).
    - `B19-2` **수리됨** — `items:` 직접 주입의 **문자열 페이로드**를 모든 소비자가 같은 눈으로 읽게: 정본 `common.currency.coerce_items_payload`(list · {items:[…]} 봉투 · 그 둘의 JSON 문자열) 신설 → `_each_input_rows`(each·reduce)와 ai-ops `_prev_items`(ai·brief)가 사용. 에러문 자기모순도 수리 — `currency_shape_note` 가 items 자리의 실제 타입·길이·미리보기를 말한다. 실측: `[table:reduce]{items:"$r.items"}` 거절→**value 90** · `[table:brief]{items:"[]"}` 가 "통화 없음"이 아니라 "0행" 으로 · 잡문자열 주입 시 `"받은 봉투: ['items'] — items 자리에 목록이 아니라 str(6자)가 있습니다: 그냥 문자열"`. ※data-ops 는 이미 동형 인라인 코드가 있어 그대로 둠(⑥ 범위 밖 리팩터 금지) — 정본과 인라인 2벌 병존은 기록해 둔다.
    - `F19-1` **수리됨(진단 정정 포함)** — 실측해 보니 case 만의 문제가 아니라 **if·case 공통의 dict/비-dict 비대칭**이었다: 분기 몸이 스칼라를 내면(예 `[self:time]`) `_attach_branch_meta` 가 메타를 stdout 로그로만 흘렸다(19회차 보고서는 case=미신고/if=신고로 읽었는데, 실제로는 그때 if 의 분기 몸이 dict 였을 뿐). 수리=**통화 불침범 + 관측 메타는 봉투 side-channel**: 블록이 step dict 에 `_branch_meta` 를 남기고 → 파이프는 `results[]` step 기록에, 단독 실행은 `system_tools_ibl` 이 결과를 `{result, matched, matched_value}` 로 감싼다. 실측: case 단독 → `matched:"0~50", matched_value:5.3` · if 단독 → `matched:"else"` · 파이프 속 블록 step 에 `matched:"count($items) > 10", matched_value:90`.
    - `F19-2` **수리됨(교재 쪽)** — 런타임 봉투는 **일부러 안 바꿨다**(단일 액션에 `final_result` 미러를 넣으면 전 표면·앱·폰이 읽는 모양이 바뀌고 토큰이 중복된다 — 5회 반복된 것은 *읽는 쪽*의 무지였다). 교재 `12_ibl_only.md` "봉투 읽는 법" 에 "단일 액션 결과는 핸들러 원문 — `final_result` 없는 게 정상이고 빈 봉투가 아니다" 를 명시. 교재-가드 통과.
    - `관찰 1` **판정·문서 수리** — 훈련 실측을 증류에 태우는 안은 **기각**(검증 안 된 상상이 번역기를 오염시키는 값 > 지표가 움직이는 값). 대신 가이드 §6 을 정정: 4지표는 훈련의 성적표가 아니라 **몸의 성적표**이고 훈련 실측이 증류 밖인 것은 설계된 규율이다(리허설은 삶이 아니다 — 18회차 B18-1 과 같은 축). 훈련 자신의 성적 = 원장의 발견→수리 이동.
  - `F19-3` **신규 발견(결함 — 이번 수리 중 자해로 드러남)**: `[self:edit]` 의 new_string 을 **실제 줄바꿈이 든 여러 줄 문자열**로 주면 이어지는 줄의 **선행 공백이 전부 제거되어** 파일에 들어간다(파이썬이면 IndentationError 로 즉사). `\n` 이스케이프로 주면 정상. old_string 쪽도 같은 손상을 입어 "공백·들여쓰기만 다릅니다" 로 매칭 실패한다. 재현: `[self:edit]{path:"…", old_string:"def f():", new_string:"def f():\<개행>    return 1"}` → 파일엔 `    return 1` 이 `return 1` 로. 이번 턴에 data-ops handler 를 한 번 깨뜨렸다가 같은 편집을 `\n` 형태로 다시 써 복구. 제안=파서/편집 액션 중 어느 쪽이 선행 공백을 먹는지 특정 후 보존(수리성). ★19회차 원장 밖이라 이번 턴엔 **고치지 않고 기록만**(범위 규율). → **종결(2026-08-22)**: `b5b564f` 수리 + `52bc6e9` 회귀 테스트. 상세는 아래 21회차 항목.
    - `F19-3` **수리됨(2026-08-22, 사용자 지시로 범위 밖 1건 집행)** — 범인은 편집 액션이 아니라 **파서**였다: `ibl_parser._preprocess` 가 열린 문자열 안에서 시작하는 줄까지 `strip()` 해서 entries 에 넣었다(D3 는 문자열 속 주석·빈 줄을 *버리지 않는* 데까지만 갔고, 깎지 않는 데까진 못 갔다). 그래서 여러 줄 문자열 param 의 둘째 줄부터 들여쓰기가 사라졌고, `[self:edit]`·`[self:write]` 로 파이썬을 쓰면 IndentationError 로 즉사했다. 격리 실측으로 **`[self:write]` 도 같은 손상**을 확인해 액션이 아닌 파서로 범위를 옮겼다. 수리=열린 문자열 줄은 원문 보존(윈도우 `\r` 만 제거). 실측(격리): 여러 줄 들여쓰기 보존 PASS · D3 회귀 PASS · 문자열 밖 들여쓴 파이프 정상 · edit old/new 양쪽 보존. 회귀 배터리 7종(pytest 43 통과 포함) 무손상.
  - **파서 계열 전수 점검(2026-08-22, F19-3 후속 — "같은 부류가 더 있나")** — 라운드트립 탐침 10항목 + 인접 경로(각 행 치환·do 문자열·리터럴 값) 실측. 파서 **복제본은 없음**(`def _preprocess` 전역 1건). 신규 결함 2건 발견·수리:
    - `P-1` **수리됨(이중 진실: 두 파서가 같은 입력에 다른 답)** — `_parse_params`·`_extract_bracketed` 가 pyjson5→json 을 먼저 태우는데 **pyjson5 는 표준 밖 이스케이프의 백슬래시를 먹는다**(실측 `pyjson5.loads('{pattern: "\d+"}')` → `{"pattern": "d+"}`). 그래서 2026-08-22 에 `_extract_string` 을 "모르는 이스케이프는 원문 보존"으로 고쳐 놓고도 그 규약이 **JSON5 경로에서 통째로 무효**였다. 영향=정규식 param 이 조용히 다른 패턴으로 바뀌어 0건을 낸다(`[self:grep]{pattern: "\d+"}` → 실제로 `d+` 를 찾음 — 침묵 실패). 수리=`_has_nonstandard_escape()` 로 표준 밖 이스케이프가 있으면 JSON/JSON5 를 건너뛰고 수동 파서로. 실측: `"\d+"`→`\d+` · `"\s*\w+"`→`\s*\w+` · `"\q미지"`→`\q미지` · `"\t"`·`"a\\b"` 표준 이스케이프 무손상.
    - `P-2` **수리됨(개행이 값을 깨뜨린다 — F19-3 의 형제)** — 리터럴 배열/객체 값 안에 **실제 개행**이 있으면 JSON 규격상 제어문자라 파싱 실패 → 옛 코드가 "배열이면 원본 문자열 반환(최선)"으로 **조용히 str 을 돌려줬다**. `[table:each]{items: [{"code": "a<개행>    b"}]}` 가 list 아닌 str 로 떨어져 소비자는 "통화 못 찾음"으로 죽고 원인은 안 보였다. 수리=`_escape_control_in_strings()` 로 문자열 안 개행·탭만 이스케이프해 재시도. 실측: 여러 줄 리터럴 → `[{"code": "a\n    b"}]` list 정상.
  - **범위 바깥 점검(2026-08-22 15:0x, 커밋 b5b564f 직후 — "파서 밖 왕복 지점에도 같은 부류가 있나")** — 직전엔 파서 본체(`_preprocess`·`_parse_params`·`_extract_bracket`)와 호출 지점을 봤다. 이번엔 그 **바깥**: IBL 코드가 텍스트로 저장됐다 다시 읽히는 왕복 지점 5종(워크플로우 `do`·트리거 `pipeline`·캘린더 `action_params.pipeline`·스위치 `command`·해마 코퍼스)과 **코드가 프롬프트/화면으로 나가는 직렬화 지점**. 고문 문장 3종(여러 줄 들여쓰기·표준 밖 이스케이프·리터럴 개행)을 각 매체에 저장→복원→재파싱 비교. 저장 매체 5종은 **전건 무손상**(텍스트 동일·파싱 동일). 결함은 저장이 아니라 **출력 직렬화**에서 나왔다:
    - `P-3` **수리 검증 통과·적용 예약(2026-08-22)** — `ibl_usage_rag._format_references` 가 해마 용례를 `code='…'` **XML 속성**에 원문 그대로 넣었다. 코드 안 홑따옴표가 속성을 그 자리에서 끊는다. 게다가 바로 윗줄에 `code = ex.ibl_code.replace('"','&quot;')` 로 이스케이프를 **계산해 놓고 쓰지 않았다**(죽은 변수 — 저자의 의도는 이스케이프였다). 실측: 코퍼스 3,539건 중 **301건(8.5%)** 이 `'`·`&`·`<` 를 담아 그 블록 전체가 비적합 XML. 소비자는 모델만이 아니다 — 계기판 `ManualMode.tsx:parseReferences` 가 **DOMParser('text/xml')** 로 진짜 파싱하는데, 비적합이면 예외가 아니라 `<parsererror>` 문서가 되어 `querySelectorAll('ref')` 가 **빈 배열**을 낸다 → '번역 근거' 패널이 조용히 사라진다(`catch` 는 발동조차 안 한다). 수리=속성은 `_xml_attr`(`&`·`<`·`"`), **코드는 CDATA 본문**(엔티티로 바꾸면 `[A] & [B]` 가 `&amp;` 로 보여 모델이 그대로 베낀다 — 코드는 원문이어야 한다) + 계기판은 `textContent` 폴백(옛 `code=` 속성도 계속 읽음). 실측: 수리 전 MALFORMED → 수리 후 well-formed, `'`·`&`·`<` 든 실제 용례 5건 코드 원문 전건 일치.
    - `P-4` **수리 검증 통과·적용 예약** — 같은 파일의 형제 직렬화 2곳(`_esc`=액션 설명·`impl_escaped`=구현 설명)도 `"` 만 이스케이프. 실측으로 `ibl_nodes.yaml` 의 description 16건·implementation 8건이 `&`·`<` 를 담아 `<implementations>` 블록이 오늘도 비적합 XML 이었다(`[self:forage]` 의 `"code:<repo>"` 등). 수리=같은 `_xml_attr` 로 통일. 실측: 수리 전 MALFORMED → 후 well-formed.
    - `N-1` **제안 2건 기계검증 통과·적용 대기(2026-08-22 15:5x)** — 아래 '보고만' 항목의 후속. 호출처 17곳을 하나씩 고치는 대신 **입구를 하나로** 만든다: `notification_manager.create()` 가 기록 직후 `notify_dispatch.deliver_notification()` 을 부르고(신설 — 전달만 하는 함수), 관문 `notify_user` 는 `create(deliver=False)` 로 기록만 하고 command·badge 를 실은 전달을 자기가 한 번 한다. 규약이 문서에만 있으면 다음 호출처가 또 어긴다 — 구조로 강제한다. `_listeners` 배관은 등록자 0(전수 grep)이라 이중 전달 위험 없음. 실측(격리 사본 2개를 조합해 전달 경로 모의): 우회 호출 `nm.warning` → **수리 전 런처 0회·OS폴백 0회(조용한 유실 재현) → 수리 후 런처 1회·OS폴백 1회**, 관문 경유 `notify_user` 는 전후 모두 정확히 1회(이중 아님), 알림함 기록 정상. proposal_id=`20260822_155040`(notify_dispatch, 먼저) · `20260822_155017`(notification_manager). ★이 턴은 REPAIR 경로가 아니어서 라이브 적용은 못 했다 — 적용은 사용자가 수리로 명령한 턴에서 `[self:patch]{op:"apply", proposal_id}`.
    - **범위 밖으로 보고만(고치지 않음)**: 스케줄 실행의 완료·실패 알림(`calendar_actions._action_run_pipeline`)이 `notification_manager` 를 직접 불러 **notify_dispatch 단일 관문을 우회**한다 — 오늘 POST /notifications 에서 고친 것과 같은 병이고, 전수 세면 관문 우회 호출처가 **14곳(7파일)**. 사용자 호소 "알림이 자꾸 끊긴다" 의 남은 절반일 가능성이 높다. 문자열 이스케이프 계열이 아니라 이번 범위 밖 — 다음 배치 후보.
    - 이상 없음으로 확인된 축(같은 계열 재발 없음): 문자열 안 `;`·`>>`·`&`·`??`(문장/파이프 분리기가 문자열 인식) · 문자열 안 중괄호 불균형 · 문자열 안 `#`·빈 줄(D3) · 한 줄 문자열 앞뒤 공백 · `do` 문장 문자열 보존 · `[table:each]` 행 치환(`_each_escape`) 의 개행·따옴표·역슬래시·`$` 왕복.

- **20회차 (2026-08-22 16:0x)** — 보고서 `outputs/imagination_training/2026-08-22_20회차.md`. 중점=파이프 안 조합이 가장 적은 **축적(1)·시간(2)·적용(2)·조건(3)** 문형 + 교재에도 조합 0인 처녀 액션(`table:compute`·`self:switch`·`self:forage`·`self:goal`·`sense:researcher`·`others:publish`·`self:folder_note`·`self:output`). 과제 13건 전수 검수 통과, 9건 실측(부작용 없는 것만). 깨끗 4 · 꼬임 2 · 불가 2 · 결함 1.
  - `F20-1` **마찰(발견)** — `sense:realty` 의 ⟨열⟩ 표기가 **source 를 안 가린다**. molit=`아파트명·법정동·보증금·전용면적…`(카탈로그와 일치) / naver=`title·name·meta·summary·price`(범용). `deal` **어휘 자체도** 다르다(naver=lease, molit=trade|rent — molit 에 lease 를 주면 `잘못된 조합` 거절). 그래서 파생 계산의 필드명을 고를 근거가 통째로 어긋난다. 최소재현: `[sense:realty]{source:"naver", …} >> [table:compute]{set: {"평단가": "round(보증금 / 전용면적, 1)"}}` → `'보증금','전용면적' 필드가 어느 행에도 없습니다`. 제안=⟨열⟩ source 별 병기(수리성) / 열 이름 정규화(판정성).
  - `F20-2` **마찰(발견)** — 같은 액션에서 **items 열 이름 ≠ 봉투 경로**(`sense:host`). 조건 좌변은 봉투 최상위를 읽는데 카탈로그 ⟨열⟩ 은 items 기준이라, `disk_percent` 로 조건을 걸면 **조건 판정 불능 → else 도 보류 → 문장 통째로 죽음**. `cpu_percent` 만 두 곳 이름이 같아 교재 대표 예시가 우연히 돈다. 봉투 경로 `.disk_root.percent` 로는 정상(`matched_value: 10.3`). 제안(수리성)=봉투 최상위에 `disk_percent`·`memory_percent` 미러 또는 카탈로그에 조건용 경로 병기.
  - `F20-3` **꼬임(발견)** — `table:since` 첫 검침이 기준선만 잡고 0행(정직 신고 `seeded: true`)인데, 감시자 문형의 자연스러운 꼬리 `>> [table:brief]` 가 0행을 **에러**로 봐서 **첫 실행이 항상 error 로 끝난다**. 문법 우회 가능(`[if: empty($items)]`·`[on_error: skip]`)이라 꼬임. 제안(판정성)=since 뒤 0행을 '정상 침묵' 관용구로 승인할지.
  - `B20-1` **결함(발견)** — **코퍼스가 유령 op 를 가르치고 검수도 통과시킨다**. `[self:finance]{op:"summary"}` 용례가 `ibl_usage.db` 에 실재하는데 런타임만 거절(`알 수 없는 op 'summary'`). `/ibl/validate` 는 `valid: true`(effect 가 액션 전체 설명으로 폴백, safety 도 액션 기본값 write), pre-commit `코퍼스 어휘 생존` 은 **액션 실존만 보고 op enum 은 안 본다**. 1회차 `F2`(validate 가 param 이름 미검사)의 **op 판**. 제안(수리성)=①빌드 코퍼스 검사에 op enum 대조 ②validate 가 op 를 enum 과 대조해 신고 — 둘 다 기존 가드 확장, 새 어휘 불필요.
  - `F20-4`·`F20-5` **마찰(소소)** — finance 유령 op 안내 문구가 실제 op 5개 중 `sync` 누락(`handler.py:85`) / `[self:notify_user]{message:}` 만 주면 알림함 제목이 빈칸으로 남는다.
  - **관찰(갭 아님 — 훈련자 읽기 규율)**: step 요약 `columns` 에 방금 만든 한글 파생 열이 안 보여 "compute 가 조용히 실패"로 오판할 뻔했으나, 봉투는 `columns_truncated: 5 · columns_total: 17` 로 **이미 절단을 신고**하고 있었다(F18-1 수리가 실사용에서 작동하는 증거). 격리해 보니 `등락폭: 0.88` 정상. — 봉투의 절단 신고를 읽어라.
  - **원장 이동**: 이번 회차는 발견 6건(결함 1·마찰 4·꼬임 1). 수리는 대장장이 고리의 일(훈련은 고치지 않는다).

### ✅ 20회차 판정·수리 집행 (2026-08-22 16:2x — 사용자 지시 "장기적으로 바람직한 쪽으로 판정해서 수리")
판정 기준(원장에 없어 실행자가 세움): **IBL 헌법** — ①새 낱말의 기본 답은 "아니오"(반-어휘-증식) ②증상을 액션마다 덧대지 말고 **문법·검증·코퍼스 같은 원인 층**에서 없앤다 ③파괴적 변경(기존 문장을 깨뜨리는 것)은 사용자 판정.

**먼저 진단 정정 4건** — 원장 문구는 발견 당시 기록이라 현재 상태를 실측했고, 넷은 **이미 닫혀 있었다**(원장에 반영):
- `B15-1` **해소 확인** — `[self:trigger]{op:"list"} >> [table:take]{n:1}` 이 items 1행으로 정상 변환 + `_untransformed: ['existing_schedules']` 자백. 침묵 통과 아님.
- `F17-1` **해소 확인** — 프로젝트 컨텍스트 오류문에 "★each/폴백/병렬 가지 안까지 … body의 project_id 필드를 쓰세요"가 이미 병기돼 있다.
- `F17-2` **해소 확인** — `??` 전멸 시 `attempts[]` 에 가지별 실패 사유 전부 보존(`_branch_errors` 도 존재).
- `F17-3` **해소 확인** — `_v4_var_payload`(workflow_engine)가 bare `$var` 를 v4 추출 계약에 합류시킴.
- ★그리고 **20회차 보고 자체의 정정**: "validate 가 유령 op 를 통과시킨다"는 부정확했다 — `/ibl/validate` 는 `valid:true` 를 주되 **`param_warning` 으로 이미 신고**하고 있었다(`op 'summary' 은(는) 이 액션에 없습니다 — 실행 시 거절됩니다. 사용 가능: [...]`). 20회차 검수 스크립트가 그 필드를 출력하지 않아 못 본 것. 남은 진짜 원인은 **코퍼스 쪽**이었다(아래 B20-1).

**수리 3건 (원인 층)**
- `B20-1` **수리됨** — 진범은 검증이 아니라 **검사 범위와 검사 항목**이었다. ①`_corpus_entries` 가 `data/training/*.json` 만 훑는데 **트레이너는 DB(ibl_usage.db)와 파일을 둘 다 읽는다** — `validate_corpus_vocab` 의 docstring 자신이 그렇게 적어 놓고도 검사는 절반만 봤고, 20회차가 주운 오염이 하필 DB 쪽에 있었다. ②액션 생존만 묻고 **op 생존은 안 물었다** — 액션 은퇴는 이관돼 왔지만 op 은퇴(`stock price→quote`, `output file→self:write` 흡수 …)는 아무도 안 봤다. 수리=같은 루프에서 op enum 대조 + `include_db=True`(vocab 검사만. param 정합은 관대한 상위집합이라 범위를 넓히면 오탐 폭증 — 기본 False 유지). **실측 오염 40건**(파일 36·DB 4, 고유 5종: `stock op=price` 26 · `self:output op=file` 7 · `showcase op=sync` 4 · `finance op=summary` 2 · `radio op="AI 뉴스"` 1)을 명백한 은퇴만 치환(37건)하고 의미가 소실된 것은 제거(5건 — 코퍼스는 *가르치는 것*이라 틀린 걸 남기느니 지운다). 백업=`data/_backups/2026-08-22_corpus_op정리/`. 증상 소멸 실측: 새 가드로 재스캔 **0건** · 해마 회상이 `showcase{op:"sync"}` 대신 `status/add` 를, `finance{op:"query", query_type:"summary"}` 를, `stock{op:"quote"}` 를 낸다.
- `F20-2` **수리됨(검증 통과·적용 예약)** — 액션마다 봉투에 미러를 넣는 안(=액션 수만큼 반복될 덧대기)을 버리고 **조건 언어가 통화를 보게** 했다: 조건 좌변 필드 해소가 봉투에서 실패하면 **items 가 1행일 때만** 그 행에서 한 번 더 찾는다(`ibl_executors._resolve_source_value`). 여러 행이면 어느 행의 값인지 언어가 정할 수 없으므로 정직 실패 유지. 어휘 증식 0, 전 액션 일반 적용.
- `F20-4` **수리됨** — `finance_op` 의 유령 op 안내를 `_OP_DISPATCHERS` 에서 파생(손으로 적힌 목록은 op 를 늘릴 때마다 뒤처진다 — 실측으로 `sync` 누락). 증상 소멸 실측: `알 수 없는 op 'summary'. 사용 가능: delete|ingest|query|save|sync`.

**보류 3건 (판정성 — 사용자 결정 없이 고치면 안 되는 것)**
- `F20-1` realty ⟨열⟩ source 미구분 — 열 이름 정규화는 **기존 문장을 깨뜨린다**(파괴적). 카탈로그 표기 병기는 미봉책이라 근본과 갈림 → 사용자 판정.
- `F20-3`·`B15-2` since 첫 검침 0행 — 첫 검침 **침묵은 이미 해소**됐다(`seeded: true` + note 정직 신고). 남은 것은 "0행을 받은 소비자가 에러를 낼지 침묵할지"이고, 이는 **언어의 관용구를 정하는 일**이라 판정 대상(문법으로 우회 가능: `[if: empty($items)]`·`[on_error: skip]`).
- `F20-5` `notify_user{message:}` 만 주면 알림 제목 빈칸 — message 앞머리를 제목으로 승격할지, title 을 필수로 할지는 알림 계약 변경 → 판정.

### ✅ 보류 3건 사용자 판정·집행 완료 (2026-08-22 17:2x — 사용자 지시 "장기적으로 봐서 어떤 판정이 좋을지 → 그 판정대로 집행")
세 판정 모두 **파괴 0 · 새 낱말 0 · 원인 층 수리**로 수렴했다. 공통 기준: ①열 이름·제목 같은 *세계의 사실*은 몸이 정하지 않는다(명사의 자리) ②증상을 액션마다 덧대지 않고 **입구 하나**에서 없앤다 ③기존 문장을 깨뜨리는 안은 그것이 '근본'처럼 보여도 기각한다.

- `F20-1` **판정: 열 이름 정규화 기각 · 색인 키를 변이 축까지 확장**. 원장이 "병기=미봉책 / 정규화=근본"으로 갈라 놓았으나 그 갈림 자체가 틀렸다 — 진짜 원인은 표기가 아니라 **색인 키의 입도**였다. ⟨열⟩ 은 fixture 실측이고 키가 `node:action[#op]` 인데 realty 의 변이 축은 op 이 아니라 **param(source)** 이다(`ibl_return_shapes.json` 에 molit·codes 둘뿐 — naver·zigbang 열은 *관측된 적이 없었다*). 정규화 기각 사유 셋: ⓐ열 이름=세계의 명사(관측 데이터). 몸이 `보증금` 으로 통일하면 외부 API 가 바뀔 때 몸이 조용히 거짓말한다 ⓑ파괴 범위가 문장보다 넓다 — 앱 view 템플릿이 `{명칭}`·`{법정동}`·`{거래금액}` 에 직결 ⓒ molit(체결된 과거 거래)과 naver/zigbang(현재 호가)은 **같은 것이 아니다**. 같은 열 이름을 씌우면 다른 사실이 한 표에 섞인다. 집행=`shape_variants: {param=값: '<fixture>'}` 선언(액션 정의가 단일 소스) → 빌드가 `ibl_fixtures.json` 의 **별도 `shape_variants` 섹션**으로 파생(건강검진·통화·returns 스윕의 측정 우주 불변 — 외부 API 를 매일 더 두드리지 않는다) → `ibl_shape_sweep.py` 가 함께 관측(`node:action@param=값`) → 카탈로그가 `⟨열: 아파트명·법정동·… | source=naver: title·name·price | source=zigbang: …⟩` 로 병기(범례 갱신). **병기가 미봉책이 되는 건 손으로 적을 때뿐이다 — 실측 파생이면 근본 수리다.** 부수: `deal` 조합 거절문을 `_dispatch` 에서 파생하고(손으로 적은 목록은 뒤처진다 — F20-4 부류) 오해의 실체인 *source 별 어휘 차이*(molit 은 trade|rent, 전세·월세는 현재 매물의 `lease`)를 갈림길로 동봉. 실측: 최소재현 `[sense:realty]{source:"naver"} >> [table:compute]` 가 **에러 → 성공**(`평당가` 파생), 관측 4/4(molit·codes·naver·zigbang), `deal:"lease"` 거절문에 source 안내 동반.
- `F20-3` **판정: 0행=정상 승인(빈손 성공) · 우회 관용구 기각**. 새 관용구를 정하는 일이 아니라 **이미 있는 계약이 한 verb 에 안 닿은 것**이었다 — 같은 파일의 `table:ai` 는 0행에 `_ok(items:[], note:"AI 호출 생략")`, `each`·`flatten`·`groupby`·`filter`·`take`·`sort` 도 전부 0행 통과(`if rows and …` 가드). **brief 하나가 예외**였고 그 예외가 감시자 문형의 자연스러운 꼬리를 첫 실행마다 error 로 끝냈다. 우회 승인(`[if: empty($items)]`·`[on_error: skip]`) 기각 사유: 감시자 문장마다 가드를 다는 **문법 세금**이고 코퍼스에 실리면 모델이 배운다(문장이 길어져 조합률이 내려간다) · `on_error: skip` 은 진짜 실패까지 삼켜 **침묵 실패 습관을 함께 가르친다**. 집행=0행 → `{items:[], rows_in:0, note}` 성공. 구분 유지: **통화 없음=에러 / 0행=성공**. 조용한 성공 금지 — `rows_in`·`note` 로 말하고, `message`(산문 정본) 키는 **넣지 않는다**(행이 없으면 산문도 없다. 빈 문자열로 위장하면 write 싱크가 빈 파일을 쓰고 `??` 폴백이 빈손을 못 알아본다). 실측: `[sense:realty]{op:"codes"} >> [table:since]{key:…} >> [table:brief]` 가 첫 검침·2회차 모두 성공(옛 동작=error), 통화 없음 갈래는 여전히 거절. ★남은 접힘 1곳 **같은 날 집행**(사용자 지시): `system_essentials._copy_piped_items` 가 "통화 없음"과 "0행"을 `_piped_items` 에서 `[]` 로 접어, *앞 액션이 통화를 안 내는 액션이었다*(진짜 오류)와 *앞 액션이 정상적으로 0행을 냈다*(정당한 빈손)를 같은 문장으로 보고했다 — 0행 계약을 이 자리에선 지킬 수가 없었다. 수리=`_piped_items` 가 **None(통화 없음) / [](0행)** 을 가르고(되읽기는 `common.currency` 정본), 호출자가 3갈래로 답한다: 통화 없음=거절+받은 봉투 진단 · 0행=빈손 성공("Error:" 로 시작하지 않아 파이프가 성공으로 읽는다 — `_is_error_result` 규약, 대상 폴더도 만들지 않는다) · **행은 있으나 레코드(dict)가 아님=별도 거절**(0행과 다른 사실이라 접으면 같은 병이 한 겹 더 생긴다). ★부수 발견: 세 번째 소비자가 붙으며 `currency_shape_note`(진단 정본)가 **JSON 문자열을 안 팠다**는 게 드러났다 — each·reduce 는 파싱된 봉투를 넘겨 안 보였지만 `_prev_result` 를 날것으로 쥔 소비자에겐 진단이 통째로 `str` 한 글자였다(수리: 문자열·목록도 판다). ★부수 이사(1500줄 규칙에 걸려): 진단 정본 `currency_shape_note` 를 `ibl_executors` → **`common/currency`** 로(소비자가 셋이 되면 ibl 층 안쪽은 더 이상 그 함수의 집이 아니다 — 패키지 핸들러가 ibl 내부를 찔러야 했다), `[self:copy]` 의 파이프 경로를 `handler.py` → 형제 **`copy_ops.py`** 로(경로 게이트는 handler 소유라 넘겨받는다 — office_ops 선례). 회귀=`test_pipe_currency_failures.py` P22, 라이브 종단 2건(분리 후 재확인 포함).
- `F20-5` **판정: title 필수화 기각 · message 앞머리 승격(관문 파생)**. 필수화하면 부르는 쪽(모델 포함)이 message 를 title 에 복붙한다 — 형식만 채운 중복 토큰이고("형식보다 내용" 위배) 기존 문장·코퍼스도 깨진다. 핵심은 **파생이 일어나는 자리**: 알림 입구는 18곳이라 액션 쪽에서 고치면 우회 호출처는 여전히 빈 제목이다. 08-22 N-1 수리가 `notification_manager.create()` 를 단일 입구로 만들어 둔 그 자리에 파생을 둔다(`derive_title`) — 전달(`notify_dispatch.notify_user`)은 **기록된 제목을 되읽는다**(둘이 갈리면 알림함과 OS 알림의 제목이 달라진다). 규칙=첫 번째 비어있지 않은 줄, 길면 낱말 경계에서 자르고 `…`. **문장 부호로 자르지 않는다** — "3.5% 올랐습니다" 가 소수점에서 잘린다(예측 가능한 규칙 하나 > 영리한 규칙). 로그 절단 표식(`…(+N자)`)은 적용 안 함(잘린 payload 가 아니라 표시용 요약이고 원문이 바로 아래 칸에 있다). `POST /notifications` 의 `title` 도 선택으로. 실측: `[self:notify_user]{message:}` → 알림함 제목=첫 줄(둘째 줄 미포함)·런처 전달 성공, `POST /notifications` 무제목 → 파생 제목·전달 성공.

**시드 12건**(`scripts/seed_f20_verdicts.py`, 코퍼스 3,537→3,549 · `ibl_distilled` 821→833): 판정이 **새로 참으로 만든 문형**만 가르친다 — ①감시자 꼬리 `>> [table:since] >> [table:brief]`(수리 전엔 첫 실행마다 error 라 코퍼스에 거의 없었다. 08-21 재학습 잔여 실패 5건이 전부 since·ai·brief 였던 것도 이 희소가 원인) + 0행이 정상인 intent("없으면 없다고") ②변이별 열 이름(naver=price·title / zigbang=distance_m / molit=거래금액·전용면적) — 카탈로그가 이제 말하는 사실을 코퍼스도 말한다 ③무제목 알림(`{message:}` 와 파이프 꼬리 `{}`) — title 을 message 복붙으로 채우는 습관이 생기지 않게 제목 없는 문장만. ★검증: 전건 `/ibl/validate` + **부작용 없는 8건은 라이브 실행까지**(그 과정에서 `[sense:stock]{symbols:}` 오문이 잡혔다 — validate 는 통과시키고 런타임이 거절하는 부류라 검증만으로는 못 거른다) · 벡터 색인 12/12 실적 대조(★`_index_batch` 는 실패를 삼킨다) · 라이브 회상 3발 실증(변형 질의가 새 시드를 근거로 zigbang=distance_m·naver=price 를 정확히 냄). ⏳재학습 대기열 합류.

**회귀**: `backend/test_shape_variant_axis.py` 9건(선언→파생·측정 우주 불변·카탈로그 인쇄·변이 없는 액션 무변화·범례·선언 가드 6종·라이브 어휘 전수) · `backend/test_notify_title.py` 11건(파생 규칙 5·관문 파생·명시 제목 불가침·전달이 기록된 제목을 쓰는가·알림함 사망 시에도 제목 생존·API 입구) · `test_ai_ops_words.py` B3 뒤집기 + B3-a~d·B4-a(구분 유지) → 배터리 30/30. 전체 `pytest -m "not local"` **257 passed**, `build_ibl_nodes.py --check` 전 가드·파생 9문서 일치.

### 21회차 (2026-08-22 18:0x — 보고서 `outputs/imagination_training/2026-08-22_21회차.md`)

중점 = **문법 축에서 유일하게 행동 조합 0% 인 폴백 `??`** + 20회차가 안 건드린 처녀 액션(`others:follow`·`others:board`·`others:auto_response`·`others:delegate`·`self:limb`·`self:cctv`·`limbs:open_window`·`engines:render_html`) + 여전히 1인 축적 문형. 과제 14건 **검수 14/14**(param_warning 0) · 실측 11건. **깨끗 12 · 꼬임 1 · 결함 1**(합 14 — 그중 문장 전체 미실행 3건: T5·T11 부작용, T9 알림 예산으로 좌변만 격리 실측). 지표: 미조합 113/151(도달 가능 111) · 조합 31 · 축적 1 — 훈련 실측은 증류에 안 담기므로 지표 불변이 정상(가이드 §6).

- `B21-1` **신규 발견(결함 — 침묵 실패)**: 핸들러가 실패를 `"오류: …"` **문자열**로 반환하면 실행기가 정상 결과로 보고 봉투를 `success: true` · `steps 3/3` 으로 닫는다. 최소 재현 `[engines:render_html]{}` → `{"result": "오류: html은 필수입니다."}` (success 키조차 없다) · 파이프 `[sense:crypto]{symbol:"BTC"} >> [table:brief]{instruction:"한 문장"} >> [engines:render_html]` → success true 인데 final_result 가 그 오류 문자열. **자동화(스케줄·트리거·워크플로우)가 실패를 성공으로 집계한다.** 규모 실측: 설치 패키지에 `return "오류: …"` **34자리/4파일**(system_essentials/handler 16 · media_producer/handler 11 · gemini_image 5 · copy_ops 2). 제안=핸들러 반환 계약을 error dict 로(정확) + 실행기 접두 승격을 그물로(포괄). ★판정 필요(범위 34자리).
- `V21-1` **신규(어휘 마찰)**: `engines:render_html` 이 파이프 통화를 안 먹는다 — `[table:brief]` 의 message 도 items 도 무시하고 `html` param 만 본다. "요약해서 그림으로"가 한 문장이 안 되고 사람이 결과를 다시 타이핑해야 한다. 대조=`[self:write]` 는 content 생략 시 직전 통화를 저장(파이프 싱크 규약). 제안=같은 규약 확장(어휘·파라미터 신설 0).
- `V21-2` **신규(어휘 마찰)**: `[self:cctv]{op:"stats"}` 가 봉투에 `sources`(소스별 현황)를 갖고도 `returns: scalar` 라 변환자가 거절. 거절 자체는 모범적(봉투 실제 키까지 인쇄). 제안=stats 를 items 로 승격, `self:limb` 의 `_mirrored` 규약 재사용(T13에서 그 규약이 도는 것 확인).
- `F21-1` **신규(문서 마찰)**: 상상 훈련 가이드 3-5 의 `/ibl/execute` 예시에 `project_id` 가 없어 그대로 부르면 패키지 도구가 전부 거절된다(이번 첫 실측 9건 중 6건이 이걸로 죽었다). 에러가 고칠 방법을 정확히 안내해 침묵은 아님. 함께: 카탈로그의 "`??` 의 가지는 단일 액션만" 문구가 낡았다 — 구현은 괄호 가지를 지원한다(아래 열매).
- **열매 확인**: ①`F19-1` 수리 살아있음 — 파이프 속 `if` 블록 step 봉투에 `matched: "count($items) > 0"`, `matched_value: 3`. ②`??` **괄호 가지 실동작 확인** — 폴백 2번째 시도가 `node: "pipe", action: "(2단)"` 로 기록. ③`table:reduce` 축적이 도메인 데이터에서 실동 — 실거래 90행의 쉼표 낀 `거래금액`을 숫자로 누적(3,334,913만원).
- **관찰(훈련 밖)**: 알림함에 제목 "알림"·본문 빈 문자열 알림 1건(17:52:09, source=ai). 훈련 시작(17:58) 이전 생성이라 스크래치 아님 — 오늘 알림 경로 2회 수리 직후라 확인 대상.
- **시드 후보 5건**(승인 대기) — `??` 문장 3건 포함(이 회차가 처음 실측한 문형).
### ✅ 21회차 판정·수리 집행 (2026-08-22 18:2x — 사용자 지시 "임시처방이 아니라 근본적 처방으로")

- `B21-1` **수리됨 — 진단 정정 포함**. 원장은 규모를 "34자리"로 적었으나 실측하니 **18자리(`Error:` 영어)는 이미 판정에 걸리고 있었다** — 진짜 새는 건 `오류:`(한글) 쪽뿐이었다. 그리고 더 중요한 정정: media_producer 계열 오류 반환 **26자리 중 10자리는 접두가 아예 없다**(`FFmpeg 오류:`·`렌더링 중 오류 발생:`·`TTS 생성 중 오류 발생:`). **접두를 늘리는 처방으로는 원리적으로 못 고친다**는 뜻이라, 근본은 접두가 아니라 **반환 계약**이다. 수리 두 층: ①**계약(본체)** — media_producer/handler.py·gemini_image.py 의 오류 반환 26자리를 `_err()` → `{"success": False, "error": …}` 로. 소비자 `lecture_workspace/deck_video.py` 도 dict 를 읽게 동행 수정(안 하면 사유 자리에 repr 이 온다). ②**그물(안전망)** — 판정 단일 소스 `workflow_engine._is_error_result` 에 한글 접두 추가(영어판과 대칭). 실측 대조: 옛 동작 `success: true · steps 3/3 · final_result=오류문자열` → 새 동작 `success: false · steps_completed 2/4 · step3 shape "error" · resume 정보`, 그리고 **뒤 step(`[self:write]`)이 실제로 실행되지 않음**(파일 미생성으로 확인). ★`Error:` 18자리는 이미 잡히므로 건드리지 않았다(범위 규율 — 새지 않는 곳을 리팩터링하지 않는다).
- `V21-1` **수리됨** — `[engines:render_html]` 에 `[self:write]` 와 **같은 파이프 싱크 규약** 확장(`html` 생략 시 `_prev_result` 수용). 어휘·파라미터 신설 0. 받는 모양 세 가지를 `_html_from_prev` 가 흡수: 통화 봉투의 `message`(산문) · `items`(표로 조판) · 이미 HTML 인 문자열. 실측: 21회차에 죽었던 `[sense:crypto] >> [table:brief] >> [engines:render_html]` 이 3/3 완주, 산출물 `rendered_4cd3104d.png`(PNG 1280x720, 33KB) 실존 확인.
- `V21-2` **수리됨** — `cctv_sources()` 가 `sources` 를 유지한 채 `items`·`count` 를 나란히 낸다(거울 키 규약) + 어휘 선언 `returns: scalar → items`. `build_ibl_nodes.py --check` 삼각 검증 전 관문 통과(바이트·tool.json·문서 파생 9건 일치). 실측: `[self:cctv]{op:"stats"} >> [table:take]{n:2} >> [table:select]{columns:["name","total_cctv"]}` → 4행→2행→2열, `_mirrored: ["sources"]` 동행.
- `F21-1` **수리됨(2건)** — ①훈련 가이드 3-5 에 `/ibl/execute` 의 `project_id` 규약을 curl 예시와 함께 명시(문장 param 이 아니라 **body 필드**여야 each/폴백/병렬 가지까지 전파). ②`??` 문구 정정: 카탈로그(`12_ibl_only.md`)·`ibl.md` 의 "`??` 의 가지는 여전히 단일 액션"이 **틀렸다** — 실측으로 반증했다: `[sense:stock]{op:"quote", ticker:"ZZZZ_NO_SUCH_TICKER"} ?? ([sense:search]{…} >> [table:take]{n:2})` → attempt 1 실패 후 attempt 2 가 `node:"pipe", action:"(2단)", status:"ok"` 로 완주하고 괄호 안 `take` 까지 적용된 2행 반환(`_fallback_used: 2`). 두 문서를 구현에 맞췄다.
- **관찰(빈 알림) 수리됨** — 원인 특정: `system_tools.execute_send_notification` 이 **빈 message** 로 불렸고(`source="ai"`), `derive_title("")` 의 기본값 "알림"이 제목 자리를 채워 **내용 없는 껍데기**가 알림함과 화면까지 갔다. 파생은 내용이 있을 때 제목을 채우는 장치이지 없는 내용을 있게 만드는 장치가 아니다. 두 관문 모두에 같은 규칙: `notification_manager.create()`(기록, 호출처 18곳 공통 입구) + `notify_dispatch.notify_user()`(전달 — 전달은 기록 실패와 무관하게 진행되는 구조라 여기서 안 막으면 반쪽 수리).
- **회귀 그물**: `backend/test_handler_error_contract.py` 6건 신설 — 한글 접두 판정 · 정상 문자열 과잉거절 방지 · **계약이 dict 인가**(접두 없는 실패도 잡히는가) · 소스에 평문 오류 return 이 남지 않았는가(후퇴 방지) · 파이프 싱크 3형 · cctv 통화+선언. 라이브 기준 5/6 통과, 나머지 1건(한글 접두)은 그 수리가 **지연 적용 대기**라 적용 후 6/6. 기존 배터리 회귀 없음(`test_pipe_currency_failures` 전부 통과 · `test_notify_title` exit 0).
- **시드 8건 집행** (2026-08-22 18:4x, 사용자 승인) — 코퍼스 3,549→3,557 · `ibl_distilled` 833→841. ①**21회차 후보 5건**: 중심은 **폴백 `??`**(문법 축에서 유일하게 행동 조합 0% 였다 — 코퍼스가 안 가르치니 번역기도 안 쓰던 고리를 끊는다) + 축적 `reduce`·고차 `each>>flatten`·`limb` 조회. ②**이번 수리가 새로 참으로 만든 문형 3건**(20회차 규율 계승 — "판정이 새로 참으로 만든 문형만 가르친다"): `>> [engines:render_html]` 파이프 싱크(V21-1, 전엔 "html은 필수"로 죽던 문장) · `[self:cctv]{op:"stats"} >> [table:*]`(V21-2, 전엔 통화 없음 거절) · `?? ( … >> … )` 괄호 가지(F21-1, 구현은 됐는데 교재가 막던 문형). ★검증: 8건 전건 `/ibl/validate` + **라이브 실행까지 8/8** · 벡터 색인 8/8 실적 대조(`ibl_examples_vec_rowids` — `_index_batch` 는 실패를 삼키므로 계수로 확인) · 라이브 회상 실증("테슬라 주가 알려주고 안 되면 웹에서라도"→0.853 으로 새 `??` 괄호 시드, "월세 매물 한 곳이 비면 다른 사이트에서"→0.803, "환율 요약해서 이미지로"→0.629 로 render_html 파이프 싱크). ⏳재학습 대기열 합류.
- **미집행 1건**: 시드 스크립트를 `scripts/seed_imagination_round_21.py` 로 남기지 못했다 — `scripts/` 는 RED 인데 이 턴이 수리 경로가 아니어서 쓰기가 거절됐다(게이트가 정직하게 막은 것). 시드 목록·태그·검증 근거는 이 항목에 남겼으므로 재현 가능하며, 다음 수리 턴에 스크립트로 고정하면 된다.

- `F19-3` **종결** — 19회차가 '기록만'으로 남긴 항목. 08-22 15:03 `b5b564f` 가 이미 수리했고(이후 턴에서 낡은 기억만 보고 '미수리'로 오보한 일이 있었다), 08-22 커밋 `52bc6e9` 가 회귀 테스트로 못박았다(`test_e6_multiline_indent_preserved` — 부정 대조 `b5b564f^` 에서 이 케이스만 실패).


### ★21회차 평가 후속 — 판정 규칙 개정 + 부류 봉쇄 집행 (2026-08-23, 사용자 지시 "판정 없이 근본 집행")
- **평가 요지**: 깨끗 비율 46%(1~3회차)→83%(18~21회차), 결함 심각도 하락(실행 불능→관측성) = 문법 축 수렴. 그러나 침묵/거짓 성공 **부류**가 자리만 바꿔 7회 재발(B8→B10→F14-1→B15-1→F18-1→B19-1→B21-1), 통화 비준수 5회(F6→F8→V13-1→F16-2→B19-2). 몸 지표(행동)는 13→21회차 평탄(조합 38→31·파이프율 18.4→15.0%) — 움직인 건 교재뿐. 맴돌기의 실체 = ①부류 재발 ②판정 보류 장기화(F1 19일·F15-1 4표본).
- **원인(사용자 질문 "왜 자꾸 판정·보류로 안 고치나")**: 가이드 4-3·보고서 양식이 결함과 어휘 신설을 같은 판정 통로로 보냄 + "판정 금지" 교정의 과잉 일반화 + 비싼 부류 스윕을 판정 서랍에 미룸. → 가이드 개정 `a222880`: **판정 요청=언어 개정·파괴적 변경 2종만**, 결함·부류 스윕·가드는 동세션 근본 집행, 보류는 2회차 안에 닫기.
- **집행 ① 정직성 불변식 가드** `scripts/honesty_invariants_sweep.py` + `backend/test_honesty_invariants.py`(13) + 주간 번들 §8.6b(`fixture_sweeps.run_honesty_sweep`, self_checks `honesty_invariants`): fixture 우주 132 에 A(거짓 성공)·B(통화 부재)·C(0행 거짓) 단언 — 부류를 봉투 입구 하나에서. 첫 실측 **132/위반 0**(지금까지의 수리 전부 유지). D=텍스트 계약(접두) 자리 18(system_essentials — 부채 아님, execute()->str 계약).
- **집행 ② `ibl_executors.py` 1471줄 이사** `b52eb24`: 출력·목표·each·소스평가 4형제 모듈, 파사드 재수출(배터리 70/70·층·크기·build 가드·라이브 실측).
- ⏳번들 첫 자동 실행(주간) 관찰. 훈련 빈도는 낮추고(결함 0 연속 2회차 기준) 실사용 관찰로 — 22회차는 관찰 2주 뒤.
