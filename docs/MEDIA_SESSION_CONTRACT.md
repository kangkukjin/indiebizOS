# 미디어 세션 통신 계약 (구현 계약, protocol_version 1)

설계 정본: docs/MEDIA_COMMUNICATION_DESIGN_2026_10_13.md. 이 문서는 그 설계를 코드가 따르는 **와이어 계약**이다.
백엔드(허브)·프런트(Electron/브라우저 엔진)·폰(Kotlin 엔진)·헬퍼(Go 엔진)가 전부 이 모양을 쓴다.

## 1. 세션 객체 (허브 API 가 돌려주는 모양)

```json
{
  "session_id": "<hex32>", "protocol_version": 1,
  "kind": "call" | "extension",
  "purpose": "voice_call" | "video_call" | "camera" | "microphone" | "speaker" | "playback",
  "authorization_basis": "accepted_call" | "extension_grant",
  "participants": [
    {"role": "caller"|"callee"|"hub"|"device", "user": {"id": "<npub|self>", "name": "..."},
     "device": {"id": "<device_id|local>", "name": "...", "body": "pc"|"phone"|"helper"}}
  ],
  "tracks": [{"id": "a0", "kind": "audio"|"video", "source": "mic"|"camera"|"playback"|"screen",
              "from": "<role>", "to": "<role>", "state": "requested"|"active"|"muted"|"rejected"|"ended"}],
  "delivery": "realtime" | "content",
  "consent_scope": {"inputs": ["mic","camera"], "outputs": ["speaker","display"], "record": false},
  "relation_generation": "<등록 세대>" | null,
  "state": "inviting"|"ringing"|"accepted"|"authorized"|"connecting"|"active"|"reconnecting"|"needs_local_action"|"ended",
  "revision": 3, "generation": 0,
  "lease": {"lease_s": 20, "keepalive_s": 5, "reconnect_s": 30, "remaining_s": 17.2},
  "expires_at": 1791877000.0,
  "ice_servers": [{"urls": ["stun:..."]}, {"urls": ["turn:..."], "username": "...", "credential": "..."}],
  "signaling": {"route": "local"|"extension"|"nostr"|"relay", "relay": "wss://.../media/relay/<room>"|null},
  "path": "direct"|"relay"|null,
  "quality": {"rtt_ms": 0, "loss": 0, "jitter_ms": 0, "bitrate_kbps": 0, "fps": 0, "width": 0, "height": 0, "dropped": 0},
  "content": {"ref": "<hex>", "url": "/media/content/<ref>", "position_s": 0, "paused": false, "volume": 80} | null,
  "needs_local_action": {"code": "...", "message": "..."} | null,
  "error": {"code": "...", "message": "..."} | null,
  "created_at": 0.0, "ended_at": 0.0, "end_reason": ""
}
```

`session_id` 는 인증 자격이 아니다. 참가자는 **참가 자격(grant)** 으로 들어온다(§4).

실패 코드(공통): `permission_required`, `needs_local_action`, `device_offline`, `device_busy`, `unsupported_track`,
`relation_revoked`, `connectivity_failed`, `content_unavailable`, `invite_expired`, `rejected`, `busy`, `request_id_conflict`,
`stale_revision`, `session_ended`, `signaling_unavailable`.

## 2. 허브 서비스 연산 (backend/services/media_sessions.py, HTTP = backend/surface/api_media.py)

| 연산 | HTTP | 입력 | 비고 |
| --- | --- | --- | --- |
| capabilities | GET /media/capabilities?target= | target(장치 id/이름, 생략=이 몸) | 장치가 신고한 트랙·엔진·상태 |
| create | POST /media/sessions | kind, purpose, target, tracks, delivery, request_id, content | request_id 멱등(같은 내용=같은 세션, 다른 내용=request_id_conflict) |
| accept | POST /media/sessions/{id}/accept | device(수락 장치) | 첫 수락이 원자적으로 이김, 나머지 초대 닫힘 |
| reject | POST /media/sessions/{id}/reject | reason | |
| signal | POST /media/sessions/{id}/signal 또는 WS 프레임 | 시그널 메시지(§3) | |
| update | POST /media/sessions/{id}/update | expected_revision, changes{mute, camera, audio_source, content{paused,position_s,volume}} | 낡은 판본=stale_revision |
| status | GET /media/sessions/{id} | | |
| list | GET /media/sessions?active=1 | | |
| end | POST /media/sessions/{id}/end | reason | 멱등(두 번째도 성공) |
| ice | GET /media/ice-config | | 단기 TURN 자격(정책 데이터) |
| health | GET /media/health | | 시그널링·TURN·수신 경로 진단 |

