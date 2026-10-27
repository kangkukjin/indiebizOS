# Cloudflare 사용 가이드

> 갱신 2026-10-26(시스템 현황 + Cloudflare 측 변화 조사). 어휘 = `[limbs:cloudflare_api]`(패키지 `tools/cloudflare`, 도구 `cf_api`) 하나. 사용량·무료 한도 대비 = 등록 스크립트 `Cloudflare사용량`. 공개 얼굴(터널·CDN)은 **백엔드 발급기**가 만든다 — AI 가 cloudflared 를 손으로 조립하는 길은 폴백이다. 아래 한도·버전 수치는 날짜가 붙은 세계의 데이터 — 바뀌면 여기만 고친다.

## 0. 호출 계약

```ibl
[limbs:cloudflare_api]{endpoint:"/zones", method:"GET"}
[limbs:cloudflare_api]{endpoint:"/zones/{zone_id}/dns_records", method:"POST", body:{type:"CNAME", name:"home", content:"<tunnel-id>.cfargotunnel.com", proxied:true}}
```

- `endpoint` = `https://api.cloudflare.com/client/v4` 이하 경로. `{account_id}` 만 .env 의 `CLOUDFLARE_ACCOUNT_ID` 로 자동 치환된다. `{zone_id}`·`{tunnel_id}` 류는 치환되지 않으므로 먼저 조회해 실제 id 를 넣는다. `method` 기본 GET, `body`(JSON)·`params`(쿼리) 선택. 타임아웃 30초.
- 반환(성공): `success:true` + `result`(Cloudflare 원봉투의 result) + **`items`**(list→행들, dict→1행 — `[table:each]`·변환자가 물린다) + `result_info`(페이지 정보).
- 반환(실패): `success:false` + `error`("코드: 메시지; …" — 봉투의 `errors[]` 를 합친 것). HTTP 200 이어도 `success` 로 판정한다(ep2833 수리).
- 쓰기(POST/PUT/PATCH/DELETE)도 같은 액션 — `side_effect` 이므로 확인 조회·goal 은 호출자가 붙인다.
- **토큰과 권한**: 토큰 하나(`CLOUDFLARE_API_TOKEN`, 설정 → API 키 탭 'Cloudflare · 공개 서빙'). 특정 endpoint 만 `401 10000 Authentication error` 면 토큰은 살아 있고 **그 제품 권한이 토큰에 없다**는 뜻 — 대시보드 → My Profile → API Tokens → 토큰 편집으로 권한을 더한다. 토큰 생사는 `/user/tokens/verify`(`result.status:"active"`).
  - 시스템이 쓰는 묶음: Zone Read · DNS Edit(발급기 DNS) · Cloudflare Tunnel Edit(`cfd_tunnel`) · Workers Scripts Edit + R2 Edit(CDN 발급기) · Account Analytics Read(사용량 GraphQL).
  - 선택: Browser Run Edit(크롤) · D1 Edit · Pages Edit. 2026-10-26 실측: 현 토큰은 Browser Run·D1 에 401 — 쓰려면 먼저 권한 추가.
- 2026-09-30 종료된 Service Key(`X-Auth-User-Service-Key`)·Global API Key 는 쓰지 않는다 — Bearer 토큰만.

## 1. 도메인(Zone)·DNS

- zone 찾기: `/zones` + `params:{name:"example.com"}` → `result[0].id`. 발급기도 이 호출로 토큰 권한을 겸사 검증한다.
- 레코드: `/zones/{zone_id}/dns_records` GET(`params:{name:"home.example.com"}`) / POST / PUT `/…/{record_id}` / DELETE. 터널 CNAME 본문은 위 예시.
- ★**2026-06-30 부터 기존 레코드의 type 변경은 PUT/PATCH 로 못 한다** — DELETE 후 POST(또는 `/dns_records/batch`). 발급기는 같은 이름 레코드를 PUT 으로 덮는데, 그 레코드가 A/AAAA 면 "DNS CNAME 설정 실패"로 끝난다 → 기존 레코드를 지우고 재발급.
- `dns_settings` 의 `foundation_dns` 불리언은 2026-11-23 종료 → `nameservers.type:"cloudflare.advanced"`(시스템 미사용).

