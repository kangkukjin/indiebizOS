# 87회차 — 세 조작면 드라이버(Android 폰·Windows PC·Chrome)를 한 프로그램으로: 쓰기·원복·실패 모양 (2026-10-20~21)

설계 [LONG_SENTENCE_DRIVER_TRIAD_DESIGN_2026_10_20.md](../../../LONG_SENTENCE_DRIVER_TRIAD_DESIGN_2026_10_20.md) · 과제 [task.md](task.md) · 프로그램 [base_v0.ibl](base_v0.ibl) · 탐침 [probes.ibl](probes.ibl)·[probe_p2_read.ibl](probe_p2_read.ibl)·[probe_p3_step1.ibl](probe_p3_step1.ibl)/[step2](probe_p3_step2.ibl)·[probe_p8.ibl](probe_p8.ibl)·[chrome_b.py](chrome_b.py) · 대조 [verify.py](verify.py) · raw 증거 `outputs/long_sentence_imagination/2026-10-20_87회차/`(git 밖, 개인 탭 제목·URL 포함).

형식 = 가이드 §2 **이음새 입장 회차**(Windows 동형 16동작·Android UI 6동작·Chrome 드라이버 — 셋 다 단일 호출 실기만 거침) + 주 과제 통과 뒤 **불변식 탐침 8** + §4-5 ① **독립 AI 1회**. 예산 23:50~00:50 KST(60분), 상한 안에 훈련자 기본·변형·탐침 완료(23:50~00:06). 독립 AI 는 00:06 발송(별도 계시).

## 1. 결과 한눈에

| 실행 | 시간 | 가지 7 | 검증 행 | 원복 대조 | 저장·재독 |
| --- | --- | --- | --- | --- | --- |
| 기본 v0 (수정 1주기: `;` 문장 구분) | 233.3초, 모델 호출 0 | 7/7 완료, 예외 0 | tv1 22/22 · 삼성0 음량 6/6 · 삼성1 2/2 · 예나폰 2/2 · Chrome 6/6 · 맥26 0/8(target 거절) · 삼성0 UI 1/2(`UI_DRIVER_UPDATE_REQUIRED`) | clipboard·keep_awake·notepad·음량·Chrome 판본 **전부 same**, UI 가지 unverified(거절) | 일치 |
| 변형 A (tv1→맥12 미연결, Chrome 창 2147483646) | 113.5초 | 7/7 완료 | 맥12 0/17 전부 `stage:target`·장치 전송 0, Chrome `TARGET_MISSING` 예외→오류 행, 나머지 네 가지 기본과 동일 | 음량 same, 기본 보고서 SHA `df2835…` 보존 | 일치 |

실기 쓰기와 원복(설계 §4 기준 셋 충족분만): tv1 clipboard 빈 글→링크→빈 글(Clear) 재조회 일치, keep_awake 60초→power 에 pid 보임→allow_sleep→power 에 없음, launch notepad→apps 에 등장→quit→apps 에 없음; 삼성0 music 3→1(half)→3(restore); 본체 Chrome 탭 14→open(배경, `activation_restored:true`, 현재 탭 5 유지)→switch 15→switch 5→close(탭 id)→판본 = 시작 판본. 미검증(설계대로 명시): 실제 소리·사람 입회·페이지 로드·Windows 화면 잠듦.

**설계의 중심 질문**(세 드라이버가 같은 결과 모양인가 — 분기 없는 `행` 투영 하나로 셋을 다룰 수 있는가): **아니오**. `행` 은 PC·Android 행에서는 status·failure·task_ref 를 채웠지만 Chrome 행에서는 `status:null`·`task_ref:null` 이 됐고(L87-4), 실패는 PC·Android 가 `status:"failed"` 레코드인 반면 Chrome 은 예외라 `[catch]` 분기가 따로 필요했다. 프로그램은 `verified` 하나가 셋에 공통이라 완주했다.

## 2. 실행 전 조건 실측과 설계와의 차이

