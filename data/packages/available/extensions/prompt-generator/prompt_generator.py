"""
PromptGenerator - 자동 프롬프트 생성 모듈

단계별 코드 강제 방식:
1. 초안 생성 (Draft) - AI로 프롬프트 초안 생성
2. 규격 검증 (Validate) - call_agent 등 필수 규격 검증
3. 압축 (Compress) - AI로 토큰 최적화
4. 예시 테스트 (Test) - 시뮬레이션으로 동작 검증
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass

# AI 모듈 임포트
try:
    from ai import AIAgent
except ImportError:
    AIAgent = None


@dataclass
class GeneratedPrompts:
    """생성된 프롬프트 결과"""
    common_settings: str
    agent_roles: Dict[str, str]


class PromptGenerator:
    """자동 프롬프트 생성기 - 단계별 코드 강제"""

    # 필수 규격: 공통 설정에 반드시 포함되어야 할 키워드
    REQUIRED_COMMON_KEYWORDS = [
        "call_agent",  # 에이전트 간 통신
    ]

    # 필수 규격: 개별 역할에 반드시 포함되어야 할 내용
    REQUIRED_ROLE_SECTIONS = [
        "역할",  # 또는 "담당", "목적"
        "협업",  # 또는 "통신", "call_agent"
    ]

    # Few-shot 예시: 좋은 프롬프트의 실제 예
    EXAMPLE_COMMON_SETTINGS = """## 위임 체인 시스템 (핵심)

이 시스템은 **자동 보고 체인**을 사용합니다:
- 작업을 위임하면 시스템이 자동으로 위임 관계를 추적합니다
- 작업이 완료되면 시스템이 자동으로 결과를 위임 체인을 따라 보고합니다
- **에이전트는 자기 일만 하면 됩니다. 보고는 시스템이 자동 처리합니다.**

## 에이전트 간 통신 (call_agent)
- call_agent는 **비동기**입니다. 호출 후 응답을 기다리지 않습니다.
- 다른 에이전트 도움이 필요하면 call_agent를 호출하세요.
- 결과 보고를 직접 할 필요 없습니다 (시스템 자동 처리).

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

## 파일 경로 규칙 (운반책 원칙)
파일 생성/전달 시 **반드시 전체 경로** 포함:
- ✅ `파일: /outputs/report.html`
- ❌ `파일 생성됨`

## 응답 형식
[작업 완료]
- 수행 내용: (구체적인 작업)
- 결과: (결과물 또는 상태)
- 파일 경로: (생성된 파일이 있는 경우)

[오류 발생]
- 문제: (무엇이 잘못되었는지)
- 원인: (추정 원인)
- 제안: (다음 단계)

## 보안 규칙
- 시스템 파괴 명령(rm -rf 등) 실행 금지
- API 키, 비밀번호 등 인증 정보 노출 금지

## 도구 사용 원칙
- 도구는 작업에 필요할 때만 호출
- 단순 질문에는 도구 없이 직접 응답"""

    EXAMPLE_ORCHESTRATOR_ROLE = """# 집사 - 총괄 지휘자

## 역할
사용자의 요청을 분석하고, 적절한 에이전트에게 작업을 배분합니다.

## 협업 에이전트
- 대장장이 (internal): 코딩/개발 전문, Python/Node.js 실행
- 출판 (internal): 콘텐츠 생성, HTML 신문/잡지 제작
- 영상담당 (internal): 영상/음악 다운로드 및 정보 조회

## 위임 원칙 (중요)

**자신이 가진 도구로 처리 가능한 작업은 직접 수행하세요.**
1. 작업 요청을 받으면 먼저 `get_my_tools()`로 자신의 도구 목록 확인
2. 해당 도구가 있으면 → 직접 처리
3. 해당 도구가 없으면 → `call_agent`로 위임

예: 당신이 `search_nostr_notes` 도구를 가지고 있다면, Nostr 검색 요청은 직접 처리하세요.

## 병렬 위임 원칙 (핵심)

