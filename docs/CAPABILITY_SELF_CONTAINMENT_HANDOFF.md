# 능력 자기완결화 — 핸드오프 (다음 세션용)

> 이 문서만 읽으면 대화 맥락 없이 이어갈 수 있게 쓴다.
> 전략 개요는 `docs/CAPABILITY_SELF_CONTAINMENT_PLAN.md`, 배경은 기억 `project_capability_self_containment`.
> 최종 갱신: 2026-07-01.

---

## 0. TL;DR (여기부터)

- **하는 일**: 어휘(액션 정의)를 중앙 `data/ibl_nodes_src/`에서 각 패키지 폴더의 `ibl_actions.yaml`로 옮겨 **패키지=자기완결 능력**으로 만든다. 그래야 설치/철거가 코드+어휘를 원자적으로 넣고 뺀다.
- **완료**: **Phase 0-① 빌드 병합기**(`scripts/build_ibl_nodes.py`) — 설치된 패키지 `ibl_actions.yaml`을 빌드가 흡수. fragment 0개면 바이트 동일(현재 상태=무동작). 전항목 검증. **✅ 커밋·푸시됨**(origin/main `7c683d0`; Phase0 커밋 자체는 `16bcd39`). 워킹트리 clean.
- **다음**: **Phase 0-③ 마이그레이션 하네스** 작성 → **Phase 1 파일럿 = `radio`**.
- **불변식**: 이름 불변(위치만 이동). Phase 0~3은 동작·142액션 무변. 마이그레이션 후 검증은 **의미 동일**(바이트 아님).

---

## 1. 지금 어디에 있나

계획 6단계 중 **Phase 0-①만 완료**. 나머지 미착수.

| Phase | 상태 |
|---|---|
| 0-① 빌드 병합기 | ✅ 완료·검증·커밋·푸시(`16bcd39`, origin `7c683d0`) |
| 0-② 부재-패키지 관용 | ✅ 구조적 자동해결(코드 불필요) |
| 0-③ 마이그레이션 하네스 | ⬜ **다음 작업** |
| 1 파일럿(radio) | ⬜ |
| 2 `[self:package]` 어휘 | ⬜ |
| 3 대량 마이그레이션 | ⬜ |
| 4 메타(needs_key/weight/locale)+활성필터 | ⬜ |
| 5 표준 에디션+seed 연결 | ⬜ |

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

## 4. 다음 작업 A — Phase 0-③ 마이그레이션 하네스

**목표**: 패키지 하나를 안전하게 자기완결로 만드는 재사용 스크립트. Phase 3의 작업마.

**제안 위치**: `scripts/migrate_package_vocab.py` (신규).

**입력**: 패키지 이름 (예: `radio`).

**절차**:
1. `data = safe_load(현재 빌드 merged)` 또는 현 `ibl_nodes.yaml` 로드. `tool_index = build_tool_index(root)`.
2. 대상 패키지가 소유한 tool 집합 = `{t for t,(pd,_) in tool_index.items() if pd.name == 패키지}`.
3. 중앙 src 액션 중 `tool`이 그 집합에 든 것 = 이관 대상. **노드별로** 그룹. (액션의 노드 = data['nodes']에서 그 액션이 있는 노드.)
4. **패키지 `ibl_actions.yaml` 작성**: 단일 노드면 `{node, actions}`, 다중이면 `{nodes: {node: {actions}}}`. actions 값은 중앙에서 뽑은 정의 그대로(dict).
5. **중앙 src에서 제거**: 해당 노드 `.yaml` 파일에서 그 액션 블록을 삭제.
   - **권장(텍스트 수술)**: 노드 src 텍스트에서 `^      <action>:` (6칸) 라인부터, 다음 형제 액션(`^      \S`) 또는 노드레벨 키(`^    \S`, 예 description/tags) 직전까지를 삭제. 나머지 바이트는 보존됨.
   - 대안(구조 재직렬화)은 노드 src가 "들여쓴 조각"이라 다루기 까다로움 — 텍스트 수술 권장.
