# Cloudflare 사용 가이드

이 가이드는 cf_api 도구와 CLI 명령으로 Cloudflare 서비스를 사용하는 방법을 설명합니다.

## cf_api 도구 사용법

```python
cf_api(
    method="GET",           # GET, POST, PUT, DELETE, PATCH
    endpoint="/zones",      # API 엔드포인트
    body={...},             # 요청 본문 (선택)
    params={...}            # 쿼리 파라미터 (선택)
)
```

`{account_id}`는 자동으로 환경변수 값으로 치환됩니다.

---

## 1. 도메인(Zone) 관리

### 도메인 목록 조회
```python
cf_api(method="GET", endpoint="/zones")
```

### 특정 도메인 정보
```python
cf_api(method="GET", endpoint="/zones/{zone_id}")
```

---

## 2. DNS 레코드

### DNS 레코드 목록
```python
cf_api(method="GET", endpoint="/zones/{zone_id}/dns_records")
```

### DNS 레코드 추가
```python
cf_api(
    method="POST",
    endpoint="/zones/{zone_id}/dns_records",
    body={
        "type": "CNAME",
        "name": "home",
        "content": "tunnel-id.cfargotunnel.com",
        "proxied": True
    }
)
```

---

## 3. Tunnel (원격 접근)

### ⚠️ CLI 명령 필요
Tunnel 생성/실행은 **cloudflared CLI**를 bash로 직접 실행해야 합니다.

### 사전 준비 (최초 1회)
```bash
# cloudflared 설치
brew install cloudflared  # macOS

# Cloudflare 로그인 (브라우저 인증)
cloudflared tunnel login
```

### 터널 생성
```bash
cloudflared tunnel create {사용자가 원하는 터널 이름}
```

### 호스트명 결정 및 DNS 라우팅

호스트명은 AI 에이전트가 자동으로 결정합니다. **여러 PC에서 같은 Cloudflare 계정을 사용할 수 있으므로**, 기기를 구분할 수 있는 이름을 포함해야 합니다.

**호스트명 네이밍 규칙:**
1. 먼저 사용자에게 이 PC를 구분할 이름을 물어봅니다 (예: "home", "office", "macbook" 등)
2. 그 이름을 호스트명에 포함합니다: `finder-{기기이름}.{도메인}`, `launcher-{기기이름}.{도메인}`
3. 예시: `finder-home.mydomain.com`, `launcher-office.mydomain.com`

**DNS 라우팅 실행 시 에러 처리:**
- `cloudflared tunnel route dns` 명령이 실패하면 (호스트명 충돌 등), 사용자에게 알리고 다른 이름을 시도합니다
- 이미 같은 호스트명이 존재한다는 에러가 나오면, 자동으로 `-2`, `-3` 등의 접미사를 붙여 재시도합니다

```bash
# Finder용 (포트 8080으로 서비스)
cloudflared tunnel route dns {터널이름} finder-{기기이름}.{도메인}

# 런처용 (포트 8765로 서비스)
cloudflared tunnel route dns {터널이름} launcher-{기기이름}.{도메인}
```

### config.yml 생성
```yaml
# ~/.cloudflared/config.yml
tunnel: {tunnel-id}
credentials-file: ~/.cloudflared/{tunnel-id}.json

ingress:
  - hostname: finder-{기기이름}.{도메인}
    service: http://localhost:8080
  - hostname: launcher-{기기이름}.{도메인}
    service: http://localhost:8765
  - service: http_status:404
```

### ⚠️ 중요: IndieBiz OS 설정에 터널 정보 자동 저장

터널 생성과 DNS 라우팅 후 반드시 `data/tunnel_config.json`에 터널 정보를 저장해야 합니다.
이 작업은 **AI 에이전트가 자동으로 수행**해야 하며, 사용자에게 직접 입력하라고 안내하지 마세요.

저장해야 할 필드:
- `tunnel_name`: 생성한 터널 이름
- `finder_hostname`: 원격 Finder용 외부 호스트명 (DNS 라우팅에서 설정한 것)
- `launcher_hostname`: 원격 런처용 외부 호스트명 (DNS 라우팅에서 설정한 것)

```json
{
  "enabled": false,
  "auto_start": false,
  "tunnel_name": "{생성한 터널 이름}",
  "hostname": "",
  "finder_hostname": "{Finder용 호스트명, 예: finder.mydomain.com}",
  "launcher_hostname": "{런처용 호스트명, 예: launcher.mydomain.com}",
  "config_path": "~/.cloudflared/config.yml"
}
```

