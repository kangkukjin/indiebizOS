# 어휘 개념중복 감사·압축 핸드오프 (2026-08-05)

> 정본. 메모리 `vocab-dedup-2026-08` 이 여기를 가리킨다.
> 배경 명제: 정합성 가드(`--check`)는 *존재* 정합만 본다 — 두 액션이 각자 정합이면
> 같은 개념이어도 통과한다. 압축(개념 중복 제거)은 *의미 거리* 검사라 다른 기관이
> 필요하고, 그 기관은 이미 있다: 해마 임베딩. 이 작업은 "IBL 이 누적적 언어로
> 남으려면 증류가 성장보다 빨라야 한다"는 진단의 실행이다.

---

## ▶ START HERE — 현재 상태와 다음 단계

**완료 (0)(1)(2)(3)(4)(5)+2b(book)+슬라이드/영상 일원화 + (7)조합성 재점검 1차(2026-08-15, **151 액션**) · 남은 것 = (6) 설계 태스크 2건(몸축·스케줄 3형제) + (7) 2차 후보(newspaper→스크립트·collect→crawl·blog→notebook — 구현 심사 필요) + 계수 숙성(2026-08-15 이후 데이터만) 후 D급 은퇴 판단.**

### (7) 조합성 재점검 1차 실행 기록 (2026-08-15) — ★후속 정본 = `VOCAB_COMPOSABILITY_HANDOFF.md`
판정 원칙: **낱말 자격 = 새 차원(감각·프로토콜·원장·미디어), 오케스트레이션·산술·URL 하드코딩 = 문장/스크립트로.**
- 계수 수리: `_usage_origin()` 에 `__self_check__` → origin `'selfcheck'` 분리 (위 (0) 절 정정 참조).
- `sense:pew_research` 은퇴 → **`sense:feed`{url, limit} 신설**(web 패키지, 범용 RSS/Atom — URL 하드코딩 복합어를 보편어로 대체). 코퍼스 5행 이관.
- `limbs:explorer`·`limbs:photo_manager` 은퇴 → **`open_window`{app: files|photos}** 흡수(ibl_routing pending-queue 직결). explorer 의 desc 거짓말("Finder") 해소 — 코퍼스 22행 이관(파인더 명시 intent 4행은 os_open 으로 정직 재배선).
- `self:residual` 은퇴 → 등록 스크립트 **"잔여추정"**(outputs/scripts/잔여추정.py — Wilson CI estimate + file_index sample, [self:script] 라이브 검증).
- 검증: build --check 전 가드 통과(151) · 라이브 종단(feed 실 RSS 3건 · open_window files/photos 큐잉 · 은퇴어 validate 반려) · 해마 시드 9 + 이관 27 + rebuild_index 3,175(벡터 누락 0) · 연상 직행 4/5. ⏳재학습 대기열: feed·open_window 흡수, "블로그 RSS"↔self:blog 경계.

| 단계 | 상태 | 커밋 |
|---|---|---|
| (0) 사용 계수 배선 (은퇴 판단의 눈) | ✅ | `09cd5b8` |
| (1) 싼 병합 5건 (163→**159 액션**) | ✅ | `80a3392` |
| (2) 검색 통합 `[sense:search]{source}` (159→**155**) | ✅ 2026-08-05 | `dbf370d` + 아래 실행 기록 |
| (3) 코퍼스 교정 (동음이의 충돌쌍) | ✅ 2026-08-05 | 아래 (3) 기록 |
| (4) M4 로컬 재학습 1회 + 연상 probe | ✅ (2) 직후 같은 세션 | 아래 (4) 기록 |
| (5) 압축 상설 기관 (--check 경고 + 주간 감사) | ✅ 2026-08-05 | 아래 (5) 기록 |
| (6) 보류 3건 → 설계 태스크 | ⏳ | — |

(2)는 백엔드 기동 중에 실행 — `/packages/reload` 로 라이브 반영·5 source 종단 검증 완료.

### (5) 실행 기록 (2026-08-05)

세 신호가 각자 맞는 기관에 상설화됐다:

| 신호 | 기관 | 카덴스 | 형태 |
|---|---|---|---|
| 자백 (desc 면책 과다 ≥3) | `build --check` `compression_warnings`(iblbuild_validators) | 커밋마다 | **경고만**(비차단) |
| 구조 (같은 group op Jaccard ≥0.8) | 〃 | 커밋마다 | 〃 |
| 실증 (코퍼스 교차-액션 최근접 ≥0.95) | `vocab_overlap_audit.run_vocab_overlap_check` — run_maintenance_bundle 8번 항목 | **주간**(168h 자기 페이싱) | 깃발(`data/ibl_overlap_flags.json` + self_checks `__ibl_health__:vocab_overlap`) |

- desc 면책 기존 4건(others:contact·self:memory·engines:slide·engines:html_video)은
  `_COMPRESSION_DESC_BASELINE` 동결 — 새 진입만 경고(래칫 관례). op Jaccard 는 현행 0(최고 0.67).
- 실증 감사는 **빌드가 코퍼스를 안 읽는 원칙**대로 유지보수 번들에 산다. ★vec 조인은
  `IBLUsageDB._get_vec_connection()`(일반 `_get_connection` 은 vec0 미로드 — 실측 함정).
  측정 실패는 audit_incomplete 로 정직 보고(침묵=눈먼 감사 금지). LLM 0·주간 ~수 초.
- 첫 강제 실행 깃발 4쌍(전부 알려진 회색지대): search_shopping↔used(혼합 의도)·
  limbs:music↔player_status·engines:slide↔self:slide·self:deck↔self:slide(슬라이드
  가족 = (6) 설계 태스크 후보). 판단·병합은 사람 몫 — 감사는 깃발만 꽂는다.

### (3) 실행 기록 (2026-08-05, (4) 1차 직후 — 교정 후 재학습 1회 더 수행)

- **재측정**(병합 후 코퍼스 3,020): 교차-액션 최근접 cos≥0.80 = 92쌍·175행 (병합 전 84쌍과
  측정 시점 다름 — 검색 병합이 일부 해소·시드가 일부 추가). 측정 코드는 세션 인라인
  (ibl_examples_vec 로드→코사인 최근접, 액션=첫 브래킷 정규식).
- **교정 3종**: ①오라벨 code 수정 5건("이더/비트코인 시세"가 sense:stock, "한달살기"가
  sense:realty, "청주 맛집"이 sense:search, 신문 제호 예시 등) ②애매 intent 문맥화 30건 —
  board/bulletin("게시판"→노스트르 태그방/자유게시판 명시), sense/limbs cctv(검색↔재생),
  android/screen(폰↔맥), limbs/self music(유튜브뮤직↔내 파일), 즐겨찾기 3형제(사이트/
  방송국/이웃), os_open("구글 검색 좀"→"브라우저로 띄워줘"), self:blog("내 블로그" 명시),
  file_find/list/explorer, ask/here(부탁 대상 몸 명시) ③대조 시드 7건 → **3,027 용례·벡터 누락 0**.
- distilled 원장에도 같은 교정 동기(해당 2건 — 나머지 교정 행은 합성 코퍼스 소속).
- **교정 흡수 재학습**(2차, epoch 5 최적 0.884): compare = desc-T5 +1.2p·code 동급·프로브
  27/27 동률 → 채택(게이트 충족). desc-T1 은 -3.9p 노이즈성 하락 있었으나 **기능 목표 달성**:
  "네이버 블로그 후기"→search{naver,blog} / "내 블로그 커피 글"→self:blog 양방향 정확,
  가디언/HN/이더/맛집/게시판 전부 교정 방향 직행(라이브 translate 실증, 워커 70763).
- 백업 2벌: `ibl_embedding.bak.20260805_search_merge`(병합 전 원본) ·
  `ibl_embedding.bak.20260805_corpus_fix`(1차 재학습 모델). 롤백=디렉토리 교체→rebuild_index→reload.
- 잔여: "웹 검색해줘"(질의어 없는 단독 표현)는 여전히 browser/os_open 과 저점(0.65) 경쟁 —
  진짜 애매라 반사 임계 아래, 의식 경로가 가름. 방치 가능.

