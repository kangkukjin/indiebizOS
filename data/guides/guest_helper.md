# USB 손발(게스트 PC 헬퍼) 가이드 — [self:limb] 발급 · [limbs:guestpc] 조작

낯선 PC 에 **USB 를 꽂아** 그 PC 에서 셸·파일 작업을 시키는 얇은 손발(헬퍼) 시스템.
두뇌·신원은 전부 내 몸(허브)에 남고, USB 엔 **허브 비밀번호가 아니라 limb key 하나**만 실린다.
"USB 에 AI 를 담는" 게 아니라 **USB 를 내 몸의 착탈식 손발로 만드는** 것.

## 구조 (폰↔PC 직접 연결 아님 — 둘 다 허브를 거친다)

```
내 폰/런처 ──(터널)──> 내 허브(두뇌·신원) <──(그 PC 인터넷, 아웃바운드)── 게스트 PC 의 헬퍼(손발)
```

헬퍼는 그 PC 에서 허브로 **아웃바운드** 접속(그 PC 방화벽·공유기 무설정). 허브가 셸 명령을
큐에 넣으면 헬퍼가 `/limb/poll` 롱폴로 당겨가 실행하고 `/limb/result` 로 회신한다. 폰이
LTE(CGNAT) 뒤에서 명령을 당겨가는 구조(phone_jobs)를 그대로 쓴다.

## 1) 발급 — USB 만들기

```
[self:limb]{op: "issue", alias: "사무실PC", ttl_days: 14, os: "win"}
```

- 새 limb key 를 만들고 `outputs/limb_issue/<alias>/` 에 **USB 페이로드**를 쓴다:
  `indiebiz-helper.json`(내 몸 주소 + 키 + 이름) + `사용법.txt`.
- `os`(win/mac/linux)를 주고 `helper/dist/` 에 빌드된 실행파일이 있으면 함께 동봉한다.
- 이 폴더 전체를 USB 에 복사한다.
- `ttl_days` 유효기간이 지나면 키가 자동 소멸(잊고 폐기 안 해도 안전). `0`=무기한.
- ★주소는 **직접 서빙 호스트(direct_hosts)** 로 박힌다 — Worker CDN 은 `/limb/` 를 프록시하지
  않으므로. 공개 주소(터널/얼굴)가 아직 없으면 `warning` 이 뜬다(먼저 터널 발급 필요).

## 2) 실행 — 그 PC 에서 헬퍼 띄우기

USB 를 그 PC 에 꽂고 헬퍼 실행파일을 더블클릭한다(`indiebiz-helper.json` 이 같은 폴더에
있어야 함). 헬퍼가 내 허브에 붙으면 **자동으로 연결(승인)** 되어 바로 쓸 수 있다.

## 3) 이름으로 명령 — 오배송 방어

반복 작업은 아래 **「등록 관용구 — 준비·실행·확인·마무리」**의 `[fn:외부PC준비]`부터
시작할 수 있다. 기본 어휘는 아래와 같고, 관용구는 같은 어휘를 조합한다.

```
[limbs:guestpc]{op: "shell", cmd: "python --version", limb: "사무실PC"}   # 이름으로 대상 지정
[limbs:guestpc]{op: "shell", cmd: "dir", cwd: "C:/Users", limb: "사무실PC"}
[limbs:guestpc]{op: "list", path: "C:/Downloads", limb: "사무실PC"}
[limbs:guestpc]{op: "read", path: "C:/note.txt", limb: "사무실PC"}
[limbs:guestpc]{op: "write", path: "C:/out.txt", content: "…", limb: "사무실PC"}
[limbs:guestpc]{op: "info", limb: "사무실PC"}
```

**낯선 PC 의 첫 명령은 `info` 로.** os·버전·사용자·관리자여부·PATH·설치된 셸/패키지매니저/
도구·눈과 손이 되는지·화면 해상도를 한 번에 준다. 이걸 안 보고 명령 문법과 패키지매니저를
추측하면(`apt` 인가 `winget` 인가, 관리자 권한이 있나) 실패 왕복이 쌓인다 — 그 왕복이 곧 지연이다.

