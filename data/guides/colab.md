# Google Colab CLI 가이드 (클라우드 GPU/TPU 실행)

구글 공식 `colab` CLI(2026-06 출시)로 터미널에서 콜랩 VM(GPU/TPU)을 빌려 파이썬을 실행한다.
로컬 맥으로 벅찬 연산(대형 모델 추론·학습, CUDA 필수 작업, 대용량 데이터 처리)을 클라우드로 넘기는 손.
IBL에서는 `run_command`(셸)로 부르고, 자주 쓰는 잡은 `[self:script]`에 등록한다 — 전용 액션 없음(의도적).

- 설치 위치: `~/.local/bin/colab` (v0.6.0 실측, `colab update`로 갱신 확인)
- 인증: **oauth2 로그인 완료**(등록된 구글 계정, 토큰 `~/.config/colab-cli/token.json` 자동 갱신)
- 상태 확인: `colab whoami`(계정·스코프·만료), `colab sessions`(활성 세션 = 인증 겸 확인)
- 자가 문서: `colab skill`(에이전트용 정본 문서), `colab readme`, `colab help <명령>`

## 0. 언제 콜랩인가 (판단 기준)

| 상황 | 도구 |
|------|------|
| 해마 임베딩 재학습 (정기) | 기존 Modal 파이프라인 (`cloud_training/` make_bundle→modal_train) — 정본 유지 |
| 일회성 GPU 실험·프로토타입 | **콜랩** (`colab run --gpu T4`) |
| CUDA 필수 라이브러리 검증 | **콜랩** |
| 긴 학습(수십 분~시간) + 중간 상태 확인 | **콜랩** 세션 방식 (`new` → `exec` 반복 → `stop`) |
| 로컬로 충분한 작업 (M4 Pro) | 로컬 — 콜랩 쓰지 말 것 (왕복·과금 낭비) |
| **내 목소리 나레이션** (강의 영상용) | **콜랩** — 등록 스크립트 `나레이션생성` (→ `voice_narration.md`) |

**과금**: GPU/TPU는 컴퓨트 유닛을 소모한다. 세션을 안 끄면 최대 24시간 계속 소모 — 작업 끝나면 **반드시 `colab stop`**. `colab run`은 자동 정리라 안전 기본값.

## 1. 핵심 정신 모델

- **세션 = 빌린 VM 위의 살아있는 Jupyter 커널.** `colab new`가 과금 시작, `colab stop`이 반납.
- **커널 상태는 `exec` 호출 사이에 유지된다** — 같은 세션이면 import·변수·함수가 살아 있다. 매번 재임포트하지 말고 상태를 쌓아갈 것. 리셋은 `stop` 또는 `restart-kernel`뿐.
- **기본 작업 디렉토리 = `/content`.** 파일 작업은 절대경로 `/content/...` 권장.
- CLI는 fire-and-forget: 명령마다 인증→한 가지 일→종료. keep-alive는 백그라운드 데몬이 자동 처리.

## 2. 일회성 잡 (기본 패턴): `colab run`

```bash
# CPU
colab run script.py arg1 arg2
# GPU (T4가 무난한 기본값 — 쿼터 문제 최소)
colab run --gpu T4 --timeout 3600 train.py
```

- `new`+`exec`+`stop`을 한 명령으로. 스크립트가 죽어도 VM은 자동 반납.
- `sys.argv`·`__name__=="__main__"` 이 로컬 `python script.py`와 동일하게 설정됨.
- **exit code 전파**: 스크립트의 예외/`sys.exit(N)`이 `colab run`의 종료 코드가 됨 — 파이프라인 판정에 그대로 쓸 것.
- **스트림 분리**: 스크립트 stdout만 stdout으로, `[colab]` 채터는 stderr로 → `colab run job.py > out.txt` 하면 깨끗한 산출만 저장.
- **★산출 파일은 자동 회수되지 않는다** (보도 기사에 "retrieve output files"라 나오지만 v0.6.0 실측 플래그 없음). 파일 산출이 있으면:
  ```bash
  colab run --keep -s myjob --gpu T4 --timeout 3600 train.py   # VM 유지
  colab download -s myjob /content/model.bin ./model.bin        # 회수
  colab stop -s myjob                                           # 반드시 반납
  ```

## 3. 세션 방식 (상태 쌓는 작업)

```bash
colab new -s work --gpu T4          # 항상 -s 이름 지정 (생략하면 랜덤 6-hex라 나중에 헷갈림)
colab install -s work torch pandas  # uv pip 기반 패키지 설치 (-r requirements.txt 도 됨)
colab upload -s work data.csv /content/data.csv
colab exec -s work -f step1.py --timeout 600
echo "print(len(df))" | colab exec -s work      # 파이프 실행 (커널 상태 이어짐)
colab download -s work /content/result.json ./result.json
colab stop -s work                  # ★반납
```

- 로컬 스크립트는 `-f`로 넘기면 업로드 없이 커널로 전송된다.
- 노트북: `colab exec -s work -f nb.ipynb` → 셀별 실행 후 `nb_output.ipynb` 생성.
- 그림(PNG/JPEG): `--output-image <경로>`로 저장 위치 고정.
- 셸 명령: `echo "nvidia-smi" | colab console -s work` (tmux 래핑이라 제어문자 섞임 — `grep -a`로 거를 것). 진짜 셸이 필요 없으면 `exec`가 빠름.

## 4. 함정 (전부 실측 또는 공식 skill 문서 기준)

