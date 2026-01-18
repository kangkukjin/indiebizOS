# 비즈니스 자동응답 시스템

## 개요

비즈니스 자동응답 시스템은 외부 정보채널(Gmail, Nostr 등)로 들어온 메시지를 자동으로 분석하고, 비즈니스 관련 문의에 대해 AI가 응답을 생성하는 시스템입니다.

## 시스템 구성요소

### 1. Channel Poller (`backend/channel_poller.py`)
- 정보채널에서 새 메시지를 주기적으로 폴링
- 받은 메시지를 `messages` 테이블에 저장
- `pending` 상태의 응답 메시지를 실제로 전송

### 2. Auto Response Service (`backend/auto_response.py`)
- 새 메시지에 대한 자동응답 처리
- AI 판단 → 비즈니스 검색 → 응답 생성 플로우 관리

### 3. AI Judgment Service (`backend/ai_judgment.py`)
- 메시지 의도 분석 및 응답 필요 여부 판단
- 검색할 비즈니스 카테고리 결정

### 4. Response Generator (`backend/response_generator.py`)
- 최종 응답 텍스트 생성

---

## 자동응답 플로우

```
[외부 메시지 수신]
       ↓
[Channel Poller가 메시지 폴링]
       ↓
[messages 테이블에 저장 (is_from_user=0)]
       ↓
[AutoResponseService.process_new_message() 호출]
       ↓
[컨텍스트 수집]
  - 이웃 정보
  - 근무지침
  - 비즈니스 문서
  - 대화 기록
  - 비즈니스 목록 ← 실제 DB에서 조회
       ↓
[AI 판단 (1차 AI 호출)]
  - action: NO_RESPONSE | BUSINESS_RESPONSE
  - no_matching_business: 요청한 서비스가 목록에 없는지
  - requested_service: 요청한 서비스명
  - searches: 검색할 비즈니스 목록
       ↓
[action == NO_RESPONSE?] → 종료 (사용자가 직접 응답)
       ↓
[비즈니스 DB 검색]
  - searches에 지정된 비즈니스 이름으로 검색
  - 관련 비즈니스 정보 수집
       ↓
[응답 생성 (2차 AI 호출)]
  - 컨텍스트 + 검색 결과 + 판단 정보 전달
  - no_matching_business=true면 해당 서비스 없음 안내
       ↓
[messages 테이블에 응답 저장 (status='pending')]
       ↓
[Pending Message Sender가 10초마다 폴링]
       ↓
[실제 메시지 전송]
       ↓
[status='sent'로 업데이트]
```

---

## AI 판단 (AIJudgmentService)

### 입력 컨텍스트
```python
{
    'message': {
        'subject': '제목',
        'content': '내용'
    },
    'neighbor': {
        'name': '발신자 이름',
        'pubkey': '...'
    },
    'work_guideline': '근무지침 텍스트',
    'business_doc': '비즈니스 소개 문서',
    'conversation_history': [...],
    'business_list': [
        {'id': 1, 'name': '중고 자전거 판매', 'description': '...'},
        {'id': 2, 'name': '번역 서비스', 'description': '...'}
    ]
}
```

### 출력 판단
```json
{
    "action": "BUSINESS_RESPONSE",
    "confidence": 0.9,
    "reasoning": "자전거 구매 문의",
    "no_matching_business": false,
    "requested_service": "",
    "searches": [
        {
            "category": "중고 자전거 판매",
            "keywords": ["자전거", "구매"],
            "confidence": 0.9
        }
    ]
}
```

### 판단 기준

| 메시지 유형 | action | searches |
|------------|--------|----------|
| 비즈니스 문의/거래 | BUSINESS_RESPONSE | 관련 비즈니스 |
| 공식적 인사/감사 | BUSINESS_RESPONSE | [] |
| 개인적 대화/잡담 | NO_RESPONSE | [] |
| 스팸/광고 | NO_RESPONSE | [] |

### 비즈니스 매칭 실패 처리

`no_matching_business: true`인 경우:
- 상대방이 요청한 서비스가 비즈니스 목록에 없음
- `requested_service`에 요청한 서비스명 기록
- 응답 생성 시 "해당 서비스를 제공하지 않습니다" 안내

---

## 응답 생성

### 프롬프트 구성요소

1. **시스템 설정**
   - 응답 톤/스타일
   - 언어 설정

2. **비즈니스 컨텍스트**
   - 근무지침
   - 비즈니스 문서
   - 검색된 비즈니스 상세정보

3. **대화 컨텍스트**
   - 최근 대화 기록
   - 현재 메시지

4. **특별 지시** (조건부)
   - 비즈니스 매칭 실패 시: 해당 서비스 없음 안내 지시

### 응답 저장

```python
# messages 테이블에 저장
{
    'contact_value': '수신자 주소',
    'channel_type': 'gmail',
    'subject': 'Re: 원본 제목',
    'content': '생성된 응답',
    'is_from_user': 1,
    'status': 'pending'  # 아직 전송 안됨
}
```

---

## Pending Message Sender

### 동작 방식

1. 10초마다 `pending` 상태 메시지 조회
2. 채널 타입별 전송 처리
3. 성공 시 `status='sent'` 업데이트
4. 실패 시 `status='failed'` 업데이트

### 전송 실패 처리

- 최대 재시도 횟수 제한 (향후 구현)
- 실패 로그 기록
- 사용자에게 알림 (향후 구현)

---

## 채널별 구현

### Gmail (`channels/gmail.py`)
- OAuth2 인증
- `poll_messages()`: 읽지 않은 메시지 조회
- `send_message()`: 이메일 전송
- `mark_as_read()`: 읽음 표시

### Nostr (`channels/nostr.py`)
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

### `data/work_guideline.txt`
- 자동응답 시 참조할 근무지침
- 응답 스타일, 업무 시간, 특별 안내사항 등

### `data/business_doc.txt`
- 비즈니스 전체 소개 문서
- AI가 컨텍스트로 참조

---

## 주의사항

1. **런처 채널 vs 프로젝트 에이전트 채널**
   - 런처의 정보채널은 `business.db` 사용
   - 프로젝트 외부 에이전트는 별도 메모리 기반 (독립적)

2. **AI 호출 비용**
   - 판단 1회 + 응답 생성 1회 = 총 2회 API 호출
   - `NO_RESPONSE` 판단 시 응답 생성 호출 없음

3. **에러 처리**
   - AI 호출 실패 시 폴백 로직 (키워드 기반 판단)
   - 메시지 전송 실패 시 `status='failed'`로 표시

---

## 관련 파일

- `backend/channel_poller.py` - 메시지 폴링 및 전송
- `backend/auto_response.py` - 자동응답 서비스
- `backend/ai_judgment.py` - AI 판단 서비스
- `backend/response_generator.py` - 응답 생성
- `backend/channels/base.py` - 채널 기본 인터페이스
- `backend/channels/gmail.py` - Gmail 채널
- `backend/channels/nostr.py` - Nostr 채널
- `data/system_ai_config.json` - AI 설정
- `data/work_guideline.txt` - 근무지침
- `data/business_doc.txt` - 비즈니스 문서
