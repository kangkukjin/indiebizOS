# 원격 PC 실행 드라이버 — 셸·접수증·전송

## 빠른 호출

원격 셸·파일은 선택한 PC의 device_id를 `PC`로 전달한다. 상주형의 작업폴더·환경은 작업별로 분리되고 휴대형은 유지된다. 요청ID는 중복 접수를 식별한다.
- 셸: `[fn:외부PC작업실행]{PC:$PC,명령:"echo HELPER_OK",요청ID:"진단-1"}`. `ok:true`는 접수이며 성공은 `observation.command_ok:true`와 결과의 종료 코드로 확인한다.
- 이어보기: `[fn:외부PC작업확인]{작업:$원결과,대기:30}`. 원 반환값·task_ref로 같은 작업을 조회한다. 대기 종료·통신 불명은 명령 종료를 뜻하지 않는다.
- 전송: `fn:외부PC파일보내기`·`fn:외부PC파일가져오기`의 describe로 PC·중앙경로·원격경로·요청ID 계약을 조회한다. 전송 접수와 실제 저장·지문 검증은 다르다.
- 목록·진단·원문: `self:limb` list, `limbs:guestpc` info/history. 원격 파일은 같은 대상의 read/list 또는 transfer를 쓴다. `self:file_find`는 허브 검색이다.
- 부족한 인자는 `execute_ibl(code="",describe=["fn:외부PC작업실행"])`. 원시 op 전체 계약은 describe의 `limbs:guestpc`, 긴 작업 상태는 `self:task`다. 화면은 `pc_control.md`, 설치·권한·교체는 `remote_pc_installation.md`를 필요한 절만 읽는다.

## 호출 계약과 대상 고정

등록 함수의 인자·기본값은 describe가 정본이다. `외부PC준비`, `외부PC작업실행`, `외부PC작업확인`, `외부PC작업마무리`, `외부PC파일보내기`, `외부PC파일가져오기`, `외부PC깨워준비`, `외부PC작업중지확인`, `외부PC재생`을 이름으로 조회한다.

`PC`는 별칭 또는 device_id다. 반복 대상은 준비 결과의 device_id로 고정할 수 있다.
`대기`는 한 호출의 0~240초 대기이며 실행 제한과 다르다. 셸·재생 실행 제한은 1~86400초다.
`요청ID`와 인자가 같으면 기존 접수증을 반환한다. 같은 ID에 다른 인자는 충돌이며 새 ID는 별도 실행이다. 실행 관용구의 `환경초기화`는 휴대형 전용이다.
상주형의 `환경`은 해당 작업에만 적용된다.

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

`외부PC작업확인`은 이전 반환값을 입력받는다. 별도 `execute_ibl` 호출에는 변수가 자동 계승되지 않으며
`inputs:{작업:이전_반환값}`으로 전달할 수 있다. 예시 ID·경로는 자리표다.
`작업`은 전체 접수증 또는 `{kind:"guestpc",task_id:"실제 ID"}` 참조를 받는다.
`self:task`의 참조 인자는 `ref`다(`task_ref`는 반환 필드).

<!-- example:guestpc_check -->
```ibl
#!ibl edition=2
[fn:외부PC작업확인]{작업:$작업,대기:30}
```

- `ok`는 조회 성공, `command_ok`는 작업 성공, `settled`는 종료 확인이다.
- `exit`·`progress`·`result`·`failure`는 실패 응답에도 있으며 미관측이면 null이다.
  잘못된 참조는 `invalid_input`으로 반환하고 원격 명령을 접수하지 않는다.
- 상주형 `succeeded/failed`는 실제 결과의 성패다. 휴대형 `succeeded`는 회신 도착이므로
  종료 코드까지 확인한다. 관용구가 두 모드의 차이를 처리한다.
- `failed/cancelled/interrupted`는 종료된 실패·취소다. `unknown`은 결과 불명이며 일부 효과가 발생했을 수 있다.
  대기의 실패 봉투도 상태·작업 참조로 복원하고, 상주형의 실패 원문은 history에서 가져온다.
