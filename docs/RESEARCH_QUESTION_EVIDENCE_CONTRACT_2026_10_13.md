# 연구 질문·근거 계약

작성일: 2026-10-13. 상태: **연구 대화용 첫 구현 반영**.
선행 설계: [연구 프로젝트](RESEARCH_PROJECT_DESIGN_2026_10_10.md),
[IBL 근거 보완](IBL_EVIDENCE_AND_PARTIAL_RECOVERY_DESIGN_2026_09_23.md).
REA의 ResidualUnknown에서 지속 질문·변경 이력·반박 보존 원리를 참고하되 역공학의 권위 등급과 자동 검증은 옮기지 않는다.

## 1. 목적과 구현 선택

다음 턴에서 이전 질문·잠정 답변·반박·남은 확인 사항을 이어받도록 한다.
저장 자체가 연구 품질 향상의 실증은 아니다. 실제 연구에서 반박 누락·근거 없는 종결·질문 재발명을 줄이는지 관찰한다.

초안의 내부 저장소 우선(A) 대신 **기존 thread_update의 questions 변경목록(B)**을 선택했다.
AI와 사용자가 동일한 공개 경로를 사용해야 실제 연구에서 쓰이고 검토될 수 있기 때문이다.
새 액션이나 op, 별도 질문 추출 모델 호출은 추가하지 않는다. 사용자 관점 notes와 질문 기록은 분리한다.

질문 수명은 **같은 프로젝트의 같은 대화**다. 다음 날 같은 대화를 재개하면 회수되며,
다른 대화로 자동 공유하지 않는다. 기존 대화별 자료 격리 원칙을 유지한다.
프로젝트 복제는 질문·자료·대화 ID와 판본을 보존하며 project_ref만 새로 발급한다.
따라서 질문의 전역 신원은 `(project_ref, question_id)`이다.

## 2. 저장 계약

`research_questions`에 판본 전체를 append한다. 한 변경 묶음은 하나의 트랜잭션이다.
각 변경은 research_events의 question.created/question.updated 사건을 남긴다.
이 사건은 판단 변경의 기록이며 답의 증명이 아니다.

| 필드 | 의미 |
| --- | --- |
| question_id | UUID hex. 문장을 바꿔도 유지 |
| revision, previous_revision_digest, revision_digest | 판본·이전 지문·현재 지문. 읽기와 갱신에서 사슬 검사 |
| fingerprint | NFC·공백 정규화한 질문+범위의 SHA-256. 열린 중복 후보 안내용 |
| text, scope | 질문과 범위. 각 1000자 이하 문자열 |
| provisional_answer | 잠정 답변. 4000자 이하. 질문 자체와 분리 |
| supporting, contradicting | 아래 근거 참조 목록. 각각 최대 30개 |
| gaps, next_probes | 남은 확인·다음 조사. 각각 최대 30개 문자열 |
| status | open / resolved. resolution에서 파생 |
| resolution | null 또는 disposition·rationale·objections |
| origin, run_id, event_sequence, created_at | 사용자/AI, 실행과 변경 사건, 시각 |

모든 변경에는 expected_revision이 필요하다. 생성은 0, 갱신은 현재 판본이다.
충돌하면 최신 원문을 다시 읽어 반영한다. 같은 fingerprint는 생성 금지가 아니라 중복 후보로 반환한다.
유사 의미의 다른 문장을 자동 병합하지 않는다. 내용 해시는 진위나 악의적 DB 변조에 대한 인증이 아니다.

## 3. 근거 참조

```json
{"version_ref":"보존 자료 UUID", "extraction_revision":1,
 "locator":"원문 문단 위치", "quote":"그 위치의 정확한 인용"}
```

서버가 내용에서 evidence_id를 계산하고 observed_in 목록을 부여한다.
검사기는 같은 대화의 research_captures, 불변 추출 판본과 blob 지문, locator의 인용 부분문자열 일치를 검사한다.
AI가 새로 연결하는 근거는 현재 run의 research_access에서 실제 전달된 구간 안에 있어야 한다.
기존 연결을 재사용하면 원래 읽기 영수증을 유지한다. 클라이언트가 보내는 observed_in으로 읽기를 위조할 수 없다.
사용자 수동 인용도 원문은 검증하되 모델 읽기 영수증을 만들지 않는다.
현재 research_access는 run 단위이므로 call_id는 만들어내지 않는다.
동일 인용을 지지·반박에 동시에 두거나 한 목록에서 중복시킬 수 없다.

