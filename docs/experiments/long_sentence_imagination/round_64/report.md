# 64회차 — 원격 PC 설정 훈련과 정본 수리

**정본 수리 적용 완료. backend 전수 10,411 통과·13 건너뜀·실패 0. 중앙 백엔드 readiness=ready 확인. 훈련자 기본·변형은 수리 전 완료, 독립 AI는 연결 단절로 부분 수행했으며 원격 헬퍼 배포·수리 후 실기기 재실행은 미검증이다.**

## 조건과 실제 범위

정본 main, 시작 코드 `a40b2414ebfc0d529317aafb166fb0dbd1d31ecf`.
시작 2026-10-13 23:59:48 KST, 준비·훈련·진단 상한 60분, 수리·회귀 별도.
기준: [설계](../../../LONG_SENTENCE_REMOTE_PC_SETUP_DESIGN_2026_10_13.md),
[실사용 에피소드 4711 검토](../../../REMOTE_PC_SETUP_EPISODE_4711_REVIEW_2026_10_13.md).

사용자 요청에 따라 공식 `backend/api.py restart --wait --drain-timeout 30`을 실행했다.
요청 `6eddf14a4f7464bf0138e7c3dafbafc9`은 restarted, worker 49777,
generation `cb26b986925e03dc7815b4e737e29644`, health healthy·live_turns=[]를 확인했다.
tv1 미연결의 info 작업 `4f791addd2924e68a6496ae55b1b5973`은 취소·종료 확인했다.
실기기는 KHJoffice Windows/Python 3.13.1로 변경하고, 기존 IndieBiz 설치와 분리된
`C:/Users/kkukj/indiebiz-training/remote-setup/r64/{trainer,agent}`를 사용했다.

원래 설계의 전체 제품 설치·부팅·모델·Electron까지 완료한 훈련은 아니다.
실제 제품 어휘 로더 사본, 전용 venv, 12개 합성 입력을 처리하는 소형 앱과 HTTP 서비스로
설정→실행→검증→변형→영수증 회수를 시험했다. 전체 제품 부팅 및 모델/Electron은 미검증이다.
실제 PC 작업 중 원격 연결이 단절되어 이 경계를 확대하지 않았다.

## 작성·실행

[과제 원문](task.md), [최초 초안](drafts/main_v0.ibl), [실행본](drafts/main_v2.ibl).
공개 외부PC 관용구/액션 계약과 조합 교재를 조회했으며 이전 에피소드의 내부 코드를
이미 보았으므로, 훈련자 성공을 공개 교재만으로 얻은 독립 능력으로 평가하지 않는다.

- v0: `$row` 대신 `$it`, 지역 함수의 외부변수 명시 인자, nullable command_ok의 Bool 판정 오류.
- v1: 함수 인자와 Bool 수정. 보간 안 `${row.path}` 1곳을 놓침.
- v2: 보간 수정. 검사 issues=0, status=incomplete(동적 타입·분석 예산 경계), 실행 허용.
- 자료 폴더의 `installed/tools/` 누락은 실행 전에 수정했다.
- 전체 IBL 실행 **85.543초**, 정상 종료. 훈련 프로그램 수정 2주기, 원격 실행 재시도 0.

| 조건 | 훈련자 결과 | 독립 AI 결과 |
|---|---|---|
| 전용 환경 | venv 준비, 기존 Python의 시스템 패키지 공유 | 별도 venv, PyYAML 설치 로그 확인 |
| 입력 12건·문자 일치 | 기본·out2 결과 모두 일치 | 처리까지 도달하지 못함 |
| 기존 사용자 설정·결과 | preserve-me 유지, out 보존 | 최종 검증 미수행 |
| 서비스 | 응답 PID 15756·시험 루트 대조, 작업 정상 종료 | 기동하지 못함 |
| 변형·응답 손실 회수 | 같은 영수증/작업 ID, runs=[out,out2] | 연결 단절로 변형 미실행 |
| 어휘 기본 인코딩 | cp1252에서 exit 0; 후속 확인에서 문자 손상 | 따옴표 오류, 로더 자체 판정 미확정 |
| 모델·Electron | 미검증으로 구분 | 미검증으로 구분 |

원래 훈련 프로그램의 로더 검사는 패키지·도구 이름만 확인해 manifest 문자 손상을
놓쳤다. 따라서 정상 종료를 로더 검증 통과로 세지 않는다. 후속 독립 기대값 대조에서
cp1252 문자 불일치와 cp949 UnicodeDecodeError를 확인했다.
첫 최소 진단은 Python 3.13 Path.read_text의 encoding='locale' 전달을 고려하지 못해
cp949 전환에 실패했고, 진단 v2에서 read_text의 미지정 인코딩만 대체하여 재현했다.
이는 실제 Windows 위에서 인코딩을 주입한 시험이며 이 PC의 기본 locale은 cp1252다.

