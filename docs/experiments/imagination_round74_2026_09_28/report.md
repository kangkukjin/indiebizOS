# 상상 훈련 74회차 결과보고서 (2026-09-28) — 파일·폴더 업무: 목록·복사·폴더 생성·삭제·폴더 메모·용량·읽기

훈련 턴 · **무수정**(가이드 §4-3: 훈련 턴은 라이브 코어를 고치지 않는다). 아래 갭 원장은 [before.json](before.json)·[isolation.json](isolation.json)과 셸로 직접 확인한 디스크 상태만으로 썼다. 집행 완료 절은 비워 두었다.

## 축 선정

- 축 = 행동 기준 미조합 메뉴의 `self:list`·`self:copy`·`self:mkdir`·`self:delete`·`self:folder_note`·`self:storage`·`self:read`·`self:write`, 그리고 `table:filter/sort/groupby/each`와의 조합이다. 도메인:
  - 다운로드 폴더 정리(오래된 파일·큰 파일·설치파일 삭제)
  - 강의 자료를 주차별 폴더로 정리
  - 사진·문서 백업 복사
  - 프로젝트 폴더 용량, 폴더 메모
  - 중복 파일·빈 폴더·숨김 파일·NFD 한글 이름·공백/특수문자 경로
- 73회차 단서("`self:read`가 pptx를 읽으면 원본 옆에 `<stem>_images/`를 만든다")를 이 축에서 따졌다. 결과는 B74-2다. 그 쓰기 때문에 읽기 전용 폴더에서는 **읽기가 실패**한다.
- 축 선정 관문 질문("기계로 열거 가능한가"): 조합 자체는 열거할 수 없다. 다만 발견 가운데 둘이 이전 회차와 같은 속이다. 읽기 op의 쓰기(B72-5 → B74-2), 평문 실패의 어댑터 오분류(B56-3 → B74-5). 둘 다 census로 넘기라고 적었다.
- 닫힌 밭(값 표기·날짜 표기·동시성·절단 표지)은 밟지 않았다. `file_find` 200건 상한은 `PARTIAL_SOURCE`로 정직하게 실패했다(확인만 했고 결함 아님). NFD 한글(B67-4 수리 표면)은 list `pattern`과 `contains` 둘 다 정상이었다.
- 탐침 표면: 모델 경로(`agent_id:"IT74_probe"`·`task_id:"IT74_task"`). 모든 요청이 `edition:2`·`project_id:"컨텐츠"`·`origin:"training"`이다.
- ★**쓰기·삭제·복사·폴더 생성은 스크래치 트리(`outputs/IT74_tree`·`IT74_backup`·`IT74_x`·`IT74_y`)에서만** 했다. `self:delete`는 선언상 **영구 삭제**("휴지통 거치지 않음")라 스크래치 경로에만 썼다. 사용자 실제 폴더는 `~/Downloads` list 읽기만 했고, 보고서에 파일 이름을 싣지 않았다.
- ★`self:storage` scan·`self:folder_note` set은 저장소 색인(`data/packages/storage_scans`)에 볼륨을 더한다. 그래서 스크래치 경로만 스캔했고, 끝마다 앱 자신의 REST(`DELETE /pcmanager/analyze/scan/{id}`)로 그 볼륨만 지웠다. 사용자 볼륨(`/`·외장)의 주석 DB에는 쓰지 않았다(정확 일치가 없어 쓰기가 일어나지 않는 오류 경로만 실측).

## 지표 스냅샷 (훈련 전)

행동 미조합 140/168 · 파이프 길이 중앙값 3 · 문형 4(조회 26·축적 8·적용 6·조건 2, 시간·발신 0) · 파트너 다양성 중앙값 2. 73회차와 같다. 원본은 [metrics.json](metrics.json). 지표는 몸의 현황이며 훈련 실측은 증류에 담기지 않는다(§6).

## 과제 표

원문·판정식: [probe.py](probe.py) · 응답 전량: [before.json](before.json) · 격리 재현: [isolate.py](isolate.py)·[isolation.json](isolation.json).

**24과제 중 기계 판정 18통과 · 6실패.** 판독으로 T13을 꼬임, T17을 결함으로 더했다(결함 6부류 · 마찰 2부류 · 어휘 후보 2). 실행 23 · check만 1(T15). 격리 재현 12건(I1~I12)은 탐침 밖에서 결함과 훈련자 잘못을 가르려고 찍었다.

탐색 중 훈련자 문장 잘못은 결함 판정에서 뺐다.
- `len([self:list]{…})`처럼 내장 함수 인자 안에 도구 호출을 넣었다(`PURE_EXPRESSION` — 교재 "그 안의 호출은 먼저 변수에 받는다"). 4과제에서 났다.
- groupby 집계에 없는 `list`를 썼다(오류가 가능 목록 `avg/count/max/min/sum`을 알려 줌).
- 기대 개수를 잘못 셌다(다운로드 11개·숨김 제외 파일 8개).

고쳐서 다시 찍었다.

