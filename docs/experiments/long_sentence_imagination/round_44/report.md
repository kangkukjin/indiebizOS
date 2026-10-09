# 44회차 — 컴퓨터 유즈: 가상 도서관 포털에서 대출 목록 읽기·내 목록 대조·반납 임박 도서 연장·화면 증거 남기기

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS` main `94e01abc`에서 훈련했다. 시스템 코드·설정·어휘 수리와 관용구 등록은 하지 않았다(발견만).
사용자 지정 주제 "컴퓨터 유즈" — `[limbs:browser]`(Playwright ref 조작)·`[limbs:screen]`(데스크톱 읽기)·`[sense:host]`(몸 상태)를 한 프로그램으로 잇는 첫 회차.

## 1. 판정과 산출물

| 실행 | 검사 | 실제 실행 | 요구 달성 | 시간 |
|---|---|---|---:|---:|
| 훈련자 기본 v0→v1 | v0 `TYPE` 3·`FORMAT_TYPE` 2(assert·`?:` 뒤에도 Null\|Text 미축소 — 작성 수정 1회) → v1 issues 0·경고 0(`incomplete`) | 정상, 5,280단계, 도구 26회(브라우저 22·screen 1·host 1·script 2), `source_complete:true` | **달성** — 결정론 검수 20/20(서버 상태·PNG·공지 원문·대조 포함) | HTTP 14.646초 |
| 훈련자 변형(불안정 포털, 같은 v1 무수정) | — | 정상, 5,252단계, 도구 22회, 2페이지 503→재시도 1회 성공(state.page2_hits 2) | **달성** — 검수 23/23: 12권 전부, L03 "연장 횟수 초과" 실패+사유, L01·L04 성공, L02 미신청 | HTTP 9.676초 |
| 독립 AI 기본 | 검사 거절 3(`$rejected` code_edits — f-string 안 `join`/`enumerate` 등) | 정상 ep4502, 도구 22(execute_ibl 18·Bash 4), 실패 0, 압축 0. IBL 로 읽기·로그인·snapshot 까지 → **공유 세션 충돌(L44-5) 뒤 자기 Playwright 스크립트**로 전체 재수행(확인창 `accept`), 데스크톱은 `screencapture`/osascript | **달성** — 정규화 검수 20/20([verify_agent](harness/verify_agent.py)), 서버 extended L01·L03·L04, L02 시도 0, 공지 원문·새 반납일 재독·충돌 사고를 report 에 명시 | 턴 286.9초 |
| 독립 AI 변형 | 거절 0(직전 스크립트에 재시도·거절 판독 추가) | 정상 ep4503, 도구 14(12·2), 압축 0. 2페이지 503→재시도(state.page2_hits 3), 오류 화면 PNG 도 저장 | **달성** — 정규화 검수 23/23: L03 거절+포털 문구 원문, 화면의 '연장 횟수 0/2' 와 사유 불일치까지 보고 | 턴 218.5초 |

- [사전 과제](task.md) · [최초 초안 main_v0](drafts/main_v0.ibl) → [v1](drafts/main_v1.ibl)(null→Text 확정 보조 함수 `글` 추가, 흐름 동일)
- 훈련자 증거: [v0 검사](../../../../outputs/long_sentence_imagination/2026-10-09_44회차/runs/trainer_base_main_v0_check.json)(로컬) · [기본 검수](evidence/trainer_base_qa.json) · [변형 검수](evidence/trainer_flaky_qa.json) · 실행 기록은 로컬 `outputs/long_sentence_imagination/2026-10-09_44회차/runs/`(응답 1.68MB — §4 L44-3)
- 탐침(작성 전 소실행·계약 조회): [describe 6+2](evidence/describe_actions.json) · [로그인 화면 snapshot](evidence/probe_browser_login.json) · [로그인→목록→상세](evidence/probe_browser_login_flow.json) · [확인창 클릭](evidence/probe_click_confirm.json) · [evaluate 로 승인](evidence/probe_confirm_override.json) · [iframe name 거절](evidence/probe_iframe_503.json) · [iframe index/url](evidence/probe_iframe_variants.json) · [503 navigate](evidence/probe_503_nav.json) · [데스크톱 캡처 모양](evidence/probe_screen_shape.json) · [navigate 시간](evidence/probe_navigate_timing_1.json)
- 산출물(훈련자, 로컬 `trainer/out/`): result.json · report.md · shots/6 PNG(연장 전·후 ×3) · desktop.png(사용자 실제 화면 — git 제외). report.md 와 result.json 은 [artifacts/trainer](artifacts/trainer/)에 사본. 상세 화면 PNG 는 눈으로 확인(L01 after: "연장이 완료되었습니다. 새 반납일: 2026.10.23", 반납일 칸 갱신, 버튼 사라짐).
- 외부 효과: 로컬 합성 포털에만 쓰기(연장 3건, 서버 `state.json` 으로 대조). 외부 사이트 0·발송 0·데스크톱 조작 0(캡처만).

## 2. 과제·환경·작성

**과제**: 사람이 실제로 부탁할 "포털에 들어가 내 상태를 읽고 → 조건에 맞는 것만 조작하고 → 화면으로 확인해 증거를 남겨라". 합성 포털은 stdlib HTTP 서버([site_server.py](harness/site_server.py)): 로그인(쿠키 세션)·대출 현황 3페이지(5권/쪽, 날짜 표기 `2026.10.09`)·상세 페이지의 연장 폼(`onsubmit=confirm()`)·예약 대기 도서는 버튼 비활성·공지는 iframe·`--flaky` 면 2페이지 첫 요청 503 + L03 연장 "연장 횟수 초과". 서버 상태 파일이 oracle 의 일부(어느 연장이 실제로 들어왔는가).
자료([prepare.py](harness/prepare.py)): 포털 12권, 내 목록 CSV 12행(L08 없음·L99 추가·L05/L11 반납일 다름, ISO 표기), 계정 JSON. 정답 `_oracle/`·서버 자료 `_site/` 는 입력 폴더 밖.

**환경**: `/ibl/execute` `project_id:"수동모드"` `origin:"training"`, 예산 100만 단계. 프로그램 안 AI 호출 0(결정론 과제). 브라우저 `driver:"playwright"`(헤드리스). 데스크톱은 읽기 op 만(click·type·key 금지 — 사용자 부재 중 실제 화면 격리).

**분해(v1)**: 보조 5(`줄찾기`·`참조`(snapshot 에서 role+name 으로 ref)·`날짜`(점→대시)·`글`(null→Text)·`열기`(navigate, 비 200 이면 wait 1.5초 뒤 1회 재시도)·`표행`(content 텍스트의 탭 5칸 행 파싱)) → 계정·CSV 읽기 → 로그인(입력칸 ref 는 snapshot 에서 찾음, `submit:true`) → '오늘'·총 페이지를 화면에서 → 2~N 페이지 `repeat` 로 누적 → `difference`·`join` 대조 → 3일 이내 `each`(불가는 사유만; 가능은 before PNG → `evaluate` 로 `window.confirm` 승인 패치 → 버튼 ref 클릭 → 결과 문구·새 반납일 재독 → after PNG; try/catch 로 항목별 실패 보존) → 공지 iframe(list→switch by url→content→reset) → `sense:host` 맨 앞 앱 + `limbs:screen` 캡처 base64 → `python_libraries` 로 PNG 저장 → result.json·report.md → 요약 반환.

**작성 조건**: 훈련 가이드·조합 교재 2권·문법 전문·browser_action.md·desktop.md·python_libraries.md·script.md·`describe` 8개·소실행 탐침 10회(위 링크). 작성 중 내부 코드 열람 0. 탐침은 작성에 필수였다 — 교재만으로는 (a) 확인창이 조용히 닫힌다는 것, (b) iframe `name` 이 거절된다는 것, (c) 데스크톱 캡처가 파일이 아니라 base64 라는 것을 알 수 없었다(§4). 원인 진단의 코드 열람은 실행·탐침 뒤(§4 각 항목에 명시).
수정 주기: v0 검사 거절 1회(null 축소 — 40회차와 같은 부류, 위치·힌트 정확) → v1 첫 실행 전건. 변형은 무수정. 작성 시간: 서버·자료 약 9분, 탐침 약 6분, 초안 약 5분, 수정 1분.
첫 소실행에서 `#!ibl edition=2` 헤더 없이 보낸 HTTP 요청은 `return {…}` 를 파싱 못 했다(교재가 말하는 "직접 HTTP 의 호환 기본값" = 판본 1 — 작성 마찰로만 기록, 갭 아님).

