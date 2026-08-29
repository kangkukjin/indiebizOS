---
title: 시스템 아키텍처
scope: 설계 의도, 신체 구조 비유, 인지 파이프라인 큰 그림, 핵심 컴포넌트 개요
owner_code: 전체 backend/ (개념 수준)
last_updated: 2026-08-28
see_also: [system_structure.md, memory.md, ibl.md, packages.md, technical.md]
---

# IndieBiz OS 아키텍처

## 정의

IndieBiz OS는 AI에게 지능적인 몸을 만들어주는 하네스(harness)다. AI의 본질적 가치는 **연결** — 사람과 세계를, 사람과 사람을, 알고 있는 것과 아직 모르는 것을 잇는 것.

하네스는 에이전틱 루프와 다르다. 에이전틱 루프는 AI의 처리량(throughput)을 올린다 — 도구를 더 많이 호출. 하네스는 AI의 판단력(intelligence)을 올린다 — 같은 모델이라도 하네스에 따라 결과의 질이 달라진다.

## 신체 구조 (생명체 메타포)

| 신체 시스템 | IndieBiz OS 구현 | 역할 |
|------------|------------------|------|
| 신경계 | IBL (6노드 — 액션 수는 아래 '시스템 통계', 빌드 파생) | 감각/행동의 상시 연결 |
| 감각기관 전처리 | 감각 전처리 (postprocess) | 원시 정보를 압축하여 뇌에 전달 |
| 선택적 주의력 | 의식 에이전트 | 매 턴 메타 판단 — 문제 정의, 초점, 달성 기준 |
| 반사 신경 | 경량 AI (분류) | EXECUTE/THINK 분류 — 의식 각성(THINK)은 **장기 작업 또는 위험 작업**일 때만(2026-08-10 기준 상향), 그 외 전부 의식 건너뜀 |
| 자기 교정 | 평가 에이전트 | 달성 기준 대비 평가, NOT_ACHIEVED 시 재시도 |
| 자의식/각성 | World Pulse | 매시간 세계/사용자/자기 상태 수집 |
| 면역계 | 일일 건강 점검 + action_health | 매일 1회 fixture·골든 검사(**AI 0** — 옛 'AI가 assumed 액션을 순찰'하던 배선은 은퇴), 모든 액션 실행을 자동 기록 |
| 자율신경계 | 스케줄러, 이벤트 엔진 | 의식 없이 돌아가는 리듬 |
| 해마 | 실행기억 (해마 + discover) | 1회 생성, 전 에이전트 공유. fine-tuned 임베딩으로 관련 기억 자동 인출 |
| 에피소딕 메모리 | episode_log + episode_summary | 에피소드(명령→응답)별 실행 로그 기록, 인지 품질 지표 영구 추적 |

## 인지 파이프라인 (연상 → Reflex/무의식 → 의식 → 실행 → 평가)

```
사용자 메시지
    ↓
[0] 연상 단계 (해마 + 심층메모리, 단일 검색)
     → (xml, top_score, top_code)
    ↓
[1] Reflex 분기 (호출 측 결정)
    ├─ top_score ≥ 0.85 → EXECUTE + reflex_hint (무의식 스킵)
    └─ 미만 → [1B] 무의식 (경량 AI) → EXECUTE/THINK
    ↓                                              ↓ THINK ( = framing 수요)
EXECUTE/Reflex                          [2] framing 재고 확인 → 있고 맞으면 재사용(의식 스킵)
    │                                      없음/안맞음 → 의식 에이전트(본격 AI): task_framing + 달성 기준
    ↓                                              ↓
[3] 실행 에이전트
    모델은 **모델 기어**가 결정 (model_resolver: 역할→축→기어→티어).
    Reflex(해마 고확신)는 'reflex' 축(균형 기어 기본=중급), EXECUTE·THINK는 'execute'·'consciousness' 축.
    (자동 변속기[무의식 분류기]가 작업마다 티어를 고르고, 수동 레버[절약/균형/최대]가 전체를 변속.
     상세: system_structure.md "모델 기어")
    ↓
[4a] THINK → GoalEval (경량 AI, 달성 기준 있을 때만, 최대 3라운드)
     EXECUTE → GoalEval 없음; 실패·복잡 궤적·세계 변경이면 SelfReflect 1회
    ↓
[5] 증류 (해마 경험 증류 + 심층메모리 증류)
```

- **연상기억**: 파이프라인 최상단에서 1회 생성. 해마(과거 IBL 사례)와 심층메모리(사용자 사실)를 합친 self-describing XML 묶음 (`<execution_memory>` + `<related_memory>`)
- **단일 검색**: 검색 1회로 top_score까지 확보 (이전 3회 중복 호출 제거, 2026-05-17)
- **해마**: 베이스 `ko-sroberta-multitask`에서 fine-tuning. **실제 런타임 검색 ~99%** (라이브 세대·측정표는 memory.md '현재 라이브 모델' — 재학습은 **로컬 M4 Pro**가 정본 경로, 클라우드는 옛 맥에어 OOM 한정이었다). 모델은 런타임 천장이라 재학습 거의 무차별 — 어휘 아닌 intent 의미를 매칭해 vocab에 강건. 절차·함정은 `data/guides/hippocampus_retraining.md`.
- **심층메모리**: 같은 fine-tuned 모델로 시맨틱 검색 (2026-05-16 도입)
- **점수 정규화**: 모든 검색 경로(시맨틱·하이브리드·FTS5 폴백)에서 0~1 보장
- **두 검증 갈래**: GoalEval은 `consciousness_output`과 그 안의 달성 기준이 있는 `THINK`에서만 돈다. `EXECUTE`는 평가값을 만들지 않고, 도구 호출에 실패 신호·복잡성·세계 변경이 있을 때 실행기 자신이 같은 세션으로 SelfReflect한다. 그러므로 `episode_summary.evaluation_result=NULL`은 미달성이 아니라 **평가 미실행**일 수 있다. Reflex·강제 역할은 SelfReflect도 생략한다.
- 상세: `data/system_docs/memory.md`

## 사용자 표면 — 런처의 세 모드 (트릴레마)

위 인지 파이프라인은 **자율주행** 모드의 내부다. 같은 IBL 신경계 위에 사용자가 직접 모는 세 표면이 있고, 각각 {속도·표현력·주권} 중 둘을 갖고 하나를 내준다.

| 모드 | 무엇 | 비용 | 큐레이션 |
|------|------|------|----------|
| 자율주행 | 의도 → 플래그십 AI가 다단계 처리 (위 파이프라인). 구 '프로젝트' | 비쌈(Opus급) | AI |
| 조종실 (구 '수동'→'계기판', 2026-07-03 개명) | 경량 모델이 자연어→IBL 번역(해마 기반) → 효과 dry-run 검수 → 실행 → (승인 시) 해마 증류. 컴파일러 프론트엔드: 모델은 번역만, 지능은 IBL 어휘에 누적. 여기에 시스템 상태·모델 기어 레버·프레즌스·주행기록이 모여 **자율주행을 포함한 전체를 감독·개입하는 조종실**로 승격(내부 탭 키는 `manual` 유지) | 거의 0 | 인간+언어 |
| 앱 | 결정화된 sense 호출을 아이콘/GUI로 직접 조작 (부동산 실거래가·상권, 도서검색). 구 '액션' | 0(코드 실행) | 결정화된 워크플로 |

**생애주기**: 새 일은 자율주행이 탐색 → IBL 흔적이 조종실 초안으로 → 검증된 고빈도 워크플로가 앱으로 결정화. *굳히는 건 증명된 것만.*

★**결정화는 절반이다 — 가이드가 통로를 지정해야 실제로 쓰인다**(2026-08-28 실측). 같은 세 일간 보고서의 셸 사용이 0/5/13회로 갈렸는데 셸 몫은 세 편 모두 같은 부류(JSON 원장 갱신·md→HTML 변환)였다. 원인은 능력이 아니라 통로 지정이었다 — "셸은 IBL 등가물이 없는 일에만" 조항을 둔 편만 0회였고, 조항 없는 두 편은 이미 등록돼 있는 스크립트를 놔두고 매 호 히어독을 새로 썼다. 같은 부류가 계기 쪽에서도 나왔다: `criteria` 품질 계약이 살아 있는데 세 보고서 주행에서 한 번도 불리지 않았다. **등록·출하만으로는 부족하고, 정본 가이드가 그 통로를 명시해야 한다**(반대로 가이드에 구체 IBL 문장을 적는 것은 금지 — 원리·낱말 이름·경계만. 좋은 조합의 정본 통로는 해마다).

- 조종실: `backend/surface/api_ibl.py` (`/ibl/translate`·`/ibl/validate`(dry-run)·`/ibl/execute`·`/ibl/distill`) + `frontend/src/components/ManualMode.tsx`. 부작용 step은 명시적 확인 게이팅, 해마 증류는 사용자 승인 시에만.
- 앱: **선언 기반 단일소스**. 각 계기는 IBL 액션의 `app:` 블록(`data/ibl_nodes_src/`)이고 `/launcher/instruments`로 자동 파생 → **데스크탑(`GenericInstrument.tsx`)·원격 런처·폰이 같은 선언을 같은 어휘로 렌더**(app 블록 1개 = 전 표면 동시 등장). 어휘: modes 탭, view 프리미티브 12종(metric/kv/kv_list/card_list+드릴/image_grid/sparkline/list_action/thread/form/editable_list/map(인터랙티브 leaflet)/calendar), `on:` 뷰-이벤트(지도 moveend→재조회·marker_click→IBL 액션 또는 `{stream:true}`→HLS 영상), filter 필터칩(정적 단일선택 재조회 + 동적 `from_field`=결과-필드 distinct 칩, 클라이언트 측 거르기), 표시 템플릿 `{path|filter}`. 0토큰 IBL 직접 실행. escape hatch 2층: OVERRIDES(photo 풍부창·네이티브 창 등 손제작 풍부판) + STATIC_DOMAINS(부동산 실거래가·길찾기 등 렌더 어휘 밖 — 2026-06-29 상권은 인터랙티브 map+동적필터+드릴로 흡수돼 은퇴). `build_ibl_nodes --check`에 app 블록 정합성 합류.
- `_raw: true` 파라미터는 `postprocess:compress`(액션 결과의 AI 요약)를 우회한다 — 다만 **현재 그 블록을 선언한 액션은 0개**다(2026-06-27, 검색계가 `records`/`items` 구조화 통화로 옮겨가며 compress 폐지 — 압축이 통화를 문자열로 파괴하던 결함). 엔진의 기계는 남아 있고 선언만 비었다.

