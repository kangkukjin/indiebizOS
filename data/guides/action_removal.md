# IBL 액션 제거 가이드

IBL 어휘(액션)를 제거하는 길은 **둘**이다 — 무엇을 지우느냐에 따라 다르다.

## (A) 패키지 통째 제거 — 대부분 자동

`[self:package]{op:"remove", package_id:"…"}` (= `package_manager.uninstall_package` / `remove_package`). 그 패키지의 **모든** 액션이 한 번에 사라지고, 아래 대부분을 **코드가 자동으로** 한다(2026-07 대칭 수정 이후):

| 정리 대상 | 자동? | 무엇이 |
|---|---|---|
| 정의 제거 (폴더 → not_installed → 빌드가 그 패키지 `ibl_actions.yaml`을 더는 병합 안 함) | ✅ | `uninstall_package` + `_rebuild_ibl_vocab` |
| 어휘 재빌드 + 런타임 캐시 리로드 | ✅ | `_rebuild_ibl_vocab` |
| **해마 용례 정리 + 벡터 삭제** (4번) | ✅ | `remove_for_package` |
| **건강기록 정리** (action_health/self_checks, 5번) | ✅ | `purge_action_records` |
| **fixture 제거** (1번) | ✅ | 재빌드 파생 — fixture 는 액션의 `fixture:`/`exempt:` 필드라 정의와 함께 빠짐(`derive_fixtures`, 고아 불가) |
| ibl-core enum(6번)·산문 상호참조 | ❌ *깃발만* | `build_ibl_nodes.py --check` + 일일 건강점검이 잡음 |

> **원칙 — 런타임/파생 자동 / 저술 깃발**: RAG가 죽은 액션을 연상하거나(해마) X-Ray에 유령이 뜨는(건강기록) **런타임 상태**는 제거가 **자동 청소**한다. fixture 는 이제 **액션 정의의 필드**(`fixture:`/`exempt:`)이고 `data/ibl_fixtures.json` 은 build 파생물이라, 재빌드만으로 정의와 함께 **자동으로 빠진다**(고아 fixture 가 구조적으로 없음 — 2026-07-02 자기완결화 완료). 남는 저술 상태(ibl-core enum·산문 상호참조)만 자동 재작성이 취약하므로 `--check`가 **깃발만** 든다(사람이 판단).

---

## (B) 단일 액션 손 제거 체크리스트

패키지는 두고 **액션 하나만**(중복·폐기 어휘) 지울 때. 아래를 손으로 밟는다.

> 능력 자기완결화(2026-07) 이후: 도구 패키지 능력의 정의는 **그 패키지의 `ibl_actions.yaml`**에, 6개 코어 노드의 backend-내장 액션은 중앙 `data/ibl_nodes_src/`에 있다. (옛 "패키지별 `ibl_actions.yaml` 폐기" 서술은 자기완결화로 무효 — 어휘가 패키지 안으로 돌아왔다.)

### 1. 액션 정의 제거 (src → 빌드 → 검증)

- [ ] **패키지 능력**이면 그 패키지 `ibl_actions.yaml`의 `actions:`에서, **코어 노드 액션**이면 `data/ibl_nodes_src/{node}.yaml`의 `actions:`에서 항목 삭제
- [ ] `data/ibl_fixtures.json` — 그 액션의 `fixtures`/`exempt` 항목도 삭제 (items/scalar 였던 경우). 안 지우면 `--check` 가 *고아 fixture*로 잡는다.
- [ ] 빌드 + 검증:
  ```bash
  python scripts/build_ibl_nodes.py          # data/ibl_nodes.yaml 재생성
  python scripts/build_ibl_nodes.py --check  # 삼각 + fixture 완전성 확인 (비0이면 잔여 참조/고아 fixture)
  ```

### 2. ibl_nodes.yaml 확인
- [ ] `data/ibl_nodes.yaml` — 산출물에서 액션이 빠졌는지 확인 (직접 편집 금지, 빌드 결과물)

