---
title: 도구 패키지 시스템
scope: 패키지 구조(handler/tool.json), 설치 절차, 설치 패키지 목록(수·표=빌드 파생). IBL 어휘 등록은 `data/ibl_nodes_src/<node>.yaml` 단일 진실 소스(ibl.md 참조). op 분기 패키지는 `_OP_DISPATCHERS` 표준 채택.
owner_code: package_manager.py, tool_loader.py
last_updated: 2026-08-21
see_also: [architecture.md, ibl.md]
---

# 도구 패키지 시스템 가이드

이 문서는 IndieBiz OS의 도구 패키지 설치/제거 방법을 정의합니다.
시스템 AI는 패키지 관련 작업 시 반드시 이 문서를 참조해야 합니다.

## 핵심 개념

### 도구 패키지란?
에이전트가 동적으로 로딩하여 사용하는 확장 기능입니다. 에이전트는 실행 시 필요한 도구를 패키지에서 불러와 사용합니다.

### 패키지 유형
- **도구 패키지 (tools)**: 에이전트가 `tool.json` + `handler.py`를 통해 동적으로 로딩하여 사용하는 기능 단위. IBL 액션으로 노출 가능.
- **백엔드 코어 모듈 (extensions/)**: 에이전트가 호출하는 도구가 아니라 백엔드 시스템 내부에서 사용되는 코어 모듈 (에이전트 실행, 대화 관리, Gmail, 스케줄러 등). `tool.json`/`handler.py` 없이 백엔드에서 직접 import.

