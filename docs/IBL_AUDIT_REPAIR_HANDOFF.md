# IBL 전면 감사·보수 핸드오프 (2026-08-05) — 잔여 부채 9항

> 정본. 다음 세션은 이 문서만으로 이어받는다. 메모리 `ibl-audit-repair-2026-08` 이 여기를 가리킨다.

## 진행 현황 (2026-08-05 2차 세션 — 전부 push)

| 항 | 상태 | 커밋 |
|---|---|---|
| ⑥ 복붙 정리 | ✅ 완료 | `882c38b` — common/http_fetch·geocode·pkg_utils 신설, curl_cffi 5벌·Nominatim 3벌 수렴, 단순 load_module 7곳 위임 (특수 변형 유지 — cache·체인프리로드는 의도된 차이) |
| ⑧ pytest 도입 | ✅ 완료 | `731c5f1` — pytest.ini + 고아 5 편입(nip44 최우선) + seam-guards CI 잡. `-m "not local"` 28 passed |
| ① 스텁 디스패처 | ✅ 완료 | `7ecf9a8` — 15개 전환(4 병렬 에이전트, 행동 변화 0) + 가드 `_stub_ops`(값 None=빌드 차단) + self-test. 부수: web-collector 죽은 records 블록 삭제 `05d5e0b` |
| ② 에러 관례 | ✅ 완료 | `0dd1050`(1단계) + `38df771`(완결, 2026-08-05 3차) — health-record 20곳(returns:items 위반 최악 부류) dict 전환 · Unknown tool 폴백 12곳 소탕 · {success:False,message}→error 80곳 · error-only→+success:False 156곳(렌더러 양쪽 d.error‖d.message 폴백이라 표시 무손상 실측) · `scripts/check_string_returns.py` 가드(execute+디스패처 op 함수 AST, 중첩 def 헬퍼 제외=오탐 0, system_essentials 텍스트 계약 31건만 BASELINE 래칫) + pre-commit + seam-guards CI |
| ③④⑤⑦⑨ | ⬜ 미착수 | ③은 ①② 선행조건 충족됨(op 함수 단위 반환 추적 + 에러 모양 단일). ①에서 안 특이점: 에러 우선순위 미세 역전 3건(phone_listen 무효 op 침묵 실행→정직 거부 등, C 에이전트 보고) |

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

### ③ per-op returns 축 (구조 개정·설계 필요)
`returns`는 액션 단위인데 op가 통화를 가른다 — business_item_op은 list(items)와
delete(effect)를 한 이름에 담을 수 없어, 전 패키지가 둘 중 하나를 택했다:
**정직**(music-player: 모든 op가 `items([])` 래핑) vs **거짓말**(business/guest-helper/memory:
items 선언 후 대다수 op는 effect 반환 — `guest-helper/ibl_actions.yaml:49-52`에 자백 주석).
- 접근: `ops.values`를 `{op: {desc, returns}}` 확장형 허용(기존 문자열형 병행) →
  빌드가 fixture 요구·안전 분류·건강검진 통화 판정을 op 단위로 내림. 이건 **언어 개정**이라
  `ibl.md` 갱신 + `iblbuild_*` 3파일 + `ibl_safety`/`ibl_health_check` 소비처 동반.
- 선행 조건: ①(스텁 전환)을 먼저 하면 op별 반환 지점이 함수 단위로 잡혀 이행이 쉬워진다.

### ④ 이중 렌더러 단일화 (대규모·최대 세금)
같은 15 프리미티브를 TS 2,025줄(`GenericInstrument.tsx`+generic/)과 파이썬 문자열 속 JS
~1,459줄(`launcher_web_render.py` 등)이 이중 구현. **데스크탑 렌더러 커밋의 85%(29/34)가
원격 렌더러 동시 수정**, 헬퍼 14개가 글자 그대로 번역돼 있음(jget/tpl/applyFilter/
buildAction/rowAction/…). 패리티 가드는 15개 문자열 존재만 보고, 추출률 70% 미만이면
**조용히 꺼진다**(`iblbuild_appview.py:128-131`).
- 해법 방향: 둘 다 JS를 실행하므로 **공유 .js 모듈 하나**(원격 셸에 서빙 + Vite import).
  패리티 가드는 불필요해져 은퇴.
- 함정: 원격판은 Python 문자열 안이라 `\\` 이스케이프 지뢰(remote-launcher-design-polish
  메모리) — 추출 자체가 이 부류를 근절한다. TS 타입 유니언(`generic/manifest.ts:60`)이
  4번째 독립 선언인 것도 함께 수렴.

### ⑤ 행위 검증 층 (검증계의 진짜 갭)
effect 57액션 실행 검증 0% · op 12%만 · desc 진실성은 주 1회 LLM 산문 대조뿐.
- 접근(값/노력 순): ①fixture에 op 지정 확대(read-safe op 위주로 40→100+)
  ②`side_effect: true` 액션용 **드라이런 fixture 규약** 신설(임시 리소스 생성→검증→원상복구
  패턴 — bulletin/portal 검증 스크립트들이 선례) ③파이프 골든 5개를 오프라인 스텁化
  (지금은 라이브 외부 API라 flaky).
- §1C-2 연산자 스위트(7케이스)가 모범 — 시도 로그·분기 수를 단언. 이 스타일로 확장.

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
⑧ pytest 도입(독립·먼저 할수록 이득) → ⑤ 행위 검증 층 (⑧ 위에서)
⑦ 디렉토리화 (독립·큰 diff라 다른 작업과 겹치지 않게 단독 세션)
⑨ api_portal 분할 (독립)
④ 렌더러 단일화 (최대 작업 — 단독 세션, 실브라우저 종단 검증 필수)
```

## 3. 하우스 규약 리마인더 (이 작업들에 적용)

- src yaml 수정 → `python3 scripts/build_ibl_nodes.py` → `--check` → 커밋. 핸들러만은
  `/packages/reload`, **패키지 tool_*.py는 reload 밖**(sys.modules 캐시 → 재시작/touch).
- 어휘 의미 변경 시 가이드·해마 용례·문서 7표면 동반(vocab_change_docs).
- 커밋은 main 직접, **pathspec으로**(`git commit -m "…" -- <경로들>`) — 동시 세션의
  공유 인덱스 함정(2026-08-05 실발생, 메모리 shared-git-index-concurrent-sessions).
- 새 가드를 만들면 self-test 동봉 + pre-commit 배선(기존 3종 신설 가드가 템플릿).
- 검증 없이 완료 선언 금지 — 이번 보수의 검증 스타일(인프로세스 스텁 케이스 + 침묵실패
  테스트 + build --check + import 스모크)을 기본으로.
