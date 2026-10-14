# 등록된 폰의 범용 원격 실행 설계

상태: **기본 구현·자동 검사 완료, 실기 인수 전**. 아래 본문은 설계 기준이며 현재 구현·검증 범위는 §10을 따른다.
기준일: 2026-10-15. 목적: 원격 기기의 기존 능력을 IBL 어휘에 연결된 범위 밖에서도 정확하게 실행한다.
상위 기준: [IBL 진화 목적](IBL_EVOLUTION_PURPOSE.md).
기존 기반: [폰의 손발 등록 설계](INDIEBIZ_BODY_AS_LIMB_DESIGN_2026_10_13.md),
[원격폰 가이드](../data/guides/remote_phone.md).

## 1. 결정과 범위

IndieBiz OS 앱 설치와 원격 손발 등록은 이미 별개다. 사용자가 삼성0에 앱을 설치해 쓰다가
USB 연결로 등록한 사례가 이 구분을 보여준다. **이 설치·등록 구조를 유지한다.**
본체와 헬퍼를 별도 APK로 나누거나 공통 런타임을 중복 설치하는 작업은 하지 않는다.

바꿀 것은 등록 이후의 실행 계약이다. PC 헬퍼처럼 폰도 중앙에서 받은 범용 명령·스크립트를
실행할 수 있게 한다. 기존 IBL 실행은 함께 유지한다. 중앙이 macOS인 것은 구현 전제가 아니다.
중앙의 OS와 무관하게 동일한 요청을 보내고, 실행 대상의 OS·권한·런타임이 결과를 결정한다.

원격 실행의 책임은 다음 셋으로 나눈다.

1. **연결·작업 관리:** 기존 손발 자격, 아웃바운드 sync, 요청 ID, 사건 spool, 작업 상태.
2. **실행:** IBL, Android 셸, 내장 Python을 각각의 실제 런타임에서 실행.
3. **기기 접근:** Android 시스템 명령과 공개 API, 기존 앱 서비스의 수명·자원 관리.

언어 추가가 권한 추가를 뜻하지 않는다. 기본 실행 신원은 앱 UID다. ADB shell 권한의 별도
서비스는 선택 확장으로 정의하며, 이번 기본 구현의 필수 의존성으로 만들지 않는다.
이 문서 작성은 설계 작업이다. 코드 수정·APK 빌드·삼성0/삼성1 설치·실기 제어는 수행하지 않았다.

## 2. 확인한 문제와 소유 위치

에피소드 기록(`data/world_pulse.db`의 `episode_log`)에서 확인한 순서는 다음과 같다.

| 사건 | 실제 경로 | 관측 |
| --- | --- | --- |
| 4773, 10/14 23:44, 소리 키우기 | 영화 음성 미디어세션 update | 판본 충돌 후 재조회·재시도로 80→95 |
| 4776, 10/15 00:28, 소수빈 음악 | 영화 세션 종료, 폰 `limbs:music` 재생 | 재생 경로 전환 |
| 4777, 00:30, 소리 반으로 | 폰 `limbs:radio` volume 47 | 라디오 없음 오류, 미달 |

기기 기능은 이미 있었다. `PhoneActions.applyVolumeLocked`와
`media/ContentPlayer.applyVolume` 모두 Android의 `AudioManager.STREAM_MUSIC`을 변경한다.
그런데 라디오 진입점은 라디오 playback ID를 요구하고, 음악 op에는 volume이 없다.
음악은 `youtube_phone.Playback`에서 70으로 시작하므로 이전 영화의 95를 그대로 현재 음량으로
간주하는 것도 잘못이다. **실제 기기 상태 조회와 독립 실행 통로가 함께 필요하다.**

