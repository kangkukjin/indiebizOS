# 산출물 지각·반성 어휘 핸드오프 (2026-08-26 설계 → **같은 날 집행 완료**)

> **집행 결과 (2026-08-26)**: Phase 0~5 전부 완료. `data/criteria/{visual_base,web}.yaml` ·
> `[engines:render]`(render_artifact.py, ops html/pdf/svg, returns items) · `image_read{op:critic}` 에
> `criteria` param · 워크플로우 **화면검수**($path·$intent·$criteria, 기본 web) 등록 · 시드 13건+
> 코퍼스 이관 14건(해마 7·distilled 2·balanced 5) · `--check` GREEN · pytest 계약 배터리 GREEN ·
> 라이브 실증(렌더 2뷰포트 2.7s → each critic 2행, verdict passed/score 반환).
> 곁수리: `ibl_usage_db._index_single` 의 `INSERT OR REPLACE` 가 vec0 에서 UNIQUE 오류로
> **스테일 벡터를 침묵 잔존**시키던 결함 → DELETE→INSERT 로 근본 수리.
> 잔여: ⏳풀 재학습 대기열 합류(시드 13) · 실사용 관찰(GoalEval 자동 첨부 실전) · 취향 파일 증축은 사용례가 이끈다.

> 목적: 시스템이 자기 시각 산출물(HTML·PDF·SVG·차트)을 **보고 → 기준에 대고 심사하고 → 미달이면 고치는** 반성 루프를 어휘·데이터·문장으로 결정화한다.
> 철학적 배경: 지능은 모델이 아니라 하네스에 축적된다 — 반성을 모델의 호의(즉흥)에서 하네스의 구조(문장)로 승격. 비평이 증발하는 대화가 아니라 축적되는 데이터(취향 파일)가 되게 한다.

## 0. 탐사로 교정된 전제 3가지

1. **`[sense:see]`는 못 쓴다** — 이미 카메라 지표어(android 패키지 `phone_capture`). 눈의 자리는 `engines`(media_producer)가 맞다: Playwright 렌더(`render_html_to_image`)와 비전 심사(`gemini_vision.py`)가 이미 그 패키지에 산다.
2. **`??`는 심판-재시도가 아니다** — 실패/0건 폴백 전용(ibl.md:479). 재시도 루프의 정본은 ① 문장 내 `[repeat: while …, max]` + `[try]/[catch]` ② `[goal:]` 블록 ③ 인지층 GoalEval(3라운드).
3. **지을 것이 생각보다 적다.** 이미 있는 것:
   - HTML문자열→PNG: `engines:render_html` (media_producer/handler.py:793)
   - 비전 심사: `engines:image_read{op:"critic"}` → `{passed, score, issues, notes}` + preset(`slide_illustration`/`general`) + `checks:[]` 임의 추가 (gemini_vision.py)
   - **자동 시각 검수 루프**: `CognitiveEval._collect_visual_artifacts`(cognition/cognitive_eval.py:176)가 도구 결과 문자열의 **절대 이미지 경로를 정규식으로 긁어** 평가자 AI에 이미지 첨부. 즉 렌더 결과 문자열에 절대 png 경로만 넣으면 GoalEval 루프가 **공짜로** 문다.

   **공백 3개**: ① 다형식(PDF·SVG·HTML파일)+다뷰포트 투영 ② 심사 기준의 데이터화(현재 preset checks가 코드 상수 — gemini_vision.py:60) ③ 얼린 문장(워크플로우).

## Phase 0 — 취향 파일 (기준의 데이터화) ★품질 상한 결정자

- 신설: `data/criteria/` (git 추적, 사용자 편집 가능 — registry.yaml/instruments 관례 준용)
  - `visual_base.yaml` — 형식 무관 기본 체크(잘림·겹침·깨짐·저해상도·과다 여백…). 현재 gemini_vision `general` preset의 코드 상수를 이관.
  - `web.yaml` — 웹 전용: 간격 스케일, 타이포 위계, 대비, 반응형(뷰포트별), 금지 패턴, 참조 2~3.
- 스키마(단순 유지): `{extends?: visual_base, checks: [문장…], forbidden: [문장…], references?: [설명…]}`
- 헌법 근거: "명사의 자리" — 취향은 세계의 명사=반증 가능한 데이터. 사용자의 비평("이 조합 금지")이 이 파일의 diff로 내려앉는다.

## Phase 1 — 투영 낱말: `engines:render` (media_producer 확장)