응답 봉투: 성공 `{"success": true, "session": {...}}`, 실패 `{"success": false, "error": {"code","message"}}` (HTTP 200·400 모두 같은 모양).
IBL 로 묶을 때는 `{items:[session]}`.

## 3. 시그널 메시지 (전송 방식 무관)

```json
{"v": 1, "session_id": "<hex32>", "msg_id": "<hex16>", "from": "<role>", "to": "<role>",
 "generation": 0, "seq": 7, "expires_at": 1791877000.0,
 "type": "invite"|"accept"|"reject"|"offer"|"answer"|"candidate"|"candidates_done"|"keepalive"|"ack"|"state"|"renegotiate"|"update"|"end",
 "payload": {...}, "mac": "<hmac-sha256 hex>"}
```

- `generation` = 협상 세대(재협상·재접속마다 +1), `seq` = 그 세대 안의 증가 순번. 낮은 세대·지난 순번·만료는 버린다.
- `candidate` 가 `offer`/`answer` 보다 먼저 오면 같은 세대 안에서만 버퍼링한다.
- `mac` = HMAC-SHA256(session_secret, canonical_json(메시지에서 mac 제외)). 릴레이가 바꾸면 검증 실패.
- `offer`/`answer` payload: `{"sdp": "...", "fingerprint": "sha-256 AB:CD:..."}` — fingerprint 는 SDP 에서 뽑아 봉투에도 적고, 수신 측은 둘이 같은지 확인한다.
- `invite` payload: `{"purpose","tracks","from_user","from_device","offer"?(발신자 SDP 동봉 가능),"signaling":{"relay"?},"secret":"<session_secret>","ice_servers"}`
- `accept` payload: `{"device","answer"?}` / `reject` payload: `{"reason"}` / `end` payload: `{"reason"}`
- `state` payload: `{"state","path","quality","code"?,"message"?}` (장치→허브 상태 보고; `state:"needs_local_action"` 이면 code·message 동반).
  재생 상태는 `content:{playing,position_s,paused,volume,duration_s,ended}` 또는 같은 키를 최상위에 실어도 된다. `needs_local_action` code 예:
  `permission_required` `camera_unavailable` `ffmpeg_missing` `camera_missing` `microphone_missing` `display_missing` `capture_failed` `engine_unsupported`.
- `keepalive` — 세 가지 자리:
  - 확장 장치 → 허브(장치 WS): payload `{}`. 허브는 같은 세대·증가 순번일 때만 임대를 갱신한다.
  - 허브 → 확장 장치(장치 WS): 허브가 `keepalive_s` 마다 보낸다(`seq` 증가). 장치는 이것으로 자기 임대를 갱신한다.
  - 통화의 브라우저 → 자기 허브(로컬 WS): payload `{"peer_alive": true|false}` — 브라우저가 DTLS 로 인증된 WebRTC DataChannel
    (레이블 `indiebiz-keepalive`, `keepalive_s` 마다 ping/pong) 로 상대 생존을 확인했을 때만 `true`. 허브는 `true` 일 때만 임대를 갱신한다.
    통화 keepalive 는 Nostr DM 으로 나가지 않는다(릴레이 낭비·지연). 미디어 패킷 도착은 어느 경우에도 갱신 사유가 아니다.
  - `connecting` 상태는 `lease_s + reconnect_s` 안에 `active` 가 돼야 한다(초과=`connectivity_failed`).

## 4. 참가 자격(grant)

세션마다 참가 장치별 토큰 `grant` = `{"session_id","role","device","tracks","expires_at","token"}`.
`token` = HMAC-SHA256(hub_secret, session_id|role|device|expires_at) hex. 확장관계 봉투와 초대에 실려 간다.
- 확장관계 장치: 봉투(`op: media_session`)에 grant 가 들어오고, WS `/limb/resident/media/{sid}` 첫 프레임이
  `{"key","installation_id","grant"}` — 등록 자격 **과** 세션 grant 둘 다 맞아야 붙는다.
  확장 경로의 프레임에는 `mac` 이 없다(봉투에 세션 비밀을 싣지 않는다) — 인증은 등록 자격+grant+TLS/LAN 핀 인증서다.
  붙은 순서: 장치 auth → 허브 `{"type":"ready","session_id","lease"}` → 장치 `{"type":"ready","capabilities":{...}}`(허브는 세션 `device_caps` 에 기록).
  협상 `generation` 은 0 에서 시작해 허브 offer 의 세대를 따른다. 장치 WS 재접속은 세대를 올리지 않는다(WebRTC 다리 유지); 새 세대는 허브의 재-offer 가 연다.
  콘텐츠 `GET /media/content/{ref}?token=` 의 token 은 허브가 미리 서명한 콘텐츠 토큰 **또는** 장치의 grant.token 둘 다 통한다.
