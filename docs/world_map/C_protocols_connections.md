# C. 통신·프로토콜·자동화·연결 (조사 2026-09-06)

> 조사 방식: 웹 검색 55회 + 페이지 1회 정독. 기존 어휘 목록(`ibl_vocab_inventory.txt`)과 `data/ibl_nodes_src/*.yaml` 을 대조. 현재 몸의 채널 어휘는 **Gmail(IMAP/SMTP)·Nostr 두 channel_type 만** 이며(`others.yaml` channel_engine 라우터, `target_key: channel_type`), Telegram·Matrix 는 워크스페이스의 별도 MCP 로만 존재하고 IBL 낱말은 아님. 따라서 메신저·푸시 부류의 어휘 후보 형태는 **새 낱말이 아니라 기존 `channel_type` 확장**으로 적었다(반-어휘-증식 원칙).

## 요약 (가장 강력한 5개)
1. **MCP 공식 레지스트리 + 상위 서버군(GitHub·Playwright·filesystem 등)** — 2026년 AI 연결의 사실상 표준이자 앱스토어. 레지스트리 API 하나로 9,600여 서버를 발견·설치 가능. 몸이 MCP 클라이언트가 되면 어휘 없이도 남의 손을 빌린다.
2. **Home Assistant REST/WebSocket + MQTT(Mosquitto/paho)** — 집·IoT 연결의 유일한 표준 쌍. Zigbee2MQTT·ESPHome 이 전부 이 두 통로 위에 얹힌다. `[limbs:home]` 한 낱말로 집 전체가 팔이 된다.
3. **Telegram Bot API** — 개인이 무료·즉시·심사 없이 쓰는 양방향 채널의 표준. 2026-06 Bot API 10.1 로 여전히 확장 중. channel_type 확장 첫 후보.
4. **OpenAPI 3.2 + Standard Webhooks** — "규격만 있으면 어떤 API 든 부른다"는 일반 어휘(`[sense:openapi]`)의 근거. 어휘 증식 없이 세계의 API 를 흡수하는 메타 통로.
5. **CalDAV/CardDAV + iCalendar/vCard, WebDAV, rclone, SSH(paramiko), Tailscale** — 개인 인프라 연결의 6대 규약. 전부 무료·오픈·30년 가까이 살아 있고, 대체가 없다.

## 표

