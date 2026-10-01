# 프롬프트 구성 표면 (2026-09-13)

## 왜
indiebizOS 에는 시스템 AI·프로젝트 에이전트·의식·의식 감독·무의식·최종 평가자·경험 증류·가이드 순찰·
IBL 번역기·자동응답 등 여러 종류의 LLM 에이전트가 있고, 프롬프트는 저마다 다르게 조립된다. 그 조립문이
`prompt_builder`·`ibl_access`·`consciousness_agent`·`cognitive_eval`·`supervisor_runtime`·`ibl_usage_rag` …
에 흩어져 있어 "이 에이전트가 지금 무엇을, 어떤 순서로, 얼마나 읽고 있나"를 사람이 볼 표면이 없었다
(사용자 요청 09-13).

## 무엇
런처 안경(로고) 메뉴에 **프롬프트 구성** 버튼. 에이전트를 고르면 아래에 층별(시스템 프롬프트 / 턴 컨텍스트 /
사용자 메시지) 조립식이 `A + B + C` 로 보이고, 조각을 누르면 본문·출처·조건·분량이 열린다.

- 파일 조각(kind=file)은 본문 그대로. 코드 상수(constant)도 그대로.
- 실행기억·IBL 환경·프로젝트 포식 기억·세계 상태 같은 가변 조각(memory/dynamic)은 **샘플 메시지 한 건으로
  정본 빌더를 그대로 돌려** 조립한다(LLM 0, 임베딩 검색만). 그래서 분량이 실제 값이다.
- 실제 턴에서만 생기는 조각(turn — 도구 원장·응답 본문·상태 JSON)은 자리·상한만 적고 본문은 비운다.
- 조건부 조각은 이번 샘플에서 안 실려도 목록에 남는다(점선 칩, "조건부").
- 시스템 AI·프로젝트 에이전트는 조각 합과 별도로 **실제 빌더 결과의 총 글자수**를 병기해 표면이 조립문과
  어긋나지 않는지 대조할 수 있게 했다(차이 = 결합 개행뿐).

## 어디
- `backend/cognition/prompt_composition.py` — 에이전트 목록(`AGENTS`)과 조립 함수. 조각 스키마
  `{key,label,layer,kind,source,condition,included,chars,tokens,content,note}`. 프로젝트 에이전트는
  `agents.yaml` 첫 활성 에이전트 기준(프로젝트 선택 가능).
- `backend/surface/api_prompt_composition.py` — `GET /prompt-composition/agents`,
  `POST /prompt-composition/assemble {agent_id, sample_message?, project_id?}`. 로컬 전용.
- `frontend/src/components/launcher-components/dialogs/PromptCompositionDialog.tsx`, `Launcher.tsx` 메뉴 버튼,
  `SettingsFrame` 에 `title` prop.

## 경계
- 표면은 요약본을 따로 짓지 않는다 — 조립 순서가 코드에서 바뀌면 이 모듈의 조각 목록도 같이 고쳐야
  한다(`test_prompt_composition.py` 가 기본 형태와 실제 빌더 총량 대조를 지킨다).
- 부작용 있는 로더는 피했다: 가이드 주입 기록(`_guide_block`)·해마 쓰기 없음. 해마 회상은 조종실
  '기억 회상 검증'(`/system-ai/recall-preview`)과 같은 읽기 경로.
- 의료 프로젝트의 라이브 환자 차트는 `# Notes` 조건 문장으로만 적고 표면에서 조립하지 않는다(민감).

## 속편 (같은 날) — 독립 창 + 가이드 파일
- 런처 안 모달은 바깥 창 크기에 갇혀 좁았다(사용자). `frontend/electron/windows.js` 의 `createToolWindow(kind)`
  가 안경 메뉴 도구 창(`prompt-composition` · `guides`)을 OS 창으로 연다 — kind 별 싱글턴, 크기 조절 자유,
  IPC `open-tool-window`. 웹 표면은 같은 창의 해시 라우트(`#/prompt-composition`, `#/guides`)와 '‹ 뒤로'.
  공통 틀 `ToolWindowFrame`.
- **가이드 파일**(`GuidesView`): `data/guides/*.md` 전체를 등록(guide_db.json)·신선도(guide_registry)·
  예산(lifecycle_policy `guide_budget_bytes`)·정리 후보 표식과 함께 목록으로 보이고, 본문을 렌더/원문으로 읽고
  고쳐 저장한다. 폴더가 정본이라 '등록만 있고 파일 없음'·'파일만 있고 미등록'을 숨기지 않는다.
  백엔드 `GET/PUT /guides/{name}` — 기존 파일만 저장(새 가이드 등록은 guide_registration.md 절차),
  예산 초과는 막지 않고 알린다(정책=압축·분할, 삭제 금지 — check_file_size 가 커밋에서 집행).
