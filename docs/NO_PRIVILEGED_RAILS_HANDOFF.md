# 특권 소멸 핸드오프 — 몸 간 특권 배관 전면 철거 (폰-맥 = 최고 레벨 이웃)

2026-07-22 세션 종료 시점. 표면 분리(docs/SURFACE_SPLIT_HANDOFF.md, 완료) 직후의
설계 논의에서 사용자가 확정한 다음 착수 과제.

## ★★재설계 (2026-07-22 3차 — 두 목표 분리, 우편함 철회) — 이 절이 현행 정본

아래 "1단계 구현 상태"(우편함)는 **철회됐다**. 사용자가 뒤엉킨 두 목표를 분리:

- **목표 1 (핵심)**: 두 indiebizOS 의 소통 — 대부분 **PC 둘**이고, 각자 공개 얼굴
  (CF 터널/tailscale)+공유창고를 가진다. **전송층은 이미 풀려 있다**(주소로 HTTP —
  창고 폴링·게시판·포털·ask). 폰네이티브는 이 목표의 *도구*였을 뿐이고, 폰의 고생
  (CGNAT=얼굴 없음)은 목표 1의 문제가 아니다. 하트비트 푸시큐도 우편함도 폰-특수
  배관이라 목표 1에 기여 없음. **끝 그림 = "몸의 주소로 HTTP ask 하나"** — Nostr 는
  사람-메신저·커뮤니티 층으로 복귀(몸의 신호 버스 아님).
  남은 것은 전송이 아니라 **관계·정책**: ①낯선 몸의 만남·부여 절차(소유주 승인 UI)
  ②검증 가능한 신원(자기보고 device_id → 서명) ③정책 바닥 — "남의 의도 자동실행
  금지"와 ask 의 정리(남의 부탁은 읽기-전용까지만 자동, 그 이상=승인 대기함).
  특권 소멸 2~5는 유효하되 **순수한 빼기**(대체 전송층 신설 없음).
- **목표 2 (개인 기능, 비핵심)**: 내 폰↔PC 메시지. 원격런처를 **연 상태에서만**
  받아도 무방(사용자 확정). → 새 배관 0으로 원격런처에 재배치.

### 작업 계획 (이 순서대로 — A→D) — ✅A·B·C 완료(같은 날, 커밋 참조), D=문서·메모리

검증 실측: clipbox 적재→원격런처(실브라우저) 조종실 카드 렌더→📋 복사→consume→카드
소멸 종단 · 빈 내용 가드 · ask payload dry_run 회귀(compiled=[self:output] 유지) ·
build --check·번들 파생(ask_mailbox 이탈)·tsc 통과. 폰 APK 재빌드=USB 연결 시 설치
(구버전 폰도 목표 2 는 원격런처로 즉시 동작 — 폰 번들과 무관, 갱신은 clip_to_mac
ask 경로·불용 코드 정리 목적).

**A. 우편함 걷어내기** (커밋 `8bb6010` 부분 철회):
- 삭제: backend/ask_mailbox.py · data/ask_mailbox_seen.json(+.gitignore 줄) ·
  channel_poller giftwrap ask 훅 · body_ask `_ask_mailbox_fallback`+호출 2곳+
  `timeout` 파라미터 · api_nodes RegisterRequest.npub+attach_npub 호출 ·
  body_trust.attach_npub · capability_card `_self_npub`+identity.npub ·
  phone_api `_start_ask_mailbox` 데몬+기동 · register payload npub ·
  _fetch_and_grant 의 npub 부착 · others.yaml ask desc 의 우편함/timeout 문구 ·
  guides/body_ask.md 우편함 문구.
- **남김** (전송 무관 ask 개선 = 목표 1 자산): payload 동봉("$payload.<키>" 치환)·
  AskRequest.payload · 소유-가드(capability_card.foreign_actions 위임)+해마 용례
  필터 · ask_peer connect 5초 분리 · 해마 시딩 6용례+ibl_distilled ·
  peer_cards identity-갱신 fix · PRIVILEGE_LEVELS "철거 목록" 재정위 ·
  phone_api clip_to_mac 의 ask 경로(폰→PC ask 상행 — 맥은 상시 도달, timeout 만 제거).

