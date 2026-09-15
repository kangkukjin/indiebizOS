# 일상 수요에서 고른 IBL 어휘 후보 10개 — 2차 조사

조사일: 2026-09-15 (기준 커밋 `a4da7009`). 1차 조사 [IBL_VOCABULARY_CANDIDATES_2026_09_15.md](IBL_VOCABULARY_CANDIDATES_2026_09_15.md)(`dc96fed1`)의
열 개(문서 편집·시트 재계산·클라우드 파일·외부 캘린더·메일함·할 일·PDF 가공·대중교통·채용·택배)와
**겹치지 않는** 열 개를 골랐다. 방법은 상상행동 가이드(`data/guides/imagination_action.md`) 4-1을 따랐다.
자연어 요구를 먼저 적고, 그 뒤에 빌드된 카탈로그(6노드 165액션)·패키지 선언·핸들러·등록 스크립트를 대조했다.

아래 이름·op 는 **제안이며 현재 실행 가능한 계약이 아니다.** 어휘 신설·op 추가·API 호출은 하지 않았다
(op 신설도 어휘 증식 — 사용자 판정 09-14). 실제 절약 폭은 미측정이다.

## 선정 기준과 결론

기준: (1) 여러 사람·여러 과제에서 반복되는가, (2) 현재 어휘 조합·`[self:script]`·브라우저로 해결되지 않거나
그 비용이 큰가, (3) items 통화로 다른 어휘와 이어지는가, (4) 공식 구현 경로가 확인되는가.

결론: 기존 어휘 **확장** 4건(시간·날씨·읽기·문자), **새 낱말** 6건(의약품·영화·항공·스마트홈·이미지·압축).
셋(이미지·압축·인쇄)은 로컬 결정론 작업이라 `[self:script]` 로 먼저 얼려 빈도를 본 뒤 승격 여부를 판정하는 편이 맞다.

## 조사에서 걸러진 것(이미 있음)

| 흔한 요구 | 현재 경로 | 비고 |
|---|---|---|
| "지금 달러 환율" | `[sense:stock]{symbol:"원달러"}` (KRW=X 별칭), `[sense:world]` economy 스냅샷 | investment/handler.py:119~127 |
| "엄마한테 문자 보내줘" | `[limbs:phone]{op:"sms", to, text}` 작성창 열기(전송은 사용자 탭) | 자율 발송 아님이 설계. 아래 4번은 이 경계를 유지한 확장 |
| "엑셀 수식 다시 계산" | `[self:sheet]` range/range_write/calculate | 1차 후보 2번이 오늘 이미 집행됨(`test_document_sheet_transit_2026_09_15.py`) |
| 요약·번역·회의록 | `[self:ask]`, `[table:brief]`, `[sense:listen]` | 1차와 같은 판단 |
| 영수증·명함 읽기 | `[engines:image_read]`, `[self:struct]` | |

## 1. 공휴일·기념일·절기 — `self:time` 확장

- **요구:** "다음 연휴가 언제야? 추석 전에 처리해야 할 일정 잡아 줘." "10월 근무일이 며칠이야?"
- **현재:** `[self:time]` 은 현재 시각만 준다. `[self:manage_events]` 에 type=holiday 선택지가 있으나 사용자가 직접 넣는 값이다.
  공휴일·대체공휴일을 아는 어휘가 없어 일정·마감·근무일 계산이 매번 모델 지식(오답 가능)에 기댄다.
- **최소 능력:** `op:"holidays"`, year·month → items(date·name·is_holiday·kind). 근무일 수·D-day 는 `[table:filter]`·`[table:compute]` 조합.
- **구현 근거:** [한국천문연구원 특일 정보(공공데이터포털)](https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15012690) —
  `SpcdeInfoService/getRestDeInfo`, 공휴일·국경일·기념일·24절기. 인증키 필요.
- **검증:** 대체공휴일·임시공휴일이 반영되는지, 연도 경계, 키 없을 때 정직 거절.

## 2. 대기질(미세먼지)·예보 일수 — `sense:weather` 확장

