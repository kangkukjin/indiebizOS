# decision — 조건 변경: 분석가 4명이 서로 다른 컴퓨터, "NAS/NFS 위 DB 파일 하나를 각자 직접 열자" 제안 검토

- 기준일: 2026-10-08 / 합성 시나리오(실제 DB·NAS·측정 없음, 시스템 변경 없음)
- 바뀐 조건: 수집 프로세스 1개는 계속 쓴다. 분석가 4명은 **서로 다른 컴퓨터(다중 호스트)**에서 동시에 읽는다. 사람이 단 주석은 잃으면 안 된다(기존 조건 유지).
- 제안: NAS/NFS에 DB 파일 하나를 두고 모든 컴퓨터가 그 파일을 직접 열어 "서버 운영을 없앤다".
- 재사용: `../base/research.md`, `../base/evidence.json`, `../base/source_notes.md`(같은 날 직접 읽은 공식 원문 24개). 기존 산출물은 수정하지 않았다.
- 표기: **[원문]** 공식 문서 사실(URL), **[추론]** 이 팀에 적용한 해석, **[제안]** 권고. 처리량·지연·손실시간 수치는 원문에 없어 만들지 않았다.

---

## 0. 결론

1. **제안은 기각한다. SQLite·DuckDB 모두 어느 쪽으로든 성립하지 않는다.**
   - **SQLite(WAL)**: [원문] "All processes using a database must be on the same host computer; WAL does not work over a network filesystem"(https://www.sqlite.org/wal.html).
   - **SQLite(rollback 저널 모드)**: [원문] 네트워크 파일시스템에서 쓰기용 배타 잠금이 잘못 동작해 DB가 손상된 사례가 있다. 롤백 모드로 위험을 줄일 수는 있지만 "SQLite library is not tested in across-a-network scenarios"이며 사용자 위험으로 쓰는 것이다(https://www.sqlite.org/useovernet.html). 손실을 허용하지 않는 주석 저장소로는 받아들일 수 없다.
   - **DuckDB native**: 공유 위치 이전에 [원문] "one process can both read and write" 또는 "multiple processes can read … but no processes can write"다(https://duckdb.org/docs/current/connect/concurrency). 수집기가 쓰는 동안 다른 컴퓨터의 분석가가 같은 파일을 여는 구성은 호스트 수와 상관없이 모델상 불가능하다. 공유 디렉터리·NAS에서는 "exercise extra caution"이라고도 적혀 있다(같은 URL).
2. **"서버 운영을 없앤다"는 목표는 다중 호스트 동시 읽기·쓰기와 함께 달성할 수 없다**(추론). 공식 문서가 다중 프로세스·다중 호스트 동시 접근에 대해 내놓는 경로는 모두 서버형이다. PostgreSQL 서버, DuckDB Quack(클라이언트-서버, **베타**), DuckLake(PostgreSQL 카탈로그 = 서버)다. 서버를 없애려면 "동시에, 최신 데이터를"이라는 조건을 "주기적 스냅샷 배포"로 낮춰야 한다.
3. **권고 [제안]**: 기존 권고 A를 유지하되 **필수**로 격상한다. PostgreSQL 18 서버를 수집기와 같은 호스트의 **로컬 SSD**에 두고, 분석가 컴퓨터는 네트워크로 **서버에 접속**한다. 분석은 분석가 컴퓨터의 DuckDB가 PostgreSQL을 READ_ONLY로 ATTACH하거나, 서버가 배포한 Parquet 스냅샷 사본을 읽는다.

---

## 1. 두 축의 구분

### 1.1 파일시스템 공유 vs DB 서버 접속

| | 파일시스템 공유(제안) | DB 서버 접속 |
|---|---|---|
| 무엇이 네트워크를 건너나 | DB 엔진의 **파일 I/O·잠금·fsync** | **SQL 요청과 결과**(서버 프로토콜) |
| 파일을 여는 주체 | 각 컴퓨터의 embedded 엔진(여럿) | 서버 프로세스 하나(한 호스트) |
| 잠금·복구 책임 | NFS/NAS의 잠금·동기화 구현에 의존 | 서버가 소유 |
| [원문] SQLite | 네트워크 링크는 File I/O 채널보다 API 호출 채널에 두는 편이 신뢰성에 유리하다. API 채널 실패는 트랜잭션 실패로 끝난다(https://www.sqlite.org/useovernet.html) | SQLite 자체는 서버가 없다("SQLite competes with fopen()", https://www.sqlite.org/whentouse.html) |
| [원문] PostgreSQL | 해당 없음. 클라이언트가 데이터 파일을 직접 열지 않는다 | `listen_addresses`로 TCP/IP 접속을 받고(기본값 localhost) `pg_hba.conf`의 host/hostssl 레코드로 클라이언트 주소·인증을 통제한다(https://www.postgresql.org/docs/current/runtime-config-connection.html , https://www.postgresql.org/docs/current/auth-pg-hba-conf.html) |

**주의할 혼동** — [원문] PostgreSQL 데이터 디렉터리를 NFS에 두는 것은 가능하다. 다만 `hard` 마운트가 필수이고, NFS 서버 쪽 `sync` export 옵션이 강하게 권고된다. 그렇지 않으면 fsync가 영구 저장소에 닿는다는 보장이 없어 손상될 수 있다(https://www.postgresql.org/docs/current/creating-cluster.html).

[추론] 이것은 **서버 프로세스 하나가 NFS를 로컬 디스크처럼 쓰는 경우**다. 여러 호스트가 같은 데이터 파일을 직접 여는 제안과는 다르다. 그러니 "PostgreSQL도 NFS를 지원하니 SQLite·DuckDB 파일을 NFS에 둬도 된다"는 근거가 되지 않는다. 이 팀은 NFS를 쓸 이유도 없다. 로컬 SSD에 두면 hard 마운트 정지와 export 옵션 위험이 사라진다.

### 1.2 단일 호스트 vs 다중 호스트

| 제품·방식 | 단일 호스트(base 조건) | 다중 호스트(이번 조건) |
|---|---|---|
| SQLite WAL, 파일 직접 열기 | 성립: 1 writer + 여러 reader 프로세스(wal.html) | **불성립**: 같은 호스트 필수, 네트워크 FS 불가(wal.html) |
| SQLite rollback, 네트워크 FS 위 직접 열기 | (해당 없음) | **비권고**: 잠금 오동작·손상 사례, 네트워크 시나리오 미시험(useovernet.html) |
| DuckDB native 파일 | writer 1개 프로세스 → 수집 중 다른 프로세스 접근 불가(concurrency) | **불성립**: 같은 이유에 공유 디렉터리·NAS 주의가 더해짐(concurrency) |
| DuckDB Quack(서버 프로토콜) | (불필요) | 가능하나 **베타**, 프로토콜·기본값 변경 가능(https://duckdb.org/docs/current/quack/overview) |
| DuckLake + PostgreSQL 카탈로그 | (과함) | DuckDB가 "stable solution"으로 제시, v1.0 생산용(2026-04). 단 카탈로그 서버가 필요(concurrency, ducklake) |
| PostgreSQL 서버 + 원격 클라이언트 | 성립 | **성립**: TCP/IP 접속, MVCC로 읽기·쓰기가 서로 막지 않음(mvcc-intro, runtime-config-connection) |
| 스냅샷 파일 배포(Parquet·SQLite 사본) | 가능 | 가능(읽기 전용, 스냅샷 시점 데이터). 최신성은 주기에 달림(추론) |

---

## 2. 대안 검토

| 대안 | 다중 호스트 동시 읽기 | 수집기 계속 쓰기 | 주석 보호 | 서버 운영 | 판정 [제안] |
|---|---|---|---|---|---|
| (0) 제안: NAS/NFS 위 단일 SQLite·DuckDB 파일 직접 열기 | 원문상 불가 또는 비권고 | — | 손상 위험(useovernet, howtocorrupt) | 없음 | **기각** |
| (a) 한 호스트에서 embedded DB + 읽기는 스냅샷 사본 배포 | 사본으로 가능 | 가능(수집 호스트 로컬) | 주석을 다른 컴퓨터에서 쓰면 쓰기 경로가 없음 → 별도 해결 필요 | 서버 없음, 배포 작업 필요 | **제한적 대안**: 분석가가 주석을 쓰지 않을 때만 |
| (b) PostgreSQL 서버(로컬 SSD) + 원격 접속 | 가능 | 가능 | PITR·pg_basebackup·pg_dump(base 근거 P3–P6) | 1대 운영 | **권고** |
| (c) (b) + 분석가 쪽 DuckDB(READ_ONLY ATTACH 또는 Parquet 스냅샷) | 가능 | 가능 | (b)와 같음 | (b)와 같음 | **권고 구성** |
| (d) DuckDB Quack 서버 | 가능 | 가능 | 백업·내구성 절은 미열람(미확인) | 서버 운영 | **보류**(베타) |
| (e) DuckLake + PostgreSQL 카탈로그 | 가능 | 가능 | 카탈로그는 PostgreSQL 백업에 의존(추론) | PostgreSQL 운영 포함 | **보류**: 20GB 규모에서 (c) 대비 이점이 불명확 |

(a)의 세부 [추론·제안]
- 수집 호스트에서 SQLite `VACUUM INTO`·Online Backup API로 일관 사본을 만들거나(https://www.sqlite.org/lang_vacuum.html , https://www.sqlite.org/backup.html), DuckDB `EXPORT DATABASE (FORMAT parquet)`로 사본을 만든다(https://duckdb.org/docs/current/sql/statements/export).
- 사본은 각 분석가의 **로컬 디스크로 복사**한 뒤 연다. NAS에 사본을 두고 여러 컴퓨터가 직접 여는 것은 읽기 전용이라도 이번 조사에서 공식 지원 문구를 찾지 못했다(미확인). 사본을 로컬로 옮기면 이 문제를 피할 수 있다.
- SQLite 사본을 다른 호스트로 보내는 공식 도구로 `sqlite3_rsync`가 있다. 일관된 스냅샷을 만들고, 복제 중 REPLICA는 읽기 전용이다(https://www.sqlite.org/rsync.html).
- 한계: 분석가 컴퓨터에서 주석을 쓰면 그 쓰기를 수집 호스트의 단일 writer에게 보낼 **서버 역할**이 필요해진다. 결국 서버 운영을 없애지 못한다(추론).

---

## 3. 기존 권고(base)에서 바뀐 부분

| 항목 | base(단일 호스트) | variant(다중 호스트) | 바뀐 이유 |
|---|---|---|---|
| 권고 A(PostgreSQL + 분석가별 DuckDB) | 권고(대안 B와 경합) | **유일한 권고**로 격상 | 다중 호스트 동시 읽기·주석 쓰기를 공식 지원하는 비베타 경로가 서버뿐 |
| 대안 B(SQLite WAL 두 파일) | 서버 없는 대안 | **탈락**(라이브 공유 저장소로서) | WAL은 같은 호스트 필수(wal.html). 네트워크 FS 직접 열기는 비권고(useovernet) |
| 대안 C(DuckDB 단일 writer + Parquet) | 조건부 | **스냅샷 배포 경로로만** 유지. 사본은 분석가 로컬로 복사 | native 다중 프로세스 불가는 그대로이고, 공유 디렉터리·NAS 주의가 추가됨 |
| PostgreSQL 접속 | 같은 호스트(로컬) | **TCP/IP 원격 접속**: listen_addresses, pg_hba.conf host/hostssl, SSL 권장 | 분석가 컴퓨터가 다름 |
| PostgreSQL 저장 위치 | 로컬 SSD | **로컬 SSD 유지, NFS 금지(권고)** | NFS에서는 hard 마운트 정지·export sync 위험(creating-cluster). NAS는 백업 목적지로만 사용 |
| 백업 | pg_basebackup + WAL 아카이빙, pg_dump | 같음. 아카이브·베이스 백업의 **목적지로 NAS 사용 가능**(추론) | NAS는 파일을 "여는" 곳이 아니라 "보관"하는 곳 |
| 운영 복잡성 | 서버 1대 | 서버 1대 + 네트워크 접근 통제·인증·(선택)TLS | 원격 클라이언트가 생김 |
| 실패 시나리오 | F1–F13 | F3(네트워크 FS)가 **핵심 위험**으로 격상, N1–N5 추가(4장) | — |

유지되는 것: 원문 사실 표(base research.md 1장), 판본(SQLite 3.53.x / DuckDB 1.5 current, 2.0.0 예정 2026-10-21 tentative / PostgreSQL 18.6), Quack 베타·DuckLake 1.0 구분, 미확인 목록.

---

## 4. 추가 실패 시나리오 (다중 호스트)

| # | 시나리오 | 근거 | 영향(추론) | 대응(제안) |
|---|---|---|---|---|
| N1 | 누군가 "테스트"로 NAS 위 SQLite 파일을 여러 컴퓨터에서 열어 당장은 잘 됨 | useovernet: 테스트된 환경과 실제 의존 환경에서 가정이 다를 수 있음 | 나중에 잠금 오동작으로 손상, 주석 손실 | 정책으로 금지. "작동한다"는 관찰을 근거로 삼지 않음 |
| N2 | PostgreSQL을 NFS에 두고 soft 마운트 또는 비동기 export 사용 | creating-cluster | I/O 오류 또는 fsync 미도달로 손상 | 로컬 SSD 사용. NFS를 쓸 수밖에 없다면 hard 마운트 + sync export를 명시 |
| N3 | listen_addresses를 넓게 열고 pg_hba를 느슨하게 둠 | runtime-config-connection, auth-pg-hba-conf | 무단 접속 | 팀 서브넷만 host/hostssl, 분석가는 읽기 역할, 주석 쓰기 권한은 분리 |
| N4 | 분석가가 네트워크 단절 중 작업 | (추론) | 서버 접속 불가 | 로컬 Parquet 스냅샷으로 읽기는 지속, 주석은 재연결 후 저장 |
| N5 | 스냅샷 배포가 중간에 끊긴 사본을 분석가가 엶 | lang_vacuum(중단 시 출력 손상 가능) | 잘못된 분석 | 완료 표식·검증 후 배포, 원자적 교체 |

---

## 5. 검증 절차 (팀이 실행할 문서화된 절차) [제안]

base research.md 7장(백업·복구 리허설)은 그대로 적용한다. 아래는 추가분이다.
1. **접속 경로 점검**: 각 분석가 컴퓨터에서 서버로 접속(TLS 사용 시 확인), 읽기 역할로 annot 쓰기가 거부되는지, 주석 쓰기 역할로는 쓰기가 되는지 확인한다.
2. **잠금 독립성 확인**: DB 파일이 NAS/NFS 경로에 없는지(데이터 디렉터리·SQLite·DuckDB 파일 위치) 점검 목록으로 주기적으로 확인한다.
3. **스냅샷 배포 리허설**: 사본 생성 → 완료 표식 → 분석가 로컬 복사 → 행 수·검증 지문 대조.
4. **백업 목적지 NAS 리허설**: NAS의 베이스 백업과 WAL 아카이브로 별도 스테이징 호스트에서 PITR 복구(base 7.2와 동일하되 소스가 NAS).
5. **네트워크 장애 리허설**: 서버 접속을 끊은 상태에서 분석가가 로컬 스냅샷으로 계속 작업할 수 있는지, 재연결 후 주석 저장이 되는지 확인한다.

## 6. 새로 측정할 항목 [제안]

base 6장에 추가한다.
- 분석가 컴퓨터 ↔ 서버 네트워크를 거친 대표 쿼리 응답 시간: (i) PostgreSQL 직접, (ii) DuckDB READ_ONLY ATTACH, (iii) 로컬 Parquet 사본.
- 스냅샷 크기·배포 소요, 분석가가 허용하는 최신성 지연(팀 결정).
- 주석 쓰기 주체·빈도를 재확인한다. 대안 (a)의 성립 여부를 가르는 핵심 미확인 항목이다.

---

## 7. 이번에 추가 조사한 근거와 이유

base 근거에는 "네트워크 FS 위 SQLite rollback 모드", "PostgreSQL 데이터 디렉터리와 NFS", "PostgreSQL 원격 접속 설정"이 비어 있었다. 이 세 가지가 제안의 성립 여부와 대안 설계를 직접 가르므로 공식 원문 4개를 2026-10-08에 추가로 읽었다.

| URL | 확인 범위 | 이유 |
|---|---|---|
| https://www.sqlite.org/useovernet.html | 네트워크 FS의 잠금·fsync 위험, rollback 모드 완화, 미시험 문구 | WAL 외 모드로 우회할 수 있는지 판단하려고 |
| https://www.postgresql.org/docs/current/creating-cluster.html | 18.2.2.1 NFS 절 | "PG도 NFS를 쓴다"는 반론을 구분하려고 |
| https://www.postgresql.org/docs/current/runtime-config-connection.html | listen_addresses | 다중 호스트 접속 경로 |
| https://www.postgresql.org/docs/current/auth-pg-hba-conf.html | 레코드 형식, host/hostssl | 다중 호스트 접근 통제 |

추가 조사하지 않은 것(미확인으로 남김):
- DuckDB native 파일을 NAS에서 여러 호스트가 **모두 읽기 전용**으로 여는 구성의 공식 지원 여부. 현 문서에는 "extra caution" 문구만 있다. 권고가 사본의 로컬 복사로 이 문제를 피하므로 결론을 바꾸지 않는다.
- PostgreSQL 읽기 전용 복제본(hot standby). 분석가 4명 규모에서 필요성이 측정되기 전이라 범위 밖으로 두었다.
- Quack의 인증·내구성·백업 절(보류 판정에 영향 없음).
- SQLite `immutable`·읽기 전용 URI 옵션. 라이브 수집이 계속되므로 해당하지 않는다.
