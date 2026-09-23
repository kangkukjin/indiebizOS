"""
IBL 해마 임베딩 학습 — 클라우드(CUDA) 포팅판

backend/ibl_embedding_trainer.py 의 충실한 포팅. 로직(데이터 추출/변형/밸런싱/
정규화/description 페어/평가)은 원본과 동일하며, 다음만 변경했다:

  - device "mps" → DEVICE (cuda 우선, 없으면 cpu)
  - epoch 사이 torch.mps.empty_cache() → torch.cuda.empty_cache()
  - 평가 encode device 'cpu' → DEVICE (GPU에서 빠르게, 결과는 동일)
  - 경로를 환경변수/기본값으로 (번들 디렉터리 기준)

원본과 같은 베이스 모델(jhgan/ko-sroberta-multitask), 손실(MNR),
정규화(normalize=True), seed(42)를 쓰므로 지표가 로컬 결과와 비교 가능하다.

사용법 (Colab):
    IBL_DATA_DIR=/content/bundle/data \
    IBL_MODEL_OUT=/content/ibl_embedding \
    python ibl_embedding_trainer_cloud.py
"""

import os
import sys
import json
import random
import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass

# A standalone bundle carries the same two pure modules beside this file.
# In a checkout use the canonical implementation, never a copied policy.
_base = Path(__file__).resolve().parents[1] / 'backend' / 'base'
if _base.is_dir():
    sys.path.insert(0, str(_base))
from corpus_policy import current_examples

import torch

# ---- 경로/디바이스 (원본과 다른 부분) ----------------------------------------
DATA_DIR = Path(os.environ.get("IBL_DATA_DIR", "/content/bundle/data"))
DB_PATH = DATA_DIR / "ibl_usage.db"
MODEL_OUTPUT_DIR = Path(os.environ.get("IBL_MODEL_OUT", "/content/ibl_embedding"))

if torch.cuda.is_available():
    DEVICE = "cuda"
elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
    DEVICE = "mps"
else:
    DEVICE = "cpu"
print(f"[device] {DEVICE}")

# 배치 크기 — 원본 검증값 4. GPU면 16/32 실험 가능(README의 주의 참고).
BATCH_SIZE = int(os.environ.get("IBL_BATCH_SIZE", "4"))
MAX_SEQ_LENGTH = int(os.environ.get("IBL_MAX_SEQ", "64"))


# ============================================================================
# Step 1: 데이터 추출 및 변형 생성  (원본 그대로)
# ============================================================================

@dataclass
class TrainingPair:
    intent: str
    ibl_code: str
    group_id: int


def extract_examples_from_db() -> List[Dict]:
    """DB 용례 추출. 번들에는 보통 export JSON 만 들어있으므로 그걸 우선 사용,
    없으면 원본 DB(있을 때)에서 읽는다."""
    export_path = DATA_DIR / "ibl_examples_export.json"
    if export_path.exists():
        with open(export_path, "r", encoding="utf-8") as f:
            examples = json.load(f)
        examples, rejected = current_examples(examples)
        print(f"[데이터] export 현재 {len(examples)}개, 제외 {rejected}")
        return examples
    if not DB_PATH.exists():
        print(f"[데이터] DB/export 없음 — DB 시드 건너뜀")
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT id, intent, ibl_code, nodes, category, provenance FROM ibl_examples ORDER BY id"
    )
    examples = [dict(row) for row in cursor.fetchall()]
    conn.close()
    examples, rejected = current_examples(examples)
    print(f"[데이터] 현재 판본 자격 제외: {rejected}")
    print(f"[데이터] DB에서 {len(examples)}개 사례 추출")
    return examples


VERB_VARIATIONS = {
    "조회": ["확인", "알려줘", "보여줘", "가져와", "찾아봐", "체크"],
    "검색": ["찾아줘", "찾아봐", "검색해줘", "서치해줘", "찾아"],
    "관리": ["보여줘", "현황", "목록", "리스트"],
    "생성": ["만들어줘", "만들어", "생성해줘", "새로 만들어"],
    "저장": ["저장해줘", "기록해줘", "남겨줘", "파일로 저장", "세이브"],
    "전송": ["보내줘", "전달해줘", "전송해줘", "날려줘"],
    "실행": ["실행해줘", "돌려줘", "시작해줘", "동작시켜", "실행"],
    "목록": ["리스트", "목록 보여줘", "뭐가 있어", "뭐 있어"],
    "열기": ["열어줘", "열어", "오픈해줘", "띄워줘"],
    "삭제": ["지워줘", "삭제해줘", "제거해줘", "없애줘"],
    "수정": ["변경해줘", "바꿔줘", "고쳐줘", "업데이트해줘"],
    "확인": ["체크해줘", "봐줘", "보여줘", "확인해줘"],
}

