# OS 이식성 이음매 (OS Portability Seam)

indiebizOS를 새 OS(윈도우/리눅스)에 깔 때 **다시 개발할 필요 없는 부분(몸 독립)** 과
**OS마다 한 번씩 채우는 부분(몸 바인딩)** 을 가르고, 그 경계를 **빌드가 강제**해 잊혀짐을
막는다. 헌법1조(substrate/superstructure 이음매)의 OS 판(版).

> 상태(2026-06-21): 윈도우/리눅스 설치 예정 없음. 지금은 **이음매를 보이게·강제·문서화**까지만.
> 실제 OS 구현은 그 OS를 손에 쥘 때(검증 가능할 때) — 미리 짠 이식 코드는 썩고 거짓 커버리지가 됨.

---

## 1. 두 부류

| | 다시 안 짜는 부분 (superstructure) | OS마다 채우는 부분 (substrate) |
|---|---|---|
| 무엇 | IBL 어휘·엔진·라우팅, 3단 인지, 기억(해마·에피소드·포식), 35개 중 ~25개 패키지(순수 Python/HTTP) | 아래 §2 backend 이음매 + §4 패키지 tier-2 |
| 이식 시 | **0** | 어댑터 칸 채우기 |

핵심: 새 OS = **다시 개발이 아니라, 유한한 능력 이음매를 채우는 일.** 게다가 뼈대는 이미
3-OS 분기가 부분적으로 들어가 있음(ibl_executors·api_pcmanager·runtime_utils·electron build:win/linux).

---

## 2. 강제되는 backend 이음매 (`OS_SEAM_ALLOWLIST`)

`scripts/build_ibl_nodes.py` 의 **OS-가드**(`check_os_branches`)가 `backend/` 를 스캔해서,
아래 선언된 이음매 파일 **밖에서** OS 마커(`platform.system()`·`sys.platform`·맥/유닉스 전용
바이너리·`/opt/homebrew` 등)가 나오면 **빌드를 실패**시킨다. 즉 이 목록이 곧 **이식 점검표**다.

| 파일 | 무엇을 OS별로 바인딩 | 윈도우/리눅스 시 |
|---|---|---|
| `runtime_utils.py` | detect_body + 번들 런타임 경로 | Win 경로 이미 있음·detect 자기감지 ✓ |
| `ibl_executors.py` | 파일/URL 열기·클립보드·탐색기 | Darwin/Windows/Linux 3분기 이미 있음 ✓ |
| `api_pcmanager.py` | 드라이브/볼륨 열거·열기 | 3 OS 분기 있음 ✓ |
| `file_index.py` | 파일 검색(맥=Spotlight `mdfind`/`mdls`) | **Win/Linux 검색 엔진 추가 필요** (가장 큰 단일 작업) |
| `api_nas.py` | ffmpeg/ffprobe 경로 | `shutil.which` 우선화 |
| `api.py` | 부팅: Windows stdout 인코딩 + PATH | Win 인코딩 이미 처리 ✓ |
| `calendar_html.py` | 브라우저 열기(open/start) | xdg-open 추가 |
| `api_photo.py` | 사진 파일 OS 열기 | tier-2: ibl_executors 열기와 통합 후보 |
| `api_tunnel.py` | cloudflared 바이너리 위치 탐색 | tier-2: 공유 `find_binary` 후보 |

새 파일에 OS 코드가 생기면: 이음매로 옮기거나, 진짜 이음매면 `OS_SEAM_ALLOWLIST` 에 **의식적으로**
추가(그래야 빌드 통과 = 점검표에 등재). 흩어진 채로는 통과 못 함.

---

## 3. 잊혀짐 방지 = 가드 (사람 주의력 아님)

- **빌드 강제**: `build_ibl_nodes.py --check/--validate` 가 OS-가드 실행. INDIEBIZ_PROFILE
  포크-가드(폰 vs 데스크탑)의 형제 — 이쪽은 맥 vs 윈도우 vs 리눅스.
- **이중 채널**: pre-commit 훅(`scripts/git-hooks/pre-commit`) + World Pulse self-check(12h 순찰,
  `run_static_ibl_check`)에 같이 합류 → commit 시점 + 정기 순찰 양쪽에서 적발.
- 철학: IBL `--check` 삼각검증이 src↔tool.json↔handler 드리프트를 막듯, OS-가드가 OS 의존
  드리프트를 막는다. (2026-06-21 에피소드 로거 누락 같은 침묵 누락의 OS 판 방지.)

---

## 4. 패키지 tier-2 (이음매-아래, 이식 시 점검 — 가드 범위 밖)

패키지 핸들러는 이미 "OS 터치 전제"라 가드가 강제하진 않음. 이식 시 손볼 곳:

| 패키지 | 의존 | 윈도우/리눅스 |
|---|---|---|
| computer-use | `screencapture`·`pbcopy`·`NSWorkspace`(pyobjc) | 🔴 ImageGrab·pyperclip·win32gui 로 재구현 |
| pc-manager | `lsappinfo`(전면 앱) | 🔴 win32gui/xdotool |
| radio | mpv 경로 | 🟡 `where`/`which` 분기 (이미 which 폴백) |
| youtube·cctv·media_producer·photo-manager | ffmpeg/ffprobe/typst | 🟡 `shutil.which` 우선화 |
| nodejs·python-exec·remotion·browser-action·android·location-services 외 25개 | platform 분기 또는 순수 HTTP | 🟢 이미 크로스플랫폼 |

요약: 🔴 2개(재구현) · 🟡 5개(경로 통일) · 🟢 28개(무손). 예상 신규 코드 ~100줄(대부분 computer-use).

---

## 5. detect_body 모델 — 자기-감지 우선, env override는 위장한 몸만

`runtime_utils.detect_body()`:
- env(`INDIEBIZ_PROFILE`) 미설정 → `platform.system()` 으로 profile 유도(Darwin→mac·Windows→windows·Linux→linux). **몸은 이미 자기가 뭔지 안다.**
- env override 는 자기-감지가 *거짓말하는* 몸에만: **안드로이드 파이썬은 `platform.system()=='Linux'` 로 위장** → phone_api 가 `INDIEBIZ_PROFILE='phone'` 명시 주입.
- 맥/폰 동작 무변경(맥='mac'·폰='phone'). 윈도우만 진실('windows')을 얻음.

소비자(file_index 등)는 이 profile/kind 로 분기. 윈도우 분기 추가 시 여기 값으로 갈래를 연다.

---

## 6. 새 OS 온보딩 절차

1. `build_ibl_nodes.py --validate` 의 **OS-가드 출력 = 작업 목록.** (§2 표)
2. 각 이음매 파일에 그 OS 분기 채우기(대부분 *이전*이지 *신규* 아님 — 3분기 이미 있음).
3. file_index 검색 엔진(Win Search/Tracker 또는 os.walk 폴백) — 진짜 신규.
4. §4 패키지 tier-2: computer-use·pc-manager 재구현, 나머지 `shutil.which` 통일.
5. frontend `electron:build:win`/`:linux`(이미 있음) + `prepare:python:win`(있음).
6. 검증: 그 OS 실기에서 `--check` 통과 + 핵심 동작 종단 확인.

> 미리 하지 말 것: 위 2~4를 그 OS 없이 짜기 = 검증 불가 → 썩음·거짓 커버리지. 가드/문서/위생까지만 선제, 구현은 OS 손에 올 때.
