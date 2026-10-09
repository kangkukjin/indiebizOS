# 47회차 — 브라우저 액트: 안 써 본 손동작으로 주문 콘솔 아침 정리(무한 스크롤·hover 메뉴·끌어다 놓기·더블클릭 편집·오른쪽 클릭 메뉴·화면 폭·기록·쿠키 복원)

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS` main `0ed710a3`(46회차 수리 포함)에서 훈련했다. 시스템 코드·설정·어휘 수리와 관용구 등록은 하지 않았다(발견만).
축 ① 44~46회차가 쓰지 않은 `limbs:browser` 손동작이 가이드 한 줄만으로 서는가 ② 화면이 말하는 것과 저장된 것이 다를 때 진실을 가려 보고하는가 ③ 독립 AI 가 같은 이음새에서 무엇을 고르는가.

## 1. 판정과 산출물

| 실행 | 검사 | 실제 실행 | 요구 달성 | 시간 |
|---|---|---|---:|---:|
| 훈련자 v0→v1 | v0 TYPE 1(`table:groupby` 반환은 `{items}` 봉투) → v1 issues 0(incomplete) | 첫 실행 정상 9.69초·24,273단계. 스크롤 5회로 40건, hover→'지연만', 카드 5장 각각 drag→더블클릭·입력·Enter→(3장) 오른쪽 클릭 메뉴, 새로 불러 대조, 390×844 요약·스크린샷, 쿠키 저장→close→새 브라우저 복원 | **달성** 검수 18/18 — 서버 이동 5건(대상 카드만)·메모 5·우선 3·로그인 1회 | 9.69초 |
| 변형 A(W-1017 이동 409, 같은 프로그램) | — | 정상 9.79초 | **달성** 20/20 — 화면은 '오늘 처리', 새로 부르면 '지연' → `ui_only:["W-1017"]`·판정 "일부 저장 안 됨", 콘솔 오류 2줄(409·`move failed W-1017`)을 근거로 보고 | 9.79초 |
| 변형 B(방침만 변경, 같은 프로그램) | — | 정상 9.21초 | **달성** 18/18 — to '제작 중'·메모 '재작업 배정'·우선 1건(W-1033) | 9.21초 |
| 독립 AI(변형 A 서버, 제약 없음) | 검사 거절·수정 다수(`$rejected`+`code_edits` 2회 포함) | 정상 ep4521, **도구 18 전부 execute_ibl(Bash 0·Python 0)**, 최대 8.9K자 프로그램. drag 함정을 밟아 W-1004 를 세 번째에 `evaluate` 로 DragEvent 를 직접 일으켜 이동 | **달성** 정규화 검수 17/18 — 서버 최종 상태·보고(저장 안 된 W-1017, 409, 네트워크 미수집, 복원) 전부 맞음. 미달 1 = drag 실패의 **원인 진단**("drop 이 안 일어남·요청 없음" — 실제로는 다른 카드 W-1033 이 두 번 끌렸다) | 457.1초 |

- [사전 과제](task.md) · 프로그램 [v0](drafts/tidy_v0.ibl)→[v1](drafts/tidy_v1.ibl)(실행본, 세 조건 무수정)
- 훈련자 증거: 검사·실행 [evidence/trainer_*.json](evidence/) · 검수 [base](evidence/trainer_base_qa.json)·[flaky](evidence/trainer_flaky_qa.json)·[b](evidence/trainer_b_qa.json) · [서버 상태](evidence/server_state/) · 산출물 [artifacts/trainer](artifacts/trainer/)
- 탐침 12: [로그인·스크롤·wait](evidence/probe_login_scroll.json) · [hover 메뉴](evidence/probe_hover_menu.json)·[하위 링크 클릭](evidence/probe_hover_click.json) · drag [첫 관측](evidence/probe_board_drag.json)·[둘째](evidence/probe_board_drag2.json)·[제목 대상 대조](evidence/probe_board_drag3_heading.json)·[최소 재현](evidence/probe_drag_min_repro.json) · [더블클릭·Enter·오른쪽 클릭 메뉴](evidence/probe_board_dbl_ctx.json) · [기록·화면 폭·스크린샷·쿠키 저장](evidence/probe_logs_resize.json)·[네트워크 기록 켜기 시도](evidence/probe_logs_network_start.json) · 쿠키 [닫은 뒤 복원](evidence/probe_close_same.json)·[새 작업 세션 복원](evidence/probe_cookies_new_task.json)
- 대조 실험: [Playwright 직접 호출](evidence/control_playwright_drag.json)([코드](harness/control_playwright_drag.py))
- 독립 AI: [요청문](evidence/ai_request.txt) · [검수](evidence/agent_free_qa.json) · [지표](evidence/ai_free_metrics.json)·[사건](evidence/ai_free_events.json) · [산출물](artifacts/agent/)
- 외부 효과: 로컬 합성 서버뿐. `data/browser_cookies/lsi47_*.json` 5개 생성 → 종료 때 삭제. 데스크톱 조작 0.

## 2. 과제·환경·작성

합성 콘솔([site_server.py](harness/site_server.py), stdlib): 주문 40건. `/orders` 는 12건씩 스크롤로 더 불러옴(300ms 지연), '보기' 메뉴는 CSS `:hover` 로만 열림, `/board` 는 HTML5 끌어다 놓기(낙관적 UI — 먼저 옮겨 보이고 POST, 실패 알림은 1.5초 뒤 사라짐)·더블클릭 메모 입력칸·자체 오른쪽 클릭 메뉴, `/summary` 는 fetch 로 채우고 폭 600 이하에서 '모바일 요약' 만 보이며 `console.warn` 1건. `--locked ID` 는 그 주문 이동을 409 로 거절. 서버 state.json 이 oracle.
**환경**: `/ibl/execute` `project_id:"수동모드"` `origin:"training"` `task_id` 명시, 예산 100만 단계, 모델 0, `driver:"playwright"`.
**분해**: 보조 4(`참조`·`주문행`·`보드상태`·`카드정리`) + 최상위 7단(로그인·스크롤 반복 → hover·지연만 → 카드마다 정리 → 화면 상태 기록·기록 읽기·새로 불러 저장 상태 → 요약 390×844 → 쿠키 저장·close·새 브라우저 복원·재확인 → 판정·파일). "화면이 말한 것(`ui_col`)" 과 "새로 부른 뒤(`saved_col`)" 를 카드마다 둘 다 남겨 `ui_only` 로 가른다.
**작성 조건**: browser_action.md·교재·describe 1·탐침 12. `limbs:browser` 패키지 코드 열람 0. 검사 수정 1회(작성자 오류 — groupby 봉투). f-string 안 따옴표 삼항은 이번엔 문구를 변수로 먼저 계산해 재발 0. 작성 시간: 서버·자료 약 3분, 탐침 약 6분, 초안·수정 약 3분.
drag 의 놓는 자리는 탐침에서 함정(L47-1)을 본 뒤 칸 영역 대신 **칸 제목**으로 정했다 — 영역으로 쓴 초안이었다면 첫 실행에서 틀린 카드가 옮겨졌을 것이다.

## 3. 검수와 독립 AI 비교

결정론 [verify.py](harness/verify.py): result.json + report.md + PNG 헤더(폭) + 서버 state(더 불러오기 offset 12·24·36, 이동 기록이 대상 카드뿐인지, 메모·우선 표시, 로그인 횟수, 최종 칸별 건수). 스크린샷은 눈으로도 확인(모바일 요약 6줄).

### 독립 AI (ep4521, 변형 A 서버, 제약 없음)

| 볼 것 | 관측 |
|---|---|
| 풀이 방식 | **전부 IBL**. 입력 읽기 → 화면 구조 파악(snapshot·html) → 로그인·스크롤·hover·보드를 프로그램 단위(4~9K자)로. 44~46회차의 자유 조건은 세 번 다 Python Playwright 였다(요청문 꼬리는 46회차 조건 A 와 같은 문장) — 이번엔 제약 없이 IBL 을 골랐다. 표본 1회이며 원인(46회차 수리·가이드·회상)은 가리지 않았다 |
| 분할·재사용 | `$ref` 로 앞 결과를 값으로 넘김(4회), `read_result` 1회, 거절된 원문을 `$rejected`+`code_edits` 로 조각 수정(2회). 호출 18회 — 46회차 조건 B(40회)의 절반 이하 |
| 방법 발견 | hover·더블클릭·오른쪽 클릭·resize·cookies 는 첫 시도에 통과. drag 는 두 번 "성공" 뒤 새로 부른 보드로 미이동을 알아채고 `evaluate` 로 dragstart/dragover/drop 을 직접 발생시켜 완수. 네트워크 기록 0건을 스스로 보고하고 콘솔 409 와 `performance` 기록으로 대체 |
| 완료 판정 | 새로 부른 보드 기준 카드별 표, W-1017 은 재시도도 409 임을 확인하고 "사람이 충돌 원인 확인" 으로 남김. 조작 직후 화면 숫자와 새로 부른 숫자가 달랐던 것도 적음 |
| 놓친 것 | W-1004 실패의 원인을 "drop 미발생·요청 없음" 으로 적었다. 서버 기록은 그 두 번의 drag 가 **W-1033 을 옮겼다**(1번째 지연→오늘 처리, 5번째 오늘 처리→오늘 처리)고 말한다. W-1033 도 옮길 대상이라 최종 상태가 우연히 맞았다 — 대상이 아닌 카드였다면 엉뚱한 주문이 옮겨진 채 보고에서 빠졌을 것이다 |
| 비용 | 457.1초, 입력 3,297,098/출력 44,308(cache_read 2,911,515), 로그인 4회(세션을 새로 열 때마다). 훈련자 9.7초·모델 0 |

훈련자 갭이 독립 AI 에서도 밟혔는가: L47-1(drag 가 다른 카드를 끎) — 밟음(2회, 원인 오진). L47-2(네트워크 기록 0건) — 밟고 정확히 보고. L47-3(쿠키 복원 순서) — 스스로 해결.

## 4. 발견과 공통 개선 방향

### 46회차 수리의 실전 확인
동의 버튼 자동 클릭 제거·navigate 메인 프레임 복귀는 이번 과제에 해당 화면이 없어 확인 대상이 아니다. 실행마다 새 세션·`session_owner` 반환·`wait:"load"` 는 재발 없음.

### L47-1 — drag 가 "성공" 하고 지정하지 않은 요소를 옮긴다
정직 보고 결함(원인은 상류). 화면 맨 위(scrollY 0)에서 카드 W-1004 를 '오늘 처리 칸' 영역(화면 아래까지 긴 region)에 끌면 결과는 `success:true`·`dragged:" → "` 인데 **옮겨진 것은 W-1033** 이다(DOM·서버 기록 일치, [최소 재현](evidence/probe_drag_min_repro.json)). 대상 영역의 중심이 화면 밖이라 누른 뒤 페이지가 237px 스크롤되고, 끌기 시작점은 화면 좌표 그대로라 그 자리에 올라온 다른 카드가 잡힌다(W-1004 중심 y331 → 스크롤 뒤 그 자리 = W-1033). 스크롤이 필요 없는 대상(칸 제목)에는 정확하다([대조](evidence/probe_board_drag3_heading.json)).
**같은 화면에서 Playwright `locator.drag_to` 를 직접 불러도 결과가 같다**([control](evidence/control_playwright_drag.json)) — IndieBiz 쪽 좌표 계산 잘못이 아니라 Playwright/Chromium 의 HTML5 끌기 동작이다. 어휘의 문제는 그것을 **검증 없이 성공으로 돌려주고, 영수증에 무엇을 끌었는지 없다**는 데 있다. 독립 AI 는 이 함정을 두 번 밟고 원인을 잘못 적었다.
처방: drag 전에 source·target 을 한 화면에 들어오게 스크롤하고(둘 다 못 들어오면 그 사실을 반환), 누른 뒤 스크롤 위치가 바뀌었으면 실패 또는 `scrolled_during_drag` 경고. 가이드 drag 절에 "놓는 자리는 화면 안의 작은 요소로, 결과는 새로 읽어 확인" 한 줄.

### L47-2 — 네트워크 기록은 켤 방법이 없고 0건을 성공으로 돌려준다
계약 공백. `logs mode:"network"` 는 언제 불러도 `{logs:[], count:0, capturing:false}` 이고, 계약의 어떤 인자(value·scope·query)로도 수집이 시작되지 않는다([탐침](evidence/probe_logs_network_start.json)). 콘솔 기록은 수집된다(경고·오류·브라우저의 "Failed to load resource … 409"). `capturing:false` 를 읽지 않는 프로그램은 "실패한 요청 0건" 으로 오독한다. 훈련자·독립 AI 둘 다 `capturing` 을 보고 "수집 안 됨" 으로 적었다.
처방: 수집 시작 방법을 계약에 싣거나(세션 시작부터 수집), 수집 중이 아니면 0건 성공 대신 "수집 안 됨" 을 값이 아닌 상태로 반환.

### L47-3 — 쿠키 복원은 "열고 → 불러오고 → 다시 열기" 인데 안내는 한 단계다
안내 공백. `cookies load` 는 브라우저가 열려 있어야 해서 닫은 직후에는 "브라우저가 열려있지 않습니다" 로 거절되고([탐침](evidence/probe_close_same.json)), 로그인 화면에서 불러오면 "상태 복원 완료. 로그인 상태가 유지됩니다" 라고 답하지만 화면은 여전히 로그인 화면이다(가이드: "자동으로 페이지 리로드되며 로그인 상태 복원" — 로그인 주소를 다시 불러 봐야 로그인 화면). 원하는 화면으로 한 번 더 navigate 해야 복원이 보인다([탐침](evidence/probe_cookies_new_task.json)). 훈련자·독립 AI 모두 풀었으나 순서는 탐침으로만 알 수 있었다.
처방: 가이드 복원 절을 "navigate(아무 화면) → load → 목적 화면 navigate → 주소로 확인" 으로, load 응답의 "유지됩니다" 를 "쿠키 N개 적용 — 목적 화면을 다시 여세요" 로.

### 관측(갭 아님)
- 조작 영수증의 대상 이름이 비어 있다: `clicked:" (e33)"`·`hovered:" (e6)"`·`double_clicked:" (e44)"`·`dragged:" → "`. ref 만 남아 사후에 무엇을 눌렀는지 영수증으로 알 수 없다(L47-1 의 진단을 어렵게 한 요인).
- `scroll` 은 한 번에 500px 고정이고 양·끝까지 인자가 없다 — 끝까지 읽기는 "scroll → wait → 문구 확인" 반복(훈련자 5회). 계약상 문제는 아니다.
- 로그인 화면 navigate 마다 "페이지 텍스트가 매우 짧습니다(47자) … 봇 차단일 수 있습니다" 경고가 붙는다 — 정상 화면의 거짓 경보.
- hover 로 연 메뉴는 다음 호출까지 열린 채 유지되고 snapshot 에 하위 링크가 새 ref 로 나타난다. 더블클릭·오른쪽 클릭·press_key·resize·screenshot·wait(text)·cookies save 는 가이드 한 줄로 첫 시도에 섰다.
- 독립 AI 가 제약 없이 전부 IBL 로 풀었다(44~46회차 자유 조건은 Python). 표본 1회.
- 검사 수정 1회는 groupby 의 `{items}` 봉투 — 교재에는 "Record 를 반환하는 도구에만 `.items`" 로만 있고 groupby 가 그 경우라는 것은 검사 메시지가 알려 줬다(힌트 정확).

## 5. 비용·낭비·한계

**상한·시간**: 20:11 시작 → 20:28 독립 AI 종료·서버 정리(약 17분/상한 60분). 보고서·원장·기억 별도. 훈련자 수정 1회.
**훈련자 비용**: 9.2~9.8초·22,451~24,328단계(모델 0). 작성자 토큰 미측정. **독립 AI**: ep4521 457.1초(도구 18 = execute_ibl 18, 입력 3,297,098/출력 44,308).

1. **필요했던 비용** — 탐침 12회(drag·네트워크 기록·쿠키 복원 순서는 가이드로 알 수 없었다), Playwright 직접 호출 대조(L47-1 의 귀책을 가르는 데 필요), 새로 불러 대조, 스크린샷 눈 확인.
2. **줄일 수 있었던 일** — (a) 독립 AI 의 drag 재시도 2회와 그에 따른 세션 재시작·재로그인 3회. (b) 훈련자 프로그램의 카드당 snapshot 3~5회(보드 55요소) — 조작 뒤 ref 가 바뀌어 매번 다시 읽는다. (c) 스크롤마다 고정 600ms 대기 5회(약 3초, 전체의 30%).
3. **원인과 근거** — (a) L47-1, (b) ref 세대 규칙(설계), (c) 작성자 선택(문구 wait 로 바꾸면 줄어든다).
4. **다음 개선과 보존할 품질** — §4 처방. 보존: 화면 상태와 저장 상태를 따로 남기기, 기록이 수집 안 됐으면 그렇게 적기, 서버가 거절한 카드를 재시도 뒤 사람에게 넘기기.

**한계·미검증**: 표본 각 1회. drag 함정은 HTML5 끌어다 놓기 + 화면 밖 대상 조합에서만 확인했다(포인터 이벤트 방식 보드는 미확인). Chrome MCP 드라이버 미시험. `reuse`·두 호출 연결은 이번 축이 아니라 안 했다. 독립 AI 가 IBL 을 고른 원인 미분리.

## 6. 종료와 재현

종료 이유: 기본·변형 A·B 와 독립 AI 가 완료 조건을 채웠고 발견 3건의 최소 재현과 대조 실험을 확보했다. 서버 5개 종료, 쿠키 파일 삭제, 상태 사본 [evidence/server_state](evidence/server_state/).
재현: `prepare.py` → `site_server.py --port … --state … [--locked W-1017]` → `run.py base|flaky|b --draft tidy_v1.ibl --task-id T` → `verify.py trainer base|flaky|b`. L47-1: 새 서버에서 [probe_drag_min_repro](evidence/probe_drag_min_repro.json) 의 code, 대조는 `control_playwright_drag.py <url>`. 독립 AI 는 `ai_chain.py free <request.txt>`. 계정 합성, 증거의 비밀번호는 `<password>`.
다음 회차 후보: L47-1·2·3 수리 뒤 같은 프로그램에서 놓는 자리를 칸 영역으로 되돌려 재생; 포인터 이벤트 방식 끌기·정렬 가능한 목록(순서 바꾸기); Chrome MCP 드라이버로 같은 과제; 독립 AI 의 IBL 선택이 반복되는지(같은 과제 2~3회).


## 7. 후속 수리 (2026-10-09)

훈련과 독립 AI가 모두 종료된 최초 증거를 보존한 채, 정본 main `de88aefb` 다음 작업으로
L47-1~3을 수리했다. 관용구 등록·해마 시딩·새 어휘 추가는 하지 않았다.

- **L47-1**: Playwright의 `locator.drag_to` 대신 두 대상의 보이는 부분에서 실제로 닿는
  좌표를 고른 뒤 마우스를 조작한다. 시작 신원·스크롤·대상 소실/잘못된 drop을 감시하고,
  동시에 보이지 않거나 가려진 대상은 조작 전에 거절한다. 실제 시작 관측과 source/target의
  snapshot 이름·역할·ref를 반환한다. 성공은 `verification:gesture_only`이며 저장 완료를 뜻하지 않는다.
  클릭·더블클릭·우클릭·hover 등에도 snapshot 이름을 영수증에 남겼다.
  Chrome의 기존 drag는 target_ref를 사용하지 않고 0,0 좌표를 보내는 자리여서 실행을 제거하고
  명시 미지원 오류로 바꿨다. Chrome의 실제 ref→좌표 드래그 구현은 후속 범위다.
- **L47-2**: Playwright 세션 시작부터 HTTP 응답과 응답 없는 연결 실패를 수집한다.
  500건 한도·기본 반환 50건·보관 건수를 표시한다. 미수집은 `NETWORK_CAPTURE_INACTIVE` 오류이며
  이전 기록은 보존한다. 새 세션은 새 수집을 시작한다. 본문·헤더는 수집하지 않는다.
- **L47-3**: navigate로 열기→load→목적 화면 navigate→URL/화면 확인을 가이드와 응답에 명시했다.
  쿠키 적용 수와 인증 확인 여부를 구분하고, localStorage는 scheme/host/port가 같은 origin에만
  적용한다. 리다이렉트·부분 적용·리로드 실패를 숨기지 않고 실제 적용 수와 부분 복원 오류를 반환한다.
  과거의 로그인 보장 문구는 은퇴 등록부에 등록했다.

### 재검증

[검수 증거](evidence/repair_verification.json). 기본 pytest 수집 경로의
[브라우저 조작 검사](../../../../backend/test_browser_interact.py),
[세션 검사](../../../../backend/test_browser_session.py),
[저장 상태 검사](../../../../backend/test_browser_storage.py)에 회귀를 추가했다.

| 전체 프로그램 | 결과 |
|---|---|
| 원본 tidy_v1 기본 | 18/18 |
| 원본 tidy_v1 저장 거절(409) | 20/20 |
| 원본 tidy_v1 방침 변경 B | 18/18 |
| 새 변형: 제목 대신 큰 칸 영역으로 drag + 저장 거절(409) | 20/20 |

새 변형은 테스트에서 원본의 target 선택 한 곳만 region으로 바꾼다. 네 실행 모두 서버 이동 내역,
다른 카드 미변경, 메모·우선 표시, 화면과 저장 차이, 모바일 PNG, 쿠키 복원과 로그인 1회를 확인했다.
네트워크 409 수집도 별도로 대조했다. 최소 재현은 W-1004만 이동하고 W-1033은 그대로다.
포인터 이벤트 방식, 먼/가려진 대상, 페이지·중첩 영역 스크롤도 검사했다.

변경 9파일에서 선택기가 고른 12/623 시험 파일(2%)과 navigation 직접 소비자 1파일:
**143 passed, 43.88초**. 44~46회차 전체 프로그램도 이 묶음에서 통과했다.
개발 중 B 조건에서 조작 전 스크롤의 지연 이벤트를 실패로 오인해, 이벤트 존재가 아니라
기준 위치 대비 실제 변화로 판정하도록 수정했다. 별도 단일 재검증 중 빌드가 추적 파일을 바꿔
세션 관문이 실패한 실행은 통과 집계에서 제외했으며, 최종 143건은 세션 종료까지 정상이다.

원본 작성자의 고정 대기·snapshot 반복 선택과 짧은 로그인 화면 경고는 이번 공통 계약 수리에서
변경하지 않았다. 새 독립 AI 실행·전체 토큰 절감·전체 backend 회귀는 미측정/미실행이며,
기존 최초 훈련 성능과 수리 후 실행 시간을 합쳐 성능 향상으로 주장하지 않는다.

어휘 보관·분리 배포 검사 **23 passed, 58.64초**도 통과했다. 어휘 빌드 `--check`, 은퇴 계약 검사,
Android 번들 재생성을 완료했다. 용례 254건 중 변경 op인 drag/logs/cookies 호출을 검토했고
기존 인자·별칭은 유지하여 재검토 원장만 갱신했다.
재기동 제어자의 정상 재시작 후 실제 `/ibl/execute`에서 [합성 빈 페이지 탐침](evidence/repair_live.ibl)을
실행해 큰 영역으로 정확한 드래그, 이름 영수증, 네트워크 자동 수집, 세션 종료까지 확인했다.
실제 Chrome 창·사용자 브라우저 데이터는 조작하지 않았다.
