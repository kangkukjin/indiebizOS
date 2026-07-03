# 새 IBL 액션 추가 체크리스트

새 액션(도구)을 만들 때 **반드시 아래 전체를 완료**해야 한다. 하나라도 빠지면 에이전트가 해당 액션을 사용할 수 없다.

> **갱신 (2026-07 능력 자기완결화 반영)**: 도구 패키지의 액션 정의는 **그 패키지 폴더 안 `ibl_actions.yaml`**에 산다 — 코드(handler)와 어휘(액션 정의)가 한 능력에 원자적으로 묶여, 설치/제거로 어휘가 함께 들고난다(설치된 37개 도구 중 36개가 이 형식). `scripts/build_ibl_nodes.py`가 **설치된 패키지들의 `ibl_actions.yaml` + 중앙 `data/ibl_nodes_src/`(6개 코어 노드의 backend-내장 액션)**를 병합해 런타임 파일 `data/ibl_nodes.yaml`을 만든다. 핸들러 시그니처는 ToolContext SDK(`execute(tool_input, context)`).
>
> → 즉 아래 2단계의 "src"는 **패키지 능력이면 그 패키지의 `ibl_actions.yaml`, 코어 노드 액션이면 중앙 `ibl_nodes_src/`**를 뜻한다. (옛 `register_actions()` *런타임 자동 등록*은 폐기 유지 — 지금은 등록이 아니라 **빌드 시 병합**이다.)

---

## 0단계: 이름부터 — IBL 명명 헌법

액션을 만들기 전에 **이름을 헌법대로 정한다.** IBL을 인간이 잘 쓸 만큼 단순하게 다듬으면 LLM도 더 잘 쓴다(LLM은 인간 데이터를 학습하니까). 어휘 정리가 IBL 개선의 핵심이다. 전문: `system_docs/ibl_design_philosophy.md`.

1. **보편적이면 짧게, 특수하면 길게**: 기준은 빈도가 아니라 *보편성*. 보편적 능력은 짧은 단독어(`read`/`search`/`time`). 특수 분야 능력은 **이름에 "언제 쓰는지"를 담아** 자기설명적으로 — 길어지는 건 정상이다.
2. **변형은 op로 (굴절)**: 한 능력의 변종은 독립 어휘로 난립시키지 말고 **한 어휘 + op 파라미터**로. 단어의 활용처럼. (kr_price·us_price → `[sense:stock]{op}`)
3. **한 단어 = 한 개념 (과통합 경계)**: op는 굴절이지 잡동사니가 아니다. 무관한 능력을 한 이름에 op로 우겨넣지 말 것. 도메인이 드러나는 소수의 명료한 액션 + 타이트한 op.
4. **특수보다 보편 우선 (중복 금지)**: 새 액션을 만들기 전에 **기존 보편 액션이 이 일을 이미 할 수 있는지** 먼저 본다. 가능하면 보편 액션을 쓰고 새 특수 액션은 만들지 않는다. 단 IBL 액션은 *접근(access)*을 캡슐화하므로(고유 API·인증·파싱), 출력이 비슷해도 접근이 진짜 다를 때만 새로 만든다.
5. **land-grab 금지**: 보편 단어(`price`·`news` 등)는 진짜 보편 동작에만. 분야 액션은 분야가 이름에 드러나야 한다.

> 임시방편(영구 별칭) 금지. 이름을 바꾸면 정본·교재 표면을 다 옮긴 뒤 별칭을 은퇴시켜 단일 어휘를 유지한다.

---

## 0.5단계: 역할과 통화 계약 — "올바른 어휘"의 정의

이름을 정했으면 **이 액션이 셋 중 무슨 역할인지** 먼저 정한다. 역할이 *무엇을 반환해야 하는지*(통화 계약)를 결정하고, 핸들러는 그 계약을 지켜야 한다. 기준은 **"출력이 다시 흐르는 통화인가"**:

- **생성 (source)** — 바깥(params)에서 정보를 길어 **통화를 낸다**. 대다수 `sense:*`, `self` 조회.
- **변환 (transform)** — **통화를 받아 같은 통화를 낸다**(closure). `engines` 변환자(filter/sort/take/…).
- **행동 (terminal)** — 통화/입력을 받아 **세상에 작용하거나 산출물을 낸다. 더 흐르지 않음.** `limbs` 조작·발신·`engines` 렌더(document/slide/chart/tts).

**올바른 어휘 = 자기 역할의 통화 계약을 지키는 것** (단일 통화 = `items` = `[{…열린 dict…}]`):

