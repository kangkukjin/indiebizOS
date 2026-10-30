# 원격 PC 설치·업데이트·부팅 검증

원격 작업의 접수·관측·취소는 [외부 PC 가이드](../data/guides/guest_helper.md)를 따른다.
다음 절차는 설치 흔적과 실제 실행 성공을 구분한다.

원격 작업의 도구 수정은 중앙 정본에서 분리한다. `remote_install.py stage-tools --root 중앙루트
--output 중앙루트/outputs/작업/tools`가 실행 조리법과 의존 모듈을 링크 없는 파일 사본으로
준비한다. 사본에서 수정·검사·전송하며 중앙 실행 코드는 바꾸지 않는다. 분류·의식·실행 지침도
원격 설치와 중앙 자기수리를 실행 대상에 따라 구분한다. 이 작업 사본은 새 Git 저장소나
권한 샌드박스가 아니며, 임의 셸의 중앙 쓰기를 차단하는 보안 경계는 아니다.

### 원격 작업용 도구와 중앙 실행부 분리

원격 설정은 대상 PC의 작업이다. 먼저 실제 실행 중인 앱의 경로·사용자 데이터 경로와
업데이트할 설치 경로를 대조한다. Git 클론 갱신만으로 별도 설치 앱이 갱신됐다고 하지 않는다.
도구 결함을 만나면 중앙 정본을 편집하기 전에 아래 명령으로 작업 사본을 만든다.

```sh
.venv/bin/python3 scripts/remote_install.py stage-tools --root /absolute/central/indiebizOS --output /absolute/central/indiebizOS/outputs/remote-job/tools
```

반환된 폴더는 조리법과 필요한 모듈의 일반 파일 사본이며 중앙 코드로 가는 링크가 없다.
기존 폴더는 덮어쓰지 않는다. 사본에서 수정·검사하고 폴더 전체를 압축·전송해 대상 PC의
작업 폴더에 푼다. 대상 Python에 psutil이 있어야 한다. 사본의 `scripts/remote_install.py plan`
에 대상 PC의 `--root`·`--npm`을 주고, 사본의 `scripts/remote_steps.py`로 계획을 실행한다.
원격의 중단된 계획을 보완할 때는 기존 접수증·단계 상태를 먼저 확인하고, 계획이 참조하는
driver를 보존한 뒤 필요한 수정만 반영한다. 새 계획으로 완료 단계를 반복하지 않는다.

중앙 `scripts/`·`backend/`는 변경 감시 대상이므로 원격용 파일 준비를 위해 직접 편집하지 않는다.
공통 소스에 돌려놓을 수정은 원격 작업과 별도로 자기수리 경로에서 검증·반영한다.
중앙 실행부 변경이 반드시 필요한 경우에만 그 의존성을 보고한다. 중앙 재기동·자기수리 완료를
모든 원격 설정의 선행 조건으로 만들지 않는다.

**IndieBiz 업데이트 조리법** `scripts/remote_install.py`는 이미 존재하는 소스 저장소와
Git·지원 Python·Node/npm을 사용한다. 없는 런타임은 OS·아키텍처를 확인하고 먼저 설치한다.
조리법은 `remote_steps.py`·`remote_update_runtime.py`·`remote_boot.py`와
`backend/base/update_maintenance.py`를 함께 사용하며 실행 Python에 psutil이 필요하다.
구판 PC에 단일 스크립트만 덮어쓰지 않는다. 구판 앱을 정상 종료한 뒤 호환되는 조리법 묶음을
준비하고, 현재 돌고 있는 설치와 중복 실행하지 않는다. 갱신 실행자는 대상 앱의 자손이 아닌 외부 PC 헬퍼·터미널이어야 한다.

```sh
/absolute/python3 scripts/remote_install.py plan --root /work/indiebizOS --npm /opt/node/bin/npm --run-id update-1 --output /work/update-plan.json
/absolute/python3 scripts/remote_steps.py /work/update-plan.json
/absolute/python3 scripts/remote_steps.py /work/update-plan.json --status
```