| # | 상상 의도 | 결과 | 분류 |
| --- | --- | --- | --- |
| T01 | 다운로드 폴더 목록 — 폴더 먼저, 이름순 | 11개. `sort by name` → `sort by is_dir desc` 2단 안정 정렬로 `empty_dir, nested` 먼저. **list 원래 순서는 무정렬**(`설치파일.dmg, big_video.mp4, old_report.pdf, empty_dir, …`). `sorted($l, ($r)=>[!$r.is_dir, $r.name])`은 `UNORDERED` | 깨끗(F74-1) |
| T02 | 한 달 넘게 안 건드린 파일만 (filter `mtime < "2026-08-28"`) | `old_report.pdf`·`설치파일.dmg` | 깨끗 |
| T03 | 가장 큰 파일 3개 | `big_video.mp4` 5,000,000 · `설치파일.dmg` 2,000,000 · `report_v2.pdf` 4,013 | 깨끗 |
| T04 | (사용자 `~/Downloads`, 읽기만) 큰 파일 5개 크기 | 내림차순 5건, 이름 미수록 | 깨끗 |
| T05 | '강의' 든 파일 — NFD로 저장된 한글 이름 | `pattern:"*강의*"` 1건·`contains` 1건, 반환 경로는 NFD 원형 보존·실존 | 깨끗 |
| T06 | 숨김 파일 빼고 파일 수 (`$r.name[0:1] != "."`) | 파일 8 · 숨김 1 | 깨끗 |
| T07 | 확장자별 개수·용량 (compute `split`/`lower` → groupby) | pdf 4건 15,051 · mp4 · dmg · txt … | 깨끗 |
| T08 | 강의 자료를 `N주차/` 폴더로 정리 (each 안 mkdir → copy) | 디스크 `1주차/1주차_개요.pptx · 2주차/… · 3주차/(과제.docx, 참고.txt)` 정확. 처리 순서는 list 순서(무정렬) | 깨끗 |
| T09 | 주차 폴더별 파일 수 (each 안 list → len) | 1·1·2 | 깨끗 |
| T10 | 사진 폴더를 기존 백업 폴더로 복사 — 백업에만 있던 옛 사진 유지 | **백업 전용 `IMG_0000_only_in_backup.jpg` 영구 소실**, 응답 "폴더를 복사했습니다 (2개 파일)" success | 결함 B74-1 |
| T11 | 같은 이름 파일을 백업에 — "(2)"로 피하기(선언) | **백업의 `OLD BACKUP CONTENT`가 새 내용으로 덮임**, 형제 파일 없음, success | 결함 B74-1 |
| T12 | 공백·특수문자·한글 폴더로 복사 후 되읽기 | `백업 폴더 (9월)/메모 & 목록.txt` → `공백과 특수문자` | 깨끗 |
| T13 | 중복 파일 찾기 (size groupby → n>1 크기 → `intersection` 필터) | `report (1).pdf · report.pdf · report_v2.pdf` — **v2는 크기만 같은 다른 파일**, 내용 대조 수단 없음 | 꼬임 V74-2 |
| T14 | 빈 폴더 찾기 (file_find → each list → len 0) | `deep_empty`·`empty_dir` | 깨끗 |
| T15 | 1GB 넘는 파일 있으면 알림 (check) | `incomplete`, 이슈 0 | 검수만 |
| T16 | (스크래치) 한 달 넘은 .dmg만 삭제하고 목록 보고 (each delete) | `deleted:["설치파일.dmg"]`, 디스크에서 사라짐, 남은 dmg 0 | 깨끗 |
| T17 | 이미 없는 파일 삭제 — `missing_ok` / 그냥 | missing_ok "이미 없습니다" success. 그냥은 **`선언된 JSON 실행 봉투가 아닙니다: Error: 경로가 존재하지 않습니다`**, `$error.code`=`ADAPTER_SHAPE`(I5) | 결함 B74-5 |
| T18 | 강의 pptx·docx 내용만 읽기 — 폴더에 새 폴더 생기면 안 됨, 읽기 전용 폴더도 | **`1주차_개요_images/`·`3주차_과제_images/` 생성**. `extract_images:false`면 생성 0. **읽기 전용 폴더 pptx = `[Errno 13] Permission denied: …/외부강의_images`**(false면 성공). docx `~workspace` = not found | 결함 B74-2(+B73-6) |
| T19 | 폴더 목록을 `INDEX.md`로 써서 그 폴더에 두기 → 되읽기 | 디스크·되읽기 일치 | 깨끗 |
| T20 | mkdir 경계 — 있는 폴더·파일과 같은 이름·중첩 한글 공백 | `existed:true` · "같은 이름의 파일이 이미 있습니다" · 중첩 생성 | 깨끗(F74-2 별도) |
| T21 | 없는 폴더·파일 경로를 list | `[Errno 2] …`/`[Errno 20] Not a directory` — `TOOL`+`details.error_type:not_found`·hint | 깨끗(정직 실패) |
| T22 | 프로젝트 폴더 용량 — 하위 폴더별 (scan → summary) | 확장자 표만(**폴더 열 없음**), 25종 중 **20행**. 하위 폴더 summary = "**이 경로를 품은 스캔 볼륨이 없습니다 … 상위 폴더를 스캔**" | 결함 B74-3(+B72-3) |
| T23 | 폴더 메모 달고 확인 (set → 재set → detail) | 저장 `folder_path`가 **`~workspace/…` 원문 토큰**, 개정은 누적 2행, **없는 폴더에도 success**, 하위 경로 root는 B74-3 거짓 문구 | 결함 B74-4 |
| T24 | PDF만 골라 백업으로 — `… >> [self:copy]{dest}` | `PIPE_COLLISION`(안내 반대 방향). each + 명시 src/dest 우회는 4건 성공 | 결함 B73-1 재확인 |

