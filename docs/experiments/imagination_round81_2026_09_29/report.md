# 상상 훈련 81회차 결과보고서 (2026-09-29) — 미디어 제작

훈련 턴 · **무수정**(가이드 §4-3). 아래 갭 원장의 근거는 셋이다.
- [before.json](before.json)·[baseline.json](baseline.json)
- 셸로 읽은 코드
  - `media_producer/handler.py`·`tts_engines.py`·`render_artifact.py`
  - `photo-manager/handler.py`, `backend/datastore/file_index.py`
  - `backend/ibl/ibl_v2_adapters.py`·`tool_context.py`·`ibl_routing.py`
  - `lecture_workspace/handler.py`, `music-player`·`radio`·`web-builder` 패키지
- 읽기 전용 대조
  - 사진 396장의 EXIF 현지 시각(`sips -g creation`)
  - `data/music/library.db`(`mode=ro`)
  - 산출 mp3의 `ffprobe`·`volumedetect`·`silencedetect`
  - 렌더 PNG는 훈련자가 직접 열어 봤다.

훈련 당시 관측은 아래에 보존했다. 후속 수리는 마지막 집행 완료 절에 별도 기록했다.

★**개인정보**:
- 사진의 경로·파일명·장소·기종, 음악의 제목·아티스트·경로, 즐겨찾기 방송국은 before.json에 모양(shape)만 남겼다. 이 보고서에도 싣지 않았다. 실은 것은 건수·칸 이름·불리언·시각 차이(시간 단위)뿐이다.
- 저장 후 before.json을 확장자(`.jpg`·`.HEIC`)·사진 폴더·vault 경로·`lat`/`artist` 값으로 검사했다. 0건이었다.
- baseline.json의 outputs 파일명 목록은 개수+해시로 줄였다.

## 축 선정

- **축**: 행동 기준 미조합 메뉴의 미디어 어휘다. 모두 describe로 op·인자·관측 반환을 확인했다.
  - 생성: `engines:tts`·`render`·`image_read`
  - 웹: `engines:web`·`web_site`·`web_component`
  - 자기 매체: `self:photo`·`music`·`slide`·`deck`·`lecture`
  - 손발: `limbs:music`·`radio`·`radio_favorite`, 감각: `sense:radio`
  - `engines:remotion`·`engines:newspaper`는 "사용 가능한 액션이 아닙니다"(비활성)여서 뺐다.
- **도메인**: 사용자의 실제 흐름에서 나올 법한 일로 골랐다.
  - 강의 슬라이드 한 장에 내 목소리 나레이션(어느 장이 아직 안 구워졌나, 시험 나레이션은 edge)
  - 가족신문 사진 고르기(날짜·장소별)
  - 사진 속 글자 읽기
  - 유튜브 썸네일 렌더
  - 블로그 최근 글을 한 페이지 웹으로
  - 강의 자료 웹 컴포넌트, 분위기별 재생목록, 라디오 즐겨찾기
  - 아침 라디오·주간 사진 트리거(check)
- **부작용·비용 규칙**
  - TTS는 edge(무과금) 1회만 실행했다. 모르는 engine·숫자 rate 호출은 합성 전에 실패하는 것을 코드로 확인한 뒤 실행했다.
  - 비전 AI(image_read read)는 1회. critic 2회는 prescreen 경로라 비전 호출이 없다.
  - 아래는 **check만** 했다.
    - GPU·AI·긴 렌더: slide create, deck video, `나레이션생성` 스크립트
    - 외부·배포: web create/build/deploy, component add/fetch
    - 소리·화면: radio/music play·stop
    - 기록 변경: 즐겨찾기 변경, trigger
  - 사진·음악 라이브러리는 읽기만 했다.
  - 쓰기는 스크래치 재생목록 `IT81_잔잔` 하나다(생성→3곡 담기→삭제, 원상 대조).
- **축 선정 관문 질문**("기계로 열거 가능한가")
  - "사진의 '그날'이 사용자의 그날인가", "산출물이 들리고 보이는가"는 실제로 만들어 보고 열어 봐야 드러난다. 그래서 훈련 축이다.
  - 발견 중 둘은 열거할 수 있으니 census로 넘긴다.
    - 평문 반환 핸들러 × `legacy-envelope` 어댑터(B81-1)
    - 산출 경로 해소기를 안 쓰는 emitter(B81-4)
- **닫힌 밭**: 값 표기·경로 방언·날짜 표기·동시성·절단 표지는 다시 갈지 않았다.
  - B81-2는 표기가 아니다. ISO로 적법하게 적히지만 **순간이 틀린** 생산자 결함이다.
  - `self:music` limit 300의 무표지 절단은 절단 표지 밭이라 적지 않았다.
- **탐침**: `agent_id:"IT81_probe"`·`task_id:"IT81_task"`. 모든 요청이 `#!ibl edition=2`·`edition:2`·`project_id:"컨텐츠"`·`origin:"training"`이다.
  - 큰 결과는 `value`가 표시 요약이라 `read_result` 페이징으로 전량 회수했다(탐침 `full_rows`).

## 지표 스냅샷 (훈련 전)

- 행동 미조합 140/168 · 파이프 길이 중앙값 3 · 문형 4(조회 26·축적 8·적용 6·조건 2) · 파트너 다양성 중앙값 2
- 80회차와 같다. 원본은 [metrics.json](metrics.json)이다.
- 지표는 몸의 현황이며, 훈련 실측은 증류에 담기지 않는다(§6).

## 과제 표

원문·판정식: [probe.py](probe.py) · 응답(개인 원문 마스킹): [before.json](before.json) · 기준선과 회차 후 diff: [baseline.json](baseline.json).

