# Android 하드웨어 제어

폰을 제어할 때 이 가이드를 읽는다. 현재 문맥에 호출 계약이 있으면 재독·API 재탐색·코드 재생성을 생략한다. 원격 장치 소개의 `control_guide`가 이 문서를 가리킨다. 등록·업데이트·범용 실행은 [remote_phone.md](remote_phone.md).

## 앱과 AI가 공유하는 실행 경로

`폰 컨트롤`에서는 앱 위쪽에서 대상 폰을 한 번 선택한다. 원격 웹의 음량·화면·손전등·센서·기기 상태 탭과 데스크톱의 각 제어 영역 모두 그 폰을 사용하며, 탭 전환으로 선택을 초기화하지 않는다. 대상을 바꾸면 이전 폰의 결과를 지운다.

`폰 컨트롤` 앱과 AI는 아래 두 Python 스크립트를 그대로 실행한다. 앱은 모델 호출 없이 IBL → 원격 Python으로 보낸다. AI도 준비된 스크립트와 인수만 보내면 된다. 새 IBL 내용어를 추가하지 않는다. 음악·콘텐츠·앱별 동작은 이 계층의 기능이 아니다.

- `data/instruments/phone_control.py`: 음량 종류별 조회·변경·복원, 진동.
- `data/instruments/phone_device.py`: 화면·밝기·회전·자동 꺼짐·손전등·센서·전원 및 연결 상태.

먼저 `[self:limb]{op:"list"}` 또는 현재 장치 소개에서 사용자가 지정한 폰의 `device_id`를 고른다. 별칭이 같으면 이름만으로 실행하지 않는다. 활성 등록·`connected:true`·`paused:false`와 Python 실행 준비를 확인한다. `info`의 `execution_contract:1`, `runtimes.python.ready:true`가 실행 조건이며 자세한 등록·복구만 `remote_phone.md`를 읽는다.

아래는 **한 번의 execute_ibl 호출**이다. `$target`에는 확인한 ID를 넣는다. 등록 기기 ID와 PC의 오디오 출력 장치 ID는 서로 다르다.

```ibl
#!ibl edition=2
$target = "등록된 폰의 device_id"
$s = [self:read]{path:"~workspace/data/instruments/phone_device.py"}
$r = [limbs:guestpc]{limb:$target,op:"python",code:$s.text,inputs:{op:"status"},timeout:20}
assert $r.success == true && $r.result.success == true, "원격 실행 실패. 변경을 재전송하지 마세요.", {result:$r}
assert $r.result.value.success == true, "폰 제어 실패. 상태를 확인하세요.", {result:$r.result.value}
return $r.result.value
```

스크립트는 파일에 저장하고 가이드에는 경로·인수·결과 계약만 둔다. `~workspace`는 실행하는 본체의 저장소다. 데스크톱·원격 앱 모두 실행할 때 이 파일을 읽으므로 AI와 같은 판본을 사용한다. 이미 파일 내용을 읽었다면 재사용한다. 응답은 바깥 성공 여부, `$r.result.success`, `$r.result.value.success`를 모두 확인한다. 통신 실패 후 변경 명령을 자동 재시도하지 않는다. 먼저 상태를 읽는다.

음량을 바꾸려면 위 예제의 파일을 `phone_control.py`로 바꾸고 먼저 `inputs:{op:"status",stream:"music"}`으로 조회한다. 이어 같은 실행 틀에서 `inputs:{op:"set",stream:"music",value:4}`처럼 인수만 바꾼다. 예시의 4는 조회한 상한 이내의 원하는 정수 단계로 바꾼다. 화면·손전등 등은 `phone_device.py`를 유지한다. 실행 성공과 `verified`가 뜻하는 확인 범위는 아래를 따른다.

## 음량·진동 (`phone_control.py`)

`stream`은 `music`(미디어, 기본), `alarm`, `ring`, `notification`. 통화 음량은 제공하지 않는다. 벨소리·알림은 제조사에서 연동할 수 있고, 방해금지 설정에 걸리면 Android가 거절한다.

