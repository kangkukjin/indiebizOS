# 능력 자기완결화 — 핸드오프 (다음 세션용)

> 이 문서만 읽으면 대화 맥락 없이 이어갈 수 있게 쓴다.
> 전략 개요는 `docs/CAPABILITY_SELF_CONTAINMENT_PLAN.md`, 배경은 기억 `project_capability_self_containment`.
> 최종 갱신: 2026-07-01 (Phase 0-② 완성 반영 — "부재-패키지 관용" 실제 구현).

---

## 0. TL;DR (여기부터)

- **하는 일**: 어휘(액션 정의)를 중앙 `data/ibl_nodes_src/`에서 각 패키지 폴더의 `ibl_actions.yaml`로 옮겨 **패키지=자기완결 능력**으로 만든다. 그래야 설치/철거가 코드+어휘를 원자적으로 넣고 뺀다.
- **완료**: Phase 0(①+③, **②도 이제 진짜 완성**) + Phase 1(radio 파일럿) + Phase 3(전체 34개 패키지 마이그레이션) + Phase 2(`[self:package]` 생애주기 어휘). 중앙 src에는 이제 backend-native **25액션**. 143액션 전체. `--check` 전항목 통과. **✅ 커밋·푸시됨**(origin/main `3dc9d6d`).
- **오늘 마지막 작업 — Phase 0-② 완성("부재-패키지 관용")**: Phase 2에서 `[self:package]{op:remove}`가 실제로 패키지를 철거해보니, **어휘 자체는 깨끗이 사라져도 `--check`의 두 검증기(fixture 완전성·포크가드)가 그 패키지 소유 fixture/allowlist 항목을 "고아"로 오탐**해 여전히 실패했다(이전에 "구조적으로 자동 해결됨"이라 적었던 판단이 절반만 맞았던 것). `scripts/build_ibl_nodes.py`에 `collect_dormant_package_qualifiers`(not_installed 쪽 `ibl_actions.yaml`을 스캔해 "정의는 있지만 꺼져있는" qualifier 집합 구축) + `_is_dormant_package_path`(stale allowlist 판정 시 그 패키지가 not_installed에 실존하면 관용) 추가. **라이브 검증**: kosis·radio를 not_installed로 옮긴 뒤 `--check` 완전 통과(재설치 후도 통과) + 돌아가는 백엔드에서 `[self:package]{op:remove}`→`--check` green→`install`로 복귀까지 종단. **네거티브 테스트**: 진짜 좀비(어디에도 없는 가짜 패키지 경로)는 여전히 정확히 flag됨 — 관용이 과하게 넓지 않음을 확인.
- **다음**: Phase 4(메타 `needs_key`/`weight`/`locale`/`tier` + 런타임 활성 필터 — "키 있음∧하드웨어 충족∧에디션 허용"만 노출) 또는 Phase 5(표준 에디션). 부재-패키지 관용은 이제 진짜 끝났으니, Phase 4는 순수하게 *새 메타 스키마 + 필터링 기능* 추가로 시작하면 된다.
- **불변식**: 이름 불변(위치만 이동). 마이그레이션 후 검증은 **의미 동일**(바이트 아님) — 하네스가 자동 단언.
- **Phase 3 중 발견·수정한 버그**: `merge_fragments`가 노드의 액션이 **전부** 이관되어 중앙 src `actions:`가 YAML null이 되는 경우 크래시(`setdefault`는 기존 None 값을 덮어쓰지 않음). `scripts/build_ibl_nodes.py`에서 수정 완료(커밋 `301d627`). engines·table 노드가 정확히 이 케이스(전체가 media_producer/web-builder/remotion-video/data-ops/visualization 소유)였음.
- **커밋 이력 함정(교훈)**: 배치 루프에서 `git commit -m "..."` 앞에 `--no-verify=false`라는 존재하지 않는 플래그를 써서 8개 커밋이 전부 실패 → 매 반복 `git add -A`만 누적되고 미커밋 상태로 34개 마이그레이션이 쌓임. 결과적으로 빌드 버그 수정 커밋(`301d627`)에 31개 패키지가 함께 실려버림(의도한 1패키지=1커밋 원칙 위반, 부득이 유지 — 재작업 리스크가 이득보다 큼). 이후 3개(visualization/web-builder/cctv)는 올바르게 분리 커밋. **다음 배치 작업 시**: 커밋 명령을 먼저 단독으로 테스트(`git commit -m test --dry-run` 류)하거나, 루프 안에서 매 반복 exit code를 실제로 확인.
- **Phase 2 중 확인한 기존 코드 함정**: `package_manager.list_available()`은 이름과 달리 installed+not_installed **전부** 반환한다(하위호환 목적). `[self:package]{op:list}`의 `available`은 `installed==False`로 걸러서 노출 — REST `/packages/available`은 옛 동작 그대로 둠(회귀 방지, 건드리지 않음).
- **교훈(사용자 지적으로 발견)**: 새 어휘를 추가하면 `data/guides/new_action_checklist.md`를 다시 열어 단계별로 대조할 것 — Phase 2에서 3·4단계(해마 합성 용례+`rebuild_index`)를 빠뜨렸다가 뒤늦게 채웠다(`self:package` 합성 용례 21개+재색인). `--check` green이 "다 했다"는 착각을 유발하기 쉬움. 상세는 기억 `feedback_vocab_change_docs`.