| 현 코드 | 제약·변경 책임 |
| --- | --- |
| `backend/services/limb_client.py` | `shell:false`, `ibl/info` 및 조건부 media만 신고·실행 |
| `backend/services/resident_pcs.py:submit` | `indiebiz-v1` 대상에서 shell을 중앙에서도 거절 |
| `data/packages/installed/tools/guest-helper/handler.py` | PC shell 봉투·대기·작업 결과는 재사용 가능, 폰 설명·Python 전달은 보완 필요 |
| `phone-companion/.../App.kt` | Chaquopy와 백엔드가 앱 프로세스에서 기동. 일반 Python 실행 파일이 있다는 보장이 없음 |
| `PhoneActions.kt`, `media/ContentPlayer.kt` | 공통 기기 음량이 재생기 상태·캐시에 종속 |
| `data/guides/remote_phone.md` | 현재 shell 거절을 설명. 구현 이후 새 계약으로 갱신 |

PC 원격 셸도 권한·도구·OS 차이로 실패할 수 있다. 차이는 성공 보장이 아니라 대체 수단을
표현할 수 있는 범위다. 폰에 셸만 열어도 모든 Android API가 명령으로 생기는 것은 아니다.
Python에서 Android API에 접근하는 길까지 제공해야 이번 공통 공백이 닫힌다.

## 3. 외부 계약: 기존 원격 작업에 실행 방식 추가

새 노드·하드웨어별 IBL 낱말은 만들지 않는다. 기존 `limbs:guestpc`와 resident 작업 원장을 쓴다.

| op | 입력 | 실행 의미 |
| --- | --- | --- |
| `info` | 기존 입력 | 실제 지원 런타임·권한·준비 상태·플랫폼 정보 |
| `ibl` | 기존 `code` | 기존 폰 IBL 엔진. 판본·반환 계약 유지 |
| `shell` | 기존 `cmd`, `stdin`, `cwd`, `env`, `timeout` | 폰의 `/system/bin/sh -c`로 앱 UID에서 실행 |
| `python` (신규 제안) | `code`, `inputs`, `cwd`, `timeout` | 내장 Chaquopy 실행. `inputs` 객체 주입, `result` 변수를 JSON 값으로 반환 |
| `transfer` | 기존 전송 계약 | 폰의 출력 로그·사진·녹음 등 회수. 기존 청크·해시·재개 계약에 연결 |

`python`을 별도 op로 두는 이유는 폰의 Python이 내장 런타임이기 때문이다.
`shell:"python"`처럼 셸 종류를 바꾸거나 PC의 `python3` 명령이 폰에도 있다고 가정하지 않는다.
PC는 기존 shell에서 Python을 실행하며, `python` op를 구현하지 않은 PC에 조용히 번역해 보내지 않는다.
IBL 호출은 전송을 요청하는 한 가지 표면이다. 원격 프로그램 본문까지 IBL로 바꾸거나
등록 스크립트로 저장해야만 실행할 수 있게 하지 않는다.

공통 입력과 처리:

- `request_id`, `background`, `timeout`, 대상 해소·접수증·history·wait는 기존 경로를 공유한다.
- 폰 shell/Python의 cwd 기본은 앱 userdata 아래 작업 디렉터리. 작업마다 명시하며 이전 작업의
  `cd`·환경 변경·Python 전역을 이어받지 않는다. PC 상주형의 cwd/env 분리 의미와 맞춘다.
- shell의 `env`는 자식 프로세스에만 적용한다. Python에는 입력 객체를 쓰며 초기 버전에서
  `stdin`·`env`·`reset`을 지원하지 않는다. 지원하지 않는 필드를 조용히 무시하지 않는다.
- 폰 shell은 `shell` 생략 또는 `sh`만 허용한다. PowerShell·cmd, `elevate:true`는 명시 거절한다.
- `mode:observe`는 초기 폰 범용 실행에서 신고하지 않는다. 코드가 읽기 전용인지 추측하지 않는다.
- 신규 프로그램 본문은 UTF-8 64 KiB, 입력 포함 봉투는 기존 256 KiB 상한을 적용한다.
  실행 timeout 기본 120초, 허용 1..3600초로 폰 명세에 신고한다. 중앙의 응답 대기시간과 구별한다.

### 3.1 능력 협상과 구버전

