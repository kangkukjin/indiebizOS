# 내 음악 라이브러리 — [self:music]

소스 폴더를 등록하면 안의 음악 파일(mp3/m4a/aac/flac/ogg/opus/wav 등)을 스캔해
라이브러리로 정리한다. 태그(제목·아티스트·앨범·앨범아트)는 자동 추출(mutagen),
태그가 없으면 "아티스트 - 제목" 파일명·폴더명 폴백. 플레이리스트 지원.

**보는 축은 폴더다.** 폴더 구조가 사용자가 직접 만든 의미 단위이므로, 이 앱은
폴더를 파인더처럼 찾아 들어가 → 그 폴더 전체 연속 재생을 주 동선으로 삼는다
(검색·플레이리스트가 보조).

## 폴더 탐색 — 파인더식 한 단계씩

`folders` 는 **한 단계만** 돌려준다. folder 를 생략하면 등록된 소스 루트, 주면 그
직속 하위 폴더다. 응답은 두 갈래:

- `items` — 바로 아래 폴더들. 맨 앞은 `⬆️ 상위 폴더`(kind=up, path 가 비면 최상위).
  각 행의 `n`/`sub` 는 **그 가지 아래 전체** 곡 수·하위 폴더 수 → 들어가기 전에 규모를 본다.
- `direct` — 그 폴더에 **직접** 든 곡(하위 폴더 제외). 파인더가 폴더와 파일을 한 화면에
  보이듯 탐색 탭에 함께 나온다. 없으면 `direct_note` 한 줄만(폴더만 든 곳은 조용하다).
- `tracks` — 그 폴더 **아래 전체**(하위 폴더 포함) 곡. 어느 단계에서 멈추든 그 아래 음악을
  전부 이어 듣는다. 표면이 곡마다 `<audio>` 를 그리므로 상한 500곡(`handler._PLAY_CAP`),
  넘치면 `play_note` 가 "N곡 중 앞 500곡"이라고 알린다.

★계기 2탭 = **파인더 그대로**:
- '폴더' 탭 = 하위 폴더 + `direct`(이 폴더 파일). 파인더로 폴더를 연 화면과 같다.
- '이 폴더 전부 재생' 탭 = `tracks`(하위 폴더 곡까지) — "다 골랐을 때" 누르는 자리.

탐색 탭에 *하위* 곡을 깔면 안 된다 — 폴더밖에 없는 곳에 곡이 보이면 그 폴더에 든 것으로
읽힌다(2026-07-28 신고: "MUSIC 안에는 폴더밖에 없어야 하는데 곡이 보인다").

옛 `folders` 는 곡을 담은 폴더를 전부(실측 275개) 평평하게 늘어놓아 찾아 들어갈 수가
없었다 — 2026-07-28 트리 탐색으로 교체.

## 형식 — 무엇이 들어오고 무엇이 변환되나

색인 대상: mp3 · m4a/aac · flac · ogg/opus · wav · aiff · wma, 그리고 **cue 시트**.

- 브라우저(Chromium)가 직접 무는 것: mp3 · m4a · aac · flac · ogg · opus · wav
- **직접 못 무는 것: wma · ape** → `/music/stream` 이 ffmpeg 으로 mp3 변환해 캐시
  (`data/music/transcoded/`, 4GB LRU). 첫 재생만 잠깐 걸리고(실측 곡당 1~6초) 이후는 원본과
  같은 속도·Range·seek. 캐시는 파생물이라 지워도 된다.
- **CD 통이미지(.ape/.flac + .cue)**: cue 를 읽어 **곡 단위로** 색인한다. 한 파일 안의
  구간이므로 `media_path`(실제 파일)와 `start`(시작 초)를 함께 들고, 재생 때 그 구간만
  잘라 변환한다. cue 가 가리키는 파일 자체는 따로 색인하지 않는다(중복 방지).
  ★cue 인코딩은 utf-8 → cp949(한글이 나올 때만) → cp1252/latin-1 순으로 추정한다.

실측(2026-07-28): 바하 전집 158장 = **3,227곡**이 곡 제목·연주자와 함께 들어왔다.
그전에는 `.ape` 가 색인 대상이 아니어서 **그 157개 폴더가 통째로 안 보였다**(폴더 트리는
색인된 곡에서 파생되므로).

## ★개념 구분 — [limbs:music] 과 다르다

- `[self:music]` = **내 파일** 음악 라이브러리 (이 가이드). "내 음악", "음악 폴더", "플레이리스트".
- `[limbs:music]` = **유튜브뮤직** 스트림 재생/다운로드 (youtube 패키지). "유튜브에서 틀어줘".
- `[sense:radio]`/`[limbs:radio]` = 인터넷 라디오.

## op 사용법