---

## 1. 지금 어디에 있나

계획 6단계 중 **Phase 0(①②③ 전부)·1·2·3 완료**. Phase 4·5 미착수.

| Phase | 상태 |
|---|---|
| 0-① 빌드 병합기 | ✅ 완료·검증·커밋·푸시(`16bcd39`, origin `7c683d0`) |
| 0-② 부재-패키지 관용 | ✅ **완성**(`3dc9d6d`) — 최초엔 "구조적 자동해결"로 오판, Phase 2가 실사용해보니 fixture/포크가드 오탐 발견 → 수정 |
| 0-③ 마이그레이션 하네스 | ✅ 완료(`scripts/migrate_package_vocab.py`) |
| 1 파일럿(radio) | ✅ 완료 — 왕복 검증(철거→137액션 클린 소멸→재설치→142 복귀) |
| 2 `[self:package]` 어휘 | ✅ 완료(`c666109`) — IBL 호출만으로 라이브 왕복 검증 |
| 3 대량 마이그레이션 | ✅ **완료**(2026-07-01) — 나머지 33개 패키지 전부 이관, youtube로 왕복 재검증 |
| 4 메타(needs_key/weight/locale)+활성필터 | ⬜ **다음 후보** |
| 5 표준 에디션+seed 연결 | ⬜ |

### 1.1 하네스 사용법 (Phase 4/5에서도 그대로 유용 — 신규 패키지 추가 시)
```bash
cd /Users/kangkukjin/Desktop/AI/indiebizOS
python3 scripts/migrate_package_vocab.py <package_name> --dry-run   # 대상 미리보기
python3 scripts/migrate_package_vocab.py <package_name>             # 실이관 + 재빌드 + 의미동일단언 + --check
```
성공 시: 패키지 폴더에 `ibl_actions.yaml` 생성 + 중앙 src에서 해당 액션 블록 제거 + `data/ibl_nodes.yaml`/`phone_manifest.json` 재생성. 실패(빌드 실패/의미 불일치/--check 실패) 시 **자동 롤백**(백업에서 복원, 생성된 fragment 삭제).
제약: 이미 `ibl_actions.yaml`이 있는 패키지는 재이관 거부(중복 방지). 소유 tool 0건이면 즉시 에러.

---

## 2. 완료한 것: Phase 0-① 빌드 병합기 (상세)

**파일**: `scripts/build_ibl_nodes.py` (미커밋).

**추가한 모듈 함수** (`def build(` 바로 위):
- `collect_package_fragments(root, yaml_mod) -> (fragments, issues)` — `PACKAGE_DIRS`(=`data/packages/installed/{tools,extensions}`) 아래 각 패키지의 `ibl_actions.yaml`을 읽어 `[(pkg_name, node, actions_dict), ...]` 반환. **두 형식 지원**:
  - 단일: `{node: <name>, actions: {...}}`
  - 다중: `{nodes: {<node>: {actions: {...}}, ...}}` (radio처럼 노드 걸침)