조리법은 사용자 소스·번역 메모리 변경, staged 변경·분기 이탈을 거절하고 fetch→fast-forward, 충돌하는 비추적/무시 파일 보존,
Git 추적 위치가 유일한 중복 패키지의 잔재 보존, venv·core/tools/ml·브라우저·npm·native rebuild·빌드,
import coverage·pip check·HEAD 일치를 확인한다. 백업은 `data/_backups/YYYY-MM-DD_이름/`다.
`remote_install.GENERATED_FILES`에 명시된 전체 파일 생성물(배포 매니페스트·어휘 파생물·UI 번들)은
사전 검사에서 보존 가능 목록으로 보고한다. 업데이트 단계는 원본 바이트를 백업한 뒤 현재 HEAD로
복원하고 갱신한다. 생성물의 삭제·심볼릭 링크·staged 변경도 거절한다. 번역 교정이 들어갈 수 있는
`frontend/i18n/translations.json`과 산문이 섞인 문서는 이 목록에 포함하지 않는다.
백업 이후 파일이 달라졌으면 복원을 중단한다. 빌드 뒤 생성물이 다시 달라져도 다음 업데이트에서
같은 보존 절차를 사용한다. 사용자 변경을 버리거나 강제 reset/clean하지 않고, 기존 venv·API 키도 교체하지 않는다.
Git 파일명은 UTF-8로 해석하며 계획의 Python 자식에도 UTF-8 환경을 전달한다.
계획 생성 시 실행 스크립트를 `_backups`의 전용 driver 폴더에 보존한다. 소스 교체 후에도 같은
스크립트로 남은 단계·재개·복원을 수행한다. 새 driver는 `scripts/`와 필요한 `backend/` 모듈을
함께 보존해 대상 소스 교체에도 도구 의존성이 바뀌지 않는다. 최초 설치의 인증 설정·훈련용 선택 의존성은 포함하지 않는다.

**실행 중인 앱 갱신**: preflight → quiesce → 갱신/설치/빌드/검사 → resume-runtime 순서다.
quiesce는 제어자의 작업 접수를 닫고 기존 작업·자식·마무리가 끝날 때까지 기다린다. 불명·대기 한도는
강제 종료로 바꾸지 않는다. 백엔드 종료가 확인되면 Electron의 해당 실행 nonce에 창 닫기를 요청한다.
미저장 편집의 닫기 취소는 그대로 존중하며, 창·렌더러가 남으면 소스·의존성을 바꾸지 않는다.
종료 계약이 없는 구형 제어자/Electron은 첫 갱신 전에 사용자가 해당 앱을 정상 종료해야 한다.
프로세스는 정확한 저장소 경로·PID·출생 시각으로 확인하며 이름/포트 전수 kill은 없다.
프로세스 인자 중 OS가 파일 경로로 해석할 수 없는 값(Windows named pipe 등)은 경로 후보에서만
제외한다. 나머지 인자와 실제 대상 백엔드 탐색은 계속하며, 대상이 살아 있으면 갱신을 차단한다.

`data/runtime/update-maintenance.json`은 계획의 유지보수 소유 기록이다. 갱신 중 새 백엔드·Electron
시작은 거절하며, 복원 단계만 해당 토큰으로 시작한다. 각 변경 단계 직전에도 정지 상태를 다시 검사한다.
실패한 계획은 이 기록과 로그를 유지한다. 다른 run-id를 만들거나 원장을 지워 다시 시작하지 않는다.
빌드/설치 실패는 원인을 고친 뒤 같은 계획의 `--retry 단계ID`로 재개한다. quiesce의 거절이 끝났으면
`--retry quiesce`가 새 종료 요청을 만들고, 아직 진행 중인 종료 요청은 같은 ID로 관측한다.

원래 꺼져 있던 앱은 계속 꺼 둔다. 켜져 있던 백엔드/데스크톱은 새 프로세스로 복원하고 세대·코드 지문·
준비 상태를 검사한다. 데스크톱은 새 nonce·Git HEAD·페이지 로드 완료도 확인한다. 실제 모델 질의나
모든 화면 기능 검사는 별도다. 시작 응답이 유실되면 기존 프로세스를 관측하며 자동으로 또 띄우지 않는다.
시작이 실패해 **해당 설치의 모든 프로세스가 끝난 것을 확인한 경우에만**, 계획 안 driver의
`scripts/remote_update_runtime.py retry-start --root 절대경로 --run-id 기존ID --npm 절대npm`으로 명시 재시도한다
(이전 계획은 그 계획에 기록된 driver 경로를 그대로 사용한다).
이후 같은 계획을 재개해 마지막 검증을 마친다. 검사 명령/로그는 해당 run-id의 `remote_steps`·
`remote_updates` 원장에 남는다. 유지보수 기록의 수동 삭제는 정상 복구 절차가 아니다.