### (4) 실행 기록 (2026-08-05, (2) 직후)

- 07-21 정본 레시피 그대로(맥미니 M4, `backend/ibl_embedding_trainer.py` batch8·seq64·seed42):
  백업 `ibl_embedding.bak.20260805_search_merge` → 학습(코퍼스 3,020·155 desc·4,871쌍,
  epoch당 ~100초, **epoch 6 최적 0.890** 조기종료) → `compare_models.py` 사과대사과 →
  **채택**(code T5 90.7→92.3 +1.6p·desc T5 93.3→93.7·프로브 26→**27/27**) → epoch_* 정리
  → rebuild_index(3,020) → **touch reload**(keeper 가 유령·사망 자동수습하는 08-05 체제라
  명시적 kill 대신 uvicorn reload 채택, 워커 교체·유령 0 확인).
- compare_models.py 에 검색 통합 프로브 5개 추가(웹/네이버 블로그/가디언/HN/구글뉴스 → sense:search).
- 라이브 번역 실증: "가디언에서 기후변화 기사"→`{source:"guardian"}` / "네이버 블로그 제주 맛집 후기"
  →`{source:"naver", type:"blog"}` / "해커뉴스 프론트페이지"→`{source:"hn"}` 전부 직행.
- 잔여 회색지대(→ (3) 대상): "네이버 블로그 후기"류가 self:blog(내 블로그)와 경쟁, "웹 검색해줘"
  단독은 limbs:os_open 과 경쟁 — 원래 있던 경계 모호(코퍼스 교정 84쌍에 합류).
- 롤백: `rm -rf data/models/ibl_embedding && mv data/models/ibl_embedding.bak.20260805_search_merge
  data/models/ibl_embedding` → rebuild_index → 백엔드 reload.

### (2) 실행 기록 (2026-08-05)

- **소속 실측이 핸드오프 가정과 달랐다**: ddg/gnews/hn=web, naver=**web-kr**, guardian=**study**.
  → 전부 **web 으로 흡수**: `tool_naver_search.py` 이동+**web-kr 패키지 은퇴**(폴더 삭제,
  core_manifest·PHONE_VERIFIED 에서 제거), `_search_guardian` 구현을 study→web 이주
  (web 의 `_guardian_items` importlib 차용도 로컬 호출로 단순화 — 교차 패키지 import 소멸).
- **★설계 번복 기록 (web/web-kr 로케일 분리)**: web-kr 분리 사유였던 "universal 로케일에서
  네이버(kr·키 필요)만 분리 관리"는 source 축과 양립 불가 → realty 선례(한 패키지 안에
  키 필요/불요 소스 혼재, 키 없으면 안내 오류)로 흡수를 택했다. 키 없는 설치에서
  `source:naver` 는 명시 오류("NAVER_CLIENT_ID 미설정")로 정직하게 떨어진다.
- **구현 형태**: 액션 `search`(tool: `search`), source 디스패치는 handler 의 `search` 갈래가
  내부 tool 이름(ddgs_search/naver_search/search_gnews/search_hn/search_guardian)으로
  재귀 위임 — 검증된 gnews/hn 배치 경로(신문 발행 shim 포함)는 무이동. `aliases:
  count: [display, page_size]` 로 구 파라미터 흡수, param-canon 면제도 `sense:search`
  로 이주.
- **★load_tool_handler 는 tool.json 레지스트리 기반** — world_pulse_collectors 가
  `_exec_tool("search_gnews")` 로 뉴스를 수집하고 있었고 병합으로 **조용히 죽을 뻔**
  (None 반환·빈 헤드라인). `_exec_tool("search", {source:...})` 로 이관. 교훈: 어휘 병합 시
  IBL 코드 문자열뿐 아니라 **tool 이름 직접 호출**(`_exec_tool`/`load_tool_handler`)도 grep.
- **ibl_health_check 픽스처 6건**·NewspaperInstrument(gnews|hn source 축)·
  AudioBriefing·12_ibl_only·가이드/시스템문서/프롬프트 전부 이관. inventory.md 재생성.
