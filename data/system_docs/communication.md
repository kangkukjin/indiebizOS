---
title: 통신·연동
scope: 채널 추상화, Gmail/Nostr, 자동응답 V3, 에이전트 위임 체인(구 delegation.md)
owner_code: channel_engine.py, channel_poller.py, auto_response.py, indienet.py, gmail.py, agent_communication.py, agent_runner.py, calendar_manager.py
last_updated: 2026-08-01
see_also: [architecture.md, scheduler_guide.md]
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
- **기본 켜짐(2026-07-28)**: nostr 채널 스위치의 기본값이 꺼짐이라 설정할 게 없는데도 DM **수신만** 조용히 멈춰 있었다 → 기본 켜짐으로. 스위치가 여닫는 것이 *수신*임을 UI 문구에도 명시(발신은 스위치와 무관).

### 폰 컴패니언 피드 (한방향 센서, 대화 채널과 분리)
폰의 네이티브 컴패니언 앱(`phone-companion/`, NotificationListenerService)이 알림을 전송:
- **수신/저장**: `backend/phone_notifications.py` → `data/phone_notifications.db` (대화용 channel_poller와 분리된 한방향 피드)
- **인가**: `data/phone_agent.json`의 pubkey만 수용, 그 외 발신자 무시
- **조회**: `[sense:phone]{op: notifications}` 또는 `/phone/notifications` API — "지금 폰에 연락 오나"의 정답 소스
- **위치**: `[sense:here]`(지표어 — 모든 몸) — 상시 수집 폐기, 물을 때 1회 능동 조회. 폰=fused GPS ±수십 m / 데스크탑 사다리(2026-08-06)=선언 위치(`data/body_location.json`, 고정 몸 정답) > OS 위치서비스(WiFi AP 지문 수십~수백 m, 랩탑 정답 — macOS CoreLocation·Windows GeoCoordinateWatcher·Linux GeoClue, 권한거부=조용히 폴백) > IP 지오(도시 수준, ISP 등록지라 틀릴 수 있음) + 움직임-증거 캐시(네트워크 지문). source=gps|declared|wifi|ip. 걸음수 수집은 폐기됨(2026-06-12).
- **카메라**: `[sense:see]`(phone_only) — 온디맨드 촬영(Camera2 정지캡처→폰 jpg, 3A 수렴). facing=back/front.
- **마이크**: `[sense:listen]{op: transcribe|record}`(phone_only) — 온디맨드 받아쓰기(STT→텍스트, 포워드 무손실)/녹음(→폰 m4a 파일).

### 맥↔폰 양방향 연합 (분산 IBL, 2026-06-17 라이브)
폰↔맥이 서로의 전용 액션을 빌려 쓴다(상세=ibl.md 분산 IBL 절). 통신 관점 요약:
- **상주**: 폰 백엔드(`:8765`)가 `AgentForegroundService`(START_STICKY·부팅)로 **앱 UI 없이** 떠 있어, 맥이 언제든 닿는다(앱 안 열어도 됨).
- **맥→폰**: `INDIEBIZ_PHONE_URL`(폰 LAN)로 HTTP 포워드, `INDIEBIZ_PHONE_TOKEN`을 `X-Phone-Token` 헤더로 동봉. 폰은 비localhost 요청에 이 토큰을 검증하고, **토큰이 설정됐을 때만 0.0.0.0(LAN) 바인드**(없으면 localhost 전용 — 노출과 인증이 한 묶음).
- **폰→맥**: `INDIEBIZ_MAC_URL`(Cloudflare 터널, HTTPS)+`INDIEBIZ_MAC_PASSWORD`(런처 세션)로 위임.
- **토큰 프로비저닝**: 정본 `.env` → `phone-companion/scripts/provision_phone_keys.py`가 `keys.json`으로 폰에 푸시(맥·폰 동일 값). 인증은 전자동(매 호출 사람 개입 없음).
- **보안**: 양방향 게이트·인터넷 비노출(폰=LAN 한정). 유일 caveat=맥→폰이 LAN 평문 HTTP라 토큰이 WiFi 평문(가정 WPA2 저위험, 공용 WiFi 금지). 토큰=폰 완전 제어권 → 유출 시 교체.

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