목록 → filter/sort/groupby/each 조합은 튼튼했다. 여기에는 mtime 문자열 비교, NFD 이름, 숨김 슬라이스, 확장자 집계, 주차 정리, 빈 폴더, 2단 정렬, mkdir 멱등, write 색인, 없는 경로의 정직 실패가 들어간다. 실패는 두 자리에서 났다. 하나는 **파일 동사가 대상 경로를 다루는 방식**이다(복사·이동이 대상부터 지운다, 읽기가 원본 옆에 쓴다). 다른 하나는 **용량 색인·폴더 메모의 경로 계약**이다(정확 일치, 원문 토큰 저장, 거짓 안내).

## 갭의 원장

### B74-1 ★최우선 — `self:copy`(와 `self:move`)가 명시 경로에서 **대상부터 지운다** — 백업이 사라지고, 겹치는 경로면 원본이 영구 삭제된다

- **요약**: `copy_path`의 명시 src/dest 가지가 대상부터 지운다.
  - 폴더: `if os.path.exists(dst): shutil.rmtree(dst)` 뒤 `copytree` (`system_essentials/handler.py` 1170~1173행, 주석 "대상이 이미 있으면 삭제 후 복사").
  - 파일: `shutil.copy2(src, dst)`로 덮어쓴다(1178행).
  - `move_path`도 `rmtree(dst)`/`os.remove(dst)` 뒤 `shutil.move`다(1242~1249행).
  - 반면 **같은 동사의 파이프 가지**(`copy_ops` → `file_index.save_media_files`)는 "이름이 겹치면 "(2)" — 덮어쓰기는 사용자가 원한 적 없는 삭제다"를 지킨다.
  - 선언 target_description은 "이름 충돌은 "(2)"로 피하고 덮어쓰지 않는다"이고, description은 "복사 (원본 유지)"다. 대상 삭제는 어디에도 없다.
  - (보고서 저장 전 위 행 번호의 코드를 직접 읽어 확인했다.)
- **최소 재현**(스크래치):
  1. `[self:copy]{src:"<앨범>", dest:"<같은 앨범의 다른 표기>"}` — `~workspace/…` 대 절대경로
  2. `[self:copy]{src:"<앨범>/2026", dest:"<앨범>"}`
  3. 기존 `백업/사진`(원본에 없는 사진 1장 포함)에 `[self:copy]{src:"<사진>", dest:"<백업>/사진"}`
- **실측**:
  - T10: 백업 전 `['IMG_0000_only_in_backup.jpg']` → 후 `['IMG_0001.jpg','IMG_0002.jpg']`. 응답 `{"success":true,"message":"폴더를 복사했습니다: …/IT74_backup/사진 (2개 파일)"}` — 지운 파일은 말하지 않는다.
  - T11: 백업 `report.pdf`의 `OLD BACKUP CONTENT`가 `%PDF-1.4 same…`으로 바뀌었고 `report (2).pdf`는 없다.
  - I4: 파일을 기존 폴더로 복사하면 `bk/c.txt`가 `OLD`→`NEW`로 덮이고, 응답은 폴더 경로만 말한다.
  - **I1(src==dest 다른 표기)·I2(dest=조상)**: 실행 뒤 `outputs/IT74_x/` 아래가 **비었다**. `앨범/a.jpg`처럼 src가 아닌 파일까지 사라졌다. 응답은 `success:false`, `ADAPTER_SHAPE: … Error: [Errno 2] No such file or directory: '…/앨범'`뿐이다. 먼저 `rmtree(dst)`가 원본(또는 원본을 품은 조상)을 지우고, 이어 `copytree(src)`가 없는 원본에서 실패한 것이다.
  - **I3**: `self:move`로 같은 형태를 주면 결과가 같다(조상 폴더 영구 소실).
  - 판본 2 check는 넷 다 `incomplete`·이슈 0이다.
