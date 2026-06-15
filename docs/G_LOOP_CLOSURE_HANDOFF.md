# G 루프 닫기 — 비평(critique) 루프 통합 핸드오프

> 작성: 2026-06-15. 목표 = 산출물 생산의 G 단계(render → 보고 → 판단 → 수정)를 닫아
> "빠르고 안정적"의 *안정* 절반을 채운다. **부품은 이미 있다. 배선이 안 됐을 뿐이다.**

---

## ✅ 진행 상태 (2026-06-15)

**Phase 1 (Option A — 슬라이드 이미지 경로 inner loop) 완료·종단검증.**
- 배선 위치: `data/packages/installed/tools/media_producer/slide_image.py`
  - 신설 `_critique(img_path, scene, style)` — 합성 *전* 원시 일러스트를 Gemini Vision으로 평가. `_gen_image`과 **같은 `_system_ai_config()` apiKey**(=Gemini AIza 키) 사용 → 키 불일치 회피. **fail-open**: 키부재/읽기실패/VLM실패 시 `{passed:True,_error}` 반환(산출 안 막음).
  - 신설 `_gen_with_critique(...)` — 생성→critique→수정 루프. 통과/ fail-open 시 조기종료, 끝까지 실패 시 **최고 점수본 채택**, 수정 라운드는 issues+무텍스트/여백 규칙을 일러스트 프롬프트에 영어 교정으로 되먹임.
  - `create_image_slide` step2를 루프로 교체, 결과 JSON에 `critique:{passed,score,issues,notes,error,rounds}` 노출. 파라미터 `critique`(기본 True, opt-out)·`critique_rounds`(기본 2).
- 동작 기본값(사용자 결정 대신 채택): **critique ON by default**(프리미엄 일러스트 경로는 품질 민감) · 라운드 **2** · 모델 **gemini-3-pro-preview→2.5-pro 폴백** · opt-out=`critique:false`.
- 검증: 라이브 `/ibl/execute [engines:slide]{style:ink_blueprint}` → 1라운드 통과(score10) 결과 부착 ✓. 결정적 단위테스트로 실패→수정(교정주입·round2 채택)·끝까지실패(최고점7 채택)·fail-open(1회종료) 전부 통과 ✓. slide_image.py는 slide_author가 매 호출 fresh load → **reload 불필요**.
- ⚠️ 텍스트-HTML 슬라이드 경로(`slide_author.create_slide`)는 전용 inner loop 미적용 — 단 **Option B 보편 백스톱이 덮음**(평가자가 렌더된 슬라이드 PNG를 직접 봄). 향후 더 타이트한 루프가 필요하면 slide_image 선례대로 추가.

**Phase 3 (Option B — 인지 평가자가 픽셀을 봄, 보편 백스톱) 완료·종단검증.** ★G의 핵심 — 슬라이드뿐 아니라 차트·신문·이미지·웹 등 *모든* 산출 작업이 기존 achievement_criteria 기계를 통해 자동으로 시각 판단을 얻음.
- `consciousness_agent.lightweight_ai_call`에 `images` 파라미터 추가 → `provider.process_message(images=...)`로 전달. 경량 프로바이더(google gemini-3.1-flash-lite)가 비전 가능. None이면 기존 텍스트 동작 그대로.
- `agent_cognitive.py` 신설 `_collect_visual_artifacts(response, tool_calls, max_images=3)` — tool_calls의 input/**result(예 image_path)**/응답텍스트에서 raster 이미지 경로를 모아 `{base64,media_type,_path}`로 인코딩. **`_collect_created_files`가 이미지를 텍스트로 읽어 버리던 물리적 원인을 우회.** 6MB/3장 상한.
- `_evaluate_achievement(... visual_artifacts=None)` — 시각 산출물 있으면 "## 시각 산출물 검수" 프롬프트 + `lightweight_ai_call(images=...)`로 평가자가 직접 봄. `_run_goal_evaluation_loop`가 수집·주입. **전부 추가형·기본값 보존**(이미지 없으면 기존과 동일), 멀티모달 실패 시 기존 except가 통과 처리(fail-safe).
- `data/common_prompts/evaluator_prompt.md`에 시각 검수 지침 추가.
- 검증: T1 수집기 결정적(이미지만 골라 base64, txt 제외, result의 image_path 추출) ✓ · T2 멀티모달 종단(경량모델이 테스트 이미지의 "42"를 실제로 읽음) ✓.

**critic 일반화 + verdict 공유통화 완료.** `engines:image_critic`(`critique_gemini_image`)에 `preset` 파라미터 — 기본 `slide_illustration`(현행, 비파괴) | `general`(임의 산출물: intent 충족·시각결함 체크). src `engines.yaml` 설명 갱신 + build --check 통과(액션 124). verdict 모양 `{passed,score,issues,notes}`를 슬라이드 inner loop·image_critic 공통 통화로 유지. 검증: T3a 범용/일치=10점 통과 · T3b 범용/불일치=0점 실패(구체 issue) · T3c 슬라이드 기본 preset 그대로 동작 ✓.

