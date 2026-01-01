# 패키지 시스템 가이드

이 문서는 IndieBiz OS의 도구 패키지 설치/제거 방법을 정의합니다.
시스템 AI는 패키지 관련 작업 시 반드시 이 문서를 참조해야 합니다.

## 핵심 개념

### available/ vs installed/
- **available/**: 설치 가능한 패키지 (아직 설치 안 됨)
- **installed/**: 설치 완료된 패키지 (실제 동작)

### 설치란?
AI가 `available/`의 패키지를 읽고 이해한 후, 시스템 규칙에 맞게 구현하여 `installed/`에 생성하는 것.

**중요**:
- `available/`의 패키지는 **형식이 자유롭다**. README, 예시 코드, 설명 문서 등 어떤 형태든 AI가 읽고 이해할 수 있으면 된다.
- `installed/`에 설치할 때는 **반드시 시스템 규칙을 따라야** 한다.

---

## 도구 패키지 (tools)

### 용도
AI 에이전트가 호출하는 도구

### 설치 위치
- 설치 전: `data/packages/available/tools/{id}/`
- 설치 후: `data/packages/installed/tools/{id}/`

### 예시
time, python-exec, file-ops, web-request, file-search, browser

---

## 설치 후 규칙 (installed/)

설치된 도구가 동작하려면 다음 규칙을 따라야 한다.

### 필수 파일

#### 1. tool.json - 도구 정의
```json
{
  "name": "도구_이름",
  "description": "도구 설명",
  "input_schema": {
    "type": "object",
    "properties": {
      "param1": {
        "type": "string",
        "description": "파라미터 설명"
      }
    },
    "required": ["param1"]
  }
}
```

한 패키지에 여러 도구가 있으면 배열로:
```json
[
  {"name": "read_file", "description": "...", "input_schema": {...}},
  {"name": "write_file", "description": "...", "input_schema": {...}}
]
```

#### 2. handler.py - 실행 로직
```python
"""
{package-id} 도구 핸들러
"""
import json

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """
    도구 실행

    Args:
        tool_name: 도구 이름 (tool.json의 name과 일치)
        tool_input: AI가 전달한 파라미터
        project_path: 현재 프로젝트 경로

    Returns:
        JSON 형식의 결과 문자열
    """
    if tool_name == "my_tool":
        # 도구 로직 구현
        result = {"success": True, "data": "..."}
        return json.dumps(result, ensure_ascii=False)

    return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)
```

---

## 설치/제거 과정

### 설치
1. `available/tools/{id}/`의 내용을 읽고 이해
2. 시스템 규칙에 맞게 `tool.json`과 `handler.py` 구현
3. `installed/tools/{id}/`에 생성
4. 시스템 재시작 없이 즉시 사용 가능 (동적 로딩)

### 제거
- `installed/tools/{id}/` 폴더 삭제
- 동적 로딩이므로 즉시 반영

---

## 동적 로딩

### 작동 방식
```
1. AI가 도구 호출 → execute_tool(tool_name, tool_input, project_path)
2. 시스템 도구인가? (call_agent, list_agents 등) → 직접 실행
3. 아니면 → installed/tools/에서 handler.py 동적 로드
4. handler.execute(tool_name, tool_input, project_path) 호출
```

### 장점
- 새 도구 설치 시 `ai_agent.py` 수정 불필요
- 핸들러는 1회 로드 후 캐시 (성능 영향 없음)

---

## 시스템 도구 (삭제 불가)

다음 도구는 시스템에 하드코딩되어 있습니다:

| 도구 | 설명 |
|------|------|
| call_agent | 다른 에이전트 호출 |
| list_agents | 에이전트 목록 조회 |
| send_notification | 알림 전송 |
| get_project_info | 프로젝트 정보 조회 |

---

## 내장 기능 (패키지 아님)

다음 기능은 시스템에 내장되어 있어 패키지로 설치/제거하지 않습니다:

- **AI 에이전트 실행**: 다중 AI 에이전트 실행 핵심 모듈
- **대화 히스토리**: 에이전트와 사용자 간 대화 기록 관리
- **Gmail**: 이메일 채널
- **카메라/이미지 입력**: 프론트엔드 WebRTC 사용
- **IndieNet**: Nostr 기반 소셜 네트워크
- **알림 시스템**: 시스템 및 에이전트 알림
- **프롬프트 생성기**: AI 프롬프트 자동 생성
- **스케줄러**: 백그라운드 예약 작업
- **스위치 러너**: 스위치 기반 에이전트 실행
- **WebSocket 채팅**: 실시간 WebSocket 통신
- **Ollama**: 로컬 AI 프로바이더
- **음성 모드**: 음성 입출력 기능 (선택적)

---

## Ollama (로컬 AI) 사용법

Ollama를 사용하면 API 비용 없이 로컬에서 AI를 실행할 수 있습니다.

### 1. Ollama 설치

**macOS/Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
https://ollama.com/download 에서 다운로드

### 2. 모델 다운로드

```bash
ollama pull llama3.2        # 기본 모델 (3B)
ollama pull qwen2.5:7b      # 한국어 좋음
ollama pull mistral         # 가벼운 모델
```

### 3. Ollama 서버 실행

```bash
ollama serve
```
(기본: http://localhost:11434)

### 4. IndieBiz에서 사용

에이전트 설정에서:
- **프로바이더**: `ollama`
- **모델**: 설치한 모델명 (예: `llama3.2`, `qwen2.5:7b`)
- **API 키**: 필요 없음 (빈칸)

### 권장 모델

| 모델 | 크기 | 특징 |
|------|------|------|
| `llama3.2` | 3B | 빠름, 기본 |
| `qwen2.5:7b` | 7B | 한국어 성능 좋음 |
| `mistral` | 7B | 균형 잡힌 성능 |
| `codellama` | 7B | 코딩 특화 |

### 주의사항

- Ollama 서버가 실행 중이어야 함
- GPU가 있으면 더 빠름 (CPU도 가능)
- 7B 모델: RAM 8GB 이상 권장

---
*마지막 업데이트: 2025-12-31*