**분해 후 결과 확인 전까지 다음 단계를 결정하지 마세요.**
- ❌ 금지: "A와 B에게 결과를 받아서 C 만들어줘" (A, B 결과가 아직 없는데 C에게 위임)
- ✅ 허용: A, B에게 위임 → 결과 수집 → 결과를 포함하여 C에게 위임
- 아직 존재하지 않는 데이터를 참조하는 위임은 금지입니다.

## 위임 방법

자신에게 없는 도구가 필요할 때만 `call_agent`를 사용하세요:
```
call_agent("출판", "잡지 만들어줘")
```

**시스템 자동화**:
- 위임하면 시스템이 자동으로 관계를 추적합니다
- 작업 완료 시 시스템이 자동으로 결과를 전달합니다
- 보고를 요청하거나 기다릴 필요 없습니다

## 작업 위임 매핑 (자신에게 해당 도구가 없을 때만)
- 코딩/스크립트 실행 → 대장장이
- 뉴스/잡지/HTML 생성 → 출판
- 영상/음악 다운로드 → 영상담당
- 웹 검색/정보 수집 → 리서처 (있는 경우)

## 채널별 발송 방법
- **GUI 응답**: 텍스트로 직접 응답
- **이메일 발송**: send_email(to, subject, body, attachments)
- **Nostr 발송**: send_nostr_message(recipient_pubkey, content)

## 파일 경로 규칙
파일 전달 시 **반드시 전체 경로** 포함:
예: "뉴스레터: /outputs/newsletter_20241225.html" """

    EXAMPLE_WORKER_ROLE = """# 대장장이 - 개발 전문가

## 역할
코드 작성, 스크립트 실행, 기술적 문제 해결을 담당합니다.

## 사용 가능한 도구
- execute_python: Python 코드 실행
- execute_nodejs: Node.js 코드 실행
- read_file / write_file: 파일 읽기/쓰기
- list_directory: 디렉토리 목록 조회

## 협업 대상
- 집사: 작업 지시를 받음
- 출판: 생성된 데이터나 차트를 전달

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

## 주의사항
- 실행 전 코드 검토 (무한루프 방지)
- 에러 발생 시 원인과 해결 방안 함께 보고"""

    # 코딩 전문 에이전트 감지용 키워드
    CODING_AGENT_KEYWORDS = ["코딩", "개발", "프로그램"]

    # 코딩 전문 에이전트에게 필수로 주입할 추가 규칙
    CODING_AGENT_RULES = """
## 코드 실행 안전 규칙 (필수)

### 금지 명령어
다음 명령어는 절대 실행하지 마세요:
- `rm -rf`, `rmdir /s` - 재귀 삭제
- `format`, `mkfs` - 디스크 포맷
- `dd if=` - 디스크 직접 쓰기
- `:(){ :|:& };:` - 포크 폭탄
- `chmod 777`, `chmod -R 777` - 위험한 권한 변경
- `curl | bash`, `wget | sh` - 원격 스크립트 직접 실행

### 코드 실행 전 체크리스트
1. **무한루프 방지**: 모든 루프에 종료 조건 또는 최대 반복 횟수 설정
2. **리소스 제한**: 대용량 파일/데이터 처리 시 청크 단위로 처리
3. **타임아웃 설정**: 외부 API 호출, 네트워크 요청에 타임아웃 필수
4. **예외 처리**: try-except로 에러 핸들링, 에러 메시지 명확히 기록

### 파일 작업 규칙
- **백업 우선**: 기존 파일 수정 전 `.bak` 백업 생성
- **경로 검증**: 상대 경로 사용 (예: `outputs/result.html`), 프로젝트 디렉토리 외부 접근 금지
- **인코딩 명시**: 파일 읽기/쓰기 시 `encoding='utf-8'` 명시

### 외부 패키지 설치
1. 먼저 `pip list` 또는 `import`로 설치 여부 확인
2. 설치 필요 시 사용자에게 알리고 승인 후 설치
3. 버전 충돌 주의 (기존 패키지 업그레이드 시 확인)

