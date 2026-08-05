---
title: 도구 패키지 시스템
scope: 패키지 구조(handler/tool.json), 설치 절차, 42개 패키지 목록. IBL 어휘 등록은 각 패키지의 ibl_actions.yaml(능력 자기완결, ibl.md 참조). op 분기 패키지 26개는 `_OP_DISPATCHERS` 표준 채택.
owner_code: package_manager.py, tool_loader.py
last_updated: 2026-08-04
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
- `data/guides/` 폴더에 마크다운 파일 저장 (현재 28개)
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

## 현재 설치된 도구 패키지 (42개)

**op 분기 26 패키지** (2026-05-28 dispatcher 표준화 — 모두 모듈 레벨 `_OP_DISPATCHERS` dict 노출, `build_ibl_nodes.py --check` 가 AST 정확 비교): android · blog · browser-action · bulletin · business · cctv · community-portal · computer-use · context7 · culture · family-news · guest-helper · health-record · investment · lecture_workspace · memory · music-player · pc-manager · public-files · radio · real-estate · study · system_essentials · web-builder · web-collector · youtube. (전체 op 분기 액션은 67개 — 그중 12개는 backend-native 라우팅이라 패키지 밖: `others:board/feed/follow/nostr` · `self:goal/manage_events/output/package/switch/trigger/workflow` · `sense:world`.)

> location-services 는 op 분기 목록에서 빠졌다 — 유일한 op 액션이던 `sense:travel`(항공·호텔)이 은퇴하면서(국내 숙박은 `sense:stay` 가 source 분기로 승계) op 보유 액션이 0이 됐다.

| ID | 이름 | 설명 |
|----|------|------|
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
| guest-helper | Guest Helper | USB 손발 — 발급 `[self:limb]{op}`(USB 페이로드 생성·승인·폐기) + 조작 `[limbs:guestpc]{op}`(셸/파일). 헬퍼=Go 단일파일, 허브로 아웃바운드(그 PC 방화벽 무설정). 눈 없음(셸·파일만) |
| health-record | Health Record Manager | 건강 정보 기록/관리 (혈압, 혈당, 체중, 증상, 투약) |
| ibl-core | IBL Core | IBL 핵심 도구 |
| investment | Investment | 한국/미국 주가, 재무제표, 공시, 뉴스, 암호화폐 분석 |
| kosis | KOSIS | 통계청 KOSIS API 국가통계 조회 |
| lecture_workspace | Lecture Workspace | 강의 워크스페이스 (강의/슬라이드/재료/데크 op 분기) |
| legal | Legal | 대한민국 법률 정보 검색 (법령, 판례, 행정규칙, 자치법규 등) |
| local-info | Local Info | 지역 정보 도구 |
| location-services | Location Services | 위치 기반 서비스 (날씨, 맛집, 길찾기, 여행 정보, 숙박·한달살기 `sense:stay`) |
| media_producer | Media Producer | 홍보용 슬라이드, HTML 기반 MP4 동영상, AI 이미지·아이콘 생성(`engines:icon` 폰-로컬) |
| memory | Memory | 심층 메모리 (자동 시스템: 연상기억 검색 + 경험 증류) |
| music-player | Music Player | 내 음악 라이브러리 `[self:music]`(op 14) — 폴더 스캔·태그·앨범아트, **폴더 단위** 탐색·연속재생·검색·플레이리스트·정지. 재생=표면의 `<audio>` + `/music/stream`. ★2026-07-28 정리: AI 추천·관련곡 그래프·앨범/아티스트 뷰 은퇴(되살리지 말 것 — 남긴 축은 폴더) |
| pc-manager | PC Manager | PC 파일 탐색, 외장하드 관리, 저장소 스캔 |
| photo-manager | Photo Manager | 사진/동영상 메타데이터 수집, 갤러리, 중복 탐지 |
| public-files | Public Files | 공개 파일 `[others:showcase]` — `/s/<5자>/` 로 디스크의 폴더를 그대로 공개(EXIF 제거·동영상 스트리밍 트랜스코드·자막) |
| radio | Radio | 인터넷 라디오 검색 및 재생 |
| real-estate | Real Estate | 부동산 시세·매물 — 국토부 실거래가 + 직방·네이버부동산 현재 매물 (`sense:realty{source}`) |
| shopping-assistant | Shopping Assistant | 네이버 쇼핑, 다나와 가격 비교 + 중고 매물 (`sense:used`) |
| startup | Startup | 창업지원 사업공고 검색 (K-Startup, 중소벤처기업부) |
| study | Study Helper | 학술 논문 검색/다운로드 (OpenAlex, arXiv, Semantic Scholar 등) + 국회도서관 국가학술정보 인물/학위논문(`sense:researcher`·`sense:paper source:nanet`) + 개체 해소(`sense:entity` Wikidata) |
| system_essentials | System Essentials | 파일 읽기/쓰기/검색(rg 고속 경로+인코딩 폴백), todo, 계획 모드, 이웃 조회, 웹앱 등기부 `[self:webapp]{op}`(파생 우선 — 진실 소스 7곳 재계산 + 전 함대 생존 실측) |
| visualization | Visualization | 범용 데이터 시각화 (차트/그래프 PNG/HTML) |
| web | Web Tools | 통합 검색 `[sense:search]{source: ddg/naver/gnews/hn/guardian}`(2026-08-05 어휘 압축 — 구 web-kr 네이버·study 가디언 흡수), 크롤링, **신문 발행 `[engines:newspaper]`**, 즐겨찾기 |
| web-builder | Web Builder | 홈페이지 제작/관리/배포 통합 도구 |
| web-collector | Web Collector | 웹 데이터 수집/스크래핑 |
| youtube | Youtube | YouTube 영상 정보, 자막 추출, 다운로드 |

