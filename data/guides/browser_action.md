# Browser Action 사용 가이드

브라우저 자동화 IBL 어휘. 연결된 내장 포식 브라우저 우선, Chrome MCP 또는 Playwright 선택.
데스크톱 일반 앱 자동화는 `[limbs:screen]` (별도 가이드 참조).

## 먼저: 세 층과 폴백 서열

브라우저 제어는 세 층이다 — ① 사이트 실행 부품(있으면: `snapshot` 응답의 `control_guide` 가 현재 도메인에 드라이버·관측이 있음을 알린다. 그 가이드를 한 번 읽고 부품을 먼저 쓴다) → ② 범용 DOM(이 가이드: navigate·snapshot ref·content·evaluate) → ③ 화면(screenshot·vision 은 캔버스·이미지처럼 DOM 이 못 주는 것에만). **격리는 도구가 아니라 자원 단위다.** 내장 Playwright 의 전용 프로필은 화면·포커스·세션이 분리되지만 같은 계정으로 로그인했으면 계정 데이터(문서·장바구니)는 공유다. Chrome MCP 는 사용자의 탭·세션을 그대로 쓴다(`shared_state`). 그래서 정기·배경 실행처럼 화면을 쓸 수 없는 문맥에서 공유 상태를 바꾸는 동작은 새 `driver:auto` 작업은 Chrome을 후보에서 제외하고, 앞선 조회로 Chrome에 결속된 작업이나 `driver:chrome` 명시는 실행 경계가 `SCREEN_CONTEXT_UNAVAILABLE` 로 거절한다. 관측만 있는 사이트도 snapshot의 `driver_surface.observations`로 알리며, `[self:limb]{op:"list",target:"site:<실제 호스트>"}`로 읽는다. 드라이버 통로가 응답 유실로 불명확하면 같은 변경을 DOM 으로 다시 시도하지 않고 상태를 재조회한다.

## 기본 흐름

페이지를 열고 DOM 구조를 관측한 뒤 조작한다. 본문은 content, 버튼·입력칸은 snapshot의 ref로 읽는다.
화면 캡처는 이미지·캔버스 등 시각 정보가 필요할 때만 지원 드라이버에서 사용한다.

```ibl
[limbs:browser]{op:"navigate",url:"https://example.com"}
[limbs:browser]{op:"snapshot"}
# 관측한 ref로 click/type한 뒤 snapshot/content로 결과를 확인한다.
[limbs:browser]{op:"content"}
```

### ref란?
- `[limbs:browser]{op: "snapshot"}` 호출 시 각 요소에 `e1`, `e2`, `e3` ... 형태의 고유 ID가 부여됨
- 이후 `[limbs:browser]{op: "click", ref: "e5"}`, `[limbs:browser]{op: "type", ref: "e3"}` 등으로 정확한 요소 지정
- 페이지가 변경되면(네비게이션, 동적 콘텐츠) **반드시 `browser_snapshot`을 다시 호출**해서 새 ref 확보
- 메뉴 열기·닫기와 화면 크기 변경도 포함한다. `REF_NOT_RESOLVED`를 받으면 같은 ref를 재시도하지 않고 새 snapshot의 요소를 고른다.
- 펼침 요소(`disclosuretriangle`, HTML `summary`)도 snapshot의 ref로 클릭한다. 같은 이름의 후보가 여럿이면 선택자까지 일치하는 유일한 요소만 조작하며, 이름이 바뀌거나 사라진 요소는 거절한다.

### snapshot vs screenshot vs browser_content
| 액션 | 용도 | 반환 |
|------|------|------|
| `[limbs:browser]{op: "snapshot"}` | 상호작용용 (ref 포함) | 요소 구조 + ref |
| `[limbs:browser]{op: "screenshot"}` | 시각적 확인용 | PNG 파일 경로 |
| `[limbs:browser]{op: "content"}` | 텍스트 읽기용 | 페이지 텍스트 |

**원칙**: 상호작용이 목적이면 항상 `browser_snapshot`. screenshot은 시각 확인이 필요할 때만.

목록의 제목·날짜가 말줄임표로 잘려 있으면 해당 항목의 상세 화면이나 실제 DOM 속성에서
전체 값을 확인한다. 화면에 보이는 축약형만으로 전체 제목 조회가 끝났다고 보고하지 않는다.
전체 값을 얻을 수 없으면 어느 항목이 미확인인지 명시한다.

---

## 드라이버 선택

대부분의 액션은 `driver` 파라미터로 어떤 드라이버를 쓸지 결정한다.

| 값 | 동작 |
|---|---|
| `"auto"` (기본) | 새 소유자 작업은 연결된 내장 브라우저 우선, 없으면 Chrome/Playwright. 이후 작업별 고정 |
| `"embedded"` | 데스크톱 내장 포식 탭과 persist:forage 로그인 상태 사용 |
| `"playwright"` | 항상 헤드리스 Playwright |
| `"chrome"` | 실제 Chrome 브라우저 (사전에 `[limbs:browser]{op: "chrome", mode: "connect"}` 필요) |