- **요구:** "오늘 미세먼지 어때? 아이 데리고 나가도 돼?" "이번 주말 비 와?"
- **현재:** Open-Meteo 현재 날씨만. location-services 패키지 description 은 "날씨/대기질 조회 … 여행 정보(항공권/호텔/관광지)"를
  약속하지만 대기질·항공권 액션은 없다(선언 부패 — 함께 고칠 것). handler 에 pm10/pm2_5 없음.
- **최소 능력:** `air:true` 또는 `op:"air"` → pm10·pm2_5·AQI, `days:N` → 일별 예보 items. 같은 좌표 해소기 재사용.
- **구현 근거:** [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api) — 키 불필요, pm10·pm2_5·european/us AQI.
- **검증:** 한국 기준(좋음/보통/나쁨) 등급을 데이터로 두고 코드에 박지 않기. 예보 단위·시간대.

## 3. 문서 읽기 형식 확장 — `self:read` HWP/HWPX/PPTX/EPUB

> ✅ **집행(2026-09-15, 사용자 판정)** — `doc_read_extra.py`(hwp v5 olefile 레코드 파서·hwpx zip+XML·pptx python-pptx·epub spine)를 handler `read_op` 확장자 분기에 연결. 봉투는 docx 와 동일(text+blocks). 실파일 검증: 원고청탁서.hwp·업무보고 pptx·Popper/롤링 epub. 회원 표면(`member_documents.read_document`)은 형식 화이트리스트를 유지해 새 형식이 회원 경로로 열리지 않는다(회원 표면 수리는 별도 이관). 시험 `backend/test_read_formats_2026_09_15.py`.

- **요구:** "이 공문(hwp) 읽고 제출 서류 목록 뽑아 줘." "이 발표자료(pptx)에서 숫자만 표로."
- **현재:** text/pdf/docx/xlsx/xls 만. 한국 공공·학교·관공서 문서의 대부분이 HWP 인데 읽을 수 없다.
  pptx 는 **쓰기**(doc_formats.py emitter)만 있고 읽기가 없다.
