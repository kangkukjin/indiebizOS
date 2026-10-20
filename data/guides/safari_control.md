# Safari 창·탭 드라이버 — 본체 앱 제어

macOS 본체 Safari의 창·탭을 화면 조작 없이 AppleScript 사전으로 다룬다.
조작면 `app:com.apple.Safari`, 등록 스크립트 `Safari제어`. 계약 조회는
`[self:script]{id:"Safari제어",args:{op:"contract"}}`다. 화면 snapshot의 `control_guide`나
등록 스크립트 설명으로 발견하고, 계약을 이미 읽었다면 다시 조회하지 않는다.
어느 탭을 다룰지는 AI가 결정하고 부품은 대상 대조·실행·결과 확인을 맡는다.

## 동작과 대상 판본

| op | 인수 | 확인 범위 |
| --- | --- | --- |
| status | window_id 선택 | 전체 창 또는 지정 창의 탭·현재 탭·revision 조회 |
| open | url, window_id·expected·launch 선택 | 배경 탭 생성, 기존 탭 URL 순서와 현재 탭 보존. 창이 없으면 새 창 |
| switch | window_id, tab, expected 필수 | 요청 탭 전환과 탭 URL 순서 보존. 이미 그 탭이면 변경 명령 생략 |
| close | window_id, tab, expected 필수 | 요청 탭을 제외한 URL 순서·개수. 창 소멸은 원래 마지막 탭일 때만 성공 |

`expected`는 `status.windows[].revision` 또는 직전 변경 결과 `state.revision`이다.
창 ID·현재 탭·탭 URL 순서를 대조하고, 달라졌으면 `STATE_CHANGED`로 **변경 전에** 중단한다.
`open`에 expected를 주려면 window_id도 필요하다. 전환·닫기에는 관측 판본이 필수다.
AppleScript 변경 명령 안에서도 URL 순서·현재 탭을 다시 대조한다.
제목은 페이지 로딩에 따라 바뀌므로 판본·닫기 대조에서 제외한다.
**탭 번호는 영구 ID가 아니다.** 같은 URL인 탭끼리의 교환, 관측 사이 변경 후 원상 복귀,
마지막 대조와 실제 효과 사이의 경쟁까지 막는 잠금·트랜잭션은 제공하지 않는다.

어떤 동작도 Safari를 앞으로 가져오지 않는다(`needs_front:false`). open은 배경 탭이며
창이 없으면 새 창이 생기는 효과가 있다. switch·close의 `shared_state:true`는 사용자가 보는
탭을 바꾸는 요청된 효과다. Safari가 꺼져 있으면 open의 `launch:true`일 때만 배경 기동한다.

## 반환값과 실패

- `verified`는 명시한 사전 재조회 조건을 모두 통과했음을 뜻한다. `checks`에 확인 항목을 싣는다.
- 변경 결과 `before`는 이전 창의 번호·현재 탭·개수·revision 요약, `state`는 변경 후 대상 창 전체다.
  전체 브라우저 창 목록은 변경 결과에 반복하지 않는다. 창이 사라지면 state는 null이다.
- `target`은 후속 동작에 쓸 `{window_id,tab,expected}`다. 열기는 새 탭, 전환은 요청 탭,
  닫기는 남은 현재 탭을 가리킨다. 후속 대상을 만들 수 없으면 null이다.
- 열기 응답의 생성 대상과 재조회가 일치하면 URL 리다이렉트가 있어도 탭 생성은 확인할 수 있다.
  `requested_url`·`observed_url`·`checks.requested_url_observed`는 별도로 반환한다.
  응답이 유실되면 정확한 요청 URL·추가 탭·기존 상태 보존을 확인할 수 있을 때만 성공이다.
- `page_loaded:null`: 페이지 로드 완료·화면 렌더링은 확인하지 않는다.
- `STATE_CHANGED`: 변경 전 대상이 달라졌다. 반환된 failure.state 또는 새 status로 다시 판단한다.
- `TARGET_MISSING`: 변경 전 창·탭·실행 중인 앱을 찾지 못했다.
- `PERMISSION_REQUIRED`: 자동화 권한을 허용해야 한다.
- `OBSERVATION_FAILED`: 변경을 전송하기 전 상태 조회 시간 초과. IBL `try/catch`로
  실패 근거를 보존하고 나머지 점검을 계속할 수 있다. 같은 조회를 즉시 반복하지 않는다.
- `POSTCONDITION_FAILED`: 변경 요청 후 보존 조건·요청 결과를 확인하지 못했다. 반환 상태를 검토한다.
- `UNKNOWN`: 응답 유실 후 효과 판별 불가 또는 변경 후 재조회 실패. 변경을 재전송하지 않는다.
  실패는 IBL `diagnostic.details`의 failure·recovery에도 남는다.