### 에러 디버깅 절차
1. 에러 메시지 전문 기록
2. 관련 코드 라인 식별
3. 3가지 이상 가능한 원인 분석
4. 단계별 해결 시도 (한 번에 하나씩)
5. 해결 안 되면 상세 보고 후 지시 대기

### 코드 품질
- 함수/변수명은 명확하게 (한글 주석 권장)
- 복잡한 로직은 함수로 분리
- 하드코딩 지양, 설정값은 상수로 분리
"""

    def __init__(self, backend_path: str = None):
        if backend_path is None:
            backend_path = Path(__file__).parent
        self.backend_path = Path(backend_path)
        self.system_spec = self._load_system_spec()

    def _is_coding_agent(self, agent: Dict[str, str]) -> bool:
        """에이전트가 코딩 전문가인지 판별"""
        # role_description 또는 role에서 키워드 검색
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

    def _load_system_spec(self) -> str:
        """시스템 명세서 로드"""
        spec_path = self.backend_path / "system_spec.md"
        if spec_path.exists():
            return spec_path.read_text(encoding='utf-8')
        return ""

    def _create_ai_agent(self, ai_config: Dict, system_prompt: str) -> 'AIAgent':
        """AI 에이전트 생성"""
        return AIAgent(
            ai_config={
                "provider": ai_config.get("provider", "google"),
                "model": ai_config.get("model", "gemini-2.0-flash"),
                "api_key": ai_config.get("api_key"),
            },
            system_prompt=system_prompt,
            agent_name="PromptGenerator"
        )

    def _call_ai(self, ai: 'AIAgent', prompt: str) -> str:
        """AI 호출 헬퍼"""
        history = []
        return ai.process_message_with_history(
            message_content=prompt,
            from_email="prompt_generator@system",
            history=history
        )

    def _fix_json_string(self, json_str: str) -> str:
        """JSON 문자열 내부의 줄바꿈을 이스케이프"""
        # 문자열 값 내부의 줄바꿈을 \\n으로 변환
        # "..." 안의 실제 줄바꿈을 찾아서 이스케이프
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
        """AI 응답에서 JSON 추출 (여러 방법 시도)"""

        # 방법 1: ```json 블록 추출
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # 줄바꿈 이스케이프 후 재시도
                try:
                    fixed = self._fix_json_string(json_str)
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

        # 방법 2: ``` 블록 추출 (json 키워드 없이)
        code_match = re.search(r'```\s*(.*?)\s*```', response, re.DOTALL)
        if code_match:
            json_str = code_match.group(1)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                try:
                    fixed = self._fix_json_string(json_str)
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

        # 방법 3: { } 블록 직접 추출
        brace_match = re.search(r'\{[\s\S]*\}', response)
        if brace_match:
            json_str = brace_match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                try:
                    fixed = self._fix_json_string(json_str)
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

        # 모든 방법 실패
        print(f"[JSON 파싱 실패] 응답 앞부분: {response[:500]}...")
        raise ValueError(f"JSON 파싱 실패. 응답 형식이 올바르지 않습니다.")

    def _build_agents_info(self, agents: List[Dict[str, str]]) -> str:
        """에이전트 목록을 상세하게 포맷팅"""
        lines = []
        for a in agents:
            name = a.get('name', '?')
            agent_type = a.get('type', 'internal')
            role_desc = a.get('role_description') or a.get('role', '')
            channels = a.get('channels', [])

            line = f"- **{name}** ({agent_type}): {role_desc}"
            if channels:
                channel_names = [c.get('channel_type', '') for c in channels if isinstance(c, dict)]
                if channel_names:
                    line += f" [채널: {', '.join(channel_names)}]"
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

    # ========== Step 1: 초안 생성 ==========
    def _step1_generate_draft(
        self,
        project_purpose: str,
        agents: List[Dict[str, str]],
        ai_config: Dict
    ) -> GeneratedPrompts:
        """Step 1: AI로 프롬프트 초안 생성"""

        agents_info = self._build_agents_info(agents)
        agent_list_text = self._build_agent_list_for_prompt(agents)

        # external 에이전트 식별
        external_agents = [a for a in agents if a.get('type') == 'external']
        internal_agents = [a for a in agents if a.get('type') != 'external']

        prompt = f"""다음 정보를 기반으로 에이전트 팀의 **실제로 작동하는** 상세한 프롬프트를 생성하세요.

