# IndieBiz OS 몸을 손발로 — 설치본이 상주 원격 하드웨어가 되는 길 (2026-10-13)

> 설계 핸드오프. 코드 변경은 아직 없다(빌드 설정 실험 1건 제외, 아래 §7).
> 정본 서열: git 커밋 > 이 문서 > system_docs. 구현이 끝나면 communication.md "USB 손발" 절과
> remote_access.md 에 요지를 옮기고 이 문서는 이력으로 남긴다.

## 1. 결정 (사용자, 2026-10-13)

두 대의 IndieBiz OS 가 있을 때 **한쪽이 다른 쪽을 원격 하드웨어로 등록하고 일방적으로
명령하는 관계**를 만든다. PC 는 헬퍼(Go 단일 파일)로 IndieBiz OS 없이도 이 관계가 되지만,
IndieBiz OS 가 깔린 몸은 **다른 방식**, 즉 자기 백엔드 안의 손발 클라이언트로 같은 관계가
된다. 그러면 PC 가 아니라도 IndieBiz OS 가 도는 어떤 하드웨어든 지배하는 원격 하드웨어로
등록·명령할 수 있다.

**보안 개정(사용자, 같은 날 오후)**: ① PC 는 **헬퍼를 설치한 PC 만** 원격 PC 로 등록된다 — IndieBiz OS 가
깔린 PC 는 손발 클라이언트를 돌리지 않는다(몸 감지가 폰일 때만 기동). ② 폰은 **IndieBiz OS 를 USB 로 설치하면서**
중앙 PC 에 등록하고 **허브 비밀번호**를 건다 — 하드웨어적으로 중앙 PC 와 연결해 설치했을 때만 중앙 PC 에 종속된
폰이 된다. 폰에는 나중에 다른 허브를 입력할 화면이 없고, 등록 자격은 1회용 초대로 만들어 폰에는 실행 키만 남는다.
→ 다른 사람이 내 IndieBiz OS PC·폰을 자기 허브에 등록하기 어렵다. 남는 구멍 = USB 디버깅이 켜진 잠금 해제 폰의
물리 점유, 디버그 빌드의 run-as(릴리스 빌드 전환은 후속). §4.5 설정 표면은 **짓지 않는다**.

**원칙(사용자, 같은 날 저녁) — 설치 ≠ 종속.** IndieBiz OS 를 설치한 폰과 중앙 PC 의 원격 하드웨어가 된 폰은 같은 것이 아니다.
설치는 설치이고, **오직 사용자가 부탁했을 때만** 그 폰이 원격 하드웨어로 등록되며, 그것도 **조종실에서 해체**할 수 있어야 한다.
구현상: `setup_phone.sh` 기본 설치는 등록하지 않는다(자격 파일 없음 → 손발 루프 미기동). 등록은 `--limb <이름>` 또는
`provision_phone_limb.py` 라는 별도 행위. 해체는 조종실 손발(USB) 목록의 해제(= `resident_pcs.remove` → 폰이 다음 sync 에서
자격을 지우고 `/limb/resident/removed` 로 확인) 또는 `[self:limb]{op:"remove"}`. 해체된 폰은 다시 "설치만 된 폰"으로 돌아간다.

첫 실물 = 낡은 안드로이드폰(삼성 Galaxy J7 2017, §7). 용도 = 다른 자리에 두고 중앙 PC 가
녹음·재생·촬영 등 몸의 어휘를 시킨다.

이 관계는 시스템의 **손발(limb)** 관계다(2026-07-23 USB 손발, 2026-10-10 상주 PC). 이웃
관계(`[others:ask]`, 대등·부탁·명함)와는 별개 문법이며 둘 다 유지한다. 07-22 "특권 배관
소멸" 원칙이 없애라고 한 허브 비밀번호 위임·폰 토큰·LAN 바인드·자기등록은 손발 역할의
폰에 필요 없다. 손발 키 하나가 그 넷을 대신한다.

## 2. 두 손발의 차이 (한 문장 요약: 손발 역할을 헬퍼만이 아니라 설치본도 맡는다)

| | 헬퍼 손발 (있음) | IndieBiz OS 손발 (이번) |
|---|---|---|
| 손발 쪽 몸 | Go 단일 파일, 엔진 없음 | 백엔드 전체, 자기 사전 있음 |
| 봉투 | 셸·파일 작업 JSON `{op, ...}` | **IBL 코드** `{op:"ibl", code, ...}` |
| 할 수 있는 일 | OS 가 셸로 허락하는 것 | 그 몸의 사전에 있는 것 (`runs_on`·몸별 프로브가 하드웨어 차이를 흡수) |
| 설치 조건 | 아무 PC | IndieBiz OS 가 도는 어떤 하드웨어 |
| 등록 | USB 폴더 + 설치 화면 | 설치본 설정 화면(또는 adb 주입)에 허브 주소 + 초대 키 |

