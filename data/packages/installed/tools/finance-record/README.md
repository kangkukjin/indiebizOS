# Finance Record

에이전트가 사용자의 재무 정보를 기록하고 조회할 수 있게 합니다.
소비(지출·수입 거래)와 소유(자산·부채 스냅샷)를 주체(owner)별로 관리합니다.

## 주요 기능
- 지출·수입 거래 저장/조회 (월간 요약, 분류별 상위)
- 자산·부채 소유 현황 (이름별 최신 평가액, 순자산)
- 다중 주체 지원 — 개인/회사 재무 분리 (기본 주체=data/finance/config.json)
- ingest — 영수증 사진·엑셀 가계부·PDF·텍스트를 AI가 구조화해 일괄 적재
  (공용 backend/services/ingest_engine.py 둘째 소비자)

## 관련
- 구 [self:spend](지출내역)는 2026-08-14 이 액션으로 흡수 — 결제 알림 수거=`op: sync`
  (finance_sync.py, 하나카드·청주페이). 옛 spending 패키지=not_installed.
- health-record 와 대칭 구조 (soft-delete·config 기반 기본 주체·공용 ingest 엔진).