| 역할 (returns) | 핸들러가 지켜야 할 계약 | 빠뜨리면 |
|------|------------------------|----------|
| **생성 (`items`)** | 결과에 `items`(비어있지 않은 dict 리스트) 부착. 가장 흔한 관습은 카드(`{title,meta,summary,url,image?}`)지만 *title조차 보장 아님*(열린 항목). 옛 수치/시계열도 items **행 dict**로(첫 키=x축 → 소비자 chart/table 이 재구성). | `>>` 로 못 흐름 = 조합 불가(섬). 자가점검은 error 키만 봐서 *못 잡는다* |
| **변환 (`transform`)** | `_prev_result`에서 items 를 읽어 **items 로** 반환(closure). `group: transform` · `scope: workspace` · `runs_on: anywhere`. | 통화가 끊김 |
| **단일값 (`scalar`)** | 통화 아님 — 단일 시세·시각·좌표 등. 명확한 dict 반환(에러 없이). | — |
| **행동 (`effect`)** | 통화 미기대 — 명확한 `success`/`error`(또는 파일 경로·산출물) 반환. **부작용이라 정기 실행 불가** → fixture 면제, `--check` 구조검사만. | — |

> ★**금지: `postprocess: compress`** — 결과 dict 전체를 LLM 압축 *문자열*로 치환해 items 를 **파괴**한다. **생성·변환 액션엔 절대 붙이지 말 것.** 긴 raw 텍스트를 줄이는 일은 *후처리*가 아니라 **핸들러가 items 로 구조화(증류)**하는 것이다 — 구조화가 곧 압축이다.

> ★`returns:` 는 **필수 필드**다. src 액션에 `returns: items | transform | scalar | effect` 한 줄을 명시한다 — `build_ibl_nodes.py --check` 가 존재·enum·transform 정합(`group:transform ⇔ returns:transform`)을 강제한다. 빠뜨리면 `--check` 실패.

---

## 1단계: 패키지 도구 작성

도구 패키지 디렉토리에 도구의 **구현(handler)**을 두고, 도구 **정의는 `ibl_actions.yaml`의 `tool_json:` 블록**에 둔다. (2026-07-03부터 `tool.json`은 빌드 산출물 — 직접 편집 금지, 빌드가 재생성한다.)

**경로**: `data/packages/installed/tools/{패키지ID}/`

| 파일 | 필수 | 설명 |
|------|------|------|
| `handler.py` | ✅ | `execute(tool_input, context)` — ToolContext SDK 시그니처 |
| `ibl_actions.yaml` | ✅ | 액션 정의(2단계) + `tool_json:` 블록(도구 정의 — 아래 템플릿) |
| `tool.json` | 산출물 | **빌드가 생성** (`_generated` 마커). 손편집하면 `--check` 실패 |
| `__init__.py` | ✅ | 빈 파일 |

### handler.py 템플릿 (ToolContext SDK)
```python
def execute(tool_input: dict, context):
    # 도구 이름: context.tool_name  (cwd·tool_name 인자 사용 금지)
    # 경로: context.project_path / context.resolve_path(p) / context.output_dir(name)
    name = context.tool_name
    if name == "my_action":
        return _my_action(tool_input, context)
    return {"success": False, "error": f"알 수 없는 도구: {name}"}
```
> `context`는 `ToolContext`(backend/tool_context.py): `tool_name`, `project_path`(절대경로), `project_id`, `agent_id`, `task_id` + `output_dir()`, `resolve_path()`. 산출물은 `context.output_dir()` 아래에 쓴다.

### 도구 정의 — `ibl_actions.yaml` 의 `tool_json:` 블록 템플릿
```yaml
tool_json:
  header:                # tool.json 최상위 메타 (id/name/description/version)
    id: my-package
    name: My Package
    description: 패키지 설명
    version: 1.0.0
  tools:
  - name: my_action
    description: 도구 설명 (에이전트가 읽는다)
    input_schema:
      type: object
      properties:
        query: { type: string, description: "..." }
      additionalProperties: true
```
빌드(`python scripts/build_ibl_nodes.py`)가 이 블록에서 `tool.json`을 생성한다.

### op 분기 액션(단일 액션 + op 파라미터)이면
핸들러에 디스패처를 표준 형태로 둔다 — `--check`가 AST로 키를 정확 비교한다:
```python
_OP_DISPATCHERS = { "my_action": { "list": _list, "new": _new, "close": _close } }
_OP_DEFAULTS    = { "my_action": "list" }   # op 미지정 시 폴백
```
`tool_json:` 블록의 op property 에는 **enum/default 를 쓰지 않는다** — 자리(`op: {type: string, description: ...}`)만 두면 빌드가 액션의 `ops:` 블록(2단계)에서 enum/default 를 **주입**한다. 저장하면 단일 소스 위반으로 빌드가 거부한다.

