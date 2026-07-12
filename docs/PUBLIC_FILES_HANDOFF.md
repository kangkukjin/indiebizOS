# 공개파일(Public Files) 핸드오프 — 2026-07-13

선택한 폴더를 Cloudflare 공개 사이트로 비추는 "열린 NAS". Cloudflare를 맥/폰에 이은
**세 번째 몸(TV 화면)**으로, IBL 어휘 `[others:showcase]` 위에 얹었다.
설계 원문: `docs/PUBLIC_FILES_APP_DESIGN.md` (단, P4 "원본 벌크업로드"는 **온디맨드(option 1)로 대체됨** — 아래 참조).

---

## 🟢 지금 라이브 (동작 확인됨)

- **공개 URL**: https://public-files.kangkukjin.workers.dev (완전 공개, 토큰 게이트 없음)
- **작동**: 앱 모드 🌐 공개파일에서 폴더 선택(GUI) → 공개 → 썸네일 그리드 → 사진 클릭 시
  **온디맨드로 맥에서 원본을 끌어와 표시 + R2 캐시**(본 것만 업로드). 브라우저 종단 검증 완료.
- **어휘**: `[others:showcase]{op: status(기본)/add/remove/sync/config/detail}` — 노드 others, 액션 152.
- **앱 3모드**: 공개 폴더(주소 배너 + 폴더카드[열기 링크·클릭 시 표시명·**공개/비공개 toggle**·동기화·제거] + 전체 동기화) / 폴더 추가(GUI 폴더 피커) / 설정(전역 접근·EXIF·원본·동영상).

## 🔑 인프라·시크릿 (이미 설정됨)

| 항목 | 값 |
|------|-----|
| R2 버킷 | `public-files` (계정 a82e4254f22e89f3e52948418cc7b459) |
| R2 S3 키 | `.env`: `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` |
| 맥 노출 터널 | 기존 `indiebiz-os` cloudflared: **`finder.kukjinkang.uk` → localhost:8765** (재사용) |
| 온디맨드 시크릿 | `.env`: `SHOWCASE_ORIGIN_SECRET` == Worker secret `SHOWCASE_SECRET` (동일값) |
| Worker env | `ORIGIN_BASE=https://finder.kukjinkang.uk`, `BUCKET`(R2), `SHOWCASE_SECRET`, (`SHOWCASE_TOKEN` 선택) |
| Worker 배포 | `cd data/packages/installed/tools/public-files/site && CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… npx wrangler@4 deploy` |

## 📁 핵심 파일

```
data/packages/installed/tools/public-files/
  ├── ibl_actions.yaml     # [others:showcase] 어휘 + ops + app 블록 + tool_json
  ├── handler.py           # op 디스패치, 백그라운드 동기화, 비공개 색인, R2 업로드 트리거
  ├── guide.md
  └── site/
      ├── index.html       # 공개 갤러리 SPA(manifest.json만 읽음) — R2에 업로드됨
      ├── worker.js         # Worker: manifest/thumbs=R2직접, media/*=온디맨드, 그외=index.html
      └── wrangler.toml     # ORIGIN_BASE var + R2 바인딩
backend/
  ├── api_showcase.py      # GET /showcase/origin/{fid}/{iid} — 온디맨드 원본(시크릿 게이트)
  ├── r2_client.py         # 의존성0 SigV4 S3 업로더 (put/get/delete_object) — AWS벡터 self-test PASS
  ├── thumbnails.py        # 썸네일 생성 단일소스 (api_photo도 위임)
  ├── api.py               # showcase_router 등록 (include_router)
  └── api_launcher_web.py  # is_public_remote_path 에 /showcase/origin/* 등록
frontend/
  ├── src/components/GenericInstrument.tsx  # FolderField(폴더 피커), form 필드 'folder' 타입
  └── electron/main.js     # select-folder IPC (dialog 제목 중립화)
data/
  ├── showcase_state.json  # 폴더 목록 + 설정 (runtime state)
  └── showcase_stage/      # R2 레이아웃 미러: manifest.json, thumbs/<fid>/, _origin_index.json(★비공개, R2 미업로드)
```

## 🏗️ 아키텍처 요약 (이음매 = 헌법 1조)

```
맥 (superstructure, IBL)                        Cloudflare (substrate, 멍청함)
─────────────────────────                      ──────────────────────────────
[others:showcase] handler                       R2 버킷 public-files
 ├ add/sync → 백그라운드 스레드                    ├ manifest.json (공개 색인)
 │   썸네일(thumbnails.py) → 스테이징              ├ thumbs/<fid>/<iid>.jpg
 │   → r2_client(SigV4) 업로드                    └ media/<fid>/<iid> (온디맨드 캐시)
 │   → _origin_index.json(item_id→실경로, 비공개)  
 └ api_showcase /showcase/origin                 Worker (worker.js)
     (시크릿+published+경로검증)                    media/* 요청:
        ▲                                           R2 캐시 있으면 → 서빙
        │ finder.kukjinkang.uk (터널)               없으면 → 맥 /showcase/origin 끌어옴
        └───────── Worker가 시크릿으로 pull ──────────  (tee 스트림) + R2 캐시
```

**핵심 불변식**: Worker는 `manifest.json` 계약만 안다. `_origin_index.json`(실경로)은 맥에만. 원본은 folder_id/item_id로만 요청(raw 경로 안 받음).

---

## 🔧 남은 일 (다음 세션)

