# 5명 콘텐츠 연구팀의 데이터 저장·분석 구조 — SQLite(WAL)·DuckDB(native)·PostgreSQL 비교

- 기준일: 2026-10-08 / 합성 시나리오(실제 DB·성능 측정 없음)
- 조건: Linux 1대, 로컬 SSD, 데이터 20GB, Python 수집 프로세스 1개가 1분마다 작은 배치 추가, 분석가 4명이 각자 별도 Python 프로세스로 동시에 SQL 분석. 원천은 재수집 가능, **사람의 주석은 잃으면 안 됨**.
- 근거 원칙: sqlite.org·duckdb.org·postgresql.org 공식 문서·공식 블로그·릴리스 페이지만 핵심 근거로 사용. 모든 원문은 2026-10-08에 직접 크롤해 해당 대목을 읽었다(상세: `source_notes.md`, 주장별 근거: `evidence.json`).
- 표기: **[원문]** = 공식 문서에 적힌 사실(URL 첨부), **[추론]** = 이 팀 조건에 적용한 나의 해석, **[제안]** = 권고·절차. 이 문서의 어떤 처리량·지연·손실시간(RPO/RTO) 수치도 원문에 없으므로 만들지 않았다. 원문에 있는 수치(예: SQLite 자동 체크포인트 1000 페이지)만 인용한다.

---

## 0. 요약 결론

1. **결정 축은 "서로 다른 OS 프로세스 1개가 쓰고 4개가 읽는다"이다.** DuckDB native 파일은 공식 문서상 "한 프로세스가 읽기·쓰기" 또는 "여러 프로세스가 읽기 전용(아무도 쓰지 않음)" 둘 중 하나다. 따라서 수집 프로세스가 쓰는 동안 분석가 4명이 같은 `.duckdb` 파일을 여는 구조는 native embedded로는 성립하지 않는다. SQLite WAL은 같은 호스트에서 1 writer + 여러 reader 프로세스를 지원한다. PostgreSQL은 다중 세션 MVCC 서버다.
2. **주석 데이터는 여러 사람이 쓰는 데이터일 가능성이 높다**(분석가가 주석을 단다고 가정, 미확인 — 6장 측정 항목). 그렇다면 writer는 1개가 아니라 1+α개가 되고, "동시 쓰기 + 일관 백업 + 시점 복구"를 공식적으로 갖춘 PostgreSQL이 주석의 기록 시스템으로 가장 안전하다.
3. **권고(A)**: PostgreSQL 18(현행 메이저)을 주석·원천 적재의 기록 시스템으로 두고, 분석가는 각자 Python 프로세스 안에서 DuckDB(in-process)로 분석한다 — PostgreSQL을 `postgres` 확장으로 읽기 전용 ATTACH하거나, 주기적으로 만든 Parquet 스냅샷을 읽는다. 주석은 `pg_basebackup` + WAL 아카이빙(PITR)으로 보호하고 `pg_dump` 논리 백업을 보조로 둔다.
4. **대안(B)**: 운영 인력이 정말 없고 주석 쓰기가 드물다면 SQLite(WAL) 두 파일(원천/주석) + 분석가별 DuckDB 읽기. 백업은 Online Backup API 또는 `VACUUM INTO`, 다른 호스트로는 `sqlite3_rsync`. PITR은 없다.
5. **보류(C/D)**: DuckDB의 다중 프로세스 쓰기 경로인 Quack 원격 프로토콜은 **베타**이고, DuckLake 1.0은 **생산용으로 공개(2026-04)**됐지만 PostgreSQL 카탈로그를 전제로 하므로 이 팀 규모에서는 A에 비해 얻는 것이 적다(추론). 2.0 출시 뒤 재평가.

---

## 1. 원문 사실 표 (판본 포함)

### 1.1 SQLite (WAL) — 현행 3.53.x 계열, chronology 최상단 3.53.4(2026-07-24)