- **코퍼스**: `scripts/migrate_vocab_search_merge.py`(★backend/ 아닌 scripts/ — 폰 번들
  스캔 밖이라 force_exclude 불요) 150행+distilled 89건 이관, hn(0행)·guardian(5행) 빈약해
  **수동 시드 10용례**(_load_model_sync 선행) → 3,020 용례·벡터 누락 0. probe: hn/naver/
  gnews 직행, "가디언 기사"·"웹 검색해줘"는 재학습 대기(구모델이 search 어휘 미학습).
- 검증: build --check 전 가드·param_canon·층 가드·tsc·parser 자기시험·라이브 5 source
  +배치+alias+파이프(&·>>·merge)+구이름 명시오류.

---

## 0. 진단 (2026-08-05 측정 — 재측정 불요, 수치 보존)

세 가지 신호로 개념 중복을 측정했다:

1. **자백**: desc 가 타 액션을 지목해 "이건 저거 아님"이라 방어 — **25/163 (15%)**
2. **구조**: op 어휘 집합 Jaccard ≥ 0.5 쌍 — **9쌍** (radio_favorite↔follow 는 1.00)
3. **실증**: 해마 코퍼스 3,010 용례의 교차-액션 최근접쌍(cos ≥ 0.80) — **84쌍**
   (최고 0.990 = "게시판 목록 보여줘"가 board/bulletin 양쪽에 붙어 있었다)

측정 코드는 1회성(세션 인라인)이었다 — 재측정이 필요하면: 코퍼스 벡터는
`ibl_examples_vec`(sqlite-vec, embedding 컬럼)에서 로드해 코사인 최근접,
액션은 `re.search(r'\[(\w+):(\w+)\]', ibl_code)` 첫 매치.

### ★진단 정정 3 (계획의 전제 — 어기면 안 됨)

1. **episode_log 0회 ≠ 미사용.** episode_log(world_pulse.db)는 자율주행 경로만
   기록한다. 앱/조종실/원격의 `/ibl/execute` 직행은 안 남는다 — family_news·icon 이
   "미사용"으로 오판됐던 원인. **은퇴 판단은 (0)의 사용 계수가 숙성된 뒤에만.**
2. **sense/limbs 쌍은 설계된 축 — 병합 금지.** cctv·radio·music 의 sense/limbs(또는
   self/limbs) 분리는 감각/동작·내파일/외부서비스 축이며 radio 선례로 헌법이 승인한
   패턴. 코퍼스 충돌은 어휘 결함이 아니라 오라벨 → 처방은 (3) 코퍼스 교정.
3. **board/bulletin 은 동음이의 — 병합 금지.** Nostr 태그방 vs 무로그인 웹게시판은
   다른 개념이 한국어 "게시판"을 공유할 뿐. 처방은 코퍼스의 애매 용례를 문맥 있는
   용례로 교체.

---

## 1. 완료된 것

### (0) 사용 계수 — `09cd5b8`

- `_execute_ibl_unified`(cognition/system_tools_ibl.py — 전 경로 단일 관문)에서
  코드에 등장한 (node,action) 쌍을 origin 별 일 집계.
- 저장: `ibl_usage.db` `action_usage_daily` (day×node×action×origin, PK upsert —
  유계·원문 무저장·실패 무해 삼킴). 조회: `ibl_usage_db.action_usage_summary(days)`.
- origin: `app`(앱 표면·포털 게이트) / `manual`(조종실) / `web`(원격 기타) /
  `agent` / `internal`. 분류 = `_usage_origin()` (시스템 프로젝트 컨텍스트 관습 재사용).
