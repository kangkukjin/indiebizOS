# 5인 콘텐츠 연구팀 데이터 저장·분석 구조 조사 (기준일 2026-10-08)

> 전제(합성 시나리오): Linux 호스트 1대, 로컬 SSD, 20GB. 수집 프로세스 1개가 1분마다 소량 배치를 추가하고, 분석가 4명이 각자 별도 Python 프로세스로 SQL을 동시에 실행한다. 원천은 재수집할 수 있지만 사람 주석은 보존해야 한다. 실DB와 성능 측정 자료는 없다. 근거는 공식 문서 8건의 추출본이다. 이전 결정문이 주어지지 않아 비교할 기존 권고는 없다.

## 1. 원문 사실

### 1.1 동시성·프로세스 경계

| 제품 | 원문이 말하는 것 | 원문이 말하지 않는 것 |
|---|---|---|
| SQLite WAL | 읽기와 쓰기는 서로 막지 않지만 쓰기는 한 번에 하나다. 모든 프로세스가 같은 호스트에 있어야 하고 네트워크 FS에서는 동작하지 않는다 ([wal](https://www.sqlite.org/wal.html)). 읽기 트랜잭션은 시작 시점의 스냅샷을 본다 ([wal](https://www.sqlite.org/wal.html)). 기본값은 롤백 저널이다 ([wal](https://www.sqlite.org/wal.html)) | 분석 질의 성능, 20GB 규모에서의 동작 |
| DuckDB native | 읽기-쓰기 모드에서는 한 프로세스만 읽고 쓴다. READ_ONLY 모드에서는 여러 프로세스가 읽을 수 있지만 어느 프로세스도 쓸 수 없다 ([concurrency](https://duckdb.org/docs/stable/connect/concurrency)). 프로세스 내부의 여러 스레드는 MVCC·낙관적 제어로 쓰며, 같은 행을 동시에 수정하면 충돌 오류가 난다 ([concurrency](https://duckdb.org/docs/stable/connect/concurrency)) | NAS·공유 디렉터리에서 잠금이 실패하는 조건 |
| PostgreSQL 18 서버 | MVCC 아래에서 읽기와 쓰기가 서로 막지 않고, 각 문장은 스냅샷을 본다 ([mvcc](https://www.postgresql.org/docs/current/mvcc-intro.html)) | 프로세스 구조, 격리 수준별 세부(13.2절은 읽지 못함) |

### 1.2 백업·복구

- **SQLite**
  - Online Backup API는 다른 연결이 쓰면 보통 백업을 재시작한다. 재시작이 잦으면 백업이 끝나지 않을 수 있다 ([backup](https://www.sqlite.org/backup.html)).
  - `step(-1)`로 한 번에 복사하면 그동안 다른 쓰기를 막는다 ([backup](https://www.sqlite.org/backup.html)).
  - 다른 라이브 백업 수단으로 VACUUM INTO와 sqlite3_rsync가 있다 ([backup](https://www.sqlite.org/backup.html)).
  - WAL 파일은 DB의 영속 상태 일부다. 분리해 복사하면 커밋이 유실되거나 DB가 손상될 수 있다 ([wal](https://www.sqlite.org/wal.html)).
  - `synchronous=NORMAL`이면 정전 뒤 트랜잭션이 롤백될 수 있다 ([wal](https://www.sqlite.org/wal.html)).
- **DuckDB**
  - EXPORT DATABASE는 schema.sql, load.sql, 테이블별 데이터 파일을 만든다. IMPORT는 새 DB를 전제로 한다 ([export](https://duckdb.org/docs/stable/sql/statements/export)).
  - 내보내기의 스냅샷 시점과 동시 쓰기와의 관계는 미기재다.
- **PostgreSQL**
  - pg_dump는 시작 시점의 내부 일관 스냅샷을 만들며, 배타 잠금 작업을 빼면 다른 작업을 막지 않는다. 롤과 테이블스페이스는 덤프하지 않는다 ([dump](https://www.postgresql.org/docs/current/backup-dump.html)).
  - pg_dumpall은 DB 간 스냅샷을 동기화하지 않는다 ([dump](https://www.postgresql.org/docs/current/backup-dump.html)).
  - PITR은 클러스터 전체만 복구한다. 완료된 WAL 세그먼트만 아카이브되므로 아카이빙이 지연되면 손실이 늘며, archive_timeout으로 상한을 둔다 ([pitr](https://www.postgresql.org/docs/current/continuous-archiving.html)).
  - 설정 파일은 WAL로 복구되지 않는다. pg_wal이 가득 차면 PANIC으로 오프라인이 된다 ([pitr](https://www.postgresql.org/docs/current/continuous-archiving.html)).

### 1.3 native embedded가 아닌 제안

- **Quack**: DuckDB를 클라이언트-서버 DB로 만든다. v1.5.2 시점 베타이며, 2026년 가을 v2.0에서 성숙할 것으로 "예상"된다. 기준일 현재 출시·성숙 여부는 **미확인**이다 ([concurrency](https://duckdb.org/docs/stable/connect/concurrency)).
- **DuckLake + PostgreSQL 카탈로그**: 별도 저장 형식에 외부 PostgreSQL이 필요하다. v1.0 사양과 구현이 2026년 4월 운영용으로 공개되었다. 장애·복구 특성은 미확인이다 ([concurrency](https://duckdb.org/docs/stable/connect/concurrency)).
- **SQLite 원격 프록시**: 사용자가 직접 구현해야 하며 SQLite 내장 기능이 아니다 ([network](https://www.sqlite.org/useovernet.html)).

### 1.4 판본·불일치

- **SQLite 문서**: 판본 번호가 없고 갱신 시각만 있다(WAL 2026-08-25, 백업 2025-11-13, 네트워크 2022-06-22).
  - 대형 트랜잭션에 대해 "100MB 초과 시 느리고 1GB 초과 시 실패할 수 있다"는 서술과 "3.11.0부터 롤백 모드만큼 효율적"이라는 서술이 공존한다. 구판 서술이 남은 것으로 보이지만 단정할 수 없다 ([wal](https://www.sqlite.org/wal.html)).
  - 백업 스냅샷 시점을 1절은 복사 시작 시점, 3.1절은 재시작을 거친 완료 시점의 최신 상태로 서술한다. 어느 쪽인지 단정할 수 없다 ([backup](https://www.sqlite.org/backup.html)).
- **WAL-reset 버그**: 3.7.0~3.51.2에서 드물게 손상이 날 수 있다. 3.51.3(2026-03-13)에서 수정되었고 3.44.6·3.50.7에 백포트되었다. 2개 이상 연결이 동시에 쓰기 또는 체크포인트를 할 때만 발생하며, 2026-08-24 갱신에서 외부 재현법이 제시되었다 ([wal](https://www.sqlite.org/wal.html)).
- **DuckDB 문서**: stable 경로가 current로 해석되고 판본 표기가 없다.
- **PostgreSQL**: 근거는 18 문서다. 19는 Beta 4로 정식 출시가 아니다.
- 검색 요약은 근거로 쓰지 않았다.

## 2. 이 팀에 대한 비교 (추론)

| 기준 | SQLite WAL | DuckDB native | PostgreSQL 서버(동일 호스트 가능) |
|---|---|---|---|
| 프로세스 경계 | 같은 호스트에서 수집 1 + 분석 4 구성이 문서 조건에 부합한다 | 쓰기 프로세스 1개와 다른 분석 프로세스 4개가 **같은 파일을 동시에** 쓰는 구성은 원문이 지지하지 않는다 | 클라이언트 프로세스 다수가 서버에 접속한다 |
| 분석 적합성 | 원문 근거 없음(미확인) | 원문 근거 없음(RAM 캐싱은 설계 이유로만 언급) | 원문 근거 없음 |
| 일관 백업 | 1분 주기 쓰기가 백업 재시작을 유발할 수 있다 | 내보내기 일관성 미기재 | 덤프 시작 시점 스냅샷이 명시되어 있다 |
| 운영 복잡성 | 낮음. 단, 체크포인트와 버전 관리가 필요하다 | 단일 프로세스 사용이라면 낮음 | 서버·롤·아카이브 관리가 필요하다 |

분석 성능은 세 제품 모두 근거가 없으므로 측정 전에는 판단하지 않는다.

## 3. 권고 구조 (제안)

1. **기본안(제안)**: 같은 Linux 호스트에서 PostgreSQL 18 서버 하나를 주석과 수집의 기록 원본으로 둔다. 근거는 읽기·쓰기 비차단 ([mvcc](https://www.postgresql.org/docs/current/mvcc-intro.html))과 시작 시점이 명시된 덤프 ([dump](https://www.postgresql.org/docs/current/backup-dump.html))다. 주석 보존 요구가 있으면 PITR을 추가한다 ([pitr](https://www.postgresql.org/docs/current/continuous-archiving.html)).
2. **경량 대안(조건부)**: SQLite WAL. 도입 조건은 다음과 같다.
   - 모든 프로세스가 같은 호스트의 로컬 파일을 쓴다.
   - 버그 수정 판본(3.51.3, 3.44.6, 3.50.7 중 하나)을 확인한다 ([wal](https://www.sqlite.org/wal.html)).
   - 주석 쓰기 경로를 정해 쓰기 경합을 관리한다.
   - 실측에서 백업이 완료되는지 확인한다.
3. **조건부 스냅샷 대안**: DuckDB native는 기록 원본이 아니라 분석용 사본으로만 쓴다. 분석가가 READ_ONLY로 여는 사본을 주기적으로 만든다 ([concurrency](https://duckdb.org/docs/stable/connect/concurrency)). 이 사본이 어느 시점의 일관 상태인지는 원문 근거가 없으므로, 기준 시점을 확보하는 방법(예: 수집을 멈춘 뒤 생성)을 검증한 경우에만 쓴다.
4. **Quack 또는 DuckLake**: Quack은 성숙도 미확인, DuckLake는 별도 형식과 외부 PostgreSQL이 필요하다. 기준일 현재 도입을 보류한다(제안).

## 4. 실패 시나리오

- **SQLite**
  - 분석 리더가 끊이지 않으면 체크포인트가 완료되지 못해 WAL이 계속 커진다 ([wal](https://www.sqlite.org/wal.html)).
  - 크래시 뒤 복구 중에는 SQLITE_BUSY가 난다 ([wal](https://www.sqlite.org/wal.html)).
  - DB 파일만 복사하고 WAL 파일을 빠뜨리면 커밋이 유실된다 ([wal](https://www.sqlite.org/wal.html)).
- **DuckDB**: 두 번째 프로세스가 쓰기를 시도하면 원문상 허용되지 않는다 ([concurrency](https://duckdb.org/docs/stable/connect/concurrency)). 오류 형태는 미확인이다.
- **PostgreSQL**
  - 아카이브 실패로 pg_wal이 가득 차면 PANIC으로 오프라인이 된다 ([pitr](https://www.postgresql.org/docs/current/continuous-archiving.html)).
  - 롤이 없으면 원래 소유권으로 재생성하지 못한다. psql 복원 오류는 부분 복원 상태를 남긴다 ([dump](https://www.postgresql.org/docs/current/backup-dump.html)).
- **공통**: 백업 파일이 존재하거나 종료 코드가 0이라는 완료표시는 원천 트랜잭션 일관성과 다르다. 백업이나 PITR만으로는 어떤 장애에서도 주석 손실 0을 보장할 수 없다. 아카이브 지연분이 남고 ([pitr](https://www.postgresql.org/docs/current/continuous-archiving.html)), 원문은 RPO/RTO 수치를 제시하지 않는다. 허용 손실 범위, 다른 호스트·매체로의 보관, 주석 작성 경로는 팀에 **추가 요구사항으로 확인**해야 한다.

## 5. 백업·복구 검증 절차 (제안)

1. **globals 수집**: `pg_dumpall --globals-only`로 롤 등을 별도로 수집한다. 롤과 테이블스페이스는 pg_dump에 포함되지 않기 때문이다 ([dump](https://www.postgresql.org/docs/current/backup-dump.html)). 이 옵션명은 추출 근거에 없으므로 18 문서에서 재확인한다.
2. **덤프와 복원 형식을 짝지어 쓴다**:
   - `pg_dump -Fc` → `pg_restore`(필요 시 `-j`)
   - plain SQL → `psql`(`-1`, ON_ERROR_STOP)
   - 두 형식을 혼용하지 않는다 ([dump](https://www.postgresql.org/docs/current/backup-dump.html)).
3. **격리 대상에 복원한다**: globals를 먼저 복원한다. 그다음 template0에서 생성한 빈 DB에 복원하고 ANALYZE를 실행한다 ([dump](https://www.postgresql.org/docs/current/backup-dump.html)).
4. **지문을 비교한다**: 키와 행수만 보지 않는다. 주석 본문, 수정 이력, 삭제 표시 등 필수 값 전체의 지문을 **백업과 같은 스냅샷**에서 계산해 복원본의 지문과 비교한다.
   - 계속 변하는 원본의 백업 직전·직후 값과 단순 일치를 요구하지 않는다.
   - 기준 시점을 확보하지 못하면 결과를 "미검증"으로 판정한다.
5. **SQLite**: DB 파일과 WAL 파일을 함께 보존하고 ([wal](https://www.sqlite.org/wal.html)), 같은 방식의 지문 비교를 적용한다.
6. **PITR**: 설정 파일을 따로 백업하고, pg_backup_stop 이후 시점으로 복구 리허설을 한다 ([pitr](https://www.postgresql.org/docs/current/continuous-archiving.html)).

## 6. 측정할 항목 (제안)

허용 한계는 팀이 정하는 제안값이다.

| 측정량 | 관찰 | 판정 규칙(제안) |
|---|---|---|
| 분석 질의 지연(후보 3안, 같은 질의 세트) | 실제 작업 주기 동안 | 팀 한계 초과 시 해당 안 탈락 |
| SQLite 백업 완료 여부·재시작 횟수 | 수집이 동작하는 중 | 완료하지 못하면 경량 대안 불채택 |
| WAL·pg_wal 크기 추이 | 같은 기간 | 계속 증가하면 경보(최종 판정과는 별개) |
| 복원 지문 일치 | 리허설마다 | 불일치 또는 미검증이면 백업 체계 불채택 |
| 실제 복구 소요 | 리허설 | 요구 RTO가 확정된 뒤 비교 |

## 7. 미확인

- SQLite 문서 판본, 분석 성능, 백업 스냅샷의 정확한 기준 시점
- DuckDB 내보내기 일관성, Quack의 현재 성숙도, DuckLake의 장애·복구 특성
- PostgreSQL 13.2절 격리 수준 세부, 'How To Corrupt Your Database Files' 문서(읽지 못함)
- 세 제품 모두의 RPO/RTO와 용량별 성능