## 시스템 구조
디렉토리 트리는 **system_structure.md** 참조 (의식·실행·평가 에이전트의 시스템 프롬프트에 자동 주입되는 정전 문서).

### 백엔드 층 구조 (2026-08-05 물리 이동)

backend 는 평면 폴더가 아니라 **층=디렉토리**다. 의존은 아래→위 **한 방향만** 흐른다:

```
base → datastore → ibl → cognition → services → surface
```
(층별 모듈 수는 아래 '시스템 통계'의 빌드 파생 구간 — 산문에 적으면 다음 커밋에 낡는다.)

- **왜 층인가**: 모듈이 평면으로 쌓이면(이동 당시 195개) "누가 누구를 부르는가"가 사람 머릿속에만 남는다. 층은 그 규율을 **디렉토리 위치로 강제**한다 — 물리 위치가 곧 선언이고, 어긴 파일은 `git mv` 하거나 `LAYERS` 를 고쳐야 한다.
- **가드**: `scripts/check_backend_layers.py` — 층 미배정 모듈·역방향 간선·교차층 순환을 잡는다. 동결 부채 `BASELINE` 7간선(전부 한 방향 상향 읽기, 순환 0)은 **신규 추가 금지**이고, 위반이 사라지면 가드가 목록에서 지우라고 요구한다. pre-commit + 일일 건강 점검 양쪽에 합류.
- **모듈 이름은 평면 유지**(`import ibl_engine`) — `backend/boot_paths.py` 가 층 경로를 `sys.path` 에 얹는다. 그래서 이동이 import 를 깨지 않았고, **그래서 조용히 낡을 수 있다**(코드베이스 지도가 반년 가까이 평면 구조를 그리고 있었다).
- **새 backend 모듈 규약**: 층 폴더에 두고 `LAYERS` 에 배정 · 스크립트는 맨 위에 `import boot_paths`.
- ★층 가드가 실제로 잡은 것: `ibl_routing`(ibl 층)이 `api_pcmanager`·`api_photo`(surface 층)를 직접 부르던 역전 → 창 열기 pending-queue 를 `backend/base/window_requests.py` 단일 저장소로 **의존 역전**해 해소. 층은 장식이 아니라 설계 압력이다.

## 핵심 컴포넌트

### 통합 AI 아키텍처 (6-Node + 쉘)
시스템 AI와 프로젝트 에이전트가 **동일한 `AIAgent` 코어(ai_agent.py) + 동일한 최상위 도구 7개**를 공유. `_is_system_ai` 플래그가 IBL 접근 노드 범위만 분리 (시스템 AI: 전체 노드, 프로젝트: 허용 노드).

**최상위 도구 7개**: `execute_ibl` / `run_command` / `todo_write` / `ask_user_question` / `enter_plan_mode` / `exit_plan_mode` / `read_guide`.
- 코드 실행은 **write→run 패턴**: 멀티라인은 `[self:write]`로 파일에 쓴 뒤 `run_command`로 실행, 한 줄은 `run_command "python3 -c '...'"`. 별도 Python/Node.js 실행기 도구는 없다 (이스케이프 충돌과 traceback 손실을 피하기 위해 제거됨).
- 인지 도구(todo/ask/plan)는 IBL 경유 불가(파라미터 구조 불일치)하여 별도 최상위. 상세 도구 schema는 `tool_loader.build_execute_ibl_tool()` 등 참조.

IBL 노드/액션 정의는 **ibl.md** 참조. 프로바이더는 **technical.md** 참조.

### 프롬프트 빌더 (prompt_builder.py)
시스템 AI와 프로젝트 에이전트 모두 동일한 프롬프트 구조 사용:

```
┌─────────────────────────────────────────┐
│     공통 설정 (base_prompt_v2.md)        │
│   - AI 행동 원칙, 도구 사용 가이드       │
├─────────────────────────────────────────┤
│      IBL 환경 (ibl_access.py)           │
│   - 사용 가능한 노드/액션 목록           │
│   - IBL 문법 가이드                     │
│   - 시스템 AI: 6개 노드 전체            │
│   - 에이전트: 허용된 노드만             │
├─────────────────────────────────────────┤
│       조건부 프래그먼트 (fragments/)     │
│   - 06_git.md: git_enabled=true일 때    │
│   - 09_delegation.md: 에이전트 2개+     │
│   - 10_system_ai_delegation.md          │
├─────────────────────────────────────────┤
│            개별 역할 프롬프트            │
│   - 시스템 AI: system_ai_role.txt       │
│   - 에이전트: agents.yaml의 role        │
├─────────────────────────────────────────┤
│         IBL 용례 RAG 참조 (동적 주입)    │
│   - 유사 과거 용례 XML 블록              │
│   - 사용자 메시지 수신 시 1회 주입        │
├─────────────────────────────────────────┤
│           컨텍스트 (동적 주입)           │
│   - 사용자 프로필, 시스템 상태 등        │
└─────────────────────────────────────────┘
```

### 프롬프트 XML 구조 / AI 프로바이더
모든 프롬프트의 XML 태그 구조와 지원 AI 프로바이더 목록은 **technical.md** 참조.
프로바이더는 모두 실시간 스트리밍 지원 (`process_message_stream()`, 이벤트: `text`/`tool_start`/`tool_result`/`thinking`/`final`/`error`).

### 위임 체인 시스템 (Delegation Chain)
에이전트 간 협업을 위한 핵심 메커니즘. 두 가지 위임 방식이 있고, 그 위에 **행위자 봉투**가 흐른다(상세=communication.md):

**1. 동기/비동기 위임** (기존)
- `[others:delegate]`/`[others:delegate]{scope: "cross"}`를 통해 작업을 위임하고 결과를 자동으로 보고받음
- 순차 위임: `completed[]` 사이클 병합으로 이전 결과 보존
- 병렬 위임: EXCLUSIVE 트랜잭션 내 원자적 `responses[]` 추가로 race condition 방지
- 시스템 AI 위임: 3-레이어 감지 (도구명 / IBL 결과 / DB pending)

**2. 스케줄 기반 위임** (Phase 27)
- 에이전트 소유 스케줄: 모든 스케줄 이벤트에 `owner_project_id`/`owner_agent_id` 부여
- 크로스 위임: `target_project_id`/`target_agent_id` 지정 시 대상 에이전트 소유로 등록
- `calendar_manager.py`가 실행 시 소유 에이전트의 컨텍스트로 파이프라인 실행

**행위자 3칸 봉투 (2026-08-21)** — 위임은 사람이 아니라 다른 실행 주체가 몸을 쓰는 자리라, 누가·무슨 과제로·어디서 왔는지가 따라다녀야 한다.
- `thread_context` 가 `agent` / `task` / `origin` 세 칸을 스레드 경계 너머로 전파하고, `/ibl/execute` 는 요청 봉투(env·헤더)에서 이를 받는다(포털 경유는 `origin='portal'`).
- 무태스크 위임(스케줄러 하달·앱 버튼의 `[others:delegate]{scope:"system"}`)에는 러너가 태스크를 발급한다 — 그래야 그 런의 쓰기가 **3중 조인**(`write_ledger` → `episode_log` → `tasks`)에 닫힌다.
- 회상 어휘는 `[self:body]{op:"writes"}`(쓰기 관문 원장) + `{op:"changes"|"log"|"file"}`(git 원장).

**몸 대 몸은 위임이 아니다**: 이웃 *몸*에게 능력을 부탁하는 건 `[others:ask]`(자연어 → 상대 사전으로 컴파일 → 실행 → 통화 회신). 몸 사이 전용 특권 배관은 두지 않는다.

### IBL (IndieBiz Logic) 시스템
- 노드 기반 추상화: `[node:action]{params}` 문법
- execute_ibl + 범용 도구 + 인지 도구 (총 7개 최상위 도구 — 셸이 없는 몸(폰)에만 `execute_python` 이 추가로 붙는다)
- **6개 노드** — 총 액션 수·노드별 내역은 아래 '시스템 통계'(빌드 파생) 참조
  - **어휘는 작아지면서 세졌다** — 2026-08-05~17 개념중복 압축으로 163→144. 표준 수술 세 가지:
    ①**복합어를 지우고 보편어를 세운다**(`sense:pew_research`→`[sense:feed]{url}` — 사전은 −1+1 인데 차원은 늘고 중복 파서도 수렴)
    ②**같은 개념의 낱말을 축으로 접는다**(검색 5액션→`[sense:search]{source}` · 사업 4형제→`[self:ledger]{store, op}` · 연락처→`[others:neighbor]{op:"contact_*"}` · 라디오 재생제어→`[limbs:radio]{op}`)
    ③**절차는 낱말이 아니라 문장이다** — 오케스트레이션뿐인 것은 `[self:script]`(등록 스크립트)나 앱 인스턴스로 얼린다. "새 낱말 만들까?"의 기본 답이 "스크립트로 등록"인 것이 **반-어휘-증식 장치**다.
  - ★**계수만으로 생사를 판정하지 말 것**(2026-08-15 실측): `sense:search_local` 은 호출 계수 19였지만 결과를 낸 적이 없었다(후계 3건 vs 은퇴어 0건). 계수는 "호출됐다"이지 "쓸모 있었다"가 아니다 — **판별법은 핸들러를 열어 대체 경로를 실측하는 것**.