- **최소 능력:** 확장자 분기 추가 — hwpx(zip+XML, 의존성 없음)·hwp(v5)·pptx(python-pptx 이미 requirements)·epub. 반환 형태는 docx 와 같은 블록 items.
- **구현 근거:** [pyhwp](https://github.com/mete0r/pyhwp)(hwp5txt), HWPX 는 OWPML 표준 zip. python-pptx 는 이미 설치 의존성.
- **검증:** 표·이미지 위치, 암호 문서 거절, 구버전 hwp(v3) 미지원 명시.

## 4. 문자·카카오 전달 채널 — `others:channel_send` provider 확장

- **요구:** "이 요약을 아내한테 카톡으로 보내 줘." "거래처에 문자로 도착 알려 줘."
- **현재:** channel_send 는 Gmail/Nostr. 폰 `sms`/`share` op 는 작성창을 열어 두는 방식(전송은 사용자 탭)이며 `limbs` 노드에 있어
  "보내 줘" 요청이 채널 어휘로 해소되지 않는다. 수신자 해소(주소록)도 channel_send 쪽에만 있다.
- **최소 능력:** provider=`phone_sms`/`phone_share` 를 channel_send 에 붙여 **수신자 해소는 공유**, 마지막 탭은 사용자 정책 유지.
  발송 완료가 아니라 "작성창 열림"을 정직하게 반환.
- **구현 근거:** 이미 있는 android handler `_act_sms`/share. 새 외부 API 없음.
- **검증:** 상상행동 5-2-a 격리 조건 — 실제 사람에게 나가지 않는 대역에서 수신자·본문 구성만 판정.

## 5. 의약품 정보 — `sense:drug` 후보

- **요구:** "이 약 이름이 뭐고 무슨 효능이야? 지금 먹는 혈압약이랑 같이 먹어도 돼?"
- **현재:** `[self:health]` 는 투약 **기록**만. 성분·효능·주의사항·상호작용을 얻는 어휘가 없어 웹 검색 산문에 기댄다.
- **최소 능력:** query(제품명/성분) → items(제품명·업체·효능·용법·주의·상호작용·부작용·보관). 복용 기록과 조합해 주의사항 대조.
- **구현 근거:** [식약처 의약품개요정보 e약은요](https://www.data.go.kr/data/15075057/openapi.do) — `DrbEasyDrugInfoService/getDrbEasyDrugList`, 개발계정 1만 건/일.
- **검증:** 동명 제품 다건, 전문의약품 미수록 범위 명시. **판단은 하지 않고 원문 인용** — 의료 조언으로 보이지 않게.

## 6. 영화 — `sense:movie` 후보

- **요구:** "이번 주말 볼 만한 영화 뭐 있어?" "그 영화 넷플릭스에 있어, 아니면 어디서 봐?"
- **현재:** 공연(KOPIS)·전시(KCISA)·도서·유튜브는 있는데 영화만 없다. 문화 소비 중 가장 빈도가 높은 축의 공백.
- **최소 능력:** `op:"boxoffice"`(일/주간), `op:"info"`(감독·배우·개봉일), `op:"where"`(국가별 OTT/대여/구매 제공처).
  상영시간표는 공식 API 가 없어 범위에 넣지 않는다.
- **구현 근거:** [KOBIS 오픈API](https://www.kobis.or.kr/kobisopenapi/homepg/apiservice/searchServiceInfo.do)(일 3,000건),
  [TMDB watch providers](https://developer.themoviedb.org/reference/movie-watch-providers)(JustWatch 제휴, 액세스 토큰 인증).
- **검증:** 한글 제목↔TMDB id 매칭 오류, 제공처 국가 코드 KR 고정, 링크는 딥링크 아님을 명시.

## 7. 항공권 조회 — `sense:flight` 후보

- **요구:** "다음 달 둘째 주 제주 왕복 가장 싼 편 찾아 줘." "도쿄 3박 항공+숙소 대략 얼마?"
- **현재:** `[sense:stay]` 숙박은 있고 이동 수단 요금은 없다(패키지 설명만 항공권을 약속). 브라우저 조작으로는 가능하나 비용이 크다.
- **최소 능력:** origin·destination·date(·return·adults) → items(항공사·출발/도착·소요·요금·통화·좌석등급). 예약은 범위 밖.
  기차(KTX)는 이번 조사에서 공식 공개 API 를 확인하지 못해 미검증으로 남긴다.
- **구현 근거:** [Amadeus Flight Offers Search](https://developers.amadeus.com/self-service/category/flights/api-doc/flight-offers-search)(self-service, 테스트 환경 무료 쿼터).
- **검증:** 테스트 환경 요금은 실제와 다름을 표시, 공항 코드 해소(제주=CJU), 환승 포함 여부.

## 8. 스마트홈 제어 — `limbs:home` 후보

- **요구:** "거실 불 꺼 줘." "외출 모드로 해 줘, 에어컨은 28도."
- **현재:** limbs 는 폰·브라우저·화면·라디오·음악까지 있으나 집 안 기기는 없다. 워크스페이스에 `smart/`·`esp32_test` 가 있으나 IBL 밖.
- **최소 능력:** `op:"states"`(entity 목록·상태 items), `op:"call"`(domain·service·entity_id·data). 기기 이름은 사전(데이터)에 두고 코드에 박지 않는다.
- **구현 근거:** [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/) — `POST /api/services/<domain>/<service>`, Bearer 토큰.
  Home Assistant 한 공급자로 시작. SmartThings 등은 후속.
- **검증:** 격리 조건 — 실제 기기 대신 시험용 HA 인스턴스. 미등록 entity 거절, 상태 변화 반환 대조.

## 9. 이미지 결정론 변환 — `self:image` 후보 (먼저 `[self:script]`)

> ✅ **스크립트로 얼림(2026-09-15)** — `data/scripts/이미지변환.py`, 등록 id `이미지변환`. `[self:script]{op:"run", id:"이미지변환", args:{paths:[…], max_side:1600, max_kb:1000, strip_exif:true}}`. 승격 판정은 action_health 의 script run 빈도로.

- **요구:** "이 사진들 용량 1MB 이하로 줄여 줘." "아이폰 HEIC 를 JPG 로 바꿔 줘." "이력서 사진 3×4 로 잘라 줘."
- **현재:** `[engines:image_gemini]` 는 생성·편집(모델 호출), `[self:photo]` 는 조회. 크기 조정·형식 변환·EXIF 제거·자르기 같은
  **비-AI 변환** 어휘가 없어 매번 Pillow 원라이너를 Bash 로 쓴다(09-05 실측: Bash 우회의 전형).
- **최소 능력:** op resize/convert/crop/strip_exif, items(파일)를 받아 출력 경로 items 반환 — `[self:file_find] >> [self:image] >> [self:copy]` 흐름.
- **구현 근거:** Pillow(이미 requirements-tools), HEIC 는 pillow-heif 추가.
- **판정:** 등록 스크립트로 먼저 얼리고 `action_health` 로 호출 빈도를 본 뒤 승격. 압축(10번)과 같은 판정 절차.

## 10. 압축·해제 — `self:archive` 후보 (먼저 `[self:script]`)

> ✅ **스크립트로 얼림(2026-09-15)** — `data/scripts/압축.py`, 등록 id `압축`. `[self:script]{op:"run", id:"압축", args:{op:"unpack", path:"받은.zip", include:["*.pdf"]}}` → items 가 `[self:copy]`·`[self:read]` 로 흐른다.

- **요구:** "받은 zip 풀어서 안에 있는 PDF 만 모아 줘." "이 폴더 압축해서 메일에 붙여 줘."
- **현재:** copy/move/delete/mkdir 는 있으나 archive 가 없다. 첨부·다운로드 흐름의 앞뒤에 거의 항상 붙는 파일 원시 동작.
- **최소 능력:** op pack/unpack/list, zip 부터(tar·7z 는 후속), 경로 탈출(zip slip) 차단, 결과 파일 items.
- **구현 근거:** 표준 라이브러리 zipfile/shutil(외부 의존 없음).
- **판정:** 9번과 동일. 다만 zip 은 다운로드·메일 첨부 어휘와의 결합 빈도가 높아 승격 가능성이 더 크다.

## 다음에 볼 후보(이번 열 개에서 제외)

- **인쇄** `limbs:print` — `lp` 한 줄, 스크립트로 충분. 빈도 관찰 뒤.
- **스포츠 일정·결과** — 공식 무료 API 가 불안정, 웹 검색 대비 절약이 불확실.
- **병원·약국 진료시간/당번약국** — `[sense:place]` 가 위치는 찾고, 진료시간은 심평원 API 확장 검토(5번 뒤).
- **은행·카드 거래 수거** — 폰 결제 알림 포획·finance ingest 가 이미 그 자리를 맡고 있다(⏳실결제 관찰 중).

## 다음 판정 방법(1차와 동일)

각 후보의 자연어 과제를 해법 없이 실행자에게 주고 현재 경로(조합·스크립트·브라우저)와 비교한다.
(1) 새로 해낼 수 있게 된 일, (2) 같은 품질을 더 적은 호출·토큰·시간·재작업으로, (3) 다른 과제에서 재사용.
외부 쓰기(4·8번)는 상상행동 5-2-a 의 격리 조건을 갖춘 대역에서만 검증한다.

## 로컬 근거

- 카탈로그: `data/ibl_nodes.yaml`, `data/ibl_nodes_src/*.yaml`
- 환율 별칭: `data/packages/installed/tools/investment/handler.py`
- 폰 sms/share: `data/packages/installed/tools/android/ibl_actions.yaml`, `handler.py` `_act_sms`
- 날씨·패키지 선언 부패: `data/packages/installed/tools/location-services/ibl_actions.yaml` (description 424행)
- 읽기 형식: `data/packages/installed/tools/system_essentials/ibl_actions.yaml` read target_description, `data-ops/doc_formats.py`(pptx 는 emitter 만)
- 등록 스크립트: `data/scripts/registry.yaml` (이미지·압축·인쇄 관련 항목 없음)
