# 통신 채널 시스템 (Communication Channels)

외부 정보채널을 통한 메시지 수신/발송 및 자동응답 시스템.

## 개요

IndieBiz OS는 GUI 외에도 Gmail, Nostr 등 외부 채널을 통해 사용자 및 이웃(파트너)과 소통합니다.

```
┌─────────────────────────────────────────────────────────────┐
│                      외부 통신 채널                          │
├─────────────────┬─────────────────┬─────────────────────────┤
│     Gmail       │     Nostr       │    (향후 확장 가능)      │
│   (폴링 방식)    │  (실시간 WS)     │                         │
└────────┬────────┴────────┬────────┴─────────────────────────┘
         │                 │
         ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│                   Channel Poller                             │
│        (채널별 메시지 수신 → DB 저장 → 라우팅)                │
└────────────────────────────┬────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌──────────┐   ┌──────────┐   ┌──────────┐
       │ 사용자   │   │ 외부인   │   │ pending  │
       │ 명령     │   │ 메시지   │   │ 메시지   │
       │ → 시스템AI│   │ → 자동응답│   │ → 발송   │
       └──────────┘   └──────────┘   └──────────┘
```

---

## 통신 채널

### Gmail (폴링 방식)
- **인증**: OAuth2 (client_id, client_secret)
- **수신**: 주기적 폴링 (기본 60초)
- **발송**: SMTP
- **설정 파일**: `data/packages/installed/extensions/gmail/config.yaml`

### Nostr (실시간 WebSocket)
- **인증**: nsec 개인키 (NIP-01)
- **수신**: 실시간 WebSocket (릴레이 구독)
- **발송**: NIP-04 암호화 DM
- **기본 릴레이**: wss://relay.damus.io, wss://nos.lol, wss://relay.primal.net

### IndieNet 연동
Nostr 키는 IndieNet identity와 연동 가능:
- 위치: `~/.indiebiz/indienet/identity.json`
- Nostr 채널 설정에 nsec가 없으면 IndieNet에서 자동 로드
- 동일한 Nostr 신원으로 여러 서비스 연동 가능

---

## 핵심 컴포넌트

| 파일 | 역할 |
|------|------|
| `channel_poller.py` | 채널 수신/발송 통합 관리 |
| `channels/base.py` | 채널 추상 인터페이스 |
| `channels/gmail.py` | Gmail 구현 |
| `channels/nostr.py` | Nostr 구현 |
| `business_manager.py` | 비즈니스/이웃/메시지 DB 관리 |
| `auto_response.py` | 자동응답 서비스 V3 (Tool Use 통합) |

---

## 메시지 흐름

### 1. 메시지 수신

```
외부 채널 → ChannelPoller → _save_message_to_db()
                               │
                ┌──────────────┼──────────────┐
                ▼                             ▼
         사용자(소유자)?                   외부인?
                │                             │
                ▼                             ▼
        _process_owner_command()        messages 테이블 저장
                │                             │
                ▼                             ▼
           시스템 AI 처리              자동응답 서비스 처리
                │                             │
                ▼                             ▼
           응답 → 채널로 전송           판단 → 검색 → 응답 생성
```

### 2. 사용자 식별

환경변수로 소유자 연락처 설정:
```env
OWNER_EMAILS=user@gmail.com,another@gmail.com
OWNER_NOSTR_PUBKEYS=npub1xxx...,npub1yyy...
```

사용자로부터 온 메시지:
- business.db에 저장하지 않음
- 시스템 AI가 직접 처리
- GUI와 동일한 방식으로 대화

### 3. 외부인 메시지

이웃(파트너)으로부터 온 메시지:
1. 연락처로 이웃 찾기 (없으면 자동 생성)
2. messages 테이블에 저장
3. 자동응답 서비스가 처리

---

## 자동응답 시스템 V3 (Tool Use 통합)

→ 상세 문서: [auto_response.md](auto_response.md)

### 처리 흐름

V3에서는 판단과 응답을 한 번의 AI 호출로 처리합니다 (Tool Use 방식):

```
새 메시지 도착 (is_from_user=0)
         │
         ▼
[AutoResponseService._process_message()]
         │
         ▼
[컨텍스트 수집: 이웃 정보, 근무지침, 비즈니스 문서, 대화 기록]
         │
         ▼
[AI 호출 (Tool Use 포함) - 1회]
         │
         ▼
[AI가 도구 선택 및 실행]
  ├─ search_business_items → 비즈니스 DB 검색
  ├─ no_response_needed → 응답 불필요 (스팸/광고/개인대화)
  └─ send_response → 응답 즉시 발송
         │
         ▼
[완료]
```

### 도구

