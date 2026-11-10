# PC 제어 — 앱과 AI의 공용 호출

macOS·Windows PC의 출력 장치·음량·음소거·주소 열기·잠금과 Windows 유튜브 제어, 그리고 두 OS 공통의 화면·전원·입회·앱·클립보드·네트워크·단축어 조작면을 한다.
앱의 PC 컨트롤과 AI는 저장 함수 `PC제어`·`PC제어확인`을 함께 쓴다.
`execute_ibl`의 `describe:["fn:PC제어","fn:PC제어확인"]`으로 서명을 조회한다.
내부 스크립트 계약은 `[self:script]{op:"list",id:"PC제어부품"}`에 있다.


## 빠른 호출

대상은 PC의 `device_id`, 본체는 `__local__`이다. macOS·Windows의 로컬 또는 상주 사용자 세션을 지원한다. 휴대형·관리 서비스 세션은 OS 제어 대상이 아니다.
- 호출: `[fn:PC제어]{대상:$PC,요청:{action:"status"}}`. 동작·인수 계약은 `[self:script]{id:"PC제어부품",args:{op:"contract"}}`로 조회한다.
- 음량은 `action:"volume",device_id:$출력,value:50`(0~100 정수), 음소거는 `action:"mute",device_id:$출력,enabled:Bool`. 출력 ID는 `status`의 `result.devices`에 있으며 PC ID와 다르다.
- 결과는 `status`·`verified`·`result`·`failure`. `completed`는 처리 종료이며 검증 범위는 동작별로 다르다. 음량 변경의 OS 재조회는 드라이버가 수행하며 물리적 소리를 검증하지 않는다.
- `pending/unknown`은 원 결과로 `[fn:PC제어확인]{작업:$원결과}`를 호출한다. 새 접수는 별도 실행이며 중복 효과가 생길 수 있다.
- Windows Chrome은 `chrome_*`(전용 프로필), 유튜브는 `youtube_*` 동작이다. 화면 판본·재생 검증 조건은 아래 해당 절에 있다.

## 대상 선택

`[self:limb]{op:"list"}`의 device_id·이름·설명·OS·연결 상태를 읽어 사용자가 가리킨
PC를 고른다. 본체는 `__local__`을 명시한다 — 장치 소개 블록의 `device_id="__local__"` 행(`adapter="local"`)이
이 가이드를 가리키며, 본체 음량·주소 열기·잠금과 아래 '본체 OS 조작면' 의 동작은 화면 조작이 아니라 이 통로다. 출력 장치 ID와 PC ID는 서로 다르다.
원격 OS 제어는 상주 사용자 세션에 연결한다. 휴대형은 원격 실행·전송 가이드를 사용하며, Windows 관리 서비스는 시스템 작업용이므로 PC제어가 사용자 화면 대신 선택하지 않는다. 중지·해제·미접속·미지원 OS·관리 세션은 실행 전에 거절한다.
OS와 실행 파일·전송 명령은 부품이 해소하며 호출자가 지정하지 않는다.

다음은 자리표 골격이다. 대상 ID와 출력 ID는 조회한 실제 값으로 고쳐 쓰는 것이 정상이다.

```ibl
#!ibl edition=2
$PC = "선택한 device_id"
return [fn:PC제어]{대상:$PC,요청:{action:"status"}}
```

상태 결과의 `result.devices`에서 사용할 출력의 ID와 can_set_volume·can_mute를 확인한다.
이 두 값은 OS 제어 API의 지원 범위이며 실제 변경 성공이나 물리적 소리를 보장하지 않는다.
장치별 `capability_basis`는 macOS에서 `coreaudio_property_settable`(속성의 쓰기 가능 여부),
Windows에서 `wasapi_endpoint_volume_interface`(활성화하고 조회한 EndpointVolume 인터페이스)다.
Windows는 하드웨어 제어가 없어도 OS의 소프트웨어 제어를 지원할 수 있다.
Windows의 true는 OS 인터페이스 활성화·조회 성공에 근거한 **API 지원 판정**이다.
OS API 지원을 묻는 조건에는 이 Bool을 사용한다. 하드웨어 직접 지원이나 실제 변경 성공을
사용자가 별도로 요구했다면 그것은 별도 미확인이며, 해당 시험을 안 했다는 이유로 API 지원 값까지 미확인으로 바꾸지 않는다.
`status`는 setter를 호출하지 않는다. `verification_scope:os_state_readback`은 현재 OS 상태 조회,
`os_setting_readback`은 volume·mute 변경 후 설정값 재조회를 뜻한다.
전체 계약은 `[self:script]{id:"PC제어부품",args:{op:"contract"}}`의 `audio_capabilities`에 있다.
상태·음량·음소거의 실제 결과에도 같은 `audio_capabilities` 계약이 포함된다.

