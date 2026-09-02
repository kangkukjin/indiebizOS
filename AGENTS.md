# AGENTS.md — 외부 AI 도구(Codex 등) 작업 규약

> Claude Code 는 CLAUDE.md(워크스페이스 루트)를, 그 밖의 AI 도구는 이 파일을 읽는다.
> 구조·설계의 정본은 `data/system_docs/anatomy.md`(정문)와 그 허브 문서들이다.

## 0. 이 복제본이 정본인가 — 가장 먼저 확인하라

정본 저장소는 소유자의 로컬 클론 하나뿐이다.

- 그 경로에 접근 가능하면 **거기서 직접 작업하라. 새로 clone 하지 마라.**
- 지금 있는 곳이 샌드박스/세션 폴더에 뜬 복제본이면(예: `~/Documents/Codex/...`),
  당신의 커밋은 **정본에 자동으로 닿지 않는다.** 2026-08-26 에 그런 고아 커밋
  10개가 생겨 사람이 하루를 들여 수습했다(`refs/codex/absorb-20260826`). 그래서:
  1. 시작 전: `git fetch origin && git log --oneline HEAD..origin/main | head`
     — 뒤처져 있으면 최신 `origin/main` 위에서 시작하라.
  2. 종료 전: push 권한이 있으면 push 하라. 없으면
     `git format-patch origin/main -o outputs/` 로 패치를 내놓아라.
  3. 보고서 첫 줄에 반영 상태를 명시하라 — "origin/main 반영 완료" 또는
     "**정본 미반영 — 패치 적용 필요**". 작업의 완료는 커밋이 아니라 정본 반영이다.
- **실재하는 커밋 해시만 보고하라.** 복제본의 해시는 복제본 절대 경로와 함께 밝혀라.

## 1. 커밋 규약

- 커밋은 **브랜치 없이 main 직접**. 동시 세션이 있을 수 있으니 커밋은 pathspec 으로
  (`git commit <파일들> -m ...`) — 남의 미커밋 작업분을 쓸어 담지 마라.
- 민감 정보(API 키·토큰) 커밋 금지. 작업·커밋 범위는 이 저장소만.

## 2. 빌드·파생물 — 손으로 고치면 되돌아간다

- 어휘 단일 소스 = `data/ibl_nodes_src/*.yaml` + 각 패키지 `ibl_actions.yaml`.
  파생물(`data/ibl_nodes.yaml`·각 패키지 `tool.json`·`data/ibl_fixtures.json`·
  문서의 마커 구간)은 **직접 편집 금지** — `python3 scripts/build_ibl_nodes.py` 로
  재생성하고 `--check` 로 검증하라.
- backend 파일을 바꾸면 `python3 scripts/build_body_bundle.py android` 로 폰 번들
  매니페스트를 재생성해야 커밋이 통과한다(pre-commit 이 강제).
- **설명을 고쳤으면 거기서 끝이 아니다.** 한 낱말의 교재는 카탈로그·파생물만이 아니라
  **핸들러의 오류·도움말 문자열과 독스트링**까지다 — 앞은 `--check` 가 대조하지만 뒤는
  아무도 안 본다(2026-08-27 실측 `aa904ffc`: 카탈로그는 참인데 런타임 문구가 은퇴한
  관용구를 계속 가르쳤다). 계약을 은퇴시켰으면 `data/retired_contracts.yaml` 에 한 줄
  등록하라 — 관문 `scripts/check_retired_contracts.py` 가 매 커밋 전 표면을 훑는다.
  절차 정본 = `data/guides/new_action_checklist.md` 0단계 7항.

## 3. 코드 규칙

- **파일 1500줄 제한**(pre-commit 강제). 넘치면 형제 모듈로 분할.
- 새 backend 모듈 = 층 폴더(`backend/{base,datastore,ibl,cognition,services,surface}/`)
  + `scripts/check_backend_layers.py` 의 `LAYERS` 배정. 독립 스크립트는 맨 위
  `import boot_paths`.
- 패키지(data/packages/…) 안의 모듈 파일명이 backend 모듈명과 겹치면 안 된다
  (모듈 그림자 관문이 차단 — `<패키지>_<이름>.py` 식으로 개명).
- 값의 동등·순서·숫자 관측·집계의 뜻은 `backend/common/value_semantics.py` 한 벌이
  소유한다. 소비자 코드에 사설 비교(`float()` 직접 등)를 재도입하지 마라(가드 존재).
- Python PEP8·한글 주석 OK. frontend 실검사 = `npx tsc -p tsconfig.app.json`.

## 4. 검증

- 회귀 = `.venv/bin/python3 -m pytest backend/ -q` (정본 맥 기준; 샌드박스는
  가능한 부분 집합만 돌리고 못 돈 것을 보고서에 명시).
- 백업은 `data/_backups/YYYY-MM-DD_이름/` 에만. 작업 폴더에 `*_backup*` 흩뿌리지 말 것.
