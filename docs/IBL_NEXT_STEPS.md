# IBL 사전 다음 단계 핸드오프

*2026-05-26 작성. 332개 액션 description/target_description 1차 정비 완료 직후.*
*2026-05-26 갱신. **별칭 24개 정리 완료** (332 → 308 액션).*
*2026-05-26 갱신. **sense 그룹화 완료** (83개 → 7 그룹, 카탈로그 API + 마법책 UI 적용).*
*2026-05-26 갱신. **파일 가상 분할 완료** (1 파일 → 6 소스 + 빌드 스크립트, byte-identical 라운드트립).*
*2026-05-26 갱신. **self/limbs 그룹화 완료** (95 ungrouped → 0. self 10 그룹, limbs 6 그룹).*
*2026-05-26 갱신. **category 필드 폐지** (111 line 제거, others 2개 ungrouped 채움. 모든 308 액션 그룹 보유).*
*2026-05-26 갱신. **노드 간 동명 정리** (self:find → self:file_find. 0 cross-node duplicate).*

## 다음 세션 한 줄

> 어휘·그룹·메타 모든 1차 정리 끝. 0 cross-node dup, 25 backward-compat alias, 29 unique groups, 308 액션. **다음**: router/tool/func 추상화 통일 → discover-first → others/engines 그룹 세분화 검토.

## 이번 세션(7차)에서 끝낸 것 — 노드 간 동명 정리

- 2차 별칭 정리(24개) 이후 cross-node dup 6개 → 5개가 자연 해소. 남은 건 1개(`find`).
- `self:find` (파일 glob, tool=glob_files) vs `limbs:find` (DOM 요소 검색, tool=browser_find) — 의도가 완전히 다른데 이름 충돌.
- 사용자 결정: `self:find` → **`self:file_find`** 이름 변경 (file 그룹 패턴과 일치, limbs 도구 이름과는 분리 유지).
- 적용:
  - `data/ibl_nodes_src/self.yaml`: 액션 헤더 `find:` → `file_find:` 1줄 변경
  - [backend/ibl_parser.py](backend/ibl_parser.py) `_ACTION_NAME_ALIASES`에 `(self, find) → (self, file_find)` 추가 (총 25개 alias)
  - 활성 코퍼스 마이그레이션: `ibl_training_balanced_20260516.json` (12), `ibl_distilled.json` (11), `ibl_usage.db` (23 행), `12_ibl_only.md` (1), `system_essentials/tool.json` (1) — 총 48 치환
- 결과: **0 cross-node duplicate action names**. 시스템 프롬프트 +10자 (file_find가 find보다 5자 길고 2회 노출).

## 이번 세션(6차)에서 끝낸 것 — category 폐지

- **조사 결과**: category는 (1) ibl_access.py:172의 group 폴백 키, (2) 카탈로그 API의 display 필드. discover/RAG/시스템 프롬프트 본문은 category를 안 본다. CLAUDE.md 표현대로 "Phase 24에 verb 제거 후 대체된 **순수 표시용**" 잔재.
- 사용자 결정: 필드 자체 제거 (옵션 A — 표준화는 ROI 낮음).
- **yaml 정리**: 111개 `category:` 줄 제거 (sense 11, self 38, limbs 18, others 4, engines 40). 분포는 일관성 부족(get/create/execute/list/control/search/io 등 8종 다수 + click/type/play 등 단일 12종).
- **others 마무리**: `neighbors`, `neighbor_detail` 2개 ungrouped → 새 `neighbor` 그룹 부여. 이제 **308 액션 전부 group 보유**.
- **코드 정리**:
  - `backend/api_ibl.py` — 카탈로그 API에서 `category` 노출 제거
  - `backend/ibl_access.py` — group 폴백 로직 단순화 (group이 모든 액션에 있음을 전제)
  - `frontend/src/components/chat/ActionGrimoire.tsx` — ActionMeta.category 제거 + others/engines 그룹 라벨 추가 (delegation/channel/neighbor/media_produce/chart/music/web_builder)
  - `data/ibl_nodes_src/meta.yaml` — "action-categories" 잔재 텍스트 2곳 정리
