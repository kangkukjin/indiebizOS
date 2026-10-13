# 미디어 세션 — 통화·확장 장치 카메라/마이크/스피커·재생 전달 (2026-10-13)

> 설계 정본 `docs/MEDIA_COMMUNICATION_DESIGN_2026_10_13.md`, 와이어 계약 `docs/MEDIA_SESSION_CONTRACT.md`.
> 새 낱말은 없다. 제어는 `[self:script]{op:"run", id:"미디어세션", args:{...}}` 한 통로, 화면은 조종실(손발 목록)·연락처 버튼이 연다.

## 두 가지 허가, 한 가지 엔진

| | 일반 통화 (`kind:"call"`) | 확장관계 (`kind:"extension"`) |
|---|---|---|
| 허가 근거 | 상대의 **수락**(`accepted_call`) — 벨이 울리고 상대가 받아야 센서가 켜진다 | **등록 자격**(`extension_grant`) — 헬퍼 설치 PC·USB 로 각인한 폰만. 벨 없음 |
| 대상 | 주소록의 nostr 연락처 이름 또는 npub | 손발 이름(`[self:limb]{op:"list"}` 의 alias) |
| 목적 | `voice_call` `video_call` | `camera`(장치 카메라→중앙 화면) `microphone` `speaker`(중앙 재생음→장치) `playback`(파일·주소 재생 전달) |
| 할 수 없는 것 | 통화 자격으로 명령·파일·등록 불가 | 통화 화면·네트워크 초대로 확장관계를 만들 수 없음 |

세션 한 행 = `session_id`·`state`·`tracks`·`path`(direct|relay)·`quality`·`error`. 상태 흐름: 통화 `inviting→ringing→accepted→connecting→active→ended`,
확장 `authorized→connecting→active→ended`(권한이 필요하면 `needs_local_action` 에서 멈춘다 — 폰에서 '카메라 대기 모드' 같은 로컬 행동 안내).

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
· `relation_revoked`(관계 중지·해제·폐기) · `needs_local_action`(장치에서 권한·대기 모드) · `content_unavailable`(파일 없음·주소 불가) ·
`signaling_unavailable`(IndieNet 신원 없음 또는 초대 전송 실패) · `invite_expired`/`rejected`/`busy`(상대 쪽 결과) · `connectivity_failed`(임대·복구 시간 만료).
`health` 가 `turn.configured:false` 면 외부망 통화는 직접 연결만 시도한다 — `data/media_policy.yaml` 에 TURN 주소, `.env` 에 `MEDIA_TURN_SECRET`.

## 운영 데이터(코드가 아니라 파일)

- `data/media_policy.yaml` — 시그널링 경로(auto|nostr|relay)·ICE/TURN·품질 프로필(phone32/phone64/helper)·한도.
- `data/session_lease_policy.yaml` — 임대(20초)·생존 확인(5초)·복구(30초)·초대(45초). 화면 공유·터미널과 같은 정책 파일.
- 이력은 `data/media/state.db`(시작·종료·경로·품질·오류만). 원본 영상·음성·토큰·SDP 는 저장하지 않는다.
