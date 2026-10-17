# 원격폰 기능 활용 — IBL·셸·Python·Android API

## 등록과 연결

Android 폰은 `setup_phone.sh --limb 삼성1`로 설치·등록한다. 허브가 만든 1회용 자격을
USB 물리 접근으로 전달하며 허브 로그인 비밀번호는 요구하지 않는다. 등록 뒤에는 폰이
허브에 원격으로 접속하므로 **USB 미연결만으로 폰을 사용할 수 없다고 판단하지 않는다.**
먼저 `[self:limb]{op:"list"}`의 활성 등록과 연결 상태를 확인한다. `adapter:"indiebiz-v1"`이면
폰 자체 IBL 엔진을 사용할 수 있다. 새 실행은 info의 `execution_contract:1`과 ops를 확인한다.
여러 등록에 같은 별칭이 남아 있으면 현재 활성 등록의 device_id를 사용한다.

- **현재 상태**: `[limbs:guestpc]{op:"info",limb:"삼성1"}`. 동기 결과의 `$r.result`는 폰이
  응답한 정보다. `.capabilities.media_session`에 지원·권한·준비 상태가 있다면 그 값을 사용한다.
  `camera:true`는 촬영 성공이 아니고 `speaker:true`는 TTS 음성 출력 성공이 아니다.
  신고에 없는 기능은 미확인으로 남긴다. 파일 경로·기능 지원과 실제 출력 확인을 구분한다.
- **하달 판본과 결과**: `code`는 별도 프로그램이다. 현재 문법은 그 문자열 안에도
  `#!ibl edition=2` 헤더를 넣는다. 바깥 프로그램의 판본이 문자열 안에 자동 적용되지는 않는다.
  동기 guestpc 응답의 `.result`는 원격 실행 봉투, **`.result.value`가 판본 2의 업무 값**이다.
  `info` 결과에는 이 `.value` 층이 없다. 실행 실패는 `[try]…[catch]`로 받고 원문과
  `$error.details.task_ref`를 보존한다. 존재하지 않는 `.ok` 필드로 실패를 검사하지 않는다.
- **긴 일**: `background:true`로 접수하고 `[self:task]{op:"wait",ref:$ticket.task_ref}`로
  같은 작업을 회수한다. 성공한 wait의 `.result`는 폰 응답이므로 판본 2 업무 값은
  **`.result.value`**다. `timed_out:true`면 같은 ref로 계속 확인한다. 폰 IBL의 실행 중 취소는
  지원하지 않고 전달 전 취소만 가능하다. 결과가 늦다고 재접수하지 않는다.
- **훈련 출처**: 호출 메타데이터의 `origin:"training"`은 허브 봉투→폰 클라이언트→폰 실행기로
  전달한다. 이 경로는 출처 전달을 지원하는 새 설치본에서 적용된다. 표식은 기기 제어를
  차단하는 샌드박스가 아니므로 훈련의 별도 실행 범위는 그대로 지킨다.

### 작은 텍스트·JSON 파일을 원격에서 작성하고 회수하기

폰의 `op:"read"`·`op:"write"`는 PC 헬퍼 전용이다. 작은 파일은 폰의 IBL 안에서
`self:write/read`를 조합하거나, 새 폰의 shell/Python에서 처리한다. 문자열에 JSON 원문을 직접 끼우거나 백슬래시를 손으로
치환하지 말고 **내용을 JSON 문자열 리터럴로 한 번 더 직렬화**한다. 다음 예제의 `rows`는
명시 입력 목록이며, 작업별 고유 시험 경로를 사용한다. IBL의 f문자열은 `${…}`만
보간한다. 코드의 보통 `{…}`는 그대로 쓰며 Python식 `{{…}}`로 바꾸지 않는다.

