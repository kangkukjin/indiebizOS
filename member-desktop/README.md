# 회원 데스크톱 배포와 업데이트

설치 제품의 범위·실제 기기 인수는 `../docs/MEMBER_DESKTOP_DESIGN_2026_10_15.md` §14–15를 따른다.

## 미리보기

`node member-desktop/build.cjs`는 macOS Apple Silicon ZIP,
`--x64`는 Intel Mac, `--win`은 Windows NSIS를 만든다.
미리보기 생성은 배포 서명이나 실제 Windows 설치 인수를 의미하지 않는다.
공개키·채널을 지정하지 않은 설치물에서는 업데이트 확인·설치가 비활성화된다.

## 배포 신뢰 설정

배포자는 저장소 밖에서 Ed25519 개인키를 보관하고 공개키만 설치물에 넣는다.
개인키·인증서·암호를 저장소·회원 PC·중앙 API에 넣지 않는다.

- `MEMBER_UPDATE_PUBLIC_KEY`: PEM 공개키 파일 경로.
- `MEMBER_UPDATE_FEED`: OS/아키텍처별 `current.json`의 고정 HTTPS URL.
- `CSC_LINK` 또는 `CSC_NAME` 및 OS별 서명/공증 자격: electron-builder의 배포 설정.

`--release`는 배포 서명과 업데이트 신뢰 설정이 없으면 실패한다.
macOS 공증과 Windows 서명은 실제 배포 자격으로 수행하고 대상 OS에서 검증한다.
코드에 임시 테스트 키를 내장하거나 테스트 키로 운영 배포하지 않는다.

## 호환 런타임 발행

화면 두 파일과 Go 실행부를 하나의 서명 manifest에 묶는다.
OS별 실행부는 해당 배포 판본의 빌드 산출물을 사용한다.
배포자 OS 서명과 권한 인수도 완료한 실행부를 제공한다.
다음 명령은 로컬 발행 디렉터리만 만들며 네트워크 업로드는 하지 않는다.

```sh
node member-desktop/publish-runtime.cjs \
  --source member-desktop \
  --helper /absolute/path/to/signed/indiebiz-member \
  --out /absolute/path/to/publication/mac-arm64 \
  --base https://publisher.example/member/mac-arm64/ \
  --version 0.1.2 --sequence 2 --platform darwin --arch arm64 \
  --key /private/release/member-ed25519.pem
```

`--platform win32 --arch x64`에서는 Windows 실행부를 지정한다.
`--expires`는 Unix 초이며 생략하면 발행 시점부터 30일이다.
sequence는 해당 채널에서 계속 증가해야 하고 같은 발행 디렉터리를 덮어쓰지 않는다.
먼저 sequence 디렉터리의 파일을 공개하고 마지막에 `current.json`을 원자적으로 교체한다.
전체 파일은 피드와 같은 HTTPS origin에 있어야 하며 리디렉션은 허용하지 않는다.

설치 앱은 공개키 서명, 만료, OS/아키텍처, shell/protocol 판본,
파일 이름·크기·SHA-256을 확인한다. 허브 주소나 등록 초대로 업데이트 신뢰를 바꾸지 않는다.
등록된 앱은 시작 60초 뒤와 6시간 간격으로 서명된 최신 판본 정보만 확인한다.
새 판본이 있으면 상단 탐색줄에 **새 업데이트 있음** 버튼만 표시한다.
버전이 바뀌어도 팝업·시스템 알림·재촉하는 배너를 띄우거나 자동 설치하지 않는다.
사용자가 버튼을 누르면 채널을 다시 확인하고, 그때 최신 버전을 대상으로 **설치할까요?**를 묻는다.
**설치**를 선택해야 파일 다운로드와 적용을 시작한다. 취소하면 버튼만 남고 계속 사용할 수 있다.
확인 창에 표시한 판본만 적용하며, 확인 도중 나온 다른 판본을 대신 설치하지 않는다.
앱 표면의 설정 → 앱 업데이트에서도 직접 확인·설치할 수 있다.
이전 자동 적용 설정은 폐기하며 새 동의로 간주하지 않는다.
실패한 sequence는 자동 재시도하지 않는다. 수정 릴리스에 새 sequence를 부여한다.

## 적용과 복구

1. 신규 작업을 막고 현재 작업을 마칠 때까지 기다린다. 진행 작업의 승인·중단은 가능하다.
2. 기존 실행부 종료를 확인하고 각 로컬 회원 DB를 SQLite `VACUUM INTO`로 백업한다.
3. pending 기록을 저장한 뒤 후보 실행부를 시작한다. 후보에는 신규 작업을 허용하지 않는다.
4. DB 무결성·protocol과 새 화면의 시작 신호를 확인하고 현재 릴리스를 확정한다.
5. 실패하면 후보를 종료하고 이전 실행부와 DB를 복구한다. 적용 중 종료되면 다음 시작에서 복구한다.