- 계수 의미 = **어휘 수요**(코드에 쓰였는가), 실행 완료 아님 — `??` 뒷가지도 계수.
- ~~자가점검(ibl_health_check)은 이 관문 밖 → 계수를 오염하지 않는다.~~ **← 거짓으로 판명(2026-08-15 감사).**
  순찰은 `/ibl/execute` + `agent_id="__self_check__"` 로 이 관문을 지나며, `_usage_origin()` 이
  이를 'agent' 로 분류해 **2026-08-15 이전 agent 계수의 ~55%가 순찰분**이었다(지문: fixture 수 × 순찰 횟수와
  정확 동기 — exhibit 1/일, entity 2/일). 수리: `__self_check__` → origin `'selfcheck'` 분리(2026-08-15).
  **은퇴/압축 감사는 2026-08-15 이후의 origin='agent' 만 신뢰할 것.** 이전 구간이 필요하면
  fixture 수 × 순찰 횟수(12h 주기)를 빼서 디컨볼루션.

### (1) 싼 병합 5건 — `80a3392` (163→159)

| 병합 | 요점 |
|---|---|
| `output{op:file}` → `write` | **write 가 파이프 싱크 겸용이 됨**: content 생략 시 `_prev_result`(workflow_engine 자동 주입) 저장, `""` 는 유효 content(None 만 폴백). 구 `_output_file` 은 RED 쓰기 안전판 우회 + 파이프 입력 무시(빈 파일)라 삭제. output 은 gui/clipboard 만. op:file 호출 시 안내 오류("write 로 이동") 반환 |
| `image_critic` → `image_read{op:critic}` | media_producer 첫 op-bearing. 구현 2함수는 `gemini_vision.py` 분리(1500줄 래칫), `_OP_DISPATCHERS` 는 handler.py 에 잔류(AST 가드가 handler 본문을 파싱). 에러 맨문자열 13건 → `{"success":False,"error":...}` 관례 변환 |
| `fs_query` → `file_find` 메타 모드 | pattern 있으면 glob, 없으면 메타(`fs_meta.py` — 구 pc-manager `_query_storage` 이식, backend/file_index.query 위임). ★메타 트리거에 **path/sort 포함** — `{path:"~/Desktop", sort:"mtime"}`(폴더 최근 파일)이 코퍼스 실사용 형태였다. files 계기(🗂️ 3탭) app 블록 동반 이사. `search_term` param-canon 면제도 이주 |
| `self:agents` → `others:agents` | 트리 조회가 상위집합. sqlite_driver 의 죽은 `agents` 갈래·`_memory_agents` 제거 |
| `run_pipeline` → `workflow{op:run, steps}` | ★**내부 배관 무접촉**: `execute_workflow_action("run_pipeline")` 갈래는 유지(트리거·캘린더 `event_action` 어휘 + system_ai_plans 가 액션명으로 직접 호출). 실행 본체는 `_run_inline` 공유. IBL 표면 어휘만 제거 |

**동반**: 코퍼스 이관 50행+distilled 1건(`backend/migrate_vocab_cheap_merges.py` —
transform() 이 5패턴 전부 처리, 재사용 가능) → `IBLUsageDB().rebuild_index()`
3,010개 8.8초. 문서 7표면(ibl.md 어휘표·12_ibl_only.md·technical/scheduler_guide/
memory.md·disk_search.md·web_builder.md·guide_db). 낡은 `sense:web_search` 예시
2곳(system_tools_ibl usage dict·tool_loader)도 수리.

**검증한 것**: build --check 전 가드 / check_param_canon / check_string_returns /
라이브(인프로세스): 파이프 싱크 실파일 확인·메타 검색 1,663건·즉석 steps 실행·
others:agents 트리·critic 디스패치 도달·op:file 안내 오류·죽은 어휘 명시 오류.
연상 probe: "파이프라인 바로 실행해"→workflow{op:run} 0.836, "에이전트 목록"→
others:agents 0.876, critic 의도 질의→image_read 상위.

---

## 2. ★다음 세션이 그대로 쓸 절차 (1단계에서 검증된 플레이북)

병합 1건의 순서 (가드가 나침반 — 빌드를 먼저 돌리고 에러를 따라가면 됨):

1. src 편집: 코어는 `data/ibl_nodes_src/*.yaml`, 패키지는
   `data/packages/installed/tools/<pkg>/ibl_actions.yaml` (actions + tool_json 두 절).