같은 프로브를 **헬퍼가 접속할 때 이미 한 번 올려두므로**, 명령을 보내기 전에도
`[self:limb]{op:"list"}` 의 `env` 로 그 PC 가 어떤 기계인지 볼 수 있다(왕복 0).

**승인은 자동이다** — 붙는 즉시 명령을 받는다. 대신 안전의 무게중심이 *승인 게이트*에서
*이름 명시*로 옮겨갔다: 명령할 때 `limb: "이름"` 으로 어느 PC 인지 지정한다(발급 시 지은
alias). 손발이 **둘 이상이면 이름은 필수** — 이름 없이 부르면 실행하지 않고 붙어 있는
목록을 보여준다. 이 강제가 곧 방어다: 유출된 키로 낯선 PC 가 하나 더 붙으면 손발이 둘이
되어 이름을 요구받고, 그때 "어? 손발이 둘이네?" 하고 알아챈다. 결과에는 어느 손발에서
돌았는지(`limb_name`)가 늘 찍혀 사후에도 확인된다.

- 손발이 하나뿐이면 `limb` 생략 가능(그 하나로 감).
- 다른 PC 에서 같은 키가 붙으면 자동승인하되 **위치 변경 알림**이 뜬다(내가 안 옮겼으면 유출 신호 → revoke).
- 특정 손발을 잠시 막고 싶으면 `[self:limb]{op:approve, target:"이름", approved:false}`(수동 잠금).
- 셸은 그 PC 의 기본 셸(win=`cmd`, mac·linux=`sh`). `timeout`(초, 기본 120).
  윈도우는 `shell: "powershell"` 로 갈아탈 수 있다(cmd 가 빈약할 때).
- **`cd` 와 환경변수가 유지된다**: `cwd` 를 생략하면 직전 명령이 끝난 자리에서 이어지고,
  `export`·`source .venv/bin/activate` 로 바뀐 환경변수도 다음 명령까지 간다. 결과의
  `cwd`·`session_env`(이어지는 변수 개수)가 지금 상태다.

  ```
  [limbs:guestpc]{op:"shell", cmd:"cd /prj && source .venv/bin/activate"}
  [limbs:guestpc]{op:"shell", cmd:"pip install requests"}   # ← 그 venv 의 pip 이 돈다
  ```

  단 **셸 함수·별칭은 이어지지 않는다** — 상주 셸이 아니라 매번 새 셸에 환경만 다시
  깔아주기 때문이다(상주 셸을 안 쓴 이유: 명령이 병렬 실행돼 셸 하나를 공유하면 출력이
  섞이고 긴 명령이 다른 명령을 막는다). 그래서 `deactivate` 같은 *함수*는 부를 수 없다 —
  venv 를 벗거나 환경이 꼬였으면 **`reset: true`**(기억한 디렉토리·환경을 버리고 그 PC
  원래 환경으로).
- **대화형 명령**: `stdin` 으로 프롬프트 입력을 미리 물린다(`stdin: "y\n"`,
  `cmd: "sudo -S ..."` + 비밀번호). stdin 을 안 주면 프롬프트는 EOF 를 받고 곧장 끝나므로
  타임아웃까지 멈추지는 않는다. ★비밀번호를 여기 적기 전에 `-y`·`--silent` 같은
  비대화형 플래그가 있는지 먼저 볼 것.
- **긴 명령의 중간 경과**: `background: true` 로 보낸 명령은 `op:"result"` 가 아직
  안 끝났을 때 `progress.tail`(지금까지의 출력 꼬리)과 누적 바이트를 함께 준다 —
  **진행 중인지 멎었는지 이걸로 판단**하고, 절대 같은 명령을 재전송하지 말 것(이중 실행).
  짧은 명령엔 중계가 없다(6초 넘게 도는 명령만 스스로 말하기 시작한다).