- `timed_out:true`는 이번 대기가 끝났다는 뜻이다. 원격 작업은 계속될 수 있다.
- `observation_failed`는 조회 자체의 실패다. 원래 참조로 재확인한다.
- 상주형 직접 상태 조회의 진행은 `progress`의 최근 5건 미리보기, 최종 셸 출력은 `result.output`이다.
  관용구의 `history_cursor`: 새 진행만 조회, 결과 보존.
  휴대형 진행은 `progress.tail`, 출력은 기존 `stdout/stderr`다. 긴 로그는 아래 history로 읽는다.

상세 계약: `docs/REMOTE_PC_SETUP_VERIFICATION.md` 「완료 대기와 진행 관측」.

### 대상 고정과 단계 실행

준비의 device_id·workspace를 다음 호출에 보존한다. 다른 PC와 조합하면 target_mismatch, 재관측에 명령·폴더·제한·요청ID를 바꾸면 resume_mismatch다. 환경·입력 변경은 기존 작업에 전달되지 않는다.
설치·빌드 계획과 remote_steps는 [원격 설치 검증](../../docs/REMOTE_PC_SETUP_VERIFICATION.md)을 따른다.

소스 업데이트의 새 계획은 기존 환경으로 빌드·import·`pip check`·브라우저·기동을 확인한다.
의존성 자동 설치와 재사용 영수증 판정은 없다. 실패 원문으로 AI가 필요한 조치를 판단한다.
이미 생성된 계획은 당시 명령을 보존한다.

화면 빌드 뒤 새 계획의 `resume-runtime --prebuilt`는 preview 화면을 다시 빌드하지 않고 Electron을
직접 실행한다. 빌드된 dist의 지문과 HEAD를 기동 영수증에 저장하고 재시작 재시도에서도 대조한다.
dev 실행은 기존 Vite 개발 서버 경로를 유지한다. 옛 계획에는 이 옵션이 없으므로 기존 동작을 따른다.
새 Electron은 같은 창의 nonce에 백엔드 기동·종료 코드·spawn 오류를 기록한다. 업데이트 드라이버는
자기가 시작한 프로세스 트리의 새 창에서 온 실패만 즉시 반환한다. 옛 앱의 실패 기록은 쓰지 않는다.

`remote_steps.py <plan.json> --status`는 저장된 단계와 별도로 `live`에 단계 경과 시간,
프로세스 생존·누적 CPU 시간·로그 크기/수정 시각, 종료·기동 대기 이유를 반환한다. 조회는 실행하지
않으며 프로세스 종료를 성공으로 간주하지 않는다. 종료 대기는 활성 작업/자식/마무리 수를 주기적으로
기록한다. CPU 시간은 누적값, 로그 크기·시각은 해당 조회 시점의 값이다.
최종 완료는 여전히 설치 단계 성공과 백엔드·새 화면의 실제 기동 검증을 모두 필요로 한다.

<!-- example:guestpc_finish -->
```ibl
#!ibl edition=2
[fn:외부PC작업마무리]{PC:"사무실PC",작업들:[$작업],산출물:[],해제:false}
```

마무리는 받은 작업 목록만 검사하며 PC 전체 큐·다른 세션의 작업을 확인하지 않는다.
`산출물`은 보고할 원격 경로 목록일 뿐 다운로드·검증하지 않으며 `artifacts_verified:false`다.
상주형의 `해제:true`는 `detach_not_supported`다. 휴대형의 detach는 헬퍼 프로세스를 종료하며 다른 작업에도 영향을 준다. 등록 제거는 별도 API다.

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
관용구는 셸·전송 실패 뒤 새 작업을 자동 접수하지 않는다.

바이너리 청크·SHA-256 검증을 사용하며 파일 내용을 모델 문맥에 싣지 않는다. 경로는 대상 OS의
절대 경로다. 중앙 저장 폴더는 미리 존재해야 한다. 동일 내용의 저장 완료 파일은 재확인 가능하고,
다른 내용의 기존 파일은 덮어쓰지 않는다. 전송 단위는 파일이며 디렉터리 자체는 지원하지 않는다. 직접 어휘를 쓰는 경우:

