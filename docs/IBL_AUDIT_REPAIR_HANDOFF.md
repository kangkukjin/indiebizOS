# IBL 전면 감사·보수 핸드오프 (2026-08-05) — 잔여 부채 9항

> 정본. 다음 세션은 이 문서만으로 이어받는다. 메모리 `ibl-audit-repair-2026-08` 이 여기를 가리킨다.

## 진행 현황 (2026-08-05 2차 세션 — 전부 push)

| 항 | 상태 | 커밋 |
|---|---|---|
| ⑥ 복붙 정리 | ✅ 완료 | `882c38b` — common/http_fetch·geocode·pkg_utils 신설, curl_cffi 5벌·Nominatim 3벌 수렴, 단순 load_module 7곳 위임 (특수 변형 유지 — cache·체인프리로드는 의도된 차이) |
| ⑧ pytest 도입 | ✅ 완료 | `731c5f1` — pytest.ini + 고아 5 편입(nip44 최우선) + seam-guards CI 잡. `-m "not local"` 28 passed |
| ① 스텁 디스패처 | ✅ 완료 | `7ecf9a8` — 15개 전환(4 병렬 에이전트, 행동 변화 0) + 가드 `_stub_ops`(값 None=빌드 차단) + self-test. 부수: web-collector 죽은 records 블록 삭제 `05d5e0b` |
| ② 에러 관례 | ✅ 완료 | `0dd1050`(1단계) + `38df771`(완결, 2026-08-05 3차) — health-record 20곳(returns:items 위반 최악 부류) dict 전환 · Unknown tool 폴백 12곳 소탕 · {success:False,message}→error 80곳 · error-only→+success:False 156곳(렌더러 양쪽 d.error‖d.message 폴백이라 표시 무손상 실측) · `scripts/check_string_returns.py` 가드(execute+디스패처 op 함수 AST, 중첩 def 헬퍼 제외=오탐 0, system_essentials 텍스트 계약 31건만 BASELINE 래칫) + pre-commit + seam-guards CI |
| ③ per-op returns | ✅ 완료 | (2026-08-05 4차) `ops.returns`/`ops.side_effect` 형제 맵 신설 + `backend/ibl_ops.py`(해소 단일 소스) + 43액션 선언 마이그레이션. **성과: 자동 건강검진 read-only 게이트에 걸려 실행조차 안 되던 fixture 32개 → 2개**(§1B GREEN 33→63, RED 0). 상세는 아래 §1-③ |
| ⑤ 행위 검증 층 | ✅ 완료 | (2026-08-05 5차) `ops.fixture`/`ops.exempt` 형제 맵 + 읽기-op 전수 완전성 가드 + `#op` 키 파생·소비. **읽기 op 커버리지 37/133 → 122/133**(fixture 53 + 면제 32 신규), §1B **GREEN 63→89 / RED 0**. 상세는 아래 §1-⑤ |
| ④ 렌더러 단일화 | ✅ 완료(로직) | (2026-08-05 6차) `backend/static/app_render_core.js` 신설 — 두 렌더러가 글자 그대로 번역해 갖고 있던 **순수 로직 26개**를 단일 소스로. 마크업 층은 의도적으로 두 벌 유지(아래 §1-④). 가드 `check_render_core.py` + 실행 회귀 `test_render_core.js`/`backend/test_render_core.py` |
| ⑦⑨ | ⬜ 미착수 | ①에서 안 특이점: 에러 우선순위 미세 역전 3건(phone_listen 무효 op 침묵 실행→정직 거부 등, C 에이전트 보고) |

## 0. 배경 — 무엇을 했고 무엇이 남았나

2026-08-05 다섯 감사(언어 코어 / 어휘 사전 / 검증계 / 핸들러 통화 규율 / 백엔드 구조)로
IBL·indiebizOS를 전면 반성한 뒤, **긴급·고가치 결함은 당일 보수 완료**:

