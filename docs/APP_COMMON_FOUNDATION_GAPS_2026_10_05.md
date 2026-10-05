# 앱 공통 기반 — IBL에 없어서 설치가 필요한 것 (통합 정리)

작성일: 2026-10-05. 개정: 같은 날 Codex 검토 반영(주체·완료 의미·미디어 제공자·위임 범위·관용구 선별 기준·순서). 상태: **정리(판정·집행 전)**.
독자: 다음 앱을 IBL 위에 세울 구현자, 언어 개정 판정자.
합친 출처: (1) 같은 날 집행된 세 앱 준비 — [공통 기반 위의 앱 구성](APP_COMPOSITION_ON_IBL_PLAN_2026_10_05.md) §6-1~3, (2) 나머지 앱 전수 감사 — [앱 전수 감사](APP_IBL_GAP_AUDIT_2026_10_05.md), (3) Codex 검토(2026-10-05, 코드 대조 의견).
원칙: "앱을 만들다 필요한 어휘·문법이 있었다면 그것을 더해서라도 공통 기반 위에"(사용자). 여기 적는 것은 **둘 이상의 앱이 같은 이유로 escape한 공통 결손**만이다. 항목마다 **책임 범위 · 기존 경로의 전환 · 완료 조건**을 적는다 — 기능 목록이 아니라 실행 계획이 되기 위해서다. ①~⑨는 채웠고 ⑦·⑩은 설치 항목이 짧아 완료 조건만 적었다. 뒤 항목의 상세 설계가 끝나야 ①을 시작하는 것은 아니다.

## 0 오늘 이미 설치된 것 (다시 만들지 않는다)

| 층 | 설치됨 | 닫힌 결손 |
| --- | --- | --- |
| 몸 | `workspace_sessions.py` — document/sheet/code 어댑터 위 공통 작업 공간(열기·스냅샷·제안·조건부 저장·버전·복구). `office_sessions`·`coding_workspace` 재사용 | 앱별 저장소·세션·작업표 |
| 어휘 | `[self:workspace]` 12 op. `self:document`·`self:sheet` 세션 op 25개 흡수(순감) | 서비스 1:1 포장 낱말 |
| 표면 언어 | 뷰 `engine`(ref=작업 공간 자료), 이벤트 `selection`/`saved`, **keep 규약**(이벤트 페이로드가 `$sel`·`$resource` 변수로 남아 ai_dock·버튼·폼이 쓴다) | 편집기 escape 3개, 선택 범위의 전달 |
| 표면 언어 | 검증기가 템플릿의 `[fn:]`·`[def:]` 허용(판본 1 파서도 `[fn:]` 실행) | 앱이 관용구를 못 부르던 것 |
| 런타임 | 위임 접수증 통일 `{accepted, task_ref, run_id, state, status_url}`, 상태 GET `?wait=`(≤30초), `mode:sync`=같은 task 대기, `scope:system` sync, 순환 거절, 전문 저장 | 위임의 "접수≠완료" 계약 |
| 런타임(이전부터) | `principal.py` — 전송 관문이 세우는 주체(owner/member/body/portal/anonymous), **좁힐 수만 있는** 규칙, contextvars·스레드 스냅샷 전파. `portal_gate`가 `narrow(portal|anonymous)`로 실행 | 실행 문맥의 주체 — **이미 있다**(§1-② 참조) |
| 관용구 | 선택교정·검토본저장·범위제안·과제열기·파일고치기·검토반영 6정의+6용례 | 앱별 관용구 0건 |

## 1 설치 목록 — 집행 순서대로

순서: **① 입력 계약 → ② 권한 기반 연결 → ③ 작업 수명·④ 이벤트 → ⑤ 미디어·⑥ 표면 지시 → ⑦ 선택·순서·페이지 → ⑧ 뷰 낱말 → ⑨ 위임 범위 → ⑩ 명사 어휘.** ①이 모든 값의 통로, ②가 모든 "사람만·회원만" 조건의 통로라 앞에 둔다. §2의 수리는 기반 완료를 기다리지 않는다.