**21과제 중 기계 판정 8통과 · 13실패**다. 결함 5부류 · 마찰 4 · 어휘 후보 1이다. 실행 13 · check만 5 · 실행+check 혼합 3. check 과제는 기계 판정이 기본 통과라서 분류는 아래 표가 정본이다.

탐색 중 훈련자 문장 잘못은 결함 판정에서 뺐다. 거절 안내가 모두 위치를 정확히 짚었다.
- `len([self:photo]{}.items)`·`unique(목록 >> each)`: PURE_EXPRESSION
- `table:join{with:…}`: UNKNOWN_ARGUMENT, 사용 가능 인자 목록이 함께 왔다
- `len(groupby 결과)`: RECORD_LENGTH 경고가 정확했다
- try 전에 초기화 안 한 변수: UNBOUND

| # | 상상 의도 | 결과 | 분류 |
| --- | --- | --- | --- |
| T01 | 강의마다 노트 있는 장 · 이미 구운 내 목소리 wav → 아직 구울 장 | 강의 8·노트 98·구운 wav 71·**구울 장 28**(anti join). 단 `list`의 `items` 카드에 `lecture_id`가 없어 옆 칸 `lectures`로만 잇는다 | 꼬임 F81-1 |
| T02 | 슬라이드 한 장 노트 앞 60자 → 시험 나레이션(edge) → 영상용 폴더 | mp3 24kHz 모노 **10.3초**, 평균 −17.5dB·최대 −4.3dB, 문장 사이 쉼 3(들리는 음성). 프로그램은 **`ADAPTER_SHAPE` 실패**, 폴더 `IT81_narr/`는 버려져 `outputs/` 바로 아래 | 결함 B81-1·B81-4 |
| T03 | "내 목소리로" — engine 선택지·길 안내, 나레이션생성·deck video check | `engine:"qwen3"` → "알 수 없는 engine 'qwen3' — gemini(기본) \| edge"(정직하나 등록 스크립트 `나레이션생성` 길은 말하지 않음). 숫자 rate → "Invalid rate '0.9'". check 셋 다 `incomplete`·경고 0. 남은 파일 0 | 재확인(B79-2) |
| T04 | 가족신문 사진 — 최근 사진 100장 중 진짜 사진 | 기본 호출 `[self:photo]{}` **PARTIAL_SOURCE 실패**(total 60,979 중 50). 최근 100장 = 몸의 산출물 100/100, 기종 0·위치 0 | 결함 B81-3 · 재확인(B78-1) |
| T05 | 사진 날짜별 — 찍은 날로 묶기·그날만 | EXIF 현지 − `taken_at` = **9.0시간 396/396**, 시간대 표시 0, 날짜 라벨 다름 23. 하루 거르기 4일: 106 중 18·4 중 1·2 중 1·2 중 2 누락, 잘못 끼운 것 0 | 결함 B81-2 |
| T06 | 사진 장소별 — 좌표 0.1도 격자 | 396장 → 33칸(상위 120·49·44). check가 `$r.lat`에 UNOBSERVED_FIELD | 깨끗(F76-2 재확인) |
| T07 | kind 값 영역 — 사진/photos/image/audio/pdf | `"사진"`·`"photos"` → **0건 성공·메시지 없음**. `"audio"` → wav 30, `"pdf"` → pdf 30을 '사진'으로. check 5개 모두 경고 0 | 재확인(B79-2) |
| T08 | 사진 속 글자 읽기 — 정답을 아는 이미지 렌더 → `>> each image_read` | 렌더 PNG를 직접 열어 확인. OCR 정답 4/4(제목·날짜·인원·강의명). 반환은 `{success,message}` 자유 서술 | 깨끗 |
| T09 | 렌더 검수 비용 계층 — 빈 화면이면 비전 없이 실패 | prescreen "빈 화면(잉크 0.00%)", `prescreen_flagged:1`, critic 비전 생략. 단 `passed:false`·`tier:"prescreen"`은 **메시지 속 `verdict_json` 문자열**에만 | 결함 B81-5 |
| T10 | 블로그 최근 글 → 한 페이지 웹 | 설명이 가르친 `latest >> [self:read]{} >> [table:document]`는 check **invalid TYPE**(Record→Text). 명시 인자로는 11블록 HTML → 1280·390 렌더, 눈으로 봐도 정상. 글은 09-21 것 | 꼬임 F81-2(B80-4 재확인) |
| T11 | 유튜브 썸네일 1280x720 — 제목 + 로컬 그림 | 두 PNG를 열어 봄. base_path 없으면 **그림이 말없이 빠짐**(깨진 아이콘도 없음), prescreen "". `base_path:"/"`면 정상 | 재확인(B73-4 새 자리) |
| T12 | 산출물을 한 폴더에 — 같은 요청의 write·document·render 위치, render path 방언 | write·document → `projects/컨텐츠/outputs`, render → 루트 `outputs`. `~workspace/…`·워크스페이스 상대·프로젝트 상대 셋 다 `…/indiebizOS/backend/…` "파일이 없습니다" | 결함 B81-4(B73-6 재확인) |
| T13 | 분위기별 재생목록 — 장르·연도·mood·검색어 | `mood` → UNKNOWN_ARGUMENT(정직). 300곡 중 장르 빈칸 239·연도 빈칸 199. DB: genre 빈칸 2,611/8,087, 자유 표기 179종, year 전부 TEXT. `q:"잔잔"` 0·`q:"piano"` 36 | 불가 V81-1·마찰 F81-3 |
| T14 | 스크래치 재생목록 IT81_잔잔 — 만들고·3곡 담고(each)·없는 곡·중복 생성·읽고·지우기 | 3/3 담김·읽기 3·중복 생성 TOOL 거절·없는 곡 "라이브러리에 없는 곡입니다."·삭제. `playlists.json` 내용 해시 원상 | 깨끗 |
| T15 | 라디오 즐겨찾기 중 한국 방송사 채널 | 즐겨찾기 8 중 `station_id` 1(나머지 `stream_url`만). 한국 목록 12는 `station_id`만(stream_url 없음) → 이어짐 1. 순진한 필터는 MISSING_FIELD `details:{}`. 재생 상태 읽기: 꺼짐 | 꼬임 F81-4 |
| T16 | 소리 내는 동사·지우기 8쌍 — 부작용 사전 판정 | check effects 8쌍 **전부 읽기=쓰기 `["unknown"]`**. 옛 validate는 6쌍 정확, `web_site list`·`web snapshot`을 쓰기로 오판 | check · 재확인(B75-4) |
| T17 | 강의 자료 웹 컴포넌트 — 섹션 카탈로그·사이트·snapshot | hero 섹션 4·사이트 6·snapshot 7칸. 둘 다 `items` 없음(`categories`·`sites`), 같은 catalog가 kind마다 `total_count`/`total_sections`. continuation `read_calls:0, state_change_possible:true` | 꼬임(B75-4 새 차원) |
| T18 | 웹 만들기→빌드→배포 / 컴포넌트 설치 / 테마 (check) | 대부분 `incomplete`·effects `unknown`. **deploy `dry_run:true`는 UNKNOWN_ARGUMENT로 거절**(닫힌 계약 — 80회차 publish와 대조) | check |
| T19 | 매일 7시 라디오 켜기 / 매주 사진 모아 알림 (trigger check) | `incomplete`. 사진 트리거는 `LITERAL_DOLLAR`(do 안 프로그램을 문자열로 봄) | check(B75-4) |
| T20 | 노트 고치기→다시 굽기→영상/내보내기 (check) | 6문장 `incomplete`. 없는 slide_id·`engine:"qwen3"` 경고 0. export→render는 UNOBSERVED_FIELD | check |
| T21 | 코퍼스 — 축 14액션 380용례 판본 2 check | invalid 41(PIPE_COLLISION 28 — web build>>deploy, TYPE 29, UNKNOWN_ARGUMENT 5, SYNTAX 2). 액션별: web 13·render 10·sense:radio 9·image_read 8·music 6 | check(교재 드리프트 재확인) |