```
[limbs:browser]{op: "navigate", url: "...", driver: "chrome"}     # 실제 Chrome
[limbs:browser]{op: "navigate", url: "...", driver: "playwright"} # 헤드리스
[limbs:browser]{op: "navigate", url: "..."}                       # auto
```

**언제 Chrome MCP?**
- 사람이 보는 실제 Chrome 창에서 동작 시연하고 싶을 때
- 봇 차단·CAPTCHA가 헤드리스보다 약함
- 자연어 요소 찾기 `[limbs:browser]{op: "find", query: "로그인 버튼"}` 가능 (Chrome 전용)

**언제 Playwright?**
- 백그라운드 자동화, 빠름
- 헤드리스 환경(서버) 또는 화면 안 띄우고 싶을 때
- 자동 ref(snapshot) 정밀도가 더 높음

Chrome 연결 실패에는 중첩 예외의 실제 원인이 포함된다. 연결 거부·서버 부재이면
동일 연결을 반복하기 전에 서버·확장 상태를 확인한다. 별도로 제공된 네이티브 브라우저 도구가
있다면 그 도구에서 실제 탭과 로그인 상태를 확인할 수 있다. 드라이버 간 로그인 세션 공유는 보장되지 않는다.

---

## 다중 탭 사용법

탭 관리는 **단일 액션 `[limbs:browser]{op: "tab", mode}`** — list / new / switch / close.

### 기본 흐름
```
$first = [limbs:browser]{op: "navigate", url: "site-a.com"}  # 첫 탭 ID 보존
[limbs:browser]{op: "tab", mode: "new", url: "site-b.com"}          # t2 탭 생성 + 자동 전환
[limbs:browser]{op: "tab", mode: "list"}                            # 열린 탭 목록 확인
[limbs:browser]{op: "tab", mode: "switch", tab_id: $first.tab_id}            # 처음 탭으로 복귀
[limbs:browser]{op: "tab", mode: "close"}                           # 현재 탭 닫기
```

### 팝업/새 탭 자동 감지
Playwright에서 새 탭이 열리면 등록 후 활성 탭으로 전환한다. 조작 영수증의
`opened_tabs:[{tab_id,url}]`와 `active_tab_changed:{from,to}`로 확인하고 새 snapshot을 읽는다.
스스로 닫힌 팝업은 `closed_tabs`에 남으며 살아 있는 마지막 탭으로 복귀한다.
snapshot의 `tab_id`·`url`은 같은 관측 탭의 값이다. 관측 중 전환은 `SNAPSHOT_TAB_CHANGED`로 재조회를 안내한다.

### 주의사항
- 탭 전환 시 ref가 초기화됨 → 전환 후 반드시 `[limbs:browser]{op: "snapshot"}` 호출
- 활성 탭을 닫으면 가장 최근 탭으로 자동 전환
- `tab_id`는 세션에 속한 불투명 문자열이다. navigate/new/list 결과를 그대로 사용한다.

---

## iframe 작업

iframe 관리는 **단일 액션 `[limbs:browser]{op: "iframe", mode}`** — list / switch / reset.

### 기본 흐름
```
[limbs:browser]{op: "iframe", mode: "list"}                         # 페이지 내 iframe 목록 확인
[limbs:browser]{op: "iframe", mode: "switch", name: "content"}      # iframe 진입 (name/index/url 중 하나)
[limbs:browser]{op: "snapshot"}                           # iframe 내부 구조 파악
[limbs:browser]{op: "click", ref: "e3"}                           # iframe 내부에서 클릭
[limbs:browser]{op: "iframe", mode: "reset"}                        # 메인 페이지로 복귀
[limbs:browser]{op: "snapshot"}                           # 메인 페이지 구조 재파악
```

### 식별 방법 우선순위
1. `name` — iframe에 name 속성이 있으면 가장 정확
2. `url` — URL 패턴의 부분 일치로 검색
3. `index` — 위치 기반 (페이지 구조 변경 시 깨질 수 있음)

```
[limbs:browser]{op: "iframe", mode: "switch", name: "payment"}
[limbs:browser]{op: "iframe", mode: "switch", url: "checkout"}      # URL 부분 일치
[limbs:browser]{op: "iframe", mode: "switch", index: 0}             # 첫 iframe
```

---

## 쿠키/로그인 상태 관리

쿠키 관리는 **단일 액션 `[limbs:browser]{op: "cookies", mode}`** — save / load.

### 저장
```
# 로그인 완료 후
[limbs:browser]{op: "cookies", mode: "save", name: "naver"}
```
- `name`을 생략하면 현재 도메인명 자동 사용
- 쿠키 + localStorage 모두 저장
- 만료된 쿠키는 자동 제외
- 저장 위치: `indiebizOS/data/browser_cookies/{name}.json`

