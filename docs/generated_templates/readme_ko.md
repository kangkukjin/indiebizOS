
**{{node_count}}개 노드, {{total}}개 조합 가능한 액션** — 도구는 `execute_ibl` 하나, 어휘 하나, {{total}}개 스키마가 아닙니다:

| 노드 | 액션 수 | 무엇이 사는가 |
|------|---------|---------------|
{{node_rows_ko}}

IBL 정의는 단일 진실 소스(`data/ibl_nodes_src/`, `scripts/build_ibl_nodes.py`로 `data/ibl_nodes.yaml` 빌드)에 살고, 커밋 시점 검사가 소스↔도구 스키마↔핸들러를 삼각으로 대조합니다. 도구 **패키지**(설치 {{tools_n}}개 + 백엔드 코어 모듈 {{exts_n}}개)는 폴더입니다 — 하나 떨궈 넣으면 언어와 무관하게 인식되고, AI 에이전트가 당신을 위해 만들고·설치하고·고칩니다. 에이전트별 `allowed_nodes`가 접근 범위를 제한합니다.
