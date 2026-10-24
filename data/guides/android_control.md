# Android OS 제어 — 앱과 AI의 공용 드라이버

폰 컨트롤 앱과 AI는 저장 함수 `Android제어`·`Android제어확인`을 사용한다.
`execute_ibl`의 `describe:["fn:Android제어","fn:Android제어확인"]`으로 서명을 조회한다.
동작별 인수·단위·조건은 `[self:script]{id:"Android제어부품",args:{op:"contract"}}`가 정본이다.
등록·업데이트·범용 실행만 [remote_phone.md](remote_phone.md)를 참고한다.

## 빠른 호출

사용자가 선택한 장치 행의 `device_id`를 `$폰`으로 둔다. 대상·목표는 AI가 결정하고,
드라이버가 매 호출의 연결·권한·현재 상태를 확인한다. 아래 범위는 가이드/describe를 재조회하지 않고 호출한다.

- 한 단계 키움: `[fn:Android제어]{대상:$폰,요청:{action:"volume_step",stream:"music",value:1}}`.
  줄임은 `value:-1`. 이 호출이 현재 값 읽기→변경→재검증하고 `result.before/actual/max/percent`를 반환하므로
  상대 변경 앞뒤에 별도 `volume_status`를 붙이지 않는다. 조회만 필요하면 `action:"volume_status"`.
  절대값은 `action:"volume",value:정수단계`(퍼센트 아님).
  크기를 정해야 하면 조회→AI가 선택한 목표 계산→변경을 한 IBL 프로그램에 묶는다. 과거 음량은 재사용하지 않는다.
- 반환 `status:"completed",verified:true`와 실제 `result`를 확인한다. `pending/unknown`은
  `[fn:Android제어확인]{작업:$원결과}`로 원 작업만 조회한다. 불명확한 변경을 재전송하지 않는다.
- 유튜브 음악은 OS 드라이버 밖의 재생기다. 폰에
  `[limbs:guestpc]{limb:$폰,op:"ibl",code:"[limbs:youtube]{op:'play',query:'검색어'}"}`로 보낸다.
  기본 오디오, 기본 검색 5개(첫 영상 재생·나머지 대기열); 한 개만 원하면 내부 호출에 `count:1`.
  응답의 바깥 접수 성공뿐 아니라 안쪽 `result.success`·제목·모드·오류를 확인한다.
  정지는 같은 폰에 `stop` 후 `queue`를 순서대로 호출해 `now_playing:null,queue_length:0`을 확인한다.
  영상 모드의 `opened:true`는 재생 증거가 아니다. 추가 미디어 조건은 `youtube_relay.md`를 읽는다.
- 앱 실행·터치·입력은 이 요약에 없다. `android_control.md`의 `앱 실행·화면 독해·입력` 절에서
  화면 판본·접근성 권한·검증 조건을 먼저 확인한다.

## 대상과 호출

`[self:limb]{op:"list"}` 또는 장치 소개에서 사용자가 지정한 **device_id**를 고른다.
같은 별칭이나 단 한 대라는 이유로 자동 선택하지 않는다. 드라이버가 활성 등록·연결·중지 여부,
Android OS·`execution_contract:1`·`runtimes.python.ready:true`를 확인하고 아니면 전송 전에 거절한다.
권한·제조사 제한은 폰의 기존 Android API가 최종 판정한다. PC의 `__local__` 대상은 지원하지 않는다.

```ibl
#!ibl edition=2
return [fn:Android제어]{대상:"선택한 device_id",요청:{action:"status"}}
```