```
[self:music]{op: "add_source", path: "~/Music"}     # 폴더 등록 — 즉시 백그라운드 스캔
[self:music]{op: "sources"}                          # 폴더 목록 + 통계 + 스캔 상태 (진행 확인도 이걸로)
[self:music]{op: "scan"}                             # 전체 재스캔 (백그라운드·증분)
[self:music]{q: "아이유"}                            # op 생략=library. 제목·아티스트·앨범·파일명 부분검색
[self:music]{op: "folders"}                          # 최상위(등록한 소스 폴더)
[self:music]{op: "folders", folder: "/…/MUSIC"}      # 그 폴더의 한 단계 아래 (파인더식 탐색)
[self:music]{op: "library", folder: "/…/재즈"}       # 폴더 단위 곡 목록 (하위 포함)
[self:music]{op: "track", path: "/…/곡.mp3"}         # 곡 상세 (태그 + 담을 플레이리스트 후보)
[self:music]{op: "playlist_create", name: "드라이브"}
[self:music]{op: "playlist_add", name: "드라이브", path: "/…/곡.mp3"}
[self:music]{op: "playlist", name: "드라이브"}       # 담긴 곡 순서대로
[self:music]{op: "stop"}                             # 재생 중지 (표면의 <audio> 를 멈춘다)
```

결과 items 구조 필드: title/artist/album/albumartist/genre/year/track_no/duration/duration_str/
path/stream(재생 URL)/image(앨범아트) → `>> [table:filter/sort/groupby]` 파이프 직결.

## 2026-07-28 은퇴 — 되살리지 말 것

아래 5기능을 **사용자 판단으로 제거**했다(쓸모가 없었다). 옛 대화·문서에서 이름을 보더라도
다시 만들지 말고, 필요하면 사용자에게 먼저 물을 것.

| 은퇴한 것 | 무엇이었나 |
|---|---|
| `compose` (AI 추천) | theme 자연어로 경량 AI가 선곡·작명해 플레이리스트 저장 |
| `related`·`walk`·`graph` | 관련곡 top-10 간선 그래프 + 랜덤 산책 + 에고 그래프 뷰 |
| `albums`·`artists` | 앨범·아티스트 묶음 목록(과 그 드릴다운) |
| `library` 의 artist/album/albumartist | 앨범·아티스트 뷰 전용 정확 필터 (검색은 `q` 가 덮는다) |
| 🕸️ 음악 그래프 계기 | 데스크탑 전용 SVG 에고 그래프 창 (MusicGraphInstrument) |

부수적으로 `library.db` 의 `edges` 테이블(관련곡 간선)은 파생 캐시라 그냥 버렸다 —
`_conn()` 이 열 때 `DROP TABLE IF EXISTS edges` 로 옛 설치본도 정리한다. 원본 음악 파일은 무손상.

## 재생

서버는 소리를 내지 않는다 — 통화의 `stream` 필드(`/music/stream`, Range 지원)를 보는 표면의
`<audio>`(media_player 프리미티브)가 문다. 앱 계기(🎧 음악)에서 곡·폴더·플레이리스트를 누르면
재생되고, 폴더·플레이리스트 드릴의 "연속 재생"은 한 곡이 끝나면 다음 곡을 자동 재생한다
(`media_player`의 `continuous: true` 렌더러 옵션). 스피커에서 소리를 내달라는 요청이면
이 액션이 아니라 계기를 안내하라 — 서버측 재생 op는 없다.

**정지**는 `op: "stop"` — 서버가 소리를 내지 않으므로 `stop_in_client: true` 를 돌려주고,
그걸 받은 표면이 자기 `<audio>` 를 멈춘다(라디오 client 모드와 **같은 규약**). 계기 상단에
라디오와 같은 자리의 `■ 정지` 버튼이 세 탭(전곡·폴더·플레이리스트)에 있다 — 한 폴더가
수백 곡이면 재생 중인 곡을 눈으로 찾아 누르는 게 사실상 불가능하기 때문. 멈춘 위치는
남으므로 다시 누르면 이어서 재생된다.

## 앱 계기 (4탭)

전곡(검색 + 드릴: 재생/플레이리스트에 담기/정보) · **폴더**(트리 탐색 / 이 폴더 전부 재생 2탭) ·
플레이리스트(만들기·삭제·곡 관리·연속 재생) · 보관함(폴더 등록·통계·재스캔).
`phone_render: false` — 폰 네이티브에선 숨고 원격 브라우저에선 보인다(pc_only).

## 함정

- **스캔은 백그라운드**: add_source/scan 은 즉시 반환된다. 완료 여부는 `op:"sources"` 의
  scan 필드로 확인 (status: scanning/done/error).
- 스트리밍은 등록된 소스 폴더 아래의 파일만(화이트리스트) — 폴더 등록 없이 stream URL 만
  만들어도 404.
- 폴더가 진실: 파일을 지우거나 옮기면 다음 스캔 때 라이브러리·플레이리스트에서 자동 제거.
- playlist_add/remove 의 path 는 library/track 결과의 path 를 그대로 쓸 것 (NFC 정규화 매칭).
- `music_core.py` 는 패키지 서브모듈이라 `/packages/reload` 로 안 바뀐다 — backend 파일 touch 로
  워커를 리로드해야 반영된다(sys.modules 캐시).
- 저장: data/music/ (sources.json·library.db·playlists.json). 서빙: backend/surface/api_music.py.
