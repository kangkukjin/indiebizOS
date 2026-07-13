# 공개파일앱 (Public Files) 설계 문서

*작성 2026-07-12. Cloudflare를 "TV 화면/방송 표면"으로 삼는 투사 채널의 첫 입주자.*

## 1. 목표

특정 폴더들을 골라 **외부 공개 사이트**로 비추는 IBL 패키지. 개인용 NAS와 달리 "보여줄 것만 고른 창"이다.

- 맥의 사진·동영상·파일이 든 폴더를 선택 → Cloudflare 공개 URL에서 그리드로 열람·재생·다운로드.
- 맥이 자도 화면은 켜져 있음(썸네일·매니페스트가 엣지에 상주).
- 안 쓰면 설치 안 함 = 능력 자체가 부재(공개 인터넷으로 파일을 뚫는 위험한 능력은 의도적으로 소환될 때만 존재).

## 2. 헌법적 위치

### 2.1 이음매 (헌법 1조: substrate/superstructure)

```
┌─────────────── 맥 (superstructure, IBL 네이티브) ────────────────┐
│  공개파일앱 = [others:showcase] 액션 + app: 계기                    │
│   - 폴더 선택, 설정, 썸네일 생성(self:photo 위임), EXIF 제거,        │
│     동영상 H.264 변환, R2로 push                                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │  R2 매니페스트 계약 (§6) — 유일한 접점
                           ▼
┌─────────────── Cloudflare (substrate, 멍청함·독립·교체가능) ──────┐
│  R2 버킷(썸네일·원본·manifest.json) + Worker(그리드 서빙)          │
│   - IBL 도 IndieBiz 도 모름. manifest.json 을 읽어 그릴 뿐.        │
└──────────────────────────────────────────────────────────────────┘
```

**불변식**: 공개 사이트(Worker)는 `manifest.json` 계약만 안다. 앱을 지워도 사이트는 마지막 동기화 상태로 살아 있다. Cloudflare를 다른 벤더로 갈아치워도 계약만 지키면 앱 무변경.

### 2.2 사용자 층 (코어 아님)

- `core_manifest.json` 기준 **사용자 어휘·앱**이지 표준 코어가 아니다. R2 자격증명·Worker 주소는 이 패키지 안에만 산다 — 표준 코어는 벤더를 안 만짐(`avoid_vendor_layer`, `core_user_install_seam`).
- 패키지 폴더: `data/packages/installed/tools/public-files/` (설치=폴더 존재).

## 3. 어휘 (IBL)

### 3.1 명명 결정 — `publish` 는 임자가 있음

`[others:publish]` 는 이미 **Nostr 발행**(신문 njump)이다. 명명 헌법(한 단어=한 개념)상 "파일을 공개 웹 표면에 올림"은 **다른 개념어**가 필요하다.

- **채택: `showcase`** — "공개적으로 진열하다". 뜻이 명확하고 `publish`(이벤트 브로드캐스트)와 구별.
- 노드는 **`others`** — 바깥(공개 인터넷)을 향한 발행 능력이라 `others:publish` 옆이 제자리. (대안: `self:showcase` — 내 폴더 상태 관리 강조. 그러나 지배 동사가 "공개"라 outward=others 채택.)

### 3.2 액션 (op-bearing 단일 센터피스)

```
[others:showcase]{op: <동사>, ...}
```

| op | 파라미터 | 하는 일 |
|----|----------|---------|
| `add` | `path`(폴더 절대경로), `title`(선택, 표시명), `mode`(media/files 기본 media) | 폴더를 공개 목록에 추가 + 첫 동기화 트리거 |
| `remove` | `path` | 공개 목록에서 제거. `purge`(bool, 기본 false)면 R2 객체도 삭제 |
| `sync` | `path`(선택, 생략=전체) | 썸네일·매니페스트(설정에 따라 원본) R2 재push |
| `status` | — | 공개 폴더 목록·URL·용량·동기화 시각 반환 (items) |
| `config` | 설정 키들(§5) | 전역 설정 갱신 |