**최초 설치와 실제 부팅 확인**: `remote_install.py`는 기존 저장소 업데이트다. 새 설치는
저장소의 `scripts/bootstrap.py` 절차를 사용하고 설치 명령과 검증 명령을 각각 기록한다.
PowerShell에서 외부 명령 뒤 로그를 출력해야 하면 `$code=$LASTEXITCODE`로 즉시 보존하고
마지막에 `exit $code`로 반환한다. 로그 출력 성공을 설치 성공으로 바꾸지 않는다.

백엔드를 시작했다면 시작한 제어자의 PID를 보존하고 다음 관측기를 호출한다.
기존 제어자를 재사용한 재시작이라면 해당 요청에서 받은 `--generation`도 지정한다.

```sh
/absolute/python3 scripts/remote_boot.py --root /work/indiebizOS --controller-pid 1234 --generation REQUEST_GENERATION --port 8765 --timeout 300
```

이 명령은 프로세스 생성 시각까지 대조하고, 현재 제어자의 FAILED/STOPPED면 즉시 실패한다.
다른 제어자·다른 세대의 옛 FAILED는 새 실패로 쓰지 않는다. ACTIVE, 인증된 runtime의
세대·코드 지문·준비 상태, health의 저장소 루트와 프로세스 생존을 모두 확인한 뒤 성공한다.
관측 중 세대가 바뀌면 다시 확인한다. 자체적으로 시작·종료·재설치하지 않는다.
`ci_boot_smoke.py`도 같은 판정기를 사용한다. `/runtime/status`를 인증 없이 호출한 403은
기능 실패 증거가 아니며, 관측기는 해당 PC의 로컬 제어자 인증 계약을 따른다.

완료 보고는 소스 확보 / 의존성 설치 / backend 부팅 / 샘플 작업 / 실제 모델 질의 /
Electron 화면을 구분한다. `find_spec`와 디렉터리 존재는 설치 흔적이며 실행 증명이 아니다.
업데이트 단계 성공은 설치 완료만 뜻한다. 부팅 관측을 하지 않았으면 부팅 미검증으로 남긴다.
헬퍼 지문이 같아도 설치 경고는 별도 문제이므로 자동 시작 경고의 해결 여부를 후속 보고에 보존한다.
UTF-8 JSON·YAML은 명시 인코딩으로 읽는다. Windows 기본 인코딩이 cp1252이면 예외 없이
손상된 글자를 얻을 수도 있으므로, 종료 코드뿐 아니라 한글·일본어·이모지 원문도 대조한다.
새 헬퍼의 Windows 셸은 PowerShell 출력·native 파이프와 Python 표준출력을 UTF-8로 맞춘다
(`env.PYTHONIOENCODING`을 지정하면 명시값 우선). 바이너리는 셸 텍스트 대신 파일 전송을 쓴다.


Windows venv의 `python.exe`는 런처일 수 있어 `Popen.pid`와 서비스 PID가 다를 수 있다.
부팅 스모크는 자신이 시작한 PID+출생시각의 자손 중 상태 원장이 기록한 제어자만 채택한다.
종료 시에도 그 실행에서 확인한 프로세스 트리를 정리한다. 다른 제어자나 재사용된 PID는 채택하지 않는다.
서비스가 보고한 nonce·루트·PID·시작시각을 신원 파일 및 실제 포트 소유자와 대조하고,
런처 PID는 별도로 보존한다. 시작 명령의 시간 제한이 끝났어도 이미 서비스가 떠 있을 수 있으므로
기존 신원·로그·포트를 먼저 회수한다. 확인 지연만으로 다시 시작하지 않는다.

