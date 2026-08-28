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