- **영향**: "사진·문서를 백업 폴더로 복사"는 이 축의 대표 과제다. 두 번째 백업부터 이전 백업에만 있던 파일(폰에서 지운 사진 등)이 조용히 사라진다. `shell_shadow`가 `cp` → `self:copy`로 대응시키는데, `cp -r src 있는폴더`는 그 안에 넣는 비파괴 동작이라 셸 직관과 정반대다. 표기만 다른 같은 경로나 상위 폴더를 dest로 잘못 준 한 번의 실수가 **휴지통도 거치지 않는 영구 삭제**가 된다. 게다가 실패 문구는 "원본이 없다"로 보여 원인을 가린다.
- **뿌리**: 명시 경로 가지가 "대상 = 교체할 것"으로 짜였다(mirror 의미). 반면 파이프 가지와 선언은 비파괴 계약이다. 같은 동사 안에 충돌 정책이 둘이다. src/dest의 실경로 겹침(같음·조상·자손) 검사도 없다.
- **제안(수리성)**:
  1. copy/move는 실경로(`realpath`, NFC)로 src/dest 겹침(같음·조상·자손)을 **실행 전 거절**한다.
  2. 폴더 복사 대상이 이미 있으면 교체가 아니라 **병합**한다. 충돌 파일은 파이프 가지와 같은 `(2)`로 피한다. 파일 복사도 같다. 교체가 필요하면 기존 표현(`[self:delete]` 뒤 copy — 코퍼스 3202가 이 형태)을 쓰면 되므로 새 인자는 필요 없다.
  3. 영수증에 만든 경로·충돌로 바꾼 이름을 싣고, 지운 것이 있으면 반드시 신고한다.
  4. 관문: 패키지·backend에서 사용자 경로에 대한 `shutil.rmtree`/`os.remove`는 `delete_path`만 허용한다(AST). 이번 조사로 copy·move 두 자리가 확인됐다.
  - 가드: {파일, 폴더} × {대상 없음, 대상 있음, src==dest 이표기, dest=조상, dest=자손} × {copy, move} → 디스크 대조.

### B74-2 `self:read`가 원본 옆에 `<stem>_images/`를 **쓴다** — 읽기 전용 폴더에서는 읽기가 실패한다 (★밭 이관: B72-5와 같은 속의 두 번째)

- **요약**: `read_docx`(office_ops)와 `read_pptx`·`read_hwp`·`read_hwpx`·`read_epub`(doc_read_extra `_save_images`)는 `extract_images` 기본값이 True다. 그림이 있으면 `path.parent / f"{stem}_images"`를 `mkdir`하고 그림을 쓴다. 판본 2 계약은 `effects: [read_external]`이다. 선언 설명도 "pptx — … 이미지는 extract_images"라고만 하고, 원본 폴더에 쓴다는 말이 없다.
- **최소 재현**: `$x = [self:read]{path:"<그림 있는 pptx>"}` → `ls <폴더>`
- **실측**:
  - T18: `강의자료/`에 `1주차_개요_images/`·`3주차_과제_images/`가 새로 생겼다. `extract_images:false`면 생성 0이다.
  - 읽기 전용(0555) 폴더의 pptx: `[Errno 13] Permission denied: '…/공유드라이브_읽기전용/외부강의_images'`로 **실패**. 같은 파일을 `extract_images:false`로 읽으면 본문 14자로 성공한다.
- **영향**:
  - 읽기가 사용자 폴더를 바꾼다. 강의 자료 폴더를 읽고 나서 list하면 `_images` 폴더가 섞이고, 주차 정리·개수 세기·백업 대상에 끼어든다.
  - 공유 드라이브·외장·남의 계정 폴더 같은 쓰기 불가 위치의 슬라이드는 **읽지도 못한다**.
  - 효과 계약이 읽기라서 읽기 영수증 재사용·병렬 쓰기 충돌 검사·"부작용 없음" 판단이 모두 이 쓰기를 모른다.
  - 같은 이름 폴더가 이미 있으면 `mkdir(exist_ok=True)` 뒤 같은 이름 그림(`image1.png`·`slide_img_1.png`)을 덮어쓴다.
- **뿌리**: B72-5(없는 주체 조회가 `owners`에 행 삽입 — 읽기 op의 쓰기)와 같은 속이다. "읽기로 선언된 op가 쓴다"를 보는 관문이 없다.
- **제안(수리성, ★밭 이관)**:
  1. 읽기의 그림 추출은 원본 옆이 아니라 파생 캐시(예: `outputs/`나 실행 산출 폴더)에 쓰고 경로를 `saved_path`로 싣는다. 또는 기본값을 끄고 명시할 때만 쓴다. 코퍼스는 옆 폴더 경로에 기대는 문장이 0건이고, 있는 두 건(2033·2034)은 `extract_images:false`다.
  2. 추출 실패(권한)는 본문 읽기를 실패시키지 않고 `images_failed`로 신고한다.
  3. census: `side_effect:false`·`effects: read_external`로 선언된 op 전수에서 쓰기 호출(`mkdir`·`open(…,'w')`·`INSERT`·`write_*`)을 AST로 찾아 목록화하고, 빌드 `--check`에 "읽기 선언 ⇒ 쓰기 호출 없음" 관문을 둔다.
  - 가드: {docx, pptx, hwp, hwpx, epub} × {쓰기 가능, 읽기 전용 폴더} → 원본 폴더 불변·본문 성공.

