# 회원 데스크톱 배포와 업데이트

설치 제품의 범위·실제 기기 인수는 `../docs/MEMBER_DESKTOP_DESIGN_2026_10_15.md` §14–15를 따른다.

## 미리보기

`node member-desktop/build.cjs`는 macOS Apple Silicon ZIP,
`--x64`는 Intel Mac, `--win`은 Windows NSIS를 만든다.
미리보기 생성은 배포 서명이나 실제 Windows 설치 인수를 의미하지 않는다.
공개키·채널을 지정하지 않은 설치물에서는 자동 업데이트가 비활성화된다.

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
다운로드와 적용은 분리되며 회원이 자동 적용을 켜면 시작 후와 6시간 간격으로 확인한다.
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