튼튼했던 것:
- 강의 로드 → 노트 필터 → `self:list` wav → anti join
- 한국어 HTML 렌더(글꼴·줄바꿈)와 모바일/데스크톱 두 뷰포트
- OCR 4/4
- 빈 화면 prescreen의 비전 생략(비용 계층화 설계대로)
- 재생목록 스크래치 왕복과 없는 곡·중복 생성 거절
- TTS의 모르는 engine·잘못된 rate 정직 실패(0바이트 파일 없음)
- 음악 `mood`·웹 deploy `dry_run`의 닫힌 계약 거절
- render·image_read 파이프 자리(B73-1 수리 확인)

실패는 두 자리에서 났다.
- **산출·판정 영수증이 평문이라 판본 2가 못 읽는 자리**다.
  - TTS 성공 → 실패로 뒤집힘(B81-1)
  - critic 판정 칸 → 문자열 안(B81-5)
- **사진 색인의 시각·범위가 사용자의 '그날'·'사진'과 다른 자리**다.
  - UTC 날짜(B81-2)
  - 몸의 산출물이 사진(B81-3)
  - limit 선택이 원천 절단(B78-1)

## 갭의 원장

### B81-1 ★ `engines:tts`가 판본 2에서 **파일을 만들고도 실패**한다 — 평문 성공 영수증이 `ADAPTER_SHAPE`로 거절된다 (★B74-5 속 세 번째 — 성공 평문 차원, 이관된 census 미집행)

- **요약**
  - `media_producer/handler.py` `create_tts`는 성공하면 `"\n".join(lines)` 평문을 돌려준다("TTS 생성 완료: <절대경로>\n길이: 10.3초\n엔진: edge / 음성: …").
  - `engines:tts`의 계약은 `legacy-envelope`(value_path "")다. `ibl_v2_adapters.decode_envelope`는 JSON이 아닌 문자열을 `text_success_prefix`가 선언된 경우에만 성공으로 받는다. 이 선언은 전체 원천에서 `self:edit`(`'Successfully edited '`) 하나뿐이다. 그래서 TTS 성공은 전부 `ADAPTER_SHAPE: 선언된 JSON 실행 봉투가 아닙니다`가 된다.
  - 효과(파일)는 이미 일어났다.
    - action_health는 success=1이다(방향이 B78-8의 반대: 기록은 맞고 판본 2가 틀림).
    - 판본 2 프로그램은 실패로 멈춘다.
    - `??`·catch·재시도가 **같은 합성을 다시 부른다**. 기본 엔진은 문자 수 과금 Gemini다.
  - 같은 핸들러의 `generate_ai_image`("AI 이미지 생성 완료: …")·`create_html_video`·`render_html_video`도 평문 성공이다(코드, 실행 안 함).
  - 경로가 문자열 안에만 있어서, 성공으로 받아도 `$t.path`로 다음 단계(`self:copy`·deck 나레이션 폴더)에 이을 수 없다.
