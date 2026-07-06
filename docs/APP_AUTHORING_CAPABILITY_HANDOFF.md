# 앱 저술 능력 강화 — 세션 핸드오프 (2026-07-06)

## 배경 (왜 이 작업인가)
**내부 AI(시스템 AI)에게 부탁해 앱을 만드는 과정이 indiebizOS의 핵심 중 하나**다 — 그래야 사람들이 여러 방식으로 자유롭게 AI를 호출해 쓴다. 그런데 실제 시도(system_ai 가 '빈노트' 앱 제작)는 **외부(Claude Code)보다 못했다**: 11분·강제종료·느린 편집·의식 지시 무시·지식 공백. 이 세션은 "미리 해둘 수 있는 것을 해둬서 빠르고 실수 없이 앱을 만들게" 하는 인프라를 정비했다.

## 커밋
- `1fd9cb7` 앱 만들기 능력 강화: 앱 승격 · 빈노트 인라인 · 저술 가이드 · [self:ask]
- `3df380e` 앱모드 도메인 평탄화 + 흰 아이콘(앱·자율주행)
- **⏳ push 미실행** (main, 로컬).

---

## 한 것 (전부 ✅ 라이브/검증)

### 1. 앱 승격 — 런처 모드 선택기
검색브라우저/자율주행/조종실/앱/비즈니스 아래 구분선에 자주 쓰는 앱을 올려 바로 실행. 승격 앱 = **앱모드 딥링크 바로가기**(`ActionDesktop` `openAppId` prop). 우클릭 승격/빼기 + 드롭다운 ✕. 저장 = `launcher_app_layout.json` `promoted[]`(순서 보존). 백엔드 `launcher_layout.py` + `AppLayoutModel` + `AppLayout` 타입. 라이브 왕복 검증.

### 2. 빈노트(BinNote) = 인라인 계기
별도 창(**갇힘 사고**) → 앱모드 인라인 `el`(ActionDesktop BackBar로 나감). 별도 창 배선(main.js/preload/types/App) **전부 제거**(잔여 0).

### 3. 커스텀 앱 저술 가이드 + 공용 헬퍼 (재사용 가드레일)
- **`data/guides/custom_app_instrument.md`** 신설(guide_db 등록):
  - 철칙0 **능력=기존 어휘 조합, 계기=표현만** ("앱 = 어휘 조합 + 약간의 코딩")
  - 철칙1 **인라인 `el` 기본**(별도창 아님 — 갇힘 방지)
  - 철칙2 **앱모드 `[self:*]`는 `project_id:'앱모드'` 필수**
  - **모델 불문** 도구: 파일=`[self:read/edit/write/grep]`, 빌드검증=`run_command`, 가이드=`read_guide` (Claude Code 네이티브 도구 불필요)
  - 만들기·**수정** 둘 다 · **속도=왕복 횟수**(인라인이 최대 절감·새파일 한번에·codebase_map·배치)
- **`frontend/src/lib/instrument.ts`** 신설:
  - `iblExecuteApp(code)` — `project_id:'앱모드'` **내장**(철칙2를 구조적으로 강제) + 견고한 응답 언랩
  - `askAI(prompt, context?)` — `[self:ask]` 래퍼(원샷)
  - `askSystemAI(message)` — `/system-ai/chat`(도구 쓰는 무거운 동기 대화, 드묾)
  - ✅ BinNote·NewspaperInstrument 이관.
- `new_action_checklist.md` 상단에 커스텀 계기 라우팅 박스.
- **가이드 연상 튜닝**: `_search_guide`(ibl_routing.py)는 키워드 스코어링(단일토큰 정확일치 +2 지배적). 단일토큰 키워드 보강으로 구별 쿼리 전부 1위, 모호한 "앱 만들기"는 new_action_checklist 라우팅 박스가 이중 안전.

### 4. `[self:ask]` — AI 호출도 어휘 (철칙0을 AI에)
동기 원샷 AI 호출이 어휘에 **없던** 공백(있던 건 `[others:delegate]` 비동기 effect뿐 → 빈노트가 raw fetch 재발명)을 메움.
- system_essentials 액션 `ai_ask`, 핸들러가 `consciousness_agent.lightweight_ai_call(role="background")` 로 경량 원샷(도구·다단계 없음).
- `returns: scalar` `{result,text}`, `exempt`(LLM=fixture 부적합). **조합 가능**: `context` 없으면 `_prev_result`를 맥락으로.
- 액션 142→**143**. build --check 통과(pre-commit 삼각검증).
- 해마: `add_examples_batch` +8 · `rebuild_index`(2642) · `ibl_distilled` +12.
- **✅ 라이브 LLM 검증**: 단순("2")·context 요약·**파이프 조합**(`[self:time]{} >> [self:ask]{...}`="오후" 632ms)·빈prompt 방어.
- **AI 호출 세 모양**(대부분 ①): ① 원샷 `[self:ask]`/`askAI`(기본) / ② 위임 `[others:delegate]{scope:system}`(산출물, `report.yaml` 모범) / ③ 무거운 동기 `askSystemAI`(도구+즉답, 드묾).