### 공개 표면 — 커뮤니티당 노드 하나 (2026-07 라이브)
위 채널(Gmail·Nostr·메신저)은 *메시지 왕복*이다. 이와 별개로, 내 시스템을 **공개 웹 주소로 노출**해
남이 브라우저로 닿게 하는 표면 가족이 `others` 노드에 자랐다. 전략=**"커뮤니티당 노드 하나"**: 모두가
노드를 돌리는 게 아니라, 커뮤니티당 노드 하나(내 시스템)를 두고 구성원은 *설치 없이 브라우저로* 참여한다.
공개 서빙은 전부 **브라우저 → Cloudflare Worker → 터널 → 맥** 3층(공유 `X-Showcase-Secret`,
`is_public_remote_path` 화이트리스트, `public-files` Worker가 경로 접두로 분기).
- **개인 포털** `[others:portal]` — `/h/<5자>/`. 여러 개 생성 가능하고, **각 주소가 자기 회원 명부 +
  진열 다이얼(첫화면 구성)을 독립 소유**. 로그인=아이디/비번(네이버식) 또는 운영자 발급 열쇠(`/h/<슬러그>/k/<키>`,
  비밀번호 분실 복구·유출 시 revoke). **회원 = 이웃 CRM(business.db) 통합, 레벨 0 손님 → 4 가족**(별도 계정
  시스템 없음). 레벨(min_level)에 따라 콘텐츠(가족신문·공개파일)와 계기(아이콘·유튜브뮤직·날씨)를 빌려 씀.
  유튜브뮤직 등 외부망 재생은 **포털별 오디오 프록시**(`/h/<슬러그>/tune/<vid>`)로 집 IP 중계. 회원 실행
  게이트=계기 `app:` 블록 템플릿의 *인스턴스*만 허용(범용 execute 금지)+일일 한도(손님/회원/전역).
- **공개 파일** `[others:showcase]` — `/s/<5자>/`. 주소별 폴더를 맥 디스크에서 즉석 walk+썸네일로 서빙
  (인덱싱 없음, EXIF 제거·영상 트랜스코드).
- **가족신문** `[others:family_news]` — `/n/<5자>/`. USB 폰 사진(DCIM)을 지난 발행 이후 구간으로 모아
  조판→누적 발행, 방명록·가족 사진 업로드(쓰기 방향 개통).
- **자유게시판** `[others:bulletin]` — `/b/<5자>/`. 로그인 없이 주소만 알면 글·사진 게시(family-news 방명록
  배관 재사용: 이름·본문 캡, IP 간격 429, 허니팟, EXIF/GPS 제거).
- **정기보고 발행 면** — `/r/<슬러그>/`. 로컬 `.md` 보고서를 "볼 때 렌더"로 서빙(새 어휘 없음).
- **포털 붙임 = 색인**: 위 콘텐츠(가족신문·공개파일·게시판·보고서)를 포털에 노출하는 건
  `[others:portal]{op:"display", key:"board:<slug>"...}` 다이얼로 켜고 끔(min_level로 손님~가족 범위 조정).

### 공유창고 — 노드 자신의 주소 (2026-07-18~21 라이브)

위 표면들이 *만드는 목적지*라면, 창고는 **노드 자신이 주소를 갖는 것**이다. 발행 행위는 하나뿐 — **폴더에 파일을 놓는다.**

- **서빙**: `공유창고/0..4/` 가 노드의 맨 주소에서 그대로 서빙된다(색인 없음·변환 없음, 파일시스템이 진실).
  바이트를 그대로 내주므로(schema-on-read) PDF 는 PDF 로, 표는 표로 가고 **해석은 읽는 쪽 AI 몫**이다.
- **레벨이 문**: 방문자 등급 0~4 는 이웃 CRM 등급과 **같은 자**(한 번 승급하면 메신저·포털·창고에 함께 적용).
  보는 사람은 `0..자기 레벨`을 **한 장의 평평한 목록**으로 보고(같은 이름은 높은 레벨이 이김), 그 위 파일은
  403 이 아니라 **404**(존재 자체가 정보라서). 의도적 누출은 `has_restricted` 한 비트뿐 — "여기 더 있다"는 냄새.
- **기계 얼굴**: `GET /manifest` 가 같은 목록을 JSON 으로(제목·파일 크기·mtime·직접 URL·`about`·`login` 블록).
  계약은 `GET /manifest` + `GET /f?path=` + 쿠키 로그인 **셋뿐** — IBL 도, 인지 파이프라인도, indiebizOS 자체도 계약이 아니다.
