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

### 오래 걸리는 명령 — background + result (★설치·빌드·다운로드는 이 길로)

```
[limbs:guestpc]{op: "shell", cmd: "winget install --id Apple.Bonjour -e --silent", background: true, limb: "사무실PC"}
  → 즉시 {job_id: "ab12…"} 반환 (기본 timeout 1800초 — 헬퍼가 그 시간까지 실행)
[limbs:guestpc]{op: "result", job: "ab12…"}
  → 완료됐으면 결과, 아직이면 pending(잠시 후 재확인)
```

- 동기 shell 의 대기 상한은 **100초**(그 위층 MCP 가 120초에 끊으므로). 100초를 넘기면
  실패가 아니라 `queued=True + job_id` 가 돌아온다 — **같은 명령을 다시 보내지 말 것**
  (그 PC 에선 계속 실행 중일 수 있어 이중 실행 위험). `op:result` 로 결과를 회수한다.
- 결과는 헬퍼 회신 후 5분간 보존되고 회수는 1회. 5분을 넘겼으면 상태 확인 명령을 새로 보낸다.
- 헬퍼는 명령을 병렬 실행한다(2026-07-24 개정) — 긴 설치가 돌아가는 중에도 폴링이 계속돼
  손발이 오프라인으로 보이지 않고, 다른 명령도 받을 수 있다. (옛 헬퍼 바이너리는 동기
  실행이라 긴 명령 중 오프라인처럼 보인다 — USB 의 실행파일을 새 빌드로 교체할 것.)

## 4) 해제 — 볼일 끝

```
[limbs:guestpc]{op: "detach", limb: "사무실PC"}   # 그 PC 헬퍼 종료
[limbs:guestpc]{op: "detach"}                     # 하나뿐이면 생략
```

휴대 USB 로 PC 를 옮겨 다니는 사용의 '볼일 끝' 동작 — 그 PC 의 헬퍼가 종료되고 그 PC 엔
아무것도 남지 않는다. 자동승인 체제라 그 PC 에서 헬퍼를 **다시 실행하면 또 자동으로 붙는다**
— detach 는 '지금 이 세션 끝'이지 영구 차단이 아니다. 그 PC 주인 입장의 해제는 더 단순하다:
창 닫기(설치·상주 없음). 영구 차단(유출·이탈)은 아래 revoke.

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
```