하드웨어 차이는 **손발 쪽 사전**이 푼다. 폰의 `[sense:listen]` 은 폰 마이크를, 데스크톱의
`[sense:listen]` 은 웹캠 마이크를 잡는다. 허브는 "이 몸에서 이 IBL 을 실행하라"만 하달한다.
어휘는 전선을 건너지 않는다(ibl.md 언어의 경계).

## 3. 재사용하는 기반 (변경 없음)

- **자격**: `limb_keys` — `resident_invite`(1회용 초대)·`resident_enroll`(설치 ID 로 실행 자격
  발급, `registration{adapter:"resident-v1", kind:"pc"}`)·`revoke`. 허브 쪽 `[self:limb]{op: issue/list/revoke/remove/pause}`.
- **연결 방향**: 손발이 허브로 아웃바운드. `POST /limb/resident/enroll` → `POST /limb/resident/sync`
  `{key, installation_id, events[], capabilities, wait}` 롱폴(최대 20초 hold) → 응답 `{ack, jobs, cancel, generation, state, paused}`.
  WSS 가 막히면 롱폴만으로도 된다(헬퍼와 동일).
- **큐·접수증·기록**: `phone_jobs` + `resident_store`(요청ID 멱등·지문 대조·`started`/`result` 사건·history·cancel) +
  `task_receipts`(`task_kinds.guestpc` → `[self:task]{op: status/wait/cancel}`).
- **하달 어휘**: `[limbs:guestpc]{op, limb, request_id, background, ...}` 와 관용구 외부PC준비·외부PC작업실행·외부PC작업확인·파일가져오기.
- **파일 전송**: `/remote-pcs/transfers` + `/limb/resident/transfers/{tid}` — 바이너리 조각·offset 재개·SHA-256·덮어쓰기 거절.
- **폰 몸의 어휘**: `[sense:listen]{op:record}`(최대 300초 동기)·`[sense:see]`·`[sense:here]`·`[limbs:phone]`(알림·진동·TTS·저장·공유)·`[limbs:android]`(화면 조작, 네이티브 접근성).
- **폰 상주**: `AgentForegroundService`(START_STICKY·부팅 복원) 가 앱 화면 없이 백엔드 :8765 를 띄운다.

## 4. 지어야 할 것

### 4.1 손발 모드 클라이언트 (백엔드 공통 모듈, 폰 APK 에 자동 번들)
`backend/services/limb_client.py` (층 = services, `check_backend_layers.LAYERS` 배정).
- 설정 = `data/limb_client.json` (폰은 `INDIEBIZ_USERDATA` 형제): `{hub_url, key, installation_id, alias}`.
  `installation_id` 는 첫 실행 때 `secrets.token_hex(16)` 로 만들어 영속(헬퍼와 같은 규칙, 32 hex).
- 루프: enroll(초대 키 → 실행 자격 키 교환, 1회) → sync 롱폴 → 봉투 실행 → 사건(`started`·`result`)을
  로컬 spool 에 먼저 적고 다음 sync 에 실어 ack 받으면 지움(헬퍼 `spool/events` 와 동일 = 재시작 중 유실 0).
  `generation` 이 바뀌면 재등록, `state:"removed"` 면 자격 삭제·루프 종료(자가 제거 = 등록 해제 계약).
- 폰 `phone_api._register_with_hub`(허브 비밀번호·폰 토큰 경로) 는 이 역할에서 **쓰지 않는다**. 폰 설정에
  손발 모드가 켜지면 자기등록 루프 대신 이 클라이언트만 돈다.
- `capabilities` 신고 = `{"adapter":"indiebiz-v1", "body": INDIEBIZ_PROFILE, "ibl": true, "shell": false,
  "card": <GET /nodes/card 와 같은 명함 투영>, "python": "3.11|3.12", "abi": ...}`. 허브는 이걸로 봉투 종류를 고른다.

### 4.2 봉투에 IBL 종류 추가 (허브 `resident_pcs.submit` + 손발 클라이언트)
- `{op:"ibl", code:"[sense:listen]{op:record, duration:30}", agent_id, mode:"background", timeout}`.
- 손발 클라이언트는 `code` 를 **자기 `/ibl/execute`** 에 넣는다(폰 `_run_push_job` 과 같은 단일 경로 — localhost 는 인증 통과).
  결과 = IBL 통화(`{items:[...]}` 또는 실패 봉투) 그대로 `result` 사건에.
