# 46회차 — 컴퓨터 유즈 3: 숙소 두 곳 비교 뒤 예약 보류(두 탭·동의 모달·날짜 위젯·스테퍼·iframe 약관·세션 만료·작업 두 호출) + 미리보기로 확인서 읽기

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS` main `c09dd108`(45회차 수리 포함)에서 훈련했다. 시스템 코드·설정·어휘 수리와 관용구 등록은 하지 않았다(발견만).
축 ① L45-2 수리 뒤 데스크톱 눈(frontmost AX·expect_app·wait) ② 독립 AI 가 IBL 어휘를 **고르는가**(조건 A 자유 / B IBL 만) ③ 새 연결(두 탭·DOM 모달·달력·스테퍼·iframe 체크박스·세션 만료·같은 task_id 두 호출).

## 1. 판정과 산출물

| 실행 | 검사 | 실제 실행 | 요구 달성 | 시간 |
|---|---|---|---:|---:|
| 훈련자 1차(비교) v0→v2 | v0 SYNTAX 1(보간 안 따옴표 삼항) → v1 PURE_EXPRESSION 1(삼항 자리 파이프) → v2 issues 0 | 정상 2.78초·5,615단계, 탭 2(A 현재 탭·B 새 탭), 동의 모달·달력·select label·스테퍼·검색 전부 ref 로 | **달성** — 6객실 총액 oracle 일치, B3 마감 제외, 선택 B1 176,000 | 2.78초 |
| 훈련자 2차(보류·PDF·미리보기) v0→v3, 같은 task_id | v0 SYNTAX 1 → v1 PURE_EXPRESSION 6(삼항 안 파이프·효과 호출·`??`) → v2 FIELD_TYPE 11(선택 변수 Null 합집합) → v3 issues 0 | 정상 1.4초. **1차 세션·탭을 그대로 이어받음**(same_session true, 로그인 없이 보류 화면 진입), iframe 약관은 `check selector`, 신청은 `dialog:"accept"`, 보류 HB001, PDF 재독 대조 전건 일치 | **달성(브라우저)** 검수 17/17 · **미리보기 다리 미실행** — `limbs:screen wait/snapshot` 이 `AX -25204 손쉬운 사용 권한` 으로 거절(백엔드 Python 에 권한 없음). `os_open` 은 먼저 실행돼 미리보기 창이 열린 채 남음 | 1.4초 |
| 변형 A(요금 인상, 같은 프로그램) | — | 1차 3.38초·2차 1.58초 | **달성** 18/18 — 보류 198,000 ≠ 비교표 176,000 을 "사용자 재결정 요청" 으로 보고, 서버 보류 1건 | 4.96초 |
| 변형 B(조식 기준, 1차를 `reuse`) | — | 1차 3.8초(reuse 0/15 — 전 호출 `unknown_write_resources`)·2차 2.18초 | **달성** 17/17 — 선택 B2 236,000·보류 일치 | 5.98초 |
| 변형 exp(세션 5요청 만료) | 2차 v4(try+프레임 만료 감지, 수정 1회) | 4회 시도: ①1차 ok·2차 프레임 안 만료로 `#agree` 실패(v3) ②1차 B 동의 클릭 `ref e12` 미해소 ③1차 ok·2차 v4 두 시도 모두 만료(서버 favicon 요청이 카운트됨 — 하네스 결함) ④favicon 보정 뒤 1차 다시 e12 미해소 | **미달** — 같은 원인(e12) 두 주기 무진전으로 중단. 재로그인 경로 자체는 탐침 [probe_hold_flow_B](evidence/probe_hold_flow_B.json)(expired:true→재로그인→보류 화면 진입)로만 확인 | — |
| 독립 AI 조건 A(자유) | — | 정상 ep4509, 도구 25(execute_ibl 14·Bash 11). **또 Python Playwright**(`scripts/run.py`), `limbs:browser` 0. 미리보기는 osascript+screencapture 로 보류번호 판독, cmd+w 는 AX 권한으로 실패(창 남음) | **달성(브라우저)** 정규화 검수 17/17, 보류 HB001·PDF 5항목 일치·재로그인 0 | 344.9초 |
| 독립 AI 조건 B(IBL 만) | 검사 거절·수정 다수(보고: report 보간 누락 1) | 정상 ep4510, **도구 40 전부 execute_ibl(limbs:browser 27·limbs:screen 5·Bash 0)** — 두 탭·모달·달력·스테퍼·selector 체크·dialog accept·pdf·self:read 전부 IBL. 탭 전환은 판본 1 로 내려가 우회 | **달성(브라우저)** 17/17. 미리보기 미실행(기본 PDF 앱이 PDFgear 라 미리보기가 앞에 안 옴 → 키 0) | 383.1초 |

