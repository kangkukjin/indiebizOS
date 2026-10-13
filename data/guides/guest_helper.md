# 원격 PC 헬퍼 — 상주 PC·휴대 USB 사용 가이드

원격 PC의 셸·파일·화면·재생은 `[limbs:guestpc]`, 등록·일시 중지·제거는 `[self:limb]`로 한다.
헬퍼는 대상 PC에서 실행되고 두뇌·신원은 중앙 허브에 남는다. 원격 PC도 허브로 아웃바운드
연결하므로 대상 공유기의 포트를 열지 않는다. **먼저 대상 이름과 상주/휴대 모드를 확인한다.**
현재 문맥에 이 가이드 전문과 환경 조회 결과가 있으면 매 명령마다 다시 읽거나 조회하지 않는다.

설치·업데이트·빌드처럼 긴 작업은 아래 **대상 고정과 단계 실행**을 먼저 적용한다.
원격 파일 검색·읽기는 같은 `limb`의 `shell/read/list`를 쓴다. `self:file_find`는 허브를
검색하므로 원격 파일 조회에 쓰지 않는다. macOS/Linux 셸은 `/bin/sh`이며 `<(...)` 같은
셸 확장을 가정하지 않는다. 각 단계의 종료 코드를 보존하려면 argv 계획을 사용한다.

## 1. 모드 선택과 설치

| 계약 | 상주 PC (새 기본 경로) | 휴대 USB (기존 issue 경로) |
| --- | --- | --- |
| 준비 | `self:limb register` → 공용 폴더를 USB에 복사 → 대상 PC에서 이름을 정해 등록 | `self:limb issue` → 이름별 발급 폴더를 USB에 복사 → 실행 |
| 수명 | 사용자 로그인 시 자동 시작, 비정상 종료 시 OS 서비스 관리자가 재기동(macOS launchd·Linux systemd; Windows는 로그인 때만 — 헬퍼 교체 때는 감시자가 새 판을 띄움). 등록 후 USB 제거 가능 | 대상 PC에서 직접 실행한 헬퍼의 수명 |
| 명령 환경 | 작업마다 cwd·env 분리. 절대 cwd·venv 실행파일 경로·env 명시 | 직전 cwd·환경변수 유지. 함수·별칭은 유지하지 않음. reset으로 초기화 |
| 화면·입력 | `mode:"interactive"` 필수 | 기존 screen·입력 호출 |
| 중복 방지 | 같은 `request_id` + 같은 명령은 기존 접수증. 내용이 다르면 충돌 | 접수증으로 관측. 같은 명령 재전송 금지 |
| 작업 후 | 연결 유지. 작업 마무리와 제거는 별개 | 필요할 때 `detach`로 프로세스 종료 |
| 제거 | 명시적인 `self:limb remove`. `removal_pending`과 `removed` 구분 | `revoke`로 키 폐기 |
| 헬퍼 교체 | Windows·macOS·Linux 모두 중앙 조종실 손발(USB)의 `헬퍼 교체` — 중앙 `helper/dist`와 다를 때만 보인다. 헬퍼가 받아 검증·교체·재기동하고 5분 안에 다시 연결하지 못하면 이전 판으로 되돌린다. AI 작업(`limbs:guestpc`)으로는 요청할 수 없다 | 해당 없음 |

`self:limb list`의 각 행에 `registration`이 있으면 상주형, null이면 휴대형이다.
상주형 `registration.state/paused`, 공통 `connected/expired/revoked`를 확인한다.
상주형에서 `detach`는 거절된다. 일시적으로 새 작업만 막으려면 `pause`를 쓴다.

```ibl
[self:limb]{op:"register"}
[self:limb]{op:"list"}
```

조종실 **손발 (USB) → 폴더 준비**도 같은 `outputs/pc-helper` 공용 폴더를 만든다.
실행파일·설정·사용법을 포함한 폴더 전체를 USB에 복사하고 대상 PC에서 OS에 맞는 파일을
실행한다. 같은 USB로 여러 PC를 등록한다. 등록 키는 등록 전용이고 각 PC의 실행 자격은
별도로 발급된다. USB 등록 키 폐기는 이미 등록된 PC를 끊지 않는다. 기존 발급 폴더·키는
자동으로 상주형으로 바뀌지 않는다.

상주형은 macOS LaunchAgent, Windows 현재 사용자 로그인 예약 작업, Linux systemd 사용자
서비스다. 로그인 전 실행·관리자 서비스는 아니다. 중앙 주소는 `/limb/*`와 `/remote-pcs/*`를
직접 전달하는 HTTPS 터널이어야 한다. 지속 WebSocket이 막히면 HTTPS 롱폴로 돌아간다.
설치·OS 권한은 대상 PC에서 허용한다. Android/iPhone/iPad 신규 등록은 지원하지 않는다.

## 2. 등록 관용구 — 이름으로 찾아 조합한다