```ibl
#!ibl edition=2
$inner=f"""#!ibl edition=2
$s=[self:write]{path:"outputs/phone-check/checklist.json",content:${json(json($rows))}}
$d=[self:read]{path:$s.path}
return {path:$s.path,items:$d.data.items,text:$d.text}
"""
$r=[limbs:guestpc]{op:"ibl",limb:"삼성1",code:$inner,timeout:60}
return $r.result.value
```

폰의 `result_ref`·`resume`는 **그 폰 저장소의 참조**다. 중앙 실행기의 read_result에 그대로
넣지 않는다. 필요한 값·원문을 원격 프로그램에서 반환하고 중앙의 `self:write`로 보존한다.
`[sense:see]`는 저장 위치 인자가 없고 앱 사진 폴더(`files/photos/`)에 jpg 경로만 돌려준다. 크기·해시는 그 폴더를 `[self:list]{path:폴더,pattern:파일이름,hash:true}`로 읽는다(파일 경로를 path에 주면 `Not a directory`). 큰 사진·녹음 파일은 경로만으로 회수된 것이 아니다. 현재 폰 손발이 신고하는 ops에 transfer가
없으면 헬퍼용 `transfer collect`를 호출해도 해결되지 않는다. 작은 텍스트 왕복과 바이너리
파일 전송의 지원 범위를 구분한다.

### 소리·미디어·등록 수명

- 소리: `[limbs:radio]{op:"play",station_id:"…"}`를 하달하면 폰 스피커에서 재생한다.
  상태는 `op:"status"`, 정지는 `op:"stop"`이다. 방송국 ID는 먼저 조회한다.
  음악의 읽기 전용 상태는 `[limbs:music]{op:"queue"}`다. 상태 조회 성공은 재생 실증이 아니다.
- 영상·마이크·스피커 연결은 [미디어 세션 가이드](media_session.md)의 기존 스크립트를 사용한다.
  지원 신고와 권한·대기 모드, 실제 프레임/음성 출력은 각각 확인한다.
- 등록 해제는 `[self:limb]{op:"remove",target:"삼성1"}`, 자격 폐기는 `op:"revoke"`다.
  단순 조회·작업 종료 때 등록을 해제하지 않는다.


## 중앙 APK 업데이트 (USB 없는 후속 갱신)

원격 하드웨어의 업데이트 주체는 **중앙 주인**이다. 조종실의 등록된 원격 기기에서
폰의 **앱 업데이트**를 누르면 중앙에 발행한 APK를 기존 등록 자격으로 전송하고,
폰이 Android PackageInstaller로 자기 앱을 교체한다. 회원 데스크톱의 사용자 선택형
업데이트와는 별개이며, 일반 에이전트의 `guestpc` 명령으로 업데이트 op를 직접 실행하지 않는다.

최초에는 원격 업데이트 계약을 지원하는 APK를 데이터 유지 설치해야 한다.
`setup_phone.sh`는 USB 최초 설치 때 앱 설치 허용을 준비한다. USB가 없으면 APK를
다운로드해 직접 설치하고 Android 설정에서 IndieBiz의 **알 수 없는 앱 설치**를 허용한다.
그 이후 APK 전달·설치 요청·재접속 확인은 USB/ADB 없이 기존 원격 연결만 사용한다.

발행은 중앙에서 같은 서명키로 만든 APK를 대상으로 한다. `phoneVersionCode`는 기존
배포보다 높아야 하며, 빌드의 기본값을 재사용해 서로 다른 APK를 같은 버전으로 발행하지 않는다.

```bash
# 6/0.6은 예시다. 각 ABI의 중앙 배포보다 높은 새 번호로 바꿔 실행한다.
cd phone-companion
./gradlew :app:assembleArm64Debug :app:assembleArm32Debug -PphoneVersionCode=6 -PphoneVersionName=0.6 --no-watch-fs --no-daemon
cd ..
.venv/bin/python3 scripts/publish_phone_update.py --apk phone-companion/app/build/outputs/apk/arm64/debug/app-arm64-debug.apk
.venv/bin/python3 scripts/publish_phone_update.py --apk phone-companion/app/build/outputs/apk/arm32/debug/app-arm32-debug.apk
```