### B74-3 `self:storage` — 선언된 폴더 롤업이 없고, 하위 경로에 거짓 안내를 하며, 스캔은 한 자리 오류에 전체가 실패한다

- **요약**:
  - ① summary는 `SELECT extension … GROUP BY extension ORDER BY total_size DESC LIMIT 20`뿐이다. 선언("폴더·확장자별 용량 집계", "디렉토리 크기 롤업")과 달리 **폴더 열이 없다**. 폴더별 집계는 앱 REST `/pcmanager/analyze/folders`에만 있고 IBL에는 없다.
  - ② `get_summary`·`add_annotation`은 `root_path`가 스캔 루트와 **정확히 같을 때만** 찾는다. 실패하면 "**이 경로를 품은** 스캔 볼륨이 없습니다 … **상위 폴더를 스캔**한 뒤…"라고 말한다. 상위 폴더가 이미 스캔돼 있어도 같은 문구다. 사용자 색인에는 `/` 볼륨이 있어 모든 로컬 경로를 품는다.
  - ③ `_scan_directory`는 `os.walk(onerror=raise)`와 `os.stat`(심볼릭 링크 추종)을 쓴다. 그래서 읽을 수 없는 하위 폴더 하나, 깨진 링크 하나에 **스캔 전체가 실패**한다. `error_count`는 상수 0이다.
- **최소 재현**:
  - `[self:storage]{op:"scan", path:"<폴더>"}` → `[self:storage]{op:"summary", root_path:"<폴더>/하위"}`
  - `[self:storage]{op:"summary", root_path:"~/Downloads"}`(`/` 스캔 존재)
  - 잠긴 하위 폴더를 둔 채 scan
- **실측**:
  - T22: 행 키 `['count','extension','total_size_mb']`, 확장자 25종 → **20행**(e01~e05 누락, 표지 없음), `file_count:26`.
  - 하위 폴더·I10·I11(`~/Downloads`): 위 거짓 문구.
  - I6 `[Errno 13] Permission denied: '…/IT74_y/locked'`, I7 `[Errno 2] … broken_link` → "스캔 실패".
  - 작은 파일은 `total_size_mb` 반올림으로 전부 0.0이다.
- **영향**:
  - "프로젝트 폴더 용량 보기"를 IBL로 말할 길이 없다. 우회는 `file_find pattern:"**/*"` → compute(절대경로 접두 제거 후 첫 조각) → groupby다. 되지만 꼬여 있고, 200건 상한이면 `limit`이 필요하다.
  - 홈·프로젝트처럼 보호 폴더나 깨진 링크가 흔한 곳은 스캔이 서지 않는다.
  - 거짓 안내는 이미 스캔된 `/` 위에 중복 스캔을 부른다.
- **제안(수리성)**:
  1. summary에 `/analyze/folders`와 같은 폴더 롤업 행을 싣는다(items에 `folder`·`size`·`count`). 선언은 구현과 맞춘다.
  2. 경로 조회는 "그 경로를 품은 가장 깊은 스캔 볼륨 + 접두 필터"로 하고, 문구는 실제 상태(품은 볼륨 있음·경로 밖)를 말한다.
  3. 스캔은 오류 항목을 건너뛰며 세고 `error_count`·`errors`(표본)로 신고한다. 링크는 `lstat`로 다룬다.
  4. 확장자 상위 N은 `truncated`·`total_extensions`를 싣는다(B72-3 관문 확장과 같은 처방).
  - 가드: {루트, 하위, `/` 아래} × {summary, folder_note set} · {잠금, 깨진 링크} scan.

### B74-4 `self:folder_note` — `folder_path`를 **원문 토큰 그대로** 저장하고, 없는 폴더에 성공하며, 코퍼스 형태는 스캔 루트에만 붙는다

- **요약**:
  - `add_annotation`은 `root_path`만 `expand_body_path`·`abspath`·NFC로 정규화한다. `folder_path`는 받은 문자열을 그대로 `INSERT`한다(존재·범위 확인 없음).
  - 선언 별칭 `folder_path: [path]`·`root_path: [path]`가 `path` 하나를 두 칸에 모두 넣는다. 그래서 코퍼스가 가르치는 `[self:folder_note]{op:"set", path:"~/projects/my_project", note:"진행 중"}`(22건 중 set 형태)은 **그 폴더가 스캔 루트 자신일 때만** 붙는다.
  - set은 매번 추가이고 개정·삭제 op는 없다.
