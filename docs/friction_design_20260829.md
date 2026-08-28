# 실패 마찰 — 변경 확정 및 실행 순서 (2026-08-29) v3

범위: 설계·순서 확정까지. **apply 하지 않음.** 근거는 전부 세션 내 실측.

> v1→v2→v3 개정 이력: v1 의 A안 진단(정렬)·B안 전제(quality 빈칸)·C안 근거(96초 3회)가 **전부 틀렸고**, v3 에서 D안의 **방향까지 뒤집혔다**(가이드를 지울 게 아니라 선언을 되살려야 한다).

## 1. 확정 근거 (실측)

### 1-1. 원장 400건
실패 7건. source: usage 362 · test 38. **test 3건 제외 + 의도적 탐침(ZZZZNOTREAL9) 제외 → 진짜 에이전트 마찰 3건**(table:each 1 · engines:web 2).
어제 실물 마찰 5건(네이버×2·DDG·transcript>>brief·26,726자 절단)은 원장 기록 **0건** — success=true 였거나 파이프 중간 step.

### 1-2. `checks` 드리프트 — 방향이 반대였다 ★
- `tools/live_check.py:248` : `checks = tool_input.get("checks") or ["status","lighthouse","screenshot"]` → :257/:260/:263 에서 분기. **구현은 완전히 지원한다.**
- `data/guides/web_builder.md` 6곳이 가르친다(47·81·125·139·142·432행, `### checks 옵션` 절 포함).
- `ibl_actions.yaml` 의 params 블록: `/actions/web` = `{'url': 'string'}` 뿐. **`checks` 선언만 없다.**
- `handler.py:74 _h_site_live_check(ti, ctx)` 는 `ti` 통째를 넘긴다 → 거절은 핸들러가 아니라 **파라미터 어휘 검증층**에서 났다.
→ **가이드가 헛것을 가르친 게 아니라 선언이 구현보다 좁다.** v2 의 처방(가이드에서 checks 삭제)은 **살아있는 기능을 문서에서 지우는 손해**였다.

### 1-3. 감사 관문이 이 구멍에 눈감는 것을 자인한다
`scripts/build_ibl_nodes.py:268` 주석: *"진실 소스는 tool.json input_schema 인데 **거기 없는 자리는 관문이 원리적으로 눈감고**"*. `--check` 는 op **이름**은 삼각 검증하지만 **op 하위 param 키**는 대조하지 않는다. `checks` 가 살아남은 경로가 이것이다.

### 1-4. forage body 축 — 진단 확정 + 부작용 정량화
- id 1056 `네이버 웹문서 검색(…)` body=**web**. forage_map 455건 분포: `code:indiebizOS` 166 · `web` 115 · `mac` 78 · …
- 명시 회상 `pc-manager/handler.py:179` : `body = tool_input.get("body") or _detect_body()` → **"mac" 78건**.
- 자동 주입 `cognitive_recall.py:281,287` : `hw = detect_body()...`(게이트용) + `recall_xml(body=None, …)` → **455건 전 공간**. **주입 경로는 이미 올바른 두 축 분리를 하고 있다.**
- 설계 정본 `FORAGER_MULTIBODY_DESIGN.md` §1: *"현재 코드는 `body = detect_body().profile`(="mac")를 `forage_map.body`에 넣어 두 개념을 섞는다"* + 결정표 6 *"두 축 분리 … conflate 해소"*. → **A 는 새 제안이 아니라 미적용 결정.**
- **부작용 정량화(신규 실측)** — 전 공간으로 열었을 때 상위 20 안의 mac 생존:

| 질의 | mac 매칭 | 전 공간 매칭 | 상위20 중 mac 생존 |
|---|---|---|---|
| 검색 | 8 | 41 | **4** (50% 유실) |
| 파일 | 31 | 69 | **3** (90% 유실) |
| 기억 | 1 | 5 | 1 (유지) |

→ **한 줄 수정만으로는 회귀다.** limit 상향 또는 body별 쿼터가 **필수 동반**.