- 허브 `submit` 의 `allowed` 는 **등록된 capabilities 로 분기**: `ibl` 신고 몸에만 `ibl` 허용, `shell:false` 몸에
  `shell` 하달은 `unsupported_resident_operation` 으로 **명시 거절**(10-10 설계 "조용히 대체 실행 금지").
- 봉투 크기 상한 256KB·요청ID 멱등·지문 충돌 규칙은 그대로.

### 4.3 허브 어휘 (★판정 필요 — op 신설은 어휘 증식)
가장 작은 모양 = `[limbs:guestpc]` 에 `op: ibl` 하나. 인자 `code`(필수)·`limb`·`request_id`·`background`·`timeout`.
`ops.values.ibl: "IndieBiz OS 손발에 IBL 실행 (code) — 그 몸의 사전으로 돈다"`. 통화 `effect`, 배경이면 접수증.
- 대안 A: 새 낱말 없이 `[sense:listen]{...}@거실폰` 의 `@별칭` 꼬리가 손발 큐로 라우팅. 반-어휘-증식에는 맞지만
  `@별칭` 은 이웃·폰-class 주소 지정과 뜻이 겹치고, 손발 관계의 "일방 명령·접수증·history" 의미가 문법에서 안 보인다.
- 추천 = op `ibl`. 이름 `guestpc` 는 10-10 설계대로 유지(PC 의미), 설명에 "IndieBiz OS 손발 포함" 을 적는다.
  더 넓은 이름(`limbs:remote`)으로 바꾸는 것은 언어 개정이라 별도 판정.
- 허브에서 하달 IBL 을 쓰거나 검사할 때 기준은 **손발의 사전**이다. 4.1 의 `card` 신고를 `[self:limb]{op:list}`·info 에
  노출해 AI 가 "그 몸이 아는 낱말"을 보고 쓴다. 검사기는 손발 쪽에서 돌고 거절이 결과로 돌아온다(컴파일은 허브, 검증은 손발).

### 4.4 폰 몸의 어휘 공백
- **재생 op 없음**: `[limbs:phone]` 은 TTS 뿐. Kotlin `MediaPlayer` 다리(`play(path|url, volume)`·`stop`·`volume`) +
  android 패키지 `_phone_act` 분기 + `ibl_actions.yaml` ops.values + `_OP_DISPATCHERS["phone_act"]` 등록 + APK 재빌드.
  통화 모양은 상주 PC `media` op(`{path/url, mode, timeout, volume 0..100}`) 와 맞춘다. 파일은 손발 전송으로 먼저 보낸다.
- **긴 녹음**: `recordAudio` 는 최대 300초 동기 블록이고 푸시 실행은 120초 httpx timeout → 손발 봉투는
  `mode:"background"` + progress 로 올린다. 300초 상한은 유지(더 길면 반복 녹음을 관용구로).
- **파일 회수**: 녹음·사진은 폰 `filesDir` 에 남는다. `_pull_remote_artifacts`(토큰 직결)는 쓰지 않는다 — 손발 전송
  `transfer action:collect` 가 정본. 손발 클라이언트가 `/limb/resident/transfers/{tid}` 업로드를 구현한다.
  49회차 L49-2(조각 45초·재시도 없음)·L49-3(요청ID 영구 실패) 수리가 같이 묶인다.

### 4.5 등록 = USB 설치 때 1회 (설정 표면 없음 — 보안 개정)
`setup_phone.sh --limb 삼성1` → `provision_phone_limb.py`(허브에서 실행): 허브 원격 접속 비밀번호 확인 → 1회용 초대
`resident_invite` → `resident_enroll(kind=phone, adapter=indiebiz-v1)` 로 이 설치(installation_id)에 묶인 실행 키 →
adb run-as 로 폰 `files/secrets/limb_client.json` → 앱 재시작. 초대는 그 자리에서 소진·폐기. 해제 = 허브 `[self:limb]{op:remove}`.

## 5. 구현 순서

1. 4.1 클라이언트 + 4.2 봉투 — 허브 격리 시험(TestClient 로 enroll→sync→ibl 봉투→result→history) 먼저.
2. 4.3 허브 op `ibl` (판정 뒤) + 삼각 `--check` + 가이드 `guest_helper.md`·`new_action_checklist` 갱신.
3. 폰: 32비트 빌드(§7) → 설치 → 4.5 주입 → `[limbs:guestpc]{op:ibl, limb:"거실폰", code:"[limbs:phone]{op:vibrate}"}` 종단.
4. 4.4 재생 op + 회수 전송 → "30초 녹음해서 가져와 / 이 파일 틀어 / 멈추고 배터리 알려줘" 세 문장 종단.
5. 무인 검증(§6) → 문서 이전(communication.md·remote_access.md·memory).