상태가 반환됐으면 그것으로 후속 판단한다. 필요한 정보가 없을 때만 대상 창의 status를 조회한다.
성공한 변경마다 별도 status를 붙이지 않는다. 화면 증거가 필요한 작업만 마지막에 screenshot을 쓴다.
`contract`·`status`는 읽기, `open`·`switch`·`close`는 변경으로 선언한다.
현재 상태는 실행마다 새로 관측한다. 조회 실패를 잡았다는 사실을 조회 성공으로 보고하지 않는다.

여러 드라이버를 점검할 때는 다음처럼 조회 실패를 값으로 남긴다. 변경 후 `UNKNOWN`은 일반
catch로 삼켜 다음 변경을 진행하지 않으며 원 실행의 불명확 상태를 유지한다.

```ibl
#!ibl edition=2
$관측 = [try] {
  $s = [self:script]{id:"Safari제어",args:{op:"status"},timeout:60}
  {verified:$s.verified,state:$s,error:null}
} [catch] {
  {verified:false,state:null,error:$error}
}
return $관측
```

```ibl
#!ibl edition=2
$상태 = [self:script]{id:"Safari제어",args:{op:"status"},timeout:60}
assert $상태.verified == true, "Safari 상태 조회 실패", {result:$상태}
return $상태
```

성공 결과에는 `status:"completed"`·`failure:null` 칸이 함께 온다(2026-10-21, 긴문장 87회차 L87-4) — PC제어·Android제어 결과와 같은 투영(`status`·`verified`·`failure`)으로
세 드라이버를 한 프로그램에서 다룰 수 있게. 실패는 여전히 **예외**이며 `[try]/[catch]` 의 `$error.details.failure{code,message,next}` 로 받는다. 실패를 레코드로 돌려주는 PC·Android 와 이 점은 다르다.

## 정해진 연속 동작은 한 프로그램으로

다음은 첫 창에 임시 빈 탭을 열고 전환했다 돌아와 닫는 예시다. 실행 전 Safari 창이 있어야 한다.
한 번의 execute_ibl로 맡긴다. 모델의 단계별 재호출 없이 값·판본을 이어 주되, 각 변경 전 현재 상태는
드라이버가 새로 확인한다. 실패하면 그 위치에서 중단하며 자동 되돌리기·닫기 재전송을 하지 않는다.
새 의미 판단이 필요한 작업은 해당 지점에서 결과를 AI에게 돌려준다.

```ibl
#!ibl edition=2
$s = [self:script]{id:"Safari제어",args:{op:"status"},timeout:60}
assert $s.window_count > 0, "Safari 창이 필요합니다", {result:$s}
$w = $s.windows[0]
$o = [self:script]{id:"Safari제어",args:{op:"open",url:"about:blank",window_id:$w.window_id,expected:$w.revision},timeout:60}
assert $o.verified == true, "배경 탭 열기 미확인", {result:$o}
$a = [self:script]{id:"Safari제어",args:{op:"switch",window_id:$o.target.window_id,tab:$o.target.tab,expected:$o.target.expected},timeout:60}
assert $a.verified == true, "탭 전환 미확인", {result:$a}
$b = [self:script]{id:"Safari제어",args:{op:"switch",window_id:$a.state.window_id,tab:$o.before.current_tab,expected:$a.state.revision},timeout:60}
assert $b.verified == true, "원래 탭 복귀 미확인", {result:$b}
$c = [self:script]{id:"Safari제어",args:{op:"close",window_id:$b.state.window_id,tab:$o.tab,expected:$b.state.revision},timeout:60}
assert $c.verified == true, "임시 탭 닫기 미확인", {result:$c}
return $c
```

## 관측과 폴백

환경별 사실은 `[self:limb]{op:"register",target:"app:com.apple.Safari",observations:[…]}`로 남긴다.
시각·판본·환경·사실·출처를 적고, `[self:limb]{op:"list",target:"app:com.apple.Safari"}`로 읽는다.
본체 관측 대상은 `__local__`이다. 과거 실기 기록과 이번 검증 범위는
`docs/CONTROL_DRIVER_DESIGN_2026_10_20.md`의 구현 기록을 따른다.

페이지 안 요소 클릭·입력은 이 부품의 범위 밖이다. `[limbs:browser]`의 DOM 계약 또는
`[limbs:screen]`의 snapshot ref를 사용하되, 브라우저가 달라지면 같은 로그인·탭이라는 보장은 없다.
드라이버 결과가 unknown이면 화면으로 같은 변경을 반복하지 않는다.
