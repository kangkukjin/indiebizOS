# 핸드오프 — 해마 재학습 ✅ 해결됨 (2026-05-29 v12)

> **상태: 완료.** v12(batch=4 + 메모리 위생 3종)로 **Top-5 91.4%** 달성, 채택·재색인·검증 완료.
> 재발 시 교훈/절차는 메모리 노트 `[[project_hippocampus_retrain_memory]]` 참조.
>
> **결과 요약:** Top-1 62.8% / Top-3 86.1% / **Top-5 91.4%** (baseline 42.3%). 최적 epoch 4.
> **근본 원인:** 0.948→0.830 하락은 어휘 정리/desc 길이가 아니라 **OOM이 강제한 batch 4→2**.
> **해결:** ① 평가 CPU화(+fit 전 model.to('mps')) ② max_seq_length 128→64 ③ epoch마다 empty_cache + `HIGH_WATERMARK_RATIO=0.0` 제거(graceful 제동). caffeinate 제거는 부차적.
> **후속 완료:** `IBLUsageDB().rebuild_index()`로 용례 DB 2264건 새 모델 재인코딩(rebuild_usage_db.py 아님!).
> 백업 보존: `data/models/ibl_embedding.bak.pre_op_vocab_20260528_181842`(0.948, 옛 어휘).

---

<details>
<summary>이하 원본 핸드오프 (v9 시점, 역사적 기록) — 펼치기</summary>

**작성: 2026-05-29 (이전 세션에서 준비 완료)**

새 세션의 Claude에게: 사용자가 학습 시작을 요청하면 **아래 "즉시 실행" 섹션 그대로 시작**하면 됩니다. 추가 정찰·확인 불필요 — 모든 준비가 끝나 있습니다.

---

## 즉시 실행 (사용자 신호 시)

### 1. 학습 시작 명령

`Bash` 도구로 background 실행:

```bash
cd /Users/kangkukjin/Desktop/AI/indiebizOS && PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 python3 backend/ibl_embedding_trainer.py 2>&1 | tee /tmp/ibl_train_v9_$(date +%Y%m%d_%H%M%S).log
```

- `run_in_background: true`로 띄울 것
- **`caffeinate` 절대 추가하지 말 것** — 사용자 직관상 caffeinate가 이번에 system kill을 늘렸음. 빼는 게 핵심
- 사용자에게 노트북 닫지 말라고 한 줄 안내

### 2. 시작 후 보고

명령 시작했음 보고 + background ID 명시 + 예상 시간(~1.5시간) 알려주기.

---

## 이미 준비된 상태 (확인 불필요)

| 항목 | 상태 |
|---|---|
| `data/models/ibl_embedding/` | 백업 모델(0.948) 복원됨. 학습이 덮어쓸 것 |
| `data/models/ibl_embedding.bak.pre_op_vocab_20260528_181842/` | 안전 백업 (학습 실패 시 복원 대상) |
| `backend/ibl_embedding_trainer.py` line 320 | `batch_size=2` (확정 — batch=1은 loss=0이라 작동 안 함) |
| trainer 코드 line 290~314 | **intent-intent 페어 제거** (주석), **description 페어 유지** |
| `data/training/*.json` | 라운드 2 변환 완료 (옛 액션 → 새 op 형식) |
| `data/ibl_usage.db` | 라운드 2 변환 완료 |
| Python 환경 | sentence-transformers, torch (MPS) 설치됨 |

## 진행 모니터링 명령

사용자가 "어떻게 돼?" 류 질문 시:

```bash
# 진행 마커
grep -E "\[Epoch [0-9]+\] 검증 점수|결과 비교|OOM|RuntimeError|Top-[0-9]+:" /tmp/ibl_train_v9_*.log | tail -20

# epoch 산출 디렉토리
ls -d /Users/kangkukjin/Desktop/AI/indiebizOS/data/models/ibl_embedding/epoch_* 2>/dev/null

# 메모리
vm_stat | awk '/Pages free/ {f=$3+0} /Pages inactive/ {i=$3+0} /Pages speculative/ {s=$3+0} /Pages wired/ {w=$4+0} END { printf "available=%.1fGB  wired=%.0fMB\n", (f+i+s)*16/1024/1024, w*16/1024 }'

# 프로세스
ps aux | grep ibl_embedding_trainer | grep -v grep
```

