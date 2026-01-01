# 대화 관리 확장

## 목적

에이전트와 사용자 간의 대화 히스토리를 저장하고 관리합니다.
이 확장이 있어야 에이전트가 이전 대화를 기억하고 맥락을 유지할 수 있습니다.

## 이 확장이 제공하는 것

- **대화 저장**: 모든 메시지를 데이터베이스에 기록
- **히스토리 로드**: AI 호출 시 이전 대화를 함께 전달
- **위임 추적**: 에이전트 간 작업 위임 체인 기록
- **이웃 관리**: 각 에이전트의 대화 상대(이웃) 관리

## 설치 시 필요한 변경사항

### 1. 데이터베이스 스키마

대화를 저장할 테이블 구조가 필요합니다.

```
agents (주체 테이블)
├── id: 고유 식별자
├── name: 이름
└── type: user / ai_agent

neighbors (이웃 테이블)
├── agent_id: 주체
├── neighbor_id: 대화 상대
└── contact_type: gui / nostr / gmail 등

messages (메시지 테이블)
├── id: 메시지 ID
├── from_agent: 발신자
├── to_agent: 수신자
├── content: 내용
├── timestamp: 시간
└── contact_type: 채널 종류

tasks (작업 테이블 - 위임 추적용)
├── id: 작업 ID
├── from_agent: 위임한 에이전트
├── to_agent: 위임받은 에이전트
├── message: 작업 내용
├── status: pending / completed
└── result: 결과
```

### 2. 메시지 저장/조회

대화를 저장하고 불러오는 기능이 필요합니다.

**저장:**
- send_message(from, to, content, contact_type)
- receive_message(from, to, content, contact_type)

**조회:**
- get_conversation_history(agent_id, neighbor_id, limit)
- format_history_for_ai(history) → AI API 형식으로 변환

### 3. 히스토리 제한

무한히 쌓이면 컨텍스트 한도를 초과합니다.

```python
HISTORY_LIMIT_USER = 5    # 사용자와의 대화: 최근 5쌍
HISTORY_LIMIT_AGENT = 4   # 에이전트 간 대화: 최근 4쌍
```

오래된 대화에는 마커를 추가:
```
[과거 대화 - 이미 처리 완료됨]
```

### 4. 위임 작업 추적

에이전트 간 위임을 추적해야 합니다.

```
1. A가 B에게 작업 위임
2. task 생성 (status: pending)
3. B가 작업 완료
4. task 업데이트 (status: completed, result: ...)
5. A에게 결과 전달
```

위임 체인 추적으로 복잡한 협업도 관리 가능합니다.

### 5. 에이전트 연동

에이전트가 대화 기능을 사용할 수 있어야 합니다.

```python
# AI 호출 전
history = conversation.get_history_for_ai(neighbor_id)
messages = history + [{"role": "user", "content": new_message}]
response = ai.call(messages)

# AI 응답 후
conversation.save_message(agent_id, neighbor_id, response, "gui")
```

### 6. 시스템 프롬프트 저장

역할, 공통 설정, 메모를 저장해야 합니다.

```json
// rules.json
{
  "messages": [
    {"role": "user", "content": "[시스템 규칙]\n..."},
    {"role": "user", "content": "[당신의 역할]\n..."},
    {"role": "user", "content": "[지속 메모]\n..."}
  ]
}
```

AI 호출 시 이 메시지들이 먼저 전달됩니다.

## 설계 고려사항

### 저장 위치
- 프로젝트별로 별도 DB 파일
- `project_001/conversations.db`

### 메시지 합치기
- 연속된 같은 role의 메시지는 하나로 합침
- AI API 규격 준수 (user-assistant 교대)

### 마이그레이션
- 스키마 변경 시 기존 데이터 이전 고려

## 참고 구현

이 폴더의 파일들은 Python + SQLite 기반 예시입니다.

```
conversation_db.py    - 데이터베이스 직접 관리
my_conversations.py   - 에이전트별 래퍼 클래스
```

### 의존성
```bash
# 별도 설치 필요 없음 (Python 표준 라이브러리 sqlite3)
```

이 코드를 그대로 사용하지 말고, 현재 시스템에 맞게 구현하세요.

## 설치 완료 확인

- [ ] 대화가 데이터베이스에 저장됨
- [ ] AI 호출 시 이전 대화가 함께 전달됨
- [ ] 히스토리 제한이 적용됨
- [ ] 에이전트 간 위임이 추적됨
- [ ] 시스템 프롬프트가 저장/로드됨
