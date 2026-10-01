# 파일 Script 실행과 등록 — [self:script]

> 2026-08-07 신설. **결정화 사다리의 가운데 가로대** — 자율주행이 write+run_command 로 만들어
> 검증까지 끝낸 스크립트를 "몸의 일부"로 승격시키는 관문. 이게 없던 시절엔 완성 스크립트가
> /tmp 고아가 되거나, 트리거가 자연어 위임([others:delegate])으로 매번 본격 모델을 깨워야 했다.

## 설계선 — 파일 실행과 IBL 연결 (2026-10-01 개정)

**실행은 파일을 기준으로 하고, IBL은 입력과 결과를 연결한다.** 코드 문자열을 실행기에
끼워 넣어 traceback을 재작성하지 않는다. Python 실행부(`backend/base/file_script.py`)는
IBL 파서·값·오류 객체에 의존하지 않는다. IBL 어댑터와 재현 CLI가 같은 실행부를 쓴다.

- 저작: `execute_ibl.inputs`의 Text를 `self:write.content`에 전달한다. 따옴표·역슬래시·탭·한글을
  IBL 코드 안에 다시 이스케이프할 필요가 없다. 삼중 따옴표는 기존 문자열 이스케이프를
  해석하므로 raw 코드 통로가 아니다. 코드 저작·수정은 inputs를 기본으로 쓴다.
- 수정: **기존 `self:edit`**의 `old_string/new_string` 또는 줄 범위를 사용한다. 수정 문자열도
  inputs로 전달한다. 전체 파일 재전송이나 셸 heredoc은 필요하지 않다.
- 실행: 등록 `id` 또는 **현재 턴의 `~turn/*.py` 경로** 중 하나를 참조한다. 임시 실행은 등록 원장을
  바꾸지 않는다. Python은 현재 몸의 인터프리터로 argv 실행하며 셸을 거치지 않는다.

## 미등록 Python 파일을 조합하기

다음 프로그램의 `inputs`에 `본문`(Python Text)과 `자료`(Record)를 넣는다.

```ibl
#!ibl edition=2
$f=[self:write]{path:"~turn/분석.py",content:$본문}
$r=[self:script]{path:$f.path,args:$자료}
return $r.items >> [table:filter]{where:($행)=>$행.n>2}
```

Python 본문 예시:

```python
import json, os, sys
from pathlib import Path
args = json.load(sys.stdin)
print("분석 중")  # stdout과 stderr는 모두 진단용
result = {"items": args["items"]}
path = Path(os.environ["INDIEBIZ_SCRIPT_RESULT"])
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
tmp.replace(path)
```

`args`는 JSON 객체 하나다. 결과 파일에는 JSON 값 하나를 쓴다. `null`도 값이다.
**종료 코드 0 + 결과 파일 없음은 `RESULT_MISSING`**, 잘못된 JSON은 `RESULT_INVALID`다.
stdout으로 되돌아가 값을 찾지 않는다. 종료 코드 비0·시간 초과는 실패이며 결과를 이미 썼다면
부분 값으로 보존한다. 오류 원문은 stderr 파일, 표시되는 꼬리는 비밀값 마스킹을 거친다.

권한은 이미 임의 로컬 코드 실행을 허용받은 **제한 없는 주인 실행 문맥**이다. 회원·이웃·포털·
노드가 제한된 에이전트는 거절한다. 리허설 출처 표시는 기존 Script의 자식 환경을 승계한다.
폴더 제한은 코드의 소속을 정할 뿐 **Python의 파일·네트워크 접근을 가두지 않는다**.
로컬 동기 실행만 지원하며 `timeout` 기본 300초, 최대 3600초다. `id`, `args_file`,
`interpreter`, `target`, `callable_contract`, `background:true`를 함께 주지 않는다.
코드 묶음은 작업 폴더의 Python 파일들(총 8MiB 이하), 결과는 32MiB 이하이며 코드 링크는 거절한다.
비-Python 자료는 원래 작업 디렉터리에서 읽는다. 외부 자료·환경까지 동결하는 재현은 아니다.

