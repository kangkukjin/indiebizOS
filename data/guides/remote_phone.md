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
접근성·카메라·마이크 권한과 백그라운드 제한은 그대로 적용된다. Wi-Fi/Bluetooth 설정 변경이
OS에 거절되면 사용자가 설정 화면에서 조작해야 한다. 실패한 변경을 자동 재실행하지 않는다.

폰 자체 AI는 원격 등록 없이 `run_command`를 사용한다. `runtime:"python"`이면 command가
Python 본문이고 inputs/result 계약은 동일하다. shell은 기본 runtime이다.
실기 배포·검증 여부는 [구현 기록](../../docs/PHONE_REMOTE_EXECUTION_DESIGN_2026_10_15.md#10-구현-기록)을 확인한다.