아래 아홉 함수는 등록된 정의다. 매번 본문을 다시 쓰지 않고
`execute_ibl(code="",describe=["fn:외부PC파일가져오기"])`로 계약을 조회한다.
상시 프롬프트에 전문을 싣지 않으며 이름 조회·의미 검색으로 찾는다.

| 함수 | 인자 | 완료와 재개 |
| --- | --- | --- |
| `외부PC준비` | `PC`, `환경조회:true`, `작업폴더:""`, `환경:{}` | 대상·모드·등록·연결·OS 정보와 명시한 workspace를 보존. `ready`도 특정 도구 설치를 보장하지 않음 |
| `외부PC작업실행` | `PC,명령`, `작업폴더:""`, `준비:{}`, `작업:{}`, `요청ID:""`, `환경:{}`, `셸:""`, `실행제한:1800`, `대기:0`, `입력:""`, `환경초기화:false` | 준비의 device_id·workspace 사용. 명시 폴더·환경으로 덮어쓸 수 있다. 작업을 주면 재접수 없이 관측. `ok:true`는 접수이며 상주형은 요청ID 필수 권장 |
| `외부PC작업확인` | `작업`, `대기:0` | 같은 작업의 상태·결과·종료 코드. `command_ok:true`가 작업 성공. 모든 접수증 메타데이터 보존 |
| `외부PC작업마무리` | `PC,작업들`, `산출물:[]`, `해제:false` | 전달한 작업만 재확인. 미종료·불명은 보류. 해제는 휴대형에만 허용 |
| `외부PC파일보내기` | `PC,중앙경로,원격경로,요청ID`, `대기:0`, `작업:{}` | 상주형. 원격 저장 완료 후 `verified:true,path,sha256`. 미완료면 반환값을 작업으로 재개 |
| `외부PC파일가져오기` | 위와 같음 | 상주형. 원격 전송 후 collect까지. `collected:true,path,sha256`가 중앙 저장 완료 |
| `외부PC깨워준비` | `PC,요청ID`, `대기:30`, `작업:{}` | 상주형. 오프라인이면 설정된 wake 경로 사용. info 실제 회신 때만 `ready:true,env` |
| `외부PC작업중지확인` | `작업`, `대기:0` | 취소 후 다시 확인. `stopped:true`만 중지 확인. 휴대형은 전달 전 취소만 가능 |
| `외부PC재생` | `PC,소스,요청ID`, `모드:"background"`, `실행제한:86400`, `작업:{}`, `음량:null` | 상주형. 원격 경로 또는 HTTP(S) 주소 재생 접수·상태 확인. 실제 소리·영상 검증은 별도 |

`PC`는 별칭 또는 device_id다. 반복 대상은 준비 결과의 device_id로 고정할 수 있다.
`대기`는 한 호출의 0~240초 대기이며 실행 제한과 다르다. 셸·재생 실행 제한은 1~86400초다.
`요청ID`는 **한 의도적 실행에 하나**를 정한다. 응답 유실 시 같은 인자·같은 ID를 재사용하고,
다시 실행하려는 새 의도에는 새 ID를 쓴다. 실행 관용구의 `환경초기화`는 휴대형 전용이다.
상주형은 `환경`을 매 작업에 전달한다. 비밀 입력은 정의·예제에 저장하지 않는다.

### 준비 → 셸 실행 → 확인 → 마무리

<!-- example:guestpc_prepare -->
```ibl
#!ibl edition=2
[fn:외부PC준비]{PC:"사무실PC"}
```

<!-- example:guestpc_run -->
```ibl
#!ibl edition=2
$준비 = [fn:외부PC준비]{PC:"사무실PC"}
[if:$준비.ok==false] { return $준비 }
return [fn:외부PC작업실행]{PC:$준비.limb,명령:"echo HELPER_OK",작업폴더:$준비.env.cwd,요청ID:"첫확인-예시-1",대기:10}
```

반환값 전체를 보존한다. `observation.command_ok`가 true가 아니면 작업 확인으로 이어간다.
별도 `execute_ibl` 호출에는 이전 변수가 자동으로 이어지지 않는다.
`inputs:{작업:실제로_받은_반환값}`으로 전달한다. 예시 ID·경로는 실제 관측값으로 바꾼다.

<!-- example:guestpc_check -->
```ibl
#!ibl edition=2
[fn:외부PC작업확인]{작업:$작업,대기:30}
```

- `ok`는 조회 성공, `command_ok`는 작업 성공, `settled`는 종료 확인이다.
- 상주형 `succeeded/failed`는 실제 결과의 성패다. 휴대형 `succeeded`는 회신 도착이므로
  종료 코드까지 확인한다. 관용구가 두 모드의 차이를 처리한다.
- `failed/cancelled/interrupted`는 종료된 실패·취소다. `unknown`은 결과 불명이며 재전송하지 않는다.
  대기의 실패 봉투도 상태·작업 참조로 복원하고, 상주형의 실패 원문은 history에서 가져온다.
