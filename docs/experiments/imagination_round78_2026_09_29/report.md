# 상상 훈련 78회차 결과보고서 (2026-09-29) — 개인 기록·기억 회상

훈련 턴 · **무수정**(가이드 §4-3). 아래 갭 원장은 [before.json](before.json)·[baseline.json](baseline.json), 그리고 셸로 직접 읽은 코드와 읽기 전용 DB 대조만으로 썼다. 집행 완료 절은 비워 두었다.

★**개인정보(사용자 판정)**: 포식 기억·대화·심층기억·건강 기록은 읽기만 했다. 이 보고서와 before.json에는 원문을 싣지 않았고, 건수·키·날짜·길이·해시만 적었다. before.json은 저장 전에 `value`·`partial`·`partial_preview`·`partial_wire`·`diagnostic`을 모양(shape)으로 접었고, 저장 후 누출 스캔 결과는 0이다.

## 축 선정

- **축**: 행동 기준 미조합 메뉴의 개인 기억·기록 어휘다. 선언과 describe로 op·인자·반환을 확인했다.
  - 기억: `self:recent_chats`(작업 기억) · `memory`(심층) · `forage`(공간) · `folder_note`(detail만 — set은 74회차가 봤다)
  - 몸·건강·원장: `self:body`(몸 이력·궤적) · `health`(건강 원장) · `ledger`(스크래치 원장)
  - `self:record`(공동 업무)는 describe가 "사용 가능한 액션이 아닙니다"를 돌려준다(묶음 비활성). 공간을 만들려면 소유자 화면의 영속 설정이 필요해 제외했다.
- **도메인**: 활성 프로젝트(부동산·컨텐츠)의 최근 대화 회상, 부동산 프로젝트 폴더와 노트북·내 책의 장소 회상, "요즘 뭐 고쳤지"(몸 이력), 혈압 추세, 오늘 운동·혈압 기록과 정정·삭제(스크래치 원장), 회상과 외부 조회(도서관)의 결합.
- **77회차 단서** `self:forage`의 `notebook:<이름>` 몸 회상을 T11에서 봤다. 노트북 목록과 포식 기억을 대조한 것이다.
- **축 선정 관문 질문**("기계로 열거 가능한가")
  - 기억 저장소의 주인·장소 이름·상태 칸이 어떻게 번역되는지는 실제로 불러 봐야 드러난다. 그래서 훈련 축이다.
  - 다만 발견 중 셋은 열거 가능하므로 census로 넘긴다: B78-1(봉투 truncated scope), B78-2(읽기의 get_or_create), B78-8(문자열 봉투 성공 판정).
- **닫힌 밭**: 절단 표지는 표지 **누락**이 아니라 **거짓 분류**(B78-1)만 적었다. 누락(memory 대화 미리보기 무표지)은 재확인으로만 적었다.
- **탐침**: `agent_id:"IT78_probe"`·`task_id:"IT78_task"`. 모든 요청이 `edition:2`·`project_id:"컨텐츠"`·`origin:"training"`이다.
- **쓰기 원칙**
  - 건강·기억·대화·포식 원장에는 쓰지 않았다. 건강 save·delete는 check만 했다.
  - 건강 오타 주체 재현(T21)은 `VACUUM`으로 뜬 **스크래치 사본 DB**에서만 돌렸다.
  - 기록·정정·삭제는 `projects/컨텐츠/outputs/IT78_건강원장.json`(ledger)에만 했다.

## 지표 스냅샷 (훈련 전)

행동 미조합 140/168 · 파이프 길이 중앙값 3 · 문형 4(조회 26·축적 8·적용 6·조건 2) · 파트너 다양성 중앙값 2. 77회차와 같다. 원본은 [metrics.json](metrics.json)이다. 지표는 몸의 현황이며, 훈련 실측은 증류에 담기지 않는다(§6). 단, 지표가 말하는 "훈련 도달 가능 139"는 과대 계산이다(F78-4).

## 과제 표

원문·판정식: [probe.py](probe.py) · 응답(마스킹): [before.json](before.json) · 기준선과 회차 후 diff: [baseline.json](baseline.json).

**24과제 중 기계 판정 12통과 · 12실패.** 결함 8부류 · 마찰 5부류.

탐색 중 훈련자 문장 잘못은 결함 판정에서 뺐다. 거절 안내가 모두 방향을 정확히 줬다.
- 내장 함수 인자 안 파이프 `unique($x >> each)`·`len($x >> filter)`(PURE_EXPRESSION, 4회)
- Record 봉투를 `.items` 없이 select에 넘김(TYPE "레코드 봉투의 행 목록은 .items로")
- 레코드 필드 안 `[if]` 블록(작성 전 교재로 교정)
- 두 낱말 대조를 위해 고른 낱말 쌍이 실제로는 같은 행에 없던 것(T05 1차 — DB 대조로 교정)