- 맥26: 23:30 명부에서 `connected:true` 였으나 23:51·23:58 실행 시각에는 끊겨 있었다(프로그램이 읽은 `connected_ids` 에 없음). 드라이버 거절은 정직했고, 설계 §2 "원격 맥 OS 드라이버 첫 실측" 은 이번에 못 했다. 거절 문장이 다섯 조건을 한 문장으로 묶어 어느 조건인지 보고서에 남지 않은 것은 L87-3.
- 폰 셋 APK: 삼성0 `hardware_control:1`·`ui_contract` 없음(ui_snapshot → `UI_DRIVER_UPDATE_REQUIRED`), 예나폰·삼성1 `hardware_control:0`(구형). UI 가지는 설계 §2 분기대로 거절 경로 관측이 됐고, 대상을 예나폰(화면 꺼짐·잠김·구형)에서 삼성0(화면 켜짐·잠금 없음·계약 1)으로 바꿔 원인을 APK 판본 하나로 좁혔다. APK 설치는 회차 밖(되먹임 후보).
- tv1 앞 창은 Netflix 가 아니라 `about:blank - Chrome` 이었다. lock·sleep·wifi·shortcut 제외는 유지(설계).

## 3. 탐침 8 결과

| # | 불변식 | 결과 | 판정 |
| --- | --- | --- | --- |
| P1 | 대상 바꾸면 값만 바뀌고 모양은 같음 | tv1·`__local__` 행 키 집합 동일(`_receipt_ref` 자리만 다름: 원격은 행에, 본체는 result 안에), 맥26 은 거절 행(키 7) | 통과, 작은 비대칭 기록 |
| P2 | `reuse:{run_id}` 면 기기 호출 0 | **reused_calls 0**, 기기 전송 3회 다시 실행(23.3초). 첫 실행에서 `limbs:guestpc`(shell, 쓰기 발자국 미상)가 앞선 `self:limb`·`self:read` 를 `unknown_write_resources` 로 제외 → 재실행에서 `no_matching_receipt`·`overlapping_write` | **L87-1** |
| P3 | 소실 영수증은 unknown·재전송 0 | task_id 를 바꾼 작업으로 `Android제어확인`·`PC제어확인` → 둘 다 `status:unknown`, `verification` stage "원래 요청·대상·작업 참조와 다릅니다", 저널에 `limbs:guestpc` 0 | 통과 |
| P4 | 거짓 성공 모양 없음 | `apps` 행 이름 null 0건, `verified:true` 인데 result 빈 객체 0건(기본·변형) | 통과(§18 ② 회귀 0) |
| P5 | OS 가 못 읽는 값은 null+basis | tv1 `power.flags/sleep_holders/lid_closed:null`, `requests_basis:"powercfg_requests_requires_admin"`, `presence.display_asleep:null` | 통과 |
| P6 | 세 드라이버 거절 모양 동형 | PC: `status:failed` + `failure{stage,message,next}`(코드 없음, 메시지 "앱을 찾지 못했거나…") / Android: 같은 모양, 코드는 메시지 앞머리 문자열 / Chrome: **예외** `code:TOOL` + `details.failure{code,message,next}` | **L87-3·L87-4** |
| P7 | 원복 불변식 3값 | 기본: 5종 전부 same, UI unverified / 변형: 음량 same | 통과 |
| P8 | needs_front 동작은 배경 문맥에서 거절 | `origin:"scheduler"` 로 `app_launch` → **폰에 전송됨**(`limbs:guestpc` 1회), 거절은 폰 APK(`UI_DRIVER_UPDATE_REQUIRED`)가 했다. 실행 전 검사 없음 | **L87-2** |
| 변형 B | 판본 경합 | status 뒤 바깥 AppleScript 로 탭 추가 → 옛 판본 close = `STATE_CHANGED` 변경 전 중단, 추가 탭 정리 뒤 판본 = 시작 판본. Android `STALE_SCREEN` 은 APK 미설치라 **탐침 불가** | 통과 / 불가 |

## 4. 발견