- `timed_out:true`는 이번 대기가 끝났다는 뜻이다. 원격 작업은 계속될 수 있다.
- `observation_failed`는 조회 자체의 실패다. 원래 참조로 재확인한다.
- 상주형 진행은 `progress`의 최근 5건 미리보기, 최종 셸 출력은 `result.output`이다.
  휴대형 진행은 `progress.tail`, 출력은 기존 `stdout/stderr`다. 긴 로그는 아래 history로 읽는다.
- exit 0은 업무의 정확성을 보장하지 않는다. 파일 내용·검사 명령·화면으로 목적 달성을 확인한다.

### 대상 고정과 단계 실행

`외부PC준비`의 `작업폴더`와 `환경`은 사용자가 선택한 실행 환경이며 `env`의 OS 관측과
구분된다. 준비 결과는 `workspace`를 통해 다음 명령으로 전달된다. 다른 PC 이름과 조합하면
`target_mismatch`로 거절한다. 로컬 파일 도구의 대상을 몰래 바꾸는 전역 설정은 없다.

```ibl
#!ibl edition=2
$준비 = [fn:외부PC준비]{PC:"사무실PC",작업폴더:"/work/indiebizOS",환경:{PATH:"/opt/node/bin:/usr/bin:/bin"}}
[if:$준비.ok==false] { return $준비 }
return [fn:외부PC작업실행]{PC:$준비.limb,준비:$준비,명령:"python3 scripts/remote_steps.py /work/update-plan.json",요청ID:"update-plan-1",실행제한:86400}
```

실제 확인한 PC·경로·실행파일을 사용한다. 다음 호출에서 접수증 전체를 `작업`으로 전달하면
명령을 다시 제출하지 않는다. 명령·대상·폴더·제한·요청ID가 바뀌면 `resume_mismatch`다.
재관측에서 `환경`·`입력`을 바꿔도 기존 작업에는 전달되지 않는다. 바꾼 환경으로 실행할 때는
기존 작업의 종료를 확인하고 별도 실행을 요청한다. 상주 작업은 task_ref만 남았어도
`외부PC작업확인`이 중앙 원장에서 대상·작업 종류를 복원한다. 명시 대상이 다르면 거절한다.

**단계 실행기** `scripts/remote_steps.py`는 원격 PC에서 실행하는 표준 라이브러리 CLI다.
원격 배관·로그인·에이전트를 새로 만들지 않는다. 같은 CLI를 현지 AI도 사용할 수 있다.
계획은 `version:1, run_id, cwd(절대경로), env, steps`이며 각 단계는
`id, argv(문자열 배열), timeout, cwd(선택), verify(선택 argv)`다. 설치 명령 뒤의
`echo`나 `tail` 성공으로 원래 실패를 덮지 않는다. 셸 문자열을 argv로 포장하면 그 셸
내부의 실패까지 판별하지는 못하므로 설치·검사를 각각 별도 단계로 쓴다.

```json
{"version":1,"run_id":"build-1","cwd":"/work/project","steps":[
  {"id":"install","argv":["/opt/node/bin/npm","ci"],"timeout":1800},
  {"id":"build","argv":["/opt/node/bin/npm","run","build"],"timeout":1800}
]}
```

- 한 저장소에는 단계 실행기 하나만 동작한다. 결과·시도별 로그는 대상 PC의
  `data/runtime/remote_steps/<run_id>/`에 있고 `--status`로 현재 단계·로그 경로를 읽는다.
- 같은 계획을 다시 실행하면 완료 단계를 반복하지 않는다. verify가 있으면 결과를 다시
  검사한다. 실패 단계는 원인을 확인한 뒤 `--retry 단계ID`로 명시 재시도한다.
  명령 성공 뒤 검증만 실패했으면 검증만 재시도한다.
- 계획·PC·루트가 바뀌면 같은 run_id를 재사용할 수 없다. 프로세스 종료 기록이 없으면
  `interrupted/blocked`로 남기며 `--retry`도 자동 재실행하지 않는다. 프로세스·파일·서비스를
  확인한 후 남은 일을 새 계획으로 작성한다. 상태 파일을 지워 재시도하지 않는다.
- 실행기 시간제한은 단계별 제한이다. guestpc의 전체 실행제한도 별도로 넉넉히 둔다.
  로그·계획에는 비밀을 넣지 않는다. 각 단계의 성공은 선언한 명령·검증에 한정된다.

**IndieBiz 업데이트 조리법** `scripts/remote_install.py`는 이미 존재하는 소스 저장소와
Git·지원 Python·Node/npm을 사용한다. 없는 런타임은 OS·아키텍처를 확인하고 먼저 설치한다.
스크립트가 없는 구판 PC에는 이 두 스크립트를 원격 전송한 뒤 사용한다(backend/boot_paths.py가
있는 저장소의 scripts/ 위치). 현재 돌고 있는 설치와 중복 실행하지 않는다.