- `returns: items` (status), `effect`(add/remove/sync/config).
- `runs_on: mac_only` (썸네일 생성·ffmpeg·R2 push는 맥에서). 폰은 `phone_render:false`로 원격 리모컨만.
- `group: showcase`, `router: handler`, `tool: showcase_op`.
- op enum/default 는 `ops:` 블록이 단일 소스 → `--check` 가 tool.json·handler `_OP_DISPATCHERS` 와 AST 삼각 비교.

## 4. app: 블록 (앱 모드 계기)

`self:photo` 의 app 블록과 동형. 아이콘 하나로 데스크탑·원격 동시 등장.

```yaml
app:
  instrument: showcase
  icon: 🌐
  name: 공개파일
  order: 16
  phone_render: false          # mac_only 능력 → 원격 리모컨만
  modes:
    - name: 공개 폴더           # status → card_list (폴더별 상태·열기·해제)
      auto_run: true
      action: '[others:showcase]{op: "status"}'
      view:
        - type: card_list
          from: items
          title: '{title}'
          lines: ['{meta}']     # "미디어 · 128장 · 2.1GB · 어제 동기화"
          actions:              # 드릴/보조 동작
            - {label: 열기, action: open_url, arg: '{url}'}
            - {label: 재동기화, action: '[others:showcase]{op:"sync", path:"$path"}'}
            - {label: 공개 해제, action: '[others:showcase]{op:"remove", path:"$path"}', style: danger, confirm: true}
    - name: 폴더 추가           # form → add
      inputs:
        - {key: path, type: text, placeholder: 공개할 폴더 절대경로}
        - {key: title, type: text, placeholder: 표시명 (선택)}
        - {key: mode, type: select, options: [media, files]}
      action: '[others:showcase]{op:"add", path:"$path", title:"$title", mode:"$mode"}'
    - name: 설정               # form(toggle/select) → config, §5
      action: '[others:showcase]{op:"status"}'   # 현재 설정 로드
      view:
        - type: form
          submit: '[others:showcase]{op:"config"}'
          fields:
            - {key: access, type: select, options: [link_only, public], label: 접근}
            - {key: strip_exif, type: toggle, label: 위치·EXIF 제거}
            - {key: push_originals, type: toggle, label: 원본까지 업로드}
            - {key: transcode_video, type: toggle, label: 동영상 H.264 변환}
```

> `card_list.actions` / `form.submit` / `open_url` 이벤트가 렌더러에 이미 있는지 구현 1단계에서 확인(없으면 최소 추가). 폴더 선택은 데스크탑 네이티브 dialog가 이상적이나 1차는 텍스트 경로 입력으로 시작(사진앱 select 폴더 선례).

## 5. 설정 스키마 (`data/showcase_state.json`, auto_response 선례)

```json
{
  "access": "link_only",        // link_only | public
  "link_token": "<랜덤>",        // link_only 시 URL 에 포함
  "strip_exif": true,            // 위치·촬영정보 제거 후 업로드
  "push_originals": true,        // false면 썸네일만(원본은 맥 깨어있을 때 터널)
  "transcode_video": true,       // .mov/HEVC/MKV → H.264 MP4
  "on_uninstall": "freeze",      // freeze(마지막 상태 유지) | purge(R2 비움)
  "r2_bucket": "...", "public_base": "https://...",
  "folders": [
    {"path": "/Users/.../여행사진", "title": "여행", "mode": "media",
     "synced_at": "...", "count": 128, "bytes": 2260000000}
  ]
}
```

## 6. R2 매니페스트 계약 (이음매의 유일한 접점)

Worker 는 이 구조만 안다. 버킷 레이아웃:

```
manifest.json                     # 전체 색인 (아래)
thumbs/<folder_id>/<item_id>.jpg  # 썸네일 (항상 — sync 시 미리 push)
media/<folder_id>/<item_id>        # 원본/변환본 — ★온디맨드 캐시(본 것만 쌓임)
```

**★원본 = 온디맨드(option 1, P4 개정).** sync 는 썸네일·manifest 만 R2 에 올린다.
원본은 벌크 업로드하지 않는다 — 방문자가 사진을 클릭할 때 Worker 가 맥
(`ORIGIN_BASE=finder.kukjinkang.uk` 터널)의 `/showcase/origin/<fid>/<iid>` 에서 하나만
끌어와 스트리밍하며 동시에 R2 `media/` 에 캐시한다(`worker.js` `body.tee()`). 그래서
136GB 폴더도 R2 에 통째로 안 올라가고, 실제로 열람된 것만 캐시된다. 맥이 꺼져 있으면
캐시 안 된 원본은 503(썸네일 그리드는 계속 보임).

