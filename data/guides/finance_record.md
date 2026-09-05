# 재무기록 ([self:finance]) 가이드

소비(지출·수입 거래)와 소유(자산·부채)를 한 원장에 기록하는 **재무 원장**.
계기: 💰 재무기록 (지출/통계/거래/자산/기록/올리기 6탭 — 지출 관리가 가장 빈번해 지출이 첫 탭).
health-record 와 대칭 구조. **구 [self:spend](지출내역)를 2026-08-14 흡수** — 결제 알림
수거는 이 액션의 `sync` op.

## 카드 지출 자동 수거 (op: sync — 구 spend 흡수)

1. 폰 포획소(알림 접근 허용)가 켜져 있으면 결제 알림은 **뜨는 순간 붙잡힌다** — 지워도 남는다.
   포획소가 꺼져 있을 때만 옛 규약(알림을 지우지 않고 모아두기)이 필요하다(활성 알림만 읽는 dumpsys 폴백).
2. 수거: `[self:finance]{op: "sync"}` (계기 지출 탭 '지금 수거하기').
   - **맥**: 폰을 USB 로 연결해야 한다(adb 로 폰 포획소를 당겨온다).
   - **폰**: 자기 포획소를 직접 읽어 **USB 없이** 수거한다(2026-09-05 — 포획소 파일 유무로 가르는 능력 게이트, source=`capture-local`).
3. 두 몸이 같은 결제를 두 번 적지 않는다 — ext_id 는 (앱|제목|본문)이라 수거 경로·시각과 무관하다.
   ★**하나카드는 같은 결제 알림을 7~238ms 간격으로 두 번 post 한다**(2026-09-05 포획소 실측: 하나카드 고유 알림 15건이 전부 2줄, 청주페이는 1줄).
   그래서 ext_id 에 시각을 넣으면 안 된다 — 넣었던 동안 원장에 모든 하나카드 결제가 2건씩 쌓였다.

- 수거된 결제는 **거래(지출)로 직접 병합**: 승인=+, 취소·환불=음수 지출(합계 자동 차감),
  충전(청주페이)=이체라 원장 제외. 파싱 실패 알림은 금액 0 + 원문 note 보존(침묵 실패 금지).
- 한계(정직 신고): 지운 알림·재부팅으로 사라진 알림은 수거 불가, 앱당 활성 알림 상한 ~24.
  놓친 결제는 월간 명세서 대사 또는 올리기(ingest)로 메꾼다.
- 수거 앱 추가 = `finance_sync.py` 의 `PAY_PKGS` 한 줄. 파서도 그 파일(원문 보존이라 재파싱 가능).
- 폰 선행 설정(1회, 2026-08-12 완료): 두 앱 시스템 알림 허용.

## 폰↔맥 원장 합치기 (2026-09-05)

두 몸이 각자 수거하므로 원장이 둘이다 — `finance_ledger_sync`(health_sync 의 동형 미러)가 합집합 머지한다.
`GET /finance/sync/export` 로 한쪽 스냅샷을 받아 `POST /finance/sync/merge` 로 다른 쪽에 밀면
머지 결과 + 그쪽 최신 스냅샷이 돌아온다(한 왕복 양방향, LWW·tombstone·멱등).

- 같은 결제를 두 몸이 각자 수거해도 **ext_id 가 같아 한 행으로 접힌다**(머지 통계의 `collided`).
- ★**주체 이름이 두 몸에서 같아야 한다**: owner uuid = `uuid5("finance-owner:"+이름)` 이라
  이름이 다르면(맥 '강국진' / 폰 기본값 '나') 같은 사람이 두 주체로 갈린다.
  각 몸의 `finance/config.json` 의 `default_owner` 를 같은 이름으로 맞출 것.

## 주체(owner) 축 — 개인/회사 분리