이전·실패 DB와 사본은 앱 데이터의 `updates/snapshots` 및 해당 workspace에 남는다.
사용자 작업 폴더는 업데이트로 되돌리지 않는다. 부팅 확정 후에 생긴 새 기록도 자동으로 버리지 않는다.
백업 손상·실행부 종료 불명은 복구 성공으로 숨기지 않고 중단한다.

런타임 업데이트는 `workspace.html`, `workspace.cjs`, Go 실행부만 바꾼다.
Electron 엔진, main/preload, 서명 신뢰 키, OS 설치 권한은 새 서명 설치물로 갱신한다.
이 범위를 벗어난 shell 판본은 다운로드·적용하지 않는다.
사용자 선택형 설치는 앱 0.1.2 / shell 2부터 제공하므로 기존 shell 1 앱에는 전체 설치물을 먼저 설치해야 한다.
전체 설치 후에는 서명·파일 검증을 통과한 이전 shell 런타임 대신 새 내장 런타임을 사용하고,
기존 대화 DB·사용자 파일·업데이트 사본·sequence 이력은 보존한다.
실제 원격 전달에는 위 공개키와 운영 HTTPS 채널을 설정한 설치물 및 서명 릴리스 발행이 필요하다.

## 검사

```sh
cd helper
go test ./...
go build -o /tmp/indiebiz-member-test .
cd ..
MEMBER_DESKTOP_TEST_BINARY=/tmp/indiebiz-member-test node --test member-desktop/test/*.test.cjs
MEMBER_DESKTOP_TEST_BINARY=/tmp/indiebiz-member-test .venv/bin/python3 -m pytest backend/test_member_desktop_integration.py
.venv/bin/python3 -m pytest backend/test_member_workspace_ui.py
```

통합 검사는 임시 서버·합성 자격·임시 DB만 사용한다. 모델 호출 대역과 UI 브리지 대역은
실제 회원 PC 두 대, 실제 API 모델, OS 권한, 운영 인증서와 HTTPS 채널 인수를 대체하지 않는다.

## 화면만 발행하기 (shell 3)

앱 0.1.3 / shell 3부터 `kind: ui`는 `display.json` **한 파일**만 받는다.
최초 지원 설치물 갱신 후 일반 화면 수정에는 Go·DB·실행부 재기동이 없다.
`python3 scripts/build_member_desktop.py`가 같은 원본에서 화면과 표시 모듈을 만든다.

```sh
node member-desktop/publish-runtime.cjs \
  --kind ui --source member-desktop \
  --out /absolute/path/to/publication/mac-arm64 \
  --base https://publisher.example/member/mac-arm64/ \
  --version 0.1.3 --sequence 1 --platform darwin --arch arm64 \
  --key /private/release/member-ed25519.pem
```

화면과 실행부 sequence는 각 종류에서 증가한다. 한 피드의 `current.json`은 지금 제공하는
종류를 가리키며, 화면 파일은 `ui/<sequence>/display.json`에 남는다. 코드·상태·브리지 호스트
지문이 다르면 UI-only 적용을 거절한다. 열린 화면과 안쪽 앱 프레임은 자기 표시 함수·스타일·
정적 DOM만 인계한다. 초안·선택·작업·승인·미디어·iframe과 실행 요청은 기존 소유자에 남는다.
UI pending 중 종료는 이전 UI로 복구하며, UI 실패로 DB 스냅샷을 복구하지 않는다.
사용자 설치 확인과 서명 신뢰는 기존 런타임 업데이트와 동일하다.

## macOS 권한과 실행부의 코드 신원

업데이트 매니페스트의 Ed25519 서명은 배포 파일의 출처·변조를 검사한다.
macOS 화면 기록·손쉬운 사용 권한을 이어 주는 OS 코드 서명은 별도다.
개발 미리보기의 ad-hoc 서명은 파일 내용에 묶이므로 재빌드 후 권한 유지 인수에 쓰지 않는다.

macOS 런타임 업데이트는 설치물에 포함된 실행부와 후보의 코드 서명을 모두 검증한다.
`cdhash` 기반 임시 신원·서명 손상·서로 다른 designated requirement는 실행부 종료와
DB 백업 전에 거절한다. UI-only는 실행 파일을 교체하지 않으므로 이 검사를 요구하지 않는다.
기존 미리보기에서 정식 서명으로 옮길 때는 전체 서명 설치물이 먼저 필요하다.
배포자는 앱과 실행부의 식별자·인증서 기반 신원을 판본 사이에 유지해야 한다.
이 검사는 서명 불일치로 인한 권한 손실 위험을 차단하며, OS 정책·사용자 철회까지 포함한
모든 상황의 권한 유지를 보장하지 않는다. 실제 기기에서 최초 허용 후 업데이트·재시작까지
검사해야 한다. 개인키 사용과 정식 서명·공증은 개발 시험이 대신 수행하지 않는다.
