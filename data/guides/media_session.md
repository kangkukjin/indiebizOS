# 미디어 세션 — 통화·확장 장치 카메라/마이크/스피커·재생 전달 (2026-10-13)

> 설계 정본 `docs/MEDIA_COMMUNICATION_DESIGN_2026_10_13.md`, 와이어 계약 `docs/MEDIA_SESSION_CONTRACT.md`.
> 새 낱말은 없다. 제어는 `[self:script]{op:"run", id:"미디어세션", args:{...}}` 한 통로, 일반 통화는 메신저 이웃 목록, 확장 미디어는 조종실 손발 목록에서 연다.

## 두 가지 허가, 한 가지 엔진

| | 일반 통화 (`kind:"call"`) | 확장관계 (`kind:"extension"`) |
|---|---|---|
| 허가 근거 | 상대의 **수락**(`accepted_call`) — 벨이 울리고 상대가 받아야 센서가 켜진다 | **등록 자격**(`extension_grant`) — 헬퍼 설치 PC·USB 로 각인한 폰만. 벨 없음 |
| 대상 | 주소록의 nostr 연락처 이름 또는 npub | 손발 이름(`[self:limb]{op:"list"}` 의 alias) |
| 목적 | `voice_call` `video_call` | `camera`(장치 카메라→중앙 화면) `microphone` `speaker`(중앙 재생음 또는 마이크→장치) `playback`(파일·주소 재생 전달) |
| 할 수 없는 것 | 통화 자격으로 명령·파일·등록 불가 | 통화 화면·네트워크 초대로 확장관계를 만들 수 없음 |

세션 한 행 = `session_id`·`state`·`tracks`·`path`(direct|relay)·`quality`·`error`. 상태 흐름: 통화 `inviting→ringing→accepted→connecting→active→ended`,
확장 `authorized→connecting→active→ended`(최초 OS 권한이 빠졌거나 화면 준비가 거절되면 `needs_local_action`으로 원인을 보고한다).

## 자주 쓰는 모양

```
[self:script]{op:"run", id:"미디어세션", args:{op:"capabilities", target:"삼성1"}}          # 장치가 무엇을 지원하나(camera/microphone/speaker/playback)
$s = [self:script]{op:"run", id:"미디어세션", args:{op:"create", kind:"extension", purpose:"camera", target:"삼성1", want_mic:true}}
[self:script]{op:"run", id:"미디어세션", args:{op:"status", session_id:$s.items[0].session_id}}
[self:script]{op:"run", id:"미디어세션", args:{op:"end", session_id:$s.items[0].session_id, reason:"done"}}
[self:script]{op:"run", id:"미디어세션", args:{op:"create", kind:"extension", purpose:"playback", target:"거실PC", content:{path:"~/Music/a.mp3", position_s:0}}}
[self:script]{op:"run", id:"미디어세션", args:{op:"create", kind:"call", purpose:"voice_call", target:"친구"}}   # 상대가 받을 때까지 inviting
[self:script]{op:"run", id:"미디어세션", args:{op:"list"}} · {op:"history", limit:20} · {op:"health"}
```

- `create` 는 `request_id` 로 멱등(같은 내용=같은 세션, 다른 내용=`request_id_conflict`).
- 재생 전달은 **대상이 재생을 보고한 뒤**(`content.playing:true`) 원본을 멈춘다. 준비 실패면 원본 유지. `update` 로 `{content:{paused, position_s, volume}}`.
- 통화 창은 사람이 조작한다(수락·음소거·카메라·종료). AI 는 의도(걸기·끊기·상태)만 표현한다 — 영상·음성 바이트는 IBL 결과에 오지 않는다.

## 실패 코드와 대처

`device_offline`(장치가 90초 안에 접속 없음) · `device_busy`(그 장치에 열린 세션 — 먼저 end) · `unsupported_track`(설치본·헬퍼 교체 필요, capabilities 로 확인)
· `relation_revoked`(관계 중지·해제·폐기) · `needs_local_action`(장치 최초 권한 설정 또는 OS 실행 거절) · `content_unavailable`(파일 없음·주소 불가) ·
`signaling_unavailable`(IndieNet 신원 없음 또는 초대 전송 실패) · `invite_expired`/`rejected`/`busy`(상대 쪽 결과) · `connectivity_failed`(임대·복구 시간 만료).
`health` 가 `turn.configured:false` 면 외부망 통화는 직접 연결만 시도한다 — `data/media_policy.yaml` 에 TURN 주소, `.env` 에 `MEDIA_TURN_SECRET`.

