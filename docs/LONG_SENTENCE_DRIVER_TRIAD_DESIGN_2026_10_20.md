# 긴문장 상상훈련 설계 — 세 조작면 드라이버(Android 폰·Windows PC·Chrome)를 한 프로그램으로 (2026-10-20)

> 상태: **설계만. 실행 0.** 회차 번호는 시작 때 [원장](LONG_SENTENCE_IMAGINATION_LEDGER.md)에서 정한다(이 문서 작성 시점의 다음 번호 = 87).
> 절차 정본: [긴문장 상상훈련 가이드](../data/guides/long_sentence_imagination.md). 드라이버 정본:
> [제어 드라이버 설계](CONTROL_DRIVER_DESIGN_2026_10_20.md) §17·§18(Windows)·§18(Chrome)·"Android OS 드라이버 계약 정비"·"Android 접근성 UI 확장",
> 가이드 [pc_control.md](../data/guides/pc_control.md)·[android_control.md](../data/guides/android_control.md)·[chrome_control.md](../data/guides/chrome_control.md).

## 1. 회차의 계기 — 왜 이 셋을 한 회차에 묶는가

10-20~21 에 조작면 드라이버 셋이 같은 날 들어왔고, 셋 다 **단일 호출 실기만** 거쳤다.

| 드라이버 | 들어온 것 | 실기로 확인된 것 | 아직 밟지 않은 것 |
| --- | --- | --- | --- |
| PC제어 Windows 동형 | `pc_control_windows.ps1` 16동작, `action_platforms` 전부 darwin+windows | tv1 원격 경로 읽기 7·쓰기 7 verified(단일 호출, 허브 직접) | **IBL 긴 프로그램**에서의 연속 호출·원복, 독립 AI 의 선택, 원격 맥(맥26)과의 **같은 프로그램 대조** |
| Android제어 + UI 확장 | 하드웨어 17동작 공용 계약, UI 6동작(`ui_snapshot`·`app_launch`·`home`·`back`·`tap`·`type_text`) | 상태 읽기만(삼성0·삼성1·예나폰), 삼성0 pending→`Android제어확인` 회수 | **쓰기 동작의 재조회**(음량·화면), **UI 6동작 실기기 전부**(설계 문서가 "테스트 통과를 실기 완료로 해석하지 않는다" 고 명시), `STALE_SCREEN` 실기 |
| Chrome제어 | AppleScript 통로 status/open/switch/close, 탭 id 영구 판본 | 본체 1회 연쇄(open→switch→switch→close), STATE_CHANGED 1회 | **IBL 프로그램 안에서의 판본 전달**, 다른 가지와 병렬 실행 중의 판본 경합, 독립 AI 가 `limbs:browser`·화면 대신 이 드라이버를 고르는가 |

세 드라이버는 같은 결과 모양 `status/target/verified/result/task_ref/verification/evidence_ref/failure` 를 **주장**한다. 그 주장이 참이면 한 IBL 프로그램이
OS 와 통로의 차이를 모른 채 세 몸을 같은 행 모양으로 다룰 수 있어야 한다. 이 회차의 중심 질문은 그것이다.

**형식** = 가이드 §2 의 **이음새 입장 회차**(새 기기 경로·새 동작·새 드라이버 셋) + 주 과제 통과 뒤 **불변식 탐침 묶음**(§6) + §4-5 ① 독립 AI **1회**(이음새 입장 조건 충족, 2회가 아니라 1회 — 85회차에서 AI 2실행의 결론은 이미 고정됐고, 이번에 묻는 것은 "드라이버를 고르는가" 하나다).
85·86회차(본체 맥·Safari, 읽기만, 쓰기 격리 부재)에서 **못 한 것 = 쓰기와 원복**이 이번의 핵심 차이다.

## 2. 설계 시점의 명부와 실행 전 조건

`[self:limb]{op:"list"}` 10-20 23:30 기준, `revoked:false`·`registration.state:active`:

| 별칭 | device_id | kind / OS | 지금 연결 | 이 회차의 역할 | 모르는 것 |
| --- | --- | --- | --- | --- | --- |
| tv1 | `guestpc-70e163471313` | pc / Windows 10 Home, PS 5.1, 관리자 아님 | 연결 | **Windows PC 가지**(읽기 7 + 쓰기 4·원복) | Netflix 창이 아직 떠 있는지, 한국어 로캘 netsh 파싱 |
| 맥26 | `guestpc-9dc41d53987d` | pc / macOS(판 미상) | 연결 | **같은 PC 가지를 대상만 바꿔** 실행(OS 대조). 쓰기는 clipboard 왕복만 | 원격 맥 OS 드라이버는 §17 에 "같은 파일이 간다" 고만 있고 미실측 |
| 삼성0 | `guestpc-fc7b12fba936` | phone / Android(안방 스피커 폰) | 연결, execution_contract 1 | **폰 하드웨어 가지**(음량 절반→복원, 밝기 재조회) | APK 가 `ui_contract:1` 인지 |
| 예나폰 | `guestpc-f0fa1e3465a0` | phone / Android(거실 스피커 폰) | 연결, execution_contract 1 | **폰 UI 가지**(screen_on→ui_snapshot→app_launch→back→home→screen_off) | 잠금 화면 유무, 접근성 서비스 켜짐, APK 판 |
| 삼성1 | `guestpc-4e51c614b25b` | phone / SM-J730K Android 9(사용자 휴대 폰) | 연결 | **읽기만**(`status`). 쓰기·UI 금지 | — |
| 본체 | `__local__` + `app:com.google.Chrome` | macOS 26.6.2, Chrome 155 | — | **Chrome 가지**(status→open 배경 탭→switch→복귀→close) | 사용자가 Chrome 을 쓰는 중인지 |
| 맥12 | `guestpc-3fd796167b18` | pc / macOS | **미연결** | 변형 A 의 "등록됐지만 응답 없는 대상" | 전원 |

폐기 동명 등록(맥12·tv1·삼성1 각 1건 `removed`)이 같은 목록에 있다 → 49회차 L49-1 자리. **별칭이 아니라 위 device_id 로 고정**한다.

실행 전 조건(운영자가 확인·`task.md`에 기록):

- 백엔드 `data/restart_control/state.json` `phase:ACTIVE`. 동시 세션이 backend·data/packages 를 편집 중이면 시작하지 않는다(84회차 재기동 churn 4회).
- **다른 세션이 같은 손발을 쓰고 있지 않은지** — 기기당 일반 자리 2개(L51-1). 겹치면 그 기기는 "자리 점유" 로 기록하고 가지를 빼지 않는다.
- tv1 의 `presence`·`apps` 를 먼저 읽어 Netflix 등 사용자 재생 창이 있으면 **lock·sleep·wifi·shortcut 은 이번에도 제외**(§18 과 같은 사유). clipboard 는 **읽어서 보관한 뒤 쓰고 원복**한다.
- 폰 셋의 `status` 로 APK 판·`ui_contract` 를 읽는다. 예나폰이 `ui_contract:1` 이 아니면 UI 가지는 **`UI_DRIVER_UPDATE_REQUIRED` 거절 경로 관측**으로 바뀐다. APK 설치는 이 회차에서 하지 않는다(설치 ≠ 훈련, 설치 뒤 재실행은 되먹임 후보). 접근성 서비스가 꺼져 있으면 사용자가 켠다(폰 설정, 회차 밖).
- 예나폰의 잠금 여부를 적는다. 잠금이 있으면 `app_launch` 가 전면으로 못 오는 것은 **드라이버 결함이 아니라 OS 조건**이며 그렇게 기록한다.
- 본체 Chrome 창 수·현재 탭을 `status` 로 적고, 사용자가 Chrome 을 쓰는 중이면 Chrome 가지는 사용자가 **손을 뗀 뒤** 돌린다(찰나의 탭 전환이 보일 수 있다는 계약 effect).
- 기준 리비전·dirty 파일(현재 Windows·Chrome 작업이 **미커밋**)·세 가이드 판본·헬퍼/APK 판본을 적는다.

