# 원격 Finder 설정 가이드

IndieBiz OS의 원격 Finder를 사용하면 외부에서 PC의 파일에 접근할 수 있습니다.

## 1. 사전 준비

### 필요한 것
- Cloudflare 계정 (무료)
- Cloudflare에 연결된 도메인 (있으면 무료, 없으면 임시 URL 사용)
- IndieBiz OS가 실행 중인 PC

## 2. IndieBiz OS 설정

1. **IndieBiz OS 런처** 실행
2. **메인 메뉴** (로고 클릭) → **설정** 클릭
3. **원격 Finder** 탭 선택
4. **원격 Finder 활성화** 토글 ON
5. **접근 비밀번호** 설정 (필수)
6. **접근 허용 경로** 추가
   - 폴더 아이콘 버튼을 클릭하면 폴더 선택 다이얼로그가 열립니다
   - 또는 경로를 직접 입력 후 + 버튼을 클릭해도 됩니다
   - 예: `/Users/username/Videos` (동영상 폴더)
   - 예: `/Users/username/Documents` (문서 폴더)
7. **설정 저장** 클릭

## 3. Cloudflare Tunnel 설정

### 3.1 cloudflared 설치

**macOS:**
```bash
brew install cloudflared
```

**Linux:**
```bash
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb
```

**Windows:**
```powershell
winget install Cloudflare.cloudflared
```

### 3.2 Cloudflare 로그인

```bash
cloudflared tunnel login
```

브라우저가 열리면 Cloudflare 계정으로 로그인하고 도메인을 선택합니다.

### 3.3 터널 생성

```bash
cloudflared tunnel create indiebiz-nas
```

터널 ID가 출력됩니다 (예: `a1b2c3d4-...`). 기억해두세요.

### 3.4 DNS 레코드 추가

```bash
cloudflared tunnel route dns indiebiz-nas nas.yourdomain.com
```

`nas.yourdomain.com`을 원하는 서브도메인으로 변경하세요.

### 3.5 설정 파일 생성

`~/.cloudflared/config.yml` 파일 생성:

```yaml
tunnel: a1b2c3d4-...  # 위에서 얻은 터널 ID
credentials-file: /Users/username/.cloudflared/a1b2c3d4-....json

ingress:
  - hostname: nas.yourdomain.com
    service: http://localhost:8765
  - service: http_status:404
```

### 3.6 터널 실행

IndieBiz OS **설정 → 터널 탭**에서 토글로 실행합니다:
1. 터널 이름이 자동으로 채워져 있는지 확인
2. **터널 실행 토글 ON** → 터널 시작
3. **자동 시작 토글 ON** → IndieBiz OS 시작 시 자동 실행

또는 터미널에서 직접 실행:
```bash
cloudflared tunnel run indiebiz-nas
```

## 4. 접속 테스트

1. 브라우저에서 `https://nas.yourdomain.com/nas/app` 접속
2. 설정한 비밀번호 입력
3. 파일 탐색!

## 5. 자동 시작 설정 (선택사항)

### macOS (launchd)

```bash
sudo cloudflared service install
```

### Linux (systemd)

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

### Windows

```powershell
cloudflared service install
```

## 6. 도메인 없이 사용하기 (임시 URL)

도메인이 없어도 임시 URL로 테스트할 수 있습니다:

```bash
cloudflared tunnel --url http://localhost:8765
```

`https://random-words.trycloudflare.com` 형태의 임시 URL이 생성됩니다.
단, PC 재시작 시 URL이 변경됩니다.

## 7. 보안 주의사항

- **비밀번호는 반드시 설정하세요**
- 허용 경로를 최소화하세요 (전체 접근 허용 비권장)
- 민감한 파일이 있는 경로는 제외하세요
- 정기적으로 비밀번호를 변경하세요

## 8. 문제 해결

### 접속이 안 될 때

1. IndieBiz OS가 실행 중인지 확인
2. `cloudflared tunnel run` 명령이 실행 중인지 확인
3. 방화벽 설정 확인

### 502 Bad Gateway

IndieBiz OS 백엔드가 실행 중이 아닙니다:
```bash
cd indiebizOS/backend && python api.py
```

### 인증서 오류

cloudflared가 최신 버전인지 확인:
```bash
cloudflared update
```

---

## 구조 요약

```
[스마트폰/외부 PC]
        │
        │ https://nas.yourdomain.com/nas/app
        ↓
[Cloudflare (SSL, DDoS 보호)]
        │
        │ Tunnel (암호화)
        ↓
[집 PC - cloudflared]
        │
        │ localhost:8765
        ↓
[IndieBiz OS]
        │
        ├── /nas/app     → 웹앱 UI
        ├── /nas/files   → 파일 목록 API
        └── /nas/file    → 파일 스트리밍 API
```

**끝!** 이제 어디서든 PC의 파일에 안전하게 접근할 수 있습니다. 🎉