### 복원
```
# 먼저 브라우저를 연다(닫힌 상태에서는 load 불가).
[limbs:browser]{op: "navigate", url: "about:blank", driver: "playwright", wait: "load"}
$restore = [limbs:browser]{op: "cookies", mode: "load", name: "naver"}
# 적용 수·warnings를 확인한 뒤 목적 화면으로 이동한다.
[limbs:browser]{op: "navigate", url: "https://www.naver.com/", wait: "load"}
[limbs:browser]{op: "snapshot"}
# URL·화면으로 로그인 여부 확인. load 자체는 인증 성공을 보장하지 않는다.
```

### 주의사항
- 쿠키 파일에 인증 토큰이 포함되므로 Git에 커밋하지 말 것
- localStorage는 저장된 origin(scheme·host·port)에만 적용한다. 다른 origin이면 저장 URL로 이동하며, 리다이렉트로 origin이 달라지거나 적용에 실패하면 부분 복원 오류와 실제 적용 수를 반환한다.
- 일부 사이트는 서버측 세션이 만료되면 쿠키만으로 복원 불가
- Chrome 드라이버에서는 쿠키 복원이 보통 불필요 (실제 Chrome이 이미 로그인 상태 유지)

---

## Chrome MCP (실제 브라우저 원격 제어)

Chrome MCP는 사용자의 실제 Chrome 브라우저를 WebSocket으로 원격 제어한다.

### 연결 흐름
```
[limbs:browser]{op: "chrome", mode: "status"}                       # 연결 여부·현재 URL·탭ID·ref 수 확인
[limbs:browser]{op: "chrome", mode: "connect"}                      # 기본 MCP 서버에 연결
[limbs:browser]{op: "chrome", mode: "connect", url: "ws://..."}     # 특정 MCP 서버 지정
[limbs:browser]{op: "chrome", mode: "disconnect"}                   # 세션 종료
```

### 연결 후 사용
연결 상태에서 `driver: "auto"` 또는 `driver: "chrome"`인 액션은 모두 실제 Chrome으로 라우팅된다.

```
[limbs:browser]{op: "chrome", mode: "connect"}
[limbs:browser]{op: "navigate", url: "https://..."}       # 실제 Chrome에 열림
[limbs:browser]{op: "snapshot"}                           # Chrome의 ref 트리
[limbs:browser]{op: "click", ref: "e1"}                           # 실제 Chrome 클릭
```

### Chrome 전용 액션
다음은 Chrome MCP에서만 가능 (Playwright에는 없음):
- `[limbs:browser]{op: "find", query: "로그인 버튼"}` — 자연어로 요소 찾기
- 자연어 검색은 browser_snapshot의 ref가 안 잡힐 때 폴백으로 유용

### 주의사항
- Chrome MCP 서버는 사용자 PC의 Chrome 확장과 연동 — 별도 설치 필요
- 헤드리스가 아니므로 사용자 화면에 동작이 시각화됨 (시연용 유리)
- 자동화 봇 차단을 우회하기 쉬움 (실제 Chrome이므로)

---

## 폼 조작 (드롭다운, 입력)

### 드롭다운(select) 선택
```
[limbs:browser]{op: "snapshot"}                                    # select 요소의 ref 확인 (role: combobox)
[limbs:browser]{op: "select", ref: "e5", label: "옵션텍스트"}           # 옵션 선택
```
- `[limbs:browser]{op: "evaluate"}`로 JS 직접 조작하지 말 것 — Playwright의 select_option이 프레임워크 호환성 높음
- `label`은 화면에 보이는 표시명 정확 일치(Playwright), `value`는 단일 값, `values`는 목록이다. 셋 중 하나만 지정한다.
- Playwright의 기존 `value`·`values`는 value 또는 표시명 매칭을 유지한다. `values:[]`는 선택 해제, 다중 선택은 multiple select에서만 가능하다. 반환 `selected`는 실제 선택된 value 목록이다.
- Chrome MCP는 단일 value만 지원한다. label·다중 선택·선택 해제는 실행 전에 명시적으로 거절한다.

### 연계 select (시/도 → 시/군/구 → 읍/면/동)
상위 선택에 따라 하위 옵션이 동적으로 바뀌는 cascading dropdown:
```
[limbs:browser]{op: "select", ref: "시도ref", values: ["부산광역시"]}
[limbs:browser]{op: "wait", timeout: 1500}                                 # 하위 옵션 로드 대기
[limbs:browser]{op: "snapshot"}                                    # 하위 select의 새 ref 확인
[limbs:browser]{op: "select", ref: "시군구ref", values: ["동래구"]}
[limbs:browser]{op: "wait", timeout: 1500}
[limbs:browser]{op: "snapshot"}
[limbs:browser]{op: "select", ref: "읍면동ref", values: ["명장동"]}
```
- 각 단계마다 **wait → snapshot** 필수 (하위 옵션이 비동기 로드됨)
- snapshot 없이 이전 ref를 재사용하면 실패함

