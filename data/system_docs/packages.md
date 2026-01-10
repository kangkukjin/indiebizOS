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
- 파일 복사나 삭제 없이 폴더 이동만 수행 (비파괴적)

---

## 도구 패키지 품질 표준

모든 도구는 설치되거나 개발될 때 다음 **품질 표준**을 반드시 준수해야 합니다.

### 1. 자가 진단 (Self-Diagnosis)
- 도구 실행 전, 필요한 외부 바이너리(예: `adb`, `ffmpeg`, `docker` 등)가 시스템에 존재하는지 `shutil.which()` 등으로 먼저 확인
- 필요한 라이브러리가 없을 경우, **"어떤 프로그램이 없는지"**와 **"예상되는 설치 경로"**를 함께 안내

### 2. 상세한 에러 보고 (Detailed Error Reporting)
- 외부 명령 실행 시 `stderr`(표준 에러)를 반드시 캡처
- 에러 발생 시 시스템 에러 메시지 원문을 사용자에게 전달
- `try...except` 블록을 사용하여 예상치 못한 파이썬 오류도 상세히 보고

### 3. 경로 유연성 (Path Resilience)
- 특정 경로에 의존하지 않음
- 흔히 도구가 설치되는 경로들을 알고리즘적으로 탐색하거나 환경 변수 활용

---

## 필수 파일 형식

### 1. tool.json - 도구 정의 (배열 형식)
```json
[
  {
    "name": "도구_이름",
    "description": "도구 설명",
    "input_schema": {
      "type": "object",
      "properties": {
        "param1": { "type": "string", "description": "설명" }
      },
      "required": ["param1"]
    }
  }
]
```

### 2. handler.py - 실행 로직 표준 템플릿
```python
import subprocess
import shutil
import os

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    # 1. 의존성 체크
    if not shutil.which("필요한_명령어"):
        return "에러: '필요한_명령어'를 찾을 수 없습니다. PATH 설정을 확인하세요."

    # 2. 실행 및 에러 캡처
    try:
        result = subprocess.run(["명령어"], capture_output=True, text=True)
        if result.returncode != 0:
            return f"실행 실패 (코드 {result.returncode}): {result.stderr}"
        return result.stdout
    except Exception as e:
        return f"예외 발생: {str(e)}"
```

### 3. README.md (선택사항)
- 패키지 설명 및 사용법
- AI가 패키지를 이해하는 데 도움

---

## 현재 설치된 도구 패키지 (12개)

| ID | 이름 | 설명 |
|----|------|------|
| android | Android | 안드로이드 기기 관리 (adb) |
| blog | Blog | 블로그 RAG 검색 및 인사이트 분석 |
| browser-automation | Browser Automation | 웹 브라우저 자동화 (Playwright) |
| health-record | Health Record Manager | 개인 건강 정보 저장/관리 (측정값, 증상, 투약, 검사결과) |
| information | Information & Publishing | API Ninjas, 여행 정보, 출판 도구 |
| nodejs | Nodejs | JavaScript/Node.js 코드 실행 |
| pc-manager | Pc Manager | 파일 및 저장소 관리 |
| python-exec | Python Exec | Python 코드 실행 |
| system_essentials | System Essentials | 파일 관리, 검색, 시스템 유틸리티 |
| web-crawl | Web Crawl | 웹페이지 크롤링 |
| web-search | Web Search | 웹 검색 엔진 (DuckDuckGo, Google News) |
| youtube | Youtube | 유튜브 동영상/오디오 관리 |

---

## 외부 폴더 등록

사용자의 기존 폴더를 패키지로 등록할 수 있습니다:
1. `POST /packages/analyze-folder` - 폴더 분석
2. `POST /packages/analyze-folder-ai` - AI가 폴더 분석 및 패키지화 제안
3. `POST /packages/register` - 패키지로 등록

---

## API 엔드포인트

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/packages` | GET | 전체 패키지 목록 |
| `/packages/installed` | GET | 설치된 패키지 목록 |
| `/packages/available` | GET | 설치 가능한 패키지 목록 |
| `/packages/{id}` | GET | 패키지 상세 정보 |
| `/packages/{id}/install` | POST | 패키지 설치 |
| `/packages/{id}/uninstall` | POST | 패키지 제거 |
| `/tools` | GET | 활성 도구 목록 |

---
*마지막 업데이트: 2026-01-09*