### ① 표면 바인딩을 타입 보존 입력으로 (표면 언어 개정 · 판정) — **집행 완료 2026-10-05**
**집행**: 판정은 "컴파일러가 미지정 입력에 매인 인자를 생략으로 접는다"로 결정(사용자, 2026-10-05). 구현 = `declared_inputs` 요청 필드 + 컴파일러 `unspecified`(인자 생략·보간 ""·그 밖 거절) + 런타임 `OMITTED` + 공용 코어 `appRequest/actionRequest` + 두 렌더러·포털 게이트(`template_allowed`, 원문 글자 대조)·회원 해소기 + 변환기 `migrate_app_templates_edition2.py`(33 블록 → edition 2, `@hub`·축약 3 블록 → edition 1+legacy_reason; 잠든 패키지 어휘는 가드가 경고로 건너뜀) + 검증기(edition 필수·구형 치환 거절·`$item`) + `--check` 판본 2 앱-템플릿 컴파일 가드. 회귀 `test_app_template_inputs_2026_10_05.py`. 같은 날 후속으로 판본 2 에 `@별칭` 노드 지정을 이월해 남은 3 블록도 edition 2 가 됐고 구형 치환 코드(코어·포털·회원 해소기)와 `edition: 1` 탈출구를 삭제했다 — **완료 조건 전부 충족**. 업무기록 화면의 `[self:record]` 직접 호출 전환은 §2(화면 수리)의 몫. 명세: ibl.md '앱 표면 노출 → 표면 바인딩', [렌더러 플랜](REMOTE_APP_GENERIC_RENDERER_PLAN.md) 최상단 항목.
**없는 것**: 앱 템플릿의 `$key`는 코드 문자열에 값을 스플라이스한다(`app_render_core.js buildAction`): 빈 값이면 인자 쌍을 정규식으로 삭제하고, 행 값의 `"`를 지운다 — **입력이 프로그램의 의미를 바꾼다**. 객체·배열을 넘길 수 없고, IBL 변수 `$x`와 이름 공간이 겹쳐 판본 2 프로그램을 쓸 수 없으며, 렌더러가 `edition`을 보내지 않아 모든 앱 호출이 판본 1로 돈다. 오늘 설치된 `selection`도 selector를 JSON **문자열**로 실어 관용구가 다시 파싱한다. 업무기록 화면이 REST로 간 명시 사유.
**책임 범위**: 표면→실행기의 값 전달만. 뷰 어휘·실행 의미는 바꾸지 않는다.
**설치**: 렌더러가 입력값·행·이벤트 페이로드·표면 상태를 `/ibl/execute`의 `inputs`(이미 있음)로 보내고 `edition: 2`를 명시. 템플릿은 `$input.key`·`$item`·`$event.*`·`$state.*` 네 이름 공간을 읽는 판본 2 프로그램. 검증은 정규식을 다른 정규식으로 바꾸지 않고 **판본 2 컴파일러(`validate_request_code`)로 템플릿을 inputs 선언과 함께 검사**한다.
**전환**: 구형 선언을 일괄 `edition:2`로 바꾸지 않는다. (a) 빌드가 구형 템플릿(`$key`·`{field}`)을 새 이름 공간으로 **기계 변환**하고 결과를 파일에 쓴다(사람이 diff 확인). (b) **생략·`null`·빈 문자열 셋을 가른다** — 인자 생략은 키 자체가 없는 것(핸들러의 `params.get("limit", 20)` 기본값이 산다), 명시 `null`은 값 `null`(기본값이 적용되지 **않는다**), 빈 문자열은 값 `""`. 지금 치환기는 빈 입력을 **인자 쌍 삭제**(=생략)로 처리하므로 변환 규칙은 "구형 템플릿에서 빈 입력이던 자리 → 생략 유지"다. 신형 템플릿은 생략을 `$input.limit ?? omit`처럼 명시하거나, 컴파일러가 미지정 입력에 매인 인자를 생략으로 접는다 — 둘 중 하나로 정하되 `null`로 바꿔 넘기지 않는다. (c) 변환기가 못 푸는 템플릿은 목록으로 신고하고 그 앱만 구형 경로를 유지한다. 두 경로는 플래그 하나로 공존하되 **새 앱은 신형만**.
**완료 조건**: 33개 앱 블록 + 독립 매니페스트 2장이 신형으로 돌고 기존 회귀(`test_app_view_*`·계기 시험) 통과, 구형 치환 코드 삭제, 업무기록 `actions/{id}` 전송을 `[self:record]` 직접 호출로 대체해도 객체 `input`·`expected[]`가 손실 없이 도착.