2. `python3 scripts/build_ibl_nodes.py` → 가드 에러를 따라 수정 → `--check` 녹색.
3. handler 디스패치 (tool 함수 매핑 불변이 원칙 — engines→table 불변식).
4. 코퍼스 이관: `backend/migrate_vocab_cheap_merges.py` 본떠 transform 작성 →
   실행 → `IBLUsageDB().rebuild_index()` → 연상 probe(search_hybrid).
5. 문서: ibl.md(§어휘표+총수 7곳쯤)·가이드·guide_db·프롬프트 fragment.
6. 커밋 (pathspec 으로 — 동시 세션 공유 인덱스).

### ★함정 목록 (1단계 실측 — 전부 가드가 잡아줬다, 우회 금지)

- **op-bearing 전환 3종 세트**: `target_key: op` 필수 + tool_json 스키마에 `op`
  property 자리 + `side_effect:` 명시. 빠지면 빌드가 정확한 문구로 지시한다.
- **`_OP_DISPATCHERS` 등록 = string-returns 가드 스캔 대상 진입.** 등록하는 함수에
  맨 문자열 return 이 있으면 그때 터진다(기존 부채가 새로 보이는 것) — 관례
  dict 로 변환하는 게 정답, BASELINE 추가는 래칫 게이밍.
- **1500줄 래칫**: handler 가 자라면 형제 모듈 분리(`_load_sibling` 패턴 —
  system_essentials 779행 선례). `_OP_DISPATCHERS` 만은 handler 본문에 남긴다.
- **폰 번들 가드**: backend 루트에 새 .py(마이그레이션 스크립트 포함)를 만들면
  `data/bodies/android.json` `force_exclude` 에 사유와 함께 선언 +
  `python3 scripts/build_body_bundle.py android` 재생성(파생 `android.engine.json`
  도 커밋에 포함).
- **param-canon 래칫**: 비정본 파라미터명이 액션을 옮겨가면
  `scripts/check_param_canon.py` BASELINE_PARAMS 의 면제도 함께 이주.
- **해마 시딩/재색인**: `rebuild_index()` 는 모델 동기 로드 포함이라 그냥 부르면
  됨. add_examples_batch 로 새 용례를 심을 땐 `_load_model_sync()` 선행(벡터 침묵
  누락 함정).
- 문서 수는 항상 파생으로 확인: 액션 총수·노드별 수는 빌드 출력이 진실.

---

## 3. (2) 검색 통합 — 다음 세션의 본론

**대상**: `search_ddg`(코퍼스 52) · `search_naver`(45) · `search_gnews`(28) ·
`search_hn`(0) · `search_guardian`(5) → **`[sense:search]{source: ddg|naver|gnews|hn|guardian}`**
(5→1, 159→155). 전부 web 패키지(확인 필요 — hn/guardian 소속 재확인).

**설계 결정(재검토 완료 — 뒤집을 이유가 나오면 기록하고 뒤집을 것)**:
- `pew_research` 는 **제외** — 파라미터 없는 피드지 검색이 아님. 은퇴 후보로
  계수 숙성 대기.
- naver 의 `type`(webkr/news/blog/cafe/...)은 sibling 파라미터로 존치.
  "뉴스"가 source:gnews 와 naver+type:news 둘 다 가능한 건 현실의 중복
  (다른 코퍼스)이라 남긴다 — source 축의 의미는 "어느 엔진".
- 기본 source: **미정** — 한국어 질의는 naver, 영어는 ddg 가 현 관례. 후보:
  (a) 기본 ddg + desc 에 한국어→naver 안내(현 상태 보존) (b) 핸들러가 질의
  한글비율로 자동(어휘가 얇아지지만 마법이 늘어남). **(a) 권장** — 마법 최소.
- `search_youtube`·`search_local`·`search_shopping` 은 이번 대상 아님(도메인 검색,
  source 축 아님). `book` 군(book/search_books/classic)은 2b 로 보류 — 검색 통합
  절차가 무사하면 재사용.

