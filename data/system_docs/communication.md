---
title: 통신·연동
scope: 채널 추상화, Gmail/Nostr, 자동응답 V3
owner_code: channel_engine.py, channel_poller.py, auto_response.py, indienet.py, gmail.py
last_updated: 2026-05-17
see_also: [architecture.md, delegation.md]
---

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
- **수신**: 실시간 WebSocket (릴레이 구독). DM 조회는 전체 릴레이 fan-out + dedup (`_query_relays` — 단일 릴레이만 읽던 버그 수정됨)
- **발송**: **NIP-17 gift-wrap DM 단일** (2026-06-05 전환 → 2026-06-13 NIP-04 완전 은퇴). 모든 발신(메신저 작성·자동응답·REST·폰)이 `send_dm_nip17`. 구 `send_dm`(NIP-04 kind:4)은 최신 앱이 복호 못 해 DM이 깨져 삭제. 수신은 NIP-17(kind:1059) 우선 + NIP-04(kind:4) 레거시 읽기(폰=NIP-17 전용, pynostr 부재)
- **모듈**: `backend/nip44.py` (NIP-44 암호화, 공식 테스트 벡터 150/150 통과) + `backend/nip17.py` (gift-wrap). DM inbox relay 선언(kind:10050) 자동 발행
- **기본 릴레이**: wss://relay.damus.io, wss://relay.nostr.band, wss://nos.lol, wss://relay.primal.net, wss://nostr.wine

### 폰 컴패니언 피드 (한방향 센서, 대화 채널과 분리)
폰의 네이티브 컴패니언 앱(`phone-companion/`, NotificationListenerService)이 알림을 전송:
- **수신/저장**: `backend/phone_notifications.py` → `data/phone_notifications.db` (대화용 channel_poller와 분리된 한방향 피드)
- **인가**: `data/phone_agent.json`의 pubkey만 수용, 그 외 발신자 무시
- **조회**: `[sense:phone]{op: notifications}` 또는 `/phone/notifications` API — "지금 폰에 연락 오나"의 정답 소스
- **위치**: `[sense:here]`(phone_only) — 상시 수집 폐기, 물을 때 1회 능동 조회(fused GPS+역지오코딩). 걸음수 수집은 폐기됨(2026-06-12).
- **카메라**: `[sense:see]`(phone_only) — 온디맨드 촬영(Camera2 정지캡처→폰 jpg, 3A 수렴). facing=back/front.
- **마이크**: `[sense:listen]{op: transcribe|record}`(phone_only) — 온디맨드 받아쓰기(STT→텍스트, 포워드 무손실)/녹음(→폰 m4a 파일).

### IndieNet 연동
Nostr 키는 IndieNet identity와 연동 가능:
- 위치: `~/.indiebiz/indienet/identity.json`
- Nostr 채널 설정에 nsec가 없으면 IndieNet에서 자동 로드
- 동일한 Nostr 신원으로 여러 서비스 연동 가능

### IndieNet 보드 (커스텀 해시태그 게시판)
커스텀 해시태그 기반의 독립 게시판 기능:
- 보드 생성/삭제/활성 보드 전환
- 해시태그별 게시글 분리 조회
- 기본 해시태그: `IndieNet`

### 메신저·커뮤니티 앱 (IBL 앱모드 계기, 2026-06-12)
이웃 메시징과 IndieNet 커뮤니티는 런처 버튼이 아니라 **IBL 액션 위의 앱모드 계기**로 제공된다
(데스크탑·원격·폰 전 표면 자동 등장). 메시지/글 **내용 동기화는 릴레이가 진실원**이라 폰·PC가
같은 키로 같은 릴레이를 구독하면 자동으로 일치(주소록 메타데이터 reconcile은 후속 과제).
- **메신저**(instrument `messenger`, 💬): `[others:messages]{op:"inbox"}`(대화 목록) →
  `{op:"thread", neighbor_id|pubkey}`(스레드, 채팅 버블) → 작성바가 `[others:channel_send]`로 답장.
  **DM 통합**: business.db(다채널 이웃·양방향) + dms.db(IndieNet Nostr DM)를 Nostr 이벤트 id로
  dedupe해 합침 — 비이웃 npub도 대화로 표시(pubkey 라우팅). 폰 컴패니언 텔레메트리(알림/위치/걸음)는 제외.
- **커뮤니티**(instrument `community`, 🌐): `[others:feed]{op:"read"/"post"}`(피드·게시) +
  `[others:board]{op:"list"/"create"/"switch"}`(게시판) + `[others:nostr]{op:"profile"/"rename"/"relays"/
  "import_key"/"reset_identity"}`(내 계정 탭 — 신원·릴레이). IndieNet(Nostr) 기반.
- **옛 IndieNet 전용 창 교체(2026-06-12, 버튼은 유지)**: 위 계기들이 피드·게시판·DM·신원·릴레이를
  전부 덮으므로 옛 bespoke IndieNet.tsx 창은 제거. 런처 '커뮤니티'(Globe) 버튼은 유지하되, 표면 무관하게
  전용 창(`#/community`, CommunityInstrumentView)으로 IBL 커뮤니티 계기를 그대로 띄운다 — 진입 통로는
  보존하고 내용만 단일 진실 소스(/launcher/instruments)로 교체. (비즈니스 창은 IBL 미커버라 유지.)
- 렌더 어휘 확장: `thread`(좌/우 버블) view 프리미티브 + `compose`(하단 작성바) — 데스크탑
  `GenericInstrument.tsx`와 원격 `api_launcher_web.py` HTML이 같은 선언을 해석.
- 발신 신원: 앱/수동 표면(`앱모드`/`수동모드` 프로젝트)의 IBL 실행은 `agent_id=system_ai`로
  기본 설정(소유자=시스템 운영자) → 작성바 전송·게시가 자기 계정으로 동작.

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

