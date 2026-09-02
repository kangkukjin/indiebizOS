# 구성요소 수준의 죽음 + 야간 하향 정규화 — 설계 핸드오프

*작성: 2026-09-02 (Claude Code). 사용자 지시 "1번부터 설계해봐. 4번도 같이." → 같은 날 **⚖ 2건 승인 + 구현 완료**(미커밋).*

> **구현 현황 (2026-09-02)** — `backend/cognition/component_lifecycle.py`(일일 전이·집행·판정 큐·번들 입구
> `run_lifecycle_bundle`) · `backend/cognition/guide_downscale.py`(주간 압축·기계 대조) · `pulse_db.workflow_run`
> 원장 + `action_health.n_items` 컬럼 · `guide_registry.guide_section_use`(절 귀속, guide_feedback 이 매 턴 기록) ·
> `scripts/check_file_size.py` 가이드 예산 규칙 집합(pre-commit 트리거에 `data/guides/*.md`) · `data/lifecycle_policy.yaml`
> · 회귀 고정물 `backend/test_component_lifecycle.py`(15) `backend/test_guide_downscale.py`(8). 라이브 첫 실행: 231항목
> 전부 alive/grace(첫 관측 = 2026-09-02 → candidate 최초 가능일 10-02, retired 최초 가능일 12-31).
>
> **설계와 다르게 한 것(이유)**: ①어휘 candidate 표식을 `ibl_actions.yaml` 에 쓰지 않고 상태·깃발 파일+알림으로만
> (카탈로그는 빌드 산출물이라 src 편집→빌드 의무가 생기고, 어휘 은퇴는 어차피 판정 큐다) ②가이드·워크플로우 은퇴를
> `retired_contracts.yaml` 에 적지 않고 `lifecycle_state.json` 의 retired 원장 + 커밋 메시지로(그 등록부는 *문구 계약*
> 관문의 입력이라 가이드 파일명이 들어갈 자리가 아니다) ③압축 관문의 "필수 파라미터 보존"은 기계로 정의가 안 서서
> 어휘 참조·절 제목·살아 있는 코드 경로 셋만 대조 ④`runs_on: phone_only` 낱말은 이 몸이 실행을 관측 못 하므로
> `body:phone` 이 지지자(관측 불능≠무신호).

> **한 줄**: 세대 교체가 없는 한 개체(indiebizOS)는 게놈이 정리될 기회가 없으므로, 죽음을
> **구성요소 수준**으로 들여와야 한다. 지금 시스템은 "죽음의 집행기는 있고(은퇴 등록부·코퍼스
> 이관·좀비 청소) **신호와 방아쇠가 없다**" 상태다 — 일곱 순찰이 깃발만 세우고, 실제 정리는
> 사람이 손으로 한다(2026-08-17 가이드 81KB · 09-02 가이드 셋 67→21·62→30·79→34KB).
> 기본값을 **생존→사멸**로 뒤집되, 생존 신호를 "사용 계수"가 아니라 **영양 지지(참조 그래프)
> + 쓸모 있는 실행**으로 정의해 계절성·유지보수 어휘 오살을 막는다.

관련 기억: `architecture_evolution_unit_ibl`(진화 단위=IBL, 앱=단백질, 생물에서 배울 것 ①④).
관련 원칙: no-counter-watch(셀 수 있으면 관문이 실패시킨다) · root-fix-not-verdict(판정=언어 개정·
파괴적 변경 2종만) · decision-node-scoping-rejected(어휘를 AI 시야에서 숨기지 말 것) ·
no-concrete-sentences-in-guides · derived-artifact-expands-a-rule.

---

## 0. 왜 #1 과 #4 를 함께 설계하나

| | #1 세포 사멸(apoptosis) | #4 수면 하향 정규화(synaptic downscaling) |
|---|---|---|
| 단위 | 항목(가이드 파일·낱말·워크플로우·스크립트) | 항목 **내부**(가이드의 절·문장) |
| 사건 | 이산 — 있다/없다 | 연속 — 크기가 준다 |
| 판단 | 무LLM(구조+신호) | LLM(의미 압축) |
| 카덴스 | 일일(전이 계산) | 주간(예산 초과분부터) |

가이드 층에서 둘은 **같은 야간 패스의 두 동작**이다 — 항목을 지우거나, 항목을 줄이거나. 다른 층
(어휘·워크플로우·스크립트)엔 #1 만 적용된다(문장 내부가 없다). 해마엔 이미 둘 다 있다
(`consolidate_distilled` cap 200 + 불량 가지치기) — 이 문서의 대상 밖.

