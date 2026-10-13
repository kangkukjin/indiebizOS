# 63회차 시스템 AI — 연구 질문 기록표

- project_ref: `d3bbe55090f54d52b435184e068b4148`
- thread_ref: `9bf7c088a4504112ac35b677995cb3dd` (다른 대화 b7144a55…·8ee19ab7…는 열람·사용 안 함; thread_list 목록 조회에서 제목만 보임)
- 작성: 2026-10-13 KST, origin=training

## 질문별 판본·근거 수·상태 (재독 후)

| question_id | 질문 | 판본 | 상태 | 지지 | 반박 | 반박 응답 | 미확인(gaps) | 다음 볼 것 | 인용 원문 일치 | 의도 대조 |
|---|---|---|---|---|---|---|---|---|---|---|
| 20e9257f3da2411a8ac2cfd5ce59f95c | 어떤 조건에서 긴 문맥이 RAG 를 이기는가 | 2 | 종결(answered) | 5 | 4 | 4 | 0 | 2 | 9/9 | 일치 |
| 665b110778d64a35a0a83c6f89bcf43f | 둘을 섞는 방식이 비용 대비 나은가 | 1 | 열림 | 5 | 3 | 0 | 2 | 3 | 8/8 | 일치 |
| 2d07aeba5d124bdc8a73a96692a28976 | 평가 벤치마크가 결론을 바꾸는가 | 1 | 열림 | 5 | 1 | 0 | 3 | 3 | 6/6 | 일치 |

Q1 판본 사슬: rev1(open, gaps 1, 반박 4, digest ca488ca9…) → rev2(resolved/answered, gaps 0, 반박 4 유지, objections 4, digest 27fcd24f…, previous=ca488ca9…).
Q2·Q3: rev1 열림. previous_revision_digest=null.

## 세 칸 판정

| 항목 | 검사 결과 | 실행 상태 | 과제 달성 |
|---|---|---|---|
| C1 PDF 8편 자료실 보존 | thread_messages materials 8건, coverage=full, blob sha256 = 입력 파일 sha256 8/8 | thread_send 접수 성공(research_51e35294…). 단 그 연구 실행은 이 기록 시점까지 running(도구 활동 0·응답 없음) | 달성 (보존은 접수 시점에 완료·판본 확인) |
| C2 세 질문·잠정답·지지/반박 인용·미확인·다음 볼 것 | 질문 3, 인용 23건 저장, 각 질문 지지≥5·반박≥1, next_probes 2~3 | thread_update 성공 2회(생성 rev0→1, Q1 rev1→2), 거절 0 | 달성. 단 Q1의 미확인은 rev1에 기록, rev2에서 반박 검토로 해소되어 gaps 0 — 8편 밖 확인 대상은 next_probes에 남김 |
| C3 근거 충분한 질문만 종결, 반박 은닉 금지 | Q1만 answered. 반박 4건 rev1→rev2 그대로, 각 반박에 objection 기록. Q2·Q3 열림 | 서버가 answered 저장 수용(종결 조건: 잠정답·지지·빈 gaps·모든 반박 objection) | 달성 |
| C4 재독 대조·표 저장 | 재독: 모든 필드 의도와 일치(3/3), 원문 재대조 23/23 | 이 파일 저장 후 재독(아래 기록 참조) | 저장·재독 확인 후 달성 |

## 코드가 보장하는 것 / 판정하지 않는 것

- 보장(기계 확인): 인용 문자열이 보존 판본(version_ref, extraction_revision=1)의 해당 쪽(locator p.N) 추출문에 그대로 있음 — 저장 전 assert, 저장 후 재대조 23/23. 보존 자료 판본(blob sha256 = 입력 파일 sha256). 판본 사슬(revision_digest·previous_revision_digest). 종결 조건(answered는 서버가 빈 gaps·objections를 요구).
- 판정하지 않음: 인용이 주장을 실제로 지지/반박하는지(지지·반박 분류는 실행자의 판단), 논문 주장이 참인지, 출처 독립성(예: Li et al.이 다른 연구를 요약한 문장 — Self-Route·ChatQA2 관련 — 은 원 논문이 아니라 요약 문장임).

## 인용 정규화 규칙
없음. self:notebook read가 돌려준 추출문(쪽 표지 `[자료:판본:p.N]` 사이)의 부분 문자열을 그대로 사용. PDF 줄바꿈 하이픈(`out- performs` 등)·곡선 따옴표·∞ 기호를 원문 그대로 유지. 문장 끝 마침표는 인용에서 제외.

## 관측(기록용)
- 서버가 저장한 근거의 observed_in은 모두 빈 목록이고 질문의 run_id는 null — 연구 실행(thread_send) 밖의 IBL 호출에서 저장했기 때문으로 보임(추정). 원문 일치 검사는 통과했음.
- self:notebook versions(project_ref,thread_ref)는 보존 직후 빈 목록을 반환했고, 같은 시점 thread_messages의 materials에는 8건이 있었음.
- read_guide(query="research_project.md")는 해당 가이드를 찾지 못했고 data/guides/research_project.md·research_questions.md를 직접 읽음.
- 보존용 thread_send의 연구 실행(13:19:45 KST 접수)이 13:33 KST 확인 시점까지 running(도구 활동 0, 응답 본문 없음). 취소하지 않았음. 첨부 보존 자체는 접수 시점에 끝나 있었음.
