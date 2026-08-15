# 등록 스크립트 실행기 — [self:script]

> 2026-08-07 신설. **결정화 사다리의 가운데 가로대** — 자율주행이 write+run_command 로 만들어
> 검증까지 끝낸 스크립트를 "몸의 일부"로 승격시키는 관문. 이게 없던 시절엔 완성 스크립트가
> /tmp 고아가 되거나, 트리거가 자연어 위임([others:delegate])으로 매번 본격 모델을 깨워야 했다.

## 설계선 (역사적 이유 — 어기지 말 것)

**어휘는 코드가 아니라 코드에 대한 참조만 나른다.** 옛날 셸 실행이 IBL 어휘였다가 은퇴한 이유
= 코드 문자열이 IBL 파라미터 층을 통과하며 이스케이프·traceback 이 부서짐(디버깅 불가).
그래서 지금도:
- **저작·디버깅 = 도구층**: `[self:write]` + `run_command` (traceback 원문). 여기엔 `code:` 파라미터가 없다.
- **완성본 반복 실행 = 어휘층**: `[self:script]{op:"run", id}` — id 만 나른다.
- 실행은 argv 리스트(셸 미경유 — 인젝션·따옴표 지옥 원리적 차단), args 는 JSON stdin.

## op 4종

```
[self:script]{}                                                          ← list: 목록+마지막 실행 상태
[self:script]{op: "register", path: "data/scripts/정산.py", description: "월간 정산"}
[self:script]{op: "run", id: "정산", args: {"month": "2026-08"}}
[self:script]{op: "remove", id: "정산"}                                  ← 파일은 보존
```

- **register**: 실존 파일만, **`data/scripts/` 안에 있어야 한다**(밖이면 거절+안내).
  id 생략 시 파일명. interpreter 생략 시 확장자 추론(.py/.sh/.js).
  같은 id 재등록 = 갱신(수리 후 재등록이 유지보수 루프). timeout 기본 300초.
- **run**: **등록된 id 만** — 임의 경로·코드 문자열 실행 불가. cwd = 스크립트의 폴더.

### 왜 `data/scripts/` 인가 (2026-08-16 개정)

등록 스크립트는 **어휘처럼 다룬다** — 결정화 사다리에서 IBL 어휘 바로 아래 가로대이기 때문이다.

| | 파일 | 추적 |
|---|---|---|
| 본문 | `data/scripts/<파일>` | ✅ |
| 정의(파일·인터프리터·설명·타임아웃) | `data/scripts/registry.yaml` | ✅ |
| 실행 상태(last_run·last_error) | `data/scripts.json` | ✗ (무시) |
| 실행 로그 | `data/script_runs/<id>.log` (매 실행 덮어씀) | ✗ |

- 옛날엔 본문이 `outputs/` 아래라 **.gitignore 에 걸려 버전 관리 밖**이었다 — 백업도 없고 다른
  기기에 따라가지도 않았다. 어휘는 `ibl_nodes_src/*.yaml` 로 추적되는데 그 아래 칸만 방치돼 있었다.
- **정의와 상태를 가르는 이유**: 안 가르면 실행할 때마다 원장이 바뀌어 git 이 시끄럽다.
  어휘의 src ↔ 파생 분리와 같은 원리.
- **경로는 저장소 상대**로 적힌다(본문=파일명, 저장소 안 인터프리터=`.venv/bin/python3`).
  옛 절대경로(`/Users/…`)는 클론한 다른 기기에서 원리적으로 못 돌았다.

## 통화 계약 — 스크립트가 파이프에 흐르게 하려면

스크립트 stdout 이 `{"items": [...]}` 또는 `{"table": {columns, rows}}` JSON 이면 **통화로 승격**:

```
[self:script]{op: "run", id: "수집"} >> [table:sort]{by: "mb"} >> [table:take]{n: 5}
[self:script]{op: "run", id: "수집"} >> [self:sheet]{op: "append", path: "장부.xlsx"}
```

JSON 이 아니면 stdout 꼬리(8KB)가 그대로 담긴다. args 는 stdin 으로 온다:
```python
import sys, json
args = json.loads(sys.stdin.read() or "{}")
print(json.dumps({"items": [...]}, ensure_ascii=False))
```

## 스케줄에 거는 법 (라이브 실증됨)

스케줄러 태스크 `action: "run_pipeline"` + `action_params.pipeline` 에 IBL 한 줄:
```
POST /scheduler/tasks {"name": "월간 정산", "time": "09:00", "repeat": "monthly", "day": 1,
  "action": "run_pipeline", "action_params": {"pipeline": "[self:script]{op: \"run\", id: \"정산\"}"}}
```
앱 버튼(`app:` 블록 action 템플릿)·조종실 번역·워크플로우 step 도 같은 한 줄을 쓴다 — 전부 0토큰 결정론.

## 실패와 유지보수 (신고는 어휘층, 수리는 도구층)

run 실패 시 `success:false + exit_code + stderr_tail + log 경로`를 정직하게 반환하고 원장
last_error 에 기록한다(목록에서 🔴 표시). 고치는 절차: 로그 확인 → run_command 로 스크립트
디버깅(도구층) → 파일 수정 → 같은 id 그대로 (파일이 같으면 재등록도 불필요). 등록 파일이
사라지면 run 이 명시적으로 알린다.

## 함정

1. **환경 드리프트**: register 시점의 인터프리터 절대경로가 박힌다. 파이썬 업그레이드로 경로가
   바뀌면 run 이 "실행 불가"를 반환 — interpreter 지정해 재등록.
2. **어휘 신설 압력의 배출구**: "X 자동화 어휘 만들까?"의 기본 답은 이제 "스크립트 짜서 등록"
   이다. 새 액션은 [ibl.md] §4 기준(기존 어휘로 비싸거나 불가능 + 모양 안정)을 넘을 때만.
3. 긴 작업은 timeout 을 넉넉히 — 초과 시 프로세스가 중단된다(부분 실행 상태 주의).