- **L87-1 (★★, 구현)** 드라이버 읽기의 재사용 불가: `limbs:guestpc` 전송(shell·python, background)은 쓰기 발자국 미상(`resources:None`)이라 같은 실행 안의 **모든** 앞선 읽기(손발 목록·실행 파일 읽기)를 재사용에서 제외하고, `reuse` 재실행은 기기 호출을 그대로 반복한다(P2: reused 0, 기기 3회). 85회차 L85-3 과 같은 뿌리. 수리는 자원 계약의 문제(장치 realm 선언 또는 op 별 발자국) — §6 참조, 이번 회차 미수리.
- **L87-2 (★★, 구현)** `needs_front:true` 인 Android UI 동작이 `origin:scheduler` 문맥에서 실행 전 검사 없이 폰에 전송됐다(P8). `control_conditions` 는 `limbs:screen`·`limbs:browser` 핸들러만 거쳤고, `self:script` 로 도는 드라이버 부품은 화면 문맥을 받을 통로가 없었다. 설계 §6 "실행 직전 경계가 검사" 위반. → ✅ 수리(§6).
- **L87-3 (★, 계약)** PC·Android 의 `failure` 에 `code` 칸이 없다. 대상 거절은 다섯 조건이 한 문장("연결·활성·shell 준비 상태가 아닙니다"), 검증 실패는 코드가 메시지 앞머리 문자열(`UI_DRIVER_UPDATE_REQUIRED: …`)이거나 아예 없음(launch 실패). Chrome 은 `details.failure.code` 가 있다. 프로그램이 실패를 종류별로 다루려면 문자열을 잘라야 했다. → ✅ 수리(§6).
- **L87-4 (★, 계약)** 앱 드라이버(Chrome·Safari, `self:script`) 성공 결과에 `status`·`failure` 자리가 없어 PC·Android 와 같은 투영이 null 을 낳고, 실패는 레코드가 아니라 예외다. → ✅ 부분 수리(성공 결과에 `status:"completed"`·`failure:null`; 실패=예외는 유지, 가이드에 명시).
- **W87-1 (★★, 낭비)** `PC제어`·`Android제어` 가 **호출마다** `[self:limb]{op:"list"}` 전체(활성 5 + 폐기 14 + 하드웨어, 65KB)를 읽는다: 기본 실행 저널 238호출 중 self:limb 26회·2.49MB(저널 바이트의 46%), 변형 A 는 22회(그중 17회가 이미 끊긴 맥12 를 향한 반복 조회). `self:read`(실행 파일 54KB) 25회·1.36MB 도 같은 모양. → ✅ 수리(§6, 목록 op `limb` 필터).
- **W87-2 (낭비, 기록만)** 검사(`check:true`) 56.3초·가드 1,104·guards_ref 2.59MB — 실행 233초의 24%. 85회차 타입 추론 수리 뒤에도 긴 프로그램에서 큰 몫. 미수리.
- **W87-3 (낭비, 기록만)** 부재 대상에 대한 프로그램의 호출: 변형 A 에서 맥12 가지가 읽기 8 + 쓰기 9 = 17회 거절을 받았다. 전송 0 이라 안전하지만 각 호출이 목록 조회를 반복했다(W87-1 과 결합). 작성 교훈: 묶음 조회의 첫 행이 `stage:target` 이면 같은 대상의 쓰기를 건너뛴다.
- 작성 마찰 1건: 한 줄에 문장 둘(`$a=… $b=…`)이 `SYNTAX` — 검사기 진단이 위치를 정확히 짚어 1주기로 끝남(73회차 L73-1 방식). 그 외 v0 수정 0회.
- 맥26 연결 흔들림은 결함이 아니라 환경 사실(연결은 시각마다 다르다). 관측 행 후보: `device:guestpc-9dc41d53987d` "연결 간헐".

## 5. 독립 AI 1회

`POST /system-ai/chat` `origin:training`, 00:06:26 발송, ep5094. §3 원문 + 별칭↔device_id 표 + 저장 위치만 넘김.