- **최소 재현**: 스크래치 루트 스캔 뒤 `[self:folder_note]{op:"set", root_path:"<루트>", folder_path:"~workspace/…/assets", note:"…"}` → `op:"detail"`. 없는 폴더로 한 번 더. `path:"<루트>/하위"` 한 칸 형태.
- **실측**:
  - T23 detail: `[{folder_path:"~workspace/outputs/IT74_tree/프로젝트A/assets", note:"…(개정)"}, {folder_path:"~workspace/outputs/IT74_tree/없는폴더", note:"IT74 유령"}, {…assets, note:"…"}]`.
  - 유령 폴더 응답 `{"success":true,"message":"주석 추가됨: ~workspace/outputs/IT74_tree/없는폴더"}`.
  - I9(코퍼스형 하위 폴더)·`path:"~/projects/my_project"`(`/` 스캔 존재): B74-3의 거짓 "품은 볼륨 없음" 문구.
  - 코퍼스형을 루트 자신에 주면 success이고 저장 경로는 역시 토큰 원문이다.
- **영향**: 같은 폴더라도 토큰으로 단 메모와 절대경로로 단 메모가 다른 키가 되어 "이 폴더 메모 뭐였지"가 표기에 따라 갈린다. 오타 경로 메모가 성공으로 쌓인다. 사용자 색인에 `/` 볼륨이 있는데도 거의 모든 폴더에 메모를 달 수 없다(루트 정확 일치 + 거짓 안내). 코퍼스의 set 예시는 현재 몸에서 늘 실패한다.
- **제안(수리성)**:
  1. `folder_path`를 `root_path`와 같은 해소점으로 정규화하고, 실존·루트 안쪽임을 확인한다. 아니면 거절하고 받은 값을 신고한다.
  2. `path` 한 칸 형태는 "`folder_path`=path, `root_path`=그 경로를 품은 가장 깊은 스캔 볼륨"으로 해소한다. 별칭을 한 칸으로 바로잡는다.
  3. 같은 폴더의 재set은 새 행 + 최신 표지, 또는 갱신으로 계약을 정해 선언에 쓴다.
  - 가드: {토큰, 절대, NFD} 표기 × {루트, 하위, 없음} × {set, detail}.

### B74-5 copy·move·delete의 평문 실패가 `ADAPTER_SHAPE`(프로토콜 고장)로 분류된다 (★밭 이관: B56-3과 같은 속의 두 번째)

- **요약**: 세 핸들러의 실패 반환은 `"Error: …"` 평문이다. 판본 2 `legacy-envelope` 어댑터는 이를 "선언된 JSON 실행 봉투가 아닙니다"(`ADAPTER_SHAPE`)로 올린다. 56회차 B56-3 수리는 "copy/move/delete … **성공** 반환도 수리한다. **실패 반환은 보존한다**"였다. 같은 파일 가족에서 `self:list`의 부재는 `TOOL`+`details.error_type:"not_found"`+hint로 정직하다.
- **최소 재현**: `[try] { $x = [self:delete]{path:"<없는 파일>"} } [catch] { $x = $error.code }; return $x`
- **실측**: I5 → `"ADAPTER_SHAPE"`, `source_complete:false`, `evidence_summary.source_failures:1`. 메시지는 `선언된 JSON 실행 봉투가 아닙니다: Error: 경로가 존재하지 않습니다: …/없는파일.zip`(T17). B74-1의 I1~I3 실패도 같은 코드다. `?? "이미 없음"` 폴백은 잡힌다.
- **영향**: "없으면 넘어가기·권한 없음·원본 없음"을 코드로 가르는 프로그램이 모두 "어댑터 고장"을 본다. 원천 불완전 표지(`source_complete:false`)가 단순한 부재를 원천 결함처럼 보이게 한다. 사용자가 읽는 문구 앞머리는 내부 프로토콜 용어다.
- **제안(수리성, ★밭 이관)**: 개별 수리가 아니다.
  1. 판본 2 `legacy-envelope` 도구 전수에서 `"Error:"` 평문 실패를 반환하는 자리를 census한다(AST: `return "Error…"`/`f"Error…"`).
  2. 공통 실패 봉투(`success:false`·`error_type`·`errno`·`path` — list의 `details`와 같은 모양)로 일괄 감싼다.
  3. 빌드 관문에 "legacy-envelope 도구의 평문 실패 반환 금지"를 둔다.
  - 가드: {copy, move, delete} × {없음, 권한, 범위 밖} → `$error.code`·`details.error_type`.

### B74-6 등록 스크립트 `폴더용량`이 설명과 다른 폴더를 잰다

- **요약**: 목록 설명은 "outputs 폴더 용량 요약 (items)"이다. 본문은 `root = Path(__file__).resolve().parents[1]  # outputs/`인데, 파일이 `data/scripts/`에 있어 실제로는 **`data/`** 하위를 잰다. 인자가 없어 다른 폴더(프로젝트 폴더)를 줄 수도 없다.
- **최소 재현**: `$s = [self:script]{id:"폴더용량"}; return $s.items >> [table:take]{n:4}`
- **실측**(I12): `showcase_stage 31682.6 · _backups 8080.1 · spill 3908.6 · models 2113.7` — 모두 `data/` 하위 폴더다.
- **영향**: "폴더 용량"을 찾는 회상이 이 스크립트를 권하면 틀린 폴더의 수치를 옳은 것처럼 보고한다. 결정화 사다리의 스크립트 가로대가 B74-3의 롤업 공백을 메우지 못한다.
- **제안(수리성)**: 루트를 인자(`path`, 기본 `~workspace/outputs`)로 받고 `expand_body_path`로 푼다. 설명·주석을 실제와 맞춘다(스크립트 등록부의 설명도 교재다).