| # | 상상 의도 | 결과 | 분류 |
| --- | --- | --- | --- |
| T01 | 지난주 부동산 에이전트와 한 얘기 — 최근 30건 중 이번 주 것 날짜·방향·길이 표 | **실패** `PARTIAL_SOURCE`(truncations `[{scope:"unknown"}]`) — 300자 미리보기 절단이 원천 불완전으로 분류됨 | 결함 B78-1 |
| T02 | 같은 요구를 try/catch `$error.partial`로 | 30행 중 이번 주 6행(09-26~09-28), 절단 3행(최대 1,499자), `source_complete:false`. items는 title·meta·summary·url만, 원 행 `.data`에 구조 칸 | 꼬임(B78-1 우회) |
| T03 | "지난 7일 중 전세 얘기만" — `days:7, query:"전세"` | 결과 id가 **인자 없을 때와 동일**(20행). 미선언 `agent:"user"`는 작동(결과 달라짐). check `incomplete`·경고 0 | 꼬임(F78-2) |
| T04 | '부동산' 기억 검색 → 출처·화자·날짜 표, 날짜 역순 | 5행(전부 대화, provenance.recorded_at으로 정렬), `clamped` 정직 신고. 미리보기 200자 무표지 | 깨끗(B72-3 재확인) |
| T05 | 기억 검색 정직성 — 없는 말 / 두 낱말 | 없는 말 0 ✓. "AI 블로그" **0** — "AI" 5·"블로그" 5, DB 대조로 두 낱말이 한 행에 함께 있는 행 15개·붙은 구 0 | 결함 B78-3 |
| T06 | 처음 보는 에이전트가 기억 지도·검색 | success, 지도 가지 1·기억 0 — 그 전에 탐색 search가 `projects/컨텐츠/memory_IT78_probe.db`를 **만들었다**(01:49) | 결함 B78-2 |
| T07 | 시스템 AI memory search 대화 가지가 읽는 DB(읽기 전용 코드 경로 대조) | `_search_conversations(data/)` → **0건**, `system_ai_memory.db` conversations LIKE '부동산' → **185건**, `data/conversations.db` messages 0 | 결함 B78-3 |
| T08 | 부동산 프로젝트 폴더는 뭐 하던 곳이었지 — 단언 종류·own/inherit·신선도 | 20행(identity 1·convention 11·dead_branch 4·substrate 4, own 2·inherit 18), 문서 있음 | 깨끗 |
| T09 | 오타 폴더(`…/projects/부동삼`) 회상 | success **19행 전부 inherit**, own 0, `root_missing:false`, `doc`=조상 문서 | 꼬임(F78-1) |
| T10 | '외장하드 영화' query → places 상위 3 → locus로 다시 열기 | 장소 5, 열린 수 9·11·1(모두 경로 장소) | 깨끗 |
| T11 | 지금 있는 노트북 vs 포식 기억의 노트북 몸 | 노트북 3 · 포식 몸 5 → 고아 2(4·3행) — freshness 표식 0, `root_missing:false` | 결함 B78-4 |
| T12 | "내 책 하네스에 대해 기억하는 것" query → book 장소 → locus | book 장소 **2개**(같은 책), `<…>` 괄호 장소를 locus로 열면 **0행** | 결함 B78-5 |
| T13 | 포식 기억의 내 책 이름으로 도서관 검색 | 괄호 이름 → `sense:book` **"XML 파싱 실패: not well-formed"** | 결함 B78-5·B78-6 |
| T14 | 요즘 뭐 고쳤지 — 이번 주 커밋 중 '수리' 최근 5 | 138커밋 중 41, 상위 5(1b9a4932 등) | 깨끗 |
| T15 | 최근 3일 파일 변화 영역별 + 미커밋 수 | 953행(data/packages 161·backend/ibl 117…), 미커밋 8 | 깨끗 |
| T16 | 가이드 파일의 일생 + 없는 경로 | 14사건(08-16~09-15). 없는 경로는 0행 + "git 이력 없음 — 경로 확인" | 깨끗 |
| T17 | 방금 내가 돌린 것들 — task_id 궤적 | 143사건(started 53·finished 52·checkpoint 38) **source 전부 `usage`**. DB의 IT70~78 궤적 3,086 전부 usage | 결함 B78-7 |
| T18 | 지난 1년 혈압 추세(건수만) | 측정 점 5, 표 3열. 봉투에 **items 없음**(선언은 "items 통화") | 깨끗(F78-3 단서) |
| T19 | 코퍼스 3683 — 혈압 조회 → 차트 | success, PNG 1(눈으로 확인: 수축기·이완기 두 선·날짜축 정상, 회차 끝에 삭제) | 깨끗 |
| T20 | 오늘 혈압 128/85 기록(check만) — 가이드 평탄형 vs value형 | `systolic`·`diastolic` 최상위형 **UNKNOWN_ARGUMENT**. `value:"128/85"` incomplete. delete incomplete. effects 모두 `unknown` | 마찰(F78-3·B75-4) |
| T21 | 건강 · 오타 person 조회(**사본 DB**) | persons 6→**7**(새 행에 uuid·updated_at — 폰 동기화 대상), 응답 "…최근 365일간 혈압 기록이 없습니다" success | 결함 B78-2 |
| T22 | 스크래치 원장 — 운동·혈압 5행 append(enum 관문) → 혈압 추세·운동 합계 | 5행, 혈압 3행 날짜 역순, 운동 75분 | 깨끗 |
| T23 | 잘못 적은 수축기 정정(upsert) + 중복 운동 행 삭제 | 정정 ✓. 삭제 = select → filter → `set target` 3호출(5→4) | 꼬임(F78-5) |
| T24 | 코퍼스 check — 278형 `{}`·3823 파이프·forage 2800 `layer`·2799 `table` | 278형 **실행 실패** PARTIAL_SOURCE · 3823 TYPE · 2800·2799 incomplete, 경고 0 | check(B78-1·F78-3) |

튼튼했던 것:
- 몸 이력 네 op(log·changes·file·writes)와 절단 표지(`truncations.scope: selection`)
- 포식 기억 locus 회상과 query→places→locus 2단계(경로 장소)
- 건강 측정 점 정렬·차트
- ledger append의 enum 관문·select·upsert
- 없는 파일 경로의 정직 문구, memory category 거절, 대화 상한 clamp 신고

