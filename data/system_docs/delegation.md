# 위임 체인 시스템 (Delegation Chain System)

에이전트 간 비동기 협업을 위한 핵심 메커니즘.

## 개요

```
사용자 → 에이전트A → call_agent(B) → 에이전트B → 작업 완료 → 자동 보고 → 에이전트A → 사용자
```

- `call_agent()` 도구로 다른 에이전트에게 작업 위임
- 위임받은 에이전트가 작업 완료 시 자동으로 결과 보고
- 위임한 에이전트는 결과를 받아 최종 처리 후 사용자에게 응답

## 핵심 컴포넌트

| 파일 | 역할 |
|------|------|
| `system_tools.py` | `call_agent()` 도구, 위임 컨텍스트 관리 |
| `agent_runner.py` | 자동 보고 체인, 메시지 큐 처리 |
| `conversation_db.py` | tasks 테이블 (태스크/위임 정보 저장) |
| `thread_context.py` | 스레드별 task_id, call_agent 플래그 |

## 태스크 (Task)

위임 시스템의 기본 단위. 하나의 요청에 대해 하나의 태스크가 생성됨.

### 태스크 필드

| 필드 | 설명 |
|------|------|
| `task_id` | 고유 ID (예: task_abc12345) |
| `requester` | 요청자 (예: user@gui, email@gmail) |
| `requester_channel` | 채널 (gui, gmail, nostr) |
| `original_request` | 원래 요청 내용 |
| `delegated_to` | 위임받은 에이전트 이름 |
| `parent_task_id` | 부모 태스크 ID (위임 체인) |
| `delegation_context` | 위임 컨텍스트 JSON |
| `pending_delegations` | 대기 중인 위임 수 |
| `ws_client_id` | WebSocket 클라이언트 ID (GUI 응답용) |

## 위임 컨텍스트 (Delegation Context)

위임 시 부모 태스크에 저장되는 컨텍스트. 보고 수신 시 복원되어 AI에게 전달.

```json
{
  "original_request": "사용자의 원래 요청",
  "requester": "user@gui",
  "delegations": [
    {
      "child_task_id": "task_001",
      "delegated_to": "에이전트B",
      "delegation_message": "이것 좀 해줘",
      "delegation_time": "2026-01-18T10:00:00"
    }
  ],
  "responses": [
    {
      "child_task_id": "task_001",
      "from_agent": "에이전트B",
      "response": "완료했습니다. 결과는...",
      "completed_at": "2026-01-18T10:05:00"
    }
  ]
}
```

### 컨텍스트 생명주기

위임 컨텍스트는 태스크와 함께 관리됨:

| 시점 | 동작 |
|------|------|
| 위임 발생 | `delegation_context`에 위임 정보 누적 |
| 위임 결과 도착 | `responses`에 결과 누적, `pending_delegations` 감소 |
| 추가 위임 없음 | 태스크 삭제 (`complete_task`) → 컨텍스트도 삭제 |
| 추가 위임 발생 | 태스크 유지, 새 위임 정보 누적 |

**핵심**: 태스크가 삭제되면 컨텍스트도 함께 삭제됨. 별도의 클리어 호출 불필요.

## 위임 흐름

### 1. 단일 위임

```
사용자 "X 해줘"
    ↓
에이전트A (task_001 생성)
    ↓
call_agent(B, "Y 해줘") → 에이전트B (task_002 생성, parent=task_001)
    ↓                              ↓
did_call_agent=True                작업 수행
    ↓                              ↓
자동 보고 스킵                    _auto_report_to_chain()
                                       ↓
                              task_002 삭제, A에게 보고
                                       ↓
                              에이전트A가 결과 수신 (컨텍스트 복원)
                                       ↓
                              최종 처리 후 사용자에게 응답
                                       ↓
                              task_001 삭제
```

### 2. 순차 위임 (결과 의존성)

이전 위임 결과가 다음 위임에 필요한 경우:

```
에이전트A
    ↓
call_agent(B, "1차 작업")
    ↓
pending_delegations = 1
    ↓
B 완료 → 에이전트A가 결과 수신 및 처리
    ↓
call_agent(C, "1차 결과 바탕으로 2차 작업")
    ↓
pending_delegations = 1 (위임 컨텍스트에 누적)
    ↓
C 완료 → 에이전트A가 결과 수신 및 처리
    ↓
추가 위임 없음 → 최종 응답, 태스크 삭제
```

