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

### 컨텍스트 초기화

새 위임 사이클 시작 시 이전 컨텍스트 자동 초기화:
- 조건: `len(responses) >= len(delegations)` (모든 응답 수신 완료)
- 위치: `_get_or_create_delegation_context()` 함수

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

### 2. 병렬 위임 (2개 이상)

```
에이전트A
    ↓
call_agent(B), call_agent(C), call_agent(D)
    ↓
pending_delegations = 3
    ↓
B 완료 → responses에 누적, pending=2, 보고 대기
C 완료 → responses에 누적, pending=1, 보고 대기
D 완료 → responses에 누적, pending=0, 통합 보고 전송
    ↓
에이전트A가 "[병렬 위임 결과 통합 보고]" 수신
```

### 3. 위임 체인 (재귀)

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

## 주의사항

1. **자기 자신에게 위임 금지**
2. **에이전트가 1명뿐이면 위임 불가** (직접 처리)
3. **위임 체인 깊이 제한** (무한 루프 방지)
4. **위임 컨텍스트는 위임 사이클 완료 시 자동 초기화**

---
*마지막 업데이트: 2026-01-18*