### F74-1 `self:list`가 파일시스템 순서로 돌려준다 — 다중 키 `sorted`에는 안내가 없다

- T01: 원래 순서는 `['설치파일.dmg','big_video.mp4','old_report.pdf','empty_dir',…]`(APFS 디렉터리 순서)다. `shell_shadow`가 `ls`·`tree`를 이 액션으로 대응시키는데 `ls`는 이름순이다. T08처럼 each 처리 순서, `take:n` 표본, 목록 보고가 기계·볼륨마다 달라진다.
- "폴더 먼저, 이름순"은 `sort by name` → `sort by is_dir desc` 2단 안정 정렬로 된다(깨끗). 하지만 자연스러운 `sorted($l, ($r)=>[!$r.is_dir, $r.name])`은 `UNORDERED: sorted의 키를 서로 비교할 수 없습니다.`로만 끝난다(목록 키 비교 불가, 2단 정렬 안내 없음).
- 제안(수리성): list 결과를 이름(NFC 기준) 순으로 결정적으로 정렬한다(선언에 명시). `UNORDERED`가 목록/레코드 키일 때 "안정 정렬을 뒤 키부터 두 번"이라는 전용 안내를 낸다(70회차 F70-1 전용 안내 부류).

### F74-2 `self:mkdir` 잎 스키마가 삭제 도구의 것을 달고 있다 (교재 드리프트)

- `system_essentials/ibl_actions.yaml` leaf `make_directory.input_schema`: `path.description: "삭제할 파일 또는 폴더 경로"`, `missing_ok`("대상이 없을 때 오류 대신 성공…")가 들어 있다. `delete_path` 잎에는 `missing_ok`가 없다. 판본 2 describe는 mkdir 계약에 `missing_ok`를 노출하지만 핸들러는 읽지 않는다(언제나 `exist_ok=True`).
- 제안(수리성): 두 잎을 바로잡는다(mkdir path 설명·`missing_ok` 제거, delete 잎에 `missing_ok`). B73-2 선언∖읽기 census가 이 자리를 잡는지 대조한다.

### V74-1 (후보) 휴지통으로 보내는 삭제가 없다

- 삭제 동사는 `self:delete`(영구, `rmtree`/`remove`) 하나다. "다운로드 정리"는 이 축의 가장 흔한 과제이고 사람은 보통 휴지통을 기대한다. B74-1이 보여 주듯 경로 실수는 즉시 되돌릴 수 없는 손실이 된다.
- 어휘 신설은 훈련이 하지 않는다. 판정 요청에 후보로만 올린다.

### V74-2 (후보) 내용 해시가 없다 — 중복 파일을 확정할 수 없다

- T13: 크기 묶음까지는 되지만 `report_v2.pdf`(같은 크기·다른 내용)를 중복으로 오탐한다. groupby에 모음 집계(`list`)가 없어 "어떤 파일들인가"를 `intersection([$r.size], $sizes)`로 되짚어야 한다. `data/guides/disk_search.md` 실측 기록은 "중복·이관 판단은 이름이 아니라 내용 해시로 해야 한다"고 가르치지만, 어휘에는 그 수단이 없다.
- 처방 순서(반-어휘-증식): 먼저 해시 스크립트를 `[self:script]`로 얼려 반복 사용을 관찰한다. 어휘 승격(파일 통화의 `hash` 필드 등)은 실제 반복 또는 사용자 판정이 인준할 때만.

## 재확인 (앞 회차 갭의 증거 추가 — 새 항목 아님)

- **B73-1**: T24 `[self:list]{…, pattern:"*.pdf"} >> [self:copy]{dest:…}` → `PIPE_COLLISION`("같은 명시 인자를 함께 주지 마세요" — 충돌 인자 없음). 선언 target_description의 대표 형태("src를 생략하고 앞 액션 결과를 >> 로 넘기면")가 판본 2에서 막힌다. each + 명시 `src/dest` 우회는 4건 성공.
- **B73-6**: T18 `[self:read]{path:"~workspace/…/3주차_과제.docx"}` → `파일을 찾을 수 없습니다: …/projects/컨텐츠/~workspace/outputs/…`. 절대경로는 성공한다. 같은 토큰으로 pptx 읽기는 성공한다.
- **B72-3**: T22 storage summary가 `LIMIT 20` 확장자 표를 `truncated`·전체 수 표지 없이 낸다(25종 → 20행, `count:20`, `file_count:26`). SQL 기본 LIMIT 침묵 절단의 같은 형태다. B72-3이 요청한 관문 확장 census의 표본으로 더할 것.