- **한 손발엔 헬퍼 하나**: 같은 키로 헬퍼가 새로 붙으면 **최신이 이기고** 낡은 쪽은
  "다른 곳에서 다시 연결되어 물러납니다" 를 찍고 스스로 종료한다. USB 를 다른 PC 로
  옮기는 정상 로밍이 저절로 정리되고, 두 헬퍼가 큐를 나눠 가져 명령이 어느 PC 에서
  도는지 모르게 되는 사고를 막는다(옛 빌드에서 실측된 문제).

### 눈과 손 — 화면 보기 · GUI 조작 (2026-08-03 신설)

셸만으로는 "눈 감고 타이핑"이다. 설치 마법사 다이얼로그도, 에러 팝업도, 창이 정말 떴는지도
보이지 않아 검증 없이 다음 명령으로 넘어가게 된다. 그래서 **눈**(screen)과 **손**(입력)을 얹었다.

```
[limbs:guestpc]{op: "screen", limb: "사무실PC"}                       # 그 화면을 AI 가 직접 본다
[limbs:guestpc]{op: "click", x: 640, y: 400, limb: "사무실PC"}         # 눌러본다
[limbs:guestpc]{op: "type", text: "hello", limb: "사무실PC"}           # 포커스된 곳에 입력
[limbs:guestpc]{op: "key", key: "cmd+s", limb: "사무실PC"}             # 단축키
[limbs:guestpc]{op: "scroll", direction: "down", amount: 5, limb: "사무실PC"}
[limbs:guestpc]{op: "drag", x: 100, y: 100, x2: 400, y2: 300, limb: "사무실PC"}
```

**★좌표는 직전 `screen` 이 보낸 이미지 위의 좌표다.** 원본 해상도로 환산하지 말 것 —
헬퍼가 축소 배율과 레티나 픽셀↔포인트 배율을 둘 다 기억해 자동으로 옮긴다. 그래서
순서가 곧 규율이다: **screen 으로 보고 → 좌표를 정해 click → 결과 확인**. 눈대중 좌표 금지.

- 입력 op 는 **기본으로 조작 후 화면을 다시 찍어** 돌려준다(`shot: false` 로 끔). 한 번의
  호출에 조작과 확인이 함께 오므로 see→act→verify 가 저절로 닫힌다. `settle_ms`(기본 700)로
  화면이 그려질 짬을 조절한다.
- `type` 은 **현재 포커스**에 들어간다 — 먼저 클릭해 포커스를 잡을 것.
- 좌표를 빠뜨리면 실행하지 않고 되묻는다(조용히 (0,0) 을 누르는 게 가장 나쁜 실패라서).
- 캡처는 `max_width`(기본 1280) · `format`(png/jpeg/auto) · `display`(다중 모니터) 조절.
  글자가 작아 안 읽히면 `max_width: 1920`. 캡처본은 허브의
  `outputs/limb_screens/<별칭>/` 에 최근 20장 남아 사후 확인이 된다.
- **셸로 되는 일은 셸이 더 정확하다.** GUI 조작은 셸로 안 되는 일(설치 마법사·로그인 창·
  GUI 전용 앱)에 쓸 것.

**OS 별 권한 — 실패하면 고장이 아니라 동의 지점이다:**

| OS | 화면 | 입력 |
|----|------|------|
| 윈도우 | 기본 탑재(PowerShell/System.Drawing) — 마찰 없음 | 기본 탑재(user32) — 관리자 창에 넣으려면 헬퍼도 관리자 |
| 맥 | 시스템 설정 > 개인정보 보호 및 보안 > **화면 기록** 허용 필요 | > **손쉬운 사용** 허용 필요. `brew install cliclick` 이면 우클릭·드래그·정밀 이동까지 |
| 리눅스 | `grim`(Wayland)·`scrot`/`imagemagick`(X11) 중 하나 설치 | `xdotool`(X11)·`ydotool`(Wayland) 설치 |