## 학습 완료 후 평가

`pilot_results.json` 갱신되면 백업(0.948)과 비교:

```bash
cat /Users/kangkukjin/Desktop/AI/indiebizOS/data/models/ibl_embedding/pilot_results.json
```

**결정 기준**:
- 새 모델 Top-5 (code) ≥ 0.90이면: 새 모델 채택, 새 어휘 직접 인지 + op 차원 정확도 확보
- 새 모델 Top-5 < 0.85이면: 백업 복원 권고(0.948), 별칭 시스템 의존
- 그 사이면: 사용자에게 trade-off 보고 (옛 어휘 정확도 vs 새 어휘 직접 인지)

백업 복원 명령:
```bash
cd /Users/kangkukjin/Desktop/AI/indiebizOS/data/models && rm -rf ibl_embedding && cp -R ibl_embedding.bak.pre_op_vocab_20260528_181842 ibl_embedding
```

---

## 컨텍스트 (오늘 작업 요약 — 새 세션 Claude를 위한 배경)

오늘(2026-05-29) 작업으로 IBL이 거의 "닫힌 언어" 상태가 됐습니다:

1. **op 어휘 단일화** — `data/ibl_nodes_src/*.yaml`의 op-bearing 24개 액션에 `ops: {default, values}` 블록 추가
2. **삼각 검증** — `scripts/build_ibl_nodes.py --check`로 src ↔ tool.json ↔ handler.py `_OP_DISPATCHERS` AST 정확 비교
3. **pre-commit 훅** — `scripts/git-hooks/pre-commit` (commit 시점 게이트)
4. **self-check 합류** — `backend/world_pulse_health.run_static_ibl_check` (12시간 정기 게이트)
5. **dispatcher 표준화** — 9 op-bearing 패키지 모두 `_OP_DISPATCHERS` dict 노출
6. **의식 에이전트 op 힌트 + 메타 인지 가드** — `data/common_prompts/consciousness_prompt.md`
7. **시스템 문서/CLAUDE.md/common_prompts** 모두 갱신
8. **학습 데이터/ibl_usage.db** 라운드 2 변환 완료 (226건 옛 액션 → 새 op 형식)

남은 마지막 단계: **해마 재학습**. 학습 데이터는 변환됐지만 모델이 옛 어휘로 학습된 상태. 새 어휘로 다시 학습하면 op 차원의 진정한 RAG 정확도 확보.

## 이전 시도 패턴 (참고)

오늘 8번 시도 모두 `caffeinate -i`와 함께 학습했는데 system kill 또는 사용자 중단으로 끝까지 못 감:

| 시도 | best | 죽음 |
|---|---|---|
| v3 | 0.825 | epoch 5 system kill |
| v4 | 0.829 | epoch 3 system kill |
| v5 | 0.796 | 사용자 중단 (description 페어 제거 실험) |
| v6 | 0.423 | batch=1 → loss=0 (in-batch negatives 없음) |
| v7 | — | 즉시 사망 (caffeinate 영향 의심) |
| v8 | 0.746 (epoch 1) | epoch 2 system kill |

**v9의 변경 — caffeinate 제거**. 사용자가 "이전 학습은 caffeinate 안 썼는데 잘 됐었다"고 회상. 그 직관을 따름. 한 가지 변수만 바꾸는 실험.

## 위험 + 폴백

- 또 system kill되면: 백업 모델(0.948) 복원 + 별칭 시스템으로 마무리. 학습은 별도 시점·머신에서.
- 학습 시작 시 `tee` 로그 명령은 한 줄로 합쳤지만 너무 복잡해 보이면 `tee` 부분 빼도 OK (실시간 모니터링은 background output으로 가능).

## 관련 메모리 노트

- `[[architecture_ibl_op_vocabulary]]` — op 어휘 단일화 + 검증 인프라
- `[[architecture_ibl_single_action_pattern]]` — 라운드 2 통합 패턴
- `[[project_self_diagnosis_priority]]` — 자가 진단 강화
- `[[execution-memory-architecture]]` — 해마 학습 절차
- `[[project_round2_dispatcher_audit]]` — 어제 dispatcher 누락 사고

---

**Bottom Line**: 사용자가 학습 시작 신호 주면 위 "1. 학습 시작 명령" 그대로 background 실행. 끝.

</details>
