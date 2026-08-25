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

**시드 12건**(`scripts/seed_f20_verdicts.py`, 코퍼스 3,537→3,549 · `ibl_distilled` 821→833): 판정이 **새로 참으로 만든 문형**만 가르친다 — ①감시자 꼬리 `>> [table:since] >> [table:brief]`(수리 전엔 첫 실행마다 error 라 코퍼스에 거의 없었다. 08-21 재학습 잔여 실패 5건이 전부 since·ai·brief 였던 것도 이 희소가 원인) + 0행이 정상인 intent("없으면 없다고") ②변이별 열 이름(naver=price·title / zigbang=distance_m / molit=거래금액·전용면적) — 카탈로그가 이제 말하는 사실을 코퍼스도 말한다 ③무제목 알림(`{message:}` 와 파이프 꼬리 `{}`) — title 을 message 복붙으로 채우는 습관이 생기지 않게 제목 없는 문장만. ★검증: 전건 `/ibl/validate` + **부작용 없는 8건은 라이브 실행까지**(그 과정에서 `[sense:stock]{symbols:}` 오문이 잡혔다 — validate 는 통과시키고 런타임이 거절하는 부류라 검증만으로는 못 거른다) · 벡터 색인 12/12 실적 대조(★`_index_batch` 는 실패를 삼킨다) · 라이브 회상 3발 실증(변형 질의가 새 시드를 근거로 zigbang=distance_m·naver=price 를 정확히 냄). ⏳재학습 대기열 유지 — **08-22 재학습은 기각**(게이트 보류 권고: desc T1 −4.1p·프로브 46→43/51). ★기각 근거는 트레이드의 내용이다: 새 모델이 잃은 프로브가 하필 이번에 시드한 `table:since` 2건 전부였다. **진단=파이프 안 시드는 그 낱말 단독을 안 가르친다**(학습은 `normalize_code_to_pattern` 으로 복합 패턴을 만들어, 짧은 질의가 머리 액션으로 끌린다) — 다음 시드는 같은 낱말의 **단독 문장**을 함께 넣을 것. 시드 자체는 코퍼스에 남아 하이브리드 검색에서 이미 작동한다(재학습 없이 회상 직행 실증).

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

### 22회차 (2026-08-22 19:1x — 보고서 `outputs/imagination_training/2026-08-22_22회차.md`)
- **★카덴스 이탈 고지**: 21회차 평가는 "22회차는 관찰 2주 뒤"로 적었으나, 사용자가 이번 턴에 직접 요청해 앞당겨 실행했다(관찰 대기가 아니라 지시 이행).
- **중점 전환 — 처녀 '어휘'에서 처녀 '문법'으로**: 도달 가능한 처녀 액션 17건 중 14건을 20·21회차가 이미 소진했고 남은 3~4건은 하드웨어·설치 부작용이라 실측 규율 밖. 그래서 코퍼스 3,557 전수 census 로 가장 안 쓰인 **문법 낱말**을 메뉴로 삼았다: `[finally]`1 · `[try]/[catch]`2 · `[on_error:]`2 · `$return`2 · `[case:]`3 · `spill`3 · `[goal:]`4 · 식할당5 · `[repeat:]`6 · `$items`7 · `reduce`8. M3·M4·M6 = "문법으로 존재하되 아무도 안 쓴 지대".
- 지표(훈련 전): 행동 207문장·조합 31(15.0%)·미조합 113/151 — 21회차와 동일(훈련은 증류에 안 담기므로 정상). 교재는 3,557·미조합 **23→19**(도달 가능 21→17) — 21회차 시드 8건이 4자리를 옮겼다.
- 검수 14/14, 실측 12건. **깨끗 10 · 꼬임 1 · 결함 2.**
- `B22-1` **(결함)** 워크플로우 시그니처가 **식 할당의 우변**을 인자로 오인 → 교재 M6 의 `do: "…$return = $x"` 저장본이 **저장은 되고 실행은 거절**된다. 재현: `save{do:"$r = [self:time]\n$return = $r"}` → `params_required:["r"]`, `run` → "인자 누락: $r". 격리로 경계 확정 — param 값 자리 참조는 정상(치환됨), **식 할당 우변만** 리터럴로 남아 오탐. 뿌리 `backend/ibl/workflow_contract.py:77 _free_vars()` 가 `사용 − 할당` 이 아니라 `사용` 만 센다. ★오늘(08-22) 들어온 시그니처 검사(W8 침묵 실패 수리)의 그물이 M6 패턴까지 걷어 올린 것. 제안=bound(assign 대상) 차집합 + `test_workflow_params.py` 4행 격리표 가드.
- `B22-2` **(결함)** `[self:write]{spill: true}` 가 **파이프 통화를 대체하지 않는다** — 파일은 써지는데 다음 step 이 상류 전량을 그대로 받는다(step2 count 0·ref 봉투인데 step3 take 가 realty 90행 봉투 수신). 결정적 실측: `spill` 뒤 파이프 싱크 `[self:write]` 를 하나 더 물리면 `q3_spill.json` 745B = `q3_after.json` 745B(같은 전량). 원인=`self:write` 가 `returns: effect` 라 파이프가 통화 무변경 통과로 다루고, `spill:true` 예외가 없다. **빈 통화 폴백이 아님**(진짜 0행은 정직하게 0으로 흐름 — filter 0행→take 0행 실측). 시험 사각: `test_ibl_program_grade.py:118 test_e3_write_spill_ref` 는 **write 자신의 봉투**만 보고 *다음 step 의 입력*은 아무도 안 본다(계약의 절반만 시험). 제안=spill step 봉투를 다음 step 통화로 채택 + 가드를 "다음 step 이 무엇을 받나"로 확장.
- `F22-1` **(마찰/관측)** `[table:groupby]` step 이 `shape:"effect"` 로 신고 — transform 인데. 파이프는 돌지만(다음 sort 가 19행 수신) 주행기록·X-ray 가 "통화 끊김"으로 읽는다. 뿌리 `data-ops/handler.py:625 _op_groupby` 가 `_emit_table` 로 `columns/rows` 만 내고 `items` 를 안 실음(통화=items 헌법의 잔여 자리). 제안=`_emit_table` 이 items 동봉 + "transform 은 shape 이 effect 가 아니다" 단언.
- `F22-2` **(마찰/정직성)** groupby 가 상류 `total`/`truncated` 승계 — 100행을 집계했는데 봉투는 `total:1179, truncated:true`(rows count 합=100). 집계표를 "1179건 집계"로 오독하게 만든다. 제안=집계 verb 는 자기 행수로 total 재작성(또는 `source_total` 개명) + `_emit_table`/`_emit_items` 소비 verb 전수 스윕.
- `F22-3` **(마찰/교재)** `[table:since]{peek:true}` 는 기준선을 **영원히 기록하지 않아** peek 로 짠 감시 문장은 항상 "새 것 0". 봉투 `note` 는 정직("첫 검침(peek) — 기준선 저장 안 함(5행 미기록)") — 침묵 아님. 문제는 카탈로그 한 줄에 함정이 없고, **훈련의 스크래치 규율이 21·22회차 훈련자를 연달아 peek 으로 밀었다**는 점. 제안=카탈로그·트리거 가이드에 "peek=미리보기, 감시엔 쓰지 말 것" 한 구(신설 0).
- **오진 격리로 반증(원장 미등재)**: ①코퍼스가 가르치는 `[sense:stock]{symbol:…}`·`[sense:used]{q:…}` 가 tool.json 스키마(`ticker`·`query`)와 달라 침묵 유실을 의심했으나 **네 표기 전부 동일 결과**(별칭 수용) — 결함 아님. ②21회차 관찰 '알림 제목 빈칸' 은 이번 회차 정상(`title:"상상훈련22: 새 글 없음"`) — 알림 경로 수리가 들었다.
- **확인된 열매**: M4 `[repeat:]` 두 모드 실동(count+collect 3회차 15행 / while+식할당 `$n`=3, `_var_updates` 신고) · M3 `[try]` 몸통의 **파이프가 끝까지 돎** · `each{on_error:"skip"}` 완주 · **괄호 병렬 분기** `A & (B >> rename) >> merge` 20행(21회차 폴백 괄호에 이어 병렬 괄호도 야생 확인) · `[case:]` 가 `matched`·`matched_value` 신고(F19-1 관측성이 case 에도 생존) · `reduce` 도메인 2회차 실동(22거래일 종가 5,455,000).
- **시드 후보 8건**(실행 검증 통과, 승인 대기) — try/on_error/repeat/case/괄호병렬 중심. `$return` 워크플로우·`spill` 문장은 **B22-1·B22-2 수리 전이라 의도적으로 제외**(안 도는 문형을 가르치지 않는다).
- **판정 요청 0건**(전부 수리성). 스크래치 전량 원상복구 확인 — 워크플로우 7 · since 키 2(10행) · 알림 1 · tmp 파일 4 · 저장소 미커밋 0.

### ✅ 22회차 판정·수리 집행 (2026-08-22 19:4x — 평가 지적 "결함을 다음 턴으로 미뤘다" 수용)
- **경계 재확인**: 가이드 4-3 현행 원문을 `self:grep` + `git show a222880` 로 실측. "훈련 세션은 스스로 고치지 않는다"는 **누가 고치나의 경계**일 뿐이고, 같은 항목이 "대장장이 고리는 결함(B)을 판정 대기로 넘기지 않고 동세션에 근본 수리한다"를 명시한다(08-23 사용자 교정, `a222880`). 22회차 첫 응답이 인용한 4-3 은 그 단서를 빠뜨린 절반 인용이었다 — 정정하고 동세션 집행.
- `B22-1` **수리됨 — 진단이 원장보다 넓었다**. `_free_vars` 를 `사용 − 할당` 으로: `workflow_contract.py` 에 `_bound_names(steps)` 신설(묶는 자리 셋 — `_assign_name` 파이프/액션 할당 대상 · `_assign` step 의 `name` 식 할당 · `_repeat` 의 `var` 회차 변수, 중첩 몸까지 순회) → `_free_vars` 예약 집합에 차집합 합류. 격리 실측으로 드러난 실제 파손 범위는 `$return` 하나가 아니라 **M6 상태 변수 전 계열**: `$return = $r`→`['r']` · `$n = 0` + `[repeat: while $n < 3]`→`['n']` · `$total = A>>B; $avg = $total.value/10; $return = $avg`→`['total','avg']` · `[repeat: 3]{… page:"$i"}`→`['i']` 가 전부 "호출자가 채워야 할 인자"로 계산돼 저장본이 실행 불가였다. 수리 후 전부 `[]`, 진짜 자유 변수(`$topic`)와 혼합 케이스는 그대로 `['topic']` — **W8 무회귀**. ★위치가 아니라 집합으로 뺀다(할당 전 참조도 인자로 안 셈) — W8 이 막으려던 것은 *한 번도 할당되지 않는* 이름이고 그건 차집합 뒤에도 걸린다.
- **회귀 그물**: `test_workflow_params.py` **W16** 신설 — 위 6행 격리표를 그대로 단언 + 저장본 실행(`$return` 몸통이 인자 요구 없이 success)까지. 배터리 **W1~W16 전부 통과**(기존 15건 무회귀). 부정 대조: 라이브(미패치) 모듈로 같은 표를 돌리면 4행이 FAIL.
- `B22-2` **철회 → `F22-4`(문서 마찰)로 재분류 — 오진이었다**. `spill` 이 "계약을 어긴다"는 진단은 틀렸다. `backend/common/spill.py` 머리주석이 설계를 명시한다: *"소비자(변환자 `_get_items`·each 입력·`$items` 바인딩·write 싱크)는 `resolve_ref` 한 줄로 **투명하게** 읽는다."* 뒤 step 이 원본을 보는 것은 의도된 동작이고, spill 이 덜어내는 것은 파이프 데이터가 아니라 `results[]`·모델 컨텍스트다(`architecture.md:209`·`technical.md:140` 이 옳게 적고 있었다). **원안대로 "spill 봉투를 다음 통화로 채택" 했다면 투명 해소 설계를 깨뜨렸을 것**이고, `test_e3_write_spill_ref` 가 write 봉투만 보는 것도 계약의 절반이 아니라 전부였다. 진짜 결함은 **문서 두 곳**: 프롬프트 카탈로그(`12_ibl_only.md`)와 어휘 desc(`system_essentials/ibl_actions.yaml` 2자리)가 "뒤 step 이 데이터 대신 참조를 받는다(재개는 `[self:read]`)"고 가르쳐 훈련자를 오진으로 밀었다. → 두 문서를 구현·정본 문서와 같은 말로 정정, `build_ibl_nodes.py` 재빌드 + `--check` 삼각 검증 통과(바이트·tool.json 40패키지·문서 파생 9·core_manifest·설치필터 일치). **코드 0줄**.
- **관문**: `[self:patch]{op:"apply"}` → `verified: true` · 4관문(`live_sync`·`py_compile`·`import_smoke`·`ibl_triangle`) 통과 · 2파일 · `backend/*.py` 라 **지연 적용 예약**(턴 종료 후 분리 수행자 재검증→반영, 리로드 1회). 데이터 파일(카탈로그·어휘 desc)은 즉시 라이브.
- **시드 조정**: `$return` 워크플로우 문장은 이번 시드 후보에서 제외 유지 — 수리가 지연 적용 대기라 라이브에서 아직 안 돈다. 적용 확인 뒤 다음 회차에 올리는 것이 20회차 규율("판정이 새로 참으로 만든 문형만 가르친다")에 맞다.
- **남긴 것**: F22-1(groupby shape=effect) · F22-2(groupby 가 상류 total 승계) · F22-3(since peek 문서) — 이번 판정 대상 아님, 전부 수리성.