**이 병합 특유의 리스크**:
- **최대 트래픽 구역**(에피소드 1,853+815+106회). 재학습 전 공백기에 구 이름
  회상이 약해진다 → 코퍼스 130행 이관이 브리지가 되지만, **(4) M4 로컬 재학습을
  같은 세션 또는 직후에 붙이는 걸 강권** (선례: [hippocampus-retrain] 메모리 —
  맥미니 M4 로컬 재학습 epoch 5, OOM 없음. 파이프라인=cloud_training/ 참조하되
  로컬 실행 선례는 2026-08-04 freelance 재학습).
- **engines:newspaper 가 search_gnews 배치 팬아웃 경로를 내부 재사용**
  (web/tool_newspaper.py) — 내부 함수 호출이면 무접촉, IBL 코드 문자열로 부르면
  이관 필요. 착수 시 grep 첫 순서.
- 액션 수준 별칭 인프라는 **없다**(param aliases 만 있음). 별칭 대신 "이관+즉시
  재학습"으로 공백기를 줄이는 쪽을 택했다. 구 이름 호출은 명시 오류("액션이
  없습니다" + available 목록)로 떨어지므로 에이전트는 자가교정 가능.
- 검색 5종의 desc 면책조항(서로를 지목)이 병합으로 자연 소멸 — desc 를 새로 쓸 때
  source 값 설명에 흡수.

**규모 감각**: 코퍼스 이관 ~130행(transform 은 `[sense:search_ddg]{` →
`[sense:search]{source: "ddg", ` 패턴 5벌 — 1단계 스크립트 본뜨면 됨).
교차 참조 grep 대상: 가이드(web_search.md·newspaper_guide.md 등)·12_ibl_only.md·
ibl.md·프롬프트 fragment·계기 app 블록(검색 액션에 app 블록이 있는지 확인).

---

## 4. (3)~(6) 잔여

- **(3) 코퍼스 교정**: 84 충돌쌍 중 병합으로 안 사라지는 것 = 동음이의·설계축
  쌍들의 오라벨. 애매 용례("게시판 목록 보여줘")를 문맥 있는 용례로 교체 +
  대조 용례 추가. (4) 재학습 직전에 1회.
- **(4) 재학습**: M4 로컬. 완료 후 rebuild_index + 연상 probe (구 이름 질의가
  신형으로 직행하는지). 실패 시 롤백 불요(모델 파일 교체 전 백업 관례).
- **(5) 압축 상설 기관**:
  - `--check` 에 **경고**(차단 아님) 2종: 신규 액션 desc 의 타 액션 면책 과다 /
    op Jaccard ≥ 0.8 쌍(★group 다르면 면제 — 정상 CRUD 오탐 방지).
  - 코퍼스 교차-액션 최근접(≥0.95) 감사는 **주간 감사**(`ibl_description_audit`
    의 run_maintenance_bundle 카덴스)에 합류 — 빌드는 코퍼스를 안 읽는 원칙.