- [사전 과제](task.md) · 1차 [v0](drafts/compare_v0.ibl)→[v2](drafts/compare_v2.ibl) · 2차 [v0](drafts/hold_v0.ibl)→[v3](drafts/hold_v3.ibl)(실행본)→[v4](drafts/hold_v4.ibl)(exp 변형용)
- 훈련자 증거: 검사·실행 기록 [evidence/trainer_*.json](evidence/) · 검수 [base](evidence/trainer_base_qa.json)·[flaky](evidence/trainer_flaky_qa.json)·[b](evidence/trainer_b_qa.json)·[exp](evidence/trainer_exp_qa.json) · [서버 상태](evidence/server_state/) · 산출물 사본 [artifacts/trainer](artifacts/trainer/)
- 탐침: [화면 권한](evidence/probe_screen_permission.json) · [검색 흐름·탭](evidence/probe_flow_call1.json) · [tab switch tab_id 거절](evidence/probe_tab_switch_tab_id_rejected.json)·[id 실행 거절](evidence/probe_tab_switch_id_runtime_rejected.json)·[index/url/name 전부 거절](evidence/probe_tab_switch_variants.json) · [프레임 문맥 잔류·세션 만료](evidence/probe_hold_links_iframe.json) · [보류 흐름(재로그인·동명 링크·프레임 snapshot)](evidence/probe_hold_flow_B.json) · [프레임 체크박스 selector/evaluate](evidence/probe_iframe_checkbox.json)
- 외부 효과: 로컬 합성 포털 보류 4건(기본·flaky·b 각 1 + 탐침 0) · 미리보기 창 1개가 열린 채 남음(사용자 화면) · 키 입력 0.

## 2. 과제·환경·작성

합성 포털([site_server.py](harness/site_server.py), 한 코드로 A 바다숙소·B 산장숙소): 로그인(쿠키) → DOM 동의 오버레이 → 검색(달력 버튼·박수 select·인원 +/-) → 객실 표 → 보류 화면(약관 iframe 체크박스 → postMessage → `confirm()`) → 완료 화면. B 는 로그인 뒤 요청 8회마다 세션 만료(`--expire`), `--flaky` 는 첫 조회 뒤 최저가 방 +11,000. 서버 state.json(로그인·만료·동의·보류·거절)이 oracle 일부. 자료 [prepare.py](harness/prepare.py): trip(11-14, 2박, 2명, 예산 260,000)·계정·포털 2.
**환경**: `/ibl/execute` `project_id:"수동모드"` `origin:"training"` **`task_id` 명시**(1차·2차 같음), 예산 100만 단계, 모델 0, `driver:"playwright"`. 데스크톱은 `desk:true` 일 때 os_open→wait expect_app→snapshot→cmd+w 만.