### evaluate 사용 원칙
`[limbs:browser]{op: "evaluate"}`는 **전용 도구로 해결 불가능한 경우에만** 사용:
- 클릭 → `[limbs:browser]{op: "click"}` 우선
- 텍스트 입력 → `[limbs:browser]{op: "type"}` 우선
- 드롭다운 선택 → `[limbs:browser]{op: "select"}` 우선
- 페이지 데이터 추출 → `[limbs:browser]{op: "content"}` 또는 `[limbs:browser]{op: "evaluate"}`
- WebSquare 등 특수 프레임워크에서 전용 도구가 안 될 때만 evaluate 사용

### 결과 검증 패턴
검색/폼 제출 후 반드시 결과 확인:
```
실행 후 [limbs:browser]{op: "snapshot"} 또는 [limbs:browser]{op: "content"}
결과가 기대와 다르면:
  - select 값이 제대로 적용되었는지 확인 (snapshot에서 selected 상태)
  - 같은 방법 반복하지 말고 대안 시도 (evaluate ↔ select)
  - 3회 이상 같은 방법이 실패하면 전략을 바꿀 것
```

---

## 에러 대응

### "ref를 찾을 수 없습니다"
→ `[limbs:browser]{op: "snapshot"}`을 다시 호출하여 최신 ref 확보

### "요소를 찾을 수 없습니다"
→ 페이지가 동적으로 변경되었을 수 있음. `browser_snapshot` 재호출 후 새 ref로 재시도

### "브라우저가 열려있지 않습니다"
→ 180초 비활성으로 자동 종료됨. `[limbs:browser]{op: "navigate"}`로 재시작

### "도구 실행 시간 초과" (60초)
→ IBL 엔진이 60초 내에 완료되지 않는 도구를 강제 중단. 이 에러가 나오면:
1. `[limbs:browser]{op: "screenshot"}`으로 현재 페이지 상태를 시각적으로 확인
2. 페이지가 로드되었다면 `[limbs:browser]{op: "content"}`로 텍스트만 추출 시도
3. 페이지 자체가 안 열리면 URL을 단순화하거나 다른 경로로 접근
4. 사용자가 "사이트를 방문하라"고 지시한 경우, web_search로 대체하지 말고 브라우저 전략을 바꿔서 재시도. 방문 실패 시 사용자에게 솔직히 보고

### 스냅샷에 원하는 요소가 없을 때
1. `[limbs:browser]{op: "scroll"}`로 해당 영역까지 스크롤 후 다시 스냅샷
2. `[limbs:browser]{op: "wait"}`로 동적 콘텐츠 로드 대기
3. iframe 내부 요소라면 `[limbs:browser]{op: "iframe", mode: "switch"}` 후 스냅샷
4. Chrome MCP면 `[limbs:browser]{op: "find", query: "..."}`로 자연어 검색 가능

### 콘텐츠 추출 실패 / 빈 페이지
→ v5.0에서 `[limbs:browser]{op: "content"}`가 4단계 폴백 자동 시도:
1. Playwright inner_text → 2. JS innerText → 3. JS textContent → 4. Readability (article/main 영역)
→ 모든 방법이 실패하면 진단 정보가 반환됨 (봇 차단 징후, SPA 여부 등)
→ 이 경우 `[limbs:browser]{op: "evaluate"}`로 직접 JS를 실행하거나, 브라우저를 포기하고 다른 방법 사용

### 클릭 후 새 페이지/팝업이 열렸을 때
→ `[limbs:browser]{op: "tab", mode: "list"}`로 새 탭 확인 → `[limbs:browser]{op: "tab", mode: "switch", tab_id: "..."}`로 전환

---

## v5.0 주요 변경사항

### navigate 개선
- 동적 콘텐츠 스마트 대기: `domcontentloaded` 후 자동으로 `networkidle` + body 텍스트 안정화 폴링 (최대 3초)
- 빈 페이지 경고: 텍스트 50자 미만이면 "JS 렌더링/봇 차단" 경고 반환
- `content_length` 힌트 포함

### browser_content 개선
- 4단계 폴백 추출 (위 참조)
- 모든 단계에 타임아웃 적용 (절대 무한 대기 불가)
- 빈 페이지 진단 기능 (봇 차단 징후, SPA 여부 자동 분석)

### snapshot 개선
- CDP 전체 작업 10초 타임아웃
- CDP 실패 시 JS 폴백 (interactive 요소 수집)
- 개별 노드 조회 0.5초 타임아웃, 최대 100개

### IBL 엔진 레벨 보호
- 모든 async 도구 실행에 60초 타임아웃 (엔진이 멈추는 일 방지)
- 병렬 실행 브랜치별 90초 타임아웃 (한 브랜치 hang → 해당 브랜치만 에러)

