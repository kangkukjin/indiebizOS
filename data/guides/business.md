# 비즈니스 창 가이드

이 가이드는 AI 에이전트가 **비즈니스 창(BusinessManager)**의 데이터를 조회하고 편집하는 방법을 설명합니다. 비즈니스 창은 사용자의 이웃·비즈니스 영역·아이템·메시지를 통합 관리하는 indiebizOS의 핵심 도메인입니다.

> **사용 원칙**: 비즈니스 도메인은 액션을 미리 정의하지 않고 **이 가이드 + DB 직접 접근 + REST API**로 처리합니다. 사용자마다 비즈니스 형태가 다르고 진화하기 때문입니다. 외부 통신(이메일 발신, Nostr DM)만 별도 액션(`[limbs:gmail_send]`, `[others:indienet_send]` 등)을 거칩니다.

---

## 1. 도메인 개념

### 비즈니스(business) — "내가 이웃에게 제공하거나 요청하는 것의 종류"

기본 7개 영역 (시스템 초기화 시 자동 생성):

| 이름 | 의미 |
|---|---|
| 나눕니다 | 기부·나눔 |
| 구합니다 | 구인·구직·구매 요청 |
| 놉시다 | 함께 할 일 (모임·활동) |
| 빌려줍니다 | 대여·렌탈 |
| 소개합니다 | 소개·추천 |
| 팔아요 | 판매 |
| 할수있습니다 | 서비스 제공 |

이건 거래 분류가 아니라 **관계 기반 교환의 명명법**입니다. 사용자가 자유롭게 추가·수정 가능.

### 이웃(neighbor) — 관계의 단위

`name`은 표시 이름이고, **실제 연락은 `contacts` 테이블의 contact_type + contact_value 쌍**으로 이루어집니다. 한 이웃은 여러 연락 수단을 가질 수 있음 (이메일 + Nostr 등).

### 레벨(level) 시스템 — 정보 공개 통제 ⭐

비즈니스 도메인의 핵심 의미는 **레벨 시스템**에 있습니다:

- 모든 비즈니스에 `level` (0~4) 부여
- 모든 이웃에 `info_level` (0~4) 부여
- **각 이웃에게는 그 이웃의 info_level 이하 비즈니스만 공개**
- `business_documents` 테이블이 레벨별로 자동 생성된 "공개 비즈니스 목록"을 보관

| level | 의미 (관례) |
|---|---|
| 0 | 가장 공개적 — 누구에게나 |
| 1~3 | 단계적 공개 |
| 4 | 가장 친밀한 관계에만 |

`info_share=0`인 이웃은 비공개 — 정보 공유 안 함.

---

## 2. 데이터 구조 (business.db)

DB 위치: `data/business.db`

```sql
businesses        -- 비즈니스 영역
  id, name, level (0~4), description, created_at, updated_at

business_items    -- 비즈니스 안의 구체적 아이템
  id, business_id (FK→businesses), title, details, attachment_path, ...

business_documents  -- 레벨별 자동 생성 공개 문서 (5행 고정, level UNIQUE)
  id, level (0~4), title, content, updated_at

work_guidelines     -- 레벨별 수동 작성 근무 지침 (5행 고정, level UNIQUE)
  id, level (0~4), title, content, updated_at

neighbors         -- 이웃
  id, name, info_level (0~4), rating, additional_info, business_doc,
  info_share (0=비공개/1=공개), favorite, created_at, updated_at

contacts          -- 이웃별 연락 수단 (1:N)
  id, neighbor_id (FK→neighbors), contact_type, contact_value, created_at

messages          -- 메시지 이력 (이웃과의 송수신)
  id, neighbor_id (nullable), subject, content, message_time,
  is_from_user (0=받음/1=보냄), contact_type, contact_value, attachment_path,
  status, error_message, sent_at, processed, replied, external_id, created_at

channel_settings  -- 통신 채널 (gmail, nostr 등)
  id, channel_type, enabled, config (JSON), polling_interval, last_poll_at
```

### attachment_path 형식
- JSON 배열: `'["path/to/img1.jpg","path/to/img2.jpg"]'`
- 레거시 단일 경로 호환: `'path/to/img.jpg'`