NOUN_SYNONYMS = {
    "사이트": ["홈페이지", "웹사이트", "웹페이지"],
    "홈페이지": ["사이트", "웹사이트", "웹페이지"],
    "워크플로우": ["자동화", "작업흐름"],
    "에이전트": ["AI", "도우미", "비서"],
    "프로젝트": ["작업", "프로젝트"],
    "파일": ["문서", "파일"],
    "스케줄": ["예약", "일정", "스케줄"],
    "이메일": ["메일", "이메일", "Gmail"],
    "캘린더": ["달력", "일정", "캘린더"],
    "뉴스": ["소식", "뉴스", "기사"],
}

ENDING_VARIATIONS = [
    ("해줘", ["해", "해줄래", "해볼래", "좀 해줘", "해주세요"]),
    ("알려줘", ["알려", "알려줄래", "알려주세요"]),
    ("보여줘", ["보여", "보여줄래", "보여주세요"]),
    ("찾아줘", ["찾아", "찾아줄래", "찾아주세요"]),
]


def generate_variations(examples: List[Dict]) -> List[Dict]:
    """규칙 기반으로 자연어 변형 생성"""
    variations = []

    for ex in examples:
        intent = ex['intent']
        ibl_code = ex['ibl_code']
        generated = set()

        for verb_key, replacements in VERB_VARIATIONS.items():
            if verb_key in intent:
                for rep in replacements[:3]:
                    new_intent = intent.replace(verb_key, rep, 1)
                    if new_intent != intent and new_intent not in generated:
                        generated.add(new_intent)
                        variations.append({
                            'intent': new_intent,
                            'ibl_code': ibl_code,
                            'source': 'verb_variation'
                        })

        for noun_key, synonyms in NOUN_SYNONYMS.items():
            if noun_key in intent:
                for syn in synonyms[:2]:
                    new_intent = intent.replace(noun_key, syn, 1)
                    if new_intent != intent and new_intent not in generated:
                        generated.add(new_intent)
                        variations.append({
                            'intent': new_intent,
                            'ibl_code': ibl_code,
                            'source': 'noun_variation'
                        })

        for ending, alts in ENDING_VARIATIONS:
            if intent.endswith(ending):
                for alt in alts[:2]:
                    new_intent = intent[:-len(ending)] + alt
                    if new_intent not in generated:
                        generated.add(new_intent)
                        variations.append({
                            'intent': new_intent,
                            'ibl_code': ibl_code,
                            'source': 'ending_variation'
                        })

    print(f"[데이터] {len(variations)}개 자연어 변형 생성")
    return variations


def balance_by_action(data: List[Dict], max_per_action: int = 30) -> List[Dict]:
    """액션별 데이터 밸런싱 — 초과분은 오래된(앞쪽) 데이터부터 제거.
    (2026-06-04: 상한 20→30 — 데이터량 레버, 인기 액션에 더 많은 대조 신호.)"""
    import re
    from collections import defaultdict

    action_pattern = re.compile(r'\[(\w+:\w+)\]')

    action_indices: Dict[str, List[int]] = defaultdict(list)
    for i, item in enumerate(data):
        code = item.get('ibl_code', '')
        actions = tuple(sorted(set(action_pattern.findall(code))))
        key = "+".join(actions) if actions else "_unknown"
        action_indices[key].append(i)

    drop = set()
    trimmed_actions = []
    for key, indices in action_indices.items():
        if len(indices) > max_per_action:
            old_indices = indices[:-max_per_action]
            drop.update(old_indices)
            trimmed_actions.append(f"{key}({len(indices)}->{max_per_action})")

    if trimmed_actions:
        print(f"[밸런싱] 액션별 상한 {max_per_action}건 적용, "
              f"{len(drop)}건 제거: {', '.join(trimmed_actions)}")
    else:
        print(f"[밸런싱] 모든 액션이 상한({max_per_action}건) 이내 — 제거 없음")

    return [item for i, item in enumerate(data) if i not in drop]