실패는 두 자리에서 났다.
1. **상태 칸을 몸이 잘못 번역하는 자리**: 표시 절단 → 원천 실패, 문자열 실패 봉투 → 성공 기록, 리허설 → 실사용
2. **기억 저장소의 주인·장소 이름이 정규화되지 않은 자리**: 새 agent·오타 person이 새 주인이 되고, 괄호 책 이름·지운 노트북이 남는다

## 갭의 원장

### B78-1 ★ `self:recent_chats`가 판본 2에서 **사실상 항상 실패**한다 — 미리보기 절단이 `PARTIAL_SOURCE`로 분류된다 (★밭 이관: B76-4와 같은 속, 두 번째)

- **요약**
  - `backend/drivers/sqlite_driver.py`는 본문을 300자로 미리보기한다. 한 행이라도 넘으면 **봉투**에 `truncated:true`를 싣는다(553·611·647행). `truncations`에는 scope가 없다.
  - 판본 2 어댑터는 scope가 `selection`이 아닌 절단을 모두 원천 불완전으로 올린다(`backend/ibl/ibl_v2_adapters.py` 188~190행).
  - 행 수는 온전하고 셀 미리보기만 잘렸는데 액션 전체가 실패한다. 최근 10건 안에 300자 넘는 대화가 없는 경우는 드물다.
- **최소 재현**: `return [self:recent_chats]{project_id:"부동산", limit:1}` → `success:false`, `diagnostic.code:"PARTIAL_SOURCE"`, `details.truncation.truncations:[{scope:"unknown"}]`
- **실측**
  - T01·T24: 코퍼스 `return [self:recent_chats]{}`(278·789·1219·1787·1833) 형이 실행에서 실패했다.
  - 우회 T02: `[try] {…} [catch] { $c = $error.partial }`는 동작한다. `source_complete:false`가 남는다.
- **보이지 않는 이유**
  - 자가점검 fixture(`__self_check__`)는 **판본 1**로 돈다. 궤적 `edition:1`이며 매일 success다.
  - 건강 원장에는 이번 회차 10호출이 전부 success=1로 기록됐다. 만성 실패 경보가 울릴 수 없다.
- **대조**: 표지를 **달지 않는** 형제는 통과한다. memory search 대화 미리보기가 200자 무표지다(B72-3 재확인). 정직한 생산자가 벌받는 구조다.
- **제안(수리성, ★밭 이관 — 다음 수리 턴 항목)**
  1. 셀·행 미리보기 절단은 행 표지(`truncated`·`content_len`)만 두고, 봉투 표지는 `truncations:[{scope:"preview", unit:"chars", …}]`처럼 원천 완전성과 분리한다. 어댑터는 preview scope를 PARTIAL로 보지 않는다.
  2. 관문 C(절단 표지)에 불변식 둘을 더한다: "봉투 `truncated`는 scope 필수", "scope 없는 truncated 생산자 0"(생산자 AST census — `substr(…,1,N)`·"…(잘림" 패턴).
  - B76-4(`compact_price_series`의 거짓 표지)와 같은 속이다. 표지 **누락**이 아니라 표지 **오분류**다.
  - 가드: 300자 넘는 행을 가진 대화 fixture → 판본 2 success·`source_complete:true`·행 표지 보존.

### B78-2 읽기가 **주인을 만든다** — 새 agent_id는 새 기억 저장소를, 오타 person은 새 건강 주체를 (★B72-5 속 세 번째 — 이관된 census가 미집행)

- **요약**
  - `self:memory`: `memory_db._get_db_path`(289~321행)는 처음 보는 agent_id마다 `projects/<p>/memory_<id>.db`를 짓는다. `_ensure_schema`(324행~)가 읽기 경로에서 파일과 표를 만든다. 09-02 수리는 빈 agent_id(`memory_None`)만 막았다.
  - `self:health`: `get_person_id → get_or_create_person`(`health_storage.py` 229~263행)이 조회에서도 persons 행을 INSERT한다. uuid·updated_at가 붙어 폰 동기화 대상이다.
  - 두 경우 모두 응답은 "기억/기록이 없습니다" success다. **틀린 주인**과 **기록 없음**을 구별할 수 없다.
- **최소 재현**
  - `[self:memory]{op:"search", query:"부동산"}`(agent_id: 처음 보는 이름) → `memory_<그 이름>.db` 생성
  - `[self:health]{op:"query", query_type:"혈압", person:"<오타 이름>"}`(사본 DB) → persons +1
- **실측**
  - T06: `memory_IT78_probe.db`(표 memories·_meta, 0행)가 생겼다. 회차 끝에 삭제했다.
  - 이미 실물로 있다: `projects/정보센터`·`projects/하드웨어`의 `memory___self_check__.db`, `projects/컨텐츠/memory_system_ai.db`(0행 — 시스템 AI 기억 정본은 `data/system_ai_state/`).
  - T21: 사본에서 persons 6→7, 응답 "IT78_오타사람의 최근 365일간 혈압 기록이 없습니다."(`success:true`)
- **수리가 샌 경위**
  - B72-5(finance "없는 주체 조회가 owners에 행 삽입")는 1b9a4932에서 `finance_storage._owner_clause`(223행)만 고쳤다. 그 함수의 docstring은 "건강 person 축과 동일 의미"라고 적는데, 형제인 건강 쪽은 그대로다.
  - B74-2 때 이미 "읽기 op의 쓰기 → 밭 이관(census+관문)"을 적었지만 census는 아직 없다.