**분해**: 1차 — 보조 4(`참조`·`글`·`원`·`객실행`) + `포털읽기`(로그인→동의→달력→박수→인원→검색→표 파싱; 포털당 1회, 탭은 호출자가 준비) → 비교·기준 필터·정렬·선택·이유 → compare.json/md → 비교 Record 반환. 2차 — `재로그인`·`보류시도`(보류 화면→만료면 재로그인→iframe 약관 selector check→reset→신청 dialog:accept→완료 판독) → 탭 조치(활성 탭이 선택 포털이 아니면 close — switch 불가) → 보류(실패 시 1회 재시도) → pdf → self:read 대조 → 판정 → 미리보기(try) → result.json/report.md.
**작성 조건**: 수리된 browser_action.md·desktop.md·교재·describe 3·탐침 9. 코드 열람 0. 검사 수정: 1차 2회, 2차 3회(전부 작성자 오류 — f-string 안 따옴표 삼항은 44·45·46 세 회차 연속 재발, 삼항 자리의 파이프/효과 호출, assert 뒤 Null 미축소). 작성 시간: 서버·자료 약 8분, 탐침 약 7분, 초안 2편 약 7분, 수정 약 4분.
1차 결과를 2차에 넘기는 방식: HTTP 응답에 `result_ref` 가 없어(관측) `$ref` 대신 1차가 쓴 compare.json 을 값으로 `inputs.compare` 에 넣었다.

## 3. 검수와 독립 AI 비교

결정론 [verify.py](harness/verify.py): compare.json(6객실 총액·B3 마감·선택) + result.json(보류번호·대조·판정·세션 동일·탭 2·미리보기 보고) + hold.pdf 텍스트(fitz) + 서버 A/B state(보류 1건·A 0·동의·만료). 기본 17/17·변형 A 18/18·변형 B 17/17·exp 12/17(미달).

### 독립 AI (ep4509 조건 A 자유 · ep4510 조건 B IBL 만)

| 볼 것 | 관측 |
|---|---|
| 풀이 방식 | **A**: 입력 읽기만 IBL, 곧 Bash 로 playwright 확인 → `probe.py`·`run.py`(두 탭·동의·달력·스테퍼·iframe `#agree`·dialog accept·page.pdf·텍스트 대조) → IBL 로 PDF 재독·결과 쓰기. 데스크톱은 ioreg/CGSession/osascript. 셸 Python 풀이. **B**: 40호출 전부 IBL — 포털마다 navigate→snapshot→type→click(동의)→달력→select label→+ 클릭→검색→content 파싱, `tab new`, 보류는 `click selector`(동명 링크)·`iframe switch name`·`check selector:#agree`·`iframe reset`·`click dialog:accept`·`pdf`·`self:read`, 데스크톱은 `os_open`→`screen wait expect_app`(권한 거절)→`screenshot path` 3장→`engines:image_read` 로 앞 앱 판독(PDFgear) → 키 0. IBL 긴 프로그램이 아니라 호출 40회의 대화형 IBL 이지만, **과제 전체가 IBL 어휘로 완수됐다** |
| 분할·재사용 | 둘 다 `reuse`·`$ref` 없음. B 는 호출당 1~3 조작으로 잘게 나눠 문맥 비용이 컸다(입력 7.1M vs A 3.7M) |
| 방법 발견 | A: describe 0, 가이드 0 — 45회차와 같은 자기 Python 경로. B: 제약을 받자 IBL 계약을 스스로 탐색(검사 거절을 읽고 selector·판본 1 전환·reset 등으로 우회), **L46-1·2·3 과 AX 권한을 전부 스스로 발견해 보고** — 훈련자 발견과 독립 일치 |
| 완료 판정 | 둘 다 완료 화면 보류번호로 성공 판정, PDF 재독 5항목 대조, 제출 직전 포트·객실 검증, 저장 후 재독·비밀값 부재 확인. B 는 동의 클릭 실패(L46-4) 뒤 "창이 사라졌지만 적용 여부 미확인" 이라고 정직하게 적음(서버는 적용됨) |
| 축적 | A 는 44·45회차 자기 스크립트 습관, B 는 제약이 없었다면 같은 길이었을 것(45회차 가설 확정: 못 쓰는 게 아니라 안 고른다) |
| 비용 | A 344.9초·입력 3,682,725/출력 28,528. B 383.1초·입력 7,132,611/출력 30,496. 훈련자 1차+2차 4.2초(모델 0) |

훈련자 갭이 독립 AI 에서도 밟혔는가: L46-1(탭 전환)·L46-2(프레임 snapshot)·L46-3(동명 링크)·L46-4(이동 클릭 거짓 실패) — 조건 B 에서 전부 밟힘. L46-5(프레임 문맥 잔류) — B 는 매 호출 reset 을 해 안 밟음. AX 권한 — 셋 다.

