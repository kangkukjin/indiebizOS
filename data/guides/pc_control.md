# 맥·Windows PC 컨트롤 — 앱·AI 공용 실행 계약

PC의 상태·음량·음소거·웹 주소 열기·유튜브 재생 교체를 요청받을 때 읽는다. 앱 모드의 **맥 컨트롤 / Windows 컨트롤**과 AI는 아래 파일을 함께 쓴다. 코드를 매번 새로 작성하지 않는다. 장치 소개의 `control_guide`는 이 파일을 가리키며, 본문과 계약이 현재 문맥에 있으면 재독하지 않는다. 가이드 목차 지문이 바뀌면 필요한 가이드를 다시 읽는다.

## 실행 파일과 대상

- 공통 인수 검사·결과 검증: `~workspace/data/instruments/pc_control.py`
- macOS: `~workspace/data/instruments/pc_control_mac.py` (`platform:"darwin"`, 대상에 Python 3 필요)
- Windows: `~workspace/data/instruments/pc_control_windows.ps1` (`platform:"windows"`, 대상에 Windows PowerShell 5.1 이상 필요)
- Windows 유튜브: `~workspace/data/instruments/pc_youtube_windows.ps1` (Chrome·Edge·Brave, 한국어/영어 UI). 같은 공통 prepare/decode를 사용한다. macOS 유튜브 교체·생방송·Firefox/Opera는 미지원이다.
- 원격 전송은 기존 등록 PC 헬퍼의 `shell`과 `stdin`을 사용한다. 새 서버·토큰·PC별 설치 프로그램은 추가하지 않는다. 활성 등록·연결·실행 허용 상태를 확인한다. 앱은 OS가 맞는 등록 PC만 보여준다.
- 본체 제어는 `op:"local"`. 원격 PC에서 실행할 때는 `prepare → guestpc shell 접수 → self:task 완료 대기 → decode` 순서다. 대상 ID는 `[self:limb]{op:"list"}`에서 확인한다. 선택한 행의 `registration.state:"active"`, `registration.paused:false`, `connected:true`, `registration.capabilities.shell:true`와 OS를 확인한다. `adapter:"network-api"`는 PC 실행 대상이 아니다. TV라는 별명으로 OS나 실제 출력 장치를 추측하지 않는다.

## 원격 실행 예시 — 먼저 상태 조회

아래 `$target`과 `$os`, `$nativePath`를 실제 대상에 맞춘다. 예시는 Windows용이다.

```ibl
#!ibl edition=2
$target = "등록된 PC의 device_id"
$os = "windows"
$nativePath = "~workspace/data/instruments/pc_control_windows.ps1"
$s = [self:read]{path:"~workspace/data/instruments/pc_control.py"}
$f = [self:write]{path:"~turn/pc_control.py",content:$s.text}
$native = [self:read]{path:$nativePath}
$p = [self:script]{path:$f.path,args:{op:"prepare",platform:$os,source:$native.text,request:{action:"status"}}}
assert $p.success == true, "PC 인수를 확인하세요.", {result:$p}
$job = [limbs:guestpc]{limb:$target,op:"shell",cmd:$p.command,stdin:$p.stdin,request_id:$p.request.request_id,timeout:30,background:true,mode:"interactive"}
assert $job.success == true, "PC 작업 접수 실패", {result:$job}
$r = [self:task]{op:"wait",ref:$job.task_ref,timeout:60}
assert $r.terminal == true && $r.state == "succeeded", "완료 전입니다. 같은 task_ref로 기다리세요.", {result:$r,task_ref:$job.task_ref}
assert $r.result != null && $r.result.exit == 0, "PC 실행 실패", {result:$r}
$v = [self:script]{path:$f.path,args:{op:"decode",plan:$p,output:$r.result.output}}
assert $v.success == true, "PC 결과 검증 실패", {result:$v}
return $v
```

맥 원격 제어는 `$os="darwin"`, `$nativePath="~workspace/data/instruments/pc_control_mac.py"`로 바꾼다. 본체 제어는 위 `$native`까지 준비한 뒤 다음으로 실행한다. 본체 OS와 `platform`이 다르면 거절된다.

```ibl
$v = [self:script]{path:$f.path,args:{op:"local",platform:$os,source:$native.text,request:{action:"status"}},timeout:35}
assert $v.success == true, "본체 제어 실패", {result:$v}
return $v
```

## request 인수와 성공의 뜻