### contact_type 표준값
- `email` — 이메일 주소
- `nostr` — Nostr npub (자동 변환됨, hex가 들어와도 npub로 정규화)
- `telegram`, `matrix`, `phone`, `sms` 등 (확장 가능)

---

## 3. REST API (백엔드 http://127.0.0.1:8765, prefix `/business`)

### 비즈니스 영역
- `GET /business` — 목록 (params: `level`, `search`)
- `POST /business` — 생성 (`{name, level, description}`)
- `GET /business/{id}` — 단건
- `PUT /business/{id}` / `DELETE /business/{id}`

### 비즈니스 아이템
- `GET /business/{business_id}/items`
- `POST /business/{business_id}/items`
- `PUT /business/items/{item_id}` / `DELETE /business/items/{item_id}`

### 문서·지침
- `GET /business/documents/all` — 5개 레벨 문서 전체
- `GET /business/documents/{level}` / `PUT /business/documents/{level}`
- `POST /business/documents/regenerate` — **자동 재생성** (businesses + items로부터)
- `GET /business/guidelines/all` 등 동일 패턴

### 이웃
- `GET /business/neighbors` (params: `search`, `info_level`)
- `POST /business/neighbors`
- `GET/PUT/DELETE /business/neighbors/{id}`
- `GET /business/neighbors/favorites/list`
- `POST /business/neighbors/{id}/favorite/toggle`

### 연락 수단
- `GET /business/neighbors/{id}/contacts`
- `POST /business/neighbors/{id}/contacts` (`{contact_type, contact_value}`)
- `PUT/DELETE /business/contacts/{contact_id}`

### 메시지
- `GET /business/messages` (params: `neighbor_id`, `is_from_user`, `status`, `processed`, `replied`, `limit`)
- `POST /business/messages` — 메시지 기록 생성 (외부 발송과 별개, 기록용)
- `GET /business/messages/{id}`
- `PUT /business/messages/{id}/status`
- `POST /business/messages/{id}/processed` / `.../replied`

### 채널·자동 응답
- `GET /business/channels` — 전체 채널 상태
- `PUT /business/channels/{type}` — 채널 설정
- `POST /business/channels/{type}/poll` — 즉시 폴링
- `POST /business/channels/gmail/authenticate` — Gmail OAuth
- `GET /business/auto-response/status`
- `POST /business/auto-response/start` / `.../stop`

---

## 4. 자주 쓰는 작업 패턴

### 4.1 이웃 검색 / 확인
```python
# REST 호출
GET /business/neighbors?search=통닭

# 또는 DB 직접 조회 (SQLite)
SELECT n.*, GROUP_CONCAT(c.contact_type || ':' || c.contact_value, '; ') AS contacts
FROM neighbors n
LEFT JOIN contacts c ON c.neighbor_id = n.id
WHERE n.name LIKE '%통닭%'
GROUP BY n.id;
```

### 4.2 새 이웃 등록 + 연락 수단 추가
```python
# 1) 이웃 생성
POST /business/neighbors {"name": "통닭집 사장님", "info_level": 1}
# → returns {"id": 8, ...}

# 2) 연락처 추가
POST /business/neighbors/8/contacts {"contact_type": "phone", "contact_value": "010-xxxx"}
POST /business/neighbors/8/contacts {"contact_type": "nostr", "contact_value": "npub1..."}
```

### 4.3 이웃과의 과거 메시지 조회
```sql
SELECT m.created_at, m.is_from_user, m.subject, m.content, m.contact_type
FROM messages m
WHERE m.neighbor_id = ?
ORDER BY m.created_at DESC
LIMIT 50;
```

### 4.4 미처리 수신 메시지 찾기
```python
GET /business/messages?is_from_user=0&processed=0
```

### 4.5 비즈니스 아이템 추가
```python
# 1) "팔아요" 비즈니스 id 찾기
GET /business?search=팔아요

# 2) 아이템 추가
POST /business/{business_id}/items {
  "title": "안 쓰는 모니터",
  "details": "27인치 4K, 거의 새것",
  "attachment_path": null
}

# 3) 문서 재생성 (옵션)
POST /business/documents/regenerate
```

### 4.6 메시지 발신 (외부) — IBL 액션 경유

비즈니스 DB는 **기록**만 담당합니다. 실제 발신은 별도 채널을 통해:

```
이메일 발신:  [limbs:gmail_send]  또는 Gmail API 직접 호출
Nostr 발신:   [others:indienet_send]  (구현 예정) 또는 indienet 모듈 직접
```

발신 후 `POST /business/messages`로 기록을 남기는 것이 권장 패턴:

```python
POST /business/messages {
  "neighbor_id": 8,
  "subject": "주문 확인",
  "content": "내일 6시 통닭 2마리 부탁드립니다",
  "contact_type": "phone",
  "contact_value": "010-xxxx",
  "is_from_user": 1,
  "status": "sent"
}
```

---

## 5. AI 에이전트 작업 흐름

비즈니스 관련 요청이 들어왔을 때 권장 흐름:

```
사용자 요청
    ↓
1. 이 가이드 로드
    ↓
2. 요청 유형 분류
   ├ 조회: SELECT (DB 직접) 또는 GET (REST)
   ├ 변경: INSERT/UPDATE (DB 직접) 또는 POST/PUT (REST)
   ├ 발신: [limbs:gmail_send] / [others:indienet_send] + 기록
   └ 분석: 조회 + [engines:summarize] 등 조합
    ↓
3. 결과 확인 (변경의 경우 SELECT으로 검증)
    ↓
4. 사용자에게 보고
```

### REST vs DB 직접 — 선택 기준
- **REST 사용**: 트리거·검증·연쇄 작업이 있을 가능성 (자동 응답, 폴러, WebSocket 알림 등)
- **DB 직접**: 단순 조회, 집계, 복잡한 JOIN, 일회성 데이터 정리

확실하지 않으면 REST를 우선.

---

## 6. 외부 시스템 연결 지도

비즈니스 도메인은 단독으로 작동하지 않고 다음 시스템들과 엮입니다:

| 외부 | 연결 지점 | 비고 |
|---|---|---|
| **Gmail** | `channel_settings.gmail` + Gmail API | 이메일 수신은 channel_poller가 polling, messages 테이블에 자동 저장 |
| **IndieNet/Nostr** | `channel_settings.nostr` + indienet 모듈 | DM 수신 자동 기록. Nostr npub은 자동 정규화 |
| **자동 응답** | `auto_response.py` | 수신 메시지에 대해 AI 에이전트가 자동 응답 (수동 시작/정지) |
| **캘린더** | calendar_events.json | 이웃과의 약속은 calendar의 appointment로도 등록 가능 |
| **알림** | notification_manager | 새 메시지·중요 이벤트가 인앱 벨 알림으로 |
| **첨부 파일** | `business_images/` 디렉토리 + nostr.build (이미지 호스팅) | 외부에 공유하는 이미지는 nostr.build에 업로드 |

---

## 7. 주의 사항

1. **레벨은 정보 공개 통제 장치** — 무심코 `info_level`을 높이지 말 것. 이웃에게 어디까지 보여줄지 사용자의 의도 확인.
2. **info_share=0**인 이웃에게는 공유 안 함 — 비공개 표식.
3. **메시지 발신은 두 단계**: 외부 채널 발송 + DB 기록. 둘 중 하나만 하면 불일치 발생.
4. **`business_documents` 자동 생성** — 사용자가 비즈니스를 변경했을 때 `POST /business/documents/regenerate`로 새로고침. `work_guidelines`는 수동.
5. **Nostr npub 형식 강제** — contact_value가 hex로 들어오면 자동으로 npub로 변환됨. 직접 SQL로 hex를 넣지 말 것.
6. **첨부 이미지** — JSON 배열 형식이 표준. 단일 문자열은 레거시 호환용.

---

## 8. 디버깅·관리

```bash
# DB 직접 검사
sqlite3 data/business.db ".tables"
sqlite3 data/business.db ".schema neighbors"

# 채널 상태 확인
curl http://127.0.0.1:8765/business/channels

# 자동 응답 상태
curl http://127.0.0.1:8765/business/auto-response/status

# 즉시 폴링
curl -X POST http://127.0.0.1:8765/business/channels/gmail/poll
```

---

## 관련 가이드
- 이메일 발신 세부: `gmail` 패키지 가이드 (예정)
- IndieNet/Nostr 세부: `indienet` 가이드 (예정)
- 캘린더 약속 등록: [calendar.md](calendar.md)
- 자동 응답 시스템: `auto_response` (예정)