## 6. 검증과 인수 기준

- 격리: `backend/test_resident_pcs.py` 계열에 indiebiz 어댑터 케이스(enroll·sync·ibl 봉투·shell 거절·removed 자가 제거).
- 실기기: ① 화면 끈 채 1시간·하룻밤 뒤 sync 가 살아 있고 하달이 닿는가 ② 재부팅 뒤 복원 ③ Doze 와 삼성 절전에서
  롱폴 간격이 늘어나는가(늘면 WifiLock·부분 WakeLock) ④ 녹음 30초→전송→허브 파일 지문 일치 ⑤ 재생·정지 ⑥ 허브
  `remove` 뒤 폰이 자격을 지우는가.
- 성공 모양의 실패 주의: 꺼진 화면 검은 사진 success(L51-2)·screen 늦게 찍힘(L51-1) 부류는 폰에도 같은 눈으로 본다.

## 7. 첫 실물 — Galaxy J7 2017 (SM-J730K) 실측 (2026-10-13, USB adb)

| 항목 | 값 | 영향 |
|---|---|---|
| Android | 9 (API 28), 보안패치 2021-04 | minSdk 28 충족. FGS `microphone` 타입 제약(14+) 없음 |
| ABI | **armeabi-v7a 만** (32비트) | 현 APK(arm64 전용) 설치 불가 |
| Python | Chaquopy 16: **3.12 는 arm64·x86_64 만** | 32비트는 **Python 3.11** 로 빌드해야 함 |
| RAM / 저장 | 3GB / 여유 6.6GB | 백엔드 상주 메모리 실측 필요 |
| 배터리 | 10%, 건강 양호, USB 급전 | 상시 충전·보호 설정 |
| Wi-Fi | 켜짐, 미연결 | 설치 전 집 Wi-Fi 연결 |
| 기타 | 타사 앱 64개, 프로세스 347 | 초기화 권장(사용자 결정) |

- 실험: `abiFilters "armeabi-v7a"` + `python.version "3.11"` 빌드 — 결과는 이 문서 아래 §7.1 에 적는다.
- 3.11 호환: 폰 번들 모듈 716개 전부 3.11 인터프리터로 컴파일 통과(2026-10-13). PEP 695/701 사용 0.
- API 29+ 무가드 호출 2곳(`PhoneActions.kt` `MediaStore.setRequireOriginal`·`ThumbnailUtils.createVideoThumbnail(File,Size,signal)`)
  → API 28 에서 그 경로만 `NoSuchMethodError`. 사진 EXIF GPS·동영상 썸네일이라 손발 역할엔 안 걸리지만 가드를 넣는다.
- 빌드 구성 결정: A36(arm64·3.12)과 J7(armeabi-v7a·3.11)을 **product flavor** 둘로 갈라 각자 APK. 하나의 APK 에 두 ABI 를
  넣는 길은 Chaquopy 가 Python 판을 변형별로 다르게 못 두면 막힌다(실험으로 확인).

### 7.1 실험 결과 (2026-10-13, J7 USB)
1. `abiFilters "arm64-v8a","armeabi-v7a"` + Python 3.12 → 설정 단계 실패: "Python 3.12 is not available for the ABI 'armeabi-v7a'. Supported ABIs are [arm64-v8a, x86_64]".
2. `abiFilters "armeabi-v7a"` + `version "3.11"` + buildPython 3.12 → 빌드 성공(49.7MB), 설치 성공, 앱·런처 화면까지 뜸.
   백엔드는 `ImportError: bad magic number in 'phone_api'` 로 실패 — buildPython(3.12) 이 미리 컴파일한 .pyc 를 3.11 런타임이 못 읽음.
3. buildPython 을 pyenv 3.11.12 로 → 빌드 성공(79MB), **백엔드 기동**(앱 시작 뒤 ~20초).
   `[limbs:phone]{op:vibrate}` 실진동 ✓ · `[sense:listen]{op:record}` 5초 m4a 생성 ✓ · 상주 PSS 155MB(3GB 중) ✓.
   폰에 curl 없음(adb shell 프로브는 `adb forward` 뒤 맥에서). 폰 시계가 2021년(네트워크 미연결) — Wi-Fi 연결 뒤 맞춰진다.
4. 결정 반영: `app/build.gradle` 을 `productFlavors { arm64(3.12) / arm32(3.11) }` 로 갈랐다. APK 경로가
   `app/build/outputs/apk/<flavor>/debug/app-<flavor>-debug.apk` 로 바뀌므로 `setup_phone.sh` 가 ABI 를 보고 flavor 를 고른다.

