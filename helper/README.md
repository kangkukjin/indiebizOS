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