- **제안(수리성, ★다음 수리 턴 첫 항목)**
  1. 읽기 op(선언 `side_effect:false`)에서 도달하는 `get_or_create*`·INSERT·`sqlite3.connect`(새 파일)·`mkdir`를 AST로 census하는 관문을 세운다.
  2. 읽기는 `lookup`(없으면 `unknown_owner` 정직 응답 — 후보 이름 동반)으로, 생성은 쓰기 op에서만 한다.
  3. 기존 유령 저장소 3개는 빈 DB 확인 뒤 정리한다(빈 파일 삭제 — 판정 요청 1과 함께).
  - 가드: 없는 agent·person 읽기 → 파일·행 수 불변 + 명시 응답.

### B78-3 `self:memory` search의 대화 가지 — 시스템 AI는 **자기 대화를 못 보고**, 프로젝트는 **붙은 구만** 찾는다

- **요약**: `memory/handler.py` `_search_conversations`(259~297행)의 문제는 셋이다.
  1. `os.path.join(project_path, "conversations.db")` 고정이다. 시스템 AI(`project_path=data/`)는 빈 `data/conversations.db`를 읽는다. 시스템 AI 대화는 옆의 `system_ai_memory.db:conversations`에 있다. recent_chats는 08-18에 같은 함정을 고쳤는데("*못 봄*을 *없음*으로" 주석, `sqlite_driver.py` 522~526행) 형제 경로에 닿지 않았다.
  2. `WHERE content LIKE '%질의%'` — 질의 전체를 붙은 구로만 찾는다. 선언은 "키워드·자연어 검색(FTS+시맨틱 통합)"인데 그건 심층기억 가지에만 참이다.
  3. `except Exception: return []` — DB 오류가 "0건"이 된다.
- **최소 재현**
  - (코드 경로) `_search_conversations("<repo>/data", "부동산")` → 0
  - (실행) `[self:memory]{op:"search", query:"AI 블로그"}` → 0
- **실측**
  - T07: 0건 vs `system_ai_memory.db` conversations LIKE → **185건**
  - T05: "AI" 5·"블로그" 5, "AI 블로그" 0. DB 대조로 두 낱말이 한 행에 함께 있는 행 15개·붙은 구 0
- **제안(수리성)**
  1. 대화 DB 해소를 recent_chats와 한 함수로 합친다(시스템 AI 분기 포함).
  2. 대화 가지도 낱말 AND(또는 FTS)로 찾는다.
  3. 예외는 `source_complete:false`·오류로 올린다.
  4. 미리보기 절단은 B78-1의 행 표지 규약을 따른다.
  - 가드: 시스템 AI 대화 fixture 검색 ≥1, 두 낱말 비인접 fixture ≥1, 잠긴 DB → 오류.

### B78-4 지운 노트북의 포식 기억이 **신선한 것처럼 남는다**

- **요약**
  - `notebook_core.delete_notebook`은 소스·색인만 지운다. 포식 문서 `data/forage_surveys/notebook_<이름>/`와 `forage_map` 행은 남는다.
  - `forage_doc.reconcile`(724~727행)은 `_is_path` 노드만 대조하므로 `notebook:`·`book:` 몸은 영원히 대조되지 않는다.
  - recall은 그 기억을 `freshness:""`·`root_missing:false`로 준다. `root_missing`은 경로 마커일 때만 계산된다(`forage_memory.py` 680~687행).
- **최소 재현**: `[self:notebook]{op:"list"}`(3개) vs `[self:forage]{op:"recall", locus:"notebook:<지운 노트북>"}` → 4행 success, 표식 0
- **실측**(T11): 노트북 몸 5개 중 2개가 고아다 — 4행(09-19)·3행(09-04, 이름으로 보아 과거 스크래치).
- **훈련 위생 함의**: 노트북 create·add는 "시스템 AI에 포식 기억 조사가 자동 위임"된다(선언, 10분 디바운스). 스크래치 노트북을 만들고 지워도 **기억은 남는다**. 가이드 §3-5 스크래치 원칙이 이 뒷문을 모른다.
- **제안(수리성 — 기존 기억 처분은 판정 요청 1)**
  1. notebook delete가 그 몸의 포식 문서를 `_gone`으로 접는다(reconcile과 같은 1주 유예).
  2. reconcile에 자체 주소 공간 몸의 존재 확인기(노트북 = notebooks 표)를 등록한다.
  3. recall의 `root_missing`을 몸별 존재 확인으로 일반화한다.
  - 가드: create → survey 행 → delete → recall이 `root_missing:true` 또는 `_gone`.

### B78-5 `book:` 몸이 **정규화 밖**이다 — 자리표 괄호를 베낀 이름, 한 책의 두 몸, 열리지 않는 장소

- **요약**
  - 증류 프롬프트가 `"book:<제목>"`(`cognitive_distill.py` 538·563행)을 가르치고, `_normalize_space`는 "라벨 그대로"(143행)다. 그래서 `<>`가 문자 그대로 몸 이름이 된다.
  - 09-18 몸 표기 통일(`canonical_body`, `forage_memory.py` 227~240행)은 `book:`·`notebook:`을 "제 이름을 지킨다"며 면제했다.
  - 입구 관문 `locus_is_address`(206~217행)도 자체 주소 공간 몸이면 locus를 보지 않고 통과시킨다. 그래서 책 몸 행들의 locus가 **주제 이름**(자리표: `<전체>`·`<첨부 이미지>` 꼴)으로 저장됐다.
  - 결과: query가 `places`로 준 장소를 가이드대로 locus로 다시 부르면 0행이다.
