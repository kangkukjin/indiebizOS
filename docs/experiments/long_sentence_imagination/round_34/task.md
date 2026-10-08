# 34회차 사전 과제 — 날마다 다시 도는 증분 집계(상태·재처리·실패 격리)

자연어 원문: [request.txt](request.txt) · 변형: [variant_request.txt](variant_request.txt)

## 선정 이유
26~33회차는 한 번 실행으로 끝나는 과제였다. 이번 축은 **같은 프로그램·같은 요청을 날마다 다시 실행하는 일** — 이전 실행의 상태를 읽어
새 파일만 처리하고, 처리 뒤 바뀐 파일은 그 파일만 재처리하며, 손상 파일은 상태에 넣지 않고 다음에 재시도되게 한다. 33회차 L33-2(reuse 신선도)의
프로그램 수준 대응물이다. 시험할 연결: `self:list` 메타(mtime·size)로 변화 감지, 상태 파일의 파일별 기여분 보존, `on_error:"collect"` 부분 실패 격리,
무변화 실행의 멱등성, 조건 변경(store×kind) 때 재독 0 으로 재계산.

## 입력(합성, `outputs/long_sentence_imagination/2026-10-08_34회차/`)
- `source/all/`: 30일치 `sales_2026-09-DD.json`, 각 200행(store 3·sku 20·kind sale/refund 12%·qty 1~5·amount). 실행자별 `inbox/{trainer,agent}` 에 단계별로 연출.
- 단계: run1 = 1~10일 · run2 = +11~20일, **3일차 파일 제자리 수정**(첫 행 amount ×10, size·mtime 변화) · run3 = 변화 없음 · run4 = +21~30일, **25일차 파일 절단(손상)**.
- 생성기·연출·oracle = `harness/prepare.py`(독립 Python). AI 에게는 inbox 경로만 준다.

## 완료 조건(실행 전 고정, 실행마다 oracle 대조)
1. run.processed_new / reprocessed / failed 가 단계 기대와 일치(run2 재처리 = 3일차 1건, run4 실패 = 25일차 1건, run3 = 전부 빈 목록 + "새 파일 없음").
2. totals_by_sku(20행)·totals_by_store(3행)의 sale·refund·net·qty 가 현재 유효 파일 전체에서 계산한 oracle 과 일치(run2 는 수정된 3일차 값 반영, run4 는 손상 파일 제외).
3. files_total·rows_total 일치. state.json 의 파일 목록 = 성공 파일만(손상 파일 제외).
4. summary.md 에 상위 10 sku·store 합계·실패 목록 절, run3 에 "새 파일 없음".
5. 재독 검증: 집계 합 = 파일별 기여분 합. 입력 파일은 연출 외에 바뀌지 않음.
6. 비용 관측: run2 가 10+1 파일만 읽는가(읽기 영수증·tool_ms), run3 은 읽기 0(상태 파일 제외)인가.

## 변형
- A(견고성, 같은 프로그램·다른 입력) = run2~4 자체(수정·무변화·손상).
- B(변경 용이성): run4 뒤 store×kind 합계 추가 — 파일 재독 0 으로 state 기여분에서 계산되는지.

## 작성 조건
공개 교재·ibl.md·`describe`(list·read·dedup)만. 소스 미열람(내부 지식 분리 불가는 밝힘). 상한 60분. **발견만, 수리 없음.**
독립 AI: `/system-ai/chat` background + origin training, 같은 request.txt + 경로, run1~4 를 같은 대화의 후속으로.