### 23회차 (2026-08-22 20:1x — 보고서 `outputs/imagination_training/2026-08-22_23회차.md`)
- **중점 — 실패 경로**: 22회차가 M3·M4 를 처음 돌렸지만 전부 **행복 경로**였다(catch 미발동·on_error 미발동 — try 몸통과 ai 가 안 죽었다). 코퍼스 census 도 같은 말: `resume` 0 · `halted` 0 · `condition_errors` 0 · `repeat:until` 1 · `$error` 2 · `[catch]` 2. 그래서 23회차는 **일부러 죽는 문장**(없는 호스트 / 없는 열)으로 실패 경로를 전수 답사했다.
- 지표: 행동 208문장·조합 31(14.9%)·미조합 113/151 / 교재 3,558·미조합 19/151. 검수 13/13, 실측 13건 + 재개 프로브 3중 대조. **깨끗 11 · 꼬임 1 · 결함 1.**
- `B23-1` **(결함 — 침묵 부류 재발, 자리만 바뀜)**: 파이프가 죽으면 봉투가 `resume: {from_step, prev_ref}` 와 함께 *"execute_ibl(code, resume={…}) — 앞 단은 재실행하지 않습니다"* 라고 정확히 안내하는데, **`/ibl/execute` 와 MCP `execute_ibl` 에 `resume` 파라미터가 없어 그 값이 조용히 버려지고 문장이 처음부터 다시 돈다.** 결정적 재현: 1단을 '재실행하면 반드시 죽는' URL 로 바꿔 resume 과 함께 재호출 → `steps 0/3`, "Step 1 에러"(resume 이 들었다면 1단은 안 돌았어야 한다). resume 없이/문자열 prev_ref 로도 **완전히 동일**. 코드 실측: 발급=`workflow_engine.py:309` · 유일 수신자=`system_tools_ibl.py:387` · 인프로세스 도구 스키마 선언=`tool_loader.py:210` · **`api_ibl.py` 0건 · `mcp_server.py` 0건**. 즉 재개는 인프로세스 에이전트에게만 닿고 아웃오브프로세스 표면(REST·MCP·조종실·훈련 가이드 curl)엔 통로가 없는데 **note 는 표면을 안 가리고 모두에게 나간다**. ★교재 `resume` 0건이 우연이 아니었다 — 닿을 수가 없었다. 제안=두 표면에 passthrough 추가(엔진은 이미 받는다) + 미지원 표면은 정직 거절 + `tool_loader.py` 스키마에만 있고 REST·MCP 에 없는 파라미터 전수 대조 스윕.
- `F23-1` **(마찰/봉투 오독)**: 파이프 봉투의 `results[]` 는 step 요약인데 **블록 문장(`[try]` 등)의 `results` 는 핸들러 원문**(검색 결과 배열)이다 — 같은 키 다른 뜻. 판별자는 이미 있다(파이프에만 `_results_summarized`·`steps_total`·`final_result`, 블록엔 `_caught`·`_untransformed`). 실체는 **카탈로그 '봉투 읽는 법'이 판별 규칙을 안 가르치는 것**. 제안=카탈로그 한 구, 코드 0줄.
- `F23-2` **(마찰/낮음)**: `[repeat:]` 가 `halted:"max"` 로 멈추면 note 는 "성공 아님·실패 아님"이라 말하는데 봉투 최상위 `success: true`. 자동화가 success 만 보면 "조건 만족하고 끝났다"로 읽는다. 제안=`halted` 최상위 승격 또는 halted 시 success 미탑재.
- **관찰(결함 아님)**: `[table:document]` 는 `path` 생략 시 고정 이름 `projects/<프로젝트>/outputs/document.md` 로 써서 두 번 부르면 앞 산출물을 말없이 덮어쓴다(이번엔 사전 부재 확인 후 삭제). `data/spill/` 76개는 cache 계급 24h GC 라 손대지 않았다.
- **확인된 열매 — 실패 경로는 대부분 모범적이었다**: `[catch]` 실발동 + `_caught` 로 삼킨 오류 전문 보존(삼키되 숨기지 않음) · 이중 실패 시 `try_error`/`catch_error` 를 `{error, step, summary, node, action}` 로 나란히 · `skip`(직전 통화 2행) vs `null`(0행) 정확 대조 + `skipped_steps:[2]` + 죽은 step `shape:"error"` · `??` 폴백 실발동 `type:"fallback"`·`attempts[]` 에 1차 실패 사유 · `each` 실패 행만 `_ok:false`+`_error` 격리하고 나머지 생존 · `condition_errors` 로 판정 불능 시 **else 보류**(헌법 조항이 코드로 생존) · `repeat: until` 실동 + `halted:"max"` 명문 note.
- **★B22-1 수리 야생 검증**: `[self:workflow]{op:"save", do:"$r = [self:time]\n$return = $r"}` 가 인자 요구 없이 저장(`params_required` 없음)되고 run 이 `returned:"$return"` 으로 완주. 22회차 발견→같은 날 수리가 실제로 새 문형을 참으로 만들었다(커밋 `30ec862`).
- **시드 후보 8건**(승인 대기) — 실패 경로 중심(try/catch·on_error skip·repeat until·each on_error) + struct·structure→document·host resources + **`$return` 워크플로우**(22회차엔 지연 적용 대기라 뺐던 것, 이번에 라이브 검증 완료).
- **집행 0건 — 사유 명시**: B23-1 의 수리 자리가 `api_ibl.py` 와 **`mcp_server.py`** 인데, 후자는 이 세션이 자기 손을 통과시키는 통로다. 표면 재기동이 필요한 배관을 훈련 턴에 갈아 끼우는 것은 가이드 4-3 의 "도는 몸이 비행 중에 자기를 고치지 않는다"에 정확히 해당. 수리성이지 판정성이 아니며 다음 `#repair` 턴 첫 항목.
- **판정 요청 0건.** 스크래치 원상복구 확인 — 워크플로우 1 · document.md 1 · tmp · 알림 0 · 작업트리 깨끗.

### ✅ 23회차 판정·수리 집행 (2026-08-22 20:4x — 사용자 `#repair` "발견된 오류들을 수리해줘. 시드도 처리해주고")
- `B23-1` **수리됨 — 부류 스윕이 같은 구멍 3개를 더 찾았다.** 보고서 제안대로 도구 스키마(`tool_loader.py`) 파라미터를 REST·MCP 와 전수 대조: `code`(O/O/O) · `verbose`(O/O/**X**) · `resume`(O/**X**/**X**) · `files`(O/**X**/**X**). resume 만이 아니라 **`files`(파서 밖 `$file:0` 통로)와 `verbose` 도 같은 부류**였다 — 자리 하나가 아니라 부류를 닫았다. ①`backend/surface/api_ibl.py`: `IBLRequest` 에 `resume`·`files` + 호출부에서 값 있을 때만 `tool_input` 에 실어 옛 호출 무회귀 ②`mcp_server.py`(RED 아님·즉시 라이브 기록): `execute_ibl(code, project_path, resume, files, verbose, ctx)` + payload 패스스루 + docstring. **실측**: 격리 `IBLRequest(resume=…, files=…)` → tool_input 키 `['code','files','resume','verbose']`, 라이브(미패치) 모델엔 `resume` 필드 자체가 없음(False). 결정적 시험 — 1단이 '재실행하면 반드시 죽는' 문장에 resume 을 실으면 `success=True · steps 2/2`(step2·3만 실행), resume 없이는 `0/3` 사망. ★`mcp_server.py` 는 **MCP 서버 프로세스 재시작 전까지 새 스키마가 안 보인다**(이 세션의 도구는 아직 옛 3파라미터).
- `F23-1` **수리됨(코드 0줄)** — 카탈로그 '봉투 읽는 법'에 판별 규칙: "`results` 키가 보인다고 step 요약이라 단정 금지 — 단일 액션·블록 문장의 `results` 는 핸들러 원문. 판별자는 `_results_summarized`·`steps_total`·`final_result`". 데이터 파일이라 즉시 라이브(grep 확인).
- `F23-2` **수리됨** — `workflow_engine` 이 `skipped_steps` 와 **같은 승격 규약**으로 `halted_steps` 를 봉투 최상위에 싣고 경고를 붙인다. 실패로 뒤집지 않았다(통화는 실제로 나왔고 note 도 "실패 아님") — 문제는 판정이 아니라 **보이지 않음**이었다. 패치된 엔진 실측: `halted_steps: [{"step":2,"halted":"max","iterations":3}]` + `warning: "…success 만 보고 '조건 달성'으로 읽지 말 것."` (수리 전엔 최상위에 없고 final_result 안에만).
- **관문**: `[self:patch]{op:"apply"}` → `verified: true` · 4관문(`live_sync`·`py_compile`·`import_smoke`·`ibl_triangle`) 통과 · 3파일(`api_ibl.py`·`workflow_engine.py`·`scripts/seed_imagination_round_23.py`) · `backend/*.py` 포함이라 **지연 적용 예약**(이 턴의 진실은 '검증 통과·적용 예약', 라이브 아님). 위 실측은 전부 격리 사본 또는 라이브 엔진 직접 호출에서 얻었다.
- **시드 8건 집행 (3중 대조)** `scripts/seed_imagination_round_23.py`: `/ibl/validate` **8/8** · 라이브 실행 **8/8** · 벡터 색인 **8/8**(`ibl_examples` 3,559→**3,567**, `ibl_examples_vec_rowids` 3,559→**3,567**, 행 수 == 벡터 수) · `ibl_distilled` 843→**851**. 내용 = 실패 경로 문형 4(try/catch · on_error skip · repeat until · each on_error) + 통화·산출 3(struct · structure→document · host resources 정렬) + **`$return` 워크플로우 1**(22회차 B22-1 수리가 새로 참으로 만들고 23회차가 야생 검증한 문형 — 20회차 규율). 라이브 회상: try/catch 0.906 · host 정렬 0.884 · repeat until 0.772 · each on_error 0.650 — 다만 `$return` 워크플로우 프로브는 **엉뚱한 데로 갔다**(`[sense:listen]` 0.768) → ⏳재학습 대기열.
- ★**B23-1 에는 시드가 없다** — `resume` 은 IBL 코드가 아니라 도구 파라미터라 문장으로 표현되지 않는다. 가르칠 자리가 코퍼스가 아니라 도구 스키마·문서다.
- **범위 규율**: 사용자가 명령한 범위(23회차 발견 오류 + 시드) 밖의 리팩터링은 하지 않았다. 보고만 하는 것 2건 — `[table:document]` 의 기본 출력 경로가 고정 이름(`outputs/document.md`, 두 번 부르면 앞 산출물을 말없이 덮어씀) · `data/spill/` 76개는 cache 계급 24h GC 라 손대지 않음.

### 24회차 (2026-08-22 21:0x — 보고서 `outputs/imagination_training/2026-08-22_24회차.md`)
- **중점 — 가장 많이 쓰는 문법의 실패 거동**: 23회차가 *순차* 실패를 답사했는데(try/catch·on_error·`??`·each 전부 모범), 행동 지표 압도적 1위 조합 문법은 **`&` 병렬 18.7%** 이고 그 실패 거동은 아무도 본 적이 없었다. 교재 census: `&` 141 · 괄호분기 1 · **try 안 & 0 · each 중첩 0 · ??3단 0** · join 6 · merge 4 · `$items` 7 · goal 4.
- 지표: 행동 209문장·조합 31(14.8%) / 교재 **3,567**(23회차 시드 8건 반영). 검수 12/12, 실측 12건. **깨끗 8 · 꼬임 1 · 결함 3(뿌리 하나).**
- `B24-1` **(결함 — 침묵/거짓 성공 부류의 여덟 번째 자리)**: **병렬 분기의 실패를 봉투가 세지 않는다.** ①한 가지 실패 → `success: true`, 최상위에 실패를 가리키는 키가 **하나도 없음**(죽은 가지의 error 는 final_result 리스트 안 JSON 문자열로만) ②**전 가지 실패도 `success: true`** — 아무것도 못 가져왔는데 성공 봉투 ③`>> [table:merge]` 가 죽은 가지를 조용히 삼켜 살아있는 3행만 내고 경고 0. 뿌리: 순차는 `skipped_steps`·`statements_failed`·`halted_steps`, 폴백은 `attempts[]` 로 신고하는데 **`branches_failed` 는 코드베이스 전체에 0건** — `workflow_parallel.py:140` 이 가지 리스트만 돌려주고 호출부가 가지별 `_is_error_result` 를 한 번도 안 부른다. ★대조가 진단을 못박는다: 같은 파일 `:85-88` 은 **괄호 분기 안쪽** step 실패를 `_branch_step_failed` 로 정확히 신고한다 — **분기 내부는 세고 분기 자체는 안 센다.** ★2026-08-22 정직성 불변식 가드(fixture 132·위반 0)가 못 잡은 이유 = 그 우주가 **단일 액션 봉투**뿐이라 병렬 봉투가 없다. 제안: (a)`branches_failed` 를 `skipped_steps`/`halted_steps` 와 같은 승격 규약으로 (b)전 가지 실패면 `success:false`(**파괴적 변경 — 판정 요청**) (c)이항 변환자가 실패 가지를 받으면 경고(W6 "공유 칸 0" 경고와 같은 배관) (d)**부류 스윕 — 정직성 fixture 우주에 병렬 봉투 추가**.
- `F24-1` **(마찰)**: 괄호 분기가 죽으면 union 이 *"통화 종류가 같아야 합니다"* 라는 **2차 증상**만 말하고 진짜 원인(분기 사망)은 안 보인다. B24-1(a) 가 고쳐지면 종속 해소.
- **확인된 열매 — ★B23-1 수리가 고장났던 바로 그 표면에서 검증됐다**: MCP `execute_ibl` 의 새 `resume` 파라미터로 재개 실행 → `resumed_from: 2` · `steps 2/2`, 1단(재실행하면 반드시 죽는 URL)은 실행되지 않음. 23회차엔 "닿을 수가 없어" 교재 0건이던 문법이 이제 이 세션의 손에서 돈다. 그 밖: F23-2 `halted_steps` 라이브 생존(`52dce56`) · **이항 변환자 3형제 전부 모범**(join=양쪽 열 목록 제시하며 거절 / union=이질 열에 "공유 칸 0" 경고 달고 통과 / 스칼라 가지=정직 거절) · **each 중첩 실동**(교재 0건, ok 2/err 0) · **`$items` 첫 실측**(교재 7·행동 0 — 32행→3행→**마커 3개 지도 1장**) · `on_error`×병렬 교차 동작 + take 의 **교재급 거절문**(병렬 뒤엔 이항 변환자가 먼저, 괄호 분기 예시까지) · **`[goal:]` 블록 실동**(교재 4·행동 0 — 생성·list·status 조회).
- **관찰**: goal 원장은 **프로젝트 축으로 갈린다** — `project_id:"컨텐츠"` 로 만든 목표가 시스템 AI 컨텍스트 `[self:goal]{op:"list"}` 엔 안 보인다("등록된 목표가 없습니다"). 스크래치 정리에서 한 번 헛짚었고 프로젝트 지정 재조회로 2건 찾아 kill+delete.
- **시드 후보 5건**(승인 대기) — each 중첩 · `$items` 지도 · try 안 병렬 · union 이질 열 · goal 블록. **B24-1 이 걸린 병렬 실패 문형은 제외**(지금 가르치면 "실패해도 성공으로 보이는 문장"을 가르치게 된다 — 수리 후 다음 회차).
- **판정 요청 1건** — B24-1(b) 전 가지 실패 시 `success:false` 는 **파괴적 변경**(기존 문장·스케줄·트리거가 멈춘다). (a)(c)(d)는 순수 가산이라 판정 불요. 훈련자 의견=바꾸는 쪽.
- **집행 0건** — 가이드 4-3 개정본대로 훈련 턴은 라이브 코어를 안 고친다. 다음 `#repair` 턴이 '집행 완료' 절을 채운다.

