# Cloudflare 도구 패키지 v2.0

Cloudflare API 통합 도구입니다. Pages, Workers, R2, D1, Tunnel 등을 관리합니다.

## 도구

| 도구 | 설명 |
|------|------|
| `cf_api` | Cloudflare API 범용 호출 (토큰 안전 주입) |

## 사용법

첫 호출 시 **cloudflare_guide.md** 가이드가 자동으로 제공됩니다.

```python
# 도메인 목록 조회
cf_api(method="GET", endpoint="/zones")

# 터널 목록 조회
cf_api(method="GET", endpoint="/accounts/{account_id}/cfd_tunnel")

# DNS 레코드 추가
cf_api(
    method="POST",
    endpoint="/zones/{zone_id}/dns_records",
    body={"type": "CNAME", "name": "home", "content": "xxx.cfargotunnel.com", "proxied": True}
)
```

`{account_id}`는 환경변수에서 자동 치환됩니다.

## 환경변수 설정

`backend/.env` 파일에 추가:

```
CLOUDFLARE_API_TOKEN=your_api_token
CLOUDFLARE_ACCOUNT_ID=your_account_id
```

설정 후 IndieBiz OS를 재시작하세요.

## CLI 명령 (bash 직접 실행)

Tunnel 생성/실행, Pages/Workers 배포는 CLI를 bash로 직접 실행합니다.
가이드 파일에서 자세한 명령을 확인하세요.

```bash
# Tunnel
cloudflared tunnel create indiebiz
cloudflared tunnel run indiebiz

# Pages/Workers
wrangler pages deploy ./dist --project-name=my-site
wrangler deploy --name my-worker
```

## 파일 구조

```
cloudflare/
├── tool.json              # 도구 정의 (cf_api 1개)
├── handler.py             # 핸들러
├── cloudflare_guide.md    # 상세 가이드 (첫 호출 시 주입)
├── README.md
└── tools/
    └── api.py             # API 호출 구현
```

## 버전

- 2.0.0 (2026-02-05): 도구 11개 → 1개로 통합, 가이드 파일 시스템 적용
- 1.0.0 (2026-02-04): 초기 버전