### 실패 → 부분 수정 → 새 시도

```ibl
#!ibl edition=2
[self:edit]{path:"~turn/분석.py",old_string:$수정전,new_string:$수정후}
$r=[self:script]{path:"~turn/분석.py",args:$확정입력}
return $r.items
```

`수정전/수정후`는 inputs Text다. 앞 실행의 확정 값은 반환된
`result_ref.completed_calls`의 `input_args` 또는 기존 `$ref`로 `확정입력`에 연결한다.
단일 프로그램 후반 실패의 순수 계산값도 `result_ref.failed_calls[].input_args`로 회수할 수 있다.
회수한 `$입력`은 도구 인자 Record이므로 `args:$입력.args`로 연결한다. 생략된 완료 호출 목록은
`result_ref.calls_read_args`로 읽는다. 비밀값 마스킹·원천 불완전성과 기존 참조 권한은 유지된다.
읽기 재사용은 기존 `reuse:{run_id}` 규칙을 따른다. Script 효과는 **unknown**이며 자동 결과
재사용·자동 재시도 대상이 아니다. 실패에도 외부 효과가 남았을 수 있으므로 수정 후 실행은
**새 시도**다. 같은 코드·입력의 `resume`은 확인된 성공/실패 영수증만 복원한다. 코드/환경 변경은
`RESUME_DIVERGED`로 거절하며 `details.changed`에 `invocation_dependency.source_hashes`(코드),
`environment_metadata_fingerprint`(환경), `interpreter` 등의 변경 지문을 표시한다. 미완료 영수증은 `EFFECT_UNCERTAIN`으로 막고 Python을 다시 돌리지 않는다.

실제 작업 문맥의 `~turn`은 그 작업의 도구 호출 사이에 유지된다. 작업 ID가 없는 독립 API 호출은
요청마다 다른 폴더를 받으며 같은 요청의 resume은 원래 폴더를 쓴다. 코드 사본·stdin 원문·
stdout/stderr·결과·실행 메타는 `data/script_runs/transient/`의 비공개 실행 폴더에 남는다.
파일 지문과 실행 증거 경로는 IBL 증거에 연결된다. **7일 보존 후 정기 정리**하며 작업 파일도
마지막 실행/작성 후 7일 지나면 정리한다. 실행 중 잠금이 있으면 건드리지 않는다.

기록 폴더는 일반 파일 읽기로 조사한다. 명시 재현은 저장소에서 다음처럼 실행한다.

```bash
.venv/bin/python backend/file_script_cli.py <실행 증거의 record 경로>
```

CLI는 코드·stdin 지문, 보존 기간을 확인한 뒤 동일 인터프리터·cwd·결과 통로로 **새 시도**를 만든다.
진행 중·중단되어 효과가 불명인 기록은 재현하지 않는다. 만료/삭제된 원문을 마스킹본으로 대체하지
않는다. 결과 JSON만 수리해 조사할 때는 저장된 파일을 읽으며 계산을 자동 재실행하지 않는다.
정기 승격 검토는 보존 중의 코드·입력·오류 증거를 이용할 수 있고, 검증된 코드를 나중에 등록하는
것은 허용한다. 승격 자체를 자동 실행하지 않는다.

## 몸의 되풀이 명령은 등록돼 있다 (2026-09-05)
관문 배터리·시험 실행처럼 매 수리 주행이 같은 명령을 치는 일은 이미 등록 스크립트다 — 셸로 다시 치지 말고 `[self:script]{op: "list"}` 로 id 를 보고 `run` 한다. 고치기 뒤 검증이 같은 프로그램에 든다: `$r=[self:script]{id:"<시험 스크립트>",args:{files:["<시험 파일>"]}}; $r.items >> [table:select]{columns:["file","passed","failed","failures"]}`. 결과 객체의 items 목록을 명시적으로 선택한 뒤 표 연산에 전달한다.

