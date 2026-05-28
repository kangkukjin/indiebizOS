# IBL 액션 정의 — 단일 진실 소스화 작업 계획

> 새 세션에서 이 문서만 보고 진행할 수 있도록 작성. 진행 전 관련 메모리(`architecture_ibl_*`) 확인 권장.

## 1. 배경과 목표

### 왜 하는가
IBL 액션 정의가 **세 곳**에 흩어져 있음:
1. `data/packages/installed/tools/<pkg>/ibl_actions.yaml` — 33개 패키지에 분산
2. `data/ibl_nodes_src/<node>.yaml` — 5개 노드 파일
3. `data/ibl_nodes.yaml` — 빌드 산출물 (LLM이 실제로 보는 것)

라운드 2 정리(2026-05-27~28)가 src에는 적용됐지만 패키지 yaml에는 미적용. 현재 사고 대기 상태:
- 양쪽 정의 151개 중 **71건 description 불일치**
- 패키지에만 있는 옛 액션 73개 (라운드 2가 통합한 잔여물)
- `_auto_register_packages`가 mtime 비교만으로 sync 결정 → 누가 패키지 yaml 만지면 라운드 2가 부분 롤백됨

### 처음부터 다시 만들어도 같은 답 (옵션 B)
IBL은 어휘 시스템(`[[architecture_ibl_as_vocabulary]]`). 사전은 하나여야 함. 라운드 N 정리·해마 학습 데이터 누적·자가 진단 모두 중앙 카탈로그를 전제. **`ibl_nodes_src/`를 단일 진실 소스로, 패키지 ibl_actions.yaml은 폐기**.

### 최종 상태
```
data/ibl_nodes_src/<node>.yaml     # 사람이 직접 편집 (단일 진실 소스)
                ↓ build_ibl_nodes.py (명시적 명령)
data/ibl_nodes.yaml                # 빌드 산출물 (header: GENERATED, 직접 편집 금지)

data/packages/installed/tools/<pkg>/
├── handler.py                     # 핸들러 코드
├── tool.json                      # LLM 도구 schema
└── README.md
# ibl_actions.yaml 없음 ← 폐기됨
```

자동 register 메커니즘(`_auto_register_packages`)도 제거. 빌드는 항상 명시적.

---

## 2. 사전 컨텍스트 (작업 전 읽기)

### 메모리
- `[[architecture_ibl_nodes_build]]` — 빌드 흐름(이미 src+nodes 관계 기록)
- `[[architecture_ibl_as_vocabulary]]` — IBL=어휘 시스템 본질
- `[[architecture_ibl_action_criteria]]` — IBL 액션 4기준
- `[[architecture_ibl_single_action_pattern]]` — 라운드 2 통합 패턴 (op 분기)
- `[[architecture_ibl_description_cost]]` — description은 시스템 프롬프트 비용
- `[[project_self_round2]]`, `[[project_others_round2]]`, `[[project_engines_round2]]`, `[[project_limbs_round2]]`, `[[project_sense_round2]]` — 라운드 2 통합 결과
- `[[project_round2_dispatcher_audit]]` — 라운드 2 후속 디스패처 누락 fix

### 코드 진입점
- `backend/api.py:65-109` — `_auto_register_packages()` (제거 대상)
- `backend/ibl_action_manager.py:73` — `register_actions()` (read-only로 강등 또는 제거)
- `backend/bootstrap_ibl_actions.py` — 역방향 도구, 전체 폐기
- `scripts/build_ibl_nodes.py` — 빌드 도구 (header 자동 삽입 추가)
- `backend/ibl_access.py:91` — `build_environment()` (LLM 카탈로그 빌더, 변경 불필요)

### 데이터 진입점
- `data/ibl_nodes_src/{meta,sense,self,limbs,others,engines}.yaml` — 6개 파일이 src 전체
- `data/_ibl_provenance.yaml` — 패키지 소유권 추적 (폐기 또는 read-only)

---

## 3. 현재 상태 수치 (작업 전 baseline)