**B. 목표 2 재배치 — 맥 메시지함 + 원격런처 수신면**:
- 백엔드(api_launcher_web, 원격런처 인증층 뒤): data/clipbox.json —
  POST /launcher/clipbox {text}(적재) · GET /launcher/clipbox(최근 목록) ·
  POST /launcher/clipbox/consume {id}(수신 처리).
- 데스크탑 Launcher.tsx '폰으로' 버튼: [others:ask] 대신 POST /launcher/clipbox.
  피드백 "담김 ✓ — 폰에서 런처 열면 받아요".
- 원격런처(launcher_app_common.py): "PC에서 온 메시지" 면 — loadPeer 패턴으로 20초
  폴링, 카드(미리보기+📋 복사=navigator.clipboard.writeText, 복사 시 consume).
  IS_PHONE(폰네이티브)이면 비활성 — clipbox 는 허브(맥)의 것, 원격런처 전용.
  ★Python-내-JS 따옴표 함정 · 두 표면 조립(launcher_surface_remote/phone) 재확인.

**C. 재빌드·검증·커밋**: py_compile · build_ibl_nodes(+--check) ·
  build_body_bundle android(ask_mailbox 이탈 177→176) · APK 재빌드(설치=USB 대기) ·
  tsc · 라이브 스모크(/ping·ask dry_run payload 회귀·clipbox 왕복) · main 커밋 push.

**D. 문서·메모리 정합화**: 이 문서(완료 표시) · BODY_CARD_RESEARCH.md "✅해소(우편함)"
  절→철회 기록 · 메모리 architecture_no_privileged_rails(1항 Nostr 처방 재작성)·
  MEMORY.md START HERE · 태스크 #3(폰 APK) 설명 갱신.

**이번 범위 밖(하지 않음)**: 배관 #1(하트비트+푸시큐) 실제 삭제 — [limbs:phone]
어휘의 에이전트 빌림이 아직 이 배관에 탄다(census 확인 후 별도 단계) · 폰 얼굴
(tailscale) 보류 · 낯선 몸 만남·신원·승인 = 목표 1 의 다음 단계(설계부터).

## [철회됨] 1단계 구현 상태 (2026-07-22 후속 세션 — 우편함, 기록용으로만 보존)

**구현**: `backend/ask_mailbox.py` 신설 — NIP-17 DM 위 ask 봉투(`{"indiebiz_ask":1,
op: ask|result, id, ts, message, payload, ...}`), ASK_RELAYS=nos.lol+damus(수신 선언
kind:10050 과 정렬). 상관관계 id + 결과 대기(수동 배달 _waiters + 능동 폴 자급),
중복제거 2층(gift id 프로세스 내 + 봉투 id 디스크 영속 data/ask_mailbox_seen.json),
freshness TTL 600초(백필 대량 실행 방지), 60KB 신호층 한도. 수신: 맥=channel_poller
giftwrap 훅(백필 가드보다 앞 — 우편함 자체 TTL) / 폰=phone_api `_start_ask_mailbox`
폴 데몬(12초 주기 — RelayClient 가 EOSE 에 닫혀 상시 구독 불가).

**신원**: 명함 identity.npub(capability_card._self_npub — 몸-인식) + 부여식 npub
접점(body_trust.attach_npub — contact_type='body', 값 "npub:<hex>") + 등록 payload
npub 동봉(api_nodes RegisterRequest / phone_api). 우편함 부탁은 seal 서명의 npub 로
원장 판정(handle_ask device_id="npub:<hex>") — 낯선 npub=정직 거절. peer_cards 는
hash 불변이어도 identity 갱신(npub 부착이 캐시에 스미도록).

**payload 동봉**: handle_ask(payload) — 컴파일 프롬프트에 "$payload.<키>" 자리표시자
안내, 실행 직전 원문 치환(body_ask._substitute_payload — 따옴표 감싼 형태는 JSON
인코딩 통치환). 응답 compiled_ibl 은 자리표시자 유지(원문 미반향). [others:ask]
params: payload·timeout 추가(desc 갱신·재빌드 완료, 액션 수 불변 158).