- `merge_fragments(data, fragments) -> issues` — `data['nodes'][node]['actions']`에 병합(변경). **충돌**(이미 존재하는 액션명)·**미지 노드** 감지해 issues 반환.
- `serialize_nodes_document(header, data, yaml_mod) -> str` — 병합된 data를 `safe_dump`(allow_unicode, sort_keys=False, width 큼)로 재직렬화. **fragment가 있을 때만** 사용.

**`build()` 내부 변경**:
- `data = _yaml.safe_load(merged)` 직후 fragment 수집·병합. `output` 변수 도입:
  - fragment 0개 → `output = merged` (기존 텍스트 = **바이트 동일**)
  - fragment 있고 병합 성공 → `output = serialize_nodes_document(...)` (재직렬화)
- fragment 오류(`frag_issues`)는 `issues = frag_issues + validate(data, root)`로 합류 → 실패 시 빌드 중단.
- `--check` 바이트 비교(`bytes_ok = current == output`)와 파일 쓰기(`target.write_text(output, ...)`) 모두 `output` 기준으로 바꿈.

**왜 안전한가**: 현재 설치된 패키지 중 `ibl_actions.yaml`을 가진 게 **하나도 없다**(house-designer는 `not_installed`라 스캔 안 됨). 그래서 병합기는 **완전 무동작**, 출력 바이트 동일. 리스크 0.

**검증 완료** (재현 명령은 §6):
- `--check` 바이트 일치(노드 6·액션 142·전 가드 통과, exit 0)
- 재직렬화→재파싱 == 원본 (142액션·블록스칼라 무손실)
- 임시 설치 패키지로 디스크 스캔·단일+다중노드 병합·충돌·미지노드 감지 → 정리 후 바이트 일치 복귀
- **커밋 상태**: Phase 0-①은 `16bcd39`로 커밋, `7c683d0`(라이브 상태 동기 — table-분리 등 그간 미커밋 더미 일괄)과 함께 origin/main에 푸시됨. **워킹트리 clean.** 다음 세션은 pull한 깨끗한 상태에서 시작.

---

## 3. 다음 세션이 알아야 할 핵심 사실

### 3.1 빌드 메커니즘
`build_ibl_nodes.py`의 `build()`는 `data/ibl_nodes.yaml`을 **텍스트 연결**로 만든다:
```
header(주석) + meta.yaml + "nodes:\n" + sense.yaml + self.yaml + ... + table.yaml   (NODE_ORDER 순)
```
- `NODE_ORDER = ["sense","self","limbs","others","engines","table"]`.
- 각 노드 src 파일은 **들여쓴 조각**: `  <node>:`(2칸) → `    actions:`(4칸) → `      <action>:`(6칸) → `        <field>:`(8칸).
- **주의**: 노드 블록에서 `actions:` 뒤에 `    description:`·`    tags:`(4칸)가 온다. 즉 **actions가 마지막이 아니다** → 액션을 파일 끝에 append하면 안 된다(중간 삽입/삭제 필요).

### 3.2 fragment 형식 (확정)
패키지 폴더에 `ibl_actions.yaml`. 템플릿: `data/packages/not_installed/tools/house-designer/ibl_actions.yaml`(단일 노드 예). 다중 노드는 `{nodes: {...}}` 형식.
- **tracked됨**: `.gitignore`에 `!**/ibl_actions.yaml` 화이트리스트 → git이 추적(패키지와 함께 이동).

### 3.3 tool → 패키지 매핑 (하네스 핵심)
`build_tool_index(root) -> {tool_name: (pkg_dir, tool_def)}` — 모든 설치 패키지 `tool.json`을 스캔. 각 액션은 src에 `tool: <tool_name>` 필드가 있으니, 이 인덱스로 **액션이 어느 패키지 소속인지** 판정한다.