- **읽는 쪽(이웃 피드)**: `warehouse_feed.py` 폴러가 등록된 이웃 창고 매니페스트를 30분마다 가져와 경로·mtime
  diff → `seed`(팔로우 직후 지난 것) / `new` / `changed` 타임라인. **모델 호출 0·토큰 0의 순수 기계층**이고,
  보존 스냅샷은 곧 **동네 전체 파일명 색인**(검색 한 번이 이웃 창고 전부를 쓸어본다).
- **방언 어댑터**: 이웃이 indiebizOS 가 아니어도 된다 — nginx/Apache 디렉터리 색인, RSS/Atom(HTML `<link rel=alternate>`
  자동발견), Nextcloud 공개 공유, 일반 웹페이지의 파일 링크를 전부 같은 매니페스트 통화로 정규화(`warehouse_adapters.py`).
  **콜드 스타트 우회** — 블로그 RSS 하나로 첫 이웃이 생긴다.
- **창고 주소 = 연락 방법**: 이웃의 `contacts` 에 `contact_type='warehouse'` 행으로 저장(이메일·Nostr 키 옆).
  주소만 아는 상대도 정상 이웃(매니페스트 제목으로 자동 명명). 리트윗은 내 창고에 놓는 `.url` 포인터 파일 —
  구독자의 클릭이 **원본 창고로 직행**한다(FOAF 발견이 프로토콜이 아니라 파일).
- **자격과 평가는 다른 축**: 상대가 준 접근 **레벨**(가입/로그인 자격을 폴러가 그대로 사용, 쿠키 만료·회수 시
  자가치유 재로그인, 실패해도 익명 폴백이라 피드는 안 멈춤)과 내가 매기는 **창고 점수 0~3**(피드·검색 필터)은 독립.
- **AI 가 채운다**: 스케줄 파이프라인이 아침 신문·AI 동향 보고서·최신 블로그 글을 창고에 떨어뜨리고, 비즈니스
  아이템(나눔·판매·가능)은 DB 에서 창고 선반으로 자동 진열된다 — **생산이 곧 발행**. 진열에는 사람이 여는
  표지 한 장(`<비즈니스> 카탈로그.html`)이 함께 나가는데, 사진을 data URI 로 실은 **자족 문서**라 받아가서
  열어도 그대로 산다(2026-07-29, `warehouse_catalog.py`. 내용이 같으면 지문 게이트가 재생성을 막는다 —
  괜히 다시 쓰면 mtime 이 흔들려 이웃 폴러가 `changed` 로 오독한다).
- **둘러보기와 추천(2026-07-29)**: 어댑터가 생긴 뒤로 세상엔 이미 창고가 많은데 볼 방법이 없었다 → 이웃찾기가
  두 갈래다. *소개글*(나를 알린 사람이 오는 수신면)과 *둘러보기*(`warehouse_directory.py` — 장르별 후보를
  훑는 면, live 파싱 + 사용자가 고칠 수 있는 시드). 방언에 **neocities** 어댑터가 합류해 개인 홈페이지
  169만 개가 창고 후보가 됐다(커스텀 도메인은 `api/info` 대조로만 채택 — 남의 사이트를 잘못 물지 않게).
  이웃 카드의 📣 **공개 추천**은 기계가 사실만 채운 초안을 사람이 고쳐 발행하고(공개 발행이라 2단 확인),
  본문이 `공유창고 Warehouse : <url>` 계약을 지켜 받는 쪽 이웃찾기에 '＋ 등록' 버튼이 그 자리에 붙는다.
  ★미러의 루트는 대개 안내 페이지라 창고가 못 된다 — 시드는 실제 색인 폴더를 가리킨다.

### 몸 사이 소통 — 명함과 부탁 (2026-07-22)

여러 몸(맥·폰·낯선 PC)이 서로를 부리는 방식이 **공유 사전 RPC** 에서 **명함 + 자연어 부탁**으로 바뀌었다.

| | 옛 방식(은퇴) | 지금 |
|---|---|---|
| 남의 몸을 부림 | 내 어휘로 상대 액션을 원격 호출(공유 레지스트리) | `[others:ask]{to, message}` — 자연어로 부탁 |
| 상대가 하는 일 | 시킨 코드를 실행 | **자기 사전으로** 컴파일→실행→통화 회신(1회 자가교정, 어휘 밖이면 정직한 거절) |
| 상대 능력 파악 | 사전을 통째로 공유 | **명함** `GET /nodes/card`(desc-프로젝션, ~70토큰/몸, 등록 시 상호 자동 교환) |
| 특별한 관계 | 전용 배관(특권) | **이웃 등급**(`body_trust`) — 폰-맥도 "최고 레벨 이웃"일 뿐 |