| 등급 | 리소스 | 한 줄(무엇을 잇나) | 통로(규격/API/CLI/pip + 인증) | 무료 범위 | 왜 표준인가 | 어휘 후보 형태 | 근거 URL | 확인일 |
|---|---|---|---|---|---|---|---|---|
| S | MCP 공식 레지스트리 (modelcontextprotocol.io) | 공개 MCP 서버 발견·메타데이터 | REST(OpenAPI 공개) `registry.modelcontextprotocol.io`, 인증 불요(읽기) | 전부 무료·오픈소스 | Anthropic·GitHub·MS·PulseMCP 공동. 2026-05 기준 9,652 서버 | `[sense:mcp]{op:"search", q}` → `[self:package]{op:"install", kind:"mcp"}` | https://registry.modelcontextprotocol.io/ | 2026-09-06 |
| S | MCP 서버 상위군: GitHub(공식)·Playwright(MS)·filesystem(Anthropic)·Notion·Slack·Supabase·AWS·Sequential-Thinking·Jira/Atlassian·Figma | 코드저장소·브라우저·파일·문서·클라우드를 LLM 도구로 | stdio/HTTP MCP 서버, 각 서비스 토큰 | 서버 자체 무료(대상 서비스 요금 별도) | 검색량 상위 15 (Ahrefs 2026-03), Playwright ★30k+ | 몸을 MCP 클라이언트로: `[limbs:mcp]{server, tool, args}` (Playwright·Context7 은 각각 `limbs:browser`·`sense:devdocs` 와 겹침) | https://mcpmanager.ai/blog/most-popular-mcp-servers/ | 2026-09-06 |
| S | Home Assistant REST + WebSocket API | 집의 모든 장치·센서·자동화 | `GET/POST /api/*`, `ws /api/websocket`, Long-lived access token; pip `homeassistant-api` | 전부 무료(셀프호스팅) | 오픈소스 홈오토메이션 사실상 유일 표준, 2026.9 릴리스 활발 | `[limbs:home]{op:"call", domain, service, entity}` / `[sense:home]{op:"state"}` | https://www.home-assistant.io/blog/2026/09/02/release-20269/ | 2026-09-06 |
| S | MQTT — Eclipse Mosquitto 브로커 + paho-mqtt | IoT 장치·센서 pub/sub 메시지 버스 | MQTT 3.1.1/5.0, `pip paho-mqtt` 2.x, 브로커 계정/TLS | 전부 무료(오픈소스) | IoT 메시징 유일 표준; Mosquitto 2.1.2(2026-02) | `[sense:mqtt]{topic, wait}` / `[limbs:mqtt]{op:"publish", topic, payload}` | https://mosquitto.org/blog/2026/02/version-2-1-2-released/ | 2026-09-06 |
| S | Telegram Bot API | 개인 양방향 메신저 채널·알림·파일 전달 | HTTPS `api.telegram.org/bot<token>`, BotFather 토큰; `pip python-telegram-bot` 22.x | 전부 무료, 심사 없음 | 개인 봇 채널 1위; Bot API 10.1(2026-06) 진행 중 | `[others:channel_send]{channel_type:"telegram"}` (channel_engine 확장, 새 낱말 아님) | https://core.telegram.org/bots/api | 2026-09-06 |
| S | GitHub REST/GraphQL API + `gh` CLI | 코드·이슈·PR·릴리스·Actions | REST v3/GraphQL v4, PAT 또는 `gh auth`; 5,000 req/h | 공개·개인 저장소 무료 | 개발 연결 유일 표준 | `[limbs:github]{op:"issue"/"pr"/"release", repo}` / `[sense:github]{op:"search"}` | https://docs.github.com/en/rest/rate-limit/rate-limit | 2026-09-06 |
| S | OpenAPI Specification 3.2 (+Arazzo 1.1) | 임의의 REST API 를 규격 하나로 기술·호출 | JSON/YAML 스펙, 인증은 스펙의 securitySchemes 를 따름 | 무료·오픈 표준 | API 기술 사실상 유일 표준; 2026 초점=LLM/에이전트 친화 | `[sense:openapi]{spec_url, operation, params}` — "규격 있는 API 는 어휘 없이 부른다" 메타 낱말 | https://thenewstack.io/openapi-initiative-new-standards-and-a-peek-at-the-roadmap/ | 2026-09-06 |
| S | CalDAV/CardDAV (RFC 4791/6352) — `caldav` 3.x, Radicale 서버 | 캘린더·할일·주소록을 iCloud·Google·Nextcloud·Fastmail 과 동기화 | HTTP DAV, Basic/앱 비밀번호; `pip caldav` 3.x(2026-03), `pip radicale` | 무료·오픈 | 캘린더·연락처 동기화 유일 개방 표준 | `[self:calendar]{op:"sync", server}` (manage_events 는 로컬 원장 — 이건 외부 동기화) | https://caldav.readthedocs.io/latest/about.html | 2026-09-06 |
| S | SSH — paramiko 5.0 / Fabric | 원격 기계 셸·파일(SFTP) | SSHv2, 키/비밀번호; `pip paramiko` 5.0(2026-05, SHA1·MD5 제거) | 무료 | 원격 접속 유일 표준 | `[limbs:ssh]{host, cmd}` (guestpc 는 USB 헬퍼 전용 — 이건 일반 SSH) | https://bitprophet.org/blog/2026/05/09/updates-for-2026/ | 2026-09-06 |
| S | rclone 1.75 | 70+ 클라우드 저장소(S3·GDrive·OneDrive·Dropbox·WebDAV·SFTP)를 rsync 처럼 | CLI + `rclone rcd` 원격제어 API, 각 remote OAuth/키 | 무료·오픈 | 클라우드 저장소 통합 유일 표준 | `[self:cloud]{op:"sync"/"ls"/"copy", remote, path}` | https://rclone.org/ | 2026-09-06 |
| S | Tailscale (WireGuard 기반 메시 VPN) | 내 기기들(PC·폰·NAS)을 인터넷 어디서든 사설망으로 | CLI `tailscale`, 로컬 API, 관리 REST API(액세스 토큰) | Personal 무료 6인·기기 무제한(2026-04 개편) | 개인 메시 VPN 사실상 표준 | `[sense:net]{op:"peers"}` / `[limbs:net]{op:"serve"/"funnel"}` | https://tailscale.com/docs/account/manage-plans/free-plans-discounts | 2026-09-06 |
| A | WireGuard 1.0.20260223 | 커널 수준 VPN 터널(직접 구성) | `wg`/`wg-quick` CLI, 키 쌍 | 무료·오픈 | Tailscale·Mullvad 등의 기반 표준 | Tailscale 이 덮음 — 직접 어휘화 불요, `[limbs:net]` 백엔드 옵션 | https://en.wikipedia.org/wiki/WireGuard | 2026-09-06 |
| A | WebDAV (RFC 4918) — Nextcloud·Synology·iCloud | 원격 파일 읽기/쓰기/목록 표준 | HTTP PROPFIND/PUT, Basic/앱 비밀번호; `pip webdavclient3` | 무료 | NAS·클라우드 파일 접근 공통 규약(rclone 도 지원) | rclone 낱말의 remote 종류로 흡수(`remote:"webdav"`) | https://help.nextcloud.com/t/connect-to-nextcloud-server-with-python/111265 | 2026-09-06 |
| A | iCalendar(RFC 5545)/vCard(RFC 6350) — `icalendar`·`vobject` | 일정·연락처 파일 교환 형식(.ics/.vcf) | 파일 형식, `pip icalendar`, `pip vobject` 1.x | 무료 | 모든 캘린더·주소록 앱의 공통 교환 형식 | `[self:read]{format:"ics"/"vcf"}` 확장 + `[table:document]{format:"ics"}` | https://github.com/py-vobject/vobject | 2026-09-06 |
| A | ntfy.sh (셀프호스팅 가능) | 폰·데스크톱 푸시 알림을 HTTP PUT 한 줄로 | `POST https://ntfy.sh/<topic>`, 토큰 선택; 자체 서버 무료 | 공개 서버 무료(속도 제한), 셀프호스팅 무제한 | 홈랩·개발자 푸시 1위(★30k+, 2026-03 릴리스) | `[others:channel_send]{channel_type:"ntfy"}` 또는 `[self:notify_user]{via:"ntfy"}`(폰 도달 — notify_user 는 데스크탑만) | https://docs.ntfy.sh/releases/ | 2026-09-06 |
| A | Apprise 1.x + apprise-api | 알림 URL 하나로 100+ 서비스(Telegram·Discord·Slack·ntfy·Gotify·SMTP…) 통합 발송 | `pip apprise`, `tgram://`·`discord://` 형식 URL | 무료·오픈 | 알림 추상화 사실상 표준(apprise-api 1.2.1, 2026-08) | channel_engine 의 **다중 채널 백엔드**로 — channel_type 여러 개를 한 번에 흡수 | https://github.com/caronc/apprise | 2026-09-06 |
| A | Discord Webhook + Bot API v10 (discord.py) | 커뮤니티 채널 알림(webhook) / 양방향 봇 | Webhook URL POST(인증 없음, 30/분) · Bot 토큰; `pip discord.py`(2026-03) | 전부 무료 | 개발자·커뮤니티 메신저 표준; API v10 유지 | `[others:channel_send]{channel_type:"discord"}` | https://docs.discord.com/developers/resources/webhook | 2026-09-06 |
| A | Bluesky / AT Protocol (`atproto` SDK) | 분산 소셜 게시·읽기·팔로우 | XRPC HTTPS, App Password 또는 OAuth; `pip atproto` | 무료, 개발자 포털·심사 없음, 5,000pt/h | 개방 소셜 API 중 가장 관대; 유일하게 X 대체 가능 | `[others:feed]{source:"bluesky"}` / `[others:publish]{to:"bluesky"}`(현 publish 는 Nostr 전용) | https://docs.bsky.app/docs/advanced-guides/rate-limits | 2026-09-06 |
| A | Mastodon API / ActivityPub (`Mastodon.py` 2.2) | 페디버스 게시·타임라인·알림 | REST + 스트리밍, OAuth 앱 토큰; `pip Mastodon.py` 2.2.2(2026-08) | 무료(인스턴스 정책 따름) | ActivityPub 구현 1위; W3C WG 가 2026 Q3 개정 중 | `[others:feed]{source:"mastodon"}` / `[others:publish]{to:"mastodon"}` | https://mastodonpy.readthedocs.io/en/stable/ | 2026-09-06 |
| A | Matrix (`matrix-nio` 0.26) | E2EE 분산 메신저·방·봇 | Client-Server API HTTPS, 액세스 토큰; `pip matrix-nio` | 무료(홈서버 무료·셀프호스팅) | 개방 메신저 표준(XMPP 를 대체); 주 22만 다운로드 | `[others:channel_send]{channel_type:"matrix"}` (kc/kmatrix MCP 존재 — IBL 낱말 아님) | https://github.com/matrix-nio/matrix-nio/releases | 2026-09-06 |
| A | signal-cli 0.14.3 | Signal 개인 계정 송수신(비공식) | CLI/JSON-RPC/dbus, 폰 번호 등록 | 무료 | Signal 에 공식 API 없음 — 이것이 사실상 유일 통로 | `[others:channel_send]{channel_type:"signal"}` | https://github.com/AsamK/signal-cli/releases | 2026-09-06 |
| A | 카카오톡 "나에게 보내기" (talk/memo) | 내 카톡 나와의 채팅방으로 알림 | REST `kapi.kakao.com/v2/api/talk/memo/default/send`, 카카오 로그인 OAuth 토큰(만료·갱신 필요) | 무료 | 한국 사용자 알림 도달 1위 앱; 친구 발송은 검수 필요, 나에게는 즉시 | `[self:notify_user]{via:"kakao"}` / `channel_type:"kakao_memo"` | https://developers.kakao.com/docs/latest/ko/kakaotalk-message/rest-api | 2026-09-06 |
| A | n8n Community Edition | 400+ 서비스 노드를 잇는 자동화 허브(셀프호스팅) | REST API + webhook 노드, API 키 | Fair-code, 셀프호스팅 무제한(2026 유지) | 오픈 자동화 1위; Zapier 대체 표준 | `[others:delegate]{to:"n8n", workflow}` — 어휘 없는 SaaS 연결을 n8n 에 위임 | https://docs.n8n.io/deploy/host-n8n/community-edition-features/ | 2026-09-06 |
| A | Node-RED 5.0 | 흐름 기반 이벤트 배선(IoT·MQTT·HTTP) | HTTP Admin API, `http in` 노드 | 무료·오픈(OpenJS) | IoT 자동화 표준; 5.0(2026-06) 대개편 | n8n 과 같은 위임 낱말의 `to:"node-red"` | https://nodered.org/blog/2026/06/09/version-5-0-released | 2026-09-06 |
| A | Docker Engine API + docker-py 7.2 | 컨테이너 실행·로그·상태 | REST over unix socket, `pip docker` 7.2.0(2026-07) | 무료 | 컨테이너 유일 표준 | `[sense:host]{op:"containers"}` 확장 / `[limbs:container]{op:"run"/"logs"}` | https://pypi.org/project/docker/ | 2026-09-06 |
| A | Zigbee2MQTT 2.14 | Zigbee 센서·조명을 MQTT 로 | MQTT 토픽 `zigbee2mqtt/<device>` | 무료 | 사설 허브 없는 Zigbee 표준 | MQTT 낱말 위에 얹힘 — 별도 낱말 불요 | https://github.com/Koenkk/zigbee2mqtt/releases | 2026-09-06 |
| A | ESPHome 2026.8 | ESP32 자작 장치 펌웨어 → HA/MQTT 노출 | YAML → 빌드 CLI, Native API/MQTT | 무료 | DIY IoT 펌웨어 표준(월간 릴리스) | HA/MQTT 낱말로 흡수(esp32_test 프로젝트와 접점) | https://esphome.io/changelog/2026.8.0/ | 2026-09-06 |
| A | A2A (Agent2Agent) 1.0.1 — `a2a-sdk` | 남의 에이전트에 작업 위임·상태 추적 | JSON-RPC/HTTP, Agent Card(`/.well-known/agent.json`) | 무료·오픈(Linux Foundation) | 150+ 조직, Google·MS·AWS 탑재; MCP 의 짝 | `[others:ask]` 의 프로토콜 백엔드(현재 ask 는 이웃 indiebizOS 전용 — A2A 로 열면 남의 에이전트도) | https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year | 2026-09-06 |
| B | Slack Incoming Webhook / Web API | 팀 채널 알림 | Webhook URL POST · Bot 토큰 | 무료 플랜 앱 10개 한도, 웹훅은 "legacy" 표기 | 업무 메신저 1위이나 개인용은 아님 | `channel_type:"slack"` (Apprise 경유가 경제적) | https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/ | 2026-09-06 |
| B | Pushover | 폰 푸시(호스팅) | REST, 앱 토큰+유저 키 | 앱 1회 $5, 월 1만 건 | 유료지만 가장 오래된 개인 푸시 표준 | Apprise `pover://` 로 흡수 | https://tool.news/tools/pushover/ | 2026-09-06 |
| B | LINE Messaging API | 일본·대만·태국 메신저 봇 | REST, 채널 토큰; `pip line-bot-sdk` | Reply 무제한 무료, Push 는 국가별 월 무료 한도 | 해당국 표준(한국 사용자는 낮음) | `channel_type:"line"` | https://developers.line.biz/en/docs/messaging-api/pricing/ | 2026-09-06 |
| B | PyPI JSON API / npm Registry API | 패키지 메타·최신 버전·검색 | `GET pypi.org/pypi/<pkg>/json`, `registry.npmjs.org/-/v1/search`, 인증 없음 | 무료 | 의존성 조회 유일 공식 통로 | `[self:install_lib]{check:true}` 확장 또는 `[sense:package]{name, registry}` | https://docs.pypi.org/api/json/ | 2026-09-06 |
| B | mDNS/Bonjour — `python-zeroconf` 0.150 | 같은 LAN 의 프린터·HA·Chromecast·이웃 몸 발견 | 멀티캐스트 UDP, 인증 없음; `pip zeroconf` | 무료 | LAN 서비스 발견 유일 표준 | `[sense:net]{op:"discover", service:"_http._tcp"}` (이웃 몸 자동 발견에 직결) | https://github.com/python-zeroconf/python-zeroconf | 2026-09-06 |
| B | WebFinger (RFC 7033) | `user@domain` → 페디버스/ID 프로필 해소 | `GET /.well-known/webfinger?resource=acct:` | 무료 | Mastodon 상호운용 필수; 개인 도메인=신원 | `[sense:entity]{op:"webfinger"}` 또는 Mastodon 낱말 내부 | https://docs.joinmastodon.org/spec/webfinger/ | 2026-09-06 |
| B | WebSub (W3C) | 피드 갱신을 폴링 대신 푸시로 받기 | 허브 구독 HTTP POST + 콜백 | 무료 | RSS 실시간화 유일 표준(Mastodon 허브 구현) | `[self:trigger]{type:"websub", feed}` — sense:feed × since 의 푸시판 | https://github.com/w3c/websub/blob/master/implementation-reports/HUB-mastodon.md | 2026-09-06 |
| B | Standard Webhooks 규격 | 수신 웹훅의 서명·타임스탬프·재시도 검증 | HMAC-SHA256 헤더 규약, 오픈 스펙 | 무료 | 웹훅 공급자들이 수렴 중인 유일 규격 | `[self:trigger]{type:"webhook", verify:"standard"}` 관문 | https://www.standardwebhooks.com/ | 2026-09-06 |
| B | Syncthing 2.1 REST API | 기기 간 P2P 폴더 동기화 상태·이벤트 | `/rest/*`, `X-API-Key` | 무료·오픈 | 클라우드 없는 동기화 표준(폰↔PC) | `[sense:host]{op:"sync_status"}` — phone_sync 의 무선판 후보 | https://docs.syncthing.net/dev/rest.html | 2026-09-06 |
| B | Uptime Kuma 2.5 | 내 서비스(터널·웹앱·포털) 생존 감시+알림 | Socket.io/API, 상태 페이지 | 무료·오픈 | 홈랩 모니터링 1위(2026-08 릴리스) | `[self:webapp]{op:"probe"}` 가 이미 생존 확인 — 겹침 가능, 알림 배선만 차이 | https://github.com/louislam/uptime-kuma/releases | 2026-09-06 |