- **개념**: 자기 투영법을 가진 형식의 결정론적 픽셀화. 판단 없음(지각 순수성). 데이터→차트 같은 **표현 판단은 이 낱말 밖**(생성 쪽 소관 — 산출된 차트 HTML/SVG가 다시 이 낱말의 입력이 됨).
- 정의(ibl_actions.yaml):
  - `target_key: op`, ops: `html`(기본) / `pdf` / `svg` — 형식=변형=op(명명법 준수)
  - params: `path`(파일) | `html`(문자열, 하위호환), `viewports: [{width,height,label}]`(기본 1280×720 단일), `output_dir`, `base_path`, `full_page`
  - `returns: items` — 행=스크린샷 `{format, viewport, page?, path(절대)}`. 결과 JSON 문자열에 절대 png 경로 포함 → GoalEval 수집기 자동 연동.
- 구현(전부 기존 의존성, 신규 0):
  - html: 기존 `render_html_to_image` 경로 재사용 + 파일 입력 시 read→`set_content`+`base_path`
  - pdf: **PyMuPDF `get_pixmap()`** — requirements-core에 이미 있고 현재 텍스트 추출만 씀. 페이지당 1행.
  - svg: html 래핑 후 동일 Playwright 경로.
  - Playwright 경로 규약: `backend/base/runtime_utils.setup_playwright_browsers_path()` (in-repo `ms-playwright/`).
- `_OP_DISPATCHERS["render_artifact"] = {"html":…, "pdf":…, "svg":…}` + `_OP_DEFAULTS` — `--check` AST 삼각검증 대상.
- fixture: 내장 미니 HTML 렌더 → Playwright 건강검진을 겸함(chromium 드리프트 조기 발견).
- **`render_html` 은퇴**: 어휘 생애주기 대칭(action_removal.md). 사전 변경=데이터이므로 판정 불요. 단 corpus 의 render_html 용례를 같은 시딩 회차에 `render{op:html}`로 이관(seed_render_vocab.py 계보 확인).

## Phase 2 — 심사 확장 (최소치)

- `image_read{op:"critic"}`에 `criteria` param: 프리셋명 또는 `data/criteria/*.yaml` 경로 → checks 로딩(+`extends` 해석). 기존 `checks:[]` param과 병합 유지.
- **다중 이미지 param 확장은 하지 않는다** — 화면별 심사는 `[table:each]` 조합으로 충분(조합이 param 증식을 이긴다). 화면 간 일관성 심사는 2단계 보류(재론 조건: each 심사가 놓치는 실사례 등장).
- 두 액션의 `achievement_criteria:` 갱신(GoalEval 3티어 추출 대상).

## Phase 3 — 문장 얼리기 (워크플로우 = 함수 한 칸)

- 등록: `검수(path, criteria)` ≈
  ```
  [engines:render]{path: $path, viewports: [데스크톱, 모바일]}
    >> [table:each]{ [engines:image_read]{op: "critic", image_path: $it.path, criteria: $criteria} }
  ```
- **뼈대만 얼린다**: 문장의 책임은 지각+심사(발견 items 산출)까지. 수정은 호출자(모델/goal)의 몫 — 얼린 루프는 시킨 것만 보지만 즉흥은 목록 밖도 보므로.
- 재시도 형태 2종은 시드로만 가르침: ① `[repeat: while …, max:3]`+`[try/catch]` 결정론 버전 ② `[goal:]`/GoalEval 위임 버전(렌더가 절대 경로를 뱉으므로 자동 작동).

## Phase 4 — 시딩·재색인

- `.venv/bin/python3` 필수, `db._load_model_sync()` assert 선행(_index_batch는 실패를 삼킨다), `add_examples_batch` 단일 경로, `data/training/ibl_distilled.json` 병기.
- 10~30건: render 3형식×뷰포트 변주 + 검수 문장 + repeat/goal 두 재시도 형태 + render_html 이관분.
- 후처리: `rebuild_index()` → `scripts/ibl_param_sweep.py`.

## Phase 5 — 검증·문서·재기동

- `python3 scripts/build_ibl_nodes.py && --check` / `scripts/ibl_health_check.py` GREEN / `POST /ibl/execute` 실행 / checklist §5.5 계약 노크(0건·실패 정직성, viewports 오용 거절).
- 문서 표면: new_action_checklist 규약대로(마커 구간은 빌드가 재생성). criteria 파일 편집법은 `data/guides/`에 한 쪽.
- **재기동 주의**: 신규 서브모듈 파일은 `/packages/reload`로 안 산다 — 백엔드 재기동 필요.

## 곁가지(이번 범위 밖, 별도 처리)

- `engines:web{op:"snapshot"}` desc 드리프트: 문서는 "사이트 스크린샷", 구현은 파일트리+git 요약(web-builder/tools/snapshot.py). → 별도 수리.
- `CognitiveEval._VISUAL_EXTS`에 pdf/svg/html 부재 — render 어휘가 PNG로 내리므로 당장은 무해. render 정착 후 재평가.