Windows `cmd /C`의 인용은 일반 argv 인용과 다르다. 헬퍼는 실행 원문을 유지하며
공백 경로를 따옴표로 감싸 실행할 수 있다. 복잡한 인라인 Python/중첩 셸은 파일로 전송해
명시 실행파일로 호출하면 인용 단계가 줄어든다. PowerShell에서 `-test.run=...`처럼 점이 든
외부 프로그램 인수는 인수 전체를 인용한다. 여러 명령을 이어 쓸 때는 각 실패 종료 코드를
즉시 확인해 뒤 명령의 성공으로 덮지 않는다. 헬퍼 소스·중앙 빌드의 갱신과 원격 설치본의
교체는 별개다. 사용자 요청 시 `[self:limb]{op:"update",target:"PC 이름 또는 device_id"}` 또는 조종실의 `헬퍼 교체`로 같은 중앙 절차를 사용한다. 접수증과 목표 해시를 보존하고 재연결·실행 지문과 원문 문자 출력을 확인한다.

## 2026-10-26 검증 범위

실제 임시 HTTP 작업자와 제어자에서 진행 중인 작업 완료 → 정상 종료 → 코드 변경 → 새 세대 부팅을 검사했다. 재기동 시스템 검사 25개 통과, Electron 종료 협약·개발 서버 Node 검사 10개 통과, 프런트엔드 타입 검사와 빌드 통과. 일반 backend 전체 실행은 10,341개 통과·5개 건너뜀·용례 검토 원장 미갱신 1개 실패였다. 해당 원장은 기존 용례 11개를 재검토한 뒤 갱신했으며, 해당 관문을 포함한 변경 관련 66개가 재검증에 통과했다. 원장 갱신 뒤 일반 전체 묶음을 다시 실행한 것은 아니다. 원격 PC에서 전체 갱신 절차·실제 Electron 화면·모델 질의는 이번 변경으로 재실행하지 않았다.

## 2026-10-26 사용자 요청의 중앙 헬퍼 업데이트

`self:limb update(target)`가 조종실과 같은 `resident_pcs.update_helper`를 호출한다.
사용자 출처·주인 권한을 확인하고 중앙 배포본만 선택한다. 진행 중 호출은 원 작업의
`task_ref`와 목표 해시를 반환하며, 그 사이 새 배포본이 발행돼도 목표를 바꾸지 않는다.
`limbs:guestpc`의 임의 update 봉투는 계속 거절한다. 가이드·어휘·의식 프롬프트는 정식
관리 경로로 실행하도록 정리하고, 교체 접수·재시작과 새 헬퍼의 지문 보고를 구분한다.

검증: `test_guest_helper_update.py`·헬퍼 상태·중앙 서비스·용례 재검토·Python 실행 권한·
어휘 아카이브/배포 검사 142개 통과. 임시 등록 원장·배포 파일·실제 컴파일러와 중앙 전송
서비스로 접수증 재사용, 서명 Mac 배포본 선택, 출처/권한 거절, 재접속 보고를 확인했다.
일반 backend 전체 최종 재실행은 10,415개 통과·5개 건너뜀·테스트 실패 0이다. 단,
다른 세션의 파일 스테이징을 live-store 보호 장치가 감지해 프로세스 종료 코드는 1이었다.
그 이전 실행의 새 테스트 목록 접근 오류는 수정했고 위 142개 및 최종 전체에 포함해 재검증했다.

`build_ibl_nodes.py --check` 통과, Android 번들 재생성 완료. 기존·신규 용례 21개를
검토했으며 `seed_helper_update_examples.py --apply`로 업데이트/진행 확인/조회 전용
예시 10개를 실행기억과 학습 데이터에 등록했다. 자연어 검색의 첫 결과와 라이브 서버의
`self:limb` 설명에 새 경로가 노출되는 것을 확인했다. 실제 원격 PC 교체는 실행하지 않았다.

## 2026-10-30 설치 경로 관측

- 2026-10-30 실측: TV1에서 실제로 실행 중인 indiebizOS 앱은 git 클론(C:\Users\kyungho\indiebizOS)이 아니라 별도로 설치된 앱이었다. 그래서 클론을 git pull로 업데이트해도 실행 중인 앱에는 반영되지 않았다. 업데이트 전에 실행 중인 프로세스의 경로를 먼저 확인해야 한다.