```ibl
#!ibl edition=2
return [fn:PC제어]{대상:"선택한 device_id",요청:{action:"volume",device_id:"조회한 출력 ID",value:30}}
```

| action | 추가 요청 인수 | 관측 범위 |
| --- | --- | --- |
| status | 없음 | OS의 출력 장치·음량·음소거 |
| volume | device_id, value:0~100 정수 | 지정 출력의 음량 재조회(오차 ±1) |
| mute | device_id, enabled:Bool | 지정 출력의 음소거 재조회 |
| open_url | url:HTTP(S) | 브라우저 열기 요청. 페이지 표시·영상 재생 보장 아님 |
| lock | 없음 | 세션 잠금 상태를 3초 안에 재조회(screen_locked). 맥은 CG 세션 사전, Windows 는 입력 데스크톱 열기+LogonUI |
| youtube_status | 없음 | Windows 브라우저의 기존 유튜브 탭 |
| youtube_replace | url,title,duration_seconds,fullscreen:Bool | 기존 재생 정지·탭 수 유지·본영상 재생·요청한 전체화면 |
| youtube_stop | 없음 | 기존 재생 정지·탭 수 유지 |

## 본체 OS 조작면 (macOS·Windows)

원격 PC 에도 같은 OS 실행 파일(`pc_control_mac.py`·`pc_control_windows.ps1`)이 가므로 본체·원격의 동작은 같다.
macOS 대상은 그 PC 의 `python3`(Xcode Command Line Tools 또는 사용자가 설치한 Python 3)으로, Windows 는 OS 기본 PowerShell 5.1 로 실행한다(`op:"contract"` 의 `requirements`). 이 도구가 없는 Mac 은 PC제어만 `PC_RUNTIME_MISSING` 으로 실패하고 헬퍼의 기본 셸·파일·전송은 그대로 동작한다.
확인 결과의 `observation` 에는 원 접수의 기기·설치 세대·작업(`transport_ref`)과 드라이버가 읽은 자원(`resource`: 출력 장치·화면·앱·탭 등)이 함께 남는다. 자원 신원을 읽지 않는 동작은 `identity:"not_reported_by_driver"` 다.
두 OS 가 같은 동작 이름·결과 모양을 쓰고, OS 가 공개 API 로 못 읽는 값은 `null` 과 `*_basis` 로 남긴다(거짓 0 없음).
이 절의 OS 동작은 사용자 세션에서 배경 API로 실행한다. Windows 관리자 권한이 필요한 조회 항목은 아래 표에 따로 표시한다. 뒤의 유튜브 UI 제어는 별도 계약이며 앞 창을 사용할 수 있다. 읽기는 OS 조회값
그대로이고, 쓰기는 변경 뒤 같은 조회로 재확인한 것만 `verified:true` 다. 동작별 `shared_state`(사용자와 공유하는
상태를 바꾸는 요청된 효과)·`verification_scope` 는 `[self:script]{id:"PC제어부품",args:{op:"contract"}}` 의 `conditions` 에
있고 결과의 `condition` 칸에도 실린다.

