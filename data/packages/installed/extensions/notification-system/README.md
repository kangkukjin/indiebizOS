# Notification System 확장

## 목적

시스템과 에이전트의 알림을 사용자에게 전달합니다.
에이전트 작업 완료, 오류 발생, 스케줄러 이벤트 등을 실시간으로 알려줍니다.

## 이 확장이 제공하는 것

- **실시간 알림**: WebSocket을 통한 즉시 알림 전송
- **알림 히스토리**: 지난 알림 조회
- **알림 유형**: 정보, 성공, 경고, 오류 등 구분
- **읽음 표시**: 알림 확인 상태 관리

## 설치 시 필요한 변경사항

### 1. 알림 데이터 저장

SQLite 또는 메모리에 알림을 저장합니다.

알림 데이터 구조:
- id: 고유 식별자
- type: info, success, warning, error
- title: 알림 제목
- message: 알림 내용
- source: 발생 주체 (에이전트명, 시스템 등)
- created_at: 생성 시간
- read: 읽음 여부

### 2. API 엔드포인트

```
GET  /notifications           # 알림 목록
GET  /notifications/unread    # 읽지 않은 알림 수
POST /notifications           # 알림 생성
PUT  /notifications/{id}/read # 읽음 표시
DELETE /notifications/{id}    # 알림 삭제
```

### 3. 다른 확장과의 연동

- **websocket-chat**: 실시간 알림 전송
- **scheduler**: 스케줄 작업 완료 알림
- **ai-agent**: 에이전트 작업 완료/오류 알림

### 4. 프론트엔드 통합

- 알림 벨 아이콘
- 읽지 않은 알림 개수 표시
- 알림 드롭다운 또는 패널
- 토스트 팝업 (새 알림 시)

## 참고 구현

```python
# notification_manager.py

from datetime import datetime
from typing import List, Dict, Any
import uuid

class NotificationManager:
    def __init__(self):
        self.notifications: List[Dict[str, Any]] = []

    def create(self, type: str, title: str, message: str, source: str = "system") -> Dict:
        notification = {
            "id": str(uuid.uuid4()),
            "type": type,  # info, success, warning, error
            "title": title,
            "message": message,
            "source": source,
            "created_at": datetime.now().isoformat(),
            "read": False
        }
        self.notifications.insert(0, notification)
        return notification

    def get_all(self, limit: int = 50) -> List[Dict]:
        return self.notifications[:limit]

    def get_unread_count(self) -> int:
        return sum(1 for n in self.notifications if not n["read"])

    def mark_read(self, notification_id: str) -> bool:
        for n in self.notifications:
            if n["id"] == notification_id:
                n["read"] = True
                return True
        return False
```

## 설치 완료 확인

- [ ] 알림 생성 API 동작
- [ ] 알림 목록 조회 가능
- [ ] 읽음 표시 동작
- [ ] 프론트엔드에 알림 표시됨