### 지원 프로바이더
자동응답은 시스템 AI의 API 설정을 공유하며, 다음 프로바이더를 지원합니다:
- **Anthropic** (Claude)
- **OpenAI** (GPT)
- **Google** (Gemini)

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

### 메시지 유형별 처리

| 메시지 유형 | AI 동작 |
|------------|--------|
| 비즈니스 문의 | `search_business_items` → `send_response` |
| 공식적 인사/감사 | `send_response` (검색 없이) |
| 개인적 대화/잡담 | `no_response_needed` |
| 스팸/광고 | `no_response_needed` |

### send_response 실행 흐름

1. 메시지 컨텍스트에서 발신자 정보 조회
2. Channel Poller의 `_send_response()` 호출하여 즉시 발송
3. DB에 발송 기록 저장 (`status='sent'`)
4. 원본 메시지 `replied=1`로 업데이트

### V2 → V3 변경사항

| 항목 | V2 (이전) | V3 (현재) |
|------|----------|----------|
| AI 호출 횟수 | 2회 (판단 + 응답) | 1회 (Tool Use) |
| 판단 로직 | 별도 ai_judgment.py | auto_response.py에 통합 |
| 응답 발송 | pending → polling → 발송 | send_response 도구로 즉시 발송 |
| 관련 파일 | ai_judgment.py, response_generator.py | auto_response.py 통합 |

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
| replied | INTEGER | 응답 완료 여부 (0=미응답, 1=응답 완료) |
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

### Gmail OAuth 설정 (전역 + 이메일별 토큰)

Gmail은 **전역 OAuth 설정**과 **이메일별 토큰**으로 구성됩니다.

#### 1. 전역 OAuth 설정
`data/packages/installed/extensions/gmail/config.yaml`:
```yaml
gmail:
  client_id: "xxx.apps.googleusercontent.com"
  client_secret: "xxx"
  email: "system-ai@gmail.com"  # 시스템 AI 이메일
```

- `client_id`, `client_secret`: Google Cloud Console에서 발급받은 OAuth 인증 정보
- `email`: 시스템 AI가 사용할 이메일 주소
- 이 설정은 **모든 이메일 계정에서 공유**됩니다

#### 2. 이메일별 토큰 파일
`data/packages/installed/extensions/gmail/tokens/`:
```
tokens/
├── system-ai@gmail.com.json      # 시스템 AI용
├── marketer@gmail.com.json       # 마케터 에이전트용
└── support@gmail.com.json        # 고객지원 에이전트용
```

- 각 이메일 주소별로 별도의 OAuth 토큰 파일이 생성됩니다
- 처음 해당 이메일로 발송 시 브라우저에서 Google 계정 인증 필요

#### 3. 에이전트 Gmail 설정
프로젝트의 `agents.yaml`에서 에이전트별 이메일 지정:
```yaml
agents:
  - name: 마케터
    type: external
    channel: gmail
    email: marketer@gmail.com  # 에이전트 전용 이메일
    allowed_tools:
      - channel_send  # 채널 발송 도구
```

**중요**: 에이전트별 `client_id`/`client_secret`은 설정하지 않습니다.
모든 이메일 계정이 전역 OAuth 설정을 공유합니다.

#### 4. 설정 순서
1. **설정 → 채널 → Gmail**에서 OAuth 정보(client_id, client_secret) 입력
2. 시스템 AI 이메일 주소 입력 및 저장
3. 앱 재시작 시 브라우저에서 해당 계정 OAuth 인증
4. 에이전트 설정에서 이메일 주소만 입력 (OAuth 정보 불필요)
5. 에이전트 첫 이메일 발송 시 해당 계정 OAuth 인증

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

### IndieNet (커뮤니티/메신저)
**전용 REST(`/indienet/*`)는 제거됨** (api_indienet.py 삭제). 커뮤니티·DM·신원은 모두 IBL 계기로 접근:
- 피드: `[others:feed]{op: list/read/post}`
- 보드: `[others:board]{op: list/create/switch}`
- DM/메신저: `[others:messages]{op: inbox/thread}` + `[others:channel_send]`
- 신원·릴레이: `[others:nostr]{op: profile/rename/relays/import_key/reset_identity}`
- 코어 모듈 `indienet.py`(채널 엔진·폴러가 사용)는 유지. Nostr DM은 NIP-17(gift-wrap) — channel_poller가 전 릴레이 멀티 구독으로 실시간 수신.

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
3. **무한 루프 방지**: 연속 자동응답 5개 이상(>=5) 시 스킵
4. **Nostr 키 관리**: nsec는 채널 설정 또는 IndieNet에서 관리

---
*마지막 업데이트: 2026-06-14 — channel 트리거("Y 메시지 오면 X 실행") 맥 발화 경로 신설: channel_poller `_save_message_to_db`(Gmail/Nostr 3수신 경로 공통 깔때기)에 `_check_channel_triggers` 훅 → 매칭 시 데몬 스레드로 파이프라인 발화(메시지를 _prev_result 주입). **폰은 메시지 폴링 안 함**(사용자 결정 2026-06-14) — 메시지 수신/폴링은 PC 담당, 폰=리모컨/두 번째 자아. 이전(2026-06-12): IndieNet 전용 REST(api_indienet) 제거 → 커뮤니티/메신저 IBL 계기화(others:feed/board/messages/nostr) + NIP-17 멀티릴레이 실시간 수신 + 자동응답 PC 전용 영속화 + 연락처 email→gmail. 이전(2026-06-10): Nostr DM NIP-17 전환(nip44/nip17 모듈) + 폰 컴패니언 피드. 이전: 2026-04-05*