- **결과**: 29 그룹 전체 노드 통합 (sense 7 + self 10 + limbs 6 + others 3 + engines 4 - 중복 1[media] = 29 unique). yaml: 3,500줄 → 3,390줄 (-110줄).

## 이번 세션(5차)에서 끝낸 것 — self/limbs 그룹화

- **소스 파일 직접 편집 후 빌드 스크립트 사용 — 4차에서 만든 새 워크플로의 첫 실사용**.
- **self (93 액션, 10 그룹)**:
  - `file` (19), `schedule` (14), `lecture` (14), `blog` (9), `photo` (8)
  - `workflow` (6), `memory` (6), `system` (6), `data` (6 — health+cctv+output 통합), `goal` (5)
- **limbs (75 액션, 6 그룹)**:
  - `browser` (28), `media` (13), `browser_session` (12), `open` (12), `desktop` (9), `cloudflare` (1)
- **마법책 UI 라벨** ([frontend/src/components/chat/ActionGrimoire.tsx](frontend/src/components/chat/ActionGrimoire.tsx)) — sense 7 + self 10 + limbs 6 = 23개 그룹 한국어 라벨 + 표시 순서 등록.
- yaml: 3,405줄 → 3,500줄 (+95줄, group: 라인 추가됨).
- 사용자 결정 사항:
  - self는 자세한 12 대신 9-10 압축 안 선택 (health/cctv/output → `data` 통합).
  - limbs는 browser를 둘로 쪼개 6 그룹 안 선택 (사용자 인터랙션과 세션 관리 분리).

## 이번 세션(4차)에서 끝낸 것 — 파일 가상 분할

- **편집용 소스 디렉토리** `data/ibl_nodes_src/` 생성 — 6개 yaml 파일:
  - `meta.yaml` (73줄), `sense.yaml` (884줄), `self.yaml` (956줄), `limbs.yaml` (680줄), `others.yaml` (150줄), `engines.yaml` (661줄)
  - 모두 단독 yaml로 파싱 가능 (PyYAML 검증). 노드 파일 4개는 root key가 column 2지만 YAML 스펙상 유효.
- **빌드 스크립트** `scripts/build_ibl_nodes.py`:
  - 소스 6개를 byte 단위로 연결 + 명시적 `nodes:\n` 헤더 삽입 → `data/ibl_nodes.yaml` 생성
  - `--check` 플래그: 빌드 결과가 현재 yaml과 일치하는지 검증 (CI/pre-commit용)
  - 첫 빌드는 **byte-identical** 라운드트립 검증 통과 (MD5 동일).
- **런타임 무변경**: `ibl_access.py` 등 yaml 직접 로드 코드 7곳 그대로 — 모두 단일 ibl_nodes.yaml만 본다.
- **편집 워크플로**: `data/ibl_nodes_src/<node>.yaml` 편집 → `python scripts/build_ibl_nodes.py` → 자동 yaml 갱신.
- 가드: README([data/ibl_nodes_src/README.md](data/ibl_nodes_src/README.md))에 워크플로/주의사항 명시. pre-commit에 `--check` 추가 권장(미구현).

## 이번 세션(3차)에서 끝낸 것 — sense 그룹화

- **sense 83개 액션을 7개 자연 그룹으로 분류**:
  - `finance` (16) — 주가·재무·공시·실적·암호화폐
  - `real_estate` (6) — 부동산 실거래·상권
  - `research` (18) — 학술 논문·기술 문서·웹/뉴스 검색·일반 API
  - `culture` (15) — 공연·전시·여행·도서·고전
  - `media` (14) — 유튜브·CCTV·웹캠·라디오
  - `places` (9) — 길찾기·날씨·맛집·수집
  - `world` (5) — World Pulse·자가점검·World Bank
