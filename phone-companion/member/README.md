# Android 회원 앱

`member`는 기존 `:app`과 설치 ID가 다른 얇은 앱이다. Chaquopy, Python, 온디바이스 Gemini,
BaseBundle을 연결하지 않는다. 접근성 서비스 원본만 빌드 시 기존 앱에서 복사한다.
채팅 HTML과 Markdown 렌더러는 공통 소스에서 PC helper와 함께 빌드한다.

```sh
cd phone-companion
./gradlew -PmemberOnly :member:assembleMemberDebug :member:lintMemberDebug
```

APK: `member/build/outputs/apk/member/debug/member-member-debug.apk`.
`memberOnly`는 기존 `:app`의 Python 번들 구성까지 제외한다. 기존 폰 네이티브 빌드는 그대로다.

앱 첫 화면에 HTTPS 허브와 회원 키를 입력한다. 키는 Android Keystore AES-GCM으로 암호화하고
백업을 끈다. 앱 알림에서 연결을 중단할 수 있다. 파일 가져오기는 Android 문서 선택기를 사용한다.
회원 봉투의 파일 경로는 앱의 member/files 안으로 제한한다. ZIP 내보내기는 문서 저장 선택기로 옮긴다. 변환된 문서도 **파일 내보내기** 버튼으로 선택해 원하는 저장소에 옮긴다.

로컬 기능: SQLite 대화·기억·작업 원장, 4상태 멱등, 승인 판, read/write/list/mkdir/file_move,
MediaPlayer play/stop/status/volume, 위치 1회 측정, accelerometer 내부 봉투,
공통 접근성 서비스 snapshot/tap/type/swipe/key/long_press/open_app.
주인이 radio/android 묶음을 공개하면 limbs:radio·sense:here·limbs:android가 자신의 폰으로 연결된다.
위치는 화면의 **위치 허용** 버튼에서 OS 권한을 먼저 허용해야 한다. 접근성도 직접 설정에서 켠다.
문서는 확장자를 유지해 최대 32MB까지 가져오며, 허브 임시 변환 후 파일 쓰기 승인으로 결과를 받는다.
폰 회원 모드에서 Python/Bash/Node 실행은 거절한다.

실기 검증은 아직 남아 있다: USB 연결 후 설치·첫 연결·저장소·알림 종료·스피커·센서·접근성 조작,
강제 종료 중 작업 상태 복구. 에뮬레이터/실기 없는 APK 빌드와 lint 통과를 이 검증의 대체로 보지 않는다.


회원 승인 화면은 접속한 허브에서 받아 실행하지 않는다. scripts/build_member_shell.py가 공통 member_shell/launcher_app_common을
PC 바이너리와 APK의 정적 자산으로 파생한다. /m/app은 별도 웹 폴백이다. `build_member_shell.py --check`로 번들 드리프트를 검사한다.

## 화면 전용 업데이트

두 Android 앱은 `shared/src/main/java/com/indiebiz/ui`의 동일 검증기·설치기를 사용한다.
첫 지원 APK를 빌드할 때 공개키와 기기별 HTTPS 피드를 설정한다.

- `INDIEBIZ_UI_PUBLIC_KEY`: 저장소 밖 Ed25519 PEM **공개키** 파일.
- `INDIEBIZ_MEMBER_UI_FEED`: 회원 앱의 `current.json`.
- `INDIEBIZ_PHONE_UI_FEED`: 주인 폰 앱의 `current.json`.

미설정 개발 APK는 내장 화면만 사용한다. 임시 키를 운영 신뢰로 쓰지 않는다.
`python3 scripts/build_surfaces.py`의 `display/member/display.json`, `display/phone/display.json`을
각 피드에 `publish-runtime.cjs --kind ui --platform android --arch all`로 서명한다.
발행 명령은 위 회원 데스크톱 README와 같으며 `--source`에 해당 표시 디렉터리를 준다.
운영 업로드는 자산 먼저, current.json 마지막 순서다.

사용자는 앱의 **화면 업데이트** 버튼에서 확인한 판본의 설치를 선택한다. 확인 전에는
매니페스트만 조회한다. 서명·만료·origin·지문·surface·shell 3/protocol 2/state 1·host를
검사하고 `filesDir/ui-releases/<sequence>`에 불변 자산을 보관한다. `AtomicFile` 활성 기록은
렌더러 응답 뒤 확정한다. 미확정 종료·실패는 이전 화면을 유지하고 APK 기본 화면이
최종 복구 기준이다. 이 저장소는 BaseBundle 재추출 대상 밖이다. APK 업데이트로 host가
달라지면 오래된 UI는 적용하지 않는다. OS 권한·브리지·Python/Go 변경은 UI-only가 아니다.