| 커밋 | 내용 |
|---|---|
| `f294f94` | 가드 2종: 모듈 그림자 차단(`scripts/check_module_shadowing.py`) + 1500줄 래칫(`scripts/check_file_size.py`) |
| `e0c9e8a` | memory `top_k` 침묵 무시 수리(aliases 정본화) + realty 소스별 `무시된_파라미터` 경고 |
| `0af6996` | 파라미터·op 정본 가드(`scripts/check_param_canon.py`, 기존 위반 32건 BASELINE 동결) |
| `a11df6d` | 건강검진 §1A returncode 판정(10/17 가드 실패해도 GREEN이던 버그) + §1B read-only 게이트 |
| `96ddb47` | ibl_access 죽은 무효화 중복·유령 노드 매핑 정리 |
| `46423ee` | 파서 침묵 실패 D1~D6 수리 + `backend/test_ibl_silent_failures.py` 상설 |
| `711fca0` | 파이프 이음매 통화 파생(`workflow_engine._to_prev_currency`) + 죽은 코드 -266줄 |

**감사의 핵심 진단** (부채 9항의 공통 뿌리):
- 기존 가드 전부가 "선언 대 선언" 비교 — **행위 검증이 없다**. effect 57액션(어휘의 35%)은
  어떤 자동 검증도 실행하지 않고, op 표면 329개 중 실행 검증은 ~12%(fixture 40개).
- 중앙 설계층(파서 경계·returns enum·프롬프트 경제)은 우수, 분산 성장층(41 패키지의
  파라미터·op·에러 관례)은 규율 붕괴.

## 1. 잔여 부채 9항 (우선순위순 아님 — 규모·성격 병기)

### ① 장식 스텁 `_OP_DISPATCHERS` 15개 → 진짜 디스패처로 (중규모·기계적)
41개 핸들러 중 **진짜 패턴 8개**(business, family-news, music-player, bulletin,
community-portal, public-files, system_essentials, web-builder, youtube),
**장식 스텁 15개**(값 전부 None, 분기는 if/elif 체인 그대로: guest-helper, memory, radio,
real-estate, android, blog, cctv, context7, culture, health-record, investment,
lecture_workspace, pc-manager, study, web-collector), STRING 변형 2개(browser-action,
computer-use), 부재 16개.
- 왜 문제: 빌드 가드(`iblbuild_validators.py` 1g)는 **키만** AST 비교 — 스텁+체인에서 분기
  하나가 사라져도 통과. 스텁은 부재보다 나쁘다(준수처럼 보임).
- 접근: 스텁 15개를 함수 참조 테이블로 전환(radio/memory 주석 "값은 None — refactor 없음"이
  전환 지점 표식). 전환 후 가드에 "값이 None인 테이블 금지" 조항 추가하면 재발 봉쇄.
- 함정: real-estate는 진짜 2축(op + source) — source 축은 가드 밖이니 전환 시 문서화.

### ② 에러 관례 5종 → 단일 관례 (✅ 완료 — 아래는 이력)
공존 중: 예외 전파 / `{success:False, error}` / `{success:False, message}` /
`{error}`(success 없음: location-services 전역, memory) / **맨 문자열**(shopping-assistant
:251·:271, business :1061, web launch_sites, location-services :974).
- `returns: items` 액션이 맨 한국어 문자열을 반환하는 경로들이 최악(통화 계약의 조용한 위반).
- 정본 후보는 이미 있다: `backend/common/response_formatter.py:44` `error_response()` —
  location-services는 **import까지 해놓고 안 쓴다**.
- 접근: ①맨 문자열 반환부터 소탕(파이프를 깨는 유일 부류 — `_parse_prev`가 JSON은 살린다)
  ②`{success:False, error}` 로 수렴 ③가드: 핸들러 return 문자열 리터럴 AST 검사(맨 문자열
  반환 금지)를 build --check에 추가.

### ③ per-op returns 축 (✅ 완료 — 아래는 이력과 이월 사항)

**설계는 핸드오프 스케치와 다르게 갔다.** `ops.values` 를 `{op: {desc, returns}}` 중첩형으로
바꾸는 대신 **형제 맵**(`ops.returns` / `ops.side_effect`)을 신설했다. 이유: `values` 는 8곳이
`{op: str}` 로 읽고 그 중 하나가 *모든 에이전트 턴의 프롬프트 카탈로그*다 — 모양을 바꾸면
놓친 소비자 하나가 조용히 `[object Object]` 를 뿜는다. 형제 맵은 순수 가산이라 기존 독자를
못 깨고, 키 드리프트는 빌드 가드가 막는다. 카탈로그 바이트 수 불변(40,426자) 확인.

