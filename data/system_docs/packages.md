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

### 2. handler.py - 실행 로직 표준 템플릿
`execute(tool_name, tool_input, project_path)` 함수를 포함해야 합니다.

```python
def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """도구 실행 함수"""
    if tool_name == "도구명":
        # 로직 구현
        return "결과"
    return f"알 수 없는 도구: {tool_name}"
```

---

## 현재 설치된 도구 패키지 (27개)

| ID | 이름 | 설명 |
|----|------|------|
| android | Android | ADB를 통한 안드로이드 기기 관리 (SMS, 통화기록, 연락처, 앱) |
| blog | Blog | 블로그 RAG 검색 및 인사이트 분석 |
| browser-action | Browser Action | Playwright 기반 브라우저 자동화 (클릭/입력/스크롤/콘텐츠 추출) |
| business | Business | 비즈니스 관계 및 연락처(이웃) 관리 |
| cloudflare | Cloudflare | Cloudflare 서비스 통합 (Pages, Workers, R2, D1, Tunnel) |
| culture | Culture | 공연(KOPIS), 도서(도서관 정보나루) 등 문화예술 정보 조회 |
| health-record | Health Record Manager | 건강 정보 기록/관리 (혈압, 혈당, 체중, 증상, 투약) |
| investment | Investment | 한국/미국 주가, 재무제표, 공시, 뉴스, 암호화폐 분석 |
| kosis | KOSIS | 통계청 KOSIS API 국가통계 조회 |
| legal | Legal | 대한민국 법률 정보 검색 (법령, 판례, 행정규칙, 자치법규 등) |
| location-services | Location Services | 위치 기반 서비스 (날씨, 맛집, 길찾기, 여행 정보) |
| media_producer | Media Producer | 홍보용 슬라이드, HTML 기반 MP4 동영상, AI 이미지 생성 |
| music-composer | Music Composer | ABC 악보 기반 작곡, MIDI 생성, 오디오 변환 |
| nodejs | Nodejs | Node.js/JavaScript 코드 실행 |
| pc-manager | PC Manager | PC 파일 탐색, 외장하드 관리, 저장소 스캔 |
| photo-manager | Photo Manager | 사진/동영상 메타데이터 수집, 갤러리, 중복 탐지 |
| python-exec | Python Exec | Python 코드 실행 |
| real-estate | Real Estate | 국토교통부 부동산 실거래가 API |
| remotion-video | Remotion Video | React/Remotion 기반 프로그래밍 방식 동영상 생성 (TSX → MP4) |
| shopping-assistant | Shopping Assistant | 네이버 쇼핑, 다나와 가격 비교 |
| startup | Startup | 창업지원 사업공고 검색 (K-Startup, 중소벤처기업부) |
| study | Study Helper | 학술 논문 검색/다운로드 (OpenAlex, arXiv, Semantic Scholar 등) |
| system_essentials | System Essentials | 파일 읽기/쓰기/검색, todo, 계획 모드, 이웃 조회 |
| visualization | Visualization | 범용 데이터 시각화 (차트/그래프 PNG/HTML) |
| web | Web Tools | 웹 검색, 크롤링, 뉴스, 신문 생성, 즐겨찾기 |
| web-builder | Web Builder | 홈페이지 제작/관리/배포 통합 도구 |
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
*마지막 업데이트: 2026-02-10*