- **최소 재현**: `[self:forage]{op:"recall", query:"하네스 책"}` → places에 `book:<하네스: …>`·`book:하네스` 둘 → 앞의 것을 `locus`로 → `map_count:0`(doc은 찾음)
- **실측**(T12·셀 대조)
  - book 몸 5개 중 3개가 괄호 이름이다.
  - 같은 책(사용자의 저서)이 `book:하네스`(2행)와 `book:<하네스: AI 시대의 새로운 몸>`(1행)으로 갈렸다.
  - 몸 4/5(행 11/13)는 locus가 몸 이름 접두가 아니라서 장소 지명으로 열 수 없다.
  - 책이 아닌 개인 서류 이미지가 book 몸으로 기록된 곳이 1(2행)이다. 분류 경계 문제이며 원문은 적지 않았다.
  - 하류 T13: 괄호 이름에서 `book:`만 떼어 도서 검색 → B78-6로 실패했다.
- **제안(수리성 — 기존 행 병합·개명은 판정 요청 1)**
  1. 몸 라벨 정규화를 책·노트북에도 적용한다: 자리표 괄호 제거, 공백·구두점 정규형, 별칭(짧은 제목) 병합 규칙.
  2. own-space 몸의 locus는 `<몸>` 또는 `<몸>/<하위>`만 허용한다. 주제 이름은 거절한다(09-18 관문의 own-space 구멍 막기).
  3. 증류 프롬프트의 자리표를 형태 기호가 아닌 예시(`book:하네스`)로 바꾼다(pitfall "경량 모델은 형태 자리표를 베낀다").
  - 가드: `places`의 모든 장소 → locus 재호출 map_count ≥1.

### B78-6 `sense:book`(정보나루) 제목에 `<`·`&`가 있으면 **"XML 파싱 실패"**다

- **최소 재현**: `[sense:book]{title:"R&D 전략", rows:3}` → TOOL "XML 파싱 실패: not well-formed (invalid token): line 1, column 83"
- **격리**
  - `"<하네스>"` → "mismatched tag"
  - `"하네스: AI 시대의 새로운 몸"` → 0건(콜론은 파싱 문제 아님)
  - `"하네스"` → 5건
  - `&`만으로도 죽는다.
- **추정 원인**: 원 응답은 확인하지 못했다(독립 프로세스에서 키 미로딩). 원천이 요청 파라미터를 XML에 이스케이프 없이 되돌리는 것으로 보인다(`tool_library.parse_xml_response`, 54·69행).
- **제안(수리성)**
  1. 정보나루의 JSON 응답 형식(`format=json`)으로 전환한다. 또는 파싱 전에 요청 에코 구간을 정화한다.
  2. 실패 시 원천 문제(`error_type:"source_parse"`)와 입력을 구분해 싣는다.
  - 가드: `&`·`<` 포함 제목 fixture → 성공 또는 정직한 0건.

### B78-7 리허설 격리가 **`trajectory_event`에 닿지 않는다**

- **요약**: `origin:"training"`은 action_health의 `source`만 바꾼다. 실행 궤적(`world_pulse.db:trajectory_event`)은 훈련 실행도 `source:"usage"`로 적는다.
- **실측**(T17)
  - IT78 궤적 143사건이 전부 usage다.
  - DB 전체의 IT70~78 task 궤적 **3,086사건**도 전부 usage다. 09-20 이후 전체 56,853사건 중 usage 외의 값이 없어 칸 자체가 죽어 있다.
- **영향**
  - 조합 지표 스크립트가 예고한 "편향 없는 모집단 = trajectory_event.ibl.started"로 옮기는 순간, 훈련의 의도된 실패와 조합이 몸의 성적표에 섞인다(§6 "리허설은 삶이 아니다" 위반).
  - `[self:body]{op:"trajectory"}`의 "최근 실사용 episode" 기본값도 리허설을 가르지 못한다.
- **제안(수리성)**: 궤적 기록기가 요청 origin을 `source`에 싣는다(action_health와 한 판정기). 소비자(지표·body trajectory 기본값·증류)가 `training`을 뺀다.
  - 가드: `origin:"training"` 실행 → 궤적 source=training.

### B78-8 자기 상태 기억(action_health)이 **문자열 봉투의 실패를 성공으로** 적는다

- **요약**
  - `ibl_engine.py` 958~966행의 성공 판정은 `isinstance(result, dict)`일 때만 `success`/`error`를 읽는다.
  - 패키지 핸들러 다수는 `json.dumps(...)` 문자열을 돌려준다(books·memory·health…). 그 실패는 `_action_success=True`로 남는다.
  - 같은 자리의 `classify_currency`는 모양을 `"error"`로 정확히 분류한다. 한 행 안에서 shape는 error, success는 1이다.
- **최소 재현**: `[self:memory]{op:"search", query:""}` → 판본 2 `$error.code:"TOOL"` "query가 필요합니다." → action_health `success=1, shape="error"`(id 244551)
- **실측**
  - 이번 회차 `sense:book` TOOL 실패 3건이 모두 success=1(error 칸 비어 있음)로 기록됐다.
  - 전수: 08-29 이후 shape="error" 실사용 1,508행 중 **769행(51%)**이 success=1이다. 53액션(self:script 387·sense:crawl 148·self:struct 31·self:ledger 25·limbs:browser 25 …)에 걸쳐 있다. (보고서 저장 전 같은 질의를 다시 돌려 success=1 770행·success=0 740행을 확인했다 — 회차 뒤 1행 증가.)
