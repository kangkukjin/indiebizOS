# Safari 창·탭 드라이버 — 본체 앱 제어의 시범

본체 macOS 의 Safari 창·탭을 **화면 조작 없이** 사전(AppleScript) 계약으로 다룰 때 읽는다.
조작면은 `app:com.apple.Safari`, 실행 부품은 등록 스크립트 `Safari제어`, 계약 조회는
`[self:script]{id:"Safari제어",args:{op:"contract"}}` 다. `[limbs:screen]{op:"snapshot"}` 의 앞 앱이
Safari 면 응답의 `control_guide` 가 이 파일을 가리킨다 — 좌표·ref 로 더듬기 전에 이 부품을 쓴다.
현재 문맥에 계약이 있으면 다시 읽거나 같은 AppleScript 를 새로 쓰지 않는다.
어느 탭을 열고 닫을지는 AI 가 정하고, 이 부품은 사전 호출과 재조회만 얼린다(앱 안의 내용 조작은 범위 밖).

## 동작과 실행 조건

어떤 동작도 Safari 를 앞으로 가져오지(activate) 않는다. `needs_front` 는 전부 false 라 정기·배경
실행에서도 실행 경계가 거절하지 않는다. `shared_state` 가 true 인 동작은 사용자가 보는 탭을 바꾸는
**요청된 효과** 이므로 요청받았으면 사용자가 작업 중이어도 실행한다.

| op | 인수 | shared_state | 확인 범위 |
| --- | --- | --- | --- |
| status | 없음 | false | 창·탭·현재 탭 조회(`applescript_readback`). 변경 없음 |
| open | url, window_id(선택, 기본 첫 창), launch(선택) | false | 지정 창 끝에 **배경 탭**. 현재 탭 불변(`current_tab_unchanged`). 창이 없으면 새 창(`window_created:true` — 그때는 사용자 화면에 창이 하나 늘어난다) |
| switch | window_id, tab | true | 그 창의 현재 탭 재조회가 요청과 같음 |
| close | window_id, tab | true | 탭 수 1 감소·요청 탭을 제외한 나머지 탭의 URL·제목 순서 재조회(동일 탭의 개체 신원은 판별 불가). 마지막 탭이면 `window_closed:true` |

`verified:true` 는 변경 뒤 재조회(`applescript_tab_readback`)를 통과했다는 보고다. 페이지 로드 완료·
화면에 실제로 그려졌는지는 범위 밖이다. 증거가 필요하면 마지막에 `[limbs:screen]{op:"screenshot"}` 한 장
(그것은 `needs_front` 동작이라 사용자 입회 문맥에서만).

```ibl
#!ibl edition=2
$상태 = [self:script]{id:"Safari제어",args:{op:"status"},timeout:60}
assert $상태.success == true, "Safari 상태 조회 실패", {result:$상태}
return $상태
```

`windows[].window_id` 와 `tabs[].index` 를 읽어 대상을 고른다. 창 번호가 아니라 `window_id` 를 쓴다(창 순서는 바뀐다).

```ibl
#!ibl edition=2
$r = [self:script]{id:"Safari제어",args:{op:"open",url:"https://example.com",window_id:223970},timeout:60}
assert $r.success == true and $r.verified == true, "탭 열기를 확인하지 못함", {result:$r}
return {window_id:$r.window_id,tab:$r.tab,current_tab_unchanged:$r.current_tab_unchanged}
```

## 네 경우의 동작 (실기 기록 2026-10-20, macOS 26.6 · Safari 26.6)

- **사용자가 동시에 작업하는 경우**: 모든 동작이 `activate` 없이 돌아 앞 앱이 바뀌지 않았다(실측: 앞 앱 ChatGPT 유지). `switch` 는 그 창의 보이는 탭을 바꾸는 요청된 효과다. 전환 뒤 재조회가 요청과 다르면 `NOT_APPLIED` — 사용자가 동시에 탭을 바꾼 경우이며 자동 재시도하지 않는다.
- **권한 부족**: 자동화(Apple Events) 미허용은 첫 사전 호출의 `-1743` 으로 드러나 `failure.code:PERMISSION_REQUIRED` 와 설정 경로를 돌려준다. 시스템 설정 > 개인정보 보호 및 보안 > 자동화. 재시도는 사용자가 허용한 뒤 한 번.
- **대상 소실**: Safari 미실행은 실행 전 검사가 `TARGET_MISSING` 으로 거절한다(`open` 에 `launch:true` 를 주면 `open -gja` 로 **배경** 기동). 없는 창·탭은 사전 오류 `-1719/-1728` → `TARGET_MISSING`. `status` 로 다시 고른다.
- **실행 뒤 응답 유실**: 사전 호출 시간 초과(10~15초)는 실패가 아니라 불명확이다. 부품이 **변경 없이** 재조회해 효과가 났으면 `verified:true, response_lost:true`, 안 났으면 `status:"unknown"` 을 유지한다. IBL 실패의 `details.failure.code`와 `details.recovery.status`에도 불명확 상태와 재조회 지침이 보존된다. 재전송하지 않는다. 실측: 숨은 Safari 의 첫 창 만들기는 효과가 즉시 나고 응답은 20초 넘게 늦었다.

## 관측

이 앱의 개체·환경별 사실(판본·설정에 따른 거절 등)은 가이드 산문이 아니라 관측 행으로 남긴다 —
`[self:limb]{op:"register",target:"app:com.apple.Safari",observations:[{observed_at:"…",version:"Safari 26.6",environment:{device:"__local__"},fact:"…",source:"…"}]}`.
snapshot 알림과 `[self:limb]{op:"list"}`의 `control_observations`가 행 수를 보인다. 본문은 `[self:limb]{op:"list",target:"app:com.apple.Safari"}`로 읽는다. 본체 관측은 `target:"__local__"`로 조회한다. 지우지 않고 `status` 로 정정한다.

## 폴백

이 부품에 없는 동작(페이지 안 요소 클릭·입력)은 `[limbs:browser]`(DOM 계약) 또는 `[limbs:screen]`
snapshot 의 ref(AXPress) 순서다. 드라이버 통로가 불명확(`unknown`)한 상태에서 화면으로 같은 변경을
다시 시도하지 않는다 — 중복 적용과 원인 은폐가 함께 생긴다.