1. **★기본 타임아웃 30초** — `run`·`exec` 둘 다 `--timeout` 기본값이 30.0초. GPU 잡은 반드시 `--timeout 3600` 같이 크게 줄 것. 안 주면 학습이 30초에 잘린다.
2. **★도구 60초 제한과의 관계** — IBL `run_command`로 긴 콜랩 잡을 돌리면 에이전트 도구 타임아웃(60s)에 걸린다. 긴 잡은 백그라운드 패턴으로:
   ```bash
   nohup colab run --gpu T4 --timeout 7200 train.py > /tmp/colab_job.log 2>&1 &
   ```
   이후 로그 파일을 읽어 진행 확인 (family-news 백그라운드+상태파일 선례와 같은 부류).
3. **미인식 `--gpu` 값은 조용히 A100 폴백** → 대개 다음 단계에서 실패. `colab new` 400 = 그 가속기 쿼터/자격 없음 → `--gpu T4`나 CPU로 폴백. 가속기 가용성은 계정 티어에 달려 있으니 GPU 할당을 전제하지 말 것.
4. **`repl`·`console`·`auth`·`drivemount`를 에이전트가 대화형으로 실행 금지** — TTY를 기다리며 행(hang)한다. `repl`/`console`은 파이프 stdin은 허용(EOF에 종료), `auth`/`drivemount`는 사람이 터미널에 있어야 함.
5. **`colab auth` ≠ CLI 인증** — `colab auth`는 VM 안에 GCP 자격을 넣는 것(BigQuery/GCS용). CLI 401/403은 스코프 문제 → `colab whoami`로 확인. 403의 대부분은 `colaboratory` 스코프 누락.
6. **병렬/동시 실행은 `--config` 분리** — 세션 상태 파일(`~/.config/colab-cli/sessions.json`)을 공유하면 얽힌다: `colab --config /tmp/jobA.json new -s a`.
7. `--auth` 같은 전역 플래그는 **서브커맨드 앞에** 와야 함: `colab --auth=adc new -s x`.
8. 존재하지 않는 스크립트 경로는 VM 할당 **전에** 실패(과금 낭비 없음).
9. **★의존성 핀 — `jupyter-kernel-client<1.0`** (2026-08-15 실측): CLI 가 이 패키지를 **버전 고정 없이**
   요구하는데 1.x 에서 `KernelClient` → `JupyterKernelClient` 로 개명돼 **모든 `exec` 이 `AttributeError`
   로 죽는다.** `colab update`·재설치 때마다 재발한다. 처방:
   ```bash
   uv pip install --python ~/.local/share/uv/tools/google-colab-cli/bin/python 'jupyter-kernel-client<1.0'
   ```
10. **★`colab upload` 의 상대경로는 루트(`/`) 기준** (실측): `colab upload x.wav x.wav` 하면
    `/content/x.wav` 가 아니라 **`/x.wav`** 에 떨어진다. 업로드가 성공했다는데 `/content` 에서 안 보이면
    이것이다. 목적지는 항상 절대경로로: `colab upload -s s x.wav /content/work/x.wav`.
11. **★T4 의 거짓 bf16 보고** (GPU 잡 일반): `torch.cuda.is_bf16_supported()` 가 T4(sm_75)에서
    True 를 반환하지만 네이티브 bf16 이 없다(에뮬레이션). **에러 없이 느려지기만** 해서 가장 알아채기
    어렵다. `torch.cuda.get_device_capability()` 로 아키텍처를 직접 볼 것 — sm_80(Ampere) 이상만 진짜 bf16.
    공식 예제를 그대로 복사하면 대개 `dtype=torch.bfloat16` 이라 여기 걸린다.

## 5. 진단·회복

| 증상 | 처방 |
|------|------|
| "Session not found" / 404 | 백엔드가 VM 회수함. `colab sessions`로 확인 후 `colab new` 재생성 (로컬 상태는 자동 정리됨) |
| 커널 먹통 / 실행 타임아웃 | `colab restart-kernel -s <이름>` (VM 유지, 커널만 리셋) |
| keep-alive 죽음 (`log`에 `consecutive_4xx_errors`) | `colaboratory` 스코프 누락 — `colab whoami`로 확인 후 재인증 |
| 실패 원인 불명 | `colab log -s <이름> -n 20` (구조화 이벤트, 원시 response_body 포함) |
| 작업 기록 보고서 | `colab log -s <이름> -o summary.ipynb` (`.md`/`.jsonl`도 확장자로 선택) |
| 브라우저로 이어보기 | `colab url -s <이름> --open` (새 VM 할당 없이 웹 UI가 기존 세션에 붙음) |

## 6. 어휘화 방침 (indiebizOS 관점)

- 전용 IBL 액션은 **만들지 않는다** — CLI가 이미 좋은 어휘이고, 반-어휘-증식 규약("새 특수 어휘 만들까?"의 기본 답 = 스크립트 등록)에 따라:
  - 1회성 → `run_command`로 직접
  - 반복되는 잡 → `[self:script]`에 등록
    - **실례: `나레이션생성`** — 목소리 복제로 강의 나레이션을 굽는다(→ `voice_narration.md`).
      세션 생성·설치·업로드·생성·회수·**원격 삭제·`stop`** 까지 한 스크립트 안에 있고,
      위 함정 9·10·11 이 전부 코드에 박혀 있다. 콜랩 잡 스크립트의 본보기로 삼을 것.
  - 빈도가 결정화 신호를 주면 그때 액션 승격 검토
- 콜랩 잡 스크립트 저작·디버깅은 도구층(write+run_command)에서 — 코드는 파라미터 층을 통과시키지 말 것 (옛 shell-IBL 은퇴 사유).
