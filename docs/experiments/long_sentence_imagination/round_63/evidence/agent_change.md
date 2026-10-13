# 63회차 추가 논문 반영 — change.md

- 대상: project_ref `d3bbe55090f54d52b435184e068b4148`, thread_ref `9bf7c088a4504112ac35b677995cb3dd` (다른 대화 미열람, 앞 프로그램 변수·산출물 미사용)
- 추가 논문: `Long_Context_LLMs_Meet_RAG__Overcoming_Challenges_for_Long_Inputs_in_RAG.pdf` (1,681,409 B, sha256 693af1edc4b4e82b76629fcfeed21833959d38974e1b8b32514951a7c43f4b61, 34쪽, 텍스트 없는 쪽 0)
- 작성: 2026-10-13 KST, origin=training

## 결론
**보존 거절 → 질문 판본 변경 없음.** 새 논문이 자료실에 보존되지 않아 보존 판본(version_ref)이 없다. 판본 없이 로컬 PDF 인용을 근거로 붙이면 판본 사슬로 거슬러 올라갈 수 없으므로 붙이지 않았다. 세 질문 모두 이번 턴에 저장하지 않았다(저장 시도 0, 저장 충돌 0).

## 보존 시도와 거절 (원문 그대로)

| 순서 | 실행 ID | 동작 | 결과 |
|---|---|---|---|
| 1 | ed5bc559b73c4c78a9ddc1c8b2dc7883 | thread_send attachments(새 논문 1편) | **거절** code=VALUE "작업 중에는 텍스트로 방향을 수정할 수 있습니다. 파일은 현재 응답 완료 후 보내세요" |
| 2 | f557283dcc7340bfb873a62aed658496 | 원인인 앞 턴 보존 실행 research_51e3529407064ae087390474e10ec804(13:19:45 접수, 도구 활동·응답 0) 에 thread_cancel | state=cancel_requested, 60초 대기 뒤에도 running |
| 3 | 0bc43404a959421eb8e53b6421f23b73 | 같은 실행 240초 추가 대기 | running, terminal=false |
| 4 | 12803cb2a3954993899184cafe78d7c4 | 상태 1회 재조회 | running → 첨부 재시도 안 함 |

우회 경로(notebook add, 파일 직접 복사, 새 대화, 다른 첨부 경로)는 쓰지 않았다. backend_runtime.log 에서 이 연구 실행의 진행 줄은 찾지 못해 멈춘 원인은 미확정이다.

## 질문별 변경 전·후

| question_id | 질문 | 변경 전 (rev·상태·digest) | 변경 후 | 바꾼 이유 |
|---|---|---|---|---|
| 20e9257f3da2411a8ac2cfd5ce59f95c | 어떤 조건에서 긴 문맥이 RAG 를 이기는가 | rev2 · resolved(answered) · 27fcd24f… | 동일 (rev2) | 변경 없음 — 보존 거절로 근거 연결 불가. 아래 후보로 보아 종결 답과 직접 충돌한다는 판정도 하지 않았음 |
| 665b110778d64a35a0a83c6f89bcf43f | 둘을 섞는 방식이 비용 대비 나은가 | rev1 · open · 5ffe698a… | 동일 (rev1) | 변경 없음 — 보존 거절로 근거 연결 불가 |
| 2d07aeba5d124bdc8a73a96692a28976 | 평가 벤치마크가 결론을 바꾸는가 | rev1 · open · 62edd01e… | 동일 (rev1) | 변경 없음 — 보존 거절로 근거 연결 불가 |

판본 동일 확인: 실행 12803cb2… 에서 questions_only 재독 — 위 rev·digest·지지/반박/남은 확인 수(Q1 5/4/0, Q2 5/3/2, Q3 5/1/3) 그대로.