- 해소 규칙 = **조이는 건 자동, 푸는 건 명시**(`backend/ibl_ops.py` 단일 소스, `ibl.md` "op 축" 절).
  액션의 보수적 `side_effect: true` 는 **끈적하다** — op 가 직접 `false` 라고 말해야 풀린다.
- 소비자 3: 조종실 dry-run(`api_ibl._safety` 가 op 로 판정) · 건강검진 read-only 게이트와
  통화 판정(`ibl_health_check._first_op`/`_is_safe`/`_op_returns_of`) · `ibl_safety.build_op_safety_map`.
- 부수 수확: **fixture 가 부르는 op 의 실존을 강제**하는 가드 신설 → `[self:blog]{op:"list"}` 가
  선언에 없는 op 였고 핸들러 폴백(`.get(op) or _op_posts`)이 삼켜 '통과'해 온 것이 드러났다.
- ★**분류는 코드를 열어서** 했다. 이름만 보고 풀었으면 틀렸을 것 5건 실측:
  `sense:world` snapshot(수집+DB 적재) · `sense:collect` query(`action: delete` 가지를 품음 —
  **op 아래 또 다른 축**) · `self:blog` latest(vault .md 지연 물질화) · `limbs:browser` screenshot
  (PNG 파일 생성) · `limbs:guestpc` screen(허브가 outputs/limb_screens/ 에 적재).
- 이월: ①효과 op 의 **통화**는 선언했지만 effect 액션 안 읽기 op 의 통화(items/scalar)는
  **측정 전이라 미선언**(안전만 선언) — ⑤ 에서 fixture 로 재면서 붙일 것. ②`sense:collect` 처럼
  op 아래 또 축이 있는 액션은 op 단위로 안전을 말할 수 없다(그 축의 어휘화가 남은 부채).

<details><summary>원래 진단 (이력)</summary>
`returns`는 액션 단위인데 op가 통화를 가른다 — business_item_op은 list(items)와
delete(effect)를 한 이름에 담을 수 없어, 전 패키지가 둘 중 하나를 택했다:
**정직**(music-player: 모든 op가 `items([])` 래핑) vs **거짓말**(business/guest-helper/memory:
items 선언 후 대다수 op는 effect 반환 — `guest-helper/ibl_actions.yaml:49-52`에 자백 주석).
- 접근: `ops.values`를 `{op: {desc, returns}}` 확장형 허용(기존 문자열형 병행) →
  빌드가 fixture 요구·안전 분류·건강검진 통화 판정을 op 단위로 내림. 이건 **언어 개정**이라
  `ibl.md` 갱신 + `iblbuild_*` 3파일 + `ibl_safety`/`ibl_health_check` 소비처 동반.
- 선행 조건: ①(스텁 전환)을 먼저 하면 op별 반환 지점이 함수 단위로 잡혀 이행이 쉬워진다.
</details>

### ④ 이중 렌더러 단일화 (✅ 로직 완료 — 아래는 무엇을 합쳤고 무엇을 남겼나)

**핵심 판단: 합칠 수 있는 것은 로직이고, 마크업이 아니다.** 핸드오프 스케치는 "공유 .js
모듈 하나 → 패리티 가드 은퇴"였지만, 실제로 두 렌더러를 열어 보니 **마크업은 합치면 손해**다 —
데스크탑은 React(제어 입력·ref·훅으로 form/editable_list/calendar/map 이 상태를 들고 있다)이고
원격은 HTML 문자열+이벤트 위임이다. 데스크탑을 innerHTML 로 내리는 것은 통합이 아니라 강등이다.
반면 *로직*(무엇을 그릴지 정하는 층)은 두 벌일 이유가 0이었고, 그것이 커밋 세금의 실체였다.