---

## 1. 현황 감사 — 층별 "생존 신호 / 집행" 표

| 층 | 생존 신호(있나) | 참조 그래프 소스 | 집행(있나) | 판정 |
|---|---|---|---|---|
| 심층메모리 DB | `used_at`(명시 읽기만 갱신, 09-02) | — | ✅ LRU cap 300 | 완료 |
| 해마 증류물 | trial/score | — | ✅ cap 200·불량 삭제 | 완료 |
| 포식 기억 | LRU | — | ✅ | 완료 |
| **가이드** (69개·808KB) | `guide_registry`: born/updated/clean_uses(origin=agent) · `guide_feedback`(쓴 놈이 고친다) · `guide_audit`(주간 6개 의미 순찰) | 가이드가 언급하는 `[node:action]` | ❌ 깃발만. 크기 무제한 | **이 문서 A·B** |
| **어휘(액션)** | `action_health`(success·shape·channel·source) · episode_log | 가이드·워크플로우·`app:` 블록·스케줄·해마 용례·스크립트 | 은퇴 **집행기** ✅(`retired_contracts.yaml`+관문·코퍼스 이관·좀비 청소) / **방아쇠 ❌** (`vocab_crystallization` 은 "은퇴 깃발 없음"을 설계 가드로 명시) | **이 문서 C** |
| **워크플로우** (`data/workflows/*.yaml`) | ❌ 실행 기록 없음(`workflow_engine` 은 안 남김) | `steps` 안의 액션 | ❌ | **이 문서 C** |
| **스크립트** (`data/scripts/registry.yaml`) | `data/script_runs/*.log` ✅ | 가이드·스케줄이 `id` 언급 | ❌ | **이 문서 C** |
| `app:` 블록 | 액션 실행이 곧 신호(0토큰 IBL 직접 실행) | 액션의 속성 | 액션과 생사 공유 | 별도 장치 불필요 |
| 커스텀 React 계기 | ❌ 열람 신호 없음 | 코드 | ❌ | **제외** — 유전자 없는 단백질(escape hatch). 사람 관리 목록 |
| `_backups`·고아 데이터 | mtime | `data_ownership.DECLARATIONS` | ❌ 30일 초과 **보고만** | **이 문서 D**(비가역 층) |
| system_docs 산문 | — | — | `doc_drift` 보고 | 대상 아님 — 문서는 죽지 않고 낡는다 |

핵심 발견: 어휘·가이드 층은 신호·집행기·순찰이 **각각 따로** 있고 이어져 있지 않다.
붙일 것은 셋 — ①참조 그래프 ②전이 규칙 ③전이의 결정권(가역성).

---

## 2. 원리 — 생물학을 규율로 번역

1. **기본값 반전**: 생존 신호가 없으면 죽는다. 삭제 신호가 없으면 남는 지금 기본값의 반대.
2. **영양 지지(trophic support)**: 뉴런은 표적이 영양인자를 주는 동안 산다. 항목은
   (ⓐ) 쓸모 있게 실행/주입됐거나 (ⓑ) **살아 있는 상위 구조가 참조**하면 산다.
   ⓑ 가 `vocab_crystallization` 이 두려워한 오살("사용 0 은 신호가 아니다 — 계절성·유지보수 어휘")의
   답이다: 유지보수 어휘는 가이드·스케줄이 참조하므로 살고, 계절 어휘는 그 계절 가이드가 참조한다.
   **참조도 없고 실행도 없는 것만 고아**다.
3. **계수 ≠ 쓸모** (`sense:search_local` 계수 19·결과 0, 2026-08-15): 실행 신호는
   `success=1 AND shape ∈ {items, records, …} (비어 있지 않음) AND source='usage' AND channel≠self_check`.
   `action_health.shape` 가 이미 통화 모양을 적으므로 새 컬럼 없이 계산 가능(빈 items 는 `shape` 판정기
   `ibl_envelope.classify_currency` 에서 구분되는지 구현 시 확인 — 아니면 `empty` 모양 1종 추가).
4. **신생 유예(neonatal grace)**: born 후 `grace_days` 동안 면제. 발달기 뉴런의 과잉 생성과 같다.
5. **단계적 죽음**: 세포도 신호를 통합한 뒤 죽는다. `alive → candidate → retired` 두 전이.
   candidate 는 **보이는 표식**(가이드 머리 주석·yaml 필드)이지 숨김이 아니다 — ★노드 스코핑 기각
   판정(어휘=창의성 재료)과 충돌하지 않게 **어휘를 AI 시야에서 빼는 dormant 단계는 두지 않는다.**
   candidate 기간에 신호가 오면 `alive` 로 돌아가고 **부활 사실이 기록**된다(계절성의 학습).