- **카탈로그 API 확장** ([backend/api_ibl.py:48](backend/api_ibl.py)): `group`·`category` 필드 노출. 이전엔 description/target_description만 반환.
- **마법책 UI 그룹 섹션 분할** ([frontend/src/components/chat/ActionGrimoire.tsx](frontend/src/components/chat/ActionGrimoire.tsx)): 노드 안에서 group별로 sub-section 헤더와 함께 칩 그룹핑. 그룹이 없는 노드(self/limbs 등)는 평탄 표시 fallback. GROUP_LABELS·GROUP_ORDER 매핑 추가.
- **다른 노드의 group 현황** (참고):
  - self: 53 ungrouped / 40 grouped (photo·blog·memory·system·schedule·goal·workflow·output·file)
  - limbs: 42 ungrouped / 33 grouped (browser·desktop·media·cloudflare·launcher·general)
  - others: 2 ungrouped / 10 grouped (delegation·channel)
  - engines: 0 ungrouped / 45 grouped (media_produce·chart·music·web_builder)

## 이번 세션(2차)에서 끝낸 것 — 별칭 정리

- **yaml에서 24개 별칭 액션 제거**: 332 → 308 액션. ibl_nodes.yaml 274줄(-7%) 축소, 시스템 프롬프트 env 2,172자(-5%) 축소.
- **런타임 alias map 추가** ([backend/ibl_parser.py](backend/ibl_parser.py:858) `_ACTION_NAME_ALIASES`): 학습 데이터/외부 호출의 옛 이름이 파싱 시 자동으로 캐노니컬로 정규화. 무중단 호환성 확보.
- **호출처 마이그레이션**:
  - 현재 학습 코퍼스: `ibl_training_balanced_20260516.json` (130 치환), `ibl_distilled.json` (1)
  - 해마 DB: `ibl_usage.db` 131 행 (FTS 트리거로 자동 동기화)
  - 스크립트: `generate_missing_intents.py` (19), `rebuild_usage_db.py` (2)
  - 가이드: `cctv.md` (2), `self_inspection_guide.md` (1)
  - 패키지 메타: `memory/tool.json`, `ibl_embedding/README.md`
  - **_archive/는 의도적으로 그대로** — 동결된 역사적 기록.

### canonical 결정 (24쌍)

| 제거된 별칭 | 캐노니컬 |
|---|---|
| sense:info | sense:stock_info |
| sense:company_news | sense:news |
| sense:nearby | sense:cctv_nearby |
| self:cctv_sources | sense:cctv_sources |
| sense:save | self:local_save |
| self:timeline | self:photo_timeline |
| self:list_scans | self:photo_list_scans |
| self:gallery | self:photo_gallery |
| self:photo_manager | limbs:photo_manager |
| self:posts | self:blog_posts |
| self:check_new | self:blog_check_new |
| self:rebuild_index | self:blog_rebuild_index |
| self:search_memory | self:memory_search |
| self:launch | limbs:launch |
| self:summary | self:storage_summary |
| self:annotate | self:folder_annotate |
| self:annotations | self:folder_annotations |
| self:explorer | limbs:explorer |
| limbs:navigate | limbs:browser_navigate |
| limbs:content | limbs:browser_content |
| limbs:close | limbs:browser_close |
| limbs:route_navigate | sense:navigate_route |
| sense:map | limbs:show_map |
| sense:cctv_open | limbs:cctv_open |

원칙: (a) 명시적 접두사(`browser_`, `blog_`, `photo_`)가 일반 명사보다 우위, (b) UI/앱 띄우기는 `limbs`, 외부 데이터 인출은 `sense`, 내부 데이터 저장/조회는 `self`. 일부(예: `route_navigate`가 sense에 → 데이터 인출)는 노드 경계 일관성을 우선해 캐노니컬 노드를 바꿈.

백업: `data/ibl_nodes.yaml.bak.20260526` (안정화 후 제거).

## 이전 세션(1차)에서 끝낸 것

