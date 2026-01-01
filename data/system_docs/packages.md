# 패키지 시스템 가이드

이 문서는 IndieBiz OS의 도구 패키지 설치/제거 방법을 정의합니다.
시스템 AI는 패키지 관련 작업 시 반드시 이 문서를 참조해야 합니다.

## 핵심 개념

### not_installed/ vs installed/
- **not_installed/**: 설치 가능한 패키지 (아직 설치 안 됨)
- **installed/**: 설치 완료된 패키지 (실제 동작)
- **dev/**: 개발 중인 패키지

### 설치란?
AI가 `not_installed/`의 패키지를 읽고 이해한 후, 시스템 규칙에 맞게 구현하여 `installed/`에 생성하는 것.

---

## 도구 패키지 개발 및 품질 표준 (중요!)

모든 도구는 설치되거나 개발될 때 다음 **품질 표준**을 반드시 준수해야 한다.

### 1. 자가 진단 (Self-Diagnosis)
- 도구 실행 전, 필요한 외부 바이너리(예: `adb`, `ffmpeg`, `docker` 등)가 시스템에 존재하는지 `shutil.which()` 등으로 먼저 확인한다.
- 필요한 라이브러리가 없을 경우, "실패"라고만 하지 말고 **"어떤 프로그램이 없는지"**와 **"예상되는 설치 경로(예: /opt/homebrew/bin 등)"**를 함께 안내한다.

### 2. 상세한 에러 보고 (Detailed Error Reporting)
- 외부 명령 실행 시 `stderr`(표준 에러)를 반드시 캡처한다.
- 에러 발생 시 시스템 에러 메시지 원문을 사용자에게 전달하여, 사용자가 직접 문제를 진단할 수 있게 한다.
- `try...except` 블록을 사용하여 예상치 못한 파이썬 오류도 상세히 보고한다.

### 3. 경로 유연성 (Path Resilience)
- 특정 경로에 의존하지 않는다. 
- 흔히 도구가 설치되는 경로들(`/usr/local/bin`, `/opt/homebrew/bin`, `~/anaconda3/bin` 등)을 알고리즘적으로 탐색하거나, 환경 변수를 최대한 활용한다.

---

## 필수 파일 형식 (installed/)

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

---

## 설치/제거 과정
(이하 생략)

---
*마지막 업데이트: 2026-01-02 23:10 (도구 품질 표준 추가)*