6. **결정권 = 가역성** (★생물엔 없는 우리 자산, git):
   - **가역 층**(git 추적: 가이드·워크플로우 yaml·스크립트·어휘 yaml): 기계가 `candidate` 표식까지 집행.
     `retired` 전이는 아래 ⚖1 판정에 따라 기계(커밋 라벨로 사후 검토) 또는 판정 큐.
   - **비가역 층**(라이브 DB·`_backups`·`outputs`): 사전 판정 — `PENDING_VERDICTS.md` 형식.
   - **어휘 은퇴는 층과 무관하게 항상 판정 큐** — 낱말을 지우는 것은 언어 개정이다(root-fix-not-verdict 의
     2종 중 하나). 기계가 하는 것은 **방아쇠와 증거 수집**(참조 0·쓸모 실행 0·마지막 사용·후계 후보).
7. **크기는 관문이 집행** (1500줄 선례 `check_file_size.py`): 가이드에 바이트 예산. 예산 초과 = 커밋 차단
   (신규) + 래칫(악화 금지) — **그리고** 야간 하향 정규화 패스의 대상.

---

## A. 가이드 층 — 죽음(#1)

**신호**
- 주입: `guide_use(origin='agent')` — 있음.
- **절 단위 사용 귀속(신설, `_recall_was_used` 패턴)**: 가이드는 통째로 주입되므로 파일 단위 신호만
  있다. `guide_feedback.review_used_guides` 는 이미 그 턴의 `tool_calls` 를 받는다 → 가이드의
  각 `##` 절이 언급하는 `[node:action]` 이 궤적에 나타났으면 **그 절이 쓰였다**고 `guide_section_use`
  에 적는다(일 단위 집계, 절 식별=헤더 텍스트 해시). LLM 0. 이것이 B(정규화)의 "무엇을 줄이나" 입력.
- 참조: 다른 가이드·`app:` 블록 desc·스케줄 잡이 이 가이드 파일명을 언급하면 지지.

**전이 규칙** (값은 `data/lifecycle_policy.yaml` 데이터 — 세계의 명사, 초기값 제안)
```yaml
guides:
  grace_days: 30          # born 후 면제
  candidate_after_days: 60  # 무주입·무참조 연속 60일 → candidate
  retire_after_days: 90     # candidate 로 90일 더 무신호 → retired
  budget_bytes: 36000       # 예산(09-02 사용자 만족 다이어트 결과 21~34KB 위)
```
- `candidate` 표식 = 가이드 첫 줄 HTML 주석(`freshness_note` 가 붙이는 자리와 같은 문법):
  `<!-- lifecycle: candidate since YYYY-MM-DD — 무주입·무참조 N일. 쓰이면 자동 복귀 -->`.
  `read_guide` 검색엔 계속 걸린다(숨김 아님).
- `retired` = `git mv data/guides/X.md data/guides/_retired/X.md` + `retired_contracts.yaml` 한 줄(있는
  집행기 재사용) + 커밋 라벨 `apoptosis(guide): X`. `_retired/` 는 `search_guide` 색인 밖.
  되살리기 = `git mv` 한 번.

## B. 가이드 층 — 하향 정규화(#4)

**대상 선정**: 예산 초과 가이드 상위 N(주 1회, `guide_audit` 의 PER_RUN 과 같은 절제) + `guide_audit`
깃발이 있는 가이드. 예산 안이고 깃발 없는 가이드는 건드리지 않는다(강한 시냅스는 남는다).

**무엇을 줄이나** — 세 부류, 우선순위 순:
1. **어휘와 어긋난 문장** — `guide_audit` 깃발·`retired_contracts` 금지 문구·`validate_guide_wiring` 죽은 경로.
2. **완성 처방** — no-concrete-sentences 규율 위반(자리표 골격이 아닌 완성 문장).
3. **쓰인 흔적 없는 절** — A 의 `guide_section_use` 가 관찰창(60일) 동안 0 인 `##` 절. 삭제가 아니라
   **한 줄 요약으로 압축**(절 제목 + "상세는 git 이력 <sha>").

