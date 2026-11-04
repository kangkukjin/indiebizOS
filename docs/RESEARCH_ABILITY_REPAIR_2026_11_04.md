# 범용 연구 능력 수리 — 구현과 검증

출발점은 에피소드 5810의 `data/outputs/deep_research_2026-11-04/repair_plan.md`다.
목적은 질문과 근거의 의미·판본을 종합과 검수까지 전달하고 같은 결과의 품질·비용을 비교하는 것이다.
새 어휘·상시 모델·운영 DB는 추가하지 않는다. 아래 구현은 연구 판단의 정답을 인증하지 않는다.

## 범위와 소유자

| 계획 | 구현·보존 | 판단 |
|---|---|---|
| R0 | 기존 planning의 sparse completion, 명시 false 거절, 한정 재시도, keep/revise 검사 재사용 | 과거 5600 실패를 현행 버그로 재수리하지 않음 |
| R1 | research_questions.context에 origin·revision_digest·omitted_fields·omitted_refs·unlisted와 상세 회수 경로. 명시 ID→오래 열린 질문→어휘 관련성 순. revision은 불변 상세 회수 | 기존 질문/계획 필드 사용, 스키마 이전 없음 |
| R2 | research_review.passages와 research_library.citation_review. 같은 인용의 주장별 창 및 질문 근거의 명시 quote를 동일 예산에 배분. read receipt별 정확한 구간·추출 판본 | 원문 중요도는 모델/사람 판단. 임의 의미 필드를 evidence에 추가하지 않음 |
| R3 | research_planning.execution_block의 기존 진행 문장을 불확실성→판별 자료→판단 변화로 구체화. gaps·next_probes와 종결 관문 유지 | 지침 변경은 이 구현 요청 아래 외부 개발자가 적용. 새 필수 폼/종결 완화 없음 |
| R4 | research_capture.review에서 질문 판본/근거 관계를 묶어 final_evaluator로 전달. research_claims의 위치를 occurrence_refs로 공유. 질문/읽기 판본 변경 시 snapshot_error | 평가 기준은 유지. segments와 질문 상태를 해석하는 안내만 추가 |
| R5 | TurnResearch의 미지원 표면을 framing/실행/평가에 명시. 네이티브 스트림의 동일 호출·동일 반환 중복만 제거 | 시스템 AI/회원 제외 유지. 새 호출이나 다른 반환은 별도 포획 |
| R6 | research_measurement + scripts/measure_research_result.py. 기존 5767 비용 분석을 공용 소유자로 이동하고 summarize_usage·billable_identity 재사용 | 오프라인 읽기 전용. 미측정·충돌·미귀속 보존. 효과 인증 없음 |

질문 투영은 내용과 생략 참조에 같은 예산을 사용한다. 전체 응답의 고정 메타데이터와
회수 안내는 별도이며 `projection_chars`는 내용·참조의 직렬화 문자 수다. 예산에 모든 주소가
들어가지 않으면 목록 페이지를 읽고, `question_history:true`에서 revision·revision_digest가
같은 판본을 선택한다. 최신 판본을 옛 요약과 합쳐 쓰지 않는다.

근거 발췌는 인용당 최대 2,400자, 전체 원문 16,000자를 유지한다. 단일 구간은 기존 quote,
여러 구간은 quote=null 및 segments[].quote다. start/end는 해당 access_id의 읽기 영수증
문자열 좌표이며 원 문서 전체 좌표가 아니다. locator·version_ref·extraction_revision과 함께
해석한다. 서로 다른 추출 판본을 연속된 원문처럼 합치지 않는다. 구조 메타데이터 비용은 별도다.
명시 근거를 온전히 전달하지 못하면 question_links.included=false이고 원문 상세가 필요하다.
이전 턴 근거가 있다는 이유로 현재 턴에 읽었다고 처리하지 않는다.

## 표면과 격리

| 표면 | 신원/보존/정리 |
|---|---|
| 일반 심층연구 | 등록 프로젝트 경로·실제 actor+conversation session, session 없으면 task. 기존 research_task_links와 run. 예외/취소에도 finally 정리 |
| 전용 연구 | project_uid+thread_id+run, ResearchRunner의 기존 역할과 library 모드 유지 |
| MCP 재진입 | 서버가 bind_execution한 actor/task와 프로젝트 경로만 adopt. 종료 뒤 신원 회수 |
| 네이티브 반환 | 활성 연구의 실제 도구 반환만 포획. 같은 스트림의 중복 반환만 제거; 획득 범위가 불명확하면 기존 unknown 상태 유지 |
| 시스템 AI | 자동 자료실 연결 미지원. 기존 파일/실행 근거 사용을 명시 |
| 회원 | 사설 소유권 대응 미확인으로 연결 미지원. 회원/대화 격리 조건을 삭제하지 않음 |

R5는 전 표면 연결 확장이 아니다. 운영 대화 이전·가짜 ID·회원 권한 변경은 없다.

## 비용과 사람 검토

```bash
.venv/bin/python3 scripts/measure_research_result.py \
  --database data/world_pulse.db --episode 5810 \
  --artifact data/outputs/deep_research_2026-11-04/repair_plan.md \
  --task research-plan --variant observed \
  --out data/outputs/research-plan-measurement.json
```

