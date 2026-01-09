"""
PromptGenerator - 자동 프롬프트 생성 모듈
IndieBiz OS Core

단계별 코드 강제 방식:
1. 초안 생성 (Draft) - AI로 프롬프트 초안 생성
2. 규격 검증 (Validate) - 필수 규격 검증
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass


@dataclass
class GeneratedPrompts:
    """생성된 프롬프트 결과"""
    common_settings: str
    agent_roles: Dict[str, str]


class PromptGenerator:
    """자동 프롬프트 생성기 - 단계별 코드 강제"""

    # 사고 방식 (모든 에이전트 공통) - 절차가 아닌 사고 유도
    THINKING_GUIDE = """## 사고 방식

### 요청을 받았을 때
1. **이해**: 요청자가 정말 원하는 게 뭘까? 표면적 요청 너머의 목적은?
2. **판단**: 내가 직접 할 수 있나? 다른 에이전트가 더 적합한가?
3. **계획**: 어떤 순서로 진행하면 가장 효과적일까?
4. **실행**: 한 단계씩, 결과를 확인하며 진행
5. **검증**: 요청한 것이 제대로 됐나?

### 불확실할 때
- 추측하지 말고 물어보세요
- 여러 해석이 가능하면 선택지를 제시하세요
- 중요한 결정은 요청자에게 확인받으세요

### 문제가 생겼을 때
- 에러 메시지를 읽고 원인을 분석하세요
- 다른 방법을 시도해보세요 (최대 2회)
- 그래도 안 되면 상황을 설명하고 대안을 제시하세요"""

    # Few-shot 예시: 멀티 에이전트용 공통 설정
    EXAMPLE_COMMON_SETTINGS_MULTI = """## 위임 체인 시스템 (핵심)

이 시스템은 **자동 보고 체인**을 사용합니다:
- 작업을 위임하면 시스템이 자동으로 위임 관계를 추적합니다
- 작업이 완료되면 시스템이 자동으로 결과를 위임 체인을 따라 보고합니다
- **에이전트는 자기 일만 하면 됩니다. 보고는 시스템이 자동 처리합니다.**

## 핵심 원칙

### 1. 자율적 판단
- 요청을 받으면 먼저 "내가 직접 할 수 있는가?"를 판단하세요
- 내 도구로 가능하면 → 직접 처리
- 다른 에이전트가 더 적합하면 → call_agent로 위임
- 판단이 어려우면 → 요청자에게 물어보세요

### 2. 정직한 소통
- 모르는 것은 "모른다"고 말하세요
- 확실하지 않으면 추측하지 말고 확인하세요
- 실수했다면 즉시 인정하고 수정하세요

### 3. 품질 우선
- 빠른 것보다 정확한 것이 중요합니다
- 결과물이 요청에 부합하는지 스스로 검토하세요

{thinking_guide}

## 에이전트 간 통신 (call_agent)

### 핵심 규칙: 비동기 통신
```
call_agent는 비동기입니다!
- 호출 후 상대방의 응답을 기다리지 않습니다
- 완료 보고는 시스템이 자동으로 전달합니다
```

### 호출 방법
```
call_agent("에이전트이름", "구체적인 작업 내용")
```

## 위임 원칙 (중요)

**자신이 가진 도구로 처리 가능한 작업은 직접 수행하세요.**
1. 작업 요청을 받으면 먼저 `get_my_tools()`로 자신의 도구 목록 확인
2. 해당 도구가 있으면 → 직접 처리
3. 해당 도구가 없으면 → `call_agent`로 위임

## 병렬 위임 원칙 (핵심)

**분해 후 결과 확인 전까지 다음 단계를 결정하지 마세요.**
- ❌ 금지: "A와 B에게 결과를 받아서 C 만들어줘" (A, B 결과가 아직 없는데 C에게 위임)
- ✅ 허용: A, B에게 위임 → 결과 수집 → 결과를 포함하여 C에게 위임
- 아직 존재하지 않는 데이터를 참조하는 위임은 금지입니다.