## 2. 꼭 필요한 변경 4건 (확정)

| # | 변경 | 층 | 파일·지점 | 위험 | 선행조건 |
|---|---|---|---|---|---|
| **C1** | `checks: array` 선언 복원 + 재빌드 | data | `web-builder/ibl_actions.yaml` `/actions/web` params → `scripts/build_ibl_nodes.py` | **낮음** (선언을 구현에 맞춤) | 없음 |
| **C2** | 회상 body 축 교정 **+ 완화책 동반** | 패키지 핸들러 | `pc-manager/handler.py:179` → `body = tool_input.get("body")` **및** limit 20→40 또는 body 쿼터 | **중** (§1-4 표) | 없음 (단 완화책 없이 금지) |
| **C3** | 미선언 param 감사 | scripts | `build_ibl_nodes.py --check` 에 *구현이 읽는 키(`tool_input.get("X")`) ↔ 선언 params* 대조 추가 | 낮음 | C1 (첫 사례=픽스처) |
| **C4** | `barren` 표지 | **RED** | `backend/ibl/ibl_honesty.py` 에 **별도** 키 (quality 칸 재사용 불가 — `agent_pipeline.py:51` 이 criteria 재시도 표지로 이미 점유) | 중 (오탐) | C3 |

**보류 — C5 턴 내 실패 지문 캐시**: 유일한 usage 사례(engines:web 2회/7초)가 C1 로 원인 제거된다. 만들 근거 소멸. C1 적용 후에도 반복이 남으면 재개.

## 3. 최종 실행 순서

```
C1 ──▶ C3 ──▶ C4
(선언 복원)  (감사)   (barren, RED)

C2 ──(독립, 완화책 동반 필수)──▶ 적용 후 회상 품질 대조
```

**순서 근거**
1. **C1 첫째** — 위험 최저(선언을 구현에 맞추는 것), 선행조건 없음, 원장 실패 2건을 즉시 제거하고 죽어 있던 기능(status/lighthouse/screenshot 선택)을 되살린다. 그리고 C3 의 회귀 테스트 픽스처가 된다.
2. **C2 는 C1 과 독립**이라 병렬 가능하나, 위험이 중간이고 완화책 설계가 필요하므로 무위험 건 뒤에 둔다. **완화책 없이 단독 적용 금지**(§1-4 표가 회귀를 보여준다).
3. **C3 은 C1 뒤** — C1 이 "미선언 키가 런타임까지 살아남은" 첫 확증 사례라, 감사가 그 사례를 재현 못 하면 감사가 틀린 것이다.
4. **C4 마지막** — 유일한 RED 변경이고, 새 봉투 키를 만드는 일이라 C3(선언 감사)가 서 있어야 같은 구멍을 다시 파지 않는다.

## 4. 기존 기제 대조 (유효)

| 기존 | 위치 | 판정 |
|---|---|---|
| 서킷브레이커 last_error | `system_tools_ibl.py:398·405·408·593` | 중복 아님 — 4연속·도구 단위 |
| goal 연속실패 | `conversation_db.py:1086` · `ibl_exec_goal.py:233` | 라운드 간, 턴 내 아님 |
| `[on_error:]`/`??`/skipped_steps | `backend/ibl/` 11파일 99매칭 | 상보 — '실패한 것' 신고. C4 는 '성공했는데 빈 것' |
| criteria 품질계약 | `agent_pipeline.py:51` · `vision_read.py` | **C4 와 칸 충돌** — 별도 키로 분리해야 함 |
| `validate_declared_params` | `iblbuild_params_check` | **선언된** param 만 검증. C3 는 **미선언·사용중** 키를 잡는 반대 방향 |
| forage dead_branch | `forage_memory.py` · `forage_consolidation.py` | C2 가 고치는 대상 |

