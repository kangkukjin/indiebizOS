# 79회차 — REFLEX 실행 문맥·#reflex 태그 이음새 입장 + 보존 궤적 비용 되먹임

고정 2026-10-19T13:29:44+0900, 훈련 상한 60분(14:31). 정본 HEAD 6863136c(가이드 §2·§4-5 개정 직후), 백엔드 세대 7c9c630b(code_digest 12f65264…, 12:42 재기동 → ed5c6b8b #reflex 태그 포함).

## 형식(개정 가이드 §2 첫 적용)
- 계기 = 10-19 신설 이음새: REFLEX 실행 문맥(efd5f94e 02:43)·`#reflex` 명시 태그(ed5c6b8b 10:47). 태그는 구현 뒤 실사용 0회(4946·4950 의 `#reflex` 는 태그 구현 전 → 분류기 선택이었음).
- 비용 되먹임 = 재호출 없이 보존 궤적 4936~4947(같은 "음악을 꺼줘" 의 REFLEX 4945 / EXECUTE 4943·4947)로 기준선. 새 측정은 훈련 경로(origin training) 짝 R2/R6.
- 불변식 탐침 = 아래 R1~R6. 독립 AI 실행 포함 사유 = §4-5 ①(이음새 입장)·③(AI 행동이 질문).
- 훈련자 전체 IBL = R3 과 같은 일을 하는 base_v0.ibl(모델 0) — R3 의 비용 기준선.

## 자료(78회차 합성 접수 원문 사본, 바이트 동일)
inputs/ = loans.json, north.txt, south.txt, west.txt, sources.json. 합성 사유: 개인 자료 불필요, 이음새가 자료가 아니라 실행 문맥이므로.
oracle(실행 전 고정): 정상반납 총합 = north 18 + south 34 + west 50 = **102**. north R03 = 정상 5·파손 0. 이름순 목록 = loans.json, north.txt, south.txt, sources.json, west.txt.

## 요청 연쇄(같은 리허설 대화, 순서 고정, 각 background 접수 → status_url 회수)
| ID | 태그 | 요청 요지 | 기대(실행 전 고정) |
|---|---|---|---|
| R1 | 없음 | inputs 파일 목록 이름순 | 분류기 판정 기록(REFLEX/EXECUTE 둘 다 허용), 5개 정확 |
| R2 | #reflex | north.txt 의 R03 정상·파손 수량 | route REFLEX, **phase=classify 모델 호출 0**, reflex_context 1, 답 5/0 |
| R3 | #reflex | 세 파일 정상반납 총합 → ai/good_total.md "합계 N" 저장 | 태그가 이김(다단계라도 사용자 결정), 파일 "합계 102", 입력 해시 불변. 비용을 R2·훈련자와 비교 |
| R4 | #execute | 방금 저장한 파일 내용·SHA-256, 다시 쓰지 말 것 | route EXECUTE, reflex.result 영수증 전달(<separate_execution_history>) 뒤 reflex.ack, 파일 해시 불변, 답 해시 일치 |
| R5 | #reflex | "아까 맨 처음 알려준 목록의 첫 파일 이름" | 최근 4메시지에 없음 → 도구 호출 전 NEEDS_CONTEXT → reflex_fallback(executor_needs_history) → 전체 문맥으로 "loans.json" |
| R6 | #execute | R2 와 같은 질문 | route EXECUTE, 답 5/0. R2 와 execution 입력·시간 짝 비교 |

판정 분리: 검사/실행 종료/과제 달성(답 정확)/불변식(위 기대)/비용. 미발동 경계는 미검증. 실기기·외부 효과 없음(쓰기는 ai/ 한 파일).
비용 비교 조건: 같은 날·같은 기어(최대, 실행 opus·분류 deepseek-flash)·같은 리허설 대화. 캐시 포함 provider 보고값, cache_create 를 별도로 본다(격리 턴은 매번 재생성).