### ✅ 24회차 판정·수리 집행 (2026-08-22 21:3x — 사용자 `#repair` "네 의견대로 고쳐. 시드도 처리하고")
- **판정 1건 승인** — B24-1(b) 전 가지 실패 시 `success:false`(파괴적 변경)를 사용자가 훈련자 의견대로 승인. 나머지 (a)(c)(d)는 순수 가산.
- `B24-1` **수리됨 — 네 갈래 전부**: (a)`branches_failed` 를 `skipped_steps`/`halted_steps` 와 같은 승격 규약으로(판정은 단일 소스 `_is_error_result`) (b)전 가지 실패는 **순차 step 실패와 같은 경로**로 보내 `success:false` + resume 참조까지 자동 (c)`data-ops/handler.py` 에 `_attach_branch_warning` 신설 — union·merge·join 5자리에 부착(죽은 가지는 items:[] 로 흘러 조용히 삼켜지던 자리) (d)정직성 스윕에 불변식 **E(병렬 봉투)** + **네트워크 없는 결정론 프로브 3**(fixture 우주가 단일 액션뿐이라 병렬이 한 번도 측정 안 되던 사각 — 그래서 여덟 번째 자리가 났다).
- **재현 실측(패치된 엔진, 보고서에 적힌 그 문장 그대로)**: ①한 가지 실패 → success true 유지 + `branches_failed`(분기 2·node·action·error) + `[병렬] 분기 실패: step 1(1/2 분기)…` 경고 ②전 가지 실패 → **success false** · steps 0/1 · `Step 1 병렬 전 가지 실패(2/2): …` ③죽은 가지+merge → items 3 그대로 + `결합 입력 중 분기 2 이(가) 실패했습니다 — 그 분기는 0행으로 흘렀습니다` ④**무회귀**: 정상 병렬 → items 7 · branches_failed 없음 · warning 없음.
- `F24-1` **수리됨 — "자동 해소"가 아니었다**. 중단 payload 는 봉투 조립부를 거치지 않아 `branches_failed` 가 통째로 사라졌다(괄호 분기가 죽으면 union 의 2차 증상만 보이던 이유). `_handle_failure` 중단 경로에도 싣도록 고쳤다 → 이제 2차 증상(`union: 통화 종류가…`) **옆에** 진짜 원인(분기 2 사망)이 선다.
- **곁가지**: 경고 생산자가 셋(repeat 상한·on_error 건너뜀·병렬 분기 실패)이 되면서 `out["warning"]` **덮어쓰기**가 드러남 — 모아서 `" / "` 로 한 번에 싣도록 수정.
- **가드**: `test_honesty_invariants.py` **+4**(실패 신고 필수 · 전 가지 실패는 성공 아님 · 정상 병렬 무회귀 · 프로브 우주가 결정론인지). 격리 배터리 **17/17**, `test_pipe_currency_failures` **22/22**(무회귀).
- **관문**: `[self:patch]{op:"apply"}` → `verified: true` · 4관문 통과 · **4파일** · `backend/*.py` 포함이라 **지연 적용 예약**(이 턴의 진실은 '검증 통과·적용 예약'). `data-ops/handler.py` 는 RED 아님=즉시 라이브. `build_ibl_nodes.py --check` 삼각 검증 통과.
- **시드 5건 집행 (3중 대조)** `scripts/seed_imagination_round_24.py`, `add_examples_batch` 단일 경로(`_load_model_sync()` 선행): validate **5/5** · 라이브 실행 **5/5** · 벡터 색인 **5/5**(`ibl_examples` 3,567→**3,572**, 행 수 == 벡터 수) · `ibl_distilled` 851→**856**. 변형 질의 회상: "각각 검색하고 그 결과마다 또 처리"→**0.906** · "두 군데 동시에 보고 안 되면 검색"→**0.777** · "맛집 여러 곳 지도 한 장에"→**0.767**. 나머지 둘은 아직 못 당김("모양 다른 두 목록을 한 표로"→0.612 · "코스피 떨어지면 알림 줘"→0.800 — 둘 다 옛 용례로) ⏳재학습 대기열.
- ★**병렬 실패 문형은 시드에서 계속 제외** — 수리가 지연 적용이라 시딩 시점 라이브가 아니었다. 적용·야생 검증 후 다음 회차(20회차 규율).
- **범위 규율**: 24회차 보고서가 신고한 B24-1·F24-1 외 리팩터링 없음. 보고만 하는 관찰 2건은 그대로 원장에 남김(goal 원장의 프로젝트 축 · `[table:document]` 기본 경로 고정 이름).

### 25회차 (2026-08-22 22:2x — 보고서 `outputs/imagination_training/2026-08-22_25회차.md`)
- 축: **분기 문법의 미답 가지**. census 로 뽑은 전 코퍼스 실사용 = `else if` **0** · `?? 3단` **0** · `_raw:true` **0** · `case` 3 · 괄호분기 3 · 블록-인-파이프 3 · `spill` 3 · `$return` 3 · `reduce` 8 · `repeat` 7 · 식 할당 7. `if` 는 32건인데 가지는 전부 처녀지였다.
- 지표: 행동 210문장·조합 31(14.8%)·미조합 113/151 / 교재 3,573. 검수 12/12(Y11 만 param_warning), 실측 12건 + 격리 5건. **깨끗 9 · 꼬임 2 · 결함 1.**
- `B25-1` **(결함)**: **조건 좌변이 소스 참조면 리스트 인덱스 경로를 못 넘는다.** 격리 3종이 뿌리를 못박는다 — (a)`$r.items.0.max_temp` **동작**(matched_value 30.3) (b)`sense:weather{…}.items.0.max_temp` **판정 불능**(else 까지 보류되어 문장이 통째로 죽음) (c)`sense:weather{…}.current.temp` **동작**. 즉 같은 조건 언어의 두 좌변이 **서로 다른 경로 해소기**를 쓰고 소스 참조 쪽만 리스트를 못 넘는다. 뿌리 = `backend/ibl/ibl_exec_sense.py:171` `_extract_dotted_field_checked()` 의 `if not isinstance(current, dict)` — 숫자 키×list 경우가 없다. 힌트 생성기도 같은 구멍(`사용 가능한 필드` 목록이 `items` 에서 멈춤). ★F20-2(20회차)가 붙인 items 폴백은 **행이 정확히 1개일 때만** 발동해 다행(多行) 통화엔 무력 — 같은 구멍에 대한 국소 덧대기였다. `items` 는 IBL 의 단일 통화이므로 "조회한 통화의 첫 행을 보고 분기"라는 가장 흔한 수요가 막혀 있다. 제안: **수리성** — 경로 해소기를 하나로 정본화(리스트 인덱스 지원)하고 소스참조·변수·힌트 생성기가 공유. 부류 스윕 = `_extract_dotted_field*` 호출 전 자리(`ibl_exec_sense.py:67·79·167`, `ibl_executors.py:61`). 가드 = (a)(b)(c)가 같은 값을 내야 한다는 불변식.
- `F25-1` **(문서 부패 + 표현 갭)**: 매 턴 주입되는 교재 `12_ibl_only.md:188·201` 의 `[repeat:]` 예시 두 곳이 **유령 파라미터** `[sense:search]{page: "$i"}` 를 가르친다 — 실제 스키마에 `page` 없음(`query·source·count·days·type·sort·country·language·curate·headlines·queries·sources·from_date·to_date`). 실측: 교재 예시 그대로 실행 → repeat 2회 collect 20행 → dedup 후 **10행**(두 회차 완전 동일 = page 조용히 무시). dedup 없이 쓰면 같은 10건이 "2페이지 20건"으로 보인다. **검수는 param_warning 을 띄운다 — 교재가 검수 경고를 유발하는 문장을 정본으로 싣고 있는 상태.** 딸린 어휘 갭 후보: 어떤 검색 액션도 페이지 오프셋을 안 받아 "여러 페이지 이어 모으기" 문형이 현재 언어에 없다(현행 우회=`count`). 어휘 신설은 요청하지 않음. 제안: **수리성**(교재 정정).
- `F25-2` **(문서 부패)**: 교재 `12_ibl_only.md:52` 가 `_raw: true` 를 현재형으로 가르치는데(“일부 검색 액션은 AI 요약해서 돌려준다”), `postprocess:compress` **선언 액션은 2026-06-27 이후 0개**라 아무 일도 하지 않는다. 실측 대조: 같은 질의를 `_raw` 유/무로 → step1 **bytes 1244 · count 5 · preview 동일**. 정본(`system_docs/architecture.md:79`·`packages.md:172`)은 이미 "선언 0개"라고 정확히 적어 뒀다 — **교재만 6주째 낡았다.** 제안: **수리성**(문단 삭제 또는 "잠자는 플래그"로 명시).
- **확인된 열매**: `[else if:]` **첫 실측**(교재 0 — 격리로 발화까지 확인, `matched` 에 조건식 원문 + `matched_value`) · `??` **3단 첫 실측**(교재 0 — `chain_length:3`, attempts 3건 전부 신고) · `??` 가지 **괄호 파이프**(`node:"pipe" · (2단)`) · **블록-인-파이프**(앞 통화를 `$items` 로 보고 else 가지 2행이 다음 step 으로) · `[table:reduce]` 실동(507,300 · `reduced_rows:10`) · **식 할당**(`$평균 = $합.value / 10` → 50730.0 이 알림 문자열에 치환) · `spill:true` **투명 해소**(step2 봉투 0행+ref, step3 이 원본 10행을 봄) · `[table:since]` 검침(1회차 seeded, 2회차 0행 + "기준선 5행" note).
- **정직성**: 판정 불능이 else 를 보류하고(Y2·Y3) 미할당 변수엔 교정 문장까지 준다. 이 부류는 이번에도 모범적이었다.
- **관찰**: `data/table_since.db` 에 이전 회차 스크래치로 보이는 스트림 `F20_3_판정검증_20260822` 25행 잔존(내 것이 아니라 미손댐 — 검침 원장에 스크래치 키가 쌓이는 경로 확인 필요할 수 있음).
- **시드 후보 8건**(승인 대기) — else if 3단 · `??` 3단 · `??` 괄호 폴백 · 블록-인-파이프 · reduce · 식 할당 · spill · since. **Y2(B25-1 걸림)·Y9(`_raw` 무효)·Y11(유령 page)은 제외** — 갭에 걸린 문장을 해마에 넣으면 결함을 가르친다.
- **판정 요청 0건** — 셋 다 수리성(결함 수리 + 교재 정정). **집행 0건** — 훈련 턴은 라이브 코어를 안 고친다(가이드 4-3). 라이브 쓰기 0건 확인.

### ✅ 25회차 판정·수리 집행 (2026-08-23 01:1x — 사용자 `#repair` "수리하고 시드처리해")
- **판정 0건** — 25회차 원장 3건 전부 수리성이었다(결함 1 + 교재 정정 2).
- `B25-1` **수리됨 — 경로 해소기를 정본 하나로 접었다**: `ibl_exec_sense._extract_dotted_field_checked()` 가 `ibl_predicates.walk_path()`(변수 좌변이 이미 쓰던 그 함수)에 위임한다. 두 좌변이 한 해소기를 공유하므로 "같은 문법이 좌변 종류에 따라 두 갈래"가 원리적으로 사라진다. `_FIELD_MISSING`↔`_MISSING` 경계만 매핑해 ★B10-case 계약(경로 부재 vs 값 null)은 보존. 순환 import 없음(ibl_predicates 는 stdlib 만 import). F20-2 의 1행 items 폴백은 `.items.0.x` 아닌 `.x` 표기를 받아 주는 **별개 편의**라 존치.
- **곁가지(같은 뿌리)**: `_field_path_hints()` 가 리스트 키를 이름만 싣고 멈추던 것 — 이제 첫 행 스칼라 칸을 `items.0.칸` 으로 최대 6개 싣는다. 판정 불능 때 **쓸 수 있는 진짜 경로를 한 번도 안 보여 주던** 자리라 힌트가 결함의 공범이었다.
- **증상 소멸 실측(격리 엔진, 보고서의 그 문장 그대로)**: (a)`$r.items.0.max_temp`→33.4 · (b)`sense:weather{…}.items.0.max_temp`→**33.4**(수리 전 판정 불능) · (c)`.current.temp`→24.1 · Y2 case → `matched "30~45" value 33.4` · 힌트 `['city','current.temp','items.0.date','items.0.max_temp','items.0.min_temp']`. **대조: 라이브(REST)는 아직 옛 코드** — 같은 (b) 가 `condition_errors`, 힌트는 `items` 에서 멈춤.
- `F25-1` **수리됨(교재 정정 — data/ 라 즉시 라이브)**: `12_ibl_only.md` 의 유령 `page` 두 곳 제거. 188줄 → `[repeat: 3, collect: true, every: "5s"]{[sense:host]{op: "status"}}`(실측 11초·3행·cpu 1.4/3.8/4.1 로 회차마다 다름 = collect 를 정직하게 가르치는 예시), 201줄 M6 예시 → 피드+`since` 로 교체해 페이지 없이 같은 교훈(while·`$n`·블록-인-파이프) 유지. data/ 전수 재검색 결과 남은 유령 `page` 0건.
- `F25-2` **수리됨(교재 정정, 즉시 라이브)**: `_raw` 문단을 "지금은 잠자는 플래그(선언 액션 0개)"로 고쳐 정본(architecture.md:79 · packages.md:172)과 같은 말을 하게 했다.
- **가드**: `test_condition_observability.py` **+5**(소스참조 리스트 인덱스 · (a)(b)(c) 동치 불변식 · 부재는 여전히 부재 · 값 null 은 부재 아님 · 힌트가 `items` 에서 안 멈춤). 격리 배터리 13/13, 무회귀 `test_ibl_program_grade*`·`test_pipe_currency_failures`·`test_honesty_invariants` **74/74**.
- **관문**: `[self:patch]{op:"apply"}` → `verified: true` · 4관문(live_sync·py_compile·import_smoke·ibl_triangle) 통과 · **3파일**. `backend/*.py` 포함이라 **지연 적용 예약**(이 턴의 진실은 '검증 통과·적용 예약').
- **시드 8건 집행** `scripts/seed_imagination_round_25.py`, `add_examples_batch` 단일 경로(`_load_model_sync()` 선행): validate **8/8** · 라이브 실행 **8/8** · 벡터 색인 **8/8**(`ibl_examples` 3,574→**3,582**, 행 수 == 벡터 수) · `ibl_distilled` 858→**866**. 변형 질의 회상: "시세 실패하면 검색해서 두 개만"→**0.900** · "주가 안 나오면 검색으로 대신"→**0.826** · "새로 올라온 글만"→0.800. 아직 못 당기는 것: "결과 많으면 다섯 개"→0.592 · "평균까지 계산"→0.632 ⏳재학습 대기열.
- ★**B25-1 이 새로 참으로 만든 문형 2건은 시드에서 제외**(소스참조 `.items.0.x` 조건 · 통화 첫 행 case 범위매칭) — 지연 적용이라 시딩 시점 라이브가 아니었다. 20회차 규율대로 적용·야생 검증 후 다음 회차.
- **범위 규율**: B25-1·F25-1·F25-2 외 리팩터링 없음. **새 관찰 1건은 고치지 않고 신고만** — `[sense:performance]{page: N}` 이 스키마에도 있고 핸들러도 받는데(`culture/handler.py:113` `cpage=ti.get("page", 1)`) page 1·2 결과가 20행 전부 동일(mt20id 교집합 20/20). F25-1 예시를 "실재하는 page" 쪽으로 옮기려다 발견했고, 그래서 교재는 페이지네이션 자체를 버리는 쪽으로 고쳤다.

### 26회차 (2026-08-23 04:1x — 보고서 `outputs/imagination_training/2026-08-23_26회차.md`)