**핵심**: 위임 결과가 컨텍스트에 누적되어 AI가 이전 작업 내역을 참조할 수 있음. 추가 위임이 없으면 태스크가 삭제되며 컨텍스트도 함께 삭제됨.

### 3. 병렬 위임 (2개 이상, 동시)

```
에이전트A
    ↓
call_agent(B), call_agent(C), call_agent(D)  ← 한 턴에 여러 위임
    ↓
pending_delegations = 3
    ↓
B 완료 → responses에 누적, pending=2, 보고 대기
C 완료 → responses에 누적, pending=1, 보고 대기
D 완료 → responses에 누적, pending=0, 통합 보고 전송
    ↓
에이전트A가 "[병렬 위임 결과 통합 보고]" 수신
    ↓
추가 위임 없음 → 최종 응답, 태스크 삭제
```

### 4. 위임 체인 (재귀)

```
A → B → C → D
```

각 단계는 동일한 구조:
1. 태스크 생성
2. 작업 수행 (위임 포함 가능)
3. 자동 보고
4. 태스크 삭제

## 자동 보고 시스템

### _auto_report_to_chain() 동작

1. **parent_task_id 있음** (위임받은 태스크)
   - 부모 태스크의 `delegation_context`에 응답 누적
   - `pending_delegations` 감소
   - 병렬 위임 수집 모드:
     - 남은 위임 있음 → 현재 태스크만 삭제, 보고 스킵
     - 모든 응답 도착 → 통합 보고 전송
   - 부모 태스크의 `delegated_to` 에이전트에게 보고

2. **parent_task_id 없음** (최초 태스크)
   - 채널에 따라 사용자에게 최종 응답:
     - gui: WebSocket (`ws_client_id`)
     - gmail/nostr: 해당 채널로 전송

### 보고 대상 결정

```
현재 태스크
    ↓
parent_task_id 있음?
    ↓ YES
parent_task.delegated_to = 보고 대상 에이전트
    ↓ NO
requester_channel로 사용자에게 직접 응답
```

## 시스템 도구

### call_agent

```python
call_agent(
    agent_id="에이전트이름",  # 또는 agent_id
    message="요청 내용"
)
```

동작:
1. 대상 에이전트 찾기 (`AgentRunner.get_agent_by_name`)
2. 자식 태스크 생성 (`_create_child_task`)
3. 위임 컨텍스트 업데이트 (`_get_or_create_delegation_context`)
4. `internal_messages`에 메시지 추가
5. `set_called_agent(True)` → 자동 보고 스킵 플래그

### list_agents

현재 프로젝트의 에이전트 목록 조회. 위임 전 적합한 대상 확인용.

### get_my_tools

자신이 가진 도구 목록 조회. 위임 전 자가 처리 가능 여부 판단용.

## 컨텍스트 복원

보고 메시지 수신 시 AI에게 위임 컨텍스트 리마인더 주입:

```
[시스템 알림 - 위임 컨텍스트 복원]
당신이 이전에 2개의 작업을 위임했을 때의 상황입니다:
- 원래 요청자: user@gui
- 원래 요청 내용: X 해줘
- 위임 내역:
  1. 에이전트B: Y 해줘
  2. 에이전트C: Z 해줘
이제 모든 위임한 작업의 결과가 도착했습니다...

---
[위임 결과 보고]
...
```

## 응답 전달 원칙

### 메시지 전달 vs 히스토리

| 구분 | 원칙 |
|------|------|
| **메시지 전달** | 응답을 자르면 안 됨. 전체 내용 전달 |
| **히스토리/컨텍스트** | 이전 기록이므로 축약 가능 |

### 긴 응답 처리

2000자 초과 응답은 파일로 저장하고 경로 전달:

```python
if len(response) > 2000:
    result_file = outputs_dir / f"result_{task_id}.txt"
    result_file.write_text(response)
    result_summary = f"[작업 완료] 상세 결과: {result_file}\n\n요약:\n{response[:500]}..."
else:
    result_summary = response  # 전체 응답
```

**위치**: `agent_runner.py` → `_auto_report_to_chain()`

### 파일 경로 원칙

파일 위치를 보고할 때는 **절대경로**를 사용:

```python
# 올바른 예
result_summary = f"결과 파일: /Users/.../projects/홍보/outputs/slides_abc123"

# 잘못된 예 (상대경로)
result_summary = f"결과 파일: outputs/slides_abc123"
```