| 도구 | 용도 |
|------|------|
| `search_business_items` | 비즈니스 DB에서 상품/서비스 검색 |
| `no_response_needed` | 응답 불필요 시 (스팸, 광고, 개인적 대화) |
| `send_response` | 응답 메시지를 발신자에게 즉시 전송 |

### V2 → V3 변경사항

| 항목 | V2 (이전) | V3 (현재) |
|------|----------|----------|
| AI 호출 횟수 | 2회 (판단 + 응답) | 1회 (Tool Use) |
| 판단 로직 | 별도 ai_judgment.py | auto_response.py에 통합 |
| 응답 발송 | pending → polling → 발송 | send_response 도구로 즉시 발송 |

---

## 메시지 발송

### 자동응답 발송 (V3)

V3에서는 `send_response` 도구가 즉시 발송합니다 (pending 대기 없음):
- Channel Poller의 `_send_response()` 호출
- DB에 발송 기록 저장 (`status='sent'`)

### 수동 메시지 발송

비즈니스 매니저 UI에서 직접 메시지 작성 가능:
1. messages 테이블에 pending 상태로 저장
2. Pending Sender가 자동 발송

---

## 데이터베이스 (business.db)

### messages 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER | PK |
| neighbor_id | INTEGER | FK → neighbors |
| contact_type | TEXT | gmail, nostr |
| contact_value | TEXT | 이메일 주소, npub |
| subject | TEXT | 제목 |
| content | TEXT | 본문 |
| is_from_user | INTEGER | 0=수신, 1=발신 |
| status | TEXT | null, pending, sent, failed, skipped |
| external_id | TEXT | 외부 메시지 ID (중복 방지) |
| message_time | TEXT | 메시지 시간 |
| created_at | TEXT | 저장 시간 |

### neighbors 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER | PK |
| name | TEXT | 이웃 이름 |
| info_level | INTEGER | 정보 수준 (0-5) |
| notes | TEXT | 메모 |

### contacts 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER | PK |
| neighbor_id | INTEGER | FK → neighbors |
| contact_type | TEXT | gmail, nostr |
| contact_value | TEXT | 연락처 값 |

### channel_settings 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| channel_type | TEXT | PK (gmail, nostr) |
| enabled | INTEGER | 활성화 여부 |
| polling_interval | INTEGER | 폴링 주기 (초) |
| config | TEXT | JSON 설정 |
| last_poll_at | TEXT | 마지막 수신 시간 |

---

## 설정 파일

### Gmail OAuth 설정
`data/packages/installed/extensions/gmail/config.yaml`:
```yaml
gmail:
  client_id: "xxx.apps.googleusercontent.com"
  client_secret: "xxx"
  scopes:
    - "https://www.googleapis.com/auth/gmail.readonly"
    - "https://www.googleapis.com/auth/gmail.send"
    - "https://www.googleapis.com/auth/gmail.modify"
```

### 시스템 AI 설정
`data/system_ai_config.json`:
```json
{
  "enabled": true,
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514",
  "apiKey": "sk-..."
}
```

### 근무지침 / 비즈니스 문서
- `data/work_guideline.txt`: 자동응답 시 참조할 근무지침
- `data/business_doc.txt`: 비즈니스 전체 소개 문서

---

## API 엔드포인트

### 채널 설정
- `GET /business/channels` - 채널 목록
- `GET /business/channels/{type}` - 특정 채널 설정
- `PUT /business/channels/{type}` - 채널 설정 수정
- `POST /business/channels/{type}/poll` - 즉시 폴링

### 자동응답
- `GET /business/auto-response/status` - 상태 조회
- `POST /business/auto-response/start` - 시작
- `POST /business/auto-response/stop` - 중지

### 메시지
- `GET /business/messages` - 메시지 목록
- `POST /business/messages` - 메시지 생성 (발송용)
- `POST /business/messages/{id}/processed` - 처리 완료
- `POST /business/messages/{id}/replied` - 응답 완료

---

## 프롬프트 구조

### 자동응답 프롬프트 (V3 - Tool Use 통합)
`data/common_prompts/base_prompt_autoresponse.md` 기반:
- 역할, 판단 기준, 도구 사용 지침을 하나의 프롬프트로 통합
- AI가 컨텍스트(이웃 정보, 근무지침, 비즈니스 문서, 대화 기록)를 참조하여 도구를 직접 선택

---

## 주의사항

1. **사용자 식별**: `.env`에 `OWNER_EMAILS`, `OWNER_NOSTR_PUBKEYS` 설정 필수
2. **API 호출 비용**: Tool Use 기반 1회 호출 (V3)
3. **무한 루프 방지**: 연속 자동응답 5개 초과 시 스킵
4. **Nostr 키 관리**: nsec는 채널 설정 또는 IndieNet에서 관리

---
*마지막 업데이트: 2026-02-01*