- **영향**: 만성 실패 경보·X-Ray 성공률·구성요소 생명주기 생존 신호·실패 패턴 분석이 이 절반을 못 본다. 몸이 자기 삶을 잘못 읽는다(B18-1과 반대 방향).
- **제안(수리성, census)**: 엔진 경계의 성공 판정을 `classify_currency` 결과와 한 벌로 합친다(문자열 JSON도 파싱). "shape=error ⇒ success=0" 불변식 관문을 세우고, 기존 행은 재분류 보고만 한다.
  - 가드: 문자열 실패 봉투 fixture → success=0·error 채움.

### F78-1 장소 회상의 정직성 — 없는(오타) 폴더가 조상의 기억을 제 것처럼 받는다

- T09: `locus:"…/projects/부동삼"` → success 19행(전부 `via:"inherit"`), `root_missing:false`, `doc`=`…/Desktop/AI/memory.md`(조상)
- "이 폴더 뭐였지"에 대한 정직한 답("그 장소 기억 없음·경로 없음")을 말하는 칸이 없다. 프로그램은 `all(via=="inherit")`로만 추론할 수 있다.
- 제안(수리성): 봉투에 `locus_exists`(몸별 확인)·`own_count`·`doc_is_ancestor`를 싣고, 교재에 "own 0이면 없음"을 적는다. B78-4의 몸별 존재 확인기와 한 스윕이다.

### F78-2 `open_params` 액션 22개는 인자 계약 밖이다 — recent_chats의 필터 인자가 침묵 속에 무시된다

- T03: `days:7`·`query:"전세"`·`since`를 주면 결과 id가 **인자 없을 때와 같다**. 미선언 `agent:"user"`는 드라이버가 읽어서 작동한다. check `incomplete`·경고 0이다.
- 전수(describe 168): open_params 22개
  - sense: `world`·`self_check`
  - self: `recent_chats`·`switch`·`goal`·`workflow`·`output`·`download`·`package`·`install_lib`
  - limbs: `os_open`·`open_window`
  - others: `delegate`·`ask`·`agents`·`publish`·`feed`·`nostr`·`board`·`follow`
  - table: `each`·`reduce`
- B77-1(원천별 인자 침묵 무시) 가족의 재확인이다. 새 차원은 **선언이 비면 check도 볼 수 없다**는 것이다.
- 제안(수리성): recent_chats 선언에 실제 인자(`limit`·`agent`·`project_id`)를 적어 닫힌 계약으로 만든다. 22개 census 뒤 의도적 개방(`each`·`reduce`·`delegate` 류)만 `open_params` 사유를 선언한다.

### F78-3 교재 드리프트 — 기억·건강 표면

- `health.md`·target_description: "`systolic`/`diastolic` 필드"(최상위 평탄형) → 판본 2 `UNKNOWN_ARGUMENT`(T20). 유효한 것은 `value:"128/85"`와 `value:{systolic,diastolic}`(코퍼스 10건의 형)뿐이다.
- health 선언 "query 결과는 items 통화": 측정 조회는 `{text,count,table,blocks,points,series_label}`이고 items가 없다(T18). 차트 파이프는 table로 동작한다(T19).
- forage 선언 "items 통화 밖이라 table 파이프 대상 아님(판정 2026-08-17)": 판본 2에서는 `$f.map >> [table:groupby]`가 잘 된다(T08). 판본 1 시절 판정 문구가 교재로 남았다.
- forage 코퍼스 2800 `layer:"map"`(은퇴한 주인모델 층 인자)·2799 `table:"forage_map"`: 계약 params에 `layer`·`table`이 남아 check 경고 0이다. `data/retired_contracts.yaml` 등록 대상이다.
- 코퍼스 3823 `[self:recent_chats] >> [table:take]`: TYPE(봉투 `.items`). 용례 재검토 대상이다.

### F78-4 조합 지표의 "훈련 도달 가능"이 비활성 묶음을 모른다

- `--list-never`는 "훈련 도달 가능 139(프롬프트 비노출 1건 제외: engines:newspaper)"라고 셈한다.
- describe로는 **14액션**이 "사용 가능한 액션이 아닙니다"다: `self:record`·`limbs:phone`·`engines:arch_*` 10·`engines:newspaper`·`engines:remotion`.
- 이번 축 메뉴의 `self:record`는 도달할 수 없었다.
- 제안(수리성): 지표가 활성 어휘(`/ibl/capabilities` 또는 describe) 기준으로 도달 가능을 셈한다.

### F78-5 스크래치 원장의 행 삭제는 3호출 꼬임이고, ledger 쓰기는 몸의 쓰기 원장에 없다

- T23: 행 삭제 = `select` → `table:filter` → `set target`. 두 호출 사이의 다른 쓰기는 잃는다(읽기부터 저장까지의 직렬화는 한 호출 안에서만).
- `self:ledger`의 원자 쓰기(`ledger_ops._atomic_json`)는 `data/write_ledger.jsonl`에 남지 않는다. `[self:body]{op:"writes"}`에서 이번 회차 원장 쓰기가 0건이다. 가이드가 "부분 기록"을 광고하는 범위이지만, 관문을 가진 1급 쓰기 어휘다.
- 제안(수리성): ledger 쓰기를 write ledger에 기록한다(행위자·task·origin). 행 삭제 op는 어휘 증식이므로 제안하지 않는다(V 후보로만 적는다: 조건 삭제가 반복되면 현실이 인준).

## 재확인 (앞 회차 갭·수리의 증거 — 새 항목 아님)

