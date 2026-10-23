# NetHack 실험의 실행 경계

2026-10-24 에피소드 5453·5454에서 확인한 반복 조회·맹목적 행동 묶음·종료 관측 소실을
수리했다. 게임 규칙은 `data/scripts/nethack_runtime.py`에 있고 IBL 문법에 넣지 않는다.
서버와 클라이언트도 같은 추적 폴더에 둔다. 개인 실행 기록·설치 환경은 `projects/`에 남긴다.

## 실행

BALROG와 Python 환경이 이미 설치된 실험 폴더에서:

```sh
.venv310/bin/python ../../../data/scripts/nethack_server.py --workspace . --seed 1 --run pilot_new --port 8797
```

기존 `projects/study/nethack/server.py` 진입점과 `outputs/nethack_play/` 보조 도구는
추적 모듈로 연결했다. 이전 본문은 `data/_backups/2026-10-24_nethack_episode_repair/`에
보존한다. 기존 실험의 행동 원장과 결과는 바꾸지 않는다. 실행 폴더를 재사용하면 거절하며,
포트 충돌은 게임 초기화 전에 실패한다. 8765는 IndieBiz 백엔드 포트다.

```sh
python3 nh.py --fresh --inv
python3 nh.py east east east
python3 nh.py --inv
python3 nh.py --input-sequence zap p down
```

- 행동 응답에는 `status.revision`, `state`, `stop_reason`, `remaining`이 있다.
  기본 중단 조건은 피격·질문·막힘·상태변화다. 미실행 행동은 자동 재전송하지 않는다.
- `--input-sequence`는 알고 있는 질문/답변 연속 입력에서만 쓴다. 피격·막힘·상태변화 중단은 유지한다.
- 무행동 `nh.py`는 마지막 응답을 재사용하며 캐시와 판본을 표시한다. 외부 조작 뒤 `--fresh`로 조회한다.
  행동은 관측 판본을 조건으로 보내고, 다른 호출이 먼저 상태를 바꿨으면 실행하지 않고 새 관측을 반환한다.
- `look`은 게임 행동이다. 실명 중에는 기본 거절하고 `observe`를 쓴다.
- 마지막 기도 턴을 반환한다. 300턴 안의 재기도는 보수적으로 멈추며, 이는 기도 성공을
  보장하는 규칙이 아니다. 상황을 판단해 `--allow-risk`로 명시적으로 재시도할 수 있다.
- 같은 위치·주변 상태에서 확정적으로 막힌 명령은 반복하지 않는다. 상태가 달라지거나
  위험 재시도를 명시하면 허용한다. 잘못된 행동을 Esc로 바꿔 게임에 전송하지 않는다.
- `rest.py`·`watchrest.py`·`elbrest.py`·`atk.py`는 매 행동의 응답으로 중단을 판단한다.
  기존 chunk 인자는 총 반복 상한에만 쓰며, 묶음을 끝낸 뒤 위험을 확인하지 않는다.
  각인이 없어지면 자동으로 도구 문자와 입력 상태를 추측하지 않고 실행자에게 반환한다.
- `final.json.last_live`는 마지막 생존 관측·진행도이며 종료 뒤 0으로 초기화된 상태와 구분된다.

## 공통 계약 수리

- 독립 실행자의 `/projects/{owner}/agents/-/tasks/{id}` 접수증은 저장된 worker 세션과
  일치할 때 조회한다. `-`는 일반 에이전트 작업에 대한 와일드카드가 아니다.
- 아직 등록되지 않은 ID의 첫 호출과 관리 작업은 호출 시점의 자산 지문을 영수증에 넣는다.
  검사 때 이미 등록된 고정 ID는 이전처럼 정의 변경을 거절한다. 실행 시점 지문도 재사용
  식별자에 포함하여 다른 구현의 결과를 빌리지 않는다. 상세는 `data/guides/script.md`.

## 검증과 한계

최종 backend 전수(`-n auto --dist loadfile`, system 포함)는 11,725 passed,
14 skipped(297.68초)였다. 수정된 경계·소비자 묶음도 180 passed였으며,
구문·1500줄 제한과 층 검사, Android 몸 번들 재생성을 확인했다.

회귀는 `backend/test_nethack_runtime.py`, `backend/test_ibl_dependencies.py`,
`backend/test_delegation_tasks.py`에 있다. 실제 BALROG 초기화·읽기·행동·캐시 확인도
새 격리 실행에서 통과했다. 증거는
`projects/study/nethack/runs/repair_smoke_49d111b2eb/smoke_result.json`이다.
seed 1에서 HP 15를 유지하며 1턴→2턴, 실제 행동은 search 한 번이었다.
추가 관찰은 HTTP 없이 캐시를 재사용했고 잘못된 행동과 오래된 판본의 행동은 실행되지 않았다.
공개 `[self:script]` 등록→실행도 실제 Python 자식 실행기로 확인했다.
API 모델을 쓰는 새 게임 전체 재실행은 하지 않는다.
따라서 생존율·완료 시간·전체 토큰의 개선 수치는 아직 측정하지 않았다.
기존 시드 0의 층 반복 현상과 대조군 부재는 이 수리로 해소됐다고 주장하지 않는다.