**소유-가드**(구현 중 실측 버그): 맥 컴파일러가 부탁을 [limbs:phone](남의 어휘)로
번역 — 물리 분리 후 남의 어휘는 레지스트리에 "미지"라 code_is_own 이 열어줌 →
handle_ask 에 엄격 가드(_foreign_actions — 미지=남의 것, 1회 교정 후 정직 거절) +
해마 참고 용례 소유-필터(_filter_foreign_refs). 맥 해마의 phone_only 용례 오염은
별도 과제로 분리(스폰). 해마 시딩 6용례(manual_seed, ask_enclosure)+ibl_distilled
800→806 — 클립보드 부탁 컴파일 결정론화(재학습 대기열).

**클립보드 이주**: '폰으로'(Launcher.tsx)=`[others:ask]{message, payload:{text},
timeout:20}` (관문 [limbs:phone] 직결 은퇴) / 'PC로'(phone_api clip_to_mac)=
body_ask.ask_peer (HTTP ask 상행 + 우편함 폴백, _forward_to_mac 은퇴). ask_peer:
HTTP connect 5초 분리 + 실패 시 우편함 폴백(_ask_mailbox_fallback — 명함 npub 해소).

**검증(맥)**: 실릴레이 자기-DM 종단 왕복 9.5초(발행→폴→언랩→신뢰 게이트 낯선 몸
거절→결과 봉투→상관관계 배달) · 부여식 후 dry_run 왕복 9.7초(compiled=[self:output]
{op:"clipboard", content:"$payload.text"}) · 로컬 실행 6.7초(치환→실제 클립보드,
원상복구) · build --check·번들 파생(ask_mailbox 합류 177)·tsc 통과. PRIVILEGE_LEVELS
선언은 "철거 대상 목록"으로 재정위(body_trust.py). 임시 부여식·테스트 산출물 정리.

**⏳폰 설치 대기(USB 필요)**: APK 는 새 번들로 빌드 완료(app-debug.apk — ask_mailbox
·소유가드 body_ask·npub 등록·폴 데몬·clip_to_mac ask 이주 포함). USB 연결 시:
`./phone-companion/scripts/setup_phone.sh` 설치 → force-stop 재기동 → A36 실기
회귀 기준 검증 ①'폰으로'(Wi-Fi=HTTP ask, LTE=우편함 — 현재 폰이 LTE 라 구버전은
node_unreachable 실측) ②'PC로' ③폰 재등록 시 맥 원장에 npub 접점 부착 확인
④맥→폰 우편함 종단(폰 npub 명함 교환 후). 구버전 폰과의 과도기: 구 폰은 payload
를 모른 채 /nodes/ask 를 받으므로 '폰으로'는 폰 갱신 전까지 미완(회귀 기준 미충족).

## 원칙 (사용자 확정 — 원문 취지 그대로)

- 남아 있는 폰-맥 특권 배관은 "**모두 없어져야 하는 것들 — 그런 게 있으면 독립적인 몸이
  아니다**." 전용선(env 주소+공유 토큰)이 하나라도 남으면 그 몸은 위성이지 독립 몸이 아님.
- **특권 실게이트 기각**: body_trust.PRIVILEGE_LEVELS(backend/body_trust.py:21,
  BODY_CARD_RESEARCH.md:171)로 특권을 원장 레벨로 *집행*하자던 기존 열린 과제는 목표로서
  폐기 — 감독이 아니라 **소멸**이 목표. PRIVILEGE_LEVELS 선언은 착수 시 이 원칙으로 갱신.
- 몸 간 관계의 문법은 **이웃 문법 하나**(명함·[others:ask]·신뢰레벨·창고)로 통일.
  폰-맥 = "주인이 서로에게 최고 레벨을 부여한 두 이웃" = 두 PC 의 indiebizOS 관계와 동형.
  낯선 몸·N대 폰·타인 몸까지 같은 코드로 확장되는 것이 이 통일의 값어치.