`adapter:"indiebiz-v1"`은 유지하고 `execution_contract:1`을 추가한다.
`ops`는 실제 구현이 준비된 것만 넣는다. 기존 `python` 문자열은 런타임 버전 정보이므로
그 값만으로 원격 Python 지원을 판단하지 않는다. 새 `runtimes` 객체에 다음을 담는다.

- shell: 실행 파일, 지원 셸, `identity:"app"`, timeout·cwd 계약, 실행 준비 여부.
- python: 구현 `chaquopy`, Python 버전·ABI, Android bridge 판본, 별도 worker 준비 여부.
- 부가 프로브: SDK·target SDK, 접근성 서비스 상태, 카메라/마이크 권한, 기기 자원 준비 상태.
- `observed_at`, 능력 판본. 신고는 힌트이며 실행 직전 현재 상태로 다시 판단한다.

중앙은 **중앙에서 허용한 연산 ∩ 대상이 신고한 연산 ∩ 현재 요청자의 권한**으로 접수한다.
대상이 신고했다고 임의 op나 권한 상승을 허용하지 않는다. 새 op에 대해 신고가 없으면 거절한다.
구형 폰은 기존 IBL·info·media가 계속 동작하고, 새 실행 요청에는 업데이트 필요를 반환한다.
새 폰/구형 중앙도 기존 op를 계속 사용한다. 실제 기기 선택은 별칭만이 아니라 활성 device ID와
설치 세대에 묶어, 미지원 요청을 다른 폰이나 중앙에서 대신 실행하지 않는다.

### 3.2 결과와 실패

resident의 기존 `started/result` 사건·task 상태를 유지한다. 새 상태 기계를 만들지 않는다.
결과에는 `success`, 실행 방식·실제 UID, `stdout`, `stderr`, `exit_code`, `cwd`,
경과시간·timeout 여부·취소 여부, Python의 구조화된 `value`, 출력 회수 참조를 담는다.
`exit_code`는 실제 셸 자식의 값이며 내장 Python은 null이다. Python 정상 완료·예외·worker 사망은
각각 실행 결과와 종료 사유로 구분한다. task 어댑터가 이를 기존 terminal 상태로 변환한다.

- 셸 종료 코드 0은 프로그램 종료 성공이며 목표 달성 보장이 아니다.
- Python 예외는 타입·메시지·traceback을 보존한다. JSON 불가 result는 반환 계약 오류다.
- Python이 result를 지정하지 않으면 null을 반환한다. stdout에서 업무 결과를 추측하지 않는다.
- 도구 없음, OS 권한 거절, 사용자 조작 필요, 자원 사용 중, worker 종료, 결과 불명을 구별한다.
  임의 셸 stderr의 문자열만으로 정확한 Android 오류 코드를 지어내지 않는다.
- stdout/stderr는 각각 64 KiB 미리보기로 제한하고 전체 로그를 작업 파일에 보존한다.
  전체 로그는 합계 8 MiB 상한·초과 여부를 기록한다. 작업 파일은 완료 뒤 7일 보존을 기본으로 한다.
  전달 대기 중 파일은 자동 삭제하지 않고 용량 부족을 보고한다. 바이너리를 JSON에 계속 넣지 않는다.
- Python value도 64 KiB를 넘으면 작업 파일·크기·SHA-256 참조로 돌린다. 폰의 경로만 반환하고
  중앙으로 파일을 가져왔다고 보고하지 않는다. transfer로 받아 지문까지 검증해야 회수 완료다.

## 4. 폰 실행기와 Android 접근

### 4.1 실행 프로세스

임의 Python 코드를 백엔드의 worker thread에서 `exec`하는 방식은 채택하지 않는다.
무한 루프·네이티브 블록·전역 오염이 통신·재생까지 손상시키고, HTTP timeout은 실행 중단이 아니다.