## 2. Tunnel — 공개 얼굴은 발급기로, cloudflared 수동은 폴백

### 2.1 시스템의 정경로(새 몸·재발급)

설정 → **원격 접근 → 공개 얼굴(창고 신원)** → Cloudflare 발급. 뒤에서 `POST /tunnel/provision/cloudflare {domain, subdomain, dry_run, skip_cdn}` 이 아래를 한 번에 한다(모두 멱등, 단계별 `steps` 로그 반환, 실패해도 성공한 단계는 남아 재시도가 이어달리기):

1. zone 확인 → 2. 터널 `indiebiz-<sub>` 조회/생성 — **원격관리형**(`config_src:"cloudflare"`; cert.pem·`cloudflared tunnel login`·config.yml 불필요) → 3. 실행 토큰 `GET /cfd_tunnel/{id}/token` → 4. ingress 원격 선언 `PUT /cfd_tunnel/{id}/configurations`(hostname + `extra_hostnames` → `http://localhost:8765`, `originRequest.httpHostHeader`=hostname, 마지막 `http_status:404`) → 5. DNS CNAME → 6. `data/tunnel_config.json` 저장(provider·tunnel_id·tunnel_token·hostname·auto_start) + `cloudflared tunnel run --token` → 7. `SHOWCASE_ORIGIN_SECRET` 보장 → 8. CDN(Worker+R2) 발급(`cdn_provision`, 실패해도 발급 성공 — 직접 서빙 폴백) → 9. public_face 배선·표면 4곳 전파.

- `dry_run:true` 로 계획만 본다. CDN 만 다시 = `POST /tunnel/provision/cdn`(조종실 '캐시 켜기'). 상태 `GET /tunnel/provision/status`, zone 목록 `GET /tunnel/provision/zones`, 공개면 자가검증 `POST /tunnel/provision/verify`.
- **AI 가 `tunnel_config.json` 을 손으로 쓰지 않는다** — 발급기가 쓴다. 실행/자동 시작 토글은 설정 UI(`/tunnel/config`·`/tunnel/start`·`/tunnel/stop`). `finder_hostname`·`launcher_hostname` 은 옛 수제 터널 몸의 유산 필드 — 새 몸의 런처·파인더 주소는 공개 얼굴에서 `origin_host()` 로 파생된다(remote_access.md).
- Tailscale Funnel 은 같은 「공개 HTTPS → localhost:8765」 계약의 다른 구현(도메인 불필요). 권위 = `public_face.provider`.

### 2.2 API 로 보기

- 터널 목록 `/accounts/{account_id}/cfd_tunnel` + `params:{is_deleted:"false"}` → `name`·`status`(healthy/down/inactive)·`config_src`(cloudflare=원격관리, local=옛 config.yml 터널). 이름으로 좁히기 `params:{name:"indiebiz-xxx"}`.
- ★2026-10-05 부터 목록 응답의 **`connections` 필드 제거** → 연결 상세는 `GET /cfd_tunnel/{id}/connections`. CIDR 인코딩 route 엔드포인트도 제거(`/teamnet/routes/{route_id}` 로).
- 원격 ingress 읽기 `GET /cfd_tunnel/{id}/configurations`. 선언 본문의 단일 소스는 `face_provision._ingress_config`(부팅 재선언과 공유) — API 로 손 고치면 다음 부팅이 되돌린다.

### 2.3 cloudflared 수동(폴백·옛 몸 보수)