- **사전 물리 분리**: 배포물은 전체 사전집이되 설치된 몸은 자기 어휘만 싣는다. 카탈로그와 해마 회상이
  소유-필터를 지나 **"남의 어휘를 학습하지 않는다"**(미지 어휘=남의 것).
- **컴파일러 능력 축은 해마 유무**: 용례가 있으면 조종실 경로로, 없으면 사전-동봉 경량 모델로 컴파일한다.
- **`delegate` 와의 구별**: `[others:delegate]`=**인격**(에이전트)에게 일을 맡김 / `[others:ask]`=**몸**에게 능력을 부탁함.
- **표면 분리**: 원격 런처(=PC 의 일부, 5탭)와 폰 네이티브(=독립 시스템, 3탭)를 조립 모듈로 갈랐다
  (`launcher_surface_remote.py` / `launcher_surface_phone.py`). 폰 조종실은 로컬 완결(translate·validate·distill·catalog).
- **클립보드**: 몸 사이 특권 배관 대신 표면 축을 태우려 원격 런처 수신면(clipbox)을 뒀다가 2026-07-28 **철회** — '폰으로'는 종전 푸시 큐를 그대로 쓴다.

### USB 손발 — 낯선 PC 에 꽂는 얇은 몸 (2026-07-23)

- **발급** `[self:limb]{op: issue/list/revoke}` → `outputs/limb_issue/<이름>/`(허브 주소 + limb key + 헬퍼 실행파일 + 사용법).
  USB 에 실리는 것은 허브 비밀번호가 아니라 **limb key 하나**이고, 분실 시 그 키만 폐기한다.
- **조작** `[limbs:guestpc]{op: shell/read/write/list/info}` — 허브에서 하달. 눈은 없다(셸·파일만).
- **연결 방향**: 헬퍼(Go 단일파일)가 그 PC 에서 허브로 **아웃바운드** 접속 → 폰 푸시 큐(`phone_jobs`)를 그대로
  재사용해 셸 봉투를 당겨가 실행·회신. 그 PC 방화벽을 건드리지 않는다. 큐에 흐르는 것은 IBL 이 아니라
  **셸 봉투 JSON**(손발=IBL 엔진 없는 얇은 몸).
- 헬퍼 콘솔은 실행 봉투를 생중계하고, 허브는 작업 시작 시 원 요청을 `note` 봉투로 한 번 하달한다(무슨 일로 움직이는지 보이게).

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

**알림 도달(2026-07-28)**: 위 그림에서 `_save_message_to_db()` 는 오래도록 *저장까지*였다 — 새 메시지가 DB 에 앉아 있어도 사용자에게 닿는 경로가 0이라, 메신저 창을 열어봐야만 알 수 있었다. 저장 직후 **`notify_dispatch.notify_user()`** 단일 관문을 태운다:

```
_save_message_to_db()  →  notify_dispatch.notify_user()
                              ├ ① 알림함 기록 (notification_manager)
                              ├ ② A: 런처 연결 시 → /ws/launcher `show_notification`
                              │     → Electron OS 네이티브 알림 + 배지 + 클릭=메신저 창
                              └ ③ B: 미연결 폴백 → desktop_notify.py
                                    (의존성 0 — osascript / PowerShell WinRT / notify-send)
```

- 워커 스레드에서 부르므로 WS 송신은 `send_launcher_command_sync`(루프 위면 예약만 — 자기교착 방지)를 쓴다.
- win·linux 는 **트레이 상주**라 창을 다 닫아도 수신·알림이 계속된다(macOS 는 독 상주).
- `[self:notify_user]` 도 같은 관문을 지난다 — AI 가 보내는 알림이 진짜 데스크탑에 뜬다.
- ★**경로 C(웹 푸시)는 은퇴**(2026-08-01): 구현·서버 검증까지 마쳤으나 실기기에서 도달 실패. 진범은 같은 origin 에 PWA 가 둘이라 안드로이드가 알림 권한을 그중 한 WebAPK 에만 위임한 것 — **알림 권한은 앱이 아니라 origin 단위**다. 재활 조건(런처 서브도메인 분리)만 주석에 남기고 코드는 전부 제거했다.

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
| contact_type | TEXT | email(구 gmail=별칭), nostr, warehouse(창고 주소) |
| contact_value | TEXT | 이메일 주소, npub, 창고 URL |
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
| info_level | INTEGER | 등급 0~4 (창고·포털·메신저가 공유하는 한 자. 숫자만이며 의미 라벨은 사용자가 정함) |
| notes | TEXT | 메모 |