서명키는 기존 설치물과 동일하게 유지한다. 발행기는 APK 서명 검증·패키지·ABI·versionCode를
확인하고 `data/resident_files/phone-releases/`에 불변 APK와 ABI별 활성 판본을 저장한다.
APK와 키는 Git 커밋 대상이 아니다. 중앙은 `POST /remote-pcs/phone-update`의
`{"target":"현재 device_id"}`로도 요청할 수 있다. `/remote-pcs`의 `phone_update`가
상태를, 기기 capabilities의 `apk_update`가 실제 설치 버전·해시·권한·최근 시도를 보고한다.

- 다운로드는 기존 인증된 청크 전송과 SHA-256 검증을 사용한다. 폰에서도 패키지·현재 서명·
  높은 versionCode·ABI를 다시 확인한다. 서명이 다르거나 낮은 버전이면 설치하지 않는다.
- 설치 요청 접수는 완료가 아니다. 새 앱의 인증된 재접속에서 설치 APK 해시가 일치해야
  `current`가 된다. APK 교체 뒤 시스템의 `MY_PACKAGE_REPLACED`가 상주 서비스를 복원한다.
- Android가 확인을 요구하면 `awaiting_permission` 또는 `awaiting_confirmation`으로
  중앙에 표시하고 폰의 알림·설치 화면을 연다. 중앙이 업데이트를 결정하는 원칙은 유지하되
  OS의 확인을 자동 클릭하거나 우회하지 않는다. Android 12+의 무인 자기 업데이트는
  설치 권한·대상 SDK 등 OS 조건을 충족할 때 적용된다.
- 설치 중에는 새 원격 작업의 실행을 대기시킨다. 설치 콜백·시도 기록은 앱의 영속 저장소에
  남으며 재접속 때 보고된다. Android 설치 거절은 기존 앱을 유지한다. 새 앱 자체가 부팅하지
  못하는 경우 APK 자동 다운그레이드/롤백은 보장하지 않으며 오프라인·미확인을 확인해야 한다.
- 중앙보다 높은 설치 버전은 `ahead`(업데이트 불필요), 같은 버전의 다른 APK는 `different_build`로 구분한다.
  설치본 해시가 중앙 배포본과 같을 때만 `current`다. 직접 설치는 중앙 발행을 대신하지 않는다.
  검증한 APK를 USB 등으로 설치했다면 같은 파일을 위 발행기로 등록해야 배포 기준도 갱신된다.
- 오래된 앱은 `bootstrap`, 미발행 ABI는 `unpublished`, 서명·Android 요구 버전 불일치는 `incompatible`로
  표시한다. 32비트 빌드 지원과 각 실제 기기의 무인 설치 성공은 구분한다.

### 실기 검증 (2026-10-16)

예나폰(SM-A516N, Android 13, arm64)은 기존 등록·데이터를 유지한 USB 준비 설치 후,
중앙 HTTPS 연결로 versionCode 4 → 5(0.5)를 전달하고 앱 자체 설치까지 완료했다.
후속 갱신에는 ADB 전송·설치를 사용하지 않았다. 자동 재기동·인증된 재접속과 배포 APK의
SHA-256 일치(`41813657b8f336a7b2602dd1cb62931f0295dc4b78469fadefd546814182b588`),
`current` 상태 및 갱신 후 원격 Python 실행을 확인했다. 최초 설치 권한 준비 뒤 이 갱신은
폰의 추가 확인 없이 진행됐다. arm32 APK는 빌드·발행만 확인했으며 삼성0에는 설치하지 않았다.
다른 Android 버전의 실제 설치 확인 화면·무인 설치는 미검증이다.

## 범용 실행 계약 1 (새 APK 필요)

