# IBL 전환 구현·배포 기록

2026-09-23, 정본 `/Users/kangkukjin/Desktop/AI/indiebizOS`의 main에서 순서대로 구현했다.
모델 비교·상상훈련·코퍼스 일괄 재작성은 수행하지 않았다.

## 정본 반영

| 단계 | 구현과 확인 | 커밋 |
| --- | --- | --- |
| 작성·저장·예약 실행 연결 | 번역 원문 보존, 새 검사 UI, 원문 판본 고정, 저장 함수·스케줄·트리거 연결, 주 교재 갱신 | `306dc11f` |
| 공통 도구 계약 | edit/grep/search/crawl의 인자·반환·효과·조건부 계약, 저장 함수 describe | `2c01c323` |
| 입력 함수 축적 | 개인 입력값 없는 AST 포장, 기존 반성 호출의 선택·작명, 출처 확인, 실제 후속 호출에서만 실적 기록 | `64c2a7b0` |
| 재개 운영 | 참조 의존성 지문, 상태·시각·회수 조회, 완료 기록만 보존 기간·용량에 따라 정리 | `d4fb1cda` |

배포 마무리에서는 이름만 다른 동일 함수의 중복 축적도 차단하고, 스크립트의 패키지 초기화·상대 import 의존성을 확인했다.
주 교재는 `data/system_docs/ibl.md`, 조합 교재와 workflow 교재도 현재 작성법을 가르친다.
과거 사례의 원문·실행 실적은 보존한다. 무표기 과거 저장 프로그램의 호환 해석도 유지한다.

## 대상별 상태

- **소유자 Mac**: 관리 제어자로 현재 백엔드를 기동하고 실행 코드 지문과 파일 지문의 일치를 확인했다.
  HTTP에서 새 함수의 inputs 실행, 같은 핸들 재개, 완료 기록 조회, 변경 입력의 재개 거절을 확인했다.
- **PC 회원**: `helper/dist/`의 Windows x64, Mac arm64/x64, Linux x64 도우미를 재빌드했다.
  기존 회원 설치 화면의 설치 ZIP 생성 경로가 이 파일을 사용한다. 다른 PC의 기존 설치본은 자동 교체되지 않는다.
  프로토콜이 부족하면 최신 **PC 도우미**를 다시 내려받으라는 안내를 반환한다.
- **소유자 Android**: `phone-companion/app/build/outputs/apk/debug/app-debug.apk`를 빌드했다.
  APK 내부에서 최신 엔진 모듈과 Chaquopy requirements의 filelock 포함을 확인했다. `.env`는 번들하지 않았다.
  adb 연결 기기는 0대여서 기기 설치·실기기 호출은 아직 하지 못했다.
- **Android 회원**: `:member`에는 로컬 Python/Bash/Node 인터프리터가 없다. 이 제품 계약은 유지한다.
  PC 도우미 업데이트가 필요한 경우와 Android 회원의 미지원 범위를 안내에서 구분한다.

## 소유자 Android 설치

기존 소유자 폰을 USB로 연결하고 USB 디버깅을 허용한 뒤, 정본 루트에서:

```bash
export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"
adb devices
adb install -r phone-companion/app/build/outputs/apk/debug/app-debug.apk
```

앱을 다시 열면 내장 엔진이 시작된다. 새 폰이라 키 주입도 필요하면 기존 설치 경로를 사용한다:

```bash
./phone-companion/scripts/setup_phone.sh --build
```

설치 후 로컬 연결 확인:

```bash
adb forward tcp:8788 tcp:8765
curl --fail http://127.0.0.1:8788/ibl/capabilities
adb forward --remove tcp:8788
```

폰 인증 설정에 따라 이 조회에는 기존 폰 인증 헤더가 필요할 수 있다. 키를 문서나 명령 출력에 복사하지 않는다.
실기기 설치 확인 전에는 APK 빌드 완료를 폰 전환 완료라고 기록하지 않는다.

## 배포 파일 지문

이 빌드의 SHA-256이며 설치 확인을 대신하지 않는다.

| 파일 | 바이트 | SHA-256 |
| --- | ---: | --- |
| `phone-companion/app/build/outputs/apk/debug/app-debug.apk` | 73904331 | `44161ac592205baedd07a1bf83f1b0ae03b87e568a61c112966b957f650a4c00` |
| `helper/dist/indiebiz-helper-linux` | 11612322 | `056d0b72f78c33d5ad4f6918f1a7f09a2068b8cae046a8f039b7ebe5312755a8` |
| `helper/dist/indiebiz-helper-mac-amd64` | 11832144 | `829962d0f912f6cd94afaa2e9c39d6695cb70887fcde2a9375e99f5484d43f81` |
| `helper/dist/indiebiz-helper-mac-arm64` | 11312786 | `35e1dd6d288347863a96a45c7b9b4732dfdd3758ef7377df1ad90dc9eaa45c69` |
| `helper/dist/indiebiz-helper-win.exe` | 11939328 | `70bedaee2fadbb92aac9bb56eaa56f4eccf57f1ae776e2cbe96a53aec3005548` |

## Mac 실제 실행 확인

관리 상태 `ACTIVE/ready`, 실행 코드 지문 `1c152dcbd39fe3e8714ab07e57fed8825cd7319b8890724a76b695154f5b0633`가 디스크와 일치했다.
명시 입력 6을 함수로 받아 7을 반환했고 같은 run_id의 재개도 7을 반환했다. recover는 completed, 입력 8로 바꾼 재개는 RESUME_CHANGED로 거절했다.

## 검증 범위와 재현 명령

- 작성·저장·예약 호출, 네 도구 계약, 입력 함수 저장·재호출, 개인값/개인 경로 제외, 실패·부분 결과 의미를 회귀 검사한다.
- 원장 검사는 실제 SQLite 영수증과 잠금으로 완료·중단·불명 보존과 정리, 재개 거절을 확인한다.
- 교재 코드 자체도 파서·컴파일러·실행기로 검사한다. 크롤링 모의 응답은 현재 실제 반환 계약을 따른다.
- 전체 백엔드: `.venv/bin/python -m pytest backend/ -q -o addopts=''`. 관련 실패 수정 후 표적 검사 55건, 의존성·재개 검사 40건, 입력 함수·증류 검사 52건 통과.
- 프런트엔드: `npx tsc -p tsconfig.app.json`, `npm run build` 통과. 번들 크기 경고는 남지만 빌드 실패는 없다.
- 도우미: `go test ./...`, `bash helper/build.sh` 통과.
- Android: `:app:assembleDebug` 통과, APK 내 최신 소스·filelock·비밀 파일 제외 확인. 실기기 검사는 연결 후 수행한다.
- 어휘·파생 문서 `build_ibl_nodes.py --check`, 층 구조 검사, 커밋 관문을 적용한다.