---

## 키보드 키 이름 참조

| 분류 | 키 |
|------|----|
| 일반 | Enter, Tab, Escape, Backspace, Delete, Space |
| 방향 | ArrowUp, ArrowDown, ArrowLeft, ArrowRight |
| 조합 | Control+a, Control+c, Control+v, Shift+Tab, Alt+F4 |
| 특수 | F1~F12, Home, End, PageUp, PageDown |

```
[limbs:browser]{op: "press_key", key: "Enter"}
[limbs:browser]{op: "press_key", key: "Control+a"}
```

---

## 실전 워크플로우 예시

### 검색 후 결과 수집
```
[limbs:browser]{op: "navigate", url: "google.com"}
[limbs:browser]{op: "snapshot"}                                # 검색창 ref 확인 (예 e3)
[limbs:browser]{op: "type", ref: "e3", text: "검색어", submit: true}
[limbs:browser]{op: "snapshot"}                                # 결과 링크 ref 확인
[limbs:browser]{op: "content"}                                 # 검색 결과 텍스트 추출
```

### 내장 브라우저와 로그인

```ibl
$열기 = [limbs:browser]{driver:"embedded",op:"navigate",url:"https://mail.naver.com"}
[limbs:browser]{driver:"embedded",op:"snapshot",tab_id:$열기.tab_id}
[limbs:browser]{driver:"embedded",op:"auth",mode:"status",tab_id:$열기.tab_id}
```

로그인돼 있으면 content로 읽는다. 필요하면 auth status가 돌려준 account_ref와 snapshot에서 관측한
로그인 버튼 submit_ref를 auth mode:login에 전달한다. 단일 계정은 account_ref를 생략할 수 있다.
submit_ref를 생략하면 채움만 한다. username_ref/password_ref는 자동 탐지가 모호할 때 명시한다.
비밀번호를 type/text·대화·스크립트 인자로 보내지 않는다. 다단계 로그인은 새 화면에서 다시 snapshot한다.

복수 계정 선택이나 추가 인증은 사용자에게 해당 탭에서 처리하도록 요청한다. 완료 뒤 auth mode:resume으로
돌아와 목적 화면을 확인한다. 비밀번호 필드가 없다는 사실만으로 인증 성공을 보장하지 않아 상태가 unknown일 수 있다.
resume의 ref는 호출자가 확인한 목적 화면 요소이며, 그 존재만을 인증 근거로 반환한다.
실패한 로그인 제출을 반복하지 않는다. cancel은 대기를 해제하며 이미 한 로그인은 되돌리지 않는다.

내장 snapshot의 요소 목록은 `elements`이며 각 요소의 ref·role·name을 읽는다(`snapshot`은 표시용 문자열).
content의 본문은 `content`이며 링크, 출처·문서·프레임 신원을 함께 반환한다. 기본 범위는 현재 프레임의
렌더링된 body 전체다. form 안의 공개 글과 여러 article도 포함하지만 입력칸·편집 영역의 값은 제외한다.
이미지·캔버스·숨겨진/미로딩 항목·다른 프레임은 `coverage_limits`에 명시된 별도 범위다.
iframe list/switch 후 읽고 reset으로 돌아온다. 범위 한계 자체를 실행 실패와 혼동하지 않는다.

긴 본문은 cursor와 next_offset을 다음 content의 cursor/offset으로 보내 같은 추출 스냅샷을 이어 읽는다.
본문·링크·제목·수집 시각은 그 스냅샷에 고정된다. 새 추출이나 문서 이동 뒤 옛 커서는 STALE_CURSOR다.
limit 기본 12000자, 허용 범위 500~20000자이며 offset은 0부터 센 유니코드 문자 위치다.
상한 안에서 limit를 명시하면 그 구간 선택(`truncations.scope:"selection"`)으로 받아 IBL에서 이어 읽을 수 있다.
next_offset이 null일 때 끝이다. 기본값 절단·범위 밖 limit의 보정·약50만자 수집 상한·링크80개 상한은
`PARTIAL_SOURCE`로 드러나며 `$error.partial`에 확보한 본문과 커서를 보존한다. `capture_truncated`,
`links_total/links_omitted`도 확인한다. 수집 상한에서 잃은 내용은 커서를 끝까지 읽어도 복원되지 않는다.
`source_complete:true`는 선언된 DOM 범위/선택의 수집 완료이며 웹사이트 전체나 미로딩 목록 완료를 뜻하지 않는다.
링크 URL의 쿼리는 제거되므로 쿼리로만 구분되는 다음 페이지는 snapshot에서 관측한 링크 ref를 클릭한다.
메일 본문을 열면 읽음 상태가 바뀔 수 있으므로 상태 보존 요구가 있으면 열기 전에 확인한다.