선택적 `--conditions`는 모델/설정/자료/예산/캐시 조건 JSON, `--review`는 아래 형태의 사람
관측 JSON이다. 같은 artifact_sha256만 연결하고 다른 판본은 거절한다. 원문 답변과 사람 수정본을
비교할 때 각각 판본별 기록을 만들며, 글자 diff를 의미 수정량으로 대신하지 않는다.

```json
{"artifact_sha256":"실제 SHA-256", "active_review_seconds":null,
 "active_edit_seconds":null, "critical_claim_changes":null,
 "correction_types":[], "quality":null, "usable_result_elapsed_ms":null}
```

비용은 episode·run·parent_call_id 계보로 model.usage만 합친다. snapshot/boundary 사건은
청구가 아니다. usage_id(구판은 call/round)가 같은 기록은 한 번만 세고 충돌은 별도 보고한다.
input에는 cache, output에는 reasoning이 포함되며 다시 더하지 않는다. `input_plus_output`은
관측된 부분합이지 전체 비용 보증이 아니다. 없는 output/세부 계수는 null이며 미측정 호출·부모 없는
비용·후처리/외부 실행의 미결합 가능성을 보존한다. provider별 정규화는 기존 ProviderMetrics가
소유한다. 운영 DB를 수정하거나 누락 모델을 다시 호출하지 않는다.

## 검증과 효과의 경계

합성 계약 검사는 사용자 정정·CAS·오래된 질문·작은 예산·읽기/추출 판본·떨어진 정의와 한계·
같은 파일의 질문 변경·네이티브 중복·다른 대화 격리·캡처→읽기→질문→제출→검수 왕복을 다룬다.
기존 계획 실패/종결/원문 회수 검사는 그대로 유지한다. 비용 검사는 후처리 계보·중복·충돌·
실패/미측정·캐시/추론 부분집합·사람 검토 판본을 확인한다.

개발 비교 도구 `docs/experiments/research_ability_2026_11_04/probe.py`는 합성 고정 자료
4종(모형/관측, 목표/체결, 정격/실사용, 전재/독립 원천)에서 단일 창과 다중 구간을 비교한다.
명시 anchor는 연구자가 이미 선택한 것으로 통제한다. 이를 자동 중요도 선택의 성공으로 해석하지
않는다. `--models`는 현재 평가 모델을 같은 조건·새 대화·도구 없이 최대 8회 호출한다.
이는 개발 진단이며 잠금 과제 평가·실제 검색·사용자 이해/수정 비용 측정은 별도다.

검증 기록:

- 관련 계약·비용 회귀 200개 통과. 네이티브 ID 재사용 처리 후 관련 96개 재확인 통과.
- 첫 비system 전수는 12,367 통과·9 건너뜀·정적 규약 실패 2건이었다. 새 오프라인 SQLite
  읽기의 timeout=10과 내부 검색 창의 누락 신고 설명을 보완했다. 실패 항목/인접 검사 12개 통과.
- 관련 system은 Python 라이브러리와 실제 세대 프로세스 검사 53개 통과(79.00초).
- 층 검사, IBL 파생 정합 검사, Android 몸 번들 재생성 통과.
- 활성 백엔드의 변경된 운영 모듈 7개와 정본 소스 일치, HTTP /health에서 ACTIVE·healthy 확인.
  HTTP /ibl/execute로 임시 Script를 실행해 활성 세대의 모듈로 격리 합성 자료실을 만들고
  저장→읽기→질문→검수 왕복 성공. 두 구간, 원문 2,400자, 동일 질문 판본 및 semantic_status=unreviewed 확인.

실제 모델 개발 비교는 현재 `gpt-6-astra:high`로 8회 모두 응답했다. 양쪽 모두 네 질문에
틀린 확정 결론을 내리지 않았다. 새 발췌는 정의와 한계를 모두 4/4 전달했고 단일 창은 0/4였다.
새 답변은 성분 모형·계약 분모·부하율·전재 관계 등 제공된 구별을 설명했다. 이는 명시 anchor의
전달 효과이며 자동 근거 선택이나 분야 일반성의 증명이 아니다.

| 개발 비교 합계(조건별 4회) | 단일 창 | 다중 구간 |
|---|---:|---:|
| 관측 input+output 토큰 | 52,527 | 52,651 |
| 그중 cache_read | 33,792 | 33,792 |
| 직렬 호출 경과 합(초) | 45.09 | 43.50 |

토큰은 124개 증가했다. 소수 호출의 지연 차이로 속도 향상을 주장하지 않는다. 사람 검토 시간과
사용자 이해는 미측정이며, 잠금 평가를 했다고 보고하지 않는다. 원문 응답·호출별 비용·자료 지문은
[개발 비교 기록](experiments/research_ability_2026_11_04/result_summary.json)에 있다.
새 측정 CLI도 에피소드 5810의 저장 결과에 실행했으며, 후처리 포함 6개 청구 기록을 읽고
같은 파일 지문에 연결했다. 사람 평가·사용 가능 시점·조건 일치의 미측정을 그대로 표시했다.

## 적용·복구

정본 main에 대상 파일만 커밋한다. backend 변경은 Android 번들 재생성과 층·IBL 정합 검사를
거치며, 최종 평가 경계의 활성화는 기존 keeper/세대 제어자가 소유한다. 수동 표식을 만들지 않는다.
운영 질문/자료실 스키마를 바꾸지 않았으므로 롤백은 코드 판본 복구이며 신규 연구 자료는 유지한다.
오류가 생긴 표면은 원문·질문 판본과 실패를 보존하고 기존 검증 판본으로 복구한다.