사용자 지시로 **25회차의 2배 규모** — 과제 12→**26**(2.17×) · 갑 원장 3→**7**(2.33×) · 총 실행 17→**60**(3.5×). 검수 26/26, 분류 깨끗 24·꼬임 2·결함 1(+후속 프로브가 발굴한 결함 2).
중점 = **처녀 어휘 × 처녀 문법**: 전 코퍼스 3,582문장에서 조합 0인 액션 17개 중 실행 가능한 **9개**를 통화 파이프에 처음 물렸고(`self:goal`·`switch`·`forage`·`folder_note`·`output`·`sense:researcher`·`others:follow`·`nostr`·`auto_response`), 교재 용례 0~8건짜리 문법(groupby agg·compute·rename+join·union·merge·flatten·each 리터럴 팬아웃·try/catch/finally·on_error:null·repeat while·워크플로우 시그니처+$return·since{watch})을 답사했다.

- `B26-1` **결함·수리됨(라이브)** — **단항 변환자가 봉투의 자기-기수 서술을 안 고친다.** 시스템 자신의 정의 `truncated == total > len(items)`(portal_warehouse:304 · test_body_vocab T1/T5)를 깨뜨렸다. 실측: `[self:grep]{…}`(total 29 · items 29 · truncated false) `>> [table:take]{n:1}` → total 29 · items **1** · truncated **false** — 즐 "29건 전부를 보여준다"면서 1건을 낸다(filter·dedup 동일). ★새 부류가 아니라 **이미 세 번 봉한 '잘림 침묵'의 네 번째 자리** — ⑥′(file_find)·⑫(grep)·⑭(`_carry_flags` 로 **이항** 변환자)의 스윗이 **단항 경로에만 안 닿았다**. 수리 = `data-ops/handler.py` 의 `_emit_items`/`_emit_table` **병목 하나**에 `_restate_scope()` 배선(28 호출 자리 전수 통과 — 이 파일 자기 교리 "생산자 N곳을 각각 고치지 않고 병목에서 닫는다"). 규칙은 전부 기존 계약 인용: truncated 는 **켜기만**(단조, `_carry_flags` OR 승계 방향) · total 은 **지어내지 않음**(join 조항). 수리 후 실측: take/filter/dedup 전부 `truncated true`, **기수 불변인 sort 는 false 유지(오폭 0)**.
- `B26-2` **결함·수리됨(라이브)** — **기수가 바뀐 변환 뒤에도 봉투 `summary` 가 변환 전 집계를 말한다.** 실측: `[sense:realty]{…} >> [table:groupby]{by:"법정동", agg:{평균가:["avg","거래금액"]}}` → items 는 법정동별 14행인데 봉투는 `summary.평균가 "31,952만원"`·`총거래건수 90`(변환 전 전체 평균). `message`·`text` 를 같은 자리에서 떨어내는 것과 **같은 부류**라 같은 병목에서 제거. 단 무조건이 아니라 **기수가 변한 때만** — message/text 는 O(items) 산문이라 파이프 블로업까지 걸리지만 summary 는 유일한 문제가 stale 이고 그건 집합이 바뀌었을 때만 발생한다. 수리 후: groupby(90→14)·take(90→3) → summary 사라짐, **sort(90→90) → 보존**.
- `B26-3` **결함·수리됨(RED, 적용 예약)** — **`[self:output]` 이 파이프 통화를 안 먹고 빈 산출을 성공으로 신고한다.** 실측: `[sense:book]{…} >> [table:take]{n:3} >> [table:select]{…} >> [self:output]{op:"gui", format:"테이블"}` → `{"ok": true, … "content": ""}`. ok:true + 빈 산출 = 침묵-삼킴(⑪′ 부류). ★★**뿌리의 증거가 파일 자신의 주석에 있었다** — `ibl_exec_output.py` 는 2026-08-05 어휘 압축에서 `_output_file` 을 지우며 *"이 함수는 안전판을 우회했고 **파이프 입력도 무시해 빈 파일을 쓰던 반쪽 싱크**였다"* 라고 적어 둠 — 그런데 **같은 결함을 가진 형제 둘(gui·clipboard)은 그 자리에 그대로 남았다**(흡수가 op 하나만 데려가고 계약을 안 데려감). 호출부 `ibl_routing.py:443-450` 는 `_prev_result` 를 성실히 넘기고 있었다. 수리 = 공통 `_sink_content()` 하나를 두고 두 op 이 공유(세 번째 op 이 생겨도 감염 안 됨), 규약은 **[self:write] 에서 그대로 복사**(content 명시가 이김 · "" 도 유효 · 생략이면 `_prev_result` · 스필 참조 해소). 더해 gui 는 빈손이면 ok:true 가 아니라 **정직한 거절**(clipboard 와의 비대칭도 해소).
- `V26-1` **어휘 갑 후보 — 고치지 않음**: `[self:folder_note]{op:"get"}` 이 목록을 `items` 가 아닌 `annotations` 로 내고 `returns: scalar` 로 선언돼 있어 table 파이프 밖이다. 단 거절은 **이미 정직하고**(봉투 키 목록 + "returns: scalar/effect 일 수 있습니다" 진단), 선언 변경은 결함 수리가 아니라 어휘의 의미 결정 — 가이드 §4-3(어휘는 현실이 인준한다) + `self:forage` 의 2026-08-17 동일 판정 전례를 따른다.
- `F26-1` **관찰 — 고치지 않음**: `self:body` 가 `count` 를 안 낸다(`['items','success','text','total','truncated']` vs `sense:feed` 의 `['count','items','message','success']`). 부재는 거짓말이 아니고 변환자가 첫 통과에서 채운다 — 신고 범위 밖 리팩터링은 범위 규율 위반.
- `F26-2` **★오진 격리로 결함 아님 판정**: `others:nostr` 가 `success` 키를 안 내서 결함으로 적으려 했으나, 파이프 앞에 두고 재보니 `success=True · 2/2 steps`(대조군 `others:auto_response` 와 동일) — 엔진이 부재를 실패로 오독하지 **않는다**. 단일 액션 = 핸들러 원문이라 계약 위반도 아니다.
- `F26-3` **훈련 환경 마찰**: `sense:book`(data4library) 30초 타임아웃이 Z7·Z15·Z25 를 1차 실행에서 죽였고 재시도엔 3건 전부 성공(일시적). 에러는 정직했다(빈 결과 위장 없이 step 중단+사유). 외부 API 의존 문장은 재시도 예산을 두고 짜야 한다.
- **★오진 격리 3건**(결함으로 적을 번했던 것): ①"빈 봉투 `{}` 10건" → 내 분석 스크립트의 `res.get(tid, {})` 기본값(부재를 빈 봉투로 오독). 단건 재현에서 정상 동작 — 시스템 무결함. ②Z3 검수 실패 → 마지막 줄 벌거벗은 `$변수` 라는 **내 문장 오류**(파서가 정직 거절), 교재형 `join{left,right,on}` 은 7단 정상. ③"`total` 승계가 거짓말" → 네이버 검색의 `total: 5,767,261`(코퍼스 적중 수)은 take 뒤에도 **참** — total 은 모집단 수치라 살리고 거짓은 `truncated: false` 라는 적극적 주장뿐임을 가려냄(수리 범위가 좋아졌고 오폭도 사라짐).
- **가드**: `test_pipe_currency_failures.py` **+2**(`P23` 단항 truncated 재서술 — 단조·무오폭·total 무생성·stale summary 제거·기수불변 보존 / `P24` output 싱크 계약). **P1~P24 전부 통과** · 무회귀 `test_body_vocab` 7/7 · `test_condition_observability` 13 · `test_honesty_invariants` 17 · `test_ibl_silent_failures` 전부.
- **관문**: `[self:patch]{op:"apply"}` → `verified: true` · 4관문(live_sync·py_compile·import_smoke·ibl_triangle) 통과 · **2파일**(`ibl_exec_output.py`·`test_pipe_currency_failures.py`) · `applied:false, scheduled:true` — `backend/*.py` 가 끼어 **지연 적용**(이 턴의 진실 = '검증 통과·적용 예약'). B26-1·B26-2 는 비-RED 라 `/packages/reload` 로 즉시 라이브·실측 검증 완료.
- **시드 0건(의도적)** — B26-3 이 지연 적용이라 시딩 시점 라이브가 아니고, 20회차 규율(수리가 야생 검증을 거친 뒤 시딩)을 따른다. 다음 회차 시드 후보 **10건** 예약(보고서 §시드 후보).
- **스크래치 정리**: 워크플로우 `상상훈련26_스크래치` 삭제 · `table_since.db` 의 동명 스트림 5행 삭제(사용자 `F20_3_판정검증_20260822` 25행 무손상) · **알림 0건 생성**(이번 회차는 notify_user 미사용).
- **판정 요청 0건** — 결함 3건 전부 수리성이라 묻지 않고 집행. V26-1 은 어휘 갑 후보로만 남김.

### 27회차 (2026-08-23, `#repair` 수리 턴) — 축: **문법 × 문법 한-문장 교차**

- **규모**: 상상 과제 **57**(검수 57 · 실측 55) = 25회차(12)의 **4.75×**, 26회차(26)의 2.19× · 총 실행 **133회** · 갭 원장 **8** · 근본 수리 **4**. 사용자 지시 "4배 규모"의 기준을 25회차로 잡고(26회차가 이미 2.17×) 목표를 박았다.
- **새 축 산출 근거**: 26회차가 *처녀 어휘 × 처녀 문법(단품)* 을 소진했으므로 코퍼스 3,582문장에 census 를 새로 돌려 세 축을 재산출(지표 JSON `27회차_census` 에 보존). **축A** op 수준 처녀 지대 = 261 op 중 등장 0회 **20개**(부작용 없는 8개 탑재). **축B** 문법 토큰 빈도 하위 15. **축C ★중점** 두 문법이 **한 문장 안에** 같이 나온 횟수 — 25조합 중 **18개가 0회**(each×try/if/on_error/repeat/$items/spill/??/&/reduce/괄호병렬, assign×each, case×each/repeat/elseif, 블록인파이프×each, if×try/on_error/$return, AI술어×each). 26회차가 각 문법을 *단품으로* 처음 밟았다면 27회차는 *서로 겹쳐서* 밟는다. **축이 옳았다는 증거: 결함 4건 중 3건이 정확히 "두 계층이 만나는 자리"에 있었고, 각각 개별로는 옳은 두 결정이 교차에서 거짓을 낳은 형태였다.**
- `B27-1` **결함·수리됨(RED, 적용 예약)** — **봉투 요약의 통화 판정기가 파이프 이음매의 판정기와 다르다.** 실측: `[self:body]{…} >> [table:select]{columns:["파일","영역"]}` → step2 `shape: "effect"` · `keys` 에 items 없음 — **같은 step 의 `final_result` 엔 items 3행**. 이번 회차 요약된 119 step 중 **11자리**(이 회차의 `groupby`/`select`/`union` step **전부**)를 때렸다. ★뿌리는 **개별로 옳은 두 결정의 교차**: 2026-08-05 D13(`results[]` 는 원형 유지·파생은 이음매에서만 — 그때는 모델이 원형 JSON 을 봐서 `columns/rows` 를 표로 읽었다) × 2026-08-22 M1(그 `results[]` 를 shape/keys 한 단어 **판정**으로 접음). 접은 뒤로 모델은 원형이 아니라 판정을 읽는데 판정자(`obj.get("items")`)가 이음매의 판정자(`derive_items`)와 달랐다 — **두 판사가 같은 물건에 다른 선고**. 비용은 틀린 데이터가 아니라 **틀린 진단**(effect 를 읽으면 그 자리에서 통화가 죽은 줄 알고 `>> [table:*]` 를 안 잇는다) — ⑥′·⑫·⑭·B26-1 부류의 다음 자리. 수리 = `ibl_envelope.summarize_result` 가 `derive_items` 에게 shape 을 묻는다(`_derived_items`). **통화 판정기는 하나여야 한다.** 파생본은 **판정에만** 쓰고 봉투에 안 싣는다(D13 의 토큰 중복 회피 근거 불변) · items 직접 방출은 파생기 미호출(빠른 경로 무변경) · 파생으로 알았으면 `items_derived: true` 로 밝힘 · 진짜 효과 봉투는 여전히 effect(오폭 0).
- `B27-2` **결함·수리됨(RED, 적용 예약)** — **스필 참조 해소기가 입구가 아니라 소비처마다 흩어져 구멍이 남았다.** 교재의 약속(*"뒤 step 은 참조를 투명하게 해소해 원래 데이터를 그대로 본다"*)이 깨진다. 실측: `[self:body]{days:2, limit:20} >> [self:write]{path:…, spill:true} >> [table:groupby]{by:"영역"}` → `groupby: 입력에서 items 통화를 찾지 못했습니다`(같은 자리 `[table:each]` 는 성공 — 그쪽엔 자기 해소기가 있어서). ★해소기가 **네 곳에 복제**(그 자체가 냄새)돼 있고도 구멍: `_op_groupby` 는 `_rows_for_field` 로 들어가는데 해소기는 형제 입구 `_get_items` 에만 — **한 파일 안에서도 입구가 둘**. 게다가 `_prev_result` 를 읽는 **7개 패키지 중 해소기 보유는 2개뿐**(ai-ops·visualization·media_producer·blog·android 없음)이라, 자동 스필이 큰 결과를 참조로 바꾸는 순간 = **데이터가 클수록** 그 다섯은 0행을 본다. 수리 = `_prev_result` 가 핸들러에 닿는 **유일한 자리** `workflow_binding._auto_inject_prev` 에서 해소 — 7개 패키지 전부와 앞으로 생길 패키지가 계약을 상속. **25회차 판정의 재적용: 해소기는 하나여야 한다.** 소비처 기존 해소기는 존치(파이프 아닌 입구=리터럴 씨앗·params 직접 통화의 담당, resolve_ref 는 멱등) · 만료·부재는 삼키지 않고 참조를 그대로 흘려보냄(새 침묵 0).
- `B27-3` **결함·수리됨(RED, 적용 예약)** — **`each` 의 `$it` 치환이 자리의 문법을 안 본다** → `[table:each] × [if:]` 라는 가장 자연스러운 교차가 통째로 말할 수 없는 문장이었다(전 코퍼스 이 교차 **0건** — 축C 가 겨눈 바로 그 자리). 실측: `do: "[if: $it.영역 matches 'backend']{…}"` → `condition: "backend/ibl matches 'backend'"` / `"'backend/ibl' 은(는) 소스 참조·$변수·리터럴·술어 함수 어느 것도 아닙니다"` → 판정 불능이라 else 도 보류 → 3건 전부 실패. **값은 옳게 뽑혔는데 따옴표가 없어서** 죽었다. 뿌리: `$it` 치환은 파싱 **전** 텍스트 치환이라 치환값이 자리의 문법을 만족해야 하는데 어느 자리든 맨몸 텍스트였다 — 파라미터 자리는 저자가 따옴표를 쓰므로(`{message:'$it.title'}`) 우연히 맞았고, 조건 자리는 `$변수` 를 원래 맨몸으로 쓰는 문법이라 깨졌다. ★비대칭이 증상을 숨겼다: `[if: $it.n > 5]` 처럼 **숫자면 맨몸이 곧 리터럴이라 우연히 동작**한다. ★형제 반증: 바깥 `$변수` 는 조건 평가기가 **직접 해소**(텍스트 치환 아님)하므로 안전 — 실측 확인, 이 결함은 `$it` 에만. 수리 = 값을 만드는 곳이 아니라 **자리를 아는 곳**이 표기를 정한다(`_inside_string` 으로 문자열 안/밖 판정 → 밖이면 `_each_literal`: 숫자·불리언·null 맨몸[조건의 크기 비교가 문자열로 변질되지 않게], 그 밖은 따옴표 / 안이면 옛 규약 그대로 무회귀).
- `B27-4` **결함·수리됨(RED, 적용 예약)** — **블록 경계가 몸통의 정직 신고를 삼킨다.** `[on_error:]` 의 계약("skipped_steps 로 신고되니 조용한 성공이 아니다")이 블록 **안에서만** 무효. 실측: 같은 문장이 맨몸이면 `{success:true, skipped_steps:[1]}`(정직), `[repeat: 2, collect: true]{…}` 안이면 `{success:true, items:[], count:0, iterations:2}`(침묵) — 읽는 쪽은 **"할 일이 없었다"와 "전부 실패했지만 봐줬다"를 구별할 수 없다**. 뿌리: `_run_body` 가 몸통 봉투에서 `final_result`(통화)만 꺼낸다 — 통화가 바로 흐르게 하려는 옳은 선택이지만 봉투가 나른 *신고*가 경계에서 통째로 사라진다. ★**repeat 만 고치면 if·case·try 가 같은 침묵을 물려받으므로**, 봉투를 손에 쥔 **유일한 자리 `_run_body`** 에서 고쳤다(`_collect_honesty` out-param, 반환 튜플 arity 불변) — 24회차 판정("부분 성공은 실패를 지우지 않는다")과 ⑭ `_carry_flags` 가 안 닿은 나머지 경계. repeat 이 회차 표시를 붙여 승계하고 `note` 로 "N/M 회차에서 step 을 건너뛰었습니다"를 말한다. 없는 것은 지어내지 않음(무사고 회차는 조용).
- `F27-1` **마찰 — 고치지 않음**: 문장 자리 블록의 결과가 `{result: "<JSON 문자열>"}` 로 한 겹 싸인다(A11 case×each · B6 중첩 if). 파이프 **속** 블록은 통화가 그대로 흐르므로(C7 실측) 실해 없음 · `final_result` 가 문자열인 것과 같은 오래된 내부 규약(`_parse_final` 존재)이라 표기 마찰로만 적는다.
- `F27-2` **마찰 — 기존 항목(1회차 F2)에 증거 추가**: validate 는 param 이름을 안 본다. C8 `[self:ask]{question:…}` 이 검수 통과 후 실행에서 `prompt(지시/질문)가 필요합니다` 로 죽음 — **실행은 정직했다**. 반대편 F5 는 `[table:sort]{by:"name"}` 에 `사용 가능한 필드: ['title','meta','summary','url']` 교정 안내(잘 동작하는 쪽).
- `V27-1` **어휘 갑 후보 — 고치지 않음**: `sense:host{op:"resources"}` 가 통화(파티션 items)와 스칼라(cpu·memory·swap)를 한 봉투에 섞어, 변환 뒤에도 스칼라가 남는다(E1 `volumes` · F2 `existing_schedules` 동형 — `_untransformed` 로 신고는 됨). "한 액션이 두 종류를 낸다"는 어휘 설계라 현실이 인준할 일(§4-3).
- **가드**: `test_pipe_currency_failures.py` **+4**(`P25` 봉투 shape=이음매 판정기·효과 오폭 없음 / `P26` 스필 해소 이음매 단일화·groupby 관통·평범 통화 무변경·만료 무침묵 / `P27` each 치환이 자리 문법 준수 + `_inside_string` 이스케이프 내성 + 없는 필드 정직 유지 / `P28` repeat 이 몸통 skipped_steps 를 회차와 함께 승계·무사고 회차는 조용). **P1~P28 전부 통과** · 무회귀 `test_ibl_program_grade` · `test_ibl_program_grade_m3m5` · `test_condition_observability` · `test_honesty_invariants` 전부 통과(격리 워크트리).
- **증상 소멸 실측**(격리 코드에 원래 실패 문장 재실행): A1 `success=True`·each 3행·행마다 조건이 갈림(`matched="backend/ibl" matches 'backend'` / docs 행은 `matched=else`) · D4 `success=True`·groupby 8그룹 · select step `shape=items count=3 derived=True`(수리 전 `effect`) · repeat `skipped_steps=[{iteration:1,step:1},{iteration:2,step:1}]`+note.
- **관문**: `[self:patch]{op:"apply"}` → `verified: true` · 4관문 통과 · **6파일**(`ibl_envelope.py`·`workflow_binding.py`·`ibl_exec_each.py`·`ibl_control_blocks.py`·`common/currency.py`·`test_pipe_currency_failures.py`) · `applied:false, scheduled:true` — 전부 `backend/*.py` 라 **지연 적용**(이 턴의 진실 = '검증 통과·적용 예약').
- **오진 격리 2건**(결함으로 적을 번했던 것): ①`final_result` 가 JSON **문자열**인 것 → 결함으로 적으려다 `_parse_final`·`ibl_envelope` 주석에서 **의도된 오래된 규약**임을 확인, 마찰(F27-1)로 강등. ②"`$변수` 도 조건에서 깨질 것" → 실측하니 조건 평가기가 직접 해소해 **안전**(`matched="$s matches \"backend\"" value=backend/ibl`) — B27-3 의 범위를 `$it` 로 정확히 좁혔다(전수 스윕이 오폭을 막은 사례).
- **시드 0건(의도적)** — 깨끗 38건 중 상당수가 B27-1 이 살아 있는 상태에서 측정됐고 수리 4건이 지연 적용이라, 20회차 규율(수리가 야생 검증을 거친 뒤 시딩)을 따른다. 다음 회차 시드 후보 7건 예약(보고서 §시드 후보).
- **스크래치**: 사용자 데이터 무변경. 워크플로우 저장(D9)·목표 등록(B8)은 **검수만** 하고 실행 안 함(원장 무변경) · `[table:since]{key:"imag27_geek"}` 기준선 5행 삭제(사용자 `F20_3_판정검증_20260822` 무손상) · 알림 0건.
- **판정 요청 0건** — 결함 4건 전부 수리성이라 묻지 않고 집행.

