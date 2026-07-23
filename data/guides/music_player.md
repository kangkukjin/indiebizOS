# 내 음악 라이브러리 — [self:music]

소스 폴더를 등록하면 안의 음악 파일(mp3/m4a/aac/flac/ogg/opus/wav 등)을 스캔해
라이브러리로 정리한다. 태그(제목·아티스트·앨범·앨범아트)는 자동 추출(mutagen),
태그가 없으면 "아티스트 - 제목" 파일명·폴더명(앨범) 폴백. 플레이리스트 지원.

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
[self:music]{op: "library", artist: "아이유"}        # 정확 필터 (album/albumartist 도 동일)
[self:music]{op: "library", folder: "/…/재즈"}       # 폴더 단위 (하위 포함 — folders 결과의 path 와 짝)
[self:music]{op: "folders"}                          # 곡을 담은 폴더 목록 (폴더 단위 재생)
[self:music]{op: "albums"}  /  {op: "artists"}       # 묶음 목록
[self:music]{op: "track", path: "/…/곡.mp3"}         # 곡 상세 (태그 + 관련곡 + 담을 플레이리스트 후보)
[self:music]{op: "related", path: "/…/곡.mp3"}       # 관련곡 top-10 (reason 연결 근거)
[self:music]{op: "walk", q: "김광석", length: 30}    # 관련곡 랜덤 워크 재생목록 (q 생략=랜덤 시작)
[self:music]{op: "graph", q: "사계"}                 # 에고 그래프 (items=노드, edges=인덱스 쌍)
[self:music]{op: "playlist_create", name: "드라이브"}
[self:music]{op: "playlist_add", name: "드라이브", path: "/…/곡.mp3"}
[self:music]{op: "playlist", name: "드라이브"}       # 담긴 곡 순서대로
```

## 관련곡 그래프 (Obsidian 로컬 그래프의 음악판)

곡마다 관련곡 top-10 간선(자기 제외) — 근거=같은 앨범(4)/아티스트(3)/폴더(2.5)/장르(1.5)/연대(1)
가중 합산, 같은 앨범·아티스트 쏠림 캡(3·5)으로 클러스터 밖 간선 보장. 스캔 후 자동 재빌드(파생물,
edges 테이블). walk=이 그래프의 가중 랜덤 산책(최근 20곡 재방문 금지, 막히면 랜덤 점프) —
"관련곡 10곡 중 랜덤 다음 곡" 랜덤 플레이가 이것. 데스크탑 전용 🕸️ 음악 그래프 계기
(MusicGraphInstrument — 노드 클릭=중심 이동+재생, 곡 끝나면 관련곡 랜덤 자동 이어듣기)가 graph op 를 소비.

결과 items 구조 필드: title/artist/album/albumartist/genre/year/track_no/duration/duration_str/
path/stream(재생 URL)/image(앨범아트) → `>> [table:filter/sort/groupby]` 파이프 직결.

## 재생

서버는 소리를 내지 않는다 — 통화의 `stream` 필드(`/music/stream`, Range 지원)를 보는 표면의
`<audio>`(media_player 프리미티브)가 문다. 앱 계기(🎵 음악)에서 곡·앨범·플레이리스트를 누르면
재생되고, 앨범·플레이리스트 드릴의 "연속 재생"은 한 곡이 끝나면 다음 곡을 자동 재생한다
(`media_player`의 `continuous: true` 렌더러 옵션). 스피커에서 소리를 내달라는 요청이면
이 액션이 아니라 계기를 안내하라 — 서버측 재생 op는 없다.

## 함정

- **스캔은 백그라운드**: add_source/scan 은 즉시 반환된다. 완료 여부는 `op:"sources"` 의
  scan 필드로 확인 (status: scanning/done/error).
- 스트리밍은 등록된 소스 폴더 아래의 파일만(화이트리스트) — 폴더 등록 없이 stream URL 만
  만들어도 404.
- 폴더가 진실: 파일을 지우거나 옮기면 다음 스캔 때 라이브러리·플레이리스트에서 자동 제거.
- playlist_add/remove 의 path 는 library/track 결과의 path 를 그대로 쓸 것 (NFC 정규화 매칭).
- 저장: data/music/ (sources.json·library.db·playlists.json). 서빙: backend/api_music.py.
