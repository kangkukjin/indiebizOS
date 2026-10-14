# 68회차 — 개인 사진·음성 묶음 정리: 중복·앨범·전사·증분 재실행 (2026-10-14, 훈련·수리 완료)

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS`, main 직접 작업. 시작 HEAD `290456be`. 훈련 21:36~22:00 KST(24분, 상한 60분), 수리·회귀·재검증 22:00~(별도). 사용자 지정: "3번 주제(사진·녹음 묶음 정리)로 훈련하고 에러와 시간낭비를 수리".

## 1. 과제와 조건

[request.txt](request.txt) 원문 — 폰에서 옮긴 사진(jpg/png)·음성(m4a) 묶음을 촬영 정보 우선으로 날짜 짓고, 묘사·핵심어, 정확 중복은 옮기고 유사 중복은 보고만, 날짜별 앨범(주제는 AI 가 2~6글자), 음성은 전사해 날짜 폴더+txt(말 없으면 미분류+사유), 목록.csv·보고서.md, 재확인, 증분 재실행(이미 정리한 것은 건너뜀·앨범 주제 유지).
자료는 전부 합성([harness/prepare.py](harness/prepare.py), [task.md](task.md)): EXIF 사진 9·정확 중복 2·유사 중복(재압축) 1·EXIF 없는 PNG 1·잘린 JPEG 1·텍스트 1·`say` 음성 2·무음 1 = 18건. 변형 3건(새 사진·이미 정리된 사진의 사본·새 음성). 비전·전사는 실제 모델(Gemini 전사·실행 모델 비전). 외부 효과 = 회차 폴더 안 파일 이동·쓰기뿐.
완료 조건·기대값은 실행 전 task.md 표. 검증기 [harness/verify.py](harness/verify.py)는 manifest 대조만 한다.

## 2. 작성

분해: 폴더·기존 상태 → 목록·지문·사진 메타 → 정확 중복(지문) → 유사 중복(시각·기종, 크기는 낱말 없음) → 사진 읽기(`self:struct` 이미지, `on_error:collect`) → 날짜별 주제(`table:ai` 1회, 기존 앨범 유지) → 이동(순차) → 음성(`inspect` 모델 0 → `transcribe`, 날짜 연결) → 목록.csv(기존 행+새 행) → 재확인(폴더 재독) → 보고서. 지역 함수 8, 낱말 11종. 전체 흐름 한 프로그램.
초안·수정본: [base_v0.ibl](base_v0.ibl)(최초) → v1(보간 안 따옴표) → v2(검사기 결함 우회) → v3(두 분기 List) → v4(null 텍스트) = 검사 통과·기본 실행 → v5(빈 시각 보호, 변형 1차 실패 뒤) = **원래 전체 프로그램** → [base_v6.ibl](base_v6.ibl)(수리 뒤 width/height 사용, 새 변형). 수정 이유는 task.md 작성 이력.
기본 조건 유지: 작성 전 런타임 코드 미열람. 검사기 내부 오류의 원인 진단에만 코드를 열었다(실행 기반 결함 진단, §4 L68-1). 참고 자료 = 교재 2권·문법 전문·describe 3·탐침 11.

## 3. 실행과 결과

| 실행 | 프로그램 | 시간 | 검사/종료/달성 | 비고 |
| --- | --- | --- | --- | --- |
| 훈련자 기본 | v4 | 46.8초(모델 14회: struct 12·ai 1·전사 1, 입력 158,537·출력 3,254 토큰, 17,008 단계) | 통과/정상/**부분 달성** 18/23 | L68-2(복사본 날짜 10-12·앨범 5개)·L68-3(잘린 JPEG 가 앨범으로) |
| 훈련자 변형 1차 | v4 | 21.9초 실패 | 통과/실패/미달 | `number('')` — L68-4(막 복사된 파일 `taken_at:""`), 이동 3건 뒤 실패(비원자) |
| 훈련자 변형 2차 | v5 | 9.4초(모델 1회) | 통과/정상/부분 달성 20/26 | 새 3건만 처리·기존 18행 불변·앨범 주제 유지·정리된 파일과의 중복 포착. 남은 불일치는 기본 실행의 L68-2·3 승계+누적 보고서 누락(작성) |
| 독립 AI 기본 | ep4765 | 253.3초, 모델 17회(입력 1,614,216·캐시 읽기 1,355,959·출력 26,283), 도구 9·IBL 5 | —/정상/**달성**(실체 확인) | 검증기 18/23 — 5건은 문구·열 이름 차이(파일시각/파일 시각, 유사 후보 양쪽 표시, 재확인 절 제목), 실체는 전부 충족 |

독립 AI 의 풀이: Python 한 편(`evidence/agent_organize.py`, 225줄 — PIL EXIF·sha256·ffprobe·이동·CSV)과 IBL 5회(`self:list`·`engines:image_read`·`sense:listen`·`self:read`). 이음새 해석: 사진 메타·지문·이동은 낱말이 있었는데도 Python 이 이겼다 — 막 복사된 파일의 메타 공백(L68-4)과 NFD 이름(L68-2)을 AI 는 PIL·`unicodedata.normalize` 로 스스로 비켜 갔고, 잘린 JPEG 도 PIL 로 걸렀다(L68-3). 묘사·전사만 IBL. 훈련자가 밟은 세 결함을 AI 는 Python 으로 우회해 결과가 더 나았다([[ibl-replaces-python-at-private-seams]]의 지표). 회상 사용 1·판정 1·문맥 압축 0·재요청 0. 증류는 training 표식으로 없음. `ibl.started` 의 `origin` 이 빈 값(에피소드 source 는 training) — 관측 공백 후보.

§4-5 여섯 가지: 풀이=Python+IBL 혼합 / 분할·재사용=AI 는 전사 캐시 재사용을 스스로 보고 / 방법 발견=describe·교재 / 완료 판정=폴더 재독·재실행 0건 확인까지 함 / 축적=앞 회차 관용구 사용 0 / 비용=위 표.

## 4. 발견

| ID | 분류 | 사실 | 최소 재현 |
| --- | --- | --- | --- |
| **L68-1** ★★ | 구현 결함(검사기) | `$x=[]` 뒤 `[if]` 에서 `[table:ai]` 결과(`{items:[…]}`)로 재대입한 변수를 `each` 에 넣으면 검사기가 `AttributeError: 'tuple' object has no attribute 'kind'` 로 죽는다. 진단·위치·로그 트레이스백 전무 → 접두 11·조각 19 이분 검사+오프라인 재현으로 1시간 중 ~8분 소모. 원인: `join(List,Record)`=Union 인데 `each` 가 `items.item`(Union 멤버 tuple)을 `$it` 타입으로 씀 | [evidence/min_if_join.request.json](evidence/min_if_join.request.json) 4줄 |
| **L68-2** ★★ | 구현 결함(값 경계) | `[self:photo]` 의 title/path 는 Spotlight 출력 그대로 **NFD**, `[self:list]` 의 name 은 **NFC** → 같은 파일 `IMG_0002 복사본.jpg` 가 이름으로 안 맞아 메타 없음 → 날짜가 파일 시각(10-12)으로, 앨범 1개 과잉 | probes/list_hash vs photo_dir |
| **L68-3** ★★ | 구현 결함(정직성) | 잘린 JPEG: `engines:image_read` 는 "검수 이미지 준비 실패"로 거절하지만 `self:struct{file}` 는 바이트를 그대로 모델에 보내 **없는 그림을 묘사한 성공 응답**("점무늬 베이지색 면…") → 손상 파일이 앨범으로 이동 | probes/struct_corrupt(수리 전 run) |
| **L68-4** ★★ | 구현 결함(원천 신선도) | 막 복사된 사진(Spotlight 미색인/부분 색인): `[self:photo]` 가 `taken_at:""` 또는 **파일 생성일**+기종 빈 값을 준다. 변형 1차 `number('')` 실패의 뿌리, 수리 뒤 재실행에서도 13장 중 10장이 복사일로 분류됨. "폰에서 막 옮긴 폴더"가 이 과제의 전형인데 색인 지연이 곧 오답. 또 가로세로 픽셀을 주는 낱말이 없었다(`self:media` probe 도 코덱만) | probes/photo_fresh_dir(색인 뒤엔 정상) · after_v5_base |
| **L68-5** ★ | 계약(값 vs 실패) | 무음 파일 `[sense:listen]` 전사 = TOOL 오류 "텍스트 결과가 없습니다". 말 없음은 실패가 아니라 값. 우회 = `op:inspect`(모델 0) 로 무음 판정 | probes/listen_03 |
| L68-6 | 작성 마찰 | `[table:filter]` 가 `List<Text>` 를 거절(레코드로 감싸야) · null 가능 텍스트 보간 FORMAT_TYPE · 보간 안 따옴표(작성 습관) · `self:read` 가 JPEG 에 utf-8 디코드 오류(미지원 형식 안내 아님) · `self:list` mtime 분 단위라 파일 시각 이름의 초가 `00` | check_v1~v3 |
| L68-7 | 구현 결함(봉투) | `[self:file_find]{limit:3}` 가 PARTIAL_SOURCE 실패 — 핸들러가 `truncated` 만 싣고 `truncations`(scope selection·reason limit)를 빠뜨려 어댑터가 "사유 없는 절단"으로 읽음 | probes/find_img |
| L68-8 | 작성(설계) | 이동을 다 하고 마지막에 목록을 쓰는 설계 — 중간 실패 뒤 이미 옮긴 3건이 목록 밖(다음 실행이 잃음). 언어 결함 아님, 교재에 한 문장 | exec_v4_variant |

## 5. 개선 방향과 수리 (같은 날, 22:00~)

| 갭 | 소유 | 수리 | 확인 |
| --- | --- | --- | --- |
| L68-1 | `backend/ibl/ibl_v2_compile.py` `_rows_of` | each 입력이 Union 이면 갈래마다 행 목록으로 읽고 원소 타입을 합류(빈 갈래는 원소 없음) | 최소 재현 검사 통과·회귀 2건 |
| L68-1 진단 | `backend/ibl/ibl_v2_entry.py` | 기반 오류를 `logger.exception` 으로 로그에 남김 | — |
| L68-2 | `backend/datastore/file_index.py` `_run_mdfind` | Spotlight 경로 NFC 정규화 | 회귀 1·라이브 photo_dir 전부 NFC |
| L68-4 | `file_index._fill_from_exif`·`_walk_candidates` 합치기 + photo-manager 카드 | ① 사진은 파일 EXIF(DateTimeOriginal·기종·픽셀)를 직접 읽음. **EXIF 원본 시각이 색인의 파일 생성일보다 우선**, 기종·크기는 색인이 비운 칸만, EXIF 없는 그림은 파일 생성 시각 ② 명시 폴더 질의는 Spotlight 결과에 **같은 조건의 파일 순회(mdls 0회)를 합쳐** 색인이 아직 모르는 파일을 빠뜨리지 않음(`unindexed` 수 신고, 촬영일·GPS 조건은 제외) ③ 카드에 `width/height`(관측 필드, 새 낱말·op·인자 0). 수리 1차(①만) 뒤 재실행에서 색인이 **일부만** 된 폴더가 파일 자체를 빼먹어 13장 중 10장이 복사일 → ② 추가 | 회귀 8·라이브 photo_dir·오프라인 14장·막 복사 폴더 재실행 23/23(§6) |
| L68-3 | `backend/services/ingest_engine.py` | 이미지 입력을 PIL 로 디코드 검사, 실패=정직 거절(image_read 와 같은 기준) | 회귀 1·라이브 struct_corrupt 거절 |
| L68-5 | android 패키지 `android_audio_provider`·`android_audio` | 텍스트 없음 → 빈 전사문 값 + `no_speech:true`, 결과 `chars:0` | 회귀 1·라이브 listen_03 success |
| L68-7 | system_essentials `fs_meta` | `truncations` 통과(path_audited 재감사 지문 갱신) | 회귀 1·라이브 find_img limit:3 성공 |
| L68-8 | `data/guides/ibl_composition_tools.md` | 이동 동반 정리는 항목마다/이동 전 기록 한 문장 + photo·listen 의 새 값 | — |
| 어휘 | photo-manager·android `ibl_actions.yaml` target_description | width/height·NFC·EXIF 직접 읽기·no_speech 문장 | `build_ibl_nodes.py --check` 통과(용례 ack 2) |

새 낱말 0·op 0·인자 0. 회귀 시험 [backend/test_long_sentence_round68_repairs.py](../../../../backend/test_long_sentence_round68_repairs.py) 13건(모델 호출 0). 관련 회귀(수리 모듈을 참조하는 backend/test_*.py 141 파일, xdist 6) 실패 0. `build_ibl_nodes.py --check`·`check_file_size.py` 통과.

## 6. 수리 뒤 검증·비용·낭비·잔여

**수리 뒤 재실행(22:38~22:44, 세대 069285c6, 실행 직전에 새로 복사한 사본 = 색인 지연을 실제로 밟음)**

| 실행 | 프로그램 | 시간 | 결과 |
| --- | --- | --- | --- |
| 원래 전체 프로그램 기본 | v5 | 33.5초 | **23/23 달성** — 앨범 4·날짜 전부 EXIF·잘린 JPEG 읽기실패 제자리·무음 미분류·NFC 이름 일치 |
| 원래 전체 프로그램 증분 | v5 | 7.5초 | 25/26 — 새 3건만·기존 18행 불변·앨범 주제 유지·정리된 파일과의 중복. 남은 1건 = 증분 보고서에 이전 음성 항목이 없음(프로그램의 누적 보고서 설계, L68-8 계열·시스템 결함 아님) |
| 새 변형 | v6(width/height 로 유사 중복 크기 판정) | 37.7초 | **23/23** — 유사 후보 "같은 촬영 시각·기종·크기 960x720" 로 실제 판정 |
| 수리 1차(EXIF 보충만) 뒤 | v5 | 31.8초 | 18/23 — 색인이 일부만 된 폴더에서 Spotlight 가 파일을 빼먹어 10/13 복사일 → ② 순회 합치기 추가 뒤 위 결과 |

최초 기준선(기본 46.8초 18/23 → 수리 뒤 33.5초 23/23)은 같은 자료·모델·조건이나 비전 응답 시간이 섞여 시간 절감은 주장하지 않는다. 수리 전 변형 1차 실패(21.9초)는 재현되지 않았다.
재기동 관측: backend 편집 뒤 제어자가 DRAINING 에서 다른 세션의 스케줄러 자식("삼성1 음악 끄기 22:37" 대기 스레드)에 막혀 600초 상한마다 `deferred`(자동 재개 없음) — 22:09 편집이 22:38 에야 적용(강제 종료 안 함, 자식 종료 뒤 `restart --wait`). 63회차 교훈("리스가 걸린 작업은 취소 가능해야")의 스케줄러판 — 시간 대기 스레드는 drain 이 끊을 수 있어야 한다(후속 후보, 이 회차 미수리).
**독립 AI 되먹임 재실행(같은 요청, 새 사본, ep4769 / task_sysai_f4b94aae, 22:44:41→22:48:29)**: 227.4초(기준 253.3), 도구 13(Bash 4·IBL 9: image_read·listen·list·read·write), 모델 30회·입력 3,569,128(캐시 읽기 3,304,770)·출력 22,979 — 기준(입력 1,614,216)의 2.2배. 결과 달성(앨범 4·날짜 전부 EXIF·잘린 JPEG 제자리·무음 미분류·전사↔앨범 연결, 검증기 19/23 의 4건은 문구·열 이름 차이). AI 자기보고: 첫 IBL 프로그램이 저장 단계에서 실패해 묘사 11장을 다시 받음("제가 짠 프로그램의 실수"). **경로 선택은 바뀌지 않았다** — EXIF·지문·이동은 여전히 Python(`/tmp/r68b_photo_script`), IBL 은 묘사·전사·읽기/쓰기. 수리는 훈련자 경로의 오답을 없앴지만 AI 가 `[self:photo]` 를 고르게 하진 못했다(AI 는 수리 전에도 PIL 로 비켜 갔으므로 고를 이유가 없었다 — 이음새 지표 그대로). 표본 1회.

**비용(훈련 대상)**: 훈련자 작성·검수 ~13분(탐침 포함), 실행 46.8+21.9+9.4초, 모델 입력 약 19만 토큰(struct 12·ai 2·전사 2). 독립 AI 253초·입력 161만(캐시 136만)·출력 2.6만. 훈련 운영(이분 탐색·재현·검증기 작성) ~10분, 수리·회귀·문서 별도.
**필요했던 비용**: 사진 묘사 12회·주제 1회·전사 2회는 결과의 핵심. inspect 로 무음을 모델 0으로 판정한 것은 재사용 가치.
**줄일 수 있었던 일**: ① 검사기 충돌 진단 ~8분 — 진단 한 줄이 있었으면 1분(L68-1 수리로 제거) ② 변형 1차 실패 뒤 수동 복원 — 목록을 항목마다 썼으면 재실행만으로 회복(L68-8) ③ 검증기 네 번 고침(열 이름·경로·스냅샷 경로·UTC) — 실행자 형식에 덜 기대게 처음부터(55회차 교훈 재발) ④ 보간 안 따옴표 SYNTAX 1회(습관).
**원인과 근거**: ①③은 실행기·작성자, ②④는 작성자. 확인된 낭비 ①②④, 후보 ③.
**보존할 품질**: 읽기 실패·유사 후보의 보고, 폴더 재독 재확인, 기존 행 불변.
**미검증**: 실기기 폰 사진(HEIC·GPS 다수)·수백 장 규모의 struct 비용·Windows/Linux 의 색인 경로(file_index 폴백 walk 는 EXIF 폴백을 공유)·큰 명시 폴더(수만 장)에서 순회 합치기의 비용(후보 상한 2만은 공유).
**다음 회차 후보**: 69 = 실제 폰 USB 사진(`source:usb`, HEIC·GPS)으로 같은 프로그램 / AI 가 `[self:photo]` 대신 PIL 을 고르는 이유(회상·describe 노출)의 발견·학습 문제 / 증분 재실행에 누적 보고서까지 / 스케줄러 시간 대기 스레드와 drain.