def normalize_code_to_pattern(ibl_code: str) -> str:
    """IBL 코드를 액션 패턴으로 정규화 (파라미터 블록 제거)."""
    import re
    pattern = re.sub(r'\{[^}]*\}', '', ibl_code)
    pattern = re.sub(r'\s+', ' ', pattern).strip()
    return pattern


def extract_action_from_code(ibl_code: str) -> str:
    """IBL 코드에서 첫 번째 [node:action] 추출 — **머리 액션**.

    평가(desc Top-k)의 정답 라벨은 계속 이것이다. 자를 바꾸지 않는다.
    """
    import re
    match = re.search(r'\[(\w+:\w+)\]', ibl_code)
    return match.group(1) if match else ""


def extract_actions_from_code(ibl_code: str) -> list:
    """코드에 등장하는 **모든** [node:action] — 등장 순, 중복 제거.

    ★로컬 트레이너(backend/ibl_embedding_trainer.py)와 **같은 규칙**이어야 한다.
      두 트레이너가 갈리면 어느 경로로 학습했느냐에 따라 몸이 달라진다.
      가드: backend/test_desc_pair_coverage.py 의 클라우드 동기화 시험.

    왜(2026-08-23 실측): desc 쌍이 머리 액션으로만 만들어져서, 파이프의 꼬리에만 사는
    낱말은 intent→description 학습 쌍을 **한 건도** 못 받았다. 코퍼스에 나오지만 머리에
    선 적 없는 액션이 **14개, 전부 `table:` 변환자**였다.
    """
    import re
    seen, out = set(), []
    for a in re.findall(r'\[(\w+:\w+)\]', ibl_code):
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def prepare_training_data(examples: List[Dict], variations: List[Dict],
                          test_ratio: float = 0.2,
                          normalize: bool = False) -> Tuple[List, List, Dict]:
    """학습/평가 데이터 분리 및 그룹핑 (패턴 내 분할)."""
    code_to_intents: Dict[str, List[str]] = {}
    for item in examples + variations:
        code = item['ibl_code']
        if normalize:
            code = normalize_code_to_pattern(code)
        intent = item['intent']
        if code not in code_to_intents:
            code_to_intents[code] = []
        if intent not in code_to_intents[code]:
            code_to_intents[code].append(intent)

    if normalize:
        print(f"[데이터] 정규화 후 고유 패턴: {len(code_to_intents)}개")

    train_pairs = []
    test_pairs = []

    for code, intents in code_to_intents.items():
        random.shuffle(intents)
        if len(intents) <= 2:
            train_pairs.extend([(intent, code) for intent in intents])
        else:
            split_idx = max(1, int(len(intents) * (1 - test_ratio)))
            train_pairs.extend([(intent, code) for intent in intents[:split_idx]])
            test_pairs.extend([(intent, code) for intent in intents[split_idx:]])

    print(f"[데이터] 학습: {len(train_pairs)}쌍, 평가: {len(test_pairs)}쌍 "
          f"({len(code_to_intents)}개 패턴, 패턴 내 분할)")

    return train_pairs, test_pairs, code_to_intents


# ============================================================================
# Step 2: 모델 Fine-tuning
# ============================================================================

def load_action_descriptions() -> Dict[str, str]:
    """ibl_nodes.yaml에서 [node:action] -> description 매핑 로드"""
    import yaml
    nodes_path = DATA_DIR / "ibl_nodes.yaml"
    if not nodes_path.exists():
        print(f"[학습] ibl_nodes.yaml 없음({nodes_path}) — description 페어 생략")
        return {}
    with open(nodes_path) as f:
        data = yaml.safe_load(f)
    descriptions = {}
    for node_name, node_data in data.get('nodes', {}).items():
        for action_name, action_data in node_data.get('actions', {}).items():
            if isinstance(action_data, dict):
                desc = action_data.get('description', '')
                if desc:
                    descriptions[f"{node_name}:{action_name}"] = str(desc)
    return descriptions