---

## 2단계: 액션 정의 (src → 빌드 → 검증)

액션 정의를 **알맞은 단일 소스**에 둔다 — 둘 중 하나:

- **도구 패키지 능력**(대다수) → 그 패키지 폴더의 **`ibl_actions.yaml`**. 최상위에 `node: <노드>`(단일 노드) 또는 `nodes: {…}`(복수 노드) 래퍼를 두고 그 아래 `actions:`를 둔다. 코드+어휘가 한 능력에 묶여 설치/제거로 함께 들고난다.
- **6개 코어 노드의 backend-내장 액션**(패키지 없이 backend가 직접 처리 — `router: system`/`workflow_engine` 등) → 중앙 **`data/ibl_nodes_src/{node}.yaml`**의 `actions:`.

어느 쪽이든 아래 **액션 항목 스키마는 동일**하다 (패키지 파일에선 `node:`/`nodes:` 래퍼 아래 들어갈 뿐).

### 액션 항목 추가
해당 `actions:` 아래에 항목을 추가:
```yaml
      my_action:
        description: 액션 설명 (시스템 프롬프트에 노출 — 20~50자)
        returns: items            # ★통화 역할 (items|transform|scalar|effect) — 0.5단계, --check 강제
        group: my_group           # UI 그룹(도메인). 표시용
        target_description: 주요 입력 설명 (UI 전용)
        router: handler
        tool: my_action           # ← tool.json 의 name 과 일치해야 함
        implementation: 내부 동작 요약 (UI 전용)
        target_key: query         # tool_input 의 주 파라미터 키
        keywords: [한글키워드, english_keyword]
        # runs_on: mac_only      # (선택) 폰 네이티브: 집 PC 전용이면. 기본 anywhere.
        #   집 하드웨어/무거운 의존/미검증 패키지=mac_only · 폰 센서=phone_only.
        #   build 가 data/phone_manifest.json 파생(폰 번들/계기필터/엔진가드 SSOT).
        # op 분기 액션이면:
        ops:
          default: list
          values:
            list: 목록 조회
            new: 새로 만들기
            close: 닫기
```

### 빌드
```bash
python scripts/build_ibl_nodes.py
```
→ `data/ibl_nodes.yaml`(런타임이 읽는 단일 파일)이 재생성된다. **`ibl_nodes.yaml`을 직접 편집하지 말 것 — 산출물이다.**

### 삼각 검증 (필수)
```bash
python scripts/build_ibl_nodes.py --check    # 실패 시 비0 종료
```
`router:handler` 액션에 대해 다음을 정확 비교한다:
- `src.tool` ↔ `tool_json:` 블록의 tools name (액션이 가리키는 도구의 실존)
- `src.ops.values` ↔ `handler.py` `_OP_DISPATCHERS[tool]` 키(AST), `src.ops.default` ↔ `_OP_DEFAULTS[tool]`
- `tool.json` 파일 ↔ 파생 결과 바이트 일치 (손편집·drift 검출 — 빌드로 재생성)
- (op enum/default 의 src↔tool.json 비교는 파생 구조로 **불필요해짐** — 빌드가 주입하므로 어긋날 수 없다)
- **fixture 완전성**: `returns: items|scalar` 액션은 `data/ibl_fixtures.json` 에 fixture 또는 exempt 가 있어야 함(다음 2.5단계). 없으면 `--check` 실패.

> 이 `--check`는 pre-commit 훅(커밋마다)과 일일 건강 점검(`ibl_health_check.py` §1A, AI 0)에 합류해 있다. 통과해야 커밋이 된다.

---

## 2.5단계: 행동 건강 fixture (실행 가능한 액션이면 필수)

`returns: items` 또는 `scalar` 인 액션은 **자기 정의(2단계의 `ibl_actions.yaml` / `ibl_nodes_src`)에 `fixture:` 필드 한 줄**을 단다 — `returns`/`ops`/`tool` 과 같은 액션 메타로. build 가 이 필드들을 모아 `data/ibl_fixtures.json`(**파생물**)으로 만들고, `ibl_health_check.py` 가 그 한 줄을 실행해 통화가 유효한지 단언한다. `--check` 가 *모든* items/scalar 액션의 `fixture`/`exempt` 필드 존재를 강제하므로 **새 액션이 건강검사망을 조용히 빠져나갈 수 없다.**