- **1b9a4932가 이 축에서 샌 자리**: B72-5 수리가 finance에만 닿았다 → B78-2(health·memory). 그 밖의 수리(ledger 원자 쓰기·chart 열 선택·몸 이력 절단 표지)는 살아 있다.
- **B72-3**(무표지 절단, 닫힌 밭 — 증거만): memory search 대화 미리보기 200자에 `truncated`·`content_len`이 없다(T04 길이 전부 200). B78-1과 정반대 쪽이다.
- **F77-1**(meta 접기): recent_chats items는 시각을 `meta`, 방향을 `title`("부동산 → user") 문자열에만 담는다. 원 행 `.data`에는 `message_time`·`from_agent`·`content_len`이 있다. memory items도 `meta:"<날짜> · 대화"`지만 `provenance.recorded_at`이 있어 T04는 구조 칸으로 됐다.
- **F76-2**(UNOBSERVED_FIELD 거짓 경고): forage locus 모드의 `root_missing`·`doc`·`map_count`·`docs_below`가 전부 경고를 받는다. 관측 반환이 query 모드 한 모양뿐이다(op·모드 축 부재).
- **B75-4**(액션별 사전 판정 부재): health save·delete, ledger, forage, memory 모두 check effects가 `unknown`이다.
- **B74-4**(folder_note): detail은 주석 0건을 정직하게 준다. 새 결함 없음.

## 시드 후보 (실행 검증 통과만 — 자동 등록 안 함)

- T04(memory search → compute provenance.recorded_at/speaker → sort)
- T08(forage locus → groupby kind·via)
- T10(forage query → places take → each locus 재회상)
- T14(body log → filter 요지 → sort → select take)
- T15(body changes → groupby 영역 + 미커밋 filter)
- T16(body file 일생 + 없는 경로 try)
- T18(health 측정 points → sort → each number)
- T19(health query → table:chart)
- T22(ledger append enum_fields → select where → sort·sum)

문장 안의 경로·프로젝트·질의어는 자리표로 바꿔 심을 것(개인 장소·주제 이름 금지 — 포식 기억은 개인정보).

**빼는 것**:
- T01·T02·T24: B78-1 전·우회
- T03: F78-2
- T05·T06·T07·T21: 결함
- T09: F78-1
- T11·T12·T13: B78-4·5·6
- T17: B78-7
- T20: check만
- T23: F78-5 꼬임
- 코퍼스 278·789·1219·1787·1833(recent_chats `{}` — B78-1 수리 전 판본 2 실패)·3823·2799·2800은 용례 재검토 대상이다.

## 판정 요청 (언어 개정·파괴적 변경 2종만)

1. **이미 쌓인 고아·갈린 포식 기억의 처분(파괴적 변경)** — B78-4·B78-5의 앞으로의 탄생 차단(notebook delete 연동·몸 라벨 정규화·own-space locus 관문)은 수리성이라 묻지 않는다. 다만 **기존 기억 데이터를 지우거나 합치는 일**이 걸린다.
   - 대상
     - (가) 지운 노트북 몸 2개·7행과 그 문서
     - (나) 같은 책의 두 몸 병합, 괄호 몸 3개 개명
     - (다) 주제 이름 locus 행 11개
     - (라) 읽기가 만든 빈 기억 DB 3개(`memory___self_check__.db` ×2·컨텐츠 `memory_system_ai.db`)
   - 선택지
     - (a) reconcile 확장으로 `_gone` 접기 → 1주 뒤 삭제(기존 정책 연장), 책 몸은 정규 이름으로 병합
     - (b) 삭제 없이 stale 표식만 달고 보존, 병합은 새 쓰기부터
     - (c) 목록만 보고하고 사람이 판·편집기에서 처리
   - 근거: 포식 기억은 개인정보이고 정본이 문서다. 병합·삭제는 되돌리기 어렵다. 고아 기억은 지금 recall에서 신선하게 나온다.

B78-1~8·F78-1~5는 모두 수리성이다.
- B78-1: 어댑터가 preview scope를 받아들이면 기존 문장은 실패에서 성공으로만 바뀐다(비파괴).
- B78-8: 과거 행 재분류 없이 앞으로의 기록만 고친다.

**다음 수리 턴의 첫 항목(밭 이관)**:
1. B78-2(+B72-5·B74-2) — 읽기 op의 생성·쓰기 AST census → 관문. 세 번째 발견이라 더 미룰 수 없다.
2. B78-1(+B76-4) — 봉투 `truncated` scope 필수 불변식 + 생산자 census.
3. B78-8 — 엔진 성공 판정과 `classify_currency` 한 벌 + "shape=error ⇒ success=0" 관문.

## 72~78회차 공통 뿌리에 78회차가 더하는 것 (훈련자 관찰)

- 77회차가 더한 "원천의 결과 없음·한도 초과가 몸의 실패 분류로 정직하게 번역되지 않는다"가 **몸 안쪽**에서도 난다. 세 가지다.
  - 표시 미리보기 절단이 원천 실패로 번역된다(B78-1).
  - 문자열 실패 봉투가 성공으로 번역된다(B78-8).
  - 리허설이 실사용으로 번역된다(B78-7).
  - 셋 다 **상태 칸의 번역기가 한 벌이 아니다**. 한쪽 판정기(`classify_currency`·origin)는 맞게 알고 있는데 옆 기록기는 다른 규칙으로 적는다.
- 뿌리 2(**선언·교재와 실제 동작의 어긋남을 대조하는 관문이 없다**)에 기억 표면이 붙는다.
  - 선언 "자연어 검색"과 실제 붙은 구 LIKE(B78-3)
  - 선언 "items 통화"와 실제 측정 봉투(F78-3)
  - 판본 1 판정 문구의 교재 잔존(F78-3)
  - 선언이 비면 check도 볼 수 없다(F78-2)