- 일반 통화 상대 허브: invite 에 동봉된 `secret` 으로 이후 메시지를 서명한다(§3 mac).
- 재접속은 새 세대·새 keepalive 순번으로 하고, 종료된 세션의 grant 는 거절(`session_ended`).

## 5. 전송 경로

| 경로 | 참가자 | 수단 |
| --- | --- | --- |
| local | 이 몸의 브라우저 엔진 ↔ 허브 | WS `/media/sessions/{sid}/ws` (런처 세션 인증) — 양방향 JSON 시그널 프레임 + `{"type":"session","session":{...}}` 상태 푸시 |
| extension | 확장 장치(헬퍼/폰) ↔ 허브 | 봉투 `op: media_session` 로 시작, 이후 WS `/limb/resident/media/{sid}` (limb 인증 + grant) |
| nostr | 상대 허브 ↔ 이 허브 | NIP-17 DM, rumor 태그 `["indiebiz-call","1"]`, content = 시그널 메시지 JSON. 채팅·AI 자동응답·자연어 실행으로 가지 않는다 |
| relay | 상대 브라우저/허브 ↔ 이 허브의 공개 주소 | WS `/media/relay/{room}?token=` — 메시지는 §3 mac 으로 서명, 릴레이는 중계만 |

일반 통화 기본: invite(+offer)·accept(+answer)·reject·end 는 **항상 nostr**. offer/answer/candidate/keepalive 는 정책
`signaling.route` 가 `auto` 면 relay 가 있을 때 relay, 없으면 nostr(이때 ICE 는 비-trickle: gathering 완료 후 완전한 SDP 한 번).

## 6. 확장관계 봉투

허브 → 장치: `{"op":"media_session","session_id","grant","purpose","tracks","ice_servers","lease":{...},"quality_profile":{...},"delivery","camera"?:"front"|"back","stream":{"url":"wss://.../limb/resident/media/<sid>","lan":{"urls":[...],"sha256":"..."}},"content"?:{...},"timeout":86400}`
폰(adapter indiebiz-v1)은 같은 내용을 `{"op":"media","action":"start","session":{...위 칸...}}` 로 받는다.
장치 WS 에서 허브가 보내는 비-시그널 프레임: `{"type":"ready","session_id","lease"}`(붙은 직후), `{"type":"rejected","reason","msg_id"}`(프레임 거절),
`{"type":"error","error":{"code","message"}}`(붙기 실패: `invalid_registration`·`permission_required`·`device_busy`·`session_ended` → 닫힘; `session_ended` 면 재접속하지 않는다), `{"type":"heartbeat"}`.
허브 → 장치 `update` payload: `{"mute"?:bool,"camera"?:bool,"audio_source"?:"mic"|"playback","content"?:{paused,position_s,volume},"quality"?:{width,height,fps}}`. 장치 → 허브 `renegotiate` payload `{"reason","ice_restart":true}` 는 허브가 로컬 엔진으로 그대로 넘긴다.
장치는 WS 로 붙어 `{"type":"ready","capabilities":{...}}` 를 보내고, 허브가 `offer`(장치가 송신자일 때는 허브가 `offer` 를 보내고 장치가 `answer`) — 방향: **허브(브라우저 엔진)가 항상 offerer**, 장치는 answerer. 장치는 `state` 로 `needs_local_action`/`active`/`quality` 를 보고한다.
종료: 허브 `end` 프레임, 장치 로컬 중지(`end` 프레임 + 보고), 등록 pause/revoke/remove, 임대 만료 — 전부 캡처·전송 해제.

## 7. 콘텐츠 전달

`create(purpose:"playback", delivery:"content", content:{path|url, position_s, volume})` → 허브가 세션 소유 참조 `ref` 를 발급.
- 로컬 파일: `GET /media/content/{ref}?token=` (Range 지원, 세션 grant 토큰, 세션 종료 시 무효). 전체 경로는 노출하지 않는다.
  허브에 공개 주소(relay_base/face public_base)가 없으면 `content.url` 은 `/media/content/…` 상대 경로다 — 장치는 자기 허브 base(헬퍼 cfg.base, 폰 limb_client hub)에 붙여 쓴다.