## 4. 발견과 공통 개선 방향

### 45회차 수리의 실전 확인
`select label:"2박"` 동작(L45-1 수리). `limbs:screen` 의 `expect_app`·`wait` 는 계약에 실렸으나 이 기기에서는 **백엔드 Python 에 손쉬운 사용 권한이 없어 `AX -25204` 로 거절**(L45-2 수리의 눈은 권한 뒤에 있다 — 훈련자·독립 AI 둘 다 같은 거절, 키 입력 0). 수리 자체의 검증은 권한 부여 뒤로 남는다.

### L46-1 — 탭 전환이 판본 2 계약에서 불가능하다
계약 불일치. 가이드·실행기는 `tab switch` 에 `tab_id` 를 요구하지만 닫힌 계약에 `tab_id` 가 없어 검사 `UNKNOWN_ARGUMENT`([probe_tab_switch_tab_id_rejected](evidence/probe_tab_switch_tab_id_rejected.json)); 계약이 허용하는 `id`·`index`·`url`·`name` 은 실행기가 전부 "tab_id가 필요합니다" 로 거절([variants](evidence/probe_tab_switch_variants.json)). 따라서 **두 탭을 열면 돌아올 수 없다**. 독립 AI(조건 B)는 판본 1 문법으로 내려가 전환했다고 보고. 훈련자는 "활성 탭이 아니면 활성 탭을 닫아 이전 탭으로" 우회(2차 호출 `tab_action`).
처방: 계약에 `tab_id` 추가(44·45회차와 같은 부류 — 닫힌 계약 census 가 실행기가 읽는 키를 못 잡는다).

### L46-2 — iframe 안에서 snapshot 은 메인 프레임을 읽는다
구현 결함. `iframe switch name:"terms"` 뒤 `content` 는 프레임 본문을, `check selector:"#agree"`·`evaluate` 도 프레임을 따르지만 **`snapshot` 은 메인 페이지 요소**(헤딩·신청 버튼)를 돌려준다([probe_iframe_checkbox](evidence/probe_iframe_checkbox.json) frame_snap_elems, [probe_hold_flow_B](evidence/probe_hold_flow_B.json)). 가이드의 "iframe 진입 → snapshot → ref 클릭" 흐름이 서지 않는다. 독립 AI 조건 B 도 같은 발견(selector 로 우회).
처방: snapshot 이 현재 프레임 문맥을 따르게 하고 결과에 `frame` 을 싣기.

### L46-3 — 이름이 같은 링크는 ref 로 누를 수 없다
설계 경계·안내 공백. 객실 표의 '예약 보류' 링크 2개는 snapshot 에서 서로 다른 ref(e37·e38)를 받지만 클릭은 "요소를 찾을 수 없습니다" — Playwright 쪽이 이름·역할 유일성으로 재해소하기 때문(가이드 "대상이 사라졌을 때" 절의 규칙). 표·목록처럼 **같은 이름의 행동이 줄마다 반복되는 화면**에서는 ref 가 쓸모없고 `selector`(`a[href^='/hold/B1']`) 로만 된다([probe_hold_flow_B](evidence/probe_hold_flow_B.json) byref vs bysel). 독립 AI 조건 B 도 같은 우회.
처방: snapshot 이 준 ref 는 그 세대 안에서 n번째 후보로 해소하거나, 거절 메시지에 "같은 이름 N개 — selector/행 문맥" 을 안내.

### L46-4 — 이동을 일으키는 클릭이 성공했는데 실패로 보고된다
정직 보고 결함. 동의 모달 '필수만 동의' 클릭은 POST→리다이렉트로 요소가 사라지는데, 클릭 뒤 재해소가 실패해 "요소를 찾을 수 없습니다(ref=e12)" 로 **실행이 중단**된다. 서버 state 는 동의가 들어왔다고 말한다(exp4 B `consents 1`, 조건 B 의 A 서버 `consents 1`). 훈련자 1차 호출 2/6 실행(exp2·exp4)·독립 AI 조건 B 1회 재현, 기본·flaky·b 는 통과 — 간헐(리다이렉트 타이밍). 효과는 났는데 프로그램은 죽고, 되감기도 안 된다.
처방: 클릭 뒤 검증은 "요소 재해소" 가 아니라 "네비게이션 발생 또는 요소 소멸" 을 성공 신호로; 실패 봉투에 `effect_observed`(URL 변경) 동반.

