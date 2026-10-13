# 폰 미디어 엔진 조달 기록 (2026-10-13)

설계 §9 "Android 라이브러리 조달은 첫 번째 기술 관문" 의 사실 기록. 계약: `docs/MEDIA_SESSION_CONTRACT.md`.

## 라이브러리

| 항목 | 값 |
| --- | --- |
| 좌표 | `io.github.webrtc-sdk:android:144.7559.15` (Maven Central, `app/build.gradle`) |
| 출처 | https://github.com/webrtc-sdk/android — Google 의 중단된 `org.webrtc:google-webrtc` 대신 커뮤니티가 upstream 을 계속 빌드·배포 |
| 라이선스 | BSD-3-Clause (POM `licenses` 확인) |
| AAR 크기 | 48.7 MB (jni 네 ABI 합) |
| ABI (AAR `jni/`) | `armeabi-v7a` 6.8 MB · `arm64-v8a` 12.1 MB · `x86` 12.6 MB · `x86_64` 16.1 MB — `libjingle_peerconnection_so.so` |
| minSdk (AAR 매니페스트) | 21 (앱 minSdk 28, Galaxy J7 2017 = Android 9/28 충족) |
| NDK | 불필요 — 프리빌트 .so. flavor `abiFilters` 가 arm32=armeabi-v7a, arm64=arm64-v8a 만 싣는다 |
| 확인 방법 | 2026-10-13 `curl` 로 POM·AAR 받아 `unzip -l` 과 `javap` 로 API(PeerConnection.restartIce, Camera2Enumerator, JavaAudioDeviceModule.Builder.setAudioAttributes, RTCStatsReport) 실재 확인 |

업데이트 경로: 같은 좌표의 다음 판본(`<milestone>.<branch>.<patch>`)으로 교체 → 두 flavor `assemble` → J7(32비트)·64비트 폰 재검증.
Maven 해석 성공은 통과 조건이 아니다 — 설계 §12 의 실기기 검증 항목은 `MEDIA_ENGINE.md` 아래 "실기기 미검증" 을 본다.

## 폰 쪽 구성 (`app/src/main/java/com/indiebiz/phoneagent/media/`)

- `MediaBridge` — Python(limb_client.py `op: media`) ↔ Kotlin 다리. start/stop/status/capabilities, JSON 만 오간다.
- `MediaSessionService` — camera|microphone|mediaPlayback 유형 FGS. 한 번에 한 세션(device_busy).
- `SessionRunner` — 세션 수명·오디오 포커스·WakeLock·종료 멱등.
- `SignalingClient` — OkHttp WS `/limb/resident/media/<sid>`(LAN 핀 우선), keepalive·세대·재접속.
- `MediaEngine` — WebRTC answerer. 프로필: 32비트 640x480@15, 64비트 1280x720@24. getStats → 계약 quality.
- `ContentPlayer` — purpose=playback/delivery=content 의 MediaPlayer(세션 범위, 메인 루퍼 직렬화, 1초 보고, update 반영).
- `MediaDisplayActivity` — 파일·URL 영상(TextureView)과 실시간 수신 영상(SurfaceViewRenderer), 재생·탐색·볼륨·종료. 표시되지 않은 영상은 재생 성공으로 보고하지 않는다.
- `CctvModeActivity`/`CctvState` — 사용자가 켜 두는 카메라 대기 모드(Android 10+ while-in-use 요건).

## 실기기 미검증 (adb 기기 0대 — 2026-10-13 시점)

설계 §12 중 컴파일·단위시험으로는 닫히지 않는 항목: J7/64비트 설치·라이브러리 로딩·카메라 인코딩·PC 수신·음성 왕복,
화면 꺼짐·Doze·절전·재부팅·자원 충돌, 1시간 통화·8시간 CCTV, LAN/휴대망/TURN/UDP 차단/망 변경, A/V 동기·에코.