**이유**: 시스템 AI와 프로젝트 에이전트의 작업 디렉토리가 다름
- 시스템 AI: `data/`
- 프로젝트 에이전트: `projects/{project_id}/`

상대경로 사용 시 파일을 찾을 수 없음.

### 스테이트리스 원칙

위임받는 에이전트는 **스테이트리스(stateless)** 상태:
- 이전에 무슨 작업을 했는지 기억하지 못함
- 위임 메시지에 **작업에 필요한 모든 정보**를 포함해야 함
- **원래 요청의 조건/제약사항**도 매번 포함해야 함

**중요**: 순차 위임 시 처음 받은 조건을 계속 전달해야 함.
에이전트는 이전 위임의 조건을 기억하지 못함.

```python
# ❌ 잘못된 예 (컨텍스트 의존)
call_agent("스토리텔러", "아까 만든 슬라이드 수정해줘")

# ❌ 잘못된 예 (조건 누락)
# 첫 번째 위임: "이미지 생성 없이 슬라이드 만들어줘"
# 두 번째 위임: "개선해서 최종 슬라이드 만들어줘"  # 조건 누락!

# ✅ 올바른 예 (완전한 정보 제공)
call_agent("스토리텔러", """
다음 슬라이드 파일을 수정해줘:
- 경로: /Users/.../outputs/slides_abc123
- 수정사항: 3번 슬라이드 제목을 '새로운 시작'으로 변경
""")

# ✅ 올바른 예 (조건 유지)
# 첫 번째 위임: "이미지 생성 없이 Tailwind CSS만 사용해서 슬라이드 만들어줘"
# 두 번째 위임: """
# 이미지 생성 없이 Tailwind CSS만 사용하는 조건 유지.
# 슬라이드 파일: /Users/.../outputs/slides_abc123
# 개선 후 최종 슬라이드와 영상 제작해줘
# """
```

## 주의사항

1. **자기 자신에게 위임 금지**
2. **에이전트가 1명뿐이면 위임 불가** (직접 처리)
3. **위임 체인 깊이 제한** (무한 루프 방지)
4. **응답을 임의로 자르지 말 것** (긴 응답은 파일로 저장)
5. **환각 방지**: 결과를 받지 않은 상태에서 "검토했습니다", "확인했습니다" 등 표현 금지
6. **스테이트리스 원칙**: 위임받는 에이전트는 이전 작업을 모름 - 필요한 모든 정보 포함
7. **조건 전달 원칙**: 순차 위임 시 원래 요청의 조건/제약사항을 매번 포함

---

## 시스템 AI 위임 (System AI Delegation)

시스템 AI가 프로젝트 에이전트에게 작업을 위임하는 시스템.

### 개요

```
사용자 → 시스템AI → call_project_agent(P, A) → 프로젝트P.에이전트A → 작업 완료 → 자동 보고 → 시스템AI → 사용자
```

- **일방향 위임**: 시스템 AI → 프로젝트 에이전트 (역방향 불가)
- 프로젝트 내부의 `call_agent()` 위임 체인과 동일한 구조 사용
- 시스템 AI Runner가 상주 프로세스로 동작하며 메시지 큐 처리

### 핵심 컴포넌트

| 파일 | 역할 |
|------|------|
| `system_ai_runner.py` | 시스템 AI 상주 프로세스, 메시지 큐 처리 |
| `system_ai_memory.py` | 시스템 AI용 tasks 테이블 |
| `api_system_ai.py` | `call_project_agent` 도구 정의/실행 |
| `agent_runner.py` | `system_ai` 채널 처리, 보고 전송 |

### 새 채널: system_ai

`requester_channel`에 새 값 추가:

| 채널 | 응답 대상 |
|------|----------|
| `gui` | WebSocket으로 GUI에 전송 |
| `gmail` | 이메일 회신 |
| `nostr` | Nostr로 회신 |
| `system_ai` | 시스템 AI에게 보고 (NEW) |

### call_project_agent 도구

```python
call_project_agent(
    project_id="프로젝트ID",
    agent_id="에이전트ID",
    message="요청 내용"
)
```

동작:
1. `AgentRunner.agent_registry`에서 대상 에이전트 찾기
2. 부모 태스크(시스템 AI)의 위임 컨텍스트 업데이트
3. 프로젝트 에이전트의 DB에 자식 태스크 생성
4. 에이전트의 `internal_messages` 큐에 메시지 추가
5. `set_called_agent(True)` 플래그 설정