### L46-5 — 실패한 실행이 iframe 문맥을 세션에 남겨 다음 호출이 프레임 안에서 돈다
격리·상태 누수. 같은 `task_id` 세션에서 프레임으로 전환한 뒤 실패로 끝난 호출의 다음 호출은 `navigate` 도 `snapshot` 도 프레임 문맥(`current_frame:"iframe"`)에서 돈다 — 메인 페이지가 "로그인" 처럼 보이고 selector 가 안 잡혀 원인을 알기 어렵다([probe_hold_links_iframe](evidence/probe_hold_links_iframe.json): iframes [] 인데 current_frame iframe). `iframe reset` 으로만 풀린다.
처방: 실행 종료(성공·실패 모두)에 프레임 문맥 reset, 또는 navigate 가 메인 프레임으로 복귀.

### 관측(갭 아님)
- HTTP `/ibl/execute` 응답에 `result_ref` 가 없다 — 교재의 `$ref` 연결은 MCP 경로 전제. 2차 호출은 1차가 쓴 compare.json 을 값으로 받았다.
- `reuse`: 브라우저 호출 전부 `unknown_write_resources` 라 변형 B 의 1차 재실행은 15/15 미재사용(L41-3 부류의 browser 판). 비용 3.8초라 실해는 작다.
- 조건 A 독립 AI 는 또 Python(Bash 11, `limbs:browser` 0). **조건 B(IBL 만)는 40호출 전부 IBL 로 같은 과제를 완수** — 못 쓰는 게 아니라 안 고르는 것(45회차 가설 확정). 조건 B 는 L46-1·2·3 과 AX 권한을 스스로 발견·보고·우회했다.
- 데스크톱: 이 기기의 PDF 기본 앱이 PDFgear 라 `os_open` 은 미리보기를 열지 않는다(조건 B 발견). 과제문이 "미리보기" 를 지정하면 `os_open` 으로는 못 연다 — 앱 지정 열기 어휘 없음(관측).
- 검사 수정 5회 중 f-string 안 따옴표 삼항 2회는 44·45·46 연속 재발(작성자 습관) — `report.md` 보간 누락은 독립 AI 도 두 회차 연속.
- 세션 만료(exp) 변형은 서버가 favicon 요청까지 세어 만료가 두 배 빨랐다(하네스 결함, 보정 뒤에도 L46-4 로 1차 실패) — 재로그인 경로는 탐침에서만 확인.

## 5. 비용·낭비·한계

**상한·시간**: 16:01:47 시작 → 16:25 독립 AI 종료·서버 정리(약 24분/상한 60분). 보고서·원장·기억 별도. 훈련자 수정 5회(1차 2·2차 3) + exp 변형용 v4 1회.
**훈련자 비용**: 1차 2.78초·5,615단계, 2차 1.4초(모델 0). 변형 A 4.96초, B 5.98초(reuse 0). 작성자 토큰 미측정. **독립 AI**: 조건 A ep4509 344.9초(도구 25 = execute_ibl 14·Bash 11, 입력 3,682,725/출력 28,528), 조건 B ep4510 383.1초(도구 40 = execute_ibl 40, 입력 7,132,611/출력 30,496, cache_read 6,827,667).