> **★ G 루프 = 완료.** 플래그십 일러스트=전용 강한 inner loop(pro-critic) + 모든 산출물=보편 평가자 비전 백스톱. 라이브 백엔드 반영(packages/reload + 백엔드 모듈 자동 reload, /health 정상).

**남은 것(= 다음 세션, G 아님):** 척추의 다른 칸 — C 공유 IR(engines가 저마다 다른 입력=스위치더미) · B 구조화 원자 · sense:host(맥 자기몸 감각) · 데이터 통화 표준(체이닝 `{{_prev_result}}` 문자열·타입無).

---

## 0. 왜 이걸 먼저 하는가 (맥락)

IBL을 "산출물 생산의 척추" A~G로 보면(A획득·B구조화·C공유IR·D배치·E스타일·F렌더·G비평):
- **A(sense:* 40개)·F(render 라이브러리)는 강하다.**
- **G는 부품이 있는데 고아다** ← 이번 작업.
- C(공유 IR)·B(구조화 원자)·sense:host(자기몸 감각)는 다음 과제(별도 핸드오프 예정).

G가 닫히면: 생성한 슬라이드/이미지/문서를 *직접 보고* 의도와 어긋나면 *고친다.* 지금은 만들고 끝(blind).

---

## 1. 현재 상태 (코드 실측 — 다음 세션은 재조사 불필요)

### 1-1. G 부품은 이미 존재한다 (슬라이드용으로 정교함)
- IBL 액션 **`engines:image_critic`** — `data/ibl_nodes_src/engines.yaml:327` (router: handler, tool: `critique_gemini_image`, `runs_on: mac_only`)
- 핸들러 **`critique_gemini_image(tool_input, output_base)`** — `data/packages/installed/tools/media_producer/handler.py:790`
  - 입력: `image_path`(절대경로 또는 data URI, 필수) · `intent`(자연어, 필수) · `checks[]`(추가체크) · `style_preset` · `model`(옵션)
  - 반환: 사람용 요약 + `verdict_json: {passed: bool, score: 0-10, issues: [...], notes: "..."}`
  - 모델: `gemini-3-pro-preview` → 404 시 `gemini-2.5-pro` 폴백. `GEMINI_API_KEY` 필요.
  - ⚠️ **기본 체크가 슬라이드-일러스트 전용이다** (다이어그램형인가/한글 미포함/빈 공간/객체 명확성/디자인톤). → 일반 산출물(차트·문서·웹)에 그대로 쓰면 false-fail 난다. 일반화는 Phase 3 과제.

### 1-2. 인지 평가 루프는 이미지를 *물리적으로 못 본다*
- **`_run_goal_evaluation_loop`** — `backend/agent_cognitive.py:1427`
  - 피드백 주입 재시도 루프. `max_rounds` 기본 2. severity(1~3)별 재시도 디렉티브.
  - **이게 "revise" 패턴의 선례다** — 새로 만들지 말고 이 구조를 그대로 따라라.
- **`_evaluate_achievement`** — `agent_cognitive.py:1317`
  - `lightweight_ai_call(prompt, system_prompt)` 호출 = **텍스트 전용 모델.** 이미지 입력 경로 없음.
- **`_collect_created_files`** — `agent_cognitive.py:1225`
  - 파일 경로를 수집한 뒤 **`open(path, 'r', encoding='utf-8')`로 텍스트 읽기.**
  - → **PNG/이미지는 바이너리라 읽기 실패 → `except: pass`로 조용히 스킵.**
  - **결론: 생성된 시각 산출물은 평가자에게 완전히 안 보인다.** 이게 G가 안 닫힌 물리적 원인.
- 평가 프롬프트 — `data/common_prompts/evaluator_prompt.md` (비전 항목 없음, 텍스트·도구trace·파일내용만).
- 슬라이드 프로토 `backend/_slide_proto.py` 엔 비평 루프 없음(수동 데모).

---

## 2. 핵심 설계 결정 — 두 통합 고도 (★사용자 결정 필요)

비평 루프를 *어느 고도*에서 닫을지가 갈림길이다.

### Option A — 액션 내부 루프 (inner loop) ★1차 권장
산출 액션 자신이 `생성 → critique → 수정`을 내부에서 돈다. 예: `engines:slide`가 PNG를 뽑은 뒤
`critique_gemini_image`를 호출, `passed=false`면 issues를 생성 프롬프트에 되먹여 재생성(N라운드).
- 장점: 국소적·결정적·재사용 가능, **인지 코어를 안 건드림(저위험)**. critic이 이미 슬라이드 튜닝됨.
- 단점: producer마다 개별 배선 필요.

### Option B — 인지 외부 루프 (outer loop) — 보편 백스톱
평가 에이전트가 *픽셀을 보게* 만든다(§1-2의 세 함수 개조).
- 장점: 모든 산출 작업이 시각 판단을 공짜로 얻음, 기존 achievement_criteria 기계에 합류.
- 단점: **인지 코어를 건드림(고위험)**, 비전 가능 모델 필요, critic 기본체크 일반화 필요, 비-이미지 산출물(docx/xlsx/html)은 "먼저 이미지로 렌더" 단계가 선행돼야 함.