- **정본**: `backend/static/app_render_core.js` — DOM·프레임워크 의존 0, 표면마다 다른 것
  (HTML 이스케이프·URL 절대화·색 어휘)은 **인자로 받는다**. 옮긴 것 26개:
  `jget` `applyFilter` `tplWith` `buildAction` `rowAction` `viewList` `emptyText` `trendUp`
  `statusGlyph` `unwrapFinalResult` `groupPartition` `fmtSpark` `sparkModel` `calendarModel`
  `calShift` `pad2` `composeChannelOptions` `isSlowNet` `preloadOf` `mediaModel`
  `hasMasterDetail` `dynFilterCats` `applyDynFilter` `parseImagePaths` `RECURRENCE_OPTS`
  `dateInputType`.
- **두 소비자**: 데스크탑=Vite import(`vite.config` `server.fs.allow:['..']` + tsconfig `allowJs`)
  / 원격·폰=`backend/launcher_render_core.py` 가 읽어 **맨 끝 ESM export 블록만 떼고** 런처
  `<script>` 에 인라인(함수 선언 호이스팅이라 조립 순서 무관). 폰 zip 은 gradle 에 별도 `from`
  (엔진 모듈 glob 이 `*.py` 만 보므로 — 빠지면 폰 앱 탭이 통째로 죽는다. 부재 시 빌드 실패로 승격).
- **가드**: `scripts/check_render_core.py`(①export 블록이 마지막 하나 ②소비자가 코어 이름
  재정의 금지 ③두 표면 조립이 코어를 실제로 싣는지) + pre-commit + CI `render-core` 잡.
  **선언이 아니라 실행으로 재는 그물**도 같이: `scripts/test_render_core.js`(조립된 런처
  스크립트를 최소 DOM 셰임 위에서 돌려 프리미티브 32종 렌더 검증) ← `backend/test_render_core.py`
  가 pytest 로 구동. 이건 감사 ⑤가 IBL 액션에 세운 규율의 렌더러판이다.
- **패리티 가드는 은퇴 안 함**(마크업 층이 여전히 둘이므로 `p.type` 케이스 누락은 계속 실재하는
  사고). 다만 그 가드의 **조용한 skip**(추출률 70% 미만이면 무언 통과, `iblbuild_appview.py:128-131`)은
  여전히 남은 결함 — 실행 회귀가 생겼으니 이제 hard-fail 로 바꿔도 안전하다(남은 일).
- **합치면서 드러난 것**(사본이 하나가 되자 차이가 곧 버그로 보였다):
  · 원격 `group` 헤더 **이중 이스케이프**(`tpl` 이 esc 한 키를 다시 `esc()`) → `A&amp;amp;B`.
  · 원격 kv/kv_list **값 이중 이스케이프**(`tpl`+`kvVal` 둘 다 esc) → `<` 가 `&lt;` 로 보이고
    `&` 낀 URL 의 href 가 망가짐. 값만 `tplWith`(원문)로 넘겨 수리.
  · 원격 `fireButton`/`fireTop` 의 `final_result` 펼치기가 `ibl()` 본판과 달라 비-JSON 문자열을
    삼켰다 → `unwrapFinalResult` 하나로 수렴.
  · 달력 월 산식이 두 벌이라 **그 달에 없는 날**(monthly 반복 31일이 2월에) 처리가 갈렸다.
- **남은 것**(로직 밖): 마크업 이중 구현 그 자체(의도) · 데스크탑 `Sparkline` 은 OVERRIDES(투자)에
  가려 제네릭 경로로는 도달 불가라 브라우저 실검증 못 함(코어 모델은 node 회귀가 덮음) ·
  TS 타입 유니언(`generic/manifest.ts` `AppViewPrim`)이 `APP_VIEW_TYPES` 의 4번째 독립 선언인 것.

### ⑤ 행위 검증 층 (✅ 완료 — 아래는 이력과 이월 사항)

**한 일**: `ops` 블록에 형제 맵 `fixture`/`exempt` 신설(③의 `returns`/`side_effect` 와 동형,
순수 가산). 파생물 `ibl_fixtures.json` 의 op 항목 키는 `node:action#op`. 빌드가 **읽기 op
전수 완전성**을 강제하고(`_check_op_fixture_coverage`), 쓰기 op 에 fixture 를 달면 거부한다
(무인 루프가 매일 부작용을 실행하게 되므로). 읽기 op 커버리지 **37/133 → 122/133**
(fixture 53 + 사유 있는 면제 32 신규 저술), §1B **GREEN 63→89 · RED 0**.

