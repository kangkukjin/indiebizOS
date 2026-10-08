# 변경 조건 검토: NAS/NFS 공유 DB 파일 제안 (기준일 2026-10-08)

> **변경 전제**: 분석가 4명이 서로 다른 컴퓨터에서 일한다. 수집 프로세스 1개는 계속 쓰고, 분석가들은 그동안 동시에 읽어야 한다.
>
> **제안**: NAS/NFS에 DB 파일 하나를 두고 각 컴퓨터가 직접 열어 서버 운영을 없앤다.
>
> **근거**: 이전 결정문과 같은 공식 문서 8건의 추출본이다. 실DB 시험과 성능 측정은 없다.
>
> **추가 조사**: 하지 않았다. 제안을 판정하는 데 필요한 핵심 근거, 즉 네트워크 FS 위에서 여러 호스트가 동시에 읽고 쓸 수 있는지는 기존 근거에 있다 ([network](https://www.sqlite.org/useovernet.html)). 비어 있는 부분은 결론을 바꾸지 않으므로 미확인으로 남긴다. 해당 부분은 PostgreSQL 원격 접속 설정과 NAS 잠금이 실패하는 조건이다.

## 1. 접근 방식 구분

| 구분 | 의미 | 이 팀에서의 위치 |
|---|---|---|
| 파일시스템 공유 | 각 호스트의 프로세스가 원격 DB 파일을 파일명으로 직접 연다 ([network](https://www.sqlite.org/useovernet.html)) | 이번 제안 |
| DB 서버 접속 | DB 파일이 있는 호스트의 프로세스만 파일을 다루고, 다른 호스트는 요청을 보낸다 ([network](https://www.sqlite.org/useovernet.html)) | 이전 기본안(PostgreSQL) |
| 단일 호스트 | 수집과 분석이 한 컴퓨터에서 이루어진다 | 이전 전제 |
| 다중 호스트 | 분석가 컴퓨터가 서로 다르다 | 변경 전제 |

다중 호스트 요구가 있어도 서버 자체는 단일 호스트에 둘 수 있다. 여러 호스트에 흩어지는 것은 클라이언트뿐이다. pg_dump는 별도 서버에 접속하는 클라이언트이며 원격 호스트에서도 실행할 수 있다 ([dump](https://www.postgresql.org/docs/current/backup-dump.html)). 일반 분석 클라이언트의 원격 접속 설정과 인증 세부는 추출 근거에 없다(미확인).

## 2. 제안안 원문 대조

| 제품·모드 | 원문 | 수집 쓰기 + 다중 호스트 동시 읽기 |
|---|---|---|
| SQLite WAL | 모든 프로세스가 같은 호스트에 있어야 하며, 네트워크 FS에서는 동작하지 않는다 ([wal](https://www.sqlite.org/wal.html)) | 불충족 |
| SQLite 롤백 모드 | 네트워크 FS의 잠금·쓰기 순서·동기화 신뢰성은 구현 의존이며, 공유 파일 안전성을 일반적으로 보장하지 않는다 ([network](https://www.sqlite.org/useovernet.html)) | 불충족 |
| SQLite 공통 | 네트워크 FS는 여러 호스트의 동시 읽기·쓰기를 일관되게 지원하지 못한다. 쓰기 유실·순서 뒤바뀜이 생길 수 있고, 일부 구현에서는 배타 잠금 오동작으로 손상된 사례가 있다 ([network](https://www.sqlite.org/useovernet.html)) | — |
| DuckDB native | 읽기-쓰기 모드에서는 한 프로세스만 접근한다. READ_ONLY 모드에서는 어느 프로세스도 쓸 수 없다. NAS에서는 각별한 주의가 필요하다고만 하고, 실패 조건은 적혀 있지 않다 ([concurrency](https://duckdb.org/docs/stable/connect/concurrency)) | 불충족 |

**판정(추론)**: 하나의 공유 파일로 "수집 1개 쓰기 + 다른 호스트들의 동시 읽기"를 처리하는 이 구성은 두 임베디드 제품의 원문이 모두 지지하지 않는다.

- 초기 테스트에서 동작하더라도 안전하다고 판단하면 안 된다. 문제가 드물고 재현하기 어렵기 때문이다 ([network](https://www.sqlite.org/useovernet.html)).
- 이 결론은 위 구성에 한정한다. 단일 호스트 사용이나 읽기 전용 공유 일반에 대한 판정이 아니다.

## 3. 대안 비교 (추론)

| 대안 | 방식 | 요구 충족 근거 | 남는 운영·제약 |
|---|---|---|---|
| A. PostgreSQL 18 서버 1대 | DB 서버 접속 | MVCC 아래에서 읽기와 쓰기가 서로 막지 않는다 ([mvcc](https://www.postgresql.org/docs/current/mvcc-intro.html)) | 서버·롤·아카이브 관리 |
| B. SQLite WAL + 프록시 | DB 호스트의 프로세스가 모든 읽기·쓰기를 수행하고 원격 요청을 중계 | 원문이 제시한 선택지다 ([network](https://www.sqlite.org/useovernet.html)) | 프록시는 사용자가 구현·운영해야 하며 SQLite 내장 기능이 아니다 |
| C. DuckLake + PostgreSQL 카탈로그 | 중앙 카탈로그가 조정 | 여러 인스턴스가 같은 DB를 동시에 읽고 쓴다 ([concurrency](https://duckdb.org/docs/stable/connect/concurrency)) | 외부 PostgreSQL과 별도 저장 형식이 필요하다. 장애·복구 특성은 미확인 |
| D. Quack | DuckDB를 클라이언트-서버로 운용 | — | v1.5.2 시점 베타이며 v2.0 성숙은 "예상"이다. 현재 상태는 미확인 ([concurrency](https://duckdb.org/docs/stable/connect/concurrency)) |
| E. 조건부 스냅샷 사본 | 기록 원본에서 만든 분석용 사본을 READ_ONLY로 연다 ([concurrency](https://duckdb.org/docs/stable/connect/concurrency)) | 실시간 동시 읽기가 아니다 | 사본의 기준 시점을 정할 근거가 없다(EXPORT 스냅샷 미기재, [export](https://duckdb.org/docs/stable/sql/statements/export)). 사본을 NAS에 두면 NAS 주의 문구가 적용된다 |

원문상 요구를 충족하는 A~D는 모두 DB 호스트에서 요청을 처리하는 프로세스나 외부 PostgreSQL을 둔다. 따라서 이 근거 범위에서는 **"서버 운영 제거" 목표가 달성되지 않는다**(추론).

## 4. 권고 (제안)

1. **NAS 공유 파일 제안: 불채택**(제안). 근거는 2절이다.
2. **기본안 유지**: PostgreSQL 18 서버 1대를 한 호스트에 두고, 수집 프로세스와 분석가 컴퓨터가 접속한다 ([mvcc](https://www.postgresql.org/docs/current/mvcc-intro.html)).
3. **SQLite 경량 대안은 형태를 바꾼다**: 공유 파일을 직접 여는 방식은 제외하고 B(프록시)로만 허용한다. 이전 조건은 그대로 유지한다.
   - 배포 계열에 해당하는 버그 수정이 포함된 판본인지 확인한다(문서상 수정: 3.51.3, 백포트: 3.44.6·3.50.7; 이후 판본도 릴리스 근거 확인) ([wal](https://www.sqlite.org/wal.html)).
   - 실측에서 백업이 완료되는지 확인한다 ([backup](https://www.sqlite.org/backup.html)).
   - 여기에 프록시 구현과 검증을 추가한다. 이 경우에도 서버 성격의 운영은 남는다.
4. **E는 유지하되** 실시간 읽기 요구를 대체하지 못한다는 점을 명시한다.
5. **C·D 보류를 유지한다.**

## 5. 이전 권고와 바뀐 점

| 항목 | 이전 결정문 | 이번 |
|---|---|---|
| 전제 | 단일 Linux 호스트, 분석가 4명이 같은 호스트에서 작업 | 다중 호스트 |
| PostgreSQL 기본안 | 같은 호스트의 클라이언트가 접속 | 원격 클라이언트가 접속. 권고는 유지하되 접속 설정은 미확인 |
| SQLite WAL 경량 대안 | 같은 호스트 로컬 파일 조건으로 조건부 허용 | 공유 파일 방식 불가, 프록시 형태로만 허용 |
| DuckDB 사본 | 같은 호스트에서 READ_ONLY | 다중 호스트에 배포할 때 NAS 주의 추가. 실시간 아님 |
| 신규 | — | NAS 공유 파일 제안 불채택 |
| 백업 절차 | 아래 7절 | 변경 없음. SQLite는 DB 호스트 기준(추론) |

## 6. 실패 시나리오 (추가분 중심)

- **NAS 공유 파일**: 쓰기 유실, 순서 뒤바뀜, 약한 sync, 잠금 오동작에 의한 손상이 생길 수 있다 ([network](https://www.sqlite.org/useovernet.html)). 파일 I/O 채널의 장애는 DB 손상까지 일으킬 수 있다 ([network](https://www.sqlite.org/useovernet.html)).
- **DuckDB**: 두 번째 쓰기 프로세스는 원문상 허용되지 않는다. 오류 형태는 미확인이다 ([concurrency](https://duckdb.org/docs/stable/connect/concurrency)).
- **PostgreSQL**: 아카이브 실패로 pg_wal이 가득 차면 PANIC으로 오프라인이 된다 ([pitr](https://www.postgresql.org/docs/current/continuous-archiving.html)).
- **공통**
  - 백업 파일이 존재하거나 종료 코드가 0이라는 완료표시는 원천 트랜잭션 일관성과 다르다.
  - 백업이나 PITR만으로는 어떤 장애에서도 주석 손실 0을 보장하지 않는다. 아카이브 지연분이 남고 ([pitr](https://www.postgresql.org/docs/current/continuous-archiving.html)), 원문은 RPO/RTO 수치를 제시하지 않는다.
  - 다음 사항은 팀에 **추가 요구사항으로 확인**해야 한다: 허용 손실 범위, 다른 호스트·매체로의 보관, 주석 작성 경로.

## 7. 백업·복구 검증 (제안, 이전 절차 유지)

1. **globals 수집**: `pg_dumpall --globals-only`로 별도 수집한다. 롤과 테이블스페이스는 pg_dump에 포함되지 않기 때문이다 ([dump](https://www.postgresql.org/docs/current/backup-dump.html)). 옵션명은 추출 근거에 없으므로 18 문서에서 재확인한다.
2. **형식 짝 맞추기**: `pg_dump -Fc` → `pg_restore`, plain SQL → `psql`(`-1`, ON_ERROR_STOP). 두 형식을 혼용하지 않는다 ([dump](https://www.postgresql.org/docs/current/backup-dump.html)).
3. **복원 순서**: globals를 먼저 복원한다. 그다음 template0에서 만든 빈 DB에 복원하고 ANALYZE를 실행한다 ([dump](https://www.postgresql.org/docs/current/backup-dump.html)).
4. **지문 비교**: 키·행수만 보지 않는다. 주석 본문, 수정 이력, 삭제 표시를 포함한 필수 값 전체의 지문을 **백업과 같은 스냅샷**에서 계산해 복원본과 비교한다.
   - 계속 변하는 원본의 백업 직전·직후 값과 단순 일치를 요구하지 않는다.
   - 기준 시점을 확보하지 못하면 "미검증"으로 판정한다.
5. **SQLite(B안)**: DB 호스트에서 Online Backup API 등 일관 백업 경로로 사본을 만들고 완료를 확인한다 ([backup](https://www.sqlite.org/backup.html)). 실행 중 DB와 WAL을 각각 복사하는 것만으로 일관성을 보장하지 않는다. WAL을 임의 분리하지 않는 원본 취급 규칙과 API의 완성된 백업 사본을 구별한다.
6. **PITR**: 설정 파일을 따로 백업하고, 베이스 백업과 연속된 필요한 WAL 체인을 확보해 해당 베이스 백업 종료 이후의 유효한 시점으로 복구 리허설을 한다 ([pitr](https://www.postgresql.org/docs/current/continuous-archiving.html)).

## 8. 측정 항목 (제안값)

허용 한계는 팀이 정하는 제안값이다. NAS 공유 파일은 시험에 통과해도 안전하다고 판정할 수 없으므로 측정 대상에서 뺀다 ([network](https://www.sqlite.org/useovernet.html)).

| 측정량 | 대상 | 관찰 | 판정 규칙(제안) |
|---|---|---|---|
| 원격 분석 질의 지연 | A, 검토 시 B | 분석가 컴퓨터에서 실제 작업 주기 동안 | 팀 한계를 넘으면 해당 안 탈락 |
| 수집 쓰기 중 원격 읽기 동시 진행 | A, B | 수집이 동작하는 동안 | 트랜잭션 경합·재시도 후의 지연·실패율이 팀이 정한 한계를 넘으면 탈락 |
| pg_wal 크기·아카이브 지연 | A | 같은 기간 | 계속 증가하면 경보. 최종 판정과는 별개 |
| 복원 지문 일치 | A, B | 리허설마다 | 불일치 또는 미검증이면 백업 체계 불채택 |
| 복구 소요 | A, B | 리허설 | 요구 RTO가 확정된 뒤 비교 |

## 9. 미확인

- PostgreSQL 원격 접속 설정과 인증. pg_hba.conf는 설정 파일 백업 맥락에서만 언급된다 ([pitr](https://www.postgresql.org/docs/current/continuous-archiving.html)).
- 문제가 되는 네트워크 FS의 이름, NAS에서 잠금이 실패하는 조건
- 프록시 구현의 장애 특성, Quack의 현재 성숙도, DuckLake의 장애·복구 특성, EXPORT 일관성
- 모든 안의 분석 성능과 RPO/RTO