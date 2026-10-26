# 98회차 수리 보고 — `fold_receipt` 미관측(None) 오판정

- 대상: `backend/test_repair_training_subject_copy.py` (git 미추적 사본), 함수 `fold_receipt`
- 수리안: 격리 제안 `20261026_231149_53adcb98552048bba187781f3e5ff6dd`
  - 사본 위치: `/Users/kangkukjin/Desktop/AI/indiebizOS/.worktrees/repair-proposal-20261026_231149_53adcb98552048bba187781f3e5ff6dd/backend/test_repair_training_subject_copy.py`
- 범위: 격리 사본 수리안과 검증까지만 했습니다. 정본 반영(apply), 재기동, 커밋은 하지 않았습니다.

## 1. 결함과 원인

수정 전 본문은 `all(value is True ...)`이면 `achieved`, 아니면 모두 `failed`를 반환했습니다. 반환값이 두 가지뿐이어서 `None`(미관측)이 섞인 경우도 `failed`로 접혔습니다. 요구에 있는 판정 순서(False 우선 → None → 전부 True)도 빠져 있었습니다.

## 2. 수정 전 재현 (지정 명령, 정본 사본에서 실행)

`INDIEBIZ_REPAIR_TRAINING_SUBJECT=1 .venv/bin/python3 -m pytest backend/test_repair_training_subject_copy.py -q`

- 출력 `..F.`, 종료 코드 1
- `FAILED ...::test_none_is_unverified` — `assert 'failed' == 'unverified'`
- 결과: 3 passed / 1 failed. 계획의 전제와 일치했습니다.
- 원문: `before_pytest.txt`

## 3. 변경 범위 (`fold_receipt.diff`)

```diff
@@ -19,9 +19,11 @@
 def fold_receipt(applied, activated, committed):
     """세 관측을 achieved / failed / unverified 로 접는다."""
     observations = (applied, activated, committed)
-    if all(value is True for value in observations):
-        return "achieved"
-    return "failed"
+    if any(value is False for value in observations):
+        return "failed"
+    if any(value is None for value in observations):
+        return "unverified"
+    return "achieved"
```

- hunk는 하나뿐이며 변경 줄은 모두 함수 본문(22–24행 → 22–26행) 안에 있습니다.
- 시그니처, docstring, `observations` 행, 시험 4개, `ENABLED`/`skipif` 활성화 조건, import, `__main__`은 바뀌지 않았습니다(diff 전체가 위 hunk 하나).
- 정본 파일은 바뀌지 않았습니다. 수정 전과 후 모두 sha256 `16c736c2…b601a`입니다. 사본의 해시는 `f7a0c65a…6228`입니다.

## 4. 판정 ① 도구 검사 통과 (pytest·patch 관문)

- `self:patch` 관문 결과: live_sync, staged_drift, py_compile, import_smoke, ibl_triangle, body_bundle 모두 통과했습니다(`verified:true`).
  - 다만 patch 응답의 `diff` 필드는 빈 문자열이었습니다(미추적 파일이라 그런 것으로 추정). 그래서 변경 범위는 위의 직접 `diff -u`로 확인했습니다.
- 지정 명령을 격리 사본 루트에서 실행했습니다(정본 `.venv` 사용).
  - 결과: `....`, 종료 코드 0. PASSED 4개(`test_all_true_is_achieved`, `test_explicit_false_is_failed`, `test_none_is_unverified`, `test_false_beats_none`)이고 SKIPPED는 0건입니다.
  - 원문: `after_pytest.txt`
  - 이 환경의 pytest 설정에서는 마지막 "4 passed" 요약 줄이 출력되지 않았습니다. 그래서 4 passed는 `-rA`의 PASSED 4줄과 종료 코드 0으로 확인했습니다.
- **해석:** 예제 4개는 27조합 중 4개만 덮고 인자 순서는 검사하지 않습니다. 따라서 이 통과만으로는 요구 충족을 판단하지 않았습니다.

## 5. 판정 ② 요구 충족 (시험 파일 밖 전수 대조)

검증 스크립트는 `verify_truth_table.py`입니다. 대상 파일을 경로로 import한 뒤 {True, False, None}³ = 27조합을 요구 진리표와 대조합니다. 각 조합에 대해서는 모든 순열을 돌려 판정이 기대값 하나로 모이는지도 확인합니다.

| 대상 | 조합 | 진리표 불일치 | 순열 위반* | 기대 분포(achieved/failed/unverified) | 종료 코드 |
|---|---|---|---|---|---|
| 수정 전(정본 사본) | 27 | **7** | 7 | 1 / 19 / 7 | 1 |
| 수정 후(격리 사본) | 27 | **0** | 0 | 1 / 19 / 7 | 0 |

\* 순열 위반은 "순열 결과 집합 ≠ {기대값}"으로 셌습니다. 수정 전 함수도 순서에는 대칭이었습니다. 수정 전의 7건은 순서 의존이 아니라 오답 7건이 순열에서도 그대로 나온 것입니다.

- 수정 전 불일치 7건은 False가 없고 None이 하나 이상인 조합 전부였습니다. 모두 `failed`가 나왔고 기대값은 `unverified`였습니다. 결함 설명과 정확히 같습니다.
- 수정 후에는 27조합 모두 기대값과 일치했고, 각 조합의 순열 판정도 모두 같았습니다.
- 원문: `truth_before.json`, `truth_after.json`
- **요구 충족 판단 근거:** 요구가 정의하는 입력 공간({True, False, None}³)을 빠짐없이 대조했고, 순서 불변성을 전수로 확인했습니다. 수정 본문도 요구 문장과 같은 구조입니다(False가 있으면 failed → None이 있으면 unverified → 그 밖은 achieved). 이 범위 안에서 요구를 충족한다고 판단합니다.

## 6. 미확인 · 범위 밖

- **미확인(요구에 정의되지 않음):** True·False·None이 아닌 입력(`1`, `0`, `"yes"` 등)은 처리 방식이 정해져 있지 않습니다. 수정 후 본문은 `is` 비교만 하므로 이런 값을 `achieved`로 판정합니다(예: `0`은 False로 취급되지 않음). 이것이 의도에 맞는지는 확인하지 못했습니다.
- **범위 밖(하지 않음):** 정본 반영(`[self:patch]{op:"apply"}`), 적용 후 활성 확인, 커밋, 재기동은 하지 않았습니다. 정본 `test_repair_training_subject.py`와 기존 격리 세션(task_sysai_* 3건)도 건드리지 않았습니다.
- 제안은 적용 대기 상태로 남아 있습니다. 쓰지 않으려면 `discard{proposal_id}`로 정리해야 합니다.

## 7. 산출물

같은 폴더(`outputs/long_sentence_imagination/2026-10-26_98회차/ai/`)에 저장했습니다.

- `before_pytest.txt`
- `after_pytest.txt`
- `fold_receipt.diff`
- `verify_truth_table.py`
- `truth_before.json`
- `truth_after.json`
- `report.md`