- **(6) 설계 태스크로 분리 (기계적 병합 금지 판정)**:
  - screen/guestpc/android 몸 축 — guestpc 는 IBL 없는 얇은 몸(셸 봉투·limb key
    동의 모델). no-privileged-rails 재설계와 얽힘.
  - 스케줄 3형제(manage_events/schedule/trigger) — 캘린더/지연실행/트리거엔진
    3 서브시스템 경계 문제.
  - **슬라이드 어휘 일원화 (2026-08-05, 사용자 결정으로 확장 실행 — 154→152)**:
    engines:slide·engines:slide_shadcn 은퇴 → `[self:slide]{op:"create"}` 가 슬라이드
    생성의 유일한 어휘. **lecture_id 미지정 = 스크래치 덱 자동 등록**(aesthetic 별 1개,
    design_system=native_<톤> 으로 관통 — 코어 무수정) → 단발 생성도 편집·순서·내보내기·
    영상화 어휘가 그대로 이어짐. content(근거 원문) 파라미터를 create 에 승계(native=전용
    필드, HTML 경로=instruction 접합). 렌더러(slide_native·shadcn_slides)는 잔류,
    저작 전용층(slide_author·slide_patterns)은 고아화로 삭제. slides.md 재작성.
    style:"text" 단발 축은 은퇴(스크래치=native 고정 — 의식적 단순화, 텍스트형은 강의
    덱 layout 강제로 잔존). 코퍼스 8행+distilled 4건 이관, probe 0.943 직행.
  - **영상 어휘 일원화 (2026-08-05, 사용자 결정 — 152→150)**: "영상을 만드는 길은 강의 덱
    하나" — `[self:deck]{op:"video"}` 결정화(슬라이드 PNG+장별 speaker_note[생성 때 자동
    시드]→TTS→씬 길이 자동 맞춤→FFmpeg MP4, 기본 백그라운드+video_state.json[신문 선례],
    wait:true=동기. 라이브 실증: 2장 덱→h264+aac 49초 나레이션 영상). 동시에
    **engines:html_video·engines:remotion 은퇴** — html_video 는 슬라이드가 HTML 이던
    시절의 어휘(create_html_video 함수는 deck video 의 엔진으로 잔류), remotion 은
    실사용 저조 판정(remotion-video 패키지 → not_installed). 코퍼스 22행 삭제+deck video
    시드 4(직행 0.895), video_workflow.md 재작성·remotion.md 은퇴 포인터·guide_db 정리.
  - **슬라이드 가족 판정 (2026-08-05, 사용자 결정)**: self 3형제(lecture/slide/deck)는
    **병합 금지 — 개체 축 존치**. 워크스페이스/장/덱은 다른 개체라 business 가족(개체마다
    한 단어) 선례 그대로이며, 합치면 13-op 메가 액션(압축 목적과 반대). overlap 감사의
    deck↔slide 깃발은 오라벨이 아니라 정확히 라벨된 자연 근접("옮겨" vs "만들어") — 관리
    대상이지 수술 대상 아님. 가족의 잔여 검토 후보는 engines:slide_shadcn →
    engines:slide{style:"shadcn"} 흡수 하나(계수 숙성 후).
  - ~~book 군~~ → **2b 완료 (2026-08-05)**: search_books→`book{source:"google"}` 흡수
    (155→**154**. 계기 배선 비용은 과대평가였다 — 도서 계기·source 축이 이미 book 쪽에
    있어 글로벌 검색 탭의 액션 문자열 교체 하나로 끝. 구현=culture/tool_gbooks.py,
    코퍼스 7행 이관·probe 0.895 직행·재학습은 대기열로 충분).
    **classic 은 병합 금지 판정**: book=서지·대출 메타데이터 / classic=고전 *원문* —
    다른 통화를 내는 별개 개념이 "책"을 공유하는 동음이의(board/bulletin 부류).
  - 즐겨찾기 3벌 — 추상 favorite 신설은 결정화 원칙 위반(빈도가 어휘를 만든다).
    follow(사용 0 추정)는 계수 숙성 후 은퇴 판단.
  - **은퇴 후보 전반(D급)**: `action_usage_daily` 몇 주 숙성 후
    `action_usage_summary(30)` 로 판단. episode_log 만으로 은퇴 금지(정정 1).

---

## 5. 검증 커맨드 모음

```bash
# 어휘 빌드 + 전 가드
python3 scripts/build_ibl_nodes.py --check

# 사용 계수 확인 (숙성 확인)
python3 -c "import sys; sys.path.insert(0,'backend'); import boot_paths; \
from ibl_usage_db import action_usage_summary; \
[print(r) for r in action_usage_summary(30)[:20]]"

# 연상 probe
python3 -c "import sys; sys.path.insert(0,'backend'); import boot_paths; \
from ibl_usage_db import IBLUsageDB; db=IBLUsageDB(); db._load_model_sync(); \
[print(q,'->',[(r.ibl_code[:50],round(r.score,3)) for r in db.search_hybrid(q,top_k=2)]) \
 for q in ['한국어로 검색해줘','뉴스 검색','파일 찾아줘']]"

# 코퍼스 잔존 구어휘 (0이어야 함)
python3 -c "import sqlite3; c=sqlite3.connect('data/ibl_usage.db'); \
[print(p, c.execute('select count(*) from ibl_examples where ibl_code like ?',(p,)).fetchone()[0]) \
 for p in ['%fs_query%','%run_pipeline%','%image_critic%']]"
```
