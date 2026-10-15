# 73회차 — 원격 하드웨어들의 사용: 여섯 몸에 같은 점검을 나눠 맡기고 한 곳에 모으기

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS`, 시작 `4e89fcc5`. 훈련 15:56~16:34 KST(38분, 상한 60분 안). 수리·회귀·수리 후 재실행 16:34~16:40 은 별도.
훈련자 IBL 은 기본(v4 → v6 재실행)·변형(v7) 모두 실행 종료, 과제는 **부분 달성**(§3 판정).
설계 [LONG_SENTENCE_REMOTE_HARDWARE_FLEET_DESIGN_2026_10_15.md](../../../LONG_SENTENCE_REMOTE_HARDWARE_FLEET_DESIGN_2026_10_15.md),
사전 계약 [task.md](task.md). 수리는 §4·§5, 되먹임은 §6.

## 1. 과제·조건

자연어 요구는 task.md 와 같다. 입력은 합성 12행([fixtures/sample.json](fixtures/sample.json), 한글·NFD·일본어·이모지·CRLF·탭·백슬래시·따옴표·빈 이름)
— 기기 처리의 바이트 보존을 통제하려는 선택이고, **기기는 전부 실물**(허브 명부의 활성 등록 6: PC 4 + 폰 2)이다.
원격 처리 부품 [fixtures/process.py](fixtures/process.py) 는 표준 라이브러리만으로 12행×2·합계·기기 신원을 쓴다. 설치·판정·보고 로직은 없다.

실행 전 실측(15:56~16:05): 백엔드는 다른 세션의 의도적 정지 상태여서 `backend/api.py start` 로 기동(15:57 healthy).
연결 3(맥12 darwin · KHJoffice windows · 삼성0 Android 16 arm64), 미연결 3(맥26·tv1·삼성1). 세 폰·PC 모두 `execution_contract` 없음(삼성0 ops `ibl/info/media`).
**훈련자 기본 실행 때(16:08) 여섯이 모두 연결**돼 있었고, 두 번째 기본(16:11)에서 맥26 이, 변형(16:14)에서 맥26 이 다시 끊겼다 — 실기기 조건은 10분 사이에도 바뀐다.

격리: 소리·화면 캡처·입력 주입·설정 변경 0. 쓰기는 중앙 회차 폴더·PC `~/indiebiz-training/fleet/73/<실행자>/`·폰 `outputs/long_sentence_imagination/round73/<실행자>/` 만.
사진은 폰이 저장한 경로·크기·해시만 다루고 내용은 보지도 옮기지도 않았다. 변형의 `pause` 는 운영자가 걸고 풀었다(16:13:18 on → 16:15:25 off, 재확인 paused:false).

## 2. 작성

분해: 명부(활성만, device_id 고정) → 몸마다 독립 가지(`[table:each]{parallel:3,on_error:"collect"}`): 문진(info, 멈춤·미연결은 이유만) → 능력표(**info 가 신고한 os·tools·ops 로 방식을 고름**: `pc_shell_python` / `phone_ibl` / `phone_python` / `unsupported`) → 상태표(PC 는 OS 별 한 방 셸 `KEY=값`, 폰은 info 카드 + 라디오 상태 하달) → 처리(PC: 파일 보내기 2 → 셸 python → 가져오기 → 중앙 재독 / 폰: 하달 IBL 안에서 self:write/read 왕복·계산) → 사진 연쇄(폰 촬영 → 폰 폴더 해시 → transfer 신고 없으면 "collect" 에서 멈춤) → 보고(JSON+한글, 재독 assert). 변형은 같은 프로그램에 `previous` 를 넣어 몸별 재사용·사진 재촬영 0·해시 재확인.

참고 자료: 조합 교재·문법 전문·`describe`(외부PC 관용구 5·guestpc·limb·write/read/each/task·sense:see·self:list) · 원격 PC/폰 가이드 · 65·66회차 프로그램의 관용구 호출 모양. 10-13 폰 손발·10-15 계약 1 구현을 이미 읽은 영향은 분리할 수 없다.

| 판 | 검사 | 바뀐 것 |
| --- | --- | --- |
| [v0](base_v0.ibl) | SYNTAX, **위치 없음**(`frames:[]`, line 2 = 보간 조각의 줄) | 최초 초안 |
| [v1](base_v1.ibl) | 같은 SYNTAX | 레코드 `+` 병합·줄 첫 `?` 삼항 제거(원인 아니었음) |
| [v2](base_v2.ibl) | SYNTAX, 이번엔 **위치 190:52** + 한글 힌트 | 이분 탐색 8조각으로 원인 확정: `f"…"` 안 `"${var}"`(따옴표 속 보간) → `${json($x)}` 리터럴로 |
| [v3](base_v3.ibl) | READONLY `$i`(26행) · MISSING_FIELD 6(폴백 레코드) | 보간 안 `get($it,"a")` 큰따옴표 → 변수로 |
| [v4](base_v4.ibl) | **통과(incomplete)** → 기본 실행 1 | `$i`→`$inf`, 폴백 레코드 전 필드 |
| [v5](base_v5.ibl)·[v6](base_v6.ibl) | 통과 → 기본 실행 2 | 실행 뒤 수정: 실패 가지가 기기 신원을 잃음(색인 짝맞춤) · **사진 대상이 `$기기[0]`(=맥12)** 이던 오답 · `외부PC준비{환경조회:false}`(문진 info 재사용) |
| [v7](base_v7.ibl) | 통과 → 변형 | 폰 해시: `self:list` 에 파일 경로를 줘 `Not a directory` → 폴더+pattern 조회 함수, 재사용 경로는 해시 재확인 |

검사 수정 주기 4(v0→v4), 실행 뒤 수정 주기 2(v5·v6 한 묶음, v7). 작성 시작 16:00 → v4 통과 16:08(8분, 이분 탐색 포함) → v7 16:14.

## 3. 실행·결과

| 실행 | 판 | 벽시계 | 기기 | 결과 |
| --- | --- | ---: | --- | --- |
| 기본 1 | v4 | 73.5초 | 6 연결·6 응답 | 5/6 처리 전건(맥12·KHJoffice·tv1·삼성1·삼성0), **맥26 실패**(`외부PC준비` 안 두 번째 info 동기 30초 초과 — 작업은 뒤에 succeeded), **사진 미시도**(훈련자 오답: 대상이 PC) |
| 기본 2 | v6 | 71.5초 | 6 연결·5 응답 | 5/6 전건, 맥26 은 **문진 info 자체가 30초 초과**(작업 `77b167f5` 는 queued 로 남음), 삼성1 촬영 성공(1.85MB)·**폰 해시 null**(`self:list` 파일 경로) · collect 에서 정직 정지 |
| 변형 | v7 | 12.9초 | KHJoffice paused · 맥26 미연결 | 재사용 4(맥12·KHJoffice·tv1·삼성1·삼성0 중 성공 5 — 모두 재접수 0), 멈춘 기기 `paused` 이유만, **재촬영 0·해시 재확인 성공** `89f30f6b…` 1,853,398 B, 기본 산출물 해시 불변 `947cd0cd…` |

독립 검증기 [harness/verify.py](harness/verify.py): 처리 성공 기기 전부 12행 id·result·name **바이트 일치**(NFD·CRLF·이모지 포함), 합계 156, 신원에 device_id·호스트명·시각(맥12 Python 3.9.6·KHJoffice 3.13.1·tv1 3.12.10·폰은 body:phone).
상태표: 맥12 `POWER=InternalBattery 100%; charged / DISK_FREE=114Gi / VOLUME=50`, KHJoffice·tv1 `ac_or_no_battery / 198.7GB·9.8GB / VOLUME unavailable`, 폰 둘 `라디오 재생 없음`, 전원·디스크·음량 `unavailable`(폰 사전에 조회 어휘를 찾지 않았음 — 정직 공백).
멈춘 KHJoffice 의 history: 변형 뒤 새 작업 0(마지막 16:12:07 기본 2 의 fetch).

**판정**: 검사 통과 / 실행 정상 종료 / 과제 **부분 달성** — T1·T2·T3·T5·T8·T9 충족, T4 는 응답 기기 5/5 전건(맥26 은 응답 안 함 = T2 로 처리), **T6 사진 연쇄는 설계 예측대로 "collect" 에서 멈춤**(폰 transfer 미지원), PC 재계산 미실행=미검증, T7 격리 충족. 기본 1 의 사진 미시도는 훈련자 오답으로 기록한다.

### 3-1. 독립 시스템 AI (ep4788 기본 · ep4789 변형)

같은 자연어([request.txt](request.txt))와 입력 사본(`agent-input/`)·출력 위치만 주었다. 훈련자 종료·전 작업 회수 뒤 시작했고, 두 실행자는 같은 실기기를 쓰므로 겹치지 않았다.

| 실행 | 벽시계 | 도구 | 모델 입력/출력(캐시 읽기 별도) | 결과 |
| --- | ---: | --- | --- | --- |
| 기본 ep4788 | 779.7초 | execute_ibl 17 · Bash 15 · TaskStop 1 | 6,280,950 / 47,931 (cache_read 5,896,114) | **5/5 처리 전건·합계 156**(독립 검증기 일치), PC 3 = 셸+process.py+transfer, 폰 2 = IBL 하달(쓰기·읽기·each·reduce). 상태표가 훈련자보다 넓음: Windows 음량 44%/29%(Core Audio COM 읽기), 재생 피크 0, 드라이브별 여유. 사진 삼성1 1,852,429 B `fe69470a…`, collect 에서 정직 정지. 명부 24건 전부를 세고 폐기 14·해제 3·휴대형 p0 를 구분 |
| 변형 ep4789 | 231.0초 | execute_ibl 11 · Bash 5 | 2,165,235 / 18,980 (cache_read 2,018,489) | **재사용 5·재접수 0**(앞 턴 result_ref 를 `read_result` 로 다시 읽음), 상태표만 새로, KHJoffice 의 `paused:true` 와 상태 요청 거절 코드 **`registration_unavailable`** 관측, 사진 재촬영 0·해시 재계산 일치, `variant/` 별도 저장 |

AI 가 Python/셸을 고른 이음새: 입력 해시 대조·결과 대조(`python3 -I` 로 중앙 검증), 소스 열람(`grep`) — **기기 조종은 전부 IBL**(원격 셸·IBL 하달·transfer·self:task). 폰 IBL 안에서 호스트명을 읽으려다(`/proc/sys/kernel/hostname`) 권한 거부로 첫 처리가 실패해 새 요청ID로 한 번 재실행했고, `[sense:host]` 를 폰에 보내 "존재하지 않는 액션" 거절을 받았다. 지시 범위 밖으로 간 것 둘을 **스스로 보고**했다: ① Windows 음량 1차 조회 스크립트에서 COM 메서드 순서를 잘못 적어 `SetChannelVolumeLevel` 이 잘못된 인자로 호출됨(E_INVALIDARG 거절, 전후 값 비교 증명은 없음) — **설정 변경 시도 1회**로 기록한다 ② `[sense:see]` 가 시험 폴더 밖(앱 사진 폴더)에 저장. 셔터음 여부를 앱 소스에서 확인(현장 청취 아님)한 것은 "소리를 내지 마" 조건을 과제 안에서 해석한 것이다.

독립성 주의: AI 의 첫 Bash 가 회차 폴더 전체를 `ls` 했다(`trainer/`·`trainer2/` 이름 노출). 이후 도구 호출에 훈련자 파일 읽기는 없다(궤적 33+16건 확인). 폰 결과 파일의 `sum` 이 `table:reduce` 봉투 그대로(`{value:156,…}`)인 것은 과제 달성에 영향 없는 모양 차이로 둔다.

| 축 | 훈련자(v6/v7) | 독립 AI |
| --- | --- | --- |
| 달성 | 부분(사진 연쇄 collect 정지=설계 예측, 맥26 미응답) | 같음 — 부분(같은 두 경계) |
| 기본 벽시계 | 71.5초(모델 호출 0) | 779.7초 |
| 변형 벽시계 | 12.9초 | 231.0초 |
| 원격 작업 수(훈련 전체) | 맥12 26·KHJoffice 26·tv1 28·삼성1 14+4실패·삼성0 13+3실패·맥26 2+2만료 | (위 합계에 포함) |
| 상태표 폭 | 전원·디스크·(맥)음량·라디오 | + Windows 음량·재생 피크·드라이브별·전원 계획 시도 |
| 수정 주기 | 검사 4 + 실행 뒤 2 | 자기 복구 2(IBL if-return 오류, 폰 권한) |

## 4. 발견

| ID | 분류 | 관측 | 재현·근거 |
| --- | --- | --- | --- |
| **L73-1** | 구현 결함(컴파일러) | 삼중 따옴표 f문자열의 리터럴 조각이 큰따옴표로 끝나면(`path:"${p}"` 모양) `ast.literal_eval(delimiter+조각+delimiter)` 가 Python `SyntaxError` 원문("unterminated string literal (detected at line 2)")을 그대로 던져 **IBL 위치·힌트 없음**(`frames:[]`). v0·v1 두 판이 여기서 막혔고 이분 탐색 8조각이 필요했다 | [evidence/base_v0_check.json](evidence/base_v0_check.json) · 최소 재현 `f"""say "${x}"""` · 시험 `backend/test_long_sentence_round73_repairs.py` |
| **L73-2** | 관용구 계약·낭비 | `외부PC준비` 기본 `환경조회:true` 가 문진에서 이미 받은 info 를 **동기 30초로 다시** 조회. 느린 몸(맥26, 방금 깬 arm64)에서 시간 초과 → 가지 전체 실패, 그 info 작업은 뒤에 `succeeded`(기본 1) | [evidence/probe_mac26_after_base.json](evidence/probe_mac26_after_base.json) · 훈련자 수리 = `환경조회:false`(v6) |
| **L73-3** | 외부 전제·상태 신선도 | 맥26 은 `list` 에 `connected:true` 인데 info 가 30초 안에 안 오고 작업이 `queued` 로 남아 뒤에 `expired`(2건). 10분 사이 연결 true→false→true 를 반복. `connected` 는 마지막 접촉일 뿐 응답 가능의 증거가 아니다 | variant_evidence · cleanup_terminal_check(expired 2) |
| **L73-4** | 구현 결함(폰 파일 발행) | 폰 안 `self:copy` 가 `[Errno 13] Permission denied: …/.publish-xxxx.jpg` 로 실패(AI 발견). 원인 = `output_publish.publish_file` 의 `os.link`(하드링크) 가 Android 앱 샌드박스에서 거부 | AI fleet_check incidents · 수리 §5 (폰 실기 검증은 APK 재빌드 뒤) |
| L73-5 | 어휘 공백(기록만) | 폰 IBL 에 배터리·저장공간·음량·호스트명을 **읽기만** 하는 어휘가 없다 — 두 실행자 모두 `unavailable`. 계약 1(Python) 설치본에선 AudioManager/StatFs 로 가능. 새 낱말 추가 대상 아님(헌법) | 훈련자·AI 상태표 |
| L73-6 | 계약(기록만) | `[sense:see]` 는 저장 위치 인자가 없어 앱 사진 폴더에 저장 → "쓰기는 전용 폴더에만" 조건과 충돌. 인자 추가는 어휘 증식이므로 가이드에 사실만 적음 | AI incidents · remote_phone.md 보강 |
| L73-7 | 작성 마찰(기록만) | `$i` 예약 이름 대입(51회차와 같은 재발), 폴백 레코드 필드 누락이 MISSING_FIELD 6건으로, f문자열 보간 안 큰따옴표 — 셋 다 검사기가 위치와 함께 잡았다(수정 1주기씩) | base_v3_check |

사진 촬영은 훈련자 2회(기본 2·수리 후 기본 3)·AI 1회 = **삼성1 에서 3장**, 전부 앱 사진 폴더에 남아 있고 내용은 어느 실행자도 보지 않았다.

## 5. 수리 (훈련 종료·전 작업 terminal 확인 16:35 뒤 적용, 재기동 16:36 ACTIVE)

| 대상 | 변경 | 검증 |
| --- | --- | --- |
| `backend/common/expression_parser.py` (L73-1) | 리터럴 조각 해석을 `_format_literal` 로: 원래 방식이 `SyntaxError` 면 이스케이프 안 된 `"`·줄바꿈만 이스케이프해 한 줄 리터럴로 재해석, 그래도 실패면 IBL `SYNTAX`(위치 포함) | 새 시험 5케이스 + 기존 `test_expression_parser.py`. **v0 재검사**: Python 원문 오류가 사라지고 184행의 진짜 오류(보간 안 큰따옴표)가 위치·힌트와 함께 보임([evidence/base_v0_check_after_repair.json](evidence/base_v0_check_after_repair.json)) |
| `backend/base/output_publish.py` (L73-4) | `_link_or_reserve`: `os.link` 이 EPERM/EACCES/EXDEV/EOPNOTSUPP 면 `O_CREAT|O_EXCL` 로 이름을 예약한 뒤 `os.replace` — 경쟁 작성자 파일을 덮어쓰지 않는 성질 유지, rename 정책도 동일 | 새 시험 2케이스(링크 거부 환경 발행·fail 거절·rename·다른 errno 는 그대로 raise) + 기존 `test_output_publish.py`. **폰 실기 검증은 미실행**(APK 재빌드·설치 필요) |
| `data/guides/guest_helper.md` (L73-2) | `외부PC준비` 행에 "이미 info 를 받았으면 환경조회:false" 한 문장 | 36KB 예산 안(33,777B) |
| `data/guides/remote_phone.md` (L73-6·해시) | `sense:see` 저장 위치·`self:list{path:폴더,pattern,hash}` 로 크기·해시 읽기 한 문장 | — |