### 1. 원본 EXIF/GPS 제거 (프라이버시 — 우선순위 높음)
현재 `api_showcase.py`의 origin 엔드포인트가 **원본을 EXIF 그대로 서빙**(촬영 위치·기기 노출). `settings.strip_exif`(기본 True) 존중해서 GPS만이라도 제거.
- **주의**: PIL 재저장은 orientation 태그를 잃어 사진이 회전될 수 있음. `piexif.remove()`(GPS IFD만 제거, 픽셀·품질 보존)가 이상적 — piexif 설치 여부 확인(없으면 공급망 게이트 `[self:install_lib]`). 또는 orientation을 픽셀로 적용 후 EXIF strip.
- 위치: `backend/api_showcase.py` origin() — FileResponse 대신 처리된 바이트 반환.

### 2. 동영상 재생 (HEVC/.mov)
아이폰 .mov(HEVC)는 브라우저 재생 불가. origin 엔드포인트가 kind=video면 ffmpeg로 H.264 MP4 트랜스코드해 반환(느림 → 첫 클릭만, R2 캐시되면 이후 빠름). 또는 sync 시 미리 web 버전 생성.
- `thumbnails.py`에 이미 ffmpeg 포스터 로직 있음 — 트랜스코드 함수 추가.
- 사진은 지금 완벽, 동영상만 미완.

### 3. state 동시성 (read-modify-write 경합)
백그라운드 sync 스레드(`_update_folder` 진행상황)와 요청 핸들러(config/remove)가 같은 `showcase_state.json`을 load-modify-save. `_save_state`는 원자적(temp+rename)이라 **손상은 없지만 lost-update 가능**(한쪽이 다른쪽 변경 덮어씀). 개선: load-modify-save 전체를 락으로 직렬화, 또는 단일 writer 큐.
- ★테스트 시 fresh-process(python3 -c)를 **라이브 백엔드와 동시에** 돌리지 말 것(이번 세션 혼란 원인).

### 4. 커밋 (전체 미커밋)
이 기능 전체가 git 미커밋. 브랜치 파서 커밋. `.env` 시크릿·`showcase_state.json`·`showcase_stage/`는 커밋 금지(gitignore 확인). `repo_pii_scrub_runtime_state` 원칙.

### 5. 어휘 변경 후속 (deferred)
`detail` op·`folder` 폼필드·showcase 액션 → 해마 시딩(`add_examples_batch`, rebuild_usage_db 덮어쓰기 주의)·가이드 7표면(`feedback_vocab_change_docs`). 이번 세션은 코드·문서 2곳(ibl.md·new_action_checklist.md)만 동기화함.

### 6. 설계 문서 갱신
`docs/PUBLIC_FILES_APP_DESIGN.md`의 P4 "원본 벌크업로드"를 **온디맨드(option 1)**로 개정. §6 매니페스트에 src·비공개 색인·origin 엔드포인트 반영.

### 7. 사진자료모음(사용자 폴더) 처리
35,251장·136GB. 현재 "⚠️ 동기화 중단됨"(재시작으로 스레드 죽음). 사용자가 앱에서 '동기화' 누르면 백그라운드 재개(썸네일 3.5만장 생성=수십분, 원본은 온디맨드라 136GB 안 올라감). R2에 부분 업로드된 ~11k 고아 썸네일은 재sync/remove 시 정리. 안 쓸 거면 remove.

---

## ⚠️ 함정 (반드시 기억)

1. **백엔드 재시작 필요**: `r2_client.py`·`api_showcase.py`·`api.py`·`thumbnails.py` 등 backend 모듈 변경은 uvicorn `--reload` 없음 → **수동 재시작**. 패키지 handler.py는 `/packages/reload`로 즉시.
2. **프론트 창 리로드**: `GenericInstrument.tsx` 등 React 변경은 Vite HMR이 번들엔 반영하나 **열린 Electron 창은 Cmd+R** 해야 보임. (이번 세션 "찾아보기 안 뜸"의 원인)
3. **앱 폼은 auto_run 필수**: 모드 액션이 데이터를 로드해야 form이 렌더됨. auto_run 없으면 폼 안 뜸(이번 "폴더 추가가 안돼"의 진짜 원인 중 하나).
4. **거대 폴더 = 백그라운드**: 동기화는 반드시 백그라운드 스레드(수만 장을 한 요청서 동기 처리하면 백엔드 통째 먹통 — 이미 해결됨, 되돌리지 말 것).
5. **SigV4 한글 키**: folder_id에 한글 가능(`fld_여행앨범`). SigV4 canonical_uri 이중 인코딩 버그 이미 수정(`r2_client.py` — 재quote 금지). 되돌리지 말 것.
6. **`fld_root` 이상**: `사진자료모음` 폴더 id가 `fld_root`로 나옴(정상은 `fld_사진자료모음`). `_folder_id`가 그 경로에서 왜 root를 내는지 미확인(경로 끝 슬래시? 조사 필요).

## ✅ 검증 명령 (스모크)

```bash
# 백엔드 살아있나
curl -s http://localhost:8765/ping -w " %{http_code}\n"
# showcase status (즉시여야)
curl -s http://localhost:8765/ibl/execute -X POST -H "Content-Type: application/json" \
  -d '{"code":"[others:showcase]{op:\"status\", project_id:\"컨텐츠\"}"}'
# 원본 엔드포인트 (SECRET=.env SHOWCASE_ORIGIN_SECRET)
curl -s "https://finder.kukjinkang.uk/showcase/origin/<fid>/<iid>" -H "X-Showcase-Secret: $SECRET" -o /dev/null -w "%{http_code}\n"  # 200
# SigV4 self-test
python3 backend/r2_client.py   # SigV4 self-test: PASS
# 빌드 삼각검증
python3 scripts/build_ibl_nodes.py --check
```

메모리: `project_public_files_app.md` (전체 이력), MEMORY.md START HERE.