## 시드 후보 (실행 검증 통과만 — 자동 등록 안 함)

- T02(오래된 파일: list → filter `!is_dir && mtime < "<날짜>"`)
- T03(큰 파일 상위 N: filter → sort size desc → take)
- T05(NFD 이름 `pattern`)
- T06(숨김 제외 `name[0:1] != "."`)
- T07(확장자 집계: compute `lower(split(name,".")[-1])` → groupby count/sum)
- T09(폴더별 개수: each 안 list를 변수에 받고 `len`)
- T14(빈 폴더: file_find → each list → filter 0)
- T19(목록 → each 줄 → `join` → write → read)
- T01(2단 안정 정렬 "폴더 먼저 이름순")

경로는 `<폴더>` 자리표로 바꿔 심을 것.

**빼는 것**:
- T08(주차별 mkdir+copy)·T12(공백 경로 copy)는 이번 실행에선 대상이 새 경로라 결과가 맞았다. 그래도 B74-1 수리로 copy 충돌 의미가 바뀌므로 수리 뒤 재확인하고 심는다.
- T16(each delete)은 영구 삭제 문형이라 V74-1 판정 전에는 해마에 심지 않는다.
- T13·T22 우회(file_find 롤업)는 꼬임이라 뺀다.
- T10·T11·T17·T18·T23·T24는 결함 수리 전이라 뺀다.

## 판정 요청 (언어 개정·파괴적 변경 2종만)

- **V74-1 — 휴지통으로 보내는 삭제 표현**(예: `self:delete`의 새 인자 또는 새 낱말)을 들일지. 근거: 삭제 동사가 영구 삭제뿐이다. 다운로드 정리가 주 도메인이다. B74-1이 보여 준 경로 실수의 비가역성. 어휘 후보이므로 사용자 판정이 인준할 때만 집행한다.

그 밖의 B74-1~6·F74-1~2는 수리성이다. B74-1(겹침 거절·병합·충돌 "(2)")은 지금 데이터를 지우는 동작을 비파괴로 바꾸는 쪽이다. 교체가 필요한 문장은 기존 표현(delete 뒤 copy)으로 말할 수 있으므로 새 인자 없이 수리할 수 있다. B74-2의 그림 추출 위치 변경은 원본 옆 폴더 경로에 기대는 코퍼스 문장이 0건이라 기존 문장을 깨뜨리지 않는다.

**다음 수리 턴의 첫 항목(밭 이관)**:
1. B74-2 — "읽기 선언 op의 쓰기" AST census + 빌드 관문(B72-5에 이은 두 번째).
2. B74-5 — legacy-envelope 도구의 평문 `Error:` 실패 반환 census → 공통 실패 봉투 + 관문(B56-3에 이은 두 번째).
3. B74-1 — 사용자 경로 `rmtree/remove`는 delete만 허용하는 관문(copy·move 두 자리 확인).

## 위생

- **스크래치**: `outputs/IT74_tree`·`IT74_backup`·`IT74_x`·`IT74_y`를 탐침·격리 앞뒤로 삭제했다. 잔존 0. `projects/컨텐츠` 아래 IT74·`~workspace` 흔적 0. `self:delete`는 영구 삭제라 휴지통으로 간 것은 없다(스크래치 경로에만 사용). 읽기 전용(0555) 스크래치 폴더는 권한을 복원한 뒤 지웠다. `self:read`가 만든 `*_images/`는 스크래치 안이라 트리째 삭제했다.
- **저장소 색인**: 스크래치 스캔 볼륨 6회(탐침 3·수동 2·격리 1, 모두 id 3)를 앱 REST `DELETE /pcmanager/analyze/scan/3`으로 지웠다. `scans.json`은 회차 시작 전 사본과 **diff 0**이다. 사용자 `scan_1.db`(`/`)·`scan_2.db`(외장)는 mtime·크기 불변이다. 사용자 볼륨에 대한 folder_note set은 정확 일치가 없어 오류 경로로만 끝났다(쓰기 0).
- **사용자 폴더**: `~/Downloads`는 list 읽기만 했다(이름 미수록). 그 밖의 사용자 폴더는 읽지도 쓰지도 않았다.
- **건강 원장**: 회차 창(22:23~) `action_health`는 **training 285행 · usage 0**이다(list 99 · copy 50 · mkdir 28 · folder_note 26 · storage 22 · read 22 · delete 14 · groupby 9 · file_find 5 · write 4 · script 3 · move 2 · sqlite 1).
- **나머지**: 알림 0(T15는 check만, 알림함에 IT74 흔적 없음). 발신 0 · AI 호출 0 · 해마 시딩 0 · 라이브 코어 편집 0 · 커밋 0. 탐침 44요청 + 격리 재현 29요청 + 탐색·위생 조회 약 25요청.
- **백엔드**: 회차 내내 `state.json` phase `ACTIVE`, 재기동·FAILED 없음.

## 집행 완료

(수리 턴이 채운다.)