밝기·자동 밝기·회전·자동 꺼짐 변경은 `observation_scope:"settings"`와 변경한 설정의
`before`·적용 후 값만 반환할 수 있다. 배터리·연결·센서 상태는 새로 관측한 것이 아니며
이 결과에 없는 필드는 미조회다. 전체 기기 상태가 필요할 때만 `status`를 요청한다.

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
| ui_snapshot | phone_ui.py → snapshot | 전면 창의 접근성 요소·패키지·화면 판본 읽기 |
| app_launch | uiControl → launcher Intent | 요청한 패키지가 전면에 있는지 |
| home | uiControl → GLOBAL_ACTION_HOME | 기본 홈 패키지가 전면에 있는지 |
| back / tap | uiControl → 기존 접근성 키/제스처 | expect가 있으면 화면 조건, 없으면 접수·관측만 verified:false |
| type_text | uiControl → ACTION_SET_TEXT | 지정한 포커스 입력칸의 실제 텍스트 |

UI 변경은 Android 서비스가 실행 직전에 화면을 한 번 읽고 판본을 대조한다.
Python에서 같은 사전 화면을 중복 조회하지 않으며, 서비스의 `before`와 조작 후 새 화면으로 검증한다.
구형 APK의 미지원은 실행 전 실패, 응답 유실은 결과 미확인으로 남기며 변경을 반복하지 않는다.

UI 제어는 아래 별도 조건을 따른다. 브라우저 DOM·탭 제어는 이 드라이버의 범위가 아니다.
하드웨어 동작의 `needs_front:false`는 앞 앱 선택을 요구하지 않는다는 뜻이며 사용자에게 보이지 않는다는 뜻이 아니다.
화면 켜기·잠금·권한 화면·음량 등은 `shared_state:true`, 격리 자원은 없다.

## 앱 실행·화면 독해·입력

새 UI 기능은 **`ui_contract:1`을 제공하는 APK와 켜진 접근성 서비스**가 필요하다.
기존 APK는 변경 전에 `UI_DRIVER_UPDATE_REQUIRED`로 거절한다. 접근성 권한은 폰 설정에서
사용자가 켠다. 기존 하드웨어 제어는 그대로 사용할 수 있다. 회원 APK도 접근성 화면 독해 확장을 공유한다.

```ibl
#!ibl edition=2
return [fn:Android제어]{대상:"선택한 device_id",요청:{action:"app_launch",package:"com.android.settings"}}
```

`app_launch`는 설치된 앱의 정확한 패키지를 받아 launcher Intent를 한 번 보낸다. 패키지가 없거나
실행 진입점이 없으면 실행 전에 실패한다. Android의 백그라운드 실행 제한·잠금·권한을 우회하지 않는다.
`home`은 기본 홈 앱 관측을 확인한다. 앱의 업무 완료나 홈 화면의 특정 페이지까지 보장하지 않는다.

`ui_snapshot`의 `result.screen`에는 `package,window_id,width,height,rotation,snapshot_id,elements,truncated`가 있다.
각 요소는 `ref,path,resource_id,label,text,cx,cy,bounds,editable,focused,enabled,password`를 제공한다.
`bounds`는 화면 픽셀의 `[left,top,right,bottom]`. 이것은 스크린샷/OCR이 아닌 접근성 트리다.
최대 200개 요소·1000개 노드·깊이 40을 읽으며 생략이 있으면 truncated:true다.
빈 입력칸도 포함하고 비밀번호 텍스트·설명은 노출하지 않는다. 앱이 제공하지 않는 캔버스 내용은 읽을 수 없다.

```ibl
#!ibl edition=2
return [fn:Android제어]{대상:"선택한 device_id",요청:{action:"ui_snapshot"}}
```

화면을 보고 선택한 뒤 `tap`에 **그 화면의 snapshot_id와 ref**, 또는 **snapshot_id와 x/y**를 전달한다.
ref와 좌표는 함께 쓰지 않는다. `back`에도 snapshot_id를 전달한다.
접근성 서비스에서 관측 판본을 다시 비교하고 다르면 `STALE_SCREEN`으로 실행 전에 거절한다.
판본은 세션·전면 창·방향·크기·관측한 요소 내용에 묶인다. 이것은 사람·다른 앱의 동시 조작까지 잠그는 OS 트랜잭션이 아니다.
자동으로 새 좌표를 선택하거나 재시도하지 않는다.

