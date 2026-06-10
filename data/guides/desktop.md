# Screen (데스크톱) 자동화 가이드 (macOS)

`[limbs:screen]{op: ...}` 단일 액션으로 macOS 화면(좌표 기반, 브라우저 밖 일반 앱)을 제어한다. (구 `[limbs:desktop]` — 2026-06-04 개명)
브라우저는 `[limbs:browser]{op: "click"}`·`[limbs:browser]{op: "type"}` 등 browser_action을 사용하라. 데스크톱과 브라우저는 **다른 도구다.**

## 핵심 원리: Snapshot → 판단 → Action → Snapshot

**좌표를 추측하지 말 것.** 클릭 전에 `snapshot`으로 화면을 **읽어서** 좌표를 얻는다.

- `snapshot` (권장 1순위) — 화면을 **구조로 독해**: UI 요소(역할/이름)와 글자(OCR)를 **클릭 좌표와 함께** 반환. 브라우저 snapshot의 데스크톱 판.
  - 층1 **AX 접근성 트리**: 버튼/입력칸의 role·title·value + center 좌표 (예: `{role:"AXButton", title:"뒤로", center:[168,120]}`).
  - 층2 **Vision OCR**: AX가 못 주는 글자(캔버스/이미지)를 center 좌표와 함께.
  - 좌표는 click과 같은 1280×800 가상공간 → 그대로 `{op:"click", x, y}`.
- `screenshot` — 픽셀 이미지만 필요할 때(시각 모델로 직접 보기). 좌표 추측이 필요해 snapshot보다 비권장.

```
[limbs:screen]{op: "snapshot"}                      # 화면 독해 (요소+글자+좌표)
→ elements/ocr_lines에서 대상의 center 좌표 선택
[limbs:screen]{op: "click", x: 168, y: 120}         # 정밀 클릭
[limbs:screen]{op: "snapshot"}                      # 결과 재확인
```

원칙: **불확실하면 snapshot.** 매 동작 후 결과 검증도 snapshot이 기본이다.
AX가 0개면(권한 미부여/앱 a11y 미노출) `ocr_lines`로 폴백한다 — 손쉬운 사용 권한을 켜면 AX 구조독해가 살아난다(클릭과 같은 권한).

---

## 좌표 시스템 (가장 중요)

- 모든 좌표는 **1280×800 가상 해상도 기준**.
- 실제 디스플레이 해상도(예: 2880×1800 Retina)로 핸들러가 자동 변환한다.
- 즉, screenshot 결과 이미지도 1280×800으로 리사이즈되어 반환 → 그 위의 좌표를 그대로 click에 넘기면 된다.

### 범위 검증
- x: 0 ~ 1280, y: 0 ~ 800
- 벗어나면 ValueError. 예: `{x: 1500, y: 400}` → 에러.

### FAILSAFE
- 마우스를 화면 모서리(0, 0)로 이동시키면 pyautogui가 즉시 정지한다.
- 의도된 비상 정지 메커니즘. 정상 동작에는 영향 없음.

---

## 9개 op 사양

| op | 필수 파라미터 | 선택 파라미터 | 용도 |
|---|---|---|---|
| `screenshot` | (없음) | `x, y, width, height` | 전체 또는 영역 캡처 |
| `click` | `x, y` | `button` (left/right/middle), `clicks` (1/2), `screenshot_after` | 좌표 클릭 |
| `type` | `text` | `interval` (키 간격, 초), `screenshot_after` | 텍스트 입력 (한글 OK) |
| `key` | `key` | `screenshot_after` | 키/단축키 (예: `'cmd+c'`, `'enter'`) |
| `mouse_move` | `x, y` | `duration` (이동 시간) | 커서 이동만 (클릭 없음) |
| `drag` | `start_x, start_y, end_x, end_y` | `duration`, `button`, `screenshot_after` | 드래그 |
| `scroll` | (없음) | `x, y, direction` (up/down/left/right), `amount` | 스크롤 |
| `cursor_position` | (없음) | — | 현재 커서 좌표 반환 |
| `screen_info` | (없음) | — | 해상도/스케일/권한 정보 |

### 자동 screenshot
다음 op는 기본값으로 동작 후 screenshot을 자동 첨부한다 (변경하려면 `screenshot_after: false`):
- `click`, `drag`, `scroll`

다음 op는 기본값이 false (변경하려면 `screenshot_after: true`):
- `type`, `key`

---

## 표준 워크플로우

### 1) 처음 보는 앱 화면 탐색
```
[limbs:screen]{op: "screen_info"}              # 권한·해상도 확인
[limbs:screen]{op: "screenshot"}               # 전체 화면
→ 이미지 분석으로 클릭 대상 좌표 결정
[limbs:screen]{op: "click", x: ..., y: ...}    # 동작 (자동 screenshot 포함)
```

### 2) 입력 필드에 텍스트 입력
필드를 클릭해서 포커스를 먼저 줘야 한다. 직접 type만 호출하면 다른 곳에 입력될 수 있다.
```
[limbs:screen]{op: "click", x: 600, y: 300}    # 필드 클릭
[limbs:screen]{op: "type", text: "안녕하세요"} # 입력
```