def train_model(train_pairs: List[Tuple[str, str]], code_to_intents: Dict,
                test_pairs: List[Tuple[str, str]] = None):
    """sentence-transformer fine-tuning (intent->description 매핑 포함)"""
    from sentence_transformers import SentenceTransformer, InputExample, losses
    from torch.utils.data import DataLoader

    BASE_MODEL = 'jhgan/ko-sroberta-multitask'
    print(f"\n[학습] 베이스 모델 로딩: {BASE_MODEL}")
    model = SentenceTransformer(BASE_MODEL, device=DEVICE)   # 원본: device="mps"
    model.max_seq_length = MAX_SEQ_LENGTH

    action_descs = load_action_descriptions()
    print(f"[학습] {len(action_descs)}개 액션 description 로드")

    train_examples = []
    train_code_to_intents: Dict[str, List[str]] = {}

    for intent, code in train_pairs:
        if code not in train_code_to_intents:
            train_code_to_intents[code] = []
        train_code_to_intents[code].append(intent)

    for code, intents in train_code_to_intents.items():
        # intent -> ibl_code 쌍
        for intent in intents:
            train_examples.append(InputExample(texts=[intent, code]))

        # intent -> action description 쌍 + description -> code 쌍
        actions = extract_actions_from_code(code)
        action = actions[0] if actions else ""
        if action in action_descs:
            desc = action_descs[action]
            for intent in intents[:5]:
                train_examples.append(InputExample(texts=[intent, desc]))
            train_examples.append(InputExample(texts=[desc, code]))

        # ★꼬리 액션도 굶지는 않게 — code 당 intent 1개 (로컬 트레이너와 동일 규칙).
        #   대등한 몫을 주면 한 질의가 두 description 을 똑같이 당겨 머리의 desc Top-1 이
        #   동전던지기가 된다. 고치려는 병은 '희석'이 아니라 '굶주림'이므로 최소량만 준다.
        for tail in actions[1:]:
            if tail in action_descs and intents:
                train_examples.append(InputExample(texts=[intents[0], action_descs[tail]]))

    random.shuffle(train_examples)
    print(f"[학습] {len(train_examples)}개 학습 쌍 구성")

    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=BATCH_SIZE)
    train_loss = losses.MultipleNegativesRankingLoss(model)

    max_epochs = int(os.environ.get("IBL_EPOCHS", "10"))
    warmup_steps = int(len(train_dataloader) * 0.1)

    print(f"[학습] {max_epochs} epochs, batch={BATCH_SIZE}, warmup={warmup_steps}")

    best_score = -1
    best_epoch = 0
    patience = 4
    no_improve = 0

    for epoch in range(1, max_epochs + 1):
        model.to(DEVICE)   # 원본: model.to('mps')
        model.fit(
            train_objectives=[(train_dataloader, train_loss)],
            epochs=1,
            warmup_steps=warmup_steps if epoch == 1 else 0,
            output_path=str(MODEL_OUTPUT_DIR / f"epoch_{epoch}"),
            show_progress_bar=True,
        )

        if test_pairs:
            code_top5 = _eval_on_test(model, test_pairs, list(code_to_intents.keys()))
            # 채택 지표(desc-Top5)와 정렬 — 조기종료가 엉뚱한 epoch 고르던 문제(2026-06-03) 해소.
            if action_descs:
                desc_top5 = _eval_desc_top5(model, test_pairs, action_descs)
                val_score = 0.5 * code_top5 + 0.5 * desc_top5
                print(f"  [Epoch {epoch}] code-Top5={code_top5:.3f} desc-Top5={desc_top5:.3f} blend={val_score:.3f}")
            else:
                val_score = code_top5
                print(f"  [Epoch {epoch}] 검증 점수(code-Top5): {val_score:.3f}")
        else:
            val_score = _quick_eval(model, train_code_to_intents)
            print(f"  [Epoch {epoch}] 검증 점수(Top-5): {val_score:.3f}")

        if val_score > best_score:
            best_score = val_score
            best_epoch = epoch
            no_improve = 0
            model.save(str(MODEL_OUTPUT_DIR))
        else:
            no_improve += 1

        # epoch 사이 GPU 캐시 해제 (원본: torch.mps.empty_cache())
        try:
            if DEVICE == "cuda":
                torch.cuda.empty_cache()
            elif DEVICE == "mps":
                torch.mps.empty_cache()
            import gc as _gc
            _gc.collect()
        except Exception as _e:
            print(f"  [경고] 캐시 해제 실패(무시): {_e}")

        if no_improve >= patience:
            print(f"  [조기 종료] {patience} epoch 연속 개선 없음 -> epoch {best_epoch}이 최적")
            break

    print(f"[학습] 최적 epoch: {best_epoch} (점수: {best_score:.3f})")
    print(f"[학습] 최적 모델 -> {MODEL_OUTPUT_DIR}")

    best_model = SentenceTransformer(str(MODEL_OUTPUT_DIR), device=DEVICE)
    return best_model