`tap`·`back`의 선택 인수 `expect:{package:"...",text:"..."}`는 동작 뒤 확인할 조건이다.
지정한 조건은 모두 일치해야 하며 text는 보이는 요소 label의 **정확한 일치**다.
조건이 없으면 호출 종료와 후속 화면만 반환하고 **verified:false**다.
전후 화면이 다르다는 이유만으로 원하는 동작이 됐다고 판정하지 않는다.

```ibl
#!ibl edition=2
return [fn:Android제어]{대상:"선택한 device_id",요청:{action:"tap",snapshot_id:"관측한 64자리 snapshot_id",ref:3,expect:{text:"다음 화면의 라벨"}}}
```

`type_text`는 `snapshot_id,ref,text`를 받는다. 먼저 입력칸을 터치하고 **다시 화면을 읽어**
focused:true인 editable 요소를 지정한다. 텍스트는 추가 입력이 아닌 **전체 교체**이고 빈 문자열은 비우기다.
한글·줄바꿈을 지원하며 최대 10000자다. 비밀번호 필드·비편집 요소·다른 포커스는 실행 전에 거절한다.
실행 뒤 같은 패키지·창·요소 경로·resource_id의 실제 텍스트를 대조한다. 키보드 Enter/전송은 하지 않는다.

```ibl
#!ibl edition=2
return [fn:Android제어]{대상:"선택한 device_id",요청:{action:"type_text",snapshot_id:"관측한 64자리 snapshot_id",ref:2,text:"안녕하세요"}}
```

모든 UI 동작은 `needs_front:true`, 변경은 `shared_state:true`다. 사람에게 보이는 전면 화면을 사용한다.
변경은 한 번만 전송하고 이후 약 1.75초 동안 최대 8회 **읽기만** 한다. 전환 지연·화면 부재·서비스 중단으로
확인하지 못하면 unknown과 원 관측을 남긴다. 탭 콜백 취소도 일부 효과 가능성이 있어 unknown이다.

## 결과와 실패 복구

PC와 같은 반환 틀: `status,target,verified,result,task_ref,verification,evidence_ref,failure`.
- `completed`: 호출 처리 종료. `verified:false`인 진동·권한 화면·조건 없는 터치/뒤로 요청을 실제 효과 확인으로 보고하지 않는다.
- `failed`: 대상/준비 거절 또는 확인한 결과가 요청과 불일치. `failure.stage/message/next`와 원 관측을 읽는다.
- `pending`: 실행 중. 전체 반환을 보존해 아래 확인 함수에 전달한다.
- `unknown`: 실행 여부·원 영수증·연결이 불명확. **변경을 다시 보내지 않는다.**

대상·화면 문맥 거절 뒤 같은 변경을 원시 shell/python·화면 조작으로 우회하지 않는다.
연결이 끊긴 작업은 원 영수증과 history로 상태를 확인하고 취소했다면 실제 종료까지 확인한다.
`reuse`의 새 실행은 연결·현재 상태를 다시 관측한다. 과거 관측만 재가공하려면 원 결과 참조를
입력으로 전달하고 관측 시점을 남긴다. 임의 원격 코드의 쓰기 범위는 미상이므로, 그 앞의
읽기 재사용이 제외됐다는 이유로 기기 상태를 캐시하거나 코드를 읽기 전용으로 선언하지 않는다.

```ibl
#!ibl edition=2
$작업 = [fn:Android제어]{대상:"선택한 device_id",요청:{action:"status"},대기:0}
return [fn:Android제어확인]{작업:$작업,대기:60}
```