## 5. 반론·한계
- **C2 반론**: body 파티션이 의도적 격리(자아별 사적 기억)라면 전 공간 개방이 그 원칙을 침해할 수 있다. 다만 `cognitive_recall.py:287` 이 이미 `body=None` 으로 부르므로 **주입 경로는 이미 개방돼 있고**, 명시 회상만 닫혀 있다 — 격리 원칙이라면 주입 쪽이 먼저 위반이다. 이 비대칭이 의도라는 근거는 문서에서 찾지 못했다.
- **C4 반론**: barren 판정(어휘 겹침 0)은 동의어·번역 검색에서 오탐한다. 결정론 규칙으로 시작해 오탐률을 재기 전에는 차단·재시도에 쓰지 말고 **표지로만** 둘 것.
- 표본 한계: 진짜 에이전트 마찰 3건. 400건은 최근 며칠치.
- **미확인**: `action_removal.md` 도 `checks:` 문자열을 포함한다(액션 제거 가이드의 예시인지 실제 드리프트인지 확인 안 함). C3 가 자동으로 판정할 것.
- **미확인**: dead_branch 재강화 9.4%(3/32) 의 절대 기준선 없음 — convention 21.7% 와의 상대 비교일 뿐.

## 6. 이번 턴 미실행
`ibl_actions.yaml`·`pc-manager/handler.py`·`build_ibl_nodes.py`·`ibl_honesty.py`·`live_check.py`·`FORAGER_MULTIBODY_DESIGN.md` **전부 읽기만**. 재빌드 안 함. `[self:patch]` 미호출. 쓴 파일은 이 설계문 1개.

---

## 7. 집행 기록 (2026-08-29, Claude Code 세션)

C1·C2·C3 집행 완료, C4 보류 유지, C5 기각 유지. 커밋 = git log 참조.

- **C3-0 (설계문에 없던 선행 발견)**: 기존 param 선언 완전성 관문(B35-3 2조각)이
  2026-08-24 모듈 분리 때 `import json` 누락 → `except Exception` 이 NameError 를
  삼켜 **통째로 침묵 no-op** 이었다. import 복원 + except 협소화(OSError/ValueError).
  프로브(가짜 미선언 키)로 소생 실증, 대조군 통과.
- **C1**: `web-builder/ibl_actions.yaml` `/actions/web` params 에 `checks: array` 선언
  복원 + 재빌드. 라이브 종단 실증: `[engines:web]{op:"check", url:…, checks:["status"]}`
  → 관문 통과 + status 만 실행(필터링 동작 증명).
- **C3**: `validate_impl_reads` 신설(`iblbuild_params_check.py`) — 앵커를 코퍼스가
  아닌 **구현 자신**(tool_input/ti AST 읽기)에 둔다. 2급 구조: 컨테이너-기대 미선언
  =즉시 빌드 실패(checks 부류·현재 0, 함수층 배관 6건은 IMPL_READ_ALLOW 사유 등재) /
  스칼라 미선언=IMPL_READ_BASELINE 동결 대장 151건(신규만 실패, 갚으면 지움·목표 0).
  음성 대조: checks 선언 제거 시 정확히 그 죽음이 빌드 실패로 재현됨.
- **C2**: 완화책은 limit 상향이 아니라 **몸별 공정 인터리브**(`forage_memory._fair_by_body`,
  body=None 시 map·territory 라운드로빈)로 — 근본 자리가 핸들러가 아니라 채움 순서라서,
  이미 body=None 인 주입 경로의 mac 기아까지 함께 고쳐진다. 핸들러 기본 = 전 공간
  (명시 body 는 여전히 좁힘, note 는 현재 몸 유지). 실측: '파일' 상위20 이
  code:indiebizOS 독점 → 몸 9개 공존(mac 3→4, '검색' mac 4→6). 어휘 설명(166행)은
  이미 "생략 시 전 공간"을 약속하고 있었으므로 이는 코드를 계약에 맞춘 수리다
  (263행 "현재 몸" 모순 문구도 정정).
- **부수 관찰**: forage_map 의 body 명명 드리프트 — `code:indiebizOS` ·
  `code:IndieBiz OS` · `code:IndieBizOS` 세 표기가 공존한다. 데이터 위생 건으로 별도.

---