## 독립 AI — 에피소드 4712

자연어 요구와 분리된 입력·출력 위치만 전달했다. 훈련자 초안·정답은 전달하지 않았다.
작업 `task_sysai_9f533b6e`는 중앙 succeeded(응답 생성 완료), 과제는 **부분 달성**이다.
00:12:51~00:22:34, **582.885초**. execute_ibl 22회, IBL 실행 이벤트 23회(내부 포함),
모델 round 33, billable_usage 8건. 입력 4,366,605 / 출력 26,003,
cache_read 4,001,186 / cache_create 356,630. 캐시는 입력의 세부 항목이므로 더하지 않는다.
훈련자 모델 토큰은 미측정이다. 모든 trajectory source는 training, 증류는 하지 않았다.

AI는 원격 쓰기·전송·환경 확인을 IBL로 묶었고 10파일 전송 지문을 확인했다.
`cmd` 안 python -c의 따옴표 오류로 기본 로더 검증 전에 실패했다. 설치 성공 로그와
후속 확인 실패의 exit 1을 구분해 보고했다. 회상 후보는 조회했으나 기존 외부PC 준비·
작업확인 관용구 대신 직접 guestpc 호출 함수를 구성했다. 비용 절감 효과는 미검증이다.

00:16:00 이후 헬퍼 연결이 끊겼다. 새 실행을 계속 성공으로 취급하지 않고 증거 파일에
미완료 조건을 남겼으며, queued 3건을 취소했다. 검수는 UNKNOWN으로 남았다.
PC 절전·네트워크·헬퍼 종료 중 원인은 확정하지 않았다.

## 발견과 수리안

| ID | 분류·근거 | 공통 수리와 검증 |
|---|---|---|
| L64-1 | 구현: UTF-8 manifest/tool/actions/activation를 기본 locale로 읽음. cp949 예외, cp1252 조용한 손상 | vocabulary_state와 부팅 영수증·remote_steps 계획/원장 읽기에 UTF-8 명시. 수정 전 8실패→수정 후 8통과 |
| L64-2 | 완료 판정: 에피소드 4711의 FAILED 세대 혼동, 기존 CI가 health 루트·세대를 대조하지 않음 | remote_boot 관측기 + CI 공유. PID·생성시각·generation·인증된 runtime·health 루트·생존·관측 중 재기동을 검사 |
| L64-3 | 구현: 헬퍼 로그의 byte 조각을 즉시 문자열로 변환. 최소 재현에서 한글😀→���글😀 | 파이프별 UTF-8 미완성 바이트 보존, 이벤트/꼬리 rune 경계 유지. Windows 셸 UTF-8 표준출력. Go 회귀 통과 |
| L64-4 | 자료·외부 전제: 헬퍼 단절로 시작된 작업 결과와 취소 종료를 회수하지 못함 | 새 작업 추가 중단, 미접수 작업 취소, 기존 ID 보존. 재연결 필요. 종료로 위장하지 않음 |
| L64-5 | 작성·검증: 정상 종료만으로 Unicode 로더를 통과시킴, AI의 다중 셸 따옴표 실패 | 파일·문자 자체의 독립 기대값 비교, 설치/검증 분리 및 완료 범위 교재 보강 |

W3 실패 단계 중단과 검증만 재시도는 기존 remote_steps 계약으로 해결된다. 회귀에서
exit 7 보존·후속 미실행·검증만 재시도·중복 효과 방지를 확인했다. 새 어휘는 추가하지 않았다.

수리안: [pending-repair.patch](pending-repair.patch), 적용 전 파일 지문:
[evidence/repair_manifest.json](evidence/repair_manifest.json).
격리 위치 `/tmp/r64-repair-stage`, git 저장소/복제본이 아닌 개별 파일의 시험용 오버레이다.
위 패치·지문은 적용 전 검토용 기록이다. 2026-10-14 사용자 지시에 따라 정본에 적용했고,
아래 후속 검증에서 검사 진입점·CI 트리거·교재 분리와 기존 테스트 모의 객체도 보완했다.

## 검증·남은 일

- 격리 Python 회귀 38개 통과: 어휘 13, 단계 실행 16, 부팅 판정 9.
- 격리 헬퍼 Go 전체 검사 통과. Unicode 분할과 꼬리, stdout/stderr 경계, EOF 검사 포함.
- Windows amd64 테스트 실행파일 교차 컴파일 통과. Windows 실제 실행은 미검증.
- 새 관측기로 실제 중앙 백엔드의 올바른 제어자·세대·루트·readiness=ready 확인.
- 적용 전 git apply --check 통과. 이후 라이브 적용·Android 번들·전체 backend 회귀 완료.
  원격 Windows의 수리 후 원래 전체 프로그램과 독립 AI 재실행은 미수행.