### 마법책 (ActionGrimoire) MVP
- 백엔드: 카탈로그 API (`GET /ibl/actions/catalog`), `_build_execution_memory(msg, action_hint)` 분기 로직, 5개 WebSocket/system_ai 핸들러에 `action_hint` 통과, 의식 에이전트 프롬프트에 `<user_selected_action>` 케이스 룰 추가.
- 프론트: 채팅창 헤더에 BookOpen 책 버튼, `ActionGrimoire.tsx` 모달 (5노드 분류, 호버 상세, ESC/바깥 닫기), 선택 칩 + Zustand 없이 ChatView 로컬 state, sendMessage payload에 `action_hint` 통합.
- 키 파일:
  - `backend/api_ibl.py` (카탈로그 API)
  - `backend/ibl_usage_rag.py:247` (`build_execution_memory_from_hint`)
  - `backend/agent_cognitive.py:268` (`_build_execution_memory`)
  - `data/common_prompts/consciousness_prompt.md:27` (의식 에이전트 룰)
  - `frontend/src/components/chat/ActionGrimoire.tsx` (모달)
  - `frontend/src/components/chat/ChatView.tsx`, `ChatInputArea.tsx`

### IBL 사전 description 정비
- **332개 액션 전수 점검 완료**:
  - description < 25자: 188개 → **0개**
  - target_description 누락: ~240개 → **0개**
  - description 평균: 36자 → 53자 (시스템 프롬프트 증가 ~3K 토큰, caching prefix라 비용 거의 무)
- 톤 원칙: description은 *액션 구분*에 필요한 최소 정보 (20-50자, 시스템 프롬프트 비용), target_description은 *형식·예시·주의사항* (UI 전용, 풍부하게).

---

## 발견한 구조적 이슈 (description과 별개)

`ibl_nodes.yaml`은 **진화의 흔적이 정리 안 된 상태**. 어휘는 만들었지만 별칭/그룹/카테고리/라우터 같은 메타가 후반에 추가되면서 *기존 액션은 마이그레이션 안 됨* → 결과적으로 *AI의 패턴 매칭 능력*에 의지해 작동.

### 정량 진단 (332개 기준)

| 이슈 | 수치 | 영향 |
|---|---|---|
| **별칭 잉여** (같은 tool 부르는 두 이름) | 29개 액션이 25개 도구의 별칭 (8.7% 잉여) | 시스템 프롬프트에 같은 도구를 두 이름으로 노출 → AI 혼란 + ~1K 토큰 낭비 |
| **노드 간 동명 액션** | 6개 (find/explorer/launch/photo_manager/cctv_open/cctv_sources) | 노드 경계 의미 약화 |
| **그룹화율 sense** | 18% (89개 중 16개만 group 지정) | 마법책에서 sense 73개가 한 덩어리로 보임 |
| **category 누락** | 63% (208/332개) | 분류 메타 절반 이상 비어 있음 |
| **target_key 누락** | 37% | params 첫 키 명시 안 됨 |
| **keywords 누락** | 45% | discover/검색 폴백 약함 |
| **router 종류** | 9종 (handler 82%, system 10%, …) | router별로 실행 키 이름 다름 (tool/func/driver+driver_node) |
| **단일 yaml 파일** | 3,609줄 / 168KB | 편집 어려움 |
| **yaml 직접 로드 코드** | 5곳 (ibl_access/tool_loader/tool_selector/system_tools/bootstrap) | 분할 시 5곳 모두 수정 필요 |

### 별칭 쌍 전수 (29개 잉여)