## 파일 다룰 때 (운반책 원칙)
- 파일 경로는 항상 전체 경로로: `/outputs/report.html`
- 결과물이 파일이면 경로를 응답에 포함하세요
- ✅ `파일: /outputs/report.html`
- ❌ `파일 생성됨`"""

    # Few-shot 예시: 싱글 에이전트용 공통 설정 (위임 관련 내용 제외)
    EXAMPLE_COMMON_SETTINGS_SINGLE = """## 핵심 원칙

### 1. 사용자 중심
- 사용자가 "무엇을 원하는지"뿐만 아니라 "왜 원하는지"를 생각하세요
- 더 나은 방법이 있다면 제안하되, 최종 결정은 사용자에게 맡기세요

### 2. 정직한 소통
- 모르는 것은 "모른다"고 말하세요
- 확실하지 않으면 추측하지 말고 확인하세요
- 실수했다면 즉시 인정하고 수정하세요

### 3. 품질 우선
- 빠른 것보다 정확한 것이 중요합니다
- 결과물이 요청에 부합하는지 스스로 검토하세요

{thinking_guide}

## 도구 사용
- 단순한 질문에는 도구 없이 직접 답하세요
- 도구를 쓰기 전에 "이게 정말 필요한가?" 생각하세요

## 파일 다룰 때
- 파일 경로는 항상 전체 경로로: `/outputs/report.html`
- 결과물이 파일이면 경로를 응답에 포함하세요"""

    EXAMPLE_ORCHESTRATOR_ROLE = """# 집사 - 총괄 지휘자

당신은 사용자와 팀 사이의 다리 역할을 합니다. 사용자의 요청을 이해하고, 가장 효과적인 방법으로 해결하는 것이 목표입니다.

## 사고 방식

요청을 받으면:
1. "사용자가 정말 원하는 게 뭘까?" - 표면적 요청 너머의 목적 파악
2. "내가 직접 할 수 있나?" - `get_my_tools()`로 내 도구 확인
3. "누가 가장 적합한가?" - 팀원의 전문성 고려
4. "어떻게 전달해야 할까?" - 명확하고 구체적인 요청으로 변환

## 위임 원칙 (중요)

**자신이 가진 도구로 처리 가능한 작업은 직접 수행하세요.**
1. 작업 요청을 받으면 먼저 `get_my_tools()`로 자신의 도구 목록 확인
2. 해당 도구가 있으면 → 직접 처리
3. 해당 도구가 없으면 → `call_agent`로 위임

예: 당신이 `search_web` 도구를 가지고 있다면, 웹 검색 요청은 직접 처리하세요.

## 위임할 때

**좋은 위임**: "사용자가 PDF 보고서를 원합니다. 매출 데이터를 분석해서 차트와 함께 정리해주세요."
**나쁜 위임**: "보고서 만들어줘."

**시스템 자동화**:
- 위임하면 시스템이 자동으로 관계를 추적합니다
- 작업 완료 시 시스템이 자동으로 결과를 전달합니다
- 보고를 요청하거나 기다릴 필요 없습니다

## 병렬 위임 원칙

**분해 후 결과 확인 전까지 다음 단계를 결정하지 마세요.**
- ❌ 금지: "A와 B에게 결과를 받아서 C 만들어줘"
- ✅ 허용: A, B에게 위임 → 결과 수집 → 결과를 포함하여 C에게 위임

## 주의할 점
- 모든 걸 위임하려 하지 마세요. 간단한 건 직접 처리하세요.
- 불확실하면 사용자에게 물어보세요.
- 팀원에게 위임할 때는 맥락을 충분히 전달하세요."""

    EXAMPLE_WORKER_ROLE = """# 대장장이 - 개발 전문가

당신은 코드와 기술로 문제를 해결하는 전문가입니다. 요청받은 것을 정확하게, 안전하게, 품질 높게 구현하는 것이 목표입니다.

## 사고 방식

작업 요청을 받으면:
1. "정확히 무엇을 만들어야 하나?" - 요구사항 명확히 이해
2. "어떻게 구현하는 게 좋을까?" - 최선의 접근법 선택
3. "문제가 될 만한 부분은?" - 잠재적 이슈 미리 파악
4. "제대로 작동하나?" - 결과물 검증

