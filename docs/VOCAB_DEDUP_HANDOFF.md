# 어휘 개념중복 감사·압축 핸드오프 (2026-08-05)

> 정본. 메모리 `vocab-dedup-2026-08` 이 여기를 가리킨다.
> 배경 명제: 정합성 가드(`--check`)는 *존재* 정합만 본다 — 두 액션이 각자 정합이면
> 같은 개념이어도 통과한다. 압축(개념 중복 제거)은 *의미 거리* 검사라 다른 기관이
> 필요하고, 그 기관은 이미 있다: 해마 임베딩. 이 작업은 "IBL 이 누적적 언어로
> 남으려면 증류가 성장보다 빨라야 한다"는 진단의 실행이다.

---

## ▶ START HERE — 현재 상태와 다음 단계

**완료 (0)(1) · 다음 = (2) 검색 통합.**

| 단계 | 상태 | 커밋 |
|---|---|---|
| (0) 사용 계수 배선 (은퇴 판단의 눈) | ✅ | `09cd5b8` |
| (1) 싼 병합 5건 (163→**159 액션**) | ✅ | `80a3392` |
| (2) 검색 통합 `[sense:search]{source}` | ⏳ 다음 세션 | — |
| (3) 코퍼스 교정 (동음이의 충돌쌍) | ⏳ | — |
| (4) M4 로컬 재학습 1회 + 연상 probe | ⏳ (2) 직후 권장 | — |
| (5) 압축 상설 기관 (--check 경고 + 주간 감사) | ⏳ | — |
| (6) 보류 3건 → 설계 태스크 | ⏳ | — |

백엔드 미기동 상태에서 작업했다 — **다음 Electron/backend 기동 때 새 어휘가 실린다**
(별도 재시작 절차 불요, 이미 커밋된 상태가 곧 라이브 코드).

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
- 자가점검(ibl_health_check)은 이 관문 밖 → 12시간 전수 순찰이 계수를 오염하지 않는다.

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
  - book 군(book/search_books/classic) — source 축 후보나 계기 배선 비용.
    (2) 성공 후 2b 로.
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