기본 대기는 60초(0~240), 기기 실행 제한은 20초다. 확인은 원래 준비·접수 영수증과
대상·request_id·소스 지문·검증기 판본을 대조한 뒤 **같은 작업만 조회**한다. 실패·취소·시간 초과에도
일부 변경 가능성이 있으면 unknown을 유지한다. 검증기 변경·근거 만료·영수증 손실도 성공으로 꾸미지 않는다.
응답 자체를 잃었으면 실행 원장의 `result_ref`·resume 또는 guestpc history에서 원 요청을 회수한다.
회수할 수 없으면 새 **읽기**(`status`/`volume_status`/`ui_snapshot`)로 현재 상태만 확인한다. 현재 값의 일치는
이전 요청이 실행됐다는 증거가 아니며, 다른 통로로 같은 변경을 재전송하지 않는다.

데스크톱 앱은 미확인 반환을 보관하고 **기존 작업 확인** 버튼으로 조회한다(창 재시작 뒤에는 실행 원장 사용).
원격 선언형 앱도 같은 함수를 호출하고 결과의 `control_task`에 원 반환 전체를 보존하며 처리 상태·작업 ID·복구 안내를 표시한다.
앱의 상태 직접 확인은 작업을 취소하거나 변경을 재전송하지 않는다.

실패 칸의 `code`(2026-10-21, 긴문장 87회차 L87-3): 대상 거절은 `TARGET_NOT_REGISTERED`·`TARGET_NOT_ANDROID`·`TARGET_REVOKED`·`TARGET_INACTIVE`·
`TARGET_NOT_CONNECTED`·`CONTRACT_MISMATCH`·`PYTHON_NOT_READY`, 검증 실패는 폰이 앞머리에 적은 코드(`UI_DRIVER_UPDATE_REQUIRED`·`STALE_SCREEN`·`POSTCONDITION_FAILED` …),
없으면 `null`. 코드를 가진 메시지는 `CODE: 설명` 모양을 지킨다.
`needs_front:true` 동작(앱 실행·화면 독해·입력)은 **사람 화면이 있는 문맥**(`user`·`training`·`test` 출처)에서만 폰에 보낸다. 정기·배경 실행에서는 전송 전에
`SCREEN_CONTEXT_UNAVAILABLE` 로 거절한다(L87-2 — 그전엔 검사 없이 폰까지 갔다). 문맥은 허브가 자식 환경 `INDIEBIZOS_SCREEN_CONTEXT` 로 실어 주고 규칙은 `control_conditions` 한 곳이다.
하드웨어 동작(음량·밝기·화면·센서)은 문맥에 상관없이 보낸다.

## 실행 부품과 배포

공용 준비·검증은 `data/scripts/android_control.py`, 공개 정의는
`data/idioms/android_control.ibl`·`android_control_check.ibl`이며 `installed.json`으로 배포한다.
`data/instruments/phone_control.py`·`phone_device.py`·`phone_ui.py`를 호출 시 읽어 폰에서 실행한다.
새 APK의 `android_control.contract:1`과 설치된 검증기·primitive 지문이 일치하면 기존
`guestpc`의 `control` 전송으로 요청만 보내 상주 엔진의 설치된 제어 함수를 호출한다.
별도 Python 프로세스를 띄우지 않으며 같은 판본·화면·결과 검증을 수행한다. 구형 폰이나
지문 불일치는 접수 전에 기존 `python` 경로를 선택한다. 접수 후 실패에 다른 경로로 재전송하지 않는다.
임의 코드는 계속 일회용 프로세스에서 실행한다. 취소 요청은 이미 들어간 Android 호출을
되돌리지 않으며, 호출 반환과 실행 자리 해제 전에는 종료됐다고 보고하지 않는다.
통신은 연결을 재사용하고 새 허브에서는 결과를 수신 long-poll과 별도 경로로 즉시 보고한다.
앱과 AI는 같은 판본·같은 검증을 쓴다. 새 IBL 내용어는 만들지 않는다. UI 확장은 접근성 관측·판본 검사·앱 실행 다리를 포함한 APK가 필요하다.
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