## 8. 2차 집행 기록 (2026-08-29 friction 후속 보고 → 수리 3건)

- **빈 에러(신규 발견)**: 스윕 결과 `{"success": False, "message": …}` 모양이 **89자리**
  — 위반이 아니라 관례였다. 89개 리터럴 대신 읽는 쪽을 고침: `err_reason_of`
  (error→message→중첩 results/final_result 회수, workflow_verdict 단일 소스) 신설,
  파이프 Step 에러 조립·병렬 가지 실패 사유 추출 두 곳에 배선. 종전 병렬 가지 쪽은
  error 부재 시 `None[:300]` TypeError 잠복 결함도 함께 소거. 라이브 실증:
  KMS3VwGh3HY(힌디어만) → 최상위 error 에 전체 사유 실림.
- **병렬 봉투 절단(#2)**: "results[]는 원형" 규약 개정(사용자 판정) — 가지 원형이
  `ENVELOPE_KEEP_MAX`(16,000 = providers 절단과 동율)를 넘으면 **표시 사본**을 스필
  참조+preview 로 교체(`branches_spilled` 신고). 파이프 통화(중간 step)·$바인딩은 원형
  유지. 실증: 자막 2가지 & 봉투 71,000자→3,628자, 두 가지 모두 ref 로 회수 가능.
  `& >> take` 중간 단계는 원형 그대로(무회귀).
- **transcript 통화(#1)**: 짧은 경로 `items`(=segments) 추가, 긴 경로(>10,000자)는
  세그먼트를 스필 참조 봉투(`items:[]+ref+_spilled`)로 — 소비자(_get_items·each·
  $items)가 resolve_ref 로 투명하게 읽는다. 실증: `transcript >> [table:take]{n:3}`
  세그먼트 3개 수신(이틀 연속 마찰 소거). 동반 가드: `_is_empty_result` 가 스필 봉투의
  `items:[]` 를 빈손으로 오판해 `??` 오발하던 자리 봉인.
- 부수: err_reason_of 신설로 workflow_engine 1,528줄 → 판정·사유 3형제를
  `workflow_verdict.py` 로 분리(재수출로 호출자 유지, LAYERS 등재), 1,405줄.
- **미검증 잔여**: transcript 긴 경로(>10,000자 실영상)의 스필 ref 라이브 종단은 짧은
  영상뿐이라 미실측(코드 경로는 병렬 가지 스필과 동일 관용구). 다음 긴 영상 실사용이 판정.

## 9. 3차 집행 기록 (2026-08-29 검증 실행 보고 ⑤~⑨ → 수리 3건)

- **⑤ rows_in 늑대소년**: HONESTY_COUNT_KEYS 에서 제명. 전수 스윕 근거 — "받았으나 못
  씀" 의미 발신자는 전부 success:False 경로(이미 오류 신고됨), 성공 경로의 rows_in>0 은
  ai-ops 의 정보성 계수뿐 → 표지 승격 맥락(성공 통화·생존 가지)에서는 원리적으로 오탐만
  가능했다. 진짜 표지(rows_dropped·error_count·truncated 등) 생존 단위검증.
- **⑧ 스필 요약 count:0**: summarize_result 가 스필 봉투(items:[]+ref)를 인지 —
  ref.count(283)·spilled·spill_path 를 요약에 싣는다. 진짜 빈손(items:[] 무ref)은 0 유지.
- **⑦ crawl 문단 분해**: 두 경로 모두 수리. BS4 = 블록 요소(잎) 단위 추출(p/h/li/
  blockquote/pre/td…, 중첩은 잎만) + 블록 없는 페이지는 빈 줄 보존 폴백. playwright =
  빈 줄 보존(`if ln.strip()` 필터가 문단 경계를 버리던 자리). 라이브 실증: 위키 문서
  crawl >> take{n:6} → heading+문단 5행(종전 통짜 2행). playwright 경로는 동종 수리로
  코드 검증만(JS 필요 사이트 실사용이 판정).
- **⑥ each keep 안내문**: 뿌리 확인(ibl_exec_each.py:509, keep 지정 여부 무관 부착)
  — 동시 세션 미커밋 파일이라 보류. 그 작업 커밋 후 수리.
- **⑨ recover 진행률**: 엔진→티켓 진행 상태 쓰기 신설이 필요한 설계 건 — 미착수.
- 부산물: 2차의 "transcript 긴 경로 스필 ref 미실측" 잔여는 이번 검증 실행(283 세그먼트
  스필→투명 해소)으로 **실전 폐쇄**.

## 10. 4차 집행 기록 (2026-08-29 ⑨ recover 진행률)

설계 = **엔진→티켓 진행 쓰기**: ① thread_context 에 `surface_ticket` 칸 신설(표면이
싣고 finally 복원 — 기존 set/restore 규율 그대로, snapshot 통째 승계로 워커 전파 자동).
② 엔진 execute_pipeline 최외곽이 **claim-by-clear**(티켓을 집으며 스레드에서 비움 —
each 하위·블록·중첩·병렬 가지가 겹쳐 쓰지 못함, 값 소유권=진행 신고권)로 소유하고
step 경계마다 `ticket_progress`(best-effort, 실패 침묵) 기록. ③ `ticket_progress` 는
running 기록에만 덧쓰고 **done 을 절대 덮지 않는다**(결말 우선). ④ recover 의 running
응답에 progress(step/of/action/updated_at)+사람이 읽는 note 동봉 — 헛폴링 소거.
라이브 종단: 6-step 문장 실행 중 `running step 1/6 [sense:crawl]` → 완주 후 봉투 회수
(6/6). 단위: done 뒤 progress 덮기 거부·결말 보존 확인.

## 11. ⑥ each keep 안내문 (2026-08-29 마감)

keep 지정 여부로 rows_replaced 안내를 가른다 — keep 을 준 호출엔 "필드 [...] 는 keep 으로
각 행에 보존돼 있습니다", 안 준 호출만 종전 처방("keep 을 쓰세요"). 직접 호출 실측 양갈래
확인(보존 여부 실제 값과 안내문 일치). 동시 세션의 미커밋 훅(같은 파일 @@383, $변수 경계
힌트)과 겹치지 않아, 인덱스에 HEAD+이 훅만 부분 스테이징해 커밋 — 그 세션 작업은
워킹트리에 그대로 남는다. 이로써 08-29 검증 보고 9건 전부 종결.

## 12. ⑫ 응답 출력 절단 (2026-08-29, ep2307)

**진단** — ep2307 실측: 1차 최종 10,851자·재실행 11,309자, 서로 다른 두 세대가 같은
~11K자에서 문장 중간 절단(§2③ 표·§2④ 인용) = 턴 출력 토큰 상한(stop_reason=
max_tokens)이 유력. 하네스가 assistant 이벤트의 stop_reason 을 **버리고 있어** 절단이
침묵했고, GoalEval 은 절단을 모른 채 재실행→전체 재작성→같은 상한 재절단 루프 끝에
"짧게 완결된" 3,403자를 ACHIEVED 로 배달(풍부한 본문 유실).

**수리** — 프로바이더(claude_code)가 마지막 턴 stop_reason 을 포착, max_tokens 면
final 에 정직 표지(⚠ 절단 고지 + `truncated_output: true`) 와 **처방**("전체 재작성
대신 잘린 지점 이후 미완 부분만 이어쓰기")을 싣는다 — 처방을 표지에 싣는 이유는
재작성이 같은 상한에서 또 잘리기 때문(ep2307 이 그 실측). 표지는 사용자·GoalEval
평가 입력·대화 이력에 자동 도달(별도 배선 0). 단위 3경로 검증(절단=표지, 정상=무표지,
마지막 턴 정본). 시스템 AI 의 자가 처방("미완 섹션 분리 출력")과 합치 — 그 처방이
필요한 순간(절단 직후)에 읽히는 자리로 통로화한 것. 실전 max_tokens 재현은 미실측
(대형 생성 필요) — 다음 장문 보고서 실행이 판정.