| 데이터셋 | 액션 수 |
|---|---|
| `ibl_nodes.yaml` | 195 (sense 77 / self 50 / limbs 39 / others 6 / engines 23) |
| `ibl_nodes_src/*.yaml` | 195 (=ibl_nodes.yaml과 일치) |
| 패키지 ibl_actions.yaml 33개 합 | 224 |
| _ibl_provenance.yaml | 364 (역사적 누적) |
| 양쪽 정의 (src ∩ 패키지) | 151 — desc 불일치 71건 |
| 패키지 only | 73 (대부분 라운드 2 통합 잔여물) |
| src only | 44 (라운드 2 신규 통합 + 백엔드 코어) |

빌드 산출물 IBL 프롬프트 크기: **29,145자** (이 작업 전후 ±5% 이내 유지가 목표).

---

## 4. 위험과 핵심 점검 포인트

### 사라질 위험 있는 액션 (Phase 1에서 점검 필수)
패키지 only 73개 중 src에 통합되지 않은 **진짜 신규**가 사라지면 안 됨. 의심 후보:
- `engines:publish_create/list/status` (publishing 패키지) — src에 없음, 라운드 2 미적용
- `self:health_query`, `self:health_save` (health-record) — src의 `[self:health]{op}`로 흡수됐는지 확인
- `limbs:cursor_position`, `limbs:mouse_move` 등 (computer-use 9개) — src의 `[limbs:desktop]{op}`로 흡수됐는지 확인
- 그 외 67개도 같은 패턴 확인

### 핸들러 디스패처 호환성
- src의 통합 액션(예: `[self:goal]{op:list}`)이 옛 패키지 액션(예: `[self:list_goals]`)의 모든 케이스를 처리하는지
- 핸들러 코드(`handler.py`)의 op 분기가 정확한지

### LLM 학습 흔적 (해마)
- 옛 액션 이름이 `data/training/ibl_distilled.json`이나 `ibl_synthetic_opus_final_2479.json`에 남아 있을 수 있음
- 작업 후 해마 코퍼스 점검 (별건이지만 기록)

---

## 5. 작업 단계

### Phase 0 — 준비 (20분)
```bash
cd /Users/kangkukjin/Desktop/AI/indiebizOS
git checkout -b ibl-source-unification
# 백업 폴더
mkdir -p /tmp/ibl_backup_$(date +%Y%m%d)
cp -r data/packages/installed/tools/*/ibl_actions.yaml /tmp/ibl_backup_$(date +%Y%m%d)/ 2>/dev/null
cp data/_ibl_provenance.yaml /tmp/ibl_backup_$(date +%Y%m%d)/
cp data/ibl_nodes.yaml /tmp/ibl_backup_$(date +%Y%m%d)/
```
체크:
- [ ] 새 브랜치 활성화 확인
- [ ] 백업 폴더에 33개 yaml + provenance + nodes 사본 존재

### Phase 1 — 누락 액션 보존 (1-2시간)
**목표**: 패키지 ibl_actions.yaml 폐기 시 ibl_nodes.yaml에서 사라질 액션이 없게 함.

작업:
1. 패키지 only 73개 → src 매핑 자동 분석 스크립트 작성:
   - 각 액션에 대해 src의 같은 패키지 소유 통합 액션 후보 표시
   - description 유사도 + handler tool 이름 기반 매칭
2. 사람 검토:
   - "이 옛 액션이 정말 [self:xxx]{op:yyy}로 흡수됐는가?" 케이스별 판단
   - 흡수된 것: 패키지 yaml만 제거하면 됨 (Phase 3)
   - 흡수 안 된 진짜 신규(publishing 3개 등): src에 추가
3. src 추가 작업:
   - `data/ibl_nodes_src/<node>.yaml`에 해당 액션 정의 작성
   - description / target_description / router / tool / group / keywords 채우기
   - 패키지의 handler.py가 이미 처리하는지 확인 (정합)
