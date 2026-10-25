# 원격 PC 설치·업데이트·부팅 검증

원격 작업의 접수·관측·취소는 [외부 PC 가이드](../data/guides/guest_helper.md)를 따른다.
다음 절차는 설치 흔적과 실제 실행 성공을 구분한다.

**IndieBiz 업데이트 조리법** `scripts/remote_install.py`는 이미 존재하는 소스 저장소와
Git·지원 Python·Node/npm을 사용한다. 없는 런타임은 OS·아키텍처를 확인하고 먼저 설치한다.
스크립트가 없는 구판 PC에는 이 두 스크립트를 원격 전송한 뒤 사용한다(backend/boot_paths.py가
있는 저장소의 scripts/ 위치). 현재 돌고 있는 설치와 중복 실행하지 않는다.

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
완료 후 앱을 실제로 시작하고 필요한 기능을 확인하는 것은 별도 검증이며 이 조리법은
실행 중인 앱을 자동 재기동하지 않는다. 최초 설치의 인증 설정·훈련용 선택 의존성은 포함하지 않는다.

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
교체는 별개다. 조종실의 해당 PC `헬퍼 교체` 후 재연결·실행 지문과 원문 문자 출력을 확인한다.
