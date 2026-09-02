# 첫 성공 온보딩 · 업그레이드 트랜잭션 핸드오프

> **2026-09-02 진행 상태 — ①·② 구현 완료(같은 날, 미커밋).** 사용자 판정 2건 확정:
> (1) 은퇴 코어 파일 = **격리 이동**(`data/_backups/<날짜>_upgrade/retired/`, 실삭제 아님) —
> 매니페스트 차집합은 기계 계산이라 오판(런타임 생성물로 바뀌어 추적에서 빠진 파일 등)이
> 복구 가능해야 한다. (2) GUIDE "외부 하네스 사실상 필수" = **시점 이동** — 설치 대장장이 이유는
> 온보딩이 대체하므로 삭제, 복구 경로 이유는 원문 그대로 "정비소" 절로 독립(첫 성공 뒤).
> 아래 계획에서 실제 구현이 달라진 곳은 각 항목의 **[구현]** 줄이 정본이다.

2026-09-02. OpenClaw 2.0 발표문(https://openclaw.ai/blog/openclaw-2-accidentally)을
IndieBiz OS 와 대조한 대화에서 사용자가 채택한 두 과제. 이 문서는 그 두 과제의
현황 실측·목표·작업 계획·관문을 담는다. 두 과제는 독립이지만 뿌리가 같다 —
**"설치 완료"와 "사용 가능"은 다른 상태인데, 지금은 둘 다 그 차이를 기계가 재지 않는다.**

대조에서 **기각·한정**한 것(다시 꺼내지 말 것):
- 인계 캡슐(다른 사람이 내 세션에 들어와 관찰·인수) — 팀 제품의 필요. telos(1인 인지
  외골격)와 맞지 않고, 몸 대 몸 통신(others/포털/이웃)이 그 자리를 이미 채운다. 열린 질문으로만 둔다.
- "기존 ChatGPT·Claude 로그인 재사용" — 벤더 구독 위에 앉는 통로를 **신설**하지 않는다
  (avoid_vendor_layer). 이미 존재하는 무키 프로바이더 3종(claude_code·codex·ollama,
  `backend/base/model_resolver.py` `_NO_KEY_PROVIDERS`)과 환경변수 키·로컬 모델을 **탐지**하는
  데까지만 간다. 새 로그인 경로 0.
- 묶음 릴리스 — OpenClaw 가 7주 밀린 이유. 우리는 main 직접 커밋이라 반대편 위험(설치
  사용자에게 릴리스 경계가 없음)을 진다. 그 위험은 ②가 받는다.

---

## ① 첫 성공 온보딩 — 종료조건을 "키 입력"에서 "첫 응답"으로

### 현황 (실측, 2026-09-02)

| 자리 | 지금 | 문제 |
|---|---|---|
| GUIDE.md 107~121 · 169~174 | 기둥① = "AI API 키 + 외부 하네스(사실상 필수)". 체크리스트 2단계 "키 입력 → 시스템 AI 깨어남" | 종료조건이 *설정*이지 *성공*이 아니다. 키를 넣었는데 모델명이 틀리거나 잔액이 없으면 첫 대화에서 처음 안다 |
| `backend/surface/api_system_ai.py` `/system-ai/welcome` | `needs_api_key: True` 고정 + "Claude/GPT/Gemini 키 입력" 정적 안내 | 무키 프로바이더(claude_code·codex·ollama)가 이미 잡혀 있어도 키를 넣으라고 한다 |
| 같은 파일 `/system-ai/status` | `has_api_key = bool(config.apiKey)`, `ready = has_api_key and enabled` | **`provider_needs_api_key` 를 안 지난다.** model_resolver 의 ★규약("키가 있나로 쓸 수 있나를 판정하는 자리는 전부 이 함수를 지날 것", 2026-08-17 사고)의 잔존 위반. 프론트 소비처(`ChatView.tsx:182`)가 `provider` 만 읽어서 아직 사고가 안 났을 뿐 |
| `backend/surface/api_env.py` `/config/env/test` | 도구 키(날씨·부동산 등)는 카탈로그 `test` 스펙으로 실사용 검증 | **시스템 AI 의 프로바이더·모델·키 조합을 실응답으로 검증하는 자리는 없다** |
| `backend/providers/ollama.py` | `localhost:11434` 고정 | 어떤 모델이 당겨져 있는지 묻지 않는다(`/api/tags` 미사용) |
| `backend/providers/cli_provider.py` 218~230 | `shutil.which` 로 명령 존재 확인 | MCP 설정 재생성 맥락에서만. "이 기계에 claude/codex 가 있고 로그인돼 있다"를 온보딩이 쓰지 않는다 |
| `frontend/src/components/Launcher.tsx` 266~ · `GuideDialog.tsx` | 첫 실행 = `localStorage.indiebiz_has_seen_guide` 로 설명 다이얼로그 1회 | 설명이지 상태기계가 아니다. 어디까지 됐는지 아무도 모른다 |

### 목표

설치 → **사용 가능한 AI 탐지** → **실제 한 문장 응답 확인** → 첫 대화. 여기까지가 온보딩이고
그 뒤(Cloudflare·도메인·폰·채널)는 첫 성공 이후 필요가 생길 때 시스템 AI 가 제안한다.
GUIDE 의 "최소 동작" 정의가 "키 입력"에서 "첫 응답"으로 바뀐다.

### 작업 계획 (A→E, A 는 독립 수리라 먼저)

**A. `/system-ai/status` 의 ready 판정 근본 수리** (작음, 독립) — ✅ [구현] `api_system_ai._system_ai_readiness`(welcome 도 파생) · `backend/test_system_ai_ready.py`(T4=surface 부류 관문)
- `ready = enabled and (not provider_needs_api_key(provider) or has_api_key)`.
  `has_api_key` 는 그대로 노출하되 의미를 "키 칸이 차 있다"로 한정.
- 회귀: `backend/test_system_ai_ready.py` — provider=claude_code·키 빈칸 → ready True;
  provider=anthropic·키 빈칸 → False. (08-17 사고의 동류 부류 관문 — 이 자리만 고치지 말고
  `grep -rn "apiKey" backend/surface | grep -v provider_needs_api_key` 로 같은 부류를 먼저 훑을 것.
  사람이 고른 범위는 샌다 — 부류 스윕은 관문을 먼저 쓴다.)

**B. 후보 탐지 `GET /system-ai/candidates`** — ✅ [구현] `backend/base/ai_candidates.detect_candidates` · 카탈로그 `data/ai_provider_catalog.yaml`(model_resolver 의 env 표도 여기서) · 라우터 `backend/surface/api_onboarding.py` · `test_onboarding_candidates.py`
- 반환 `{items:[{provider, model, source, needs_key}]}` (통화 = items 하나).
- 탐지원 3종, 순서대로: (1) 환경변수·`.env` 의 알려진 키(ANTHROPIC_API_KEY·OPENAI_API_KEY·
  GEMINI_API_KEY·OPENROUTER_API_KEY·DEEPSEEK_API_KEY) (2) `shutil.which("claude"|"codex")`
  + 로그인 여부(각 CLI 의 자격 파일 존재만, 값은 읽지 않음) (3) `http://localhost:11434/api/tags`
  (타임아웃 1초, 실패=후보 없음, 오류 아님).
- **탐지 규칙은 데이터**(`data/ai_provider_catalog.yaml` 같은 자리 — 프로바이더별 env 이름·
  CLI 명령·기본 모델). 세계의 명사(어느 벤더의 어떤 환경변수 이름)는 반증 가능한 데이터로,
  코드에 벤더 이름을 늘어놓지 말 것(nouns_place). `api_env.py` 의 카탈로그 패턴을 그대로 쓴다.
- 자리: `backend/surface/` (표면) + 탐지 함수는 `backend/base/model_resolver.py` 옆 새 모듈
  (`check_backend_layers.py` LAYERS 배정 잊지 말 것).

**C. 실응답 검증 `POST /system-ai/probe`** — ✅ [구현] `ai_candidates.probe`(실패 kind 12종, 원문 동봉) · `test_onboarding_probe.py`
- 입력 `{provider, model, api_key?}`. 저장하지 않고 oneshot 1턴("한 단어로 답하세요: 준비됐나요?")
  호출 → `{ok, reply, latency_ms, error}`. 키 틀림·모델명 오타·잔액 0·CLI 미로그인이 **각각 다른
  문장**으로 돌아와야 한다(정직 — "설정되지 않았습니다" 하나로 뭉개지 말 것).
- 성공 시에만 프론트가 저장 요청을 보낸다(검증 → 저장 순서. 저장 → 실패 발견 순서가 지금의 문제).
- 재사용: `api_env.py` 의 test 정신, `model_resolver.resolve` 의 provider 캐시(키가 달라지면
  캐시 키가 달라져 자동 교체 — probe 가 캐시를 오염시키지 않는지 확인).

**D. 첫 실행 표면 = 상태기계** — ✅ [구현] `frontend/src/components/OnboardingDialog.tsx`(loading→pick→probing→verified/failed, 검증 뒤 저장, "첫 대화 시작"=시스템 AI 창) · 상태 원장 `backend/datastore/onboarding_state.py`(`first_reply_at` 은 `save_conversation("assistant")` 한 곳에서 기록) · Launcher 첫 실행 = 온보딩 → 가이드
- GuideDialog 를 "후보 목록 → 선택(또는 직접 입력) → probe → 첫 대화로 이동" 4상태로.
  후보가 1개면 선택을 건너뛰고 바로 probe. 후보 0 이면 지금의 키 발급 안내.
- `/system-ai/welcome` 의 `needs_api_key` 를 고정값에서 status 파생으로. 정적 문구에서
  벤더 3종 나열 제거(후보 목록이 대신 말한다).
- 완료 표식은 localStorage 가 아니라 서버(`data/onboarding_state.json`: `first_reply_at`).
  원격 런처·다른 표면에서도 같은 상태를 본다(3표면 파리티).
- 첫 성공 뒤 Cloudflare·폰 제안은 **시스템 AI 의 첫 대화 프롬프트에 한 줄**로 — 새 다이얼로그 0.

**E. 문서** — ✅ [구현] GUIDE.md/GUIDE_EN.md 기둥①="사용 가능한 AI(첫 응답)", 정비소 절 신설, 체크리스트 2·6 · technical.md API·설정 절 (★공개 문서 문장은 사용자 검토 대상)
- GUIDE.md 기둥①·체크리스트: "최소 동작 = 첫 응답". "외부 하네스 사실상 필수" 문구는
  **사용자 판정** — 첫 성공까지는 하네스 없이 도달 가능해지므로 "설치 위임 선택지"로 낮출지
  사용자가 정한다(문구 하나지만 제품 정의라 묻는다).
- technical.md API 절에 candidates/probe 추가. `data/guides/new_action_checklist.md` 는
  해당 없음(새 IBL 낱말 0 — 전부 표면 기능. 어휘로 승격하지 말 것).

### 관문
- `backend/test_system_ai_ready.py`(A) · `backend/test_onboarding_candidates.py`(B — env/which/
  ollama 를 스텁으로 3원천 각각 후보를 만든다, ollama 다운=빈 목록·200) ·
  `backend/test_onboarding_probe.py`(C — 실패 4종이 서로 다른 문장).
- `scripts/ci_boot_smoke.py` 확장: /health 뒤 `/system-ai/candidates` 200 (빈 CI 에서 items=[]).
- 실기: 빈 사용자 데이터로 앱 기동 → ollama 만 있는 기계 → 첫 대화까지 키 입력 0 회.

---

## ② 업그레이드 트랜잭션 — 기존 설치본을 깨지 않는 관문

### 현황 (실측, 2026-09-02)

| 자리 | 지금 | 구멍 |
|---|---|---|
| `scripts/bootstrap.py` | 정본 설치 = git clone + 이 레시피(헌법 canonical-install-path). CI `portability.yml` boot-smoke 가 매 푸시 **빈** 트리 부팅을 증명 | **노후 설치본** 위의 업그레이드는 아무도 증명하지 않는다 |
| `frontend/electron/bootstrap.js` `initUserData`·`syncDirOverwrite` | resources → userData 를 `copyFileSync` 로 직접 덮어씀. 확장자 규칙(.py/.js/.md…)+`core_manifest` 술어. `.db` 보존은 "확장자 목록에 없음"으로 **암묵**. `common_prompts` 는 rm+cp | 원자성 0, 사전 백업 0, 롤백 0. 중간에 죽으면 반쯤 갱신된 설치본. 테스트 0(참조하는 파일이 자기 자신뿐) |
| `scripts/build_core_manifest.py` · `data/core_manifest.json` | `git ls-files` 파생, 키 = `core` 하나 | **은퇴 목록 없음**(`retired` grep 0건). 옛 설치본엔 사라진 코어 파일이 영원히 남는다 — 은퇴 어휘 `.yaml` 이 stale 하던 08-31 윈도우 실전 사고의 뿌리와 같은 부류 |
| `backend/datastore/*.py` 8개 | `CREATE TABLE IF NOT EXISTS`, `PRAGMA user_version`·schema_version **0건** | 컬럼 추가는 파일마다 ad hoc. `backend/migrate_*.py` 3개는 일회성 수동 스크립트 |
| `backend/datastore/red_watchdog.py` `_rollback` | 자기수리(RED 쓰기)는 manifest `{files: path→backup|null}` + 감시견 + /health 판정 + 롤백 | **비대칭**: 파일 한 줌 고치는 자기수리엔 트랜잭션이 있고, 설치본 전체를 갈아끼우는 업그레이드엔 없다 |

### 목표

릴리스 관문 5종을 **체크리스트가 아니라 실패하는 테스트**로(no-counter-watch):

| 관문 | 상태 | 담당 |
|---|---|---|
| 빈 설치본 부팅 | ✅ 있음 (`ci_boot_smoke.py`) | — |
| 노후·개인화 설치본 업그레이드 부팅 | ❌ | B |
| 사용자 소유물 보존(DB·설정·자작 앱·패키지 활성상태) | ❌ (설계는 됨, 증명 없음) | B |
| 실패 시 원상복구 | ❌ | D |
| 은퇴 코어 파일 잔존 검사 | ❌ | C + B |

### 작업 계획 (B 먼저 — 관문을 먼저 쓰고 고친다)

**B. 노후 설치본 픽스처 + 업그레이드 스모크** (`scripts/make_aged_install.py` · `scripts/ci_upgrade_smoke.py`) — ✅ [구현] 직전 태그 worktree → 옛 부팅 → 개인화(태그 이후 상류 변경 없는 최소 패키지 끔·자작 패키지·파일·설정·DB 행·옛 액션명 행·은퇴 예정 어휘 조각) → 경로 B(설치본 동기화, resources=지금 트리의 배포 집합 근사) → 경로 A(git pull 등가 = 상류가 바꾼 파일만) → 부팅·보존·롤백·은퇴 단언. 로컬 실측 통과(v1.5.2 → 작업 트리).
  ★발견→✅닫힘(같은 날): git 경로에서 패키지 켜고/끄기 = 추적 디렉토리 이동이라 상류가 그 패키지를 바꾸면 맨손 `git pull` 이 상류가 고친 파일만 옛 자리에 되살려 **반쪽 패키지**를 만든다(ai-ops 로 실측: installed/ 에 tool.json 등 일부만 부활). 뿌리 = **업그레이드 레시피 부재**(bootstrap.py 만 있고 짝이 없었다, 문서에 git pull 0회). 처방 = `scripts/update.py`: 사용자 배치 걷기 → ff pull → 재적용(실패 시 원복, 양쪽 존재=충돌 신고). 폴더 위치=진실 규칙은 유지 — 런타임 독자 20여 곳(tool_loader·api_packages·portal·bulletin…)을 오버레이로 바꾸는 건 과대. 픽스처는 이제 **상류가 바꾼 패키지를 우선** 끄고(어려운 경우), 경로 A 는 깨끗한 트리(CI)에서 진짜 레시피를 돌린다. 진짜 레시피는 worktree 실측(v1.5.2→HEAD, ai-ops 이동)으로 확인.
- 픽스처: 직전 태그(`git describe --abbrev=0`)를 `git worktree` 로 꺼내 `bootstrap.py --core-only`
  → 개인화 주입: 코어 패키지 1개를 not_installed 로, 사용자 패키지 1개 추가(`origin=user`),
  자작 앱 1개, `business.db` 행 N, 설정 키, 프로젝트 1개, 사용자 어휘 yaml 1개 → **소유물 해시
  스냅샷**(경로→sha256, DB 는 행수+컬럼 목록).
- 적용 두 경로: (1) git 경로 = 그 트리에서 HEAD 로 checkout 후 부팅 (2) 포장 경로 =
  `node -e "import('./frontend/electron/bootstrap.js').then(m=>m.initUserData())"` 를
  resources/userData 를 임시 폴더로 돌려 호출(이미 export 돼 있음 — `app.getPath` 만 주입 가능하게).
- 단언: /health 200 → 스냅샷 해시 불변 · 패키지 활성상태 불변 · DB 행수 불변+새 컬럼 존재 ·
  은퇴 목록(C)의 경로가 dest 에 없음 · `build_ibl_nodes.py --check` 초록(파생물 신선).
- `pytest.ini` 는 backend/ 만 수집 — 이 스모크는 CI 잡으로(F). 로컬은 `python3 scripts/ci_upgrade_smoke.py`.

**C. 은퇴 목록** (`build_core_manifest.py` `retired` 구간) — ✅ [구현] 직전 매니페스트(작업 트리 파일) core 와의 차집합을 누적, 돌아오면 해제. `userdata_sync.quarantineRetired` 가 격리 이동(판정 (1)). 현재 retired 는 전부 빈 배열.
- 빌드 때 직전 커밋된 매니페스트의 `core` 와 현재 `git ls-files` 차집합을 `retired` 에 **누적**
  (커밋됨, 빈 배열이 정상). `bootstrap.js` 는 dest 에 `retired` 경로가 있으면 제거 — 단
  판정은 "매니페스트가 코어였다고 기억하는 것"만, 사용자 파일은 이름이 같아도 건드리지 않는다
  (사용자 것은 애초에 core 에 없었으므로 자동 분리).
- ★**실삭제 vs `data/_backups/YYYY-MM-DD_upgrade_retired/` 격리 이동 — 사용자 판정**
  (파괴적 변경 부류). 기본 제안 = 격리 이동 + 30일 규약(백업 README).

**D. 트랜잭션화** (`bootstrap.js`) — ✅ [구현, 설계 변경] 스테이징 폴더 스왑이 아니라 **저널 트랜잭션**(`frontend/electron/userdata_sync.js`, electron 무의존): 덮어쓰기 전 원본 백업+저널 한 줄(JSONL) → `data/.upgrade_pending` 표식 → 완료 시 회수 · 도중 죽음은 다음 기동이 되감고 재동기화 · 내용 같은 파일 무변경. 이유: userData 의 사용자 DB(해마·포식 수백 MB) 통째 복사가 무겁고, 동기화가 건드리는 범위(코어 파일)만 저널이 정확히 덮는다 — red_watchdog 의 `{path→backup|null}` 형식과 같은 꼴. "/health 실패 시 롤백"은 채택 안 함: 설치본 경로에선 앱 바이너리를 되돌릴 수 없어 데이터만 되돌리면 새 코드↔옛 데이터 불일치가 더 나쁘다. 트랜잭션의 의미 = 원자성(전부 또는 전무)+수동 복구용 백업.
- `initUserData` 를 3단으로: 스테이징(`userData/_staging_<ts>/` 에 전체 적용) → 검증
  (필수 파일 존재·JSON 파싱·`core_manifest` 일치) → 디렉토리 단위 rename 스왑. 실패는 어느
  단에서든 스테이징 삭제 = 이전 설치본 무손상.
- 스왑 직전 사용자 소유물(DB·설정 JSON·installed 배치)을 `data/_backups/<날짜>_upgrade/` 로
  `VACUUM INTO`/복사. 매니페스트 형식은 `red_watchdog` 의 `{files: path→backup|null}` 재사용
  (두 트랜잭션이 한 형식을 쓰면 롤백 코드도 하나로 수렴할 수 있다 — 지금은 재사용만, 통합은 뒤).
- 부팅 후 /health 실패 시 롤백은 **keeper 가 아니라 다음 기동의 Electron** 이 맡는다(자기 죽음
  뒤 단계를 계획에 넣지 말 것 — 스왑 직후 `data/.upgrade_pending` 표식, 첫 /health 200 이 지운다.
  다음 기동에 표식이 남아 있으면 백업 복원).
- 관문: B 에 "중간 실패 주입"(스테이징 중 예외) 케이스 추가 → 이전 설치본 해시 불변.

**E. 스키마 버전** (`backend/datastore/schema_migrations.py`) — ✅ [구현] `PRAGMA user_version` 레지스트리, ibl_usage·world_pulse v1(옛 액션명 개편 흡수), `_init_db` 훅 2곳, `test_schema_migrations.py`. **"부팅 거절"은 "서브시스템 실패 기록(boot_status → /health degraded)"으로** — 마이그레이션은 트랜잭션이라 반쯤 적용된 DB 는 없고, 정직한 실패 표시가 기존 부팅 교리와 맞는다. `migrate_storage_action.py`·`migrate_cctv_action.py` 은퇴, `migrate_nodes.py` 는 유지(프로젝트 agents.yaml 대상, --reverse 보유 — 다른 부류).
- `PRAGMA user_version` + 단일 마이그레이션 레지스트리(DB 파일별 `[(version, sql|fn)]`).
  8개 파일의 `CREATE TABLE IF NOT EXISTS` 는 version 0 으로 흡수, 이후 컬럼 추가는 여기에만.
  부팅 시 자동 적용, 실패 = **부팅 거절**(반쯤 마이그레이션된 DB 로 뜨지 않는다 — 정직).
- `migrate_storage_action.py`·`migrate_cctv_action.py`·`migrate_nodes.py` 는 이미 적용된 몸이
  대부분이므로 은퇴(C 의 첫 손님). 적용 안 된 몸이 있을 가능성은 B 픽스처가 잡는다.
- 관문: `backend/test_schema_migrations.py` — version 0 DB 에 전체 적용 후 컬럼 목록 = 최신 스키마,
  중간 버전에서 재적용 시 멱등.

**F. CI** — ✅ [구현] `portability.yml` `upgrade-smoke`(ubuntu, fetch-depth 0 + node 22) · BUILD.md "릴리스 관문" 절.
릴리스 태그는 이 잡 초록이 전제(version-tag-sync 규약에 한 줄 추가).

### 순서와 판정
- 순서: **B → C → E → D → F**. B 없이 C·D·E 를 하면 "고쳤다"를 증명할 자리가 없다.
- 사용자 판정 2건 — ✅ 확정(머리 참조): (1) 격리 이동 (2) 정비소 절로 시점 이동.
- 남은 열린 것: 온보딩 UI 실기(빈 사용자 데이터로 앱 기동 → ollama 만 있는 기계 → 키 입력 0회) 는 아직 실측 전.
- 문서 갱신 의무: BUILD.md(릴리스 관문 5종), technical.md(스키마 버전·백업 경로), `data/_backups/README.md`
  (upgrade 백업 항목), system_docs 꼬리.

### 하지 말 것
- 카운터·로그로 "얼마나 자주 깨지나 두고 보기" — 셀 수 있으면 관문이 실패시킨다.
- 파생물(`core_manifest.json`·`ibl_nodes.yaml`·`tool.json`) 손 편집 — 빌드가 되돌린다.
- 자동 업데이터(원격 다운로드·자기 교체) 신설 — 이 과제는 **이미 있는 두 경로**(git pull·설치본
  동기화)를 트랜잭션으로 만드는 것이지 세 번째 경로를 여는 것이 아니다.
