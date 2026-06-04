# 새 IBL 액션 추가 체크리스트

새 액션(도구)을 만들 때 **반드시 아래 전체를 완료**해야 한다. 하나라도 빠지면 에이전트가 해당 액션을 사용할 수 없다.

> **갱신 (2026-05-28 IBL 단일화 반영)**: 더 이상 패키지별 `ibl_actions.yaml` + `register_actions()` 자동 등록을 쓰지 않는다. 액션 정의의 단일 진실 소스는 `data/ibl_nodes_src/`이며, `scripts/build_ibl_nodes.py`로 빌드한다. 핸들러 시그니처도 ToolContext SDK(`execute(tool_input, context)`)로 통일됐다.

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

## 1단계: 패키지 도구 작성

도구 패키지 디렉토리에 도구의 **구현(handler)**과 **정의(tool.json)**를 둔다. (액션 정의 yaml은 패키지가 아니라 2단계의 src에 둔다.)

**경로**: `data/packages/installed/tools/{패키지ID}/`

| 파일 | 필수 | 설명 |
|------|------|------|
| `handler.py` | ✅ | `execute(tool_input, context)` — ToolContext SDK 시그니처 |
| `tool.json` | ✅ | `tools[]` 배열에 도구 정의 (name, description, input_schema) |
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

### tool.json 템플릿
```json
{
  "tools": [
    {
      "name": "my_action",
      "description": "도구 설명 (에이전트가 읽는다)",
      "input_schema": {
        "type": "object",
        "properties": { "query": { "type": "string", "description": "..." } },
        "additionalProperties": true
      }
    }
  ]
}
```

### op 분기 액션(단일 액션 + op 파라미터)이면
핸들러에 디스패처를 표준 형태로 둔다 — `--check`가 AST로 키를 정확 비교한다:
```python
_OP_DISPATCHERS = { "my_action": { "list": _list, "new": _new, "close": _close } }
_OP_DEFAULTS    = { "my_action": "list" }   # op 미지정 시 폴백
```
그리고 tool.json `input_schema.properties.op.enum` = op 값들, `op.default` = 기본값으로 맞춘다.

---

## 2단계: 액션 정의 (단일 소스 src → 빌드 → 검증)

**액션 정의는 패키지가 아니라 `data/ibl_nodes_src/{node}.yaml`에 추가한다.** (node = `sense`/`self`/`limbs`/`others`/`engines`)

### src에 액션 추가
해당 노드 파일의 `actions:` 아래에 항목을 추가:
```yaml
      my_action:
        description: 액션 설명 (시스템 프롬프트에 노출 — 20~50자)
        group: my_group           # UI 그룹(도메인). 표시용
        target_description: 주요 입력 설명 (UI 전용)
        router: handler
        tool: my_action           # ← tool.json 의 name 과 일치해야 함
        implementation: 내부 동작 요약 (UI 전용)
        target_key: query         # tool_input 의 주 파라미터 키
        keywords: [한글키워드, english_keyword]
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
- `src.tool` ↔ `tool.json` 의 name
- `src.ops.values` ↔ `tool.json` `op.enum`, `src.ops.default` ↔ `op.default`
- `src.ops.values` ↔ `handler.py` `_OP_DISPATCHERS[tool]` 키(AST), `src.ops.default` ↔ `_OP_DEFAULTS[tool]`

> 이 `--check`는 pre-commit 훅과 World Pulse self-check(12시간 주기)에도 합류해 있다. 통과해야 커밋이 된다.

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

## 5단계: 확인

1. **등록**: `[node:my_action]{...}` 를 execute_ibl(또는 `POST /ibl/execute`)로 실행 — 단, sense 외 부작용 액션은 주의.
2. **연상**: `IBLUsageDB().search_hybrid("자연어", top_k=5)` 에 내 액션이 상위로 나오는지.
3. **실행**: 서버 재시작 후 에이전트에게 자연어로 요청.

---

## 전체 요약

| 단계 | 작업 | 빠뜨리면? |
|------|------|----------|
| 1. 패키지 도구 | handler.py(`execute(tool_input, context)`) + tool.json | 도구 자체가 없음 |
| 2. src 정의 + 빌드 | `ibl_nodes_src/{node}.yaml` → `build_ibl_nodes.py` → `--check` | IBL 실행 불가 / 검증 실패 |
| 3. 해마 데이터 | 합성 용례 + 학습 JSON | 에이전트가 연상 못 함 |
| 4. 임베딩 | `rebuild_index()` | 시맨틱 검색 불가 |
| 5. 확인 | 등록 + 연상 + 실행 | 배포 후 장애 |

**1~4를 모두 완료해야 에이전트가 액션을 인식하고 사용할 수 있다.**