- 설치: macOS `brew install cloudflared` / Windows `winget install Cloudflare.cloudflared`. 백엔드 `get_cloudflared_path` 가 PATH 와 OS 표준 경로를 찾는다. 2026-10 최신 2026.10.x. 2026.5.2+ 는 `tunnel run` 시작 때 연결성 사전검사를 한다. 2027 에 32비트 Windows·Intel Mac 빌드 폐기 예고.
- 옛 로컬관리 터널(`config_src:"local"`, `~/.cloudflared/config.yml` + `cloudflared tunnel login/create/route dns`)은 그대로 돈다 — **새 몸에는 만들지 않는다**. 보수 규칙: ingress 마지막은 반드시 `service: http_status:404`; `cloudflared tunnel run` 을 터미널에서 띄우지 말고 설정 토글로(`api_tunnel.start_tunnel` 이 `tunnel run --token`/`tunnel run <name>` 표식으로 **자기 터널만** 식별·정지한다 — 같은 기계의 다른 cloudflared 는 건드리지 않는다).
- 대시보드: 2026-02 부터 메인 대시보드 Networking → Tunnels 에서 관리, 08-10 라이브 로그, 08-18 origin 설정(TLS·연결 옵션). 2026-03 `wrangler tunnel` 실험 명령(원격관리 터널 생성)은 발급기가 같은 일을 하므로 시스템에선 안 쓴다.
- 경로 정규화: cloudflared 2026.10.0 부터 옵션(`--disable-path-normalization=false`), **2027-01-25 기본 ON** — 시스템 ingress 는 hostname 기준이라 영향 적음, 점검만.

### 에러 처리

| 증상 | 원인 | 대응 |
|------|------|------|
| 특정 endpoint 만 `401 10000` | 토큰에 그 제품 권한 없음 | 토큰 편집해 권한 추가(0절) |
| zone 을 찾지 못함 | 도메인이 이 계정에 없음 / Zone Read 없음 | `/zones` 로 확인 |
| 터널 생성 실패 / already exists | 이름 충돌 | 발급기는 같은 이름 재사용(멱등). 수동이면 `cfd_tunnel?name=` 조회 |
| DNS CNAME 설정 실패 | 같은 이름의 A/AAAA 존재(type 변경 금지) 또는 DNS Edit 없음 | 기존 레코드 DELETE 후 재발급 |
| cloudflared 실행 실패 | 미설치 | 설치 힌트 따라 설치 — 설정은 저장돼 재시작 때 자동 재시도 |
| 공개면 catch-all 404 | 실행 중 프로세스의 ingress 가 옛 것 | 부팅 `verify_public_face` 가 재기동. 수동 = `POST /tunnel/provision/verify` |
| 502 via cloudflared | 오리진(8765) 응답 지연·다운 | `data/restart_control/state.json` 의 phase 먼저 |

## 3. Workers · 정적 사이트 — Pages 대신 Workers Static Assets