APK에 비공개 Android service(`exported:false`, 별도 `:remote_exec` 프로세스)를 둔다.
기존 상주 서비스가 작업 동안 bind해 수명을 관리하고, 작업은 처음에 하나씩 실행한다.
새 프로세스에서 최소 Chaquopy 초기화만 수행한다. `App.onCreate`는 프로세스 역할을 구분해
worker에서 백엔드·WebView·미디어·손발 sync를 다시 시작하지 않도록 바꾼다.
Python 작업마다 worker를 새로 시작하고 완료 후 종료해 import·환경·스레드 상태가 다음 작업에
남지 않게 한다. 재사용 최적화는 상태 분리와 성능을 측정한 뒤 별도로 판단한다.
기존 APK의 런타임을 사용하되 프로세스 메모리는 추가되므로 J7에서 시작시간·PSS를 측정한다.

별도 프로세스의 목적은 오류·수명 분리다. **같은 앱 UID이므로 보안 샌드박스가 아니다.**
신뢰된 등록 주인이 앱 권한으로 코드를 실행하는 모델이며, 앱이 읽을 수 있는 파일과 자격을
임의 코드로부터 숨길 수 있다고 주장하지 않는다. 일반 이웃·회원·외부 요청에 이 실행 권한을
자동 부여하지 않고 기존 호출자 권한·출처 검사와 연결한다.

셸도 관리되는 자식 프로세스로 실행한다. timeout/취소 시 작업 소유 프로세스와 자식의 종료를
확인하고 worker를 교체한다. PID만 재사용하지 않도록 작업·시작 신원을 함께 기록한다.
프로세스 그룹/자식 회수는 Android 9 arm32와 현대 arm64에서 먼저 검증할 구현 관문이다.
확인 불가한 자식·OS 부작용까지 모두 취소됐다고 표시하지 않는다.

입출력은 파이프 또는 파일 디스크립터로 주고받아 Binder에 대형 프로그램·출력을 싣지 않는다.
worker 사망을 메인 프로세스가 관찰하며 sync는 계속 살아 있어야 한다. `info`·취소·전송 같은
제어 요청은 긴 실행 큐 뒤에서 막히지 않게 별도 처리한다.

### 4.2 Python → Android: 기존 언어와 API 사용

제안 모듈 `indiebiz_android`는 worker의 application Context, 앱 서비스 호출,
작업 파일·자원 수명 연결을 제공한다. 일반 Android API는 기존 Chaquopy `java.jclass`로 호출한다.
API 메서드마다 새 IBL op나 새 자체 언어를 만들지 않는다. 추가 래퍼는 비동기 수명·스레드·
자원 소유권을 실제로 관리해야 하는 기능에만 둔다.

예시(구현 후 쓸 **제안 Python 본문**, 현재 실행 가능하다는 뜻이 아님):

```python
from java import jclass
from indiebiz_android import context

AudioManager = jclass("android.media.AudioManager")
audio = context.getSystemService("audio")
stream = AudioManager.STREAM_MUSIC
if audio.isVolumeFixed():
    raise RuntimeError("fixed_volume")
before = audio.getStreamVolume(stream)
target = before // 2
audio.setStreamVolume(stream, target, 0)
after = audio.getStreamVolume(stream)
result = {"before": before, "requested": target, "actual": after,
          "max": audio.getStreamMaxVolume(stream), "applied": after == target}
```

0..100이라는 가상 연속값 대신 실제 OS 단계를 읽고 결과를 검증한다. 반올림 규칙을 명시하며,
음량 단계 절반과 사람에게 들리는 음압·지각 크기 절반을 같은 것으로 보고하지 않는다.

카메라·녹음·화면 입력은 단순 Context만으로 기존 서비스의 상태를 공유할 수 없다.
기존 `PhoneActions`·`PhoneAccessibilityService`·미디어 서비스의 static 객체는 프로세스별로
다르므로 worker에서 직접 불러 같은 인스턴스라고 가정하지 않는다. 소유 프로세스에 Binder로
요청하고 작업 ID로 자원 임대·종료를 연결한다. 접근성·미디어 엔진을 worker에 두 벌 띄우지 않는다.
기존 IBL 핸들러도 같은 기기 구현을 사용한다. 장기 재생은 기존 미디어 세션에 넘기고,
범용 Python worker를 영구 재생 서비스로 쓰지 않는다.