## 미저장 영향 후보 (판정 아님, 저장 안 함)
로컬 PDF를 self:read 로 읽은 추출문(실행 514ca1e634094ab99c84c1ed4139ca68). 이 추출문은 줄바꿈(\n)을 포함해 자료실 추출 판본과 문자열이 다를 수 있으므로, 보존 후에는 보존 판본에서 인용을 다시 회수해야 한다.

| 후보 질문 | 쪽 | 후보 문장(로컬 추출 그대로, 줄바꿈은 공백으로 표시) | 잠정 방향 |
|---|---|---|---|
| Q3 벤치마크 | p.3 | "these benchmarks often rely on random negative examples and do not accurately reflect the challenges posed by the "hard negatives" encountered in real-world RAG scenarios" | 지지 후보 |
| Q2 혼합 비용 | p.2 | "our research reveals that increasing the number of retrieved passages does not consistently improve performance with long-context LLMs" | 지지·반박 양쪽 관련 후보(혼합이 항상 이득은 아님) |
| Q2 혼합 비용 | p.1 | "We first showcase the effectiveness of retrieval reordering as a simple yet powerful training-free optimization" | 지지 후보(비용 수치는 없음) |
| Q1 이기는 조건 | p.1 | "the quality of generated output initially improves first, but then subsequently declines as the number of retrieved passages increases" | 긴 문맥 LLM 을 RAG 리더로 쓸 때의 조건 — 긴 문맥 단독 대 RAG 비교가 아니어서 종결 답과의 직접 충돌로 보지 않음(잠정). 보존 뒤 재검토 필요 |

## 판정 칸 분리
| 항목 | 검사 결과 | 실행 상태 | 과제 달성 |
|---|---|---|---|
| 새 논문 보존 | 자료실 materials 8건 그대로(새 논문 없음) | thread_send 거절(VALUE) | 미달 — 단 거절을 받아 그대로 기록(우회 없음) |
| 영향 질문만 갱신 | 영향 후보는 위 표(미저장) | 저장 시도 0 | 미검증 — 보존 판본이 없어 갱신 불가 |
| 닿지 않는 질문 판본 유지 | 세 질문 rev·digest 재독 동일 | — | 달성(세 질문 모두 변경 없음) |
| 저장 충돌 시 재저장 | 저장 시도 0 → 충돌 0 | — | 해당 없음 |
| change.md 저장·재독 | 이 파일 | 저장 후 재독 assert | 저장·재독 확인 후 달성 |

## 보장 / 비판정
- 기록상 보장(서버): 기존 인용의 원문 일치·보존 판본·판본 사슬·종결 조건. 이번 턴은 새 저장이 없어 새로 보장된 것은 없다.
- 판정 안 함: 위 후보 문장이 질문을 실제로 지지·반박하는지, 논문이 참인지, 출처 독립성.

## 사용자 결정 필요
멈춘 연구 실행 research_51e3529407064ae087390474e10ec804 가 취소 요청 후에도 끝나지 않아 이 대화에 파일을 보낼 수 없다. 백엔드 재기동 등으로 실행을 종료할지 결정이 필요하다. 종료되면 첨부 재시도 → 보존 판본에서 인용 재회수 → 영향 질문만 갱신 순으로 이어갈 수 있다.


---

# 2차 시도 (2026-10-13 14:25~ KST, origin=training) — 보존 성공, 영향 질문만 갱신

이 절이 위 1차 기록을 이어 받는다. 1차 기록(거절·변경 없음)은 지우지 않고 그대로 둔다.

## 1. 멈춘 실행 재확인
- research_51e3529407064ae087390474e10ec804 재조회(실행 13075d8c…): **state=cancelled, terminal=true**, 대화 active_run=null, materials 8건. 1차의 취소 요청이 이후 반영되어 끝났다. 재기동 등 추가 조치는 하지 않았다.
- 질문 최신 판본 재확인: Q1 rev2 resolved(answered) 27fcd24f… / Q2 rev1 open 5ffe698a… / Q3 rev1 open 62edd01e… — 1차 기록과 동일.