앱 설치와 원격 등록은 별개다. 기존 APK를 업데이트하고 info의
`.result.capabilities.execution_contract == 1`, ops의 shell/python/transfer를 확인한다.
구형 설치에는 중앙에서 대신 실행하지 않고 미지원 오류를 반환한다.

- `op:shell,cmd:"id"`: `/system/bin/sh -c`, 앱 UID. cwd·env·stdin을 지원한다.
- `op:python,code:본문,inputs:객체`: Chaquopy 별도 프로세스. inputs를 읽고 result에 JSON 값을 넣는다.
- timeout 기본120초·1..3600초. cwd 생략 시 userdata/remote_work, 상대 경로도 이곳 기준이다.
- 매 작업은 새 프로세스다. mode는 background만, shell은 sh만, elevate/reset 미지원.
  Python은 env/stdin/shell을 받지 않는다. 폰에 python3/curl 실행 파일이 있다고 가정하지 않는다.
- shell/Python은 주인만 접수할 수 있다. 앱 UID는 ADB shell UID와 다르며 권한을 추가하지 않는다.
- `background:true,request_id:고유값`으로 접수하고 같은 task_ref로 관측한다.
  실행 timeout·취소는 worker 종료 결과를 확인한다. 이미 발생한 기기 변경은 되돌리지 않는다.
  `worker_cleanup_confirmed`/`resource_cleanup_confirmed`가 false이면 결과 불명이다.
  자식 회수 범위는 관측된 프로세스 트리다. 탈출한 데몬까지 종료했다고 주장하지 않는다.
- 결과는 `.result.stdout/stderr/exit_code/value`. Python 예외는 exception_type·traceback으로 보존한다.
  stdout/stderr 각각 64KiB 미리보기, 전체 로그 합계8MiB 상한, 큰 value는 value_ref로 반환한다.
  완료 파일은 7일 후 다음 실행에서 정리한다. 전송 중·실패한 회수는 핀으로 보존하며 재개 성공 때 해제한다.
- 파일 회수는 `transfer action:receive,path:폰경로` 완료 뒤 `action:collect,local_path:중앙경로`.
  SHA-256과 크기를 확인한다. 경로 반환만으로 회수 완료가 아니다. 기존 다른 파일은 덮어쓰지 않는다.

### 재생기와 무관하게 기기 음량을 절반으로

다음 Python을 `op:python`의 code로 전달한다. OS 단계의 절반이며 지각 음압의 절반을 뜻하지 않는다.

```python
from java import jclass
from indiebiz_android import context
AudioManager = jclass("android.media.AudioManager")
audio = context.getSystemService("audio")
stream = AudioManager.STREAM_MUSIC
if audio.isVolumeFixed():
    raise RuntimeError("fixed_volume")
before = audio.getStreamVolume(stream)
target = before // 2
audio.setStreamVolume(stream, target, 0)
after = audio.getStreamVolume(stream)
result = {"before": before, "requested": target, "actual": after,
          "max": audio.getStreamMaxVolume(stream), "applied": after == target}
```

음악 시작·다음 곡은 현재 음량을 유지한다. 라디오 전용 volume은 라디오 대상을 확인하지만,
기기 AudioManager 호출에는 재생 중인 라디오가 필요 없다. 영화 세션은 명시 음량 변경만 적용하고
같은 세션의 재시작 봉투로 음량을 되돌리지 않는다. 상태에는 실제 OS 음량이 나온다.

