# Cloudflare 도구 패키지

Cloudflare 서비스 통합 도구 패키지입니다.

## 기능

- **Pages**: 정적 사이트 배포
- **Workers**: 서버리스 함수
- **R2**: 오브젝트 스토리지
- **D1**: SQLite 데이터베이스

## 환경변수 설정

`backend/.env` 파일에 다음을 추가하세요:

```env
CLOUDFLARE_API_TOKEN=your_api_token_here
CLOUDFLARE_ACCOUNT_ID=your_account_id_here
```

### API 토큰 발급 방법

1. [Cloudflare 대시보드](https://dash.cloudflare.com) 접속
2. My Profile → API Tokens → Create Token
3. "Edit Cloudflare Workers" 템플릿 선택 (또는 커스텀 권한 설정)
4. 생성된 토큰 복사

### Account ID 확인 방법

1. [Cloudflare 대시보드](https://dash.cloudflare.com) 접속
2. 우측 사이드바에서 Account ID 확인

## 도구 목록

| 도구 | 설명 |
|------|------|
| `cf_config` | 설정 상태 확인 (get, test) |
| `cf_pages_deploy` | Pages에 정적 사이트 배포 |
| `cf_pages_list` | Pages 프로젝트 목록 |
| `cf_worker_deploy` | Worker 생성/배포 |
| `cf_worker_list` | Workers 목록 |
| `cf_r2_upload` | R2 파일 업로드 |
| `cf_r2_list` | R2 버킷/파일 목록 |
| `cf_d1_query` | D1 SQL 쿼리 실행 |
| `cf_d1_list` | D1 데이터베이스 목록 |

## 사용 예시

```python
# 설정 확인
cf_config(action='get')

# API 연결 테스트
cf_config(action='test')

# Pages 배포
cf_pages_deploy(project_name='my-blog', directory='/path/to/dist')

# Worker 배포
cf_worker_deploy(
    worker_name='my-api',
    code='export default { async fetch(request) { return new Response("Hello"); } }'
)
```

## 의존성

- `wrangler` CLI: Pages, Workers, R2 배포에 필요
  ```bash
  npm install -g wrangler
  ```

## 버전

- 1.0.0 (2026-02-04)