## 시스템 명세
{self.system_spec}

## 프로젝트 목적
{project_purpose}

## 에이전트 목록
{agents_info}

---

## 좋은 프롬프트 예시 (Few-shot)

아래는 잘 작성된 프롬프트의 예시입니다. **이 형식과 상세함을 따라하세요.**

### 공통 설정 예시:
```
{self.EXAMPLE_COMMON_SETTINGS}
```

### 오케스트레이터(집사) 역할 예시:
```
{self.EXAMPLE_ORCHESTRATOR_ROLE}
```

### 워커(대장장이) 역할 예시:
```
{self.EXAMPLE_WORKER_ROLE}
```

---

## 생성 규칙

### ⭐ 핵심 메시지 (반드시 포함)
프롬프트에 다음 내용을 **반드시 포함**하세요:
- "보고는 시스템이 자동 처리합니다" (자동 보고 체인)
- "작업에만 집중하세요"
- "파일 생성 시 전체 경로 명시"

### ⛔ 절대 금지
다음 내용은 프롬프트에 **절대로 포함하지 마세요**:
- "완료되면 알려주세요", "보고해주세요" 등 수동 보고 요청
- `list_available_tools()`, `get_current_time()`, `list_agents()` 호출 지시
- "작업 전 권한 확인", "사용 가능한 도구 확인" 등의 루틴 체크 지시
- 복잡한 보고 절차나 task_id 수동 관리 지시
- "결과는 XX를 거쳐 전달된다" 같은 특정 에이전트 경유 언급 (시스템이 parent_task_id를 따라 동적으로 전달)

**이유**: 시스템이 자동으로 보고 체인을 처리합니다. 에이전트는 작업에만 집중하면 됩니다.