### 3.4 --check가 도는 가드들 (전부 통과해야 exit 0)
삼각검증(등록·op enum·default·handler `_OP_DISPATCHERS`) / 코퍼스 param 정합 / fixture 완전성 / 포크-가드(INDIEBIZ_PROFILE) / OS-가드 / launcher-가드 / phone_manifest 정합 / 바이트 일치.
- fragment로 옮긴 액션도 이 삼각검증을 **자동으로** 받는다(병합된 data 기준). 액션의 `tool`이 그 패키지 `tool.json`에 있으니 통과.

### 3.5 불변식
- **이름 불변**: 액션 이름·`tool` 문자열·`ibl_code` 불변 → 해마 코퍼스 무손상. 절대 리네임 금지(위치만 이동).
- **의미 동일 ≥ 바이트 동일**: fragment가 생기는 순간 `ibl_nodes.yaml`은 **safe_dump 형식으로 전면 재포맷**된다(첫 마이그레이션 커밋에서 생성파일 diff가 거대함 — 정상). 검증은 **파싱해서 dict 비교**로 한다, 텍스트 diff 아님.
- backend-native 액션(pkg 없음: workflow/trigger/delegate/world/self_check 등)은 이관 대상 아님 → 중앙 src에 잔류(엔진 어휘).

---

## 4. Phase 0-③·Phase 1·Phase 3 — 완료 요약 (참고용, 재작업 불필요)

마이그레이션 하네스(`scripts/migrate_package_vocab.py`)는 §3.2~3.3 설계 그대로 구현·검증 완료. radio 파일럿(5액션) 및 나머지 33개 패키지(118액션) 전부 이관됨. **재사용은 §1.1** 명령으로 — 신규 패키지 추가 시나 이관 검증 재확인 시 그대로 쓴다.

**해결한 함정**(§0 요약 참조):
- 텍스트 수술 경계는 `^      <action>:`부터 다음 6칸 형제 또는 4칸 노드키 직전까지 — 정규식으로 정확히 처리됨(`remove_action_block`).
- 노드 액션이 **0개**가 되는 케이스(engines·table 노드가 정확히 이랬음) — `merge_fragments`의 `setdefault` 버그로 처음엔 크래시했으나 수정 완료(`301d627`). 빈 `actions:`(YAML null)를 `{}`로 정규화하는 방어가 `merge_fragments`와 `build()`의 total_actions 카운트 두 곳에 필요했다 — **비슷한 코드를 새로 짤 때는 `n.get("actions") or {}` 패턴을 기본으로 쓸 것**, `n.get("actions", {})`는 키가 None으로 존재하면 방어되지 않는다.

---

## 6. 검증 명령 (복붙용)

```bash
cd /Users/kangkukjin/Desktop/AI/indiebizOS

# 현재 상태 정상 확인 (바이트 일치·전 가드·exit 0)
python3 scripts/build_ibl_nodes.py --check; echo "exit=$?"

# 병합기 헬퍼 단위 검증 (재직렬화 무손실 + 병합/충돌/미지노드)
python3 - <<'PY'
import importlib.util, yaml, copy
s=importlib.util.spec_from_file_location('b','scripts/build_ibl_nodes.py')
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
d=yaml.safe_load(open('data/ibl_nodes.yaml',encoding='utf-8')); o=copy.deepcopy(d)
assert yaml.safe_load(m.serialize_nodes_document("# t\n",d,yaml))==o, "roundtrip broke"
print("roundtrip OK")
PY
```

의미 동일 단언 패턴(하네스에서 재사용):
```python
before = yaml.safe_load(<빌드전 ibl_nodes.yaml 또는 merged>)
# ... 마이그레이션 + build ...
after  = yaml.safe_load(open('data/ibl_nodes.yaml',encoding='utf-8'))
assert after == before, "의미 변함 — 롤백"
```

---

## 7. 함정 · 주의

