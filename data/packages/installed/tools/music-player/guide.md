# music-player — 내 음악 라이브러리 ([self:music])

소스 폴더를 등록하면 안의 음악 파일(mp3/m4a/aac/flac/ogg/opus/wav/aiff/wma)을 스캔해
라이브러리로 정리한다. 태그(제목·아티스트·앨범·앨범아트)는 mutagen, 태그가 없으면
"아티스트 - 제목" 파일명·폴더명(앨범) 폴백. 플레이리스트 생성·담기·빼기 지원.

## 개념 구분 (명명 헌법)

- `[self:music]` = **내 파일** 라이브러리 (이 패키지). self 노드 = 내 소유 데이터 (self:photo 선례).
- `[limbs:music]` = 유튜브뮤직 스트림 재생 (youtube 패키지). sense:radio/limbs:radio 공존 선례처럼
  같은 낱말이 노드 축으로 구분된다.

## op 요약

| op | 입력 | 결과 |
|----|------|------|
| library (기본) | q(부분검색) / artist·album·albumartist(정확) / folder(폴더 단위) / path(단일) / limit(300) | 곡 items |
| track | path | track(태그) + related(관련곡) + playlists(담기 후보, track_path 동봉) |
| related | path (+limit) | 관련곡 top-10 (reason 연결 근거) |
| walk | q 또는 path (없으면 랜덤) + length(30) | 관련곡 랜덤 워크 재생목록 (step·reason) |
| graph | path/q 중심곡 | 에고 그래프 — items=노드(ring 0/1/2), edges=[인덱스 쌍], center |
| folders | — | 곡을 담은 폴더 목록 (library folder 와 짝) |
| albums / artists | — | 묶음 목록 (곡 수·앨범아트) |
| playlists / playlist | — / name | 목록 / 담긴 곡 순서대로 |
| playlist_create / delete | name | 생성·삭제 |
| playlist_add / remove | name + path | 곡 담기·빼기 |
| sources | — | 등록 폴더 + stats + scan 상태 (보관함 탭 한 화면) |
| add_source / remove_source | path(폴더) | 등록(즉시 백그라운드 스캔)·제거 |
| scan | — | 전체 재스캔 (백그라운드·증분 mtime) |

## 재생 아키텍처

서버는 소리를 내지 않는다. 통화의 `stream` 필드(`/music/stream?path=…`)를 **보는 표면의
`<audio>`(media_player 프리미티브)**가 문다 — 라디오 client 모드와 같은 축. 데스크탑
Electron은 맥에서 돌므로 맥 스피커, 원격 런처는 그 브라우저에서 소리가 난다.
`media_player`의 `continuous: true`(이 패키지에서 추가된 렌더러 옵션)는 한 곡이 끝나면
같은 목록의 다음 곡을 자동 재생한다 — 앨범·플레이리스트 연속 듣기.

- 스트리밍: `backend/api_music.py` `GET /music/stream` — HTTP Range(206) 지원, seek 가능.
- 앨범아트: `GET /music/cover?path=&size=` — 내장 태그 → 폴더 아트(cover.jpg 등) → SVG 음표
  플레이스홀더. 캐시 `data/music/covers/`.
- **화이트리스트**: 등록된 소스 폴더 아래의 실존 파일만 서빙 (sources.json 이 진실).

## 저장 구조 (data/music/)

- `sources.json` — 등록 폴더 목록 (photo scans.json 선례)
- `library.db` — 트랙 인덱스 (sqlite WAL). **파생물** — 폴더가 진실, 파일이 사라지면
  스캔 시 라이브러리·플레이리스트에서 자동 제거.
- `playlists.json` — 플레이리스트 (이름 + 트랙 경로 순서 목록)
- `scan_state.json` — 백그라운드 스캔 진행 상태 (scanning/done/error)

## 관련곡 그래프

- edges 테이블(library.db) — 곡마다 top-10 간선(자기 제외). 같은 앨범(4)/아티스트(3)/폴더(2.5)/
  장르(1.5)/연대(1) 가중 + 다양성 캡(같은 앨범 3·같은 아티스트 5) + 대형 버킷(장르 등) 표본 연결.
- **파생물**: 스캔·remove_source 후 자동 재빌드, 비어 있으면 첫 회상 시 즉석 빌드(_ensure_graph).
- walk=가중 랜덤 산책(최근 20곡 재방문 금지·막히면 랜덤 점프). 계기 "이어듣기" 탭 + 🕸️ 음악 그래프
  계기(데스크탑 커스텀, MusicGraphInstrument.tsx — graph op 소비)가 소비자.
- 옛 한국 mp3 태그 모지바케(cp949→latin-1)는 _fix_mojibake 가 복원(한글이 나올 때만 채택).

## 함정

- **스캔은 백그라운드** (도구 60초 제한 — family-news 선례): add_source/scan 은 즉시 반환,
  진행 상태는 `op:sources` 의 scan.label 로 확인. 중복 기동은 in-process 락으로 거부.
- 경로 비교는 전부 NFC 정규화 (macOS NFD 한글 — photo_db 선례).
- mutagen 미설치여도 동작 (파일명 폴백, has_cover=0). 설치: backend/requirements-tools.txt.
- api_music 과 handler 는 `music_core.py` 를 sys.modules 공유 키(`indiebiz_music_core`)로
  같은 인스턴스로 문다 (bulletin_core 선례) — music_core 수정 시 백엔드 재시작 필요.
- 같은 앨범명 동명이인은 albumartist 로 구분 (앨범 드릴이 두 값을 함께 넘긴다).

## 앱 계기 (🎵 음악, 5탭)

전곡(검색+드릴: 재생/담기/정보) · 앨범(드릴: 연속 재생/곡 목록) · 아티스트 ·
플레이리스트(만들기·삭제·드릴: 연속 재생/곡 관리) · 보관함(폴더 등록 folder 필드·통계·재스캔).
phone_render: false (파일이 이 PC에 있음) — 원격 런처에서는 브라우저로 재생 가능.