### 4.3 범위와 권한

앱 UID의 shell은 ADB shell과 다르다. `input`·`cmd` 등이 설치돼 있어도 앱 신원에서
실패할 수 있다. 그런 경우 Android API·활성 접근성 서비스 등 현재 승인된 경로를 선택한다.
실패한 쓰기 명령을 다른 경로로 자동 재실행하지 않는다. 부분 실행 여부를 확인한 뒤 결정한다.

Wi-Fi/Bluetooth 직접 토글, 백그라운드 카메라·마이크, 앱 설치·실행에는 OS/target SDK/
현재 앱 상태별 제한이 있다. 범용 실행으로 그 제한이 사라진다고 설명하지 않는다.
원격에서 권한 확인 화면을 요청한 것은 권한 획득 완료가 아니며, 필요한 폰 조작을 반환한다.
폰의 자체 AI도 같은 로컬 실행 서비스를 재사용할 수 있지만 원격 등록을 요구하지 않는다.
미등록이면 원격 작업 접수·자격 발급·대외 수신 경로가 생기지 않는다.

ADB/Shizuku 계열 연결은 선택 확장이다. 적용 전 실제 지원 OS·ABI, 최초 승인·기동,
USB 해제·재부팅 뒤 유지/복구, 앱과 broker의 인증·버전 호환을 확인해야 한다.
별도 실행 신원으로 신고하고 명시적으로 선택할 때만 사용한다. root·Device Owner를
몰래 획득하거나, 일반 shell 실패를 계기로 권한을 자동 상승시키지 않는다.
**기본 범용 실행 완료와 ADB 권한 확장 완료는 별도다.** 현재 볼륨 문제에는 후자가 필요 없다.

## 5. 작업 수명·등록·실패 복구

USB 등록·기존 실행 키·설치 세대·아웃바운드 sync·해제 구조를 그대로 쓴다.
새 인바운드 셸 포트나 별도 허브 비밀번호를 만들지 않는다.
중앙 제출·폰 접수·기기 서비스 호출에 작업 신원과 허용된 origin을 이어 기록한다.
훈련 origin은 출처이지 부작용을 차단하는 샌드박스가 아니다.

- 같은 request ID+내용은 기존 작업을 회수하고 다른 내용은 충돌로 거절한다.
- 실행 시작·최종 결과는 spool 후 전송하며 ACK 유실로 프로그램을 재실행하지 않는다.
- 중앙 wait timeout은 대기 종료다. 실제 실행 timeout은 폰 제어자가 종료를 확인한 결과다.
- 실행 중 재부팅·프로세스 사망 뒤 효과를 확인할 수 없으면 unknown으로 종료한다.
  이미 수행한 음량 변경·촬영·파일 쓰기를 자동 반복하지 않는다.
- cancel은 요청과 완료를 구별한다. 중단 이후에도 이미 발생한 부작용은 되돌아가지 않는다.
- pause는 기존 새 작업 차단 의미를 유지한다. remove/revoke가 폰에 전달되면 대기 작업을
  폐기하고 범용 실행 worker와 그 자원 임대를 종료한 뒤 기존 자격 제거 절차를 수행한다.
  통신 단절 중에는 폰이 즉시 폐기를 알 수 없으므로 작업 deadline이 상한을 제공한다.
- 정지·해제는 손발 역할에만 적용한다. 폰의 독립 대화·AI와 무관한 재생을 일괄 종료하지 않는다.

## 6. 볼륨을 첫 수직 검증 사례로 삼는다

범용 실행만 추가하고 기존 재생기의 음량 덮어쓰기를 두면 사용자 의도가 다시 깨진다.
기기 미디어 음량의 조회·변경 구현을 재생 상태에서 분리하고 기존 소비자를 그 구현에 연결한다.

- 기기 음량 제어는 재생 여부와 무관하게 동작한다.
- `PhoneActions`·`ContentPlayer`의 중복 AudioManager 처리를 공통 구현으로 모은다.
  예외를 삼키고 성공으로 보고하지 않으며 설정 뒤 실제 값을 조회한다.