**검증의 범위는 바뀐 곳이다.** 수리·개발 주행의 시험은 고친 모듈의 시험 파일만 준다 — 전수(수천 건·수 분)는 커밋 관문과 CI 의 몫이고, 시험 스크립트는 전수를 전경으로 받지 않는다. 오래 걸리는 스크립트는 전경으로 붙들지 말고 핸들로 받는다: `[self:script]{op: "run", id: "<id>", background: true}` ⏎ `[self:script]{op: "status", job_id: "<받은 job_id>", wait: 240}` — 끝날 때까지 한 호출로 기다리고(진행 줄이 함께 온다), 프로세스 목록·로그 파일을 뒤지는 폴링은 하지 않는다.

## op 5종

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
- **run**: 등록 `id` 또는 위의 임시 `path` 중 하나. 아래 stdin 두 통로는 **등록 id 실행**의 계약이다. cwd = 스크립트의 폴더.
  stdin payload 는 두 통로 중 **하나**다 — 작은 리터럴은 `args`,
  큰 payload(원장 배치 등)는 **`args_file`(그 JSON 객체가 담긴 파일 경로)**.
  둘을 함께 주면 거절한다(stdin 은 하나다).

### 왜 `data/scripts/` 인가 (2026-08-16 개정)

등록 스크립트는 **어휘처럼 다룬다** — 결정화 사다리에서 IBL 어휘 바로 아래 가로대이기 때문이다.

| | 파일 | 추적 |
|---|---|---|
| 본문 | `data/scripts/<파일>` | ✅ |
| 정의(파일·인터프리터·설명·타임아웃) | `data/scripts/registry.yaml` | ✅ |
| 실행 상태(last_run·last_error) | `data/scripts.json` | ✗ (무시) |
| 실행 로그 | `data/script_runs/<id>-<실행 UUID>.log` (실행별 보존) | ✗ |

- 옛날엔 본문이 `outputs/` 아래라 **.gitignore 에 걸려 버전 관리 밖**이었다 — 백업도 없고 다른
  기기에 따라가지도 않았다. 어휘는 `ibl_nodes_src/*.yaml` 로 추적되는데 그 아래 칸만 방치돼 있었다.
- **정의와 상태를 가르는 이유**: 안 가르면 실행할 때마다 원장이 바뀌어 git 이 시끄럽다.
  어휘의 src ↔ 파생 분리와 같은 원리.
- **경로는 저장소 상대**로 적힌다(본문=파일명, 저장소 안 인터프리터=`.venv/bin/python3`).
  옛 절대경로(`/Users/…`)는 클론한 다른 기기에서 원리적으로 못 돌았다.

## 등록 id의 값 반환 계약

현재 IBL에서는 기존 스크립트도 직접 호출한다. 기존 스크립트의 JSON stdin 형식은 그대로다.
JSON stdout은 객체·목록·스칼라 전체가 값이고, 평문 stdout은 완전한 문자열이다.
실행 결과는 `value`에 담긴다. `.items` 자동 추출이나 문자열 JSON 봉투를 가정하지 않는다.

```ibl
#!ibl edition=2
$r=[self:script]{id:"수집",args:{}}
$r.items >> [table:sort]{by:"mb",descending:true} >> [table:take]{n:5}
```

위 `수집`은 등록 id 예시다. 실제 id는 list로 확인한다. 종료 코드가 0이어도 JSON의
`success:false` 또는 `error`는 실행 실패다. 부분 원천 표지도 경계에서 전파한다.
새 명시 타입 프로토콜(`callable_contract`의 `ibl-script/2`)은 opt-in이며 기존 스크립트의
본문·등록을 이 프로토콜로 바꾸지 않아도 현재 IBL에서 호출할 수 있다.
list/register/remove/status는 관리 결과 Record를 반환한다. 기존 등록의 background 실행은
job_id 영수증을 반환한다. 새 wire 스크립트의 background는 아직 지원하지 않으며 실행 전에 거절한다.
list의 등록 목록과 status의 작업 목록은 `.items`로 꺼내 table에 전달한다.
status의 `.items`는 완료 뒤에도 작업 행이며 스크립트 업무 값은 `.result` 또는 `.items[0].result`다.
목록·상태는 수정 실행에서도 새로 관측한다.