| action | 추가 요청 인수 | 관측 범위 |
| --- | --- | --- |
| display | 없음 | 화면 목록(id·main·builtin·active·asleep·width·height·brightness·can_set_brightness)과 screen_locked·on_console. Windows 는 id=DISPLAYn 번호, asleep·builtin 은 null, 밝기는 WMI 인스턴스(내장 화면)만 |
| brightness | value:0~100 정수, display_id(선택, 기본 주 화면) | 지정 화면 밝기 재조회(오차 ±2). `can_set_brightness:false`(외부 모니터 등)면 두 OS 모두 변경 없이 거절 |
| power | 없음 | power_source·battery(없으면 null)·flags(잠 방지 플래그)·sleep_holders(잠 못 들게 하는 프로세스)·lid_closed(맥 노트북만, 아니면 null)·keep_awake. Windows 의 flags·sleep_holders 는 관리자일 때만(`powercfg /requests`), 아니면 null+`requests_basis` |
| presence | 없음 | idle_seconds(마지막 입력 뒤 초)·front(앞 앱 pid·name, 맥은 bundle_id·Windows 는 title)·screen_locked·display_asleep(Windows 는 null). 사용자가 보고 있는지의 판단 재료이지 판정이 아니다 |
| apps | 없음 | front·apps(화면에 보이는 앱의 name·pid, 맥은 bundle_id·Windows 는 title·path)·background_count |
| launch | app(맥: 번들 ID `com.apple.TextEdit` 또는 앱 이름 `TextEdit`. Windows: 실행 파일 이름 `notepad`·시작 메뉴 바로가기 이름·AUMID) | 앱 목록 재조회(5초). 이미 실행 중이면 `already_running:true`. 창은 생길 수 있으나 앞으로 오지 않는다(Windows 는 최소화로 열기 요청, 앱이 무시할 수 있음) |
| quit | app | 앱 목록 재조회(8초). 맥은 앱별 Apple Events 자동화 권한이 없으면 -1743 거절, Windows 는 주 창에 닫기 요청(강제 종료 없음). 저장 확인 창이 뜨면 시간 초과 실패 |
| clipboard | 없음 | 글 100,000자까지·length·truncated. 그림 등 글 아닌 내용은 비어 보인다 |
| clipboard_write | text(100,000자 이하) | 쓴 뒤 재조회 일치 |
| network | 없음 | wifi(port·enabled·ssid — 맥은 위치 권한 없으면 null, Windows 는 연결 중일 때만)·bluetooth(enabled·connected 기기). 블루투스 연결·해제는 지원하지 않는다 |
| wifi | enabled:Bool | Wi-Fi 전원 재조회(Windows 는 WinRT 라디오, 관리자 불요). 원격 PC 에서 끄면 그 연결 자체가 끊길 수 있다 |
| shortcuts | 없음 | 사용자가 만든 단축어 이름 목록. Windows 는 작업 스케줄러 루트 폴더의 작업 이름(`shortcuts_basis`) |
| shortcut | name(shortcuts 로 조회한 이름) | 정상 종료(exit 0)와 출력 4,000자(Windows 작업은 출력 없음·LastTaskResult 0). 단축어 안의 효과는 범위 밖이라 `verified:false` |
| keep_awake | seconds:1~86400 정수, display(선택, 화면도 안 끄기) | 맥은 전원 관리 목록 재조회, Windows 는 잠 방지 자식 프로세스 생존 재조회(`readback_basis`). 한 번에 하나만 켤 수 있다 |
| allow_sleep | 없음 | 켜 둔 잠들지 않기 프로세스 종료 확인. 없으면 그대로 verified |
| sleep | 없음 | 잠자기 요청. 잠들었는지는 범위 밖 |

```ibl
#!ibl edition=2
return [fn:PC제어]{대상:"__local__",요청:{action:"presence"}}
```

```ibl
#!ibl edition=2
return [fn:PC제어]{대상:"__local__",요청:{action:"launch",app:"com.apple.TextEdit"}}
```

`display`는 밝기 제어 지원과 display_id, `presence`는 idle_seconds·screen_locked·display_asleep을 반환한다.
`keep_awake`/`allow_sleep`은 잠 방지 프로세스의 시작·종료다. `shortcut`은 OS에 등록된 기존 단축어·예약 작업을 호출한다.
실패 원인은 `failure.message`와 `result.error`에 있다.
본체 앱 자체의 창·탭 조작(Safari·Chrome 등)은 앱 드라이버(`safari_control.md`·`chrome_control.md`)가 맡고, 여기 동작은 OS 수준까지다.

## Windows Chrome 창·탭 (전용 프로필 CDP)

