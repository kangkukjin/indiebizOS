# 3층 이름 드리프트 전체 감사 — 2026-07-02

> 핸드오프 §5 후속(search_gnews 리네임에서 "다른 액션도 3층 이름 드리프트 있을 수 있음" 우려). 전 117 tool-보유 액션 대상.

## 3층 정의
1. **액션명** (層1) — `[node:action]`의 action. **에이전트/사용자·코퍼스 노출 어휘.**
2. **tool명** (層2) — 액션 def의 `tool:` = `context.tool_name` = tool.json name. **내부 디스패치 키.**
3. **함수명** (層3) — 핸들러/모듈의 impl 함수.

핵심 비대칭: **코퍼스(ibl_code)는 층1(액션명)만 쓴다.** `[engines:web]`이지 `web_op`(tool)가 아님. → **tool명 리네임은 코퍼스 무영향**(층1 리네임만 코퍼스 마이그레이션 필요 = search_gnews가 무거웠던 이유).

## 결론: 어휘는 건강함. 재발하는 버그-부류 드리프트 없음.

### 層1 (액션 어휘) — 깨끗
- 벤더/제품어가 든 액션 7개(`pew_research`·`search_ddg`·`search_naver`·`cloudflare_api`·`slide_shadcn`·`image_gemini`·`remotion`)는 전부 **벤더가 곧 구분 개념**인 정당한 커버리지(검색엔진 소스·명명된 데이터소스·특정 프레임워크) — `search_guardian`/`sense:paper source:nanet`과 같은 패턴. 옛 `search_news`식 *일반어 land-grab은 없음*.
- 유일 경계선=`image_gemini`(단일 이미지 제공자라 벤더명이 곧 액션명 — 제공자 교체 시 좀비어휘 위험). 판단 보류.

### 層1↔2 (액션→tool) — 105/117 상이하나 전부 의도된 관습
- **op-디스패처**(50): `X` → `X_op` (`slide`→`slide_op`). ops 보유.
- **동사확장**(37): `copy`→`copy_path`, `list`→`list_directory`, `grep`→`grep_files`, `kosis`→`kosis_lookup`. tool이 액션 어근 포함.
- **메커니즘 명명**(나머지): `see`→`phone_capture`, `here`→`phone_locate` (tool이 *구현 기전*을 노출 — 오히려 유용).
- → 드리프트 아님.

### 層2↔3 (tool→함수) — 일치 (search_gnews 부류 재발 없음)
스팟체크 전부 함수명 == tool명(± 밑줄 접두 관습):
- `search_guardian`↔`_search_guardian`, `search_books`↔`_search_books`, `phone_sync`↔`_phone_sync`, `kakao_navigation`↔`def kakao_navigation`, `critique_gemini_image`↔`def critique_gemini_image`, `kcisa_quick_search`↔branch, `radio_status`↔branch.
- **search_gnews의 tool≠함수(search_google_news) 같은 stale 3중 불일치는 발견되지 않음** → 그 수정은 *패턴이 아닌 이상치*를 닫은 것.

## 선택적 정리 후보 (내부 tool명 벤더 누수 — 층1은 깨끗한데 층2만 누수)
| 액션(깨끗) | 현 tool(누수) | 문제 | 제안 |
|---|---|---|---|
| `sense:exhibit` | `kcisa_quick_search` | 벤더(KCISA)+구현("quick_search") 누수 | `exhibit_search` 또는 `exhibit_lookup` |
| `sense:navigate_route` | `kakao_navigation` | 벤더(Kakao) 누수 — 제공자 교체 시 좀비어휘 | `route_directions` 또는 tool==action(`navigate_route`) |

- 비용: 각 3파일(액션 `tool:` + tool.json name + handler branch/함수) + `--check`. **코퍼스 무영향**(액션명 불변). 저비용·저위험.
- 가치: 좀비어휘 예방(벤더 교체 대비). 단 **내부명이라 에이전트 비노출** → 순수 위생.
- gemini 트리오(`critique_gemini_image` 등)는 **액션도 `image_gemini`라 벤더 임베드가 일관** → 여기서 제외(층1까지 손대는 별건).

## 권고
**대량 리네임 불필요.** 어휘 계층은 건강하다. 위 2개 내부 tool명만 원하면 위생 차원 정리(저비용). 감사의 핵심 소득 = *search_gnews는 이상치였고 패턴이 아니다*라는 확인.
