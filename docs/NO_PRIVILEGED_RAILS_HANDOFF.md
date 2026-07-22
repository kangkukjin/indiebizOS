# 특권 소멸 핸드오프 — 몸 간 특권 배관 전면 철거 (폰-맥 = 최고 레벨 이웃)

2026-07-22 세션 종료 시점. 표면 분리(docs/SURFACE_SPLIT_HANDOFF.md, 완료) 직후의
설계 논의에서 사용자가 확정한 다음 착수 과제. **아직 코드 손 안 댐 — 원칙·순서 확정 상태.**

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