Windows PC 의 Chrome 창·탭은 OS 수준이 아니라 앱 조작면 `app:com.google.Chrome` 이다. 맥 본체는 `Chrome제어`(`chrome_control.md`),
Windows PC 는 같은 계약을 **PC제어의 `chrome_*` 동작**으로 부른다(실행 파일 `pc_chrome_windows.ps1`). 통로는 DevTools 프로토콜이고
Chrome 136+ 가 기본 프로필의 원격 디버깅을 거부하므로 **전용 프로필**(`%LOCALAPPDATA%\IndieBiz\ChromeProfile`)만 본다 — 사용자가
따로 띄운 크롬은 `other_chrome_instances` 개수로만 알려 주고 그 탭은 다루지 않는다(그쪽 유튜브 탭은 `youtube_*` 가 UI Automation 으로 다룬다).
`chrome_launch`는 실행 여부를 확인하고 `result.windows`에 창·탭 관측을 함께 반환한다. TV와의 조합 예시는 [TV 제어](tv_control.md#전원브라우저검색을-함께-준비하기)에 있다.

처음 한 번 `chrome_launch` 로 띄우고(최소화로 요청, `shortcut:true` 면 바탕화면 "IndieBiz Chrome" 바로가기 생성) 그 프로필에서 필요한 로그인을 한다.

| action | 추가 요청 인수 | 관측 범위 |
| --- | --- | --- |
| chrome_launch | url(선택), shortcut:Bool(선택) | DevTools 포트 확인(`browser`·`port`). 이미 떠 있으면 `already_running:true` 변경 없음 |
| chrome_status | window_id(선택) | 창(`window_id`·`state` normal/minimized/maximized/fullscreen)·탭(`tab_id`·url·name, **id 순 — 탭 띠 순서가 아님**)·`current_tab`(표시 중인 탭, 최소화 창은 null)·`revision` |
| chrome_open | url, window_id·expected·launch(선택) | CDP `background` 생성 — 현재 탭 불변. 창이 없으면 새 창. 꺼져 있으면 `launch:true` 때만 그 주소로 기동. 유튜브 영상 주소는 거절(`youtube_replace`) |
| chrome_switch | window_id, tab, expected | `tab` 은 **targetId(32자리 16진수)** 다. 변경 뒤 표시 상태 재조회. 최소화 창은 확인 불가(`POSTCONDITION_FAILED`) |
| chrome_close | window_id, tab, expected | targetId 로 닫고 남은 탭 집합 대조. 마지막 탭이면 창 소멸 |

`expected` 는 `windows[].revision` 또는 직전 결과 `state.revision`(창 id·현재 탭·탭 id 집합). 다르면 변경 전 `STATE_CHANGED`.
결과의 `target` 은 다음 호출 인수 `{window_id,tab,expected}` 다. `UNKNOWN`·`POSTCONDITION_FAILED`는 변경 효과를 확정하지 못한 상태다.
원격 PC 라 실행은 접수증(`PC제어확인`)으로 회수한다 — 연속 동작은 각 단계의 `result.target` 을 다음 요청에 잇는다.

```ibl
#!ibl edition=2
return [fn:PC제어]{대상:"선택한 device_id",요청:{action:"chrome_status"}}
```

```ibl
#!ibl edition=2
$s = [fn:PC제어]{대상:"선택한 device_id",요청:{action:"chrome_open",url:"https://news.hada.io/",window_id:1378650243,expected:"관측한 revision"}}
return $s
```

## 유튜브 영상 선택

Windows의 Chrome·Edge·Brave에서 기존 재생 탭을 교체한다. `video`는 검색 결과의 한 행을 받는다.
제목·길이는 로드된 영상과 대조하는 값이며 `duration`(M:SS/H:MM:SS)은 부품이 초로 바꾼다.
기존 `url`·`title`·`duration_seconds` 직접 지정도 지원하며 `video`와는 상호 배타적이다.
`fullscreen`은 생략하면 false다. 생방송은 지원하지 않는다. 광고가 재생 중이거나
본영상 시간을 확인하지 못하면 검증 실패다. `open_url`에는 재생 교체·재생 검증 계약이 없다.
macOS의 브라우저 교체는 지원하지 않는다. TV 자체 앱 실행은 [TV 제어](tv_control.md)의 launch다.
다음은 첫 검색 행을 사용하는 예시다. 실제로는 검색 행의 제목·채널을 보고 고른다.

```ibl
#!ibl edition=2
$검색 = [limbs:youtube]{op:"search",query:"사용자가 원하는 음악",limit:3}
$영상 = $검색.items[0]
return [fn:PC제어]{대상:"선택한 device_id",요청:{action:"youtube_replace",video:$영상,fullscreen:true}}
```

PC제어 반환의 상태는 `$작업.status`, 장치 관측은 `$작업.result`, 실패 설명은 `$작업.failure`다.
함수 반환에는 `value`·`success` 필드가 없다.
`execute_ibl`가 바깥에 붙이는 `value`는 프로그램 내부의 함수 반환 필드가 아니다.
TV제어 스크립트는 `success`·`observations`를 직접 돌려주므로 PC제어와 같은 모양으로 가정하지 않는다.

실패 결과에는 `failure.code`·`failure.next`·`result.last_observation`이 있다.
- `YOUTUBE_NO_TAB`: 기존 브라우저에서 교체할 유튜브 탭이 발견되지 않음.
- `YOUTUBE_FOCUS_FAILED`: 대상 창의 초점을 확인하지 못함. 드라이버는 최소화 창 복원과 초점 확인을 수행한다.
- `YOUTUBE_TITLE_MISMATCH`·`YOUTUBE_DURATION_MISMATCH`: 로드된 본영상의 불일치를 연속 두 번 관측하면 대기를 끝낸다. 요청한 제목·길이와 실제 본영상이 다름.
- `YOUTUBE_PLAYER_ERROR`: 플레이어 안의 보이는 오류 문구를 즉시 돌려준다. 오류 원문이 결과에 포함된다.
- `YOUTUBE_PLAYBACK_TIMEOUT`: 실행 한도 안에 재생 조건을 확인하지 못함. 마지막 관측을 반환한다.

`read_result`는 기존 결과·영수증 회수이며 새 기기 호출이 아니다(`code`와 상호 배타적).
결과 후처리 오류는 앞선 기기 변경을 취소하지 않는다.

## 완료와 후속 확인

반환은 status·target·verified·result·task_ref·verification·evidence_ref·failure다.
`completed`는 호출 처리 종료, `verified`는 동작별 사후 조건의 검증 여부다.
OS 음량 관측은 물리 스피커에서 소리가 나는지 확인한 것이 아니다.

`pending`이면 **전체 반환값**을 보존해 다음처럼 확인한다. 새 변경 요청과 원 작업 조회는 별도 호출이다.

```ibl
#!ibl edition=2
$작업 = [fn:PC제어]{대상:"선택한 device_id",요청:{action:"status"},대기:0}
return [fn:PC제어확인]{작업:$작업,대기:60}
```

대기는 기본 60초, 유튜브는 150초이고 0~240초로 조절한다. 장치 실행 제한은 별도로
기본 30초·유튜브 120초다. `pending`은 실행 결과가 아직 도착하지 않은 상태다.
`unknown`은 접수·관측·원 근거가 불확실한 경우다. 실패에는 단계와 다음 확인 방법이 있다.

후속 확인은 준비·접수의 원래 실행 영수증과 대상·요청 ID·OS·소스 지문을 대조한다.
verification을 임의 수정하면 검증하지 않는다. 검증기 코드가 바뀌거나 영수증이 만료되면
unknown으로 남긴다.
evidence_ref나 그 안의 plan·job이 누락·null·잘못된 자료형이어도 unknown으로 반환하며 원격 조회·변경을 전송하지 않는다.
값을 잃었으면 execute_ibl의 기존 `result_ref.read_args`로 원 반환을 회수한다. 접수 응답 자체를
잃은 경우 원 실행의 resume·실행 기록과 guestpc history로 확인하고 새 요청을 만들지 않는다.

실패 칸에는 `code` 가 있다(2026-10-21, 긴문장 87회차 L87-3). 대상 거절은 조건별 코드 `TARGET_NOT_REGISTERED`·`TARGET_REVOKED`·`TARGET_INACTIVE`·`TARGET_ADAPTER_UNSUPPORTED`·`TARGET_SESSION_UNSUPPORTED`·
`SHELL_NOT_READY`·`TARGET_NOT_CONNECTED`, 묶음의 미지원 항목은 `UNSUPPORTED_ACTION`, 실행 실패는 실행 파일이 앞머리에 적은 코드(`LAUNCH_FAILED` 등)다.
코드가 없는 실패는 `code:null` 이며 `message` 로만 판단한다. 코드를 가진 메시지는 `CODE: 설명` 모양이라 registered-json/1 통로에서도 코드가 살아남는다.
같은 실행 안에서 같은 PC 를 여러 번 부를 때 묶음 조회의 첫 행이 `stage:"target"` 이면 그 대상의 나머지 호출은 건너뛴다 — 끊긴 PC 에 쓰기를 열일곱 번 보내도 전송은 0 이지만 호출마다 손발 조회를 반복한다(W87-3).
드라이버는 손발 목록을 `[self:limb]{op:"list",limb:$대상}` 로 그 손발만 읽는다(전체 원장 65KB → 10KB, W87-1).

대상 선택이 연결·활성·권한 조건으로 거절되면 원시 `guestpc shell`이나 화면 조작으로
같은 변경을 우회하지 않는다. `info` 한 번의 응답은 드라이버의 모든 실행 조건을 충족했다는
증거가 아니다. 이미 접수한 변경은 원 `task_ref`·history로 상태를 확인하고, 필요하면
그 작업의 취소와 종료를 확인한다. 끊긴 대상에 새 변경을 쌓으면 재연결 때 뒤늦게 실행될 수 있다.

`reuse`의 새 실행은 연결 목록·현재 상태를 다시 읽는다. `resume`은 같은 실행의 영수증 회수다.
과거 관측은 원 실행의 `result_ref.input_args`로 참조할 수 있다. 임의 셸·Python 전송은
쓰기 범위가 미상으로 등록되어 앞선 읽기의 재사용이 제외될 수 있다.

## 설치와 수리

`PC조회묶음`은 여러 조회 사이에서 대상 선택과 실행 파일 읽기를 공유하는 관용구다.
기본 항목은 status·display·power·presence다. 선택 항목은 apps·clipboard·network·shortcuts까지이며,
읽기만 받는다. OS 가 지원하지 않는 항목은 항목별 실패로 남긴다.
반환은 `{target,items}`이고 각 행에 action과 기존 PC제어의 결과·실패·영수증이 있다.
항목별 `verified`를 확인하며 pending 행은 `PC제어확인`에 그 행 전체를 전달한다.
동일 PC의 조회는 순서대로 실행하므로 여러 상태가 같은 시각의 원자적 스냅샷이라는 뜻은 아니다.
본체는 원격 목록을 조회하지 않으며, 원격은 목록을 한 번 읽되 각 실제 전송의 연결·권한 검사는 유지한다.
다음 호출에서는 현재 상태를 다시 읽는다. 접수 전 target/prepare 실패에는 존재하지 않는 task_ref 조회를 권하지 않는다.

```ibl
#!ibl edition=2
$점검 = [fn:PC조회묶음]{대상:"__local__",항목:["status","presence","display","power"]}
return $점검
```

배포 정의의 정본은 `data/idioms/pc_control*.ibl`·`pc_read_batch.ibl`, 구현은 `data/scripts/pc_control.py`다.
설치 목록 `data/idioms/installed.json`이 첫 부팅에도 정의를 제공한다. 같은 이름의 다른 개인
정의는 충돌로 신고한다. 임베딩 색인 등록은 `register_webapp_idioms.py --seed-file pc_control_seeds.json`을 사용한다.
구현은 prepare→guestpc→task→검증을 연결한다. `PC제어실행`은 두 공개 함수가 공유하는 내부 부품이며 대상 선택 결과를 입력받는다.

## 범용 원격 화면·입력

```ibl
[limbs:guestpc]{op:"screen",limb:"사무실PC",mode:"interactive"}
[limbs:guestpc]{op:"click",limb:"사무실PC",mode:"interactive",x:640,y:400}
[limbs:guestpc]{op:"type",limb:"사무실PC",mode:"interactive",text:"hello"}
[limbs:guestpc]{op:"key",limb:"사무실PC",mode:"interactive",key:"cmd+s"}
```

좌표는 screen 이미지 기준이며 헬퍼가 축소·레티나 배율을 환산한다. 예제의 좌표는 자리표다.
입력은 기본 재캡처(`shot:false`로 끄기), `settle_ms` 기본 700이다. type은 현재 포커스에 입력한다.
캡처는 `max_width` 기본 1280, `format` png/jpeg/auto, `display` 다중 모니터 선택이며
최근 20장이 `outputs/limb_screens/<별칭>/`에 남는다. move·scroll·drag도 같은 모드와 좌표 규칙이다.

| OS | 화면·입력 조건 |
| --- | --- |
| Windows | 기본 OS API 사용. 관리자 창 입력은 헬퍼도 관리자 권한 필요 |
| macOS | 화면 기록·손쉬운 사용 권한. cliclick 설치 시 우클릭·드래그·정밀 이동 지원 |
| Linux | grim/scrot/ImageMagick 캡처 도구와 xdotool/ydotool 입력 도구 필요 |

GUI 지원 신고는 info, 실제 실행 결과는 해당 작업의 응답에 있다. OS에 따라 권한 변경 반영에 헬퍼 재시작이 필요할 수 있다.

## 사람이 직접 다루는 화면 공유

조종실 → 손발 (USB) → **화면 공유**. 새 PC 헬퍼·Android 앱은 짧은 단절을 복구하며 이전 입력을 재전송하지 않는다.
OS 권한·LAN 경로·기록 정책은 [헬퍼 안내](../../helper/README.md#사람용-화면-공유), 기기별 적용·실측은
[연결 수리 기록](../../docs/REMOTE_HARDWARE_TRANSPORT_REPAIR_2026_10_31.md)을 따른다.
