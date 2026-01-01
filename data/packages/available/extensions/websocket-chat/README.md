# WebSocket 채팅 확장

## 목적

에이전트와 실시간으로 대화할 수 있게 합니다.
HTTP 폴링 대신 WebSocket을 사용하여 즉각적인 응답과 스트리밍이 가능합니다.

## 이 확장이 제공하는 것

- **실시간 양방향 통신**: 메시지를 보내면 즉시 응답 수신
- **스트리밍 응답**: AI 응답이 생성되는 대로 실시간 표시
- **자동 보고**: 에이전트가 위임 작업 완료 시 자동 알림
- **연결 관리**: 여러 클라이언트의 동시 연결 처리

## 설치 시 필요한 변경사항

### 1. WebSocket 서버

WebSocket 연결을 받을 엔드포인트가 필요합니다.

```
엔드포인트: /ws/chat/{client_id}
프로토콜: WebSocket
```

각 클라이언트는 고유 ID로 연결하고, 서버는 이를 관리합니다.

### 2. 메시지 프로토콜

클라이언트와 서버 간 메시지 형식을 정의해야 합니다.

**클라이언트 → 서버:**
```json
{
  "type": "chat",
  "message": "안녕하세요",
  "agent_name": "집사",
  "project_id": "project_001",
  "images": []
}
```

**서버 → 클라이언트:**
```json
// 응답 시작
{"type": "start"}

// 응답 내용 (스트리밍)
{"type": "response", "content": "안녕"}
{"type": "response", "content": "하세요!"}

// 응답 완료
{"type": "end"}

// 자동 보고 (위임 작업 완료)
{"type": "auto_report", "content": "작업이 완료되었습니다"}

// 에러
{"type": "error", "message": "에이전트를 찾을 수 없습니다"}
```

### 3. 연결 관리자

여러 클라이언트의 연결을 관리해야 합니다.

필요한 기능:
- 연결 등록 (connect)
- 연결 해제 (disconnect)
- 특정 클라이언트에 메시지 전송
- 브로드캐스트 (전체 전송)
- 연결 상태 ping/pong

### 4. 에이전트 연동

메시지를 받으면 해당 에이전트를 호출해야 합니다.

```
1. WebSocket 메시지 수신
2. project_id와 agent_name으로 에이전트 찾기
3. 에이전트가 실행 중인지 확인
4. 대화 히스토리 로드
5. AI 호출 (스트리밍)
6. 응답을 WebSocket으로 전송
7. 히스토리에 저장
```

### 5. 프론트엔드 연결

UI에서 WebSocket을 사용해야 합니다.

```javascript
// 연결
const ws = new WebSocket(`ws://localhost:8000/ws/chat/${clientId}`);

// 수신
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // type에 따라 처리
};

// 발신
ws.send(JSON.stringify({
  type: 'chat',
  message: '...',
  ...
}));
```

### 6. 연결 유지

네트워크 불안정에 대비해야 합니다.

- ping/pong으로 연결 상태 확인
- 연결 끊김 시 자동 재연결
- 재연결 시 이전 상태 복구

## 설계 고려사항

### 스트리밍 vs 일괄
- AI 응답을 토큰 단위로 스트리밍할 것인지
- 완성 후 일괄 전송할 것인지
- 스트리밍이 UX에 좋지만 구현이 복잡

### 동시성
- 한 클라이언트가 여러 메시지를 빠르게 보내면?
- 메시지 큐로 순서 보장 권장

### 보안
- 인증된 사용자만 연결 허용
- project_id, agent_name 접근 권한 확인

## 참고 구현

이 폴더의 `api_websocket.py`는 FastAPI + websockets 기반 예시입니다.

```
api_websocket.py
├── WebSocketManager    - 연결 관리
├── ws_chat()           - 채팅 엔드포인트
└── 메시지 처리 로직
```

### 의존성 (Python 구현)
```bash
pip install fastapi websockets
```

이 코드를 그대로 사용하지 말고, 현재 시스템에 맞게 구현하세요.

## 설치 완료 확인

- [ ] WebSocket 엔드포인트가 동작함
- [ ] 클라이언트가 연결/해제됨
- [ ] 메시지를 보내면 AI 응답이 실시간으로 옴
- [ ] 여러 클라이언트가 동시에 연결 가능
- [ ] 연결이 끊겨도 재연결됨