- 라디오 대상 확인은 라디오 전용 호출에 유지하되 기기 음량 호출에 강요하지 않는다.
- 음악 시작·다음 곡에서 70을 강제 설정하지 않는다. 명시적 음량 입력이 없는 재생은 현재 값을 유지한다.
- 미디어세션 update에서 사용자가 음량을 바꾼 경우와 상태 동기화가 캐시 값을 재전달한 경우를
  구별한다. 재접속·seek·pause·다음 곡이 이전 캐시로 사용자의 기기 음량 변경을 되돌리지 않는다.
- 상태 보고는 요청한 값·현재 OS 값·재생기 내부 gain을 구별한다. 범용 API 변경 뒤 상태를 재조회한다.

완료 판단은 “명령 exit 0”이 아니라 같은 대상에서 실제 OS 값이 바뀌고 재생 전환 후에도
유지되는 것이다. 다른 앱·사용자의 동시 변경까지 영구적으로 막거나 원자성을 보장하지 않는다.

## 7. 구현 위치와 이행 순서

| 순서 | 변경 | 완료 관문 |
| --- | --- | --- |
| 1 | arm32/arm64 worker·최소 Context·셸/Python 프로브 | 무한 루프 종료 뒤 sync·재생 생존, UID·API 호출 확인 |
| 2 | `limb_client`, `resident_pcs`, guest-helper에 능력 협상·shell/Python 전달 | 구버전 호환, 대상 고정, 요청ID·실패·취소 종단 |
| 3 | 기기 서비스 연결·파일 전송·출력 회수 | 권한 오류·자원 충돌 보존, 파일 해시 일치 |
| 4 | 공통 음량 구현과 재생기 소비자 전환 | 재생 없음/음악/라디오/영화에서 조회·변경·유지 |
| 5 | 교재·등록·배포·운영 검증 | 미등록/등록/해제·잠금·재부팅, 실제 AI가 새 실행 경로 사용 |
| 선택 확장 | 승인된 ADB 권한 broker | 별도 설치·재기동·권한·수명 실증, 지원 범위 명시 |

예상 파일 소유권:

- 중앙: `backend/services/resident_pcs.py`, `data/packages/installed/tools/guest-helper/handler.py`,
  그 패키지 `ibl_actions.yaml`. 기존 wait/history/transfer와 오류 반환을 재사용한다.
- 전송: `backend/services/limb_client.py`는 접수·spool·원장에 집중하고 새 실행 로직은 형제
  services 모듈로 분리한다. 공통 OS 코드에 삼성1 이름·특정 음악·액션 이름 분기를 넣지 않는다.
- 기존 폰 로컬 실행 표면과 중앙 원격 API도 같은 실행 서비스·권한 검사를 사용한다.
  범용 실행을 위해 인증 없는 새 HTTP endpoint를 만들거나 PC용 실행 파일 기반 script runner를
  폰에 그대로 복제하지 않는다. 폰 자체 AI의 도구 소개에는 실제 준비된 로컬 실행 경로를 노출한다.
- Android: `App.kt`, Manifest, 별도 worker service·Binder 계약, 내장 Python 실행 모듈·
  `indiebiz_android`, 공통 음량 구현. 접근성·미디어 서비스는 기존 소유자를 재사용한다.
- 기존 소비자: `PhoneActions.kt`, `media/ContentPlayer.kt`, YouTube 폰 재생과 라디오 연결.
- 문서: remote_phone·guest_helper 가이드, remote_access·communication 요지, 관련 도움말·오류 문구.
  retire 대상은 “폰의 shell은 항상 미지원” 계약이며 실제 구현 시 retired_contracts에 등록한다.

