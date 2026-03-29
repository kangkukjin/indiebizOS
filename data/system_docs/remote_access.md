# 원격 접근 시스템 (Remote Access)

IndieBiz OS의 원격 접근 시스템입니다. Cloudflare Tunnel을 통해 외부에서 안전하게 홈 서버를 제어하고 파일에 접근할 수 있습니다.

## 개요

### 두 가지 원격 기능

| 기능 | 경로 | 목적 |
|-----|------|------|
| **원격 Finder** | `/nas/app` | 파일 탐색, 동영상 스트리밍, 다운로드 |
| **원격 런처** | `/launcher/app` | 시스템 AI/에이전트 채팅, 스위치 실행 |

각 기능은 **별도의 비밀번호**로 독립적으로 활성화할 수 있습니다.

### 핵심 특징
- **Cloudflare Tunnel**: 포트 포워딩/DDNS 없이 안전한 외부 접근
- **자동 SSL**: Cloudflare가 HTTPS 인증서 자동 관리
- **세션 인증**: 기능별 독립적인 비밀번호 및 세션 관리
- **경로 보호**: 허용된 경로만 접근 가능 (원격 Finder)

### 활용 예시

**개인 NAS로 활용 (원격 Finder)**
- 집에 미니 PC를 두고, 외출 중 스마트폰으로 파일 탐색/동영상 스트리밍
- 여행 중에도 집 PC에 저장된 영화나 사진을 바로 감상
- 별도의 NAS 장비 없이 기존 PC로 개인 클라우드 구축

**원격 AI 서버로 활용 (원격 런처)**
- 외출 중 스마트폰에서 모든 프로젝트 에이전트에게 질문/지시
- 투자 에이전트에게 시장 분석 요청, 법률 에이전트에게 법령 검색 등
- 스위치 한 번 터치로 뉴스 수집, 리포트 생성 등 자동화 작업 실행
- 집 PC의 AI 에이전트 전체를 원격으로 구동하는 개인 AI 서버

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        외부 네트워크                              │
│                                                                  │
│  사용자 브라우저 ──► https://home.mydomain.com/nas/app          │
│                  └► https://home.mydomain.com/launcher/app      │
│                              │                                   │
└──────────────────────────────┼───────────────────────────────────┘
                               │ (Cloudflare Edge)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Cloudflare Tunnel                           │