- **새 프로젝트는 Workers**. Pages 문서 첫머리에 "Start new projects with Workers" 배너(2026-10 확인), 종료일은 발표 없음. 기존 Pages 프로젝트는 유지하되 새로 만들지 않는다. Workers Sites 는 폐기(→ Static Assets).
- 정적자산 Worker: `wrangler.toml`/`wrangler.jsonc` 에 `main` 없이 `[assets] directory="./public"`, SPA 면 `not_found_handling="single-page-application"`, Worker 코드가 먼저 받아야 하면 `run_worker_first`. **자산 요청은 무료·무제한**(Worker 호출 없음). 선례 = diary(정적자산)·kospi-board(`main` Worker). ★`/index.html` 은 `/` 로 307 — 서비스워커 precache 함정(webapp.md 실측).
- Pages → Workers 이주: `pages_build_output_dir` → `assets.directory`, `wrangler pages deploy` → `wrangler deploy`, `functions/` 있으면 `wrangler pages functions build` 로 `_worker.js` 만들어 `main` 지정(`.assetsignore` 에 `_worker.js`). 미리보기 URL 은 `preview_urls=true` + Workers Builds 설정. Cloudflare 밖 네임서버의 커스텀 도메인은 Workers 에서 불가. 검증 = `wrangler deploy --dry-run`.
- 배포 도구 = **Wrangler v4**(2026-10 최신 4.152, `engines.node >=22`). 프로젝트에 고정된 Node·Wrangler(`package.json` devDependencies)를 쓰고 전역 최신과 섞지 않는다. 순서 `npm ci` → `npm test` → `npm run build`(=dry-run) → `npm run deploy`. 인증은 .env 의 `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID` 환경변수(wrangler·cf 둘 다 읽음). ES 모듈 Worker 를 Node 로 검사하려면 `type:"module"` 또는 `.mjs`.
- **`cf` CLI(2026-09-28 오픈 베타)** = Wrangler 후속. Cloudflare API 전부(2,900+ 명령, OpenAPI 생성)를 덮고 설정은 `cloudflare.config.ts`, 빌드는 Vite. 베타 종료 시 Wrangler 마지막 메이저 → 18개월 유지보수. **지금은 이주하지 않는다**: 미이주 Wrangler 프로젝트에서 `cf dev/build/deploy` 를 실행하면 설정 파일을 생성·오염한다(미리보기는 `cf migrate --dry-run` 만). 자원 조회(`cf d1 list`·`cf r2 buckets list`)는 공존 가능하지만 시스템에선 `[limbs:cloudflare_api]` 가 같은 일. 아직 못 하는 것: 라이브 로그(`wrangler tail`)·단일 secret.
- 시스템의 CDN Worker(`public-files-<슬러그>`)는 wrangler 없이 REST 로 올린다(`PUT /workers/scripts/{name}` 멀티파트, 바인딩 BUCKET·ORIGIN_BASE·SHOWCASE_SECRET 은 메타데이터 — `cdn_provision.py`). **손으로 `wrangler deploy` 하지 말 것** — 이름·바인딩이 발급기 소유, 재배포 = `/tunnel/provision/cdn`.
- 한도(Free, 2026-10 공식): 요청 10만/일(00:00 UTC 리셋, 초과 = 오류 1027) · CPU 10ms/호출(초과 = 1102; fetch·KV·DB 대기는 미포함). Paid $5/월 = 1천만 요청 + 3천만 CPU-ms 포함. Durable Objects Free = SQLite 백엔드만, 10만 요청/일·5GB.
- REST: 목록 `/accounts/{account_id}/workers/scripts` · 코드 `/…/scripts/{name}` · workers.dev 서브도메인 `/workers/subdomain`. ★Workers KV 옛 경로 `/workers/namespaces/*` 는 2026-10-15 종료 → `/storage/kv/namespaces/*`(시스템 미사용).
- 그 밖의 2026 신제품(시스템 미사용, 이름만): Sandboxes GA·Containers 재구축·Dynamic Workers(에이전트 코드 실행), Agents SDK/Project Think, Workers Builds. 필요가 생기면 **그때** 가이드에 절을 연다 — 미리 어휘를 만들지 않는다.

## 4. R2

- 버킷 관리 = REST: `/accounts/{account_id}/r2/buckets` GET(result 가 `{buckets:[…]}` dict → items 1행; 버킷을 행들로 돌리려면 `items[0].buckets`) / POST `{name}` / DELETE `/…/{name}`.
- **오브젝트 읽기·쓰기는 REST 가 아니라 S3 호환 API 전용** — `backend/base/r2_client.py`(SigV4, `R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`, 엔드포인트 `https://<acct>.r2.cloudflarestorage.com`, region `auto`). `[limbs:cloudflare_api]` 로는 못 한다. 발급기의 index.html 업로드도 이 길.
- 무료(Standard 만, 2026-10 공식): 10GB-월 · Class A 100만 · Class B 1천만 / 월 · **이그레스 무료**(Workers API·S3 API·r2.dev). 유료 Standard $0.015/GB-월, A $4.50/백만, B $0.36/백만. Infrequent Access 는 무료 할당 없음·최소 30일 과금·조회 $0.01/GB. Delete 류·401 거절은 과금 없음.
- 사용량·한도 대비는 `[self:script]{op:"run", id:"Cloudflare사용량"}`(GraphQL; `days`·`sections` 인자) — **무료 한도 상수의 정본은 그 스크립트**(여기 수치와 어긋나면 스크립트를 믿고 둘을 맞춘다).
- 새 식구(시스템 미사용): R2 SQL(2026-05 종량 $2.50/TB 스캔)·Basin(Iceberg 카탈로그, 2026-09 GA).

## 5. D1