### 위임 흐름

```
사용자 "전체 분석해줘" (GUI)
    ↓
시스템AI (task_sysai_001 생성)
    ↓
call_project_agent("projectA", "analyst", "매출 분석해줘")
    ↓ did_call_agent=True → 자동 보고 스킵
프로젝트A.analyst (task_002 생성, parent=task_sysai_001, channel=system_ai)
    ↓
작업 수행
    ↓
_auto_report_to_chain()
    ↓ channel == 'system_ai'
_send_to_system_ai() → SystemAIRunner.send_message()
    ↓
task_002 삭제
    ↓
시스템AI가 internal_messages에서 결과 수신
    ↓
컨텍스트 복원 후 최종 처리
    ↓
사용자에게 응답 (WebSocket)
    ↓
task_sysai_001 삭제
```

### SystemAIRunner 클래스

상주 프로세스로 동작하는 시스템 AI 실행기:

```python
class SystemAIRunner:
    internal_messages: List[dict] = []  # 메시지 큐
    _instance: Optional['SystemAIRunner'] = None  # 싱글톤

    @classmethod
    def send_message(cls, content: str, from_agent: str, task_id: str = None):
        """외부에서 시스템 AI에게 메시지 전송"""

    def _run_loop(self):
        """백그라운드 루프 - 1초마다 메시지 큐 폴링"""

    def _check_internal_messages(self):
        """메시지 처리 및 AI 응답 생성"""
```

### 순차/병렬 위임 지원

시스템 AI도 프로젝트 에이전트와 동일한 위임 패턴 지원:

**순차 위임** (결과 의존):
```
시스템AI → call_project_agent(A, "1차") → A 완료 → 결과 수신
    ↓
call_project_agent(B, "1차 결과로 2차") → B 완료 → 결과 수신
    ↓
추가 위임 없음 → 최종 응답, 태스크 삭제
```

**병렬 위임** (동시):
```
시스템AI
    ↓
call_project_agent(A), call_project_agent(B), call_project_agent(C)
    ↓
pending_delegations = 3
    ↓
A 완료 → pending=2, 대기
B 완료 → pending=1, 대기
C 완료 → pending=0, 통합 보고 → 시스템AI
    ↓
추가 위임 없음 → 최종 응답, 태스크 삭제
```

### 프로젝트 자동 활성화

`call_project_agent` 호출 시 대상 에이전트가 실행 중이 아니면:
1. 해당 프로젝트의 **모든 활성 에이전트**를 자동 시작
2. 프로젝트 팀 단위로 작업 수행
3. 프로젝트 내부에서 자체 위임 체인 사용 가능

```
시스템AI → call_project_agent("의료", "내과", "두통 진단")
    ↓
프로젝트 "의료" 전체 활성화 (내과, 비뇨기과, 심장전문, ...)
    ↓
"내과"가 작업 수행
    ↓ (필요시)
내과 → call_agent("심장전문", "심장 관련 확인")
```

### 프로젝트 내부 위임과 동일한 원칙

| 기능 | 프로젝트 내부 | 시스템 AI |
|------|-------------|-----------|
| 단일 위임 | ✓ | ✓ |
| 병렬 위임 | ✓ | ✓ |
| 위임 컨텍스트 | ✓ | ✓ |
| 자동 보고 | ✓ | ✓ |
| 컨텍스트 복원 | ✓ | ✓ |

### 주의사항

1. **일방향만 가능**: 프로젝트 에이전트는 시스템 AI에게 위임 불가
2. **프로젝트 팀 단위**: 위임 시 프로젝트 전체 에이전트가 활성화됨
3. **태스크 저장 위치**:
   - 시스템 AI 태스크 → `data/system_ai_memory.db`
   - 프로젝트 에이전트 태스크 → 프로젝트별 `conversation.db`
4. **환각 방지**: 결과 없이 "검토했습니다" 등 표현 금지

---
*마지막 업데이트: 2026-01-26*
*변경: 긴 응답 파일 저장 정책 추가, 컨텍스트 클리어 → 태스크 삭제로 정리*

> 참고: 위임 프롬프트 파일
> - `fragments/09_delegation.md`: 프로젝트 내 에이전트 간 위임 가이드
> - `fragments/10_system_ai_delegation.md`: 시스템 AI → 프로젝트 에이전트 위임 가이드