```sh
/absolute/python3 scripts/remote_install.py plan --root /work/indiebizOS --npm /opt/node/bin/npm --run-id update-1 --output /work/update-plan.json
/absolute/python3 scripts/remote_steps.py /work/update-plan.json
/absolute/python3 scripts/remote_steps.py /work/update-plan.json --status
```

조리법은 추적 변경·분기 이탈을 거절하고 fetch→fast-forward, 충돌하는 비추적/무시 파일 보존,
Git 추적 위치가 유일한 중복 패키지의 잔재 보존, venv·core/tools/ml·브라우저·npm·native rebuild·빌드,
import coverage·pip check·HEAD 일치를 확인한다. 백업은 `data/_backups/YYYY-MM-DD_이름/`다.
추적 변경을 버리거나 강제 reset/clean하지 않고, 기존 venv·API 키도 교체하지 않는다.
완료 후 앱을 실제로 시작하고 필요한 기능을 확인하는 것은 별도 검증이며 이 조리법은
실행 중인 앱을 자동 재기동하지 않는다. 최초 설치의 인증 설정·훈련용 선택 의존성은 포함하지 않는다.

현지 AI에 위임할 수 있으면 같은 목표·절대 저장소 경로·계획·검증 조건을 전달하고, 허브는
그 결과와 로그를 확인한다. 이미 연결된 위임 채널을 사용하며 새 에이전트 설치·인증은 가정하지 않는다.

<!-- example:guestpc_finish -->
```ibl
#!ibl edition=2
[fn:외부PC작업마무리]{PC:"사무실PC",작업들:[$작업],산출물:[],해제:false}
```

마무리는 받은 작업 목록만 검사하며 PC 전체 큐·다른 세션의 작업을 확인하지 않는다.
`산출물`은 보고할 원격 경로 목록일 뿐 다운로드·검증하지 않으며 `artifacts_verified:false`다.
상주형에서 `해제:true`는 `detach_not_supported`로 거절한다. 휴대형도 별도 작업이 돌고 있다면
해제하지 않는다. 등록 해제·헬퍼 제거는 사용자가 그것을 요청했을 때 별도로 한다.

### 파일 전송과 결과 회수

<!-- example:guestpc_send -->
```ibl
#!ibl edition=2
[fn:외부PC파일보내기]{PC:"사무실PC",중앙경로:"/central/input.zip",원격경로:"/remote/input.zip",요청ID:"자료전송-예시-1",대기:30}
```

<!-- example:guestpc_receive -->
```ibl
#!ibl edition=2
[fn:외부PC파일가져오기]{PC:"사무실PC",중앙경로:"/central/result.zip",원격경로:"/remote/result.zip",요청ID:"결과회수-예시-1",대기:30}
```

두 함수는 완료 전에 `ok:false`와 현재 상태·접수증을 돌려줄 수 있다. `queued/running`은 실패가
아니다. **같은 함수에 같은 인자와 `작업:이전_반환값`을 추가**하여 확인·collect를 이어간다.
`collect_failed`도 이 방식으로 중앙 저장만 재시도한다. 재개 인자가 바뀌면 `resume_mismatch`다.
셸·전송 실패는 자동 재실행하지 않는다. 원인을 고친 뒤 새 실행을 명시한다.

바이너리 청크·SHA-256 검증을 사용하며 파일 내용을 모델 문맥에 싣지 않는다. 경로는 대상 OS의
절대 경로다. 중앙 저장 폴더는 미리 존재해야 한다. 동일 내용의 저장 완료 파일은 재확인 가능하고,
다른 내용의 기존 파일은 덮어쓰지 않는다. 폴더는 ZIP 등으로 묶는다. 직접 어휘를 쓰는 경우:

```ibl
[limbs:guestpc]{op:"transfer",limb:"사무실PC",action:"receive",path:"/remote/result.bin",request_id:"수신-예시-1"}
# task_ref 완료 확인 후, 실제 받은 transfer_id를 넣는다.
[limbs:guestpc]{op:"transfer",action:"collect",limb:"사무실PC",transfer_id:"실제전송ID",local_path:"/central/result.bin"}
```

전송 접수 응답을 잃으면 같은 요청ID·인자로 원래 접수증을 회수한다. 직접 바이트 전송을
재개할 때는 같은 transfer_id를 쓰되 원래 작업이 여전히 실행 중인지 먼저 확인한다.
`verified:true`는 전송 바이트의 검증이며 파일 내용의 업무적 정확성 판정이 아니다.

### 깨우기와 재생·중지

WOL 경로는 먼저 한 번 설정한다. relay는 **대상 LAN에 켜진 PC의 ID/이름**이다.
중앙이 같은 LAN에 있을 때만 `central`을 쓴다. 경로 설정 호출은 신호를 보내지 않는다.

```ibl
[limbs:guestpc]{op:"wake",limb:"사무실PC",mac:"00:11:22:33:44:55",broadcast:"192.168.20.255",relay:"원격지중계PC"}
```