## 2. 보존 (같은 대화·같은 첨부 경로)
- thread_send attachments(request_id r63-agent-late-paper-v2, 실행 c85bda81…) → accepted, 연구 실행 research_749f79b349954177aebf634c30295b0c → **succeeded**.
- 자료실(sources, 실행 0a41efca…): source_ref `404e490b604a4c57838235b834853fb7`, **version_ref `1ef1b433dc234bc580af9d483febbcae`**, preservation=stored, coverage=full, index_state=ready, extraction_revision=1. 자료실 9건.
- 보존 판본 재독: self:notebook read(version_ref) 커서 0~96000 9구간, total_chars 98,848. 쪽 표지 `[자료:1ef1b433dc234bc580af9d483febbcae:p.N]` 로 쪽을 나눔.
- 우회 경로(notebook add·파일 복사·새 대화·다른 대화 자료)는 쓰지 않았다.

## 3. 인용 (보존 판본의 해당 쪽 추출문에서 잘라 assert 로 원문 포함 확인)
| 질문 | 방향 | 쪽 | 인용 (보존 판본 그대로) | 서버 evidence_id |
|---|---|---|---|---|
| Q3 벤치마크 | 지지 | p.3 | While long-context LLMs (Reid et al., 2024) demonstrated impressive performance on benchmarks like "needle-in-the-haystack" (Kamradt, 2023) and RULER (Hsieh et al., 2024a), these benchmarks often rely on random negative examples and do not accurately reflect the challenges posed by the "hard negatives" encountered in real-world RAG scenarios | 5574a3ee42b592c7b1447017cf66a71271d119b1fb8d2ac2888fc92a882207a5 |
| Q2 혼합 비용 | 반박 | p.2 | our research reveals that increasing the number of retrieved passages does not consistently improve performance with long-context LLMs | 09613b752909e42774514fabc2a0f8c1417f1c19d990df5205a3041fcedc162d |
| Q2 혼합 비용 | 지지 | p.1 | Yet, it would still not be feasible for large corpora (e.g., Wikipedia) and can incur higher computational costs | 5cbd36f5da4ece7b087b3905d46a2952db37b8c8a13384eceb73588766cd4bd1 |

1차 기록의 로컬 후보 중 p.1 "retrieval reordering … training-free optimization" 은 비용 수치가 없어 Q2 근거로 넣지 않았다. 대신 같은 p.1 의 계산 비용 문장을 지지로 넣었다.