(표 37행: S 11 · A 16 · B 10)

## 겹침 메모 (기존 어휘와 겹쳐 뺀 것)
- **IMAP/SMTP 일반** — `others:channel_send/read` 의 Gmail 이 이미 IMAP/SMTP 로 구현(`others.yaml` 73·100행). 차이=Gmail 외 계정(iCloud·Naver·Fastmail). `channel_type:"imap"` 한 항목으로 열면 되고 `imap-tools` 1.14(2026-07)가 표준 lib. 새 낱말 아님.
- **RSS/Atom** — `sense:feed` 가 정본. 차이=JSON Feed 1.1(`application/feed+json`)은 feedparser 가 파싱 못 하므로 feed 낱말 안에 분기 한 줄이 필요(채택 낮음, Linodians 인수 2025-10).
- **Nostr** — `others:nostr/feed/publish/channel_*` 다 있음. 제외.
- **Cloudflare Tunnel** — `limbs:cloudflare_api` 가 Tunnel 포함. ngrok 은 무료 티어 악화(아래)라 대체 불요.
- **cron** — `self:schedule`·`self:trigger{schedule}` 가 정본.
- **Webhook 수신** — `self:trigger{type:webhook}` 있음. 차이=Standard Webhooks 서명 검증(표 B 로 남김).
- **Context7 MCP** — `sense:devdocs` 가 이미 Context7. **Playwright MCP** — `limbs:browser` 가 Playwright/Chrome MCP. 둘 다 표에는 MCP 군 안에서만 언급.
- **Cloudflare Workers/Pages 배포** — `engines:web`·`others:showcase` 가 덮음.
- **Google Calendar API** — CalDAV 로 Google 도 닿으므로(앱 비밀번호) 별도 항목 안 둠; Google OAuth 는 민감 스코프 검수가 개인에게 마찰(2026 확인). 
- **Gotify** — ntfy 와 동일 자리(셀프호스팅 푸시), 2026 도 활발(v2.9.1)이나 ntfy 가 우세. Apprise `gotify://` 로 흡수.
- **Huginn** — 2026-08 커밋은 있으나 n8n·Node-RED 가 표준 자리. 위임 낱말의 `to:` 옵션으로 충분.
- **XMPP(slixmpp 1.16)** — 살아 있으나 개인 메신저 표준 자리는 Matrix 로 이동. 겹침.
- **Uptime Kuma** — `self:webapp` 생존 확인과 겹침 가능 — 표에 B 로 두되 "알림 배선만 차이" 표기.