## 3. 주 과제 — 시스템 AI 에도 그대로 줄 자연어 요구

> "집 안 기기들로 **저녁 영상 시청 준비**가 되는지 점검하고 준비해 줘. 거실 TV 에 붙은 Windows PC(tv1)는 화면·전원·사용자 입회·실행 앱·네트워크 상태를 읽고,
> 60초 동안 잠들지 않게 잡았다가 풀어 주고, 클립보드에 오늘 볼 링크 `https://example.org/tonight` 를 넣었다가 **원래 내용으로 되돌려** 줘. 메모장을 최소화로
> 띄웠다가 닫아 줘. 안방 스피커 폰(삼성0)은 미디어 음량을 **절반으로** 낮췄다가 끝나면 **원래대로** 복원하고, 밝기 설정을 읽어 둬. 거실 스피커 폰(예나폰)은
> 화면을 켜고 지금 화면을 읽은 다음 설정 앱을 열어 화면을 읽고, 뒤로 가서 홈으로 돌아온 뒤 화면을 꺼 줘. 내 휴대폰(삼성1)은 상태만 읽고 **아무것도 바꾸지 마**.
> 이 맥의 Chrome 에는 같은 링크를 **배경 탭**으로 열되 내가 보는 탭은 그대로 두고, 그 탭으로 갔다가 원래 탭으로 돌아온 뒤 **그 탭만** 닫아 줘.
> 같은 점검을 맥26 에도 보내되 거기서는 클립보드 왕복만 해.
> 기기마다 **시작 상태와 끝 상태가 같은지** 확인하고, 어느 동작이 실패·미확인이어도 나머지는 계속하고, 성공·실패·미확인을 구분한 JSON 보고서 하나로 남겨 줘.
> 실제로 소리가 났는지·사람이 보고 있는지·페이지가 다 떴는지는 확인한 것과 구분해 줘. 안 되는 기기는 건너뛰고 이유를 적어."

AI 에는 이 글 + 기기 별칭↔device_id 표 + 저장 폴더만 준다. 훈련자 초안·함수 이름·"드라이버를 써라" 는 주지 않는다. **무엇을 고르는가**(fn:PC제어/Android제어/Chrome제어 vs `limbs:screen`/`limbs:browser`/Python 직접)가 관측 대상이다.

## 4. 입력·격리·기본 상태

**쓰기 동작 선택 기준** 셋을 모두 만족하는 것만 실기로 보낸다: ① 드라이버가 **재조회 확인 범위**를 선언한다 ② 같은 드라이버로 **원복**할 수 있다 ③ 사용자 작업을 끊지 않는다.

| 몸 | 실기 쓰기(원복 짝) | 읽기 | 이번에 하지 않는 쓰기 |
| --- | --- | --- | --- |
| tv1 | keep_awake 60→allow_sleep · clipboard_write→clipboard_write(원문) · launch notepad→quit | display·power·presence·apps·clipboard·network·shortcuts | lock·sleep·wifi·shortcut·brightness(외부 모니터, 거절 경로만) |
| 맥26 | clipboard_write→clipboard_write(원문) | 같은 7종 | launch/quit(사용자 작업용 노트북) |
| 삼성0 | volume_half(music)→volume_restore | status·volume_status·brightness 설정 읽기(`status`) | 밝기·회전·토치·화면 |
| 예나폰 | screen_on→screen_off · app_launch(`com.android.settings`)→back(expect)→home | ui_snapshot ×3 | type_text·tap 좌표(설정 앱에 글 넣을 자리가 없고, 좌표 tap 은 탐침 §6 에서만) |
| 삼성1 | 없음 | status | 전부 |
| 본체 Chrome | open(about:blank 가 아닌 과제 링크, 배경)→switch→switch(복귀)→close(탭 id) | status | 창 닫기·시크릿·다른 탭 |

**기본 상태 스냅샷**: 각 가지의 첫 읽기(clipboard 원문·음량 단계·전면 패키지·창/탭 판본·앞 앱)를 `$baseline` 로 보관하고, 끝에 같은 읽기를 다시 해 **같음/다름/미확인** 3값으로 대조한다(84회차 L84-1 교훈: 2값 필터 금지). 클립보드 원문은 보고서에 **길이와 SHA-256 만** 싣는다(개인 데이터).