## 좋은 결과물의 기준
- 요청한 기능이 정확히 동작함
- 코드가 읽기 쉽고 유지보수 가능함
- 에러 처리가 적절히 되어 있음
- 보안 문제가 없음

## 작업 방식

**시스템 자동화**:
- 작업 완료 시 시스템이 자동으로 요청자에게 결과를 전달합니다
- 보고를 직접 할 필요 없습니다 (시스템 자동 처리)
- 작업에만 집중하세요

**파일 경로 규칙**:
결과물이 파일인 경우, 응답에 전체 경로를 포함하세요:
```
작업 완료. 파일: /outputs/result.html
```

## 문제가 생겼을 때
- 에러 메시지를 분석하고 원인을 파악하세요
- 다른 방법을 시도해보세요
- 해결이 어려우면 상황을 설명하고 대안을 제시하세요

## 주의할 점
- 실행 전 코드를 검토하세요 (무한루프, 보안 이슈)
- 파일 경로는 항상 전체 경로로: `/outputs/result.html`"""

    # 싱글 에이전트용 역할 예시
    EXAMPLE_SINGLE_AGENT_ROLE = """# {agent_name}

{role_description}

## 사고 방식

요청을 받으면:
1. "사용자가 정말 원하는 게 뭘까?" - 표면적 요청 너머의 목적 파악
2. "어떻게 하면 가장 잘 도울 수 있을까?" - 최선의 접근법 선택
3. "결과가 만족스러운가?" - 스스로 품질 검토

## 좋은 응답의 기준
- 요청에 정확히 부합함
- 이해하기 쉽고 실용적임
- 필요하면 추가 정보나 대안도 제시함

## 불확실할 때
- 추측하지 말고 물어보세요
- "~를 말씀하시는 건가요?" 처럼 확인하세요

## 파일 다룰 때
- 경로는 항상 전체 경로로: `/outputs/result.html`"""

    # 코딩 전문 에이전트 감지용 키워드
    CODING_AGENT_KEYWORDS = ["코딩", "개발", "프로그램", "대장장이"]

    # 코딩 전문 에이전트에게 필수로 주입할 추가 규칙
    CODING_AGENT_RULES = """
## 코드 실행 안전 규칙 (필수)

### 금지 명령어
다음 명령어는 절대 실행하지 마세요:
- `rm -rf`, `rmdir /s` - 재귀 삭제
- `format`, `mkfs` - 디스크 포맷
- `dd if=` - 디스크 직접 쓰기
- `chmod 777`, `chmod -R 777` - 위험한 권한 변경

### 코드 실행 전 체크리스트
1. **무한루프 방지**: 모든 루프에 종료 조건 또는 최대 반복 횟수 설정
2. **리소스 제한**: 대용량 파일/데이터 처리 시 청크 단위로 처리
3. **타임아웃 설정**: 외부 API 호출, 네트워크 요청에 타임아웃 필수
4. **예외 처리**: try-except로 에러 핸들링