### ② 권한 기반의 연결 — 주체·허용 범위·사람 승인은 서로 다른 사실 (언어 개정 · 판정) — **1차 집행 2026-10-05**
**집행**: (1) 액션 선언 `requires: {principal, min_level, human_confirm, ops}` + 빌드 검증(`validate_requires`) + 실행기 관문 한 곳(`backend/base/action_requires.gate`, `execute_ibl` 잎) (2) 사람 승인 토큰 `backend/base/approval_tokens`(주체·액션·op·요청 지문 challenge, 1회·120초) + `/ibl/approve`(사람 통로) + 요청 `approval` 필드 + 두 렌더러의 승인 왕복(approval_required → confirm → approve → 같은 요청 재전송; 포털은 승인 통로 없음) (3) `$principal` 표면 변수(매니페스트에 요청마다 `principal` 부착, 검증기 허용) (4) 첫 소비자 `[self:package]{op: activate|deactivate}`(owner + human_confirm → `set_package_active(HUMAN_AUTHORITY)`). **2차 집행(같은 날 밤)**: (5) 어휘 활성 HTTP `/vocabulary/{id}/activation` 을 얇은 통로로 — 사람 표면 증명(`human_authority`) 뒤 `[self:package]{op, package_id, profile}` 를 실행기 관문 위로 보낸다(`run_ibl_as_human`: 그 요청 지문에 토큰 발급 → 관문 소비 → 핸들러가 HUMAN_AUTHORITY). `human_authority` 의 역할은 "사람 표면 증명" 하나로 줄었다. (6) 업무기록 확인 토큰을 공통 승인 토큰으로 — `issue_confirmation` 발급·`record_commands.apply` 소비가 같은 challenge(주체·`self:record`·`request_hash` = 명령·정의 판본·입력·expected·사유)를 쓰고, 공간별 `confirmations` 표(DDL·내보내기·복원)는 은퇴. record-ops `path_audited` 재감사(4 파일). **판정(구현자, 2026-10-05 밤)**: ⓐ포털 자원 범위(`requires.paths`)는 액션마다 "어느 인자가 자원인가"를 선언하는 자리가 먼저 있어야 한다(`self:read` 의 path, `self:record` 의 space…) — 그 자리는 ⑤(핸들·접근 규칙)와 같은 설계라 ⑤ 와 함께 열고, 그 전까지 포털 화이트리스트(원문 대조)는 그대로. ⓑ회원 승인 통로 `/m/approve` 는 지금 회원이 닿는 `human_confirm` 액션이 없어(유일한 소비자 `self:package` 는 owner 전용) 소비자 없는 배관이다 — ⑩ 에서 회원 등급의 human_confirm 액션이 생길 때 그 첫 소비자와 함께(승인 토큰이 `/m/run` 봉투를 타고 member_session → 관문까지 가는 배선 + 회원 셸 왕복은 실기기 확인이 붙는다). ⓒ`self:install_lib` 의 `install_approvals` 는 접지 않는다 — 두 패턴은 "누가 기다리는가"가 다르다: 승인 토큰은 **사람이 보는 표면이 지금 묻고 바로 재전송**(동기, 120초), install_approvals 는 **자율 에이전트가 요청을 남기고 사람이 나중에 조종실에서 승인**(비동기, 영속). 공통 토큰에 '보류 원장'을 붙이면 ③의 작업 수명과 겹친다 — ③ 뒤에 재검토. **남은 것(⑩ 뒤)**: 바탕화면·가져오기·외부사용자·패키지 설치/삭제 HTTP 창의 IBL 전환.
**있는 것**: 실행 문맥의 주체(`principal.current()`)는 이미 있고 넓힐 수 없다. 감사의 "봉투에 주체가 없다"는 **틀렸다** — 봉투 필드가 없을 뿐 문맥에는 있다.
**없는 것 셋**:
1. **액션이 요구 권한을 선언할 자리가 없다.** 지금 "사람만"은 라우트 함수 `human_authority`(Origin·Fetch-Metadata 검사)와 `vocabulary_lifecycle.human_required` 플래그에 산다. 그래서 `self:package`는 "변경 제안만", 매니저·설정·외부사용자는 REST로 남고, NAS는 별도 쿠키를 둔다.
2. **표면이 주체를 읽을 수 없다.** 매니페스트에 `$principal`이 없어 회원별 다른 뷰를 액션이 서버에서 분기해야 한다.
3. **사람의 승인이 대상에 묶인 공통 계약이 아니다.** 업무기록은 CSRF+120초 확인 토큰을 따로 만들었고, 포털은 계기 템플릿 화이트리스트, 회원 앱은 서버 해소 동작 ID로 "임의 코드 금지"를 각자 구현했다.
**책임 범위**: 주체 모델을 새로 만들지 않는다. 기존 `principal`에 (1) 액션 선언 `requires: {principal: owner|member(level≥n), human_confirm: true|false}`와 실행기 관문, (2) 표면 주입 **읽기 전용** `$principal`(kind·level·id — 판정에 쓰는 값은 서버 문맥, 표면 값은 표시·분기용), (3) 승인 토큰 계약 — **대상(resource·action)·행위·유효기간**에 묶인 1회성, 발급은 사람이 보는 표면에서만, 검증은 실행기 — 세 개를 **연결**한다. `is_web_surface()`가 답하는 "재생이 어디서 나야 하나"는 주체가 아니라 표면 정보이므로 ⑥으로 보낸다.
**전환**: `human_authority` 호출처 → 해당 액션의 `requires`로 이관(라우트는 얇은 통로로 남거나 삭제). 포털 화이트리스트는 **허용 낱말과 주체만으로는 대체되지 않는다** — 같은 `self:read`라도 공개 폴더와 개인 폴더는 다르고, 템플릿 일치 검사는 고정 인자(경로·범위)까지 묶는다. 새 계약이 **대상 자원과 인자 범위**를 동등하게 제한할 수 있을 때(`requires`에 자원 범위 선언, 예: `paths: [public/**]`)만 템플릿 검사를 줄인다. 그 전까지는 그대로 둔다. 사람 승인 토큰은 `resource·action`뿐 아니라 **실제 변경 내용의 지문**(제안 본문·diff·입력의 해시)에 묶어 승인 뒤 내용 교체를 막는다 — `[self:workspace]{op:"propose"}`의 `proposal`이 그 지문의 자연스러운 담지자. 업무기록 확인 토큰은 공통 승인 토큰의 첫 소비자. 회원 앱 동작 ID는 ①+② 뒤 `/m/run`이 IBL 원문을 받을 수 있는지 평가 — 당장 은퇴 대상은 아니다.
**완료 조건**: `requires` 없는 액션의 거동 불변 · `self:package` 활성화가 IBL로 사람 승인 토큰과 함께 성공 · 포털 손님이 `requires: owner` 액션을 부르면 실행기 관문이 거절(화이트리스트 꺼도) · 매니저 창의 생애주기 호출이 IBL로 가능(⑩ 뒤).

