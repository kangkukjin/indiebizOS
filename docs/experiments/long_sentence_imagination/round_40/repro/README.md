# 40회차 최소 재현

- **L40-1 미지 요청 키 무시**: `evidence/probe_unknown_key2.json` 의 요청(`continuation:{reuse_args:{run_id}}`, `bogus_key:1`) → `success:true`, `warnings:null`, `reuse:null`. 같은 run_id 를 최상위 `reuse:{run_id}` 로 보내면 `receipt_reused` 16건·모델 호출 0(`trainer_B_main_v1_reuse.json`). 잘못된 run_id 는 `REUSE_ARGUMENT` 거절(`probe_unknown_key.json`).
- **L40-2 추출 비결정성·타입**: `drafts/main_v0.ibl` 의 `[table:ai]` 를 같은 계약서 5건(`artifacts/.../contracts.json` 비교)에 세 번 실행 — notice_days(K03) 30 / null / 30. v0 의 `number($c.notice_days)` 가 null 에서 `NUMBER_REQUIRED`(`evidence/trainer_A_main_v0.json`). 검사는 schema 필드를 Unknown 으로 보아 경고 없음.