1. **필요했던 비용** — 탐침 9회(탭 전환·프레임·동명 링크·세션 만료·권한을 교재로는 알 수 없었다), PDF 재독 대조, 서버 state 대조, 독립 AI 의 제출 직전 포트·객실 검증과 "미리보기가 앞에 오지 않으면 키를 안 보낸다".
2. **줄일 수 있었던 일** — (a) 훈련자 exp 변형 4회 재시도 중 2회는 하네스(favicon)·1회는 stale compare.json(1차 실패 뒤 2차 실행) 이라는 운영 실수. (b) 독립 AI 조건 B 는 조건 A 의 2.1배 입력 토큰(7.1M vs 3.7M)으로 같은 결과 — IBL 호출 40회의 왕복이 Python 1회 실행보다 모델 문맥을 더 쓴다(IBL 선택의 비용). (c) 2차 호출에서 활성 탭이 선택 포털이면 탭 조치 0 — 두 탭 중 어느 쪽이 활성인지에 성공이 걸려 있다(L46-1).
3. **원인과 근거** — (a) 작성자/하네스, (b) 호출 단위 설계(한 호출에 여러 조작을 묶으면 줄어든다 — 조건 B 는 호출당 1~3 조작), (c) 계약 공백.
4. **다음 개선과 보존할 품질** — §4 처방. 보존: 완료 화면·PDF 재독으로 성공 판정, 금액 불일치 시 재결정 요청, 포커스 불확실 시 입력 보류.

**한계·미검증**: 데스크톱 다리는 권한 때문에 세 실행 모두 미실행/부분(조건 A 는 osascript 로 읽기만). 세션 만료 재로그인은 프로그램에서 미검증. 표본 1회. 사용자가 자리에서 작업 중이라 미리보기/PDFgear 창이 열린 채 남았다.

## 6. 종료와 재현

종료 이유: 기본·변형 A·B 와 독립 AI 두 조건이 브라우저 완료 조건을 채웠고 발견 5건의 최소 재현을 확보했다. 세션 만료 변형은 같은 원인(L46-4) 두 주기 무진전으로 중단(미달). 데스크톱 다리는 권한·기본 앱 때문에 미실행 — **사용자 조치 필요**: 백엔드 Python(`/opt/homebrew/…/python@3.13`)에 '손쉬운 사용' 권한, 미리보기(또는 PDFgear) 창 닫기. 서버 16개 종료, 상태 사본 [evidence/server_state](evidence/server_state/).
재현: `prepare.py` → `site_server.py --site A|B --port … --state … --account …`(변형 `--flaky`, `--expire N`) → `run.py base 1 --draft compare_v2.ibl --task-id T` → `run.py base 2 --draft hold_v3.ibl --task-id T [--desk]` → `verify.py`. 독립 AI 는 `ai_chain.py condA|condB runs/ai_request_A|B.txt`. 계정·코드 합성, 증거의 비밀번호는 `<password>` 로 치환.
다음 회차 후보: 권한 부여 뒤 데스크톱 루프 재시험(expect_app·wait·snapshot 프레임 복귀 포함); L46-1~5 수리 뒤 같은 프로그램 재생(원래 전체 흐름·exp 변형 포함); 독립 AI 가 제약 없이도 IBL 을 고르게 하는 경로(회상에 조건 B 의 성공 경로 노출) 실험.

## 7. 후속 수리 (2026-10-09)

이 절은 최초 훈련 관측과 분리한 수리 기록이다. 적용 전 정본 main은 `5c6c9c4a`.
훈련자 기본·변형의 응답과 실패 진단, 독립 AI 두 작업의 `succeeded` 영수증을
확인한 뒤 적용했다. 작업 ID·실행 ID·적용 시작 시각은
[evidence/repair_terminal_audit.json](evidence/repair_terminal_audit.json)에 보존했다.

