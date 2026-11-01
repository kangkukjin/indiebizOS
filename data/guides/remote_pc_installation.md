# 원격 PC 드라이버 설치·등록·업데이트

## 빠른 호출

설치 전에도 이 가이드를 이름으로 조회한다. `[self:limb]{op:"register"}`는 공용 등록 폴더 준비, `op:"list"`는 등록·연결·드라이버 부품과 업데이트 상태 조회다. 대상 PC에서 OS 설치·권한을 승인한다. 사용자 요청의 교체는 `[self:limb]{op:"update",target:"선택한 device_id"}`이며 접수와 완료는 다르다. 설치 세대나 배포 지문이 바뀌면 재조회한다. Windows 무인관리 최초 설치의 UAC는 현지 사람이 승인한다. 일반 사용자 세션과 관리 서비스는 별도 신원이다.

## 1. 모드 선택과 설치

| 계약 | 상주 PC (새 기본 경로) | 휴대 USB (기존 issue 경로) |
| --- | --- | --- |
| 준비 | `self:limb register` → 공용 폴더를 USB에 복사 → 대상 PC에서 이름을 정해 등록 | `self:limb issue` → 이름별 발급 폴더를 USB에 복사 → 실행 |
| 수명 | 사용자 로그인 시 자동 시작, 비정상 종료 시 OS 서비스 관리자가 재기동(macOS launchd·Linux systemd; Windows HKCU Run(기존 설치는 예약 작업)은 로그인 때만 — 헬퍼 교체 때는 감시자가 새 판을 띄움). 등록 후 USB 제거 가능 | 대상 PC에서 직접 실행한 헬퍼의 수명 |
| 명령 환경 | 작업마다 cwd·env 분리. 절대 cwd·venv 실행파일 경로·env 명시 | 직전 cwd·환경변수 유지. 함수·별칭은 유지하지 않음. reset으로 초기화 |
| 화면·입력 | `mode:"interactive"` 필수 | 기존 screen·입력 호출 |
| 중복 방지 | 같은 `request_id` + 같은 명령은 기존 접수증. 내용이 다르면 충돌 | 접수증으로 관측. 같은 명령 재전송 금지 |
| 작업 후 | 연결 유지. 작업 마무리와 제거는 별개 | 필요할 때 `detach`로 프로세스 종료 |
| 제거 | 명시적인 `self:limb remove`. `removal_pending`과 `removed` 구분 | `revoke`로 키 폐기 |
| 헬퍼 교체 | 사용자 요청 시 `[self:limb]{op:"update",target:"PC"}` — 버튼과 같은 중앙 절차. [업데이트·완료 확인](../../helper/README.md#사용자-요청의-헬퍼-업데이트) | 해당 없음 |

`self:limb list`의 각 행에 `registration`이 있으면 상주형, null이면 휴대형이다.
상주형 `registration.state/paused`, 공통 `connected/expired/revoked`를 확인한다.

상주형에서 `detach`는 거절된다. 일시적으로 새 작업만 막으려면 `pause`를 쓴다.

```ibl
[self:limb]{op:"register"}
[self:limb]{op:"list"}
```

조종실 **손발 (USB) → 폴더 준비**도 같은 `outputs/pc-helper` 공용 폴더를 만든다.
실행파일·설정·사용법을 포함한 폴더 전체를 USB에 복사하고 대상 PC에서 OS에 맞는 파일을
실행한다. 같은 USB로 여러 PC를 등록한다. 등록 키는 등록 전용이고 각 PC의 실행 자격은
별도로 발급된다. USB 등록 키 폐기는 이미 등록된 PC를 끊지 않는다. 기존 발급 폴더·키는
자동으로 상주형으로 바뀌지 않는다.

상주형은 macOS LaunchAgent, Windows 현재 사용자 로그인 자동 실행(HKCU Run, 기존 예약 작업 유지), Linux systemd 사용자
서비스다. 로그인 전 실행·관리자 서비스는 아니다. 중앙 주소는 `/limb/*`와 `/remote-pcs/*`를
직접 전달하는 HTTPS 터널이어야 한다. 지속 WebSocket이 막히면 HTTPS 롱폴로 돌아간다.
설치·OS 권한은 대상 PC에서 허용한다. 이 PC 헬퍼 등록 경로는 Android/iPhone/iPad에 사용하지 않는다. Android는 remote_phone.md의 APK 등록 경로를 쓴다.

## 4. 수명·해제·기록 보존

상주형 작업은 별도 workspace·프로세스·환경에서 실행한다. 같은 작업 ID를 중복 실행하지 않고
이벤트·결과를 중앙 ACK까지 보존한다. 재시작 중 결과를 잃으면 unknown으로 남기며 자동 재실행하지
않는다. 취소는 실행 중 자식까지 중지 요청한다. 작업 로그는 상한 뒤 log_gap을 표시한다.
CPU/메모리 하드 제한이나 OS 보안 샌드박스는 아니다. 현재 사용자의 권한으로 실행한다.

```ibl
[self:limb]{op:"pause",target:"사무실PC",paused:true}
[self:limb]{op:"pause",target:"사무실PC",paused:false}
# 등록 해제·헬퍼 제거를 명시적으로 요청받은 경우만:
[self:limb]{op:"remove",target:"사무실PC"}
```

remove는 새 작업을 차단하고 `removal_pending`으로 남는다. 기기의 제거 확인 뒤 `removed`다.
작업 폴더·USB 원본은 보존한다. 제거 접수만으로 제거 완료라고 보고하지 않는다.

휴대형 기존 사용:

```ibl
[self:limb]{op:"issue",alias:"휴대PC",ttl_days:14,os:"win"}
[limbs:guestpc]{op:"detach",limb:"휴대PC"}
[self:limb]{op:"revoke",target:"휴대PC"}
```

issue는 `outputs/limb_issue/<별칭>/`에 설정·실행파일·사용법을 만든다. ttl_days=0은 무기한이다.
유효한 키로 접속하면 자동 승인되며 명령의 limb 이름으로 오배송을 막는다. 대상은 항상 명시한다.
같은 키로 새 헬퍼가 붙으면 최신 세션이 이긴다. 위치 변경 알림은 키 유출 여부를 확인할 단서다.
휴대형 detach는 현재 프로세스만 종료하며 재실행하면 다시 붙는다. 영구 차단은 revoke다.
휴대형 환경은 유지되지만 함수·별칭은 유지되지 않는다. venv는 명시 실행 경로를 권장하며,
환경이 꼬이면 reset:true로 초기화한다. stdin으로 비대화형 입력을 줄 수 있다.

휴대형 전달 전 명령은 10분 뒤 만료, 완료 결과·회수 기록은 7일 보존한다. op:result는 호환
1회 회수이므로 반복 관측에는 self:task를 쓴다. 헬퍼는 사용자 설정 폴더의 delivery 원장에
수신·결과를 남기고 허브 확인까지 결과만 재전송한다. macOS 작업 중 유휴 잠자기를 막지만
덮개를 닫은 실행·항상 화면 켜짐을 보장하지 않는다. 이 배관은 최신 헬퍼 바이너리가 필요하다.

## 5. 등록·개정·검증과 빌드

정의 정본은 `data/idioms/guestpc_*.ibl`, 등록 자료는 `guestpc_seeds.json`이다.
기존 네 함수의 이름을 유지하며 선택 인자를 추가했다. 아래는 기존 정의의 명시 개정과 새 정의
등록을 함께 한다. SQLite backup 후 기존 개정 원장에 옛 정의·통계를 보존하고 신규 용례는
`add_examples_batch`로 등록한다. 벡터 색인까지 확인하며 상시 소개는 끈다.

```bash
.venv/bin/python3 scripts/register_webapp_idioms.py --seed-file guestpc_seeds.json --apply --local-encoder --revise-reason "상주 헬퍼 계약 정렬과 전송·깨우기·중지·재생 관용구 검증"
```

`--local-encoder`는 실행 중인 중앙 백엔드의 임베딩을 사용한다. 꺼져 있으면 이 옵션을 빼서
로컬 모델을 적재한다. 동일 자료의 재등록은 멱등이다. 검사: `backend/test_guestpc_idioms.py`,
`backend/test_guestpc_resident_idioms.py`, `backend/test_resident_pcs.py`. 임시 중앙 원장과 실제
핸들러·IBL 실행기를 연결해 검사하며 OS 설치·WOL·실제 오디오 출력 검증은 별도다.

헬퍼는 `helper/`의 Go 소스를 `helper/build.sh`로 빌드한다. macOS 10.15~11 Intel은
Go 1.22와 `go.legacy.mod`를 쓰는 `mac-amd64-legacy`를 사용한다. 일반 mac-amd64는 macOS 12
이상이 필요하다. 실제 기기 호환성은 실기기 시험으로 확정한다. 발급 폴더 실행파일을 갱신할 때
기존 `indiebiz-helper.json` 키를 재발급·교체하지 않는다.
설치·제거 세부 사항은 `helper/README.md`, 설계는 `docs/REMOTE_PC_RESOURCE_DESIGN_2026_10_10.md`.

남의 PC에서 실행할 때는 그 PC 주인의 동의가 전제다. 허브·터널 연결이 필요하고 서명 없는
바이너리는 OS 경고가 나타날 수 있다. 손발 실행 자격은 이웃 등급 자동 부여와 별개다.


## 모든 폴더·외장 드라이브와 관리자 명령

workspace는 기본 위치이며 절대 cwd/path로 OS가 허용한 모든 경로를 쓴다.
일반 헬퍼의 shell `elevate:true`는 원격 PC의 OS 인증창에서 이번 명령을 승인한다.
비밀번호를 채팅·cmd·stdin·env로 전달하지 않는다. UAC 보안 화면은 헬퍼로 조작할 수 없다.

Windows **무인 관리 서비스**는 최초 관리자 등록 후 로그인 없이 설치·설정을 실행한다.
`info.resident`의 `service_scope:machine`, `elevation_unattended:true`를 확인한다.
이 대상의 shell은 LocalSystem이며 매번 UAC를 띄우지 않는다. 일반 사용자용 앱·화면은
사용자 세션 헬퍼로, 시스템 설치·설정은 관리 서비스로 보낸다. 설치기는 무인 옵션을 쓴다.
서비스가 없는 일반 헬퍼를 무인 관리 가능하다고 추정하지 않는다.
등록·보호·해제·플랫폼 범위는 `helper/README.md`의 무인 관리 서비스를 따른다.


## 배포와 완료 확인

`self:limb list`와 조종실 목록의 `drivers.components`는 실제 설치 단위마다 한 행이다. OS 제어·원격 실행이 공유하는 바이너리는 한 번만 교체한다. `update`는 기존 설치 구현의 상태이며 접수 성공을 설치 성공으로 바꾸지 않는다. 새 판본의 인증된 신고 뒤에도 필요한 OS 동작을 확인한다. 미관측 권한·호환 조건은 unknown이다.
Mac은 서명 release 매니페스트, Windows·Linux는 기존 dist 실행파일을 설치 어댑터가 검증한다. Mac legacy 빌드 선택은 기존 Go 계열 관측을 유지한다. Android는 [원격폰 가이드](remote_phone.md)의 ABI·SDK·서명 검증과 OS 설치 확인을 따른다. TV는 대상에 설치하는 프로그램이 없다.
PC 교체의 대기·인계·되돌리기는 [헬퍼 안내](../../helper/README.md#사용자-요청의-헬퍼-업데이트)를 따른다. Android 설치 실패를 PC처럼 자동 롤백할 수 있다고 가정하지 않는다.

## IndieBiz OS 본체 설치

원격 제어 부품 교체와 본체 앱 설치는 다른 작업이다. `bootstrap.py`·`remote_install.py`·`remote_steps.py`의 계획·로그·종료·재개는 [원격 PC 설정 검증](../../docs/REMOTE_PC_SETUP_VERIFICATION.md)에 있다. 클론 갱신만으로 실행 중인 설치 앱이 바뀌지 않으므로 실제 프로세스 경로와 건강 응답을 확인한다.

## 과거 관측의 근거

이관 시점의 실측 원문·지문·UAC 설명 충돌은 [이관 기록](../../docs/experiments/hardware_driver_migration_2026_11_01.json)에 보존했다. 특정 PC의 설치 실패나 대기 시간을 일반 기기 계약으로 적용하지 않는다. 새 대상별 실측은 관측 원장, 일반 구현 문제는 가이드 피드백 제안으로 보존한다.
