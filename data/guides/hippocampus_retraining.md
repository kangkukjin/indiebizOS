# 해마 임베딩 재학습 가이드

해마(`data/models/ibl_embedding/`)는 "자연어 → 과거 IBL 용례"를 연상하는 fine-tuned
임베딩 모델이다. 새 어휘를 만들면 코퍼스에는 바로 들어가지만 **모델 가중치는 재학습
전까지 그 어휘를 모른다** — 그래서 새 액션 작업의 끝에 늘 "⏳재학습 대기열"이 붙는다.
이 문서는 그 재학습을 실제로 돌리는 절차다.

> 관련: `new_action_checklist.md`(어휘 추가 시 해마 시딩) · `action_removal.md`(어휘 제거
> 시 코퍼스 정리) · `data/system_docs/memory.md`(기억 7종 지도).
> 클라우드(Colab/Modal) 경로는 `cloud_training/README.md`. **다만 그 문서의 "로컬은
> OOM" 전제는 옛 맥에어 기준이다** — 아래 §1 참조.

---

## 0. ★함정 두 개 — 시작하기 전에 반드시

이 둘을 모르면 조용히 망가진다. 에러가 안 난다는 게 핵심이다.

### ① 학습기는 **라이브 모델 폴더에 직접 덮어쓴다**

`ibl_embedding_trainer.py` 의 `MODEL_OUTPUT_DIR` 는 스테이징 폴더가 아니라
**지금 백엔드가 쓰고 있는 `data/models/ibl_embedding/`** 이고, 최고 기록 epoch 마다
그 자리에 `model.save()` 한다.

```bash
# 돌리기 전에 반드시 — 이 백업이 곧 비교의 A 면이자 롤백 경로다
cp -R data/models/ibl_embedding "data/models/ibl_embedding.bak.$(date +%Y%m%d_%H%M%S)"
```

백업 없이 돌리면 **비교할 옛 모델이 사라져 채택 판단 자체를 못 한다**(새 모델이 더
나쁜지 알 방법이 없다). 또 학습 중엔 그 폴더가 반쯤 쓰인 상태라, 그 동안 모델을
새로 로드하는 다른 프로세스는 깨진 걸 읽는다(이미 로드해 둔 백엔드는 메모리에 있어 무관).

### ② **재색인 없이 백엔드를 재시작하면 조용히 망가진다**

새 모델이 인코딩한 질의를 **옛 모델이 만든 벡터**와 비교하게 되어 회상 품질이
무너지는데, **에러는 하나도 안 난다**. 순서를 지킬 것:

```
백업 → 학습 → A/B 비교 → 채택 → epoch_* 삭제 → rebuild_index() → 백엔드 재시작
                                                  ^^^^^^^^^^^^^ 재시작보다 먼저
```

재시작이 먼저 일어나 버렸다면 **즉시 재색인**하면 봉합된다(2026-08-04 실제로 그렇게 됐다).

---

## 1. 어디서 돌릴 것인가 — 맥미니면 로컬

| 기계 | 판정 |
|------|------|
| 맥미니 M4 Pro (24GB) | **로컬로 그냥 된다.** epoch 당 ~100초, 전체 15분. 2026-07-21·08-04 실증 |
| 옛 맥에어 | OOM(batch 4→2 강제) — 클라우드 경로가 이때 생겼다 |

```bash
cd ~/Desktop/AI/indiebizOS
nohup python3 backend/ibl_embedding_trainer.py > /tmp/retrain.log 2>&1 &
```

MPS(Apple Silicon GPU)를 쓴다. 진행 로그가 길어 백그라운드 + 로그 파일이 편하다.

## 2. 레시피 (코드에 박혀 있는 값)

| 항목 | 값 | 위치 |
|------|----|------|
| 베이스 모델 | `jhgan/ko-sroberta-multitask` | `BASE_MODEL` |
| batch_size | **8** | `DataLoader(..., batch_size=8)` |
| max_seq_length | 64 | 의도·설명·코드가 대개 30~50토큰 |
| epochs | 10 (patience 3 조기종료) | `max_epochs` / `patience` |
| seed | 42 | `random.seed(42)` — 분할 재현성 |
| loss | MultipleNegativesRankingLoss | batch 안 다른 샘플이 negative |

**코퍼스 = `ibl_usage.db` + `data/training/*.json` 전부.** 주의: 글롭이 `*.json` 이라
`....json.bak.xxx` 같은 백업은 자동 제외되지만, **`.json` 으로 끝나는 파일은 무엇이든
학습에 들어간다**(예: `_proposed_verify_intents_20260525.json` 40건). 임시 파일을
`data/training/` 에 `.json` 으로 두지 말 것.

**액션별 상한 20건** 밸런싱이 걸린다 — 용례를 100건 심어도 20건만 학습된다. 희소
어휘와 과다 축적 어휘의 격차를 줄이는 장치이고, 이것 때문에 **희소 어휘 프로브는
재학습마다 흔들린다**(§5 참조).

## 3. 채택 판정 — 사과 대 사과

baseline(소생 모델) 대비 수치는 의미가 제한적이다. **직전 라이브 모델과 같은 분할에서**
비교해야 한다.

```bash
python3 cloud_training/compare_models.py \
    data/models/ibl_embedding.bak.<타임스탬프> \   # A = 직전 라이브(백업)
    data/models/ibl_embedding                      # B = 새 모델
```

두 모델을 **현재 코퍼스의 동일 seed42 분할**로 평가하고 신어휘 프로브까지 돌린 뒤
채택 권고를 출력한다. 판정 기준 = **B 가 aggregate desc-Top5 에서 동급 이상**이고
회귀가 없을 것.