검증되는 것은 원문 일치와 접근 이력이다. **인용이 실제로 주장을 지지하는지, 자료가 참인지, 출처들이 독립적인지는 판정하지 않는다.**
research_sources.kind는 수집 방식이지 일차·공식 출처 권위가 아니다.
서로 다른 source_id는 독립 출처를 보증하지 않고, observed_in은 실행 실험의 증거가 아니라 읽기 기록이다.
발행 시각·출처 독립성·실험 결과에 대한 조건 검사기는 아직 구현하지 않는다.

## 4. 종결과 재개

resolution은 다음 중 하나다.

- answered: 잠정 답변과 지지 근거가 있고 gaps가 비어 있어야 한다. 모든 반박 evidence_id에 검토 이유를 남긴다.
- withdrawn: 질문 철회와 이유.
- out_of_scope: 현재 범위 밖이라는 판단과 이유.

모든 종결에는 rationale이 필요하다. verified는 지원하지 않는다.
answered 역시 **실행자/사용자의 판단**이며 코드가 진리를 검증했다는 뜻이 아니다.
반박을 지우거나 남은 확인을 숨겨서 종결하지 않도록 실행 지침에서 명시한다.
내용 변경이 들어오고 종결을 다시 명시하지 않으면 자동으로 열린다.
resolution:null로 명시적으로 다시 열 수도 있다. 과거 판본·반박·종결 이유는 남는다.

## 5. 사용과 회수

공개 사용 예시는 [연구 질문 가이드](../data/guides/research_questions.md)에 있다.

- self:project thread_update + questions: 전체 목록 교체가 아니라 **질문별 변경 묶음**.
- self:project thread_messages + questions_only:true: 목록·검색·페이지·단일 질문.
- question_id + question_history:true: 해당 질문의 판본 이력.
- self:notebook read: 해당 추출 판본의 원문 회수.
- 연구 대화 헤더의 **연구 질문**: 목록, 추가·수정, 잠정 답변, 지지·반박, 원문 페이지, 종결·재개, 변경 이력 비교.

주 실행 모델에 7500자 예산의 질문 요약 목록을 전달한다. 열린 질문 우선이며 생략 건수를 표시한다.
모델은 필요한 전체 기록을 같은 공개 도구로 읽고 업데이트한다. 요약 목록은 새 원문 읽기가 아니다.
저장은 모델의 판단에 따른 도구 호출이다. 매 답변마다 강제 저장하거나 별도 API 모델을 부르지 않는다.
화면의 인용 추가는 현재 대화에서 AI에게 자료를 읽고 연결하도록 요청한다.

## 6. 검증과 남은 범위

`backend/test_research_questions.py`는 동시 수정·배치 롤백·재개·원문 일치·대화 격리·
AI 읽기 영수증 위조 거부·종결 조건·새 정보에 의한 재개·판본 손상·복제 신원을 검증한다.
기존 연구 저장소·대화 시험과 공개 IBL 경로도 함께 검증한다.

초안의 범용 source_id/source_hash 어댑터, 작업 단위 missing[]/gap과의 연결,
requirement 술어 평가, 질문 관계 그래프와 범위 변경 supersedes,
대화 간 명시적 공유는 **미구현**이다. 연구 질문의 gaps는 현재 문자열 목록이다.
독립적인 공통 IBL 봉투 필드를 추가하지 않고, 실제 두 번째 소비자가 생길 때
research_evidence의 검증 경계에서 어댑터를 합친다.
연구 품질의 효과 측정과 실제 모델이 기록을 얼마나 잘 유지하는지는 별도 실사용 검증 대상이다.

검증 기록(2026-10-13): backend 비system 종합 회귀 **10092 passed, 1 skipped**,
어휘 archive/bundle 관련 system **23 passed**. TypeScript, Vite 빌드, IBL 파생물 일치,
층 가드 통과. Chromium에서 실제 질문 컴포넌트와 API 대역으로 저장·충돌 초안 보존·이력 보기를 확인했다.
공개 IBL 경로의 생성·조회는 backend 회귀에서 별도로 확인했다. 실 API 모델을 호출한 연구 품질 비교 실험은 수행하지 않았다.