내장 드라이버는 macOS/Linux 소유자 작업용이다. Windows는 아직 연결 미지원이다. 기존 탭은 UI에서
“이 탭을 AI에 맡기기”로 공유한 뒤 tab list의 tab_id로 지정한다. 자동 생성 탭은 해당 작업에 귀속된다.
사람이 조작하거나 “AI 중지”를 누르면 USER_TAKEOVER이며 자동으로 탈취하지 않는다. 사용자가 재개를 요청한 뒤
새 snapshot으로 확인한다(auth resume/cancel이 대기를 해제한다). close는 작업 연결을 해제하고 앱을 종료하지 않는다.
AI의 탭·팝업은 처음부터 백그라운드에서 열고, 런처 창이나 사용자가 보고 있는 탭을 바꾸지 않는다.
탭·문서·ref는 숨겨진 상태로 유지되어 후속 호출을 이어갈 수 있다. 저장 계정으로 가능한 로그인도
백그라운드에서 처리한다. auth가 사용자 인증·계정 선택 필요를 반환할 때만 해당 탭 또는 팝업을
보여주고, 인증 인계 종료·취소 후 자동으로 숨긴다. 사용자가 원래 열어둔 패널은 유지한다.

현재 지원: navigate, tab, snapshot, content(text), click(single), type, press_key(관측 ref 필수), select,
check, scroll, wait(text/ref/문서 완료), iframe, auth, close. 자유 evaluate·HTML·쿠키 내보내기·파일 전송·로그·
화면 캡처는 미지원이며 다른 드라이버로 자동 이동하지 않는다. 드라이버를 바꾸려면 close 후 새로 시작한다. screenshot/evaluate/HTML이 필요한 절차는 첫 navigate부터 driver:playwright 또는 chrome을 명시한다. timeout 단위는 기존과 같은 밀리초이며 내장 요청은 최대 45초다.
사용자/작업 사이의 계정 전환을 피하고 인증 대기 중 AUTH_SESSION_BUSY는 기존 인증부터 완료한다.

### 여러 사이트 동시 비교
```
$first = [limbs:browser]{op: "navigate", url: "site-a.com/product"}
[limbs:browser]{op: "content"}                                  # 정보 수집
[limbs:browser]{op: "tab", mode: "new", url: "site-b.com/product"}       # t2 생성 + 자동 전환
[limbs:browser]{op: "content"}                                  # 정보 수집
[limbs:browser]{op: "tab", mode: "switch", tab_id: $first.tab_id}                 # 필요시 처음 탭으로 복귀
```

### Chrome MCP로 실제 브라우저 시연
```
[limbs:browser]{op: "chrome", mode: "connect"}                           # 사용자 Chrome 연결
[limbs:browser]{op: "navigate", url: "https://...", driver: "chrome"}
[limbs:browser]{op: "find", query: "로그인 버튼"}                      # 자연어 요소 검색
[limbs:browser]{op: "click", ref: "..."}                               # ref로 클릭
[limbs:browser]{op: "chrome", mode: "disconnect"}                        # 세션 종료
```

---

## 통합 전 액션명 → 새 op 매핑 (참고)

옛 코드·메모에서 다음 액션이 보이면 파서가 자동으로 새 형태로 정규화한다. 새 코드는 단일 액션 + op 파라미터만 쓰면 된다.

| 옛 이름 | 새 형태 |
|---|---|
| `[limbs:browser]{op: "tab", mode: "list"}` | `[limbs:browser]{op: "tab", mode: "list"}` |
| `[limbs:browser]{op: "tab", mode: "new", url}` | `[limbs:browser]{op: "tab", mode: "new", url}` |
| `[limbs:browser]{op: "tab", mode: "switch", tab_id}` | `[limbs:browser]{op: "tab", mode: "switch", tab_id}` |
| `[limbs:browser]{op: "tab", mode: "close"}` | `[limbs:browser]{op: "tab", mode: "close"}` |
| `[limbs:browser]{op: "iframe", mode: "list"}` | `[limbs:browser]{op: "iframe", mode: "list"}` |
| `[limbs:browser]{op: "iframe", mode: "switch", name/index/url}` | `[limbs:browser]{op: "iframe", mode: "switch", ...}` |
| `[limbs:browser]{op: "iframe", mode: "reset"}` | `[limbs:browser]{op: "iframe", mode: "reset"}` |
| `[limbs:browser]{op: "cookies", mode: "save", name}` | `[limbs:browser]{op: "cookies", mode: "save", name}` |
| `[limbs:browser]{op: "cookies", mode: "load", name}` | `[limbs:browser]{op: "cookies", mode: "load", name}` |
| `[limbs:browser]{op: "chrome", mode: "connect", url?}` | `[limbs:browser]{op: "chrome", mode: "connect", url?}` |
| `[limbs:browser]{op: "chrome", mode: "disconnect"}` | `[limbs:browser]{op: "chrome", mode: "disconnect"}` |
| `[limbs:browser]{op: "chrome", mode: "status"}` | `[limbs:browser]{op: "chrome", mode: "status"}` |