**어떻게** — LLM 패스(주간, 고급 모델 아님 — 압축은 경량 티어 가능, 판단은 기계 대조가 맡는다):
- 입력: 가이드 본문 + 위 세 부류의 위치 표식 + 예산.
- 출력: 압축본.
- **기계 대조(관문)**: 압축본은 원본의 ①살아 있는 `[node:action]` 참조 집합 ②필수 파라미터 언급
  ③`##` 절 제목 집합(요약으로 남김) 을 **보존**해야 통과. 하나라도 빠지면 그 회차 건너뛰고
  `unchecked` 로 남긴다(판정 불가 ≠ 무결, `guide_audit` 규율 상속).
- 통과 시 `[self:body]{op:commit}` 로 커밋, 라벨 `downscale(guide): X 34→22KB`. 사후 검토 = 커밋 diff.
- **되먹임**: 다음 주입 시 `freshness_note` 가 "지난 정규화 YYYY-MM-DD" 를 적고, 압축 뒤 그 가이드를 쓴
  턴에서 `guide_feedback` 이 **사실오류를 고쳤다면** 그 절은 압축 금지 목록에 오른다(과압축의 학습).

**하지 않는 것**: 예산 안 가이드 자발 압축 X · 사용자 작성 산문의 "문체 개선" X · 삭제로 예산 맞추기 X
(예산은 압축·분할로만; 분할=모듈화 선례).

## C. 어휘·워크플로우·스크립트 층 — 죽음(#1)

**참조 그래프 구축**(무LLM, 일일, `backend/cognition/component_lifecycle.py` 신설·LAYERS cognition 등록):
- 노드: 액션(`ibl_nodes.yaml`) · 가이드 · 워크플로우 · 스크립트(`registry.yaml`) · 스케줄 잡 · `app:` 블록.
- 간선(참조): 가이드→액션(`validate_guide_wiring` 의 정규식 재사용) · 워크플로우 `steps`→액션 ·
  `app:` 블록→액션 · 스케줄 잡→워크플로우/스크립트/액션 · 가이드→스크립트 `id` · 해마 용례→액션
  (`ibl_usage.db`, `corpus_vocab_audit` 의 리프 워커 재사용).
- **지지 = 살아 있는 노드에서 들어오는 간선 ≥ 1**. 후보끼리만 서로 참조하면 지지가 아니다(고아 섬).

**실행 신호**:
- 액션: §2-3 정의. 창 = `candidate_after_days`.
- 워크플로우: **기록이 없다** → `workflow_engine` 실행 진입점에 `record_action_health("self","workflow", …,
  shape)` 와 같은 결로 `workflow_run(name, ts, ok)` 한 줄 추가(몸의 명사=코드). 이 한 줄이 없으면 층 전체가
  측정 밖이므로 **C 의 선행 조건**.
- 스크립트: `script_runs/<id>.log` mtime·행.

**전이**:
- `candidate`: yaml 에 데이터 필드 `lifecycle: {candidate_since: YYYY-MM-DD, evidence: "참조 0·쓸모 실행 0·마지막 YYYY-MM-DD"}`
  (어휘는 `ibl_actions.yaml` src 에 — 빌드가 파생물로 내리고 카탈로그 desc **뒤에** 한 줄 표식. 숨김 X).
- `retired`:
  - **어휘 → 항상 판정 큐**(언어 개정). 큐 항목에 증거와 **후계 후보**(같은 노드의 desc 유사 액션)를 실어
    사용자가 한 줄로 판정할 수 있게. 판정 후 집행은 있는 절차(`retired_contracts.yaml`·코퍼스 이관·
    `--check` 코퍼스 생존 가드·좀비 청소).
  - **워크플로우·스크립트 → 가역 층 규칙(⚖1)**: `_retired/` 이동 + 등록부 한 줄 + 라벨 커밋.
- 부활: candidate 상태에서 §2-3 신호 1건 → `lifecycle` 필드 제거 + `lifecycle_revivals.jsonl` 한 줄
  (무엇이·얼마 만에 — 이게 쌓이면 `candidate_after_days` 를 늘릴 근거가 데이터로 생긴다).

## D. 비가역 층 — `_backups`·`outputs` 고아

`data_ownership` 이 이미 30일 초과·미선언 항목을 **보고**한다. 바꾸는 것 하나: 보고서를 사람이 읽는
JSON 이 아니라 **`PENDING_VERDICTS.md` 형식의 판정 항목**으로 적립(`- [ ] YYYY-MM-DD — _backups/X 30일
초과 N MB · 삭제?`). 실삭제는 종전대로 사용자. 큐가 5건이면 상상훈련이 멈추는 규칙을 그대로 공유해
"보고만"이 영구 방치로 새는 것을 막는다.