**격리**: 사용자 휴대폰 쓰기 0. 예나폰·삼성0 은 책상·스피커 거치 폰이라 손 뗌 조건이 자연히 성립한다. tv1 은 Netflix 재생을 끊을 동작을 뺐다. 본체 Chrome 은 배경 동작만이고 `activation_restored` 를 본다. 외부 발송·공개·구매·예약 0.

원자료·로그·보고서는 `outputs/long_sentence_imagination/YYYY-MM-DD_N회차/`, git 에는 `docs/experiments/long_sentence_imagination/round_N/` 의 비민감 프로그램·task·판정만.

## 5. 훈련자 프로그램의 책임 분해

전체 IBL 하나(edition 2, `/ibl/execute` `code`·`origin:training`·`project_id:study`, 85·86 과 같은 `transport.py` 재사용). 핵심 조합은 IBL, Python 하네스는 요청·응답 보존·독립 대조·탐침 외부 교란만.

```
[def:행]($면,$대상,$동작,$r)        # 세 드라이버 결과 → 공통 행. 드라이버가 같은 모양을 주장하므로 분기 없이 get 투영만
   {surface,target,action,status:get($r,"status"),verified:get($r,"verified",false)==true,
    scope:get($r,"verification.scope"|"verification_scope"),failure_code:get($r,"failure.code",null),
    task_ref:get($r,"task_ref",null),elapsed_ms,raw_ref:<증거 파일 경로>}
[def:PC가지]($대상,$쓰기여부)       # PC조회묶음 7종 → pending 은 PC제어확인 → (쓰기여부) keep_awake/clipboard/launch 와 원복 → 끝 읽기
[def:폰하드가지]($대상)             # status → volume_status → volume_half → volume_status → volume_restore → volume_status
[def:폰UI가지]($대상)               # status(ui_contract 확인) → screen_on → ui_snapshot → app_launch → ui_snapshot → back{expect} → home → ui_snapshot → screen_off
                                     # ui_contract 아니면 app_launch 1회만 보내 거절 코드를 행으로 남기고 나머지 건너뜀
[def:크롬가지]($url)                # status → open(expected:revision) → switch(새 탭) → switch(원래 탭) → close(탭 id, expected) → status(판본 == 시작 판본)
[def:원복대조]($before,$after)      # 3값: same / changed / unverified
```

최상위: `[self:limb]{op:"list"}` 로 연결 여부를 읽고 **응답한 기기만** 가지를 연다 → `[fn:PC가지]{tv1} & [fn:PC가지]{맥26} & [fn:폰하드가지]{삼성0} & [fn:폰UI가지]{예나폰} & [fn:Android제어]{삼성1,status} & [fn:크롬가지]` **병렬** → 행 결합·원복대조 → JSON `self:write` → `self:read` 재독 일치 → 요약 반환. 모든 가지는 `[try]/[catch]` 로 실패를 행으로 남기고 다른 가지를 막지 않는다(86회차 불변식: 실패를 정상 관측으로 바꾸는 폴백 없음, 실패 뒤 즉시 재전송 없음).

**분기 없는 `행` 함수가 설계의 핵심 검증기**다: 세 드라이버의 모양이 정말 같으면 `행` 에 `[if:$면==…]` 가 하나도 필요 없다. 필요해지는 자리가 곧 발견이다(§10 ①).

## 6. 변형과 불변식 탐침 묶음

**변형 A — 응답 없는 대상**: 같은 프로그램에 tv1 자리를 맥12(`guestpc-3fd796167b18`, 미연결)로, Chrome 창을 `2147483646` 으로. 기대: PC 가지 전부 `target` 거절·장치 전송 0·`[self:limb]` 목록 1회, Chrome `TARGET_MISSING`, 나머지 네 가지는 정상 완료, 기본 보고서 파일 SHA 보존.