새 어휘·op·인자 0. 수리 후 전체 프로그램 재실행: **기본 3**(v7, 75.4초, 응답 5/5 전건, 사진 촬영·폰 해시 `fec8a3e8…` 2,008,788 B, collect 정지) · **변형 2**(13.9초, 재사용 5·재접수 0·해시 재확인 일치·KHJoffice paused). 회귀: 새 시험 8건 포함 표현식 파서·발행 묶음 24 통과, IBL v2 전체·guestpc 관용구 묶음 388 통과(144초). 수리가 AI 경로 선택을 바꾸는지의 같은 요청 재실행은 **하지 않았다** — 두 수리 중 AI 가 밟은 것은 L73-4 뿐이고 그것은 폰 APK 재빌드 전에는 AI 경로에 닿지 않는다(미검증으로 남김).

## 6. 비용·낭비·잔여

- 상한 60분, 훈련 38분(준비·명부 실측 9 / 작성·검사 12 / 기본·변형 7 / AI 17 / 회수 1). 수리·회귀·재실행 약 6분 별도. 훈련자(작성자) 토큰 미측정, AI 는 §3-1 표(입력에 캐시 읽기 미포함).
- **필요했던 비용**: 기기마다 독립 가지·`on_error:"collect"`(한 몸 실패가 다른 몸 결과를 지우지 않음 — 맥26 실패 세 번 모두 나머지 5대 전건 보존), 중앙 재독·독립 검증기, 접수증 보존.
- **줄일 수 있었던 일**: ① L73-1 이분 탐색 8조각·2판(≈5분) — 컴파일러가 위치를 줬으면 1판 ② 기본 1 의 사진 미시도(훈련자 오답)로 기본을 두 번 돌림(원격 작업 ~30건 중복) ③ 외부PC준비 의 중복 info(L73-2) ④ AI 의 소스 grep 5회(셔터음·계약 1 확인)는 과제 해석엔 기여했지만 공개 교재에 그 사실이 있었다면 불필요 — remote_phone.md 보강으로 일부 해소.
- **보존한 품질**: 응답/멈춤/미연결의 구별, 중앙 대신 계산 0, 사진 내용 비열람, 재사용 영수증.
- **잔여·다음 회차 후보**: 폰 계약 1 APK 설치 뒤 같은 요청(사진 연쇄 끝까지 + L73-4 실기 검증 + AI 되먹임) · 맥26 연결 깜빡임의 헬퍼 쪽 원인(롱폴/절전) · `connected` 신선도 표기 · 폰 읽기 전용 상태 어휘의 자리(계약 1 Python 용례로 해소 가능한지) · 사진 3장 정리(사용자 결정).
