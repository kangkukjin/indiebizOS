# 능력 자기완결화 (Capability Self-Containment) — 장기 계획

> 상태: **Phase 0·1·2·3 완료**(2026-07-01). 다음 세션은 Phase 4부터. 상세=`docs/CAPABILITY_SELF_CONTAINMENT_HANDOFF.md`.
> 작성: 2026-07-01. 관련 대화: 최소 설치 씨앗 → 업데이트 → 표준/확장 → 어휘·앱 관리.

## 1. 문제 (한 문장)

**능력(capability)이 IndieBizOS에서 일급 단위가 아니다.** 하나의 능력을 이루는 세 조각이 서로 다른 곳에 흩어져 있어, 능력을 하나의 단위로 **설치·철거·구분**할 수 없다.

| 조각 | 무엇 | 지금 사는 곳 |
|---|---|---|
| 어휘 | 능력이 *무엇*인가 (이름·설명·op) | 중앙 `data/ibl_nodes_src/{sense,self,limbs,others,engines,table}.yaml` |
| 코드 | *어떻게* 실행되나 | 패키지 폴더 `data/packages/installed/tools/<pkg>/` (handler.py·tool.json) |
| 설치상태 | *켜졌나* | 폴더 위치 (installed / not_installed) |

### 세 고장
1. **설치/철거가 어휘를 안 옮긴다** — `package_manager.uninstall_package`는 코드 폴더만 옮김. 어휘는 중앙 src에 잔류 → 좀비어휘 / `--check` 깨짐. 새 패키지 어휘는 안 뜸(손으로 src 편집해야).
2. **단위 불일치** — 설치는 패키지 단위인데 한 패키지에 어휘 다수, 게다가 이질적(`web` = `search_ddg` 글로벌·키리스 + `search_naver` 한국·키필요)이 묶여 분리 불가.
3. **언어에 관리 어휘 없음** — `self:package` 류 IBL 액션 부재. 관리는 백엔드 REST/UI로만. 시스템이 자기 언어로 grow-on-demand 못 함.

### 뿌리
능력 = {어휘 + 코드 + 의존성 + 메타(키·무게·로케일)} 여야 하는데 흩어져 있고 생애주기(설치/철거/구분) 동작이 없다.

## 2. 목표 아키텍처

**각 패키지 = 자기완결 능력.** 어휘 조각을 코드와 함께 폴더에 둔다. 빌드는 *중앙 코어 + 설치된 패키지들의 조각*을 병합.

- **패키지-소유 액션** → 그 패키지의 `ibl_actions.yaml`에 정의 (관례 이미 존재: `house-designer/ibl_actions.yaml`).
- **backend-native 액션** (pkg 없음: workflow/trigger/schedule/delegate/world/self_check 등, 엔진 자체 기능) → 중앙 `ibl_nodes_src/`에 잔류. 이것이 *항상 존재하는 불가철 코어*.
- **빌드** = 중앙 7파일 + 설치된 패키지 `ibl_actions.yaml` 병합 → `ibl_nodes.yaml`.
- **설치** = 폴더 투입 → 리빌드 → 어휘 등장 / **철거** = 폴더 제거 → 리빌드 → 어휘 소멸 (원자적, 좀비 없음).

이러면 README의 "폴더 하나 떨어뜨리면 인식된다"가 *코드뿐 아니라 어휘까지* 참이 되고, 국제/서드파티 팩이 자연히 가능해진다.

## 3. 설계 결정 (확정)