- **최소 재현**: `[engines:tts]{text:"안녕하세요", engine:"edge", output_filename:"IT81_x.mp3"}` → 판본 2 `success:false`·`ADAPTER_SHAPE`, 그러나 `projects/컨텐츠/outputs/IT81_x.mp3` 존재
- **실측**(T02)
  - `evidence_summary.failures:[{action:"engines:tts", code:"ADAPTER_SHAPE"}]`
  - 파일은 mp3 24kHz 모노 10.30초, mean −17.5dB·max −4.3dB, −40dB 0.5초 이상 쉼 3(문장 경계)이다. 무음이 아니다. 훈련자는 귀로 듣지 못했으므로 길이·음량·쉼 구조로 판정했다.
  - action_health tts 5행: 정직 실패 4(success 0), 이 호출 1(success 1)
- **제안(수리성, ★밭 이관)**
  1. `create_tts`는 `{success, path, duration, engine, voice, ignored}` Record를 돌려준다. 같은 파일의 평문 성공 3자리도 같게 한다.
  2. **census**: `legacy-envelope` 어댑터 액션의 핸들러 반환을 AST로 전수 조사한다(평문 `return f"…"`/`"\n".join`). 평문 성공·평문 실패(B74-5) 모두 포함한다.
  3. 관문: "legacy-envelope 핸들러는 JSON 봉투 또는 선언된 `text_success_prefix`/`text_error_prefixes`만 낸다"를 빌드 `--check`에 넣는다.
  - 가드: tts edge 실행 → 판본 2 success·`path` 존재·파일 길이 > 0.

### B81-2 ★ `self:photo`의 `taken_at`은 **UTC인데 시간대 표시가 없다** — '그날' 사진 거르기에서 아침 사진이 빠지고 날짜 라벨이 전날이 된다

- **요약**
  - `file_index._item_from_meta`는 `mdls -plist`의 `kMDItemContentCreationDate`(plistlib가 **naive UTC** datetime으로 준다)를 `val.isoformat()`로 적는다(243행). 결과는 `"2019-06-30T01:30:00"`처럼 시간대 없는 문자열이고, `month = iso[:7]`이다.
  - 경계 `_iso_bound`는 `…T00:00:00Z`/`…T23:59:59Z`다(110~123행). 한국 기준 하루 거르기가 09:00~익일 09:00이 된다. (보고서 저장 전 두 자리를 직접 읽어 확인했다.)
  - 폰 몸의 `_mediastore_query`는 같은 인자를 `_epoch_ms`(`time.mktime`, **현지 자정**)로 해석한다. 같은 문장 `start:"2026-09-01"`이 맥과 폰에서 다른 순간을 뜻한다.
  - 닫힌 밭(날짜 **표기**)과 다르다. 적힌 문자열은 적법한 ISO지만, 값 코어는 naive 값을 현지/미상으로 취급하므로 생산자가 순간을 틀리게 넘긴 것이다.
- **최소 재현**: `[self:photo]{has_gps:true, limit:400}`의 `taken_at` vs 같은 파일 `sips -g creation`(EXIF 현지), 그리고 그 사진의 현지 날짜로 `start`/`end`를 준 하루 질의
- **실측**(T05, 격리 셸 대조)
  - 396장 전부 EXIF 현지 − `taken_at` = **+9.0시간**이다. 시간대 접미 0이다.
  - 날짜 라벨이 다른 사진은 23장(5.8%)이다. 이 표본에서 월 라벨이 다른 사진은 0이다(월말 새벽 사진이면 달도 틀린다).
  - 하루 거르기(날짜는 D0~D3으로 가림)
    - D0: 현지 106장 중 반환 88(18 누락)
    - D1: 4 중 3
    - D2: 2 중 1
    - D3: 2 중 **0**
    - 잘못 끼운 것 0(표본의 전날 저녁 사진이 has_gps 표본 밖이었을 뿐, 코드상 전날 15시 이후 사진이 끼어든다)
- **영향**: 가족신문 "나들이 날 사진", "이번 주 사진" 트리거(T19)는 사진이 적게 나오지만 성공이라 사람이 모른다. 타임라인 `groupby month`도 월말·월초 새벽 사진을 옮긴다.
- **제안(수리성)**
  1. plist datetime을 aware(`+00:00`)로 받아 현지 시각 + 오프셋(`2019-06-30T10:30:00+09:00`)으로 적는다. `month`는 현지 기준으로 만든다.
  2. 맥 `_iso_bound`를 폰과 같은 현지 자정으로 맞춘다. 두 몸이 하나의 해석기를 쓴다.
  3. 선언에 "촬영일 = 현지 시각"을 적는다.
  - 가드: EXIF 현지 시각을 아는 fixture 사진 → `taken_at` 오프셋 포함, 현지 날짜로 하루 질의 시 누락 0(맥·폰 경로 공통 함수 시험).
  - 값이 바뀌므로 저장 프로그램의 결과가 달라진다. 틀린 값이 맞는 값이 되는 쪽이라 수리성으로 본다.

### B81-3 `self:photo`의 '사진'은 **홈 아래 모든 이미지**다 — 최근 사진이 전부 몸의 산출물이다

- **요약**
  - `kind:"photo"`는 Spotlight `public.image` 전체다. 제외는 `_NOISE_SUBSTR`(설치 트리·캐시)뿐이라, 몸이 매일 만드는 차트·QA 렌더·보고서 PNG(`indiebizOS/outputs`·`projects/*/outputs`)가 촬영 사진과 섞인다.
  - 정렬은 "최근 수정 limit개 후보 안의 촬영일"이다(선언된 경고). 그래서 몸이 이미지를 만들수록 사진이 밀려난다.
  - 행에 '카메라 사진인가'를 말하는 칸이 없다(`camera` 빈 문자열로 추론할 뿐).