│                                                                  │
│  cloudflared tunnel run ◄──► Cloudflare 네트워크                │
│         │                                                        │
└─────────┼────────────────────────────────────────────────────────┘
          │ localhost:8765
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    IndieBiz OS 백엔드                            │
│                      (FastAPI :8765)                            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 원격 Finder (api_nas.py)        원격 런처 (api_launcher_web.py)   │
│  │                                                           │   │
│  │ /nas/auth/login - 로그인       /launcher/auth/login - 로그인    │
│  │ /nas/files      - 파일 목록     /launcher/app      - 웹 앱     │
│  │ /nas/file       - 스트리밍                                │   │
│  │ /nas/app        - 웹 앱        → 기존 API 호출:           │   │
│  │                                  /system-ai/chat          │   │
│  │                                  /projects/*/chat         │   │
│  │                                  /switches                │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. 원격 Finder

외부에서 홈 서버의 파일에 접근하고 동영상을 스트리밍합니다.

### 기능
- 폴더 탐색 (Finder 스타일 UI)
- 동영상 스트리밍 (구간 탐색 지원)
- 텍스트 파일 미리보기
- 파일 다운로드

### API 엔드포인트

| 엔드포인트 | 메서드 | 인증 | 설명 |
|-----------|--------|------|------|
| `/nas/config` | GET/PUT | - | 설정 조회/저장 |
| `/nas/auth/login` | POST | - | 로그인 → 세션 발급 |
| `/nas/auth/logout` | POST | ✓ | 로그아웃 |
| `/nas/files` | GET | ✓ | 파일/폴더 목록 |
| `/nas/file` | GET | ✓ | 파일 스트리밍 (Range 지원) |
| `/nas/text` | GET | ✓ | 텍스트 파일 (10MB 제한) |
| `/nas/app` | GET | - | 웹 앱 HTML |

### 설정 파일
경로: `data/nas_config.json`

```json
{
  "enabled": true,
  "password": "your_password",
  "allowed_paths": [
    "/Users/username/Videos",
    "/Users/username/Documents"
  ]
}
```

### 보안
- **경로 보호**: `allowed_paths`에 지정된 디렉토리만 접근 가능
- Path Traversal (`..`) 차단
- 심볼릭 링크 우회 방지

---

## 2. 원격 런처

외부에서 시스템 AI와 프로젝트 에이전트를 제어합니다.

### 기능
- **시스템 AI 채팅**: IndieBiz OS 전체 제어
- **프로젝트 에이전트 채팅**: 개별 프로젝트 AI와 대화
- **스위치 실행**: 원클릭으로 자동화 작업 실행

### API 엔드포인트

| 엔드포인트 | 메서드 | 인증 | 설명 |
|-----------|--------|------|------|
| `/launcher/config` | GET/POST | - | 설정 조회/저장 |
| `/launcher/auth/login` | POST | - | 로그인 → 세션 발급 |
| `/launcher/auth/logout` | POST | ✓ | 로그아웃 |
| `/launcher/app` | GET | - | 웹 앱 HTML |

### 설정 파일
경로: `data/launcher_web_config.json`

```json
{
  "enabled": true,
  "password": "your_password"
}
```

### 웹 앱 기능
- 시스템 AI 채팅 인터페이스
- 프로젝트 목록 사이드바
- 에이전트 선택 및 채팅
- 스위치 목록 및 실행 버튼
- 다크 테마 UI
- 모바일 반응형 디자인

---

## 사전 준비: Cloudflare 가입 및 설정

원격 접근을 사용하려면 **Cloudflare 계정**과 **도메인**이 필요합니다.

### 1단계: Cloudflare 계정 가입

1. **https://dash.cloudflare.com/sign-up** 접속
2. 이메일과 비밀번호 입력
3. 이메일 인증 완료
4. **무료(Free) 플랜** 선택 (Tunnel은 무료 제공)

### 2단계: workers.dev 서브도메인 활성화 (필수)

Cloudflare 가입 후 **Workers & Pages에 한 번 접속**해야 무료 서브도메인이 생성됩니다.

1. Cloudflare 대시보드 → **Workers & Pages** 클릭
2. 처음 접속하면 자동으로 서브도메인 생성됨
3. `username.workers.dev` 형태의 서브도메인 확인

> ⚠️ **참고**: workers.dev는 Workers/Pages 전용이라 Tunnel에 직접 사용할 수 없습니다.
> Tunnel을 사용하려면 아래 방법으로 **자체 도메인**이 필요합니다.

### 3단계: 도메인 추가 (Tunnel 사용 시 필요)

Cloudflare Tunnel을 사용하려면 **Cloudflare에 등록된 도메인**이 필요합니다.

#### 방법 A: 기존 도메인 이전 (권장)
1. Cloudflare 대시보드 → **Add a Site**
2. 보유한 도메인 입력 (예: `mydomain.com`)
3. **Free 플랜** 선택
4. DNS 레코드 스캔 확인
5. 도메인 등록기관(가비아, Namecheap 등)에서 **네임서버 변경**
   - Cloudflare가 제공하는 네임서버로 변경
   - 예: `xxx.ns.cloudflare.com`, `yyy.ns.cloudflare.com`
6. 네임서버 전파 대기 (최대 24시간, 보통 몇 시간)

#### 방법 B: Cloudflare에서 도메인 구매
1. Cloudflare 대시보드 → **Domain Registration** → **Register Domains**
2. 원하는 도메인 검색 및 구매 (원가로 제공, 마크업 없음)
3. 즉시 Cloudflare에 연동됨

#### 💡 도메인을 몰라도 됩니다!

에이전트가 `cf_zones_list` 도구로 등록된 도메인을 자동 조회합니다.
"원격 접근 설정해줘"라고만 하면 에이전트가 알아서 도메인을 찾습니다.

### 4단계: API 토큰 발급

시스템 AI가 Cloudflare를 제어하려면 **API 토큰**이 필요합니다.

1. **https://dash.cloudflare.com/profile/api-tokens** 접속
2. **Create Token** 클릭
3. **Edit Cloudflare Workers** 템플릿 선택 (또는 Custom Token)
4. 필요한 권한 추가:
   - `Zone:Zone:Read`
   - `Zone:DNS:Edit`
   - `Account:Cloudflare Tunnel:Edit`
   - `Account:Workers R2 Storage:Edit` (R2 사용 시)
   - `Account:Workers Scripts:Edit` (Workers 사용 시)
5. **Continue to summary** → **Create Token**
6. 생성된 토큰 복사 (⚠️ 한 번만 표시됨!)

### 5단계: Account ID 확인

1. Cloudflare 대시보드에서 아무 도메인 선택
2. 우측 하단 **API** 섹션에서 **Account ID** 복사

### 6단계: IndieBiz OS에 설정

시스템 AI에게 다음과 같이 요청:

```
Cloudflare API 토큰을 환경변수로 저장해줘.
토큰: [복사한 토큰]
Account ID: [복사한 Account ID]
```

또는 직접 `backend/.env` 파일에 추가:

```
CLOUDFLARE_API_TOKEN=your_api_token_here
CLOUDFLARE_ACCOUNT_ID=your_account_id_here
```

### 7단계: cloudflared 설치

터미널에서 직접 설치하거나, 시스템 AI에게 "cloudflared 설치해줘"라고 요청합니다.

```bash
# macOS (Homebrew)
brew install cloudflared

# macOS (직접 다운로드)
curl -L -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz
tar -xzf cloudflared
sudo mv cloudflared /usr/local/bin/

# Linux (Ubuntu/Debian)
curl -L -o cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

# Linux (다른 배포판)
curl -L -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/
```

### 8단계: Cloudflare 로그인 (최초 1회)

```bash
cloudflared tunnel login
```

브라우저가 열리면:
1. Cloudflare 계정으로 로그인
2. 터널에 사용할 **도메인 선택**
3. 인증 완료 후 인증서가 자동 저장됨 (`~/.cloudflared/cert.pem`)

---

## 원격 접근 설정: 단계별 가이드

사전 준비(1~8단계)가 완료되면, 시스템 AI에게 명령하여 원격 접근을 설정합니다.

### 9단계: 환경변수 설정

시스템 AI에게 Cloudflare API 정보를 환경변수로 저장하도록 요청합니다.

**시스템 AI에게 입력:**
```
cloudflare 도구의 환경변수를 설정해줘.
CLOUDFLARE_API_TOKEN: [4단계에서 복사한 토큰]
CLOUDFLARE_ACCOUNT_ID: [5단계에서 복사한 Account ID]
```

**예시:**
```
cloudflare 도구의 환경변수를 설정해줘.
CLOUDFLARE_API_TOKEN: abc123xyz789...
CLOUDFLARE_ACCOUNT_ID: 1234567890abcdef
```

시스템 AI가 `backend/.env` 파일에 환경변수를 저장합니다.

### 10단계: IndieBiz OS 재시작

환경변수가 적용되도록 IndieBiz OS를 재시작합니다.

- 런처 창을 닫고 다시 실행
- 또는 터미널에서 백엔드 재시작

### 11단계: 터널 설정

시스템 AI에게 터널 설정을 요청합니다. (프로젝트 생성 불필요)

**시스템 AI에게 입력:**
```
원격 접근 터널을 설정해줘.
```

**또는 도메인을 알면:**
```
home.mydomain.com 도메인으로 터널을 설정해줘.
```

시스템 AI가 자동으로:
1. `cf_api`로 등록된 도메인 목록 조회
2. 사용자에게 **기기 구분 이름** 질문 (예: "home", "office", "macbook")
3. bash로 `cloudflared tunnel create {터널이름}` 실행
4. bash로 `cloudflared tunnel route dns {터널이름} finder-{기기이름}.{도메인}` 실행
5. bash로 `cloudflared tunnel route dns {터널이름} launcher-{기기이름}.{도메인}` 실행
6. `~/.cloudflared/config.yml` 파일 생성
7. `data/tunnel_config.json`에 터널 이름, 호스트명 자동 저장

> 💡 **다중 PC 지원**: 같은 Cloudflare 계정에서 여러 PC에 터널을 설정할 수 있습니다.
> 기기 구분 이름으로 호스트명이 겹치지 않도록 합니다.
> 호스트명 충돌 시 자동으로 `-2`, `-3` 접미사를 붙여 재시도합니다.

### 12단계: 원격 Finder/런처 활성화

런처의 **설정** (안경 메뉴 → 설정)에서:

1. **원격 Finder 탭**
   - 활성화 토글 ON
   - 비밀번호 설정 (강력한 비밀번호 사용)
   - 접근 허용할 폴더 경로 추가 (폴더 아이콘 버튼으로 선택 또는 직접 입력)
   - 외부 접속 URL이 자동 표시됨 (터널 설정 완료 시)

2. **원격 런처 탭**
   - 활성화 토글 ON
   - 비밀번호 설정 (Finder와 다른 비밀번호 권장)
   - 외부 접속 URL이 자동 표시됨 (터널 설정 완료 시)

### 13단계: 터널 실행

런처의 **설정 → 터널 탭**에서 터널을 관리합니다.

1. **터널 탭** 선택 (구름 아이콘)
2. **터널 이름**: 11단계에서 자동 저장됨 (수동 입력도 가능)
3. **터널 실행 토글** ON → 터널 자동 실행
4. **자동 시작 토글** ON → IndieBiz OS 시작 시 터널 자동 실행

> 💡 **터널 실행 상태**: 토글 옆에 초록색 점이 표시되면 정상 실행 중

**수동 실행이 필요한 경우 (터미널):**
```bash
cloudflared tunnel run indiebiz
```

### 14단계: 접속 확인

브라우저에서 접속하여 정상 작동 확인:

- **원격 Finder**: `https://home.mydomain.com/nas/app`
- **원격 런처**: `https://home.mydomain.com/launcher/app`

---

## 요약: 처음부터 끝까지

| 단계 | 작업 | 위치 |
|-----|------|------|
| 1 | Cloudflare 계정 가입 | dash.cloudflare.com |
| 2 | workers.dev 서브도메인 활성화 | Workers & Pages 방문 |
| 3 | 도메인 추가 (Tunnel용) | Cloudflare 대시보드 |
| 4 | API 토큰 발급 | Cloudflare 프로필 |
| 5 | Account ID 확인 | Cloudflare 대시보드 |
| 6 | IndieBiz OS에 설정 | 또는 .env 직접 편집 |
| 7 | cloudflared 설치 | 터미널 |
| 8 | cloudflared tunnel login | 터미널 (최초 1회) |
| 9 | **시스템 AI에게 환경변수 설정 요청** | IndieBiz OS |
| 10 | IndieBiz OS 재시작 | - |
| 11 | **시스템 AI에게 "터널 설정해줘"** | IndieBiz OS |
| 12 | 원격 Finder/런처 활성화 | 설정 다이얼로그 |
| 13 | **터널 실행 토글 ON** | 설정 → 터널 탭 |
| 14 | 접속 확인 | 브라우저 |

---

## Cloudflare Tunnel 설정 (상세)

### 도구 패키지: cloudflare

`cf_api` 도구로 Cloudflare API를 호출하고, bash로 `cloudflared` CLI를 실행합니다.

#### API 호출 예시

```python
# 도메인 목록 조회
cf_api(method="GET", endpoint="/zones")

# 터널 목록 조회
cf_api(method="GET", endpoint="/accounts/{account_id}/cfd_tunnel")

# DNS 레코드 추가
cf_api(
    method="POST",
    endpoint="/zones/{zone_id}/dns_records",
    body={"type": "CNAME", "name": "home", "content": "tunnel-id.cfargotunnel.com", "proxied": True}
)
```

> 💡 `{account_id}`는 환경변수에서 자동 치환됩니다.

#### CLI 명령 (bash 실행)

```bash
# 터널 생성
cloudflared tunnel create {터널이름}

# DNS 라우팅 (기기 구분 이름 포함)
cloudflared tunnel route dns {터널이름} finder-{기기이름}.{도메인}
cloudflared tunnel route dns {터널이름} launcher-{기기이름}.{도메인}

# 터널 실행 (설정 UI 토글 사용 권장)
cloudflared --config ~/.cloudflared/config.yml tunnel run {터널이름}
```

### cloudflared 자동 감지

백엔드는 `is_cloudflared_installed()` 함수(`api_tunnel.py`)로 cloudflared 설치 여부를 자동 감지합니다.
- 시스템 PATH 및 일반적인 설치 경로(`/usr/local/bin`, `/opt/homebrew/bin` 등)에서 바이너리를 탐색
- 터널 상태 API(`/tunnel/status`)에서 `cloudflared_installed` 필드로 설치 여부 반환
- 미설치 시 터널 시작 요청이 설치 안내 메시지와 함께 거부됨

### finder_hostname / launcher_hostname 분리 설정

`tunnel_config.json`에서 Finder와 Launcher에 별도 호스트명을 지정할 수 있습니다.

```json
{
  "tunnel_name": "indiebiz",
  "finder_hostname": "finder-home.mydomain.com",
  "launcher_hostname": "launcher-home.mydomain.com"
}
```

- **분리 호스트명**: Finder와 Launcher가 각각 독립된 서브도메인을 가짐 (예: `finder-home.example.com`, `launcher-home.example.com`)
- **단일 호스트명**: `~/.cloudflared/config.yml`에서 하나의 호스트명이 포트 8765로 매핑되면 양쪽 모두 동일한 호스트명을 사용
- `parse_ingress_hostnames()` 함수가 config.yml의 ingress 규칙을 파싱하여 서비스 포트/경로/호스트명 키워드 기반으로 자동 분류

### CORS 자동 설정

`tunnel_config.json`의 `finder_hostname`, `launcher_hostname` 값이 백엔드 시작 시 CORS 허용 origin에 자동 추가됩니다. 별도 설정 불필요.

### 수동 설정

1. **cloudflared 설치**
   ```bash
   # macOS
   brew install cloudflared

   # Linux
   curl -L -o cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared.deb
   ```

2. **Cloudflare 로그인** (최초 1회)
   ```bash
   cloudflared tunnel login
   # 브라우저에서 도메인 선택하여 인증
   ```

3. **터널 생성 및 라우팅**
   ```bash
   cloudflared tunnel create indiebiz
   cloudflared tunnel route dns indiebiz home.mydomain.com
   ```

4. **config.yml 생성**
   ```yaml
   # ~/.cloudflared/config.yml
   tunnel: {tunnel-id}
   credentials-file: ~/.cloudflared/{tunnel-id}.json

   ingress:
     - hostname: home.mydomain.com
       service: http://localhost:8765
     - service: http_status:404
   ```

5. **터널 실행**
   ```bash
   # 포그라운드
   cloudflared tunnel run indiebiz

   # 시스템 서비스로 등록 (부팅 시 자동 시작)
   sudo cloudflared service install
   ```

---

## 런처 설정 UI

**설정 → 원격 Finder / 원격 런처 탭**

각 탭에서:
- 활성화/비활성화 토글
- 비밀번호 설정
- 웹앱 URL 확인
- (원격 Finder만) 허용 경로 관리

---

## 시스템 통합

### 파일 위치

| 구분 | 파일 |
|-----|------|
| 원격 Finder 백엔드 | `backend/api_nas.py` |
| 원격 런처 백엔드 | `backend/api_launcher_web.py` |
| 터널 관리 백엔드 | `backend/api_tunnel.py` |
| 프론트엔드 설정 | `frontend/src/components/.../SettingsDialog.tsx` |
| Finder 설정 | `data/nas_config.json` |
| 런처 설정 | `data/launcher_web_config.json` |
| 터널 설정 | `data/tunnel_config.json` |
| Tunnel 도구 | `data/packages/installed/tools/cloudflare/` |

### API 라우터 등록

`backend/api.py`:
```python
from api_nas import router as nas_router
from api_launcher_web import router as launcher_web_router
from api_tunnel import router as tunnel_router

app.include_router(nas_router, tags=["nas"])
app.include_router(launcher_web_router, tags=["launcher-web"])
app.include_router(tunnel_router, tags=["tunnel"])
```

### 터널 관리 API

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/tunnel/config` | GET | 터널 설정 조회 |
| `/tunnel/config` | POST | 터널 설정 저장 |
| `/tunnel/start` | POST | 터널 실행 |
| `/tunnel/stop` | POST | 터널 중지 |
| `/tunnel/status` | GET | 터널 상태 확인 |

---

## 보안 고려사항

1. **별도 비밀번호**: Finder와 런처에 서로 다른 비밀번호 설정 권장
2. **강력한 비밀번호**: 외부 노출되므로 복잡한 비밀번호 사용
3. **허용 경로 제한**: 원격 Finder에서 민감한 폴더 제외
4. **Cloudflare Access**: 추가 인증 레이어가 필요한 경우 Zero Trust Access 정책 설정

---

## 문제 해결

### cloudflared 로그인 필요
```bash
cloudflared tunnel login
# 브라우저에서 Cloudflare 계정 로그인 후 도메인 선택
```

### 터널 연결 실패
1. `cloudflared tunnel run` 프로세스 확인
2. `~/.cloudflared/config.yml` 설정 확인
3. DNS 레코드 전파 대기 (몇 분 소요)

### 로그인 실패
1. 설정에서 기능 활성화 확인
2. 비밀번호 설정 확인
3. 브라우저 쿠키 삭제 후 재시도

---

*마지막 업데이트: 2026-03-27*