- 주소: 대상이 접근 가능한지 허브가 HEAD 로 확인 못 하면 그대로 전달하되 실패는 `content_unavailable`.
- 재생 이동: 대상 `state{playing:true}` 확인 전에는 원본을 멈추지 않는다(원본 정지는 UI 의 별도 조작).

### 7.1 폰의 영상 출력과 실시간 재생

`playback`은 `delivery:"content"` 외에 `delivery:"realtime"`도 받습니다. 실시간은
`video_receive:true` 장치만 허용하며 기본 트랙은 `hub→device`, `source:"playback"`인
video와 audio입니다. 반대 방향이나 센서 소스로 바꾼 트랙은 거절합니다. 콘텐츠 전달에는
`content.path|url`이 필요하고, 실시간 소스는 중앙 통화 창의 재생 요소가 제공합니다.

폰은 `video_receive`와 `video_playback` 능력을 신고합니다. 미디어 화면은 등록 권한을
바꾸지 않으며 카메라·마이크를 열지 않습니다. 콘텐츠의 실제 비디오 트랙을 확인해 영상이면
표시 Surface를 기다립니다. `content` 보고에는 `has_video, video_visible, needs_display,
width, height`가 추가됩니다. 표시 전에는 `playing:false`; 미표시는
`state:"needs_local_action", needs_local_action:{code:"display_required", message:…}`입니다.
첫 표시 프레임 이후 재생 성공을 보고합니다. 실시간 영상도 장치의 표시 보고가 성공을 결정하며
중앙 송신 엔진의 `active`만으로 대체하지 않습니다. 화면 제거 시 영상은 표시 대기로 돌아가고,
콘텐츠 동영상은 위치를 보존하여 멈춥니다. 오디오 전용 콘텐츠는 계속 재생합니다.

## 8. 정책 데이터

- `data/session_lease_policy.yaml` — 임대 프로필(screen/terminal/media).
- `data/media_policy.yaml` — ice_servers(STUN/TURN, TURN 은 `secret_env` 로 단기 자격), signaling(route auto|nostr|relay, relay_base), 품질 프로필(장치 종류별 해상도·fps·bitrate 상한), 수신 알림.
- TURN 비밀은 `.env`(`MEDIA_TURN_SECRET`)에. 코드에 세계의 명사(주소·주체) 고정 금지.

### 구현 보강: 로컬 투영과 인증 경계

- 공개 세션의 `local_role`은 필수이며, `pending_offer`는 `signaling` 안이 아닌 최상위입니다.
  수신 화면이 늦게 붙어도 마지막 offer를 읽을 수 있습니다.
- `/media/events` WS는 로컬 통화 API와 같은 사용자 인증을 사용하고
  `{type:"media_event",event,session}`을 전달합니다. 첫 연결에서는 활성 세션 snapshot을 보냅니다.
- 확장 장치 WS는 URL의 sid·인증된 device_id·grant를 프레임의 세션과 결속합니다.
  일반 통화의 원격 `state`는 로컬 수락 또는 센서 활성화의 근거가 아닙니다.
- `seq=0`은 서버가 생성한 순서 독립 제어 프레임입니다. 중복·세대·만료 검사는 그대로 적용하고,
  양수 seq의 최댓값을 0으로 되돌리지 않습니다. 브라우저·장치의 순번은 양수로 증가합니다.
- `content.playing`은 대상 플레이어의 재생 보고입니다. 현재 원본 플레이어를 붙잡고 있는
  호출자가 그 확인 뒤에 원본을 정지합니다. 일반 경로/URL 재생 요청 자체는 원본을 정지시키지 않습니다.


### 스피커 전송의 로컬 입력 선택 (2026-10-14)

`purpose:"speaker"`의 허브는 `update`에 `audio_source:"mic"|"playback"`을 보낼 수 있다.
허브→장치 오디오 트랙의 source와 consent_scope를 함께 갱신하며 방향·트랙 ID는 유지한다.
수신 장치는 같은 오디오 수신 경로를 사용하고 카메라·마이크 능력을 요구하지 않는다.
이 갱신 자체는 센서를 열지 않는다. 송신 창에서 사람이 보내기를 누른 뒤 OS 권한을 받아
입력을 열며, 종료·창 닫기 뒤 도착한 캡처 결과도 즉시 정리한다.