**변형 B — 판본 경합(외부 교란)**: 하네스가 Chrome 가지의 `open` 뒤·`close` 전에 AppleScript 로 탭 하나를 더 연다 → `close` 는 `STATE_CHANGED` 로 변경 전 중단, 재전송 0, 보고서에 남은 탭 id 기록. 예나폰은 `ui_snapshot` 뒤 하네스가 `app_launch` 로 화면을 바꾼 다음 **옛 snapshot_id** 로 `back` → `STALE_SCREEN` 실행 전 거절, 폰 실행 0.

**탐침 묶음**(각 수 초, 주 과제·변형 통과 뒤, 발견은 바로 `backend/test_*.py` 관문으로):

| # | 불변식 | 방법 | 통과 모양 |
| --- | --- | --- | --- |
| P1 | 대상 바꾸면 결과 바뀜·모양은 같음 | PC가지(읽기만)를 tv1·맥26·`__local__` 셋에 | 행 모양·키 집합 동일, 값(display id `DISPLAY1` vs 맥 id, `requests_basis`)은 다름 |
| P2 | 재사용이면 기기 호출 0 | 읽기 전용 PC가지를 `reuse:{run_id}` 로 | 전송 원장에 새 guestpc 전송 0, 결과 동일 |
| P3 | 소실 영수증은 unknown | Android `대기:0` pending 행의 task_ref 를 손상시켜 `Android제어확인` / PC 도 동형 | `unknown`·verified false·재전송 0 |
| P4 | 거짓 성공 모양 없음 | `apps` 행에서 이름 null 인 행 수, `verified:true` 인데 `result` 빈 객체인 행 수 | 둘 다 0(§18 발견 ② 부류의 관문) |
| P5 | OS 가 못 읽는 값은 null+basis, 0 아님 | tv1 `power.flags`·`sleep_holders`, `display.asleep`, `lid_closed` | null + `*_basis` 문자열, 숫자 0 아님 |
| P6 | 실패 모양 동형 | 세 드라이버의 거절 1건씩(없는 app·없는 package·없는 탭) | `failure.code` 가 셋 다 같은 자리·타입(registered-json/1 어댑터가 failure 객체를 문자열로 뭉개는지 — 10-20 기억 ★) |
| P7 | 원복 불변식 | §4 기본 상태 대조 | clipboard SHA·음량 단계·전면 패키지·탭 id 순서·keep_awake 프로세스 전부 `same`; `unverified` 는 허용하되 `changed` 0 |
| P8 | needs_front 동작은 배경 문맥에서 거절 | 예나폰 `app_launch` 를 `origin` 없이/`scheduler` 로 보낼 수 있으면 | 거절 코드, 폰 전송 0. HTTP 로 origin 을 못 바꾸면 "탐침 불가" 로 기록(과제 아님) |

## 7. 완료 조건과 증거

- **검사 통과·실행 종료·몸별 달성·원복 달성·실패 보고 달성**을 각각 센다. 하나의 "성공" 으로 합치지 않는다.
- 기본: 응답한 기기 수 = 가지 수, 각 가지의 행 수가 설계 표와 같고 순서 보존, `verified` 수 / `unknown` 수 / `failed` 수 / 거절 수 보고. 쓰기 행은 **재조회 행이 바로 뒤에** 있어야 verified 로 센다.
- 원복: P7 전부 `same` 또는 `unverified`(사유 포함). `changed` 1건이면 회차는 "달성" 아님.
- JSON 저장 후 재독 일치, 변형 뒤 기본 파일 SHA 보존.
- 미검증 명시: 실제 소리·사람 입회·페이지 로드·Windows 화면 잠듦·설정 앱의 어느 페이지인지.
- 증거: `evidence.json`(요청·응답·전송 원장 발췌·시각), 드라이버별 호출 지연표(첫 호출/둘째 호출 분리 — Windows Add-Type 16~24초), 세 가이드 판본·APK 판.

## 8. 두 실행, 예산, 기록