신규 backend 모듈은 층 배정·1500줄 제한을 지킨다. 어휘 원본 변경 뒤 빌더로 파생물을 갱신하고
폰 번들도 재생성한다. 기존 IBL·media 의미와 PC 셸 구현을 한꺼번에 재작성하지 않는다.
APK만 배포해서는 중앙의 거절 관문이 남는다. 중앙 지원을 먼저 반영하고 폰을 업데이트한 다음
새 능력 신고를 확인한다. 롤백 시 신고된 지원이 사라지면 해당 신규 요청을 중단한다.

## 8. 인수 기준과 미검증

| 검증 축 | 필수 확인 |
| --- | --- |
| 등록 | 미등록 설치는 원격 명령 불가. 명시 USB 등록 뒤 가능. 해제 후 원격 불가·독립 앱 사용 가능 |
| 중앙 OS | macOS 전용 경로 없음. Windows/Linux 중앙에서도 같은 봉투 직렬화·대상 해소 검사; 실제 미시험 OS는 별도 표기 |
| 폰 런타임 | Android 9 arm32와 현대 arm64에서 shell·Python·Android API 실행. 없는 curl/python3를 있다고 가정하지 않음 |
| 표현 | 따옴표·한글·줄바꿈·빈 입력, stdout/stderr 분리, JSON 결과·예외·대형 출력의 보존 |
| 수명 | 무한 루프·자식 프로세스·네이티브 대기·취소·worker 사망에도 sync 생존; 죽은 작업 자동 재실행 없음 |
| 신원 | 앱 UID와 shell UID 구분, 이웃 권한으로 주인 손발 실행 불가, 다른 기기 대체 실행 없음 |
| 음량 | 무재생/음악/라디오/영화, 0·최댓값·홀수 단계 절반·고정 음량 정책, 다음 곡·재접속 뒤 유지 |
| 다른 능력 | 별도 IBL 낱말 추가 없이 파일 변환·기기 상태 API 조합 실행; 카메라/입력은 기존 서비스 연결·권한 거부 확인 |
| 회수 | 생성 파일·전체 로그를 transfer로 회수해 해시 비교. 경로 반환을 전송 성공으로 취급하지 않음 |
| 연결 | 화면 꺼짐·망 단절·재부팅·ACK 유실에서 상태 보존, 결과 불명·대기 종료·실행 종료 구별 |
| AI 사용 | 자연어 요청으로 범용 경로를 선택·실행·재조회하는지 확인. 코드 직접 실행만으로 AI 활용 성공을 주장하지 않음 |

기존 `test_limb_client.py`, `test_resident_pcs.py`, `test_guestpc_resident_idioms.py`,
`test_phone_execution_routes.py`를 소비자 회귀에 포함하고 새 시험은 소유 모듈별로 둔다.
구현 변경 범위에 따라 [회귀 규약](REGRESSION_TESTING.md)의 선택 검사·종합/격리 검사를 수행한다.
APK 컴파일과 가짜 Android 브리지 시험을 실제 기기 검증으로 대신하지 않는다.
품질·벽시계 시간·모델 호출/토큰은 실제 AI 요청으로 측정하며 현재 성능 개선 수치는 없다.

설계 당시에는 모두 미구현이었다. 이후 구현·인수 상태는 §10에 기록한다.

## 9. 플랫폼 근거