## 8. 구현 (2026-10-13, 미커밋)

| 조각 | 파일 | 상태 |
|---|---|---|
| 손발 클라이언트 | `backend/services/limb_client.py` (폰 번들 자동) | ✅ enroll 된 자격으로 sync 롱폴·IBL 봉투 실행·사건 spool·unknown 복구·remove/revoke 시 자격 삭제. 몸 감지(detect_body)=phone 일 때만 기동 |
| 허브 봉투 관문 | `resident_pcs.submit` | ✅ adapter=indiebiz-v1 → ibl·info 만(신고 ops 로 더 좁힘), 헬퍼엔 ibl 거절. `ibl_code_required`·64KB 상한 |
| 자격 | `limb_keys.resident_enroll(kind, adapter)` + `_load` mtime 재독 | ✅ 외부 프로세스(등록 스크립트)가 쓴 원장을 라이브 허브가 바로 본다 |
| 허브 어휘 | `[limbs:guestpc]{op:"ibl", limb, code}` (`guest-helper/handler._op_ibl`, yaml, 가이드 §IndieBiz OS 손발) | ✅ build --check 통과, 용례 46건 ack |
| 소유 판정 | `ibl_registry._outside_strings` | ✅ 문자열 리터럴 안의 `[node:action]` 은 데이터 — 손발에 보내는 IBL 이 "남의 어휘"로 거절되던 입구·회상 게이트 수리 |
| 폰 라디오 host | `tool_radio._phone_play/stop/status/volume` + Kotlin `PhoneActions.playStream/stopStream/streamStatus/setStreamVolume` (WAKE_LOCK, WifiLock) | ✅ 빌드. 실소리는 등록 뒤 E2E |
| 폰 표면 축 | `phone_execution_routes` 가 `surface` 를 thread_context 에 전달 | ✅ WebView=client, 손발·폰 두뇌=host |
| 등록 스크립트 | `phone-companion/scripts/provision_phone_limb.py`, `setup_phone.sh --limb` | ✅ 틀린 비밀번호=아무것도 안 만듦(실측) |
| 해마 | `scripts/seed_phone_limb_ibl.py` 16용례 | ✅ |
| 시험 | `backend/test_limb_client.py` 7건 + resident/guestpc 회귀 86건 | ✅ |
| J7 | arm32 APK 재설치, 백엔드 12초 기동, 자격 없을 때 손발 루프 미기동 | ✅ |
| 조종실 해체 | 손발(USB) 패널 `해제`(`POST /remote-pcs/state {remove}`) → 허브 removal_pending → 폰이 sync 에서 받아 `/limb/resident/removed` 확인 → 허브 removed, 폰 자격 삭제 | ✅ 실측(삼성1). 패널에 폰 표식("폰 (IndieBiz OS)")·폰용 문구 추가, `tsc` 통과. 해체 뒤 폰은 "설치만 된 폰" |
| 등록 스크립트 개정 | 비밀번호 단계 제거(사용자 확정: 등록 조건은 헬퍼와 같이 "허브가 만든 자격 + 물리 접근" 둘뿐), `--replace`(허브 주소 교체) | ✅ |
| E2E 등록·명령 | J7 을 `삼성1` 로 등록(USB `adb reverse tcp:8766 tcp:8765`, 허브=http://127.0.0.1:8766) | ✅ 허브 `[self:limb]{op:list}` 에 adapter indiebiz-v1·live. `op:ibl` 진동 **왕복 0.69초**, `op:info` 명함, `background:true` 5초 녹음 → `[self:task]{op:wait}` succeeded(파일 경로), `op:shell` → `unsupported_on_this_body`, `[limbs:radio]{op:status}` ok, `op:play` → Wi-Fi 없어 "인터넷 연결 실패" 정직 실패. `/ibl/translate "삼성1에게 라디오 틀라고 해"` → 심은 용례 #5037 회상 |

후속: ① J7 Wi-Fi 연결 뒤 `--replace --hub https://finder.kukjinkang.uk`(또는 LAN http://192.168.0.32:8765) 로 재등록 → 라디오 실소리·화면 끈 채 하룻밤 ② 녹음·사진 파일 회수(transfer collect 의 폰 구현) ③ 릴리스 빌드(run-as 차단) ④ API 29+ 무가드 2곳 ⑤ 높은 레벨 이웃의 ask 범위에 limbs:guestpc 가 드는지 확인(손발 명령=허브 주인 전용 권고) ⑥ communication.md·remote_access.md 요지 이전.