```ibl
[limbs:guestpc]{op:"transfer",limb:"사무실PC",action:"receive",path:"/remote/result.bin",request_id:"수신-예시-1"}
# task_ref 완료 확인 후, 실제 받은 transfer_id를 넣는다.
[limbs:guestpc]{op:"transfer",action:"collect",limb:"사무실PC",transfer_id:"실제전송ID",local_path:"/central/result.bin"}
```

전송 접수 응답을 잃으면 같은 요청ID·인자로 원래 접수증을 회수한다. 바이트 전송 재개는 같은 transfer_id의 offset 계약을 사용한다.
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
WOL의 실제 부팅 가능 상태는 기기의 전원·네트워크 설정에 달려 있다.

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
PC 가 10분 안에 끌어가지 않은 명령(꺼짐·끊김)은 `failed` 에 `error:"expired"` 로 닫힌다.

## 3. 기본 어휘·GUI·작업 기록

```ibl
[limbs:guestpc]{op:"shell",limb:"사무실PC",cmd:"python --version",cwd:"C:/Users/Public",background:true,request_id:"파이썬확인-예시-1"}
[limbs:guestpc]{op:"info",limb:"사무실PC"}
[limbs:guestpc]{op:"list",limb:"사무실PC",path:"C:/Downloads"}
[limbs:guestpc]{op:"read",limb:"사무실PC",path:"C:/note.txt"}
[limbs:guestpc]{op:"write",limb:"사무실PC",path:"C:/out.txt",content:"내용"}
[limbs:guestpc]{op:"history",limb:"사무실PC"}
```

새 helper(`shell_contract:2`)의 기본 셸은 Windows PowerShell 5.1, macOS/Linux `/bin/sh`다.
기존 배치/CMD 문법은 `shell:"cmd"`, PowerShell 7은 `shell:"pwsh"`를 명시한다.
선택한 셸이 없으면 실패하며 다른 방언으로 바꾸지 않는다. PowerShell은 실행 전 구문 검사,
cmd는 실행 후 종료 코드·오류 진단을 AI에게 전달한다. 구형 helper의 기본값은 info의 능력으로 확인한다. read는 200KB 상한이 있으므로
바이너리·큰 파일은 transfer를 쓴다. `history`는 상주형 중앙 원장의 tasks/events이며
`job`으로 특정 작업, `cursor`로 이벤트 다음 페이지를 읽는다. 응답은 페이지 단위다.
일반 조회는 대기 결과를 바로 돌려주지만, 지연 가능성이 있으면 `background:true`로 접수증을 받는다.
동기 응답 제한이 끝나도 접수된 명령은 계속 실행될 수 있고 task_ref로 조회된다.

## 재관측과 전송 재시도

- 이름 조회는 폐기·만료·제거된 같은 별칭을 제외한다. device_id 명시는 그 등록 자체를
  검사하므로 폐기된 ID를 다른 기기로 바꾸지 않는다. 유효한 동명 기기는 여전히 거절한다.
- 상주 shell은 동기·background 모두 기본 실행 제한 1800초다. background는 접수 후 기다릴지의
  선택이며 명령 신원을 바꾸지 않는다. 명시 timeout 변경은 다른 명령이다. 동기 결과도 반복 회수된다.
- `history.tasks`와 `외부PC작업확인`에 `started_at`·`ended_at`(기기 epoch 시각), `seconds`가 있다.
  출력 페이지와 독립이므로 긴 출력도 종료 시각을 숨기지 않는다. 관측되지 않은 시각은 null이다.
  progress는 최근 사건 5건의 미리보기(로그당 최대 2000자); `progress_scope`와 `history_args`가
  전체 기록 조회를 안내한다. 전문은 history의 cursor로 읽는다. 결과 원문은 별도 result에 보존한다.
- 새 PC 헬퍼는 1MiB 바이너리 배치를, Android는 512KiB 배치를 협상한다. 구형 PC의
  128KiB JSON 경로도 유지한다. 인증된 LAN 우선, 외부 허브 폴백.
  일시 네트워크 오류·408/429/5xx는 같은 offset으로 최대 5번 시도한다.
  작업 취소·전체 제한은 HTTP 대기에도 적용된다. 같은 offset·같은 바이트는 중복 저장하지 않는다.
  허브 저장소의 `committed`는 중앙 적재 완료이며 원격 전달 완료는 작업 결과와 SHA-256으로 확인한다.
