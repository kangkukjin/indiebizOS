# KOSPI 보드

기존 Cloudflare Worker 운영 소스다. `worker.js`는 ES 모듈이며 같은 파일이 HTML과
`/api/quotes`를 제공한다. `package.json`의 `type: module`을 유지한다.

```bash
# 저장소 루트에서
cd outputs/web-projects/kospi-board
npm ci
npm test
npm run build
```

Node와 Wrangler는 개발 의존성과 lockfile에 고정한다. npm 스크립트는 이 프로젝트의
Node 실행 파일을 사용하므로 맥의 전역 Node 20을 교체할 필요가 없다.
첫 설치를 전역 Node 20으로 하면 엔진 경고가 나올 수 있다. 설치 후 `npm test`와
`npm run build`가 성공하는지 확인한다. `node worker.js`나 전역 `wrangler`로 실행하지 않는다.
검증은 실제 배포 HTML의 스크립트를 실행해 손익·갱신·장애 표시와 원천 폴백을 확인한다.

배포 인증 환경변수(`CLOUDFLARE_API_TOKEN`, 필요 시 `CLOUDFLARE_ACCOUNT_ID`)가
준비된 환경에서 `npm run deploy`를 실행한다. 인증값은 소스·설정·lockfile에 쓰지 않는다.
`npm run build`는 업로드 없는 dry-run이다.

이 폴더의 소스·설정·lockfile·검증·문서만 `.gitignore` 예외로 추적한다.
`.wrangler/`, `node_modules/`, 비밀 파일과 다른 `outputs/` 산출물은 계속 제외한다.