```
annotate_folder        → self:annotate, self:folder_annotate
blog_check_new_posts   → self:check_new, self:blog_check_new
blog_get_posts         → self:posts, self:blog_posts
browser_close          → limbs:close, limbs:browser_close
browser_get_content    → limbs:content, limbs:browser_content
browser_navigate       → limbs:navigate, limbs:browser_navigate
company_news           → sense:news, sense:company_news
get_folder_annotations → self:annotations, self:folder_annotations
get_gallery            → self:gallery, self:photo_gallery
get_nearby_cctv        → sense:nearby, sense:cctv_nearby
get_storage_summary    → self:summary, self:storage_summary
get_timeline           → self:timeline, self:photo_timeline
kakao_navigation       → sense:navigate_route, limbs:route_navigate
launch_sites           → self:launch, limbs:launch
launcher_command       → limbs:open_project, open_system_ai, open_indienet, open_business, open_multichat, open_folder (6개가 같은 func)
list_cctv_sources      → sense:cctv_sources, self:cctv_sources
list_scans             → self:list_scans, self:photo_list_scans
local_db_save          → sense:save, self:local_save
memory_search          → self:search_memory, self:memory_search
open_cctv              → sense:cctv_open, limbs:cctv_open
open_file_explorer     → self:explorer, limbs:explorer
open_photo_manager     → self:photo_manager, limbs:photo_manager
rebuild_search_index   → self:rebuild_index, self:blog_rebuild_index
show_location_map      → sense:map, limbs:show_map
yf_stock_info          → sense:stock_info, sense:info
```

---

## 추가 수정 (2026-05-26, 라운드 종료 후 시스템 AI 실사용 테스트로 발견)

시스템 AI가 IBL 액션을 한 바퀴 실행 점검하던 중, **이전부터 존재하던** 도구 등록 누락 6건 발견:
- 증상: `[engines:chart]`, `[engines:lecture_plan]` 등 호출 시 `도구 핸들러를 찾을 수 없습니다`
- 진단: ibl_nodes.yaml에서는 `tool: chart` / `tool: create_lecture_plan` 등을 참조하는데, 해당 패키지 `tool.json`의 `tools` 배열에 등록이 빠짐. handler.py에는 dispatch 분기 다 있었음. 등록만 누락된 옛 상처.
- 수정: 6개 tool 등록 추가
  - `data/packages/installed/tools/visualization/tool.json`: `chart` (umbrella → line/bar/pie/scatter/heatmap/candlestick/multi 분기)
  - `data/packages/installed/tools/media_producer/tool.json`: `create_lecture_plan`, `create_lecture_write`, `create_lecture_illustrate`, `create_lecture_compose`, `critique_gemini_image`
- 검증: import-level로 6개 모두 tool→package 매핑·schema 로드·handler 모듈 동적 로드 성공. 런타임은 `tool_loader._tool_to_package_map`가 프로세스 시작 시 빌드되므로 **백엔드 재시작 필요**.
- 발견된 *별개 이슈* (수정 안 함):
  - `[others:channel_*]` "에이전트 정보가 없습니다" — 시스템 AI에 채널 신원 없음. 정책 결정 사안.
  - `[sense:travel]` "endpoint 매개변수 필요" — yaml description이 `endpoint` 필수를 명시 안 함. 메타 정비 영역.

### `new_action_checklist.md` 가이드 따라 후속 보강

사용자 지적으로 가이드 점검 — 빠진 단계 2건 발견 후 보완:
- **패키지 ibl_actions.yaml 일관성**: `visualization/ibl_actions.yaml`에 `chart` umbrella 누락 → 추가.
- **해마 합성 용례 부재**: lecture_* 5개 + image_critic 합계 60개 / `chart` umbrella 5개 보강 = **총 65개 합성 용례 추가**.
  - `IBLUsageDB.add_examples_batch()`로 DB 등록 (가이드 3-(1))
  - `data/training/ibl_distilled.json`에 append (가이드 3-(2))
  - `db.rebuild_index()` 실행 → 2,197개 indexed (가이드 4단계, 28초)
- **시맨틱 검색 검증** (가이드 5-(2)): 7건 쿼리 중 6건 rank 1, `[engines:chart]`는 짧은 일반 쿼리에서 구체 차트와 균형(rank 2/4).
- **남은 단계 5-(3)**: 실제 실행 확인은 **백엔드 재시작 후** 시스템 AI에서 자연어로 호출해보면 됨.

## 현재 라운드 종료 (2026-05-26)