일반 Android API는 java.jclass/context를 쓴다. 기존 서비스 자원이 필요한 기능은
`from indiebiz_android import call`로 소유 프로세스에 요청한다:
`call("snapshot")`, `call("tap",x,y)`, `call("typeText",text)`, `call("pressKey","back")`,
`call("capturePhoto","back")`, `call("recordAudio",초)`, `call("streamStatus")`.
접근성·카메라·마이크 권한과 백그라운드 제한은 그대로 적용된다. USB 등록 시 원격 센서 시작을
허용하면, 등록된 중앙 PC의 카메라·마이크 요청이 잠금 위에 전용 화면을 연다(잠금 해제 없음).
이 기능은 접근성 권한 대신 '다른 앱 위에 표시' 허용을 사용하며 종료 시 화면을 닫는다.
자세한 설치·준비 상태는 [미디어 세션 가이드](media_session.md)를 따른다. Wi-Fi/Bluetooth 설정 변경이
OS에 거절되면 사용자가 설정 화면에서 조작해야 한다. 실패한 변경을 자동 재실행하지 않는다.

폰 자체 AI는 원격 등록 없이 `run_command`를 사용한다. `runtime:"python"`이면 command가
Python 본문이고 inputs/result 계약은 동일하다. shell은 기본 runtime이다.
실기 배포·검증 여부는 [구현 기록](../../docs/PHONE_REMOTE_EXECUTION_DESIGN_2026_10_15.md#10-구현-기록)을 확인한다.

## 조종실 손발에서 폰 화면 공유

화면공유 지원 APK(0.7/versionCode 7부터)로 업데이트한 폰은 조종실 → 손발의 **화면 공유**로
PC와 같은 전용 창을 연다. 별도 원격제어 앱·USB·ADB는 필요 없다. 구형 앱에는 업데이트 안내가
나오며, 실제 설치 후 재접속에서 `desktop_stream:1`, `ops:desktop`, `os:android`가 확인되어야 한다.

1. 폰 설정 → 접근성 → 설치된 서비스에서 **IndieBiz**를 켠다(최초 준비).
2. 손발에서 폰의 **화면 공유**를 누른다.
3. 폰의 IndieBiz 앱이나 화면 공유 알림을 열고 Android의 **화면 전체 공유**를 승인한다.
   다른 앱 위에 표시 권한이 있으면 승인 화면을 직접 띄운다. 캡처 승인은 세션마다 필요하며
   자동 승인·잠금 해제는 하지 않는다. 2분 안에 승인하지 않으면 연결을 닫고 다시 시작한다.
4. 원격 창에서 클릭=탭, 누른 뒤 놓기=길게 누르기, 드래그/휠=스와이프를 사용한다.
   위쪽 **뒤로·홈·최근 앱** 버튼으로 탐색한다. 입력창을 먼저 탭하면 문자·한글 조합·붙여넣기·
   삭제·좌우 커서 이동을 지원한다. PC 단축키 전체나 모든 앱의 특수 편집기는 지원하지 않는다.
5. 원격 창을 닫거나 폰 알림의 **종료**를 누르면 공유와 입력을 종료한다. 연결 단절·등록 자격
   폐기에도 세션을 닫는다. Android가 잠금 등으로 캡처를 중단하면 새 승인이 필요하다.

캡처는 Android `MediaProjection` 전용 포그라운드 서비스, 조작은 기존 접근성 서비스다.
PC와 같은 인증된 화면 세션/바이너리 WebSocket을 사용하며 긴 변 1280px 이하·최대 5fps JPEG로
전송한다. 화면·입력 내용은 작업 이력이나 파일에 저장하지 않는다. 회전 때 캡처 크기를 갱신하고,
전체 화면과 좌표가 맞지 않는 앱 단독 캡처는 거절한다. 보안 화면·DRM 영상은 보이지 않을 수 있다.
부드러운 동영상·게임 스트리밍이나 멀티터치 제어를 보장하는 기능은 아니다.

검증: 인증된 PC/폰 스트림·자격 불일치·임대/종료·권한 대기·입력 경계 회귀, Android 제스처 단위검사,
브라우저 화면/탐색/드래그/키보드/한글 조합을 검사한다. 실제 폰의 설치·OS 승인·화면 전송·조작은
별도 실기 확인이며 빌드 성공이나 `desktop_stream` 신고만으로 실기 성공이라 판단하지 않는다.