- [ADB](https://developer.android.com/tools/adb): 연결·셸 접근 수단. 앱 UID 실행과 동일하지 않다.
- [Android 앱 샌드박스](https://source.android.com/docs/security/app-sandbox): 실행 언어를 바꿔도 UID 권한은 유지된다.
- [AudioManager](https://developer.android.com/reference/android/media/AudioManager): 기기 스트림 음량·실제 단계·고정 정책.
- [별도 서비스 프로세스](https://developer.android.com/guide/topics/manifest/service-element): `android:process` 계약.
- [Chaquopy FAQ](https://chaquo.com/chaquopy/doc/current/faq.html): 내장 Python의 중단과 별도 프로세스 선택.
- [Chaquopy 제약](https://chaquo.com/chaquopy/doc/current/android.html): 일반 multiprocessing을 그대로 전제할 수 없음.
- [전경 서비스 제약](https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start): 카메라·마이크 준비와 앱 상태.
- [접근성 서비스](https://developer.android.com/guide/topics/ui/accessibility/service): 화면 관측·입력의 기존 API.
- [Shizuku](https://shizuku.rikka.app/introduction/): 선택적 별도 권한 서비스 구조의 참고. 채택·설치 완료가 아니다.

## 10. 구현 기록

2026-10-15: 기본 실행 계약1을 구현했다. 중앙의 명시 능력 협상·주인 검사, 기존 등록/작업 원장,
별도 `:remote_exec` 프로세스의 shell/Python, 직접 Android API 접근과 서비스 자원 IPC,
취소·시간제한·worker 사망 결과, 청크 전송·재개·해시·덮어쓰기 거절을 연결했다.
폰 자체 AI의 기존 run_command도 같은 서비스를 사용하며 원격 등록을 요구하지 않는다.
등록 방식·APK 수는 바뀌지 않았다. ADB/Shizuku 권한 broker는 이번 범위에 없다.

음량은 DeviceAudio로 공통화했다. 음악의 70 강제값을 없애고 현재 기기 음량을 유지한다.
영화 시작은 명시 음량만 적용하고 적용한 세션 ID를 보존해 재연결의 옛 시작값을 반복하지 않는다.
seek/pause 갱신은 실제 변경 필드만 전달한다. 실제 OS 음량을 조회하고 설정 실패를 숨기지 않는다.

프로세스 회수는 시작 ticks로 신원을 대조한 관측 프로세스 트리 범위다. 이미 이탈한 데몬이나
OS에 확정된 기기 변경까지 취소했다고 표시하지 않는다. 자원 IPC는 작업 종료 때 interrupt하고
종료 확인에 실패하면 unknown을 반환한다. 같은 UID이므로 악의적인 코드를 가두는 경계가 아니다.
완료 파일은 다음 실행 때 7일 경과분을 정리하고 전송 핀은 실패/재시작에도 유지한다.

검증:

- 전체 backend 회귀(시스템 검사 포함): **10,496 passed, 13 skipped**, 246.95초.
  최초 샌드박스 실행은 브라우저·소켓·프로세스 권한 차단으로 실패했고, 해당 권한을 허용한 재실행 결과다.
- 마지막 실행·전송·미디어·기존 폰/PC 계약 묶음: **165 passed, 1 deselected**.
  실제 Python worker를 호스트 별도 프로세스에서 실행해 JSON/한글·예외·FD 출력·상한·shell timeout을 검증했다.
  가짜 Android 브리지와 실제 resident HTTP 저장소로 능력 협상·주인 검사·취소 경합·info 병행·중복 방지·전송 재개를 검증했다.
- arm32(Python3.11), arm64(Python3.12) Debug APK 빌드 성공. 기존 Android JVM 단위 검사 **각 5개 통과**.
  APK 안의 새 Python 모듈·fcntl 확장과 backend 계약/실행/전송/중앙/API 소스 일치를 검사했다.
- 어휘 빌드 정합성·층 가드·은퇴 교재 검사 통과. 기존 용례68개 검토, 신규 합성 용례10개 등록·벡터 색인·학습 JSON 반영.
- 빌드·시험은 정본 작업트리 기준이다. 시작 전에 있던 캘린더·번역·폰 연결 유지 변경은 이번 커밋에 포함하지 않는다.

APK: `phone-companion/app/build/outputs/apk/{arm32,arm64}/debug/app-{arm32,arm64}-debug.apk`.
실행 명령과 재현용 합성 용례는 `data/idioms/phone_execution_seeds.json`에 보존한다.
현재 USB ADB 목록은 비어 있어 삼성0/삼성1에
설치하지 않았다. Android 9 arm32·현대 arm64 실기에서 볼륨·백그라운드 서비스 시작·취소·
카메라/마이크 해제·프로세스 PSS·재부팅/망 단절·자연어 AI 선택은 아직 인수하지 않았다.
중앙 Windows/Linux에서의 실사용도 미검증이다. APK 빌드와 호스트 모의 시험을 실기로 간주하지 않는다.