4. 재빌드 + 검증:
   ```bash
   python3 scripts/build_ibl_nodes.py
   python3 scripts/build_ibl_nodes.py --check
   ```
체크:
- [ ] 73개 모두 분류 완료 (흡수됨 / src 추가 필요)
- [ ] src 추가분 액션 호출 정상 (curl로 1개씩 sample)
- [ ] --check 통과

### Phase 2 — description 불일치 71건 정리 (30분-1시간)
**목표**: 양쪽 정의 151개 중 desc 다른 71건을 src 기준으로 통일.

작업:
1. 불일치 71건 list 추출 (스크립트로)
2. 표본 10건 사람 검토 — src가 더 새로움(라운드 2 결과)이 일반적인지 확인
3. 패키지 측 desc 무시(어차피 Phase 3에서 패키지 yaml 폐기) → 사실상 추가 작업 없음
4. 단, 패키지 측이 더 정확한 정보가 있는 케이스가 발견되면 src로 옮김

체크:
- [ ] 71건 표본 검토 보고서 (간단히 메모)
- [ ] 필요 시 src 보정

### Phase 3 — 패키지 ibl_actions.yaml 폐기 (30분)
작업:
```bash
# 이미 Phase 0에서 백업했음
find data/packages/installed/tools -name 'ibl_actions.yaml' -delete
# (또는 안전하게 mv로 백업 폴더 이동 후 git rm)
```
빌드 + 검증:
```bash
python3 scripts/build_ibl_nodes.py
python3 scripts/build_ibl_nodes.py --check
# 액션 수가 Phase 1 후 수치(예: 198)와 일치하는지
```
체크:
- [ ] 33개 파일 제거 확인
- [ ] ibl_nodes.yaml 액션 수 = (195 + Phase 1 추가분)
- [ ] --check 통과

### Phase 4 — 백엔드 코드 정리 (1-2시간)
제거/변경 대상:

**`backend/api.py`**
- [ ] `_auto_register_packages()` 함수 (line 65-109) 제거
- [ ] 그 함수 호출 지점(lifespan startup 등) 제거
- [ ] import 정리

**`backend/ibl_action_manager.py`**
- [ ] `register_actions()` — 다른 사용처 grep 후, 없으면 제거
- [ ] `_save_yaml`, `_backup_nodes`, `_save_provenance` — 변경계 함수 제거
- [ ] 읽기 전용 함수(`_load_provenance` 등)는 유지해도 무방
- [ ] 파일 자체를 폐기할 수 있으면 폐기

**`backend/bootstrap_ibl_actions.py`**
- [ ] 전체 폐기 (역방향 도구이므로 더 이상 의미 없음)
- [ ] git rm

**`data/_ibl_provenance.yaml`**
- [ ] 폐기 또는 README로 강등 (역사적 누적)
- [ ] 단, 다른 곳(예: x-ray)에서 참조하는지 확인 후 결정

검증:
```bash
grep -rn "_auto_register_packages\|register_actions\|bootstrap_ibl_actions" backend/ scripts/
# 모두 제거됐는지
```
체크:
- [ ] grep 결과 0건
- [ ] 백엔드 import 에러 없음 (python3 -c "import api" 같은 sanity check)

### Phase 5 — 빌드 산출물 명시화 (15분)
**`scripts/build_ibl_nodes.py` 수정**:
- `target.write_text(merged, ...)` 직전에 header 자동 prepend:
  ```python
  header = (
      "# GENERATED — DO NOT EDIT\n"
      "# Source: data/ibl_nodes_src/{meta,sense,self,limbs,others,engines}.yaml\n"
      "# Rebuild: python3 scripts/build_ibl_nodes.py\n"
      "# Check  : python3 scripts/build_ibl_nodes.py --check\n\n"
  )
  target.write_text(header + merged, ...)
  ```
- `--check`는 header 제거 후 비교하도록 수정 (또는 header도 결정론적이므로 그대로 비교)

체크:
- [ ] 재빌드 후 ibl_nodes.yaml 첫 줄 header 확인
- [ ] --check 통과