| | 훈련자(기본 v0) | 독립 AI(ep5094) |
| --- | --- | --- |
| 벽시계 | 233초(검사 56초 별도) | 1,185초 |
| 모델 호출·토큰 | 0 / 미측정 | consciousness 2·execution 1·evaluate 1·classify 3 / 입력 5.77M(cache_read 5.28M·create 0.47M)·출력 36K |
| 도구 호출 | IBL 1실행(저널 238호출) | 31(execute_ibl 27·Bash 4), 검사 거절 4(`$rejected` → code_edits 재검사) |
| 드라이버 선택 | fn:PC제어·PC조회묶음·fn:Android제어·Chrome제어 | **같은 셋을 IBL 로**. `limbs:screen`·`limbs:browser` 0, Python 0 |
| 달성 | tv1·삼성0·Chrome same, 삼성1 읽기만, UI 거절, 맥26 거절 | tv1·삼성0·Chrome same(음량 3→1→3), 삼성1 읽기만, 예나폰 UI 전부 거절(구형 APK), **맥26 부분** |
| 미검증 명시 | 소리·입회·페이지 로드·화면 잠듦 | 같은 넷 + 메모장 최소화 여부·tv1 네트워크 경로 |

AI 의 다른 길 둘(설계 §10 ⑧ 답): ① **드라이버가 거절한 대상에 원시 통로로 접근** — 명부에서 맥26 이 `connected:false` 인데 `[limbs:guestpc]{op:"info"}` 가 응답하자 `fn:PC제어` 대신 원시 `shell`(osascript clipboard info·pbpaste·hostname) 을 보냈고, 이어 `fn:PC제어` clipboard 왕복 중 연결이 끊겨 `clipboard_write ""` 가 헬퍼 대기열에 남았다. AI 는 "재연결 때 그 시점 클립보드를 지울 수 있다" 고 판단해 history 로 대기 3건을 찾아 **cancel** 했다(올바른 복구). 교훈 후보: 연결이 흔들리는 대상에 쓰기를 보내면 끊김 뒤 대기열의 변경이 미래에 실행된다 — 드라이버 거절 뒤 원시 통로로 같은 변경을 재시도하지 않기(설계 §7 "통신 실패 뒤 화면 조작으로 같은 변경 재시도 금지" 의 동형). ② tv1 클립보드 포맷을 원시 PowerShell 로 한 번 더 읽었다(드라이버 `clipboard` 가 텍스트만 돌려줘 "원래 내용" 보존을 확인하려는 보수성).
AI 의 IBL 작성 마찰 4건은 전부 타입 검사 거절(널 가능 필드 `$c0.text`·삼항식 안 호출·`$o.target` 널 접근·each 안 조건식) → `get()` 투영으로 고침. 훈련자 1건(`;`)과 부류가 다르다.
회상: 해마 1건(5082) 제시·사용 0, 가이드 블록 제시. AI 는 `describe` 로 서명을 먼저 읽었다.

## 6. 수리 (2026-10-21 00:28~00:45, 같은 세션)

| 발견 | 수리 | 검증 |
| --- | --- | --- |
| L87-2 needs_front 배경 전송 | `script_ops._child_env` 가 `INDIEBIZOS_SCREEN_CONTEXT`(control_conditions.screen_context JSON)를 자식에 싣고, `android_control.select_target` 이 `condition(action).needs_front` 이고 문맥 `available:false` 면 `SCREEN_CONTEXT_UNAVAILABLE` 로 거절. 환경 없음(허브 밖 직접 실행)=미상, 막지 않음 | 시험 7+8건(backend/test_android_control.py). 실기: `origin:scheduler` app_launch → `stage:target`·`SCREEN_CONTEXT_UNAVAILABLE`·`limbs:guestpc` **0**(수리 전 1). `origin:training` 은 통과 뒤 APK 거절 |
| L87-3 failure.code | PC·Android `select_target` 거절을 조건별 코드 메시지로 분리, `verify` 의 `fail()` 과 관용구 6개 catch 가 `code` 칸(앞머리 `CODE:` 추출, IBL 은 `strip` 기반 — 텍스트 `==` 가 대소문자를 무시해 `upper/lower` 비교가 안 됨), `pc_read_batch` 미지원 항목 `UNSUPPORTED_ACTION`, 실행 파일 launch 실패 `LAUNCH_FAILED:` 앞머리 | 시험(test_pc_control 8건·test_android_control 3건). 실기: 맥26 `TARGET_NOT_CONNECTED`, 미등록 `TARGET_NOT_REGISTERED`, tv1 launch `LAUNCH_FAILED`, 삼성0 `UI_DRIVER_UPDATE_REQUIRED` 전부 `code` 칸 |
| L87-4 앱 드라이버 모양 | chrome_control.py·safari_control.py 성공 `base` 에 `status:"completed"`·`failure:null` | 시험 1건. 실기 Chrome status `{status:completed,failure:null,verified:true}` |
| W87-1 손발 목록 | guest-helper `_limb_list` 에 `limb`(device_id·별칭) 필터, ibl_actions.yaml `limb: string`, 관용구 PC제어·PC조회묶음·Android제어가 `limb:$대상` 으로 조회(해마 재등록 2회, 백업 `data/_backups/2026-10-21_00*`), self:script 핸들러 재감사 지문 갱신 | 시험 1건(test_control_driver). 실기 같은 읽기 프로그램: `self:limb` 2회 191,294B → **21,126B**(−89%), 시간 25.5→24.2초(기기 지연이 지배) |