6. `python3 scripts/build_ibl_nodes.py` 실행(빌드) → 이제 fragment 존재하니 `ibl_nodes.yaml` 재직렬화됨.
7. **의미 동일 단언**: 마이그레이션 전 `data`(deepcopy 보관)와 마이그레이션 후 `safe_load(ibl_nodes.yaml)`가 **deep-equal**인지 확인. 다르면 실패·롤백.
8. `--check` 통과 확인(전 가드).

**하네스 자체 안전장치**: 6단계 전에 대상 파일들 백업(또는 git stash 지점), 7단계 실패 시 복원.

**함정**:
- 텍스트 수술의 경계 판정(6칸 액션 블록의 끝)을 정확히. 블록 스칼라(`|`)·리스트(`keywords:`)가 액션 안에 있으니 "다음 6칸 키 또는 4칸 키까지"로 끊어야 함.
- 이관 후 중앙 노드 파일에 그 노드의 액션이 **0개**가 될 수도(예: 노드 전체가 한 패키지). 그래도 `  <node>:\n    actions:\n    description: ...` 형태 유지되게(빈 actions 허용되는지 빌드로 확인). radio는 sense/limbs에 다른 액션도 많아 이 경우 아님.

---

## 5. 다음 작업 B — Phase 1 파일럿: `radio`

**왜 radio**: coherent(라디오 한 능력)·**키리스**·**다중 노드**(sense+limbs)·**제거 가능**(빼도 시스템 정상) → 전 루프를 가장 잘 검증.

**radio 액션**(현 카탈로그): `sense:radio`, `limbs:radio`, `limbs:player_status`, `limbs:volume`, `limbs:radio_favorite`. (실행 시 `build_tool_index`로 정확한 소유 tool 재확인할 것.)

**절차**:
1. 하네스로 radio 마이그레이션 → `data/packages/installed/tools/radio/ibl_actions.yaml` 생성(형식 B 다중노드) + 중앙 src에서 제거.
2. `build` → `--check` 통과 + 의미 동일 확인.
3. **라이브 왕복**(핵심 증명):
   - radio 패키지 철거(`not_installed`로 이동 or `package_manager.uninstall_package`) → `build` → radio 어휘가 카탈로그에서 **사라짐**(좀비 0, --check 통과).
   - 재설치 → `build` → radio 어휘 **복귀**.
4. 성공 시 커밋(“radio 어휘 자기완결화 — 파일럿”).

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
| `scripts/build_ibl_nodes.py` | 빌드/`--check`. **Phase 0-① 수정됨**. `build()`, `collect_package_fragments`, `merge_fragments`, `serialize_nodes_document`, `build_tool_index`(tool→pkg), `NODE_ORDER`, `PACKAGE_DIRS`, `repo_root`. |
| `data/ibl_nodes_src/{meta,sense,self,limbs,others,engines,table}.yaml` | 중앙 어휘 소스(현재 142액션 전부 여기). 마이그레이션이 여기서 액션을 빼감. |
| `data/ibl_nodes.yaml` | 생성물(GENERATED). build 산출. |
| `data/packages/installed/tools/<pkg>/` | 패키지: `handler.py`(op 디스패처)·`tool.json`(tool 정의). 여기에 `ibl_actions.yaml` 추가 예정. |
| `data/packages/not_installed/tools/house-designer/ibl_actions.yaml` | fragment **형식 템플릿**. |
| `backend/package_manager.py` | `install_package`·`uninstall_package`(폴더 이동). Phase 2 `[self:package]`가 래핑. |
| `backend/ibl_access.py` | `ibl_nodes.yaml` 로드→카탈로그. Phase 4 활성필터 지점. |
| `docs/CAPABILITY_SELF_CONTAINMENT_PLAN.md` | 전략 6단계. |

---

## 9. 착수 순서 (다음 세션)

1. §6 첫 명령으로 현재 상태 초록 확인.
2. §4대로 `scripts/migrate_package_vocab.py` 작성 + 텍스트 수술 + 의미동일 단언. 작은 임시 패키지로 자체 테스트.
3. §5대로 radio 파일럿 실행 → 철거/재설치 왕복 증명.
4. 통과 시 커밋(파일럿). 이후 Phase 2(`[self:package]`) 또는 Phase 3(대량) 진행.