## 3. 검수와 독립 AI 비교

결정론 [verify.py](harness/verify.py): result.json + report.md + PNG 유효성 + **서버 state.json**(실제 연장 id·시도 수·L02 시도 0·2페이지 재시도 수) + 공지 원문 일치 + 새 반납일 재독 값. 훈련자 기본 20/20, 변형 23/23. 독립 AI 산출물은 키 이름이 달라(`renewals`·`comparison`·`completeness`…) [verify_agent.py](harness/verify_agent.py) 가 훈련자 모양으로 정규화한 뒤 같은 검수를 돌렸다(기본 20/20·변형 23/23 — 정규화 전 실패는 전부 키 이름). 결과 PNG·데스크톱 PNG 는 눈으로 확인했다.

### 독립 AI (ep4502 기본 · ep4503 변형)

| 볼 것 | 관측 |
|---|---|
| 풀이 방식 | 기본: IBL 6프로그램(계정·CSV 읽기, navigate+snapshot, `[def:다음ref]` 로 '다음' 링크 ref, 목록 3페이지, mkdir)까지 IBL 로 진행하다 **공유 세션의 URL 이 남의 포털로 바뀐 것을 발견**(L44-5) → Bash 로 playwright 확인 → `out/scripts/portal_run.py`(155줄, sync_playwright, `page.on("dialog", accept)`, 클릭 직전 포트·id 검증, 반납일 재독으로 성공 판정) 를 `self:script path` 로 실행 → IBL 로 result/report 작성·재독. 데스크톱은 `screencapture -x` + osascript(System Events) Bash. 셸 Python 풀이이므로 IBL 긴 프로그램 성공으로 세지 않는다. 변형: 같은 스크립트에 페이지 재시도(상한 3)·거절 문구 판독 추가, 오류 화면 PNG 저장 |
| 분할·재사용 | 변형에서 자기 스크립트·분석 JSON 재사용(요청문이 허용). IBL `reuse` 는 쓰지 않음(쓸 읽기 영수증이 스크립트 안에 있어 해당 없음) |
| 방법 발견 | `describe:["limbs:browser"]` 1회(tab list 와 함께), 가이드 검색 흔적 없음. 확인창·세션 충돌의 해법을 어휘 밖(Python)에서 찾음 — L44-1·L44-5 가 어휘로는 풀리지 않는다는 독립 증거 |
| 완료 판정 | 저장 후 재독, PNG 를 `PIL` 로 열어 통계 확인, 클릭 직전 URL·id 검증, "성공은 메시지가 아니라 반납일 재독으로 판정". 평가 경로: 응답에 미승인 표식 없음(43회차 L43-3 의 UNKNOWN 재발 없음 — 변형 요청문이 자체 완결이라 기준 상속 문제를 피했을 수 있음, 표본 1) |
| 축적 | 회상 사용 없음(`recall.used` 0). 훈련자 프로그램·탐침은 보지 않음(독립 유지) |
| 비용 | 기본 286.9초·입력 3,929,261/출력 28,674(cache_read 3,606,264·cache_create 315,559), 변형 218.5초·입력 2,183,142/출력 24,055. 훈련자 실행 14.6/9.7초(모델 0, 작성자 토큰 미측정) |