회귀: test_android_control·test_pc_control·test_chrome_control·test_safari_control·test_control_driver·test_guestpc_resident_idioms 299 통과, 넓은 묶음은 §7. `build_ibl_nodes.py --check` 통과. 백엔드 `restart --wait` 1회(00:33, 27초).
**미수리**: L87-1(자원 계약 개정 — 사용자 판정), W87-2(검사 56초), 예나폰·삼성0 APK 갱신(회차 밖), AI 관측 ①의 가이드 문장(드라이버 거절 뒤 원시 통로 재시도 금지 — 후보).
수리 뒤 되먹임(수리 전후 같은 요청 재실행)은 탐침 셋(P8·W1·P6)만 했고 전체 과제·AI 재실행은 하지 않았다.

## 7. 잔여 수리 감사와 후속 반영 (2026-10-21)

사용자의 최근 훈련 잔여 수리 요청으로 78~87회차 원장과 최근 보고서·커밋을 대조했다.
85회차 수리와 86회차 JSON 진단 수리는 정본에 반영돼 있었다. 이번에는 아래 경계를
수리했다. 새로운 기기 쓰기 훈련이나 독립 AI 실행은 하지 않았다.

### W87-2 — 검사 메타데이터의 중복 수집 제거

원 `base_v0.ibl`과 고정된 합성 기기 ID·URL·창 번호로 검사만 재생했다. 프로파일에서
`script_snapshot` 253회가 Python 환경 지문을 253회 다시 만들고 스크립트 등록부도
반복 파싱했다. 프로파일 총 129.914초 중 이 함수 누적 102.520초, 환경 지문 누적
73.236초였다(계측 오버헤드가 있으며 누적 시간은 서로 겹친다).

`ibl_dependencies`가 한 `compile_program` 호출 안에서 등록부·스크립트 의존성·환경
메타데이터를 공유한다. 호출 위치마다 독립된 증거 사본을 보존한다. 검사 종료·예외 때
공유 범위를 해제하며, 다음 검사와 실제 실행 직전의 의존성 확인은 새로 읽는다.
프로세스 전체 캐시나 기기 관측 캐시는 추가하지 않았다.

| 동일 프로그램 검사 | 시간 | 오류 | 실행 시 검사 |
| --- | --- | --- | --- |
| 수리 전(비프로파일) | 50.856초 | 0 | 1,240 |
| 메타데이터 수리 직후 | 1.665초 | 0 | 1,240 |
| 신선도 계약까지 반영 후 | 1.843초 | 0 | 1,240 |

계획·의존성 지문을 제외한 보고서 전체가 동일했다. 최종 의존성에서는 변경한 코어와
어휘 계약의 지문만 달랐다. 실제 기기 ID를 쓰던 최초 회차의 1,104개 검사와 이번
고정 입력의 1,240개를 같은 입력이라고 비교하지 않는다. 같은 입력의 단일 전후 실측이며,
전체 기기 작업 시간·독립 AI 시간·토큰 절감은 미측정이다.
[재현 검사](check_benchmark.py), [비민감 측정 증거](residual_check_evidence.json).

### L87-1 — 잘못된 재사용 기대 정정과 실제 신선도 결함 수리

