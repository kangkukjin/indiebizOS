# 기존 IBL 코퍼스 용례 점검 — 2026-09-09

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS`의 기존 6,545행에서 **412행 교체, 6,133행 유지**.
용례 추가·삭제·중복 제거는 하지 않았다. 학습 JSON 182행과 운영 DB 230행에 적용 완료했다.

| 원본 | 점검 전/후 행 수 | 교체 | 유지 |
|---|---:|---:|---:|
| `data/training/_proposed_verify_intents_20260525.json` | 40 → 40 | 0 | 40 |
| `data/training/ibl_distilled.json` | 800 → 800 | 112 | 688 |
| `data/training/ibl_training_balanced_20260516.json` | 1,961 → 1,961 | 70 | 1,891 |
| `data/ibl_usage.db`의 `ibl_examples` | 3,744 → 3,744 | 230 | 3,514 |
| 합계 | 6,545 → 6,545 | 412 | 6,133 |

범위는 `data/guides/hippocampus_retraining.md`의 코퍼스 정의(DB + training/*.json)다.
`_archive`와 `.bak`는 과거 보관본이라 수정하지 않았다. 모델 가중치 재학습도 하지 않았다.

## 검토 기준과 교체 내용

정본 `data/system_docs/ibl.md`, `docs/IBL_LEARNABILITY_2026_09_09.md`, 현재 파서·타입 검사기,
파라미터 검사기와 실제 핸들러를 기준으로 2,386개 서로 다른 코드를 검토했다.
197종의 코드에서 교체가 필요했고, 행별 의도를 확인해 412행에 적용했다.
각 행의 유지/교체 판정과 변경 전후 해시는 `rows_01.jsonl`부터 `rows_07.jsonl`에 있다.

- 따옴표에 담긴 `each` 실행 본문을 직접 블록으로 옮겼다. 따옴표 `do` 자체가 불법이라는 뜻은
  아니다. 현재 허용되는 구문이지만 인용부호·변수 경계 오류를 줄이는 새 작성 표기로 통일했다.
  예약/워크플로 내부 문자열의 실제 IBL도 해당 범위 안에서 검토했다.
- 반복 입력이 없는 표본, 산문 요약을 잃는 반복, 임의로 정한 반복 상한, 빈 결과에서도 계속
  도는 루프, 실제 행 수와 다른 평균 분모를 고쳤다. 요약을 모을 때는 `collect:true`를 쓴다.
- `$prev`, `[prev.output_path]`, `{{first_result_link}}`, 생략 기호, 중복 파라미터,
  자연어 `steps`를 실행 코드로 둔 표본을 실제 값·변수·IBL 본문으로 교체했다.
- 이미지 생성 결과의 `path`, 비디오 완성 응답의 `output`, 비동기 작업의 `job_id` 등을
  실제 생산자에 연결했다. 생성 결과 메타데이터를 PNG 파일로 쓰는 오용도 고쳤다.
- KOSIS 검색 카드와 실제 통계 데이터, 공연 원시 열과 전시 열, 파일의 `name/mtime/size`,
  영상 검색 카드와 상세의 조회수 등 생산자별 필드를 대조했다.
- 네이버/직방 전세 조회는 `deal:rent, lease:전세`로, 네이버 금액은 원 단위 `price`로
  맞췄다. 제곱미터→평 단가 환산, 주가·GDP의 연도 축, 시세 병합의 통화 단위도 보정했다.
- 메시지 읽기로 연결된 주소록 의도는 이웃 목록으로, 사이트 북마크 의도는 사이트 목록으로
  고쳤다. 같은 라디오 목록 코드를 쓰더라도 실제 라디오 의도인 DB 1759행은 유지했다.
- 이름 붙은 용례(alias)는 입력 인자를 받는 함수 몸으로 검사했다. 독립 프로그램처럼 검사해서
  정상적인 자유 변수·입력 통화를 잘못 지우지 않았다. 변경된 코드의 호출 서명과 alias 반환
  타입은 실행기의 계산자로 갱신했다.

의도 문장, JSON 순서·다른 필드, DB ID·출처·별칭·topic·성공/실패 통계는 보존했다.
DB에서 바뀐 필드는 `ibl_code`, `nodes`, `signature`, `returns`, `updated_at`뿐이다.
`nodes/signature/returns`는 코드에서 파생되는 검색·호출 메타데이터다.

## 검증 결과

- 적용 후 6,545행 전체 문법·타입 오류 0, 파라미터 검사 오류 0, 검사기 기권 0.
- 재실행 시 `pending:0`: 이미 적용된 행을 다시 바꾸지 않는다.
- 행 집합·순서·의도 해시·코드 해시 검증 통과. SQLite 무결성 및 외부 콘텐츠 FTS 무결성 통과.
- 운영 DB의 변경 230행을 현재 로컬 모델로 재임베딩했다. 벡터가 없었던 기존 행 2건도 포함되어
  벡터 수는 3,719→3,721. 용례 행 수는 3,744로 동일하다.
- 이관/의미 검증 5개 + 현재 작성 규칙·값식 회귀 87개 = **92개 통과**.
  외부 생산자는 고정 입력으로 대체하고 실제 엔진에서 연도 결합·단위 보존·산문 수집을 확인했다.
- 전체 backend 회귀 3,161개: 최초 샌드박스 실행 3,147 통과, 3 skip, 9 실패, 2 error.
  로컬 서버·LibreOffice 제약으로 실패한 검사는 권한을 높여 관련 25개를 재실행해 모두 통과했다.
  따라서 남은 실패는 이번 데이터 적용 **이전에도 실패한**
  `backend/test_each_currency_contract.py::test_C13_교재도_같은_계약을_가르친다` 1개다.
  이 테스트는 교재 한 줄에 `**고차**`와 `each{`가 함께 있어야 한다는 과거 표기를 찾는다.
  코퍼스 수정 범위 밖의 교재/테스트는 고치지 않았다.
- `scripts/build_ibl_nodes.py --check`, `scripts/check_retired_contracts.py` 통과.

필드 관측 경고는 14종 코드/22행에 남는다. 검사기의 관측 표본이 아래 실제 반환 필드를
다 포함하지 않아서 나는 경고로, 없는 열이라고 간주해 지우지 않았다.

| 필드/계약 | 실제 구현 근거 |
|---|---|
| 지출 `amount` | finance-record 지출 조회 행 |
| 도서 `loan_count` | culture 정보나루 대출 정보 |
| CCTV `playable` | CCTV 재생 가능 상태 보강 |
| 사진 `camera` | photo-manager 사진 메타데이터 |
| 메시지 `favorite` | business의 받은 메시지 원시 행 |
| HN `date` | web/handler.py의 `_hn_items` |
| 일정 `action/time` | backend/datastore/calendar_manager.py의 이벤트 저장 |
| 파일 `name/mtime/size` | system_essentials/handler.py의 `_file_views` |
| Cloudflare effect 응답의 `items` | cloudflare/tools/api.py가 result와 함께 방출 |
| HTTP `body_preview` | HTTP body 조회 응답 |

이 점검은 외부 API·웹사이트·발송·파일 삭제·유료 AI 생성 등을 실행하지 않았다.
`${…}`로 남은 입력 자리, 등록 스크립트·프로젝트·파일의 존재, 외부 서비스 응답과 생성 품질은
사용 시 확인해야 한다. 유지 판정은 현재 검토에서 교체 근거가 없다는 뜻이며 모든 용례의
외부 실행 성공을 보증한다는 뜻은 아니다.

## 기록과 재적용

- `replacements.jsonl`: 교체 전후 코드, 항목별 이유, 적용할 정확한 origin/row_id.
- `rows_*.jsonl`: 6,545행 각각의 판정. JSON row_id는 0부터 시작하고, DB row_id는 실제 id.
- `scripts/review_corpus_2026_09_09.py`: 기본 읽기 전용 검증, `--apply`로 실제 적용.
  새 행을 넣거나 기존 행을 지우지 않으며, 의도/코드/행 집합이 검토본과 다르면 중단한다.
  JSON 원본·SQLite 온라인 백업 후 UPDATE와 벡터 교체를 한다. 오류가 나면 트랜잭션을
  되돌리고 이미 쓴 JSON을 복구한다. 원본에 새로운 사용 기록이 붙은 뒤에는 재검토가 필요하다.

```sh
.venv/bin/python3 scripts/review_corpus_2026_09_09.py
.venv/bin/python3 scripts/review_corpus_2026_09_09.py --apply
```

적용 전 백업: `data/_backups/2026-09-09_082815_corpus_review/`.
운영 코퍼스/백업은 기존 Git 제외 정책을 유지한다. 이 문서·교체 목록·행별 판정·이관 스크립트가
커밋에 남는 재현 자료이며, 추가 학습 용례가 아니다.