### 5. 앱모드 도메인 평탄화
도메인→계기 2단 진입 폐지 — 각 계기가 독립 최상위 앱. 계기 하나면 한 번에 열림(뒤로=홈), 여럿 묶던 도메인(내 기기→사진·파일, 부동산→실거래가·상권)은 개별 앱으로 분리. **그룹핑은 사용자 폴더가 담당.**
- `ActionDesktop`: `DOMAINS(Domain[])` → `APPS(App[])`, `domainId/instrumentId` → `openId` 단일. `staticAppsFrom()`가 STATIC 평탄화(el은 매니페스트 주입, soon 제외). `HOME_ORDER`·`STATIC_APP_META` 평탄 id.
- 라이브 매니페스트 대조: 9 static + 18 manifest = 27, 중복 0.

### 6. 흰 아이콘
`DraggableIcon` `whiteTile` 프롭 신설(흰 배경 타일). 앱모드 앱 + 자율주행 프로젝트 아이콘에 적용. 폴더(주황)·스위치(주황)·멀티챗(보라)은 기능 색 유지.

---

## 남은 것 (다음 세션)

### 즉시
- **push** (2 커밋 로컬).

### 후속 (선택, 라이브 검증 필요)
- **헬퍼 미이관 4계기**: ForageBrowser(unwrap 미묘히 다름)·YtMusic·Directions(인라인 per-call)를 `iblExecuteApp`으로. **GenericInstrument는 `>>` 평탄화 특수라 건드리지 말 것.**
- **[self:ask] 완전 연상**: 파인튜닝 임베딩 모델이 self:ask 이전이라 "요약"류 부분 연상 → 다음 재학습 시 완성(`ibl_distilled`에 용례 있음). 재학습 = cloud_training make_bundle→modal_train→apply_model→rebuild_index.
- **평탄화 잔여**: 옛 `realestate`/`device` 위치키가 `launcher_app_layout.json`에 고아로 남을 수 있음(무해, 새 앱은 auto-pos).

### 진짜 남은 과제 — 과정 축 (하네스/프롬프트, 가이드 밖)
"외부가 낫다"의 진짜 원인은 지식이 아니라 **과정**이다. 어휘·가이드로는 못 푼다:
1. **왕복 횟수** — 매 도구 호출이 1 LLM 턴(큰 시스템프롬프트 재소비). 11분÷~30호출≈19s/호출. 가이드에 "왕복 최소화" 원칙은 넣었으나(인라인·배치·codebase_map), 근본은 하네스.
2. **의식 지시 이행 갭** — 의식 에이전트가 좋은 계획(codebase_map 읽어라·plan 먼저)을 냈는데 실행 에이전트가 무시하고 브루트포스. → 이행 강제 메커니즘 필요.
3. **11분 단일 abortable 턴** — 체크포인트로 쪼개 사용자가 중간 개입·재지향 가능하게.
4. **콜드 캐시 97s 의식** — 고정 세금.

**전략(선언형 우선)**: 내부 AI가 실패하는 곳=커스텀 React escape-hatch, 성공하는 곳=작은 선언형 `app:` 블록. 이기는 길 = 어휘를 미리 넓혀 더 많은 앱이 코드 없이 선언형으로 되게 → 실패 경로를 드물게. `[self:ask]`가 그 첫 조각(AI 호출도 이제 선언형 버튼 한 줄).

---

## 핵심 파일
- 가이드: `data/guides/custom_app_instrument.md` (정본), `data/guides/new_action_checklist.md`(라우팅)
- 헬퍼: `frontend/src/lib/instrument.ts`
- 앱모드: `frontend/src/components/ActionDesktop.tsx`, `Launcher.tsx`(승격), `launcher-components/DraggableIcon.tsx`(whiteTile)
- self:ask: `data/packages/installed/tools/system_essentials/{ibl_actions.yaml,handler.py}`
- 관련 메모리: `project_custom_app_instrument_capability`, `app_mode_desktop_personalization`