훈련자 갭이 독립 AI 에서도 밟혔는가: L44-1(확인창) — 밟힘(IBL 에서 못 풀어 Python `accept`). L44-3(데스크톱 파일 싱크) — 밟힘(`screencapture` 셸로 우회). L44-5(공유 세션) — 밟힘(피해자). L44-2(iframe 인자) — AI 는 Python 에서 프레임을 직접 다뤄 해당 없음. L44-4(navigate 대기) — AI 스크립트는 자체 Playwright 라 해당 없음.

## 4. 발견과 공통 개선 방향

### L44-1 — 확인창(confirm)이 조용히 닫히고 click 은 성공이라고 말한다
구현 결함·정직 보고. Playwright 드라이버가 모든 dialog 를 `dismiss()` 하고(`browser_session._on_dialog`, 진단 열람) `click` 은 `success:true` 를 돌려준다. confirm() 이 낀 폼 제출(연장 신청)은 **취소되는데 실패 신호가 없다** — `dialog_info` 는 사후 기록만 하고, 승인/거절을 정하는 op·인자가 없다.
최소 재현 [probe_click_confirm](evidence/probe_click_confirm.json): 클릭 success, dialog 기록(type confirm), URL 불변, 서버 attempts 0. 우회 [probe_confirm_override](evidence/probe_confirm_override.json): `evaluate` 로 `window.confirm = () => true` 패치 뒤 클릭 → `?done=1`·서버 extended. 가이드(browser_action.md)는 dialog 처리 방법을 적지 않는다. 독립 AI 는 어휘로 못 풀고 Python `d.accept()` 로 갔다.
처방: `[limbs:browser]{op:"dialog", mode:accept|dismiss, text}` 또는 click 의 `dialog:"accept"` 인자 + dialog 가 떴다 닫힌 클릭의 결과에 `dialog_dismissed:true` 신고. 가이드에 확인창 절.

