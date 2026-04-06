# 새 IBL 액션 추가 체크리스트

새 액션(도구 패키지)을 만들 때 **반드시 아래 전체를 완료**해야 한다. 하나라도 빠지면 에이전트가 해당 액션을 사용할 수 없다.

---

## 1단계: 패키지 생성

도구 패키지 디렉토리를 생성하고 필수 파일을 작성한다.

**경로**: `data/packages/installed/tools/{패키지ID}/`

| 파일 | 필수 | 설명 |
|------|------|------|
| `handler.py` | ✅ | `execute(tool_name, tool_input, project_path)` 함수 |
| `tool.json` | ✅ | 도구 정의 (이름, 설명, input_schema) |
| `ibl_actions.yaml` | ✅ | IBL 액션 정의 (node, actions, router, tool, target_key) |
| `__init__.py` | ✅ | 빈 파일 |

### handler.py 템플릿
```python
def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    if tool_name == "my_action":
        return _my_action(tool_input)
    return f"알 수 없는 도구: {tool_name}"
```

### ibl_actions.yaml 템플릿
```yaml
node: "self"  # 또는 sense, limbs, others, engines
actions:
  my_action:
    description: "액션 설명"
    router: handler
    tool: my_action
    target_key: query
    keywords:
      - 한글키워드
      - english_keyword
```

---

## 2단계: IBL 노드 등록

패키지 파일만 만들면 시스템이 모른다. **반드시 register_actions를 실행**해야 `ibl_nodes.yaml`에 등록된다.

```python
cd backend
python3 -c "
from ibl_action_manager import register_actions
result = register_actions('패키지ID')
print(result)
"
```

### 확인
```python
python3 -c "
import yaml
with open('../data/ibl_nodes.yaml') as f:
    data = yaml.safe_load(f)
actions = data['nodes']['self']['actions']  # node에 맞게 변경
print('my_action' in actions)  # True여야 함
"
```

---

## 3단계: 해마 합성 데이터 생성

에이전트가 이 액션을 **연상**하려면 해마(실행기억)에 용례가 있어야 한다. 첫 등록 시에는 경험 증류 데이터가 없으므로 합성 데이터를 수동 생성한다.

### 합성 데이터 작성 원칙
- **다양한 자연어 표현**: 같은 의도를 다르게 표현 (10~30개)
- **한글 + 영문**: 둘 다 포함
- **필터/파라미터 변형**: 다양한 파라미터 조합
- **파이프라인**: 다른 액션과 조합하는 예시도 포함

### 데이터 형식
```json
{"intent": "사용자가 입력할 자연어", "ibl_code": "[node:action]{params}"}
```

### 등록 방법

#### (1) DB에 직접 등록
```python
from ibl_usage_db import IBLUsageDB
db = IBLUsageDB()
db.add_examples_batch([
    {"intent": "...", "ibl_code": "...", "nodes": "self", "source": "synthetic", "tags": "패키지ID"},
    ...
])
```

#### (2) 학습 데이터 JSON에 append
```python
import json
with open('data/training/ibl_distilled.json', 'r') as f:
    data = json.load(f)
data.extend([
    {"intent": "...", "ibl_code": "..."},
    ...
])
with open('data/training/ibl_distilled.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

**(1)과 (2) 둘 다 해야 한다.** DB는 즉시 검색용, JSON은 다음 재학습용.

---

## 4단계: 임베딩 재구축

합성 데이터를 DB에 넣었어도 **벡터 임베딩이 없으면 시맨틱 검색에서 안 나온다.** 서버 Python 환경에서 rebuild_index를 실행해야 한다.

```bash
cd backend
# 서버와 동일한 Python 사용 (sentence-transformers 설치된 환경)
python3 -c "
from ibl_usage_db import IBLUsageDB
db = IBLUsageDB()
result = db.rebuild_index()
print(result)
"
```

**주의**: 시스템 Python(`/usr/bin/python3`)에 `sentence-transformers`가 없으면 실패한다. 서버가 사용하는 Python 경로를 확인할 것:
```bash
ps aux | grep "python.*api.py" | grep -v grep
```

---

## 5단계: 확인

### (1) ibl_nodes.yaml 등록 확인
```
[self:my_action]{...}  # execute_ibl로 실행 가능한지
```

### (2) 해마 연상 확인
```python
from ibl_usage_db import IBLUsageDB
db = IBLUsageDB()
results = db.search_hybrid("자연어 질의", top_k=5)
for r in results:
    print(f"[{r.score:.2f}] {r.intent} → {r.ibl_code}")
# 내 액션이 상위에 나오는지 확인
```

### (3) 실제 실행 확인
서버 재시작 후, 에이전트에게 해당 기능을 자연어로 요청해보기.

---

## 전체 요약

| 단계 | 작업 | 빠뜨리면? |
|------|------|----------|
| 1. 패키지 생성 | handler.py, tool.json, ibl_actions.yaml | 도구 자체가 없음 |
| 2. 노드 등록 | `register_actions()` | IBL 실행 불가 |
| 3. 해마 데이터 | 합성 용례 + 학습 JSON | 에이전트가 연상 못 함 |
| 4. 임베딩 | `rebuild_index()` | 시맨틱 검색 불가 |
| 5. 확인 | 등록 + 연상 + 실행 | 배포 후 장애 |

**1~4를 모두 완료해야 에이전트가 액션을 인식하고 사용할 수 있다.**