### Phase 6 — (선택) 디렉토리 개명 (1시간)
ibl_nodes_src → 더 명확한 이름으로:
- 후보: `data/ibl/` (가장 짧음), `data/ibl_source/`, `data/ibl_definitions/`
- 영향 받는 코드: `scripts/build_ibl_nodes.py`의 `src_dir` 경로
- 영향 받는 메모리: `[[architecture_ibl_nodes_build]]` 업데이트

이 단계는 보류 가능. 우선 기능적 정리가 끝난 후 별건 PR로.

### Phase 7 — 검증 (1시간)
백엔드 재시작 후:
- [ ] `curl localhost:8765/xray/data` — failing_actions 0건
- [ ] 노드별 sample 호출:
  ```bash
  for code in '[sense:legal]{query:"민법",project_id:"법률"}' \
              '[engines:web_catalog]{kind:"components",project_id:"컨텐츠"}' \
              '[others:channel_read]{channel_type:"gmail",account:"indienetkukjin@gmail.com",max_results:3}' \
              '[self:time]' \
              '[self:goal]{op:"list"}'; do
    curl -s -X POST localhost:8765/ibl/execute -H 'Content-Type: application/json' -d "{\"code\":\"$code\"}" | head -c 200
    echo
  done
  ```
- [ ] 모든 호출 success
- [ ] LLM이 보는 IBL 프롬프트 크기 측정 — baseline 29,145자 ±5%

### Phase 8 — 문서/메모리 업데이트 (30분)
- [ ] `CLAUDE.md` — IBL 시스템 섹션에서 패키지 ibl_actions.yaml 언급 제거 (있다면)
- [ ] `data/system_docs/ibl.md`, `architecture.md`, `technical.md` — 빌드 흐름 도해 업데이트
- [ ] `[[architecture_ibl_nodes_build]]` 메모리 — 패키지 yaml 폐기 반영
- [ ] 새 메모리 작성 검토: `architecture_ibl_unification` — 이번 작업의 배경/결정 과정 기록 (장기 가치 있음)

---

## 6. 롤백 계획

작업 브랜치에서 진행. 문제 시:
```bash
git checkout main
# 백업한 패키지 yaml 복원 (필요 시)
cp /tmp/ibl_backup_*/ibl_actions.yaml data/packages/installed/tools/<pkg>/
```
`_auto_register_packages` 등 코드는 git revert.

---

## 7. 추정 작업 시간

| Phase | 시간 |
|---|---|
| 0 준비 | 20분 |
| 1 누락 보존 | 1-2시간 (가장 신중해야) |
| 2 desc 불일치 | 30분-1시간 |
| 3 패키지 yaml 폐기 | 30분 |
| 4 백엔드 코드 정리 | 1-2시간 |
| 5 산출물 명시화 | 15분 |
| 6 개명 (선택) | 1시간 — 별건 가능 |
| 7 검증 | 1시간 |
| 8 문서/메모리 | 30분 |
| **합계** | **6-8시간** (Phase 6 제외) |

1-2 작업 세션으로 완료 가능.

---

## 8. 다음 세션 시작 시 첫 명령

새 세션에서:
```
docs/IBL_SOURCE_UNIFICATION_PLAN.md 읽고 Phase 0부터 시작해줘.
관련 메모리(architecture_ibl_*)도 같이 참조하고.
중요한 갈림길이 나오면 진행 전에 물어봐.
```

진행 중 중요 갈림길 (사용자 확인 필요):
- Phase 1: 패키지 only 73개 중 흡수 vs 신규 판정 애매한 케이스
- Phase 4: `_ibl_provenance.yaml` 완전 폐기 vs read-only 보존
- Phase 6: 디렉토리 개명 여부

---

*작성: 2026-05-28 (claude-opus-4-7[1m])*
*이 문서는 작업 완료 후 docs/IBL_SOURCE_UNIFICATION_DONE.md로 옮기거나 git rm 권장.*
