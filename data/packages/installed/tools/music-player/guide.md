# music-player — 내 음악 라이브러리 ([self:music])

소스 폴더를 등록하면 안의 음악 파일(mp3/m4a/aac/flac/ogg/opus/wav/aiff/wma)을 스캔해
라이브러리로 정리한다. 태그(제목·아티스트·앨범·앨범아트)는 mutagen, 태그가 없으면
"아티스트 - 제목" 파일명·폴더명 폴백. 플레이리스트 생성·담기·빼기 지원.

**보는 축은 폴더**(사용자가 손으로 만든 의미 단위) — 파인더처럼 한 단계씩 찾아 들어가
어느 단계에서든 그 아래 전체를 연속 재생하는 게 주 동선이고, 검색·플레이리스트가 보조다.

폴더 드릴은 **탐색/재생 2탭**이다 — '폴더'(하위 폴더만) / '이 폴더 전부 재생'(하위 포함
전체 곡). 탐색 중 곡을 같이 깔면 폴더에 직접 든 곡으로 오해된다(실사용 신고).
그리고 드릴은 **재귀**다: `item_click.recursive: true` = "지금 보고 있는 드릴 화면(view 또는
tabs)을 그대로 다시 쓴다". 한 벌 선언으로 깊이 제한 없이 파고든다(단계마다 손으로 중첩해
쓰면 declared depth 에서 반드시 막힌다). 렌더러 2곳·검증기 모두 같은 규칙.

## 개념 구분 (명명 헌법)

- `[self:music]` = **내 파일** 라이브러리 (이 패키지). self 노드 = 내 소유 데이터 (self:photo 선례).
- `[limbs:music]` = 유튜브뮤직 스트림 재생 (youtube 패키지). sense:radio/limbs:radio 공존 선례처럼
  같은 낱말이 노드 축으로 구분된다.

## op 요약

| op | 입력 | 결과 |
|----|------|------|
| library (기본) | q(부분검색) / folder(폴더 단위, 하위 포함) / path(단일) / limit(300) | 곡 items |
| track | path | track(태그) + playlists(담기 후보, track_path 동봉) |
| folders | folder(생략=최상위) | 한 단계 탐색 — items=직속 하위 폴더(맨 앞 ⬆️ 상위 행) + tracks=그 폴더 아래 전체 곡(상한 500) |
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
같은 목록의 다음 곡을 자동 재생한다 — 폴더·플레이리스트 연속 듣기.

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

## 2026-07-28 은퇴 — 되살리지 말 것

사용자 판단으로 5기능 제거(쓸모가 없었다). 옛 문서·대화에서 이름을 보더라도 다시 만들지 말 것.

- `compose` (AI 추천 플레이리스트) — theme 자연어 → 경량 AI 2단 선곡·작명·저장
- `related`·`walk`·`graph` — 관련곡 top-10 간선 그래프, 가중 랜덤 산책, 에고 그래프
- `albums`·`artists` — 앨범·아티스트 묶음 목록과 드릴다운
- `library` 의 artist/album/albumartist 정확 필터 (앨범·아티스트 뷰 전용이었다 — 검색은 q 가 덮는다)
- 🕸️ 음악 그래프 계기 (MusicGraphInstrument.tsx, 데스크탑 STATIC_DOMAINS)

`library.db` 의 `edges` 테이블은 파생 캐시라 버렸다 — `_conn()` 의 `DROP TABLE IF EXISTS edges`
가 옛 설치본까지 정리한다(원본 음악 파일 무손상). 옛 한국 mp3 태그 모지바케 복원
(`_fix_mojibake`, cp949→latin-1)은 태그 추출 쪽이라 **그대로 남아 있다**.

## 함정

- **스캔은 백그라운드** (도구 60초 제한 — family-news 선례): add_source/scan 은 즉시 반환,
  진행 상태는 `op:sources` 의 scan.label 로 확인. 중복 기동은 in-process 락으로 거부.
- 경로 비교는 전부 NFC 정규화 (macOS NFD 한글 — photo_db 선례).
- mutagen 미설치여도 동작 (파일명 폴백, has_cover=0). 설치: backend/requirements-tools.txt.
- api_music 과 handler 는 `music_core.py` 를 sys.modules 공유 키(`indiebiz_music_core`)로
  같은 인스턴스로 문다 (bulletin_core 선례) — music_core 수정 시 백엔드 재시작 필요.

## 앱 계기 (🎧 음악, 4탭)

전곡(검색+드릴: 재생/담기/정보) · **폴더**(드릴: 연속 재생/곡 목록 — 주 동선) ·
플레이리스트(만들기·삭제·드릴: 연속 재생/곡 관리) · 보관함(폴더 등록 folder 필드·통계·재스캔).
phone_render: false (파일이 이 PC에 있음) — 원격 런처에서는 브라우저로 재생 가능.
