# 건강기록 ([self:health]) 가이드

혈압·혈당·체중·심박수·체온·산소포화도 측정값, 증상, 투약, 검사 문서를 한 액션으로 관리하는
**건강 원장**. 계기: 🩺 건강기록 (요약/측정/투약/기록/검색 5탭). 가족 구성원별(person 축) 관리 지원.

## op

- **save**: 건강 정보 저장.
  - 측정값(권장 평탄형): `[self:health]{op: "save", category: "혈압", value: "128/85"}`
    — 혈압은 `"수축기/이완기"` 문자열 또는 `systolic`/`diastolic` 필드, 그 외는 수치 하나.
    카테고리는 한국어(혈압/혈당/체중/심박수/체온/산소포화도)·영어(blood_pressure 등) 모두 수용.
  - 증상: `{op: "save", info_type: "symptom", data: {category: "두통", severity: "mild", description: "..."}}`
  - 투약: `{op: "save", info_type: "medication", data: {name: "약이름", dosage: "5mg", frequency: "1일 1회"}}`
  - 문서(검사 결과): `{op: "save", info_type: "document", data: {category: "blood_test", image_path: "/경로", extracted_data: {...}, description: "..."}}`
    — image_path 는 저장소(`data/health/images/`)로 복사되고, extracted_data 에 OCR/판독 수치를 dict 로.
  - 공통 옵션: `measured_at`(ISO 시각, 생략=지금), `note`, `person`(생략=기본 사용자).
- **query**: 조회. `query_type` 하나로 분기 — `summary`(기본)/`search`/`측정기록`/`증상`/`투약`/`문서`/`목록`(사람 목록),
  또는 `혈압`·`혈당` 같은 카테고리명을 직접 넣으면 그 측정 추이.
  - 옵션: `keyword`(search 필수), `days`(기본 365), `person`, `category`(측정 필터).
  - 측정 조회는 `{text, table, blocks, points}` 통화 — table 은 날짜 피벗(혈압=수축기/이완기 2열)이라
    `>> [table:chart]` / `>> [table:spreadsheet]` 파이프 직결.
- **ingest**: 다형 입력 일괄 적재 — `file`(이미지·PDF·엑셀·txt/md/csv 경로) 또는 `text`(자유 텍스트/붙여넣기)를
  AI가 구조화해 저장. 계기 '올리기' 탭이 이 op(파일은 `/launcher/upload` 로 올라와 경로가 됨).
  - 파이프라인 = **공용 ingest 엔진**(`backend/services/ingest_engine.py`): 원문 추출(PDF 텍스트층+스캔 정직 거부,
    엑셀 TSV, 인코딩 폴백) → 구조화(텍스트=경량 AI / 이미지=Gemini 비전 패스스루) → **결정론 검증**(수치 없는
    측정·kind 불명은 지어내지 않고 건너뜀, 건너뜀 사유 반환) → 기존 save 경로로 낱개 적재.
  - 이미지/PDF 원본은 문서 레코드로 자동 보존(image_path).
  - ★재무 등 다음 도메인도 같은 엔진에 스키마 프롬프트+op 한 줄로 얹는다 — 도메인마다 새로 만들지 말 것.
- **delete**: 기록 삭제. `record_type`(measurement/symptom/medication/document) + `record_id`
  (**조회 출력의 (#번호)**). soft-delete(tombstone)라 폰 동기화에 전파. `person` 지정 시 그 사람 것만(오삭제 방지).

## 파라미터 정합 메모 (스펙↔코퍼스)

학습 코퍼스는 `{op: "query", category: "혈당"}` / `{op: "save", category: "혈압", value: ...}` 평탄형을
가르치고, 핸들러가 한국어·평탄형·query_type 혼용을 전부 정규화한다(모듈 상단 공용 지도).
**새 용례를 시드할 땐 평탄형(위 권장형)을 쓸 것** — data 중첩형도 동작하지만 정본은 짧은 쪽.

## 저장 구조

- DB: `data/health/health_records.db` (persons/measurements/symptoms/medications/documents,
  uuid 동기화 컬럼 — 폰 동기화는 `backend/datastore/health_sync.py`).
  폰에서는 `INDIEBIZ_USERDATA/health/` (APK 재추출에 안 지워짐).
- 이미지: `data/health/images/`.
- **기본 사용자 = `data/health/config.json` 의 `default_person`** (코드에 실명 없음 — '명사의 자리').
  파일이 없으면 "나". ★기존 설치에서 이 파일을 지우면 새 저장이 다른 인물로 갈라지니 주의.

## 함정

- 측정 save 에 수치가 비면 저장 거부(조용한 손실 방지) — value 를 꼭 채울 것.
- record_id 는 조회 출력의 (#번호)에서 얻는다 — 번호 없이 delete 하면 거부.
- 심박수/체온/산소포화도는 summary 의 "최근 측정값"에 함께 나온다. 단위: mg/dL(혈당), kg(체중), bpm, ℃, %.
- `data/health_records.db`(data 루트)는 정본이 아니다 — 정본은 `data/health/` 아래. 루트에 빈 파일이
  생겼다면 잘못된 경로로 연 흔적이니 지울 것.