### 3) 단축키
조합키는 `+`로 구분. 키 이름은 pyautogui 표기를 따른다.
```
[limbs:screen]{op: "key", key: "cmd+c"}        # 복사
[limbs:screen]{op: "key", key: "cmd+shift+s"}  # 다른 이름으로 저장
[limbs:screen]{op: "key", key: "enter"}        # 엔터
[limbs:screen]{op: "key", key: "escape"}       # ESC
[limbs:screen]{op: "key", key: "cmd+space"}    # Spotlight (앱 실행)
```

자주 쓰는 키: `enter`, `tab`, `escape`, `space`, `backspace`, `delete`,
`up`/`down`/`left`/`right`, `cmd`, `shift`, `alt`(option), `ctrl`.

### 4) 드래그 (파일 이동·창 크기 조정)
```
[limbs:screen]{op: "drag", start_x: 200, start_y: 400, end_x: 800, end_y: 400}
```

### 5) 긴 페이지 스크롤
스크롤은 좌표 생략 시 현재 커서 위치 기준.
```
[limbs:screen]{op: "scroll", direction: "down", amount: 5}
```

---

## desktop vs browser_*

| 상황 | 사용할 도구 |
|---|---|
| Safari/Chrome 안의 웹페이지 | `[limbs:browser]{op: "navigate"}` + `[limbs:browser]{op: "click", ref}` (browser_action) |
| Finder, Notion, Slack 데스크톱 앱, 시스템 환경설정 | `[limbs:screen]{op}` |
| macOS 전역 단축키 (Cmd+Space, Mission Control 등) | `[limbs:screen]{op: "key"}` |
| 웹페이지 안 요소 클릭 | `[limbs:browser]{op: "click", ref}` (정확) > `[limbs:screen]{op: "click", x, y}` (좌표 추측 = 약함) |

**원칙**: 가능하면 browser_*. 좌표보다 ref가 정확하다. desktop은 브라우저로 접근 불가한 영역에만.

---

## 권한 (macOS)

`screen_info`로 권한 상태를 확인할 수 있다. 권한 부족 시 동작이 무음 실패할 수 있다.

| 권한 | 어디서 | 무엇이 필요 |
|---|---|---|
| 화면 기록 | 시스템 설정 → 개인정보 보호 → 화면 기록 | screenshot |
| 손쉬운 사용 | 시스템 설정 → 개인정보 보호 → 손쉬운 사용 | click·type·key·drag·scroll·mouse_move |

권한 부여 후 백엔드 프로세스(Python)를 재시작해야 반영된다.

---

## 흔한 함정

- **좌표 추측**: screenshot 없이 "대충 600, 400" 같은 추측 클릭은 실패한다. 반드시 screenshot으로 확인.
- **이전 화면 좌표 사용**: 페이지·창 상태가 바뀌면 좌표도 바뀐다. 동작 후 screenshot으로 다시 파악.
- **type 전에 click 누락**: 입력 대상에 포커스가 없으면 엉뚱한 곳에 입력된다.
- **단축키 표기**: `cmd-c`(X) → `cmd+c`(O). `command+c`도 인식되지만 `cmd+c` 권장.
- **drag 좌표 범위**: 시작·끝점 모두 1280×800 안이어야 한다.
- **브라우저 안에서 desktop 사용**: 좌표 추측이 ref보다 약하다. browser_action을 우선.

---

## 조합 예시

### Spotlight로 앱 실행
```
[limbs:screen]{op: "key", key: "cmd+space"}
[limbs:screen]{op: "type", text: "Calculator"}
[limbs:screen]{op: "key", key: "enter"}
```

### Finder에서 파일 복사 → 다른 폴더에 붙여넣기
```
[limbs:screen]{op: "screenshot"}
→ 파일 위치 확인
[limbs:screen]{op: "click", x: ..., y: ...}    # 파일 선택
[limbs:screen]{op: "key", key: "cmd+c"}
→ 대상 폴더로 이동
[limbs:screen]{op: "key", key: "cmd+v"}
```

### 화면 일부만 캡처해서 분석
```
[limbs:screen]{op: "screenshot", x: 0, y: 0, width: 640, height: 400}
```

---

## 통합 전 액션명 → 새 op 매핑 (참고)

옛 코드·메모에서 다음 액션이 보이면 파서가 자동으로 새 형태로 정규화한다. 새 코드는 `desktop{op}`만 쓰면 된다.

| 옛 이름 | 새 op |
|---|---|
| `desktop_screenshot` | `screenshot` |
| `desktop_click` | `click` |
| `desktop_type` | `type` |
| `desktop_key` | `key` |
| `mouse_move` | `mouse_move` |
| `desktop_drag` | `drag` |
| `desktop_scroll` | `scroll` |
| `cursor_position` | `cursor_position` |
| `desktop_screen_info` | `screen_info` |
