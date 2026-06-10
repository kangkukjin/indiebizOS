# Browser Action 사용 가이드

브라우저 자동화 IBL 어휘. Playwright(헤드리스) 기본, Chrome MCP(실제 Chrome 원격 제어) 선택.
데스크톱 일반 앱 자동화는 `[limbs:screen]` (별도 가이드 참조).

## 핵심 원리: Screenshot → 판단 → Action

**모르는 사이트를 방문할 때는 반드시 시각적 피드백(screenshot)을 먼저 사용하라.**
screenshot 없이 CSS 셀렉터나 ref를 추측하면 높은 확률로 실패한다.

### 기본 흐름 (모르는 사이트)
```
[limbs:browser]{op: "navigate", url: "https://..."}
[limbs:browser]{op: "screenshot"}                          → 화면 확인
[limbs:browser]{op: "snapshot"}                    → ref 트리 확보
[limbs:browser]{op: "click", ref: "e5"} 또는 [limbs:browser]{op: "type", ref: "e3", text: "..."}
[limbs:browser]{op: "screenshot"}                          → 결과 검증
```

### 익숙한 사이트
```
[limbs:browser]{op: "navigate", url: "..."}
[limbs:browser]{op: "snapshot"}                    → ref 확인
[limbs:browser]{op: "click", ref: "e5"}
[limbs:browser]{op: "snapshot"}
```

원칙: **확인하지 않은 것을 추측하지 마라.** 페이지 구조를 모르면 screenshot으로 먼저 확인.

### ref란?
- `[limbs:browser]{op: "snapshot"}` 호출 시 각 요소에 `e1`, `e2`, `e3` ... 형태의 고유 ID가 부여됨
- 이후 `[limbs:browser]{op: "click", ref: "e5"}`, `[limbs:browser]{op: "type", ref: "e3"}` 등으로 정확한 요소 지정
- 페이지가 변경되면(네비게이션, 동적 콘텐츠) **반드시 `browser_snapshot`을 다시 호출**해서 새 ref 확보

### snapshot vs screenshot vs browser_content
| 액션 | 용도 | 반환 |
|------|------|------|
| `[limbs:browser]{op: "snapshot"}` | 상호작용용 (ref 포함) | 요소 구조 + ref |
| `[limbs:browser]{op: "screenshot"}` | 시각적 확인용 | PNG 파일 경로 |
| `[limbs:browser]{op: "content"}` | 텍스트 읽기용 | 페이지 텍스트 |

**원칙**: 상호작용이 목적이면 항상 `browser_snapshot`. screenshot은 시각 확인이 필요할 때만.

---

## 드라이버 선택 (Playwright vs Chrome MCP)

대부분의 액션은 `driver` 파라미터로 어떤 드라이버를 쓸지 결정한다.

| 값 | 동작 |
|---|---|
| `"auto"` (기본) | Chrome MCP 연결되어 있으면 Chrome, 아니면 Playwright |
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

---

## 다중 탭 사용법

탭 관리는 **단일 액션 `[limbs:browser]{op: "tab", op}`** — list / new / switch / close.

### 기본 흐름
```
[limbs:browser]{op: "navigate", url: "site-a.com"}        # t1 탭에서 열림
[limbs:browser]{op: "tab", mode: "new", url: "site-b.com"}          # t2 탭 생성 + 자동 전환
[limbs:browser]{op: "tab", mode: "list"}                            # 열린 탭 목록 확인
[limbs:browser]{op: "tab", mode: "switch", tab_id: "t1"}            # t1로 복귀
[limbs:browser]{op: "tab", mode: "close"}                           # 현재 탭 닫기
```

### 팝업/새 탭 자동 감지
링크 클릭으로 새 탭이 열리면 자동으로 감지되어 세션에 등록됨. `[limbs:browser]{op: "tab", mode: "list"}`로 확인.

### 주의사항
- 탭 전환 시 ref가 초기화됨 → 전환 후 반드시 `[limbs:browser]{op: "snapshot"}` 호출
- 활성 탭을 닫으면 가장 최근 탭으로 자동 전환
- `tab_id`는 `t1`, `t2` 등 문자열 (`list` 결과에서 확인)

---

## iframe 작업

iframe 관리는 **단일 액션 `[limbs:browser]{op: "iframe", op}`** — list / switch / reset.

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

쿠키 관리는 **단일 액션 `[limbs:browser]{op: "cookies", op}`** — save / load.

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
# 새 세션에서
[limbs:browser]{op: "navigate", url: "naver.com"}
[limbs:browser]{op: "cookies", mode: "load", name: "naver"}
# → 자동으로 페이지 리로드되며 로그인 상태 복원
```

### 주의사항
- 쿠키 파일에 인증 토큰이 포함되므로 Git에 커밋하지 말 것
- localStorage 복원은 같은 도메인에서만 작동 (다른 도메인이면 자동으로 해당 URL로 이동 후 복원)
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
[limbs:browser]{op: "select", ref: "e5", values: ["옵션텍스트"]}           # 옵션 선택
```
- `[limbs:browser]{op: "evaluate"}`로 JS 직접 조작하지 말 것 — Playwright의 select_option이 프레임워크 호환성 높음
- `values`에는 옵션의 **텍스트** 또는 **value** 사용 가능

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

### 로그인이 필요한 사이트 작업
```
[limbs:browser]{op: "navigate", url: "site.com/login"}
[limbs:browser]{op: "cookies", mode: "load", name: "site"}               # 저장된 상태 복원 시도
# (로그인 안되어있으면) 수동 로그인 진행
[limbs:browser]{op: "cookies", mode: "save", name: "site"}               # 상태 저장
# 이후 작업 수행
```

### 여러 사이트 동시 비교
```
[limbs:browser]{op: "navigate", url: "site-a.com/product"}     # t1
[limbs:browser]{op: "content"}                                  # 정보 수집
[limbs:browser]{op: "tab", mode: "new", url: "site-b.com/product"}       # t2 생성 + 자동 전환
[limbs:browser]{op: "content"}                                  # 정보 수집
[limbs:browser]{op: "tab", mode: "switch", tab_id: "t1"}                 # 필요시 t1로 복귀
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
