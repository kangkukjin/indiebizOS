# Chrome 창·탭 드라이버 — 본체 앱 제어

macOS 본체 Google Chrome의 창·탭을 화면 조작 없이 AppleScript 사전으로 다룬다.
조작면 `app:com.google.Chrome`, 등록 스크립트 `Chrome제어`. 계약 조회는
`[self:script]{id:"Chrome제어",args:{op:"contract"}}`다. 화면 snapshot의 `control_guide`나
등록 스크립트 설명으로 발견하고, 계약을 이미 읽었다면 다시 조회하지 않는다.
`Safari제어`(`safari_control.md`)와 같은 계약이며, 아래 "Safari와 다른 점"만 Chrome 고유다.
어느 탭을 다룰지는 AI가 결정하고 부품은 대상 대조·실행·결과 확인을 맡는다.


## 빠른 호출

macOS 본체 Chrome은 아래 스크립트다. Windows는 PC제어의 chrome_*를 쓰며 pc_control.md의 전용 프로필·CDP 계약을 읽는다. 두 통로의 tab 뜻은 다르다.
- 상태: `[self:script]{id:"Chrome제어",args:{op:"status"},timeout:60}`. windows에서 사용자가 지정한 창·탭을 고른다. args의 window_id로 조회 범위를 좁힐 수 있다. 요약 범위에서 계약·목록 재조회는 필요 없다.
- 같은 호출의 args로 open은 `op:"open",url`과 선택 window_id·expected·launch, switch·close는 `op,window_id,tab,expected`를 전달한다. macOS tab은 index(1부터 세는 위치), Windows tab은 targetId다. expected는 windows[].revision 또는 직전 state.revision이고 open의 expected에도 window_id가 필요하다. 꺼진 앱은 open에 launch:true일 때만 기동한다.
- 드라이버가 변경 전 판본과 변경 후 조건을 확인한다. `status:"completed",verified:true`와 checks로 판단하고 state·target={window_id,tab,expected}를 후속 호출에 넘긴다. 성공마다 status를 다시 붙이지 않는다. 정해진 연속 동작은 한 프로그램에서 잇고 실패하면 중단한다.
- open은 새 탭을 활성으로 만든 뒤 기존 탭을 복원한다(checks.activation_restored). 순간 전환이 보일 수 있다. switch·close는 공유 상태 변경이다. 앱을 앞으로 가져오지 않는다. page_loaded:null이므로 페이지 로드·영상 재생은 별도 확인한다.
- 실패는 예외다. try/catch의 `$error.details.failure`·recovery를 보존한다. STATE_CHANGED는 변경 전 중단이므로 반환 상태 또는 새 status로 재판단한다. UNKNOWN·POSTCONDITION_FAILED는 효과가 있을 수 있어 변경 재전송·화면 조작 반복을 금한다. 필요한 상태만 읽는다. OBSERVATION_FAILED는 조회 실패이며 즉시 반복하지 않는다. 권한 오류·판본 한계는 해당 절을 읽는다.

## 동작과 대상 판본

| op | 인수 | 확인 범위 |
| --- | --- | --- |
| status | window_id 선택 | 전체 창 또는 지정 창의 탭(`tab_id` 포함)·현재 탭·`mode`·`minimized`·revision 조회 |
| open | url, window_id·expected·launch 선택 | 끝에 탭 생성, 기존 탭 id 순서와 현재 탭 보존(활성 복원). 창이 없으면 새 창 |
| switch | window_id, tab, expected 필수 | 요청 탭 전환과 탭 id 순서 보존. 이미 그 탭이면 변경 명령 생략 |
| close | window_id, tab, expected 필수 | 그 위치의 탭을 **탭 id로** 닫는다. 남은 탭 id 순서 대조. 창 소멸은 원래 마지막 탭일 때만 성공 |

`expected`는 `status.windows[].revision` 또는 직전 변경 결과 `state.revision`이다.
판본은 **창 id·현재 탭 번호·탭 id 순서**다. 달라졌으면 `STATE_CHANGED`로 **변경 전에** 중단한다.
`open`에 expected를 주려면 window_id도 필요하다. 전환·닫기에는 관측 판본이 필수다.
AppleScript 변경 명령 안에서도 탭 id 순서·현재 탭을 다시 대조한다.
`tab`은 1부터 세는 위치 번호(status의 `index`)이고, 실행 직전 그 위치의 탭 id를 대조한다.

## Safari와 다른 점

- **탭 id가 영구 신원이다.** URL·제목은 판본에서 빠지므로 탭 안에서 페이지가 이동해도 판본은 유효하고,
  같은 URL 탭을 혼동하지 않는다. 닫기는 번호가 아니라 id로 보낸다.
- **Chrome은 새 탭을 활성으로 만든다.** open은 같은 스크립트 안에서 이전 현재 탭을 복원하고
  `checks.activation_restored`로 보고한다. 창이 화면에 있으면 찰나의 전환이 보일 수 있다.
  복원을 확인하지 못하면 `POSTCONDITION_FAILED`다(탭은 생겼을 수 있다 — 반환 상태로 판단).
