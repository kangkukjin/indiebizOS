# 41회차 사전 과제 — 소규모 사용자 실험의 연구 보고서 (2026-10-09, 03:13 KST 시작, 상한 60분)

## 자연어 요구 원문 (훈련자·독립 AI 공통)

두 인터페이스(A/B)로 60명이 과제 3종(T1·T2·T3)을 각 4회 수행한 실험 자료로 연구 보고서를 써. 자료 폴더: design.json(사전등록 — 가설 H1~H4 와 방향, α=0.05 Bonferroni 4회 보정 → 0.0125, 제외 규칙, 조건당 최소 n=8, 분석 단위, CI·검정·효과크기 수식, 설문 역문항), participants.csv(id, group, age_band, experience), trials/P01.json~P60.json(participant, group, trials[trial_id, task_type, rep, duration_s, errors, completed]), survey.csv(participant, Q1~Q7, 1~5), t_critical.json(df 1~120 의 양측 임계값 p05·p0125). design.json 의 규칙을 그대로 따른다.
1. 자료 품질: 제외 규칙(완료시간 0 이하·600 초과, errors 가 수가 아님, 같은 파일 안 중복 trial_id 는 첫 것만)으로 제외된 trial 을 파일·trial_id·이유와 함께 세고, 참가자별 유효 trial 수, 설문 응답 없는 참가자, n<8 인 조건을 보고해.
2. 조건(인터페이스×과제 6개)별로 참가자별 유효 trial 평균을 분석 단위로 n·평균·표본 표준편차·95% 신뢰구간(평균 ± t(p05, n−1)·sd/√n)을 구해.
3. 가설마다 Welch t(t=(mB−mA)/√(sA²/nA+sB²/nB), 자유도 Welch–Satterthwaite 내림), t_critical.json 의 p0125 임계값과 비교, Cohen's d(pooled sd) → 판정: 유의하고 방향 일치=지지, 유의하지만 반대=불지지(반대 방향 유의), 비유의=불지지(차이 없음 입증 아님), 어느 쪽이든 n<8=검정 불가.
4. 설문은 Q3·Q6 을 역문항(6−x)으로 반전해 참가자별 7문항 평균을 만족도로 하고, 응답 없는 참가자는 빼고 H4 를 같은 방법으로 검정해.
5. 그림 2장을 PNG 로 저장해: 조건별 평균 완료시간과 신뢰구간(오차막대), 집단별 만족도. 보고서에서 파일명으로 참조해.
6. report.md: 초록·방법·결과(품질·조건 표·가설 표·그림)·가설별 결론·한계. 산문의 숫자도 계산값만. 비유의를 "차이 없음 입증"으로 쓰지 마.
7. manifest.json: 입력 파일 전부의 sha256, 표·그림마다 출처 파일과 계산 규칙, 실행 식별자.
결과(quality.json·stats.json·report.md·manifest.json·PNG 2장)는 out 폴더에. 이전 실행의 out 폴더가 주어지면 stats.json 을 비교해 바뀐 표·가설·그림만 changelog.md 에 적고, 안 바뀐 그림은 다시 그리지 마. 자료 생성기·oracle·다른 실행자의 코드·결과는 열지 마.

## 선정 이유
37·38회차(문헌 조사 보고)와 달리 자료를 직접 분석하는 연구 보고. 새 연결: 통계 내장 없는 IBL 로 Welch t·CI·d 를 식으로 조합(임계값은 데이터), `table:chart` 그림과 보고서 참조,
재현 manifest, 자료 정정 뒤 `reuse` 로 바뀐 파일만 재독·changelog(L33-2 수리 실전 검증), `table:brief` 산문 1회의 숫자 근거 검수(40회차 검수기).

## 입력(합성, 시드 41, harness/prepare.py) 과 함정
60명(A 30·B 30), 세션 파일 60(720 trial 중 P23 은 11개), 제외 대상 4(P05 duration 0, P12 650, P31·P48 errors "NA"), 설문 P17 없음, experience 결측 2.
H1 지지(B 빠름), H2 반대 방향 유의, H3 비유의, H4 지지. 보정 전 p05 임계값을 쓰면 결론이 바뀌지는 않지만 t 표 열 선택이 보고서에 드러나야 한다.

## 완료 조건·기대값 (oracle/expected.json, 독립 Python — scipy 로 t 표 교차 확인)
| 항목 | 기대 |
|---|---|
| 품질 | 제외 4(이유 3종), 중복 0, 설문 결측 P17, n<8 조건 없음 |
| 조건 | A-T1 n30 62.42 [60.288, 64.552] · B-T1 48.541 [46.742, 50.34] · A-T2 89.761 · B-T2 100.711 · A-T3 119.352 · B-T3 120.454 |
| 만족도 | A n29 3.379 sd .308 · B n30 4.019 sd .27 |
| 가설 | H1 지지(t −10.1752 df56 d −2.6272) · H2 불지지(반대 방향 유의, t 6.6565) · H3 불지지(비유의, t 0.6415) · H4 지지(t 8.4674) |
| 그림·manifest | PNG 2장 존재·보고서 참조, 입력 64파일 sha256 전부, 표·그림 출처 |
| 변형 1(B 참가자 7명 T1 +15 재전송, prev=out) | B-T1 52.041, H1 t −5.9223 지지 유지, changelog = 조건 B-T1·H1·그림 1 만, 그림 2 재생성 없음, reuse 로 53파일 재사용·7파일 재독 |
| 변형 2(B×T3 결손 n=6) | low_n [B-T3], H3 검정 불가, 그림 1 에 B-T3 비움 |
| 변형 3(P50: 음수·"NA"·중복 id) | 제외 7, 중복 1, 나머지 결론 base 와 같음 |

작성 조건: 공개 교재·문법 전문·describe(table:chart·brief·script) 만. 실행 HTTP `/ibl/execute`, `origin:"training"`, `project_id:"수동모드"`.
