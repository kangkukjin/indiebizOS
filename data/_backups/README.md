# _backups — 일회성 백업의 단일 주소

이관·정리·실험 전에 뜨는 **일회성 백업은 전부 여기에** 둔다.
`data/` 루트, `cloud_training/`, 작업 폴더에 `*_backup*` 사본을 흩뿌리지 말 것.

## 규약
- 디렉토리: `YYYY-MM-DD_이름/` (예: `2026-08-14_contact_type_migration/`)
- 단일 파일: `YYYY-MM-DD_이름.확장자` (예: `2026-08-14_ibl_usage.db`)
- **30일 지난 항목은 삭제 후보**다. 실제 삭제는 사용자가 결정한다(자동 삭제 없음).
- **큰 백업은 개수로도 센다** — 해마 모델 백업(`data/models/ibl_embedding.bak.*`)은 하나가 423MB 이고
  재학습마다 하나씩 생겨 30일을 기다리면 10개(4G)가 된다. 보관 = **최근 3개**(2026-08-22 사용자 판정,
  절차 정본 `cloud_training/README.md` 함정 ①). 기각 모델 `._rejected_*` 은 백업이 아니라 폐기물이다.
- 라이브 SQLite 는 파일 복사가 아니라 `VACUUM INTO` 또는 `.backup` 으로 뜰 것(WAL).

## 예외 (여기 안 둠)
- `safe_store.py` 가 저장 시마다 만드는 `*.bak` 직전-세대 사본 — 설계된 기능, 원본 옆에 산다.
- LRU 캐시(`showcase_stage/`, `youtube_cache/` 등) — 백업이 아니라 스스로 비우는 캐시.

## 유래
2026-08-14 청소에서 제정. 당시 `data/` 루트·`cloud_training/` 에 흩어져 늙던
일회성 백업 약 6.4G(해마 DB 6월 사본 456M, 학습 실험 zip 6개 2.3G, 이관 백업,
0.1.0 구빌드 3.2G, .fuse_hidden 유령 147개)를 정리하며, 재발 방지로 주소를 통일했다.