P2의 “reuse면 기기 전송 0”은 현재 상태를 묻는 프로그램에 맞는 불변식이 아니었다.
PC·Android 부품은 이미 실행마다 새로 관측하도록 선언되어 있다. 또한 임의 shell/python은
기기 밖 파일·네트워크에도 영향을 줄 수 있어 기기 ID만으로 쓰기 범위를 좁힐 수 없다.
`unknown_write_resources` 무효화는 유지한다. 이를 제거하거나 일반 원격 코드를
읽기 전용으로 선언하는 수리는 하지 않는다.

이 경계를 확인하다 **반대 방향의 결함**을 재현했다. 쓰기 없는 `self:limb list`·
`limbs:guestpc info/history` 프로그램은 외부 연결 상태가 바뀌어도 새 실행의 reuse에서
이전 “연결됨”을 반환했다(신규 시험 3개 모두 실패). 두 액션의 기존 `per_run` 선언으로
읽기를 매 새 실행마다 갱신한다. 같은 실행의 resume은 원래 관측 영수증을 복원한다.
장치 전송은 대역으로 검사했으며 실제 기기 연결을 끊거나 설정을 변경하지 않았다.

과거 관측만으로 보고서를 고칠 때는 명시적 결과 참조를 입력으로 전달한다. 이 구분을
PC·Android·긴문장 훈련 가이드와 IBL 명세에 반영했다. 임의 원격 코드의 쓰기 발자국
정밀화는 별도 계약 설계가 필요한 최적화 후보이며, 현 보수적 동작을 미수리 결함으로
계속 세지 않는다.

### 나머지 누락과 검증

- 연결·활성·권한·화면 문맥 거절 뒤 같은 변경을 원시 전송으로 우회하지 않도록 가이드를
  보완했다. 이미 접수한 작업은 원 영수증·history 및 취소 후 종료 확인으로 처리한다.
- 87회차 뒤 남은 설치 검사에 Android 관용구 두 개를 포함하고, 자식 환경 검사에
  화면 문맥 전달을 명시적으로 대조했다. PC Chrome의 `window_id/tab/expected` 인자
  설명도 등록부에 보충했다. 검사 조건을 삭제하거나 실행 검사를 건너뛰지 않았다.
- 신규 의존성 회귀 8개는 검사 안 공유·호출별 증거 사본·실행 전 재검사·원문/등록부/
  환경/새 import 변경·계약 특수화 변경·예외 뒤 정리를 검증한다. 신선도 회귀 3개는
  새 실행 갱신과 같은 실행 복원을 함께 확인한다.
- 최초 직접 검사 99개는 assertion이 모두 통과했지만 검사 도중 문서를 편집해 저장소
  변경 감시가 실패했다. 후속 직접 검사와 최종 종합 회귀는 편집 없이 수행했다.
- 최초 종합 회귀는 샌드박스의 브라우저·포트·중첩 Seatbelt 제한으로 실패했다.
  실제 누락 3개와 신규 시험의 직접 실행 진입점을 보완한 뒤 관련 **59개 통과**.
  정상 권한 최종 비-system **11,371 passed·1 skipped·0 failed**,
  Python 작업자·어휘 아카이브/배포·전체 긴문장 재생 system **79 passed**.
  어휘 정합·Android 몸 번들·층 구조·은퇴 계약 관문을 통과했다.
- 재기동 제어자의 `restart --wait`가 중단 작업 없이 `restarted`를 반환했다.
  실제 `/ibl/execute`에 같은 프로그램을 `check:true, origin:training`으로 제출해
  HTTP 200·**2.207초·ok=true·executed=false·issues=[]·guards_total=1,240**을 확인했다.
  `status:incomplete`는 보존된 실행 시 검사이며 기기 동작의 완료를 뜻하지 않는다.

남은 범위: 81·83회차의 EXECUTE 답변에서 미확인 기능 단정·부분 후기를 전체로
일반화하는 현상, 84회차의 일부 영어 진행 문구는 해결됐다고 주장하지 않는다.
85·86회차 Safari 실기 timeout 원인, 폰 UI 계약 APK 설치·Android STALE_SCREEN 실기,
원격 맥 연결 안정성도 미검증으로 유지한다. 이번 수리의 성공으로 덮지 않는다.