### ③ 작업 수명의 공통 관찰·제어 — 접수증은 모양보다 "완료의 의미"가 먼저 (통화·어휘 개정 · 판정) — **1차 집행 2026-10-05 밤**
**집행(1차)**: (a) 접수증 통화 1종 `backend/base/task_receipts.receipt` — `{accepted, task_ref:{kind, task_id[, owner]}, state}`; 위임 접수증(`delegation_tasks.accepted`)이 이 통화 위로 옮겨 `kind: delegation` 을 얻었다. (b) **읽는 낱말** `[self:task]{op: status|wait|cancel, ref, timeout}` 신설(판정 기록 아래) — `wait` 는 유한(≤240초) 대기 뒤 `result` 를 값으로 잇고 시간 초과는 `timed_out`(실패 아님). (c) 상태 어휘 한 벌(queued/running/waiting_children/cancel_requested/succeeded/failed/cancelled/interrupted/unknown) — 등록부가 어휘 밖 투영을 `unknown` 으로 거절. (d) 어댑터 7종: delegation(코드 — `routing_system.register_all` 주입) · script(system_essentials `script_ops.task_status`) · guestpc(`phone_jobs.peek_result` 비파괴 + `cancel_pending`) · newspaper(상태 파일에 `task_id`, 시작 시각 보존) · lecture_video(`deck_video.status` 의 interrupted 판정 그대로) · notebook_source(`sources.status`) · sheet_op(`[self:workspace]` apply/save 의 시트 접수 — owner=자료 id). 패키지 종류는 각 `ibl_actions.yaml` 최상위 `task_kinds: {kind: "모듈:함수"}`(사전 — 데이터 길)로 선언하고 등록부가 처음 만날 때 적재한다. 회귀 `backend/test_task_receipts_2026_10_05.py`(한 프로그램이 두 접수증을 기다려 합치는 시험 포함). **판정 기록(구현자, 사용자 위임)**: `[self:task]` 는 새 낱말이다(어휘 +1). 대안 — `self:script status` 를 범용화(이름이 거짓) / `self:goal` 에 얹기(수명이 다르다) / 낱말 없이 HTTP status_url 만(IBL 안에서 값으로 잇지 못함 — 1순위 결손 그대로) — 을 물리쳤다. 흡수는 하지 않았다: `self:script status(job_id, wait)`·`guestpc result`·`deck video check` 는 호환으로 남는다(다음 차수에 용례가 `[self:task]` 로 옮겨가면 은퇴 판정). **2차(같은 날 밤)**: `scope: system` 위임이 접수 시점에 시스템 작업을 선발급해 같은 접수증(`task_ref{kind: delegation, owner: system}`·status_url)을 돌려주고 `mode: sync` 는 그 작업을 기다린다(옛 경로는 부모 task id 를 러너에 넘겨 자식 작업이 없었다). 예약 경로의 `queued+task_id` 추적 의미를 바꾸지 않으려 접수증에 `task_id` 는 싣지 않았다(child_task_id·task_ref 로 읽는다). **남은 것(3차)**: 사진·PC 스캔(HTTP 동기 경로 → 접수증 + React 폴링 은퇴, 실기기 확인)·표면 `await:` 선언 + mode 버튼 결과 렌더(렌더러 2곳 `setInterval` 은퇴)·`/m/run` NDJSON 을 같은 투영의 스트림으로. 성능 미측정.
**없는 것**: 위임 접수증은 통일됐지만 다른 긴 작업은 각자 모양이다 — `[self:script]{background}`→`job_id`+`op:status`, guestpc→`op:result`, `[engines:newspaper]`→즉시 반환+상태 JSON 파일, 사진·PC 스캔→스레드+진행 dict+2초 폴링, 시트 `apply`→`state:queued`. `status_url`은 HTTP 경로라 **IBL 안에서 읽을 낱말이 없다**. 런타임의 `ticket`·`/ibl/recover`·`completion_channel`(취소)은 표면이 한 곳도 쓰지 않고, mode 버튼은 성공 결과를 그리지 않는다.
**책임 범위**: 수명이 다른 셋을 하나로 섞지 않는다 — **목표**(`self:goal`, 라운드를 거듭하는 의지), **작업**(task/job, 한 실행), **티켓**(HTTP 연결 복구, 전송 계층). 공통으로 두는 것은 **관찰·제어 계약**이며, 기존 실행기(위임 task·script job·guestpc·시트 엔진·스캔 스레드)는 그 계약의 **어댑터 뒤**에 남는다.
**설치**: (a) 접수증 통화 1종 — 위임 접수증 모양을 채택(`task_ref·state·progress·result_ref`), 모든 긴 작업의 반환. (b) **IBL에서 접수증을 기다려 값으로 잇는 낱말** — 관용구가 `$r = [self:task]{op:"wait", ref:$receipt.task_ref, timeout}` 뒤 `$r.result`를 다음 연산에 넘길 수 있어야 한다. **화면 진행률만 생기면 조합의 공백은 그대로다** — 이것이 1순위. 이름은 판정(`self:goal status`·`self:script status`·위임 GET을 접는 것이 먼저). (c) 상태 어휘를 가른다: `cancel_requested`≠`cancelled`, `timeout`(대기자의 사정, 작업은 계속)≠`failed`(작업의 사정), 재접속(`ticket`으로 같은 결과 회수)≠재실행(새 task). (d) 표면 `await:` 선언 — 접수증이면 진행률·취소·완료 시 재조회, mode 버튼 결과 렌더.
**전환**: 신문 상태 JSON·사진 `scan/progress`·PC 동기 스캔을 어댑터로 감싸 접수증을 돌려주게 한다(엔진 코드는 유지). 회원 앱 `/m/run` NDJSON은 같은 상태 투영을 스트림으로 내는 소비자로.
**완료 조건**: 신문·사진·PC·노트북·강의 비디오·매니저 command가 같은 접수증을 반환하고 한 관용구가 그중 둘을 기다려 결과를 합쳐 다음 낱말에 넘기는 시험 통과 · 취소 요청 후 `cancelled`까지 상태 전이가 기록되고 대기 초과가 실패로 바뀌지 않음 · 표면 폴링 코드(`setInterval`·`scan/progress`) 삭제.

