# IBL 액션 제거 가이드

중복이거나 더 이상 작동하지 않는 IBL 액션을 제거할 때 참조하는 체크리스트.
액션을 제거하면 여러 곳에 흩어진 참조를 모두 정리해야 한다.

## 체크리스트

### 1. 액션 정의 제거
- [ ] `data/packages/installed/tools/{패키지}/ibl_actions.yaml` — 해당 액션 항목 삭제
- [ ] `register_actions('{패키지}')` 실행하여 ibl_nodes.yaml에 반영
  ```bash
  cd backend && python3 -c "from ibl_action_manager import register_actions; print(register_actions('{패키지}'))"
  ```

### 2. ibl_nodes.yaml 확인
- [ ] `data/ibl_nodes.yaml` — 액션이 제거되었는지 확인 (register_actions가 처리하지만 수동 확인 권장)
- [ ] `data/_ibl_provenance.yaml` — 해당 액션의 출처 항목 제거

### 3. 도구 정의 정리
- [ ] `{패키지}/tool.json` — 해당 도구의 JSON 정의 제거 (tool.json에 단독 도구로 정의된 경우)
- [ ] `{패키지}/handler.py` — 도구 함수는 다른 액션에서 사용하지 않는 경우에만 제거

### 4. 해마 (학습 데이터 + 벡터 임베딩)
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
- [ ] `data/self_check_plan.json` — 다음 plan 재생성 시 자동 제거됨 (수동 불필요)
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