## 대상이 사라졌을 때

Playwright는 ref의 이름·역할을 유지하는 유일한 요소만 조작한다. 같은 역할의 첫 버튼·입력칸으로 대체하지 않는다. 대상이 사라지면 snapshot을 다시 읽는다. 동명 요소가 여럿이면 `REF_AMBIGUOUS`와 `candidate_count`가 반환된다. 새 snapshot만으로 중복은 해소되지 않는다. content/evaluate로 행·링크 주소를 확인한 뒤 고유한 `selector`로 지정한다(예: 관측한 객실의 `a[href^="/hold/B1?"]`).


## 작업별 Playwright 세션·확인창·이동 대기

Playwright 세션은 주체·프로젝트·에이전트·작업별로 격리된다. 작업 ID가 없는 직접
IBL 실행은 실행마다 새 세션이다. 여러 HTTP 호출을 한 작업으로 잇는 호출자는 같은
`task_id`를 요청 봉투에 보낸다. 서로 독립인 작업에는 다른 ID를 쓴다. 같은 작업의
여러 탭은 순서대로 전환하며, 병렬로 하나의 활성 탭을 조작하지 않는다.
`session_owner`·`tab_id`가 결과에 실리고 다른 세션의 탭 ID는 전환할 수 없다.
새 세션은 공용 자동 쿠키 파일을 읽거나 덮지 않는다. 로그인 재사용은 기존
`cookies save/load`로 명시한다. 180초 유휴 종료 뒤에는 다시 navigate해야 한다.
Chrome MCP는 사용자의 공유 브라우저이며 이 격리·dialog·wait 옵션을 지원하지 않는다.

```ibl
[limbs:browser]{op:"navigate",url:"https://example.com",driver:"playwright",wait:"load"}
[limbs:browser]{op:"click",ref:"관측한_ref",driver:"playwright",dialog:"accept"}
[limbs:browser]{op:"press_key",key:"Enter",driver:"playwright",dialog:"accept",dialog_text:"응답"}
```

`dialog`는 **그 조작 한 번에만** 적용된다. 기본은 dismiss이며 confirm/prompt를
자동 취소하면 `DIALOG_NOT_ACCEPTED` 실패와 `dialogs`·`dialog_dismissed`를 반환한다.
명시적 dismiss도 취소 사실을 반환한다. 실제 업무 성공은 변경된 화면에서 다시 확인한다.
`dialog_info`는 마지막 기록을 읽으며 이미 닫힌 확인창을 뒤늦게 승인하는 명령이 아니다.

navigate의 `wait_for`는 goto 완료 조건(domcontentloaded/load/networkidle), `wait`는
그 뒤의 대기다. `stable`(기본)은 기존 동적 안정화, `load`는 추가 대기 생략,
`idle`은 networkidle까지 기다리되 시간 초과는 실패다. 정적 화면에는 load를 쓰고
동적 화면은 stable 또는 후속 wait(selector/text)로 확인한다. `session_started:true`는
이번 이동에 브라우저 기동이 포함됐다는 뜻이다.
iframe list와 switch의 index는 메인 프레임을 제외한 0부터의 같은 목록이다.
name/id는 정확 일치, url은 부분 일치이며 메인으로 복귀할 때는 mode:reset을 쓴다.


DOM 동의·약관 버튼은 자동 클릭하지 않는다. snapshot으로 내용을 읽고 필요한 버튼을
명시적으로 click한다. 클릭 성공은 도구 조작의 완료이며 업무 성공은 완료 화면·산출물로 확인한다.
iframe switch 뒤 snapshot도 그 프레임만 읽으며 `frame:{kind,name,url}`을 반환한다.
프레임은 명시적인 reset 또는 navigate(goto/back/forward)까지 유지된다. navigate는
실패하더라도 메인 프레임으로 복귀한다. 여러 호출에 걸쳐 switch→snapshot→check를
이어 쓸 수 있으며, 실패 후 새 페이지로 이동할 때 이전 프레임 문맥이 남지 않는다.

탭 전환은 `tab list`의 `tab_id`를 사용한다. `mode:"switch", index:0`은 현재 목록의 첫 탭이다. 오래 유지하는 연결에는 위치보다 tab_id를 사용한다.


## 드래그와 조작 결과 확인

`[limbs:browser]{op:"drag", source_ref:"e1", target_ref:"e2", driver:"playwright"}`는
snapshot의 이름·역할을 영수증 `source`·`target`에 남긴다. 놓는 자리는 화면 안의 작은 요소나
칸 제목을 권장한다. 긴 영역은 보이는 부분에서 실제로 닿는 점을 고르고, 두 대상을 한 화면에
놓을 수 없거나 가려졌으면 `DRAG_NOT_IN_VIEW`로 조작 전에 거절한다. 누른 뒤 스크롤·시작 대상
변경은 `DRAG_TARGET_UNVERIFIED`와 관측으로 반환한다. 성공도 `verification:gesture_only`이며
서버 저장 성공의 증거는 아니다. 화면과 새로 읽은 저장 결과를 대조하고 실패한 항목을 보존한다.
Chrome 드라이버는 두 ref의 드래그 좌표 연결을 지원하지 않아 명시 오류를 반환한다.