### 28회차 (2026-08-23, `#repair` 수리 턴) — 축: **생산자 × 변환자 인접 행렬(처녀 칸 88%)**

- **규모**: 상상 과제 **96** = 25회차(12)의 **8.00×**, 27회차(57)의 1.68× · 생산자 60종 사전 실측 · 총 실행 192+ · 갭 원장 **5** · 근본 수리 **1**.
- **새 축 산출 근거**: 27회차가 *문법×문법 교차* 를 소진했으므로 **다른 차원**(어휘와 문법이 만나는 면)으로 census 를 새로 돌렸다. 레지스트리에서 items 방출 액션 **79**·변환자 **16** 을 뽑고 코퍼스 3,582문장의 `A >> [table:X]` 인접을 전수로 셌다 → 교차 칸 **1,264 중 등장 145 · 처녀 1,119(88%)**. 변환자를 한 번도 못 만난 생산자 15개(`self:list`·`self:health`·`self:goal`·`sense:paper`·`sense:researcher`·`sense:video`·`others:follow` 등). 변환자별 파트너 다양성 최저: **`table:flatten` 0/79** · compute 1 · merge 1 · select 2 · ai 2 · join 3 · reduce 3 · dedup/each/rename 4. 각 처녀 칸 = "이 소스의 봉투가 실제로 이 변환자를 먹이는가"라는 진짜 질문이며, 이 시스템의 결함이 역사적으로 살아 온 면이다. ★문장을 짓기 전에 **생산자 60종을 한 번씩 실측해 실제 열 이름을 확보**하고 그 열로만 파라미터를 채웠다(가이드 §3-3 "추측 금지"의 기계적 이행 — 1회차 F2 의 교훈).
- `B28-1` **결함·수리됨(라이브)** — **빈손(0행)에서 필드 부재를 단정한다.** 실측: `[self:body]{days:3, limit:5} >> [table:filter]{where:"존재하지않는값ZZZ"} >> [table:rename]{map:{"파일":"경로"}}` → step1 이 `columns=[…'파일']` 로 그 열의 실재를 신고했는데 step3 이 `rename: 필드 ['파일'] 이(가) 없습니다. 행 필드 예: []`. ★**오류문이 스스로를 반박한다** — `행 필드 예: []` 는 *아무것도 못 봤다*이지 *없다*가 아니다. 사라진 건 필드가 아니라 행이다. **부류 전수 측정**(단항 9종 × {빈손, 행+없는필드}): filter·sort·take·select·dedup·groupby·compute·flatten **8종은 빈손을 0행 성공으로 흘려보내는데 rename 만 ERROR** — 혼자 다른 답. ★뿌리: **F17 이 빈손 계약을 "verb 마다 심사" 로 정해 둔 것**. 그래서 verb 마다 `not any(k in r for r in dict_recs)` 를 손으로 다시 적었고(전수 13자리), 빈손 보호는 *호출자가 먼저 짧게 끊어 주는 우연*에 기댔다 — 8개는 우연히 끊겼고 rename 만 안 끊겼다. verb 를 하나 고치면 다음 verb 가 다시 틀린다. 수리 = **갈래가 사는 자리는 verb 가 아니라 판정기**이므로, 부재 판정을 단일 판정기 `_absent_fields(names, observed)` 로 옮기고 **관측이 0이면 어떤 이름도 부재로 주장하지 않게** 했다(`_observed_fields` 가 행/열 어느 쪽에서든 관측 집합 생성). 이제 빈손 보호는 호출자의 우연이 아니라 **판정기의 성질**이다. 선례 동형: 조건 평가의 "판정 불능은 거짓이 아니다"(빈 집합에서 필드 부재는 *거짓*이 아니라 *판정 불능*). **과교정 없음** — 행이 있으면 여전히 시끄럽게 거절. 수리 후 라이브 실측: rename 이 형제 8개와 같은 답(0행 성공) · DP1(8단 realty 체인) 실패→**성공** · 전수 행렬에서 빈손 위반 verb **0**.
- `F28-1` **관찰 — 고치지 않음(오진 격리 기록)**: census 가 `flatten` 을 "파트너 0" 인 유일한 변환자로 지목해 15문장을 겨눴고 **15건 전부 실패**했으나, 격리하니 **전부 내 문장 오류**였다 — 스칼라 열(`title`·`파일`)을 펼치라 시켰고 목록이 아닌 것은 펼칠 수 없다. 거절은 정직했고 사용 가능한 필드까지 안내(`flatten: field 'title' 에서 목록을 가진 행이 없습니다(행 4개 전부 건너뜀). 행 필드 예: [...]`). 정본 경로는 정상: `[self:body]{…} >> [table:each]{do:"[self:grep]{…}"} >> [table:flatten]{field:"_result"}` → 3행이 12행으로 펼쳐짐(열 파일·줄번호·내용). → **파트너 0 은 "고장"이 아니라 "아직 아무도 필요로 하지 않았다"**. 다음 회차가 같은 census 신호로 같은 오진을 반복하지 않도록 원장에 남긴다.
- `F28-2` **외부 마찰(F26-3 재확인)**: `sense:book`(data4library) 30초 타임아웃이 2건을 1차에서 죽였고 재실행에 통과. 에러는 정직(빈 결과 위장 없음).
- **관찰 1 — 24~27회차 수리가 깊은 합성에서 버틴다(긍정 실측)**: 6~8단 체인 6건의 봉투를 단계별 감사. **B26-1** DP2 최종 `items=6·total=368·truncated=true` 로 불변식 성립, 나머지는 **total 을 지어내지 않음**. **B27-1** `items_derived:true` 가 표 형 방출 변환자(groupby·rename·select)에만 정확히 붙고 items 직접 방출(sort·take·compute·filter)엔 안 붙음 — 오폭 0. **B27-2** DP8 이 8단 안에 `[self:write]{spill:true}` 를 끼고도 완주.
- **관찰 2 — 처녀 지대 88% 를 훑었는데 조용한 오동작 0건(긍정 실측)**: 성공 78문장의 *실제 산출물*을 기계 재검사(compute 파생열 실존·select 열 축소·rename 새이름·reduce 결과). 의심 4건 전부 설계대로(`since` 첫 검침 = 기준선 시딩 0행 + 봉투가 그렇게 말함 / `brief` 는 산문 message 라 items 없음이 정상). **ok:true 인데 틀린 것 0건** — 네 회차 연속 봉해 온 '침묵-삼킴' 부류가 재발하지 않았다. ★이번 회차의 성적은 원장 항목 수가 아니라 **처녀 지대 통과율**로 읽어야 한다(가이드 §6).
- **가드**: `test_pipe_currency_failures.py` **+1**(`P29` — 불변식 A: 빈손이면 단항 verb **전수**가 0행 성공(부재 주장 금지) / 불변식 B: 행이 있으면 여전히 시끄러운 거절(과교정 금지) / 판정기 자체 단위 검사). ★rename 하나가 아니라 **부류를 지킨다** — 새 verb 가 부재 판정을 손으로 적어도 여기서 걸린다. **P1~P29 전부 통과** · 무회귀 `test_ibl_program_grade` · `_m3m5` · `test_condition_observability` · `test_honesty_invariants` · `test_ibl_silent_failures` · `test_body_vocab` 전부.
- **관문**: data-ops 는 RED 아님 → `/packages/reload` 로 **즉시 라이브·증상 소멸 라이브 실측 완료**. `backend/test_pipe_currency_failures.py` 는 RED → `[self:patch]{op:"apply"}` `verified:true` · 4관문 통과 · `applied:false, scheduled:true` (**적용 예약**, 다음 턴 판정).
- **범위 밖이라 보고만**: 손으로 적은 부재 판정 **12자리**(121·385·393·404·494·502·516·550·564·802·818·1112·1330)는 전수 측정 결과 **오늘은 전부 정상**(호출자가 빈손을 먼저 끊는다) — 결함이 아니므로 판정기로 갈아끼우는 것은 수리가 아니라 리팩터링이고 명령 범위 밖. 대신 **P29 가 부류를 지키므로** 미래에 그중 하나가 빈손에 노출되면 시험이 잡는다. / `self:workflow`·`self:goal`·`self:switch`·`self:finance`·`others:follow` 는 0행이라 처녀 칸 미충족(데이터 부재이지 결함 아님) / `sense:classic` 은 Gutenberg 외부 접속 실패로 제외.
- **시드 0건(의도적)** — 20회차 규율(수리가 야생 검증을 거친 뒤 시딩). 다음 회차 후보 12건 예약(보고서 §시드 후보).
- **스크래치**: 사용자 데이터 무변경 · `[table:since]` 스크래치 스트림 3종 28행 삭제(사용자 `F20_3_판정검증_20260822` 무손상) · 알림 0건 · 워크플로우/목표 등록 0건.
- **판정 요청 0건** — B28-1 은 수리성이라 묻지 않고 집행.

### 28회차 **평가** (2026-08-23, 사용자 지시 — 훈련 회차가 아니라 세 회차를 되짚은 감사 턴)