- **문장이 프로그램급으로 올라갔다 (2026-08-22, M1~M6)** — 어휘 증가는 `[table:reduce]` 하나뿐이고 나머지는 전부 *문법*이다. 설계 의도: **한 문장 = 한 프로그램**, 단 범용 자료구조·재귀는 `[self:script]` 로 얼린다(언어를 프로그래밍 언어로 키우지 않는다).
  - 술어 언어(`$변수[.경로]`·`count/empty/exists`·`matches`·`and/or/not`·AI 술어) · 제어 블록(`[try][catch][finally]`·`[on_error:]`·`[repeat:]`) · 상태(`$n = $n + 1` 한 줄 식·`while` 이 몸 변수를 봄) · 블록-인-파이프 · `$return` 반환
  - 봉투 다이어트·자동 스필·재개는 **엔진 규약**(언어 밖) — 아래 '감각 피드백' 절.
  - 워크플로우는 **함수 쪽으로 한 칸** 옮겨졌다: 이름·인자(미할당 `$이름`=시그니처, `params_required`/`params_default`)·반환값(`$return`)·스코프 격리·합성(파이프로 다음 문장에 통화를 넘김) + 순환·깊이(5) 가드.
  - **개정은 실제 프로그램이 끌었다**(2026-08-27~28, 여덟 건). 매일 사람이 손으로 돌리던 세 일간 보고서(AI 동향·부동산·유튜브 팁)를 **한 문장 = 한 프로그램**으로 다시 쓰는 실험이 표현 공백을 적발했고, 사용자 판정("언어의 한계는 다 고쳐")으로 일괄 집행했다 — 치환 의미론(통짜 `.path`=원형)·`$변수 >>` 파이프 머리·변환자 `items` 개방·식 문자열 함수, 그리고 괄호형 확장 경로 `${x.items.*.f}`/옵셔널 `?`·`[table:each]{on_error:"keep"}`(실패 행을 `_error` 를 달아 통화로 흘림)·파이프 세그먼트 `if` 불일치=**직전 통화 통과**·document blocks 의 `when` 절. 검증 결과 팁 23문장·동향 24문장·부동산 21문장이 전부 가이드 품질 기준을 충족했다(원문·산출물=`data/_backups/2026-08-28_report_program_experiments/`, 상태=`docs/IBL_REPORT_PROGRAMS_HANDOFF.md`). ★교훈: **언어의 표현 공백은 진짜 프로그램을 써 봐야 드러난다** — 상상훈련이 못 잡는 부류다.
  - **실패는 위치를 갖는다**(2026-08-27): 모든 실패 봉투에 `traceback`(frames 바깥→안쪽·`error_type`·실패 지점 입력 통화 요약·예외 꼬리)이 붙고 — each 행·병렬 가지 같은 부분 실패도 예외 없다 — AI step 의 품질 미달은 `criteria` 품질 계약이 `error_type:"quality"` 로 **위치 있는 실패**로 만든다(판정 불능=통과+`unjudged`, 재시도 통과=`_criteria_retried` 정직 표지). 둘 다 봉투 다이어트 밖. 정본 = `docs/IBL_TRACEBACK_HANDOFF.md` · `docs/IBL_QUALITY_CONTRACT_HANDOFF.md`.
  - 명세·예약어는 **ibl.md**, 교재는 `data/common_prompts/fragments/12_ibl_only.md`, 개정 이력은 `docs/IBL_PROGRAM_GRADE_DESIGN.md`.
- **액션 해석**: 직접 매칭만 사용 (verb 런타임 해석 제거)
- **값 의미론 단일 코어**(2026-08-25): `common/value_semantics.py`가 값 분류(null/bool/number/**datetime**/text/structure/other — datetime 은 2026-08-27 신설), JSON 구조 순회(dict=무순서 쌍·list=순서 열), 조건 동등성, 4상태 순서(작음/같음/큼/판정불능), 숫자 관측, 정렬 버킷(숫자→날짜→문자열→결측), groupby 엄격 식별자와 join/merge/dedup 관계 식별자를 한 벌로 소유한다. `table:filter/sort`·`[if]/[case]/repeat`·선언형 `response.sort`·집계·관계 연산은 의미를 재구현하지 않고 공통 결과를 자기 오류 봉투로 번역만 한다. `test_value_semantics_single_owner.py`가 대칭·추이·동등/순서/정렬 일치와 사적 정책 함수 재도입 금지를 지킨다.
- **프롬프트 가독성**: 액션에 category 태그 부여 → `<action-categories>`로 그룹 표시 (순수 표시용)
- **액션 라우팅**<!-- ROUTERS:START -->(액션 단위 실측, 합 151): handler 122 · system 19 · channel_engine 7 · driver 1 · workflow_engine 1 · trigger_engine 1<!-- ROUTERS:END -->
  - handler: 패키지 `handler.py` / system: 백엔드 내부 함수 직접 / channel_engine·driver: 채널·프로토콜 추상화 / workflow·trigger: 오케스트레이션 엔진
  - (`api_engine` 은 `api_registry.yaml` 실행 엔진 — 라우터 축이 아니라 별도 경로다.)
- `api_registry.yaml`에 `node` 필드 추가 시 자동으로 노드 액션에 병합 — `ibl_nodes.yaml` 편집 불필요
- 에이전트별 접근 제어: `allowed_nodes`로 노드 필터링
- 인프라 노드(`self`, `others`, `table`)는 모든 에이전트에 자동 허용 — 노드 yaml의 `always_on: true` 플래그가 단일 소스 (`ibl_access._always_allowed()`가 레지스트리에서 읽음)
→ 상세 문서: [ibl.md](ibl.md)

### $file:N 파라미터 시스템
IBL 파서 밖에서 코드나 긴 텍스트를 전달하기 위한 메커니즘:
- `execute_ibl`의 `files` 파라미터로 긴 콘텐츠를 별도 전달
- IBL 파라미터에서 `$file:0`, `$file:1` 등으로 참조
- IBL 파서가 파라미터 내부의 코드를 잘못 해석하는 문제 방지
- 코드 블록, 긴 텍스트, 멀티라인 콘텐츠에 적합

### 감각 피드백 (Sensory Feedback) 시스템
파이프라인으로 묶어도 AI가 각 단계의 결과를 전부 볼 수 있어야 한다는 원칙:

**Provider tool result 절삭 정책**
- 기본: 8KB → **16KB**로 확대
- 파이프라인 실행 시: `_action_count × 16KB`로 동적 확장 — 액션 수에 비례하여 결과 보존

**중간 결과 보존 — 원칙의 현행 모양(2026-08-22 봉투 다이어트, M1)**
- `workflow_engine`/`ibl_engine`은 중간 결과를 절삭하지 않고 전부 누적한다(엔진 안쪽은 원형 그대로).
- 바뀐 것은 **에이전트 경계**다: `results[]`는 step 요약(shape·count·bytes·columns·preview, 실패 step은 오류문 원형)으로 접히고 **`final_result` 하나만 원형**으로 나간다. 옛 모양은 `verbose: true`.
  - 원칙은 유지된다("각 단계가 무엇을 냈는지 보인다") — 접힌 것은 *같은 내용의 중복 전송*이지 관측 자체가 아니다.
- `[self:write]{spill:true}` 스필 싱크와 **자동 스필**(이음매 통화 200K자 초과 → `data/spill/` 참조 봉투)도 같은 계열: 통화를 참조로 바꾸고 소비자가 투명 해소.
- ★**진단은 다이어트 대상이 아니다**(2026-08-28). `[table:each]` 의 부분 실패가 다문장 요약에 통째로 접히고 `message` 만 "errors 참조"를 가리켜 **참조 대상 없는 참조**가 되던 침묵 모순을 수리했다 — 요약 봉투가 `errors[]` 다이제스트(상한 3건·건당 300자)와 `error_count` 를 함께 나르고, 넘치면 `errors_digest_truncated` 로 절단을 신고한다(침묵 클램프 금지). 모듈 자신이 이미 선언한 원칙의 집행이지 새 정책이 아니다. 가드 `backend/test_envelope_errors_digest.py`.

**속도의 지렛대는 왕복 수가 아니라 '모델이 읽은 문자수'다**(2026-08-28 실측)
- 15일치 일간 보고서에서 벽시계가 IBL 조합 증가에도 접히지 않아 시간을 갈라 봤더니, 도구 실행은 총 시간의 한 자릿수 %이고 거의 전부가 모델 왕복인데 **왕복당 모델 시간이 읽는 양에 따라 20~28초로 움직였다**. 재는 계기가 없던 자리라 등록 스크립트 `에피소드통계` 에 **결과천자**를 신설했다 — `tool_result` 줄의 보이는 몫 + 절단 표식 `(+N자)` 의 숨긴 글자수를 더한 **정확값**(로그 절단은 기록을 자른 것이지 모델이 받은 결과를 자른 게 아니다). 옛 `...` 행은 하한 표지를 달고, 결과 줄이 없는 in-process 방언은 `None`(0 과 다름).
- 처방은 **읽기-접기**: 목록·후보는 표 꼬리로 얇게 흘리고 원문 정독은 선별 통과분에만. 경계 — 내용 판단에 필요한 정독까지 접지 말 것(두 단으로 나누는 것이 원리이지 깊이 제거가 아니다). 세 보고서 가이드 §0 에 조항으로 들어갔다.

**>> 연산자 실패 규약**
- 기본은 **즉시 중단**(`stop`) — 앞 단계가 실패하면 뒤를 돌리지 않는다.
- 문장 접두 `[on_error: skip|null]`로 문장 단위 변경 가능(2026-08-22 M3). 건너뛴 step 은 봉투에 신고된다(침묵 금지). 블록 차원의 처리는 `[try]{…}[catch]{…}[finally]{…}`.

**검색 결과 후속 액션 안내**
- 검색 결과에 `_note` 필드로 후속 액션 안내 (crawl, video_transcript 등)
- AI가 다음 단계로 자연스럽게 이어갈 수 있도록 힌트 제공

### 감각 전처리 (Sensory Preprocessing)
액션 출력을 경량 AI로 압축해 컨텍스트 폭발을 막는 층. `data/ibl_nodes_src/<node>.yaml`의 `postprocess` 블록으로 액션별 선언한다 — 다만 **2026-06-27 이후 이 블록을 선언한 액션은 0개**다. 압축이 `records[]` 통화를 문자열로 파괴하던 결함이 드러나, 검색·여행계가 전부 **구조화 통화(`records`/`items`) + 사람용 `message`** 로 옮겨가면서 압축 자체가 필요 없어졌다(당시 은퇴한 액션명 `search_ddg`·`search_gnews`는 지금 `[sense:search]{source}` 로 접혔다).
엔진의 기계는 남아 있다(`ibl_engine.py`의 `_postprocess()`, 우회 플래그 `_raw`) — 되살릴 자리는 "통화가 아니라 산문을 내는 액션"뿐이다. 컨텍스트 폭발의 현행 대책은 압축이 아니라 **봉투 다이어트 + 스필**(위 감각 피드백 절).