- **훈련자**: 자료 준비·작성·검수·실행·변형·탐침·진단 합해 60분, 시작 때 상한 시각을 적고 늘리지 않는다. 수정 주기는 횟수·이유 기록. 같은 원인 2주기 무진전이면 최소 재현만 남기고 멈춘다. 작성자 토큰 미측정, 프로그램 모델 호출 0 예상(원장으로 대조).
- **독립 AI 1회**: `POST /system-ai/chat` `{"message": §3 원문 + 별칭표 + 저장 폴더, "origin":"training"}`, 보내기 전 `episode_log` 마지막 id 기록. 변형은 보내지 않는다. 회수: `supervision.tool.started/finished`(fn:PC제어/Android제어/Chrome제어 호출 수, `limbs:screen`·`limbs:browser` 호출 수, Bash/Python 호출 수), `model.usage` 역할별, `recall.presented/used`(세 가이드·연결 손발 블록이 떴는가), 벽시계, 산출 JSON 을 훈련자와 같은 완료 조건으로 대조. **AI 가 돌 동안 하네스는 Chrome·폰을 건드리지 않는다**(L44-5 오배송 재발 금지).
- 비교표 한 장: 달성(몸별)·시간·호출·토큰·화면 조작 수·원복 결과. 표본 1 을 일반화하지 않는다.
- 원장에 시작 항목·형식(이음새 입장+탐침+AI 1회)·이유를 적는다. 발견은 L{N}-k 로 번호, 수리는 별도 작업.

## 9. 이번 회차에서 하지 않는 것

APK 설치·헬퍼 교체, tv1 lock/sleep/wifi/shortcut, 삼성1 쓰기, type_text·좌표 tap 의 실과제 사용(탐침 전용), Windows Chrome(통로 없음 — 확장 쪽 후속), 원격 맥의 Chrome(미구현), 거실TV(network-api) 제어, 창 앞으로/창 목록(needs_front 미구현), 새 낱말·새 op·드라이버 코드 수정(발견은 기록, 수리는 별도). 합성 자료는 없다 — 전부 실기기·실원천이며 합성은 부재 대상 ID·창 번호·손상 영수증뿐.

## 10. 예상 발견 자리(가설 — 확정하지 않는다)

① **결과 모양 불일치**: Chrome제어는 `self:script` 직접(registered-json/1, 실패가 `error` 문자열), Android/PC 는 `fn:` 함수(failure 객체) → `행` 함수에 분기가 필요해지는 첫 자리. ② Windows **첫 호출 지연**(Add-Type 16~24초)이 `PC조회묶음` 7종 합산으로 `timeout:60` 을 넘겨 묶음 전체가 거짓 timeout. ③ 예나폰 **잠금/화면 꺼짐**에서 `app_launch` 가 전면으로 못 오고 `verified:false`·후속 관측 8회로 끝남 — 드라이버는 정직하나 "화면 켜기 ≠ 잠금 해제" 를 보고서가 구분하는가. ④ 폰 셋 **APK 가 `ui_contract:1` 이 아님** → UI 가지 전체가 거절 경로. ⑤ 맥26 원격 맥 OS 드라이버 **첫 실측**: 헬퍼가 `pc_control_mac.py` 를 받는지, `lsappinfo`·`caffeinate` 가 원격 세션에서 도는지. ⑥ tv1 `clipboard_write` 원복이 **Netflix 창 활성 상태**에서 Set-Clipboard 권한/포커스에 걸리는가. ⑦ 병렬 `&` 여섯 가지가 **같은 헬퍼 통로**(tv1·맥26)에 동시에 들어갈 때 L51-1 일반 자리 2개 제한. ⑧ 독립 AI 가 연결 손발 블록·가이드를 **회상받고도** 폰 UI 를 `limbs:screen` 이나 Python adb 로 가는가(85회차에서 PC 는 드라이버를 골랐다). ⑨ Android `volume_restore` 가 폰 안 영수증의 외부 변경 감지로 **복원을 거부**하는 경우(사용자가 그 사이 음량을 만졌을 때)를 `changed` 가 아니라 `unverified` 로 보고하는가.

어느 것도 회차 전에 수리하지 않는다. 밟힌 것만 L 번호로 남긴다.