### ④ 구독·주기 (뷰 어휘 개정 · 판정)
**없는 것**: 두 렌더러 모두 `setInterval` 0, 푸시 구독 0. 상주 `channel_poller`와 웹소켓 라우터가 표면에 닿지 않는다. 메신저 새 메시지, 유튜브 재생 상태, 멀티채팅 스트리밍, 라디오·CCTV 상태.
**책임 범위**: 표면이 "언제 다시 묻는가·무엇을 받는가"만. 채널의 생산(`channel_poller`·웹소켓)은 그대로.
**설치**: 뷰 이벤트 `tick:{every}`(주기 재조회), `push:{channel}`(서버 이벤트 수신, 페이로드는 ①의 `$event`). ③의 진행 수신과 같은 배관.
**전환**: 유튜브뮤직 override의 4초 폴링·메신저 수동 새로고침·매니저 DB 폴링을 선언으로 바꾸고 React 폴링 코드 삭제. 원격 렌더러도 같은 두 이벤트.
**완료 조건**: 매니페스트 메신저가 새 메시지를 재조회 없이 받는 시험 · 유튜브뮤직 override 제거 · 두 표면 파리티 가드 통과 · 열려 있지 않은 계기는 구독이 해제됨(누수 0).

### ⑤ 미디어·파일 — 공통 핸들과 접근 규칙, 제공자는 종류별로 (통화 개정 · 판정)
**없는 것**: 앱이 패키지별 URL(`/music` `/yt` `/photo` `/nas` `/showcase` `/lectures`)과 **서버 절대경로**를 알아야 한다. 렌더러는 `BACKEND_MEDIA_ROUTES` 화이트리스트를 손으로 관리. 업로드는 `/launcher/upload`가 절대경로 문자열을 돌려주는 1파일 통로, 폼 `images/files`는 데스크탑 전용.
**책임 범위**: 앱이 알아야 할 **계약**을 하나로 — 통화에 미디어 핸들 1종(`{$blob: handle, mime, bytes?, range?}`)과 접근 규칙(주체·만료). **내부 제공 방식은 하나로 접지 않는다** — 일반 파일(Range), 변환 중 영상(진행 상태 있는 제공), HLS(재생목록+조각)는 제공자가 다르다. 핸들 해소기가 종류별 제공자로 보낸다.
**전환**: 각 패키지 핸들러가 URL 리터럴 대신 핸들을 반환 → 렌더러 화이트리스트 삭제 → 기존 라우터는 제공자 구현으로 재배치(URL 공개 노출만 사라짐). 업로드는 같은 핸들의 역방향(폼 필드·다중·원격).
**완료 조건**: 매니페스트 사진·음악 앱이 패키지 URL 없이 재생·표시 · 화이트리스트 코드 삭제 · 원격에서 폼 파일 업로드 동작 · 쇼케이스 공개 Worker 경로는 핸들 해소를 거쳐도 기존 대역폭·Range 동작 유지.

