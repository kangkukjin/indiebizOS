# 게시판 (bulletin) — 로그인 없는 자유게시판

`[others:bulletin]` — 게시판을 만들면 공개 주소(`/b/<5자 코드>`)가 하나씩 생기고, 주소를 아는 사람은 **로그인 없이** 들어가 글·사진을 남긴다. 공개파일(`showcase`)·가족신문(`family_news`)·개인 포털(`portal`)의 네 번째 형제 — 같은 3층 구조(브라우저 → Cloudflare Worker → 터널 → 맥 백엔드)와 인덱싱 없는 라이브 서빙을 공유한다.

## op 분기

| op | 하는 일 |
|----|---------|
| `status` (기본) | 게시판 목록 — 각 게시판의 이름·주소·글 수 + 전역 설정 |
| `create` | `title` 로 새 게시판 + 주소 발급 (`allow_images` 사진 허용, 기본 true) |
| `config` | `board_id` 있으면 게시판 설정(`title` 개명·`allow_images`), 없으면 전역 `public_base` |
| `delete` | `board_id` 게시판 삭제 — 주소·글·사진 동반 제거 |
| `detail` | `board_id` → 게시판 + 최근 글 200개 (모더레이션용) |
| `post_delete` | `board_id` + `post_id` 글 하나 삭제 |
| `portals` | `board_id` → 이 게시판을 붙일 수 있는 포털 목록 + 현재 붙임 상태 (읽기) |

예: `[others:bulletin]{op: "create", title: "우리 동네 자유게시판"}`

## 저장·서빙 (이음매)

- 게시판 메타 = `data/bulletin/state.json`, 글 = 게시판별 `data/bulletin/<board_id>/posts.json` (즉석 append, flock). 인덱싱·manifest 없음 — 맥이 요청 시 서빙.
- 공개 서빙·익명 글쓰기 = `backend/api_bulletin.py` (`/bulletin/page·media·post`). `X-Showcase-Secret`(공개파일과 공유 시크릿) 게이트.
- 공개 Worker(`public-files/site/worker.js`)가 `/b/<slug>/…` 를 맥으로 프록시(동적, no-cache). 형제 `/s/`·`/n/`·`/h/` 와 같은 Worker·R2.

## 방어 (익명 공개 쓰기)

- 첨부 이미지는 PIL 재인코딩으로 **EXIF/GPS 전부 제거** + 최대 1600px 다운스케일 → JPEG. 매직바이트 검사.
- 같은 IP 연속 글쓰기 간격 제한(429). 이름/본문 글자수 상한. 숨은 허니팟 필드(봇 필터).
- 게시판당 글 최신 5000개 보관.

## 포털에 붙이기

특정 게시판을 특정 포털에 붙이면 포털 홈에서 그 게시판으로 들어간다(가족신문·공개파일과 같은 **색인** 방식 — 원본은 무변경).

- 붙임의 실체 = `portal_state.json` 의 그 포털 `display["board:<slug>"].enabled == true`.
- `portal_core.listable_universe()` 가 `board:<slug>` 콘텐츠 타일을 유도 → 포털 앱 **진열 탭**에서 바로 붙임 대상이 됨.
- 게시판 앱 **포털 연결** 탭에서도 관리 — 실제 붙임/떼기는 정식 `[others:portal]{op: "display", portal, key: "board:<slug>", enabled}` 로 실행.

## 커뮤니티 보드와 구별

`[others:board]`(커뮤니티) = Nostr 릴레이 기반 분산 채널. `[others:bulletin]` = 로그인 없는 **로컬 웹 게시판**(주소 아는 사람이 글쓰기). 이름·개념이 다르다.
