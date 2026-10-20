# PC 제어 — 앱과 AI의 공용 호출

macOS·Windows PC의 출력 장치·음량·음소거·주소 열기·잠금과 Windows 유튜브 제어, 그리고 두 OS 공통의 화면·전원·입회·앱·클립보드·네트워크·단축어 조작면을 한다.
앱의 PC 컨트롤과 AI는 저장 함수 `PC제어`·`PC제어확인`을 함께 쓴다.
`execute_ibl`의 `describe:["fn:PC제어","fn:PC제어확인"]`으로 서명을 조회한다.
내부 스크립트 계약은 `[self:script]{op:"list",id:"PC제어부품"}`에 있다.

## 대상 선택

`[self:limb]{op:"list"}`의 device_id·이름·설명·OS·연결 상태를 읽어 사용자가 가리킨
PC를 고른다. 본체는 `__local__`을 명시한다 — 장치 소개 블록의 `device_id="__local__"` 행(`adapter="local"`)이
이 가이드를 가리키며, 본체 음량·주소 열기·잠금과 아래 '본체 OS 조작면' 의 동작은 화면 조작이 아니라 이 통로다. 출력 장치 ID와 PC ID는 서로 다르다.
PC가 한 대여도 자동 선택하지 않는다. 중지·해제·미접속·미지원 OS는 실행 전에 거절한다.
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
두 OS 가 같은 동작 이름·결과 모양을 쓰고, OS 가 공개 API 로 못 읽는 값은 `null` 과 `*_basis` 로 남긴다(거짓 0 없음).
Windows 는 관리자 권한을 요구하지 않는다. 전부 배경에서 돈다 — `needs_front` 동작은 없고 어떤 동작도 앱을 앞으로 가져오지 않는다. 읽기는 OS 조회값
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

쓰기 전에 읽는 순서는 이렇다. brightness 전에 display 로 `can_set_brightness` 와 display_id 를 본다. 화면을 찍거나
사용자 입회가 필요한 일 전에 presence 로 idle_seconds·screen_locked·display_asleep 을 본다(꺼진 화면을 찍어 검은
그림을 success 로 받는 일을 막는 자리). 밤일처럼 긴 배경 작업은 keep_awake 로 시작하고 allow_sleep 으로 끝낸다.
shortcut 은 사용자가 단축어 앱(Windows 는 작업 스케줄러)에서 만든 흐름을 이름으로 부르는 탈출구다 — 새 동작이 필요하면 코드보다 단축어가 먼저다.
실패는 `failure.message` 와 `result.error` 에 원인이 있고, 변경 요청을 자동 재전송하지 않는 규칙은 같다.
본체 앱 자체의 창·탭 조작(Safari 등)은 앱 드라이버(`safari_control.md`)가 맡고, 여기 동작은 OS 수준까지다.

## 유튜브 영상 선택

Windows의 Chrome·Edge·Brave에서 기존 재생 탭을 교체한다. 영상 검색 결과의 URL·전체 제목·
길이를 사용하며 길이는 **초** 단위 정수다. 생방송은 지원하지 않는다. 광고가 재생 중이거나
본영상 시간을 확인하지 못하면 검증 실패다. `open_url`로 새 유튜브 영상 플레이어를 추가하지 않는다.
macOS의 브라우저 교체는 지원하지 않는다. TV 자체 앱 실행은 [TV 제어](tv_control.md)의 launch다.

## 완료와 후속 확인

반환은 status·target·verified·result·task_ref·verification·evidence_ref·failure다.
`completed`는 호출 처리 종료이며, `verified:false`를 목표 달성으로 보고하지 않는다.
OS 음량 관측은 물리 스피커에서 소리가 나는지 확인한 것이 아니다.

`pending`이면 **전체 반환값**을 보존해 다음처럼 확인한다. 변경 요청은 다시 보내지 않는다.

```ibl
#!ibl edition=2
$작업 = [fn:PC제어]{대상:"선택한 device_id",요청:{action:"status"},대기:0}
return [fn:PC제어확인]{작업:$작업,대기:60}
```

대기는 기본 60초, 유튜브는 150초이고 0~240초로 조절한다. 장치 실행 제한은 별도로
기본 30초·유튜브 120초다. pending을 failed로 바꾸거나 자동 재전송하지 않는다.
`unknown`은 접수·관측·원 근거가 불확실한 경우다. 실패에는 단계와 다음 확인 방법이 있다.

후속 확인은 준비·접수의 원래 실행 영수증과 대상·요청 ID·OS·소스 지문을 대조한다.
verification을 임의 수정하면 검증하지 않는다. 검증기 코드가 바뀌거나 영수증이 만료되면
unknown으로 남긴다. 최신 코드를 다시 보내 과거 결과를 대신 만들지 않는다.
evidence_ref나 그 안의 plan·job이 누락·null·잘못된 자료형이어도 unknown으로 반환하며 원격 조회·변경을 전송하지 않는다.
값을 잃었으면 execute_ibl의 기존 `result_ref.read_args`로 원 반환을 회수한다. 접수 응답 자체를
잃은 경우 원 실행의 resume·실행 기록과 guestpc history로 확인하고 새 요청을 만들지 않는다.

## 설치와 수리

여러 상태를 점검할 때는 `PC조회묶음`으로 대상 선택과 실행 파일 읽기를 공유한다.
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
구현은 prepare→guestpc→task→검증을 소유한다. 정상 호출에서 이 연결을 다시 작성하지 않는다.
`PC제어실행`은 두 공개 함수가 공유하는 내부 부품이며 직접 대상 선택을 대신하는 공개 입구로 쓰지 않는다.