### ⑥ 표면 지시 (봉투 필드 정식화 · 소형)
`play_in_client`·`stop_in_client`·`download_in_client`·`pc_only`·`stream:true`·`[MAP:]`·`[STREAM:]`을 렌더러 3곳이 각자 덕타이핑.
**책임 범위**: 액션이 "이 결과를 어디서 어떻게 재생·저장·열어라"를 봉투로 말하고 렌더러가 해석. 주체(②)와 분리 — `is_web_surface()`가 답하던 "어디서 재생되나"는 여기 속한다.
**설치**: 봉투 `surface: {play|stop|open|download|share|stream}` + 대상 핸들(⑤). ⑤와 같이 간다.
**전환**: 라디오·유튜브·창고 핸들러의 매직 필드 → 봉투 필드; 렌더러 3곳의 덕타이핑을 공용 코어 한 곳으로. 채팅 텍스트 태그 `[MAP:]`·`[STREAM:]`은 채팅 렌더러가 같은 봉투 필드를 읽는 소비자로 바꾸고 태그는 호환 입력으로 당분간 유지.
**완료 조건**: 매직 필드 문자열이 렌더러에서 사라지고 공용 코어 한 곳만 `surface`를 해석 · 라디오 재생/정지가 데스크탑·원격·포털 세 표면에서 같은 선언으로 동작.

### ⑦ 선택·순서·페이지·표면 상태 (뷰 어휘 개정 · 판정)
다중선택→일괄 액션(사진 저장·창고 이동), 순서 바꾸기(강의 슬라이드·재생 큐), cursor 소비(`self:record query`에 있는데 렌더러 소비 0; 업무기록·메신저·멀티채팅), 표면 로컬 상태(드릴 경로·초안·마지막 입력 — 데스크탑은 모드 전환 시 리셋, 원격은 입력값만 localStorage). **설치**: 이벤트 `select`(다중)·`reorder`, 뷰 공통 `page:`(next_cursor 자동 소비), `state:` 선언(영속은 명시 IBL 쓰기). ①의 `$event`·`$state` 이름 공간이 그릇. **완료**: 사진 전용창의 선택-저장, 강의 reorder가 매니페스트로.

### ⑧ 뷰 낱말 — 승격 4기준을 이미 충족하는 것만 (뷰 어휘 개정 · 판정)
| 낱말 | 은퇴시킬 escape | 비고 |
| --- | --- | --- |
| `tree`(파인더) | 폴더 창·공유창고·PC 탐색·NAS Finder·빈노트 폴더·강의 재료 — 6개 | recursive 드릴은 back 스택이 없어 대체 불가 |
| `grid`(정렬 표)·`chart` | PC 분석(treemap·scatter·timeline)·투자 | `blocks.table`은 정적, `table:chart`는 파일 effect |
| map `map_click`·`layers` | 데스크탑 지도 escape | 저장 별+검색+경로+CCTV 동시 |
| `video`(HLS) | `StreamPlayer`·`stream:true` 플래그 | 호스트명 하드코딩 판정 제거 |
| 다화자 `thread`+첨부·카메라 입력창 | 멀티채팅·팀채팅·빈노트 AI 패널 | ④와 함께 |
정당한 escape로 남는 것: 슬라이드 캔버스·오버레이 좌표 편집(engine 어댑터로 흡수 가능), 녹음 스튜디오, 창 간 네이티브 드래그, webview.
**책임 범위**: 데이터·상호작용 계약만(승격 기준 ④). 레이아웃·스타일을 선언하기 시작하면 정지.
**전환**: 낱말 하나당 지정된 escape를 매니페스트로 다시 쓰고 **같은 커밋에서** 그 escape를 삭제한다(공존 금지 — escape가 남으면 낱말이 안 쓰인다). 렌더러 2곳·검증기·문서 2줄 동시 갱신(뷰-어휘 가드).
**완료 조건**: 표의 escape 전부 삭제 · 폴더 창·창고·PC 탐색·NAS가 `tree` 하나로 서고 back 스택이 동작 · 원격·폰 렌더러 파리티 가드 통과.