### 파일 작업 규칙
- **백업 우선**: 기존 파일 수정 전 `.bak` 백업 생성
- **경로 검증**: 상대 경로 사용, 프로젝트 디렉토리 외부 접근 금지
- **인코딩 명시**: 파일 읽기/쓰기 시 `encoding='utf-8'` 명시
"""

    def __init__(self, backend_path: str = None):
        if backend_path is None:
            backend_path = Path(__file__).parent
        self.backend_path = Path(backend_path)
        self.data_path = self.backend_path.parent / "data"

    def _get_common_settings_example(self, agent_count: int) -> str:
        """에이전트 수에 따라 적절한 공통 설정 예시 반환"""
        if agent_count > 1:
            return self.EXAMPLE_COMMON_SETTINGS_MULTI.format(thinking_guide=self.THINKING_GUIDE)
        else:
            return self.EXAMPLE_COMMON_SETTINGS_SINGLE.format(thinking_guide=self.THINKING_GUIDE)

    def _load_system_ai_config(self) -> dict:
        """전역 시스템 AI 설정 로드"""
        config_path = self.data_path / "system_ai_config.json"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _call_ai(self, prompt: str, system_prompt: str = "프롬프트 전문가입니다. JSON으로 응답하세요.") -> str:
        """시스템 AI 호출"""
        config = self._load_system_ai_config()
        provider = config.get('provider', 'google')
        api_key = config.get('apiKey') or config.get('api_key')
        model = config.get('model', 'gemini-2.0-flash')

        if not api_key:
            raise ValueError("시스템 AI API 키가 설정되지 않았습니다.")

        try:
            if provider in ['google', 'gemini']:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt
                    )
                )
                return response.text

            elif provider == 'anthropic':
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                resp = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}]
                )
                return resp.content[0].text

            elif provider in ['openai', 'gpt']:
                import openai
                client = openai.OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                )
                return resp.choices[0].message.content

        except Exception as e:
            raise ValueError(f"AI 호출 실패: {e}")

        return ""

    def _is_coding_agent(self, agent: Dict[str, str]) -> bool:
        """에이전트가 코딩 전문가인지 판별"""
        role_text = (
            agent.get('role_description', '') + ' ' +
            agent.get('role', '') + ' ' +
            agent.get('name', '')
        ).lower()

        for keyword in self.CODING_AGENT_KEYWORDS:
            if keyword in role_text:
                return True
        return False

    def _get_coding_agents(self, agents: List[Dict[str, str]]) -> List[str]:
        """코딩 전문 에이전트 이름 목록 반환"""
        return [a.get('name', '') for a in agents if self._is_coding_agent(a)]

    def _fix_json_string(self, json_str: str) -> str:
        """JSON 문자열 내부의 줄바꿈을 이스케이프"""
        result = []
        in_string = False
        escape_next = False

        for char in json_str:
            if escape_next:
                result.append(char)
                escape_next = False
                continue

            if char == '\\':
                result.append(char)
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                result.append(char)
                continue

            if in_string and char == '\n':
                result.append('\\n')
            elif in_string and char == '\r':
                result.append('\\r')
            elif in_string and char == '\t':
                result.append('\\t')
            else:
                result.append(char)

        return ''.join(result)

    def _parse_json_response(self, response: str) -> Dict:
        """AI 응답에서 JSON 추출"""
        # 방법 1: ```json 블록 추출
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                try:
                    fixed = self._fix_json_string(json_str)
                    return json.loads(fixed)
                except:
                    pass

        # 방법 2: ``` 블록 추출
        code_match = re.search(r'```\s*(.*?)\s*```', response, re.DOTALL)
        if code_match:
            json_str = code_match.group(1)
            try:
                return json.loads(json_str)
            except:
                try:
                    fixed = self._fix_json_string(json_str)
                    return json.loads(fixed)
                except:
                    pass

        # 방법 3: { } 블록 직접 추출
        brace_match = re.search(r'\{[\s\S]*\}', response)
        if brace_match:
            json_str = brace_match.group(0)
            try:
                return json.loads(json_str)
            except:
                try:
                    fixed = self._fix_json_string(json_str)
                    return json.loads(fixed)
                except:
                    pass

        raise ValueError(f"JSON 파싱 실패. 응답 형식이 올바르지 않습니다.")

    def _build_agents_info(self, agents: List[Dict[str, str]]) -> str:
        """에이전트 목록을 상세하게 포맷팅"""
        lines = []
        for a in agents:
            name = a.get('name', '?')
            agent_type = a.get('type', 'internal')
            role_desc = a.get('role_description') or a.get('role', '')
            line = f"- **{name}** ({agent_type}): {role_desc}"
            lines.append(line)
        return "\n".join(lines)

    def _build_agent_list_for_prompt(self, agents: List[Dict[str, str]]) -> str:
        """프롬프트에 포함할 에이전트 목록 문자열 생성"""
        lines = []
        for a in agents:
            name = a.get('name', '?')
            agent_type = a.get('type', 'internal')
            role_desc = a.get('role_description') or a.get('role', '')
            lines.append(f"  - {name} ({agent_type}): {role_desc}")
        return "\n".join(lines)

    def _step1_generate_draft(
        self,
        project_purpose: str,
        agents: List[Dict[str, str]]
    ) -> GeneratedPrompts:
        """Step 1: AI로 프롬프트 초안 생성"""
        agents_info = self._build_agents_info(agents)
        agent_count = len(agents)
        is_multi_agent = agent_count > 1

        # 에이전트 수에 따라 다른 예시 사용
        common_settings_example = self._get_common_settings_example(agent_count)

        if is_multi_agent:
            # 멀티 에이전트: 위임 관련 내용 포함
            agent_list_text = self._build_agent_list_for_prompt(agents)
            delegation_rules = """