### contacts 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER | PK |
| neighbor_id | INTEGER | FK → neighbors |
| contact_type | TEXT | email(구 gmail=별칭), nostr, warehouse — 창고 주소도 '그 사람에게 닿는 접점' |
| contact_value | TEXT | 연락처 값 |

### channel_settings 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| channel_type | TEXT | PK (email, nostr — 2026-07-22 채널 어휘 `gmail`→`email` 단일화, gmail 은 별칭만) |
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
## 위임 체인 시스템 (Delegation Chain System)

에이전트 간 비동기 협업을 위한 핵심 메커니즘.

> **2026-05-27 라운드 2 통합 (이력)**: 옛 `delegate_project`/`ask_sync`/`delegate_workflow` 3종이 `[others:delegate]` 단일 액션으로 통합됐다 — `mode: "async|sync|workflow"` × `scope: "cross"` 분기(기본=같은 프로젝트 async). 본문은 새 형식으로 갱신 완료. 파라미터 어휘는 `data/ibl_nodes_src/others.yaml` 참조.

## 개요

```
사용자 → 에이전트A → call_agent(B) → 에이전트B → 작업 완료 → 자동 보고 → 에이전트A → 사용자
```

- `[others:delegate]` IBL 액션으로 다른 에이전트에게 작업 위임 (기존 `call_agent()` 도구, Phase 25: others 노드)
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
  "completed": [
    {
      "to": "에이전트A",
      "message": "이전에 위임했던 요청",
      "result": "이전 위임의 결과",
      "completed_at": "2026-01-18T09:55:00"
    }
  ],
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
| 위임 발생 | `delegations[]`에 위임 정보 누적, `pending_delegations++` |
| 위임 결과 도착 | `responses[]`에 결과 원자적 추가, `pending_delegations--` |
| 사이클 완료 후 새 위임 | `delegations[]` + `responses[]` → `completed[]`로 병합, 새 사이클 시작 |
| 추가 위임 없음 | 태스크 삭제 (`complete_task`) → 컨텍스트도 삭제 |

**핵심**: 태스크가 삭제되면 컨텍스트도 함께 삭제됨. 별도의 클리어 호출 불필요.

### completed[] 사이클 병합

순차 위임 시 이전 위임 결과를 보존하기 위한 메커니즘:

```
1차 위임: delegations=[B], responses=[B결과], pending=0
    ↓ 새 위임 발생 (2차)
사이클 완료 감지 (pending=0, delegations>0)
    ↓
completed에 병합: [{to: B, message: "...", result: "B결과"}]
    ↓
delegations=[], responses=[] 초기화
    ↓
2차 위임 시작: delegations=[C], pending=1
```

이 병합은 `_get_or_create_delegation_context()` (프로젝트 에이전트)와 `_execute_call_project_agent()` (시스템 AI) 양쪽에서 수행됨.

### 병렬 위임 원자적 응답 추가

병렬 위임 시 두 에이전트가 동시에 완료되면 race condition 발생 가능:

```
# 문제: 동시 완료 시 responses[] 유실
에이전트B 완료 → read context → append B결과 → write
에이전트C 완료 → read context → append C결과 → write  ← B결과 덮어씀!
```

**해결**: `decrement_pending_and_update_context()`에 `new_response` 파라미터 추가.
DB의 EXCLUSIVE 트랜잭션 안에서 read-append-write를 원자적으로 수행:

```python
# conversation_db.py / system_ai_memory.py
def decrement_pending_and_update_context(task_id, new_response=None):
    with get_exclusive_connection() as conn:
        # 1. DB에서 현재 delegation_context 읽기
        # 2. new_response를 responses[]에 추가
        # 3. pending_delegations-- 와 함께 저장
```

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