허용 전엔 정확한 안내와 함께 실패한다(예: 맥 오류 1002 = 손쉬운 사용 미허용). 권한을 준
뒤에는 **헬퍼를 재실행**해야 반영된다. `op: "info"` 가 그 PC 에서 눈·손이 될지 미리 알려준다.

### 오래 걸리는 명령 — 발송과 제한된 대기를 한 프로그램으로

```
$r = [limbs:guestpc]{op:"shell", cmd:"python --version", background:true, limb:"사무실PC"}
return [self:task]{op:"wait", ref:$r.task_ref, timeout:60}
```

- 설치·빌드·다운로드는 `background:true`(기본 실행 제한 1800초)로 보낸다. 위처럼
  접수와 대기를 한 프로그램으로 묶으면 모델 왕복을 줄일 수 있다. 대기 시간이 끝나도
  작업은 취소되지 않는다. 반환된 `task_ref`로 다음 대기를 이어가며 명령은 다시 보내지 않는다.
- `self:task`는 `queued`(아직 전달 전), `running`(전달/진행 보고), `succeeded`(결과 회신),
  `cancelled`, `failed`(전달 전 만료), `unknown`(실행 결과 미확인)을 구분한다.
  `succeeded`는 회신 도착을 뜻하므로 셸의 `result.exit`도 확인한다.
- 허브는 기기별 작업·소유 정보·결과를 `data/phone_jobs.db`에 보존한다. 전달 전 명령은
  10분 뒤 만료되고, 완료 결과·회수 기록은 7일간 남는다. 이미 전달한 명령은 허브 재기동 뒤
  자동 재전송하지 않는다. 늦은 결과로 확정하며, 결과가 없으면 실행 불명으로 남긴다.
- `op:result`는 이전 호환용 1회 회수다. 반복 관측은 `self:task`로 한다. 동기 호출의
  대기 제한을 넘겨도 실행 실패로 단정하지 말고 응답의 `task_ref`를 사용한다.
- 새 헬퍼는 이 PC의 사용자 설정 폴더 `indiebiz-helper/delivery/`(`data_dir` 지정 시 그 아래)에
  수신 기록과 결과를 보존하고, 허브 확인까지 결과만 재전송한다. 같은 작업 ID를 다시 받아도
  명령을 중복 실행하지 않는다. 실행 중 종료된 기록은 자동 재실행하지 않는다.
  이 기록은 헬퍼 종료 뒤에도 남으며, 확인된 완료 기록은 7일 뒤 실행 중 정리한다.
- macOS에서는 실제 작업을 실행하는 동안만 `caffeinate -i`로 유휴 잠자기를 막는다.
  연결만 유지하는 동안에는 막지 않고, 화면 켜짐이나 덮개를 닫은 상태의 실행을 보장하지 않는다.
- 헬퍼의 폴은 명령 실행과 병렬이다. 드레인 중에도 기존 작업의 폴·진행·결과 통신은 유지한다.
  헬퍼의 결과 재전송·잠자기 방지는 USB 실행파일을 새 빌드로 교체해야 적용된다.

## 등록 관용구 — 준비·실행·확인·마무리

다음 네 함수는 해마에 등록하여 `[fn:이름]`으로 호출한다. 정의를 매번 다시 쓰지 않는다.
`execute_ibl(code="",describe=["fn:외부PC작업실행"])`으로 인자·반환 계약을 조회할 수 있다.
헬퍼는 대상 PC에서 먼저 실행되어 있어야 한다. `외부PC준비`는 연결을 점검하는 함수이며
꺼진 PC의 헬퍼를 원격으로 시작하거나 키를 발급하지 않는다.