---

## 3. 관문·회귀 고정물 (구현과 함께, 카운터-두고-보기 금지)

- `scripts/check_file_size.py` 에 **두 번째 규칙 집합**(가이드 바이트 예산 + BASELINE 래칫) 추가 — 파일별
  전개 X(derived-artifact 규율), 규칙 하나·대상 glob 하나. pre-commit 은 빌더 트리거 목록을 그대로 쓴다.
- `backend/test_component_lifecycle.py`:
  1. 참조는 있고 실행 0 인 어휘는 candidate 가 되지 않는다(유지보수·계절 어휘 오살 회귀).
  2. `success=1` 이지만 빈 통화(shape empty)만 있는 액션은 무신호로 센다(search_local 회귀).
  3. `source='test'`·`channel='self_check'` 실행은 신호가 아니다(2026-08-15 순찰 55% 오염 회귀).
  4. born 후 grace 안은 무조건 alive.
  5. candidate 실행 1건 → alive 복귀 + revivals 기록.
  6. 어휘 retired 는 판정 큐에만 적히고 파일을 건드리지 않는다.
  7. 후보끼리의 상호 참조는 지지가 아니다.
- `backend/test_guide_downscale.py`: 압축본이 액션 참조·필수 파라미터·절 제목을 하나라도 잃으면 커밋 안 됨
  + `unchecked` 기록. LLM 은 스텁.
- 야간 합류: `run_maintenance_bundle` 항목 **9) lifecycle(일일, 무LLM)** · **6.6) guide_downscale(주간,
  6.5 guide_audit 직후 — 깃발을 입력으로 받기 위해)**. 각각 자체 카덴스 게이트·실패 격리(번들 규약).
- 알림: 전이(candidate 진입·retired 커밋·판정 큐 적립) 발생 시 1건.

## 4. 하지 않는 것

- 자동 **승격** 없음(결정화 판단은 사용자 — 기존 감지기 가드 유지). 이 문서는 하향 방향만.
- 어휘를 AI 시야에서 **숨기는 단계 없음**(노드 스코핑 기각).
- LLM 이 생사를 **판단**하지 않는다 — 생사는 구조+신호, LLM 은 B 의 압축 작업만.
- system_docs 산문·커스텀 React 계기·해마 코퍼스는 대상 밖(각자 다른 장치).
- 수치(grace 30·candidate 60·retire 90·예산 36000)는 **정책 데이터**로 두고 부활 원장이 재조정 근거.

## 5. ⚖ 사용자 판정 필요 (2건 — 이 둘 외엔 묻지 않고 집행)

1. **결정권=가역성 해석**: git 추적 층(가이드·워크플로우·스크립트)의 `retired` 전이를 **기계가 집행하고
   커밋 라벨로 사후 검토**하는 것을 "파괴적 변경"으로 보지 않기로 하는가? (되살리기 = `git mv` 한 번.)
   기각이면 이 층도 어휘처럼 판정 큐로 — 처리량은 사용자 대역폭에 묶인다.
2. **가이드 바이트 예산의 존재**: 1500줄 규칙처럼 **관문이 커밋을 막는** 규칙으로 두는가?
   (초기값 36KB 는 09-02 다이어트 결과에서. 현재 위반 0, `new_action_checklist.md` 34KB 가 가장 근접.)

## 6. 구현 순서·규모

1. C 선행: `workflow_run` 기록 한 줄 + 실행 신호 정의 함수(§2-3) + 회귀 1~3 — 반나절.
2. 참조 그래프 + 전이 계산 + candidate 표식 쓰기(가이드 주석·yaml 필드) + 번들 9) — 하루.
3. 가이드 예산 관문(check_file_size 확장) + 절 단위 사용 귀속(guide_feedback 확장) — 반나절.
4. B 하향 정규화 패스 + 기계 대조 + 커밋 — 하루.
5. D 판정 큐 적립 형식 전환 — 한 시간.
6. 문서 표면: `data/system_docs/memory.md`(가이드=절차 기억의 생명주기 절 갱신) · `architecture.md` 면역계 행 ·
   `data/_backups/README.md`(판정 큐 언급) · 이 문서 → 구현 후 `changelog.log`.

첫 실측 목표: 한 달 뒤 `lifecycle_revivals.jsonl` 이 비어 있지 않으면(오살 직전 부활이 있었으면)
`candidate_after_days` 를 늘리고, 예산 관문에 걸린 가이드가 B 로 예산 안에 들어오는지 본다.