### 연상기억 (해마 + 심층메모리)
fine-tuned 임베딩(768d)으로 과거 IBL 사례(해마)와 사용자 사실(심층메모리)을 단계 0에서 1회 검색해 모든 에이전트에 self-describing XML로 주입.
- 해마: 로컬 M4 Pro 재학습(세대·측정표 정본=memory.md), 런타임 검색 ~99% — 자동 경험 증류 (점수 < 0.7, 또는 ≥0.7이어도 회상이 실제로 안 쓰였으면)
- 심층메모리: 같은 모델 공유로 시맨틱 검색 (2026-05-16 도입)
- 상세 (단계별 흐름·증류 조건·DB 스키마·학습 절차): **memory.md**

### 몸 원장 (Body Ledger, 2026-08-21)
"몸이 언제 어떻게 바뀌었나"를 몸 스스로 회상하는 네 기둥. 계기는 `[self:grep]` 사건이었다 — 2026-08-05 층 분리 같은 **몸 개조가 회상 불가능**해서 낡은 가정이 6주간 잠복했다. 몸이 바뀌면 몸에 대한 가정이 깨지므로, 변화 자체가 연상 가능한 기억이어야 한다.
1. **소유 선언 레지스트리**(`backend/cognition/data_ownership.py`) — 데이터 가족마다 주인·수명·백업 계급을 선언. 새 데이터 가족을 만들면 `DECLARATIONS` 등재가 의무다.
2. **어휘**(`[self:body]{op}`) — 읽기 여섯: `changes`(최근 파일 변화, 미커밋 포함) / `log`(커밋) / `file`(한 파일의 일생, 이름변경·이동 관통) / `diff`(실제 바뀐 줄) / `writes`(관문 통과 쓰기) / `trajectory`(한 실행의 핵심 사건 순서 — hash·ref, 원문 아님). **쓰기 하나: `commit`(각인, 2026-08-27)** — 지정한 `paths` 만 원장에 기록한다(`message`·`paths` 필수, 관문 통과 필요). 명명 헌법 2조대로 `[self:commit]` 신조어가 아니라 몸 원장 낱말의 **굴절**로 들어왔고, 공유 인덱스 계약을 지킨다(남의 스테이징 생존 + 각인 후 인덱스 동기화). 부작용 op 라 fixture 를 두지 않는다(건강검진이 실행해 버린다) — 용례는 `data/guides/body.md`. 가드 `test_body_commit.py` C1~C8. 정본 = `docs/SELF_EVOLUTION_AUTOMATION_HANDOFF.md`.
3. **쓰기 관문 원장**(`backend/base/write_ledger.py`) — git 이 못 보는 런타임 쓰기(`data/`·`outputs/`)를 관문 통과 시 append-only 로 한 줄. 행위자(agent·task·origin)가 실려 episode·tasks 와 조인된다. ★**전수 감시 데몬은 두지 않는다**(관문 훅만) — 그래서 관문 밖 직접 쓰기는 원리적으로 미기록이고, `writes` op 는 그 **부분성을 정직하게 광고**한다. 폴링류(심장박동 가족)의 행위자 없는 쓰기는 6시간당 1건으로 압축.
4. **정본 서열** — git 커밋(사건) > `docs/`(설계) > `data/system_docs/`(장기기억). 하네스 뷰(`CLAUDE.md`)는 시스템 *바깥*이라, 바깥 뷰에만 있는 사실은 누출로 친다.

### 도구 패키지 시스템 (노드 구현체)
도구 패키지들이 IBL 노드의 실제 구현체로 동작(수는 아래 '시스템 통계'·목록은 packages.md — 둘 다 빌드 파생). 폴더 기반 탐지 + 동적 로딩. op 분기 패키지는 `_OP_DISPATCHERS` 표준 채택(2026-05-28~) — `build_ibl_nodes.py --check`가 AST 정확 비교로 src↔tool.json↔handler 일치 검증. 패키지 구조·설치·생성 절차는 **packages.md** 참조.

### 자동응답 서비스 V3
- Tool Use 기반 단일 AI 호출로 판단/검색/발송 통합
- `search_business_items`, `no_response_needed`, `send_response` 도구
- 응답 즉시 발송 (polling 대기 없음)
→ 상세 문서: [communication.md](communication.md)

### 다중채팅방 시스템
- 독립 창에서 여러 프로젝트의 에이전트를 소환하여 그룹 대화 수행

### 의식·평가 에이전트
인지 파이프라인의 전체 흐름과 단계별 디테일은 위 "인지 파이프라인" 섹션과 `memory.md` 참조.

- **의식 에이전트 (본격 AI)** — `backend/cognition/consciousness_agent.py`
  - 직접 문제를 풀지 않고 "지금 어떤 문제를 풀어야 하는가"를 자기 한계 인식 기반으로 정의
  - 핵심 철학: 문제는 **나의 한계** × **환경의 제약**이 만나는 곳에서 생긴다
  - 출력: task_framing, achievement_criteria, history_summary, capability_focus, guide_files, self_awareness, world_state
  - 프롬프트: `data/common_prompts/consciousness_prompt.md`
  - 베이스 프롬프트(base_prompt_v6.md)의 "네 한계를 알아라" 원칙과 양방향 일관
- **framing 재사용 게이트 (2026-05-31)** — `agent_cognitive._run_consciousness_or_reuse()` + `_consciousness_fit_gate()`
  - 설계 원리: THINK = "framing이 필요하다"는 *수요* 선언. 분류기(무의식)는 history-blind라 "직전 태스크의 변주"를 알 수 없다 — 그래서 의식 호출 직전에 "그 수요를 *재고*로 충당할 수 있나"를 별개 신호로 묻는다 (분류기를 재심사하지 않음)
  - 같은 대화(registry_key)에서 만든 framing이 30분 내 재고에 있고 경량 fit 게이트가 적합 판정 → 의식(Opus) 호출 스킵, 재사용. turn마다 바뀌는 achievement_criteria만 게이트가 새로 생성 (비싼 framing 재사용 / 싼 criteria 갱신)
  - 캐시: 모듈 레벨 `_FRAMING_CACHE` (30분 TTL), SESSION_RESET·재시작 시 폐기. fits=false·재고 없음·게이트 실패 시 풀 의식 폴백(품질 손실 0)
  - 효과: 연속 THINK turn에서 의식 40~54초 + Opus 호출 제거. 주제 전환은 명시적=SESSION_RESET / 암묵적=fit 게이트가 분담
- **평가 에이전트 (경량 AI)** — `cognitive_eval._run_goal_evaluation_stream()`
  - achievement_criteria 대비 평가. NOT_ACHIEVED 시 재실행 (최대 3라운드)
  - **스트림 안**에서 돈다: 평가 진행 표지와 재실행 에이전트의 이벤트가 그대로 흐른다. 블로킹 함수였던 옛 판은 재실행(실측 10분)이 통째로 화면 밖이라 WS 유휴 타임아웃(600초)을 구조적으로 넘겼다(2026-08-22 수리)
  - 프롬프트: `data/common_prompts/evaluator_prompt.md`

### 의식 시스템 (Consciousness Pulse & Self-Check)
시스템에 자기인식을 부여하는 주기적 상태 수집 및 자가 점검 시스템:

```
┌─────────────────────────────────────────────────────────┐
│              Consciousness Pulse (매 1시간)               │
├──────────────┬──────────────────┬────────────────────────┤
│  World Delta │   User State     │     Self State          │
│  경제 지표    │   최근 대화 수   │   서비스 alive 체크     │
│  날씨 (매시간)│   미처리 태스크   │   디스크/메모리         │
│  뉴스 (6시간) │   다가오는 일정   │   최근 자가점검 결과    │
└──────────────┴──────────────────┴────────────────────────┘
                           ↓
              world_pulse.db (SQLite)
                           ↓
              world_pulse.md 가이드 파일 갱신
```

**일일 건강 점검 (매일 1회, `run_daily_health_check` — AI 0)**: `scripts/ibl_health_check.py` 를 subprocess 로 한 번 돌린다. §1A 정적 정합성 + §1B 통화 무결성(fixture 전수 probe) + §1C 골든 파이프(연산자·거울 키 포함) — 전 구간 결정론이다.
- **AI 순찰은 은퇴했다**: 옛 배선(`trigger_ai_health_check`, 6h)은 시스템 AI에게 assumed 액션을 훑게 했다. IBL 구조 건강이 변하는 건 *어휘를 쓸 때뿐*이고 그건 커밋 게이트가 막으므로, 정기 잡은 회귀 그물 한 벌이면 족하다.
- **파라미터의 출처**: 액션별 fixture(`data/ibl_fixtures.json`, `--check` 가 완전성 강제). 어느 액션을 돌려도 되는지는 `ibl_safety.py` 가 **선언에서 파생**한다(`returns:` + `side_effect:` 선언, op 단위 해소는 `ibl_ops`) — 옛 LLM 분류 캐시 `self_check_plan.json` 은 생성 경로가 2026-06-27 삭제된 뒤 3주간 유령 목록으로 판정을 대신하다 파생으로 교체됐다.
- 결과는 `self_checks` 에, 실사용 액션 건강은 `action_health` 에 기록(2026-08-21: `channel`·`error` 칸 추가 — 어느 통로에서 왜 실패했는지가 남는다). 부작용 op 는 fixture 금지이므로 `exempt` 로 선언한다.
- 3단계 상태: verified(**실사용** 최근 성공), failed(실사용 실패만), assumed(실사용 기록 없음 — 건강 체크 전용 실패는 failed 로 올리지 않는다). ★"assumed 가 많다"는 미검증이 아니라 *실사용이 없었다*는 뜻이다.
- 사용자가 "자기 점검해줘" 하면 시스템 AI가 이 데이터를 `self_inspection_guide.md` 절차(실패 액션 재시도 → transient/reproducible 분류 → 수정 난이도 평가)로 분석한다. RED 가 있으면 일일 잡이 알림 한 통을 사람에게 보낸다.