<!-- example:guestpc_wake -->
```ibl
#!ibl edition=2
[fn:외부PC깨워준비]{PC:"사무실PC",요청ID:"기동확인-예시-1",대기:30}
```

이 함수는 먼저 목록을 확인하고, 오프라인일 때만 저장된 경로로 신호를 보낸다. info 작업을
접수해 그 PC가 돌아와 실제 응답할 때까지 제한된 대기를 한다. 기다림이 끝나면 반환값을
`작업`으로 다시 넣어 같은 probe를 관측한다. 깨우기 성공·부팅·로그인·재생 준비는 다른 사실이다.
미설정 경로를 추측하거나 새로 구성하지 않는다. 기기별 WOL·동면·전원 꺼짐 지원은 실기기로 시험한다.

<!-- example:guestpc_media -->
```ibl
#!ibl edition=2
[fn:외부PC재생]{PC:"사무실PC",소스:"/remote/song.mp3",요청ID:"음악재생-예시-1"}
```

재생 관용구의 소스는 **원격 파일** 또는 HTTP(S) 주소다. 중앙 파일이면 먼저 파일보내기를
완료하고 그 원격 경로를 넘긴다. `모드:"interactive"`는 영상·사진, 기본 background는 오디오다.
mpv가 필요하며 Mac의 로컬 오디오는 afplay도 쓴다. 상주 헬퍼는 로그인 셸 PATH를 받지 못하므로 PATH 다음에 OS별 설치 위치(Homebrew·`/Applications`·`~/Applications/**/mpv.app` 앱 번들, Windows scoop·winget·choco)를 실행 가능 여부로 확인한다. 결과의 `player_path`가 실제 실행 파일이고, 못 찾으면 `needs_media_player`의 `searched`에 확인한 위치가 남는다. 새 바이너리를 설치한 PC부터 적용된다. `음량`은 생략하면 재생기 기본값, 지정하면 0~100이며 0도 전달한다. afplay에는 0~1로 환산한다. 재개 시 음량도 동일해야 한다. 로그인한 사용자의 오디오/화면 권한이 필요하다.
작업 `running`은 실행 시작이며 실제 소리·화면의 증명이 아니다(`playback_verified:false`).
플레이어 부재는 결과의 `needs_media_player`로 확인한다. 상태 확인은 반환값을 작업확인에
넘기거나 재생 관용구의 `작업`으로 전달한다. 중지는 그 접수증을 사용한다.

<!-- example:guestpc_stop -->
```ibl
#!ibl edition=2
[fn:외부PC작업중지확인]{작업:$작업,대기:30}
```

`cancel_requested`는 중지 요청만 접수된 상태다. `stopped:true`는 취소 종료가 확인된 경우다.
이미 성공·실패로 끝났으면 그 사실을 보존하며 취소된 것처럼 바꾸지 않는다.

## 3. 기본 어휘·GUI·작업 기록

```ibl
[limbs:guestpc]{op:"shell",limb:"사무실PC",cmd:"python --version",cwd:"C:/Users/Public",background:true,request_id:"파이썬확인-예시-1"}
[limbs:guestpc]{op:"info",limb:"사무실PC"}
[limbs:guestpc]{op:"list",limb:"사무실PC",path:"C:/Downloads"}
[limbs:guestpc]{op:"read",limb:"사무실PC",path:"C:/note.txt"}
[limbs:guestpc]{op:"write",limb:"사무실PC",path:"C:/out.txt",content:"내용"}
[limbs:guestpc]{op:"history",limb:"사무실PC"}
```

셸은 Windows cmd(선택 powershell), macOS/Linux `/bin/sh`다. read는 200KB 상한이 있으므로
바이너리·큰 파일은 transfer를 쓴다. `history`는 상주형 중앙 원장의 tasks/events이며
`job`으로 특정 작업, `cursor`로 이벤트 다음 페이지를 읽는다. 전건 로그를 단일 응답으로 가정하지 않는다.
일반 조회는 대기 결과를 바로 돌려주지만, 지연 가능성이 있으면 `background:true`로 접수증을 받는다.
동기 응답 제한을 넘겨도 접수된 명령은 재전송하지 않고 응답의 task_ref를 확인한다.

```ibl
[limbs:guestpc]{op:"screen",limb:"사무실PC",mode:"interactive"}
[limbs:guestpc]{op:"click",limb:"사무실PC",mode:"interactive",x:640,y:400}
[limbs:guestpc]{op:"type",limb:"사무실PC",mode:"interactive",text:"hello"}
[limbs:guestpc]{op:"key",limb:"사무실PC",mode:"interactive",key:"cmd+s"}
```

