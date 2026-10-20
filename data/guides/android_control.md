# Android OS 제어 — 앱과 AI의 공용 드라이버

폰 컨트롤 앱과 AI는 저장 함수 `Android제어`·`Android제어확인`을 사용한다.
`execute_ibl`의 `describe:["fn:Android제어","fn:Android제어확인"]`으로 서명을 조회한다.
동작별 인수·단위·조건은 `[self:script]{id:"Android제어부품",args:{op:"contract"}}`가 정본이다.
등록·업데이트·범용 실행만 [remote_phone.md](remote_phone.md)를 참고한다.

## 대상과 호출

`[self:limb]{op:"list"}` 또는 장치 소개에서 사용자가 지정한 **device_id**를 고른다.
같은 별칭이나 단 한 대라는 이유로 자동 선택하지 않는다. 드라이버가 활성 등록·연결·중지 여부,
Android OS·`execution_contract:1`·`runtimes.python.ready:true`를 확인하고 아니면 전송 전에 거절한다.
권한·제조사 제한은 폰의 기존 Android API가 최종 판정한다. PC의 `__local__` 대상은 지원하지 않는다.

```ibl
#!ibl edition=2
return [fn:Android제어]{대상:"선택한 device_id",요청:{action:"status"}}
```

기기 상태는 `status`, 음량 상태는 `volume_status`다. 음량은 **퍼센트가 아닌 OS 정수 단계**이며
조회한 `result.max` 이하로 지정한다. 밝기는 기존 폰 API와 같은 **1~255**, 자동 꺼짐은 초 단위다.

```ibl
#!ibl edition=2
return [fn:Android제어]{대상:"선택한 device_id",요청:{action:"volume",stream:"music",value:4}}
```

| 공개 action | 기존 실행 부품의 op | 확인 범위 |
|---|---|---|
| volume_status | phone_control.py status | 지정 음량 종류의 현재 값 |
| volume / volume_step / volume_half / volume_mute / volume_restore | set / step / half / mute / restore | 목표 단계와 실제 단계 일치 |
| vibrate | vibrate | 요청 접수만, verified:false |
| status | phone_device.py status | 기기 상태 조회(구형 APK의 부분 조회 포함) |
| brightness / brightness_auto / rotation / timeout | 같은 이름 | 적용 설정 재조회. 물리적 밝기 측정 아님 |
| screen_on / screen_off | 같은 이름 | 화면의 interactive 상태. 잠금 해제·인증 보장 아님 |
| torch | torch | 선택한 카메라의 토치 콜백 상태 |
| sensor | sensor | 지정 센서의 유효한 한 표본 |
| settings_permission | 같은 이름 | 설정 화면 열기 요청만, verified:false |

현재 범위는 기존 하드웨어 기능의 계약 정비다. 앱 실행·홈/뒤로·범용 화면 입력·브라우저는 이 드라이버에 추가하지 않았다.
동작의 `needs_front:false`는 앞 앱 선택을 요구하지 않는다는 뜻이며 사용자에게 보이지 않는다는 뜻이 아니다.
화면 켜기·잠금·권한 화면·음량 등은 `shared_state:true`, 격리 자원은 없다.

## 결과와 실패 복구

PC와 같은 반환 틀: `status,target,verified,result,task_ref,verification,evidence_ref,failure`.
- `completed`: 호출 처리 종료. `verified:false`인 진동·권한 화면 요청을 실제 효과 확인으로 보고하지 않는다.
- `failed`: 대상/준비 거절 또는 확인한 결과가 요청과 불일치. `failure.stage/message/next`와 원 관측을 읽는다.
- `pending`: 실행 중. 전체 반환을 보존해 아래 확인 함수에 전달한다.
- `unknown`: 실행 여부·원 영수증·연결이 불명확. **변경을 다시 보내지 않는다.**

```ibl
#!ibl edition=2
$작업 = [fn:Android제어]{대상:"선택한 device_id",요청:{action:"status"},대기:0}
return [fn:Android제어확인]{작업:$작업,대기:60}
```

기본 대기는 60초(0~240), 기기 실행 제한은 20초다. 확인은 원래 준비·접수 영수증과
대상·request_id·소스 지문·검증기 판본을 대조한 뒤 **같은 작업만 조회**한다. 실패·취소·시간 초과에도
일부 변경 가능성이 있으면 unknown을 유지한다. 검증기 변경·근거 만료·영수증 손실도 성공으로 꾸미지 않는다.
응답 자체를 잃었으면 실행 원장의 `result_ref`·resume 또는 guestpc history에서 원 요청을 회수한다.
회수할 수 없으면 새 **읽기**(`status`/`volume_status`)로 현재 상태만 확인한다. 현재 값의 일치는
이전 요청이 실행됐다는 증거가 아니며, 다른 통로로 같은 변경을 재전송하지 않는다.

데스크톱 앱은 미확인 반환을 보관하고 **기존 작업 확인** 버튼으로 조회한다(창 재시작 뒤에는 실행 원장 사용).
원격 선언형 앱도 같은 함수를 호출하고 결과의 `control_task`에 원 반환 전체를 보존하며 처리 상태·작업 ID·복구 안내를 표시한다.
앱의 상태 직접 확인은 작업을 취소하거나 변경을 재전송하지 않는다.

## 실행 부품과 배포

공용 준비·검증은 `data/scripts/android_control.py`, 공개 정의는
`data/idioms/android_control.ibl`·`android_control_check.ibl`이며 `installed.json`으로 배포한다.
기존 `data/instruments/phone_control.py`·`phone_device.py`를 호출 시 읽어 폰에서 실행한다.
앱과 AI는 같은 판본·같은 검증을 쓴다. 새 IBL 내용어나 APK 기능을 요구하지 않는다.
의미 검색 시드는 `android_control_seeds.json`, 등록은 `.venv/bin/python3 scripts/register_webapp_idioms.py --seed-file android_control_seeds.json --apply`다.

아래 표의 `op`는 실행 부품 내부 계약이다. 일반 호출은 위 공개 `action`을 사용한다.

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