사용자 질문 "양을 8배까지 늘렸는데 제대로 잘 해낸 걸까?" 에 대한 실측 감사. 규모(96=8.00×)와
분류 집계는 원본(`/tmp/imag28/results.json` 96건)과 대조해 **정확**했으나, **보고서가 초록이라
적은 것 중 하나가 초록이 아니었다.** 아래 3건을 집행(전건 수리성).

- `E28-1` **거짓 초록 — 회귀 확인이 실제로는 안 돌았다** (결함·수리됨). 27·28회차가 회귀를
  `python backend/test_X.py > log && echo OK` 로 판정했는데 그 배터리들엔 `__main__` 이 없어
  **시험을 한 건도 안 돌리고 종료코드 0**(로그 0바이트)을 냈다. 전수 측정: 배터리 44개·시험
  303건 중 **147건(49%)** 이 직접 실행에서 한 번도 안 돌았다. **거울상**도 있었다 — 정본
  러너(pytest.ini·CI)가 스크립트형 배터리 3개에서 **0건을 수집하고 조용히 지나갔고**, 그중
  `test_repair_staging.py` 는 자기수정 안전 **63검사**다(CI 에서 한 번도 안 돌았다).
  ★뿌리는 하나: **러너가 둘이면 한쪽은 반드시 조용히 0건이 된다.** 손으로 적은 러너는
  드리프트하며, "아무 시험도 안 부르는 러너" 는 "전부 부르는 러너" 의 **미래**였다.
  ★그리고 **0건은 '통과' 가 아니라 '아무것도 안 봤다'** 인데 러너가 둘을 같은 초록으로 보여줬다.
  수리 = 러너를 하나로: 모든 배터리의 `__main__` 이 `pytest.main([__file__])` 로 **위임**하고
  (거부가 아니라 위임이라 순찰·손버릇이 그대로 살아 있다), 스크립트형 3개는 다리 시험으로
  pytest 에 편입(면제는 추론이 아니라 `RUNNER: script-battery` **선언**으로만).
  실측: 직접 실행이 0바이트 → 15건 실행 · pytest 수집 **39파일 304건 → 42파일 307건** ·
  전체 **316 passed, 2 skipped**(2 = `allow_module_level` 로 **이유를 말하고** 빠진 것).
  가드 `backend/test_single_runner.py` R1~R4 · 가이드 §4-4 신설.
- `E28-2` **턴이 자기 기록을 자기가 지운다** (결함·수리됨). 위 감사 중 B18-2 가드
  (`test_episode_source.py`)가 **원장 적재량에 따라 통과·실패를 오갔다**(999건 통과 / 1001건 실패).
  기전: B18-2 가 축출 정렬 맨 앞에 출처 키를 세우면서 `id ASC` 가 실사용 행에 주던 보호
  (방금 쓴 행 = 가장 새 행 = 후보의 반대편)가 **시험 행에서만** 사라졌다 — 원장의 유일한
  시험 행은 곧 '가장 오래된 시험 행'이라, `_finalize` 가 행을 닫고 요약까지 쓴 직후 자기가 부른
  정리가 그 행을 지웠다. 수리 = 보호를 정렬이 아니라 **후보 집합**에서(`_cleanup_old_episodes(keep_id)`),
  방금 쓴 행을 빼고 그 다음 것을 지우므로 상한은 정확히 유지된다(한 칸 덜 지우는 미봉책 아님).
  ★**주변 상태로 답이 바뀌는 가드는 신뢰할 수 없다** — 초록을 봐도 무엇이 증명됐는지 알 수 없다.
  가드 `test_episode_source.py` +1(상한 초과 재현, 임시 DB).
- `E28-3` **리허설이 건강 원장에 실사용으로 쌓였다** (결함·수리됨). 훈련은 갭을 찾으려고
  *일부러* 없는 종목(`ZZZZINVALID`)·안 되는 문장·빈 손을 밟는데 그 의도된 실패가
  `source='usage'` 로 적재됐다. 실측: 8배 회차 **20분**이 남긴 `table:flatten` 실패 32건이
  7일 만성 실패 **순위 1위**(37건 중 86%)를 만들었다 — 사용자 알림함까지 올라갔던 B18-1 사고의
  재연 직전. 게다가 집계 질의 두 곳(건강 요약·X-Ray)이 `last_usage_failure` 만 source 를 보고
  `total`/`successes` 는 **출처 무관**으로 세서, 표식을 달아도 사용자가 보는 성공률에는 계속
  섞일 판이었다. 수리 = ①판정을 **행위자 봉투**로(`origin:"training"` → actor_context 가
  each·폴백·병렬 가지까지 전파) ②격리는 B18-1 과 **같은 자리**(`record_action_health`) ③판정은
  한 벌(`thread_context.in_rehearsal`, pulse_db 는 위임) ④격리 SQL 조각도 한 벌
  (`pulse_db.NOT_ISOLATED_SQL` 을 두 집계가 공유) ⑤`self_check`(순찰)은 격리하지 **않는다** —
  몸이 스스로를 실제로 재는 진짜 신호다. 가이드 §3-5 에 훈련자 지시 추가.
  ★덤: `origin` 이 `'user'` 가 아니게 되어 **리허설은 RED 수정 그랜트를 못 받는다**(22회차 사고와 같은 방향).
  라이브 종단: 같은 문장을 봉투 유무만 바꿔 두 번 실행 → `training` / `usage` 로 정확히 갈림.
  과거 정리: 원장(episode_log)이 말해 주는 훈련 창 17개에서 **실패 111건**을 `training` 으로 이관
  (겹치는 비훈련 에피소드는 **겹친 구간만** 제외 — 창을 통째로 버리지도 뭉개지도 않았다).
  성공 행은 **손대지 않았다** — 같은 창의 리허설 프로브와 그 턴의 진짜 수리 작업(`self:edit`·
  `self:patch`)을 구별할 방법이 없어서다. ★구별할 수 없는 것을 구별한 척하지 않는다(앞으로는
  봉투가 정확히 가른다). 결과: `table:flatten` 이 만성 실패 목록에서 **사라짐**(37→5).
  가드 `backend/test_health_source_isolation.py` R1~R5. 백업 `data/_backups/2026-08-23_health_training_retag/`.
- **평가의 나머지(고치지 않고 보고만)**: ①8배의 질 — 과제가 `생산자×변환자` 격자를 기계적으로
  채운 템플릿이고 `tasks.py` 에 "규모 96 충족" 주석이 있다(패딩 명시). flatten 15건은 같은 저작
  오류 하나의 15배 복제라 96의 16%가 발견 0건. ②수확 체감 — 2배 3건 → 4배 4건 → **8배 1건**.
  27회차 보고서가 스스로 적었듯 결함은 문장 수가 아니라 **새 축**이 낳는다. → 다음 회차는
  규모가 아니라 **축**을 지시하는 편이 수확이 크다(27회차 문법×문법 교차가 그 증거).

### 29회차 (2026-08-23) — 축: **변환자 → 후속 인접 순서쌍**(파이프의 두 번째 홉 이후)
28회차 보고서의 자아비판("결함은 문장 수가 아니라 새 축이 낳는다")을 받아, 규모(8배=96과제,
25회차 12과제의 8.00배)는 지키되 축을 새로 census 했다. 27=문법×문법, 28=생산자(첫 홉)×변환자
다음의 **관절**. 공간 320(변환자16→후속21, 자기쌍 제외) · 코퍼스 기출 57(17.8%) · **처녀 263(82.2%)**.
좌항별 처녀 최다는 `reduce` 20·`compute` 19 — 이 둘은 전 코퍼스에서 후속을 각각 **1회**만
가져 봤고, 실제로 결함 3건 중 2건이 그 언저리에서 나왔다. 문장 짓기 전에 생산자 24종의
반환 열을 실측(`/tmp/it29/cols.json`)해 추측 파라미터를 배제 — `sense:realty{molit}` 은 카탈로그
8열이 아니라 실측 **13열**이었다. 결과: 깨끗 89 · 꼬임 4 · 불가 3. **검수는 96/96 전수 통과** —
이번 수확은 전부 검수가 못 보는 층(통화 규격·입력 진단·타임아웃 신고)에 있었다.
- `B29-1` **emitter 가 "입력 없음"과 "입력은 왔는데 못 쓴다"를 구별하지 않았다** (결함·부류·수리됨).
  `… >> [table:reduce]{as:"총거래액"} >> [table:chart]` → reduce 는 `[{"총거래액":1101000000}]` 을
  **1행 확실히** 냈는데 chart 는 *"데이터가 비어있습니다. data 또는 data_file을 제공하세요"*.
  참인 원인은 "첫 열=x축이라 1열 통화엔 값 열이 없다". 0행일 때도 같은 문구라 두 사건이 뭉개졌다.
  document 도 같은 부류 — 0행을 *"blocks(문서 IR 블록 배열)가 필요합니다"* 로 오진(같은 파이프가
  행이 있을 땐 blocks 없이 잘 흐른다). ★같은 노드에 **이미 정직한 형제**가 있었다: `[table:brief]`
  = `{"rows_in":0, "note":"입력 0행 — 종합할 내용이 없어 AI 호출 생략(비용 0)"}`, spreadsheet 는 빈 시트 산출.
  다섯 emitter 중 **둘만** 거짓말했다. 수리 = 입력 경계에서 세 상태를 실제로 구별
  (①통화 미도착→판단 근거 없으니 있는 척 않고 기존 경로에 위임 ②0행 ③행은 있으나 쓸 축·값 없음)
  + 봉투에 `rows_in`·`columns` 동봉. 자리: `visualization/handler.py::_diagnose_no_data`(신설),
  `data-ops/doc_build.py::render_document`(`_arrived_rows`).
- `F29-1` **형제 emitter 중 chart 만 산출 경로 낱말이 달랐다**(`path` vs `output_path`, 96과제 중 9건이
  밟음 — 검수는 정직히 경고했으나 파일은 딴 데 떨어졌다). ★수리 **자리를 한 번 고쳐 잡았다**:
  처음엔 핸들러에 `or tool_input.get("path")` 를 넣었는데 빌드가 `tool.json` 을 **파생물로 재생성**해
  손 편집을 즉시 되돌렸다. 단일 소스는 패키지 `ibl_actions.yaml` 이고 거기엔 이미 `aliases:` 기제가
  있었다 → 코드를 되돌리고 `aliases: {output_path: [path]}` 로 이전. 런타임
  (`ibl_routing._normalize_param_aliases`)과 검수 어휘(`ibl_param_vocab._alias_keys`)가 같은 선언
  하나를 읽는다. **어휘 이름을 핸들러 코드에 심지 않는다**(헌법 '명사의 자리').
- `B29-3` **병렬 타임아웃이 내부 문구를 흘렸고, 저자가 쓴 정직 신고는 죽은 코드였다**(결함·수리됨).
  `[A] & [B] >> [table:join]` 에서 한 가지가 90초를 넘기면 봉투에
  `"Step 1 병렬 실행 예외: 1 (of 2) futures unfinished"`. `as_completed(..., timeout=)` **자신의**
  TimeoutError 를 아무도 안 잡아 for 문 밖으로 튀었고, 바로 아래 저자가 써 둔 "미완료 브랜치 처리"
  (어느 가지가 몇 초에 걸렸는지 말해 주는 신고)는 **한 번도 실행된 적 없는 죽은 코드**였다 —
  주석이 의도를 증언하는데 배선이 빠진 자리. ★부수 발견: `with ThreadPoolExecutor` 의 암묵적
  `shutdown(wait=True)` 탓에 타임아웃이 **벽시계를 전혀 묶지 못했다**(90초를 선언해 놓고 낙오
  가지를 끝까지 기다림). 수리 = try/except 로 저자의 신고 루프를 살리고 `with` 를 걷어
  `finally: shutdown(wait=False, cancel_futures=True)`. 가드가 둘을 동시에 증명: 5초 자는 가지 +
  1초 상한에서 **1.06초 반환**. 자리: `backend/ibl/workflow_parallel.py`(RED, 지연 적용).
- 가드 `backend/test_emitter_input_honesty.py` R1~R6 신설. 회귀 `320 passed, 2 skipped`
  (deselect 1건은 RED worktree 에 gitignore 된 `data/*.db` 가 없어 생기는 **worktree 아티팩트** —
  라이브에서 같은 배터리 통과 확인. 회귀로 오독하지 말 것).
- **판정 대기 `F29-2`**: emitter 산출 경로 규약이 **3인3색**(실측) — spreadsheet=절대경로 존중 /
  document=경로 버리고 프로젝트 outputs(단 메시지로 정직 고지) / chart=(수리 전) 무시.
  통일은 어느 쪽이든 **기존 문장의 산출 위치를 바꾸므로** 파괴적 변경 → 사용자 판정으로 올림
  (권고: 절대경로 존중=spreadsheet 쪽). 2회차 안에 판정하거나 '수용된 한계'로 닫을 것.
- **미수리 관찰**: `[table:since]` 의 첫 검침 통지(`note: "첫 검침 — 기준선 N행 저장…"`)가 **파이프
  중간에서는 봉투 표면까지 못 올라온다** — #73~#78 여섯 과제 전부 사용자가 0건만 보고 "첫
  검침이라 기준선만 세웠다"와 "새 것이 없다"를 구별할 수 없었다. 자리는 이미 있다:
  `skipped_steps`·`condition_errors`·`_caught` 를 승격하는 `workflow_engine.py:668` 규약에
  `note`/`seeded` 를 얹으면 된다. 다음 `#repair` 턴의 입력.
- **시드 0건(의도)**: 89건이 실행까지 통과했으나 대부분 "문법적으로만 처녀인 관절"이고 intent 가
  격자를 채우려 지은 것이라, 28회차가 자아비판한 템플릿 강도와 같다. §4-3 "검증 안 된 상상이
  번역기를 오염시킨다"를 지켜 실사용 관찰을 기다린다.
- **8배의 질 (28회차 지적에 대한 응답)**: 좌항 16개를 서로 다른 10개 도메인(부동산 실거래·전세,
  주가, 날씨, 음악, 자가점검 원장, git 원장, 중고매물, 창업공고, 기술피드, 프로세스 목록)에
  접지해 "같은 저작 오류의 N배 복제"를 피했다. 수확: 2배 3건 → 4배 4건 → 8배(28회차) 1건 →
  **8배+새 축(29회차) 3건 + 판정 1건 + 관찰 1건**. 규모가 아니라 축이 낳는다는 가설이 재확인됐다.
- ★**29회차 자기교정 (수리가 절반만 덮은 것을 라이브 재현이 잡았다)**: B29-1 처방 후
  `/packages/reload` 로 재현 문장을 다시 돌리자 **0행 → chart** 만 옛 문구 그대로였다. 원인은
  진단기가 통화를 `_extract_table_from_prev()` 로 집었는데 **그 헬퍼가 *그릴 수 있는* 표만
  만들어 주느라 빈 items 를 먼저 버린다**는 것 — "0행이 도착했다"는 사실이 진단기까지 못 왔다.
  1열 경우는 표가 만들어져 덮였고 0행 경우는 안 덮였다. 더 나쁜 건 **가드가 이걸 가렸다**:
  R2 첫 판이 `d = d or _diagnose_no_data({"table": {...,"rows":[]}} …)` 로 우회 입력을 하나 더
  대서 초록을 받았다(시험이 진짜 경로를 안 밟았다). → 교훈: **가드에 우회 입력을 대지 말 것.
  그리고 수리 뒤엔 반드시 라이브에서 원 재현 문장을 다시 돌릴 것**(§4-4 의 pytest 규약이
  회귀는 지켜 줘도 "이 수리가 실제 증상을 죽였나"는 재현만이 답한다). 처방 = 진단기가
  `_prev_result` 봉투를 직접 보고 items 가 리스트면(비었어도) 0행 도착으로 인정(문자열 JSON
  봉투 포함) + R2 에서 우회 제거. 네 상태(0행/1열/통화미도착/정상) 전부 라이브 실측 확인.