- **D1. 조각 파일 = 패키지 폴더 안 `ibl_actions.yaml`** (기존 관례 계승). 다중 노드 선언 가능(예: radio = sense:radio + limbs:radio). 형식은 `house-designer/ibl_actions.yaml`을 템플릿으로.
- **D2. 어휘(무엇) vs tool.json(도구 매핑, 어떻게) 분리 유지** → `--check` 삼각(ibl_actions ↔ tool.json ↔ handler `_OP_DISPATCHERS`) 그대로 살림.
- **D3. 코어는 중앙 잔류** — backend-native 액션만. `ibl_nodes_src`가 "엔진 자체 어휘"로 축소.
- **D4. 이름 불변** — 마이그레이션은 *정의 위치*만 옮김. 액션 이름/코드 문자열 불변 → 해마 코퍼스 무손상. (패키지 *분할*도 이름은 유지 → 코퍼스 안전.)
- **D5. 불변식**: Phase 0~3은 순수 리팩터 — 142 액션·동작 동일, `ibl_nodes.yaml` **의미 동일**(바이트는 달라질 수 있음). 신기능(게이팅/에디션)은 Phase 4~5에서만.
- **D6. 항상 초록** — 패키지 1개당 1커밋, 매 커밋 `build --check` + 스모크 통과. bisect 가능·되돌림 가능.

## 4. 단계 (Phases)

### Phase 0 — 토대 & 안전망 (동작 변화 0)
- [x] **`build_ibl_nodes.py` 병합기** — 중앙 7파일 빌드 후 **설치된 패키지 `ibl_actions.yaml` 병합**. fragment 0개면 `output=merged`(바이트 동일). 있으면 구조 병합 후 재직렬화(`serialize_nodes_document`). 헬퍼: `collect_package_fragments`·`merge_fragments`·`serialize_nodes_document`. `--check` 바이트 비교와 write 모두 `output` 기준. **(2026-07-01 완료·검증)**
- [x] **fragment 형식 확정** — 단일: `{node: <name>, actions: {...}}` (house-designer 관례) / 다중: `{nodes: {<node>: {actions: {...}}, ...}}` (radio처럼 노드 걸침). 둘 다 collect가 처리.
- [x] **`--check` 부재-패키지 관용** — *구조적으로 자동 해결*: 빌드는 설치된 패키지 fragment만 흡수 → not_installed 패키지 어휘는 카탈로그에 없음 → 좀비/에러 없음. (단 해당 액션이 아직 중앙 src에 있으면 마이그레이션 전까진 여전히 중앙 소속 — Phase 3에서 패키지별로 이관되며 관용이 실현됨.) 별도 코드 불필요.
- [x] **마이그레이션 하네스** 스크립트(`scripts/migrate_package_vocab.py`, 완료): 패키지 하나에 대해 [중앙 src에서 액션 추출(tool→패키지 매핑=`build_tool_index`) → 패키지 `ibl_actions.yaml` 기록 → 중앙 src에서 제거 → 리빌드 → `ibl_nodes.yaml` **의미 동일** 단언]. Phase 3의 작업마로 재사용됨.
- 성공기준: `build --check` 초록, `ibl_nodes.yaml` 의미 동일(diff 0), 해마/카탈로그 무변.
- **검증 완료**: `--check` 바이트 일치(142 액션·전 가드 통과) / 재직렬화→재파싱==원본(무손실) / 디스크 스캔·단일+다중노드 병합·충돌·미지노드 감지 / 임시 패키지 정리 후 복귀. **미커밋.**

### Phase 1 — 파일럿 1개 패키지 ✅ 완료
- [x] 파일럿 = **`radio`** (coherent·키리스·다중노드[sense+limbs]·제거 가능 = 전체 루프 검증에 최적).
- [x] 하네스로 radio 마이그레이션 → `build --check` → 의미 동일 확인.
- [x] 라이브 왕복: radio **철거** → radio 어휘 사라짐(좀비 0) → **재설치** → 복귀.
- 성공기준: 파일럿으로 전 루프 end-to-end 증명. **달성.**

### Phase 3 — 대량 마이그레이션 (본 그라인드) ✅ 완료(2026-07-01)
- [x] 나머지 33 패키지를 하네스로 마이그레이션(118액션). youtube로 왕복 재검증.
- [ ] **이질 패키지 분할**(고장② 해결, 필요한 곳만): `web` → `web-core`(ddg/crawl) + `kr-search`(naver); `location-services` → 글로벌(weather) + KR(restaurant/navigate) 등. 이름 불변. **미착수 — 분할은 향후 별도 작업.**
- 종료상태: 중앙 src = backend-native 24액션만(sense2·self13·limbs2·others7); 그 외 전 패키지 액션이 자기 패키지에 co-locate. **달성.**
- 성공기준: 매 커밋 초록, 전체 완료 후 142 의미 동일. **달성.** 마이그레이션 중 `merge_fragments` null-병합 버그 발견·수정(상세=핸드오프).