| op | 추가 인수 | 동작 |
|---|---|---|
| status | stream 선택 | 현재 actual/max, percent, 복원 가능 여부 |
| set | value: 정수 단계 | 기기 상한 이내 값 적용 |
| step | value: -1 또는 1 | 한 단계 변경 |
| half | 없음 | 현재 단계의 절반, 내림 |
| mute | 없음 | 0단계 요청, 실제 값이 다르면 실패 |
| restore | 없음 | 이 스크립트의 마지막 변경 복원 |
| vibrate | duration_ms: 1~1000 (기본 200) | 짧은 진동 요청 |

복원 기록은 폰 안에서 음량 종류별로 분리하고 잠금으로 보호한다. 다른 곳에서 음량이 바뀌면 복원을 거절한다. 적용 후 actual을 읽어 확인한다. 진동 응답은 요청 접수이며 실제 촉각 감지의 증거가 아니다.

## 기기 기본 기능 (`phone_device.py`)

| op | 추가 인수 | 조건·확인 |
|---|---|---|
| status | 없음 | hardware_control, capabilities, 화면·배터리·연결·센서·손전등 상태 |
| screen_on | 없음 | 다른 앱 위에 표시 권한. 잠금 해제 없이 화면 켜기 |
| screen_off | 없음 | 접근성 서비스. 화면 끄기·잠금 |
| brightness | value: 1~255 | 시스템 설정 변경 허용. 수동 밝기로 전환 |
| brightness_auto | enabled: boolean | 자동 밝기 켜기·끄기 |
| rotation | enabled: boolean | 자동 회전 또는 현재 방향 고정 |
| timeout | seconds: 15~600 정수 | 화면 자동 꺼짐 시간 |
| torch | enabled: boolean, camera_id 선택 | 카메라 권한·플래시 필요. 생략 시 첫 플래시 |
| sensor | sensor: 아래 이름 | 한 번 읽고 리스너 해제 |
| settings_permission | 없음 | 폰에서 권한 설정 화면 열기. 허용은 사용자 조작 |

센서 이름: `light`(lx), `proximity`(cm), `accelerometer`(m/s²), `gyroscope`(rad/s), `magnetic_field`(µT), `pressure`(hPa). status의 sensors에 있는 것만 사용한다. reading.values는 센서 원시 축 순서, accuracy는 Android 정확도 코드, timestamp_ns는 부팅 이후 시간이다. 화면 꺼짐·백그라운드 제한·센서 부재는 실패할 수 있다. 1.5초 내 관측하지 못하면 실패하고 구독을 해제한다.

화면·설정·손전등 변경 응답은 `verified`를 확인한다. false이면 실행 요청이 성공해도 목표 상태는 미확인이다. 설정값 확인은 물리적 화면 밝기의 측정과 다르다. 상태는 관측 시점의 값이다. 손전등은 짧게 실행되는 Python 작업자가 아닌 폰의 상주 프로세스가 소유한다. 따라서 명령 종료 뒤에도 유지되며 `enabled:false`로 끈다.

`hardware_control:0`은 구버전 APK: 상태 조회만 지원하고 새 변경은 실행하지 않는다. `hardware_control:1`은 새 기본 제어 브리지다. 새 기능은 0.14 이상 APK와 개별 권한이 필요하다. 권한 없이 성공한 척하거나 셸 우회하지 않는다. 권한 설정 후 status를 다시 읽는다.

일반 앱에 허용되지 않는 Wi-Fi·블루투스 토글, 전원 종료·재부팅은 제공하지 않는다. 네트워크와 배터리는 관측 항목이다. 화면 켜기·끄기를 기기 부팅·종료와 혼동하지 않는다.

## 속도 원칙

한 변경은 원격 실행 한 번으로 적용과 확인을 끝낸다. 앱 버튼에는 별도 자동 상태 재조회가 없다. 반복적인 목록 조회·API 검색·코드 생성·스크린샷 확인은 필요한 경우에만 한다. 연결 전송과 Python 작업자 시작 시간은 남는다. UI의 소요 시간은 실제 요청 왕복 시간이며 속도 개선율을 추정해 표시하지 않는다. 복합 동작은 검증된 기본 기능을 조합하는 상위 스크립트로 만든다.