### 폴더 구조
- **not_installed/tools/**: 설치 가능한 도구 패키지 (아직 설치 안 됨)
- **installed/tools/**: 설치 완료된 도구 패키지 (에이전트가 사용 가능)
- **installed/extensions/**: 백엔드 코어 모듈
- **dev/tools/**: 개발 중인 패키지

### 설치/제거 원리
- **설치**: `not_installed/tools/` → `installed/tools/`로 폴더 이동
- **제거**: `installed/tools/` → `not_installed/tools/`로 폴더 이동

---

## 필수 파일 형식

### 1. tool.json - 도구 정의 (배열 형식)
에이전트에게 노출될 도구의 이름과 입력 스키마를 정의합니다.

```json
[
  {
    "name": "도구명",
    "description": "도구 설명",
    "input_schema": {
      "type": "object",
      "properties": {
        "param1": {"type": "string", "description": "파라미터 설명"}
      },
      "required": ["param1"]
    }
  }
]
```

### 도구 설명 작성 가이드 (2026-01-20)
AI가 도구를 정확히 선택하도록 간결하고 범용적인 설명 권장:
- **구조**: 한줄 요약 + 데이터 형식 + 예시
- **예시**: `"라인 차트 생성. x-y 데이터를 선으로 연결하여 시각화.\n\n데이터 형식: [{x: 값, y: 값}, ...]\n\n예시: data=[{x:1, y:1}, {x:2, y:4}]"`

### 가이드 파일 시스템 (guide_file) (2026-01-29)
복잡한 사용법을 가진 도구에 상세 가이드를 on-demand로 제공하는 시스템.
description에 모든 내용을 넣지 않고, 필요할 때만 가이드를 주입하여 토큰을 절약합니다.

**두 가지 유형:**

**(A) 공용 가이드 (data/guides/)** — 의식 에이전트 기반 선택
- `data/guides/` 폴더에 마크다운 파일 저장 (현재 67개 / `guide_db.json` 등록 65개)
- 의식 에이전트가 사용자 메시지를 분석하여 관련 가이드 2-3개 선택
- `prompt_builder._load_guide_file()`로 로드 후 프롬프트에 주입

동작 흐름:
```
사용자 메시지 → consciousness_agent.get_guide_list() (키워드 매칭, 상위 10개)
    → consciousness_agent.process() (가이드 선택)
    → JSON 출력: { "guide_files": ["investment.md", ...] }
    → prompt_builder가 data/guides/에서 읽어 프롬프트에 주입
```

**(B) 패키지 레벨 가이드 (tool.json의 guide_file)**
- 패키지 폴더 내 가이드 파일
- `tool.json`의 `guide_file` 필드로 지정 (개별 도구 또는 패키지 레벨)
- 에이전트가 `read_guide` 도구로 직접 읽거나 IBL 엔진에서 참조

**가이드 파일 작성 팁:**
- 사용법, 규칙, 예시 코드 포함
- description에는 한 줄 요약만, 나머지는 가이드에 작성
- 5000~8000자 이내 권장

**관련 파일:** `consciousness_agent.py`, `prompt_builder.py`, `tool_loader.py`, `system_tools.py`, `ibl_engine.py`

### 2. 실행 로직 — 두 가지 방식

#### (A) handler.py (복잡한 후처리가 필요한 경우)
`execute(tool_name, tool_input, project_path)` 함수를 포함해야 합니다.

```python
def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """도구 실행 함수"""
    if tool_name == "도구명":
        # 로직 구현
        return "결과"
    return f"알 수 없는 도구: {tool_name}"
```

#### (B) api_registry.yaml 등록 (API 호출 + transform으로 충분한 경우)
`data/api_registry.yaml`에 도구를 등록하면 handler.py 없이 동작합니다. `node` 필드를 추가하면 IBL 노드 액션으로 자동 병합됩니다.

```yaml
kosis_search_statistics:
  service: kosis
  endpoint: /statisticsList.do
  transform: kosis_list
  node: sense                # IBL 자동 병합 (Phase 25: statistics → sense)
  action_name: search_statistics
  description: "통계표 목록 검색"
```

api_engine 라우팅 액션들이 이 방식을 사용합니다.

### 3. IBL 노드 액션 등록 — 단일 진실 소스 (2026-05-28~)

패키지의 도구를 IBL 노드 액션으로 노출하려면 **`data/ibl_nodes_src/<node>.yaml`에 직접 액션을 추가**한다. 패키지 폴더에 `ibl_actions.yaml`을 두지 않는다 (옛 방식은 폐기됨; [[architecture_ibl_unification]] 참조).

```yaml
# data/ibl_nodes_src/engines.yaml
engines:
  # scope: workspace          # (선택) 노드 레벨 기본값. 자세한 건 ibl.md "액션 스코프" 참고.
  actions:
    create_site:               # 액션 이름 (노드 내에서 유일해야 함)
      description: 웹사이트 프로젝트 생성
      router: handler          # handler.py로 라우팅
      tool: site_manager       # handler.py에서 매핑할 도구명
      target_key: site_name    # 자연어에서 추출한 대상이 매핑될 파라미터
      default_input:           # 기본 입력값 (선택)
        action: create
    add_component:
      description: 웹사이트에 컴포넌트 추가
      target_description: 컴포넌트 이름
      router: handler
      tool: component_manager
      target_key: component_name
```

추가 후 빌드 + 검증:
```bash
python3 scripts/build_ibl_nodes.py          # data/ibl_nodes.yaml 재생성
python3 scripts/build_ibl_nodes.py --check  # 일치 확인
```

빌드 산출물(`data/ibl_nodes.yaml`)은 첫 줄에 `# GENERATED — DO NOT EDIT` 헤더가 있으며 런타임이 읽는 단일 파일이다. 직접 편집하지 말 것.

#### postprocess 필드 (감각 전처리)
정보성 액션의 출력이 길 때 경량 AI로 압축하여 에이전틱 루프의 컨텍스트 폭발을 방지한다. 감각기관이 원시 데이터를 전처리해서 뇌에 보내는 것과 같은 원리. `ibl_nodes_src/<node>.yaml`의 액션 정의 안에 `postprocess` 블록으로 선언.

```yaml
search:
  router: handler
  tool: search
  postprocess:                # 후처리 설정 (선택)
    type: compress            # 전처리 유형 (현재: compress)
    threshold: 1500           # 이 글자 수 이상일 때만 압축 (기본: 1500)
    prompt: "각 검색 결과를 제목, URL, 핵심 내용 1줄로 압축하라."  # 액션별 커스텀 프롬프트 (선택)
```

- **type**: 전처리 유형. 현재 `compress`만 구현. 향후 `filter`, `structure` 등 추가 가능.
- **threshold**: 결과가 이 글자 수 미만이면 후처리를 건너뜀 (기본: 1500).
- **prompt**: 액션 특성에 맞는 압축 지시. 생략 시 범용 프롬프트 사용.
- engines 등 결과를 보존해야 하는 액션에는 적용하지 않는다.

### 4. 가이드 파일 - 에이전트용 사용 설명서 (선택)

복잡한 워크플로우를 가진 패키지는 가이드 파일을 작성하여 에이전트가 올바른 순서로 도구를 사용하도록 한다.

**두 가지 레벨**:

#### (A) 패키지 레벨 가이드 (도구 호출 시 자동 주입)
- tool.json에 `"guide_file": "파일명.md"` 추가
- 에이전트가 이 패키지의 도구를 처음 호출할 때 자동으로 가이드 내용이 주입됨
- 파일 위치: 패키지 폴더 내 (예: `installed/tools/web-builder/web_builder_guide.md`)

#### (B) 시스템 레벨 가이드 (search_guide로 검색 가능)
- `data/guides/` 폴더에 마크다운 파일 작성
- `data/guide_db.json`에 항목 추가 (id, name, description, keywords, file)
- 에이전트가 `search_guide("키워드")`로 검색하여 참조
- 여러 패키지에 걸친 워크플로우 설명에 적합

---

## 패키지 설치 — 완전한 등록 절차

### UI를 통한 설치 (일반적인 경우)
`POST /packages/{id}/install` API 또는 UI 도구 상자에서 설치하면 `package_manager.py`가 자동으로:
1. 패키지 폴더를 `not_installed/` → `installed/`로 이동
2. tool.json, handler.py 검증
3. inventory.md 자동 업데이트
4. (선택) `ibl_usage_generator`로 새 도구의 기본 용례를 RAG에 추가

**패키지 설치는 IBL 어휘를 자동 추가하지 않는다.** 패키지가 새 IBL 액션으로 노출되어야 하면 `data/ibl_nodes_src/<node>.yaml`에 액션을 직접 추가하고 `python3 scripts/build_ibl_nodes.py`를 실행한다. ([[architecture_ibl_unification]])

### 수동 설치 (패키지 폴더를 직접 생성한 경우)
패키지 폴더를 `installed/tools/`에 직접 만들면 된다.

**필수 파일 구조:**
```
installed/tools/{package_id}/
├── tool.json          # 필수 — 도구 정의
├── handler.py         # 필수 — execute(tool_name, tool_input, project_path) 함수
├── manifest.json      # 권장 — 패키지 메타데이터
└── tools/             # 실제 도구 모듈들
```

IBL 어휘 추가가 필요하면 별개 작업:
```bash
# data/ibl_nodes_src/<node>.yaml 편집 후
python3 scripts/build_ibl_nodes.py          # 빌드
python3 scripts/build_ibl_nodes.py --check  # 검증
# 백엔드의 인메모리 캐시는 invalidate_cache() 또는 재시작으로 갱신
```

**가이드 파일 등록** (있는 경우):
- 패키지 레벨: tool.json에 `"guide_file": "가이드파일명.md"` 필드 추가
- 시스템 레벨: `data/guide_db.json`에 항목 추가 + `data/guides/`에 파일 작성

### 패키지 제거
`POST /packages/{id}/uninstall`이 패키지 폴더를 `not_installed/`로 이동한다. **IBL 어휘는 자동 제거되지 않음** — 이 패키지가 노출하던 IBL 액션이 src에 있다면 직접 정리해야 한다 (`ibl_nodes_src/<node>.yaml`에서 제거 → 재빌드).

### 주의사항
- **노드 추가 금지**: 기존 6개 노드(sense, self, limbs, others, engines, table)만 사용. 새 노드는 `data/ibl_nodes_src/meta.yaml`/`scripts/build_ibl_nodes.py`(NODE_ORDER) 변경 + 라우팅 코드 합의 후 별건 작업.
- **액션 이름 충돌**: 같은 노드에 같은 이름의 액션이 이미 있으면 src 빌드가 후행 정의로 덮어쓰니, 접두사를 붙여 구분할 것 (예: `radio_play`, `radio_search`).
- **빌드 산출물 직접 편집 금지**: `data/ibl_nodes.yaml` 첫 줄의 `# GENERATED` 헤더 확인. 수정 시 다음 빌드에서 원복된다.

---

<!-- IBL_STATS:START -->
## 현재 설치된 도구 패키지 (41개 — 빌드 파생)

**op 분기 28 패키지** (2026-05-28 dispatcher 표준화 — 모두 모듈 레벨 `_OP_DISPATCHERS` dict 노출, `build_ibl_nodes.py --check` 가 AST 정확 비교): android · blog · browser-action · bulletin · business · cctv · community-portal · computer-use · context7 · culture · family-news · **finance-record** · guest-helper · health-record · investment · lecture_workspace · **media_producer** · memory · music-player · **notebook** · pc-manager · public-files · radio · real-estate · study · system_essentials · web-builder · youtube. (전체 op 분기 액션은 **69개** — 그중 일부는 backend-native 라우팅이라 패키지 밖: `others:board/feed/follow/nostr` · `self:goal/manage_events/output/package/switch/trigger/workflow` · `sense:world`.)

> location-services 는 op 분기 목록에서 빠졌다 — 유일한 op 액션이던 `sense:travel`(항공·호텔)이 은퇴하면서(국내 숙박은 `sense:stay` 가 source 분기로 승계) op 보유 액션이 0이 됐다.
<!-- IBL_STATS:END -->

> 아래 표의 **행 집합은 빌드가 관리**한다(은퇴 행 자동 삭제·신설 행 자동 추가 — tool.json 설명으로). 설명 산문은 문서 소유라 풍부하게 고쳐도 보존된다.

<!-- PACKAGES_TABLE:START -->
| ID | 이름 | 설명 |
|----|------|------|
| ai-ops | AI Ops (원샷 낱말) | 원샷 AI 낱말 — 통화 대수 세 자리(입구 self:struct=비정형→items 구조화 · 중간 table:ai=items→items 의미  |
| android | Android | 안드로이드 폰 화면 조작 — `[limbs:android]{op}` 단일 센터피스 (snapshot/tap/type/swipe/key/long_press/open_app). 집 PC=ADB+uiautomator(USB) / 폰 자신=네이티브 AccessibilityService(USB 불필요) — 핸들러가 프로파일로 분기. 폰 온디맨드 감각(`sense:here`/`listen`/`see`/`phone`) 핸들러도 이 패키지 |
| blog | Blog | 블로그 RAG 검색 및 인사이트 분석 (진실 소스=Obsidian vault, DB는 파생 검색 인덱스) |
| browser-action | Browser Action | Playwright 기반 브라우저 자동화 v5.0 (36개 도구: ref/CSS selector, stealth, 쿠키 동의 자동처리, 네트워크 캡처, vision 모드, 다중 탭/iframe, 동적 콘텐츠 대기, 다단계 폴백 추출, CDP 타임아웃) |
| bulletin | Bulletin | 로그인 없는 자유게시판 `[others:bulletin]` — 게시판마다 공개 주소 `/b/<5자>`, 주소 아는 사람이 로그인 없이 글·사진 게시 |
| business | Business | 비즈니스 관계 및 연락처(이웃) 관리 |
| cctv | CCTV | CCTV/웹캠 관련 도구 |
| cloudflare | Cloudflare | Cloudflare 서비스 통합 (Pages, Workers, R2, D1, Tunnel) |
| community-portal | Community Portal | 개인 포털 `[others:portal]` — `/h/<5자>/` 다중 포털, 회원=이웃 CRM 레벨 0~4, 진열 다이얼·회원 실행 게이트·감사 로그 |
| computer-use | Computer Use | 컴퓨터 사용 자동화 |
| contest | Contest | AI 공모전·경진대회 검색 (Kaggle, `sense:contest`) |
| context7 | Context7 | Context7 라이브러리 문서 검색 |
| culture | Culture | 공연(KOPIS), 도서(도서관 정보나루), Project Gutenberg 고전 원문, 한국고전종합DB 등 문화예술 정보 조회 |
| data-ops | Data Ops | 통화 변환자 9동사 (filter/sort/take/select/dedup/groupby/join/union/merge) — 순수 변환. `group: transform`, `scope: workspace`, `runs_on: anywhere`. 파이프(`>>`·`&`)와 같은 닫힌 계급. + 표준 코어 문서 emitter `table:structure`·`table:document` (2026-07-03 media_producer서 이관) |
| family-news | Family News | 가족신문 `[others:family_news]` — 폰(USB) 사진으로 판 조판→`/n/<5자>` 누적 발행, 방명록·가족 사진 업로드 |
| finance-record | Finance Record | 재무 원장 `[self:finance]{op}` — 소비(지출·수입 거래)와 소유(자산·부채)를 **주체(owner) 축**(개인/회사)으로 한 원장에. 폰 결제 알림 수거(`op:sync`)·다형 입력 적재(`ingest_engine` 공용). 2026-08-14 `[self:spend]` 흡수 |
| guest-helper | Guest Helper | USB 손발 — 발급 `[self:limb]{op}`(USB 페이로드 생성·승인·폐기) + 조작 `[limbs:guestpc]{op}`(셸/파일). 헬퍼=Go 단일파일, 허브로 아웃바운드(그 PC 방화벽 무설정). 눈 없음(셸·파일만) |
| health-record | Health Record Manager | 건강 정보 기록/관리 (혈압, 혈당, 체중, 증상, 투약) |
| ibl-core | IBL Core | IBL 핵심 도구 |
| investment | Investment | 한국/미국 주가, 재무제표, 공시, 뉴스, 암호화폐 분석 |
| kosis | KOSIS | 통계청 KOSIS API 국가통계 조회 |
| lecture_workspace | Lecture Workspace | 강의 워크스페이스 (강의/슬라이드/재료/데크 op 분기) |
| legal | Legal | 대한민국 법률 정보 검색 (법령, 판례, 행정규칙, 자치법규 등) |
| location-services | Location Services | 위치 기반 서비스 (날씨, 맛집, 길찾기, 여행 정보, 숙박·한달살기 `sense:stay`) |
| media_producer | Media Producer | 홍보용 슬라이드, HTML 기반 MP4 동영상, AI 이미지·아이콘 생성(`engines:icon` 폰-로컬) |
| memory | Memory | 심층 메모리 (자동 시스템: 연상기억 검색 + 경험 증류) |
| music-player | Music Player | 내 음악 라이브러리 `[self:music]`(op 14) — 폴더 스캔·태그·앨범아트, **폴더 단위** 탐색·연속재생·검색·플레이리스트·정지. 재생=표면의 `<audio>` + `/music/stream`. ★2026-07-28 정리: AI 추천·관련곡 그래프·앨범/아티스트 뷰 은퇴(되살리지 말 것 — 남긴 축은 폴더) |
| notebook | Notebook | 근거 고정 질의 `[self:notebook]{op}` — 문서 더미(PDF·텍스트·유튜브 자막·웹 URL)에 이름 붙여 두고 **소스 안에서만** 답하며 인용을 단다(NotebookLM 로컬판). 인용은 코드가 원문에서 추출=환각 차단, 근거 없으면 `not_in_sources` 정직 반환. 색인=ko-sroberta+sqlite-vec+FTS5(★해마 모델 아님), `pc_only` |
| pc-manager | PC Manager | PC 파일 탐색, 외장하드 관리, 저장소 스캔 |
| photo-manager | Photo Manager | 사진/동영상 메타데이터 수집, 갤러리, 중복 탐지 |
| public-files | Public Files | 공개 파일 `[others:showcase]` — `/s/<5자>/` 로 디스크의 폴더를 그대로 공개(EXIF 제거·동영상 스트리밍 트랜스코드·자막) |
| radio | Radio | 인터넷 라디오 검색 및 재생 |
| real-estate | Real Estate | 부동산 시세·매물 — 국토부 실거래가 + 직방·네이버부동산 현재 매물 (`sense:realty{source}`) |
| shopping-assistant | Shopping Assistant | 새 상품 가격비교 `[sense:search_shopping]`(다나와 — used/all·naver 축은 2026-08-04 은퇴) + 중고 매물 `[sense:used]{source: bunjang/danggeun/joongna/naver}` + 프리랜서·외주 `[sense:freelance]`(크몽) |
| startup | Startup | 창업지원 사업공고 검색 (K-Startup, 중소벤처기업부) |
| study | Study Helper | 학술 논문 검색/다운로드 (OpenAlex, arXiv, Semantic Scholar 등) + 국회도서관 국가학술정보 인물/학위논문(`sense:researcher`·`sense:paper source:nanet`) + 개체 해소(`sense:entity` Wikidata) |
| system_essentials | System Essentials | 파일 읽기/쓰기/검색(rg 고속 경로+인코딩 폴백), todo, 계획 모드, 이웃 조회, 웹앱 등기부 `[self:webapp]{op}`(파생 우선 — 진실 소스 7곳 재계산 + 전 함대 생존 실측) |
| visualization | Visualization | 범용 데이터 시각화 (차트/그래프 PNG/HTML) |
| web | Web Tools | 통합 검색 `[sense:search]{source: ddg/naver/gnews/hn/guardian}`(2026-08-05 어휘 압축 — 구 web-kr 네이버·study 가디언 흡수), 크롤링, RSS 피드, **신문 발행 `[engines:newspaper]`**(2026-08-15 스위치화 — prompt_hidden, 신문 계기 발행 버튼 전용) |
| web-builder | Web Builder | 홈페이지 제작/관리/배포 통합 도구 |
| youtube | Youtube | YouTube 영상 정보, 자막 추출, 다운로드 |
<!-- PACKAGES_TABLE:END -->

**미설치 대기(`not_installed/`)**: house-designer · music-composer · nodejs · publishing · python-exec · remotion-video(2026-08-05 은퇴 — 영상 정본=`[self:deck]{op:"video"}`) · spending(2026-08-14 은퇴 — 재무 정본=`[self:finance]`) — 전체 카탈로그는 배포되되 큐레이션된 소수만 기본 활성(코어/사용자 경계는 `data/core_manifest.json`).

**삭제된 패키지(디렉토리째 없음, 되살리지 말 것)**: `web-collector`(2026-08-15 — `sense:collect` 은퇴, `sense:crawl` 이 상위호환) · `local-info`(2026-08-15 — 지역정보 3형제 은퇴, `[sense:search]{source:"naver", type:"cafe"}` 가 승계. ★`area` 기본값 "오송" 하드코딩 = 세계의 명사가 코드에 박힌 헌법 위반이라 패키지와 함께 소멸) · `web-kr`(2026-08-05 — 네이버 검색이 `[sense:search]{source}` 로 흡수). 백업=`data/_backups/2026-08-15_*`.


**참고**: cloudflare 패키지의 `cf_tunnel` 도구는 원격 Finder 시스템의 Cloudflare Tunnel 설정을 자동화합니다. → [remote_access.md](remote_access.md)

---

<!-- EXT_COUNT:START -->
## 백엔드 코어 모듈 (extensions/) — 5개
<!-- EXT_COUNT:END -->

`installed/extensions/`에 위치한 모듈들은 에이전트가 호출하는 도구가 아니라 백엔드 시스템 내부에서 사용되는 코어 모듈입니다.
(prompt-generator·scheduler·switch-runner 는 pre-IBL 휴면 사본이라 2026-08-13 은퇴 — 정본은 backend/ 의 prompt_builder·scheduler·switch_runner)

| ID | 설명 |
|----|------|
| conversation | 대화 이력 관리 (conversation_db) |
| gmail | Gmail 연동 |
| indienet | 외부 메신저 연동 (Nostr 기반) |
| notification-system | 알림 시스템 |
| websocket-chat | WebSocket 기반 실시간 채팅 |

---

## 외부 폴더 등록
사용자의 기존 폴더를 패키지로 등록할 수 있습니다. AI가 폴더를 분석하여 적절한 `tool.json`과 `handler.py` 생성을 제안할 수 있습니다.

---

## 도구 상자 & 패키지 공유 (Nostr)

내가 만든 도구 패키지를 다른 IndieBiz 사용자들과 공유할 수 있습니다.

### 패키지 공개하기
1. 도구 상자에서 설치된 패키지의 "Nostr에 공개" 버튼 클릭
2. 설치 방법이 AI에 의해 자동 생성됨 (수정 가능)
   - AI가 패키지 전체(tool.json, handler.py, requirements.txt 등)를 분석
   - 다른 AI 개발자가 같은 기능을 구현할 수 있는 정보 생성
3. 선택적으로 사인(서명) 추가
4. 공개 버튼 클릭

공개된 패키지는 `#indiebizOS-package` 해시태그로 Nostr 네트워크에 게시됩니다.

### 다른 사용자의 패키지 검색/설치
1. 도구 상자에서 "도구 검색" 버튼 클릭
2. Nostr 네트워크에서 공개된 패키지 검색
3. 패키지 선택하여 상세 정보 확인
4. "설치" 클릭 시 시스템 AI가 보안/품질/호환성 검토 후 설치

---

## API 엔드포인트
- `GET /packages` - 전체 패키지 목록
- `GET /packages/installed` - 설치된 패키지
- `GET /packages/available` - 설치 가능한 패키지
- `POST /packages/{id}/install` - 설치
- `POST /packages/{id}/uninstall` - 제거
- `GET /tools` - 활성 도구 목록
- `POST /packages/{id}/generate-install-instructions` - AI 기반 설치 방법 생성
- `POST /packages/publish-to-nostr` - Nostr에 패키지 공개
- `GET /packages/search-nostr` - Nostr에서 패키지 검색

---
*최근 변경(2026-08-21): 패키지 표 행 집합=빌드 관리(산문 행 불가침)·수치=파생 마커. 이력 정본=git log·changelog.log(`[self:body]` 회상) — 꼬리에 이력을 쌓지 말 것(2026-08-21 다이어트, 전문=직전 git 판).*
