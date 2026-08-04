# 공개파일 (Public Files)

선택한 폴더를 외부 공개 사이트(Cloudflare)로 **라이브 서빙**하는 노출 층. 개인용 NAS 와
달리 **보여줄 것만 고른 창**이다. **인덱싱이 없다** — 맥이 요청 시 그 디렉토리를 즉석에서
훑고 썸네일을 그 자리에서 생성하므로, 파일을 옮기거나 지우면 다음 조회에 즉시 반영된다.

## 어휘

```
[others:showcase]{op: "status"}                              # 추가한 폴더 + 각 폴더가 담긴 주소
[others:showcase]{op: "add", path: "/Users/.../여행", mode: "media"}   # 폴더 추가(공개는 바스켓에서)
[others:showcase]{op: "remove", path: "/Users/.../여행"}     # 폴더 제거(모든 주소에서)
[others:showcase]{op: "config", strip_exif: true, transcode_video: true}   # 전역 설정
```

- `mode`: `media`(사진·동영상·음악 그리드 — 브라우저가 바로 열고 재생하는 것) / `files`(파일 전체).
- 폴더 추가만으론 **비공개** — '바스켓'(주소)에 담아야 공개. 담는 즉시 라이브.
- EXIF/GPS 는 원본 서빙 시 기본 제거. 동영상은 브라우저 비재생 컨테이너면 H.264 변환.

## 바스켓 = 공개 주소 (bare 루트는 잠금)

**모든 갤러리는 바스켓 하나 = 주소 하나**(`<base>/s/<slug>`). `slug` 는 5자 대문자
코드(A-Z). **bare 루트(`<base>/`)는 항상 잠겨** 콘텐츠가 전혀 없다 — 어떤 주소의 코드를
지워도(=bare 루트) 아무것도 안 보인다. 널리 공유하면 공개 갤러리, 아는 사람만 주면 비밀.

```
[others:showcase]{op: "basket_list"}                                  # 주소 목록
[others:showcase]{op: "basket_save", title: "가족에게"}                # 생성(5자 코드 발급)
[others:showcase]{op: "basket_save", title: "전체 공개", all_folders: true}  # 전체 폴더 자동 포함
[others:showcase]{op: "basket_save", basket_id: "bsk_…", title: "새 이름"}   # 개명
[others:showcase]{op: "basket_detail", basket_id: "bsk_…"}            # 담긴 폴더 + 담기/빼기
[others:showcase]{op: "basket_toggle", basket_id: "bsk_…", folder_id: "fld_…"}  # 담기/빼기
[others:showcase]{op: "basket_delete", basket_id: "bsk_…"}            # 주소 삭제(폴더 보존)
```

- **전체 공개 갤러리** = `all_folders: true` 바스켓. 모든 폴더 자동 포함, 폴더 추가 시 자동
  반영. 이것도 자기 slug 주소를 가져 bare 루트엔 안 뜬다.
- 폴더가 어느 주소에 담기느냐가 곧 보안 경계. 담기/빼기는 즉시 반영(동기화 없음).

## 아키텍처 (라이브 서빙)

```
맥 (superstructure, api_showcase.py)          Cloudflare (substrate = 멍청한 프록시 + 캐시)
────────────────────────────────             ──────────────────────────────────────────
[others:showcase] handler                     Worker (worker.js)
  상태(폴더·바스켓)만 관리                        /s/<slug>/list?path=  → 맥에 프록시(캐시 안 함=항상 최신)
  showcase_state.json                          /s/<slug>/thumb/<fid>?rel=&v= → R2 캐시 or 맥 생성
                                               /s/<slug>/media/<fid>?rel=&v= → R2 캐시 or 맥 원본(Range)
  /showcase/list   디렉토리 즉석 walk            그 외 → index.html(SPA)
  /showcase/thumb  썸네일 즉석 생성              bare / → 잠금 안내
  /showcase/media  원본(EXIF strip·트랜스코드)
     ▲ 이 몸의 공개 호스트(터널, wrangler.toml 의 ORIGIN_BASE) + X-Showcase-Secret
```