def _eval_on_test(model, test_pairs: List[Tuple[str, str]], all_codes: List[str]) -> float:
    """실제 test set으로 Top-5 정확도 측정"""
    from sentence_transformers.util import cos_sim

    unique_codes = list(set(all_codes))
    test_intents = [p[0] for p in test_pairs]

    intent_embs = model.encode(test_intents, convert_to_tensor=True, show_progress_bar=False, device=DEVICE)
    code_embs = model.encode(unique_codes, convert_to_tensor=True, show_progress_bar=False, device=DEVICE)
    sims = cos_sim(intent_embs, code_embs)

    correct = 0
    for i, (_, true_code) in enumerate(test_pairs):
        top5 = sims[i].topk(5).indices.tolist()
        if true_code in [unique_codes[idx] for idx in top5]:
            correct += 1
    return correct / len(test_pairs)


def _eval_desc_top5(model, test_pairs: List[Tuple[str, str]], action_descs: Dict[str, str]) -> float:
    """채택 지표와 동일한 desc-Top5(액션 description 매칭) — 조기종료 모니터 정렬용."""
    from sentence_transformers.util import cos_sim

    action_list = list(action_descs.keys())
    desc_list = [action_descs[a] for a in action_list]
    test_intents = [p[0] for p in test_pairs]

    intent_embs = model.encode(test_intents, convert_to_tensor=True, show_progress_bar=False, device=DEVICE)
    desc_embs = model.encode(desc_list, convert_to_tensor=True, show_progress_bar=False, device=DEVICE)
    sims = cos_sim(intent_embs, desc_embs)

    correct = 0
    for i, (_, true_code) in enumerate(test_pairs):
        true_action = extract_action_from_code(true_code)
        top5 = sims[i].topk(5).indices.tolist()
        if true_action in [action_list[idx] for idx in top5]:
            correct += 1
    return correct / len(test_pairs)


def _quick_eval(model, code_to_intents: Dict) -> float:
    """빠른 검증: intent->code 매칭 정확도 (샘플링)"""
    from sentence_transformers.util import cos_sim
    import random as _rand

    codes = list(code_to_intents.keys())
    if len(codes) > 200:
        codes = _rand.sample(codes, 200)

    test_intents = []
    test_codes = []
    for code in codes:
        intents = code_to_intents[code]
        if intents:
            test_intents.append(intents[0])
            test_codes.append(code)

    if not test_intents:
        return 0.0

    intent_embs = model.encode(test_intents, convert_to_tensor=True, show_progress_bar=False, device=DEVICE)
    code_embs = model.encode(test_codes, convert_to_tensor=True, show_progress_bar=False, device=DEVICE)
    sims = cos_sim(intent_embs, code_embs)

    correct = 0
    for i in range(len(test_intents)):
        top5 = sims[i].topk(5).indices.tolist()
        if i in top5:
            correct += 1
    return correct / len(test_intents)


# ============================================================================
# Step 3: 평가
# ============================================================================

def evaluate_model(model, test_pairs: List[Tuple[str, str]],
                   all_codes: List[str], label: str,
                   action_descs: Dict[str, str] = None):
    """top-k 검색 정확도 측정 (code 매칭 + description 매칭)"""
    from sentence_transformers.util import cos_sim

    unique_codes = list(set(all_codes))
    code_embeddings = model.encode(unique_codes, convert_to_tensor=True,
                                   show_progress_bar=False, device=DEVICE)

    test_intents = [pair[0] for pair in test_pairs]
    intent_embeddings = model.encode(test_intents, convert_to_tensor=True,
                                      show_progress_bar=False, device=DEVICE)

    similarities = cos_sim(intent_embeddings, code_embeddings)

    results = {}
    for k in [1, 3, 5]:
        correct = 0
        for i, (intent, true_code) in enumerate(test_pairs):
            top_k_indices = similarities[i].topk(k).indices.tolist()
            top_k_codes = [unique_codes[idx] for idx in top_k_indices]
            if true_code in top_k_codes:
                correct += 1
        accuracy = correct / len(test_pairs) * 100
        results[k] = accuracy

    print(f"\n=== {label} (code 매칭) ===")
    print(f"  평가 쌍: {len(test_pairs)}개")
    print(f"  Top-1: {results[1]:.1f}%  Top-3: {results[3]:.1f}%  Top-5: {results[5]:.1f}%")

    if action_descs:
        action_list = list(action_descs.keys())
        desc_list = [action_descs[a] for a in action_list]
        desc_embeddings = model.encode(desc_list, convert_to_tensor=True,
                                        show_progress_bar=False, device=DEVICE)
        desc_sim = cos_sim(intent_embeddings, desc_embeddings)

        desc_results = {}
        for k in [1, 3, 5]:
            correct = 0
            for i, (intent, true_code) in enumerate(test_pairs):
                true_action = extract_action_from_code(true_code)
                if true_action not in action_list:
                    continue
                top_k_indices = desc_sim[i].topk(k).indices.tolist()
                top_k_actions = [action_list[idx] for idx in top_k_indices]
                if true_action in top_k_actions:
                    correct += 1
            accuracy = correct / len(test_pairs) * 100
            desc_results[k] = accuracy

        print(f"  --- description 매칭 (액션 단위) ---")
        print(f"  Top-1: {desc_results[1]:.1f}%  Top-3: {desc_results[3]:.1f}%  Top-5: {desc_results[5]:.1f}%")
        results['desc'] = desc_results

    return results


