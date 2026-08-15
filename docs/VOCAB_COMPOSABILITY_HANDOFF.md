# 어휘 조합성 재점검 핸드오프 (2026-08-15)

> **다음 세션 START HERE.** 1차 집행 완료(154→**151**, 커밋 `a38c2d8`) + 2차 집행 완료(151→**150** — §1b, 같은 날 후반).
> 남은 것: **2c(blog→notebook)는 사용자 판정 대기**(§2c), 스위치화·휴면 후보는 계수 숙성(§3), 판정 대기 표(§4).
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
- **등록 스크립트 "잔여추정"**(outputs/scripts/잔여추정.py) ← `self:residual` 은퇴. estimate(Wilson CI)+sample(file_index).
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