**핵심**: 위임 결과가 `completed[]`에 병합되어 AI가 이전 사이클 작업 내역을 참조할 수 있음. 추가 위임이 없으면 태스크가 삭제되며 컨텍스트도 함께 삭제됨.

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
   - `new_response` 파라미터로 부모 태스크의 `responses[]`에 원자적 추가
   - `pending_delegations` 감소 (EXCLUSIVE 트랜잭션 내에서 동시 수행)
   - 병렬 위임 수집 모드:
     - 남은 위임 있음 → 현재 태스크만 삭제, 보고 스킵
     - 모든 응답 도착 → DB에서 최신 컨텍스트 재조회 → 통합 보고 전송
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

### WebSocket 위임 감지 (시스템 AI)

시스템 AI의 WebSocket 핸들러(`api_websocket.py`)는 위임 발생 시 태스크를 유지해야 합니다.
IBL 경로를 통한 위임을 감지하기 위해 **3-레이어 감지** 사용:

| 레이어 | 감지 방법 | 설명 |
|--------|----------|------|
| 1 | 도구 이름 매칭 | `call_project_agent` 직접 호출 감지 |
| 2 | IBL 결과 문자열 매칭 | `execute_ibl` 결과에서 위임 키워드 감지 |
| 3 | DB pending_delegations 확인 | DB에서 pending > 0 확인 (최종 안전망) |

위임 감지 시: 태스크 유지 (삭제 스킵)
위임 미감지 시: 태스크 삭제 → 사용자에게 응답

### 주의사항

1. **일방향만 가능**: 프로젝트 에이전트는 시스템 AI에게 위임 불가
2. **프로젝트 팀 단위**: 위임 시 프로젝트 전체 에이전트가 활성화됨
3. **태스크 저장 위치**:
   - 시스템 AI 태스크 → `data/system_ai_memory.db`
   - 프로젝트 에이전트 태스크 → 프로젝트별 `conversation.db`
4. **환각 방지**: 결과 없이 "검토했습니다" 등 표현 금지

---

## 스케줄 기반 위임 (Schedule-based Delegation)

기존의 동기적 위임(`call_agent`, `call_project_agent`)에 더해, **시간 기반 비동기 위임** 시스템.

### 개요: 두 가지 위임 경로

| 구분 | 동기 위임 | 스케줄 위임 |
|------|----------|------------|
| 방식 | `[others:delegate]`, `call_project_agent` | `[self:schedule]` + 크로스 위임 |
| 시점 | 즉시 (작업 도중) | 미래 시간 (스케줄러가 트리거) |
| 용도 | A가 일하다가 B에게 분담 | "매일 9시에 B가 이걸 해라" |
| 결과 전달 | 자동 보고 체인 | 대화창 자동 열기 + WS push |

두 경로는 조합 가능: 스케줄로 에이전트가 활성화된 후, 작업 중 동기 위임 사용 가능.

### 에이전트 소유 스케줄 (Owner-based Scheduling)

모든 스케줄 이벤트에는 소유자(owner)가 명시됨:

```json
{
  "id": "evt_abc123",
  "title": "매일 뉴스 수집",
  "action": "run_pipeline",
  "action_params": {"pipeline": "[sense:search]{query: 'AI 뉴스'}"},
  "owner_project_id": "투자",
  "owner_agent_id": "researcher"
}
```

- `owner_project_id`: 소유 프로젝트 (시스템 AI일 때 `__system_ai__`)
- `owner_agent_id`: 소유 에이전트 ID
- 실행 시 owner의 project_path에서 파이프라인이 실행됨
- 결과는 owner의 대화창에 전달 (열려있으면 WS push, 닫혀있으면 창 자동 열기)

### 셀프 스케줄 vs 크로스 위임

**셀프 스케줄** — 자기 자신의 스케줄 등록:
```
[self:schedule]{at: "09:00", pipeline: "[sense:search]{query: '오늘 뉴스'}"}
```

**크로스 위임** — 다른 에이전트의 스케줄에 등록:
```
[self:schedule]{at: "09:00", target_project_id: "투자", target_agent_id: "analyst",
  pipeline: "[sense:search]{query: '오늘 주요 뉴스'}"}
```

`target_project_id`/`target_agent_id`를 지정하면 해당 에이전트가 owner가 되어, 그 에이전트의 컨텍스트에서 실행되고 결과도 그쪽 대화창에 전달됨.

### 핵심 컴포넌트

