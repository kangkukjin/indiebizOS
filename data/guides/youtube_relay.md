# 유튜브 릴레이 ([limbs:music]{op: "relay"}) 가이드

## 무엇인가
원격런처·폰 표면이 **유튜브에 직접 접속하지 않고** 유튜브 영상·음악을 보는 길.
맥이 yt-dlp 로 스트림 URL 을 해소하고, ffmpeg 이 그 URL 에서 받으면서(`-c copy`
리먹스, 재인코딩 0) 첫 바이트부터 fMP4 생방송으로 중계한다 — 같은 바이트가 캐시로
tee 되어(공개파일 스트리밍 트랜스코드 선례) 두 번째 재생부터는 캐시 직행(Range·seek 완전).

**mode:"client" 와의 차이**: client 는 googlevideo URL 을 클라이언트에 직접 주는데,
그 URL 은 해소한 맥의 IP 에 잠겨 있어 집 WiFi 밖(LTE)에선 재생이 죽는다(포털 tune
프록시와 같은 부류). relay 는 받는 쪽이 항상 맥 자신이라 표면이 어디에 있든 재생된다.

## 사용법
```
[limbs:music]{op: "relay", query: "아이유 밤편지", media: "audio"}          # 검색 → 소리만
[limbs:music]{op: "relay", query: "여행 브이로그", media: "video", count: 6} # 검색 → 영상
[limbs:music]{op: "relay", query: "https://youtu.be/…", media: "video"}     # URL 직접
```
- 통화: `{success, media, items:[{title, channel, duration, video_id, stream, thumb, is_video}]}`
- **relay 자체는 검색만 하므로 즉답**(대기 0). 해소+ffmpeg 는 표면이 `stream`
  (`/yt/relay/<video_id>?kind=audio|video`)을 무는 순간(재생 버튼) 시작된다.
- 실측: 첫 바이트 ~2초(해소 포함), 4분 영상 완주 캐시 ~30초. 캐시 직행 ~5ms.

## 서빙 면 (backend/api_ytrelay.py)
- `GET /yt/relay/{video_id}?kind=audio|video` — 캐시 있으면 FileResponse(Range 206),
  없으면 생방송(`X-Transcode-Live: 1`, no-store) + 파이썬 tee → 완주 시 faststart 리먹스.
- 시청 중단 시에도 데몬 스레드가 마저 받아 캐시를 완성한다(thumbnails.detach 재사용).
- 캐시: `data/youtube_cache/<id>.<kind>.mp4`, 5GB 상한 LRU(재생 시 mtime 터치).
- 인증: 로컬 신뢰 — 외부는 런처 세션(`/music/stream` 동급, is_public 등록 금지).
- duration 패치: yt-dlp 의 총 길이를 fMP4 init(mvhd·tkhd·mdhd)에 박아 생방송에서도
  시크바에 총 길이가 정확히 보인다.

## 앱 표면 — ▶️ 유튜브 (yttv 계기, 시청 전용 앱)
음악 앱(🎵 유튜브 뮤직=ytmusic)과 별개의 **동영상 시청 앱**. 유튜브 앱을 닮은 3탭:
- **홈**: `[sense:video]{op:"feed"}` — 추천 피드. 시청 기록(data/youtube_watch.json,
  릴레이 서버가 재생마다 적재)에서 ①본 채널의 새 영상(채널 RSS) ②본 제목 연관
  검색(ytsearch)을 병렬로 모아 라운드로빈 병합(본 것 제외). 기록 없으면 콜드스타트
  기본 카테고리. **볼수록 개인화되는 자기강화 루프**(실측: 1편 시청 후 피드 전환).
- **검색**: search_youtube → 카드 그리드.
- **기록**: `op:"history"` — 시청 기록(최신순 dedup).
- 카드 클릭 → **시청 페이지**(`op:"watch"`): 릴레이 플레이어 + 연관 동영상 8건.
  연관 클릭=`recursive` 드릴 → 다음 영상 시청 페이지(유튜브식 무한 탐색).
  watch 는 열리면서 릴레이 해소를 **백그라운드 예열**(`_prewarm_relay`) — 재생 버튼이
  거의 즉시 시작(실측 0.3초).
- 구현: `tool_watch.py`(youtube 패키지 — feed/watch/history). ★phone_render:false —
  폰 네이티브는 relay 상대 URL 이 폰 자신을 가리켜 죽는다(릴레이=PC 몸). 원격 런처는 됨.

