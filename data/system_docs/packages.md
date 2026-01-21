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

## 현재 설치된 도구 패키지 (19개)

| ID | 이름 | 설명 |
|----|------|------|
| android | Android | 안드로이드 기기 관리 (adb) |
| blog | Blog | 블로그 RAG 검색 및 인사이트 분석 |
| culture | Culture | KCISA 문화정보(전시, 축제) 조회 |
| health-record | Health Record Manager | 개인 건강 정보 저장/관리 |
| information | Information & Publishing | API Ninjas, 여행 정보, 맛집 검색 등 |
| investment | Investment | KRX, DART, SEC 글로벌 금융 데이터 분석 |
| kosis | KOSIS | 통계청 데이터 조회 |
| media_producer | Media Producer | HTML 기반 슬라이드(12종 테마), 영상 제작, AI 이미지 생성 |
| nodejs | Nodejs | JavaScript/Node.js 코드 실행 |
| pc-manager | PC Manager | 파일 및 저장소 관리, 시스템 분석 |
| photo-manager | Photo Manager | 사진 라이브러리 관리 |
| python-exec | Python Exec | Python 코드 실행 |
| read-and-see | Read and See | 문서 읽기 및 시각적 분석 |
| real-estate | Real Estate | 부동산 실거래가 조회 |
| startup | Startup | 창업 지원 정보 |
| study | Study Helper | 학습 및 논문 요약 지원 |
| system_essentials | System Essentials | 파일 관리, 검색, 시스템 유틸리티 |
| visualization | Visualization | 라인/막대/캔들스틱/파이/산점도/히트맵 차트 생성 |
| web | Web Tools | 웹 검색 및 크롤링 |
| youtube | Youtube | 유튜브 동영상/오디오 관리 |

---

## 외부 폴더 등록
사용자의 기존 폴더를 패키지로 등록할 수 있습니다. AI가 폴더를 분석하여 적절한 `tool.json`과 `handler.py` 생성을 제안할 수 있습니다.

---

## API 엔드포인트
- `GET /packages` - 전체 패키지 목록
- `GET /packages/installed` - 설치된 패키지
- `GET /packages/available` - 설치 가능한 패키지
- `POST /packages/{id}/install` - 설치
- `POST /packages/{id}/uninstall` - 제거
- `GET /tools` - 활성 도구 목록

---
*마지막 업데이트: 2026-01-21*