### L44-2 — iframe 전환의 가이드·계약·구현이 셋 다 다르다
계약 불일치. 가이드와 구현은 `name`(정확 일치·1순위)·`id`·`index`·`url` 을 받지만 어휘의 닫힌 계약에 `name` 이 없어 `UNKNOWN_ARGUMENT`([probe_iframe_503](evidence/probe_iframe_503.json)). `index` 는 `list` 가 메인 프레임을 뺀 채 `page.frames` 위치(1부터)를 보고하는데 `switch` 는 `frames[index]` 라 **가이드의 "index:0 = 첫 iframe" 이 메인 프레임으로 전환되고 success:true**([probe_iframe_variants](evidence/probe_iframe_variants.json): switched_to url `/notice`, 본문은 메인). `url` 부분 일치는 동작. 훈련자는 `list` 의 url 로 우회.
처방: 계약에 `name` 추가(또는 `id` 로 통일하고 가이드 수정), list 의 index 와 switch 의 index 를 같은 수로, 메인 프레임으로의 전환은 `reset` 으로만.

### L44-3 — 데스크톱 캡처는 파일이 못 되고, 1MB base64 가 실행 봉투에 실린다
통화·비용. `[limbs:screen]{op:"screenshot"}` 은 `path` 없이 `{content, images:[{base64,media_type}], details}` 만 돌려준다(`images` 는 관측 반환 목록에도 없음 — [probe_screen_shape](evidence/probe_screen_shape.json)). "캡처를 파일로 남겨 달라" 는 요구를 IBL 로 채우려면 base64(1,019,980자)를 값으로 받아 `python_libraries` 2호출(b64decode → export bytes)로 저장해야 한다(훈련자 v1 §7, 1.0초). 브라우저 `screenshot` 은 `path` 로 바로 파일이다.
더 큰 비용: 프로그램 값에 base64 를 넣지 않았는데도 실행 봉투 `recordings` 에 원문이 실려 HTTP 응답 1,382,808자 중 1,037,003자가 캡처 base64 다([trainer_base_main_v1](evidence/trainer_base_main_v1.json) 은 recordings 를 뺀 사본). 호출자가 매 실행 1MB 를 받고 버린다. 독립 AI 는 `screencapture -x` 셸로 우회.
처방: screen screenshot 에 `path`(브라우저와 같은 계약) + 이미지 봉투를 recordings 에서 참조(`image_ref`/파일 경로)로 대체.