Android 폰은 카메라 권한과 지금 카메라를 시작할 준비 상태를 구분한다. 현재 앱은 Android 9에서는
백그라운드 시작을 허용한다. Android 10 이상에서는 USB 등록 시 **다른 앱 위에 표시**를
허용한 폰에 한해, 등록된 중앙 PC의 카메라·마이크 요청으로 전용 연결 화면을 직접 연다.
잠긴 화면에서도 작동하며 잠금 자체는 해제하지 않는다. 연결 중 화면을 어둡게 유지하고,
종료하거나 폰에서 연결 화면을 닫으면 센서와 화면을 정리한다. `remote_sensor_start`는 이
현재 원격 화면 시작 가능 여부·등록 상태이고, `camera_ready`는 지금 앱의 가시성·센서 권한 상태다.
새 설치는 `setup_phone.sh --limb 이름`, 기존 폰 업데이트는 `--remote-media` 옵션을 쓴다.
등록된 폰의 앱 시작 화면에서도 최초 카메라·마이크 권한과 자동 화면 열기 권한을 설정한다.
권한을 갖추면 중앙 요청이 화면 준비→서비스 시작을 이어서 수행한다. 런처에 대기 버튼은 없다.
폰이 시그널링 연결 전에 시작을 거절해도 중앙은 작업 결과를 읽어 `needs_local_action`과
실제 안내를 표시한다. 누락된 최초 권한을 설정한 뒤 중앙에서 다시 요청한다.
접수 성공만으로 영상 연결을 성공 처리하지 않으며, 안내 뒤 임대가 끝나도 거절 원인을 보존한다.

## 운영 데이터(코드가 아니라 파일)

- `data/media_policy.yaml` — 시그널링 경로(auto|nostr|relay)·ICE/TURN·품질 프로필(phone32/phone64/helper)·한도.
- `data/session_lease_policy.yaml` — 임대(20초)·생존 확인(5초)·복구(30초)·초대(45초). 화면 공유·터미널과 같은 정책 파일.
- 이력은 `data/media/state.db`(시작·종료·경로·품질·오류만). 원본 영상·음성·토큰·SDP 는 저장하지 않는다.

## 폰의 일반 통화와 이어 듣기

폰과 PC 모두 **메신저 이웃 목록**에서 저장된 Nostr 연락처가 있는 이웃에게만
**음성 통화·영상 통화** 버튼이 나타납니다. 버튼은 해당 연락처를 자동으로 사용하며
통화 주소 입력·복사 화면은 없습니다. Nostr 연락처가 없는 이웃에게는 버튼을 표시하지 않습니다.
공유창고 이웃 탭과 폰 런처의 별도 통화 버튼은 사용하지 않습니다.
폰에서는 선택한 이웃과 통화 종류를 네이티브 통화 화면으로 넘겨 권한 확인 후 발신합니다.
수신은 알림을 눌러 수락하거나 거절합니다. 수락 전에는 카메라/마이크를 열지 않으며,
일반 통화는 USB 확장관계 등록과 무관합니다. 진행 중인 통화는 알림에서 다시 열거나
종료할 수 있습니다. 통화 중에는 기존 확장 카메라/마이크 세션을 동시에 시작할 수 없습니다.

앱모드 음악·영상 플레이어의 **다른 장치에서 이어 듣기**는 재생 위치와 볼륨을 함께 보냅니다.
장치가 실제 재생을 확인하면 원본을 자동으로 멈추며, 실패·취소 시에는 원본을 유지합니다.
로컬 URL 전달에는 허브 공개 주소가 필요하고, 인증된 원본 서버의 접근이 거절되면 파일 경로
전달을 사용합니다. blob/DRM 소스를 일반 파일 URL로 바꿀 수 있다고 가정하지 않습니다.

## TURN 운영 준비