**정적 정합성 검증 합류 (2026-05-28 신설, 현행 배관은 2026-06-27 단순화)**: `build_ibl_nodes.py`의 삼각 검증(src ↔ tool.json ↔ handler.py `_OP_DISPATCHERS`)을 self-check 사이클이 실행 — 현행은 `world_pulse_health.run_ibl_health_check()`가 `scripts/ibl_health_check.py`를 subprocess로 돌려 §1A 결과를 `self_checks` 테이블에 `__static__:ibl_consistency` 식별자로 기록(옛 `run_static_ibl_check()`는 2026-06-27 은퇴). 정적 부채(누락된 등록, op 키 drift)와 런타임 부채(액션 실패)가 같은 사이클에서 잡힘. pre-commit 훅(commit 시점)과 일일 건강 점검(하루 1회)의 이중 검증 채널.

**의식 에이전트 메타 인지 가드 (2026-05-28)**: consciousness_prompt에 3 가드 — backend 자기 편집=자기 reload 자해 인식, 첫 호출 성공 시 의심 즉시 갱신, timeout/실패 후 같은 코드 재시도 금지. 어제 dispatcher audit 사고에서 시스템 AI가 보인 자해/의심 휴리스틱 패턴을 후속으로 처치.

**에피소딕 메모리**: 에피소드(사용자 명령→최종 응답)별 실행 로그 기록
- `episode_log` 테이블: 전체 로그 (최근 100개 보존)
- `episode_summary` 테이블: 인지 품질 지표 영구 보존 (해마 점수, 무의식 판정, 의식 소요시간, 실행 라운드, 평가 결과)
- 파일: `backend/base/episode_logger.py`, DB: `data/world_pulse.db`
- API: `/xray/episodes`, `/xray/episodes/{id}`, `/xray/episode-summaries`

**서버 시작 시**: 최근 1시간 내 펄스가 없으면 즉시 수집, 있으면 건너뜀

- 비용: 사용자/자신 상태는 DB 쿼리만 (비용 0), 세계 정보는 경량 API 호출
- 파일: `backend/cognition/world_pulse.py`, `backend/cognition/world_pulse_health.py`, `data/world_pulse.db`
- 설정: `data/world_pulse_config.json`
- API (`api_config.py` 내): `/world-pulse/config`, `/world-pulse/refresh`, `/world-pulse/today`, `/world-pulse/trend`, `/world-pulse/pulses`, `/world-pulse/self-checks`, `/world-pulse/health`

### 공유창고 (몸의 공개 얼굴, 2026-07-18~21)

공개 표면(포털·공개파일·가족신문·게시판)이 *만드는 목적지*라면, 창고는 **노드 자신이 주소를 갖는 것**이다.

- **발행 = 폴더에 파일 놓기**: `공유창고/0..4/` 가 노드의 맨 주소에서 그대로 서빙된다. 색인도 변환도 없고 파일시스템이 진실 — 바이트를 그대로 내주고(schema-on-read) 해석은 읽는 쪽 AI 몫.
- **레벨이 문**: 방문자 등급(0~4) = 이웃 CRM 등급과 **같은 자**. 보는 사람은 `0..자기 레벨`을 한 장의 평평한 목록으로 보고(같은 이름은 높은 레벨이 이김), 위 레벨 파일은 403 아닌 **404**(존재 자체가 정보). 유일한 의도적 누출은 `has_restricted` 한 비트(냄새).
- **기계 얼굴**: `GET /manifest`(제목·파일·크기·mtime·URL·`about`·`login` 블록) + `GET /f?path=` + 쿠키 로그인. **이게 계약의 전부** — IBL도 인지 파이프라인도 계약에 없다.
- **읽는 쪽(이웃 피드)**: `warehouse_feed.py` 폴러가 등록된 이웃 창고의 매니페스트를 30분마다 가져와 경로·mtime diff → `seed`/`new`/`changed` 타임라인. **AI·토큰 0의 순수 기계층**. 보존 스냅샷은 곧 동네 전체 파일명 색인(검색). 이웃이 indiebizOS 가 아니어도 된다 — `warehouse_adapters.py` 가 nginx/Apache 색인·RSS/Atom(HTML 자동발견)·Nextcloud 공개공유·일반 웹페이지를 같은 통화로 정규화(콜드 스타트 우회).
- **창고 주소 = 연락 방법**: 이웃의 `contacts`에 `contact_type='warehouse'` 행으로 저장(이메일·Nostr 키 옆). 리트윗은 내 창고에 떨어뜨린 `.url` 포인터 파일 — 구독자 클릭이 원본 창고로 직행(FOAF 발견이 프로토콜 아니라 파일).
- **둘러보기(2026-07-29)**: 어댑터가 생긴 뒤로 세상엔 이미 창고가 많은데 볼 방법이 없었다 → 이웃찾기가 두 갈래 — *소개글*(나를 알린 사람이 오는 수신면)과 *둘러보기*(`warehouse_directory.py`: Neocities 태그 브라우즈를 요청 1회로 파싱 + 사용자가 고칠 수 있는 시드 목록). 이웃 카드의 📣 **공개 추천**은 기계가 사실만 채운 초안을 사용자가 고쳐 발행하고(공개 발행이라 2단 확인), 본문이 `공유창고 Warehouse : <url>` 계약을 지켜 받는 쪽 이웃찾기에 '＋ 등록' 버튼이 그 자리에 붙는다. 방언에 **neocities** 어댑터가 합류(프로필의 update 이벤트=변화 피드, 루트 링크=파일 목록. 커스텀 도메인은 `api/info` 대조로만 채택 — 남의 사이트를 잘못 물지 않게).
- **AI 가 채우는 진열**: 비즈니스 아이템(나눔·판매·가능)이 창고 폴더로 물질화될 때 사람이 여는 표지 한 장(`<비즈니스> 카탈로그.html`, `warehouse_catalog.py`)이 함께 발행된다 — 사진을 data URI 로 실은 **자족 문서**(받아가서 열어도 그대로 산다)에 연락처 꼬리는 비즈니스 문서와 같은 소스(`api_portal._contact_pairs`). 매 공개 요청마다 도는 자리라 **지문 게이트**(첫 줄 `<!-- catalog:<sha1> -->`)로 내용이 같으면 재생성 0 — 괜히 다시 쓰면 mtime 이 흔들려 이웃 폴러가 `changed` 로 오독한다.
- **자격·평가 두 축**: 상대가 준 접근 **레벨**(가입/로그인 자격을 폴러가 그대로 사용, 만료 시 자가치유·실패 시 익명 폴백)과 내가 매기는 **창고 점수 0~3**(피드·검색 필터)은 독립.
- **주소는 파생**: 몸의 공개 주소는 흩어진 설정이 아니라 창고가 실제로 서빙하는 얼굴에서 파생(`origin_host()`, 권위=`public_face.provider`). Cloudflare 발급이 터널·Worker·R2 캐시까지 만들고(`cdn_provision.py`), 인증 게이트는 fail-closed(미등록 호스트=외부 취급, 프록시 신호를 `Host`보다 먼저).
→ 상세: [communication.md](communication.md)

### 몸 사이 소통 — 명함과 부탁 (2026-07-22)

여러 몸(맥·폰·낯선 PC)이 서로를 부리는 방식을, **공유 사전 RPC**(내 어휘로 남의 몸을 원격 호출)에서 **명함 + 자연어 부탁**으로 바꿨다.

- **명함** `GET /nodes/card` — 레지스트리에서 파생한 desc-프로젝션(표준 코어 제외·params 미포함·몸 인식 필터). 등록 시 상호 자동 교환·캐시(`peer_cards.py`), 프롬프트 냄새 ~70토큰/몸.
- **부탁** `POST /nodes/ask` (어휘 `[others:ask]`) — 받는 몸이 **자기 사전으로** 컴파일→실행→통화로 회신(1회 자가교정, 어휘 밖이면 정직한 거절). 컴파일러 능력 축은 *해마 유무*(용례 있으면 조종실 경로, 없으면 사전-동봉 경량 모델).
- **사전 물리 분리**: 배포물=전체 사전집, 설치=자기 어휘만(로더 필터 + 폰 번들 물리 필터). 카탈로그·해마 회상이 **소유-필터**를 지나 "남의 어휘를 학습하지 않는다".
- **사전 이음매 — 로더가 둘인 이유**(2026-08-24 계약화): 같은 `ibl_nodes.yaml` 을 읽는 로더가 둘인데 중복이 아니라 **의미가 다르다**. `ibl_access.load_nodes_raw` = *원본 사전집*(생 yaml, 배포물 전체), `ibl_registry.load_nodes_installed` = *이 몸의 설치본*(원본 + api_registry 병합 + `detect_body` 기반 타몸 어휘 prune). 설치는 몸의 의미론이라 언어(ibl 층)가 아니라 datastore 층에 산다 — "몸의 명사=코드"의 자리다. ibl 층이 소비하는 공개 표면은 `load_nodes_installed`·`invalidate_nodes`·`pruned_reason`·`self_can_run`·`foreign_actions`·`code_is_own` 이고, 그 밖의 언더스코어 심볼은 계약이 아니다(층-밖에서 찌르지 말 것). 두 로더 다 **부재≠파손** — 없는 파일은 조용한 빈 값, 깨진 파일은 재생성 안내를 단 오류다.
- **신뢰 = 이웃 등급**(`body_trust.py`): 특별함은 배관이 아니라 레벨. 낯선 몸의 부탁은 거절되고, 폰-맥도 "최고 레벨 이웃"일 뿐이다 — **몸 사이 특권 배관을 두지 않는다**가 설계 원칙.
- **표면 분리**: 원격 런처(=PC의 일부, 5탭)와 폰 네이티브(=독립 시스템, 3탭)를 조립 모듈로 가름(`backend/surface/launcher_surface_remote.py`·`backend/surface/launcher_surface_phone.py`). 폰 조종실은 로컬 완결(translate/validate/distill/catalog).

### USB 손발 (게스트 PC 헬퍼, 2026-07-23)

낯선 PC 에 USB 로 꽂아 셸·파일 작업을 시키는 **얇은 몸**. 두뇌·신원은 허브에 남고 USB 엔 limb key 하나(맥 비밀번호가 아니다).
- 어휘 2: `[self:limb]{op: issue/list/revoke}`(발급=USB 페이로드 생성) + `[limbs:guestpc]{op: shell/read/write/list/info}`(허브에서 하달).
- 연결=헬퍼(Go 단일파일)가 그 PC 에서 허브로 **아웃바운드** 접속 → 폰 푸시 큐(`phone_jobs`)를 재사용해 셸 봉투를 당겨가 실행·회신. 그 PC 방화벽 설정 불필요.
- 눈 없음(셸·파일만). 발급은 이름 명시가 원칙이고(오배송 방어), 폐기(revoke)는 그 키만 죽인다.

