# 반사 규칙 모순 수리 (2026-09-26)

## 증상
반사(해마 낱말 채널 top-1 점수 ≥ 0.85 → 분류기 없이 곧장 EXECUTE)가 09-23 이후 한 번도 발동하지 않았다.
같은 자리를 지나는 반사 귀속(`record_recall_outcome`, top_code 필요)도 0건. 실행기억 `<ref>` 는 전부 `body_omitted="true"`.

## 원인 — 같은 날 들어온 두 규칙이 서로의 여집합을 걸렀다
`ibl_usage_rag._top_for_execution` 은 top-1 이 `exclusion_reason(row) or reference_needs_expansion(code)` 이면 코드를 비우고 점수를 0.80 으로 눌렀다.

| 규칙 | 커밋 | 판정 |
|---|---|---|
| `corpus_policy.exclusion_reason` | `0f16fa09` 09-23 "코퍼스 전수 판정과 현재 판본 소비 경계 마감" | 판본 1(구형) → `legacy_source` 제외 |
| `hippo_tree.reference_needs_expansion` | `1d12a775` 09-23 "판본 2의 기존 어휘·관용구·학습 경로 연결" | 판본 2 → 무조건 숨김(`source_edition(code) == 2`) |

판본은 1 아니면 2 이므로 OR 는 항상 참이다. 실측(ibl_usage.db 3,721행): 판본 1 2,481행은 자격에서, 판본 2 1,240행은 노출에서 걸려 **반사 후보 0건**.
판본 2 통째 숨김은 코퍼스 감사 계획(`IBL_CORPUS_AUDIT_PLAN_2026_09_23.md` 3단계 "즉시 반사 후보로 승격하지 않는다. 자격 정책을 먼저 확정한다")의 자리표였고, 그 자격 정책이 같은 날 `exclusion_reason` 으로 확정되면서 자리표를 걷어야 했는데 남았다. 시험 `test_corpus_policy.py` 가 이 상태를 단언으로 고정하고 있었다.

## 수리
- **역할을 가른다.** 자격(판본·검토 판정)은 `exclusion_reason` 이, 노출은 길이(>1200자)와 문장 수만 본다. `reference_needs_expansion` 에서 판본 조건 제거.
- **판본을 아는 문장 수** `hippo_tree.sentence_count` 신설 — 판본 2 는 헤더·주석을 뺀 최상위 문장(`v2_statements`, 따옴표·괄호 밖 줄바꿈/`;` 경계 = 판본 2 문법의 문장 경계), 판본 1 은 `split_sentences`. 판본 헤더가 깨지면 0 → 숨김.
  `split_sentences` 자체는 손대지 않았다 — 증류·관용구 기계가 판본 2 를 한 단위로 본다는 전제(test_ibl_v2_assets) 위에 있다. 파서(ibl 층)는 data 층에서 부를 수 없어(층 가드) 같은 스캐너 규칙을 쓴다.
- 숨긴 본문의 "(문장 n …)" 표시도 `sentence_count` 로.
- 반사 거부권 위험 축(`_reflex_veto` ②): `op: "deploy"` 문자열 목록 → 정규식. 저장 용례 다수가 JSON 꼴 `{"op":"run",…}` 이라 옛 목록은 그 표기를 놓쳤다.
- 시험: `test_corpus_policy.py` 단언을 정책대로(현재 판본 한 문장 = 인라인 노출 + 반사 후보), 회귀 `test_reflex_rules_2026_09_26.py`.

## 수리 후 실측
| 구분 | 행 |
|---|---|
| 자격 제외(판본 1, legacy_source) | 2,481 |
| 노출 숨김(여러 문장 4 · 1200자 초과 4) | 8 |
| **반사 후보** | **1,232** |

판본 1 행은 코퍼스 정책대로 여전히 반사하지 않는다(구형 원문은 현재 작성 정답이 아니다). 판본 2 로 이식되는 만큼 후보가 는다(`IBL_MIGRATION_REMAINING_PLAN_2026_09_23.md`).

## 바뀌지 않은 것
반사 임계 0.85, 낱말 채널만 반사(관용구 제외), 거부권 ①(`>>` 다단계)·③(요구 여럿), 긴 붙여넣기 문서 0.80 캡, `distilled_component` 캡, 소유 필터, REPAIR 단서 우선.