좌표는 **직전 screen 이미지에서 관측한 좌표**다. 예제 숫자를 그대로 사용하지 않는다.
헬퍼가 축소·레티나 배율을 환산한다. screen → 좌표 선택 → 입력 → 결과 화면 확인 순서다.
입력은 기본 재캡처(`shot:false`로 끄기), `settle_ms` 기본 700이다. type은 현재 포커스에 입력한다.
캡처는 `max_width` 기본 1280, `format` png/jpeg/auto, `display` 다중 모니터 선택이며
최근 20장이 `outputs/limb_screens/<별칭>/`에 남는다. move·scroll·drag도 같은 모드와 좌표 규칙이다.
셸로 되는 작업은 셸을 쓴다. GUI의 좌표를 관용구에 고정하지 않는다.

| OS | 화면·입력 조건 |
| --- | --- |
| Windows | 기본 OS API 사용. 관리자 창 입력은 헬퍼도 관리자 권한 필요 |
| macOS | 화면 기록·손쉬운 사용 권한. cliclick 설치 시 우클릭·드래그·정밀 이동 지원 |
| Linux | grim/scrot/ImageMagick 캡처 도구와 xdotool/ydotool 입력 도구 필요 |

권한 변경 뒤 헬퍼를 재실행한다. 실제 GUI 가능 여부는 info와 작업 결과로 확인한다.

## 4. 수명·해제·기록 보존

상주형 작업은 별도 workspace·프로세스·환경에서 실행한다. 같은 작업 ID를 중복 실행하지 않고
이벤트·결과를 중앙 ACK까지 보존한다. 재시작 중 결과를 잃으면 unknown으로 남기며 자동 재실행하지
않는다. 취소는 실행 중 자식까지 중지 요청한다. 작업 로그는 상한 뒤 log_gap을 표시한다.
CPU/메모리 하드 제한이나 OS 보안 샌드박스는 아니다. 현재 사용자의 권한으로 실행한다.

```ibl
[self:limb]{op:"pause",target:"사무실PC",paused:true}
[self:limb]{op:"pause",target:"사무실PC",paused:false}
# 등록 해제·헬퍼 제거를 명시적으로 요청받은 경우만:
[self:limb]{op:"remove",target:"사무실PC"}
```

remove는 새 작업을 차단하고 `removal_pending`으로 남는다. 기기의 제거 확인 뒤 `removed`다.
작업 폴더·USB 원본은 보존한다. 제거 접수만으로 제거 완료라고 보고하지 않는다.

휴대형 기존 사용:

```ibl
[self:limb]{op:"issue",alias:"휴대PC",ttl_days:14,os:"win"}
[limbs:guestpc]{op:"detach",limb:"휴대PC"}
[self:limb]{op:"revoke",target:"휴대PC"}
```

issue는 `outputs/limb_issue/<별칭>/`에 설정·실행파일·사용법을 만든다. ttl_days=0은 무기한이다.
유효한 키로 접속하면 자동 승인되며 명령의 limb 이름으로 오배송을 막는다. 대상은 항상 명시한다.
같은 키로 새 헬퍼가 붙으면 최신 세션이 이긴다. 위치 변경 알림은 키 유출 여부를 확인할 단서다.
휴대형 detach는 현재 프로세스만 종료하며 재실행하면 다시 붙는다. 영구 차단은 revoke다.
휴대형 환경은 유지되지만 함수·별칭은 유지되지 않는다. venv는 명시 실행 경로를 권장하며,
환경이 꼬이면 reset:true로 초기화한다. stdin으로 비대화형 입력을 줄 수 있다.

휴대형 전달 전 명령은 10분 뒤 만료, 완료 결과·회수 기록은 7일 보존한다. op:result는 호환
1회 회수이므로 반복 관측에는 self:task를 쓴다. 헬퍼는 사용자 설정 폴더의 delivery 원장에
수신·결과를 남기고 허브 확인까지 결과만 재전송한다. macOS 작업 중 유휴 잠자기를 막지만
덮개를 닫은 실행·항상 화면 켜짐을 보장하지 않는다. 이 배관은 최신 헬퍼 바이너리가 필요하다.

## 5. 등록·개정·검증과 빌드

정의 정본은 `data/idioms/guestpc_*.ibl`, 등록 자료는 `guestpc_seeds.json`이다.
기존 네 함수의 이름을 유지하며 선택 인자를 추가했다. 아래는 기존 정의의 명시 개정과 새 정의
등록을 함께 한다. SQLite backup 후 기존 개정 원장에 옛 정의·통계를 보존하고 신규 용례는
`add_examples_batch`로 등록한다. 벡터 색인까지 확인하며 상시 소개는 끈다.

```bash
.venv/bin/python3 scripts/register_webapp_idioms.py --seed-file guestpc_seeds.json --apply --local-encoder --revise-reason "상주 헬퍼 계약 정렬과 전송·깨우기·중지·재생 관용구 검증"
```