### 29회차 후속 — 판정 J29-1 집행 + 관찰 1건 수리 (2026-08-23, 사용자 판정 턴)

**J29-1 판정 = (가) 주어진 경로는 지킨다.** F29-2 가 올린 "emitter 산출 경로 3인3색"을
사용자가 "장기적으로 바람직한 쪽"으로 닫으라 지시했다. 판단 근거는 새 규약을 고르는 문제가
아니라 **이미 있는 규약을 셋이 안 지키고 있었다**는 데 있다 — `[self:write]` 가 세우고
`[table:spreadsheet]` 가 따르던 배치 규약(절대경로 존중 / 디렉토리 포함 상대는 프로젝트 기준 /
bare 파일명만 `outputs/` 리다이렉트)이 몸의 가장 오래되고 가장 많이 쓰이는 파일 규약이다.
반대안(모두 프로젝트 outputs 강제)은 `/tmp`·NAS 로 쓰던 spreadsheet 문장을 **조용히 딴 데로**
보내므로 이 몸이 금하는 침묵 이동 부류가 된다.

★**판정을 다시 재 보니 이건 파괴적 변경이 아니었다.** 29회차가 "어느 쪽이든 산출 위치가
바뀐다"고 적었지만, 실제로 바뀌는 것은 **사용자가 디렉토리를 적어 준 경우뿐**이고(가장 흔한
bare 파일명은 전후 동일하게 `outputs/`), 그 경우의 옛 동작은 어느 쪽 규약으로도 옳지 않았다
(chart 는 말없이 버렸고 document 는 고지하며 버렸다). "아무도 *내 디렉토리가 버려지는 것*에
의존하지 않는다" — 파괴적 변경 여부는 **의존 가능한 계약이 깨지는가**로 묻는 것이지 동작이
달라지는가로 묻는 게 아니다. 판정 요청이 과잉이었던 자리로 기록한다.

**수리 = 해소기를 하나로 접었다**(25회차 원칙의 재적용). 배치 규칙은 이제
`ToolContext.resolve_output_path()` **한 곳**에만 산다 — ToolContext 는 이미 "도구는 이
컨텍스트를 통해서만 외부 경로를 결정한다"고 선언한 자리다. 세 emitter 가 전부 그것을 통과한다
(확장자 보정만 emitter 의 몫 — 형식이 정하므로). ★**출처인 `[self:write]` 도 같이 통과시켰다** —
규약의 출처를 예외로 두면 다음 변경에서 다시 갈라진다(3인3색이 정확히 그렇게 생겼다).
곁가지로 `test_ibl_program_grade.py::test_e3` 의 **반쪽 context 스텁**을 진짜 `ToolContext` 로
바꿨다: 경로 해소가 컨텍스트 계약의 일부가 됐는데 스텁은 그 계약을 안 밟아 결함을 가린다
(29회차가 배운 "가드에 우회 입력을 대지 말 것"의 같은 부류).

★**쓰기 범위는 게이트에게 묻는다 — 베끼지 않는다.** chart·document 가 준 경로를 지키게 되면
프로젝트 outputs 밖으로 나갈 수 있게 되므로 RED 구역 판정이 필요해졌다. 그 규칙
(`_RED_ZONE_DIRS`·보호 상태파일·그랜트)은 쓰기 게이트(`system_essentials/handler.py`)가 **한 번만**
선언한다. 해소기는 `tool_loader.load_tool_handler("write_file")` 로 그 게이트를 **빌려** 쓰고,
못 빌리면 **fail-closed**(프로젝트 밖 거절)로 떨어진다. 규칙을 복사해 왔으면 그게 바로 드리프트다
(pre-commit 훅이 `red_safety_selftest --triggers-regex` 로 *묻기만* 하는 것과 같은 형태).
라이브 실측: `[table:document]{filename:"…/frontend/index.html"}` → **거절**(옛 동작은 경로를
버리고 `outputs/index.html` 을 만들며 **성공**했다).

**관찰(0행 사유 소실) 수리 — 승격 규약 네 번째.** `[table:since]` 첫 검침 통지가 파이프 중간에서
사라지던 것을 `halted_steps`·`skipped_steps`·`branches_failed` 와 같은 규약으로 봉투 표면에
올린다(`empty_notes` + `warning`). ★판정은 **모양으로만** 한다 — 어휘 이름을 엔진에 심지
않는다(헌법 '명사의 자리'): 조건은 "통화가 0행인데 `note` 를 달고 있는 **중간** step" 하나다.
`note` 는 이 몸에서 사용자 데이터이기도 하므로(notebook 메모·건강 기록) `items` 가 빈 리스트라는
**통화 모양**이 함께 있어야만 승격한다. 마지막 step 은 `final_result` 로 이미 보이므로 싣지
않는다(중복 토큰 0). 부수 수확: `[table:brief]`·`[table:ai]` 의 "입력 0행 — AI 호출 생략(비용 0)"
도 같은 규약으로 중간에서 들리게 됐다.

**가드**: `backend/test_emitter_output_path.py` P1~P12 · `backend/test_empty_reason_visibility.py`
E1~E6 신설. ★둘 다 **수리 없이 실제로 빨간지 먼저 확인**했다(경로 11/12 실패, 사유 2/6 실패) —
28회차의 "0건은 통과가 아니라 아무것도 안 봤다는 뜻"을 시험 자신에게도 적용한 것이다.
회귀 `339 passed, 2 skipped` (라이브). 라이브 종단 5건 실측(준 경로 존중·bare 는 그대로
outputs·chart 동일·RED 거절·since 사유 승격).

★**28회차 가드가 즉시 값을 했다**: 새 시험 두 개가 `__main__` 위임 없이 들어오자
`test_single_runner.py::test_r2` 가 그 자리에서 빨갛게 잡았다(직접 실행 0건 통과 방지).
★**폰 번들 재파생**(`scripts/build_body_bundle.py`) — 29회차가 남긴 `test_emitter_input_honesty`
누락분까지 함께 편입(engine 225 · blocklist 69).

### 30회차 (2026-08-23) — 축: **실패 문법 × 실패 원인** (언어의 '고장 나는 쪽 절반')
25~29회차의 축은 넷 다 **잘 되는 경로**의 조합이었다(처녀 액션·문법×문법·생산자×변환자·변환자→후속).
이번엔 반대쪽. 지표의 '문법 사용률' 표가 먼저 일렀다 — `&`·`if/case`·`$변수`는 있는데
**`try`·`on_error`·`repeat`·`??` 는 표에 아예 없다.** census: 실패 문법을 쓰는 문장이 코퍼스
3,582 중 **28건(0.78%)**, `resume` 은 **0회**. 격자(실패문법 8 × 실패원인 12) = 96칸 ·
기출 17(17.7%) · **처녀 79(82.3%)**. 기출은 거의 전부 '네트워크' 열 — **지금까지 이 언어가
상상해 본 고장은 사실상 '인터넷이 안 될 때' 하나였다.** 96칸 전수 실행. 결과: 정직신고 62 ·
고장없음 12 · 검수거절 6 · **차단됨 16**(아래 B30-2 여파).
- `B30-2` **차단기가 블록 문장을 전부 빈 키 하나로 뭉쳤다** (결함·수리됨·이번 회차 최대 피해).
  `[repeat:]`·`[try]`·`[if:]` 는 node·action 이 비어 `_fail_key` 가 전부 `agent::` **한 바구니**로
  들어갔다. 실측: 과제 #78 하나가 3회 실패해 바구니를 열자 **#81~#96 열여섯 칸이 한 번도 실행되지
  못했고**(회차의 17% 무효화), 막힌 문장들이 받은 사유는 자기가 건드리지도 않은 차트 열 문제였다.
  차단 메시지는 `[:] 액션이 연속 3회 실패…` 로 **아무 이름도 대지 못한다**(로그 실측: 빈 키 차단 36회).
  ★바로 위 주석이 의도를 정확히 적어 뒀다 — "단일 액션만 체크(파이프라인/병렬은 통과)". 병렬은
  `_parallel` 로 걸렀는데 **블록 표지는 아무도 안 걸렀다.** ★판정이 **두 벌**(체크 지점·갱신 지점이
  각자 키 조립)이라 같은 실수가 두 곳에 살았다. 수리 = `_breaker_key()` **한 벌**로 모으고 블록
  표지 7종·빈 node/action 을 비대상 처리(E28-3 의 `NOT_ISOLATED_SQL` 과 같은 규율).
- `B30-3` **리허설의 의도된 실패가 사용자의 실제 호출을 차단할 수 있었다** (결함·수리됨).
  훈련은 `ZZZZINVALID` 를 일부러 밟는데(이 회차 15회) 그 실패가 차단기를 열면 90초간 사용자의
  진짜 `[sense:stock]` 까지 막힌다. 차단기는 `origin:"training"` 을 전혀 보지 않았다 — **E28-3 과
  똑같은 사건이 다른 원장에서 재발**(그때는 순위 오염, 여기선 사용자 차단이라 더 나쁘다).
  수리 = 지우지 않고 **키 공간 분리**(`agent:training:node:action`), 판정기는 E28-3 이 세운
  `thread_context.in_rehearsal()` 그 한 벌을 재사용(새 판정기 안 만듦).
- `B30-1` **`[try]{[A] & [B]}` 가 "action 파라미터가 필요합니다"로 죽는다** (결함·수리됨).
  파서는 병렬을 `{"_parallel": […]}` 한 step 으로 내는데 `ibl_engine` 의 블록 디스패치 목록
  (`_goal`/`_condition`/`_case`/`_try`/`_repeat`/`_assign`)에 **`_parallel` 만 빠져** 아래 `action`
  검사까지 떨어졌다. 봉투가 `node: null, action: null` 로 **무엇이 죽었는지 모른다고 자백**한다.
  ★**코드가 이미 이 부류에 이름을 붙여 알고 있었다** — `system_tools_ibl.py:429` 의 "전 표면 블록
  실행 봉쇄 부류". 최상위 경로는 그때 고쳤고 **블록 몸 경로는 안 고쳤다**(부류 스윕이 한 자리에서
  멈춘 사례 — 앞으로 이 부류를 만나면 `_run_body` 계열도 함께 볼 것). 대조: 같은 한계를 `??` 는
  검수 시점에 정확한 이유로 거절한다 → **같은 한계를 두 문법이 다르게 말하면 안 된다.** 다만 try 의
  몸엔 우선순위 모호성이 없으므로 처방은 거절이 아니라 **지원**. 수리 = `_parallel` 분기를 형제들
  옆에 두되 의미론은 복제하지 않고 `execute_pipeline` 에 위임(**러너는 하나**). 가드가 분기 **순서**
  (action 검사보다 앞)와 **위임**(복제 아님)을 함께 본다.
- `F30-1` **몸은 정직한데 그 정직을 읽는 법을 아무도 안 가르쳤다** (마찰·부류·수리됨).
  실측: `skipped_steps`·`_caught`·`condition_errors`·`halted` 는 교재 언급 1회씩인데
  **`_fallback_used`·`ok_count`/`error_count`·`rows_in` 은 0회**. 이 회차에서 `_fallback_used` 는
  14칸, `ok_count/error_count` 는 6칸에 실제로 실렸다 — 달고는 있는데 읽는 쪽이 뜻을 배운 적이 없다.
  위험: `_fallback_used` 는 **데이터 출처가 바뀌었다**는 표지라, `[sense:stock] ?? [sense:search]` 가
  그걸 달고 오면 그건 시세가 아니라 검색 결과이고 "주가는 X" 라 답하는 순간 거짓말이 된다
  (`success: true` 만 봐선 구별 불가). ★`rows_in` 은 **29회차에 내가 신설해 놓고 가르치는 걸 빠뜨린
  표지**다 — 만든 사람도 잊는다. 수리 = `12_ibl_only.md` 봉투 절에 "정직 표지를 읽어라 —
  `success: true` 가 '다 잘 됐다'는 뜻이 아니다" 계약 조항 신설(7종의 뜻 + 보고를 어떻게 바꾸는지).
  가드 `test_R7` 이 8종의 교재 등재를 회귀로 지킨다. **어휘를 늘릴 때 교재 등재를 같이 하라**는
  규약이 필요하다는 신호(다음 회차 후보).
- **판정 대기 `G30-1`**: `??` 가 병렬(`&`)·조건 블록을 가지로 못 받는다(검수 거절 6칸). 거절 이유는
  옳다(우선순위 미정의 → 액션 유실). 우회 실측: `$par = [A] & [B]` + `[if: empty($par)]` 동작 ·
  B30-1 수리 후엔 `[try]{[A] & [B]}[catch]{[C]}` 가 그 수요를 정확히 덮는다. **권고: 넓히지 말 것**
  (없는 것은 능력이 아니라 짧은 표기이고, 대가로 사는 것은 모호성). 사용자 판정 대기 — 2회차 안에
  판정하거나 '수용된 한계'로 닫을 것.
- **미수리 관찰**: `[repeat: until …]{$r = <실패>}` 같은 정상적 재시도는 **설계상 연속 실패를 만드는데**
  차단기는 그것을 '눈감은 반복'으로 읽는다. B30-2/3 로 블록 자체는 비대상이 됐지만 repeat **몸통 안의
  단일 액션**은 여전히 카운트된다. 정상 재시도와 눈감은 반복을 구별하는 규약이 필요한지는 다음 회차 질문
  (지금 손대면 폭주 방어가 약해져 성급하다).
- ★**훈련자가 두 번 오진했고 두 번 다 격리가 반증했다**(가이드 §3-5 오진 격리 의무의 실전 사례).
  1차 판정기가 `??` 18칸을 "침묵 회복"으로 찍었으나 격리해 보니 `results[0].attempts[]` 에 신고
  중이었다(**추출기가 한 겹 얕았다**). 2차는 "층2 신고"로 낮춰 잡았으나 `final_result` 에
  `_fallback_used` 가 버젓이 있었다(**표지 목록이 불완전했다**). 결함이라 적기 전에 최소 재현으로
  두 번 반증됐다 — 그리고 **그 두 번의 오진 자체가 F30-1 의 증거**가 됐다(나조차 그 표지를 몰랐다).
  교훈: 판정기를 만들 때 "무신고"라는 결론은 **표지 목록의 완전성에 전적으로 의존**한다. 목록을
  먼저 실측으로 채우고(전 봉투에서 키를 수집) 그 다음 세라.