**비공개 색인**: `data/showcase_stage/_origin_index.json`(item_id→실제 파일경로)은 맥에만
있고 R2 에 절대 안 올라간다. origin 엔드포인트가 이걸로 raw 경로를 해소한다(방문자는
folder_id/item_id 만 안다). 시크릿(`SHOWCASE_ORIGIN_SECRET`==Worker `SHOWCASE_SECRET`)
게이트 + 공개/hidden 검증 + 경로이탈 방어 3중.

`manifest.json`:
```json
{
  "version": 1,
  "title": "...", "access": "link_only", "token_required": true,
  "folders": [{
    "id": "fld_ab12", "title": "여행", "mode": "media", "count": 128,
    "items": [{
      "id": "img_001", "title": "IMG_1234.jpg", "kind": "photo",
      "dir": "2012년/여행",                    // ★발행 루트 기준 하위 디렉토리(""=루트 직속)
      "thumb": "thumbs/fld_ab12/img_001.jpg",
      "src": "media/fld_ab12/img_001.jpg",   // 없으면 썸네일만 (원본 비공개)
      "w": 4032, "h": 3024, "size": 2600000
    }]
  }]
}
```

- **폴더 구조 보존**: 각 item 의 `dir`(발행 루트 기준 하위경로)로 공개 사이트가 원본 디렉토리 트리를 그대로 탐색(하위폴더 카드 + 브레드크럼, 다단계 중첩). manifest 는 여전히 폴더당 flat items 배열이고 트리는 사이트가 `dir` 로 클라이언트에서 구성(dir 없는 옛 manifest=""=루트 평면, 하위호환).
- 동영상: `kind:"video"`, `thumb`=포스터, `src`=`media/<fid>/<iid>`. Worker 가 온디맨드로 맥에서 끌어올 때 브라우저 비재생 컨테이너(.mov/HEVC 등)는 origin 이 H.264 MP4 로 트랜스코드해 반환 → R2 캐시 후 `<video>` + range 스트리밍.
- 원본 없는 아이템(`src` 부재)=썸네일만 공개. 큰 라이브러리 대비.
- ★EXIF/GPS 제거·동영상 트랜스코드는 **origin 서빙 시점**(맥 `api_showcase.py`)에 일어난다 — sync 시점이 아님(온디맨드라 미리 처리할 원본이 없음). 처음 클릭 때 처리→R2 캐시, 이후는 캐시 서빙.

## 7. 동기화 흐름 (`op:sync`)

★거대 폴더도 백엔드를 막지 않도록 **백그라운드 스레드**에서 실행(요청은 즉시 반환,
진행상황은 state 에 기록). 모든 state read-modify-write 는 `_STATE_LOCK` 로 직렬화
(진행상황 기록이 사용자 토글을 덮어쓰는 lost-update 방지).

1. 폴더 walk → 파일 열거 (media 모드=이미지·동영상; files 모드=전체).
2. 각 아이템:
   - 썸네일 생성 — **`backend/thumbnails.py` 단일소스 재사용**(`self:photo` 와 공유, 동영상=ffmpeg 포스터).
   - `thumbs/<fid>/<iid>.jpg` R2 PUT(`r2_client.py` 의존성0 SigV4).
   - 비공개 색인 `_origin_index.json[fid][iid] = 실경로` 기록(온디맨드 원본 해소용).
3. `manifest.json` 재작성 → R2 PUT. 상태 파일 `synced_at`/`count`/`bytes` 갱신.
4. **증분**: 썸네일이 원본보다 새로우면 재생성 스킵.
5. ★원본은 이 단계에서 안 올린다 — 방문자 클릭 시 origin 엔드포인트가 EXIF 제거/트랜스코드해 온디맨드 서빙(§6).

## 8. 공개 사이트 (Worker — 멍청한 substrate)