| 관용구 | 인자 | 반환·효과 |
| --- | --- | --- |
| `외부PC준비` | `PC`(별칭 또는 device_id, 필수) | 목록에서 대상을 확인하고 `info` 조회. `ok/status/limb/limb_name/env` 반환. 대상 없음·중복·오프라인은 `ok:false`; 도구 호출 실패는 IBL 실패로 전파. |
| `외부PC작업실행` | `PC`, `명령`, `작업폴더` 필수. `셸:""`, `실행제한:1800`, `대기:0`, `입력:""`, `환경초기화:false` | `background:true`로 셸 명령을 한 번 제출. `limb/limb_name/task_ref/cwd/observation` 반환. `ok:true`·`status:"accepted"`는 **접수**를 뜻한다. |
| `외부PC작업확인` | `작업`(실행 또는 이전 확인의 반환값), `대기:0` | 같은 작업 참조로 상태·진행·결과·종료 코드 조회. `status/settled/command_ok/exit/timed_out/progress/result/failure`와 대상·참조 반환. 셸 재전송 없음. |
| `외부PC작업마무리` | `PC`, `작업들`(비어 있지 않은 실행/확인 반환값 목록), `산출물:[]`, `해제:false` | 전달받은 작업들을 다시 조회. 미종료·결과 불명·조회 실패가 있으면 해제 보류. 모두 종료됐고 `해제:true`이면 대상 device_id로 헬퍼 종료 요청. |

### 1. 대상 환경 확인

<!-- example:guestpc_prepare -->
```ibl
#!ibl edition=2
[fn:외부PC준비]{PC:"사무실PC"}
```

`env`의 OS·셸·도구·권한·현재 폴더를 보고 실제 작업 명령을 정한다. `ready`는 연결·환경
조회 성공이며, 특정 도구 설치나 관리자 권한이 있다는 보장은 아니다. GUI 작업은 기존
`screen → 입력 → 화면 확인` 절차를 쓰며 좌표를 관용구에 고정하지 않는다.

### 2. 한 번 제출하고 작업 참조 보존

다음 예제는 현재 폴더에서 짧은 출력 명령만 실행한다. 실제 작업에서는 확인된 OS에 맞춘
명령과 작업 폴더를 넣는다. 준비 결과의 `limb`를 전달하면 선택한 손발의 device_id를 사용한다.

<!-- example:guestpc_run -->
```ibl
#!ibl edition=2
$준비 = [fn:외부PC준비]{PC:"사무실PC"}
[if:$준비.ok==false] { return $준비 }
return [fn:외부PC작업실행]{PC:$준비.limb,명령:"echo HELPER_OK",작업폴더:$준비.env.cwd,대기:10}
```

반환값 전체를 `작업`으로 보존한다. 기본 `대기:0`은 즉시 상태를 확인하며, `대기`는 0~240초다.
`실행제한`은 헬퍼가 명령을 실행하도록 허용하는 시간(초, 1 이상)이고, `대기`와 다르다.
작업 폴더는 매번 명시하며 환경변수는 기존 헬퍼 세션의 값을 이어 쓴다. 필요할 때만
`환경초기화:true`로 기존 환경을 버린다. 비밀 입력은 등록 정의나 예제에 저장하지 않는다.

### 3. 대기 시간이 끝났으면 확인만 반복

아래 `$작업`은 위 실행의 반환값이다. **별도 호출에서는 앞 프로그램의 변수가 자동으로
이어지지 않으므로**, `execute_ibl`의 `inputs:{작업:실제로_받은_반환값}`으로 전달한다.
`task_ref`·`limb`·`limb_name`을 함께 보존하고, 예시 작업 ID를 실 ID처럼 쓰지 않는다.

<!-- example:guestpc_check -->
```ibl
#!ibl edition=2
[fn:외부PC작업확인]{작업:$작업,대기:30}
```

