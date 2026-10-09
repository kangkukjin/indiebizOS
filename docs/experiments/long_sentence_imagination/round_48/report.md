# 48회차 — 브라우저 액트 2: 상점 관리 콘솔 주간 진열 개편(자동완성 검색·새 탭 편집·가격 슬라이더·글상자·포인터 방식 순서 바꾸기·비동기 내보내기·파일 내려받기·뒤로 가기·네트워크 기록)

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS` main `ce28e577`(47회차 수리 포함)에서 훈련했다. 시스템 코드·설정·어휘 수리와 관용구 등록은 하지 않았다(발견만).
축 ① 44~47회차가 쓰지 않은 브라우저 연결이 가이드만으로 서는가 ② 47회차 수리 3건(drag 신원·네트워크 자동 수집·이름 영수증)의 실전 재발 여부 ③ 독립 AI 가 같은 이음새(새 탭·슬라이더·순서 바꾸기·내려받기)에서 무엇을 고르는가.

## 1. 판정과 산출물

| 실행 | 검사 | 실제 실행 | 요구 달성 | 시간 |
|---|---|---|---:|---:|
| 훈련자 v0→v1 | v0 거절 3(`$i` 예약 이름 2 · 삼항 안 효과 호출 1) → v1 issues 0(incomplete) | 첫 실행 정상 10.36초·10,201단계. 상품 2건 각각 제안 클릭→새 탭 전환→슬라이더 키 조작→글상자→저장→탭 닫기, 끌기 3회, 내보내기 완료 대기, 페이지 안 fetch 로 파일 받아 저장·재독·대조, 뒤로 가기, 네트워크 기록 | **달성** 검수 16/16 — 서버 저장·순서·내려받기 기록 일치, display.csv 는 서버 파일과 바이트까지 같음(BOM·CRLF) | 10.36초 |
| 변형 A(P-05 첫 저장 500, 같은 프로그램) | — | 정상 10.0초 | **달성** 17/17 — 화면의 "저장 실패(500)" 를 읽고 재시도, 시도 2회·네트워크 기록 `POST /api/save → 500` 1건 보고, 판정 완료 | 10.0초 |
| 변형 B(방침만 변경: 편집 3·맨 위 4, 같은 프로그램) | — | 정상 13.14초·14,368단계 | **달성** 16/16 — 끌기 4회, 진열에 없는 상품(도자 머그 청)은 "파일로 확인 못 함" 으로 구별 | 13.14초 |
| 독립 AI(변형 A 서버, 제약 없음) | IBL 거절 3회(`$i` 예약 이름·공백 든 칸 이름 `.진열 문구`·람다 자리 each) — `$rejected`+`code_edits` 로 조각 수정 | 정상 ep4524, 도구 18(execute_ibl 14·Bash 4). **브라우저 조작은 자기 Playwright 스크립트 하나(237줄, 실행 5초)**, 입력 읽기·스크립트 저장·CSV 대조·보고서 재독은 IBL. `limbs:browser` 호출 0 | **달성** 정규화 검수 17/17 — 서버 저장·재시도 2회·순서·내려받기·바이트 일치·500 1건 보고 | 243.6초 |

- [사전 과제](task.md) · 프로그램 [v0](drafts/shop_v0.ibl)→[v1](drafts/shop_v1.ibl)(실행본, 세 조건 무수정)
- 훈련자 증거: 검사·실행 [evidence/trainer_*.json](evidence/) · 검수 [base](evidence/trainer_base_qa.json)·[flaky](evidence/trainer_flaky_qa.json)·[b](evidence/trainer_b_qa.json) · [서버 상태](evidence/server_state/) · 산출물 [artifacts/trainer](artifacts/trainer/)
- 탐침 7: [자동완성·새 탭 클릭](evidence/probe_search_popup.json) · [새 탭 목록·전환](evidence/probe_popup_list.json) · [새 탭 직후 경쟁·슬라이더 type·새 탭 네트워크](evidence/probe_popup_race.json) · [슬라이더 키·글상자](evidence/probe_slider_editable.json) · [저장·탭 닫기·포인터 끌기](evidence/probe_save_close_drag.json) · [내보내기 대기·내려받기 클릭·네트워크](evidence/probe_export_click.json) · [페이지 안 fetch·저장·뒤로 가기](evidence/probe_fetch_back.json)
- 독립 AI: [요청문](evidence/ai_request.txt) · [검수](evidence/agent_free_qa.json) · [지표](evidence/ai_free_metrics.json)·[사건](evidence/ai_free_events.json) · [산출물·스크립트](artifacts/agent/) · [서버 상태](evidence/server_state/agent_flaky.json)
- 외부 효과: 로컬 합성 서버뿐. 쿠키 파일 생성 0. 데스크톱 조작 0.

## 2. 과제·환경·작성

합성 콘솔([site_server.py](harness/site_server.py), stdlib): 상품 24종(이름 앞부분이 겹침). `/products` 검색창은 입력 250ms 뒤 `/api/suggest` 로 제안 목록(listbox)을 채우고, 고르면 그 상품만 보인다. '편집' 은 `target=_blank`. `/edit/ID` 는 `input[type=range]`(1만~6만·1천 단위)와 contenteditable 글상자, 저장은 fetch POST(`--fail-save-once ID` 는 첫 저장만 500). `/display` 는 **mousedown/mousemove/mouseup 으로 직접 만든 정렬 목록**(끄는 동안 DOM 이 실시간으로 바뀌고, 놓으면 순서를 POST). `/export` 는 작업을 만들어 400ms 마다 진행률을 묻고 1.6초 뒤 내려받기 링크(`Content-Disposition: attachment`, 주소는 매번 다른 토큰, **세션 쿠키 없으면 403**)를 띄운다. 서버 state.json 이 oracle.
**환경**: `/ibl/execute` `project_id:"수동모드"` `origin:"training"` `task_id` 명시, 예산 100만 단계, 모델 0, `driver:"playwright"`.
**분해**: 보조 4(`참조`·`슬라이더값`·`진열`·`상품편집`) + 최상위 6단(상품마다 편집 → 방침 순서대로 위로 끌기(끌 때마다 순서 재독, 자리마다 최대 3회) → 새로 불러 저장 순서 → 내보내기·파일 받기·CSV 대조 → 뒤로 가기 재확인 → 네트워크·탭·판정·파일).
**작성 조건**: browser_action.md·교재·describe 1·탐침 7. `limbs:browser` 패키지 코드 열람 0. 검사 수정 1회(작성자 오류 — `$i` 가 repeat 의 예약 이름이라는 것, 삼항 안 효과 호출; 둘 다 힌트 정확). 작성 시간: 서버·자료 약 3분, 탐침 약 3분, 초안·수정 약 3분.
탐침 없이는 쓸 수 없었던 자리 셋: 새 탭이 클릭 직후 목록에 없을 수 있다(L48-1) → "뜰 때까지 짧게 기다려 주소로 찾아 전환", 슬라이더는 `type` 이 거절된다(L48-3) → "눌러 초점 → Home → ArrowRight N번 → 값 재독", 내려받기 링크 클릭은 파일을 남기지 않는다(L48-2) → "페이지 안 fetch 로 받아 `self:write`".

## 3. 검수와 독립 AI 비교

결정론 [verify.py](harness/verify.py): result.json + report.md + display.csv(내용·바이트) + 서버 state(저장 시도·다른 상품 변경 0·편집 화면 열람·제안 질의·선택·진열 순서·내보내기·내려받기/거절).

### 독립 AI (ep4524, 변형 A 서버, 제약 없음)

| 볼 것 | 관측 |
|---|---|
| 풀이 방식 | 브라우저 조작 전체를 Python Playwright 스크립트 하나로(탐침 스크립트 2 → 본 스크립트 1, Bash 4회). 입력 읽기·스크립트 파일 쓰기·탐침 HTML 읽기·내려받은 CSV 와 방침의 대조·보고서 재독은 IBL(14회). 47회차는 같은 꼬리 문장에 전부 IBL 이었다 |
| 고른 이유(본인 보고) | "47회차에 끌어다 놓기가 실제로 안 움직였고 네트워크 기록이 0건으로 나온 문제를 피하려는 선택 … 이번 결과로는 IBL 쪽 두 문제가 고쳐졌는지 알 수 없어." — 두 문제는 `ce28e577` 로 수리됐고 이번 훈련자 실행에서 재발 0 이다. **실패의 기억은 남았고 수리 사실은 닿지 않았다** |
| 이음새 | 새 탭은 `expect_popup`, 내려받기는 `expect_download`+`save_as`(suggested_filename `display.csv`), 네트워크는 `context.on('response')` — 훈련자가 탐침으로 우회를 찾아야 했던 세 자리(L48-1·2·4)가 Python 쪽에서는 각각 한 줄이었다. 대신 브라우저 조작에 IBL 영수증이 없다(무엇을 눌렀는지는 스크립트의 자기 기록 evidence.json 뿐) |
| 분할·재사용 | 거절된 IBL 원문을 `$rejected`+`code_edits` 로 3회 조각 수정, `$checked:` 로 검사 통과본 실행 1회 |
| 완료 판정 | 저장마다 편집 화면을 다시 불러 서버 값 확인(실패 뒤 "값이 안 바뀜" 을 확인하고 재저장), 새로 부른 진열 순서·CSV·뒤로 간 화면 대조, 결과 파일 재독. 도구 성공이 아니라 재독으로 판정했다고 명시 |
| 놓친 것 | 없음(검수 17/17). 스크립트를 다듬는 동안 편집 화면을 8회 열었으나(훈련자 2회) 저장 시도는 3건으로 방침대로다 |
| 비용 | 243.6초, 입력 2,708,265/출력 22,703(cache_read 2,444,534·cache_create 257,092), 압축 0. 훈련자 10.0초·모델 0(작성자 토큰 미측정) |

훈련자 갭이 독립 AI 에서도 밟혔는가: L48-1~4 — **안 밟음**(그 경로를 쓰지 않았다). 대신 IBL 계산 쪽에서 훈련자와 같은 `$i` 예약 이름 거절을 밟았다.
이음새 지표로 보면: 사적 파일 읽기·쓰기·대조는 IBL 영수증으로 남았고, 브라우저 세션에서 내 폴더로 넘어오는 내려받기는 IBL 을 거치지 않았다 — Python 을 쓴 것 자체는 결함이 아니고, 그 선택의 근거가 낡은 기억이었다는 점과 내려받기 이음새가 IBL 에 없다는 점(L48-2)이 관측이다.

## 4. 발견과 공통 개선 방향

### 47회차 수리의 실전 확인
- **drag**: 포인터 이벤트 방식 목록(HTML5 끌기 아님, 끄는 동안 대상이 자리를 비킴)에서 7회 전부 의도한 항목이 의도한 자리에 놓였다. 영수증 `observation:{started:true, html5:false, actual_source:"… 진열 항목", wrong_source:false}`·`verification:"gesture_only"` 를 프로그램이 그대로 기록에 실었다. 재발 0.
- **네트워크 자동 수집**: 켜는 절차 없이 `capturing:true`, 변형 A 의 500 을 `status:500·method:POST` 로 읽어 보고의 근거로 썼다. 재발 0(단 빠지는 요청 부류가 있다 — L48-4).
- **이름 영수증**: `clicked:"황동 촛대 편집 (e18)"`·`element:"상품 검색 (e6)"`. 재발 0.
- 쿠키 복원은 이번 과제에 없었다.

### L48-1 — 새 탭을 여는 클릭이 그 사실을 말하지 않고, 활성 탭이 조용히 바뀐다
계약·정직 보고 공백. `target=_blank` 링크 클릭의 영수증은 `success:true`·`url` 은 원래 화면·`tab_id` 는 원래 탭이고 새 탭에 대한 말이 없다. 그런데 세션의 활성 탭은 새 탭으로 넘어간다. 바로 다음 호출의 결과가 시점에 따라 갈린다 — [첫 탐침](evidence/probe_search_popup.json)에서는 직후 `tab list` 가 **1개**(새 탭 없음), [둘째](evidence/probe_popup_race.json)에서는 직후 `snapshot` 이 `url` 은 원래 화면인데 `tab_id` 는 새 탭(t2)으로 **섞여** 나왔고 400ms 뒤에야 새 탭 주소가 됐다. 가이드는 "자동으로 감지되어 세션에 등록됨, tab list 로 확인" 뿐이라 활성 전환과 시차를 알 수 없다. 클릭 직후 snapshot 으로 ref 를 잡는 평범한 프로그램은 어느 탭의 화면을 읽었는지 모른 채 다음 조작을 한다.
처방: 클릭이 새 탭을 열었으면 그 영수증에 `opened_tabs:[{tab_id,url}]` 와 `active_tab` 을 싣고(짧은 유예 안에 감지), 활성 탭을 바꿨으면 바꿨다고 말한다. snapshot 의 `url`·`tab_id` 는 같은 탭에서 읽는다. 가이드 다중 탭 절에 "새 탭은 클릭 뒤 조금 늦게 나타나고 활성 탭이 된다 — 주소로 확인하고 전환" 한 줄.

### L48-2 — 파일 내려받기: 클릭은 성공인데 파일도 흔적도 없다
어휘·계약 공백(이음새). 내려받기 링크를 누르면 서버는 파일을 내줬다고 기록하지만([탐침](evidence/probe_export_click.json): downloads 1) 영수증은 보통 클릭과 같고(`success:true`, 주소 그대로), 받은 파일의 경로·이름이 어디에도 없으며 `~/Downloads`·작업 폴더에도 남지 않는다. 네트워크 기록에도 그 응답이 없다. 계약의 op 26개 중 내려받기를 가리키는 것이 없다. "화면에서 내보낸 파일을 내 폴더에 받아 대조" 는 브라우저 세션(쿠키)과 내 파일 사이의 이음새라 셸 요청으로 대신할 수 없다(쿠키 없는 요청은 403).
쓸 수 있었던 우회: `evaluate` 가 Promise 를 기다려 주므로 페이지 안에서 `fetch(링크).arrayBuffer()` → `TextDecoder(…,{ignoreBOM:true})` 로 글자를 받아 `self:write`([탐침](evidence/probe_fetch_back.json)). 글자 파일은 바이트까지 같게 받았다(BOM 은 `r.text()` 로 받으면 사라진다). 한계: 이진 파일(xlsx·pdf·zip)은 이 길로 저장할 방법이 없고, 가이드의 "evaluate 는 전용 도구가 안 될 때만" 과 긴장한다.
처방 후보(새 낱말 없이): 내려받기를 일으킨 click 의 영수증에 `downloads:[{suggested_filename, path, size}]` 를 싣고 `path` 인자(이미 screenshot·pdf 에 있음)로 저장 위치를 받는다. 저장하지 못했으면 성공이 아니라 "내려받기가 시작됐으나 저장되지 않음" 을 돌려준다. 가이드에 내려받기 절.

### L48-3 — 슬라이더를 맞추는 길이 안내에 없다
안내 공백. `type` 을 slider ref 에 쓰면 "입력 가능한 요소가 아닙니다 (role=slider). textbox, searchbox 등의 입력 필드 ref 를 사용하세요" 로 거절된다([탐침](evidence/probe_popup_race.json)) — 무엇을 하라는 말이 없다. 되는 길은 click 으로 초점 → `press_key Home` → `ArrowRight` 를 (목표−최소)/단위 번 → 값 재독이고, 최소·최대·단위는 snapshot 에 없어 `evaluate` 로 읽어야 한다(snapshot 은 `value` 만). 42,000원에 키 32회, 변형 B 49,000원에 39회(기본 실행 합계 50회 0.97초) — 호출당 약 20ms 라 시간은 작지만 단계 수와 영수증이 늘어난다.
처방: 거절 문구에 "슬라이더는 초점 뒤 Home/End·화살표 키, 값은 snapshot 의 value 로 확인" 을 넣고, snapshot 의 slider 항목에 min·max·step 을 싣는다. 가이드 폼 조작 절에 한 줄.

### L48-4 — 네트워크 기록이 새 탭의 첫 문서 요청과 내려받기 응답을 빠뜨린다
관측 공백. [새 탭 탐침](evidence/probe_popup_race.json): 새 탭이 `/edit/P-09` 를 불러 서버에 열람이 기록됐는데 기록에는 원래 탭의 문서 요청 1건뿐이다(새 탭에서 그 뒤에 일어난 저장 POST 는 잡힌다 — [탐침](evidence/probe_export_click.json)). 같은 탐침에서 `/files/….csv` 내려받기 응답도 없다. `scope:"session"`·`coverage:"recent_responses_and_failures"` 를 읽은 프로그램은 "실패 요청 0건" 을 전부 본 결과로 쓰기 쉽다. 이번 과제의 실패(저장 500)는 빠지는 부류가 아니라 판정에 영향이 없었다.
처방: 새 탭은 열리는 순간부터 수집하고, 내려받기 응답도 기록하거나, `coverage` 에 빠지는 부류를 밝힌다.

### 관측(갭 아님)
- 포인터 방식 목록에 "항목을 다른 항목 위에 놓으면 앞에 들어가는지 뒤에 들어가는지" 는 화면 구현에 달렸다. 프로그램은 끌 때마다 순서를 다시 읽어 판단했고(자리마다 최대 3회), 7회 모두 첫 시도에 맞았다.
- 늦게 뜨는 제안 목록은 `wait selector:"#sug li"` 한 줄로 섰고, 제안은 snapshot 에 `role:"option"` 으로 이름과 함께 나온다. contenteditable 글상자는 `role:"textbox"` 로 `type` 이 통했다. `navigate mode:"back"` 은 주소·상태를 그대로 돌려줬다. 진행률 화면은 `wait text:"내보내기 완료"` 로 기다렸다. `tab close` 는 `remaining_tabs`·`active_tab` 을 돌려준다.
- `self:write` 는 BOM·CRLF 를 그대로 쓰고, `self:read` 는 CSV 를 `data.items` 로 풀어 줘 대조가 식 몇 줄이었다(39회차 L39-1 의 CRLF 소실은 재발하지 않음).
- 검사 수정: `$i` 가 블록 밖에서도 예약 이름(힌트가 대안 이름까지 줌), 삼항 안 효과 호출(45·46회차와 같은 부류의 작성자 오류, 세 번째). 탐침에서 `$x = [try]{ return … }` 는 프로그램 전체를 반환했다 — try 본문의 return 은 값이 아니라 프로그램 종료다(작성자 오류).
- 독립 AI 가 브라우저 어휘를 피한 이유가 수리 전 기억이었다(45회차 "수리된 어휘가 에이전트 선택에 안 닿음" 의 재관측, 표본 1). 수리 사실을 실패 기억과 같은 자리에 남기는 길이 없다.
- 보조 함수 `참조` 의 선형 검색이 단계의 47%(4,770/10,201)를 썼다 — 요소 수십 개 화면에서는 무해.

## 5. 비용·낭비·한계

**상한·시간**: 00:26 시작 → 00:38 독립 AI 종료·서버 정리(약 12분/상한 60분). 보고서·원장·기억 별도. 훈련자 수정 1회.
**훈련자 비용**: 10.0~13.1초·10,201~14,368단계(모델 0). 작성자 토큰 미측정. **독립 AI**: ep4524 243.6초(도구 18 = execute_ibl 14·Bash 4, 입력 2,708,265/출력 22,703).

1. **필요했던 비용** — 탐침 7회(새 탭 시차·슬라이더·내려받기는 가이드로 알 수 없었다), 끌 때마다 순서 재독, 새로 불러 저장 순서 확인, 파일 저장 뒤 재독 대조.
2. **줄일 수 있었던 일** — (a) 슬라이더 키 상품당 10~39회(값을 한 번에 줄 길이 없다 — L48-3). (b) 새 탭 대기 반복(150ms·목록 조회, 상품당 1~2회 — L48-1 이 영수증으로 풀리면 0). (c) 저장 뒤 고정 400ms 대기(문구가 둘 중 하나라 text 대기를 못 씀). (d) 훈련자의 검사 거절 1회(예약 이름·삼항).
3. **원인과 근거** — (a) L48-3 (b) L48-1 (c) `wait text` 가 "둘 중 하나" 를 못 받음(작성자가 selector 로 바꾸면 줄어든다) (d) 작성자.
4. **다음 개선과 보존할 품질** — §4 처방. 보존: 끌기·저장마다 화면을 다시 읽어 확인, 받은 파일을 저장 뒤 다시 읽어 대조, 파일로 확인할 수 없는 항목을 따로 적기, 재시도 횟수와 실패 요청을 보고에 남기기.

**한계·미검증**: 표본 각 1회. 내려받기 우회는 글자 파일에서만 확인(이진 미확인). 새 탭 시차는 로컬 서버 2회 관측(1개로 보임 1·섞임 1)이며 빈도는 재지 않았다. 끌기는 위로 올리는 방향만 썼다(아래로 내리기·화면 밖 긴 목록 미확인). Chrome MCP 드라이버 미시험. `reuse`·두 호출 연결은 이번 축이 아니다.

## 6. 종료와 재현

종료 이유: 기본·변형 A·B 와 독립 AI 가 완료 조건을 채웠고 발견 4건의 탐침 증거를 확보했다. 독립 AI 작업 `task_sysai_1add9a66` 종료 확인, 서버 5개 종료, 상태 사본 [evidence/server_state](evidence/server_state/).
재현: `prepare.py` → `site_server.py --port … --state … [--fail-save-once P-05]` → `run.py base|flaky|b --draft shop_v1.ibl --task-id T` → `verify.py trainer base|flaky|b`. 탐침은 `probe.py <label> <task_id> <code파일>`(evidence 의 code 칸). 독립 AI 는 `ai_chain.py free <request.txt>`. 계정 없음(세션 쿠키만).
다음 회차 후보: L48-1·2 수리 뒤 같은 프로그램에서 대기 반복·fetch 우회를 걷어내고 재생; 이진 파일 내려받기·여러 파일; 아래로 내리는 끌기와 화면 밖 긴 정렬 목록; 업로드→처리→내려받기 왕복; Chrome MCP 드라이버.