- 별도 소형 레포/디렉토리(`public-files/site/`), IBL 무관. 배포=wrangler.
- 라우트: `/` (폴더 목록) → `/f/<folder_id>` (그리드) → `/f/<id>/<item_id>` (라이트박스/재생).
- `link_only`면 `?t=<token>` 없으면 403. `access` 는 manifest 에서 읽음.
- 렌더=정적 HTML + 약간의 JS(그리드·라이트박스·`<video>`). R2 를 fetch 로 읽음.
- **가능하면 IndieBiz 원격 웹앱의 `image_grid`/`card_list` 렌더 로직과 시각적으로 통일** (같은 선언형 어휘의 공개판).

## 9. 접근 제어

- **기본 `link_only`**: 랜덤 토큰이 URL 에. 아는 사람만. 개인 사진 기본값으로 안전(`remote_surfaces_auth_audit` 연장).
- `public`: 토큰 없이 열림. 신문·포트폴리오 등 진짜 공개용일 때만 명시 선택.
- 토큰 회전(`op:config` 로 재발급) → 옛 링크 무효화.

## 10. self:photo 재사용 경계

- **재사용**: 썸네일·동영상 포스터 생성, 미디어 메타(kind/size/taken_at), `image_grid` 렌더 어휘.
- **분리**: `self:photo`=개인 사진 관리(인덱싱·검색). `others:showcase`=노출(무엇을 바깥에 보이나). showcase 가 photo 를 **호출**하되 삼키지 않음. files 모드(문서 등)는 photo 무관, `card_list` + 파일 아이콘.

## 11. 보안·프라이버시

- 폴더 선택 = **보안 경계**. 고른 폴더만 manifest 에 존재, 나머지 디스크는 사이트에 부재.
- EXIF/GPS 기본 제거.
- 읽기 전용 방송: 공개 사이트→맥으로 **명령 경로 없음**(초인종/리모컨은 별도 인증 표면, 이 앱 범위 밖). 공격 표면 최소.
- 자격증명은 패키지 로컬. 공개 repo 에 상태 커밋 금지(`repo_pii_scrub_runtime_state`).

## 12. 구현 단계

- **P0 — 어휘 골격**: `public-files/ibl_actions.yaml`(`others:showcase` + ops + app 블록) + handler `showcase_op` op 디스패처(스텁) + `build_ibl_nodes.py --check` 삼각 통과. 액션 +1.
- **P1 — 로컬 동기화(엣지 없이)**: `op:add/sync` 가 썸네일·manifest 를 **로컬 폴더**에 생성(self:photo 재사용 검증). `op:status` 반환. R2 미접속.
- **P2 — R2 push**: `cf_api`/S3 로 썸네일·manifest 업로드. 증분. 상태 영속.
- **P3 — 공개 Worker**: 정적 그리드 사이트 + link_only 토큰 + `<video>` 재생. 종단(맥 자도 켜짐).
- **P4 — 원본·동영상 변환(★온디맨드로 개정, option 1)**: 벌크 업로드 대신 방문자 클릭 시 origin 엔드포인트(`api_showcase.py`)가 EXIF/GPS 제거·`.mov`/HEVC→H.264 트랜스코드해 하나씩 서빙→R2 캐시. `strip_exif`/`transcode_video` 설정을 origin 이 존중. 라이브 종단 검증됨(터널+공개 Worker media 경로 둘 다).
- **P5 — 앱 계기 마감**: 데스크탑 폴더 dialog, 설정 form, card_list actions 검증. 원격 파리티.

각 단계: `--check` + `/packages/reload` + 라이브 `/ibl/execute` 스모크. 어휘 변경이므로 해마 시딩(add_examples_batch)·가이드 7표면·문서 갱신은 P0 확정 후.

## 13. 미결 결정 (사용자 몫)

1. **개념어 `showcase` 확정?** (대안: expose/share/gallery-public) — 명명 헌법상 사용자 결정.
2. **노드 `others` vs `self`?** (outward=others 권장).
3. **접근 기본 `link_only` 확정?** (개인 사진이면 권장).
4. **원본 정책 기본** — push_originals ON(맥 자도 원본 열림, 용량↑) vs OFF(썸네일만, 원본은 맥 깨어있을 때).