| 갭 | 수리와 확인 |
|---|---|
| L46-1 | 닫힌 계약에 `tab_id` 추가. Playwright/Chrome의 switch는 기존 계약·회상 용례에 있던 `index`도 0부터 해소한다. 잘못된 Chrome ID를 첫 탭으로 보내던 폴백은 거절한다. 판본 2 검사와 실제 탭 왕복, 잘못된 인덱스/ID 거절 확인. |
| L46-2 | snapshot이 선택한 프레임의 CDP 접근성 트리를 읽고 `frame:{kind,name,url}`을 반환한다. 이름·URL이 같은 두 프레임도 실행 문맥으로 식별한다. 다른 사이트의 분리 프레임은 해당 target에서 AX·selector를 조회한다. 실제 Chromium에서 프레임별 체크박스를 ref로 선택하고 부모 요소가 섞이지 않음을 확인했다. selector 추출 시간 초과가 이미 얻은 AX 이름·역할을 버리지 않도록 했다. |
| L46-3 | 동명 요소를 임의로 선택하지 않는 기존 신원 보호를 유지하고, `REF_AMBIGUOUS`·`candidate_count`와 행/링크 주소를 확인한 고유 selector 안내를 반환한다. 중복에 새 snapshot만 반복하라는 안내를 수정했다. **동명 ref의 자동 구분 구현은 아니다.** |
| L46-4 | **원인 정정:** click 구현에는 성공 뒤 요소를 다시 해소하는 코드가 없었다. `STEALTH_INIT_SCRIPT`의 DOM observer·타이머가 동의 버튼을 먼저 자동 클릭했다. 이를 제거해 명시 click과의 경쟁을 없앴다. 이전 초기화 코드/수리 코드 격리 재현에서 자동 클릭은 **1→0**, 버튼 잔존은 **0→1**이었다([증거](evidence/repair_consent_probe.json)). 페이지 이동만 보고 성공을 추정하거나 효과를 재시도하지 않는다. |
| L46-5 | navigate(goto/back/forward)가 메인 프레임으로 복귀하고 ref를 비운다. 실제 이동 시도가 실패해도 복귀 상태를 유지한다. 호출마다 reset하지 않으므로 같은 작업의 여러 호출로 iframe switch→snapshot→check를 이어갈 수 있다. |

검증 코드는 `backend/test_browser_navigation.py`·`test_browser_session.py`와 기존
ref 신원·snapshot 경계 검사에 있다. 첫 실행은 시험자료의 문자 인코딩/iframe 로딩 순서
오류를 발견해 보정했다. 최신 검증은 별도 임시 서버·Chromium에서 실행하며 사용자의
데스크톱에 키 입력·창 열기·실제 예약을 보내지 않았다.

- 원래 `compare_v2.ibl` + `hold_v3.ibl`의 기본·요금 인상·조식 변형을 PDF 재독과 기존 oracle까지 재생: 각각 **17/17·18/18·17/17**.
- `hold_v4.ibl` 세션 만료 복구: 비교 후 세션을 만료 직전으로 만들어 신청 단계 만료→재로그인→보류 1건·PDF 대조 **17/17**. 새 로그인은 8요청 동안 유효하다.
- 새 변형: 비교 뒤 다른 탭을 활성화하고 닫기 우회를 `tab_id` 전환으로 교체. **17/17**, 두 탭 모두 유지.
- 원래 5요청 만료 조건도 재생: **보류 실패·서버 보류 0건을 정확히 보고**. favicon 제외만으로 해결되지 않는다. 새 로그인 이후 검색(1)→동의 POST(2)→검색(3)→보류(4)→약관(5)→신청 POST(6)→완료(7)여서 5요청으로는 완료 자체가 불가능하다. 이를 성공 변형으로 세지 않는다.
- 기존 44회차 전체 프로그램 4조건과 45회차 3조건도 통과. 선택기가 고른 전이 소비자와 어휘 배포 검사를 포함한 종합 **396 passed**, 마지막 snapshot 예외 경계 보강 후 관련 검사 **65 passed**(범위 중복). backend 전수는 이번 변경에서 실행하지 않았다.

라이브 허브도 수정 소스와 같은 digest로 ACTIVE·ready임을 확인했다. HTTP IBL 한 프로그램으로 탭 전환→iframe snapshot→ref 체크→navigate 메인 복귀→세션 닫기를 실행해 completed를 회수했다([증거](evidence/repair_live_smoke.json)).

잔여: 실제 데스크톱의 손쉬운 사용 권한·기본 PDF 앱은 이 수리로 바뀌지 않았다.
미리보기 다리와 독립 AI의 자발적 IBL 선택은 재검증하지 않았고, 전체 시간·토큰 절감도
측정하지 않았다. 가이드·용례 계약 검토·파생 어휘 및 은퇴 계약 관문은 함께 갱신했다.