## 죽었거나 유료화된 것 ("쓰지 말 것" 으로 남길 가치)
| 리소스 | 2026-09 상태 | 판정 | 근거 |
|---|---|---|---|
| X(Twitter) API | 무료 티어 폐지, 종량제 기본($0.005/읽기·$0.015/게시), Basic·Pro 도 2026-06/09 강제 이관 | **쓰지 말 것** — Bluesky·Mastodon 으로 | https://postproxy.dev/blog/x-api-pricing-2026/ |
| Reddit API | 무료 100 qpm 남았으나 2025 말부터 신규 앱 등록=수동 승인 티켓; 상업 $12k/월 | 개인 봇 사실상 불가 — RSS(`old.reddit.com/.rss`)로 | https://www.techloy.com/reddit-api-pricing-in-2026-complete-guide-for-developers-and-businesses/ |
| WhatsApp Business API | 개인 계정 API 없음; 건당 과금, 2026-10-01 부터 24h 창 안 서비스 답장도 과금, BSP 마진 2~5배 | **개인 사용 불가** | https://sleekflow.io/blog/whatsapp-business-price |
| 카카오톡 "친구에게 보내기"/알림톡 | 친구 발송은 앱 검수+상대도 앱 동의 필요, 알림톡은 비즈니스 채널·유료 | 나에게 보내기만 쓸 것 | https://developers.kakao.com/docs/latest/ko/kakaotalk-message/common |
| IFTTT 무료 | 애플릿 2개, 단일 액션, 60분 지연, 웹훅 불가 | 죽은 것과 같음 — n8n | https://automationatlas.io/answers/ifttt-pricing-explained-2026/ |
| Zapier 무료 | 월 100 태스크·2단계 한도 | 시험용 이상 불가 — n8n | https://www.activepieces.com/blog/zapier-pricing |
| ngrok 무료 | 2026 초 2시간 세션·1GB/월·랜덤 URL·스플래시 페이지 | Cloudflare Tunnel(이미 어휘)로 | https://pinggy.io/blog/best_ngrok_alternatives/ |
| Telegram 사용자 계정 자동화(Telethon/MTProto) | 라이브러리는 살아 있음(1.44, 2026-06)이나 신규 계정·멤버 추출은 밴 위험 | Bot API 만 쓸 것 | https://github.com/LonamiWebs/Telethon/issues/3861 |
| Slack Incoming Webhook | 동작하나 "legacy custom integration" 표기, 무료 플랜 앱 10개 한도 | 개인용 아님, 필요 시 Apprise 경유 | https://comparetiers.com/blog/slack-free-plan-limitations-2026 |
| JMAP (IMAP 후계) | 표준 살아 있으나 Fastmail·Stalwart·Thunderbird 외 채택 미미 | 2026 엔 IMAP 유지, JMAP 은 관망 | https://datatracker.ietf.org/wg/jmap/history/ |