- `ok:true`는 조회 성공이다. 명령 성공은 **`command_ok:true`**일 때만 확인된 것이다.
- `status:"succeeded"`는 결과 회신을 뜻한다. `result.exit != 0`이면 `command_ok:false`다.
- `command_ok:null`은 종료 코드가 아직 없거나 결과를 확인할 수 없다는 뜻이다.
- `timed_out:true`는 이번 대기 종료일 뿐이다. `running/queued/unknown`을 실패나 성공으로
  단정하지 않고 같은 반환값으로 다시 확인한다. `progress.tail`에 중간 출력이 있을 수 있다.
- 조회 자체가 실패하면 `status:"observation_failed"`와 원래 참조를 반환한다. 실행 관용구도
  접수 뒤 조회가 실패하면 참조를 보존한다. 이때 **실행 관용구를 다시 부르지 않는다.**
- 종료 코드 0만으로 업무나 산출물의 정확성이 검증되지는 않는다. 필요한 파일 읽기·검사 명령·
  화면 확인을 수행한다. 검사 명령을 새로 제출했다면 그 작업도 마무리 목록에 포함한다.

### 4. 결과 정리와 선택적 해제

<!-- example:guestpc_finish -->
```ibl
#!ibl edition=2
[fn:외부PC작업마무리]{PC:"사무실PC",작업들:[$작업],산출물:[],해제:false}
```

해제까지 요청할 때는 `해제:true`로 바꾼다. `detached:true`일 때만 헬퍼 종료 응답을 확인한
것이다. 명령이 실패했어도 종료가 확인됐다면 해제할 수 있지만 `commands_ok/ok`는 false다.
전달한 작업 중 하나라도 진행·불명·조회 실패 상태라면 `status:"unfinished"`로 해제를 보류한다.
다른 PC의 작업이 섞인 목록이나 빈 목록은 거절한다.

검사 범위는 **전달받은 작업 목록**이다. 그 PC의 전체 큐나 다른 세션의 작업을 조회하는
기능은 아니므로, 해당 PC에서 별도로 진행 중인 작업이 있다면 해제를 요청하지 않는다.
`산출물`은 보고할 원격 경로의 목록이며 파일을 내려받거나 존재·내용을 검사하지 않는다.
반환의 `artifacts_verified:false`가 이 한계를 표시한다. 키 폐기는 별도의 `self:limb revoke`다.

정의 정본은 `data/idioms/guestpc_{prepare,run,check,finish}.ibl`, 등록 자료는
`data/idioms/guestpc_seeds.json`이다. 다른 설치본에 등록할 때는 저장소 루트에서 다음을 실행한다.
기존 등록 스크립트가 문법·의존성을 검사하고 SQLite 백업 후 `add_examples_batch`로 등록한다.
상시 프롬프트에는 추가하지 않고 이름 조회·의미 검색으로 찾는다.

```bash
.venv/bin/python3 scripts/register_webapp_idioms.py --seed-file guestpc_seeds.json --apply --local-encoder
```

`--local-encoder`는 실행 중인 로컬 백엔드의 임베딩을 사용한다. 백엔드가 꺼져 있으면
이 옵션을 빼서 로컬 모델을 적재한다. 같은 자료를 다시 등록해도 용례는 중복 추가하지 않는다.

## 4) 해제 — 볼일 끝

```
[limbs:guestpc]{op: "detach", limb: "사무실PC"}   # 그 PC 헬퍼 종료
[limbs:guestpc]{op: "detach"}                     # 하나뿐이면 생략
```

휴대 USB 로 PC 를 옮겨 다니는 사용의 '볼일 끝' 동작 — 그 PC 의 헬퍼가 종료된다. 실행 기록은 위 보존 규칙을 따른다. 자동승인 체제라 그 PC 에서 헬퍼를 **다시 실행하면 또 자동으로 붙는다**
— detach 는 '지금 이 세션 끝'이지 영구 차단이 아니다. 그 PC 주인 입장의 해제는 더 단순하다:
창 닫기(상주 종료, 실행 기록은 위 보존 규칙을 따름). 영구 차단(유출·이탈)은 아래 revoke.

## 5) 폐기 — 뒷정리