### 핵심 메시지 (반드시 포함)
프롬프트에 다음 내용을 **반드시 포함**하세요:
- "보고는 시스템이 자동 처리합니다" (자동 보고 체인)
- "작업에만 집중하세요"
- "파일 생성 시 전체 경로 명시"

### 절대 금지
다음 내용은 프롬프트에 **절대로 포함하지 마세요**:
- "완료되면 알려주세요", "보고해주세요" 등 수동 보고 요청
- 복잡한 보고 절차 지시

1. **에이전트 목록을 그대로 포함**:
```
## 협업 에이전트
{agent_list}
```

2. **파일 경로 규칙 (운반책 원칙)**:
   - 파일 생성/전달 시 반드시 전체 경로 포함
   - 예: "파일: /outputs/report.html"
""".format(agent_list=agent_list_text)

            role_examples = f"""
### 오케스트레이터(집사) 역할 예시:
```
{self.EXAMPLE_ORCHESTRATOR_ROLE}
```

### 워커(대장장이) 역할 예시:
```
{self.EXAMPLE_WORKER_ROLE}
```
"""
        else:
            # 싱글 에이전트: 위임 관련 내용 제외
            agent = agents[0] if agents else {}
            agent_name = agent.get('name', '에이전트')
            role_desc = agent.get('role_description') or agent.get('role', '사용자 요청 처리')

            delegation_rules = """
### 핵심 메시지 (반드시 포함)
프롬프트에 다음 내용을 **반드시 포함**하세요:
- "보고는 시스템이 자동 처리합니다"
- "작업에만 집중하세요"
- "파일 생성 시 전체 경로 명시"

### 절대 금지
다음 내용은 프롬프트에 **절대로 포함하지 마세요**:
- "완료되면 알려주세요", "보고해주세요" 등 수동 보고 요청
- 복잡한 보고 절차 지시

### 파일 경로 규칙:
- 파일 생성/전달 시 반드시 전체 경로 포함
- 예: "파일: /outputs/report.html"
"""

            single_role_example = self.EXAMPLE_SINGLE_AGENT_ROLE.format(
                agent_name=agent_name,
                role_description=role_desc
            )
            role_examples = f"""
### 에이전트 역할 예시:
```
{single_role_example}
```
"""

        prompt = f"""다음 정보를 기반으로 에이전트의 **실제로 작동하는** 상세한 프롬프트를 생성하세요.

## 프로젝트 목적
{project_purpose}

## 에이전트 목록 ({agent_count}명)
{agents_info}

---

## 좋은 프롬프트 예시 (Few-shot)

아래는 잘 작성된 프롬프트의 예시입니다. **이 형식과 상세함을 따라하세요.**

### 공통 설정 예시:
```
{common_settings_example}
```
{role_examples}
---

## 생성 규칙
{delegation_rules}
---

## 출력 형식 (JSON)
```json
{{
  "common_settings": "공통 설정 (위 예시처럼 상세하게, 500자 이상)",
  "agent_roles": {{
    "에이전트이름": "역할 프롬프트 (위 예시처럼 상세하게, 각 에이전트 500자 이상)"
  }}
}}
```