### 웹앱 등기부 (몸이 낳은 웹앱들, 2026-08-01)

이 시스템은 공개면·계기·외부 배포로 웹앱을 계속 낳는데, 정작 그것들의 목록을 갖고 있지 않았다. `[self:webapp]{op: list/status/register/remove}`(system_essentials, `webapp_registry.py`)가 그 등기부다.

- **파생 우선**(수동 원장은 드리프트한다): 진실 소스 7곳 — 포털(`portal_state`)·게시판·가족신문·공개파일 바스켓·정기보고 발행면·web-builder `sites.json`·`outputs/web-projects/*/wrangler.toml`(야생 Worker) — 에서 **매 호출 재계산** + 고정 2면(런처·NAS PWA). 파생 밖 예외만 `data/webapps.json` 에 수동 보충.
- `status`=전 함대 **병렬 HTTP 생존 실측**(🟢/🔴·응답코드·지연). 🕸️ 계기 3탭(함대/생존/등록)이라 전 표면에 자동 등장.
- 판단 기준은 가이드 `webapp.md`: 웹앱 4부류 결정 트리(몸 공개면 / 포털 계기 대여 / 외부 서버리스 / 자족 단일 HTML)·몸 공개면 5조각 레시피·PWA 함정(★같은 origin 다중 PWA 는 알림 권한이 한쪽 WebAPK 로 위임된다 — 알림 권한은 앱이 아니라 **origin 단위**).

### 알림 도달 경로 (2026-07-28)

수신한 메시지(Nostr/Gmail)가 DB 에 저장만 되고 사용자에게 닿는 경로가 0이던 것을 봉합. 수신 단일 관문(`channel_poller._save_message_to_db`) 직후 `notify_dispatch.notify_user()` 하나로 모인다 — ①알림함 기록 ②**A: 런처 연결 시** WebSocket `show_notification` → Electron OS 네이티브 알림+배지+클릭=메신저 창 ③**B: 미연결 폴백** `desktop_notify.py`(의존성 0 — osascript / PowerShell WinRT 토스트 / notify-send). win·linux 트레이 상주로 창을 다 닫아도 수신·알림이 계속된다.
★**경로 C(웹 푸시)는 은퇴**: RFC 8291 구현까지 마쳤으나 실기기 도달 실패 — 같은 origin 의 PWA 둘 중 하나에만 알림 권한이 위임되는 안드로이드 동작이 진범이었다. 재활 조건(런처 서브도메인 분리로 origin 독점)만 주석에 남기고 코드는 전부 제거했다.

### 원격 접근 시스템
Cloudflare Tunnel을 통해 외부에서 IndieBiz OS를 제어합니다:

- **원격 Finder** (`api_nas.py`): 파일 탐색, 동영상 스트리밍, 다운로드 — 개인 NAS처럼 활용. 홈 화면 설치 시 별도 앱(**IBFind**).
- **원격 런처** (`api_launcher_web.py` + `launcher_surface_remote.py`): 자율주행·조종실·앱·공유창고·포식 5탭 — 브라우저면 어디서나 같은 표면. 웹앱 매니페스트로 홈 화면 설치 가능(서비스워커는 캐시하지 않음 = 항상 라이브).
- **표면이 곧 착지점**: 결과가 어디로 떨어지는지는 *어느 표면이 물었나*로 정해진다(폰 브라우저에서 누른 재생은 폰에서 난다). ★클립보드 수신면(clipbox)은 2026-07-28 철회 — '폰으로'는 종전 푸시 큐를 그대로 쓴다.
- 세션 기반 인증 (기능별 별도 비밀번호)
- 모바일 반응형 다크 테마 UI
→ 상세 문서: [remote_access.md](remote_access.md)

### 브라우저 자동화 (browser-action 패키지)
두 가지 드라이버를 통한 브라우저 제어:

- **Playwright 드라이버**: 별도 Chromium 인스턴스를 띄워 자동화. 항상 사용 가능.
- **Chrome MCP 드라이버** (계획): 사용자의 실제 Chrome 브라우저를 MCP 프로토콜로 제어. Chrome 확장 프로그램(MCP 서버)이 `localhost`에서 SSE/HTTP로 노출, IndieBiz OS가 MCP 클라이언트로 연결.
  - 수동 연결: 에이전트가 필요할 때 `[limbs:browser]{op: "chrome"}`로 연결
  - Chrome 미실행 시 Playwright로 자동 폴백
  - 같은 IBL 액션(`limbs:browser_*`)을 사용, 내부 드라이버만 다름

## 프로젝트 & 에이전트 (데스크탑 3오브젝트)

바탕화면 공간에 세 종류의 오브젝트를 배치한다 (구 overview.md 흡수):
- **프로젝트(Project)**: AI 에이전트들의 팀. 역할별 에이전트를 담고, 통째로 복사·템플릿화 가능. 대화DB·에이전트·심층메모리가 프로젝트별로 물리 격리(공간에 맥락 경계 위탁). 모델·API 키는 에이전트별이 아니라 시스템 전체 모델 기어가 결정.
- **스위치(Switch)**: 자연어 명령을 저장해 한 번의 클릭으로 실행하는 자동화 오브젝트.
- **폴더(Folder)**: 프로젝트·스위치를 정리하는 컨테이너(중첩 가능).

에이전트 유형:
- **외부 에이전트(External)**: Nostr/Gmail/Telegram 채널을 가져 원격에서 명령을 받고 IndieNet으로 타 노드와 소통.
- **내부 에이전트(Internal)**: 채널 없이 OS 내부에서만 동작(프로젝트 내 협업·보안 작업).

동작·접근:
- 프로젝트 단위로 독립된 작업 공간. 각 프로젝트에 역할별 에이전트 배치
- 에이전트 간 위임: 단일/순차/병렬 (`[others:delegate]{scope: "cross"}`) — 상세: communication.md
- 시스템 AI: 전체 노드 접근, 프로젝트 에이전트에 위임 가능
- 프로젝트 에이전트: 허용된 노드만 접근 (allowed_nodes)

## 외부 연동

- **통신**: Gmail, Nostr (DM은 NIP-17 gift-wrap, 구 NIP-04 호환 수신), Telegram
- **NAS**: 음악 스트리밍, 자막 관리, 웹앱 호스팅
- **안드로이드 (양방향)**: 제어=ADB 기반 `[limbs:android]{op}` (snapshot→요소 탭) / 감각=폰 컴패니언 앱(NotificationListener)이 알림·위치·걸음을 NIP-17 한방향 피드로 전송 → `[sense:phone]{op}` + `/phone/*` API.
- **폰 네이티브 (두 번째 독립 자아)**: phone-companion/ (Kotlin+Chaquopy) 네이티브 앱이 **폰에서 온디바이스 Python 백엔드**를 띄워 앱모드 슈퍼앱을 서빙하고 **실제 IBL 엔진**이 폰 안전 패키지(`build_ibl_nodes.PHONE_VERIFIED_PACKAGES`)를 로컬 실행한다. **두뇌도 폰-로컬**: 빌린 맥 두뇌(claude_code 원격 렌트)에서 **폰 인-프로세스 Gemini**(경량 3.1-flash-lite / 본격 3.5-flash)로 전환 — 빌린 두뇌는 자기 몸(맥)을 데려오지만 Gemini API는 폰서 직접 호출하므로, away-case 역방향 장치(WS/remote_turn)를 통째 은퇴하고 outbound(/embed·_forward_to_mac)만 유지. 모델은 `runtime_utils.detect_body()`로 **자기 하드웨어를 감지**(맥=sysctl 칩명, 폰=Build jclass)해 자신을 맥 아닌 "폰"으로 인식 → 두 HW = 두 정체성(정체성은 하네스=프롬프트+기억에 있지 모델 위치 무관). 빌드가 정본 트리(엔진+패키지+`ibl_nodes.yaml`)+하네스(prompt_builder/agent)를 `indiebiz_base.zip` 에셋으로 번들→filesDir 추출(BaseBundle은 APK 업그레이드 때만 wipe). `runs_on` 능력 태그(`anywhere`/`pc_only`/`phone_only`)와 `data/phone_manifest.json`이 폰 못 도는 계기/액션을 숨기거나 허브(데스크톱)에 단건 위임. 온디맨드 감각=`sense:here`(위치)·`sense:listen`(마이크)·`sense:see`(카메라)·`sense:phone`(알림), 조작=네이티브 AccessibilityService(`limbs:android`, USB 불필요). 폰서 Python 인-프로세스 실행(`execute_python`)도 가능 — 기기 프로그래밍 에이전트. 라디오는 stream URL을 WebView(hls.js)로 돌려 **폰 스피커** 재생. **기억 두 부류**: 사용자 세계-데이터(연락처·비즈니스·일정·의료기록)=공유·CRDT 동기화 / 각 자아의 주관적 기억(대화·해마·자기상태)=자아별 사적·비동기화. 폰=리모컨 아닌 두 번째 독립 자아.
- **원격**: Cloudflare Tunnel (Finder + 런처). 원격 런처=집 PC 리모컨 의미론(라디오 재생은 집 PC 스피커).
- **브라우저**: Playwright 기반 자동화

## 자기수정 — REPAIR 경로 (2026-08-05 헌법 개정)

시스템이 **자기 코드(RED 구역: `backend/`·`data/packages/`)를 직접 고치는** 경로. 옛 설계의 '사람 승인 게이트'는 폐기됐다 — *"어차피 AI가 하는 걸 사람이 일일이 승인할 거라면 사람이 하는 것과 다름없다"*. 대신 **한도 3 + 기계 안전판**:

- **한도 ①사람 명령**: `thread_context.task_origin == 'user'` 인 태스크에서만(WS 채팅·`/system-ai/chat`·에이전트 명령 HTTP 4곳만 세팅). 스케줄러·자가점검·위임 사슬·외부 채널은 **미세팅 = fail-closed** → 자율 태스크는 종전대로 `[self:patch]` 제안만. **새 진입점을 만들면 `set_task_origin("user")` 를 붙일 것** — 그리고 그 표면이 `cognitive_stream` 에 닿는지는 관문(`backend/test_user_surface_pipeline.py`)이 묻는다. 묻는 것은 **누가 명령했나** 하나뿐이다. 시스템 AI 냐 프로젝트 에이전트냐(=누가 실행하나)는 한도가 아니다.
- **한도 ②최고 모델 고정**: 기어가 절약이어도 REPAIR 실행 모델은 고급으로 승격(`model_resolver`, reflex→경량 고정의 역방향).
- **한도 ③의식 각성**: 의식 토글 OFF 여도 REPAIR 는 THINK(의식 framing) 경로를 강제.
- **기계 안전판**: 사전 구문검증(`compile` — 깨진 `.py` 는 라이브에 닿기 전 거부) → 원본 백업(파일당 최초 1회) → backend `.py` 면 **분리 워치독**(`red_watchdog.py`, `start_new_session` — 서버가 죽어도 생존)이 리로드 후 `/health` 확인, 죽어 있으면 백업 복원 + 재기동 + OS 알림으로 **자동 롤백**.

### ★일반 원칙 둘 (이 경로가 가르쳐 준 것)

1. **자기 죽음 이후에 실행돼야 하는 단계는, 죽음을 넘는 프로세스가 소유한다.**
   옛 keeper 규약("작업 전 표식 세우고, 작업 후 지운다")은 자기수리에서 **원리적으로 완주 불가**였다 — backend 를 고치는 시스템 AI 는 그 backend 안에서 살아서, 편집이 부른 리로드가 회수 단계를 실행할 턴을 죽인다(실측: 표식이 남아 감시가 몇 시간 멎음). 2026-08-17 개정에서 표식은 **기계 소유**가 됐다: 쓰기 직전 자동으로 서고(내용이 소유자 표시이자 심장박동), 회수는 워치독이 어느 결말에서든 하고, 놓쳐도 keeper 가 `PAUSE_TTL` 900초 만료로 감시를 재개한다. → 평범한 `backend/*.py` 편집엔 **이제 아무 의례도 필요 없다**.
2. **죽음을 넘긴 판정은 다음 턴의 입이 닫는다.**
   수리의 성패는 자기 턴이 죽은 뒤에 난다 — 워치독이 `result.json` 에 적지만 읽는 쪽이 없어서 "성공한 수리"와 "그냥 멎은 수리"가 사용자 자리에서 구별되지 않았다. `red_report.py` 가 미보고 판정을 회수해 다음 턴 0단계 연상에 `<repair_outcome>` 으로 얹는다(없으면 0토큰·한 번만). **누구의 입이 닫는가 = 수리한 그 에이전트**(2026-08-25 사용자 확정) — 주인 열쇠(`red_report.owner_key`, 시스템 AI 는 예약 id 하나로 접는다)를 쓰기 시점에 원장(manifest·session)에 박고 회상이 자기 것만 줍는다. 회수는 한 번뿐이라, 남이 먼저 주우면 표식만 찍히고 명령한 창에서는 영영 안 보인다.
3. **'누가 도는가'는 원장 한 벌에만 묻지 않는다 — 그 한 벌은 지워질 수 있다.**
   지연 적용은 "열린 주행기록(`ended_at IS NULL`)이 곧 도는 턴"이라는 표식 하나에 기대고 있었다. 그런데 그 표식을 세우는 고아 회수가 *시간 순서*로 판정했다 — "나보다 먼저 시작된 미종료 행은 죽은 턴". 그 전제는 서버 진입점에서만 참이라, 살아 있는 몸 곁에서 뜬 임시 프로세스(라이브 데이터 경로를 물려받은 프로브·스크립트)가 같은 배선을 부르자 **도는 턴의 표식을 지웠고**, 적용은 "열린 턴 없음"으로 읽고 그 턴 위에 썼다 — 리로드가 그 턴을 끊었다.
   ⇒ ①회수 판정을 추정(시간)에서 실측(**행의 주인이 살아 있는가**, `episode_log.owner`=pid:시작시각)으로 옮기고, ②적용은 원장이 침묵할 때 **몸에게 직접 묻는다**(`/health` 의 `live_turns` — 그 워커가 지금 열어 둔 턴). ③되돌릴 수 없는 부팅 부작용(완료 task 정리)은 **부팅 주체만** 한다(이미 도는 백엔드가 있으면 건너뛰고, 건너뛴 사실을 말한다).
   판정 불능은 어느 층에서도 '없음'으로 뭉개지 않는다 — 도장을 못 읽으면 살아 있다고 보고, 몸이 `live_turns` 를 모르면 다시 묻는다. **틀린 대기가 틀린 쓰기보다 언제나 싸다.**

4. **선언에 없는 조건은 조건이 아니다 — 그리고 표면이 하나 갈라지면 선언 전체가 그 표면에서 무효다.**
   헌법은 한도를 셋으로 선언했는데(사람 명령·최고 모델·의식 각성) 같은 커밋의 코드는 넷을 걸었다 — `is_system_ai and origin == 'user'`. 넷째는 어디에도 선언된 적이 없고, 하필 헌법이 **정당한 진입점으로 이름 붙인** "에이전트 명령 HTTP"(폰 원격런처 → 프로젝트 에이전트)를 배제했다. 사람이 명령했느냐(`origin`)와 누가 실행하느냐(`is_system_ai`)는 다른 축인데 코드만 축을 하나 더 갖고 있었다.
   그 위에 표면 하나가 파이프라인을 우회했다: `api_agents._run_agent_command` 만 `cognitive_stream` 을 건너뛰고 AI 를 직접 불러, **분류·의식·모델 승격·그랜트가 통째로 없는 턴**을 만들었다. 실측(ep1915, 2026-08-24): 사용자가 `#repair` 를 붙였는데 그 턴의 로그에 `[무의식] 분류` 가 0줄이고 RED 가 "REPAIR 경로로 발급된 적이 없습니다"로 거절했다 — 사용자는 태그를 붙였고, 그 표면에는 태그를 읽는 코드가 없었다.
   ⇒ 조건은 정본(커밋·이 문서)으로 되돌리고, 표면 포크는 **관문**으로 잠갔다(`test_user_surface_pipeline`: `set_task_origin("user")` 를 세우는 함수는 자기 호출 그래프 안에서 `cognitive_stream` 에 닿아야 한다). 사람이 고른 grep 은 반드시 샌다 — 부류는 관문이 지킨다.

5. **보호 구역의 판정은 판정자의 집이 아니라 과녁의 뿌리에서 유도한다.**
   RED 판정(`backend/`·`data/packages/`)이 *로드된 게이트 사본의 집*에 고정돼 있어서, 라이브 게이트에게 `.worktrees/…/frontend/` 는 RED 가 아니었다 — 회귀 시험이 워크트리의 `frontend/index.html` 을 실제로 덮어썼다. 격리 사본은 apply 로 라이브가 될 원본이라, **여기가 오염되면 검증을 통과한 척하는 코드가 라이브로 간다**. 거울상도 같이 나왔다: 워크트리 게이트에게는 본체 `backend/` 가 RED 가 아니어서 격리 안 코드가 절대경로로 기질을 그랜트 없이 쓸 수 있었다.
   ⇒ `red_zone_family.py` 가 기준 루트를 **과녁 경로에서** 유도한다. 본체와 그 git 워크트리(`.git` 파일 → 본체 `.git/worktrees`)는 **한 가족**이고, `backend/`·`frontend/` 이름만 같은 남의 저장소는 종전대로 허용이다. 게이트 자신은 가족 판정 *이전에* 항상 보호된다. 가드 `test_red_zone_body_family.py` F1~F6(네 방향 종단).

6. **부류를 이름 열거로 막으면 반드시 샌다 — 자연 작명을 부류로 덮어라.**
   2026-08-23 에 `test_*.py` 신규 생성의 리로드 절단을 이름 열거로 봉했는데, 08-27 에 같은 부류가 **다른 이름으로 재발**했다: 수리 턴이 만든 실측 사본(선행 밑줄 하나로 시작하는 스크래치 이름)이 리로드를 불러 그 턴 자신을 apply 전에 절단하고 좌초시켰다. 열거 대신 스크래치의 자연 작명(선행 밑줄 하나)을 부류로 덮었다 — `_[!_]*.py`(`[!_]` 가 `__init__.py` 같은 산 배관을 지킨다). ★**제외 목록은 uvicorn 부팅 때 읽힌다** — 재기동 전의 몸은 옛 목록으로 판단한다. 그리고 가드는 선언(fnmatch)이 아니라 **실판정자**(설치본 uvicorn FileFilter, `pathlib.match`)로 종단 실측해야 한다. 둘의 의미론이 업그레이드로 갈리면 선언만 초록인 채 샌다.

상세: `docs/SELF_MODIFICATION_SAFETY_DESIGN.md`

## 표준 코어 vs 사용자 경계 (설치·업데이트 이음매)

IndieBiz OS는 **표준 코어**(IBL 문법 + 기능어 노드 + 백엔드/프론트 엔진 + 도구 패키지·앱 카탈로그)를 배포하지만, 설치되는 순간 *사용자의 인스턴스*가 된다 — 사용자는 어휘를 더하고, 앱을 설치·저술하고, 대화·설정을 쌓는다. 이 둘의 경계는 **단일 진실** `data/core_manifest.json` 하나로 그어진다(`scripts/build_core_manifest.py`가 **git 추적 집합**=배포에 딸려오는 것에서 파생, 손목록 없음). 원래 이 경계는 `.gitignore`·electron-builder 필터·업데이트 heuristic 셋에서 제각각 인코딩돼 서로 어긋났는데(어휘가 stale 보존되는 등), 이 매니페스트로 접어 네 곳이 한 진실을 향하게 했다.

두 불변식:

- **설치가 다 깔지 않는다.** 많은 패키지가 자기 API 키를 요구해, 다 활성화하면 못 쓰는 것에 파묻힌다. 전체 카탈로그는 배포되되(`not_installed/`에 대기) **큐레이션된 소수만 기본 활성**. 각 패키지는 `origin`(core/user)을 갖고, 설치 파일 패키징(`build_dist_filter.py`)이 매니페스트 주도라 사용자의 커밋한 개인 앱·파일은 배포로 새지 않는다. 개인 패키지를 커밋해도 코어에서 빼려면 opt-out(`.origin`=`user`).
- **업데이트가 사용자 것을 안 덮는다.** 재설치·업데이트는 코어 소유 파일만 갱신한다(`main.js` `initUserData`). 사용자의 **설치 상태**(어떤 패키지를 켜고/껐는지=폴더 배치), 저술한 어휘·앱, 설정, 대화 이력은 그대로 살아남는다 — 업데이터가 번들 기본 배치를 다시 강요하지 않고 사용자가 고른 폴더 위치를 존중(`syncPackagesPreservingState`). 코어 어휘 산출물만 매니페스트 기준 강제 갱신.

헌법적으로 이건 하부/상부 이음매(substrate/superstructure)와 표준-코어(기능어 self/others/table=표준 vs 내용어=사전) 원칙을 **패키지·앱·설치·업데이트 층까지 밀어낸 것**이다. 상세: technical.md '설정 파일 위치'.

## 이음매 시민권 (커밋·부팅 게이트, 2026-07-25~26)

액션(어휘)은 `--check` 삼각 검증이라는 시민권을 오래 가졌지만, **액션이 아닌 것**(이음매 = 인증 게이트·이벤트 루프 규율·공개 라우트·파생물·부팅)은 주석과 관습으로만 지켜졌다. 같은 부류의 검사를 이음매에도 준다 — 전부 AST/실측 기반, 의존성 0, pre-commit + CI(`.github/workflows/`).

- **인증 게이트 fail-closed**: `remote_access_guard` 가 블록 전체를 `except: pass` 로 감싸 "보수적"이라 불렀지만 실제로는 fail-open 이었다(판정자 `is_external_request` 는 "로컬임이 증명될 때만 로컬"인데 래퍼 한 줄이 그 규율을 무효화). 판정 불능 → **503**(조용히 열리는 대신 시끄럽게 멈춘다), 인증 실패 → 401.
- **공개 노출 ↔ 인증 대조 가드**(`check_public_routes.py`): "자체 시크릿 게이트 보유"라는 주석을 검사로 승격. 오라클은 코드가 아니라 **살아있는 라우트 테이블**(실제 `app.routes` 를 훑고 실제 `is_public_remote_path` 에 묻는다 — 등록 목록을 재파싱하면 그 파서가 또 드리프트한다). 헬퍼 안에서 검사하는 간접 호출까지 추적하고, **공허한 통과를 금지**(거짓 초록은 붉은 것보다 나쁘다).
- **이벤트 루프 규율 가드**(`check_event_loop.py`): async 본문의 동기 블로킹 호출은 단일 프로세스 백엔드를 세우고, 이 서버는 자기 자신을 부르는 경로가 잦아(창고 폴러→공개 얼굴→터널→자기) 자기교착이 된다 — 같은 부류가 세 번 재발했다. ★정확도가 전부라 중첩 sync 함수·람다·클래스 메서드를 허용 규칙으로 두고 **음성 픽스처를 미탐 픽스처보다 중히** 본다(오탐 한 번이면 가드가 꺼지고 미탐도 같이 사라진다).
- **신선 clone 게이트**: main 이 개발 기계에서만 통과하고 clone 에서는 `--check` 실패였다(원인 둘 다 *커밋되지 않은 로컬 상태*) → 커밋된 것만 보는 눈을 CI 에 붙이고, 파생물 3종을 추적으로 돌리고, 파생 결정성(auth 레지스트리를 import 아닌 AST 로)까지 고쳤다.
- **부팅 관측**(`boot_status.py`): lifespan 의 `except: print(...실패 무시)` 블록 10개를 성패 양쪽 계측(제어 흐름 무변경). `/world-pulse/health` 가 `boot` 절을 함께 내보내고 부팅 실패가 하나라도 있으면 overall 을 degraded 로 올린다 — 사흘 뒤 "왜 스케줄이 안 도나"의 답이 터미널 스크롤 저편에 있지 않게.
- **윈도우 이식성 게이트**(`check_win_portability.py`): 유닉스 전용 stdlib 의 무가드 톱레벨 import 탐지. ★위험지대는 규율 잡힌 `backend/` 가 아니라 **데이터 취급되는 실행 코드** `data/packages/`.

**밭 폐쇄 — 발견을 기다리지 않고 탄생을 차단한다**(2026-08-27). 상상훈련이 같은 속(屬)의 새 종을 네 회차 연속 발견한 뒤, 구조 원인이 "판정 자리의 전수 목록이 없고 *발견*이 스윕의 입구였던 것"으로 밝혀졌다. 교리 「부류 스윕은 관문을 먼저 쓰고 고쳐라」를 밭마다 적용해 **census → 일괄 스윕 → 상설 관문**의 연쇄로 닫았고, census 가능한 밭 여섯(값 판정·경로 해석·compute 식 비교·파라미터 표면 일치·시간 의미론·동시성)이 전부 닫혔다.

- **사설 값 판정**(`check_value_judgment.py`) — AST census 267 원시 히트 → 유의 60자리, 15자리를 `text_match`/`values_equal`/`relation_identity` 위임으로 스윕. 잔여 34자리는 **동결 목록이 아니라** 자리마다 `# vj-ok: <사유>`(침묵 클램프 교리와 같은 태도).
- **경로 해석**(`check_field_path.py`) — `"items.0.title"` 이 표면마다 값/None/오류로 갈리던 워커 5방언을 `common/field_path.py` 한 벌로. 결측(MISSING)≠null 구별을 보존한다.
- **compute 식 비교** — `safe_expr` 의 파이썬 원시 비교(`"Seoul"=="seoul"` 이 거짓·혼합 타입은 TypeError)를 AST 재작성으로 값 코어에 위임. 같은 몸의 `filter` 와 다른 선고를 내던 마지막 조건 표면이었다.
- **파라미터 표면 일치**(`test_surface_param_parity`) — 도구 스키마 ⊆ REST ⊆ MCP 포함을 기계가 단언(주석 의무를 검사로 승격).
- **시간 의미론**(2026-08-27, 사용자 판정) — 값 코어에 `DATETIME` 종류 신설. **선언 표기(`YYYY-MM-DD`[+시각][+`Z`/±HH:MM])만 날짜**이고 표기 밖·달력 위반은 수선 없이 텍스트다. 같은 순간은 같은 실체로 접히고(Z↔+00:00, +09:00 10시↔Z 01시, 날짜만↔그날 00:00 — 동등·순서·관계 키·그룹 키까지), naive/aware 혼합이나 날짜 vs 비표기 텍스트의 순서는 **판정 불능(정직 거절)**이다. ★표면 스윕이 0이었다 — 앞선 밭 폐쇄가 모든 판정을 코어 한 벌로 접어 둔 덕에 종류 하나를 더하니 filter·블록·compute·정렬·키·응답 변환이 자동 승계했다. **밭을 먼저 닫으면 언어 개정이 싸진다.**
- **동시성**(`check_concurrency.py`) — 기계로 판정 가능한 셋만 정직하게: `sqlite3.connect` timeout 미선언 67자리를 전부 명시(다중 프로세스가 같은 DB 를 쓰는 몸에서 **잠금 대기는 기본값 암묵 의존이 아니라 저자의 결정**), 리로드 워커 안 Thread 13자리에 수명 설계 사유(`# cc-ok`), `check_same_thread=False` 1자리에 잠금 풀 설계 명시. 수용된 잔여(엔진 스레드 50자리·"긴 작업" 판정·락 없는 공유 상태)는 관문 헤더에 명문화하고 그 규율은 pitfall 원장이 소유한다.
- ★**자동 편입은 기각**: 명단 밖의 정규화 없는 원시 비교를 기계가 자동으로 끌어오면 *한 벌을 채택하는 것이 벌칙*이 되는 역유인이 생긴다 — 관문 헤더에 명문으로 남겼다.

## 시스템 통계

> 아래 마커 구간의 수치는 `scripts/build_ibl_nodes.py`가 레지스트리 실측으로 재생성한다(손 수정 금지). 마커 밖 항목(프로젝트·해마 등 런타임 수치)은 날짜를 달아 손으로 갱신.

<!-- IBL_STATS:START -->
- 도구 패키지: **41개** (+ 백엔드 extensions **5개**), IBL: **6노드 151 액션** (sense 40·self 50·limbs 14·others 17·engines 9·table 21)
- backend **.py 283개**(test 제외, git 추적 기준) — 층 디렉토리 `base 23 · datastore 36 · ibl 38 · cognition 43 · services 28 · surface 60`(+ common 15·providers 11·channels 4·drivers 3). 가이드 **68개**(guide_db 등록 **67**)
- op 분기 액션 **70개** — 핸들러 구현은 전부 `_OP_DISPATCHERS` 표준(**28개 패키지**, 나머지는 패키지 밖 backend-native), `--check` 가 src↔tool.json↔handler 를 AST 정확 비교. 부작용 여부는 통화(`returns`)에서 분리된 `side_effect:` 선언(true 41·false 15·미선언 95)
<!-- IBL_STATS:END -->
- 활성 프로젝트: 24개 (시스템 프로젝트 수동모드·앱모드 포함), 에이전트 33개 (2026-08-22 실측)
- 해마 코퍼스 **3,530 용례**·증류 누적 907 (2026-08-22 실측 — 라이브 수치는 조종실·memory.md)
- 등록 스크립트 `data/scripts/`(`registry.yaml` + .py) — 어휘가 아닌 절차의 거처. 개수는 레지스트리가 정본이다.

## 참조

- IBL 명세: `data/system_docs/ibl.md`
- 실행기억 & 해마: `data/system_docs/memory.md`
- 패키지 가이드: `data/system_docs/packages.md`
- 설계 철학 (백서): `WHITEPAPER.md`

---
*최근 변경(2026-08-28): 밭 폐쇄 여섯(값 판정·경로 해석·compute 식·파라미터 표면·시간 의미론·동시성)과 상시 관문, RED 몸-가족·리로드 스크래치 부류 원칙 둘, `[self:body]` 쓰기 굴절 `commit` 반영. 봉투의 errors 다이제스트와 '속도의 지렛대=읽은 문자수' 계기, '결정화는 통로 지정까지' 교훈 추가. 라우팅 분포·수치는 파생 마커가 정본. 이력 정본=git log·changelog.log(`[self:body]` 회상).*
