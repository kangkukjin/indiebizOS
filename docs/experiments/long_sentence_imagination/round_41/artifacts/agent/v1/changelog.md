# changelog — `20261009T032342-53daec0dff26` → `20261009T032750-76d776f7df5c`

비교 기준: 이전 실행 `/Users/kangkukjin/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-10-09_41회차/agent/out/stats.json`. 이번 자료: `/Users/kangkukjin/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-10-09_41회차/agent/v1`.

## 입력 파일 변화 (sha256 대조)

- 바뀐 파일 7개: trials/P33.json, trials/P35.json, trials/P37.json, trials/P39.json, trials/P41.json, trials/P43.json, trials/P45.json
- 바뀌지 않은 파일 57개 (design.json 포함 여부: 동일 — 규칙 불변).
- 읽기 기록: 바뀌지 않은 입력 파일도 **다시 읽었다**. sha256 대조에 파일 전체가 필요하고, 분석 단위(참가자×과제 평균)·조건 통계·검정을 전 참가자 자료로 처음부터 다시 계산했기 때문이다(이전 실행은 참가자별 중간값을 저장하지 않아 재사용할 캐시가 없다).
- 이전 out 에서 읽은 파일: stats.json(비교 기준), manifest.json(이전 입력 sha256), quality.json(품질 표 비교), fig2_satisfaction_by_group.png(바이트 복사). 이전 report.md 는 읽지 않았다.

## 바뀐 표: 조건별 기술통계 (stats.json#conditions)

- B-T1: mean 48.5408 → 52.0408; sd 4.8186 → 7.7165; ci_low 46.7416 → 49.1595; ci_high 50.3401 → 54.9222

## 바뀐 가설 (stats.json#hypotheses)

- **H1** 판정 유지(지지). mB 48.5408 → 52.0408; sdB 4.8186 → 7.7165; t -10.1752 → -5.9223; df 56 → 53; crit_p0125 2.5809 → 2.5858; d -2.6272 → -1.5291

## 바뀐 그림

- `fig1_duration_by_condition.png`: 입력 통계가 바뀌어 다시 그렸다.

## 바뀌지 않음

- 자료 품질 표, 만족도 기술통계, 가설 H2·H3·H4, 그림 `fig2_satisfaction_by_group.png`(다시 그리지 않고 이전 PNG 를 바이트 복사)