`--local-encoder`는 실행 중인 중앙 백엔드의 임베딩을 사용한다. 꺼져 있으면 이 옵션을 빼서
로컬 모델을 적재한다. 동일 자료의 재등록은 멱등이다. 검사: `backend/test_guestpc_idioms.py`,
`backend/test_guestpc_resident_idioms.py`, `backend/test_resident_pcs.py`. 임시 중앙 원장과 실제
핸들러·IBL 실행기를 연결해 검사하며 OS 설치·WOL·실제 오디오 출력 검증은 별도다.

헬퍼는 `helper/`의 Go 소스를 `helper/build.sh`로 빌드한다. macOS 10.15~11 Intel은
Go 1.22와 `go.legacy.mod`를 쓰는 `mac-amd64-legacy`를 사용한다. 일반 mac-amd64는 macOS 12
이상이 필요하다. 실제 기기 호환성은 실기기 시험으로 확정한다. 발급 폴더 실행파일을 갱신할 때
기존 `indiebiz-helper.json` 키를 재발급·교체하지 않는다.
설치·제거 세부 사항은 `helper/README.md`, 설계는 `docs/REMOTE_PC_RESOURCE_DESIGN_2026_10_10.md`.

남의 PC에서 실행할 때는 그 PC 주인의 동의가 전제다. 허브·터널 연결이 필요하고 서명 없는
바이너리는 OS 경고가 나타날 수 있다. 손발 실행 자격은 이웃 등급 자동 부여와 별개다.


## 49회차 수리: 재관측과 재시도

- 이름 조회는 폐기·만료·제거된 같은 별칭을 제외한다. device_id 명시는 그 등록 자체를
  검사하므로 폐기된 ID를 다른 기기로 바꾸지 않는다. 유효한 동명 기기는 여전히 거절한다.
- 상주 shell은 동기·background 모두 기본 실행 제한 1800초다. background는 접수 후 기다릴지의
  선택이며 명령 신원을 바꾸지 않는다. 명시 timeout 변경은 다른 명령이다. 동기 결과도 반복 회수된다.
- `history.tasks`와 `외부PC작업확인`에 `started_at`·`ended_at`(기기 epoch 시각), `seconds`가 있다.
  출력 페이지와 독립이므로 긴 출력도 종료 시각을 숨기지 않는다. 관측되지 않은 시각은 null이다.
  progress는 최근 사건 5건의 미리보기(로그당 최대 2000자); `progress_scope`와 `history_args`가
  전체 기록 조회를 안내한다. 전문은 history의 cursor로 읽는다. 결과 원문은 별도 result에 보존한다.
- 전송 조각은 128KiB이며 일시 네트워크 오류·408/429/5xx만 같은 offset으로 최대 5번 시도한다.
  작업 취소·전체 제한은 HTTP 대기에도 적용된다. 같은 offset·같은 바이트는 중복 저장하지 않는다.
  허브 저장소의 `committed`는 중앙 적재 완료이며 원격 전달 완료는 작업 결과와 SHA-256으로 확인한다.
- 같은 요청ID는 끝난 실패도 그대로 관측한다. **실패 종료를 확인한 전송만** 새 요청ID와 기존
  transfer_id로 다시 접수한다. 보내기·가져오기 관용구의 `전송ID` 인자가 이를 전달한다.
  `.part`를 이어 받고 지문을 다시 확인한다. 새 시도의 요청ID도 재사용하므로 접수 응답 유실 시
  중복 작업을 만들지 않는다. 진행 중·결과 미확인 작업에는 새 요청ID를 만들지 않는다.

```ibl
// $실패는 종료된 failed 전송의 접수증. 동일한 파일·원격경로만 재개한다.
return [fn:외부PC파일보내기]{PC:$실패.pc_request,중앙경로:$실패.local_path,
  원격경로:$실패.remote_path,요청ID:"원래일감-send-retry-1",전송ID:$실패.transfer_id,대기:60}
```

큰 텍스트도 read를 반복하지 말고 transfer receive→collect로 가져온다. 원격 read에는 offset·limit가 없다.
`압축`은 UTF-8 표시 없는 ZIP 이름도 유효한 UTF-8이면 같은 이름으로 목록·필터·추출한다.
옛 코드페이지와 모호한 이름은 `name_encoding:"cp437"` 또는 `"cp949"`로 명시한다.
info의 패키지 관리자는 OS별 후보만 확인하며 macOS의 Java apt를 Linux 패키지 관리자로 세지 않는다.
헬퍼 수정(조각 재시도·환경 조회)은 새 바이너리를 설치한 PC부터 적용된다.


## 50회차 수리: 작업 종료·출력·확인 자리

- `외부PC작업확인`은 실패·취소·불명에서도 한 번의 작업 조회로 시각·진행·결과 원문을 보존한다.
  `status`는 기존 상태이고 `outcome`은 시간제한 종료를 `timeout`으로 구별한다.
  `timed_out:true`는 이번 조회의 대기만 끝났다는 뜻이며 작업의 시간제한 종료와 다르다.