## 4. 질문별 변경 전·후 (저장 1회, 실행 8a2a1083…; 이후 재독 실행에서 확인)
| question_id | 질문 | 변경 전 | 변경 후 | 바꾼 이유 |
|---|---|---|---|---|
| 20e9257f3da2411a8ac2cfd5ce59f95c | 어떤 조건에서 긴 문맥이 RAG 를 이기는가 | rev2 · resolved(answered) · 27fcd24f… · 지지5/반박4 | **동일** rev2 · resolved · 27fcd24f… · 지지5/반박4 | 유지·재개 안 함. 이 논문은 긴 문맥 LLM을 **RAG 리더로 쓸 때** 검색 지문 수의 영향(늘리면 오르다 떨어짐, hard negatives)을 다룬다. 긴 문맥 단독 대 RAG를 비교하지 않으므로 Q1의 '이기는 조건'을 반박하지 않는다. 그 결과는 Q1 답이 이미 둔 한계(극단 길이·관련 정보 집중 저하)와 같은 방향이다. p.1 의 "코퍼스 전체를 직접 넣는 것은 큰 코퍼스에서 불가능·비용 큼"은 실현 가능성·비용 서술이지 주어진 문맥의 QA 성능 비교가 아니어서 Q1과 충돌로 보지 않았다. |
| 665b110778d64a35a0a83c6f89bcf43f | 둘을 섞는 방식이 비용 대비 나은가 | rev1 · open · 5ffe698a… · 지지5/반박3/남은확인2 | rev2 · open · 5690a54d… (prev 5ffe698a…) · 지지6/반박4/남은확인2 | 혼합(긴 문맥 LLM+RAG)에서 검색 지문을 늘려도 성능이 꾸준히 오르지 않는다는 문장을 반박에, 코퍼스 전체 직접 입력의 계산 비용 문장을 지지에 더함. 잠정 답에 한 문단 덧붙이고 scope·첫 남은확인의 '8편'→'9편'. 같은 기준의 비용 수치는 이 논문에도 없어 open 유지. 기존 근거·남은확인은 지우지 않음(둘째 남은확인·next_probes 의 '8편 밖' 표기는 그 원 논문이 9편에도 없으므로 그대로 둠). |
| 2d07aeba5d124bdc8a73a96692a28976 | 평가 벤치마크가 결론을 바꾸는가 | rev1 · open · 62edd01e… · 지지5/반박1/남은확인3 | rev2 · open · 2eb964b5… (prev 62edd01e…) · 지지6/반박1/남은확인3 | NIAH·RULER가 무작위 오답 예시에 기대 실제 RAG의 hard negatives를 반영하지 못한다는 문장을 지지에 더함. 잠정 답에 한 문장 덧붙이고 scope '8편'→'9편'. 반박(Self-Route)이 남아 open 유지. |

- 최종 재독(이 파일을 쓴 실행): Q1 rev2 digest 27fcd24f… 그대로, 새 논문 근거 0건. Q2·Q3 의 previous_revision_digest 가 변경 전 digest 와 일치(판본 사슬 확인).

## 5. 저장 충돌
- 저장은 기대 판본(Q2 rev1, Q3 rev1)을 지정해 Q2·Q3 한 묶음(전부 성공/전부 취소)으로 1회 시도 → **성공, 충돌 없음**. 충돌 시 '최신 판본 재독 → 내 인용·문단 병합 → 재저장' 분기를 프로그램에 넣어 두었으나 실행되지 않았다(호출 기록상 thread_update 1회).
- 참고: 저장 실행 8a2a1083… 은 저장·재독 assert 를 모두 통과한 뒤 결과 요약 함수의 null resolution 처리 오류(RECORD_REQUIRED)로 마지막 반환만 실패했다. 저장은 영수증(Q2 rev2, Q3 rev2)으로 확인했고 다시 저장하지 않았다.
- 이 change.md 2차 절의 첫 기록은 f-문자열 보간 실수로 자리표시가 문자 그대로 남아, 같은 내용을 보간을 고쳐 다시 썼다(1차 절은 그대로).

## 6. 판정 칸 (2차)
| 항목 | 결과 |
|---|---|
| 새 논문 보존 | 달성 — version_ref 1ef1b433dc234bc580af9d483febbcae, coverage full |
| 영향 질문만 갱신 | 달성 — Q2·Q3 만 rev2, 인용은 보존 판본 원문 포함 assert 통과 |
| 종결 질문 | Q1 충돌 없음 판단 → 재개 안 함, 판본 유지(재독 확인) |
| 저장 충돌 | 발생 안 함 (재저장 분기 미실행) |
| change.md | 이 절 추가 후 재독 확인 |

## 7. 보장 / 비판정
- 보장: 인용 문자열이 보존 판본(version_ref·extraction_revision 1)의 해당 쪽 추출문에 그대로 있다는 것(프로그램 assert + 서버 인용 검사), 판본 사슬.
- 판정하지 않음: 인용이 질문의 주장을 실제로 지지·반박하는지(위 방향은 실행자의 판단 기록), 논문 주장의 참·거짓, 출처 독립성(Jin et al. 2024 가 기존 Q2 반박 인용 속 'Jin et al., 2024' 와 같은 논문일 수 있음 — 미확인).