- 기능은 죽이지 않는다 — 특권 배관 위의 기능(클립보드 왕복 등)은 이웃 문법으로 **재표현**.

## 현재 상태 (이 세션에서 확인)

이미 이웃 문법인 것: 명함 교환(/nodes/card, peer_cards 상호 fetch) · [others:ask](자기
사전 컴파일·정직 거절) · 신뢰 원장(body_trust, 부여식) · 창고 폴링. 이미 은퇴한 변장:
catch-all 프록시·창고 프록시·스위치 원격·채팅 폴백·표면 공유(→몸별 조립).

**남은 특권 배관 5개** (전부 env 주소+공유 토큰/비번 전용선, 원장 미경유):

| # | 배관 | 코드 앵커 |
|---|------|-----------|
| 1 | 하트비트 등록+푸시 큐 (허브-위성) | 폰: phone_api.py `_register_with_hub`(:641, 롱폴 wait25 :721, 푸시작업 실행 :748, 기동조건 :1576) / 맥: api_nodes.py /nodes/register(:49)·/nodes/heartbeat(:86), phone_jobs.py, ibl_engine `_queue_push_fallback`(:178) |
| 2 | 엔진 관문 자동위임 | ibl_engine `_forward_to_phone`(:223)·`_forward_to_mac`(:302)·`_census_log`(:148→data/forwarding_census.jsonl, 집계 scripts/forwarding_census_report.py) |
| 3 | 모델·해마 렌트 | phone_api `_run_local_harness`(:1165 부근 — 중급·본격=claude_code_remote 맥 렌트, 해마=렌트 인덱스) |
| 4 | business/health DB 머지 | phone_api /business/sync/*(:794~)·/health/sync/*(:855~), business_sync.py |
| 5 | 파일 당김(토큰 직결) | ibl_engine `_pull_remote_artifacts`(:380, _forward_to_phone 결과에서 호출), 폰 /launcher/file, [limbs:phone] @hub |

클립보드 두 버튼(사용자가 "지금 중요한 기능"으로 지목):
- **'폰으로'(맥→폰)**: Launcher.tsx:755 → `[limbs:phone]{op:clipboard}>>{op:notify}` →
  관문 직결 또는 푸시 큐(#1·#2 의존). **브라우저(원격런처)는 이 방향을 구조적으로 대체
  불가**(상시 수신 채널 없음+웹 보안상 외부발 클립보드 쓰기 불가) — 폰네이티브 유지 확정.
- **'PC로'(폰→맥)**: phone_api /launcher/clip-to-mac(:195) → `_forward_to_mac`
  `[self:output]{op:clipboard}`(#2 의존). 원격런처 브라우저 경로(붙여넣기 칸 폴백)는 별도 생존.

## 전송층 결정 (이 세션의 논의 결과)

- **계층화**: 신호층(작고 드문 것 — ask 부탁·프레즌스·클립보드 텍스트)=**보편 우편함** /
  대량층(파일·렌트급 스트림)=HTTP 직결(도달 가능할 때).
- 우편함 1순위 후보=**Nostr DM(NIP-17)**: 배관 기존(channel_poller kind:1059)·npub 신원닻
  방향과 합류·양쪽 아웃바운드라 CGNAT/멀티폰 해소. 폰 컴패니언 1차(06-06)가 NIP-17이었던
  역사 있음 — 전면 전송이 아니라 *신호층 한정*이므로 당시 한계(지연·페이로드)와 충돌 안 함.
- 검토된 대안(참고): 오버레이 메시(tailscale/Headscale — 자기 몸들엔 최강이나 낯선 몸
  확장 불가)·MQTT·ntfy/UnifiedPush(자기호스팅 푸시 — 현 하트비트의 표준화판)·Matrix
  (kmatrix-mcp 기존)·iroh(노드ID 다이얼+실스트림, 생태계 어림). 릴레이 실측 주의: 이
  코드베이스에서 릴레이 저자조회 수십초→2.2초 병렬화 이력(nostr_relay_latency_fix).

## 작업 순서 (의존 관계 — 순서 틀리면 클립보드가 먼저 죽는다)

1. **하행 우편함의 이웃화 (선행 필수)**: Nostr DM 위 `[others:ask]` 큐 — 기존 열린 과제
   "ask 푸시큐 폴백(LTE 실측 발생)"의 답이기도 함. 클립보드 '폰으로'를 최고 신뢰레벨
   ask("클립보드에 넣어줘"+알림)로 이주. 설계 숙제: 상관관계 ID·타임아웃·중복 제거(릴레이
   재전달)·릴레이 상시 구독(폰 포그라운드 서비스 기존)·자기호스팅 릴레이(NAS) 여부.
2. **관문 매장**: forwarding_census.jsonl 며칠 0 확인 → _forward_to_* 자동 빌림 분기 제거
   (명시 호출부는 1단계에서 ask 로 이주 완료 후). 'PC로'는 ask 상행(맥 도달=HTTP ask)으로.
   phone_api 의 사용처-0 트리오(_mac_proxy·_relay·_list_or_empty)도 phone_proxy_census
   0 확인 후 함께 매장.
3. **렌트 독립**: 폰에 자기 키 프로비저닝(키 배급=주인이 몸을 차리는 일, 몸 간 특권 아님)
   → 폰 기어가 자기 키로 클라우드 직접. 해마=자기 축적까지 사전-동봉 컴파일(조종실
   폰-로컬이 이미 이 경로, distill 도 폰-로컬로 쌓기 시작함).
4. **DB 머지 재표현**: 메시지=릴레이 진실원 선례대로, 주소록도 교환 문법(ask/창고/릴레이
   계약)으로. 두 몸의 주소록이 다를 수 있음을 수용(그게 독립).
5. **파일 재표현**: 폰=맥 창고의 **회원**(가입·레벨— 기존 창고 회원 시스템 재사용)으로
   업로드, 또는 ask 응답 동봉. _pull_remote_artifacts 철거.
6. 각 단계마다: 프레즌스 표시(조종실 peerStatus "연결됨")를 허브 등록이 아닌 이웃
   핑/명함 fetch 로 재표현 — UI 회귀 주의.

## 함정·가드

- **철거는 대체 뒤에**: #1 배관을 먼저 끊으면 '폰으로'(LTE 포함)가 즉사. 단계마다 클립보드
  왕복 실기 검증(A36 USB 상시)을 회귀 기준으로.
- census 파일 2개 혼동 금지: **forwarding_census.jsonl**(관문 자동위임, 맥·폰 각자
  data/) vs **phone_proxy_census.jsonl**(폰 catch-all 404). 매장 대상이 다름.
- ibl_engine 자기교착 부류: 이벤트 루프 스레드에서 결과 블로킹 금지(기존 주석 :200 부근,
  LTE 푸시·창고 폴러와 같은 부류) — 우편함 구독/발행도 루프 밖 스레드로.
- Nostr 수신은 freshness 가드(과거 백필 대량 실행 방지 — auto_response kind:1059 선례).
- gemini-2.5-flash 명시+thinkingBudget:0 (flash-latest 별칭 함정).
- 폰 최신화: `setup_phone.sh --build` + force-stop 재기동, adb forward tcp:8788.
- 신원: 낯선 몸과 같은 우편함을 쓰게 되므로 npub 서명 검증(기존 열린 과제)이 1단계와
  자연 합류 — device_id 자기보고를 서명으로 승격할 기회.

## 배경 (이 세션)

표면 분리 완료(`4feb402` 모듈화·`6d1ea80` 표면 조립 2개·`e8d22e4` 조종실 폰-로컬 4라우트,
main push). 논의 흐름: 클립보드 왕복의 중요성 → 폰네이티브 상시성=하행의 유일 채널 →
폰-맥 통신 구조(직결+하트비트 롱폴) → Nostr/대안 조사 → "남은 특권 전부 소멸" 확정.
메모리: architecture_no_privileged_rails.md(헌법)·project_surface_split.md.