| 파일 | 역할 |
|------|------|
| `calendar_manager.py` | 에이전트 소유 스케줄 저장/실행, `owner_project_id`/`owner_agent_id` 필드 |
| `api_system_ai.py` | `_execute_schedule()` — 셀프/크로스 위임 분기 |
| `api_scheduler.py` | `GET /calendar/events/by-agent` — 에이전트별 스케줄 조회 API |
| `websocket_manager.py` | `send_to_system_ai_chat()`, `find_system_ai_connections()` |
| `api_websocket.py` | `/ws/launcher` — 백엔드→Electron 창 제어 (자동 열기) |
| `Launcher.tsx` | WS 리스너 — 창 열기 명령 수신 |
| `workflow_engine.py` | `execute_pipeline(agent_id=)` — 파이프라인에 agent_id 전달 |
| `trigger_engine.py` | 이벤트/트리거 기반 실행 엔진 (구 `event_engine.py`에서 이전) |

### 스케줄 실행 흐름

```
스케줄 시간 도래
    ↓
CalendarManager._action_run_pipeline()
    ↓
owner_project_id/owner_agent_id 읽기
    ↓
ProjectManager로 project_path 해석
    ↓
execute_pipeline(steps, project_path, agent_id=owner_agent_id)
    ↓
결과 → _deliver_result_to_chat()
    ↓
대화창 열림? → WS push (auto_report)
대화창 닫힘? → Launcher WS로 창 열기 + DB 저장
```

---

## 위임 시스템 전체 요약

IndieBiz OS의 위임은 두 가지 레이어로 구성:

| 레이어 | 메커니즘 | 특징 |
|--------|---------|------|
| **동기 위임** | `[others:delegate]`, `[others:delegate]{scope: "cross"}` | 즉시, 작업 도중 분담, 결과 자동 보고 |
| **스케줄 위임** | `[self:schedule]` + 크로스 위임 | 시간 기반, 에이전트 소유 |

두 레이어는 조합 가능:
- 스케줄로 활성화된 에이전트가 작업 중 동기 위임 사용
- 멀티에이전트 작업계획서는 동기 위임을 순차/병렬로 조합하여 실행

---
*위임 시스템 이력:*
*Phase 25: others 노드로 통합. `[others:delegate]`, `[others:delegate]{scope: "cross"}`.*
*Phase 28: `create_plan`/`_execute_plan()` 폐지. 작업계획서는 자연어로 작성하고 기존 위임 도구로 실행.*
*event_engine.py → trigger_engine.py로 이전 (event_engine.py는 하위 호환 래퍼로 유지).*

> 참고: 위임 가이드 파일 (guide_db.json에서 검색)
> - 프로젝트 에이전트용: `delegation_agent.md`
> - 시스템 AI용: `delegation_system_ai.md`
> - 작업계획서 작성: `work_plan_writing.md`