### 3. 도구 정의 정리
- [ ] `{패키지}/tool.json` — 해당 도구의 JSON 정의 제거 (tool.json에 단독 도구로 정의된 경우)
- [ ] `{패키지}/handler.py` — 도구 함수는 다른 액션에서 사용하지 않는 경우에만 제거

### 4. 해마 (학습 데이터 + 벡터 임베딩)

> **(A) 패키지 제거 시 자동** — `remove_for_package(package_id)`가 그 패키지 `ibl_actions.yaml`의 모든 `[node:action]`을 참조하는 용례를 찾아 `_delete_examples`(행 + 벡터 동시 삭제)한다. 아래는 **(B) 손 제거** 시 직접 하는 절차.
- [ ] `data/training/*.json` — 해당 액션을 참조하는 학습 데이터 수정 (대체 액션으로 변경 또는 삭제)
- [ ] `data/ibl_usage.db` — 해마 DB의 용례 수정 + 임베딩 재생성
  ```bash
  cd backend && python3 -c "
  from ibl_usage_db import IBLUsageDB
  db = IBLUsageDB()
  with db._get_connection() as conn:
      rows = conn.execute('SELECT id, intent, ibl_code FROM ibl_examples WHERE ibl_code LIKE \"%{액션명}%\"').fetchall()
  for row in rows:
      db._index_single(row[0], row[1], row[2])  # 변경 후 재인덱싱
  "
  ```

### 5. 건강 기록 정리 (action_health + self_checks)

> **(A) 패키지 제거 시 자동** — `purge_action_records(action_names)`가 world_pulse.db 두 테이블에서 그 액션들의 행을 삭제(action 컬럼은 `node:` 없는 **맨 액션명**). 아래는 **(B) 손 제거** 시 직접.
- [ ] `data/world_pulse.db`의 `action_health` 테이블에서 해당 액션 기록 삭제
- [ ] `data/world_pulse.db`의 `self_checks` 테이블에서 해당 액션 기록 삭제
  ```bash
  cd /path/to/indiebizOS && python3 -c "
  import sqlite3
  conn = sqlite3.connect('data/world_pulse.db')
  d1 = conn.execute('DELETE FROM action_health WHERE action = \"{액션명}\"').rowcount
  d2 = conn.execute('DELETE FROM self_checks WHERE action = \"{액션명}\"').rowcount
  conn.commit(); conn.close()
  print(f'action_health: {d1}건, self_checks: {d2}건 삭제')
  "
  ```
- 삭제하지 않으면 X-Ray에 존재하지 않는 액션이 비정상으로 계속 표시됨

### 6. 기타 참조
- [ ] `data/packages/installed/tools/ibl-core/tool.json` — 레거시 노드 도구의 enum/description에서 제거
- [ ] `data/guides/world_pulse.md` — 자동 생성 파일, 다음 펄스에서 자동 갱신됨

### 7. 검증
- [ ] 프로젝트 전체에서 해당 액션명 검색하여 잔여 참조 확인
  ```bash
  grep -r "{액션명}" data/ --include="*.{yaml,json,md,py}" | grep -v node_modules | grep -v __pycache__
  ```

## 주의사항

- **handler.py의 함수는 신중하게**: 제거하려는 액션의 handler 함수가 다른 액션에서도 사용될 수 있다 (예: `company_news`가 `stock_news`의 폴백으로도 사용). `handler.py`에서 해당 함수를 grep해서 다른 호출이 없는지 확인 후 제거.
- **학습 데이터 변경 후 재학습**: 학습 데이터(training/*.json)를 수정한 경우, 해마 모델 fine-tuning을 다시 해야 최적 성능이 나온다. 즉시 반영은 범용 임베딩으로 동작하고, 주기적 재학습 때 반영됨.
- **대체 액션이 있으면 변환**: 단순 삭제보다 대체 액션으로 변환하는 것이 낫다. 해마가 기존 패턴을 새 액션으로 안내할 수 있다.