- **최소 재현**: `[try] { $p = [self:photo]{kind:"photo", limit:100}; $r = $p.items } [catch] { $r = $error.partial.items }` → 경로가 워크스페이스인 행 수
- **실측**
  - T04: 100/100이 워크스페이스 산출물이고 기종 0·위치 0이다.
  - 이 회차가 렌더한 PNG 8장이 몇 분 안에 `q:"IT81"` '사진'으로 잡혔다.
  - `has_gps:true`로 좁히면 396장 중 워크스페이스는 3이다(가족신문 업로드 사본).
- **제안(수리성)**
  1. 기본 범위에서 몸의 산출물 폴더(워크스페이스 `outputs/`·`projects/*/outputs/`·`data/`)를 뺀다. 필요하면 `path`로 명시한다.
  2. 행에 `origin:"camera|generated|screenshot"`(기종·EXIF 유무 기반)을 싣고 선언한다.
  - 가드: 렌더 직후 `kind:"photo"` 기본 질의에 그 렌더가 없어야 한다.

### B81-4 media_producer 산출물이 **산출 경로 단일 규약(J29-1) 밖**이다 — 폴더를 말없이 버리고, 같은 요청의 산출물이 두 곳에 떨어진다

- **요약**
  - J29-1 판정(2026-08-23)은 "주어진 경로는 지킨다, 해소기는 하나"다(`ToolContext.resolve_output_path`). 그런데 `media_producer`는 이 해소기를 쓰지 않는다.
    - tts는 `os.path.join(output_base, os.path.basename(output_filename))`다. 폴더를 **고지 없이** 버린다.
    - render는 `_out_stem`으로 파일명만 쓴다(선언 "파일명 stem").
  - `engines:render`·`image_read`는 노드 scope가 `workspace`다. 그래서 project_id가 있어도 산출은 루트 `outputs/`로 간다. 같은 요청의 `self:write`·`table:document`는 `projects/컨텐츠/outputs/`로 간다.
  - render `path`는 `os.path.abspath(src_path)`, 즉 백엔드 프로세스 cwd 기준이다. `~workspace` 펼침도 프로젝트·워크스페이스 기준도 없다(B73-6과 같은 뿌리의 새 자리).
  - 회귀 배터리 `test_emitter_output_path.py`는 emitter 3개(spreadsheet·document·chart)만 본다. 사람이 고른 스윕이 샌 자리다.
- **최소 재현**
  - `[engines:tts]{text:"안녕", engine:"edge", output_filename:"IT81_narr/a.mp3"}` → `outputs/a.mp3`
  - `$d=[table:document]{…filename:"x"}; [engines:render]{path:$d.path}` → 두 산출물이 다른 루트에
  - `[engines:render]{path:"~workspace/projects/컨텐츠/outputs/x.html"}` → "파일이 없습니다: …/indiebizOS/backend/~workspace/…"
- **실측**(T02·T12)
  - 위치: write·document `projects/컨텐츠/outputs`, render `outputs`
  - 방언 셋(`~workspace`·워크스페이스 상대·프로젝트 상대) 모두 `…/indiebizOS/backend/` 아래로 해석돼 실패했다.
  - 절대경로만 성공했다.
- **제안(수리성, ★밭 이관 — J29-1·B73-6)**
  1. tts·render·AI 이미지의 산출 경로를 `resolve_output_path`로 보낸다(폴더 존중, bare 이름은 프로젝트 outputs).
  2. 입력 `path`/`image_path`는 `context.resolve_path`(방언 펼침)로 받는다.
  3. census 관문: "패키지 핸들러의 `open(`/`save(`/`screenshot(path=`로 가는 산출 경로가 해소기를 거치는가", "입력 경로 키가 `resolve_path`를 거치는가"를 AST로 전수 검사한다(`check_field_path` 그물 확장).
  - scope workspace 액션의 산출 위치는 선언에 적거나 프로젝트 outputs로 통일한다.

### B81-5 `engines:image_read` critic의 선언 반환(`passed/score/issues/notes`)이 **메시지 문자열 안**에만 있다

- **요약**
  - operations 선언은 "critic — 의도 정합 채점 — passed/score/issues/notes"다. 실제 값은 `{success:true, message:"이미지 평가: …\n평가 결과: ✗ 실패 …\n\nverdict_json: {\"passed\": false, \"score\": 0, …, \"tier\": \"prescreen\"}"}`다.
  - 관측 반환도 `message`뿐이다.
  - render 설명이 권하는 "장별 critic → 통과 못한 장만 다시"(`[if: not $v.passed]`)를 칸으로 쓸 수 없고, 문자열을 쪼개야 한다(F77-1 속, 판정 영수증 자리).
- **최소 재현**: `$r=[engines:render]{html:"<html><body></body></html>"}; $r.items >> [table:each]{ [engines:image_read]{op:"critic", image_path:$it.path, intent:"표지", prescreen:$it.prescreen} }` → 행 칸이 `success`·`message`뿐
- **실측**(T09): `verdict_keys:["message","success"]`, 메시지 속 JSON을 꺼내면 `passed:false`·`score:0`·`tier:"prescreen"`이다(비전 호출 없음은 설계대로).
- **제안(수리성)**: critic은 verdict 칸을 최상위로 싣고, 표시 문구는 `message`로 남긴다. read도 `answer` 칸을 병기한다. fixture를 다시 돌려 관측 반환을 갱신한다.
  - 가드: prescreen·비전 두 경로 모두 `$v.passed` Bool.