### L44-4 — navigate 는 정적 페이지에서도 호출당 0.5초를 기다린다
비용(드라이버 기본값). `navigate` 가 `domcontentloaded` 뒤 `_wait_for_dynamic_content`(networkidle 최대 3초 → 300ms 간격 본문 길이 2회 안정화)를 **매번** 돈다. 원시 GET 0.9ms 인 로컬 정적 페이지에서 호출당 520~550ms(5회 연속 측정 [probe_navigate_timing_1](evidence/probe_navigate_timing_1.json)·[2](evidence/probe_navigate_timing_2.json)), snapshot·content 는 40ms. 훈련자 기본 실행의 이동 10회 ≈ 5초(14.6초의 1/3), 변형 9.7초 중 ~4초. 끄는 인자가 없다(`wait_for` 는 goto 의 wait_until 만). 또 첫 호출은 브라우저 기동 ~7초(기본 실행 line 18: 7회 10,771ms vs 변형 3,673ms — 세션이 180초 유휴로 닫힌 뒤 재기동)가 계약·가이드에 없다.
처방: 응답이 정적(HTML 길이 안정·네트워크 0)이면 즉시 반환하거나 `wait:"load"|"idle"|"stable"` 선택 인자, 기동 비용을 결과에 신고(`session_started:true`).

### L44-5 — 브라우저 세션이 백엔드에 하나뿐이라 동시 실행이 서로의 페이지를 바꾼다
격리 공백. `[limbs:browser]` 의 Playwright 세션은 `BrowserSession.get_instance()` 단일 인스턴스(탭 t1)다. 훈련자의 navigate 시간 탐침(13:43:58·13:44:01, 포트 8939)이 독립 AI ep4502(13:42:41~13:47:28, 포트 8932)와 겹치자 **AI 의 페이지가 남의 포털로 바뀌었다**. AI 는 navigate 직후 URL 을 재확인해 알아채고 공유 세션에서의 클릭을 중단, 자체 Playwright 프로세스로 재수행했다([agent report §6](artifacts/agent/report.md)). 충돌을 알리는 신호는 없고 URL 재확인만이 방어였다 — 확인 없이 클릭했다면 **남의 포털에 연장이 들어갔다**(쓰기 오배송).
원인 제공은 훈련자의 동시 탐침(운영 실수, 보고서에 그대로 둔다). 그러나 같은 몸에서 정기 작업·위임 에이전트·사용자 요청이 동시에 브라우저를 쓰는 일은 정상 운영이며 격리 공백은 실제다.
처방: 실행(run)·주체별 브라우저 컨텍스트/탭 격리(최소한 실행마다 새 탭 + 다른 실행의 탭 접근 거절), 또는 세션 점유 잠금과 `BROWSER_BUSY` 거절. 결과 봉투에 `tab_id`·`session_owner` 신고.

### 재발·작성 마찰(갭 아님)
- 검사가 `assert $x != null`·`?:` 뒤에도 `Null|Text` 를 좁히지 않아 v0 거절 5건(40회차 변형 A 와 같은 부류). 위치·힌트 정확, 보조 함수 `글` 로 1회 수정. 타입 좁힘(narrowing)은 열린 개선 후보.
- `$i` 예약 바인딩(L41-4 재발, 탐침 작성 중 1회).
- HTTP 직접 호출에 `#!ibl edition=2` 헤더가 없으면 `return {…}` 파싱 실패(판본 1 기본) — 교재가 말하는 대로이나 탐침 첫 호출에서 밟음.
- `sense:host` 의 `frontmost_app` 은 프로세스 이름 "Electron"(앱 표시 이름 아님) — 두 실행자 모두 그대로 보고하고 한계를 적음.

## 5. 비용·낭비·한계

