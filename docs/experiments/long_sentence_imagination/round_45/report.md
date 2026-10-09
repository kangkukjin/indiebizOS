# 45회차 — 컴퓨터 유즈 2: 체육센터 강좌 신청 두 사람 몫(연쇄 select·업로드·접수 코드 확인창·영수증 PDF 대조) + 데스크톱 손

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS` main `1f069e64`(44회차 수리 커밋 포함)에서 훈련했다. 시스템 코드·설정·어휘 수리와 관용구 등록은 하지 않았다(발견만).
목적: 44회차 발견 5건의 수리(dialog·wait·iframe·screenshot path·작업별 세션)가 **새 연결 위에서 실전으로 서는지** + 44회차에 없던 연결(비동기 연쇄 select·snapshot 상한·upload/check·prompt 확인창·pdf→self:read·동시 실행 격리·데스크톱 조작 루프).

## 1. 판정과 산출물

| 실행 | 검사 | 실제 실행 | 요구 달성 | 시간 |
|---|---|---|---:|---:|
| 훈련자 기본 v0→v2 | v0 `SYNTAX` 1(보간 안 따옴표 삼항) → v1 `PURE_EXPRESSION` 2(삼항 자리의 파이프·효과 호출) → v2 issues 0 | 정상, 12,528단계, 도구 약 40회(브라우저 ~30·screen 7·host 1·read 4·write 2), `source_complete:true` | **달성(브라우저)** — 검수 18/18(서버 접수 2·업로드 sha·코드·PDF 대조·합계·snapshot 상한·세션). **데스크톱 다리는 오동작**(§4 L45-2: 계산기가 뜨지 않았는데 입력·cmd+q 전송, 화면값 미판독 → 보고서에 "불일치" 로 정직 기록) | HTTP 10.63초 |
| 훈련자 변형 A(불안정 포털, v3=v2+desk 게이트) | — | 정상, 일시 오류 1회 재제출·C28 정원 마감 거절 | **달성** — 검수 21/21(재제출 기록·실패 사유 원문·PDF 1·합계 45,000) | 10.56초 |
| 훈련자 변형 B(동시 실행 2, v3, 신청자 1명씩) | — | 두 요청 동시 접수, session_owner 서로 다름, 교차 오염 0 | **달성** — 각 18/18, 벽시계 8.95초 vs 순차 합 17.59초 | 8.64 · 8.95초 |
| 독립 AI 기본 | IBL 검사 거절 1(문장 사이 `;`)·셸 관문 오탐 2 | 정상 ep4505, 도구 33(execute_ibl 16·Bash 17), 압축 0. **처음부터 자기 Python Playwright**(probe.py→apply_run.py, `limbs:browser` 호출 0), 데스크톱은 osascript·screencapture | **달성(브라우저)** — 정규화 검수 18/18([verify_agent](harness/verify_agent.py)), 서버 접수 2·업로드 sha·코드 일치. 계산기는 '맨 앞 앱이 바뀌어 입력 안 함' 으로 **미실행** 명시 | 턴 379.2초 |
| 독립 AI 변형 | IBL 결과 파일 프로그램 수정 5회(전체 재전송) | 정상 ep4506, 도구 20(15·5). 직전 스크립트 재사용, 일시 오류 뒤 중복 접수 3중 확인 뒤 재제출, C28 거절 원문 | **달성** — 정규화 검수 21/21, 계산기 미실행(같은 이유) | 턴 458.2초 |

- [사전 과제](task.md) · [최초 초안 v0](drafts/main_v0.ibl) → [v1](drafts/main_v1.ibl) → [v2](drafts/main_v2.ibl)(실행본) → [v3](drafts/main_v3.ibl)(v2 + `inputs.desk` 게이트 — 기본 실행의 데스크톱 오동작 뒤 변형·동시 실행 안전 조치, 브라우저 흐름 동일)
- 훈련자 증거: [v0 검사](evidence/trainer_base_main_v0_check.json) · [v1 검사](evidence/trainer_base_main_v1_check.json) · [기본 실행](evidence/trainer_base_main_v2.json) · [기본 검수](evidence/trainer_base_qa.json) · [변형 A 실행](evidence/trainer_flaky_main_v3.json) · [검수](evidence/trainer_flaky_qa.json) · 변형 B [강가상](evidence/trainer_base_main_v3_8945_강가상.json) · [이합성](evidence/trainer_base_main_v3_8945_이합성.json) · [서버 상태](evidence/server_state/)
- 탐침: [describe 4](evidence/describe_actions.json) · [신청 화면 snapshot·목록 상한](evidence/probe_apply_form.json) · [select values 거절](evidence/probe_select_values_rejected.json) · [select label 실행 거절](evidence/probe_select_label_runtime_rejected.json) · [전체 흐름 성공](evidence/probe_apply_flow.json) · [navigate wait:load](evidence/probe_navigate_wait_load.json) · [wait:stable](evidence/probe_navigate_wait_stable.json)
- 산출물(훈련자, 로컬 `trainer/out*`): result.json·report.md·receipts/이름.pdf. 사본 [artifacts/trainer](artifacts/trainer/). PDF 는 `self:read` 텍스트로 대조(이름·강좌·수강료·접수번호).
- 외부 효과: 로컬 합성 포털 쓰기(접수)만. **데스크톱 키 입력 7회가 기본 실행에서 실제 전송됨**(§4 L45-2 — 사용자 화면에 미친 영향은 미확인).

## 2. 과제·환경·작성

합성 포털([site_server.py](harness/site_server.py)): 로그인(쿠키) → 강좌 목록 40개(요소 413 — snapshot 100개 상한 시험) → 신청 폼(지역→센터→강좌 연쇄 select, `/api/*` 400·600ms 지연, 이름·생년월일·파일 input·약관 checkbox, 제출 시 `prompt()` 접수 코드) → `/receipt/{id}`. `--flaky`: 첫 제출 "일시 오류" 거절, 목록 조회 뒤 C28 정원 0. 서버 state.json(접수·업로드 sha256·코드·거절)이 oracle 의 일부.
자료([prepare.py](harness/prepare.py)): 신청자 2(강가상 C03 45,000 · 이합성 C28 72,000), 증명서 PNG 2(PIL), 코드 2, 계정 1. 동시 실행용 서버 8945 별도.

**환경**: `/ibl/execute` `project_id:"수동모드"` `origin:"training"`, 예산 100만 단계, 모델 호출 0, `driver:"playwright"`. 데스크톱은 계산기만, `frontmost_app=="loginwindow"` 또는 성공 0 이면 미실행(v3 부터는 `desk:true` 명시 필요).

**분해(v2)**: 보조 7(`줄찾기`·`글`·`참조`(snapshot role+name→ref)·`표값`(탭 키값)·`원`(45,000원→45000)·`목록행`(탭 7칸)·`제출`(신청 화면을 처음부터 채워 제출 — 재제출용 분리)) → 입력·`only` 필터 → 로그인(`wait:"load"`) → 목록 snapshot 상한 관측 + content 로 수강료 사전확인 → 신청자 each(제출 → "일시 오류" 면 1회 재제출 → 접수/거절 판독 → pdf → self:read → 6항목 대조) → 합계 → 계산기(try) → result.json·report.md.
**작성 조건**: 수리된 browser_action.md·desktop.md·교재 2권·문법 전문·describe 4·탐침 7. 내부 코드 열람 0(진단 포함 — 45회차는 코드를 열지 않았다). 작성 시간: 서버·자료 약 7분, 탐침 약 4분, 초안 약 5분, 수정 2회 약 2분.
**검사 수정 2회**(둘 다 위치·힌트 정확): ① f-string 보간 안에 `"…" : "…"` 삼항을 넣은 SYNTAX(41회차 L41 부류 재발 — 문구를 변수로 먼저), ② `$x = 조건 ? (파이프) : …`·`조건 ? [fn:제출]{…} : $r` 의 PURE_EXPRESSION(효과 호출은 if 문장으로). 둘 다 작성자 오류.
**탐침이 필수였던 것**: `select` 의 인자 이름(§4 L45-1) — 가이드대로 `values` 를 쓰면 검사 거절, 계약대로 `label` 을 쓰면 실행 거절.

## 3. 검수와 독립 AI 비교

결정론 [verify.py](harness/verify.py): result.json + report.md + PDF 텍스트(pypdf) + **서버 state.json**(접수 이름·강좌·수강료·업로드 sha256·코드·거절 목록) + 합계 + 사전확인 수강료 + snapshot 상한 관측 + 세션 필드 + 계산기 보고 유무. 훈련자 기본 18/18, 변형 A 21/21, 변형 B 각 18/18.

### 독립 AI (ep4505 기본 · ep4506 변형)

| 볼 것 | 관측 |
|---|---|
| 풀이 방식 | **IBL 로 브라우저를 한 번도 부르지 않았다.** 첫 도구 호출 뒤 Bash 로 `2026-10-09_44회차/*/out*/scripts` 를 뒤져 자기 44회차 Python 경로를 찾고, `probe.py`(페이지 HTML 저장) → `apply_run.py`(sync_playwright, option 등장 폴링, set_input_files, dialog accept, 제출 직전 포트·값 검증, page.pdf, 텍스트 추출 대조)를 썼다. IBL 은 입력 읽기·HTML 재독·결과 파일 쓰기(16회). 데스크톱은 Bash(ioreg 유휴·osascript frontmost·`open -a Calculator`·AX 버튼 열거) + `limbs:screen screenshot path` + `engines:image_read` 로 화면 확인. 셸 Python 풀이이므로 IBL 긴 프로그램 성공으로 세지 않는다 |
| 분할·재사용 | 변형에서 자기 스크립트·탐침 HTML 재사용(허용). 결과 파일 IBL 은 `$rejected`+`code_edits` 수정 경로를 썼다(기본 2회) — 변형에서는 "고칠 부분만 보내는 경로가 없어 전체 재전송" 이라고 보고(5회): 거절 봉투가 수정 경로를 매번 주지 않는 듯(미확인, R4 후보) |
| 방법 발견 | `describe` 0, 가이드 검색 0. 회상 1건 사용(hippocampus 2건+등록 스크립트 3개 — 브라우저 어휘 아님). **수리된 dialog·wait·세션 격리를 알 길이 없었고 찾지도 않았다** — 44회차에 Python 으로 성공한 기억이 선택을 결정 |
| 완료 판정 | 접수번호 칸으로 성공 판정, PDF 재독 7항목 대조, 제출 직전 포트·값 검증, 저장 후 재독·비밀값 부재 확인. 재제출 전 중복 접수 3중 확인(내역 페이지 없음·접수번호 없음·잔여 불변) — 훈련자 프로그램에 없던 신중함 |
| 축적 | 자기 44회차 산출물을 길로 삼음(독립성은 유지 — 훈련자 폴더 미접근). 어휘 수리의 효과가 에이전트 경로에 닿지 않음(§4 관측) |
| 비용 | 기본 379.2초·입력 4,988,697/출력 30,615(cache_read 4,701,560), 변형 458.2초·입력 5,686,809/출력 50,468. 훈련자 10.6/10.6/8.95초(모델 0). 데스크톱 "자리 확인" 왕복(Quartz 모듈 부재 4회 재시도·frontmost 샘플링 9회)이 두 실행 합 약 2분 |

훈련자 갭이 독립 AI 에서도 밟혔는가: L45-2 — 밟힘(snapshot app Electron 을 보고 판정에서 제외, osascript 로 대체; 입력은 보류). L45-1 — 해당 없음(Python select_option). 44회차 수리 5건 — AI 는 IBL 브라우저를 안 써 검증에 기여하지 않음.

## 4. 발견과 공통 개선 방향

### 44회차 수리의 실전 확인(재발 0)
`click … dialog:"accept", dialog_text:코드` 로 prompt 확인창이 승인되고 `dialogs[].handled:true`·`dialog_dismissed:false` 가 결과에 실렸다(L44-1). `navigate wait:"load"` 는 정적 로컬 페이지 5회 연속 47~48ms(첫 호출 360ms = `session_started:true`), 기본 `stable` 은 같은 페이지 608~1,308ms([probe_navigate_wait_load](evidence/probe_navigate_wait_load.json)·[stable](evidence/probe_navigate_wait_stable.json), L44-4). 실행마다 새 세션(`session_owner`·`tab_id` 가 모든 브라우저 결과에 동반), 동시 2실행이 서로 다른 소유자로 각자의 포털에 접수(L44-5). `limbs:screen screenshot path` 는 이번 과제엔 없었고 L44-2(iframe)도 해당 없음. snapshot 100개 상한은 `element_count 413 / shown_count 144 / truncated:true / omitted_count 269`(`display_budget`)로 정직하게 드러나 content 로 우회할 수 있었다 — 갭 아님.

### L45-1 — `select` 의 인자 이름이 가이드·계약·실행기에서 셋 다 다르다
계약 불일치. 가이드(browser_action.md §폼 조작)는 `values:["옵션텍스트"]`, 어휘 계약(`operations.select`)은 `value/label`, 실행기는 `values` 또는 `value` 만 받는다. 그래서 가이드대로 쓰면 검사 `UNKNOWN_ARGUMENT`([probe_select_values_rejected](evidence/probe_select_values_rejected.json)), 계약대로 `label` 을 쓰면 검사는 통과하고 **실행에서** `values(또는 value)가 필요합니다` 거절([probe_select_label_runtime_rejected](evidence/probe_select_label_runtime_rejected.json)). `value` 는 Playwright 가 value·label 둘 다에 맞춰 주어 센터 이름(`"가상 수원체육센터"`)으로도 동작했다(실행 v2). 44회차 L44-2 와 같은 부류(가이드↔닫힌 계약↔구현의 삼중 불일치)가 다른 op 에서 재발 — 닫힌 계약 census(F78-2)가 설명·가이드까지는 대조하지 않는다는 뜻.
처방: 계약에 `values`(목록) 추가 또는 가이드를 `value` 로, `label` 은 구현하거나 계약에서 빼기. select 와 같은 "옵션 고르기" 는 사용자가 아는 **표시 글자**로 고를 수 있어야 한다.

### L45-2 — 데스크톱 `snapshot` 이 맨 앞 앱이 아니라 IndieBiz(Electron) 창을 읽는다
구현 결함·안전. 맨 앞 앱이 ChatGPT(System Events 와 `sense:host` 모두 ChatGPT)인 순간에도 `[limbs:screen]{op:"snapshot"}` 은 `app:"Electron"`, elements 80개 = IndieBiz 런처 창의 버튼들(정보센터·설정·팀내 대화…)을 돌려준다([probe_screen_app_detection](evidence/probe_screen_app_detection.json)). 독립 AI 도 같은 시각 osascript 가 Calculator 라 할 때 snapshot 은 Electron 이라고 보고해 판정에서 제외했다.
결과: 훈련자 기본 실행의 계산기 다리는 Spotlight → 계산기 → `45000+72000=` → cmd+q 를 보냈지만, 보낸 뒤 읽은 snapshot 이 런처 창이라 화면값을 못 찾고 "불일치" 로 적었다. 키 입력이 실제로 어디에 들어갔는지는 **미확인**(정황: 실행 전후 Calculator 프로세스 없음 → 계산기가 열려 입력을 받고 cmd+q 로 닫혔을 가능성이 높지만 증거 없음). 가이드의 "snapshot 으로 읽고 → ref 로 클릭" 루프가 IndieBiz 밖 앱에서는 **눈이 다른 곳을 본다** — 좌표 클릭·ref 클릭 모두 런처 창을 누르게 된다.
또 데스크톱 어휘에는 "앱이 뜰 때까지 기다리기"·"맨 앞 앱이 X 인지 확인하고만 입력하기" 가 없다(`type` 은 현재 포커스로 간다). 훈련자가 snapshot 뒤 `app` 을 검사하지 않고 입력한 것은 작성 오류이며, v3 부터 `desk:true` 명시 없이는 이 다리를 끄도록 바꿨다.
처방: snapshot 이 `frontmost` 프로세스의 AX 트리를 읽고 `app` 에 그 이름을 싣기(또는 `app:` 인자), `type/key/click` 에 `expect_app` 가드(불일치면 거절), `wait`(앱 등장·idle) op. 사용자가 다른 앱을 쓰는 중이면 조작을 보류하는 정책은 독립 AI 의 판단이 맞다.

### 관측(갭 아님·재발)
- 독립 AI 는 수리된 어휘가 있어도 **처음부터 Python Playwright** 로 갔다(IBL 의 `limbs:browser` 호출 0). 44회차의 자기 성공 경로를 기억해 재사용한 것(§3 "발견·학습"). 어휘가 고쳐져도 그 사실이 에이전트의 선택에 닿지 않으면 수리 효과가 실사용에 안 나타난다 — R5 후보.
- 독립 AI 가 신고한 셸 안전 관문(`shell_shadow_gate`) 오탐 2건(`head -c 3000` 의 숫자를 파일명으로, grep 정규식 `[A-Za-z]*` 를 파일 패턴으로) — IBL 밖이라 갭 ID 없이 기록.
- 검사 수정 2회는 작성자 오류(보간 안 따옴표, 순수 식 자리의 효과 호출) — 위치·힌트 정확.
- PDF 텍스트 추출은 표 셀을 "접수번호R001" 처럼 붙여 돌려준다 — `contains` 대조는 되지만 키=값 파싱은 안 된다(관측).

## 5. 비용·낭비·한계

**상한·시간**: 15:15:56 시작 → 독립 AI 변형 종료까지(§6). 훈련자 몫은 자료·서버 7분, 탐침 4분, 초안 5분, 수정 2분, 실행 기본 10.6초·변형 A 10.6초·변형 B 8.95초(동시). 보고서·원장·기억 작성은 별도.
**훈련자 비용**: 기본 12,528단계·도구 약 40회(모델 0). 작성자(이 세션) 토큰 미측정. **독립 AI**: 기본 ep4505 379.2초(도구 33 = execute_ibl 16·Bash 17, 입력 4,988,697/출력 30,615, cache_read 4,701,560), 변형(§3).

1. **필요했던 비용** — 탐침 7회 중 `select` 인자 2회 거절은 L45-1 발견의 비용이자 실행 성공의 전제. 신청마다 PDF 저장·재독·6항목 대조, 서버 state 대조. 독립 AI 의 제출 직전 포트·값 검증과 "맨 앞 앱이 바뀌면 입력하지 않는다" 판단(45회차에서 가장 값진 비용).
2. **줄일 수 있었던 일** — (a) `navigate` 기본 `stable` 을 그대로 썼다면 11회 이동 ≈ 7~14초였을 것을 `wait:"load"` 로 ≈ 0.5초(44회차 L44-4 수리의 실측 효과). (b) 재제출(`제출` 함수 재호출)은 폼을 처음부터 다시 채운다 — 포털이 입력을 지우므로 불가피. (c) 데스크톱 다리: snapshot 이 엉뚱한 앱을 읽어 7회 입력이 **증거 없는 비용**이 됐다(L45-2). (d) 독립 AI 379초 vs 훈련자 10.6초 — 같은 결과를 36배 시간에; Python 재구현(probe.py·apply_run.py)과 Quartz 모듈 부재로 셸 4회 재시도, 계산기 앞 확인 왕복 9회.
3. **원인과 근거** — (a) 드라이버 기본값(수리됨, 선택은 작성자 몫), (c) 구현 결함, (d) 발견·학습(수리된 어휘 미사용). 확인된 낭비 (c)(d), 추가 확인 후보: PDF 추출의 셀 결합.
4. **다음 개선과 보존할 품질** — §4 처방. 보존: 제출 직전 대상 검증, PDF 재독 대조, 정직한 실패 문구, 포커스 불확실 시 입력 보류.

**한계·미검증**: 데스크톱 조작 루프는 L45-2 때문에 **성공 증거를 남기지 못했다**(미달로 기록). `driver:"chrome"` 미실행. 사용자가 실제로 자리에서 앱을 오가는 중이라 데스크톱 실험은 사용자에게 방해가 될 수 있었다 — 독립 AI 는 중단을 택했고, 훈련자 v2 는 그 판단 없이 입력했다. 표본 1회.

## 6. 종료와 재현

종료 이유: 기본·변형 A·변형 B·독립 AI 2실행이 브라우저 완료 조건을 채웠고, 데스크톱 다리는 L45-2 로 성공 증거를 남길 수 없어 미달로 닫았다(사용자가 자리에서 앱을 오가는 중이라 재시도도 방해가 된다). 15:15:56 시작 → 15:38:56 서버 7개 종료(약 23분/상한 60분, AI 대기 포함). 서버 최종 상태는 [evidence/server_state](evidence/server_state/).
재현: `harness/prepare.py` → `site_server.py --port 8941 --data _site/trainer/data.json --state …`(변형 `--flaky`) → `run.py base|flaky --draft main_v3.ibl [--desk] [--only 이름 --port-override 8945]` → `verify.py`. 독립 AI 는 `ai_chain.py base runs/ai_request_base.txt`. 계정·코드는 합성 값.
다음 회차 후보: L45-2 수리 뒤 데스크톱 루프 재시험(사용자 입회·`expect_app` 가드); 독립 AI 가 수리된 IBL 어휘를 **고르게** 하는 경로(회상에 browser 용례·가이드 노출) 실험; `driver:"chrome"`; 두 신청자를 `task_id` 묶음으로 같은 세션에서 처리하는 시험.
