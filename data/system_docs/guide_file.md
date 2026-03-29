# 도구 가이드 파일 시스템 (guide_file)

도구 패키지에 상세 사용 가이드를 제공하는 on-demand 주입 시스템입니다.

## 목적

복잡한 도구(영상 제작, 코드 실행 등)는 사용법이 길어서 description에 모두 넣으면 매 대화마다 토큰을 낭비합니다. 가이드 파일 시스템은 **필요할 때만** 상세 가이드를 AI 컨텍스트에 주입합니다.

## 가이드의 두 가지 유형

### 1. 도구 패키지 가이드 (tool.json의 guide_file)
- 도구 패키지 폴더 내에 위치하는 가이드 파일
- `tool.json`의 `guide_file` 필드로 지정
- `tool_loader.py`의 `get_tool_guide()`로 조회
- 도구 실행 시 `read_guide` 도구를 통해 에이전트가 직접 읽거나, IBL 엔진에서 참조

### 2. 공용 가이드 (data/guides/)
- `data/guides/` 폴더에 위치하는 범용 가이드 파일 (현재 32개)
- 의식 에이전트가 사용자 메시지를 분석하여 필요한 가이드를 선택
- `prompt_builder.py`의 `_load_guide_file()`로 로드하여 프롬프트에 주입

## 동작 원리

### 의식 에이전트 기반 주입 (주요 메커니즘)

```
1. 대화 시작 시: consciousness_agent.get_guide_list()가 사용자 메시지 기반으로
   관련 가이드 상위 10개를 키워드 매칭하여 available_guides로 제공
2. 의식 에이전트가 사용자 메시지, 히스토리, IBL 액션 목록, 가이드 목록을 종합 분석
3. JSON 출력의 "guide_files" 필드에 필요한 가이드 파일명을 지정 (최대 2-3개)
4. prompt_builder가 guide_files의 각 파일을 data/guides/에서 읽어 프롬프트에 주입
```

### 처리 흐름
```
사용자 메시지 입력
    ↓
consciousness_agent.get_guide_list(user_message)
    키워드 매칭으로 관련 가이드 상위 10개 선별 → available_guides
    ↓
consciousness_agent.process()
    사용자 메시지 + 히스토리 + IBL 요약 + available_guides + world_pulse 분석
    ↓
의식 에이전트 JSON 출력: { ..., "guide_files": ["investment.md", ...], ... }
    ↓
prompt_builder._load_guide_file(guide_filename)
    data/guides/{guide_filename} 에서 파일 읽기 (캐시 사용)
    ↓
프롬프트에 "# 가이드: {filename}\n{content}" 형태로 주입
```

### 도구 패키지 가이드 (보조 메커니즘)

```
tool.json에 guide_file 필드 존재
    ↓
tool_loader._build_tool_guide_map()
    도구 이름 → 가이드 파일 경로 매핑 구축 (서버 시작 시 1회)
    ↓
에이전트가 read_guide 도구 호출 또는 IBL _search_guide 사용
    ↓
tool_loader.get_tool_guide(tool_name)으로 가이드 내용 조회
```

## 적용 방법

### 공용 가이드 추가 (data/guides/)

`data/guides/` 폴더에 마크다운 파일을 생성합니다. 의식 에이전트가 자동으로 인식합니다.

### 도구 패키지 가이드 설정 (tool.json)

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

| 파일 | 역할 |
|------|------|
| `backend/consciousness_agent.py` | 의식 에이전트 — guide_list 수신, guide_files 출력으로 필요한 가이드 선택 |
| `backend/prompt_builder.py` | `_load_guide_file()` — data/guides/에서 가이드 로드 및 프롬프트 주입 |
| `backend/tool_loader.py` | `get_tool_guide()` — tool.json 기반 도구 가이드 조회, `_build_tool_guide_map()` — 매핑 구축 |
| `backend/system_tools.py` | `read_guide` 도구 실행 — 에이전트가 직접 가이드 검색/읽기 |
| `backend/ibl_engine.py` | `_search_guide()` — guide_db.json 기반 가이드 키워드 검색 |
| `data/guides/` | 공용 가이드 파일 저장소 (32개) |
| `data/common_prompts/consciousness_prompt.md` | 의식 에이전트 프롬프트 — guide_files 출력 규칙 정의 |

### 의식 에이전트의 가이드 선택 규칙

의식 에이전트 프롬프트(`consciousness_prompt.md`)에 정의된 규칙:
- available_guides에서 **정의된 문제를 풀 때** 필요한 가이드 파일을 선택
- 관련 없으면 빈 배열
- 가장 관련 있는 것 2-3개로 제한

### 가이드 주입 위치

프롬프트 빌드 시 의식 에이전트 출력의 다른 항목들(history_summary, task_framing, ibl_focus, context_notes)과 함께 주입됩니다. 프로젝트 에이전트와 시스템 AI 모두 동일한 방식으로 적용됩니다.

## 가이드 파일 작성 팁

- 도구의 **사용법, 규칙, 예시 코드**를 포함
- description에는 한 줄 요약만 남기고, 나머지는 가이드에 작성
- 마크다운 형식 권장 (AI가 잘 해석함)
- 너무 길면 토큰 낭비이므로 핵심만 (5000~8000자 이내 권장)

## 적용 사례

| 패키지 | 도구 | guide_file 위치 | 가이드 파일 | 내용 |
|--------|------|-----------------|------------|------|
| media_producer | create_html_video | 도구 레벨 | html_video_guide.md | HTML 영상 제작 규칙, GSAP 애니메이션, 레이아웃 패턴 |
| media_producer | create_slides | 도구 레벨 | slides_guide.md | 슬라이드 제작 가이드 |
| music-composer | abc_to_midi, midi_to_audio, compose_and_export | 패키지 레벨 | music_composer_guide.md | ABC Notation 문법, GM 악기 목록, 믹싱 옵션, EQ 프리셋 가이드 |
| (Remotion은 별도 방식) | — | — | visual_guide.md | check_remotion_status 결과에 직접 포함 |

## 비교: 다른 방식들

| 방식 | 장점 | 단점 |
|------|------|------|
| **description에 전체 내용** | 간단 | 매 대화마다 토큰 낭비 |
| **별도 도구로 가이드 로드** (Remotion 방식) | 확실한 로딩 | 도구마다 하나씩 더 만들어야 함 |
| **의식 에이전트 선택** (현재 주요 방식) | 문맥 기반 지능적 선택, 불필요한 가이드 배제 | 의식 에이전트 비활성 시 주입 안 됨 |
| **tool.json guide_file** (보조 방식) | 범용적, 설정만으로 적용 | 에이전트가 read_guide로 직접 읽어야 함 |

---
*마지막 업데이트: 2026-03-27*