| 요청 | request | 확인하는 것 |
|---|---|---|
| 상태 | `{action:"status"}` | 호스트·OS·출력 장치 ID/이름·음량·음소거·조절 지원 여부 |
| 음량 | `{action:"volume",device_id:"조회한 ID",value:30}` | 해당 ID의 OS 음량을 다시 읽어 ±1 이내 확인 |
| 음소거 | `{action:"mute",device_id:"조회한 ID",enabled:true}` | 해당 ID의 실제 음소거 값 재조회; 해제는 false |
| 일반 주소 열기 | `{action:"open_url",url:"https://example.com/"}` | 기본 브라우저에 요청 전달. `verified:false`. 유튜브 영상·재생목록 링크는 거절 |
| 잠금 | `{action:"lock"}` | 잠금 명령 전달. `verified:false`; `can_lock:true`인 경우만 사용 |

`success`는 내부 결과까지 확인한다. IBL 실행이 성공했어도 반환 객체의 `success:false`는 실패다. `decode`는 요청 ID·OS·동작·프로토콜·출력 장치 ID를 대조한다. `source_sha256`은 실행에 사용한 네이티브 파일의 지문이다. UI와 AI 모두 같은 prepare/decode를 거친다.

`$target`은 **PC 등록 ID**, `request.device_id`는 **그 PC의 오디오 출력 ID**다. 서로 바꿔 쓰지 않는다. 상태의 `devices`에서 사용 목적에 맞는 장치를 선택한다. UI의 출력 장치 선택은 **조절 대상 선택**이며 기본 출력 전환이 아니다. `can_set_volume`/`can_mute`가 false면 시도하지 않는다. HDMI 등 OS 조절이 없는 장치는 외부 리모컨이 필요하다. OS 음량 재조회는 물리 스피커에서 소리가 들렸다는 검증이 아니다. `audio_error`가 있으면 호스트 상태만 조회된 것이며 오디오 성공으로 보고하지 않는다.

시간 초과·연결 해제·결과 유실은 변경 여부를 모르는 상태다. 변경 명령을 자동 반복하지 말고 새 status로 확인한다. 음소거는 toggle 대신 명시적인 true/false, 음량은 증감 대신 절대값을 사용한다. 사용자가 선택한 장치가 사라지면 다른 장치로 자동 대체하지 않는다.

## 화면 확인과 재생의 경계

원격 화면은 기존 `[limbs:guestpc]{limb:$target,op:"screen",mode:"interactive",max_width:1280}`로 확인한다. PC의 화면 캡처 권한이 필요하며, 한 번 가져온 화면은 실시간 영상이 아니다. 앱의 화면 확인은 원격 PC에만 제공한다.

### 기존 재생 교체 — 새 음악 요청의 기본 의미

“다른 음악 틀어”, “tv1에 유튜브 틀어”는 같은 대상 PC의 기존 재생을 **교체**한다. 추가 재생·대기열 추가는 사용자가 명시했을 때만 한다. `open_url`은 세션을 관리하지 못하므로 유튜브 영상·재생목록 주소를 거절한다. 이를 우회해 `Start-Process`, `open`, 새 탭/창 열기로 재생하지 않는다.

Windows 컨트롤 앱의 **유튜브 재생 교체**에서 검색 → 영상 선택 → 기존 재생 교체를 누른다. AI도 아래 경로를 그대로 사용한다. 검색은 허브에서 하되 재생은 지정 PC에서 한다. `[limbs:music]`이나 허브의 `[limbs:browser]`로 원격 PC 재생을 대신하지 않는다.

1. `[sense:search_youtube]{query:"요청한 음악",limit:6}`의 `items`에서 URL·전체 제목·길이를 고른다. `duration`의 `HH:MM:SS`/`MM:SS`를 초 정수로 바꾼다. 제목이나 길이를 추측하지 않는다.
2. 아래 `$request`와 `$target`을 실제 값으로 채운다. `youtube_status`/`youtube_stop`은 추가 인수가 없다. 세 동작은 **반드시 `pc_youtube_windows.ps1`**을 읽는다.
3. 스크립트가 열린 지원 브라우저의 네이티브 탭을 열거하고 실제 주소창으로 유튜브를 식별한다. 기존 유튜브를 모두 일시정지한 뒤 기존 탭 한 개의 주소만 교체한다. 같은 영상이면 그 탭을 재사용한다. 탭·창을 추가하거나 닫지 않는다. 유튜브 탭이 없으면 PC에서 한 번 열도록 안내하고 종료한다.
4. 요청한 영상 ID·전체 제목·전체 길이, 광고 아님, 재생 상태와 시간 진행을 두 표본에서 확인한다. 다른 유튜브 탭의 정지와 탭 개수·신원 유지도 확인한다. `fullscreen:true`면 마지막에 플레이어 전체화면을 확인한다.
5. 광고의 실제 건너뛰기 버튼이 나타나면 그 버튼을 누른다. 광고·버퍼링 등으로 본영상 검증이 시간 내 끝나지 않으면 실패로 반환한다. `observation.last_observation`에 마지막 광고/재생 상태를 보존한다. 실패 후 새 창, `Ctrl+W`, 주소창 단축키/좌표 추측, 새 URL 실행으로 우회하지 않는다. 상태를 조회하고 실제 오류를 알린다.