def main():
    random.seed(42)
    # 재현성: DataLoader(shuffle=True)는 torch RNG를 쓰므로 torch도 시딩(2026-06-04).
    try:
        import torch as _torch
        _torch.manual_seed(42)
        if _torch.cuda.is_available():
            _torch.cuda.manual_seed_all(42)
    except Exception:
        pass
    print("=" * 60)
    print("IBL 해마: 임베딩 검색 모델 학습 (클라우드)")
    print("=" * 60)

    print("\n--- Step 1: 데이터 준비 ---")
    examples = extract_examples_from_db()
    variations = []  # Unreviewed paraphrases do not inherit a row's audit.

    training_dir = DATA_DIR / "training"
    for synth_file in (sorted(training_dir.glob("*.json")) if training_dir.exists() else []):
        try:
            with open(synth_file, 'r', encoding='utf-8') as f:
                synth_data = json.load(f)
            if isinstance(synth_data, list) and synth_data:
                synth_data, rejected = current_examples(synth_data)
                print(f"[데이터] {synth_file.name}: 현재 {len(synth_data)}건, 제외 {rejected}")
                variations.extend(synth_data)
        except Exception as e:
            print(f"[데이터] {synth_file.name} 로드 실패: {e}")

    variations = balance_by_action(variations)

    train_pairs, test_pairs, code_to_intents = prepare_training_data(
        examples, variations, normalize=True
    )
    all_codes = list(code_to_intents.keys())
    action_descs = load_action_descriptions()

    print("\n--- Step 2: Baseline 평가 ---")
    from sentence_transformers import SentenceTransformer
    baseline_model = SentenceTransformer('jhgan/ko-sroberta-multitask', device=DEVICE)
    baseline_results = evaluate_model(
        baseline_model, test_pairs, all_codes,
        "Baseline (ko-sroberta-multitask)",
        action_descs=action_descs
    )

    print("\n--- Step 3: Fine-tuning (+ description 매핑) ---")
    MODEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    finetuned_model = train_model(train_pairs, code_to_intents, test_pairs=test_pairs)

    print("\n--- Step 4: Fine-tuned 모델 평가 ---")
    finetuned_results = evaluate_model(
        finetuned_model, test_pairs, all_codes,
        "Fine-tuned (IBL + description)",
        action_descs=action_descs
    )

    print("\n" + "=" * 60)
    print("결과 비교")
    print("=" * 60)
    for k in [1, 3, 5]:
        diff = finetuned_results[k] - baseline_results[k]
        arrow = "up" if diff > 0 else "down" if diff < 0 else "="
        print(f"  Top-{k}: {baseline_results[k]:.1f}% -> {finetuned_results[k]:.1f}% ({arrow}{abs(diff):.1f}%p)")

    result_path = MODEL_OUTPUT_DIR / "pilot_results.json"
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump({
            'data': {
                'db_examples': len(examples),
                'variations': len(variations),
                'train_pairs': len(train_pairs),
                'test_pairs': len(test_pairs),
                'unique_codes': len(all_codes),
            },
            'baseline': baseline_results,
            'finetuned': finetuned_results,
            'device': DEVICE,
            'batch_size': BATCH_SIZE,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n결과 저장: {result_path}")


if __name__ == '__main__':
    main()