★ORIGIN_BASE·Worker 이름은 **몸마다 다르다**(wrangler.toml 은 git 밖, 템플릿만 추적).
다른 몸의 값을 복사해 쓰면 배포가 그 몸의 Worker 를 덮어쓰고 원본도 남의 몸을 가리킨다.
이 몸의 공개 호스트는 설정→터널 탭의 "이 컴퓨터의 창고 주소"에서 확인한다.

**핵심 불변식**:
- **인덱싱·manifest·썸네일 사전 push 없음.** 파일시스템이 곧 진실 — 파일 변경은 즉시 반영.
- `v=<mtime>` 가 캐시 버전키 — 파일 내용이 바뀌면 mtime 이 바뀌어 새 캐시 키로 자동 재생성.
- **맥이 켜져 있어야 갤러리가 열린다**(원본은 이미 그랬음). 맥이 꺼지면 SPA 가 안내.
- 게이트: 맥이 slug→바스켓→folder 소속 + 경로 이탈을 검증. raw 절대경로 안 받음(folder_id + rel).
- R2 는 SPA 호스팅 + 썸네일/원본 지연 캐시로만. 옛 manifest·thumbs·spaces 는 고아(무해).

## 동영상 HLS 적응형 (2026-08-04 — 넷플릭스식 화질 자동 전환)

유튜브 릴레이의 sidx→byterange HLS 를 로컬 파일에 이식하되, 사다리는 우리가 만든다
(단일 소스 `backend/hls_ladder.py`, NAS 파인더 `/nas/hls/*`(api_nas_hls.py)와 공유).

- **렌디션 = 전역 sidx fMP4 한 파일**(ftyp+moov+sidx+moof…, 유튜브 DASH 구조).
  같은 캐시 파일이 프로그레시브(Range)와 HLS 세그먼트(EXT-X-BYTERANGE)를 동시 서빙 —
  조각 파일 스프레이 없음, LRU·R2 키가 '파일 하나' 그대로. 스트리밍 트랜스코드의
  완주 리먹스(thumbnails.finish_stream_transcode)도 이 포맷으로 바뀌었다(faststart 은퇴).
  ★empty_moov 는 duration=0 → patch_file_duration 이 moov 세 박스를 박는다(스캔 범위는
  moov 끝까지 — moof 까지 훑으면 sidx 바이너리 우연 일치가 색인을 오염시킬 수 있다).
- **렁 = nano(360p ≤0.35M)/tiny(480p ≤0.6M)/low(720p)/orig, h264 만.** lowh(HEVC)는
  변형 간 코덱 혼합 전환이 기기별 리스크라 사다리 밖(프로그레시브 토글 전용 유지).
  nano=비상 바닥 — 테슬라는 시동을 걸면 와이파이→LTE 로 갈아타고 그 LTE 를 차 자체
  (지도·텔레메트리)와 나눠 쓴다: tiny(~0.7Mbps)조차 순간 굶는 상황의 마지노선.
  ★오디오는 전 렁 동일(aac 96k 스테레오) — 변형 전환 시 오디오 설정이 갈리면 딸꾹질.
- **빌드 = 요청 기반**: `/showcase/hls/<slug>/<fid>?rel=` 마스터 요청이 결핍 렁을
  전역 단일 워커에 enqueue(tiny·low=인코딩, orig=원본이 웹 코덱일 때만 -c copy 리먹스,
  옛 faststart 캐시=reindex 승격). 사다리 없으면 404 → SPA 가 기존 프로그레시브로
  폴백(그 시청의 tee 캐시가 첫 렁) → 볼수록 사다리가 자란다.
- **Worker**: m3u8 만 새 no-store 프록시(`/s/<slug>/hls/…`) — 세그먼트는 기존 media
  URL 의 Range 그대로(R2 캐시 재사용). `rv=`(렌디션 파일 **크기**)가 캐시 키에 합류 —
  재인코딩으로 바이트가 바뀌면 키가 갈린다(★mtime 은 LRU touch 로 매 시청 변해 못 쓴다).
- **SPA 화질 버튼 3상**: ⚡자동(HLS)→🐢저용량(프로그레시브 low/lowh)→🎞원본→자동.
  자동이 기본 — 느린 회선은 hls.js 가 조각마다 강등(테슬라 '소리만 나오고 정지'의 근본 해소).
- **LRU**: showcase 30GB(`media_web/`)·NAS 20GB(`nas_stream_cache/`), 서빙마다 mtime 터치.