**권장 경로: A를 슬라이드에 먼저(가치 입증·저위험) → 그 다음 B를 보편 백스톱으로.**

---

## 3. 작업 분해 (단계별)

### Phase 0 — 정찰 (다음 세션 첫 작업, 30분)
1. `media_producer/handler.py`의 실제 슬라이드 producer 읽기 — `generate_slide`류 / `slide_shadcn` (라인은 `grep -n "def generate_slide\|def.*slide_shadcn" handler.py`). **이미 critic을 부르는지** 확인, PNG가 만들어지는 정확한 훅 지점 찾기.
2. 런타임 env에 `GEMINI_API_KEY` 있는지 확인.
3. §2 스코프를 사용자와 확정 (A만 / A→B).

### Phase 1 — Option A: 슬라이드 inner loop
1. 슬라이드 producer 끝(PNG 생성 직후)에 루프 삽입:
   `critique_gemini_image(image_path=<png>, intent=<슬라이드 instruction/content>, style_preset=<design_system>)`.
2. `verdict.passed == false` && 라운드 남음 → issues를 생성 프롬프트에 되먹여 재생성. **`_run_goal_evaluation_loop`의 피드백 주입 패턴 복제.** 라운드 상한 = 2(시작값).
3. `intent`는 슬라이드의 instruction/content가 이미 담고 있으니 통과만.
4. 비용 제어: `critique: false` 같은 opt-out 파라미터. 최종 verdict를 액션 결과에 노출.

### Phase 2 — verdict를 공유 통화로 (작지만 곱셈효과)
- `{passed, score, issues[], notes}` 모양을 *재사용 가능한 "비평 통화"*로 문서화. producer들과 평가자가 같은 판단 언어를 쓰게. (4번 대화 "명사 통화" 실천의 첫 조각.)

### Phase 3 — Option B: 평가자가 픽셀을 본다 (보편 백스톱)
1. `_collect_created_files`(또는 신설 `_collect_visual_artifacts`)가 이미지/PDF를 확장자로 감지 → **텍스트로 읽지 말고 경로를 따로 보관.**
2. `_evaluate_achievement`에서 시각 산출물 존재 & 기준이 시각 결과물을 함의하면: (a) 산출물마다 `image_critic` 호출해 verdict를 평가에 접거나, (b) 비전 가능 모델로 이미지째 평가.
   - 전제: 비전 가능 경량/중급 모델, 또는 시각 평가만 VLM으로 라우팅.
3. **critic 기본체크 일반화** — 슬라이드-일러스트 전용 디폴트를 `style_preset`/`checks` 뒤로 옮기거나 artifact-type 파라미터 신설. 차트·문서페이지·웹스크린샷도 평가 가능하게.
4. 비-이미지 산출물(docx/xlsx/html)은 critic 전에 **이미지 렌더 선행** 필요(HTML은 `engines:render_html` 재사용, PDF→이미지 등). 의존성으로 기록.

---

## 4. 사용자 결정 대기 항목
1. **1차 스코프**: 슬라이드만(A) vs 평가자 비전까지(B)? → 권장 A 먼저.
2. **비용 허용도**: critique = 라운드·산출물당 VLM 호출 1회. 기본 라운드 수? opt-in vs opt-out?
3. **모델**: critique를 gemini-3-pro(품질) vs flash(비용) 중 무엇으로?

## 5. 검증 계획
- **Phase 1**: 일부러 결함 슬라이드 생성(예: 일러스트에 한글 강제) → critic이 `passed=false`로 잡는지 → 수정 라운드가 개선하는지 → **상한에서 종료(무한루프 없음)** 확인. 임시 출력 디렉토리, 비파괴.
- 비용·지연 수용 가능한지 측정.
- **Phase 3**: 차트/이미지 생성 작업 → 평가자 피드백이 *시각 품질*을 실제로 언급하는지.

## 6. 위험·주의
- Phase 3는 인지 코어(`agent_cognitive`)를 건드리니 **Phase 1로 가치 입증 후** 착수.
- critic 기본체크는 슬라이드 튜닝됨 — 비-슬라이드에 맹목 적용 금지(false-fail).
- `_collect_created_files`가 비-UTF8을 조용히 스킵하는 게 *이미지가 안 보이는 이유다* — 수정은 이미지를 텍스트 리더에서 우회시키는 것.
- 루프 상한·드롭 로깅 규율(기존 평가자 패턴 답습).

---

## 부록 — 한 줄 요약
`engines:image_critic`(슬라이드 튜닝, verdict_json 반환)는 이미 있고, 인지 평가자는 `_collect_created_files`가
이미지를 텍스트로 읽으려다 조용히 버려서 *픽셀을 못 본다.* → **A: 슬라이드 producer에 생성→critique→수정 내부 루프
(저위험, `_run_goal_evaluation_loop` 패턴 복제) → B: 평가자가 이미지를 보게 개조(보편, 고위험)** 순서로 닫는다.
