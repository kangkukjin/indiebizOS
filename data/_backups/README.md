# _backups — 일회성 백업의 단일 주소

이관·정리·실험 전에 뜨는 **일회성 백업은 전부 여기에** 둔다.
`data/` 루트, `cloud_training/`, 작업 폴더에 `*_backup*` 사본을 흩뿌리지 말 것.

## 규약
- 디렉토리: `YYYY-MM-DD_이름/` (예: `2026-08-14_contact_type_migration/`)
- 단일 파일: `YYYY-MM-DD_이름.확장자` (예: `2026-08-14_ibl_usage.db`)
- **30일 지난 항목은 삭제 후보**다. 실제 삭제는 사용자가 결정한다(자동 삭제 없음).
  2026-09-02 부터 후보는 주간 데이터 소유 감사가 `outputs/imagination_training/PENDING_VERDICTS.md` 의
  '미결' 절에 `- [ ]` 로 적립한다(비가역 층=사전 판정, docs/COMPONENT_APOPTOSIS_HANDOFF.md §D) — '보고만' 이
  영구 방치로 새지 않게. 미결 5건이면 상상훈련 마라톤이 멈추고 사용자를 부른다.
- **큰 백업은 개수로도 센다** — 해마 모델 백업(`data/models/ibl_embedding.bak.*`)은 하나가 423MB 이고
  재학습마다 하나씩 생겨 30일을 기다리면 10개(4G)가 된다. 보관 = **최근 3개**(2026-08-22 사용자 판정,
  절차 정본 `cloud_training/README.md` 함정 ①). 기각 모델 `._rejected_*` 은 백업이 아니라 폐기물이다.
- 라이브 SQLite 는 파일 복사가 아니라 `VACUUM INTO` 또는 `.backup` 으로 뜰 것(WAL).
- **git 추적 금지.** 이 폴더는 `.gitignore` 대상이고, 이 README 하나만 `!` 로 예외다 —
  규약 정본은 신선 clone 에도 있어야 하므로. 백업은 정리 *전에* 뜨는 물건이라
  자격증명·PII 가 그대로 들어 있을 수 있고, 이 저장소는 public 이다.
  (2026-08-24 실측: 규약 제정 *이전*에 들어온 40파일이 계속 추적되고 있었다 —
  `.gitignore` 는 이미 추적 중인 파일을 되돌리지 못한다. `scripts/check_tracked_ignored.py`
  가 그 부류를 매 커밋 차단한다.)

## 업그레이드 백업 (`YYYY-MM-DD_upgrade/`, 2026-09-02)
설치본 동기화(`frontend/electron/userdata_sync.js`)가 코어 파일을 덮어쓸 때 자동으로 만든다 —
`files/`(덮어쓴 원본) · `retired/`(은퇴 코어의 격리본, 실삭제 아님) · `journal.jsonl`(되감기 원장) ·
`manifest.json`. 내용이 같은 파일은 안 뜨므로 같은 버전 재기동엔 생기지 않는다. 30일 규약 동일.

## 예외 (여기 안 둠)
- `safe_store.py` 가 저장 시마다 만드는 `*.bak` 직전-세대 사본 — 설계된 기능, 원본 옆에 산다.
- LRU 캐시(`showcase_stage/`, `youtube_cache/` 등) — 백업이 아니라 스스로 비우는 캐시.

## 유래
2026-08-14 청소에서 제정. 당시 `data/` 루트·`cloud_training/` 에 흩어져 늙던
일회성 백업 약 6.4G(해마 DB 6월 사본 456M, 학습 실험 zip 6개 2.3G, 이관 백업,
0.1.0 구빌드 3.2G, .fuse_hidden 유령 147개)를 정리하며, 재발 방지로 주소를 통일했다.