| 축 | 원문 사실 | URL |
|---|---|---|
| 동시성 | "readers do not block writers and a writer does not block readers" | https://www.sqlite.org/wal.html |
| 동시성 | "since there is only one WAL file, there can only be one writer at a time" | https://www.sqlite.org/wal.html |
| 프로세스 경계 | "All processes using a database must be on the same host computer; WAL does not work over a network filesystem" (wal-index 공유 메모리 때문) | https://www.sqlite.org/wal.html |
| 프로세스 경계 | 읽기 트랜잭션은 시작 시 "end mark"를 고정해 한 시점의 내용만 본다. 독자는 별도 프로세스에 있을 수 있다 | https://www.sqlite.org/wal.html |
| 운영 | 읽기 전용 WAL DB를 열려면 `-shm` 파일 쓰기 권한 또는 디렉터리 쓰기 권한이 필요 | https://www.sqlite.org/wal.html |
| 운영 | 기본 자동 체크포인트는 WAL이 1000 페이지에 이르면 실행. 오래 지속되는 읽기 트랜잭션은 체크포인트 진행을 막을 수 있다 | https://www.sqlite.org/wal.html |
| 내구성 | `synchronous=NORMAL`에서 체크포인트를 별도 스레드·프로세스로 돌리면 "transactions are no longer durable and might rollback following a power failure or hard reset" | https://www.sqlite.org/wal.html |
| 백업 | Online Backup API: 완료 시 대상이 "copying commenced" 시점의 비트 단위 동일 사본("snapshot"), 점진 복사 가능 | https://www.sqlite.org/backup.html |
| 백업 | `VACUUM INTO`: 출력은 "a consistent snapshot of the original database". 중단·전원 손실 시 출력이 불완전·손상될 수 있음. 원본의 synchronous가 NORMAL/FULL이면 출력에 fsync | https://www.sqlite.org/lang_vacuum.html |
| 백업 | 트랜잭션 도중 파일 복사는 손상 사본을 만들 수 있다. 직전 쓰기가 실패했다면 `-wal`/`-journal`을 DB 파일과 함께 복사해야 한다 | https://www.sqlite.org/howtocorrupt.html |
| 백업(별도 도구) | `sqlite3_rsync`: 라이브 DB를 SSH(또는 로컬)로 복제, 시작 시점의 "fully-consistent snapshot". 3.47.0(2024-10-21)부터 제공, WAL·같은 page size 제약은 3.50.0(2025-05-29)에서 제거 | https://www.sqlite.org/rsync.html , https://www.sqlite.org/howtocorrupt.html |
| 분석 적합성 | 공식 문서가 "Data analysis"를 용도로 든다. 동시에 "Situations Where A Client/Server RDBMS May Work Better" 절을 두며 client/server는 동시성·중앙화를 강조한다고 설명한다(해당 절의 세부 항목은 미열람) | https://www.sqlite.org/whentouse.html |

### 1.2 DuckDB (native 파일, embedded) — 문서 "1.5 current", 최신 릴리스 1.5.6(2026-09-28)

| 축 | 원문 사실 | URL |
|---|---|---|
| 프로세스 경계 | "Read-write mode: one process can both read and write to the database. Read-only mode: multiple processes can read from the database, but no processes can write" | https://duckdb.org/docs/current/connect/concurrency |
| 프로세스 경계 | 쓰기 스레드 여러 개는 MVCC+낙관적 동시성 제어로 지원하나 "all within that single writer process" | https://duckdb.org/docs/current/connect/concurrency |
| 동시성 | 같은 행을 동시에 수정하면 conflict 오류, 흔한 대응은 트랜잭션 재실행 | https://duckdb.org/docs/current/connect/concurrency |
| 운영 | 파일 락으로 동시 접근을 다루며 공유 디렉터리·NAS에서는 각별히 주의 | https://duckdb.org/docs/current/connect/concurrency |
| 다중 프로세스 쓰기(별도 프로토콜) | "supported through the Quack remote protocol, which turns DuckDB into a client-server database. Quack in beta stage as of DuckDB v1.5.2, and is expected to become mature by DuckDB v2.0 in fall 2026" | https://duckdb.org/docs/current/connect/concurrency |
| Quack 성숙도 | "under active development and the protocol, function names, settings, and defaults are still subject to change", "beta release of Quack, available in DuckDB v1.5.3" | https://duckdb.org/docs/current/quack/overview |
| 다른 저장 형식 | "For a stable solution, consider using the DuckLake format with PostgreSQL as the catalog database"; DuckLake v1.0 사양과 DuckDB 구현은 2026-04 "intended for production use" | https://duckdb.org/docs/current/connect/concurrency , https://duckdb.org/docs/current/core_extensions/ducklake , https://duckdb.org/2026/04/13/ducklake-10 |
| 백업 | `EXPORT DATABASE`는 디렉터리로 schema.sql·load.sql·테이블 파일(CSV 또는 Parquet) 생성, `IMPORT DATABASE`는 **빈 DB**에 넣어야 함(기존 객체가 있으면 already exists 오류) | https://duckdb.org/docs/current/sql/statements/export |
| 백업 보조 | `CHECKPOINT`는 WAL을 데이터 파일에 동기화. v1.4부터 `FORCE CHECKPOINT`는 진행 중 트랜잭션을 중단하지 않고 체크포인트 락을 기다림 | https://duckdb.org/docs/current/sql/statements/checkpoint |
| 분석 적합성 | OLAP 지향, columnar-vectorized 실행 엔진, 서버 설치 없음, in-process | https://duckdb.org/why_duckdb |
| 외부 연결(확장) | `postgres` 확장: 실행 중인 PostgreSQL을 ATTACH해 읽기·쓰기, `READ_ONLY` 옵션 있음 / `sqlite` 확장: SQLite 파일 읽기·쓰기 | https://duckdb.org/docs/current/core_extensions/postgres/overview , https://duckdb.org/docs/current/core_extensions/sqlite |
| 판본 | 릴리스 달력: 2.0.0 예정 2026-10-21, 2.0.1 예정 2026-11-18("tentative"). v1.4부터 격번 LTS | https://duckdb.org/release_calendar |