Linux 서버의 직접 DNS 이름, 공인 IP, TLS 인증서와 확인한 coturn 이미지 digest를 준비한 뒤
저장소의 `.venv/bin/python3 scripts/media_turn_setup.py --help`를 확인합니다.
`--host`, `--public-ip`, `--image coturn/coturn@sha256:...`로 배포 파일을 생성하고,
`--apply`를 함께 주면 이 허브의 정책과 루트 `.env`도 설정합니다. 출력 경로인
`data/media_turn_private/`에는 비밀이 있으므로 Git이나 채팅에 올리지 않습니다.
서버에서 인증서 두 파일을 `certs/`에 배치하고 `docker compose up -d`로 시작합니다.
방화벽은 3478 UDP/TCP, 5349 TCP, 49160–49260 UDP를 허용합니다. HTTP 터널 주소는
TURN 서버 주소로 사용할 수 없습니다. 인증서 갱신 후 컨테이너를 재시작합니다.

허브 재시작 후 `/media/health`와 실제 강제 TURN 통화를 모두 확인해야 합니다.
`configured=true`만으로 휴대망·UDP 차단 환경의 영상 출력까지 검증된 것은 아닙니다.

## 폰에서 중앙PC 영상 보기

새 APK와 최초 권한 설정을 마친 폰은 중앙 요청으로 영상 화면을 자동으로 엽니다. 중앙PC의 손발 목록에서:

- **이 장치에서 재생**: 중앙PC의 동영상 파일 경로나 폰이 접근 가능한 URL을 전달합니다.
  폰이 직접 디코딩하고 화면에 표시하며, 중앙과 폰 양쪽에서 일시정지·위치·볼륨·종료를 조작합니다.
- **영상 보내기**: 중앙PC에서 고른 동영상의 영상·소리를 WebRTC로 전송합니다.
  `video_receive`를 신고한 새 설치본에만 버튼이 표시됩니다. 소스가 재생된 뒤 보내기 버튼을 누릅니다.
  소리 없는 동영상도 전송할 수 있습니다. 이 기능은 PC 전체 화면 공유가 아닙니다.

IBL 제어는 기존 미디어세션 스크립트입니다. 파일 전달은 `purpose:"playback", content:{path:"…"}`,
실시간 전송은 `purpose:"playback", delivery:"realtime"`으로 만들고 열린 창에서 소스를 선택합니다.

중앙 요청은 등록 자격을 검증한 뒤 세션 전용 출력 화면을 열고 실제 가시성·출력 표면을
확인한 뒤 서비스를 시작합니다. 폰에서 미리 화면을 열거나 수신 대기를 누를 필요가 없습니다.
중앙에서 종료하면 출력 화면도 닫힙니다. 폰에서 화면을 닫거나 다른 화면으로 나가면 해당
영상·콘텐츠 세션을 종료하며, 닫힌 화면을 늦게 도착한 요청이 되살리지 않습니다.
영상은 첫 표시 프레임을 확인해야 `playing:true`가 되므로 접수만으로 원본을 멈추지 않습니다.
화면 준비가 실패하면 중앙에 원인을 보고합니다. 잠금 화면 위에 표시하되 잠금은 해제하지 않습니다.

코덱·컨테이너는 폰의 MediaPlayer/WebRTC가 지원해야 합니다. URL을 브라우저에서 실시간
전송할 때는 원본 서버의 CORS 허용이 필요합니다. 접근 불가·DRM 자료는 자동 변환하지 않습니다.

폰 런처에는 별도 화면 업데이트 버튼도 없습니다. APK에 설정된 신뢰 가능한 서명 피드를
주기적으로 확인해 새 UI를 자동 적용하며, 검증·상태 인계에 실패하면 이전 화면을 유지합니다.
피드가 없는 APK는 내장 화면을 사용하며, 코드·엔진 변경은 중앙의 APK 업데이트 경로로 전달합니다.
이 변경의 빌드·실기기 인수 범위는 `docs/PHONE_CENTRAL_PREPARATION_2026_10_17.md`를 따릅니다.


## 이 PC의 마이크 소리 보내기

손발 목록에서 대상 PC의 **재생음 보내기 → 마이크 입력 → 마이크 소리 보내기**를 누릅니다.
처음에는 macOS 마이크 접근을 허용해야 합니다. 보내는 소리 크기와 마이크 음소거·장치 선택을
확인할 수 있으며 **종료**하거나 창을 닫으면 마이크를 해제합니다. 파일·주소 재생도 그대로
선택할 수 있습니다. 전송 중 다른 입력 종류로 바꾸려면 종료한 뒤 다시 엽니다.
대상은 스피커 수신만 지원하면 되므로 카메라와 마이크가 없어도 됩니다.