```ibl
#!ibl edition=2
$target = "등록된 Windows PC의 device_id"
$request = {action:"youtube_replace",url:"https://www.youtube.com/watch?v=영상ID11자리",title:"검색 결과의 전체 제목",duration_seconds:600,fullscreen:true}
$s = [self:read]{path:"~workspace/data/instruments/pc_control.py"}
$f = [self:write]{path:"~turn/pc_control.py",content:$s.text}
$native = [self:read]{path:"~workspace/data/instruments/pc_youtube_windows.ps1"}
$p = [self:script]{path:$f.path,args:{op:"prepare",platform:"windows",source:$native.text,request:$request}}
assert $p.success == true, "영상 URL·제목·길이를 확인하세요.", {result:$p}
$job = [limbs:guestpc]{limb:$target,op:"shell",cmd:$p.command,stdin:$p.stdin,request_id:$p.request.request_id,timeout:120,background:true,mode:"interactive"}
assert $job.success == true, "PC 작업 접수 실패", {result:$job}
$r = [self:task]{op:"wait",ref:$job.task_ref,timeout:150}
assert $r.terminal == true && $r.state == "succeeded", "완료 전입니다. 같은 task_ref로 기다리고 재전송하지 마세요.", {result:$r,task_ref:$job.task_ref}
assert $r.result != null && $r.result.exit == 0, "PC 실행 실패", {result:$r}
$v = [self:script]{path:$f.path,args:{op:"decode",plan:$p,output:$r.result.output}}
assert $v.success == true, "유튜브 재생 확인 실패", {result:$v}
return $v
```

`youtube_replace` 성공은 `verified:true,previous_stopped:true,playback_verified:true`와 `playback`의 실제 URL·제목·전후 재생 위치·전체 길이를 가진다. `youtube_status`는 `tabs`에 관측 상태를 담으며, 그 `verified:true`는 조회 성공일 뿐 본영상 검증 성공이 아니다. `youtube_stop`은 열린 유튜브 플레이어들의 일시정지를 확인한다. 어느 것도 실제 스피커 소리를 청취한 증거는 아니다.

검사 중 선택 탭과 마우스 위치가 바뀌고, 시간 표시 갱신을 위해 브라우저 창을 최대화한다. 플레이어 전체화면도 해제될 수 있다. 잠긴 세션, 지원하지 않는 UI 언어/브라우저, 확인 불가능한 플레이어는 추측하지 않고 실패한다. 일반 YouTube 웹 탭을 대상으로 하며 설치형 앱·숨은 다른 로그인 세션·다른 사이트의 미디어까지 정지했다고 주장하지 않는다. Windows 본체 실행은 같은 소스로 `op:"local",timeout:120`을 사용한다. macOS는 자동 교체 미지원임을 알리고 새 플레이어를 추가하지 않는다.

원격 실행이 `terminal:false` 또는 `result:null`이면 완료 전이다. 반환된 `task_ref`로 `[self:task]{op:"wait",ref:$r.task_ref,timeout:30}` 후 terminal/result를 검사한다. 기다리는 동안 변경 명령을 다시 보내거나 `$r.result.output`을 먼저 읽지 않는다.

화면 잠금은 사용자가 요청했을 때만 한다. Windows는 LockWorkStation, 맥은 CGSession이 존재할 때만 제공한다. 해당 명령이 없는 최신 맥에서는 버튼이 비활성화된다. 잠금·웹 열기는 사용자의 세션 환경에 따라 달라지므로 상태 조회와 구별한다.

## 앱을 보강할 때

새 동작은 공통 CONTRACT·인수 검증, OS별 실행과 결과, UI, 이 가이드를 함께 갱신한다. 기존 IBL 어휘(`self:script`, `limbs:guestpc`)를 사용하며 하드웨어 버튼마다 새 낱말을 추가하지 않는다. 원격 장치의 OS→가이드 연결은 `data/guide_db.json`의 `control_platforms` 데이터가 소유한다. 현재 두 전용 화면은 데스크톱 앱 모드에 있으며 원격 웹 런처용 화면은 별도 구현 대상이다.
