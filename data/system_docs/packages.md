# 도구 패키지 시스템 가이드

이 문서는 IndieBiz OS의 도구 패키지 설치/제거 방법을 정의합니다.
시스템 AI는 패키지 관련 작업 시 반드시 이 문서를 참조해야 합니다.

## 핵심 개념

### 도구 패키지란?
에이전트가 동적으로 로딩하여 사용하는 확장 기능입니다. 에이전트는 실행 시 필요한 도구를 패키지에서 불러와 사용합니다.

### 폴더 구조
- **not_installed/tools/**: 설치 가능한 패키지 (아직 설치 안 됨)
- **installed/tools/**: 설치 완료된 패키지 (에이전트가 사용 가능)
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
description에 모든 내용을 넣지 않고, 도구가 실제 호출될 때만 가이드를 주입하여 토큰을 절약합니다.
상세 내용은 `guide_file.md` 문서를 참조하세요.

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
  node: informant            # IBL 자동 병합 (Phase 21: statistics → informant)
  action_name: search_statistics
  description: "통계표 목록 검색"
```

api_engine 라우팅 액션들이 이 방식을 사용합니다.

### 3. ibl_actions.yaml - IBL 노드 액션 등록 (선택)

패키지의 도구를 IBL 노드 액션으로 노출하려면 `ibl_actions.yaml`을 작성해야 한다.
이 파일은 에이전트가 `execute_ibl`로 호출하는 노드 액션(예: `forge.create_site`, `source.search`)을 정의한다.

```yaml
node: forge               # 어떤 노드에 등록할지 (forge, source, system 등 기존 노드)
actions:
  create_site:             # 액션 이름 (노드 내에서 유일해야 함)
    description: 웹사이트 프로젝트 생성
    router: handler        # handler.py로 라우팅
    tool: site_manager     # handler.py에서 매핑할 도구명
    target_key: site_name  # 자연어에서 추출한 대상이 매핑될 파라미터
    default_input:         # 기본 입력값 (선택)
      action: create
  add_component:
    description: 웹사이트에 컴포넌트 추가
    target_description: 컴포넌트 이름
    router: handler
    tool: component_manager
    target_key: component_name
    default_input:
      action: add
guides:                    # 이 노드에서 사용할 가이드 파일 (선택)
- web-builder/web_builder_guide.md
```

**중요**: `ibl_actions.yaml`을 작성하는 것만으로는 등록이 완료되지 않는다.
반드시 `register_actions()`를 호출하여 `ibl_nodes.yaml`에 병합해야 한다.

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
3. **`register_actions(package_id)` 호출** → ibl_actions.yaml의 액션을 ibl_nodes.yaml에 병합
4. inventory.md 자동 업데이트

### 수동 설치 (패키지 폴더를 직접 생성한 경우)
패키지 폴더를 `installed/tools/`에 직접 만들면 된다.

**필수 파일 구조:**
```
installed/tools/{package_id}/
├── tool.json          # 필수 — 도구 정의
├── handler.py         # 필수 — execute(tool_name, tool_input, project_path) 함수
├── manifest.json      # 권장 — 패키지 메타데이터
├── ibl_actions.yaml   # IBL 액션 사용 시 필수
└── tools/             # 실제 도구 모듈들
```

**IBL 액션 자동 등록:**
서버 시작 시 `_auto_register_packages()`가 자동 실행되어, `ibl_actions.yaml`이 있지만 아직 `_ibl_provenance.yaml`에 등록되지 않은 패키지를 감지하고 `register_actions()`를 호출한다. **폴더만 넣고 서버를 재시작하면 IBL 액션이 자동 등록된다.**

서버 재시작 없이 즉시 등록하려면:
```bash
cd /path/to/indiebizOS/backend
python3 -c "from ibl_action_manager import register_actions; print(register_actions('패키지ID'))"
```

**가이드 파일 등록** (있는 경우):
- 패키지 레벨: tool.json에 `"guide_file": "가이드파일명.md"` 필드 추가
- 시스템 레벨: `data/guide_db.json`에 항목 추가 + `data/guides/`에 파일 작성

### 패키지 제거
```bash
# IBL 액션 해제
python3 -c "from ibl_action_manager import unregister_actions; print(unregister_actions('패키지ID'))"
```
- `_ibl_provenance.yaml`에서 해당 패키지 소유 액션을 찾아 `ibl_nodes.yaml`에서 제거
- guides도 함께 제거됨

### 주의사항
- **ibl_actions.yaml의 node 값은 기존 노드여야 한다** (forge, source, system 등). 존재하지 않는 노드를 지정하면 경고 후 건너뜀.
- **액션 이름 충돌**: 같은 노드에 이미 같은 이름의 액션이 다른 패키지 소유로 등록되어 있으면 건너뜀. 접두사를 붙여 구분할 것 (예: `radio_play`, `radio_search`).
- **register_actions() 없이 ibl_actions.yaml만 편집하면 아무 효과 없음**. 반드시 호출해야 함.

---

## 현재 설치된 도구 패키지 (35개)

| ID | 이름 | 설명 |
|----|------|------|
| android | Android | ADB를 통한 안드로이드 기기 관리 (SMS, 통화기록, 연락처, 앱) |
| blog | Blog | 블로그 RAG 검색 및 인사이트 분석 |
| browser-action | Browser Action | Playwright 기반 브라우저 자동화 (클릭/입력/스크롤/콘텐츠 추출) |
| business | Business | 비즈니스 관계 및 연락처(이웃) 관리 |
| cctv | CCTV | CCTV/웹캠 관련 도구 |
| cloudflare | Cloudflare | Cloudflare 서비스 통합 (Pages, Workers, R2, D1, Tunnel) |
| computer-use | Computer Use | 컴퓨터 사용 자동화 |
| culture | Culture | 공연(KOPIS), 도서(도서관 정보나루) 등 문화예술 정보 조회 |
| health-record | Health Record Manager | 건강 정보 기록/관리 (혈압, 혈당, 체중, 증상, 투약) |
| house-designer | House Designer | 건축 설계 (평면도, 3D뷰) |
| ibl-core | IBL Core | IBL 핵심 도구 |
| investment | Investment | 한국/미국 주가, 재무제표, 공시, 뉴스, 암호화폐 분석 |
| kosis | KOSIS | 통계청 KOSIS API 국가통계 조회 |
| legal | Legal | 대한민국 법률 정보 검색 (법령, 판례, 행정규칙, 자치법규 등) |
| local-info | Local Info | 지역 정보 도구 |
| location-services | Location Services | 위치 기반 서비스 (날씨, 맛집, 길찾기, 여행 정보) |
| media_producer | Media Producer | 홍보용 슬라이드, HTML 기반 MP4 동영상, AI 이미지 생성 |
| memory | Memory | 대화 이력, 심층 메모리 관리 |
| music-composer | Music Composer | ABC 악보 기반 작곡, MIDI 생성, 오디오 변환 |
| nodejs | Nodejs | Node.js/JavaScript 코드 실행 |
| pc-manager | PC Manager | PC 파일 탐색, 외장하드 관리, 저장소 스캔 |
| photo-manager | Photo Manager | 사진/동영상 메타데이터 수집, 갤러리, 중복 탐지 |
| python-exec | Python Exec | Python 코드 실행 |
| radio | Radio | 인터넷 라디오 검색 및 재생 |
| real-estate | Real Estate | 국토교통부 부동산 실거래가 API |
| remotion-video | Remotion Video | React/Remotion 기반 프로그래밍 방식 동영상 생성 (TSX → MP4) |
| shopping-assistant | Shopping Assistant | 네이버 쇼핑, 다나와 가격 비교 |
| startup | Startup | 창업지원 사업공고 검색 (K-Startup, 중소벤처기업부) |
| study | Study Helper | 학술 논문 검색/다운로드 (OpenAlex, arXiv, Semantic Scholar 등) |
| system_essentials | System Essentials | 파일 읽기/쓰기/검색, todo, 계획 모드, 이웃 조회 |
| visualization | Visualization | 범용 데이터 시각화 (차트/그래프 PNG/HTML) |
| web | Web Tools | 웹 검색, 크롤링, 뉴스, 신문 생성, 즐겨찾기 |
| web-builder | Web Builder | 홈페이지 제작/관리/배포 통합 도구 |
| web-collector | Web Collector | 웹 데이터 수집/스크래핑 |
| youtube | Youtube | YouTube 영상 정보, 자막 추출, 다운로드 |

**참고**: cloudflare 패키지의 `cf_tunnel` 도구는 원격 Finder 시스템의 Cloudflare Tunnel 설정을 자동화합니다. → [원격 Finder 문서](remote_finder.md)

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
*마지막 업데이트: 2026-02-22*