```python
import sys, json
args = json.loads(sys.stdin.read() or "{}")
print(json.dumps({"items": [{"value": args.get("value")}]}))
```

## 큰 payload — 나르지 말고 가리킨다 (`args_file`, 2026-09-01)

수십 행짜리 원장 갱신을 `args` 리터럴로 쓰면 IBL 문장 안에 킬로바이트가 박힌다.
그 마찰이 이틀 연속 셸 stdin 우회를 낳았고(등록 통로 밖 실행 = 실행 이력·상태·해마가
굶는다), 그래서 **payload 를 파일로 두고 경로만 넘기는 통로**가 생겼다.
계약은 `args` 와 같다 — **JSON 객체 하나**(배열·스칼라는 거절). 상대경로는 저장소 루트 기준.

```
[self:write]{path: "<payload 경로>", content: "<{op, path, items…} JSON>"}
[self:script]{op: "run", id: "<등록 id>", args_file: "<payload 경로>"}
```

결과에 `args_file`·`args_bytes` 가 실린다 — 가리키는 값은 호출 밖에서 바뀌므로
**무엇으로 돌았는지**를 결과만 보고 알 수 있어야 한다.

## 결과를 다음 스크립트에 전달하기

`$r=[self:script]{id:"수집",args:{}}; [self:script]{id:"검증",args:{op:"accept",data:$r}}`처럼
값을 명시적으로 넣는다. 파이프를 쓰면 전체 args 객체가 전달된다:
`{op:"accept",data:$r} >> [self:script]{id:"검증"}`.
IBL의 부분 실패는 실행 증거로 보존한다. 일반 데이터에 근거 없는 success 표지를 새로 붙이지 않는다.
기존 저장 프로그램의 input_as·자동 봉투 추출은 docs/compatibility/ibl_legacy_script.md에 기록돼 있다.

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


## 등록 id의 긴 작업 — background + status (2026-08-21)
타임아웃(기본 300초)을 넘길 스크립트(나레이션 생성·렌더·대량 수집)는 **동기로 부르지 말 것**. 동기 호출이 타임아웃으로 죽으면 결과도 잃고, 그 뒤 셸 `sleep`/`ps` 폴링 한 번이 모델 왕복 한 번이다.
```
[self:script]{op: "run", id: "나레이션생성", args: {lecture_id: "x"}, background: true}   # → job_id 즉시
[self:script]{op: "status", job_id: "나레이션생성-20260821_233000", wait: 120}          # 끝날 때까지 ≤120초 유한 대기, done 이면 result
[self:script]{op: "status", id: "나레이션생성"}                                           # 그 스크립트의 최근 작업들
```
- 러너는 별도 프로세스(`_bg_runner.py`)라 백엔드 리로드·워커 교체에 살아남는다. `running` 인데 러너 pid 가 죽었으면 `lost` 로 정직 표시.
- 상태 파일 `data/script_runs/jobs/<job_id>.json`, 로그 `data/script_runs/<job_id>.log`.
- **진행 가시성**: 러너가 스크립트의 **stderr 를 로그에 실시간**으로 흘리고, `status`의 모든 작업
  행에 `progress`(마지막 줄들, 관측한 줄이 없으면 빈 목록)를 싣는다. 완료 뒤에도 보존하며
  stdout 결과는 진행 줄에 섞지 않는다. 긴 스크립트는 진행을 stderr 에 쓰면 된다(stdout 은 통화 자리).
  실사고: 55분짜리 나레이션 생성이 26라운드 내내 'running' 만 돌려줬다 — 로그가 끝난 뒤에야 생겼기 때문.