### ★프로브를 매번 늘려라

`compare_models.py` 상단 `PROBES` 는 "옛 모델이 약하던 질의 → 기대 액션" 목록이다.
**지난 재학습 이후 새로 만든 어휘를 여기 추가하지 않으면 흡수 여부를 측정할 수 없다.**
경계 반대편(비슷하지만 다른 액션으로 가야 하는 질의)도 같이 넣으면 "새 어휘를 당기다
옛 어휘를 밀어냈는지"가 잡힌다.

## 4. 채택 후 마무리

```bash
# ① epoch 체크포인트 삭제 — 각 423MB, 8개면 3.3GB
rm -rf data/models/ibl_embedding/epoch_*

# ② 재색인 (필수! 재시작보다 먼저)
cd backend && python3 -c "from ibl_usage_db import IBLUsageDB; print(IBLUsageDB().rebuild_index())"

# ③ 백엔드 명시적 재시작
```

재색인 후 **행 수 == 벡터 수**를 확인할 것(불일치 = 색인 누락).

라이브 검증은 `/ibl/translate` 로 — 새로 흡수됐어야 할 질의와, 밀려나면 안 되는
경계 질의를 함께 던진다.

### 롤백

```bash
rm -rf data/models/ibl_embedding
mv data/models/ibl_embedding.bak.<타임스탬프> data/models/ibl_embedding
# → rebuild_index → 백엔드 재시작
```

## 5. 이력 (같은 레시피)

| 날짜 | 코퍼스 | 최적 epoch | 검증 | 비고 |
|------|--------|-----------|------|------|
| 2026-07-13 | — | — | — | 레시피 확립 |
| 2026-07-21 | 2,871 | 5 | 0.882 | code T1/5 67.6/92.5 · desc T1/5 72.9/95.2 |
| 2026-08-04 | 2,988 | 5 | 0.882 | 동일 분할 A/B 에서 6지표 전부 우세(code T5 88.9→92.2, desc T5 92.2→94.2) |
| 08-16 ~ 08-22 오전 | — | — | — | ★이 표가 빠뜨린 회차들 — `data/models/ibl_embedding.bak.*` 백업이 증거(08-16 ×2·08-17 ×2·08-19·08-20·08-21·08-22 오전). 수치는 남아 있지 않아 적지 않는다(모르는 걸 적는 것보다 빈칸이 정직하다) |
| 2026-08-22 14:11 | 3,538건 → **학습쌍 6,553** | **10** | 0.864 | 19회차 수리 커밋 직후. A/B(동일 분할): desc T1 74.9→78.6(+3.7p)·T5 94.5→95.0 / code T5 90.1→89.4(-0.7p) · 프로브 43→46(+3) → 채택 |

**★2026-08-22 관찰 — 코퍼스가 커지자 최적 epoch 이 뒤로 밀렸다.** 07-21·08-04 은 학습쌍
3천 안팎에서 epoch 5 가 두 번 연속 최적이었는데, 6,553쌍에서는 **epoch 10(마지막)이 최적**
이었고 점수가 9→10 에서도 계속 오르는 중이었다(0.855→0.864). 즉 이번엔 **10 이 천장이
아니라 벽**일 수 있다 — 다음 회차에 `max_epochs` 를 늘려 더 오르는지 볼 것.

**지표는 분할이 같을 때만 비교된다.** 07-21 의 92.5% 와 08-04 의 92.2% 를 나란히 놓으면
안 된다 — 코퍼스가 달라 분할(935쌍/393패턴 → 889쌍/399패턴)이 다르다. 이래서 §3 의
A/B 비교가 필요하다.

**★프로브도 썩는다 — 양쪽 모델이 다 틀리면 어휘부터 의심할 것.**
`sense:travel` 3건과 `limbs:iframe` 1건은 07-21·08-04 양쪽 모델이 다 틀렸는데, 원인은
"코퍼스가 얇다"가 아니라 **그 액션들이 은퇴해 어휘에 없다는 것**이었다(2026-08-04 확인.
국내 숙박은 `sense:stay` 가 승계). 존재하지 않는 액션을 기대값으로 둔 프로브는 영원히
못 맞히고, 프로브 점수를 조용히 깎아 A/B 판정을 흐린다.

→ 어휘를 은퇴시킬 때 `PROBES` 도 함께 정리할 것(`action_removal.md` 의 대칭 절차와 같은 결).
→ 양쪽 모델이 똑같이 틀리는 프로브가 보이면 재학습 탓하기 전에
   **그 액션이 아직 살아 있는지부터** 확인하라.

## 6. 관련 함정 — 용례 시딩

재학습 전에 용례를 심을 때:

```python
db = IBLUsageDB()
db._load_model_sync()          # ★이게 먼저
db.add_examples_batch(SEEDS)   # source='manual_seed'
```

`_load_model_sync()` 없이 `add_examples_batch` 를 부르면 임베딩 모델이 **백그라운드
로딩 중**이라 **벡터가 조용히 안 붙는다**(FTS 로만 걸려 회상되는 척한다). 신호는
`export_hippo_index` 의 "누락 N" 또는 행 수 ≠ 벡터 수.

`source='manual_seed'` 는 `rebuild_usage_db` 덮어쓰기를 피한다. 다만 **다음 파인튜닝이
배우게 하려면 `data/training/ibl_distilled.json` 에도 같은 용례를 넣어야 한다** —
DB 는 회상용, training json 은 학습용으로 역할이 갈린다.