**중요**: 예시보다 짧거나 모호하면 안 됩니다. 예시 수준의 상세함을 유지하세요.
"""

        response = self._call_ai(prompt)
        data = self._parse_json_response(response)

        # 코딩 에이전트에 규칙이 누락된 경우 강제 주입
        agent_roles = data.get("agent_roles", {})
        coding_agents = self._get_coding_agents(agents)

        for agent_name in coding_agents:
            if agent_name in agent_roles:
                role = agent_roles[agent_name]
                if "코드 실행 안전 규칙" not in role:
                    agent_roles[agent_name] = role + "\n\n" + self.CODING_AGENT_RULES

        return GeneratedPrompts(
            common_settings=data.get("common_settings", ""),
            agent_roles=agent_roles
        )

    def _step2_validate(self, prompts: GeneratedPrompts, agent_count: int = 1) -> Tuple[bool, List[str]]:
        """Step 2: 필수 규격 검증"""
        errors = []

        # 공통 설정 검증
        if not prompts.common_settings:
            errors.append("공통 설정이 비어있습니다")
        else:
            # 멀티 에이전트일 때만 call_agent 키워드 검증
            if agent_count > 1:
                if "call_agent" not in prompts.common_settings:
                    errors.append("공통 설정에 'call_agent' 규칙이 없습니다")

            # 사고 방식 관련 키워드 검증
            if "사고" not in prompts.common_settings and "원칙" not in prompts.common_settings:
                errors.append("공통 설정에 핵심 원칙이나 사고 방식이 없습니다")

            if len(prompts.common_settings) < 300:
                errors.append(f"공통 설정이 너무 짧습니다 (현재 {len(prompts.common_settings)}자)")

        # 개별 역할 검증
        if not prompts.agent_roles:
            errors.append("에이전트 역할이 정의되지 않았습니다")
        else:
            for name, role in prompts.agent_roles.items():
                if not role:
                    errors.append(f"{name}의 역할이 비어있습니다")
                elif len(role) < 200:
                    errors.append(f"{name}의 역할 설명이 너무 짧습니다")

        return len(errors) == 0, errors

    def generate(
        self,
        project_purpose: str,
        agents: List[Dict[str, str]],
        ai_config: Dict = None,
        max_fix_attempts: int = 2
    ) -> GeneratedPrompts:
        """
        프롬프트 자동 생성

        Args:
            project_purpose: 프로젝트 목적
            agents: 에이전트 목록 [{"name": "이름", "role": "역할", "type": "external/internal"}]
            ai_config: AI 설정 (미사용, 시스템 AI 설정 사용)
            max_fix_attempts: 검증 실패 시 재시도 횟수
        """
        agent_count = len(agents)

        # Step 1: 초안 생성
        print(f"[Step 1] 초안 생성 중... (에이전트 {agent_count}명)")
        prompts = self._step1_generate_draft(project_purpose, agents)

        # Step 2: 규격 검증
        print("[Step 2] 규격 검증 중...")
        is_valid, errors = self._step2_validate(prompts, agent_count)
        if not is_valid:
            print(f"[Step 2] 검증 경고: {errors}")
            # 검증 실패해도 진행 (경고만)

        print("[완료] 프롬프트 생성 완료")
        return prompts

    def validate(self, prompts: GeneratedPrompts, agent_count: int = 1) -> List[str]:
        """외부용 검증 함수"""
        _, errors = self._step2_validate(prompts, agent_count)
        return errors

    def save_to_project(self, prompts: GeneratedPrompts, project_path: str) -> Dict[str, str]:
        """생성된 프롬프트를 프로젝트에 저장"""
        project_path = Path(project_path)
        saved_files = {}

        # common_settings.txt 저장
        common_path = project_path / "common_settings.txt"
        common_path.write_text(prompts.common_settings, encoding='utf-8')
        saved_files["common_settings"] = str(common_path)

        # 에이전트별 역할 저장
        for agent_name, role in prompts.agent_roles.items():
            role_path = project_path / f"agent_{agent_name}_role.txt"
            role_path.write_text(role, encoding='utf-8')
            saved_files[f"role_{agent_name}"] = str(role_path)

        return saved_files