### 1.3 PostgreSQL (서버) — 현행 메이저 18(최초 2025-09-25, 현 minor 18.6, 지원 종료 2030-11-14)

| 축 | 원문 사실 | URL |
|---|---|---|
| 동시성 | MVCC로 각 문장이 스냅샷을 보며 "reading never blocks writing and writing never blocks reading", SSI 직렬화 수준에서도 유지 | https://www.postgresql.org/docs/current/mvcc-intro.html |
| 백업 3방식 | SQL dump / File system level backup / Continuous archiving | https://www.postgresql.org/docs/current/backup.html |
| 논리 백업 | pg_dump는 "consistent exports even if the database is being used concurrently", 읽기·쓰기 사용자를 막지 않음. 단 "generally not the right choice for taking regular backups of production databases" | https://www.postgresql.org/docs/current/app-pgdump.html |
| 논리 백업 | 덤프는 pg_dump 시작 시점 스냅샷. 배타 락이 필요한 연산(대부분 ALTER TABLE)은 예외. 역할·테이블스페이스는 pg_dumpall(--globals-only)로 따로. 새 판본으로 재적재 가능 | https://www.postgresql.org/docs/current/backup-dump.html |
| 물리 백업 | pg_basebackup은 실행 중인 클러스터를 다른 클라이언트에 영향 없이 백업, PITR 출발점으로 사용, 전체·증분 백업 가능 | https://www.postgresql.org/docs/current/app-pgbasebackup.html |
| PITR | WAL 재생을 임의 시점에서 멈춰 "consistent snapshot" 복구 가능. 백업 시작 시점까지 거슬러 올라가는 **연속된** 아카이브 WAL이 필요. 아카이브 절차를 먼저 설정·시험하라고 권함. 아카이브는 기존 파일 덮어쓰기를 거부하도록 설계하라고 권함 | https://www.postgresql.org/docs/current/continuous-archiving.html |
| 판본 | 메이저 5년 지원, 항상 현재 minor 실행 권장. 19는 개발판(2026-09-24 Beta 4) | https://www.postgresql.org/support/versioning/ |

---

## 2. 네 축 비교 (원문 → 이 팀 적용 추론)

### 2.1 동시 읽기/쓰기의 프로세스 경계

| | SQLite WAL | DuckDB native | PostgreSQL |
|---|---|---|---|
| [원문] writer | 한 번에 1개(프로세스 무관), 같은 호스트 | 1개 **프로세스**(내부 다중 스레드) | 다중 세션 MVCC |
| [원문] reader | 다른 프로세스 가능, 쓰기와 서로 막지 않음 | 여러 프로세스는 **모두 읽기 전용**일 때만 | 다중 세션 |
| [추론] 1 수집 + 4 분석 프로세스 | 성립(같은 로컬 SSD 조건 충족) | **native 파일 하나로는 불성립** — 수집이 read-write로 열면 다른 프로세스는 같은 파일을 열 수 없다는 것이 모델의 귀결 | 성립 |
| [추론] 분석가가 주석을 쓰면 | 쓰기가 직렬화됨. 수집 배치·주석 쓰기가 서로 대기 → 재시도 처리 필요 | native로는 분석 프로세스가 쓸 수 없음 | 자연스럽게 지원 |

[추론] DuckDB에서 "공유 파일 하나"를 쓰려면 (a) 수집을 끝낸 뒤 read-only로만 여는 시간 분할, (b) Quack(베타) 서버, (c) DuckLake+PostgreSQL 카탈로그 중 하나여야 한다. (a)는 1분 주기 적재와 상시 분석을 동시에 만족하지 못한다.

