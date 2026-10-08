# 41회차 최소 재현 (HTTP /ibl/execute, origin:"training", project_id:"수동모드")

- **L41-1 `table:chart` output_format 무시**: `evidence/trainer_base_main_v2.json`(spec, stem 경로 → TOOL "Cannot infer image type"), `probe_chart_format2.json`(table 형 동일). 경로에 `.png` 를 붙이면 성공(`trainer_base_main_v3.json`).
- **L41-2 `table:chart` x/y 목록 거절**: `probe_chart_format.json` — `chart_type:"bar",x:["a","b"],y:[1,2]` → "x 에는 string 이 와야 하는데 2개짜리 목록".
- **L41-3 차트 호출이 전체 읽기 재사용을 끔**: `probe_chartreuse.json`(읽기 2 + chart + write → `continuation.read_calls 0`) vs `probe_writereuse.json`(읽기 2 + write → `read_calls 2`). 전체 프로그램의 제자리 정정 재실행 `trainer_v1b_main_v3_reuse.json` 은 `reuse.skipped` 20건 전부 `no_matching_receipt`. 대조군: 차트 없는 작은 프로그램의 reuse 는 12/12(`probe_reuse_again.json`).