이렇게 하면 사용자가 **설정 → 터널 탭**을 열었을 때 터널 이름이 이미 채워져 있고,
토글만 켜면 바로 터널이 시작됩니다.
또한 **원격 Finder/런처 탭**에서 외부 접속 URL이 자동으로 표시됩니다.

### 터널 실행 (설정 UI 사용)

터널 설정이 완료되면 **IndieBiz OS 설정에서 토글로 터널을 제어**합니다.

**사용자에게 안내할 내용:**
> 터널 설정이 완료되었습니다. 이제 **설정 → 터널 탭**에서:
> 1. **터널 실행 토글을 ON**으로 켜주세요
> 2. 자동 시작을 원하면 **자동 시작 토글도 ON**

⚠️ **중요**: 터미널에서 `cloudflared tunnel run` 명령 대신 **설정의 터널 토글**을 사용하세요.

### API로 터널 목록 조회
```python
cf_api(method="GET", endpoint="/accounts/{account_id}/cfd_tunnel")
```

---

## 4. Pages (정적 사이트)

### Pages 프로젝트 목록
```python
cf_api(method="GET", endpoint="/accounts/{account_id}/pages/projects")
```

### Pages 배포 (CLI 권장)
```bash
# wrangler 설치
npm install -g wrangler

# 배포
wrangler pages deploy ./dist --project-name=my-site
```

---

## 5. Workers (서버리스)

### Workers 목록
```python
cf_api(method="GET", endpoint="/accounts/{account_id}/workers/scripts")
```

### Worker 배포 (CLI 권장)
```bash
wrangler deploy --name my-worker
```

### Worker 코드 조회
```python
cf_api(method="GET", endpoint="/accounts/{account_id}/workers/scripts/{script_name}")
```

---

## 6. R2 (오브젝트 스토리지)

### 버킷 목록
```python
cf_api(method="GET", endpoint="/accounts/{account_id}/r2/buckets")
```

### 버킷 생성
```python
cf_api(
    method="POST",
    endpoint="/accounts/{account_id}/r2/buckets",
    body={"name": "my-bucket"}
)
```

### 파일 업로드 (S3 API 사용)
R2는 S3 호환 API를 사용합니다. boto3 또는 AWS CLI로 접근하세요.

---

## 7. D1 (SQLite 데이터베이스)

### 데이터베이스 목록
```python
cf_api(method="GET", endpoint="/accounts/{account_id}/d1/database")
```

### 데이터베이스 생성
```python
cf_api(
    method="POST",
    endpoint="/accounts/{account_id}/d1/database",
    body={"name": "my-database"}
)
```

### SQL 쿼리 실행
```python
cf_api(
    method="POST",
    endpoint="/accounts/{account_id}/d1/database/{database_id}/query",
    body={"sql": "SELECT * FROM users LIMIT 10"}
)
```

---

## 8. 계정 정보

### API 토큰 확인
```python
cf_api(method="GET", endpoint="/user/tokens/verify")
```

### 계정 정보
```python
cf_api(method="GET", endpoint="/accounts/{account_id}")
```

---

## 원격 접근 설정 요약

### 터미널 작업 (최초 1회)
```bash
# 1. cloudflared 설치 및 로그인
brew install cloudflared && cloudflared tunnel login

# 2. 터널 생성 (이름은 사용자가 정함)
cloudflared tunnel create {터널이름}

# 3. DNS 라우팅 (기기 구분 이름 포함, 사용자에게 물어볼 것)
cloudflared tunnel route dns {터널이름} finder-{기기이름}.{도메인}
cloudflared tunnel route dns {터널이름} launcher-{기기이름}.{도메인}

# 4. config.yml 생성 (위 예시 참고)

# 5. data/tunnel_config.json에 터널 이름 + 호스트명 자동 저장 (AI 에이전트가 수행)
```

### 설정 UI 작업
터널 설정 완료 후 (터널 이름은 이미 자동 저장됨):
1. **설정 → 터널 탭** 이동
2. **터널 실행 토글 ON** → 터널 시작
3. **자동 시작 토글 ON** → IndieBiz OS 시작 시 자동 실행
4. **원격 Finder/런처 탭**에서 각각 활성화

외부 접속 URL:
- 원격 Finder: `https://{호스트명}/nas/app`
- 원격 런처: `https://{호스트명}/launcher/app`
