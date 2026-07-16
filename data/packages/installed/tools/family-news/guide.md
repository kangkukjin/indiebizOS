# 가족신문 (family-news) 가이드

폰(USB) 사진으로 신문 판을 조판해 공개 주소에 누적 발행하는 가족용 정기간행물.
`[others:family_news]{op: ...}` 단일 액션.

## 흐름

1. **제작** `{op:"create"}` — 폰이 USB 로 연결돼 있어야 한다(adb). 지난 발행 이후(첫 판은
   최근 7일, `days` 로 조정)의 DCIM 사진을 MediaStore 로 조회 → 날짜별 비례 샘플링으로
   `photo_limit`(기본 48) 이하로 추림 → pull → EXIF GPS 를 Kakao 역지오코딩(1km 격자
   캐시 `data/family_news/geo_cache.json`)으로 "시군구 동" 장소명으로 → 웹판(1600px,
   EXIF/GPS 제거) → 날짜별 섹션 정적 HTML. **백그라운드 조판** — create 는 즉시 반환,
   진행은 `{op:"status"}` 의 building 으로 확인. 미발행 초안이 있으면 갈아엎는다(호수 재사용).
2. **미리보기** — `http://localhost:8765/family-news/preview/<eid>/` (맥 로컬 전용, 터널 차단).
3. **발행** `{op:"publish", edition_id}` — 첫 발행 때 5자 코드 주소(`<public_base>/n/<코드>/`)
   생성. 아카이브 홈에 발행판이 누적된다(최신 먼저). 발행 전 판은 절대 공개되지 않는다.
4. **방명록/사진 보내기** — 공개 페이지 하단. 가족 업로드는 공개되지 않고
   `data/family_news/uploads/` 에 쌓였다가 **다음 create 때 "가족이 보내온 사진" 섹션으로
   합류**(발행 전 검수를 거치는 구조). `{op:"uploads"}`/`{op:"comments"}` 로 앱에서 조회.

## 함정

- **폰 미연결**: create 가 즉시 "USB 연결 확인" 으로 거부. `adb devices` 로 확인.
- **datetaken 기준**: MediaStore `datetaken`(촬영 시각) 으로 구간을 자르므로, 카톡 저장
  이미지 등 DCIM 밖 사진은 안 실린다(의도 — 스크린샷·다운로드 제외).
- **장소 없음**: 폰 카메라의 위치 태그가 꺼져 있으면 장소가 비고 날짜 섹션만 남는다.
- **draft 갈아엎기**: create 는 미발행 초안을 대체한다. 발행판은 건드리지 않는다.
- **handler 도구라 /ibl/execute 직접 호출 시 project_id 필요** (예: "컨텐츠").
- **공개 사진 프라이버시**: 웹판은 EXIF 전부 제거(위치·기기). 장소는 텍스트 라벨로만.

## 서빙 구조 (헌법 1조 이음매)

- 맥: `backend/api_family_news.py` — `/family-news/page|media|gb|upload/{slug}` (X-Showcase-Secret
  게이트, 발행판만) + `/family-news/preview/*` (로컬 전용, is_public_remote_path 미등록).
- Worker: public-files 와 공유 (`site/worker.js`) — `/n/<slug>/` 홈(동적, 캐시 없음),
  `/n/<slug>/e/<eid>/` 판(정적 HTML), `/n/<slug>/e/<eid>/media/<file>` 사진(R2 지연 캐시),
  `/n/<slug>/gb` GET/POST 방명록, `/n/<slug>/upload` POST 업로드(raw body, multipart 아님).
- 판 디렉토리는 발행 후 불변(재제작은 새 eid) — R2 캐시 무효화 불필요.