- status 창 행에 `mode`(`normal`/`incognito`)와 `minimized`가 있다. 시크릿 창도 창 목록에 든다.
- Windows PC의 Chrome은 이 스크립트가 아니라 **PC제어의 `chrome_status`·`chrome_open`·`chrome_switch`·`chrome_close`**
  (`pc_control.md` 'Windows Chrome 창·탭', 통로 = CDP 전용 프로필)로 같은 계약을 쓴다. 거기서는 `tab`이 위치 번호가 아니라
  targetId이고 탭 띠 순서를 알 수 없다. 이 스크립트를 Windows 본체에서 부르면 `UNSUPPORTED_PLATFORM`이다.

어떤 동작도 Chrome을 앞으로 가져오지 않는다(`needs_front:false`). switch·close의 `shared_state:true`는
사용자가 보는 탭을 바꾸는 요청된 효과다. Chrome이 꺼져 있으면 open의 `launch:true`일 때만 배경 기동한다.

## 반환값과 실패

- `verified`는 명시한 사전 재조회 조건을 모두 통과했음을 뜻한다. `checks`에 확인 항목을 싣는다.
- 변경 결과 `before`는 이전 창의 번호·현재 탭·개수·revision 요약, `state`는 변경 후 대상 창 전체다.
  창이 사라지면 state는 null이다. 열기 결과에는 새 탭의 `tab_id`가 있다.
- `target`은 후속 동작에 쓸 `{window_id,tab,expected}`다. 열기는 새 탭, 전환은 요청 탭,
  닫기는 남은 현재 탭을 가리킨다. 후속 대상을 만들 수 없으면 null이다.
- `page_loaded:null`: 페이지 로드 완료·화면 렌더링은 확인하지 않는다.
- `STATE_CHANGED`·`TARGET_MISSING`·`PERMISSION_REQUIRED`·`OBSERVATION_FAILED`·`POSTCONDITION_FAILED`·
  `UNKNOWN`의 뜻과 처리는 `safari_control.md`와 같다. 변경 뒤 불명확하면 재전송하지 않고 status로 판별한다.

상태가 반환됐으면 그것으로 후속 판단한다. 성공한 변경마다 별도 status를 붙이지 않는다.
`contract`·`status`는 읽기, `open`·`switch`·`close`는 변경으로 선언한다.

```ibl
#!ibl edition=2
$관측 = [try] {
  $s = [self:script]{id:"Chrome제어",args:{op:"status"},timeout:60}
  {verified:$s.verified,state:$s,error:null}
} [catch] {
  {verified:false,state:null,error:$error}
}
return $관측
```

성공 결과에는 `status:"completed"`·`failure:null` 칸이 함께 온다(2026-10-21, 긴문장 87회차 L87-4) — PC제어·Android제어 결과와 같은 투영(`status`·`verified`·`failure`)으로
세 드라이버를 한 프로그램에서 다룰 수 있게. 실패는 여전히 **예외**이며 `[try]/[catch]` 의 `$error.details.failure{code,message,next}` 로 받는다. 실패를 레코드로 돌려주는 PC·Android 와 이 점은 다르다.

## 정해진 연속 동작은 한 프로그램으로

첫 창에 임시 빈 탭을 열고 전환했다 돌아와 닫는 예시다. 실행 전 Chrome 창이 있어야 한다.
한 번의 execute_ibl로 맡기고, 각 변경 전 현재 상태는 드라이버가 새로 확인한다.
실패하면 그 위치에서 중단하며 자동 되돌리기·닫기 재전송을 하지 않는다.

```ibl
#!ibl edition=2
$s = [self:script]{id:"Chrome제어",args:{op:"status"},timeout:60}
assert $s.window_count > 0, "Chrome 창이 필요합니다", {result:$s}
$w = $s.windows[0]
$o = [self:script]{id:"Chrome제어",args:{op:"open",url:"about:blank",window_id:$w.window_id,expected:$w.revision},timeout:60}
assert $o.verified == true, "배경 탭 열기 미확인", {result:$o}
$a = [self:script]{id:"Chrome제어",args:{op:"switch",window_id:$o.target.window_id,tab:$o.target.tab,expected:$o.target.expected},timeout:60}
assert $a.verified == true, "탭 전환 미확인", {result:$a}
$b = [self:script]{id:"Chrome제어",args:{op:"switch",window_id:$a.state.window_id,tab:$o.before.current_tab,expected:$a.state.revision},timeout:60}
assert $b.verified == true, "원래 탭 복귀 미확인", {result:$b}
$c = [self:script]{id:"Chrome제어",args:{op:"close",window_id:$b.state.window_id,tab:$o.tab,expected:$b.state.revision},timeout:60}
assert $c.verified == true, "임시 탭 닫기 미확인", {result:$c}
return $c
```

## 관측과 폴백

환경별 사실은 `[self:limb]{op:"register",target:"app:com.google.Chrome",observations:[…]}`로 남기고
`[self:limb]{op:"list",target:"app:com.google.Chrome"}`로 읽는다. 본체 관측 대상은 `__local__`이다.
페이지 안 요소 클릭·입력은 이 부품의 범위 밖이다 — `[limbs:browser]`(Chrome 연결이면 같은 탭·로그인)
또는 `[limbs:screen]`의 snapshot ref를 쓴다. 드라이버 결과가 unknown이면 화면으로 같은 변경을 반복하지 않는다.