### ⑨ 위임의 실행 범위 지정 — 소형이 아니다 (위임 계약 개정 · 판정) — **1차 집행 2026-10-05 밤**
**집행(1차)**: `[others:delegate]{…, role, allowed, context}` — 봉투(`delegation_tasks.envelope`)가 `allowed` 를 **부모 집합 ∩ 요청**으로만 만들고(무제한 부모면 요청 그대로, agents.yaml 과 같은 해석이라 표준 코어 포함; 부모 밖 노드는 잘라 `allowed_clamped` 로 알림), 요청이 없으면 부모 집합을 **상속**한다. 수신(`received`)이 처리 동안 스레드 `allowed_nodes` 를 세워 실행 관문(판본 1·2)과 프롬프트 어휘 스코핑이 같은 집합을 읽고, 그 턴의 재위임은 자동으로 그 집합 안에 갇힌다. `role` 은 시스템 AI 위임의 `force_role`(프롬프트 조립 선택; 프로젝트 에이전트는 자기 역할 고정이라 봉투에만 남음), `context` 는 메시지에 JSON 블록으로 동봉(64KB 상한)+봉투 보존. 세 scope 모두 같은 봉투. **첫 소비자 판정(구현자)**: `/forage/chat` 을 `[others:delegate]{scope:system, mode:sync}` 로 바꾸지 **않았다** — 시스템 AI 러너는 한 번에 한 메시지라 검색이 긴 보고서 뒤에 줄을 선다(실측 구조: `_check_internal_messages` 순차 pop). 대신 라우트가 **같은 봉투 계약**(`delegation_tasks.scoped(role="forage", allowed=["sense"], context=사냥판)`) 위의 얇은 통로가 됐다 — 좁힘·상속·집행이 위임과 한 벌(②의 HTTP 얇은 통로와 같은 모양). 부수 변화: 옛 `{sense,self,table}` 손수 집합에서 표준 코어 해석으로 `others` 가 포함된다(프롬프트 몇 줄). 회귀 `test_delegation_tasks::test_allowed_narrows_only_and_inherits / test_same_scope_delegate_carries_role_allowed_context / test_execution_rejects_nodes_outside_allowed_set / test_forage_route_is_thin_passage_over_delegation_scope`. **남은 것**: 빈노트 `/system-ai/chat`·강의 `slide_ai`·문서 `generate_selection` 의 같은 통로 전환(세 앱 재구성 때), `allowed` 를 액션 단위(노드:액션)로 좁히는 문법은 쓰임이 생기면.
**없는 것**: `delegate{scope:system, mode:sync}`는 열렸으나 역할·허용 노드·구조화 맥락을 줄 수 없다. 검색브라우저 `/forage/chat`(`force_role`, `allowed_set=sense+self+table`, 사냥판 스냅샷), 빈노트 `/system-ai/chat`, 강의 `slide_ai`, 문서 `generate_selection`.
**책임 범위**: `allowed`는 **부모 권한을 좁히기만** 하고(②의 narrow 규칙과 같은 방향) 하위 위임에 **상속**된다. `role`은 프롬프트 조립 선택, `context`는 구조화 입력(①의 inputs로 전달). **모든 AI 호출을 전체 인지 파이프라인에 올리지 않는다** — 선택 문장 교정 같은 제한 변환은 `table:ai`가 맡고(시간·토큰), 도구가 필요한 작업만 위임 경로. 둘이 **같은 호출·결과 계약**(③의 접수증, 결과 참조)을 갖는 것이 목표이지 하나로 합치는 것이 아니다.
**완료**: 검색브라우저 `/forage/chat`이 `delegate{role:"forage", allowed:[sense,self,table], context:$hunt}`로 대체되고 허용 집합 밖 낱말 호출이 거절되는 시험 · 하위 위임이 부모 `allowed`를 넓히지 못함.