### F81-1 `self:lecture` list의 주 컬렉션 `items`에 `lecture_id`가 없다

- T01: `items` 행은 `title·meta("일반인 · 88슬라이드")·summary:null·url:null`이다. `lecture_id·slide_count`는 옆 칸 `lectures`에만 있다. "단일 통화 items"대로 파이프하면 load로 잇지 못한다(77회차 F77-1의 같은 자리 재확인).
- load의 `items`(순번·slide_id·speaker_note…)는 관측 반환(list 모양 title/meta/…)과 달라 check가 UNOBSERVED_FIELD를 낸다(F76-2).
- 제안(수리성): 카드 행에 `lecture_id`·`slide_count`(정수)를 싣는다. op별 관측(`#load`)을 둔다.

### F81-2 **액션 설명이 판본 2에서 무효인 파이프를 가르친다** — 교재 표면에 설명 문자열이 빠져 있다

- T10: `self:blog` 설명의 발행 파이프 `[self:blog]{op:"latest"} >> [self:read]{} >> [table:document]{format:"html"}`가 check `invalid`·TYPE("Text가 필요하지만 Record입니다")다. latest 봉투를 path 자리에 흘린다.
- render 설명의 "`>> [table:each]` 로 장별 critic 심사 파이프 가능"을 그대로 쓴 코퍼스 4277·4278도 TYPE(Record → `.items` 필요)다.
- T21: 축 14액션 380용례 중 invalid 41이다.
  - web `build >> deploy` PIPE_COLLISION 28(같은 site_id 명시)
  - `sense:radio`·`self:music` 봉투를 `.items` 없이 take/sort 16
  - 옛 `where:{field,op,value}` 3
  - `desc:true` 1
- 설명은 모델이 describe로 읽는 **런타임 교재**다. 그런데 `check_retired_contracts`·코퍼스 용례 관문 어느 쪽도 설명 속 문장을 판본 2로 check하지 않는다.
- 제안(수리성): 빌드 `--check`에 "설명·target_description 속 IBL 조각(백틱·`>>` 포함)을 판본 2 check" 변을 넣고, 두 설명을 명시 인자형으로 고친다. 코퍼스 41건은 용례 재검토 대상에 올린다.

### F81-3 음악 '분위기'로 고를 칸이 없다 — 장르는 1/3이 비고 자유 표기, 연도는 문자열

- T13: `mood`는 UNKNOWN_ARGUMENT로 정직하게 거절된다.
- DB: genre 빈칸 2,611/8,087, 서로 다른 표기 179종(같은 장르의 한/영 표기 혼재), year는 전부 TEXT(빈칸 4,156), duration 0/NULL 52다. `q:"잔잔"` 0건이다.
- "잔잔한 곡 재생목록"은 지금 어휘로 장르 문자열·검색어 우회뿐이다.
- 제안(수리성): year를 정수(또는 null)로 싣고, genre 정규화(표기 사전)는 선택한다. 분위기 자체는 V81-1이다.

### F81-4 라디오 즐겨찾기와 방송사 목록을 이을 열쇠가 없다

- T15: 즐겨찾기 8개 중 7개가 `stream_url`만 있고 `station_id`가 없다. `sense:radio korean` 12행은 `station_id`만 있고 `stream_url`이 없다. 그래서 "즐겨찾기 중 KBS 채널"은 1개만 이어진다.
- 순진한 `$r.station_id != ""` 필터는 MISSING_FIELD이고 `details:{}`(어느 행인지 없음 — F72-2)다.
- 제안(수리성): 즐겨찾기 add 때 `station_id`를 역조회해 채우거나, korean 행에 `stream_url`을 싣는다(F76-1 식별자 칸 census 항목).

### V81-1 (후보) 음악의 분위기·빠르기 칸

- "분위기별 재생목록"은 사용자 음악 계기의 자연스러운 요구다. 태그에는 없는 축이다(BPM·에너지는 오디오 분석으로만 나온다).
- **어휘 신설은 제안하지 않는다.** `self:music` 행의 선택 칸으로 둘지(스캔 때 분석)는 현실 반복이 인준할 일이다. 2026-07-28 은퇴한 AI 선곡(`compose`)을 되살리자는 뜻이 아니다.

## 재확인 (앞 회차 갭·수리의 증거 — 새 항목 아님)

- **B78-1**(의도한 선택의 원천 절단 오분류) — **가장 강한 증거**
  - `[self:photo]{}` 기본 호출(limit 50)이 total 60,979 중 50행이라 **항상 PARTIAL_SOURCE 실패**다(T04). limit은 선언된 사용자 선택인데, 홈에 사진이 limit보다 많으면 모든 사진 질의가 판본 2에서 실패한다.
  - 같은 창의 형제 `self:music` limit 300은 count 300으로 무표지 성공한다. 같은 "limit 선택"이 형제마다 반대로 번역된다.
  - 이관된 census에 생산자(`file_index` 전 경로)를 추가한다.
- **B79-2**(원천 인자 값 영역 침묵)
  - `self:photo` kind: `"사진"`·`"photos"` → 0건 성공·메시지 없음. 코드상 content-type 절이 없는 `kMDItemFSName == '*'` 질의가 되고, 실측은 0이다.
  - `"audio"`·`"pdf"` → wav·pdf를 사진으로 준다. 선언은 photo/video/all이다.
  - tts `engine`에 enum 선언이 없어 check 경고 0이다(실행은 정직하게 거절).
  - voice `"kkj3"`만 주면 Gemini로 넘어가 서버 오류에 맡겨진다(코드, 실행 안 함).
  - deck video `engine:"qwen3"`도 check 경고 0이다.