가시적인 메타·구조 정비는 1-7차로 마무리. 남은 세 항목은 **평가 후 의도적 skip**:

| # | 항목 | 결정 | 이유 |
|---|---|---|---|
| ~~1~~ | ~~별칭 정리~~ | 1차 완료 | -2,172자 / ~600-700 토큰 |
| ~~2~~ | ~~sense 그룹화~~ | 1차 완료 | 7 그룹 |
| ~~3~~ | ~~파일 가상 분할~~ | 1차 완료 | 6 src + 빌드 스크립트 |
| ~~4~~ | ~~self/limbs 그룹화~~ | 1차 완료 | 10 + 6 그룹 |
| ~~5~~ | ~~category 정리~~ | 1차 완료 | 필드 폐지 |
| ~~6~~ | ~~노드 간 동명 정리~~ | 1차 완료 | self:find → file_find |
| **—** | router/tool/func 통일 | 평가 후 skip | AI는 안 봄(description만 시스템 프롬프트). yaml 가독성만 미미 향상이나 `tool`/`func`/`driver` 구분이 *의미 정보*를 잃음. ROI 낮음. 분기 9줄짜리 if/else는 유지 부담 거의 없음. |
| **—** | others/engines 그룹 세분화 | skip | 현재 그룹화로 충분. media_produce(16)/web_builder(16)가 크지만 묶음 의미가 명확. |
| **—** | discover-first 아키텍처 | skip | ~7K 토큰/호출 절감 가능하나 아키텍처 변경 규모가 큼. 시스템 안정화 이후 별도 검토. |

다음 IBL 작업이 필요해지면 이 표 위에 새 항목을 추가하라.

### #1. 별칭 정리 — 첫 작업으로 권장

**판단 필요한 케이스**:
- `browser_navigate` vs `navigate` 류 — `browser_` 접두사 있는 쪽이 *명시적 그룹화*. 더 새로운 명명일 가능성. 어느 쪽이 *canonical*인지 결정.
- `cctv_open`이 sense + limbs 양쪽에 — sense는 *외부 정보 수집*인데 cctv_open은 *브라우저 실행*이라 limbs가 더 적절. 노드 경계 정리.
- `info` vs `stock_info` — 한 글자만 다름. 일반 명사 `info`는 다른 도메인에서도 쓸 수 있어 충돌 가능. `stock_info`가 더 안전.

**진행 방법**:
1. 별칭 쌍 25개에 대해 *canonical 결정* + 다른 하나를 제거
2. 제거 전 — 코드에서 그 이름을 직접 호출하는 곳 grep (예: `[limbs:close]` 패턴)
3. 호출처가 있으면 canonical로 변경 + yaml에서 제거
4. 호출처 없으면 yaml에서만 제거

**예상 절감**: ~600-1000 토큰 (XML 골격 포함). 캐시 첫 인코딩 시 즉시 효과.

### #2. sense 그룹화 — 두 번째 작업

sense 89개의 자연스러운 그룹 후보 (descriptio 보고 추정):
- `finance` — price/info/kr_price/us_price/kr_company/us_company/kr_disclosure/us_filing/kr_financial/us_financial/kr_investor/kr_stock_investor/earnings/company_news/crypto/news/stock_info/search_stock (~18개)
- `academic` — search_arxiv/search_openalex/search_scholar/search_semantic/search_pubmed/download_arxiv/download_pubmed/search_library_docs/resolve_library/gutenberg_books/korean_classics (~11개)
- `real_estate` — apt_rent/apt_trade/house_rent/house_trade/district_codes/commercial (~6개)
- `book` — book/book_by_isbn/book_detail/library_regions/kdc/recommended_books/search_books (~7개)
- `culture` — venue/exhibit/genres/performance/performance_regions/travel/korean_classics (~7개)
- `news_search` — search_ddg/search_naver/search_news/search_guardian/search_local/crawl/pew_research (~7개)
- `youtube` — search_youtube/summarize_video/video_info/video_languages/video_transcript (~5개)
- `cctv` — cctv_search/cctv_capture/cctv_nearby/cctv_by_name/cctv_open/cctv_sources/nearby/webcam/webcam_nearby (~9개)
- `location` — map/navigate_route/reverse_geocode/show_map (~4개)
- `data` — api_ninjas/world_bank
- `collect` — collect/collect_query/collect_save/collect_sites/local_query/save
- `world` — world_pulse/world_refresh/world_trend/self_check
- `radio` — korean_radio/search_radio
- `restaurant` — restaurant
- ...