```
[self:limb]{op: "revoke", target: "사무실PC"}     # 이 키만 폐기(USB 분실 시)
```

USB 를 잃어버려도 이 키 하나만 폐기하면 끝 — 허브 로그인·구독·데이터 API 키는 USB 에
실리지 않으므로 유출될 게 없다.

## 원칙 · 경계

- **augmentation-over-autonomy**: 남의 PC 에 셸을 내주는 고권한 도구다. 내 PC 아닌 곳에
  쓸 땐 그 PC 주인의 명시적 동의가 전제("남의 의도 자동실행 금지"의 거울상).
- 손발은 신뢰 원장(`grant_body`)의 레벨4 이웃으로 **자동 등록되지 않는다** — 인가는 오직
  limb key(붙으면 자동승인). 셸 실행 몸에 이웃 자격을 함부로 주지 않기 위함.
- 자동승인의 오배송 방어는 *이름 명시*가 진다(손발 둘 이상이면 필수). 유출 방어선은
  revoke(키 폐기)와 host 변경 알림. 편의(마찰 없는 로밍)와 안전(이름·폐기)의 트레이드오프.
- 허브가 켜져 있고 터널이 살아 있어야 한다(본체 의존). 대신 USB 는 수 MB 로 얇다.
- 서명 없는 실행파일은 SmartScreen·백신 경고가 뜰 수 있다(회사 PC 는 차단 가능).

## 헬퍼 빌드 (배포자용)

`helper/` 에 Go 단일 파일 소스. `helper/build.sh` 로 win/mac/linux 크로스컴파일 →
`helper/dist/`. 발급([self:limb]{op:issue})이 대상 OS 실행파일을 USB 페이로드에 동봉한다.
```
cd helper && ./build.sh      # Go 설치 필요
```
- **구형 인텔 맥(macOS 10.15~11)**: Go 1.25+ 산출물은 최소 macOS 12 라 Catalina 에서
  `dyld: Symbol not found: _SecTrustCopyCertificateChain` 으로 꺼진다. build.sh 가
  Go 1.22(10.15 지원 마지막) + `go.legacy.mod`(그 툴체인이 받는 의존성 고정)로
  `indiebiz-helper-mac-amd64-legacy` 를 따로 굽고, 맥 발급 묶음에 함께 실린다.
  의존성을 올릴 때 go.legacy.mod 는 Go 1.22 가 받는 버전에 남겨 둘 것.

## 실측 기록 (자동 누적)

> 실행 에이전트가 턴 종료 후 덧붙인다.
- 2026-10-09 실측: helper/go.mod 가 Go 1.25 이상을 요구해 Go 1.26.5 로 빌드된 helper/dist 의 mac-amd64 는 otool minos 12.0 이다. 이 파일은 macOS 10.15(Catalina) 인텔맥에서 _SecTrustCopyCertificateChain 심볼을 찾지 못해 시작하자마자 종료된다. 가이드에는 '빌드된 실행파일이 있으면 동봉'이라고만 적혀 있어 이 함정이 드러나지 않는다.
- 2026-10-09 실측: Catalina 용 레거시 헬퍼는 Go 1.22.12(10.15 를 지원하는 마지막 Go)와 helper/go.legacy.mod(의존성 고정, 예: sqlite v1.34.5)로 따로 빌드하면 된다. 결과는 minos 10.13 이고 nm -u 에 _SecTrustCopyCertificateChain 이 없어 정적 검증을 통과했다. 헬퍼 코드는 고칠 곳이 없었다.
- 2026-10-09 후속: 레거시 빌드 산출물을 정본에 반영하고 맥12 발급 폴더와 ZIP을 기존 키로 복원했다. 실제 Catalina 기기 실행은 미검증이다. 자기수리에서 기존 발급 폴더를 갱신할 때는 사본에서 실행파일·사용법만 준비하고 self:patch apply의 artifact_paths로 두 경로를 명시한다. indiebiz-helper.json은 재발급·교체하지 않는다.