- 같은 요청ID는 끝난 실패도 그대로 관측한다. **실패 종료를 확인한 전송만** 새 요청ID와 기존
  transfer_id로 다시 접수한다. 보내기·가져오기 관용구의 `전송ID` 인자가 이를 전달한다.
  `.part`를 이어 받고 지문을 다시 확인한다. 새 시도의 요청ID도 재사용하므로 접수 응답 유실 시
  중복 작업을 만들지 않는다. 진행 중·결과 미확인 작업에는 새 요청ID를 만들지 않는다.

```ibl
#!ibl edition=2
# $실패는 종료된 failed 전송의 접수증. 동일한 파일·원격경로만 재개한다.
return [fn:외부PC파일보내기]{PC:$실패.pc_request,중앙경로:$실패.local_path,
  원격경로:$실패.remote_path,요청ID:"원래일감-send-retry-1",전송ID:$실패.transfer_id,대기:60}
```

원격 read에는 offset·limit가 없다. 상한보다 큰 파일의 회수 경로는 transfer receive→collect다.
`압축`은 UTF-8 표시 없는 ZIP 이름도 유효한 UTF-8이면 같은 이름으로 목록·필터·추출한다.
옛 코드페이지와 모호한 이름은 `name_encoding:"cp437"` 또는 `"cp949"`로 명시한다.
info의 패키지 관리자는 OS별 후보만 확인하며 macOS의 Java apt를 Linux 패키지 관리자로 세지 않는다.
헬퍼 수정(조각 재시도·환경 조회)은 새 바이너리를 설치한 PC부터 적용된다.


## 작업 종료·출력·확인 자리

- `외부PC작업확인`은 실패·취소·불명에서도 한 번의 작업 조회로 시각·진행·결과 원문을 보존한다.
  `status`는 기존 상태이고 `outcome`은 시간제한 종료를 `timeout`으로 구별한다.
  `timed_out:true`는 이번 조회의 대기만 끝났다는 뜻이며 작업의 시간제한 종료와 다르다.
- 셸이 0으로 끝났지만 자식이 출력 통로를 계속 잡고 있으면 수집을 2초 뒤 닫고
  `exit:0`, `output_incomplete:true`, `warning`을 반환한다. 명령 성공과 출력 수집 완료는 다르다.
  출력 일부는 보존되며 자식 생존·서비스 준비 상태는 이 반환만으로 확인되지 않는다.
- 새 헬퍼의 일반 작업 자리는 2개이고, `info/list/read/screen` 확인 자리는 별도로 1개다.
  짧은 셸 확인은 `mode:"observe",timeout:5`처럼 명시한다(1~10초만 허용). 셸 내용을
  읽기 전용을 강제하는 기능은 아니며 일반 작업과 별도 실행 한도를 적용한다. 이 자리도
  취소·일시정지·접수 중복 방지를 동일하게 따른다. 자리마다 접수 순서를 보존한다.
- 관용구에서는 `외부PC작업실행`의 `모드:"observe",실행제한:5`로 지정한다.
  `registration.capabilities.observation_parallel:1`인 헬퍼부터 지원하며 기존 설치는
  새 바이너리 적용이 필요하다. 중앙 원장 `history`·`self:task` 조회는 원격 실행 자리를 쓰지 않는다.

```ibl
#!ibl edition=2
# 긴 작업 두 개가 실행 중이어도 별도 자리에서 상태 확인
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
구별할 수 없다.

history는 화면 결과의 b64를 생략하고 image_omitted와 image_task_ref를 제공한다.
원장의 원본 바이트는 보존하며 해당 접수증의 self:task 조회로 회수할 수 있다.



## 설치와 권한

상주/휴대 모드, 관리자 인증, 무인관리, 제거는 [설치 관리](remote_pc_installation.md). OS 음량·화면·앱·재생은 [PC 제어](pc_control.md).