- **B73-4**(로컬 그림이 렌더에서 빠짐) — 새 자리: `engines:render` html 문자열
  - base_path 없이 절대경로 `<img>`를 주면 그림이 **말없이 사라지고**(깨진 아이콘도 없음) prescreen이 ""(깨끗)이다(T11, 훈련자가 PNG로 확인).
  - `base_path:"/"`면 실린다. 0층 관측(`requestfailed`)이 about:blank 출처의 파일 그림 실패를 못 본다.
- **B73-6**(`~workspace` 미펼침): `engines:render` `path`(T12). 상대경로는 백엔드 cwd 기준이다(B81-4).
- **B75-4**(check의 액션별 사전 판정 부재)
  - 읽기/쓰기 8쌍의 check effects가 전부 같은 `["unknown"]`이다(T16): radio status/play, music queue/play, music playlists/stop, radio_favorite list/remove, music library/playlist_delete, web_site list/remove, lecture list/delete, web snapshot/deploy.
  - 옛 validate는 6쌍을 맞히고, **`web_site list`·`web snapshot`을 쓰기로 오판**했다. 옛 판정도 정본이 될 수 없다.
  - **새 차원**: continuation이 web snapshot·catalog 읽기를 `read_calls:0, state_change_possible:true`로 적는다(T17). effects를 모르면 증분 실행 `reuse`가 읽기 영수증을 재사용하지 못한다.
- **B78-8**(건강 원장과 판본 2 판정 불일치)
  - `self:photo` 44행이 전부 success=1인데, 그중 판본 2 PARTIAL_SOURCE 실패가 다수다.
  - tts는 반대로 health 1·판본 2 실패다(B81-1).
- **F76-2**(관측 반환의 변이 축 부족)
  - `self:photo` 설명은 lat/lng를 말하는데 관측 반환에 없어서 `$r.lat`가 UNOBSERVED_FIELD다(T06). lat/lng는 좌표가 있는 행에만 붙는 칸이다.
  - lecture load 행, deck export `path`도 같다.
- **F72-2**(진단 안내 부족): FIELD_TYPE·MISSING_FIELD `details:{}`(탐색·T15).
- **F77-1**(구조가 표시 문자열에만): lecture list `meta`의 슬라이드 수, TTS 영수증 경로(B81-1), critic 판정(B81-5).
- **B80-4**(블로그 로컬 사본의 "최근 글"): latest가 여전히 09-21 글이다(T10).
- **B73-1 수리 확인**: `render >> image_read`·`document >> render` 파이프 check가 `incomplete`(PIPE_COLLISION 없음)이고 실행도 된다(T08). 다만 render 봉투를 each로 넘기려면 `.items`가 필요하다(F81-2).
- **F78-2 대조**: web deploy `dry_run:true`는 UNKNOWN_ARGUMENT로 **거절**된다(T18, 닫힌 계약). 80회차 `others:publish`의 침묵과 대비되는, 닫힌 계약이 맞게 일한 자리다.

## 시드 후보 (실행 검증 통과만 — 자동 등록 안 함)

- T01(lecture list → `.lectures` each load → 노트 있는 장 filter → `self:list` narration wav → compute slide_id → join anti → 구울 장 수). 강의 id는 자리표로 바꿔 심을 것.
- T14(playlist_create → 검색 결과 each playlist_add → playlist 읽기). 스크래치 삭제 단계는 빼고 심을 것.

**빼는 것**:
- T02: B81-1
- T04·T05·T07: B81-2·3, B78-1
- T06: F76-2 경고
- T08·T09: 비전·prescreen 문자열 판정(B81-5)
- T10: F81-2
- T11: B73-4
- T12: B81-4
- T13·T15: F81-3·4
- T16~T21: check
- 코퍼스 invalid 41건(4277·4278 포함)과 blog·render 설명 속 파이프는 용례·설명 재검토 대상이다.

## 판정 요청 (언어 개정·파괴적 변경 2종만)

**0건.**
- B81-2는 사진 촬영일 값이 바뀐다(틀린 UTC → 맞는 현지 시각+오프셋). 저장 프로그램의 결과가 달라지지만 틀린 값을 맞게 하는 쪽이라 수리성으로 봤다.
- B81-3의 기본 범위 축소는 `path` 명시로 옛 동작을 되찾을 수 있다.
- V81-1은 어휘 후보일 뿐이다(현실 반복이 인준).

**다음 수리 턴의 첫 항목(밭 이관·census)**:
1. B81-1(+B74-5): `legacy-envelope` 핸들러 평문 반환 census + 관문. tts·AI 이미지·HTML 영상은 Record 영수증으로 바꾼다.
2. B78-1: `file_index` limit 선택을 원천 절단으로 번역하는 자리 + 형제(music 무표지)와 한 규약으로 맞춘다.
3. B81-4(+B73-6): 패키지 핸들러 산출·입력 경로가 `resolve_output_path`/`resolve_path`를 거치는지 AST census(`test_emitter_output_path` 3개 → 전수).
4. B81-2: 생산자 datetime aware 관문. 몸 간 날짜 경계 해석기를 하나로 만든다.

## 72~81회차 공통 뿌리에 81회차가 더하는 것 (훈련자 관찰)

- **상태 칸의 번역기가 한 벌이 아니다**(78회차 관찰)는 이번에 **반대 방향**으로 났다.
  - 78·80에서는 실패가 성공으로 적혔다. 이번에는 **성공이 실패로** 뒤집혔다. 핸들러·파일·건강 원장은 성공인데 판본 2 어댑터만 평문을 못 읽었다(B81-1).
  - 같은 limit 선택이 사진에서는 원천 절단 실패, 음악에서는 무표지 성공이다.
  - 번역 규칙이 액션 옆 선언(`text_success_prefix`)에 흩어져 있고, 그 선언을 한 액션은 하나뿐이다.