- `/accounts/{account_id}/d1/database` GET / POST `{name}` · 쿼리 `POST /…/{database_id}/query {sql, params}`.
- 한도(2026-10 공식): Free 10 DB·500MB/DB·계정 5GB·Time Travel 7일·호출당 50 쿼리 / Paid 5만 DB·10GB/DB·1TB·30일·1,000 쿼리. Free 는 일일 행 읽기/쓰기 초과 시 오류(00:00 UTC 리셋). 읽기 복제(`read_replication:"auto"`, Sessions API) 추가 비용 없음.
- 시스템은 D1 미사용(상태는 로컬 파일·SQLite). 토큰에 D1 권한 없음(2026-10-26 실측 401) — 쓰려면 권한부터.

## 6. Browser Run(옛 Browser Rendering) — 크롤·스크린샷

- **2026-04-15 이름 변경**: REST 경로 `/accounts/{account_id}/browser-run/…`, 토큰 권한 **Browser Run - Edit**. 옛 `/browser-rendering/…` 경로의 수용 여부는 미확인(2026-10-26 둘 다 401 = 권한 부재) — 새 경로를 쓴다.
- 크롤 시작 `POST /browser-run/crawl` 본문 `{url, limit(기본 10), depth, formats:["html"|"markdown"|"json"], render(기본 true), source:"all"|"sitemaps"|"links", maxAge(기본 86400), options:{includePatterns, excludePatterns, includeSubdomains, includeExternalLinks}, crawlPurposes:["search"|"ai-input"|"ai-train"]}` → `result` = job id 문자열. 조회 `GET /browser-run/crawl/{job_id}`(`?limit=1` 로 상태만), 취소 DELETE. 상태 running/completed/errored/cancelled_*.
- 한도(2026-10 공식): Free 브라우저 10분/일 · 동시 3 · 새 인스턴스 1/20초 · 크롤 5 잡/일 · 100 페이지/크롤 · Quick Actions 1 요청/10초. Paid 종량(동시 200, 3/초, 30 요청/초, 2026-04 레이트리밋 3→10 rps). 잡 최대 7일, 결과 14일 보관, robots.txt 준수. `render:false` 는 브라우저 시간 0.
- 시스템에선 로컬 Playwright(`[limbs:browser]`, browser_action.md)가 1차. Browser Run 은 맥이 꺼져 있어도 돌아야 하거나 대량 크롤일 때.

## 7. 계정

- `/user/tokens/verify` → `result.status`. `/accounts/{account_id}` 계정 정보. `POST /accounts` 이름 65자 제한(2026-09-27). Account Roles API → Permission Groups API(`/iam/permission_groups`, 종료일 미정).

## 8. 폐기 달력(시스템에 닿는 것만)

| 날짜 | 변경 | 시스템 영향 |
|------|------|-------------|
| 2026-06-30 | DNS 레코드 type 변경 PUT 금지 | 발급기 DNS 덮어쓰기 — A→CNAME 이면 DELETE 후 재발급 |
| 2026-09-30 | Service Key 인증 종료 | 없음(Bearer 토큰만) |
| 2026-10-05 | cfd_tunnel 목록 `connections` 제거 | 연결은 `/connections` 서브경로 |
| 2026-10-15 | KV 옛 경로 종료 | 미사용 |
| 2026-11-23 | `foundation_dns` 불리언 종료 | 미사용 |
| 2026-12-01 | DNS Analytics REST → GraphQL | 미사용(사용량 스크립트는 이미 GraphQL) |
| 2027-01-25 | cloudflared 경로 정규화 기본 ON | hostname 기준 ingress — 점검만 |
| 2027-03-31 | Zone Settings Batch API 종료 | 미사용 |

## 실측 기록(자동 누적)

> 실행 에이전트가 턴 종료 후 덧붙인다.
- 2026-09-05 ep2833: 병렬 분기 실패가 error "" 로 신고 → errors[] 합산. result→items 통화. 사용량 임시 파이썬을 `Cloudflare사용량` 스크립트로 얼림.
- 2026-10-26 조사 갱신: 토큰 verify active. `cfd_tunnel` 에 원격관리(cloudflare) 터널들과 옛 로컬관리(local) 터널이 공존 — 새 몸은 발급기 경로만. Pages 프로젝트는 남아 있으나 신규는 Workers. Browser Run·D1 은 토큰 권한 부재로 401.