```yaml
      my_action:
        returns: items
        fixture: '[sense:my_action]{query: "올바른 예시 입력"}'   # ← returns 옆에 한 줄
        # 실행 인자가 꼭 필요해 고정 예시가 불가능하면 fixture 대신:
        # exempt: '파일 경로 인자 필요(고정 fixture 부적합)'
```

- **fixture**: 그 파라미터로 실행하면 GREEN(유효 통화/단일값)이 나오는 *대표 입력 하나*. 외부 키·데이터 의존이면 YELLOW 가능(구조 결함 아님).
- **exempt**: 파일 경로·좌표 쌍·표본 인자처럼 고정 예시가 부적합하거나, 폰/기기 전용이라 맥서 못 도는 경우. **반드시 사유를 적는다.**
- **effect(부작용)·transform(변환자)은 필드 없음** — effect 는 실행 불가(구조검사만), transform 은 골든 파이프(`ibl_health_check.py` §1C)로 흐름 검증.
- **파생**: `data/ibl_fixtures.json` 은 build 산출물이다(**직접 편집 금지** — 소스는 액션 필드). fixture 가 액션과 한 몸이라 **설치/제거를 자동으로 따라가고 고아 fixture 가 생기지 않는다**(2026-07-02 자기완결화). 패키지 능력이면 그 패키지 `ibl_actions.yaml`, 코어 노드면 `ibl_nodes_src` 에 필드를 둔다.
- **검증**: `python scripts/ibl_health_check.py` 로 자기 액션이 **GREEN** 인지 확인. RED 면 통화 계약 위반 — 고치기 전엔 미완성. 자세히 `docs/IBL_MAINTENANCE_MANUAL.md`.

---

## 3단계: 해마 합성 데이터 생성

에이전트가 이 액션을 **연상**하려면 해마(실행기억)에 용례가 있어야 한다. 첫 등록 시엔 경험 증류 데이터가 없으므로 합성 용례를 수동 생성한다.

### 원칙
- **다양한 자연어 표현** 10~30개 (한글 + 영문)
- **파라미터/op 변형** 다양하게
- 다른 액션과 **조합(파이프라인)**하는 예시도 포함

### 형식
```json
{"intent": "사용자가 입력할 자연어", "ibl_code": "[node:action]{params}"}
```

### 등록 (둘 다 한다)
```python
# (1) DB에 즉시 등록 (검색용)
from ibl_usage_db import IBLUsageDB
db = IBLUsageDB()
db.add_examples_batch([
    {"intent": "...", "ibl_code": "...", "nodes": "sense", "source": "synthetic", "tags": "패키지ID"},
])

# (2) 학습 JSON에 append (다음 재학습용) — data/training/ibl_distilled.json
```
**(1)은 즉시 검색, (2)는 다음 fine-tuning 반영. 둘 다 필요.**

---

## 4단계: 임베딩 재구축

합성 데이터를 DB에 넣었어도 **벡터 임베딩이 없으면 시맨틱 검색에 안 나온다.** 서버와 동일한 Python(sentence-transformers 설치된 환경)에서:
```bash
cd backend
python3 -c "from ibl_usage_db import IBLUsageDB; print(IBLUsageDB().rebuild_index())"
```
> 모델을 교체했거나 DB를 크게 바꿨으면 `rebuild_index()`로 재색인 필수. 서버 Python 경로 확인: `ps aux | grep 'python.*api.py' | grep -v grep`

---

## 자동 경로: 패키지를 통째로 설치할 때

위 1~5단계는 **한 패키지 안에 액션을 손으로 저술**하는 절차다. 이미 완성된 패키지를 **설치**하는 경우엔 `[self:package]{op:"install", package_id:"…"}`(= `package_manager.install_package`)가 다음을 자동으로 한다:

- not_installed → installed 이동 + 패키지 검증(`validate_tool_package`)
- 어휘 재빌드(그 패키지 `ibl_actions.yaml` 병합) + 런타임 캐시 리로드 (`_rebuild_ibl_vocab`)
- **해마 용례 자동 생성(3단계)** — `generate_for_package`가 그 패키지의 각 액션에 기본 용례를 심고 인라인 색인(4단계 포함)

즉 **설치는 3·4단계를 대신 해준다.** fixture(2.5)도 이제 패키지 `ibl_actions.yaml` 의 액션 필드라, 재빌드가 중앙 `data/ibl_fixtures.json` 으로 **파생** — 설치/제거를 자동으로 따라간다(손수 유지 불필요). **제거의 대칭 절차는 `action_removal.md` 참조.**

---

## 선택 단계: 앱 표면 노출 (`app:` 블록)