- **'사용자의 뜻'과 '몸의 기록'의 좌표계가 다르다**(79·80의 "선언이 말하지 않는 기본값·이름"의 새 모양).
  - 사진의 '그날'은 UTC 날이다(B81-2).
  - '사진'은 모든 이미지다(B81-3).
  - '산출 폴더'는 파일명뿐이다(B81-4).
  - 셋 다 success이고, 해석을 말하는 칸이 없다.
  - 두 몸(맥·폰)이 같은 인자를 다르게 해석하는 것은 이 뿌리가 **몸 경계**까지 간다는 증거다.
- **액션 설명도 교재다.** "교재 수리는 표면 전수"(§4-3)의 표면 목록에 describe가 돌려주는 description·target_description이 빠져 있다. 빌드 `--check`가 파생물·문서 마커는 대조하면서 설명 속 IBL 조각은 판본 2로 check하지 않는다(F81-2).
- **수리의 누출은 또 형제 패키지에서 났다.**
  - J29-1 해소기 → media_producer
  - B73-6 `~workspace` → render
  - B78-1 → file_index
  - B73-1 파이프 자리는 이번에 render·image_read까지 닫힌 것을 확인했다. census로 닫은 부류는 형제까지 닫혔고, 사람이 고른 스윕은 샜다는 대조다.

## 위생

- **기준선**: 탐침 전 03:29:48에 떴다([baseline.json](baseline.json)).
  - action_health max id 244743, notify_log 6261, 알림함 3통
  - 재생목록·음악 소스·스캔 상태·라디오 즐겨찾기·웹 사이트 레지스트리·목소리 원장 해시
  - 두 outputs 목록(개수+해시로 축약), 강의 트리, 음악 라이브러리 8,087곡, usb 캐시, 코퍼스 3,735, episode_log 4142
- **회차 후 diff**
  - action_health 새 행 중 training 181, **전부 `training`/agent**다.
  - 같은 창의 usage 33행(`self:edit`·`list`·`read`·`time`·scheduler `others:delegate`)·알림 3통("스케줄 위임 접수")·notify_log 3건·episode_log 3건은 **03:30 주간 재조사 스케줄**(cctv·편집인·광대)이 남긴 것이다. 탐침은 이 액션들을 부르지 않았다.
  - `playlists.json`: 내용 해시 동일, mtime만 바뀜(스크래치 생성·삭제의 재기록)
  - 나머지 저장소 불변: 즐겨찾기·사이트 레지스트리·목소리 원장·강의 트리·음악 라이브러리·코퍼스
- **스크래치**
  - `IT81_*` 14개를 `probe.py clean`으로 삭제했다. 프로젝트 outputs 6(html 3·txt 2·mp3 1), 루트 outputs 8(png)이다.
  - 두 outputs 목록은 기준선과 같다(diff 0).
  - `IT81_narr/` 폴더는 만들어지지 않았다(B81-4). `/tmp/IT81`은 check 문장 안에서만 썼다.
  - 스크래치패드의 describe 사본·대조 스크립트, 탐침 폴더의 `__pycache__`는 정리했다.
  - baseline.json의 파일명 목록을 축약했으므로 `probe.py clean/after`를 다시 쓰려면 기준선을 새로 떠야 한다.
- **호출**
  - 유료·외부 AI: 비전 1(image_read read, OCR)
  - TTS: edge 1(무과금 네트워크), Gemini 0
  - 라디오: `sense:radio korean` 3, 재생 0
  - 로컬: Spotlight/mdls(사진 44), 렌더 약 18, web snapshot·catalog, 강의 22, 음악 14
  - 검사: check 약 440(코퍼스 380 포함), `/ibl/validate` 16
  - 셸 대조: `sips` 약 800, `ffprobe`/`ffmpeg` 3
  - 재생·배포·발행·발신 0, 해마 시딩 0
- **사용자 데이터 무손상**
  - 사진·음악은 읽기만 했다. 즐겨찾기·사이트·강의·노트는 변경 0이다.
  - before.json에 사진 경로·파일명·기종·좌표, 곡 제목·아티스트·경로가 0건임을 패턴 검사로 확인했다.
- **나머지**: 라이브 코어 편집 0 · 커밋 0
- **백엔드**: 회차 내내 `state.json` phase `ACTIVE`(`last_result.outcome: restarted`), 재기동·FAILED 없음.

## 집행 완료

2026-09-29 후속 수리: [잔여 수리 및 검증 보고서](../../IMAGINATION_81_REMAINING_REPAIRS_2026_09_29.md).

B81-3 기본 사진 범위, F81-1 op별 관측, F81-2 교재, F81-3 연도, F81-4 라디오 연결 키를 반영했다. 깨진 이미지 prescreen·enum 사전 검사·행 오류·웹 items도 보완했다. 교재 55건을 이력 보존하여 수정했고, 관련 397건의 정적 오류는 0건이다. 대역 실행 165개와 최종 관련 회귀 146개가 통과했다. 전체 회귀의 원장 검사 실패 1개는 최종 묶음에서 재검증했다.

기본 사진 조회의 실제 20,000개 후보 상한, 분위기 분석 후보, 전 패키지 AST 전수 감사·설명 자동 관문의 미구현은 위 보고서에 구분했다. 훈련 당시 21과제를 전부 다시 실행한 것으로 해석하지 않는다.
