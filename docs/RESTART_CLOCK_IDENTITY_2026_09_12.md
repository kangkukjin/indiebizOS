# macOS 시계 보정 후 백엔드 시작·공개파일 연결 장애

2026-09-12 정본 맥에서 재현하고 수리했다. 변경은
`backend/base/restart_process.py`의 프로세스 신원 생성·생존 판정·자손 수집에 있다.

## 원인과 증거

- macOS `timed` 원장은 00:08:19.497에 NTP에 따라 시스템 시각을 약
  1.986862초 뒤로 보정했다. 그 직후 로그 시각이 00:08:17.531로 돌아간다.
- 설치된 psutil 7.2.2의 macOS `create_time()`은 모듈 import 당시와 현재의
  부팅 시각 차이를 보정한다. 장수 제어자와 새로 시작한 워커가 같은 프로세스의
  출생 시각을 다르게 관측할 수 있다. 기존 코드는 이 값의 완전 일치로 생존을 판정했다.
- 제어 상태에 `recovery_reason=active_crash`가 남았지만 이전 워커는 여전히
  8765 포트에서 `/health`에 HTTP 200을 반환했다. 이후 상태는 `worker=null`,
  `STOPPED`가 되어 실제 워커의 소유권을 잃었다. 새 시작은 포트 점유 때문에 실패했다.
- 공개파일용 cloudflared 로그에는 같은 00:08:19에 SIGTERM 종료가 기록됐다.
  터널이 복구되지 않아 공개 `/manifest`가 HTTP 530을 반환했다.
- 실제 시스템 시각을 바꾸지 않고 진단 프로세스 안에서 psutil의 초기 부팅 시각을
  2초 이동시키자 기존 `alive()`는 같은 살아 있는 워커를 False로 판정했다.
  주입을 제거하면 다시 True가 되었다.

## 수리

macOS의 출생값 읽기를 `_birth_time()` 한 곳으로 모았다. psutil 내부
`create_time(monotonic=True)`를 사용하여 커널의 보정 전 출생값을 얻는다.
macOS에서는 이 값도 epoch 형식이므로 정상적으로 기록된 기존 영수증을 유지한다.
해당 옵션 이전 psutil에는 보정이 없으므로 공개 메서드로 호환한다. 다른 OS의
출생값 계약은 유지한다. PID만 비교하거나 시각 오차 허용 범위를 넓히지 않는다.
호환 근거는 upstream의 [7.1.3 macOS 구현](https://github.com/giampaolo/psutil/blob/release-7.1.3/psutil/_psosx.py)과
[7.0.0 macOS 구현](https://github.com/giampaolo/psutil/blob/release-7.0.0/psutil/_psosx.py)이다.

당시 잔존 워커는 활성 사용자 턴이 없음을 확인하고 저장된 PID·출생 영수증을
대조해 정상 종료했다. 복구 전 상태는
`data/_backups/2026-09-12_restart_clock_recovery/`에 보존했다(제어 비밀 포함,
git 제외). 종료 표식은 손으로 변경하지 않았다. 기존 시작 앱으로 재실행해
`ACTIVE`, `ready`, `known`과 공개파일 터널 복구를 확인했다.

## 검증

`test_restart_process.py`에 앞·뒤 2초 보정의 실제 프로세스 회귀를 추가했다.
워커와 자손의 신원이 유지되고, 다른 출생값의 영수증으로 종료할 수 없으며,
일치하는 자손은 실제로 종료됨을 검사한다. 테스트는 임시 코드·데이터와 loopback
서버를 사용하고 실제 시스템 시계는 변경하지 않는다.

검사 결과:

- 시작·종료 및 이전 관련 수리 회귀: **73 passed**, 132.24초.
  `/tmp/indiebiz-restart-fix-tests.log`.
- 전체 backend 회귀: **3,917 passed, 1 skipped**, 255.37초.
  `/tmp/indiebiz-restart-full-tests.log`.
- 실제 Electron의 숨은 시험 창 닫기→재시작 2회: 각각 STOPPED와 다음 세대
  변경 확인(3.341초, 3.347초). 임시 데이터·포트를 쓰는 가벼운 시험 서버이며
  운영 모델 로딩 시간은 아니다. `/tmp/indiebiz-restart-electron-tests.log`.
- Android 몸 번들 재생성·`--check`, backend 층 검사와 `git diff --check` 통과.
- 운영 시작 앱이 오류창 없이 정상 화면을 표시하고, 제어 상태와 워커의 세대·코드
  digest가 일치했다. 외부 공개 manifest와 공개파일 목록 HTTP 200, 브라우저에서
  실제 저장장치의 하위 폴더 3개 표시를 확인했다. 공개 터널은 자동 기동으로 복구됐다.

새 회귀와 실행 시험은 정본 macOS에서 수행했다. 이 수리는 psutil 내부 macOS
메서드를 한 헬퍼에서 사용하므로 psutil 갱신 때 시계 보정 회귀를 유지해야 한다.
