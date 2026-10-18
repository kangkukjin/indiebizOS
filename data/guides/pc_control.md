# 맥·Windows PC 컨트롤 — 앱·AI 공용 실행 계약

PC의 상태·음량·음소거·웹 주소 열기를 요청받을 때 읽는다. 앱 모드의 **맥 컨트롤 / Windows 컨트롤**과 AI는 아래 파일을 함께 쓴다. 코드를 매번 새로 작성하지 않는다. 장치 소개의 `control_guide`는 이 파일을 가리키며, 본문과 계약이 현재 문맥에 있으면 재독하지 않는다. 가이드 목차 지문이 바뀌면 필요한 가이드를 다시 읽는다.

## 실행 파일과 대상

- 공통 인수 검사·결과 검증: `~workspace/data/instruments/pc_control.py`
- macOS: `~workspace/data/instruments/pc_control_mac.py` (`platform:"darwin"`, 대상에 Python 3 필요)
- Windows: `~workspace/data/instruments/pc_control_windows.ps1` (`platform:"windows"`, 대상에 Windows PowerShell 5.1 이상 필요)
- 원격 전송은 기존 등록 PC 헬퍼의 `shell`과 `stdin`을 사용한다. 새 서버·토큰·PC별 설치 프로그램은 추가하지 않는다. 활성 등록·연결·실행 허용 상태를 확인한다. 앱은 OS가 맞는 등록 PC만 보여준다.
- 본체 제어는 `op:"local"`. 원격 PC에서 실행할 때는 `prepare → guestpc shell → decode` 순서다. 대상 ID는 `[self:limb]{op:"list"}`에서 확인한다. TV라는 별명으로 OS나 실제 출력 장치를 추측하지 않는다.

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
$r = [limbs:guestpc]{limb:$target,op:"shell",cmd:$p.command,stdin:$p.stdin,request_id:$p.request.request_id,timeout:30}
assert $r.success == true && $r.result.exit == 0, "실행 결과가 불완전합니다. 변경을 재전송하지 말고 상태를 조회하세요.", {result:$r}
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
| 주소 열기 | `{action:"open_url",url:"https://www.youtube.com/"}` | 기본 브라우저에 요청을 전달함. `verified:false` |
| 잠금 | `{action:"lock"}` | 잠금 명령 전달. `verified:false`; `can_lock:true`인 경우만 사용 |

`success`는 내부 결과까지 확인한다. IBL 실행이 성공했어도 반환 객체의 `success:false`는 실패다. `decode`는 요청 ID·OS·동작·프로토콜·출력 장치 ID를 대조한다. `source_sha256`은 실행에 사용한 네이티브 파일의 지문이다. UI와 AI 모두 같은 prepare/decode를 거친다.

상태의 `devices`에서 사용 목적에 맞는 장치를 선택한다. UI의 출력 장치 선택은 **조절 대상 선택**이며 기본 출력 전환이 아니다. `can_set_volume`/`can_mute`가 false면 시도하지 않는다. HDMI 등 OS 조절이 없는 장치는 외부 리모컨이 필요하다. OS 음량 재조회는 물리 스피커에서 소리가 들렸다는 검증이 아니다. `audio_error`가 있으면 호스트 상태만 조회된 것이며 오디오 성공으로 보고하지 않는다.

시간 초과·연결 해제·결과 유실은 변경 여부를 모르는 상태다. 변경 명령을 자동 반복하지 말고 새 status로 확인한다. 음소거는 toggle 대신 명시적인 true/false, 음량은 증감 대신 절대값을 사용한다. 사용자가 선택한 장치가 사라지면 다른 장치로 자동 대체하지 않는다.

## 화면 확인과 재생의 경계

원격 화면은 기존 `[limbs:guestpc]{limb:$target,op:"screen",mode:"interactive",max_width:1280}`로 확인한다. PC의 화면 캡처 권한이 필요하며, 한 번 가져온 화면은 실시간 영상이 아니다. 앱의 화면 확인은 원격 PC에만 제공한다.

주소 열기는 기존 영상 정지, 원하는 영상의 실제 재생, 전체 화면을 보장하지 않는다. “TV1에 유튜브 틀어”를 주소 요청 성공만으로 완료 처리하지 않는다. 브라우저 제어나 화면 확인으로 재생 상태를 별도로 확인해야 한다. 현재 PC 컨트롤 앱에는 영상 선택·재생 상태 검증·전체 화면 기능을 넣지 않았다.

화면 잠금은 사용자가 요청했을 때만 한다. Windows는 LockWorkStation, 맥은 CGSession이 존재할 때만 제공한다. 해당 명령이 없는 최신 맥에서는 버튼이 비활성화된다. 잠금·웹 열기는 사용자의 세션 환경에 따라 달라지므로 상태 조회와 구별한다.

## 앱을 보강할 때

새 동작은 공통 CONTRACT·인수 검증, OS별 실행과 결과, UI, 이 가이드를 함께 갱신한다. 기존 IBL 어휘(`self:script`, `limbs:guestpc`)를 사용하며 하드웨어 버튼마다 새 낱말을 추가하지 않는다. 원격 장치의 OS→가이드 연결은 `data/guide_db.json`의 `control_platforms` 데이터가 소유한다. 현재 두 전용 화면은 데스크톱 앱 모드에 있으며 원격 웹 런처용 화면은 별도 구현 대상이다.