- **시드 0건(의도)**: 이 회차 문장은 전부 *일부러 고장 내는* 것(`ZZZZINVALID`·없는 열·없는 파일).
  해마에 올리면 번역기가 "주가를 물으면 ZZZZINVALID 를 조회한다"를 배운다 — §4-3 이 가장 날카롭게
  적용되는 회차다.

- **31회차 (2026-08-23, 8.00배 96과제)** — 축: 집합 참조(`$items`) × 소비자. 코퍼스 3,592문장 중 `$items` 9건(0.25%)·닿아본 소비자 2개뿐.
  - `B31-1` 집합이 글자 자리에 닿으면 파이썬 예외 누출(`'list' object has no attribute 'strip'`) → **수리됨**(바인딩이 표식, step 실패가 번역 — 액션 열거 없음)
  - `B31-2` 문장 *속* `$items` 는 치환·경고·실패 없이 **글자 그대로 저장**(메모리 12건 실측) → **수리됨**(정직 거절)
  - `F31-1` 실패 힌트가 '네가 준 키는 안 읽혔다'를 안 말함(96과제 중 12건이 이 침묵으로 죽음) → **수리됨**(선언 어휘 동봉)
  - `F31-2` 좌표 없는 목록 → show_map 은 이미 정직하게 거절(결함 아님, 기록만)
  - `G31-1` 문장 속 집합 참조 → **판정(08-23 사용자): 치환 + 경고로 통일, 집행 완료.** 근거 = ①규칙이 둘이었다(`$변수`=조용한 JSON·`$items`=조용한 거절) ②깨질 문장 0(문장 속 `$변수` 61건 전부 스칼라·저장 워크플로우 0) ③거절로 통일하면 두 목록→한 AI 지시문 길이 닫힌다. ★"결합 규약이 없다"는 31회차 진단은 절반만 맞았다 — 규약(JSON)은 이미 있었고 **조용했던 것**이 결함. 표식 `_list_in_text` 한 벌(파이프·블록·호출자 params), 번역 엔진 한 곳.

- **32회차 (2026-08-23, 8.00배 96과제)** — 축: 고차 문장의 안쪽(`[table:each]{do:}` 12종 × 바깥 통화 8종). 코퍼스 each 50건인데 do 안쪽 문법은 3종뿐(단일40·파이프6·중첩3), 나머지 9종 0회.
  - `B32-1` 신고가 한 방향뿐 — do 가 통화를 내어 **원 행이 대체**돼도 침묵(입력 2행→출력 10행이 무설명) → **수리됨**(`rows_replaced` 대칭 신고 + keep 안내)
  - `F32-1` 교재(12_ibl_only.md)가 은퇴한 `_ok/_result` 계약을 가르침 — 같은 문서 199행과 자기모순, yaml 가드(C11)는 교재를 안 봄 → **수리됨**(정정 + 교재 가드 C13 신설)
  - `G32-1` do 안 변환자·AI낱말이 행을 통화로 못 받음(16칸 거절, 정직) = **언어 개정 판정 요청**
  - 관찰: 처녀 문법 9종 중 **7종이 그냥 된다**(조건·try·폴백·병렬·변수할당·쓰기·스칼라) — 고차 자리는 언어를 거의 다 받아들이는데 아무도 안 썼을 뿐이었다.

- **33회차 (2026-08-23, 8.00배 96과제)** — 축: 블록 문장이 설 수 있는 **자리**(블록 문법 12종 × 자리 8종). 32회차 '고차 문장의 안쪽'의 형제. 근거 = 문법 사용률 최하위(`??` 0.4%·`if/case` 1.4%), M6 '블록은 파이프 세그먼트' 행동 코퍼스 0건. 검수 90/96 · 실행 73/96(깨끗 73·꼬임 17·불가 6).
  - `B33-1` `case` 좌변 해석기가 `if` 와 달랐다 — 술어함수(count/empty/exists)가 case 에서만 '판정 불능'(2칸). 교재는 '조건 언어 if/case 공통'이라 가르친다 → **수리됨**(`$` 접두 판별 *제거*, 좌변을 `atom_value` 하나로 통일 — 특례 추가 아님). 제안 `20260823_162936` → **라이브 적용됨**(2026-08-23 17:34)
  - `B33-2` `do:` 는 코드인데 바깥 동명 변수가 **할당 좌변까지** 치환 → `$n = $n + 1` 이 `0 = 0 + 1`(4칸). ★M6 가 **블록 몸**에 이미 내린 처방이 '코드를 나르는 param'에는 승계 안 됨 → **수리됨**(param 이름 열거도 통째 유예도 아닌 **텍스트 자신의 섀도잉** `assigned_names`, 깨질 용법 0). 제안 `20260823_162859`·`20260823_162913` → **라이브 적용됨**(2026-08-23 17:34). ★그 턴의 apply 가 거절된 진짜 사유는 '수리 경로 아님'이 아니라 **그랜트 TTL 만료**였다(45분 턴, 발급 시각부터 재는 30분 시계) — 근본 수리는 `red_grant` 절 참조
  - `F33-1` 교재가 `collect` 없는 `repeat` 도 통화를 낸다고 가르침(2칸이 여기서 죽음) → **수리됨**(교재 216행 정정, 라이브 즉시). ★가드 미설치 — 같은 시험 파일에 두 제안을 못 얹어 다음 수리 턴 몫
  - `F33-2` 블록 몸의 통화는 **첫 액션에만** 간다 — while/until 은 카운터 할당이 첫 줄이라 구조적으로 걸림(4칸). 교재가 이미 정확 = 결함 아님, 회피법 명시
  - `F33-3` 블록이 파이프 **머리**에 서면 몸의 반환형이 하류 계약(6칸, 정직 거절) = 기록만
  - `G33-1` `[on_error:]` 접두는 파이프 세그먼트가 될 수 없다(4칸, **검수가 사유와 함께** 거절) = 설계대로, 우회 `[try][catch]` 실측 통과. 세그먼트 단위 오류 정책 수요는 훗날 개정 안건
  - **오진 격리 2건**(가이드 §3-5 의무): ①'블록 봉투에 success 없음'(18칸) → 반증, 교재가 '핸들러 원문'이라 이미 가르침 — **훈련 하네스의 오독**(고치니 실행 58→73) ②'검수가 사유를 안 말함'(6칸) → 반증, `syntax_error` 필드로 말함. ★두 오진의 뿌리가 같다 — 봉투 모양이 여럿인데 키 하나로 성패를 판정하려 했다. **훈련 하네스 자신도 '정직 표지를 읽어라' 규약의 독자**임을 실측으로 배움
  - `G32-1` **재상신 2회차** — 33회차 P6 실측이 근거 보강: 블록 문법 12종 중 **10종이 `do` 안에서 그냥 된다**. 막힌 것은 통화를 받는 변환자·AI 낱말 하나뿐이라 갭이 좁아졌다

- **34회차 (2026-08-23, 수리 턴 — 훈련 아님)** — 사용자 지시 "오류가 있을 만한 곳을 뒤져 고쳐라". 탐색 3축(실사용 원장·미커밋 변경분·회귀).
  - `B34-1` **스칼라 선언 param 에 목록·사전** — `[sense:stock]{ticker: ["AAPL","MSFT"]}` 가 **에러 없이 태국 증시 AAPL19.BK** 를 돌려줬다(str() 로 뭉개진 문자열이 종목명 검색어가 됨). `[sense:weather]{city:[...]}` 는 `'list' has no attribute 'lower'`. 조용한 오답이 예외보다 나쁘다 → **수리·라이브 적용됨**(`.upper()` 자리 58곳 열거 대신 **tool.json input_schema 대조**를 `_route_handler` 관문 한 곳에. array 선언 param 은 통과 = 깨질 용법 0)

- **35회차 (2026-08-23, 4.00배 48과제)** — 축: **B34-1의 부류 전수 스윕**(타입 위반 8종 × 자리 6종). 직전 턴 사용자 지적 *"처방 범위를 자리 하나로 좁게 잡는다"* 를 직접 겨눔. 검수 48/48 · 결말 정직거절 37 · 파이썬예외샘 6 · 조용한통과 5.
  - `F35-1` **교재가 정직 표지 1번으로 가르치는 `_fallback_used` 가 실물로 안 나온다** — 폴백 결과가 **평문 스칼라**면(dict 도 JSON 문자열도 아닌 세 번째 모양) 표지가 조용히 사라진다. ★30회차가 이미 절반 고쳤다: `test_R7` docstring 이 "몸이 실제로 싣는데"라고 **가정**하고 교재만 고쳤고 가드도 교재만 봤다. ★34회차의 세션 자신이 이 키를 세어 0 을 얻고 '폴백 없음'으로 읽은 거짓 안심이 피해 사례 → **수리·적용 예약**(결과 모양 열거 대신 표지를 **봉투**로 옮기고 `branches_failed` 배선 승계 — step 요약→_seq 누산→최상위+warning). 회귀 `test_R8`(평문 스칼라 + 거짓 경보 금지)
  - `B35-1` **string 자리에 숫자 → 파이썬 예외**(V3, 6자리 전부 `'int' has no attribute 'lower'`) = **판정 요청(파괴적 변경)**. 거절하면 코퍼스 **79건 파괴** 실측(`[limbs:screen]{x: 300, y: 200}` 45건 등), `str()` 변환도 불가 — 파서가 `ticker: 005930` 을 이미 **5930** 으로 만든다(앞 0 소실). 세 겹 갭(핸들러 미방어 + tool.json 선언 부정확 + 파서 0 소실)
  - `B35-2` bool·int 자리의 **조용한 타입 강제**(`headlines: "yes"` 통과 · `n: 3.7` → 3행 침묵 절단) — B35-1 판정 시 같은 관문에서 함께 처리하는 게 옳아 미수리·기록
  - **오진 격리 2건**: ①'병렬·폴백 자리에서 위반이 통과'(17칸) → 반증, `branches_failed`·`attempts` 로 **정직 신고** 중이었고 판정 함수 오독(고치니 정직거절 25→37) ②'MCP 에 `origin` 파라미터 없음 = 표면 누락' → 반증, 헤더 전파가 **설계**(RED 그랜트 축이라 호출자가 못 정함)
  - 관찰: V1·V2가 6/6 정직거절 = **B34-1 수리의 회귀 확인**(수리 전엔 조용한 오답 또는 예외)

- **36회차 (2026-08-25, 4.00배 48과제)** — 축: **통화 모양 8종 × 문장 경계 6종**(파이프·개행 변수·세미콜론 변수·조건·try·병렬 재사용). 최종 교정본 validate 48/48 · 무부작용 실측 48/48 · 깨끗 42 · 결함 영향 6. 훈련 호출은 `source=training`으로 전량 격리.
  - `B36-1` **희소 items→table 투영의 조용한 열 소실 — 수리됨.** `_get_table`이 전 행 키를 첫 등장 순으로 합쳐 union에서 뒤 행의 값이 보존된다.
  - `B36-2` **내림차순에서 결측값이 맨 앞으로 역전 — 수리됨.** 수치→문자열→결측 버킷 순서는 고정하고 각 값 버킷 안에서만 정렬 방향을 적용한다.
  - `F36-1` **inline `items` 검수/실행 진단 불일치 — 수리됨.** 공개 스키마에 `items`가 없는 파이프 전용 변환자는 validate가 먼저 경고하고 runtime도 `table:each` 대신 `take{items:…} >> 변환자`를 안내한다. 직접 입력 언어는 넓히지 않았다.
  - `F36-2` **지원하지 않는 catch 몸을 “catch 없음”으로 오진 — 수리됨.** 블록 존재와 몸 파싱 실패를 분리해 목록·사전 리터럴이 식에서 미지원임을 정확히 알린다. `$return=0`·catch 액션은 그대로 정상.
  - 수리 가드=`backend/test_imagination_round36_repairs.py` 6건. 관련 데이터/IBL 회귀 123건과 전체 backend 배터리 498건 통과.
  - 긍정: 표준/빈/단일/중복/혼합 통화의 경계 동치성, 빈손 6자리, scalar 오연결의 condition_errors·branches_failed·`_caught`, 이종 union warning 모두 생존. 시드 0건(격자 구두점 변형으로 코퍼스 팽창 방지). 보고서=`outputs/imagination_training/2026-08-25_36회차.md`.

- **37회차 (2026-08-25, 8.00배 96과제)** — 축: **비교 연산 표기 12종 × 숫자 값 모양 8종**(정수·실수·숫자문자열·쉼표·음수·소수·큰정수·선행영 + 각 희소 행). validate 96/96 · 무부작용 실측 96/96 · 기대 결과 48 · 결측 포함 48. 훈련 액션 192행은 `source=training`으로 전량 격리.
  - `B37-1` **필드 없는 행이 `>`·`>=`를 만족 — 수리됨.** 비교 관문 한 곳에서 결측 순서 비교를 불일치로 판정해 `_num_cmp(None,n)`의 `"None"` 사전식 승격을 차단. 기호/워드·문자열/구조형/목록형에 동시 적용.
  - `G37-1` **`!=/ne`의 결측 의미 — 판정·집행 완료(사용자: 권고 따름).** “모르는 값은 다르다고 주장하지 않는다”로 정해 결측 행을 제외. 결측 동등 검색과 값 있는 행의 `ne null`은 보존.
  - 수리 가드=`backend/test_imagination_round37_repairs.py`(원 96칸 재생 + 결측/null × 3조건형 + 결측 검색 경계). 전체 backend 528 passed·2 skipped, 빌드·층·Android 번들·라이브 종단 3건 통과. 긍정: 기호/워드 별칭 6쌍 × 8모양 전부 동치, 값이 있는 288개 행 판정은 예상과 일치, 숫자 표기 8종의 수치 의미 보존. 시드 0건. 보고서=`outputs/imagination_training/2026-08-25_37회차.md`.

- **38회차 (2026-08-25, 4.00배 48과제)** — 축: **조인 키 모양 8종 × 전달·결합 경로 6종**(items 직접·변수·table join, merge 직접·변수, union→dedup). validate 48/48 · 무부작용 실측 48/48 · 깨끗 35 · 의미 불일치 13. 훈련 액션 184행은 `source=training`으로 전량 격리.
  - `B38-1` **숫자 키 0이 빈 키로 소실 — 발견됨.** `_norm(s or "")`가 `0`·`False`를 `""`로 바꿔 `0`/`"0"` join은 누락, merge/dedup은 중복 보존(6경로 전부 오답). `None`만 별도 처리하는 수리 필요.
  - `B38-2` **items/table 흡수 순서에 따라 null·부재 join 결과가 달라짐 — 발견됨.** 직접 병렬 items 봉투는 `_get_table` 우선으로 table화되어 null끼리 조인(2행), 같은 자료의 변수 raw list 경로는 items 규약으로 제외(1행). 공용 조인키 유효성 판정과 입력 모양 선판별 필요.
  - `G38-1` **빈 문자열 관계 키 의미 — 판정 요청.** join은 빈 키끼리 연결하지만 merge/dedup은 키 없음으로 보존. 권고는 거짓 관계 연결을 막도록 빈/공백 키를 null·부재와 같이 join 제외.
  - 긍정: 정상·대소문자·다중공백·숫자문자열 24/24 경로 동치, merge/dedup은 키 없는 원행 보존. 시드 0건. 보고서=`outputs/imagination_training/2026-08-25_38회차.md`.