렌더러 어휘(이 앱을 위해 신설, 두 렌더러 동기): `media_player` 의 `lazy: true`
(preload=none — 항목마다 스트림을 미리 물면 항목 수만큼 ffmpeg 가 뜬다),
`video: '{is_video}'`(또는 true), `poster: '{thumb}'` / `card_list` 카드의
`wide: true`(16:9 가로 썸네일 상단 — 유튜브 모바일 홈 카드).

## 추천의 정직한 경계
유튜브 계정 개인화 추천=로그인 쿠키 없인 불가(안 함). 인기 급상승 페이지=2025년
유튜브가 제거(실측: home 리다이렉트 — feed/trending 다시 시도하지 말 것). 그래서
추천 재료는 전부 비로그인: 채널 RSS(youtube.com/feeds/videos.xml?channel_id=)·
ytsearch·자기 시청 기록.

## 적응형 재생 (HLS — 기본 경로, 넷플릭스식)
`/yt/hls/{video_id}/master.m3u8` — **유튜브의 화질 사다리(avc1 144~1080p DASH)를
재인코딩 없이 byterange HLS 로 묶는다**: 각 스트림이 ftyp+moov(init)+sidx(조각
색인)+moof… 구조(실측)라 sidx 만 파싱하면 EXT-X-MAP+EXT-X-BYTERANGE 플레이리스트가
나오고, 세그먼트는 googlevideo 로 Range 그대로 중계. hls.js 가 조각마다 회선을 재서
화질을 자동 전환(느린 회선=화질만 내려가고 안 멈춤 / 빠른 회선=1080p — 실측 localhost
에서 1080 렁 자동 선택).
- 통화 `stream_hls` + media_player `src_hls` 어휘. 우선순위: hls.js > 사파리 네이티브
  HLS > 프로그레시브(src, 느린 회선이면 src_low). 원격 렌더러=video[data-hls]
  MutationObserver 하이드레이션, 데스크탑=HlsVideo 컴포넌트(CDN hls.js).
- lazy 계약 유지: autoStartLoad:false + play 이벤트에 startLoad.
- ★★yt-dlp 를 최신으로 유지할 것 — 2026.02 판은 유튜브 정책 변화로 **360p 결합 포맷
  하나만** 받았다(사다리 전멸, "원본"이 사실 360p였음). 2026.07 판으로 갱신하니 전
  사다리 복구(실측). 화질 저하 신고가 오면 렁 수부터 실측.
- HLS 경로는 캐시 tee 없음(조각 스프 — 재시청 캐시는 프로그레시브 경로의 것).
- **로컬 파일(NAS·공개파일)도 같은 방식으로 확장됨**(2026-08-04): 사다리를 우리가
  만든다 — `backend/hls_ladder.py`(렌디션=전역 sidx fMP4 한 파일, 요청 기반 빌드),
  공개파일 `/showcase/hls/…`·NAS `/nas/hls/…`. 상세는 public-files 패키지 guide.md.

## 저대역 (테슬라 등 느린 회선 — 프로그레시브 폴백용)
`?q=low` = **유튜브가 이미 만들어 둔 ≤480p 판을 고르는 것**(-c copy 리먹스 그대로 —
공개파일 저대역과 달리 로컬 재인코딩이 없다). 증상="소리는 나오는데 화면 정지"
(1.4Mbps 회선에 1080p 3-5Mbps → 비디오 버퍼만 굶음, 테슬라 실차 실측).
- 통화의 `stream_low` 필드 + media_player `src_low` 렌더러 어휘: 표면이
  navigator.connection(downlink<3 또는 rtt>250)으로 자동 선택. 캐시 슬롯 분리
  (`<id>.video.low.mp4`) — 같은 슬롯이면 저화질이 데스크탑을 오염. 오디오는 q 무시.
- 좋은 WiFi 의 테슬라가 원본을 받았는데도 정지하면(디코드 한계 부류) 수동 토글 후속.

## 함정
- **옛 영상(2005년대)은 결합 포맷 하나뿐** — audio 포맷 문자열에 `/best` 폴백이 없으면
  "Requested format is not available"(실측 jNQXAC9IVRw). 결합 입력이어도 오디오 경로는
  `-vn` 이라 무해.
- 오디오 copy 는 acodec 이 mp4a(aac)일 때만 — 아니면 AAC 재인코딩 폴백(드묾, 오디오라 빠름).
- 해소 결과는 45분 메모리 캐시 — 부패 시(스트림 첫 바이트 실패) 자동 무효화 후 502,
  다음 요청이 재해소.
- 생방송 중엔 seek 불가(Range 없음) — 캐시 완성 후 재로드하면 완전 seek. 짧은 대기라
  오프셋 스트림(t=)은 만들지 않았다(공개파일과 달리 원본이 이미 짧은 유튜브 클립).
