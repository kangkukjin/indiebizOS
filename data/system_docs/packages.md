---
title: 도구 패키지 시스템
scope: 패키지 구조(handler/tool.json), 설치 절차, 설치 패키지 목록(수·표=빌드 파생). IBL 어휘는 코어 `ibl_nodes_src`와 패키지 `ibl_actions.yaml`이 소유권별 정본이며, op 분기 패키지는 `_OP_DISPATCHERS` 표준 채택.
owner_code: package_manager.py, tool_loader.py
last_updated: 2026-09-13
see_also: [architecture.md, ibl.md]
---

# 도구 패키지 시스템 가이드

이 문서는 IndieBiz OS의 도구 패키지 설치/제거 방법을 정의합니다.
시스템 AI는 패키지 관련 작업 시 반드시 이 문서를 참조해야 합니다.

## 핵심 개념

### 도구 패키지란?
에이전트가 동적으로 로딩하여 사용하는 확장 기능입니다. 에이전트는 실행 시 필요한 도구를 패키지에서 불러와 사용합니다.

### 패키지 유형
- **도구 패키지 (tools)**: 에이전트가 `tool.json` + `handler.py`를 통해 동적으로 로딩하여 사용하는 기능 단위. IBL 액션으로 노출 가능.
- **백엔드 코어 모듈 (extensions/)**: 에이전트가 호출하는 도구가 아니라 백엔드 시스템 내부에서 사용되는 코어 모듈 (에이전트 실행, 대화 관리, Gmail, 스케줄러 등). `tool.json`/`handler.py` 없이 백엔드에서 직접 import.

