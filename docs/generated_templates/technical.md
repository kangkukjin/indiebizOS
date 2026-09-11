
- `backend/`: 서버 소스 코드 — **층=디렉토리**(2026-08-05 물리 이동). 의존은 아래→위 한 방향:
  `base`({{layers_base}}) → `datastore`({{layers_datastore}}) → `ibl`({{layers_ibl}}) → `cognition`({{layers_cognition}}) → `services`({{layers_services}}) → `surface`({{layers_surface}}). `.py` 총 {{backend_py}}개(test 제외).
  - ★**모듈 이름은 평면**(`import ibl_engine`) — `backend/boot_paths.py` 가 층 경로를 `sys.path` 에 얹는다.
  - 새 backend 모듈 = 층 폴더에 두고 `scripts/check_backend_layers.py` 의 `LAYERS` 에 배정. 독립 스크립트는 맨 위에 `import boot_paths`.
  - 층 밖 공용: `backend/common/`({{layers_common}}) · `backend/providers/`({{layers_providers}}, AI 프로바이더 스트리밍) · `backend/channels/`({{layers_channels}}) · `backend/drivers/`({{layers_drivers}})
- `data/`: 시스템 설정 및 데이터
- `data/packages/installed/tools/`: 설치된 도구 패키지 (**{{tools_n}}개** — op 분기 **{{op_pkgs}}개**가 `_OP_DISPATCHERS` 표준)
- `data/packages/installed/extensions/`: 백엔드 코어 모듈 (**{{exts_n}}개**)
- `data/api_registry.yaml`: API 도구 정의 — {{api_tools_n}}개 도구 중 {{api_bound_n}}개가 `node`로 바인딩돼 로드 시 노드 액션에 자동 병합(`ibl_engine._merge_api_registry_actions`, 2026-08-22 실측)
- `data/scripts/`: **등록 스크립트**(`registry.yaml` + `<이름>.py`) — `[self:script]{op: run}` 이 id 로만 실행. 어휘가 아니라 *절차*의 거처
- `data/private_nouns.txt`: **개인 명사 관문 목록**(gitignore, 로컬 전용) — `scripts/check_private_nouns.py`(pre-commit, 모든 스테이지 파일)가 가족·개인 이름·목소리 키가 몸(코드·어휘·가이드·문서)에 박히는 것을 막는다. 한 줄=정규식, `allow: <glob>`=면제(저자 서명·연구 기록). 이름 자체가 저장소에 들어오지 않는 구조(2026-09-02)
- `data/instruments/`: standalone 앱 매니페스트 (어휘 없는 계기 — report·newspaper)
- `data/guides/`: 가이드 {{guides_n}}개 (guide_db 등록 {{guide_db_n}}). `codebase_map.md` 는 system_structure.md 에서 **자동 파생**이므로 직접 편집 금지
