# source_notes — 확인·실패·판본 기록

- 기준일: 2026-10-08. 모든 URL은 이 날 `sense:crawl`로 본문을 받아 정규식으로 해당 대목을 원문 그대로 발췌해 읽었다. 웹 검색 요약은 근거로 쓰지 않았다(직접 URL 접근).
- 이 작업에서 DB 생성·설정 변경·벤치마크·외부 발송은 하지 않았다.

## 확인한 원문 (24개 URL: SQLite 7 · DuckDB 10 · PostgreSQL 7, 모두 공식 도메인)

### SQLite — 현행 3.53.x (https://www.sqlite.org/chronology.html 최상단 3.53.4, 2026-07-24)
| URL | 확인 범위 | 쓰임 |
|---|---|---|
| https://www.sqlite.org/wal.html | 동시성, 체크포인트, 단점, 내구성 문단 | 동시성 |
| https://www.sqlite.org/backup.html | cp 방식·Online Backup API·관련 도구 | 백업 |
| https://www.sqlite.org/lang_vacuum.html | VACUUM INTO 절 | 백업 |
| https://www.sqlite.org/rsync.html | 사용법·스냅샷 의미·제약 | 백업(별도 유틸) |
| https://www.sqlite.org/howtocorrupt.html | 1.2, 1.3 | 실패 시나리오 |
| https://www.sqlite.org/whentouse.html | 데이터 분석·client/server 비교 서두 | 분석 적합성 |
| https://www.sqlite.org/chronology.html | 최근 릴리스 날짜 | 판본 |

### DuckDB — 문서 "1.5 current", 최신 1.5.6(2026-09-28), 2.0.0 예정 2026-10-21(tentative)
| URL | 확인 범위 | 쓰임 |
|---|---|---|
| https://duckdb.org/docs/current/connect/concurrency | 문서 전체 | 동시성 |
| https://duckdb.org/docs/current/quack/overview | 개요·Warning | 별도 서버 프로토콜 성숙도 |
| https://duckdb.org/docs/current/sql/statements/export | 문서 전체 | 백업 |
| https://duckdb.org/docs/current/sql/statements/checkpoint | 문서 전체 | 백업 보조 |
| https://duckdb.org/docs/current/core_extensions/ducklake | 릴리스 표기·함수 일부 | 다른 저장 형식 |
| https://duckdb.org/2026/04/13/ducklake-10 | 제목·TL;DR | DuckLake 1.0 성숙도 |
| https://duckdb.org/release_calendar | 예정·LTS·최근 릴리스 | 판본 |
| https://duckdb.org/why_duckdb | Simple/Feature-rich/Fast | 분석 적합성 |
| https://duckdb.org/docs/current/core_extensions/postgres/overview | 개요·ATTACH·설정 일부 | 외부 DB 연결 확장 |
| https://duckdb.org/docs/current/core_extensions/sqlite | 개요·ATTACH | 외부 형식 연결 확장 |

### PostgreSQL — 현행 18(현 minor 18.6), 지원 18/17/16/15/14, 19 개발판
| URL | 확인 범위 | 쓰임 |
|---|---|---|
| https://www.postgresql.org/docs/current/mvcc-intro.html | 13.1 전체 | 동시성 |
| https://www.postgresql.org/docs/current/backup.html | 장 서두 | 백업 |
| https://www.postgresql.org/docs/current/backup-dump.html | 25.1 요지 | 백업 |
| https://www.postgresql.org/docs/current/app-pgdump.html | Description·스냅샷 옵션 | 백업 |
| https://www.postgresql.org/docs/current/app-pgbasebackup.html | Description·형식·증분 | 백업 |
| https://www.postgresql.org/docs/current/continuous-archiving.html | 서두·아카이빙 설정 | 백업(PITR) |
| https://www.postgresql.org/support/versioning/ | 정책·판본 표 | 판본 |

## 판본 관찰과 차이 설명

1. 요청한 `duckdb.org/docs/stable/...` 주소는 `docs/current/...`로 연결되었고 머리말이 "1.5 current"였다. 따라서 이 보고서의 DuckDB 사실은 1.5 계열 문서 기준이다.
2. Quack 베타의 판본 표기 불일치: concurrency 문서 "beta stage as of DuckDB v1.5.2" vs Quack 문서 "beta release of Quack, available in DuckDB v1.5.3". 문서 작성 시점 차이로 보이나(추론) 확정하지 못했다. 두 문서 모두 베타.
3. "Quack expected to become mature by DuckDB v2.0 in fall 2026"은 예상 문구다. 2.0.0 날짜(2026-10-21)는 릴리스 달력상 tentative — 기준일(10-08) 현재 미출시.
4. why_duckdb의 "Quack을 통해 in-process 영역을 벗어났다"는 홍보성 서술이고, 성숙도 판단은 Quack 문서의 베타·변경 가능 경고를 따랐다.
5. DuckLake 1.0: ducklake 확장 문서 "April 2026", 블로그 URL 날짜 2026-04-13, 제목 "Reaches Production-Readiness", concurrency 문서 "intended for production use" — 서로 일치.
6. sqlite3_rsync: howtocorrupt 문서 "3.47.0 (2024-10-21)부터 제공", rsync 문서 "WAL·같은 page size 제약은 3.50.0 (2025-05-29)에서 제거". 옛 문서나 그것을 요약한 2차 자료는 이 제약을 여전히 적었을 수 있다.
7. pg_dump 위상 차이: app-pgdump는 "정기 운영 백업에 일반적으로 부적합", backup 장은 세 방식 중 하나로 제시 — 기능 차이(시작 시점 스냅샷·PITR 없음 vs 판본 이식성)로 설명되며 모순이 아니다.
8. DuckDB FORCE CHECKPOINT는 v1.4부터 동작 변경(진행 중 트랜잭션 중단 → 락 대기). 그 이전 판 문서를 근거로 한 설명과 다를 수 있다.
9. SQLite chronology의 3.53.4를 "최신"으로 본 것은 페이지 상단 첫 행 기준이다(추출 순서상 최상단).

## 실패·미확인

- 크롤 실패: 없음(모든 요청 URL 응답 수신, 도구 실패 0).
- 내용 미확인(이번에 해당 문구를 찾지 못했거나 읽지 않음):
  - DuckDB EXPORT DATABASE가 트랜잭션 일관 스냅샷을 보장한다는 문구 — export 페이지 전체 발췌에서 발견 못 함.
  - DuckDB에서 "CHECKPOINT 후 파일 복사"를 공식 백업으로 권하는 문구 — 찾지 못함, 권고에 쓰지 않음.
  - DuckDB postgres 확장 Transactions 절 본문(PostgreSQL 측 스냅샷·격리 의미).
  - DuckDB sqlite 확장과 SQLite WAL 락의 상호작용.
  - Quack의 인증·내구성·백업 절.
  - SQLite wal.html 9장(SQLITE_BUSY) 본문, PRAGMA synchronous / integrity_check 문서.
  - sqlite3_rsync의 성숙도 표기.
  - PostgreSQL recovery_target_* 상세, pg_verifybackup.
  - Python 표준 라이브러리 sqlite3 backup 바인딩(공식 Python 문서, 범위 밖).
  - 서드파티 SQLite 복제 도구(공식 문서 범위 밖, 평가하지 않음).
- 성능 수치: 세 제품 모두 이 팀 조건의 처리량·지연·RPO/RTO 수치를 공식 문서가 제공하지 않으므로 보고서에 수치를 만들지 않았다. 원문 내 수치(SQLite 자동 체크포인트 1000 페이지)만 인용.