- **첫 마이그레이션 = ibl_nodes.yaml 전면 재포맷**. 생성파일이라 무방하나, diff는 텍스트로 보지 말고 **의미 동일**로 검증.
- **리네임 금지** — 코퍼스 깨짐. 위치만 이동.
- **부재-패키지 관용**은 마이그레이션돼야 실현. 아직 중앙 src에 있는 액션은 그 패키지 철거 시 --check 깨짐(정상 — 미이관 상태이기 때문). 그러니 "철거 왕복 테스트"는 이관 완료된 패키지에만.
- **문서 7표면 동기**(feedback_vocab_change_docs): 어휘 구조가 실제로 바뀌는 Phase 3~5에서 audit/api_ibl/guides/architecture/packages/README 갱신.
- **커밋 규율**: 1패키지 = 1커밋, 매 커밋 `--check` 초록. bisect 가능.
- **핸들러 편집 시**: 어휘/코드 변경이 라이브 백엔드에 반영되려면 `/packages/reload`(핸들러) 또는 재시작(부팅 로드). 이번 Phase 0은 빌드 스크립트만 건드려 런타임 영향 없음.

---

## 8. 파일 지도

| 파일 | 역할 |
|---|---|
| `scripts/build_ibl_nodes.py` | 빌드/`--check`. `build()`, `collect_package_fragments`, `merge_fragments`(None-방어 수정됨), `serialize_nodes_document`, `build_tool_index`(tool→pkg), `NODE_ORDER`, `PACKAGE_DIRS`, `repo_root`. |
| `scripts/migrate_package_vocab.py` | 마이그레이션 하네스(완료). `find_owned_actions`, `build_fragment_doc`, `remove_action_block`, `migrate`. |
| `data/ibl_nodes_src/{meta,sense,self,limbs,others,engines,table}.yaml` | 중앙 어휘 소스. backend-native **25액션**(sense 2·self 14[package 포함]·limbs 2·others 7). engines·table은 `actions:` 비어있음(정상, 빌드 시 fragment로 채워짐). |
| `data/ibl_nodes.yaml` | 생성물(GENERATED). build 산출. |
| `data/packages/installed/tools/<pkg>/ibl_actions.yaml` | **35개 패키지 전부 보유**(radio+34). `handler.py`(op 디스패처)·`tool.json`(tool 정의)와 나란히. |
| `data/packages/not_installed/tools/house-designer/ibl_actions.yaml` | fragment **형식 템플릿**(단일노드 참고용). |
| `backend/package_manager.py` | `install_package`·`uninstall_package`(폴더 이동). `[self:package]`가 `backend/ibl_routing.py`의 `_package_op`를 통해 래핑함(완료). |
| `backend/ibl_routing.py` | `_package_op`(list/info/install/remove)·`_rebuild_ibl_vocab`(재빌드+캐시 초기화) — Phase 2 구현부. |
| `backend/ibl_access.py` | `ibl_nodes.yaml` 로드→카탈로그. Phase 4 활성필터 지점. |
| `docs/CAPABILITY_SELF_CONTAINMENT_PLAN.md` | 전략 6단계. |

---

## 9. 착수 순서 (다음 세션 — Phase 4 또는 Phase 5)

1. §6 첫 명령으로 현재 상태 초록 확인.
2. **Phase 4**: 부재-패키지 관용은 이제 완료됐으니(§0), 순수하게 메타 스키마만 남음 — 각 패키지 `ibl_actions.yaml`에 `needs_key`/`weight`/`locale`/`tier` 필드 추가(핸들러에서 자동 도출 가능하면 자동, 아니면 수동 부여) + `--check`에 이 메타 정합성 검증(op 어휘 검증과 같은 결) + 런타임 활성 필터(`prompt_builder`/`ibl_access` — 설치된 것 중 "키 있음∧하드웨어 충족∧에디션 허용"만 카탈로그·프롬프트에 노출, 키 대기=dormant 상태로 표시).
3. **Phase 5**: 표준 에디션(keyless∧universal∧light) 프리셋 정의 + install.sh/seed.py 연결.
4. 시작 전 `git log --oneline -14`로 이 세션 커밋들(`301d627`~`3dc9d6d`) 확인해 상태 파악.
