# 도구 가이드 파일 시스템 (guide_file)

도구 패키지에 상세 사용 가이드를 제공하는 on-demand 주입 시스템입니다.

## 목적

복잡한 도구(영상 제작, 코드 실행 등)는 사용법이 길어서 description에 모두 넣으면 매 대화마다 토큰을 낭비합니다. 가이드 파일 시스템은 **도구가 실제로 호출될 때만** 상세 가이드를 AI 컨텍스트에 주입합니다.

## 동작 원리

```
1. 도구 로드 시: description은 간결하게 유지, guide_file 필드는 AI에게 전달되지 않음
2. AI가 도구 호출: execute_tool()에서 도구 실행 후, 첫 호출이면 가이드를 결과 앞에 붙임
3. 이후 같은 도구 재호출: 가이드 생략 (이미 AI 컨텍스트에 있으므로)
```

## 적용 방법

### 1. 가이드 파일 작성
패키지 폴더에 마크다운 파일을 생성합니다.

```
data/packages/installed/tools/my-package/
├── tool.json
├── handler.py
└── my_guide.md      ← 가이드 파일
```

### 2. tool.json에 guide_file 지정

**개별 도구에 지정** (해당 도구에만 적용):
```json
{
  "tools": [
    {
      "name": "complex_tool",
      "guide_file": "my_guide.md",
      "description": "간결한 한 줄 설명만 작성",
      "input_schema": { ... }
    },
    {
      "name": "simple_tool",
      "description": "이 도구는 가이드 없이 description만으로 충분",
      "input_schema": { ... }
    }
  ]
}
```

**패키지 레벨에 지정** (패키지 내 모든 도구에 적용):
```json
{
  "guide_file": "package_guide.md",
  "tools": [
    { "name": "tool_a", "description": "..." },
    { "name": "tool_b", "description": "..." }
  ]
}
```

개별 도구의 guide_file이 패키지 레벨보다 우선합니다.

## 기술 구현

### 관련 파일
- `backend/tool_loader.py`: `get_tool_guide()` — 도구 이름으로 가이드 내용 조회
- `backend/system_tools.py`: `_inject_guide_if_needed()` — 도구 실행 결과에 가이드 주입

### 처리 흐름
```
tool.json에 guide_file 필드 존재
    ↓
tool_loader._build_tool_guide_map()
    도구 이름 → 가이드 파일 경로 매핑 구축 (서버 시작 시 1회)
    ↓
AI가 도구 호출 → system_tools.execute_tool()
    ↓
도구 실행 후 _inject_guide_if_needed() 호출
    ↓
첫 호출이면: 가이드 내용을 결과 앞에 붙여서 반환
재호출이면: 결과만 그대로 반환
```

### 가이드 주입 추적
- `agent_id:tool_name` 조합으로 추적
- 같은 에이전트가 같은 도구를 다시 호출하면 가이드 생략
- 다른 에이전트가 호출하면 다시 주입
- 서버 재시작 시 자동 초기화
- `reset_guide_injection()` 함수로 수동 초기화 가능

## 가이드 파일 작성 팁

- 도구의 **사용법, 규칙, 예시 코드**를 포함
- description에는 한 줄 요약만 남기고, 나머지는 가이드에 작성
- 마크다운 형식 권장 (AI가 잘 해석함)
- 너무 길면 토큰 낭비이므로 핵심만 (5000~8000자 이내 권장)

## 적용 사례

| 도구 | 가이드 파일 | 내용 |
|------|------------|------|
| create_html_video | html_video_guide.md | HTML 영상 제작 규칙, GSAP 애니메이션, 레이아웃 패턴 |
| (Remotion은 별도 방식) | visual_guide.md | check_remotion_status 결과에 직접 포함 |

## 비교: 다른 방식들

| 방식 | 장점 | 단점 |
|------|------|------|
| **description에 전체 내용** | 간단 | 매 대화마다 토큰 낭비 |
| **별도 도구로 가이드 로드** (Remotion 방식) | 확실한 로딩 | 도구마다 하나씩 더 만들어야 함 |
| **guide_file 시스템** (현재) | 범용적, 토큰 절약, 설정만으로 적용 | 첫 호출 결과가 길어짐 |

---
*마지막 업데이트: 2026-01-29*