- 셸이 0으로 끝났지만 자식이 출력 통로를 계속 잡고 있으면 수집을 2초 뒤 닫고
  `exit:0`, `output_incomplete:true`, `warning`을 반환한다. 명령 성공과 출력 수집 완료는 다르다.
  서버가 이미 떠 있을 수 있으므로 다시 실행하지 말고 PID·응답을 확인한다. 오래 띄울 자식은
  `nohup command >server.log 2>&1 </dev/null &`처럼 통로를 분리한다. 출력 일부는 보존되며
  자식의 계속 실행이나 서비스 준비 완료를 이 경고만으로 보증하지 않는다.
- 새 헬퍼의 일반 작업 자리는 2개이고, `info/list/read/screen` 확인 자리는 별도로 1개다.
  짧은 셸 확인은 `mode:"observe",timeout:5`처럼 명시한다(1~10초만 허용). 셸 내용을
  읽기 전용으로 강제하는 기능은 아니므로 긴 작업을 이 자리에 넣지 않는다. 이 자리도
  취소·일시정지·접수 중복 방지를 동일하게 따른다. 자리마다 접수 순서를 보존한다.
- 관용구에서는 `외부PC작업실행`의 `모드:"observe",실행제한:5`로 지정한다.
  `registration.capabilities.observation_parallel:1`인 헬퍼부터 지원하며 기존 설치는
  새 바이너리 적용이 필요하다. 중앙 원장 `history`·`self:task` 조회는 원격 실행 자리를 쓰지 않는다.

```ibl
// 긴 작업 두 개가 실행 중이어도 별도 자리에서 상태 확인
return [fn:외부PC작업실행]{PC:"사무실PC",명령:"ps -o pid,ppid,command -p 1234",
  작업폴더:"/tmp",모드:"observe",실행제한:5,요청ID:"상태확인-1",대기:10}
```

### 화면 관측과 대기 종료

화면 촬영은 짧은 확인 자리에서 실행하며 일반 작업 둘의 종료를 기다리지 않는다.
동기 screen의 60초 대기가 끝나면 해당 촬영의 취소를 요청한다. 취소 요청은 종료 증명이
아니며 반환된 task_ref로 self:task status/wait를 확인한다. 이미 끝난 촬영은 원래 결과를
보존한다. background:true로 명시 접수한 촬영은 접수증의 수명을 따르며 직접 취소한다.
새 헬퍼는 취소를 캡처 프로세스까지 전달한다. 구형 헬퍼의 실행 중 촬영에는 이 보장이 없다.

캡처 성공은 이미지 획득 성공이다. image_observation:uniform과 warning은 원본 화소가
모두 같은 색임을 나타낸다. 화면 전원 꺼짐·잠금·권한 문제·실제 단색 화면은 이 관측만으로
구별할 수 없다. 입력이나 전원 설정 변경으로 자동 보정하지 않는다.

history는 화면 결과의 b64를 생략하고 image_omitted와 image_task_ref를 제공한다.
원장의 원본 바이트는 보존하며 해당 접수증의 self:task 조회로 회수할 수 있다.


## 사람이 직접 다루는 화면 공유

조종실 → 손발 (USB) → 등록된 PC의 **화면 공유**를 누른다. Mac·Windows·Linux
헬퍼가 화면·마우스·키보드를 연결하며 내부망 연결을 먼저 시도하고 외부 WSS로 자동
폴백한다. 별도 VNC 설정이나 경로 선택은 없다. 기존 설치는 헬퍼 교체가 필요하다.
화면 접근은 설치 시 해당 OS에서 허용하며 Wayland는 포털의 동의 정책을 따른다.
현재 로그인한 그래픽 세션이 대상이다. 영상·입력은 작업 기록에 저장하지 않는다.

## 모든 폴더·외장 드라이브와 관리자 명령

상주 작업의 workspace는 기본 위치다. 절대 cwd/path로 사용자 권한이 허용하는 마운트된
모든 경로를 쓴다. Mac의 보호 폴더에는 설치된 헬퍼의 전체 디스크 접근 권한도 필요하다.
상주 shell의 `elevate:true`는 **원격 PC의 OS 인증창**을 열고 승인된 이번 명령만 관리자
권한으로 실행한다. 비밀번호는 채팅·cmd·stdin·env에 담지 않는다. 권한이 필요한 파일
작업은 이 관리자 셸로 한다. 잠긴 볼륨·읽기 전용 볼륨·OS 보호를 자동 해제하지 않는다.

`[limbs:guestpc]{op:"shell",limb:"사무실PC",cmd:"id",elevate:true,background:true}`

관리자 인증은 사람이 원격 PC 화면에서 완료한다. Windows UAC 보안 데스크톱은 사용자
헬퍼에서 제어할 수 없어 로컬 승인이 필요하다. 취소·시간 초과·헬퍼 종료는 관리자 명령도
종료한다. 이전 헬퍼·휴대형·mode:observe는 elevate를 지원하지 않는다.

플랫폼별 설치·권한·연결·수명 계약은 `helper/README.md`를 따른다.