### Phase 2 — 생애주기 어휘 ✅ 완료(2026-07-01)
- [x] `[self:package]{op: list/install/remove/info}` IBL 액션 = `package_manager` + 리빌드 + `ibl_access`(+ibl_engine+consciousness_agent) 핫리로드 래핑(`backend/ibl_routing.py` `_package_op`/`_rebuild_ibl_vocab`).
- [x] 파일럿(radio)으로 IBL 경로 왕복 테스트 — `/ibl/execute` 호출만으로 제거→재설치, 사람 개입(`/packages/reload`) 불필요.
- 성공기준: 시스템이 *자기 언어로* 능력을 설치/철거(고장③ 해결). **달성.**

### Phase 4 — 능력 메타 (표준 문제로 넘어가는 다리)
- [ ] 각 `ibl_actions.yaml`에 `needs_key`·`weight`·`locale`·`tier` 부여 (핸들러에서 자동 도출 + `--check` 검증 = op 어휘 검증과 같은 결).
- [ ] 런타임 활성 필터(prompt_builder/ibl_access): 설치된 것 중 "키 있음 ∧ 하드웨어 충족 ∧ 에디션 허용"만 노출. 키 대기 = dormant(임시방편 아님, SIM 슬롯).

### Phase 5 — 표준 에디션 & 설치 선택
- [ ] 에디션 매니페스트: **표준 = keyless ∧ universal ∧ light** 기본 패키지 집합.
- [ ] 3-상태: available(카탈로그만) / installed-dormant(코드 있음, 키 대기) / live.
- [ ] seed/installer(이미 만든 install.sh·seed.py·bootstrap.md)에 **에디션 + 로케일 선택** 연결 → 관련 팩만 설치. 로케일-무관은 *설치조차 안 함*(카탈로그엔 있어 on-demand 제안).

## 5. 불변식 & 리스크

- **해마 무손상**: 액션 이름·코드 문자열 불변이 열쇠. 이름 바꾸면 코퍼스 마이그레이션 필요 → **금지**(위치만 이동).
- **항상 초록 / 1패키지 1커밋**: 되돌림·bisect 가능.
- **의미 동일이 바이트 동일을 대체**: Phase 0에서 병합기 도입 시점엔 바이트 동일, 마이그레이션 시작 후엔 의미 동일 단언으로 전환.
- **문서 7표면 갱신 의무** (feedback_vocab_change_docs): 어휘 구조 변경 시 audit/api_ibl/guides/architecture/packages/README 동기.
- **backend-native는 co-locate 대상 아님** → 중앙 src는 절대 비지 않음(엔진 어휘로 잔존).
- **리스크**: 이질 패키지 분할 시 공유 코드 중복 → 공통 모듈은 별도 얇은 의존으로. deps 격리는 무게 축(Phase 4~5)에서.

## 6. 표준 vs 관리 — 분리 유지

이 계획의 Phase 0~3은 **관리 메커니즘**(어휘를 설치/철거하는 장소)만 만든다. "표준이 뭐냐"는 Phase 5의 *기본 집합 프리셋*일 뿐 — 섞지 않는다. (섞어서 복잡했던 게 원래 문제였음.)

## 7. 착수 지점 (다음 세션)

Phase 0의 세 항목부터:
1. `build_ibl_nodes.py` 병합기 (설치된 패키지 `ibl_actions.yaml` 흡수, 없으면 바이트 동일).
2. `--check` 부재-패키지 관용 + per-package 삼각.
3. 마이그레이션 하네스(추출→기록→제거→리빌드→의미동일 단언).
그다음 Phase 1 파일럿 = `radio`.

참고 파일: `scripts/build_ibl_nodes.py`(입력=중앙 7파일, line~1332), `data/packages/not_installed/tools/house-designer/ibl_actions.yaml`(형식 템플릿), `backend/package_manager.py`(install/uninstall), `backend/ibl_access.py`(카탈로그 로드).