**상한·시간**: 13:30:42 시작 → 13:53:37 독립 AI 변형 종료·서버 정리(약 23분/상한 60분, AI 대기 포함). 보고서·원장·기억 작성은 별도(약 15분). 훈련자 수정 1회·변형 수정 0회.
**훈련자 비용**: 기본 14.6초·5,280단계·도구 26회(모델 0), 변형 9.7초·5,252단계·22회. 작성자(이 세션) 토큰 미측정. **독립 AI**: 기본 286.9초(입력 3.93M/출력 28.7K, cache_read 3.61M), 변형 218.5초(입력 2.18M/출력 24.1K). 포함 범위 = 에피소드의 `billable_usage` 합(역할별 분해는 [ai_base_metrics](evidence/ai_base_metrics.json)·[ai_flaky_metrics](evidence/ai_flaky_metrics.json)).

1. **필요했던 비용** — 작성 전 소실행 탐침 10회(교재·계약만으로는 확인창·iframe·캡처 모양을 알 수 없었다 — 정확성에 직접 기여), 연장 전·후 캡처 6장과 반납일 재독(증거·검수), 서버 상태 대조(진짜 외부 효과 확인). 독립 AI 의 클릭 직전 URL·id 검증(L44-5 에서 오배송을 막은 바로 그 비용).
2. **줄일 수 있었던 일** — (a) navigate 고정 대기 ≈ 5초/실행(L44-4). (b) 데스크톱 캡처의 base64 1MB 왕복 + script 2호출 ≈ 1초, 응답 1MB(L44-3). (c) 브라우저 재기동 7초(기본 실행; 180초 유휴 종료 뒤) — 연속 작업에는 세션 유지가 낫다. (d) 독립 AI 는 공유 세션 충돌로 IBL 진행분을 버리고 Python 으로 재수행(L44-5), 그리고 확인창·캡처 어휘 공백 때문에 어차피 Python 이 필요했다(L44-1·3) — IBL 긴 프로그램 한 번(14.6초)이 할 일을 287초에 했다. 재사용으로 피한 비용: 변형은 훈련자 무수정 9.7초, AI 는 자기 스크립트 재사용으로 219초.
3. **원인과 근거** — 전부 드라이버 기본값·통화 설계·단일 세션(작성자 선택 아님). 확인된 낭비: (a)(b)(c)(d). 추가 확인 후보: 기동 7초가 Chromium 콜드 스타트인지 세션 정리 지연인지.
4. **다음 개선과 보존할 품질** — §4 처방. 보존: 전·후 캡처·반납일 재독·서버 대조·정직한 실패 문구·클릭 직전 대상 검증은 줄이지 않는다.

**한계·미검증**: 합성 포털 1종(폼·confirm·iframe·503 만). 실제 사이트의 봇 차단·로그인 2단계·동적 렌더는 안 봤다. `limbs:screen` 조작 op(click·type·key)는 격리 조건으로 **미실행**(사용자 부재). `driver:"chrome"`·Chrome MCP 경로 미실행. 표본 1회.

## 6. 종료와 재현

종료 이유: 기본·변형·독립 AI 2실행이 완료 조건을 채웠고 발견 5건의 최소 재현이 확보됐다. 서버 6개(8931~8934·8938·8939)는 종료, 서버 최종 상태는 [evidence/server_state](evidence/server_state/)에 사본.
재현: `harness/prepare.py` → `site_server.py --port 8931 --data _site/trainer/loans.json --state …`(변형은 `--flaky`) → `run.py base|flaky --draft main_v1.ibl` → `verify.py`. 독립 AI 는 `ai_chain.py base runs/ai_request_base.txt`(요청문은 task.md 의 자연어 + 경로). 개인정보: 데스크톱 캡처(사용자 실제 화면)는 로컬 outputs 에만, 계정은 합성 값.
다음 회차 후보: 같은 과제를 `driver:"chrome"`(실제 Chrome)으로; `limbs:screen` 조작(사용자 입회)으로 네이티브 앱 한 바퀴; 동시 실행 2개의 브라우저 격리 시험(L44-5 수리 뒤); 로그인 세션 `cookies save/load` 로 재방문 비용.