- wait 상한 240초(초과 요청은 신고 후 상한). 더 긴 작업은 status 를 다시 부르거나 트리거에 맡긴다.


## 입출력 타입을 선언하는 스크립트 계약 (선택)

Python·Bash·Node 인터프리터는 그대로 지원한다. 기존 등록의 stdin/stdout는 변경하지 않는다.
기존 등록은 계약을 새로 붙이지 않아도 현재 IBL에서 직접 호출한다.
입출력 타입까지 검사할 스크립트는 등록 시 아래 `callable_contract`와 전용 입출력 봉투를 함께 구현한다.

```yaml
callable_contract:
  version: 1
  params: {x: Number}
  result: Record
  effects: [pure]
  adapter: {protocol: ibl-script/2}
```

stdin은 `{protocol:"ibl-script/2", args:{x:3}, context:{edition:2}}`다.
stdout은 `{protocol:"ibl-script/2", ok:true, value:{n:6}}` 또는
`{protocol:"ibl-script/2", ok:false, error:"사유"}`다. `value.error`는 평범한 업무 데이터다.
입력 이름·반환 타입·JSON·종료 코드를 검사한다. 일반 args 문자열의 몸 경로 별칭은 확장하지 않는다.
새 계약과 기존 호출의 판본이 다르면 실행 전에 거절한다. 현재 새 프로토콜은 로컬·회원 PC·인증된 원격 기기의 동기 실행을 지원한다.
원격은 capabilities의 ibl-script-call/1, 회원 PC는 도우미의 ibl-script/2를 확인한 뒤 실행한다.
새 wire의 background·회원 args_file·직접 연결 불가 기기의 푸시 큐 전송은 지원하지 않는다.
원격 응답이 끊기면 결과 불명으로 남기며 같은 실행을 자동 재전송하지 않는다. 등록 계약을 모르는 script는 순수 캐시 대상으로 간주하지 않는다.
자세한 언어 계약은 [주 IBL 교재](ibl_composition.md)를 읽는다.


## 실행 안에서 객체를 이어 쓰는 등록 스크립트

`python_libraries`는 설치 라이브러리의 함수·생성자·메서드·속성을 이름으로 호출하는 등록 ID다.
`[self:script]{id:"python_libraries",args:{op:"call",target:"statistics:mean",args:[[2,4,6]]}}`
처럼 사용한다. 객체를 이용한 조합과 export는 [호출 가이드](python_libraries.md)를 따른다.
새 어휘나 함수별 등록은 필요 없다. 목록의 callable_contract로 등록 입력 계약을 확인한다.

등록의 `callable_contract.adapter.protocol: ibl-script-session/1`은 같은 최상위 IBL 실행에서
동일 ID의 자식 프로세스를 유지하는 선택적 계약이다. args는 IBL 값 wire로 전달하며 참조 수명은
해당 실행으로 제한한다. 효과는 unknown, adapter.stateful/local_code는 true여야 한다.
Python 역할 인터프리터와 data/scripts 안의 실존 진입 파일을 요구한다. 현재는 제한 없는 주인의
로컬 동기 실행만 허용하며 background·args_file·원격 전달을 거절한다. 일반 등록 Script의
기존 JSON/ibl-script/2 계약과 영수증 재생은 바꾸지 않는다. 세션 상태의 영수증 재생은 거절한다.

세션 stdin 첫 줄은 protocol/owner/generation 초기화이며 준비 응답에는 protocol/ready/environment가
필요하다. 이후 각 줄은 invocation id와 pack된 params, 응답은 ok와 pack된 value 또는 error/partial이다.
실행 종료에 프로세스를 정리한다. 이 계약을 구현하지 않은 일반 스크립트에 세션 선언만 붙이면 안 된다.
