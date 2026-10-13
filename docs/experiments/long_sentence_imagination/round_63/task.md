# 63회차 — 연구 질문을 실원문 근거로 이어가고 종결하기

설계: [LONG_SENTENCE_ROUND63_DESIGN_2026_10_13.md](../../../LONG_SENTENCE_ROUND63_DESIGN_2026_10_13.md).
시작 2026-10-13 13:06 KST, 정본 main `a9fd00ce`(다른 세션의 미커밋 24파일 — guest-helper·resident_pcs, 이번 이음새와 무관), 백엔드 ACTIVE 세대 `5f1e74dd`, 시작 전 마지막 에피소드 4667. 상한 60분. 로컬 작업 폴더 `outputs/long_sentence_imagination/2026-10-13_63회차/`.

## 자연어 요구 (시스템 AI 에도 그대로)

긴 문맥 언어모델과 검색증강 생성(RAG)의 상대 성능을 조사하는 연구 대화를 열어 줘. 제공한 공개 논문 원문 여덟 편을 그 대화의 자료실에 보존하고, "어떤 조건에서 긴 문맥이 RAG 를 이기는가", "둘을 섞는 방식이 비용 대비 나은가", "평가 벤치마크가 결론을 바꾸는가" 세 질문을 기록해 줘. 질문마다 잠정 답변을 쓰고, 지지하는 문장과 반박하는 문장을 원문에서 정확히 인용해 연결하고, 아직 확인하지 못한 것과 다음에 볼 것을 남겨 줘. 근거가 충분한 질문만 답변으로 종결하되, 반박을 지우거나 숨겨서 종결 조건을 맞추지 마. 저장이 끝나면 질문 기록을 다시 읽어 저장된 것과 네가 뜻한 것이 같은지 확인하고, 질문별 판본·근거 수·상태를 표로 남겨 줘. 그다음 이 대화의 기억이 없는 새 호출로서, 기록만 읽고 조사를 이어받아 종결 가능한 질문을 판정해 줘. 이후 제공하는 추가 논문 한 편은 이미 종결한 질문과 충돌할 수 있어. 영향받는 질문만 다시 열고 나머지 질문의 판본은 그대로 두며, 무엇을 왜 바꿨는지 적어 줘. 다른 대화의 자료는 쓰지 말고, 논문이 참인지는 판정하지 말고 인용이 원문과 같은지만 보장해 줘.

## 입력 (실자료, 전부 공개 arXiv 원문)

검색은 `[sense:paper]` 로 했다. arXiv 원천은 제목 검색이 전부 0건(success)이었고 OpenAlex 가 찾아 arXiv 번호로 대응시켜 `download` 했다(운영 관측 §발견). PDF 사본과 해시는 `papers/pdf_index.json`.

| # | arXiv | 제목 | 용도 |
| --- | --- | --- | --- |
| 1 | 2307.03172 | Lost in the Middle: How Language Models Use Long Contexts | 기본 |
| 2 | 2406.15319 | LongRAG: Enhancing Retrieval-Augmented Generation with Long-context LLMs | 기본 |
| 3 | 2501.01880 | Long Context vs. RAG for LLMs: An Evaluation and Revisits | 기본 |
| 4 | 2409.01666 | In Defense of RAG in the Era of Long-Context Language Models | 기본 |
| 5 | 2404.06654 | RULER: What's the Real Context Size of Your Long-Context Language Models? | 기본 |
| 6 | 2406.13121 | Can Long-Context Language Models Subsume Retrieval, RAG, SQL, and More? | 기본 |
| 7 | 2402.14848 | Same Task, More Tokens: the Impact of Input Length on the Reasoning Performance of LLMs | 기본 |
| 8 | 2411.03538 | Long Context RAG Performance of Large Language Models | 기본 |
| 9 | 2410.05983 | Long-Context LLMs Meet RAG: Overcoming Challenges for Long Inputs in RAG | **변형(늦게 도착)** |

연구 프로젝트 `d3bbe55090f54d52b435184e068b4148`(긴문장63 긴문맥 대 RAG). 대화: 훈련자 `b7144a55…`, 시스템 AI `9bf7c088…`, 미끼 `8ee19ab7…`(논문 1 이 들어 있음, version_ref `46292dc0…` — 다른 대화 자료 거부 탐침용).
자료실 추출 locator 는 PDF 쪽 단위 `p.N` 이며 추출은 결정론적이라 운영자 사전 표는 백엔드 추출기로 오프라인 계산했다(`papers/paras_*.json`).

## 공개 판정 계약 (양쪽에 동일)

1. 검사 결과 / 실행 상태 / 과제 달성은 별도 칸. 달성은 필수 조건 전부에 근거가 있을 때만.
2. 코드가 보장하는 것 = 인용 원문 일치·보존 자료 판본·판본 사슬·종결 조건. 인용이 주장을 실제로 지지하는지·논문이 참인지·출처 독립성은 판정하지 않는다. 섞어 쓰면 실패.
3. 거부는 결함이 아니다. 거부를 받고 보존하면 달성, 거부를 우회하면 미달.
4. 판정 행은 `(project_ref, question_id, revision)` 과 실행 ID·산출물로 거슬러 올라간다.
5. 재개 호출은 앞 프로그램의 변수·result_ref 를 받지 않는다. 받는 것은 `project_ref·thread_ref` 두 값뿐.
6. 비용은 작성·실행·복구·운영 구분, 같은 과금 이벤트 중복 합산 금지.

## 심는 조건과 실행 전 기대 (운영자, 실행 전 고정)

| 조건 | 기대 |
| --- | --- |
| 원문에 없는 문장 quote | 거부, 보존, 성공으로 세지 않음 |
| 같은 인용을 지지·반박에 동시에 | 거부 |
| 미끼 대화의 version_ref `46292dc0…` | 거부 |
| extraction_revision 2 | 거부 |
| gaps 남긴 answered | 거부 |
| 반박 있는 질문을 objections 없이 answered | 거부 |
| 운영자가 같은 질문 판본을 올린 뒤 옛 expected_revision 으로 저장 | 충돌 → 최신 판본 재읽기 → 재저장, 사슬 유지 |
| 같은 문장·범위 질문 재생성 | duplicate_candidates, 자동 병합 없음 |
| 논문 9 추가 뒤 종결 질문 | 닿는 질문만 자동 재개, 무관 질문 revision 불변, 이력 보존 |
| 기억 없는 재개 | `project_ref·thread_ref` 만으로 질문·근거·이력 회수 |

변형 기대: 논문 9 는 "검색 구절을 더 넣을수록 좋다는 이전 연구(Li 2024·Xu 2023)에 반해 성능이 올랐다 내려간다" 를 말하므로 질문 1·2 에 닿고 질문 3 에는 닿지 않는다. 질문 3 의 revision 은 변형 전후 같아야 한다.

## 되먹임 블록 (개정 §6 첫 적용)

56회차 `task.md` 요청문을 글자 그대로 `/system-ai/chat`(origin training, background) 으로 13:06 에 보냈다. 기본 `task_sysai_a348e83f`, 변형(보증금 1억5천) `task_sysai_c5d40358`. 기준선: ep4604 146.758초·수집 IBL·비교 Python·RESULT_MISSING(L56-5), ep4605 56.470초·재검색 0·반환 오류 재발. 비교 축 = 경로 선택·같은 오류 재발·시간·토큰. 표본 1회.