- 새 부류 하나: **기억 저장소의 열쇠(주인·장소 이름)가 입구에서 정규화·검증되지 않는다**.
  - 새 agent·오타 person이 새 주인이 된다(B78-2).
  - 자리표 괄호가 몸 이름이 된다(B78-5).
  - 지운 노트북이 살아 있는 장소로 남는다(B78-4).
  - 09-18 포식 기억 감사가 경로 몸에 세운 "주소가 곧 열쇠" 관문을 책·노트북·심층기억 주인·건강 주체에도 세우는 것이 한 처방이다.
- 수리의 누출은 매번 **형제 경로**에서 났다: finance→health, recent_chats→memory 대화 가지, 경로 몸→book 몸. 수리 턴이 "같은 함수 이름·같은 주석을 가진 형제"를 grep하는 것보다 관문(census)을 먼저 세우는 편이 맞다(pitfall hand-picked-sweep-leaks).

## 위생

- **기준선**: 탐침 전 01:46:44에 떴다([baseline.json](baseline.json)). 기억·대화·포식·건강·해마 DB 행 수·mtime과 포식 문서 트리·회상 색인·업무 공간·스캔을 담았다.
- **회차 후 diff**(02:09:37)
  - action_health 새 행 **99, 전부 `training`/agent**. B78-8 때문에 실패도 success=1로 적혔다.
  - notify_log 0 · 알림 추가 0 · since 원장 불변.
  - **기억 저장소 diff 0**(`stores_changed: {}`): system_ai_memory 대화 3,564 · 컨텐츠 대화 639 · 심층기억 90/15/0 · 포식 727행·문서 150 · 건강 persons 6·측정 41 · 코퍼스 3,735 · episode_log 불변 · `data/record_spaces` 없음 그대로.
- **호출**: 외부 5회(정보나루 — T13 1·격리 4), 유료 AI 0, 발신 0, 해마 시딩 0.
  - 셸 대조는 전부 읽기 전용: 대화 DB LIKE 건수, forage_map 행 수·locus 형태, trajectory source 집계, action_health shape 집계.
  - 건강 오타 주체는 스크래치 사본 DB에서만 재현했다.
- **스크래치**(전부 삭제 확인)
  - `projects/컨텐츠/outputs/IT78_건강원장.json`(T22·T23)
  - `projects/컨텐츠/outputs/chart_20260929_020123.png`(T19)
  - 읽기가 만든 `projects/컨텐츠/memory_IT78_probe.db`(B78-2)
  - 스크래치패드의 건강 DB 사본
  - 실행기가 남긴 결과 사본 `data/spill/tool_evidence/<1폴더>` 108파일은 시스템 관리물이라 두었다. 이번 회차 읽기의 개인 원문 사본이 들어 있고, 수명 정책 적용 여부는 미확인이다.
- **사용자 데이터 무손상**: 대화·심층기억·포식 기억·건강 기록·노트북은 읽기만 했다. 건강 save·delete·포식 note는 check만 했다.
- **나머지**: 라이브 코어 편집 0 · 커밋 0.
- **백엔드**: 회차 내내 `state.json` phase `ACTIVE`(`last_result.outcome: restarted`), 재기동·FAILED 없음.

## 집행 완료

(1차) `747d5103` — B78-1·2·3·7·8 수리([77~81 공통 경계 수리](../../IMAGINATION_77_81_REPAIRS_2026_09_29.md)).

(2차 · 2026-09-29) 라이브 재탐침으로 샌 것을 골라 수리 — 정본 [78·79 잔여 수리](../../IMAGINATION_78_79_RESIDUAL_REPAIRS_2026_09_29.md).
- F78-1·B78-4: 장소 존재 확인기 한 벌(`place_exists`) → recall `locus_exists`·`own_count`·`doc_is_ancestor`, root_missing·freshness·reconcile 공유. notebook delete 가 그 몸 기억을 `_gone` 유예로 접음. 수리 전 고아는 표식만(판정 요청 1 대기).
- B78-5: 책·노트북 몸 정규형 한 벌을 입구·회상이 공유, own-space locus 관문, 옛 괄호·주제 이름 행도 읽기에서 찾아짐(places→locus ≥1 가드). 증류 프롬프트 자리표 교체. 같은 책 두 몸의 병합은 판정 요청 1 대기.
- B78-6: 정보나루 `<request>` 날 에코를 경계에서 처리 + `source_parse` 구분. 형제: 고전종합DB 검색어 무시 수리.
- F78-2: 열린 인자 계약 전수 관문(`iblbuild_open_params.py`) — 20개 중 18개 닫음, recent_chats 미지 인자는 table:filter 안내와 함께 거절.
- F78-3: health 평탄 키 선언(구현-읽기 관문이 튜플 루프를 봄)·측정 조회 table 선언, forage 판본 1 문구·은퇴 인자(`retired_contracts.yaml`).
- F78-4: 도달 가능 셈을 `self_can_run` 으로(139→126). F78-5: ledger 쓰기가 쓰기 원장에.
- B72-3 재확인: 대화 가지 미리보기 행 표지.
- 부수: 평문 실패 판정 한 벌(`common.currency.is_plain_failure`) — 인자 경고 머리 장식이 실패를 성공으로 바꾸던 누수와 통화 분류기의 평문 실패 성공 기록.
- 교재: 2799·2800·294·1257·1349·1373·1566 개별 교정(영수증은 잔여 수리 문서).