### 2.2 분석 적합성

- [원문] DuckDB는 OLAP·columnar-vectorized이며 행 단위 처리 시스템(PostgreSQL·SQLite 포함)보다 OLAP 쿼리에서 오버헤드가 적다고 **DuckDB 자신이** 설명한다(https://duckdb.org/why_duckdb). 이것은 경쟁 제품 측 주장이므로 중립 벤치마크가 아니다.
- [원문] SQLite 공식 문서도 데이터 분석 용도를 든다(https://www.sqlite.org/whentouse.html).
- [추론] 20GB 전체 스캔·집계·조인이 분석의 중심이라면 분석 엔진으로 DuckDB를 쓰는 편이 유리할 가능성이 높다. 그러나 이 팀의 실제 쿼리 형태(점 조회 vs 전체 집계)와 속도 요구는 미확인이며 측정 전에는 결론 내리지 않는다(6장).
- [추론] DuckDB를 "저장소"가 아니라 "각 분석가 프로세스 안의 엔진"으로 쓰면 프로세스 경계 문제를 피하면서 분석 이점을 얻는다. 원천은 `postgres`/`sqlite` 확장 ATTACH(READ_ONLY) 또는 Parquet 스냅샷으로 공급한다.

### 2.3 일관된 백업·복구

| | 일관 백업 수단(원문) | 시점 복구 | 주의(원문) |
|---|---|---|---|
| SQLite | Online Backup API, VACUUM INTO, sqlite3_rsync | 없음(스냅샷 단위) | 트랜잭션 중 cp 금지, -wal 동반 필요, VACUUM INTO 중단 시 출력 손상 가능 |
| DuckDB | EXPORT DATABASE → IMPORT DATABASE(빈 DB) | 없음(스냅샷 단위) | EXPORT의 트랜잭션 일관성 보장 문구는 **이번에 읽은 범위에서 확인 못 함(미확인)** |
| PostgreSQL | pg_dump(논리, 시작 시점 스냅샷), pg_basebackup + WAL 아카이빙 | **PITR 있음** | WAL 아카이브의 연속성이 끊기면 복구 불가, 역할 등은 globals 별도 |

[추론] "주석을 잃으면 안 된다"는 요구는 "마지막 백업 이후의 주석도"를 포함할 가능성이 크다. 스냅샷 백업만 있는 SQLite/DuckDB는 백업 간격만큼의 주석을 잃을 수 있고, PostgreSQL은 연속 WAL 아카이빙으로 그 창을 줄일 수 있다. 다만 **얼마만큼 줄어드는지는 원문이 수치로 보장하지 않으므로** 여기서도 수치를 제시하지 않는다(아카이빙 주기·저장 위치 설계와 리허설로 팀이 정해야 함).

[추론] 모든 백업이 같은 SSD에 있으면 SSD 고장 시 원본과 함께 잃는다. 주석 백업은 다른 물리 매체·다른 호스트로 보내야 한다.

### 2.4 운영 복잡성

- [원문] DuckDB: 설치·갱신할 서버 소프트웨어 없음(https://duckdb.org/why_duckdb). SQLite: 단일 파일, 설치·사용이 쉬움(https://www.sqlite.org/whentouse.html).
- [원문] PostgreSQL: WAL 아카이빙을 위해 `wal_level`, `archive_mode`, `archive_command`/`archive_library` 설정이 필요, pg_basebackup은 REPLICATION 권한과 pg_hba.conf 허용 필요(https://www.postgresql.org/docs/current/continuous-archiving.html , https://www.postgresql.org/docs/current/app-pgbasebackup.html). 메이저는 5년 지원(https://www.postgresql.org/support/versioning/).
- [추론] 운영 부담 순서: SQLite < DuckDB native(단, 다중 프로세스 문제를 우회하는 추가 구조가 필요하면 역전) < PostgreSQL. PostgreSQL의 추가 부담은 서버 프로세스·계정·설정·아카이브 감시·메이저 업그레이드이며, 이는 주석 보호(PITR)와 맞바꾸는 비용이다.

---

## 3. native embedded와 구분해야 할 것 (성숙도·판본)

| 항목 | 성격 | 성숙도(원문) | 판본·날짜 | 이 팀 판단 |
|---|---|---|---|---|
| DuckDB native 파일 | embedded | 안정(정식 기능) | 문서 1.5 current / 1.5.6 | 단일 writer 프로세스 제약 |
| DuckDB Quack | **별도 서버 프로토콜**(HTTP, 확장) | **베타**, 프로토콜·이름·기본값 변경 가능 | concurrency 문서 "v1.5.2 기준 베타", Quack 문서 "v1.5.3에서 베타 제공", v2.0(가을 2026)에 성숙 "예상" | 주석 기록 시스템으로 지금 채택하지 않음 |
| DuckLake | **다른 저장 형식**(카탈로그 DB + 데이터 파일) | v1.0 "Production-Readiness" | 2026-04(블로그 URL 2026-04-13) | PostgreSQL 카탈로그 전제 — 데이터 증가·다중 writer 레이크가 필요할 때 후보 |
| DuckDB postgres/sqlite 확장 | **외부 DB 연결 확장** | 문서에 실험 표기 없음, 단 postgres 확장의 filter pushdown 옵션은 "currently experimental" | 1.5 current | 분석가 프로세스에서 읽기 전용 ATTACH 용도 |
| SQLite sqlite3_rsync | **별도 유틸리티**(SSH) | 공식 배포 프로그램(성숙도 표기 없음 → 미확인) | 3.47.0 도입, 3.50.0 제약 제거 | 다른 호스트로 주석 사본 전송 후보 |
| 서드파티 SQLite 복제 도구 | 공식 밖 | 이번 조사 범위 밖(미확인) | — | 공식 문서만 근거로 하므로 평가하지 않음 |
| PostgreSQL 19 | 개발판 | Beta 4(2026-09-24) | — | 채택하지 않음, 18 사용 |

---

## 4. 권고 구조와 대안

### 4.1 권고 A — PostgreSQL 기록 시스템 + 분석가별 in-process DuckDB [제안]

```
수집 프로세스 ──INSERT(1분 배치)──▶ PostgreSQL 18
                                     ├─ schema raw   (재수집 가능)
                                     └─ schema annot (사람 주석, 보호 대상)
분석가 1..4 (각자 Python)
   ├─ 주석 작성/수정 ──▶ PostgreSQL annot (일반 트랜잭션)
   └─ 분석: 프로세스 내 DuckDB
        ├─ ATTACH PostgreSQL (TYPE postgres, READ_ONLY)
        └─ 또는 raw의 Parquet 스냅샷(주기 export) 읽기
백업: pg_basebackup(주기) + WAL 아카이빙 → 다른 매체/호스트
      + pg_dump -n annot (논리, 판본 이식용) + pg_dumpall --globals-only
```

- 근거 연결: 다중 프로세스 읽기·쓰기(mvcc-intro), PITR(continuous-archiving), 실행 중 백업(app-pgbasebackup), 판본 이식 가능한 논리 사본(backup-dump), 분석 엔진(why_duckdb), 외부 ATTACH(postgres 확장).
- **도입 조건**: (1) 팀에 PostgreSQL 서버를 띄우고 감시할 사람이 최소 1명 있다. (2) 분석가가 주석을 쓴다(쓰기 주체가 여럿). (3) "마지막 스냅샷 이후 주석 손실"을 받아들일 수 없다. (4) 백업을 보낼 별도 매체·호스트가 있다.
- **raw를 PostgreSQL에 둘지**: 20GB 집계를 DuckDB의 postgres 스캔으로 감당할 수 있는지는 미측정. 부족하면 raw만 Parquet 파일(수집기가 직접 쓰기)로 분리하고 PostgreSQL엔 주석과 메타데이터만 두는 변형(A′)을 쓴다. 원천은 재수집 가능하므로 Parquet raw는 백업 대상에서 낮은 등급으로 둘 수 있다(추론).

### 4.2 대안 B — SQLite(WAL) 두 파일 + 분석가별 DuckDB [제안]

- `raw.db`(수집기 단독 쓰기), `annot.db`(분석가 주석 쓰기) 분리. 분석가는 각자 SQLite 연결 또는 DuckDB `sqlite` 확장으로 읽음.
- 백업: `annot.db`는 Online Backup API 또는 `VACUUM INTO`로 주기 스냅샷 → `sqlite3_rsync`로 다른 호스트에 일관 사본. `raw.db`는 재수집 가능하므로 낮은 빈도.
- 내구성: 원문상 `synchronous=NORMAL` + 별도 체크포인트 구성은 전원 손실 시 커밋이 롤백될 수 있으므로 **annot.db는 그 구성을 피하고** 원문의 durability 조건을 확인한 설정을 쓴다(구체 설정값의 durability 의미는 PRAGMA synchronous 문서를 별도로 읽어 확정할 것 — 이번 조사에서 해당 페이지는 미열람).
- **도입 조건**: 모든 프로세스가 같은 Linux 호스트·로컬 파일시스템(NFS 등 금지), 주석 쓰기 빈도가 낮아 직렬화 대기가 문제가 되지 않음(측정 필요), 스냅샷 간격만큼의 주석 손실 위험을 팀이 명시적으로 수용, 서버 운영 인력이 없음.
- 장점: 서버 없음, 파일 단위 사본이 쉬움. 단점: PITR 없음, 쓰기 직렬화, 긴 분석 트랜잭션이 체크포인트를 막아 WAL이 커질 수 있음.

### 4.3 대안 C — DuckDB native 단일 writer + Parquet 스냅샷 [제안, 조건부]

- 수집기만 `.duckdb`를 read-write로 소유하고 주기적으로 `EXPORT DATABASE ... (FORMAT parquet)` 또는 Parquet COPY로 스냅샷 디렉터리를 만든다. 분석가는 스냅샷을 각자 DuckDB로 읽는다. **주석은 이 파일에 넣지 않고** A(PostgreSQL) 또는 B(annot.db)에 둔다.
- 조건: 분석가가 스냅샷 주기만큼 늦은 데이터로 충분함. EXPORT의 트랜잭션 일관성 문구는 미확인이므로 스냅샷 완료 표식(예: 완료 후 디렉터리 원자적 이름 변경)을 팀이 설계해야 한다(추론).

### 4.4 보류 D — Quack / DuckLake

- Quack: 베타이고 변경 가능 문구가 명시돼 있으므로 "잃으면 안 되는" 주석의 경로로는 채택하지 않는다. DuckDB 2.0(예정 2026-10-21, tentative) 이후 공식 문서의 성숙도 표기가 바뀌면 재평가.
- DuckLake 1.0: 생산용이지만 카탈로그로 PostgreSQL을 권하므로 결국 PostgreSQL 운영이 필요하다. 20GB·5명 규모에서 A 대비 추가 이점은 아직 불명확(추론). 데이터가 레이크 규모로 커지거나 여러 writer가 대용량을 쓰게 되면 후보.

---

## 5. 실패 시나리오

| # | 시나리오 | 근거(원문) | 영향(추론) | 예방·대응(제안) |
|---|---|---|---|---|
| F1 | 실행 중 SQLite 파일을 `cp`/rsync로 복사, `-wal` 누락 | howtocorrupt.html, backup.html | 백업에 신·구 내용 혼재 → 손상, 주석 손실 | Backup API·VACUUM INTO·sqlite3_rsync만 사용, 파일 복사 금지 규칙 |
| F2 | DuckDB 파일을 수집기가 열고 있는 동안 분석가 프로세스가 같은 파일을 열려 함 | connect/concurrency | 분석 프로세스 열기 실패, 또는 수집기 정지 강요 | 구조 C(스냅샷) 또는 A로 회피 |
| F3 | DB 파일을 NFS/공유 디렉터리로 옮김 | wal.html, connect/concurrency | SQLite WAL 비작동, DuckDB 파일 락 문제 | 로컬 SSD 고정, 원격 접근은 서버(A)로 |
| F4 | 분석가의 긴 읽기 트랜잭션이 SQLite 체크포인트를 막음 | wal.html | WAL 파일 성장, 디스크 압박 | 분석 연결의 트랜잭션을 짧게, WAL 크기 감시(측정 항목) |
| F5 | `synchronous=NORMAL` + 별도 체크포인트 구성에서 전원 손실 | wal.html | 커밋된 주석이 롤백될 수 있음 | annot.db에 그 구성 금지 |
| F6 | VACUUM INTO 도중 전원 손실 | lang_vacuum.html | 백업 파일 불완전·손상 | 완료 후 검증(7장)을 거친 사본만 "유효"로 표시 |
| F7 | PostgreSQL WAL 아카이브 중간 파일 누락 | continuous-archiving.html | 누락 이후 시점으로 PITR 불가 | 아카이브 연속성 점검, 덮어쓰기 거부 명령 |
| F8 | pg_dump만 있고 역할·권한(globals) 없음 | backup-dump.html | 복구 후 권한 재구성 필요 | pg_dumpall --globals-only 병행 |
| F9 | 파일 시스템 백업을 다른 PostgreSQL 메이저에서 복구 시도 | backup-dump.html("extremely server-version-specific") | 복구 불가 | 같은 메이저 바이너리 보관, 판본 이식은 pg_dump |
| F10 | DuckDB IMPORT를 비어 있지 않은 DB에 실행 | sql/statements/export | already exists 오류 | 항상 새 빈 DB로 복원 |
| F11 | DuckDB 동시 UPDATE 충돌 | connect/concurrency | 트랜잭션 오류 | 재시도 로직 |
| F12 | 모든 백업이 같은 SSD | (추론) | SSD 고장 시 전부 소실 | 다른 매체·호스트 사본 |
| F13 | Quack 프로토콜·기본값 변경 | quack/overview | 업그레이드 후 클라이언트 비호환 | 채택 보류 |

---

## 6. 아직 측정해야 할 항목 [제안]

원문은 이 팀 조건의 성능·손실시간을 알려주지 않는다. 다음은 **스테이징 환경에서 팀이 측정**해야 한다(이 보고서 작성 중에는 아무 DB도 만들지 않았다).

1. 업무 사실: 주석을 쓰는 주체(분석가 4명 모두? 별도 도구?), 시간당 주석 쓰기 건수, 주석 1건 크기, 주석 수정·삭제 여부.
2. 팀이 허용할 주석 손실 창(RPO)과 복구 소요(RTO) — 수치는 팀의 결정이며 원문에서 오지 않는다.
3. 대표 분석 쿼리 10~20개의 응답 시간: (a) PostgreSQL 직접, (b) DuckDB postgres ATTACH, (c) DuckDB on Parquet 스냅샷, (d) SQLite 직접, (e) DuckDB sqlite ATTACH.
4. 1분 배치 적재와 4명 동시 분석이 겹칠 때 적재 지연·대기·SQLITE_BUSY·재시도 빈도.
5. SQLite WAL 파일 크기 추이(긴 분석 트랜잭션 유무별), 체크포인트 소요.
6. 백업 소요·크기: Backup API vs VACUUM INTO vs sqlite3_rsync / pg_basebackup 전체·증분 / pg_dump(annot) / EXPORT DATABASE.
7. 복원 소요: 각 방식으로 빈 환경에 복원해 질의 가능 상태가 되기까지.
8. PITR 정밀도: 목표 시각으로 복구했을 때 그 직전 주석이 존재하는지.
9. WAL 아카이브 생성량·저장 공간, 아카이브 실패 감지 시간.
10. 데이터 증가율(20GB → ?)과 Parquet 스냅샷 저장 공간.
11. DuckDB 2.0 출시 후 Quack 성숙도 표기 변화(문서 재확인 항목).

---

## 7. 백업·복구 검증 절차 (팀이 실행할 문서화된 절차) [제안]

> 이 절차는 문서화만 했으며 이 컴퓨터에서 실행하지 않았다.

### 7.1 공통 원칙
- 백업은 **복원해 본 것만 유효**하다. 주 1회 이상(빈도는 팀이 RPO에 맞춰 정함) 별도 스테이징 디렉터리·호스트에서 복원 리허설.
- 주석 테이블의 "검증 지문"을 정의: 행 수, 기본키 최솟값·최댓값, 최근 수정 시각 최댓값, 정렬된 (id, updated_at, 본문 해시)의 집계 해시. 원본에서 백업 직전 기록 → 복원본에서 재계산 → 일치 확인. (원본은 계속 변하므로 "백업 시작 시점 이전에 커밋된 주석이 모두 있는지"로 판정.)
- 결과를 날짜·방식·소요·불일치 여부로 기록.

### 7.2 PostgreSQL(권고 A)
1. 아카이브 설정을 먼저 시험(원문 권고): 아카이브 디렉터리에 WAL 파일이 생기고, 같은 이름 파일 덮어쓰기가 거부되는지 확인.
2. pg_basebackup으로 베이스 백업 → 다른 매체로 전송.
3. 리허설 A(최신 복구): 스테이징에 베이스 백업 배치 → restore_command로 아카이브 WAL 재생 → 서버 기동 → 7.1 지문 비교.
4. 리허설 B(PITR): 테스트 주석을 시각 T1에 넣고 T2에 "실수로" 삭제 → recovery_target_time을 T1과 T2 사이로 복구 → 테스트 주석 존재 확인.
5. 리허설 C(논리): `pg_dump -n annot` 사본을 `pg_restore`로 빈 DB에 복원 + globals 적용 → 지문 비교.
6. 아카이브 연속성 점검: 베이스 백업 시작 이후 WAL 파일 이름 순번에 빈 곳이 없는지 정기 확인.
7. (미확인) pg_verifybackup 등 백업 매니페스트 검증 도구는 이번에 원문을 읽지 않았으므로 도입 전 공식 문서 확인.

### 7.3 SQLite(대안 B)
1. Online Backup API(Python `sqlite3` 모듈의 backup 기능 — 공식 Python 문서는 이번 범위 밖, 미확인) 또는 `VACUUM INTO`로 annot.db 스냅샷 생성. VACUUM INTO 출력 파일은 사전에 없거나 비어 있어야 함(원문).
2. 생성 완료가 확인된 파일만 완료 디렉터리로 이동(중단 시 손상 가능 — 원문).
3. sqlite3_rsync로 다른 호스트의 복제본 갱신(3.50.0 이상 권장 — 그 이전엔 WAL·page size 제약).
4. 리허설: 스테이징에서 사본을 열어 7.1 지문 비교, 무결성 검사 PRAGMA 실행(해당 PRAGMA 문서는 이번 미열람 — 도입 전 확인).
5. 금지 행동 점검: 라이브 파일 cp 스크립트가 없는지 cron·스크립트 검토.

### 7.4 DuckDB(대안 C의 원천 스냅샷)
1. 수집기 프로세스 안에서 `EXPORT DATABASE '<dir>' (FORMAT parquet)`.
2. 리허설: 새 빈 DB에서 `IMPORT DATABASE '<dir>'`(빈 DB 필수 — 원문) → 테이블별 행 수 비교.
3. 원천은 재수집 가능하므로 "재수집 리허설"(원천 → 재적재 소요)도 한 번 측정해 백업 대신 재수집으로 충분한지 판단.

---

## 8. 원문과 다른 자료·판본 차이, 미확인

- 요청 URL `/docs/stable/...`은 `/docs/current/...`로 연결되었고 문서 머리에 "1.5 current"가 표시됐다. 이전 판 문서·검색 요약에서 DuckDB 다중 프로세스 쓰기를 "지원 안 함"으로만 설명하는 경우가 있을 수 있으나, 현 문서는 **native 파일 모델은 그대로 단일 writer 프로세스**이고 다중 프로세스 쓰기는 Quack(베타)로 "지원된다"고 덧붙인 것이다 — 두 서술은 모순이 아니라 범위가 다르다.
- Quack 베타 판본 표기가 문서마다 다르다: concurrency 문서 "as of v1.5.2", Quack 문서 "available in DuckDB v1.5.3". 최신 릴리스는 1.5.6(2026-09-28). 문서 갱신 시점 차이로 보이며(추론) 어느 쪽이든 베타다.
- why_duckdb는 "Quack을 통해 in-process 영역을 벗어났다"고 쓰지만, 같은 사이트의 Quack 문서는 베타·변경 가능을 명시한다. 성숙도 판단은 Quack 문서를 따랐다.
- "Quack이 v2.0(가을 2026)에 성숙할 것"은 **예상**이며 사실이 아니다. 2.0.0 날짜도 tentative.
- sqlite3_rsync: 도입 3.47.0(2024-10-21). 옛 문서 기준의 "양쪽 모두 WAL 모드, 같은 page size" 제약은 3.50.0(2025-05-29)에서 제거됐다고 현 문서에 표시돼 있다.
- pg_dump: 참조 페이지는 "정기 운영 백업으로는 일반적으로 적합하지 않다"고, 백업 장은 세 방식 중 하나로 소개한다. 이유: pg_dump는 시작 시점 스냅샷만 주고 PITR이 없으나 판본 이식성이 있다 — 그래서 A에서 보조 수단으로만 둔다.
- DuckDB FORCE CHECKPOINT는 v1.4부터 동작이 바뀌었다(진행 중 트랜잭션 중단 → 대기).
- **미확인**: DuckDB EXPORT DATABASE의 트랜잭션 일관성 보장 문구 / DuckDB postgres 확장의 PostgreSQL 측 스냅샷·격리 수준 / "CHECKPOINT 후 파일 복사"를 공식 백업 방법으로 권하는 문구(이번에 찾지 못함 → 권고에 쓰지 않음) / SQLite PRAGMA synchronous·integrity_check 상세 / pg_verifybackup / 서드파티 SQLite 복제 도구 / sqlite3_rsync 성숙도 표기.
- 웹 검색 엔진 요약은 이번 판단 근거로 쓰지 않았고, 모든 사실은 공식 URL을 직접 크롤해 확인했다.