### 폴더 구조
- **not_installed/tools/**: 보유 묶음 보관 위치. 최초 이관 시 잠듦으로 시작
- **installed/tools/**: 보유 묶음 보관 위치. 최초 이관 시 활성으로 시작
- **installed/extensions/**: 백엔드 코어 모듈
- **dev/tools/**: 개발 중인 패키지

### 보유와 활성 (어휘 레고박스 1판)

보유는 installed/tools와 not_installed/tools의 합집합이다. 두 폴더는 보관 위치이며
최초 이관 이후 켜짐/꺼짐을 뜻하지 않는다. 사전집은 보유 전체, 실행 사전은 몸별
`data/vocabulary/activation.json`으로 로드 시 거른다. 필수 공급자는
`data/vocabulary_policy.yaml` 한 선언으로 보호한다.

HTTP·런처 **내 어휘**·self:package는 `vocabulary_lifecycle.set_package_active` 한 함수를 쓴다.
사람이 깨우거나 잠재우면 원장과 캐시만 바뀐다. 폴더 이동·전체 빌드·코퍼스 삭제는 없다.
저장고 이동은 다음 AI 요청의 프롬프트에서 묶음의 자동 소개와 관련 관용구를 빼서 모델 입력을 줄인다. 상주 시스템 AI·프로젝트 에이전트도 기억 없는 요청까지 현재 활성 집합으로 다시 조립한다. 과거 대화와 코퍼스는 보존하며, 실행 차단만으로 잠재우기 완료로 보지 않는다.
IBL 호출은 사람에게 변경을 제안하며 직접 활성 선택을 바꿀 수 없다. 과거 삭제 진입점도
기억과 파일을 보존하는 잠재우기로 수렴한다.

### 파일로 주고받기

런처 안경 메뉴 → 설정 아래 **내 어휘**에서 **단어묶음 저장고**를 우클릭 → **파일 가져오기**로 `.iblpack`을 넣는다. 받은 묶음은
검증·용례 시딩 후 잠든 상태로 보관하며 사람이 깨운다. **내보내기**는 공개 소스와
배포 용례를 한 파일로 만든다. manifest가 없는 옛 묶음은 공개 fixture를 용례로 쓰며,
추가 자원은 제작자의 manifest 선언이 필요하다. 개인 기억·설정을 자동 동봉하지 않는다.
형식·변환·등록 경계의 정본은 `docs/IBLPACK_FORMAT.md`다.

새 파일 등록에는 사전집 갱신이 필요하지만 깨우기/잠재우기에는 빌드가 없다.
정본 배포에서 기존 묶음을 나누는 경우에는 `vocabulary_policy.yaml`의 `bundle_splits`가
소유권 이동을 확인한 뒤 기존 활성 선택·분류·쓰레기통 복원 위치를 새 묶음에 한 번만
이어 준다. 새 묶음에 이미 선택 기록이 있으면 덮어쓰지 않는다. 학술은 논문·연구자 /
개체 식별 / 세계은행 통계, 문화는 공연·전시 / 책·고전, 쇼핑은 상품·중고 / 외주
서비스로 분리했다. 낱말 이름·호출 계약·기존 기억은 유지한다.
[분리 구현·검증 기록](../../docs/VOCAB_BUNDLE_SPLIT_2026_09_13.md).
형제 모듈 교체는 기존 재시작 제약을 따른다. 상주 자원 정지·메모리 회수는 1판 밖이다.
옛 텍스트는 새 파일로 변환만 하며 Nostr도 같은 ZIP의 운반 경로를 쓴다.

## 필수 파일 형식

### 1. tool.json - 도구 정의 **(빌드 산출물 — 직접 편집 금지)**
에이전트에게 노출될 도구의 이름과 입력 스키마. **손으로 쓰지 않는다** — `scripts/build_ibl_nodes.py` 가 패키지의 `ibl_actions.yaml`(아래 §3) 의 `tool_json` 블록 + `ops` 에서 파생하고, 파일 첫 줄 `_generated` 표식이 그 사실을 광고한다. 편집해도 다음 빌드가 되돌리고, `--check` 가 커밋을 막는다.

형식은 **객체**(옛 배열 형식 아님):

```json
{
  "_generated": "build_ibl_nodes.py가 ibl_actions.yaml의 tool_json 블록에서 파생 — 직접 편집 금지.",
  "id": "패키지id",
  "name": "패키지 이름",
  "description": "패키지 설명",
  "version": "1.0.0",
  "guide_file": "guide.md",
  "tools": [
    {
      "name": "도구명",
      "description": "도구 설명",
      "input_schema": {
        "type": "object",
        "properties": {"param1": {"type": "string", "description": "파라미터 설명"}},
        "required": ["param1"]
      }
    }
  ]
}
```

**삼각 검증**: `--check` 가 `ibl_actions.yaml`(또는 코어 src) ↔ `tool.json` ↔ `handler.py` 의 `_OP_DISPATCHERS` 를 AST 로 정확 비교한다 — op 하나가 어긋나도 커밋이 막힌다.

### 도구 설명 작성 가이드 (2026-01-20)
AI가 도구를 정확히 선택하도록 간결하고 범용적인 설명 권장:
- **구조**: 한줄 요약 + 데이터 형식 + 예시
- **예시**: `"라인 차트 생성. x-y 데이터를 선으로 연결하여 시각화.\n\n데이터 형식: [{x: 값, y: 값}, ...]\n\n예시: data=[{x:1, y:1}, {x:2, y:4}]"`

### 가이드 파일 시스템 (guide_file) (2026-01-29)
복잡한 사용법을 가진 도구에 상세 가이드를 on-demand로 제공하는 시스템.
description에 모든 내용을 넣지 않고, 필요할 때만 가이드를 주입하여 토큰을 절약합니다.

**두 가지 유형:**

**(A) 공용 가이드 (data/guides/)** — 의식 에이전트 기반 선택
- `data/guides/` 폴더에 마크다운 파일 저장 (수치는 architecture.md '시스템 통계'의 빌드 파생 구간)
- 의식 에이전트가 사용자 메시지를 분석하여 관련 가이드 2-3개 선택
- `prompt_builder._load_guide_file()`로 로드 후 프롬프트에 주입

동작 흐름:
```
`<execution_map>` 의 가지별 `guide:` 줄(가이드 목차) → 의식이 guide_files 로 지목 (2026-09-03, 옛 get_guide_list 키워드 매칭 폐지)
    → consciousness_agent.process() (가이드 선택)
    → JSON 출력: { "guide_files": ["investment.md", ...] }
    → prompt_builder가 data/guides/에서 읽어 프롬프트에 주입
```

**(B) 패키지 레벨 가이드 (tool.json의 guide_file)**
- 패키지 폴더 내 가이드 파일
- `tool.json`의 `guide_file` 필드로 지정 (개별 도구 또는 패키지 레벨)
- 에이전트가 `read_guide` 도구로 직접 읽거나 IBL 엔진에서 참조

**가이드 파일 작성 팁:**
- 사용법, 규칙, 예시 코드 포함
- description에는 한 줄 요약만, 나머지는 가이드에 작성
- 5000~8000자 이내 권장

**관련 파일:** `consciousness_agent.py`, `prompt_builder.py`, `tool_loader.py`, `system_tools.py`, `ibl_engine.py`

### 2. 실행 로직 — 두 가지 방식

#### (A) handler.py (복잡한 후처리가 필요한 경우)
표준 `execute(tool_input, context)` 함수를 포함해야 합니다. 도구 이름·프로젝트 경로·에이전트 등 호출 문맥은 `ToolContext`가 나릅니다.

```python
def execute(tool_input: dict, context):
    """도구 실행 함수"""
    if context.tool_name == "도구명":
        # 로직 구현
        return {"success": True, "items": []}
    raise ValueError(f"알 수 없는 도구: {context.tool_name}")
```

#### (B) api_registry.yaml 등록 (API 호출 + transform으로 충분한 경우)
`data/api_registry.yaml`에 도구를 등록하면 handler.py 없이 동작합니다. `node` 필드를 추가하면 IBL 노드 액션으로 자동 병합됩니다.

```yaml
kosis_search_statistics:
  service: kosis
  endpoint: /statisticsList.do
  transform: kosis_list
  node: sense                # IBL 자동 병합 (Phase 25: statistics → sense)
  action_name: search_statistics
  description: "통계표 목록 검색"
```

api_engine 라우팅 액션들이 이 방식을 사용합니다.

### 3. IBL 노드 액션 등록 — 어휘가 사는 두 자리

어휘의 단일 진실 소스는 **둘로 갈린다**(보유 묶음 각각이 자기 fragment 를 갖는다 — 수·표는 아래 PACKAGES_TABLE 빌드 구간이 정본):

| 어디에 | 무엇 |
|--------|------|
| `data/ibl_nodes_src/<node>.yaml` | **코어 어휘** — 기능어(`self`·`others`·`table`)와 패키지에 묶이지 않는 액션 |
| `<패키지>/ibl_actions.yaml` | **패키지 어휘** — 그 패키지가 가져오는 낱말. 능력 자기완결화: 설치하면 어휘가 따라 들어오고 제거하면 따라 나간다 |

빌드가 둘을 합쳐 `data/ibl_nodes.yaml`(런타임 캐시)과 각 `tool.json` 을 만든다. 패키지 fragment 는 두 형식을 받는다 — 단일 노드 `{node: <이름>, actions: {...}}`, 다중 노드 `{nodes: {<노드>: {actions: {...}}}}`. 템플릿은 `data/packages/installed/tools/house-designer/ibl_actions.yaml`.

> 옛 판(2026-05-28)은 "패키지 폴더에 `ibl_actions.yaml` 을 두지 않는다"고 적고 있었다 — 그 규약은 능력 자기완결화로 뒤집혔다. 지금 코어 src 에 넣어야 하는 것은 *패키지가 없어도 존재해야 하는 낱말*뿐이다.

```yaml
# data/ibl_nodes_src/engines.yaml
engines:
  # scope: workspace          # (선택) 노드 레벨 기본값. 자세한 건 ibl.md "액션 스코프" 참고.
  actions:
    create_site:               # 액션 이름 (노드 내에서 유일해야 함)
      description: 웹사이트 프로젝트 생성
      router: handler          # handler.py로 라우팅
      tool: site_manager       # handler.py에서 매핑할 도구명
      target_key: site_name    # 자연어에서 추출한 대상이 매핑될 파라미터
      default_input:           # 기본 입력값 (선택)
        action: create
    add_component:
      description: 웹사이트에 컴포넌트 추가
      target_description: 컴포넌트 이름
      router: handler
      tool: component_manager
      target_key: component_name
```

추가 후 빌드 + 검증:
```bash
python3 scripts/build_ibl_nodes.py          # data/ibl_nodes.yaml 재생성
python3 scripts/build_ibl_nodes.py --check  # 일치 확인
```

빌드 산출물(`data/ibl_nodes.yaml`)은 첫 줄에 `# GENERATED — DO NOT EDIT` 헤더가 있으며 런타임이 읽는 단일 파일이다. 직접 편집하지 말 것.

#### postprocess 필드 (감각 전처리) — ★현재 선언한 액션 0개
정보성 액션의 출력이 길 때 경량 AI로 압축하여 컨텍스트 폭발을 방지하는 층. 액션 정의 안에 `postprocess` 블록으로 선언한다.

> **새 액션에 이걸 붙이기 전에 읽을 것**: 2026-06-27 이후 이 블록을 선언한 액션은 없다. 압축이 `records[]`/`items[]` 통화를 문자열로 파괴해서, 검색·여행계가 전부 **구조화 통화 + 사람용 `message`** 로 옮겨갔기 때문이다. 통화를 내는 액션에는 붙이지 말 것 — 파이프가 그 자리에서 끊긴다. 긴 결과의 현행 대책은 압축이 아니라 봉투 다이어트·자동 스필(technical.md)이다.

```yaml
search:
  router: handler
  tool: search
  postprocess:                # 후처리 설정 (선택)
    type: compress            # 전처리 유형 (현재: compress)
    threshold: 1500           # 이 글자 수 이상일 때만 압축 (기본: 1500)
    prompt: "각 검색 결과를 제목, URL, 핵심 내용 1줄로 압축하라."  # 액션별 커스텀 프롬프트 (선택)
```

- **type**: 전처리 유형. 현재 `compress`만 구현.
- **threshold**: 결과가 이 글자 수 미만이면 후처리를 건너뜀 (기본: 1500).
- **prompt**: 액션 특성에 맞는 압축 지시. 생략 시 범용 프롬프트 사용.
- 통화(`items`/`records`)를 내는 액션·결과를 보존해야 하는 액션에는 적용하지 않는다. 호출자는 `params._raw: true` 로 우회할 수 있다.

### 4. 가이드 파일 - 에이전트용 사용 설명서 (선택)

복잡한 워크플로우를 가진 패키지는 가이드 파일을 작성하여 에이전트가 올바른 순서로 도구를 사용하도록 한다.

**두 가지 레벨**:

#### (A) 패키지 레벨 가이드 (도구 호출 시 자동 주입)
- tool.json에 `"guide_file": "파일명.md"` 추가
- 에이전트가 이 패키지의 도구를 처음 호출할 때 자동으로 가이드 내용이 주입됨
- 파일 위치: 패키지 폴더 내 (예: `data/packages/installed/tools/bulletin/guide.md`)

#### (B) 시스템 레벨 가이드 (`read_guide` 도구로 검색 가능)
- `data/guides/` 폴더에 마크다운 파일 작성
- `data/guide_db.json`에 항목 추가 (id, name, description, keywords, file)
- 에이전트가 `read_guide` 도구(내부 `ibl_routing.search_guide`)로 검색하여 참조
- 여러 패키지에 걸친 워크플로우 설명에 적합

---

## 패키지 설치 — 완전한 등록 절차

### 내 어휘에서 선택

런처 안경 메뉴 → 설정 아래 **내 어휘**(아이콘 데스크톱 — 필수 단어묶음·단어묶음 저장고는 고정 폴더, 쓰레기통은 위치를 옮길 수 있는 보호 폴더, 나머지는 일반 폴더로 자유 분류; 바탕과 각 폴더는 독립 OS 창)에서 묶음을 **저장고에 넣기**(잠재우기)·**바탕으로 꺼내기**(깨우기)로 고른다(`POST /vocabulary/{id}/activation`). 준비된 묶음의 선택에는 빌드·재시작이 없다. 창 구조의 정본은 `docs/VOCABULARY_WINDOWS_2026_09_13.md`.
새 묶음 등록이나 정의 변경은 보유 사전집 갱신이 필요한 별개의 동작이다.

### 수동 설치 (패키지 폴더를 직접 생성한 경우)
패키지 폴더를 `installed/tools/`에 직접 만들면 된다.

**필수 파일 구조:**
```
installed/tools/{package_id}/
├── ibl_actions.yaml   # 어휘 소스 — 액션 정의 + tool_json 블록 (빌드가 읽는다)
├── tool.json          # 빌드 산출물 — 손으로 만들지 말 것
├── handler.py         # 필수 — execute(tool_input, context). op 분기는 `_OP_DISPATCHERS`
├── manifest.json      # 권장 — 패키지 메타데이터
└── tools/             # 실제 도구 모듈들 (tool_*.py)
```

어휘를 살리는 절차:
1. `ibl_actions.yaml`에 액션/op 설명·통화·부작용·fixture와 `tool_json` 원본을 쓴다.
2. `handler.py` 구현과 `_OP_DISPATCHERS`를 맞춘다.
3. 빌드로 중앙 레지스트리·tool.json·fixture·문서 마커를 파생한다.
4. 첫 등록은 `add_examples_batch`로 자연어→IBL 용례를 시드하고 재학습용 데이터에도 남긴다. 설명은 존재를 알릴 뿐 자연어 선택과 인자 모양을 대신하지 않는다.
5. `scripts/ibl_param_sweep.py`로 관측 인자 표면을 갱신하고 실제 해마 연상 프로브와 fixture 종단을 확인한다.
6. `build_ibl_nodes.py --check`와 패키지 건강검사를 통과시킨다.

```bash
# <패키지>/ibl_actions.yaml (또는 코어면 data/ibl_nodes_src/<node>.yaml) 편집 후
python3 scripts/build_ibl_nodes.py          # ibl_nodes.yaml·tool.json·문서 파생 재생성
python3 scripts/build_ibl_nodes.py --check  # 삼각 검증 + 파생물 신선도
```
- 라이브 반영: `POST /packages/reload` 는 **`handler.py` 만** 갈아끼운다 — `tool_*.py` 같은 서브모듈이나 새 어휘는 백엔드 재기동이 필요하다.
- 새 액션을 더했으면 `data/guides/new_action_checklist.md` 의 문서 표면 갱신 의무도 함께 처리한다.

**가이드 파일 등록** (있는 경우):
- 패키지 레벨: tool.json에 `"guide_file": "가이드파일명.md"` 필드 추가
- 시스템 레벨: `data/guide_db.json`에 항목 추가 + `data/guides/`에 파일 작성

### 잠재우기

POST /packages/{id}/uninstall은 사람의 요청임(`api_vocabulary.human_authority` — 브라우저 출처, 원격은 런처 세션 인증; 로컬 무인 HTTP·IBL 은 사람 선택으로 보지 않는다)을 검사한 뒤 공통 생명주기로
활성 선택을 해제한다. 소개·실행용 회상·호출을 차단하고 파일·설정·용례·벡터를 보존한다.
코드 업데이트 후 형제 모듈을 교체하는 경우의 기존 재시작 제약은 그대로다.

### 주의사항
- **노드 추가 금지**: 기존 6개 노드(sense, self, limbs, others, engines, table)만 사용. 새 노드는 `data/ibl_nodes_src/meta.yaml`/`scripts/build_ibl_nodes.py`(NODE_ORDER) 변경 + 라우팅 코드 합의 후 별건 작업.
- **액션 이름 충돌**: 같은 노드에 같은 이름의 액션이 이미 있으면 src 빌드가 후행 정의로 덮어쓰니, 접두사를 붙여 구분할 것 (예: `radio_play`, `radio_search`).
- **빌드 산출물 직접 편집 금지**: `data/ibl_nodes.yaml` 첫 줄의 `# GENERATED` 헤더 확인. 수정 시 다음 빌드에서 원복된다.

---

<!-- IBL_STATS:START -->
## 현재 보유한 도구 패키지 (50개 — 빌드 파생)

**op 분기 33 패키지** (2026-05-28 dispatcher 표준화 — 모두 모듈 레벨 `_OP_DISPATCHERS` dict 노출, `build_ibl_nodes.py --check` 가 AST 정확 비교): android · blog · books · browser-action · bulletin · business · cctv · community-portal · computer-use · context7 · culture · entity-lookup · family-news · finance-record · guest-helper · health-record · investment · lecture_workspace · location-services · media_producer · memory · music-player · notebook · pc-manager · public-files · radio · real-estate · study · system_essentials · web · web-builder · youtube · publishing. (전체 op 분기 액션은 **76개** — 그중 일부는 backend-native 라우팅이라 패키지 밖: `others:board/feed/follow/nostr` · `self:goal/manage_events/output/package/switch/trigger/workflow` · `sense:world`.)

> 목록은 현재 `_OP_DISPATCHERS`를 가진 보유 패키지에서 파생한다. 새 op를 추가하거나 은퇴시키면 빌드가 목록과 수를 함께 갱신한다.
<!-- IBL_STATS:END -->

> 아래 표의 **행 집합은 빌드가 관리**한다(은퇴 행 자동 삭제·신설 행 자동 추가 — tool.json 설명으로). 설명 산문은 문서 소유라 풍부하게 고쳐도 보존된다.

<!-- PACKAGES_TABLE:START -->
| ID | 이름 | 설명 |
|----|------|------|
| ai-ops | AI Ops (원샷 낱말) | 원샷 AI 낱말 — 통화 대수 세 자리(입구 self:struct=비정형→items 구조화 · 중간 table:ai=items→items 의미  |
| android | Android | 안드로이드 폰 화면 조작 — `[limbs:android]{op}` 단일 센터피스 (snapshot/tap/type/swipe/key/long_press/open_app). 집 PC=ADB+uiautomator(USB) / 폰 자신=네이티브 AccessibilityService(USB 불필요) — 핸들러가 프로파일로 분기. 폰 온디맨드 감각(`sense:here`/`listen`/`see`/`phone`) 핸들러도 이 패키지 |
| blog | Blog | 블로그 RAG 검색 및 인사이트 분석 (진실 소스=Obsidian vault, DB는 파생 검색 인덱스) |
| books | 책·고전 | 도서 검색·대출 통계·추천과 서양·한국 고전을 조회합니다. |
| browser-action | Browser Action | Playwright 기반 브라우저 자동화 v5.0 (36개 도구: ref/CSS selector, stealth, 쿠키 동의 자동처리, 네트워크 캡처, vision 모드, 다중 탭/iframe, 동적 콘텐츠 대기, 다단계 폴백 추출, CDP 타임아웃) |
| bulletin | Bulletin | 로그인 없는 자유게시판 `[others:bulletin]` — 게시판마다 공개 주소 `/b/<5자>`, 주소 아는 사람이 로그인 없이 글·사진 게시 |
| business | Business | 비즈니스 관계 및 연락처(이웃) 관리 |
| cctv | CCTV | CCTV/웹캠 관련 도구 |
| cloudflare | Cloudflare | Cloudflare 서비스 통합 (Pages, Workers, R2, D1, Tunnel) |
| community-portal | Community Portal | 개인 포털 `[others:portal]` — `/h/<5자>/` 다중 포털, 회원=이웃 CRM 레벨 0~4, 진열 다이얼·회원 실행 게이트·감사 로그 |
| computer-use | Computer Use | 컴퓨터 사용 자동화 |
| contest | Contest | AI 공모전·경진대회 검색 (Kaggle, `sense:contest`) |
| context7 | Context7 | Context7 라이브러리 문서 검색 |
| culture | 공연·전시 | KOPIS 공연·공연장과 KCISA 전시·문화행사를 조회합니다. |
| data-ops | Data Ops | 통화 변환자 9동사 (filter/sort/take/select/dedup/groupby/join/union/merge) — 순수 변환. `group: transform`, `scope: workspace`, `runs_on: anywhere`. 파이프(`>>`·`&`)와 같은 닫힌 계급. + 표준 코어 문서 emitter `table:structure`·`table:document` (2026-07-03 media_producer서 이관) |
| entity-lookup | 개체 식별 | Wikidata에서 동명이인·동음이의를 식별하고 개체의 사실을 조회합니다. |
| family-news | Family News | 가족신문 `[others:family_news]` — 폰(USB) 사진으로 판 조판→`/n/<5자>` 누적 발행, 방명록·가족 사진 업로드 |
| finance-record | Finance Record | 재무 원장 `[self:finance]{op}` — 소비(지출·수입 거래)와 소유(자산·부채)를 **주체(owner) 축**(개인/회사)으로 한 원장에. 폰 결제 알림 수거(`op:sync`)·다형 입력 적재(`ingest_engine` 공용). 2026-08-14 `[self:spend]` 흡수 |
| freelance-services | 외주 서비스 | 외주 서비스 상품과 프리랜서 전문가를 검색합니다. |
| guest-helper | Guest Helper | USB 손발 — 발급 `[self:limb]{op}`(USB 페이로드 생성·승인·폐기) + 조작 `[limbs:guestpc]{op}`(셸/파일). 헬퍼=Go 단일파일, 허브로 아웃바운드(그 PC 방화벽 무설정). 눈 없음(셸·파일만) |
| health-record | Health Record Manager | 건강 정보 기록/관리 (혈압, 혈당, 체중, 증상, 투약) |
| house-designer | House Designer | 대화형 집 설계 도구. 다각형 방, 재질, 구조 요소(기둥/보), 다중 지붕, 필로티, 건물 프로파일, 계단(직선/L자/U턴/나선형/Winder |
| ibl-core | IBL Core | IBL 핵심 도구 |
| investment | Investment | 한국/미국 주가, 재무제표, 공시, 뉴스, 암호화폐 분석 |
| kosis | KOSIS | 통계청 KOSIS API 국가통계 조회 |
| lecture_workspace | Lecture Workspace | 강의 워크스페이스 (강의/슬라이드/재료/데크 op 분기) |
| legal | Legal | 대한민국 법률 정보 검색 (법령, 판례, 행정규칙, 자치법규 등) |
| location-services | Location Services | 위치 기반 서비스 (날씨, 맛집, 길찾기, 여행 정보, 숙박·한달살기 `sense:stay`) |
| media_producer | Media Producer | 홍보용 슬라이드, HTML 기반 MP4 동영상, AI 이미지·아이콘 생성(`engines:icon` 폰-로컬) |
| memory | Memory | 심층 메모리 (자동 시스템: 연상기억 검색 + 경험 증류) |
| music-player | Music Player | 내 음악 라이브러리 `[self:music]`(op 14) — 폴더 스캔·태그·앨범아트, **폴더 단위** 탐색·연속재생·검색·플레이리스트·정지. 재생=표면의 `<audio>` + `/music/stream`. ★2026-07-28 정리: AI 추천·관련곡 그래프·앨범/아티스트 뷰 은퇴(되살리지 말 것 — 남긴 축은 폴더) |
| notebook | Notebook | 근거 고정 질의 `[self:notebook]{op}` — 문서 더미(PDF·텍스트·유튜브 자막·웹 URL)에 이름 붙여 두고 **소스 안에서만** 답하며 인용을 단다(NotebookLM 로컬판). 인용은 코드가 원문에서 추출=환각 차단, 근거 없으면 `not_in_sources` 정직 반환. 색인=ko-sroberta+sqlite-vec+FTS5(★해마 모델 아님), `pc_only` |
| pc-manager | PC Manager | PC 파일 탐색, 외장하드 관리, 저장소 스캔 |
| photo-manager | Photo Manager | 사진/동영상 메타데이터 수집, 갤러리, 중복 탐지 |
| public-files | Public Files | 공개 파일 `[others:showcase]` — `/s/<5자>/` 로 디스크의 폴더를 그대로 공개(EXIF 제거·동영상 스트리밍 트랜스코드·자막) |
| radio | Radio | 인터넷 라디오 검색 및 재생 |
| real-estate | Real Estate | 부동산 시세·매물 — 국토부 실거래가 + 직방·네이버부동산 현재 매물 (`sense:realty{source}`) |
| shopping-assistant | 상품·중고 | 새 상품 가격비교와 중고 거래 매물을 검색합니다. |
| startup | Startup | 창업지원 사업공고 검색 (K-Startup, 중소벤처기업부) |
| study | 논문·연구자 | 학술 논문 검색·다운로드와 연구자·공저자 조회. |
| system_essentials | System Essentials | 파일 읽기/쓰기/검색(rg 고속 경로+인코딩 폴백), todo, 계획 모드, 이웃 조회, 웹앱 등기부 `[self:webapp]{op}`(파생 우선 — 진실 소스 7곳 재계산 + 전 함대 생존 실측) |
| visualization | Visualization | 범용 데이터 시각화 (차트/그래프 PNG/HTML) |
| web | Web Tools | 통합 검색 `[sense:search]{source: ddg/naver/gnews/hn/guardian}`(2026-08-05 어휘 압축 — 구 web-kr 네이버·study 가디언 흡수), 크롤링, RSS 피드, **신문 발행 `[engines:newspaper]`**(2026-08-15 스위치화 — prompt_hidden, 신문 계기 발행 버튼 전용). 2026-08-28 검색 통화 계약 둘: ①모든 소스가 **발행일 `date`(ISO 8601)** 를 싣는다(gnews=RFC2822 파싱·naver=news pubDate/blog postdate — 파싱 불능이면 필드를 달지 않는다, 모르는 날짜 미주장) → 신선도를 `[table:filter]` 술어로 세울 수 있다 ②`queries` 파라미터 선언이 `[string, array]` 유니온(핸들러가 이미 하던 배치 팬아웃을 문장 안에서 쓸 수 있게 — 선언이 능력보다 좁아 정직 거절되던 비대칭 수리). 가드 `backend/test_search_date_field.py` D1~D6 |
| web-builder | Web Builder | 홈페이지 제작/관리/배포 통합 도구 |
| world-statistics | 세계은행 통계 | 세계은행의 국가별 경제·사회 지표 시계열을 조회합니다. |
| youtube | Youtube | YouTube 영상 정보, 자막 추출, 다운로드 |
| nodejs | Node.js Executor | Node.js/JavaScript 코드 실행 환경. JSON 처리, 비동기 작업, npm 패키지 활용, 프론트엔드 로직 검증에 사용합니다. fs, path, crypto 등 내장 모듈과 설치된 npm 패키지 사용 가능. |
| publishing | Publishing Project Manager | 출판 프로젝트(책) 관리 도구. 원고 관리, 구조 기획, 조각글 수집 등.  사용 가이드: data/guides/book_publishing.md 참조 |
| python-exec | Python Executor | Python 코드 실행 환경. 수학 계산, 데이터 처리, 파일 파싱(JSON/CSV/XML), 날짜 계산, 차트 생성(matplotlib) 등에 사용합니다. pandas, numpy, requests 등 주요 라이브러리 사용 가능. |
| remotion-video | Remotion Video | React 기반 프로그래밍 방식의 동영상 생성 도구. Remotion 프레임워크를 사용하여 React/TSX 컴포넌트를 MP4 동영상으로 렌더링합니다. |
<!-- PACKAGES_TABLE:END -->

현재 잠든 목록은 폴더명에서 추측하지 않고 런처 **내 어휘** 또는 `self:package` 목록에서 확인한다.

**삭제된 패키지(디렉토리째 없음, 되살리지 말 것)**: `web-collector`(2026-08-15 — `sense:collect` 은퇴, `sense:crawl` 이 상위호환) · `local-info`(2026-08-15 — 지역정보 3형제 은퇴, `[sense:search]{source:"naver", type:"cafe"}` 가 승계. ★`area` 기본값 "오송" 하드코딩 = 세계의 명사가 코드에 박힌 헌법 위반이라 패키지와 함께 소멸) · `web-kr`(2026-08-05 — 네이버 검색이 `[sense:search]{source}` 로 흡수). 백업=`data/_backups/2026-08-15_*`.


**참고**: cloudflare 패키지의 `cf_tunnel` 도구는 원격 Finder 시스템의 Cloudflare Tunnel 설정을 자동화합니다. → [remote_access.md](remote_access.md)

---

<!-- EXT_COUNT:START -->
## 백엔드 코어 모듈 (extensions/) — 5개
<!-- EXT_COUNT:END -->

`installed/extensions/`에 위치한 모듈들은 에이전트가 호출하는 도구가 아니라 백엔드 시스템 내부에서 사용되는 코어 모듈입니다.
(prompt-generator·scheduler·switch-runner 는 pre-IBL 휴면 사본이라 2026-08-13 은퇴 — 정본은 backend/ 의 prompt_builder·scheduler·switch_runner)

| ID | 설명 |
|----|------|
| conversation | 대화 이력 관리 (conversation_db) |
| gmail | Gmail 연동 |
| indienet | 외부 메신저 연동 (Nostr 기반) |
| notification-system | 알림 시스템 |
| websocket-chat | WebSocket 기반 실시간 채팅 |

---

## 외부 폴더 등록
사용자의 기존 폴더를 패키지로 등록할 수 있습니다. AI가 폴더를 분석하여 적절한 `tool.json`과 `handler.py` 생성을 제안할 수 있습니다.

---

## 도구 상자 & 패키지 공유 (Nostr)

내가 만든 도구 패키지를 다른 IndieBiz 사용자들과 공유할 수 있습니다.

### 패키지 공개하기
1. **내 어휘** 바탕 우클릭 → **제작 및 라이브러리 관리**에서 묶음의 "Nostr에 공개" 클릭
2. 게시 본문은 같은 `.iblpack` ZIP 을 `IBLPACK/1` + Base64 텍스트로 실은 것(`GET /packages/{id}/generate-install` = `encode_package`) — AI 가 설치 설명을 짓지 않는다(수정 가능)
3. 선택적으로 사인(서명) 추가
4. 공개 버튼 클릭 — 게시 API 50,000자 한도를 넘으면 파일 전달을 안내한다

공개된 패키지는 `#indiebizOS-package` 해시태그로 Nostr 네트워크에 게시됩니다.

### 다른 사용자의 패키지 검색/설치
1. **내 어휘** 바탕 우클릭 → **공유 어휘 찾기**
2. Nostr 네트워크에서 공개된 패키지 검색
3. 받으면 `POST /packages/install-from-text` 가 옛 텍스트도 변환해 같은 `.iblpack` 등록 관문(`vocabulary_import.import_package`)으로 보낸다 — 검증·용례 시딩 뒤 **잠든 상태**로 보관되며 필수 묶음은 외부 파일로 교체할 수 없다
4. 시스템 AI 가 검토·설치하는 단계는 없다 — 깨우기는 코드 실행을 허용하는 사람의 선택이다

---

## API 엔드포인트
- `GET /packages` - 전체 패키지 목록
- `GET /packages/installed` - 활성 묶음
- `GET /packages/available` - 보유 묶음
- `POST /packages/{id}/install` · `POST /packages/{id}/uninstall` - 깨우기·잠재우기(사람 권한 검사, 공통 생명주기)
- `POST /packages/reload` - 런타임 캐시 초기화(`[self:package]{op:"reload"}` 와 같은 몸통)
- `GET /tools` - 활성 도구 목록
- `GET /vocabulary` · `POST /vocabulary/{id}/activation` · `GET /vocabulary/{id}/words` - 레고박스 목록·활성 선택·낱말
- `POST /vocabulary/import` · `GET /vocabulary/{id}/export` - `.iblpack` 가져오기·내보내기
- `GET|POST /vocabulary/desktop` - 내 어휘 아이콘 배치
- `GET /packages/{id}/generate-install` - Nostr 공유용 `IBLPACK/1` 텍스트 인코딩
- `POST /packages/{id}/publish` - Nostr에 패키지 공개
- `GET|POST /packages/nostr/search` - Nostr에서 패키지 검색
- `POST /packages/install-from-text` - 공유 텍스트(옛 형식 포함)를 `.iblpack` 등록 관문으로

---
*최근 변경(2026-08-28): web 패키지 검색 통화 계약 둘(발행일 `date` ISO 8601 · `queries` 유니온 선언) 반영. 패키지 표의 행 집합은 빌드가, 설명 산문은 문서가 소유한다. 이력 정본=git log·changelog.log(`[self:body]` 회상).*


### 내 어휘의 아이콘 데스크톱

런처 안경 메뉴의 **설정 바로 아래 → 내 어휘**를 고르면 아이콘 데스크톱이 독립 창으로 열린다. 자율주행·조종실 등의 모드 선택기와 모바일 모드 바에서는 제거했다.
일반 폴더와 아이콘의 위치는 몸별 활성 원장의 `desktop`에 저장되며, 분류는 실제 패키지 폴더를 옮기지 않는다.
처음에는 역할별 일반 폴더를 제공하고 사용자가 이름·위치·중첩 구조를 바꿀 수 있다. 일반 폴더를 없애면 내용은 상위 공간으로 나온다.

- **필수 단어묶음**: 보호된 보라색 묶음들을 표시. 필수 묶음은 잠재우거나 쓰레기통으로 보낼 수 없다.
- **단어묶음 저장고**: 큰 고정 아이콘. 묶음을 넣으면 잠들고 바탕·일반 폴더로 꺼내면 깨어난다. 활성 변경이 실패하면 이동도 적용하지 않는다.
- **쓰레기통**: 바탕 안에서 위치를 옮길 수 있는 삭제 대기 보관함. 위치는 저장되며 정렬해도 유지된다. 이름 변경·삭제·다른 폴더 안으로 이동은 금지한다. 넣으면 잠들며 파일·기억을 보존한다. 복원은 이전 사용 상태와 분류를 되돌린다. 현재 화면은 영구 삭제를 수행하지 않는다.

묶음 우클릭은 기본설명·단어소개·내보내기·상태에 따른 이동·정렬을 제공한다. 단어소개는 잠든 묶음도 선언에서 읽으며 핸들러를 실행하지 않는다.
저장고 우클릭에는 파일 가져오기·공유 어휘 찾기·제작 및 라이브러리 관리를 둔다. 바탕과 일반 폴더의 빈 공간 우클릭은 새 폴더·정렬이다.
폴더 창 안에서 아이콘을 바깥 바탕이나 다른 폴더로 끌어낼 수 있고, 우클릭의 꺼내기·보관·복원으로도 같은 작업을 수행한다.

어휘 바탕과 각 폴더는 OS 제목 표시줄·창 테두리를 가진 독립 Electron 창이다. 런처 바깥으로 이동하고 크기를 조절할 수 있으며, 여러 폴더를 나란히 열 수 있다. 같은 폴더를 다시 열면 기존 창을 복원해 앞으로 가져온다. 바탕 창을 닫아도 열린 폴더는 남는다.
마우스 드래그는 창을 넘는 HTML DataTransfer를 사용하고, 이동·이름 변경 등의 결과는 IPC로 다른 열린 폴더와 조종실에도 전파한다. 웹 표면은 같은 창의 폴더 라우트로 이동하고 뒤로가기로 돌아온다. [구현·검증 기록](../../docs/VOCABULARY_WINDOWS_2026_09_13.md).