- ★**상속된 모순도 막게 넓혔다**: 옛 검사는 `ops.returns[op] == effect` 를 *직접 선언*한
  경우만 봤다. `side_effect: false` 인데 통화는 액션의 `returns: effect` 를 **상속**하는 op
  21개(`limbs:browser`·`limbs:guestpc`·`limbs:screen`·`limbs:music`…)는 "읽기라고 선언해
  놓고 통화는 미선언"인 상태로 행위 검증에서 조용히 빠져 있었다. 이제 자기 통화를 말해야 한다.
- ★**선언 전에 실행해 재는 규율이 결함을 냈다**(측정이 곧 산출물):
  ①`sense:performance` venue/genres/regions·`sense:book` recommended — `returns: items`
  액션인데 **통화를 안 달고** native 키(`data`/`genres`/`regions`)로만 뱉고 있었다
  (액션 fixture 가 `search` 하나만 돌던 탓에 몇 달간 아무도 안 봄). 핸들러 수리.
  ②`self:package#info` 는 통화가 없어 `ops.returns: scalar` 로 정직화.
  ③**싱글턴 로더 import 레이스**(아래 별항).
- ★**병렬 probe 가 잡은 진짜 동시성 결함**: `sys.modules[key]=module` 을 `exec_module`
  **앞**에 두는 주문이 4개 핸들러에 복붙돼 있어, 동시 호출자가 **반쯤 만들어진 모듈**을
  받았다(실측: `[sense:video]{op:"history"}` 가 `has no attribute 'history'` 로 죽고 같은
  순간 `feed` 는 성공). IBL 은 `&` 병렬이 1급이라 이론적 레이스가 아니다.
  → `common/pkg_utils.load_singleton`(잠금 + 완주 표식 + 실패 시 sys.modules 정리)로 수렴,
  youtube·radio·cctv·browser-action 전환. 회귀 테스트에 **음성 대조**(옛 주문이 8중 7 실패)
  동봉 — `backend/test_pkg_singleton_race.py`.
- 이월(⑤의 나머지 두 갈래, 미착수): ①`side_effect: true` op 용 **드라이런 fixture 규약**
  (임시 리소스 생성→검증→원상복구 — bulletin/portal 검증 스크립트가 선례). 쓰기 op 196개는
  여전히 실행 검증 0. ②파이프 골든 5개 오프라인 스텁화(지금은 라이브 외부 API라 flaky).
- 남은 YELLOW 3(`others:follow`·`others:portal`·`self:switch`)은 전부 "items 빈(데이터 없음)"
  — 사용자 데이터가 실제로 비어 있는 것이라 구조 결함 아님.

### ⑥ 복붙 정리 — curl_cffi 6벌·지오코더 3벌 (소규모·즉효)
그림자 버그(cctv 옛 common.py)는 치료됐고 가드도 섰으니, 이제 공유가 가능하다:
- curl_cffi 크롬위장 6벌: `web/tool_webcrawl.py:34` · `real-estate/tool_naver.py:41` ·
  `real-estate/tool_zigbang.py` · `location-services/tool_stay.py:22` ·
  `shopping-assistant/tool_danawa.py:34` · `tool_freelance.py:24` → `backend/common/http_fetch.py` 신설.
- Nominatim 지오코더 3벌(바이트 동일): `real-estate/handler.py:38` ·
  `real-estate/tool_zigbang.py:87` · `location-services/handler.py:726`.
- importlib 재로드 주문 45벌 → `common/pkg_utils.load_sibling()` 하나.
- 함정: 패키지는 backend를 sys.path로 import하므로 순환 없음. 단 **폰 몸**에서 backend
  common이 번들에 포함되는지(`build_body_bundle`) 확인 후 이동.