## 네트워크 기록

Playwright는 세션 시작부터 각 탭의 HTTP 응답과 응답 없는 요청 실패를 수집한다.
`[limbs:browser]{op:"logs", mode:"network"}`로 조회한다. `status:409` 같은 HTTP 오류와
`status:null`·`failure`가 있는 연결 실패를 구분한다. 요청/응답 본문·헤더는 수집하지 않는다.
기록은 세션의 최근 500건 중 기본 50건을 반환한다(`capacity`, `retained_count`, `count`).
진행 중 요청은 아직 없을 수 있으며 이 목록만으로 전체 요청 성공을 단정하지 않는다.
`capturing:false`는 빈 성공이 아니라 `NETWORK_CAPTURE_INACTIVE` 실패다. 새 세션은 새로 수집한다.


## 조작 중 브라우저 사건과 다운로드 (Playwright)

click·press_key·evaluate 등은 같은 사건 수집기를 쓴다. 관측된 사건만 `opened_tabs`,
`closed_tabs`, `navigated`(이전/새 URL, 관측된 문서 status_code), `downloads`,
`file_chooser`, `page_errors`에 담고 활성 변경은 `active_tab_changed`로 알린다.
`page_errors`는 `logs mode:"console"`에도 `source:"pageerror"`로 남는다.
`file_chooser`가 보이면 snapshot으로 파일 입력을 찾아 `upload_file`에 ref/selector와 path를 준다.
파일 선택창을 열었다고 업로드가 완료된 것은 아니다.

영수증은 그때까지 **관측한** 사실이다(`event_scope:"pending_and_during_operation"`).
클릭·입력 등의 반환 전 짧은 사건 전달 유예(80ms)가 있으며 페이지 안정화나 인과관계를 보장하지 않는다.
더 늦은 사건은 다음 조작/조회 영수증에 남고, 필요한 화면 조건은 `wait`로 기다린다.
보류 사건은 최근 256건이며 초과량은 `events_omitted`로 알린다.
입력 중 탭이 닫혀 키 해제를 끝내지 못하면 `verification:"page_closed_during_input"`,
`input_completed:false`로 닫힘 관측을 돌려준다. 남은 탭에서 결과를 확인한다.

```ibl
$받음 = [limbs:browser]{op:"click", selector:"a[download]", path:"outputs/export.bin", driver:"playwright"}
return $받음.downloads
```

click·press_key·evaluate·type의 `path`는 내려받기 저장 위치로 쓸 수 있다. 생략하면
`outputs/browser_downloads/<고유번호>/<서버 파일명>`에 저장한다. 같은 조작에서 여러 파일이면
명시 경로의 두 번째 파일부터 `_2`, `_3`를 붙인다. 텍스트·이진·Blob 파일 모두 브라우저가 받은
바이트를 저장하며, 서버 파일명은 기본 경로의 파일명 부분으로만 사용한다.
`downloads`의 `saved:true`·`path`·`size`가 저장 영수증이다. 저장 완료는 최대 30초 기다리며
실패는 `DOWNLOAD_NOT_SAVED`와 파일별 오류로 반환한다. 늦게 시작된 내려받기는 다음 영수증에
실리고, 조작의 path 지정이 끝난 뒤 시작됐다면 기본 위치에 저장한다.
세션을 닫아도 저장된 파일은 남는다. 파일의 업무 내용은 필요에 따라 재독·대조한다.

네트워크는 컨텍스트에서 수집하므로 새 탭의 첫 요청도 포함한다. 내려받기 HTTP 응답이
브라우저에서 노출되지 않는 경우 상태코드를 만들어내지 않는다(`coverage_limits`).
`logs mode:"network"`의 `download_history`는 최근 100건의 저장 결과를 별도로 제공한다.
파일 전환 때 문서 요청이 `net::ERR_ABORTED`로 끝날 수 있으므로 같은 URL의 저장 영수증과
함께 해석한다. Blob 내려받기에는 HTTP 요청 자체가 없다.

슬라이더는 `type` 대상이 아니다. snapshot의 `value`, `min`, `max`, `step`을 읽고 click으로
초점을 준 뒤 `press_key`의 Home/End·ArrowRight/ArrowLeft로 조절하고 값을 다시 읽는다.
HTML range는 min/max/step(생략 시 0/100/1)을 표시한다. 사용자 정의 ARIA slider는
공개한 min/max만 표시할 수 있으며 step을 추정하지 않는다.