- 전 op 공통 `owner` 파라미터. **미지정=기본 주체**(`data/finance/config.json` 의 `default_owner`).
- 새 주체 등록 = 이름을 처음 쓰면 자동 생성. 예: `{op: "save", kind: "지출", amount: 50000, owner: "OO상사"}`
  → 이후 `{op: "query", owner: "OO상사"}` 로 회사 재무만 조회. 주체 목록=`query_type: "주체목록"`.
- 건강기록의 person 축과 같은 의미 — 개인/회사/가족 구성원의 원장이 한 DB에서 갈라진다.

## op

- **save**: 평탄형 저장.
  - 거래: `{op: "save", kind: "지출"|"수입", amount: 12000, category: "식비", counterparty: "김밥천국", date: "YYYY-MM-DD"}`
    — amount 는 원 단위 숫자("3.5만"/"1.2억" 한국식 단위 문자열도 수용).
  - 소유: `{op: "save", kind: "자산"|"부채", name: "신한은행 예금", value: 32000000, asset_type: "account"}`
    — **같은 name 을 다시 저장하면 새 시점 평가액**(이력이 곧 추이). asset_type: cash/account/securities/realestate/vehicle/loan/other.
- **query**: `query_type` 분기 — `summary`(기본, 이달 거래+순자산)/`거래`/`지출`/`수입`(거래 필터)/
  `자산`/`부채`(이름별 최신 스냅샷+순자산)/`검색`(keyword)/`주체목록`. 옵션: `month "YYYY-MM"`, `days`, `owner`.
  - 거래 조회는 `{text, table, blocks, points, items}` 통화 — table(날짜|구분|분류|거래처|금액)은
    `>> [table:chart]` 파이프 직결, points=일자별 지출 합계(sparkline).
- **delete**: `record_type`(transaction/holding) + `record_id`(조회 출력의 #번호). soft-delete(tombstone).
- **ingest**: `file`(영수증 사진·엑셀 가계부·PDF·txt/csv 경로) 또는 `text` → **공용 ingest 엔진**
  (`backend/services/ingest_engine.py` — health 와 같은 엔진, 스키마만 재무)로 구조화 후 일괄 저장.
  영수증=합계 1건 expense(품목은 note), 가계부 표=행마다 거래 1건. 금액 없는 거래는 지어내지 않고
  건너뜀+사유 반환. 영수증/PDF 원본은 `data/finance/files/` 에 사본 보존.

## 저장 구조

- DB: `data/finance/finance_records.db` — owners/transactions/holdings 3테이블, uuid·soft-delete
  (health 선례, 동기화 대비). 폰에서는 `INDIEBIZ_USERDATA/finance/`.
- **기본 주체 = `data/finance/config.json` 의 `default_owner`** (코드에 실명 없음 — '명사의 자리').

## 구 [self:spend] 은퇴 기록 (2026-08-14 합병)

- 옛 spend(list/summary/sync)는 이 액션으로 전부 흡수: list→`query`(query_type 지출, source
  필터), summary→`query`(summary — hana/cjpay·상위 가맹점 라벨), sync→`sync`.
- spending 패키지=not_installed 이동, 옛 원장(빈 상태였음)=`data/_backups/2026-08-14_spend_merge_spending.db`.
- **되살리지 말 것** — 지출은 재무 원장의 부분집합이라 한 어휘가 맞다(사용자 판정).

## 함정

- 거래 save 에 amount 가 비면 저장 거부(조용한 손실 방지).
- 소유 조회는 기본 이름별 최신만 — 전체 이력은 storage.holding_history (추이 계기는 후속).
- record_id 는 조회 출력의 (#번호)에서. owner 지정 delete 는 그 주체 것만(오삭제 방지).

## 실측 기록 (자동 누적)

> 실행 에이전트가 턴 종료 후 덧붙인다.
- 2026-09-05 실측: 라이브 코드로 sync 를 다시 읽어 실행하면 중복이 접히지만, 이미 도는 백엔드 프로세스는 옛 `finance_sync` 모듈을 그대로 들고 있어 재시작 전까지 수정이 반영되지 않는다 — 수거 수정 후엔 실측을 새 프로세스가 아니라 재시작한 백엔드로 확인해야 한다.