### ⑩ 몸의 명사 생애주기 어휘 (어휘 추가 · 판정 불요, ② 뒤) — **집행 2026-10-05 밤(사용자: 전부 진행, 판정은 구현자 추천)**
**집행**: 새 낱말 7 — `self:project`·`self:folder`·`self:trash`(프로젝트·폴더·스위치·채팅방 공통 휴지통)·`others:chat_room`·`others:warehouse`(이웃 창고 피드)·`self:warehouse`(내 창고 관리)·`others:channel`(채널 설정·폴러)·`self:media`(탐침·변환·HLS·자막) / 기존 낱말 op 확장 3 — `others:agents`(create·update·delete·start·stop·role·note; 주 키 op, agent_id 호환)·`self:switch`(info·create·update·rename·copy·trash·delete + run 은 ③ 접수증으로 수리 — 옛 run 은 없는 생성자·메서드를 불러 AttributeError)·`limbs:launch`(ops 블록 open_ui/list/add/remove, 주 키 op·옛 action 별칭). **구현 원칙**: 조종실 라우트와 **같은 서비스 함수** 한 벌 — 라우트 본문에만 살던 논리를 서비스로 내렸다(`services/launcher_ops`·`cognition/agent_lifecycle`·`services/chat_room_ops`·`services/warehouse_ops`(좋아요·리트윗·허용 창고 필터)·`services/warehouse_admin`(내 창고, 경로 규칙 `base/warehouse_paths`)·`services/channel_settings_ops`(gmail config.yaml·폴러 새로고침 포함)·`services/media_ops`(ffprobe 캐시·내장 자막)) 그리고 라우트(api_agents·api_switches·api_warehouse_feed·portal_admin·api_business·api_nas)가 그 함수를 부른다. 라우터(ibl_routing)는 이름만 알고 구현은 조립 루트(boot_common)가 능력 주입(서비스층은 인지층이 import 못 함 — 같은 의존 역전). **권한**: 쓰기 op 전부 `requires.principal: owner`; 영구 삭제(project delete·trash empty·agents delete·chat_room delete·switch delete·warehouse purge·forget)와 채널 `set` 은 `human_confirm`. 프로젝트·휴지통·내 창고·채널은 읽기도 주인 전용. **판정 기록(구현자)**: ⓐ프로젝트/폴더/휴지통을 한 낱말에 op 로 우겨넣지 않았다(한 단어=한 개념) — 단 휴지통은 세 저장소의 합집합이라 하나. ⓑ내 창고와 이웃 창고는 노드가 다르다(self/others)는 이유로 두 낱말. ⓒ채널 설정은 `channel_read/send` 에 op 를 얹지 않고 `others:channel`(설정은 다른 개념) — 셋을 하나로 합치는 rename 은 비용이 커서 보류. ⓓcalendar update/toggle/run_now 는 어휘에 이미 있어 **뷰 바인딩(렌더러)만** 남음 → 실기기 묶음(③ 3차·⑦)으로. ⓔ즐겨찾기 앱 블록의 add/delete 버튼도 뷰 작업이라 같은 묶음. ⓕ`[others:agents]` 의 start/stop 은 러너 명부(agent_registry.agent_runners) 한 곳을 조종실과 공유. **교훈**: agent 이름 변경 때 옛 라우트는 role 을 함께 줄 때만 파일을 옮겨 고아 역할 파일이 남았다 — 서비스는 이름이 바뀌면 role·note 파일을 따라 옮긴다. 회귀 `backend/test_lifecycle_vocab_2026_10_05.py`(9건: 런처 항목·관문·스위치 접수증·에이전트·채팅방·창고 둘·채널·미디어(ffmpeg 있을 때)·즐겨찾기 별칭). 해마 용례 28건(`scripts/seed_body_lifecycle_examples.py`, 멱등). 가이드 `data/guides/body_lifecycle.md`. 성능 미측정.
에이전트·프로젝트·폴더·휴지통(매니저·폴더 창), 채팅방(멀티채팅), 스위치 CRUD, 즐겨찾기 add/remove 노출, calendar update/toggle, 창고 feed·like·poll·레벨, 채널 설정, 미디어 probe·transcode·자막. 공백이 아니라 op·낱말 추가지만 ②의 `requires` 없이는 매니저·설정이 여전히 REST다.

## 2 설치가 아닌 수리 (판정 불요 · **기반 완료를 기다리지 않는다**)
낱말이 있는데 REST·코드로 다시 짠 곳 — 신문 `issue()`→`[engines:newspaper]{wait:true}`, 강의 REST 18개→`self:lecture/slide/material/deck`, 창고 이웃 3종→`[others:neighbor]`, 매니저 agents/command→`others:agents/delegate`, PC list/analyze→`self:list/storage`, 사진 save/open→`self:copy/limbs:os_open`, 스위치→`self:switch`, 주행기록·트레이스 창→`self:body trajectory`, 헬퍼 중복 `runIBL` 2곳→`iblExecuteApp`. 값 전달이 ①에 걸리는 것(객체 인자)만 ① 뒤로 미루고 나머지는 지금 한다. 죽은 코드(`api-business.ts` 31메서드, `api_gmail.py`, `gen_newspaper.py`×2, scheduler tasks 래퍼, 원격 `CUSTOM_RENDERERS`) 삭제는 파괴적이라 판정. 상세는 감사 §2.

## 3 설치가 아닌 가꾸기 — 선별 기준
33개 선언형 앱 중 31개가 호스트 액션 1개만 참조한다. **그 자체가 잘못은 아니다** — 음악 앱이 음악 낱말을 주로 쓰는 것은 자연스럽고, 분해하면 권한·트랜잭션·성능을 잃는 op도 있다. 관용구로 옮길 대상의 기준은 (a) **여러 앱에서 반복되는 절차**인가, (b) **기존 부품으로 같은 보장(원자성·권한·실패 증거)을 유지하며** 표현되는가 — 사용 빈도 하나로 정하지 않는다([no-switchization-by-usage]). 관용구 수·REST 감소는 성과가 아니다. 성과 기준은 **기존 공통 능력을 중복 구현하지 않고, 새 능력이 공통 계약(①값 전달·②권한·③접수증·⑤핸들)을 통해 조합되는가**다. 새 엔진에는 콜백 경로가, 새 도메인에는 전용 저장소가 있을 수 있다 — 경로·저장소 개수는 보조 지표다.

## 4 판정 요청 (언어 개정·파괴적 변경만)
①②③④⑤⑦⑧⑨의 신설·개정, ⑥은 설계 확인, §2 죽은 코드 삭제. 순서 ① → ② → ③+④ → ⑤+⑥ → ⑦+⑧ → ⑨ → ⑩. 각 항목은 자기 **완료 조건**으로 닫히며, 측정하지 않은 성능 개선은 주장하지 않는다.