### ⑦ backend/ 디렉토리화 — 숨은 순환 86개 가시화 (중규모·기계적)
모듈 수준 순환 0은 착시 — intra-backend import의 70%(454/644)가 함수 안으로 밀려 있고
진짜 순환 86개(`agent_runner↔agent_communication`, `api_portal↔public_face` 등).
`ibl_routing.py`는 최상위 내부 import 0 / 함수 내 28.
- 접근: 로직 무변경 이동만으로 `core/ ibl/ agents/ routers/ launcher/` 디렉토리화 →
  순환이 import 오류로 드러남 → 그때 하나씩 푼다. 이동은 `ci_import_smoke` + 침묵실패
  테스트 + 이식성 CI가 안전망.
- 함정: `sys.path.insert` 훅 23곳, 폰 번들 경로 산식, Electron 스폰 경로가 평면 구조를
  가정 — 이동 전 `runtime_utils.get_base_path` 소비처 훑을 것.

### ⑧ 테스트 스위트 도입 (소규모 시작·복리)
pytest 부재. 고아 테스트 5개가 시작점: `backend/test_ibl_silent_failures.py`(46423ee 신설,
이미 회귀 가치 실증 — 죽은 코드 일소 검증에 사용됨) · `test_evaluator_trace.py` ·
`test_consciousness_json_relax.py` · `test_discover_contribution.py` ·
`test_nip44_vectors.py`(**암호 구현의 유일 검증**이 CI 밖 — 최우선 편입).
- 접근: `pytest.ini` + CI 잡 하나(seam-guards.yml에 스텝 추가) + 고아 5개 assert화.
  새 테스트 강요 없이 "있는 것부터 돌게"가 1단계.

### ⑨ BASELINE 파일 분할 — api_portal 최우선 (중규모)
`scripts/check_file_size.py` BASELINE 7건은 래칫 동결(더 못 자람) 상태. 분할 완료 시
**BASELINE에서 항목 삭제**(재진입 봉인)를 잊지 말 것.
- `backend/api_portal.py` 1903 최우선 — 16섹션에 **인증 시스템 통째**(로그인:1425,
  가입:1529, 비번재설정:1610)+파일서빙+방명록+PWA+오디오프록시 = 5모듈 분할.
- `data-ops/handler.py` 1711 — 통화 소비자 정본이라 둘째 우선.
- 나머지: api_nas 1515, media_producer 2건(핸드오프 doc ⑥⑨), youtube/tool_youtube 1570,
  frontend/electron/main.js 1990.

## 2. 순서 제안 (의존 관계)

```
⑥ 복붙 정리(즉효·독립) ──┐
① 스텁 디스패처 전환 ────┼→ ③ per-op returns (①이 선행이면 쉬움)
② 에러 관례 수렴 ────────┘
⑧ pytest 도입(독립·먼저 할수록 이득) → ⑤ 행위 검증 층 ✅ (⑧ 위에서)
⑦ 디렉토리화 (독립·큰 diff라 다른 작업과 겹치지 않게 단독 세션)
⑨ api_portal 분할 (독립)
④ 렌더러 단일화 ✅ (2026-08-05 6차 — 로직 단일화 + 실브라우저 종단)
```

**남은 것은 ⑦⑨ 둘뿐**이고 서로 독립이다. 아무 순서로나.

## 3. 하우스 규약 리마인더 (이 작업들에 적용)

- src yaml 수정 → `python3 scripts/build_ibl_nodes.py` → `--check` → 커밋. 핸들러만은
  `/packages/reload`, **패키지 tool_*.py는 reload 밖**(sys.modules 캐시 → 재시작/touch).
- 어휘 의미 변경 시 가이드·해마 용례·문서 7표면 동반(vocab_change_docs).
- 커밋은 main 직접, **pathspec으로**(`git commit -m "…" -- <경로들>`) — 동시 세션의
  공유 인덱스 함정(2026-08-05 실발생, 메모리 shared-git-index-concurrent-sessions).
- 새 가드를 만들면 self-test 동봉 + pre-commit 배선(기존 3종 신설 가드가 템플릿).
- 검증 없이 완료 선언 금지 — 이번 보수의 검증 스타일(인프로세스 스텁 케이스 + 침묵실패
  테스트 + build --check + import 스모크)을 기본으로.