이 그룹화는 마법책 UI에서 자연스러운 섹션 분할이 됨. group 필드만 채우면 카탈로그 API가 자동으로 그룹별 분류.

### #3. 파일 분할 — 세 번째 작업 (편집 편의)

**현재 위험**: yaml을 직접 로드하는 코드가 *5곳*. 단순 파일 분할은 5곳 수정 필요.

**권장 방안 — 가상 분할 (런타임 변경 없음)**:
1. 편집용 소스 디렉토리 `data/ibl_nodes_src/`:
   ```
   data/ibl_nodes_src/
     meta.yaml
     sense.yaml       (sense 노드만)
     self.yaml
     limbs.yaml
     others.yaml
     engines.yaml
   ```
2. 빌드 스크립트 `scripts/build_ibl_nodes.py`:
   - 6개 yaml 읽어 병합 → `data/ibl_nodes.yaml` 생성
   - 한 번에 모든 노드 통합, 기존 형식 보존 (PyYAML dump가 아닌 yaml 구조 유지)
3. 편집 워크플로:
   - 평소: 소스 디렉토리에서 편집 → `python scripts/build_ibl_nodes.py` → 단일 yaml 생성
   - 런타임: 단일 ibl_nodes.yaml 그대로 사용 (변경 없음, 위험 없음)
4. CI/hook (선택): pre-commit에서 자동 빌드

**대안 — 실제 분할 (런타임도 디렉토리 우선)**:
- 5곳의 yaml 로드 코드를 *디렉토리 우선, 파일 폴백* 패턴으로 모두 수정
- 더 깔끔하지만 위험 큼. 5곳 모두 검증 필요.
- 권장: **먼저 가상 분할 → 안정화 → 그 다음 실제 분할 마이그레이션**

### #6/7 — 큰 결정 (당장 X)

router/tool/func 통합과 discover-first는 *아키텍처 변경*. 1-3번 정리 후 시스템이 깔끔해진 다음에 결정. 지금은 보류.

---

## 메모리 참조 (다음 세션 컨텍스트)

- `[[architecture_ibl_description_cost]]` — description은 시스템 프롬프트 비용. target_description은 UI 전용.
- `[[architecture_ibl_as_vocabulary]]` — IBL은 도구 폭증의 *언어적* 해법. 어휘가 누적의 형식. 이번 진단으로 *어휘 정돈*이 시스템 가치의 핵심임을 확인.
- `[[architecture_three_tier_cognition]]` — 3단 인지 모델. 척수반사(런처/스케줄러)는 IBL 바깥에 정당.
- `[[architecture_ibl_action_criteria]]` — IBL 액션 4기준 (조합성·빈도·실시간성·외부 인터페이스). 별칭 정리 시 *그 액션이 진짜 IBL에 있어야 하는지* 기준으로 활용.
- `[[project_indiebizos_runtime]]` — dev 모드 상시 사용, Electron 재빌드 금지.

---

## 핸드오프 한 줄 (라운드 종료)

> 1-7차로 1라운드 마무리: 332 desc → 별칭 24개 → sense 7 그룹 + 카탈로그 API + UI → 파일 가상 분할 → self 10·limbs 6 그룹 → category 폐지 → cross-node 동명 정리.  → **현재 상태: 308 액션 / 29 그룹 / 25 alias / 0 cross-node dup / yaml 3,390줄.**  남은 router 통일·discover-first·others/engines 세분화는 평가 후 의도적 skip (위 표 참고).
