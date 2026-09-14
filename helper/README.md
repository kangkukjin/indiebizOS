# indiebiz-helper — USB 손발(게스트 PC 헬퍼)

USB 로 낯선 PC 에 꽂아 실행하는 **얇은 손발**(Go 단일 실행파일, 런타임 불필요).
두뇌가 아니다 — 옆의 `indiebiz-helper.json` 에서 내 몸(허브) 주소와 limb key 를 읽어 허브에
아웃바운드로 붙고, 허브가 내려보내는 셸/파일 명령을 그 PC 에서 실행해 결과를 돌려준다.

## 빌드 (크로스컴파일, Go 설치 필요)

```bash
cd helper && ./build.sh
```

산출물: `dist/indiebiz-helper-win.exe`, `-mac-arm64`, `-mac-amd64`, `-linux`.
발급기(`[self:limb]{op:issue, os:...}`)가 대상 OS 실행파일을 USB 페이로드에 동봉한다.

## 실행 (그 PC 에서)

`indiebiz-helper.json` 과 실행파일을 같은 폴더에 두고 실행파일을 더블클릭.

```json
{ "base": "https://mac.example.ts.net", "key": "limb_…", "alias": "사무실PC" }
```

- `base` 내 몸(허브)의 공개 주소 — `/limb/*` 가 백엔드에 직접 닿는 direct host.
- `key` limb key (허브 비밀번호 아님. 이 손발 하나만 인가).
- 첫 접속은 승인 대기 → 허브에서 `[self:limb]{op:approve}` 승인 후 명령 시작.
- 창을 닫으면 손발이 떨어진다.

## 프로토콜

| 방향 | 엔드포인트 | 내용 |
|------|-----------|------|
| 접속 | `POST {base}/limb/connect` | `{key, host}` → 등록·승인상태 |
| 하행 | `POST {base}/limb/poll` | `{key, wait}` 롱폴 → 셸 봉투 jobs |
| 상행 | `POST {base}/limb/result` | `{key, job_id, result}` |

셸 봉투 op: `shell`(cmd/cwd/timeout) · `read`(path) · `write`(path/content) · `list`(path) · `info`.
1단계는 셸/파일만 — 화면 캡처·GUI 조작 없음(눈 없음).


## 회원 모드 (2026-09-14)

설정에 `"mode":"member"`를 넣는다. 기존 `limb` 모드는 변하지 않는다. neighbor_id로 발급한 키의 설정에는
회원 모드가 자동으로 들어가며, 서버도 회원 키의 구형 모드 접속을 거절한다. 접속 승인과 별도로 파일 쓰기·
명령·프로그램·장기기억 저장은 **회원의 로컬 화면에서 승인**한다. 위의 옛 승인 대기 설명과 달리 현재 유효한
일반 손발 키는 접속 시 자동 승인된다(명령 목적지 이름과 키 폐기로 관리).

회원 화면은 127.0.0.1 임의 포트에서 열린다. 설정 키는 브라우저에 보내지 않고 loopback 한시 토큰을 쓴다.
`data_dir`를 지정하지 않으면 사용자 설정 폴더/IndieBizMember/허브·키 해시 아래 member.db를 만든다.
동일 별칭의 다른 회원이 SQLite를 공유하지 않는다. 파일·기억·작업 원장은 회원 기기에만 쓴다.
`auto_allow`는 로컬 설정의 작업 op 목록이며 기본값은 비어 있다. 테스트의 자동 허용을 실사용 설정으로 복사하지 않는다.

재시도는 원래 request_key로 결과를 조회한다. 같은 키에 다른 내용은 거절한다. 실행 중 재시작은 unknown이다.
UI 결과 목록에서 미확인 작업을 확인하고, 효과를 내는 작업은 자동 반복하지 않는다.
프로그램은 list/register/run, 역할 인터프리터는 python3/bash/node다. .ibl 등록은 로컬 문장 원장에 보관한다.
resources는 프로그램 폴더 안의 자원 상대경로, dependencies는 필요한 패키지 기록이다. 실행 시 자동 설치는 없다.
화면의 기억 내보내기는 7종 내용 테이블+등록 파일+자원+의존성의 ZIP을 만든다. 작업 키/인증 키는 졸업 데이터가 아니다.
독립 설치본에서 `.venv/bin/python3 scripts/import_member_archive.py member-export.zip`로 가져온다.

검사: `go test -race ./...`, 배포 파일: `bash build.sh` (Windows amd64, macOS arm64/amd64, Linux amd64).
회원 공개 후보는 파일/문서/등록 프로그램과 라디오다. 문서의 임시 변환은 허브에서, 원본·결과는 회원 기기에 둔다.
라디오 media 봉투는 로컬 번들의 브라우저 오디오로 실행하고 실제 재생/중지/상태/볼륨 응답을 받는다.
별도 플레이어 설치는 필요 없다. 화면을 켜 두어야 하며 브라우저가 지원하는 스트림 형식에 한한다.
전달받은 media 명령은 한 번만 획득한다. 새로고침·연결 종료로 결과를 잃어도 자동 재생하지 않는다.

회원 승인 화면은 접속한 허브에서 받아 실행하지 않는다. scripts/build_member_shell.py가 공통 member_shell/launcher_app_common을
PC 바이너리와 APK의 정적 자산으로 파생한다. /m/app은 별도 웹 폴백이다. `build_member_shell.py --check`로 번들 드리프트를 검사한다.
