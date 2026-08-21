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
  id 생략 시 파일명. **interpreter 는 생략하는 게 정답**(아래 "어디서나 도는 원장").
  같은 id 재등록 = 갱신(수리 후 재등록이 유지보수 루프). timeout 기본 300초 —
  **재등록 시 생략하면 기존 값을 승계**한다(안 그러면 2400초짜리가 조용히 300으로 깎인다).
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

## 어디서나 도는 원장 — 인터프리터는 역할 이름만 (2026-08-22)

registry.yaml 은 **git 추적 대상**이라 3 OS 로 그대로 클론된다. 여기에 인터프리터 *경로*를
적으면 원리적으로 부서진다 — 맥의 `.venv/bin/python3` 은 윈도우에선 `.venv\Scripts\python.exe`,
`python3.13` 은 다음 업그레이드에 없고, `/opt/homebrew/...` 는 이 기기에만 있다.

**인터프리터는 '몸의 명사'다** — "지금 무슨 파이썬으로 도는가"는 그 몸의 런타임만 아는 사실이지
원장에 적어 다른 몸에 부칠 데이터가 아니다("명사의 자리" 헌법). 그래서:

| 층 | 값 |
|---|---|
| 원장(registry.yaml) | **역할 이름**만 — `python` · `bash` · `node` |
| 런타임(`_resolve_interpreter`) | 파이썬=`sys.executable`(그 몸 자신) · 그 외=PATH 조회 |

- register 에서 interpreter 를 **생략하면** 확장자로 역할이 정해진다. 이게 기본 사용법이다.
- 경로를 명시하면 존중하되 **경고**를 함께 낸다. 그리고 `scripts/check_win_portability.py`
  (pre-commit + CI portability.yml)가 커밋을 거절한다 — 추적 원장에 경로가 들어가는 길을 막는다.
- **자가치유**: 다른 기기·옛 형식에서 온 원장에 경로가 박혀 있고 이 몸에 그 경로가 없으면,
  런타임이 파일명에서 역할을 되살려 실행하고 `interpreter_note` 로 그 사실을 알린다
  (윈도우식 `C:\Python\python.exe` 도 두 구분자 모두로 잘라 해소한다). 마이그레이션 없이 돈다.
- 특정 파이썬이 꼭 필요하면 인터프리터를 박지 말고 **스크립트 본문이 스스로 처리**하게 한다.

### 함께 고친 OS 가정 — `os.kill(pid, 0)`
유닉스에선 "살아 있나?"라는 무해한 질문이지만 **윈도우에선 `TerminateProcess`** 다. 즉 상태를
물을 때마다 그 프로세스가 죽는다(exit code 0 이라 정상 종료처럼 보이기까지 한다). 이 저장소에
세 곳 잠복해 있었다: 이 러너, 강의 렌더(`deck_video`), **RED 자기수정 워치독**(죽여놓고 "생존"
으로 판정해 자동 롤백 안전판이 조용히 사라진다 — 셋 중 최악).

- 판정 단일 소스 = `common.platform_utils.pid_alive` (psutil → 윈도우 `OpenProcess`+
  `GetExitCodeProcess` → 유닉스 `os.kill` 순). 러너 분리도 같은 모듈의 `spawn_detached`.
- 재발 방지: `check_win_portability.py` 가 `os.kill(pid, 0)` 을 AST 로 잡아 커밋을 거절한다
  (platform_utils 만 예외).

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

1. ~~환경 드리프트~~ (2026-08-22 해소 — 아래 "어디서나 도는 원장" 참조). interpreter 를
   손으로 박으면 여전히 그 몸 전용 원장이 되고, CI 가 거절한다.
2. **어휘 신설 압력의 배출구**: "X 자동화 어휘 만들까?"의 기본 답은 이제 "스크립트 짜서 등록"
   이다. 새 액션은 [ibl.md] §4 기준(기존 어휘로 비싸거나 불가능 + 모양 안정)을 넘을 때만.
3. 긴 작업은 timeout 을 넉넉히 — 초과 시 프로세스가 중단된다(부분 실행 상태 주의).


## 긴 작업 — background + status (2026-08-21)
타임아웃(기본 300초)을 넘길 스크립트(나레이션 생성·렌더·대량 수집)는 **동기로 부르지 말 것**. 동기 호출이 타임아웃으로 죽으면 결과도 잃고, 그 뒤 셸 `sleep`/`ps` 폴링 한 번이 모델 왕복 한 번이다.
```
[self:script]{op: "run", id: "나레이션생성", args: {lecture_id: "x"}, background: true}   # → job_id 즉시
[self:script]{op: "status", job_id: "나레이션생성-20260821_233000", wait: 120}          # 끝날 때까지 ≤120초 유한 대기, done 이면 result
[self:script]{op: "status", id: "나레이션생성"}                                           # 그 스크립트의 최근 작업들
```
- 러너는 별도 프로세스(`_bg_runner.py`)라 백엔드 리로드·워커 교체에 살아남는다. `running` 인데 러너 pid 가 죽었으면 `lost` 로 정직 표시.
- 상태 파일 `data/script_runs/jobs/<job_id>.json`, 로그 `data/script_runs/<job_id>.log`.
- wait 상한 240초(초과 요청은 신고 후 상한). 더 긴 작업은 status 를 다시 부르거나 트리거에 맡긴다.