- 포트 충돌 fallback 분기는 코드에 있지만 이번 실제 기본·변형에서는 발동되지 않아 미검증.

적용 전 보류 사유였던 작업은 원격 사본의 읽기 진단
`3f940b7cd55f4d0eaab253937d8b6ea8` 하나다. 00:16:01 started 후 결과가 없고
cancel_requested다. 중앙 AI 작업은 종료했지만 원격 종료와 같지 않다.
훈련 규약 §6의 모든 티켓 종료 조건에 따라 적용을 보류하고 PC 재연결을 요청했다.
훈련자가 추가한 로그 시험 `ba7d360ca99e4c9892b3b8363a4b0525` 및 AI의 queued 작업은
cancelled·terminal을 확인했다. 인위적으로 DB 종료 상태를 고치지 않았다.

사용자는 재연결 시도 후 **“그냥 수리해”**라고 지시했다. 앞서 고지한 원격 티켓 종료 대기를
중앙 수리의 선행 조건에서 제외하라는 지시로 받아 적용했다. 이는 원격 작업이 종료됐다는 뜻이 아니다.
KHJoffice의 진단은 마지막 관측상 cancel_requested·종료 미확인으로 남기고 DB를 고치지 않았다.
tv1의 추가 접속 확인 `e827de48c7844130bcdea8809e332f0d`는 cancelled·terminal을 회수했다.
남은 원격 검증은 해당 PC 연결 → 기존 작업 status/history 회수 → 종료 확인 → 헬퍼 배포 및
새 격리 폴더에서 원래 프로그램·변형·AI 재실행이다. 원격 배포와 원인 미확정 연결 문제를
이번 중앙 수리 완료와 혼동하지 않는다.

## 비용·낭비 검토

환경과 실제 출력 확인은 필요했다. 줄일 수 있는 비용은 v0 변수 규칙 오류, v1 보간 잔재,
AI의 셸 따옴표 재작업, 로더 exit 0만 확인해 뒤늦게 문자 검사를 추가한 부분이다.
사전 입력 스냅샷과 함수 인자·nullable 반환·문자 기대값 검수를 한 번에 준비할 수 있다.
기존 작업 영수증을 재사용하여 중복 처리 1회를 피했고, 원격 단절 뒤에는 재설치하지 않았다.
85.5초와 582.9초는 실행 조건·모델 포함 범위·완료 범위가 달라 성능 배수로 비교하지 않는다.
격리 수리안 작성·회귀·증거 정리는 훈련 성능에 합산하지 않는 별도 후속 작업이다.

## 정본 적용 후 검증 (2026-10-14)

선택기: 변경 5파일·backend 모듈 2개 → 전이 시험 619/673(92%), 허브 vocabulary_state.
이에 `backend/ -n auto --dist loadfile --ff`로 system을 포함한 전체를 실행했다.
첫 결과 10,406 통과·5 실패·13 건너뜀(239.08초). 새 test_remote_boot의 pytest 직접 실행
진입점 1건을 보완했다. 나머지 4건은 기존 YouTube 모의 객체의 `_phone.is_phone` 누락이었다
(관련 handler·테스트는 적용 전 HEAD와 동일). desktop 전제를 모의 객체에 명시했고
제품 코드·기존 assertion은 바꾸지 않았다. 관련 115개 통과(6.99초) 후 최종 전체는
**10,411 통과·13 건너뜀·실패 0, 227.60초**다.

- Go `go test ./...` 통과(19.004초), Windows amd64 교차 컴파일 통과. Windows 전용 실행 시험은 맥에서 건너뛴다.
- Android 몸 번들 재생성 완료(추적 산출물 변경 없음), 어휘 빌드 정합·backend 층·Windows 이식성 관문 통과.
- 실제 중앙 새 세대 `d694acd32409a71cec1e197585afa47d`, worker 51654의 ACTIVE·readiness=ready를 새 관측기로 확인했다.
- CI가 remote_boot.py 변경에도 실행되도록 경로 트리거를 추가했다.
- 가이드 크기 관문 초과를 해소하기 위해 기존 업데이트 절차와 새 검증 설명을
  [원격 PC 설정 검증](../../../REMOTE_PC_SETUP_VERIFICATION.md)으로 옮기고 진입 가이드에서 연결했다.
- 원격 Windows 배포, 전체 제품 설치·실제 모델·Electron, 수리 후 전체 과제/AI 재실행은 미검증이다.

검증 요약과 최종 파일 지문은 [repair_applied.json](evidence/repair_applied.json)에 보존한다.
