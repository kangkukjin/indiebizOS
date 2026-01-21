# 비즈니스 자동응답 시스템 V3

## 개요

비즈니스 자동응답 시스템은 외부 정보채널(Gmail, Nostr 등)로 들어온 메시지를 자동으로 분석하고, 비즈니스 관련 문의에 대해 AI가 응답을 생성하는 시스템입니다.

**V3 변경사항 (2026-01-21):**
- 기존 2단계 AI 호출 → 1단계 Tool Use 방식으로 통합
- AI가 도구를 직접 호출하여 판단, 검색, 발송을 한 번에 처리
- 응답 즉시 발송 (polling 대기 없음)

---

## 시스템 구성요소

### 1. Channel Poller (`backend/channel_poller.py`)
- 정보채널에서 새 메시지를 주기적으로 폴링
- 받은 메시지를 `messages` 테이블에 저장
- 사용자 명령 감지 시 시스템 AI 호출
- 응답 메시지 전송 (`_send_response`)

### 2. Auto Response Service (`backend/auto_response.py`)
- 새 메시지에 대한 자동응답 처리
- Tool Use 기반 단일 AI 호출
- 3가지 도구: `search_business_items`, `no_response_needed`, `send_response`

### 3. 프롬프트 (`data/common_prompts/base_prompt_autoresponse.md`)
- 자동응답 AI의 역할 및 판단 기준 정의
- 도구 사용 지침

---

## 자동응답 플로우 (V3)

```
[외부 메시지 수신]
       ↓
[Channel Poller가 메시지 폴링]
       ↓
[messages 테이블에 저장 (is_from_user=0)]
       ↓
[AutoResponseService._process_message() 호출]
       ↓
[컨텍스트 수집]
  - 이웃 정보
  - 근무지침
  - 비즈니스 문서
  - 대화 기록
       ↓
[AI 호출 (Tool Use 포함)]
       ↓
[AI가 도구 선택 및 실행]
  ├─ search_business_items → 비즈니스 DB 검색
  ├─ no_response_needed → 응답 불필요 처리
  └─ send_response → 응답 즉시 발송
       ↓
[완료]
```

---

## 도구 정의

### 1. search_business_items
비즈니스 데이터베이스에서 상품/서비스 검색

```json
{
  "category": "팔아요",
  "keywords": ["자전거", "중고"]
}
```

### 2. no_response_needed
자동응답이 부적절한 경우 호출 (스팸, 광고, 개인적 대화)

```json
{
  "reason": "스팸 메시지"
}
```

### 3. send_response
응답 메시지를 발신자에게 즉시 전송

```json
{
  "subject": "RE: 문의사항",
  "body": "안녕하세요. 문의하신 내용에 답변드립니다..."
}
```

---

## 메시지 유형별 처리

| 메시지 유형 | AI 동작 |
|------------|--------|
| 비즈니스 문의 | `search_business_items` → `send_response` |
| 공식적 인사/감사 | `send_response` (검색 없이) |
| 개인적 대화/잡담 | `no_response_needed` |
| 스팸/광고 | `no_response_needed` |

---

## 응답 발송 처리

### send_response 도구 실행 흐름
1. 메시지 컨텍스트에서 발신자 정보 조회
2. Channel Poller의 `_send_response()` 호출하여 즉시 발송
3. DB에 발송 기록 저장 (`status='sent'`)
4. 원본 메시지 `replied=1`로 업데이트

### 제목 포맷
- 응답 제목: `Re: {원본 제목}`
- DB 저장 제목: `(IN)agent: {AI가 지정한 제목}`

---

## 채널별 구현

### Gmail
- OAuth2 인증
- `poll_messages()`: 읽지 않은 메시지 조회
- `send_email()`: 이메일 전송

### Nostr
- 개인키 기반 인증
- 실시간 WebSocket 연결
- DM(Direct Message) 송수신

---

## 설정 파일

### `data/system_ai_config.json`
```json
{
  "enabled": true,
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514",
  "apiKey": "sk-..."
}
```

---

## V2 → V3 변경사항

| 항목 | V2 (이전) | V3 (현재) |
|------|----------|----------|
| AI 호출 횟수 | 2회 (판단 + 응답) | 1회 (Tool Use) |
| 판단 로직 | 별도 AI 호출 | AI가 도구로 직접 처리 |
| 응답 발송 | pending → polling → 발송 | send_response 도구로 즉시 발송 |
| 관련 파일 | ai_judgment.py, response_generator.py | auto_response.py 통합 |

---

## 관련 파일

- `backend/auto_response.py` - 자동응답 서비스 (Tool Use 통합)
- `backend/channel_poller.py` - 메시지 폴링 및 전송
- `backend/business_manager.py` - 비즈니스 데이터 관리
- `data/common_prompts/base_prompt_autoresponse.md` - 자동응답 프롬프트
- `data/system_ai_config.json` - AI 설정

---

*마지막 업데이트: 2026-01-21*