**미설치 대기(`not_installed/`)**: house-designer · music-composer · nodejs · publishing · python-exec · remotion-video(2026-08-05 은퇴 — 영상 정본=[self:deck]{op:"video"}) — 전체 카탈로그는 배포되되 큐레이션된 소수만 기본 활성(코어/사용자 경계는 `data/core_manifest.json`).


**참고**: cloudflare 패키지의 `cf_tunnel` 도구는 원격 Finder 시스템의 Cloudflare Tunnel 설정을 자동화합니다. → [remote_access.md](remote_access.md)

---

## 백엔드 코어 모듈 (extensions/) — 8개

`installed/extensions/`에 위치한 모듈들은 에이전트가 호출하는 도구가 아니라 백엔드 시스템 내부에서 사용되는 코어 모듈입니다.

| ID | 설명 |
|----|------|
| conversation | 대화 이력 관리 (conversation_db) |
| gmail | Gmail 연동 |
| indienet | 외부 메신저 연동 (Nostr 기반) |
| notification-system | 알림 시스템 |
| prompt-generator | 프롬프트 자동 생성 |
| scheduler | 예약 작업 스케줄러 |
| switch-runner | 스위치 실행기 |
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
*마지막 업데이트: 2026-08-04 — op 분기 27→**26 패키지**/68→**67 액션** 정정(location-services 의 유일 op 액션 `sense:travel` 이 은퇴 — 국내 숙박은 `sense:stay` 가 source 분기로 승계). shopping-assistant 설명에서 중고 스크래핑 축 은퇴 반영(중고는 `[sense:used]` 정본). 이전 — **어휘 +1, 어휘 −6(같은 패키지에서)**: ①**system_essentials 에 `[self:webapp]{op: list/status/register/remove}`** 신설 — 이 패키지의 첫 op 분기 액션(`webapp_registry.py` 형제 모듈, handler 는 `_OP_DISPATCHERS` 표준). **파생 우선 등기부**: 포털·게시판·가족신문·공개파일·정기보고·web-builder `sites.json`·`outputs/web-projects/*/wrangler.toml` 7곳에서 매 호출 재계산(수동 원장은 드리프트한다) + `data/webapps.json` 수동 보충. `status`=전 함대 병렬 HTTP 생존 실측. 가이드 `webapp.md`(guide_db 58). ②**music-player 축소**(op 19→13→14): AI 추천 `compose`·관련곡 그래프 `related/walk/graph`(+🕸️ 커스텀 계기)·앨범/아티스트 뷰를 사용자 판단으로 은퇴하고 **폴더**를 유일한 축으로 남긴 뒤, 라디오의 `stop` 규약을 그대로 빌려 정지를 더했다(폴더 하나가 수백 곡이라 재생 중인 `<audio>` 를 눈으로 찾는 게 불가능했다). 파생 캐시 `edges` 테이블은 폐기, 은퇴 어휘의 해마 용례 15건도 함께 삭제 — **설치/제거 생애주기는 대칭**. 같은 패키지에 `.ape`+cue 시트 색인(CD 통이미지를 곡 단위로)과 못 읽는 형식(wma) 실시간 변환 합류. ③**패키지 위생 가드 둘**: enum↔handler 분기 정합(AST — 핸들러가 아는 값이 스키마에 없던 `realty source:naver` 부류 차단) + desc 규율 lint(≤200자·이름 충돌 세트 변별 필수). ④public-files 의 media 모드가 오디오도 진열·재생, business 아이템이 창고 카탈로그로 자동 진열(`warehouse_catalog.py`), warehouse 방언에 **neocities** 어댑터 + 둘러보기 디렉터리(`warehouse_directory.py`). ★서브모듈 함정(재확인): `/packages/reload` 는 `handler.py` 만 라이브 — 패키지의 `tool_*.py` 는 sys.modules 캐시에 남으므로 백엔드 재시작(또는 backend 파일 touch) 필요. **현 상태: 42개 도구 패키지 + 8개 extensions, 6노드 163 액션**(sense 48·self 52·limbs 18·others 18·engines 14·table 13). 이전(2026-07-25) — **신규 패키지 2 + 어휘 5**: **guest-helper**(USB 손발 — 발급 `[self:limb]{op}` + 조작 `[limbs:guestpc]{op}`, Go 헬퍼가 허브로 아웃바운드·푸시 큐 재사용, 눈 없음=셸/파일만)와 **music-player**(내 음악 `[self:music]` — 스캔·태그·앨범아트·플레이리스트 + 관련곡 그래프[가중 간선 top-10·랜덤 산책·AI 추천 compose], 재생은 서버 무음=표면의 `<audio>`+`/music/stream`) 신설. 기존 패키지 확장: web 에 **`[engines:newspaper]`**(신문 발행 결정화 — 데스크탑 계기 코드에만 살던 레시피를 액션으로, 기본 백그라운드), others 코어에 **`[others:ask]`**(이웃 몸에 자연어 부탁), public-files 에 동영상 생방송 재생(스트리밍 트랜스코드·자막·오프셋 시크), system_essentials `self:grep` 2층화(rg 고속 경로 + 인코딩 폴백). **`runs_on` `mac_only`→`pc_only` 전역 개명**(소스 yaml·검증자·문서 — 그 값의 뜻은 macOS 가 아니라 compute-class). ★서브모듈 함정: `/packages/reload` 는 `handler.py` 만 라이브 — 패키지의 `tool_*.py`·코어 모듈은 sys.modules 캐시에 남으므로 백엔드 재시작(또는 backend 파일 touch) 필요. 당시: 42개 도구 패키지 + 8개 extensions(ai-agent 폐기), 6노드 162 액션(sense 48·self 51·limbs 18·others 18·engines 14·table 13). 이전(2026-07-17) — **공개 표면 가족 신설(커뮤니티당 노드 하나)**: 신규 패키지 — community-portal(`[others:portal]` 개인 포털 `/h/`)·public-files(`[others:showcase]` 공개 파일 `/s/`)·family-news(`[others:family_news]` 가족신문 `/n/`)·bulletin(`[others:bulletin]` 로그인 없는 게시판 `/b/`) + 정기보고 발행 면(`/r/`, 어휘 없음). 그 외 신규: `[sense:stay]`(location-services 숙박)·`[sense:entity]`(study Wikidata)·`[sense:used]`(shopping-assistant 중고)·`[self:install_lib]`(공급망 승인 게이트)·`[engines:icon]`(media_producer 폰-로컬 아이콘). **table 노드 분리**(2026-06-30, engines 변환자/emitter→table). publishing·music-composer는 not_installed 이동. **현 상태: 40개 도구 패키지 + 8개 extensions(ai-agent 폐기), 6노드 157 액션**. 이전(2026-07-02) — **report-viewer 패키지 은퇴 → 정기보고 앱을 어휘 없는 standalone 매니페스트로 재구성**(`data/instruments/report.yaml`). 옛 `self:report` 전용 액션(list/read/latest/new)을 삭제하고, 앱을 일반 부품 조합으로 재작성: 보기=`[self:file_find]`+`[self:read]{blocks}`, 생성=`[others:delegate]{scope: system}`(자율주행 위임), 레시피=가이드 파일. **일반 부품 2가지 강화**(둘 다 앱-비종속·재사용): ①`others:delegate` 에 `scope: system`(시스템 AI 타겟) 추가 — 앱 "생성" 버튼이 자율주행에 자연어 의도를 fire-and-forget. ②`self:read` 가 `blocks` 옵션 + 파이프 이전 step 의 파일경로 자동 바인딩(`file_find | take:1 >> read`). **인프라**: `data/instruments/*.yaml` standalone 앱 매니페스트 소스 신설(`api_launcher_web._derive_instruments` 병합 + `%BASE%` 레포루트 토큰 서버측 치환) + `build_ibl_nodes.validate_standalone_instruments`(저술-시점 [node:action] 참조 검증, 음성테스트 확인). 액션 142→**141**(self:report 삭제, 순증 어휘 0). 해마 self:report 용례 14건 회수(ibl_examples+FTS+ibl_distilled 638→624). 앱 UX 데스크탑·원격 동일 보존. 설계=`docs/APP_AS_MANIFEST_DESIGN.md`. 이전(2026-06-30) — 패키지 목록 정합화(contest 추가로 38개 명시) + **폰 엔진 번들 파생 구조**: 백엔드 코어 모듈(extensions)을 손-유지 리스트(`_ENGINE_MODULES`)가 아니라 `data/bodies/*.json` 몸 프로파일에서 파생(`scripts/build_body_bundle.py`, 3겹 게이트=빌드 재생성+pre-commit `--check`+온디바이스 자가점검) — 새 backend 모듈이 폰에 자동 흐름. 폰 자아 도구 번들은 여전히 `build_ibl_nodes.PHONE_VERIFIED_PACKAGES`+runs_on 파생. 142 액션·38 도구 패키지. 이전(2026-06-27) — 앱 표면 품질 일괄 개선(라디오 즐겨찾기·CCTV 인앱 재생 stream 버튼·여행 날짜+한국 지방공항·투자 TIGER200·날씨 오송·문화 지역·길찾기 거리/예상시간) + 부동산 직방 호가(sense:realty source:zigbang)·AI 공모/창업(sense:contest/startup) + read_guide claude_code 노출 + 폰 네이티브 재빌드. 142 액션(sense 44·self 44·limbs 17·others 11·engines 26)·38 도구 패키지. 이전(2026-06-22) — 38개 도구 패키지(+백엔드 extensions 9). IBL 142 액션. study 패키지에 국회도서관 국가학술정보 기반 인물/학위논문 액션 추가(`sense:researcher`·`sense:paper source:nanet` — 동명이인 분리·국내 학위 추적). 목록에 data-ops(통화 변환자 9동사)·report-viewer 반영. 이전(2026-06-14): 35개 도구 패키지 유지. 폰 자아 번들=22 패키지(runnable 95) — `build_ibl_nodes.PHONE_VERIFIED_PACKAGES` + runs_on 태그로 파생, 폰 못 도는 액션은 맥에 위임. 라이브러리=비계/API=몸 원칙으로 무거운 의존 대신 경량 HTTP 호출(arxiv·shopping 이식 증명, 지연 import). 이전(2026-06-12): business 패키지 도메인 전면 IBL화(self:business/business_item/business_document/work_guideline op + others:neighbor 통합·contact·messages·feed/board/nostr·auto_response + self:phone_sync). 옛 BusinessManager.tsx·NeighborManagerDialog.tsx 은퇴. 이전(2026-06-10): 35개 정합화. 이전(2026-05-28): IBL 단일 진실 소스화*