1. **위 예시의 구조를 반드시 따르세요**:
   - 명확한 섹션 헤더 (## 역할, ## 협업 에이전트 등)
   - 시스템 자동화 설명 포함
   - 파일 경로 규칙 명시

2. **에이전트 목록을 그대로 포함**:
```
## 협업 에이전트
{agent_list_text}
```

3. **external 에이전트는 채널별 발송 방법 포함**:
   - GUI 응답: 텍스트로 직접
   - 이메일: send_email(to, subject, body, attachments)
   - Nostr: send_nostr_message(recipient_pubkey, content)

4. **파일 경로 규칙 (운반책 원칙)**:
   - 파일 생성/전달 시 반드시 전체 경로 포함
   - 예: "파일: /outputs/report.html"
"""

        # 코딩 전문 에이전트 감지 및 추가 지시 생성
        coding_agents = self._get_coding_agents(agents)
        coding_instruction = ""
        if coding_agents:
            coding_instruction = f"""

5. **코딩 전문 에이전트 특별 규칙** (중요!):
   다음 에이전트들은 코딩/개발/프로그램 전문가입니다: {', '.join(coding_agents)}

   이 에이전트들의 역할 프롬프트에는 반드시 아래 규칙을 포함하세요:
   ```
{self.CODING_AGENT_RULES}
   ```

   이 규칙들이 누락되면 안전하지 않은 코드가 실행될 수 있습니다.
"""

        prompt += coding_instruction + """
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

        ai = self._create_ai_agent(ai_config, "프롬프트 전문가입니다. JSON으로 응답하세요.")
        response = self._call_ai(ai, prompt)
        data = self._parse_json_response(response)

        # 코딩 에이전트에 규칙이 누락된 경우 강제 주입
        agent_roles = data.get("agent_roles", {})
        for agent_name in coding_agents:
            if agent_name in agent_roles:
                role = agent_roles[agent_name]
                # 상세 규칙 필수 키워드들 - 이것들이 모두 있어야 충분히 상세한 것
                required_keywords = [
                    "에러 디버깅 절차",  # 5단계 디버깅
                    "코드 실행 전 체크리스트",  # 4개 항목
                    "외부 패키지 설치",  # 설치 절차
                ]
                # 필수 키워드 중 하나라도 없으면 전체 규칙 주입
                missing = [kw for kw in required_keywords if kw not in role]
                if missing:
                    # 기존의 짧은 "코드 실행 안전 규칙" 섹션 제거 후 상세 버전으로 교체
                    import re
                    # "## 코드 실행 안전 규칙" 부터 다음 "##" 전까지 제거
                    role = re.sub(
                        r'##\s*코드 실행 안전 규칙.*?(?=\n##|\n\n##|\Z)',
                        '',
                        role,
                        flags=re.DOTALL
                    ).strip()
                    agent_roles[agent_name] = role + "\n\n" + self.CODING_AGENT_RULES

        return GeneratedPrompts(
            common_settings=data.get("common_settings", ""),
            agent_roles=agent_roles
        )

    # ========== Step 2: 규격 검증 ==========
    def _step2_validate(self, prompts: GeneratedPrompts) -> Tuple[bool, List[str]]:
        """Step 2: 필수 규격 검증 (코드로 강제)"""
        errors = []

        # 공통 설정 검증
        if not prompts.common_settings:
            errors.append("공통 설정이 비어있습니다")
        else:
            for keyword in self.REQUIRED_COMMON_KEYWORDS:
                if keyword not in prompts.common_settings:
                    errors.append(f"공통 설정에 '{keyword}' 규칙이 없습니다")

            # 공통 설정 최소 길이 검증 (Few-shot 예시 수준 유지)
            if len(prompts.common_settings) < 500:
                errors.append(f"공통 설정이 너무 짧습니다 (현재 {len(prompts.common_settings)}자, 500자 이상 필요)")

        # 개별 역할 검증
        if not prompts.agent_roles:
            errors.append("에이전트 역할이 정의되지 않았습니다")
        else:
            for name, role in prompts.agent_roles.items():
                if not role:
                    errors.append(f"{name}의 역할이 비어있습니다")
                elif len(role) < 500:
                    errors.append(f"{name}의 역할 설명이 너무 짧습니다 (현재 {len(role)}자, 500자 이상 필요)")

                # 협업 관련 키워드 검증
                collaboration_keywords = ["call_agent", "협업", "위임", "에이전트"]
                has_collaboration = any(kw in role for kw in collaboration_keywords)
                if not has_collaboration:
                    errors.append(f"{name}의 역할에 협업/위임 관련 내용이 없습니다")

        return len(errors) == 0, errors

    def _step2_fix(
        self,
        prompts: GeneratedPrompts,
        errors: List[str],
        ai_config: Dict
    ) -> GeneratedPrompts:
        """Step 2-fix: 검증 실패 시 AI로 수정"""

        prompt = f"""다음 프롬프트에 문제가 있습니다. 수정해주세요.

## 현재 프롬프트
공통 설정:
{prompts.common_settings}

개별 역할:
{json.dumps(prompts.agent_roles, ensure_ascii=False, indent=2)}

## 발견된 문제
{chr(10).join(f"- {e}" for e in errors)}

## 수정 요청
위 문제를 해결하여 다시 JSON 형식으로 출력하세요.

```json
{{
  "common_settings": "수정된 공통 설정...",
  "agent_roles": {{
    "에이전트이름": "수정된 역할..."
  }}
}}
```
"""

        ai = self._create_ai_agent(ai_config, "프롬프트를 수정합니다. JSON으로 응답하세요.")
        response = self._call_ai(ai, prompt)
        data = self._parse_json_response(response)

        return GeneratedPrompts(
            common_settings=data.get("common_settings", prompts.common_settings),
            agent_roles=data.get("agent_roles", prompts.agent_roles)
        )

    # ========== Step 3: 압축 ==========
    def _step3_compress(self, prompts: GeneratedPrompts, ai_config: Dict) -> GeneratedPrompts:
        """Step 3: AI로 토큰 최적화 (의미 유지하면서 압축)"""

        prompt = f"""다음 프롬프트를 압축해주세요.

## 압축 규칙
1. 의미 중복 제거
2. 설명 문장 → 명령형 문장으로 변환
3. 불필요한 수식어 제거
4. 핵심 규칙은 반드시 유지

## 현재 프롬프트
공통 설정:
{prompts.common_settings}

개별 역할:
{json.dumps(prompts.agent_roles, ensure_ascii=False, indent=2)}

## 출력 형식 (JSON)
```json
{{
  "common_settings": "압축된 공통 설정...",
  "agent_roles": {{
    "에이전트이름": "압축된 역할..."
  }}
}}
```
"""

        ai = self._create_ai_agent(ai_config, "프롬프트 압축 전문가입니다. JSON으로 응답하세요.")
        response = self._call_ai(ai, prompt)

        try:
            data = self._parse_json_response(response)
            return GeneratedPrompts(
                common_settings=data.get("common_settings", prompts.common_settings),
                agent_roles=data.get("agent_roles", prompts.agent_roles)
            )
        except Exception:
            # 압축 실패 시 원본 반환
            print("[압축] 실패, 원본 유지")
            return prompts

    # ========== Step 4: 예시 테스트 ==========
    def _step4_test(
        self,
        prompts: GeneratedPrompts,
        agents: List[Dict[str, str]],
        ai_config: Dict
    ) -> Tuple[bool, str]:
        """Step 4: 시뮬레이션으로 동작 검증"""

        # 첫 번째 에이전트로 테스트
        test_agent = agents[0] if agents else {"name": "테스트", "type": "external"}
        test_role = prompts.agent_roles.get(test_agent.get("name"), "")

        prompt = f"""다음 프롬프트를 가진 에이전트가 있습니다.

## 공통 설정
{prompts.common_settings}

## 이 에이전트의 역할
{test_role}

## 테스트
사용자가 "안녕하세요, 도움을 요청합니다"라고 했을 때:
1. 이 에이전트가 어떻게 응답할지 예시를 보여주세요
2. 다른 에이전트에게 call_agent를 호출해야 한다면 그 형식도 보여주세요

## 출력 형식 (JSON)
```json
{{
  "response_example": "에이전트의 응답 예시",
  "call_agent_example": {{"agent_name": "대상", "message": "내용"}} 또는 null,
  "is_valid": true/false,
  "issues": ["문제점1", "문제점2"] 또는 []
}}
```
"""

        ai = self._create_ai_agent(ai_config, "프롬프트 검증 전문가입니다. JSON으로 응답하세요.")
        response = self._call_ai(ai, prompt)

        try:
            data = self._parse_json_response(response)
            is_valid = data.get("is_valid", True)
            issues = data.get("issues", [])

            if issues:
                return False, f"시뮬레이션 문제: {', '.join(issues)}"
            return is_valid, "검증 통과"
        except Exception as e:
            # 파싱 실패해도 통과 처리 (테스트는 부가 기능)
            return True, f"검증 스킵: {e}"

    # ========== 메인 생성 함수 ==========
    def generate(
        self,
        project_purpose: str,
        agents: List[Dict[str, str]],
        ai_config: Dict,
        max_fix_attempts: int = 2,
        skip_compress: bool = True,  # 기본적으로 압축 스킵 (상세함 유지)
        skip_test: bool = False
    ) -> GeneratedPrompts:
        """
        프롬프트 자동 생성 (단계별 코드 강제)

        Args:
            project_purpose: 프로젝트 목적
            agents: 에이전트 목록
            ai_config: AI 설정
            max_fix_attempts: 검증 실패 시 재시도 횟수
            skip_compress: 압축 단계 스킵
            skip_test: 테스트 단계 스킵
        """
        if not ai_config:
            raise ValueError("AI 설정이 필요합니다.")
        if not AIAgent:
            raise ValueError("AI 모듈을 로드할 수 없습니다.")

        # Step 1: 초안 생성
        print("[Step 1] 초안 생성 중...")
        prompts = self._step1_generate_draft(project_purpose, agents, ai_config)

        # Step 2: 규격 검증 (+ 수정 루프)
        print("[Step 2] 규격 검증 중...")
        for attempt in range(max_fix_attempts + 1):
            is_valid, errors = self._step2_validate(prompts)
            if is_valid:
                print(f"[Step 2] 검증 통과")
                break
            elif attempt < max_fix_attempts:
                print(f"[Step 2] 검증 실패, 수정 시도 {attempt + 1}/{max_fix_attempts}")
                prompts = self._step2_fix(prompts, errors, ai_config)
            else:
                print(f"[Step 2] 검증 실패 (최대 시도 초과): {errors}")
                # 실패해도 계속 진행 (경고만)

        # Step 3: 압축
        if not skip_compress:
            print("[Step 3] 압축 중...")
            prompts = self._step3_compress(prompts, ai_config)
        else:
            print("[Step 3] 압축 스킵")

        # Step 4: 예시 테스트
        if not skip_test:
            print("[Step 4] 예시 테스트 중...")
            test_passed, test_message = self._step4_test(prompts, agents, ai_config)
            print(f"[Step 4] {test_message}")
        else:
            print("[Step 4] 테스트 스킵")

        print("[완료] 프롬프트 생성 완료")
        return prompts

    def validate(self, prompts: GeneratedPrompts) -> List[str]:
        """외부용 검증 함수"""
        _, errors = self._step2_validate(prompts)
        return errors

    def save_to_project(self, prompts: GeneratedPrompts, project_path: str) -> Dict[str, str]:
        """생성된 프롬프트를 프로젝트에 저장"""
        project_path = Path(project_path)
        saved_files = {}

        # common_settings.txt 저장
        common_path = project_path / "common_settings.txt"
        common_path.write_text(prompts.common_settings, encoding='utf-8')
        saved_files["common_settings"] = str(common_path)

        # 에이전트별 역할 저장 (프로젝트 루트에 직접 저장)
        # switch_manager.py가 project_path / f"agent_{name}_role.txt" 경로를 사용함
        for agent_name, role in prompts.agent_roles.items():
            role_path = project_path / f"agent_{agent_name}_role.txt"
            role_path.write_text(role, encoding='utf-8')
            saved_files[f"role_{agent_name}"] = str(role_path)

        # txt 파일 저장 후 rules.json도 동기화
        try:
            from api import update_all_agents_rules_json
            update_all_agents_rules_json(project_path)
            print("[save_to_project] rules.json 동기화 완료")
        except ImportError:
            # api 모듈 없이 단독 실행 시 수동 동기화
            from my_conversations import MyConversations
            for agent_name in prompts.agent_roles.keys():
                note_file = project_path / f"agent_{agent_name}_note.txt"
                note_content = note_file.read_text(encoding='utf-8').strip() if note_file.exists() else ""
                MyConversations.save_rules_history(
                    agent_name=agent_name,
                    system_prompt=prompts.common_settings,
                    role=prompts.agent_roles[agent_name],
                    persistent_note=note_content,
                    project_path=str(project_path)
                )
            print("[save_to_project] rules.json 동기화 완료 (standalone)")

        return saved_files


# CLI 테스트
if __name__ == "__main__":
    import os

    generator = PromptGenerator()

    agents = [
        {"name": "집사", "role": "외부 사용자와 소통하고 작업을 조율", "type": "external"},
        {"name": "리서처", "role": "웹에서 정보를 검색하고 수집", "type": "internal"},
    ]

    ai_config = {
        "provider": os.environ.get("AI_PROVIDER", "google"),
        "model": os.environ.get("AI_MODEL", "gemini-2.0-flash"),
        "api_key": os.environ.get("GOOGLE_API_KEY", ""),
    }

    if not ai_config["api_key"]:
        print("GOOGLE_API_KEY 환경변수 필요")
        exit(1)

    result = generator.generate("뉴스레터 발행 팀", agents, ai_config)

    print("\n=== 공통 설정 ===")
    print(result.common_settings)
    print("\n=== 개별 역할 ===")
    for name, role in result.agent_roles.items():
        print(f"\n[{name}]")
        print(role)