액션을 **앱 모드 계기(GUI)**로도 쓰게 하려면 src 액션 정의에 `app:` 블록을 단다 — 그러면 데스크탑(`GenericInstrument.tsx`)과 원격 런처에 **계기로 자동 등장**한다(표면별 코드 0줄, `GET /launcher/instruments` 파생).

```yaml
        app:
          icon: 🪙
          name: 코인                  # 단독 계기는 icon+name 필수
          order: 6                    # 홈 그리드 정렬
          inputs:
          - { key: coin, type: text, default: BTC, required: true }
          action: '[sense:crypto]{coin_id: "$coin"}'    # $key=입력 치환
          view:
          - { type: metric, big: '{data.current_price_krw|num}' }
```

- **저술 전에 기존 계기를 모방하라.** 명세 암기보다 튼튼한 절차: 만들려는 계기와 가장 비슷한 기존 `app:` 블록을 먼저 읽는다 — 살아있는 용례 코퍼스는 `grep -rn 'app:' data/ibl_nodes_src/*.yaml data/packages/installed/tools/*/ibl_actions.yaml` + standalone `data/instruments/*.yaml`. 패턴별 모범: 단순 조회+지표=host(시스템) / 목록+드릴+지도+종속 select=realty / CRUD 폼·탭=business / 채팅=messenger / 달력=calendar / 이미지=photo.
- view 프리미티브 14종: metric / kv / kv_list / card_list / image_grid / sparkline / list_action / thread / form / editable_list / map / calendar / group / blocks — 표시 템플릿 `{path|filter}`. blocks=문서 IR(read{blocks:true}·table:structure 출력) 렌더. **응답 shape은 추측하지 말고 live `/ibl/execute`로 확인 후 작성.**
- form 필드 9종: text / select / toggle / textarea / images / date / time / datetime / recurrence
- ★위 두 어휘 줄은 빌드의 **뷰-어휘 문서-동기 가드**가 `APP_VIEW_TYPES`/`APP_FORM_FIELD_TYPES` 선언과 자동 대조한다 — 뷰 어휘를 바꾸면 이 줄(과 `ibl.md` 앱 절의 같은 줄)도 함께 고쳐야 빌드가 통과한다.
- 정합성은 2단계의 `--check`가 함께 검증한다(`validate_app_blocks` — 참조 액션 실존, $key↔inputs, view 어휘, 계기 그룹).
- 해마(3·4단계)와 무관 — app:은 에이전트가 호출하는 어휘가 아니라 표면이 읽는 선언.
- 어휘 전체 명세: `docs/REMOTE_APP_GENERIC_RENDERER_PLAN.md`, 요약: `system_docs/ibl.md` "앱 표면 노출" 절. 뷰 어휘의 헌법적 지위(승격 4기준·정지규칙)는 `ibl.md` "표현 언어의 층위" 조항.

---

## 5단계: 확인

1. **등록**: `[node:my_action]{...}` 를 execute_ibl(또는 `POST /ibl/execute`)로 실행 — 단, sense 외 부작용 액션은 주의.
2. **연상**: `IBLUsageDB().search_hybrid("자연어", top_k=5)` 에 내 액션이 상위로 나오는지.
3. **실행**: 서버 재시작 후 에이전트에게 자연어로 요청.

---

## 전체 요약

| 단계 | 작업 | 빠뜨리면? |
|------|------|----------|
| 0.5. 역할·통화 계약 | 생성/변환/행동 정하고 역할의 통화 계약 충족 (`ibl_health_check.py` GREEN) | 통화 끊김 = 조합 불가(섬), 자가점검도 못 잡음 |
| 1. 패키지 도구 | handler.py(`execute(tool_input, context)`) + tool.json | 도구 자체가 없음 |
| 2. src 정의 + 빌드 | `ibl_nodes_src/{node}.yaml` → `build_ibl_nodes.py` → `--check` | IBL 실행 불가 / 검증 실패 |
| 2.5. fixture | 액션에 `fixture:`/`exempt:` 필드(items/scalar) → build 가 `ibl_fixtures.json` 파생 | `--check` 실패 = 커밋 거부 / 건강검사 누락 |
| 3. 해마 데이터 | 합성 용례 + 학습 JSON | 에이전트가 연상 못 함 |
| 4. 임베딩 | `rebuild_index()` | 시맨틱 검색 불가 |
| 5. 확인 | 등록 + 연상 + 실행 | 배포 후 장애 |
| (선택) 앱 표면 | src에 `app:` 블록 | 앱 모드 계기로 안 보임 (에이전트 사용엔 무관) |

**1~4(+items/scalar이면 2.5)를 모두 완료해야 에이전트가 액션을 인식하고 사용할 수 있다.**