*마지막 업데이트: 2026-08-01 — **받은 것이 사용자에게 닿고, 창고가 바깥을 보다**: ①**알림 도달 경로 A+B**(2026-07-28, 위 '메시지 수신' 절): 수신이 DB 에 저장만 되고 사용자 도달 경로가 0이던 것을 `notify_dispatch` 단일 관문으로 봉합 — 런처 연결 시 OS 네이티브 알림+배지+클릭 이동, 미연결이면 의존성 0 데스크탑 폴백, win·linux 트레이 상주. 경로 C(웹 푸시)는 실기기 불발로 은퇴(★알림 권한은 **origin 단위**). 부수 수선: `websocket_manager.broadcast_message` 부재로 `[out:gui]` WS 푸시가 조용히 전멸하던 것, `[self:notify_user]` 설명의 거짓("텔레그램"). ②**nostr 채널 기본 켜짐**(2026-07-28): 설정할 게 없는데 기본값이 꺼짐이라 DM **수신만** 조용히 멈춰 있었다. 스위치가 여닫는 것이 수신뿐임을 문구에도 명시. ③**창고가 바깥을 보다**(2026-07-29): 이웃찾기 두 갈래(소개글 수신면 / 둘러보기)·📣 공개 추천(사실만 채운 초안 → 사람이 고쳐 발행)·**neocities 어댑터**(개인 홈페이지 169만)·비즈니스 아이템의 자족 카탈로그 자동 진열. 이전(2026-07-25) — **몸이 주소를 갖고, 몸끼리 말을 트다**: ①**공유창고**(2026-07-18~21, 위 '공유창고' 절): 발행=폴더에 파일 놓기 → 노드 맨 주소에서 그대로 서빙(색인·변환 없음), 레벨 0~4=이웃 CRM 과 같은 자(위 레벨은 403 아닌 404·`has_restricted` 냄새 한 비트), 기계 얼굴 `GET /manifest`+`GET /f?path=`+쿠키 로그인이 계약의 전부. 읽는 쪽=30분 폴러(seed/new/changed, 모델 호출 0)와 **방언 어댑터**(nginx 색인·RSS/Atom·Nextcloud·일반 웹페이지)로 설치 안 한 이웃까지 편입, 리트윗=`.url` 포인터 파일, 창고 주소=이웃의 `contact_type='warehouse'`, 회원 자격 폴링(자가치유·익명 폴백)과 창고 점수 0~3(접근 레벨과 독립인 내 평가 축). ②**몸 사이 소통 = 명함+부탁**(2026-07-22): `GET /nodes/card` + `POST /nodes/ask`(어휘 `[others:ask]`) — 상대 액션 이름을 흉내 내는 대신 자연어로 부탁하고 받는 몸이 자기 사전으로 컴파일·실행. 사전 물리 분리(설치=자기 어휘만·소유-필터), 신뢰=이웃 등급(`body_trust`), **몸 사이 특권 배관 없음**. 표면 분리(원격 런처 5탭 / 폰 네이티브 3탭), 클립보드는 clipbox 로 재배치. **채널 어휘 `gmail`→`email` 단일화**(별칭만 잔존 — 번역 테이블 3사본 소멸). ③**USB 손발**(2026-07-23): `[self:limb]` 발급 + `[limbs:guestpc]` 조작, 헬퍼가 허브로 아웃바운드(푸시 큐 재사용·셸 봉투 JSON). 이전(2026-07-17) — **공개 표면 가족(커뮤니티당 노드 하나)**: 메시지 왕복 채널(Gmail·Nostr·메신저)과 별개로, 내 시스템을 공개 웹 주소로 노출하는 표면이 `others` 노드에 자람 — `[others:portal]`(개인 포털 `/h/`, 다중·아이디/비번 또는 열쇠 로그인·회원=이웃 CRM 레벨 0~4·오디오 프록시)·`[others:showcase]`(공개 파일 `/s/`)·`[others:family_news]`(가족신문 `/n/`)·`[others:bulletin]`(로그인 없는 게시판 `/b/`) + 정기보고 발행 면(`/r/`). 공개 서빙=브라우저→Cloudflare Worker→터널→맥 3층(공유 `X-Showcase-Secret`). 포털 붙임=`[others:portal]{op:display}` 색인 다이얼(min_level 손님~가족). 위 "공개 표면" 절 참조. 이전(2026-06-17) — **맥↔폰 양방향 연합 라이브·인증화**: 폰 백엔드가 앱 UI 없이 상주(`AgentForegroundService` START_STICKY·부팅), 맥→폰 `X-Phone-Token` 인증(폰 phone_api 미들웨어, 토큰 있을 때만 `0.0.0.0` 바인드), `provision_phone_keys.py`가 토큰 푸시 — 인증 전자동. 보안=양방향 게이트·인터넷 비노출·caveat는 LAN 평문 HTTP. 이전(2026-06-14) — channel 트리거("Y 메시지 오면 X 실행") 맥 발화 경로 신설: channel_poller `_save_message_to_db`(Gmail/Nostr 3수신 경로 공통 깔때기)에 `_check_channel_triggers` 훅 → 매칭 시 데몬 스레드로 파이프라인 발화(메시지를 _prev_result 주입). **폰은 메시지 폴링 안 함**(사용자 결정 2026-06-14) — 메시지 수신/폴링은 PC 담당, 폰=리모컨/두 번째 자아. 이전(2026-06-12): IndieNet 전용 REST(api_indienet) 제거 → 커뮤니티/메신저 IBL 계기화(others:feed/board/messages/nostr) + NIP-17 멀티릴레이 실시간 수신 + 자동응답 PC 전용 영속화 + 연락처 email→gmail. 이전(2026-06-10): Nostr DM NIP-17 전환(nip44/nip17 모듈) + 폰 컴패니언 피드. 이전: 2026-04-05*
