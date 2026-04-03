"""
IBL 해마 파일럿: 학습된 임베딩 검색 모델 구축

현재 범용 임베딩(ko-sroberta-multitask) vs IBL 도메인 fine-tuned 모델의
검색 정확도를 비교하는 실험 스크립트.

사용법:
    cd /Users/kangkukjin/Desktop/AI/indiebizOS/backend
    python ibl_embedding_trainer.py
"""

import os
import sys
import json
import random
import sqlite3
import struct
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "ibl_usage.db"
MODEL_OUTPUT_DIR = DATA_DIR / "models" / "ibl_embedding"

# ============================================================================
# Step 1: 데이터 추출 및 변형 생성
# ============================================================================

@dataclass
class TrainingPair:
    intent: str
    ibl_code: str
    group_id: int  # 같은 ibl_code를 공유하는 그룹


def extract_examples_from_db() -> List[Dict]:
    """현재 DB에서 (intent, ibl_code) 쌍 추출"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT id, intent, ibl_code, nodes, category FROM ibl_examples ORDER BY id"
    )
    examples = [dict(row) for row in cursor.fetchall()]
    conn.close()
    print(f"[데이터] DB에서 {len(examples)}개 사례 추출")
    return examples


# 동사 변형 패턴 (ibl_usage_generator.py에서 확장)
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

# 추가 변형 패턴 — 어미 변환
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

        # 1. 동사 변형
        for verb_key, replacements in VERB_VARIATIONS.items():
            if verb_key in intent:
                for rep in replacements[:3]:  # 상위 3개
                    new_intent = intent.replace(verb_key, rep, 1)
                    if new_intent != intent and new_intent not in generated:
                        generated.add(new_intent)
                        variations.append({
                            'intent': new_intent,
                            'ibl_code': ibl_code,
                            'source': 'verb_variation'
                        })

        # 2. 명사 동의어
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

        # 3. 어미 변환
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


def prepare_training_data(examples: List[Dict], variations: List[Dict],
                          test_ratio: float = 0.2,
                          normalize: bool = False) -> Tuple[List, List, Dict]:
    """학습/평가 데이터 분리 및 그룹핑

    Args:
        normalize: True이면 코드를 액션 패턴으로 정규화.
                   [sense:stock_info]{symbol: "삼성전자"} → [sense:stock_info]
                   파라미터만 다른 코드들이 같은 그룹으로 합쳐짐.
    """
    # 모든 데이터를 ibl_code 기준으로 그룹핑
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
        print(f"[데이터] 정규화 후 고유 패턴: {len(code_to_intents)}개 (정규화 전 코드 수와 비교)")

    # 각 패턴 안에서 intent를 train/test로 분리
    train_pairs = []
    test_pairs = []

    for code, intents in code_to_intents.items():
        random.shuffle(intents)
        if len(intents) <= 2:
            # 2건 이하면 전부 학습용
            train_pairs.extend([(intent, code) for intent in intents])
        else:
            split_idx = max(1, int(len(intents) * (1 - test_ratio)))
            train_pairs.extend([(intent, code) for intent in intents[:split_idx]])
            test_pairs.extend([(intent, code) for intent in intents[split_idx:]])

    print(f"[데이터] 학습: {len(train_pairs)}쌍, 평가: {len(test_pairs)}쌍 ({len(code_to_intents)}개 패턴, 패턴 내 분할)")

    return train_pairs, test_pairs, code_to_intents


# ============================================================================
# Step 2: 모델 Fine-tuning
# ============================================================================

def load_action_descriptions() -> Dict[str, str]:
    """ibl_nodes.yaml에서 [node:action] → description 매핑 로드"""
    import yaml
    nodes_path = PROJECT_ROOT / "data" / "ibl_nodes.yaml"
    if not nodes_path.exists():
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


def extract_action_from_code(ibl_code: str) -> str:
    """IBL 코드에서 첫 번째 [node:action] 추출"""
    import re
    match = re.search(r'\[(\w+:\w+)\]', ibl_code)
    return match.group(1) if match else ""


def normalize_code_to_pattern(ibl_code: str) -> str:
    """IBL 코드를 액션 패턴으로 정규화.

    파라미터를 제거하고 액션 패턴만 남긴다.
    [sense:stock_info]{symbol: "삼성전자"} → [sense:stock_info]
    [sense:price]{symbol: "A"} >> [engines:chart]{type: "line"} → [sense:price] >> [engines:chart]
    [a:b]{...} & [c:d]{...} → [a:b] & [c:d]
    """
    import re
    # {…} 파라미터 블록 제거
    pattern = re.sub(r'\{[^}]*\}', '', ibl_code)
    # 공백 정리
    pattern = re.sub(r'\s+', ' ', pattern).strip()
    return pattern


def train_model(train_pairs: List[Tuple[str, str]], code_to_intents: Dict,
                test_pairs: List[Tuple[str, str]] = None):
    """sentence-transformer fine-tuning (intent→description 매핑 포함)"""
    from sentence_transformers import SentenceTransformer, InputExample, losses
    from sentence_transformers.evaluation import InformationRetrievalEvaluator
    from torch.utils.data import DataLoader

    BASE_MODEL = 'jhgan/ko-sroberta-multitask'
    print(f"\n[학습] 베이스 모델 로딩: {BASE_MODEL}")
    model = SentenceTransformer(BASE_MODEL)

    # 액션 description 로드
    action_descs = load_action_descriptions()
    print(f"[학습] {len(action_descs)}개 액션 description 로드")

    # 학습 데이터 구성
    train_examples = []
    train_code_to_intents: Dict[str, List[str]] = {}

    for intent, code in train_pairs:
        if code not in train_code_to_intents:
            train_code_to_intents[code] = []
        train_code_to_intents[code].append(intent)

    for code, intents in train_code_to_intents.items():
        # 1. intent ↔ intent 쌍 (같은 코드 내)
        if len(intents) >= 2:
            for i in range(len(intents)):
                for j in range(i + 1, min(i + 4, len(intents))):
                    train_examples.append(InputExample(texts=[intents[i], intents[j]]))

        # 2. intent → ibl_code 쌍
        for intent in intents:
            train_examples.append(InputExample(texts=[intent, code]))

        # 3. intent → action description 쌍 (핵심 추가)
        action = extract_action_from_code(code)
        if action in action_descs:
            desc = action_descs[action]
            for intent in intents[:5]:  # 상위 5개 intent
                train_examples.append(InputExample(texts=[intent, desc]))
                # description → code 쌍도 추가 (description과 code의 연결)
            train_examples.append(InputExample(texts=[desc, code]))

    random.shuffle(train_examples)
    print(f"[학습] {len(train_examples)}개 학습 쌍 구성")

    # DataLoader — 배치 작게 (MPS 메모리 제한)
    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=8)

    # Loss: MultipleNegativesRankingLoss
    # 같은 배치 내의 다른 쌍이 자동으로 negative가 됨
    train_loss = losses.MultipleNegativesRankingLoss(model)

    # Epoch별 학습 + 검증 (조기 종료 없이 고정 epoch)
    max_epochs = 10
    warmup_steps = int(len(train_dataloader) * 0.1)

    print(f"[학습] {max_epochs} epochs 고정 실행, epoch별 검증")
    print(f"[학습] warmup steps: {warmup_steps}")

    best_score = -1
    best_epoch = 0
    patience = 999  # 조기 종료 비활성화
    no_improve = 0

    for epoch in range(1, max_epochs + 1):
        model.fit(
            train_objectives=[(train_dataloader, train_loss)],
            epochs=1,
            warmup_steps=warmup_steps if epoch == 1 else 0,
            output_path=str(MODEL_OUTPUT_DIR / f"epoch_{epoch}"),
            show_progress_bar=True,
        )

        # 검증: 실제 test set으로 평가 (학습에 사용되지 않은 데이터)
        if test_pairs:
            val_score = _eval_on_test(model, test_pairs, list(code_to_intents.keys()))
        else:
            val_score = _quick_eval(model, train_code_to_intents)
        print(f"  [Epoch {epoch}] 검증 점수: {val_score:.3f}")

        if val_score > best_score:
            best_score = val_score
            best_epoch = epoch
            no_improve = 0
            # 최적 모델 저장
            model.save(str(MODEL_OUTPUT_DIR))
        else:
            no_improve += 1

        if no_improve >= patience:
            print(f"  [조기 종료] {patience} epoch 연속 개선 없음 → epoch {best_epoch}이 최적")
            break

    print(f"[학습] 최적 epoch: {best_epoch} (점수: {best_score:.3f})")
    print(f"[학습] 최적 모델 → {MODEL_OUTPUT_DIR}")

    # 최적 모델 로드
    best_model = SentenceTransformer(str(MODEL_OUTPUT_DIR))
    return best_model


def _eval_on_test(model, test_pairs: List[Tuple[str, str]], all_codes: List[str]) -> float:
    """실제 test set으로 Top-5 정확도 측정"""
    from sentence_transformers.util import cos_sim

    unique_codes = list(set(all_codes))
    test_intents = [p[0] for p in test_pairs]
    test_codes = [p[1] for p in test_pairs]

    intent_embs = model.encode(test_intents, convert_to_tensor=True, show_progress_bar=False)
    code_embs = model.encode(unique_codes, convert_to_tensor=True, show_progress_bar=False)
    sims = cos_sim(intent_embs, code_embs)

    correct = 0
    for i, (_, true_code) in enumerate(test_pairs):
        top5 = sims[i].topk(5).indices.tolist()
        if true_code in [unique_codes[idx] for idx in top5]:
            correct += 1
    return correct / len(test_pairs)


def _quick_eval(model, code_to_intents: Dict) -> float:
    """빠른 검증: 학습 데이터 내에서 intent→code 매칭 정확도 (샘플링)"""
    from sentence_transformers.util import cos_sim
    import random as _rand

    # 각 코드에서 intent 하나씩 샘플링하여 검증
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

    intent_embs = model.encode(test_intents, convert_to_tensor=True, show_progress_bar=False)
    code_embs = model.encode(test_codes, convert_to_tensor=True, show_progress_bar=False)
    sims = cos_sim(intent_embs, code_embs)

    # Top-5 정확도
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
    # 모든 고유 ibl_code의 임베딩 계산
    unique_codes = list(set(all_codes))
    code_embeddings = model.encode(unique_codes, convert_to_tensor=True,
                                   show_progress_bar=False)

    # 평가 셋의 intent → 가장 가까운 코드 찾기
    test_intents = [pair[0] for pair in test_pairs]
    test_codes = [pair[1] for pair in test_pairs]
    intent_embeddings = model.encode(test_intents, convert_to_tensor=True,
                                      show_progress_bar=False)

    # 코사인 유사도 계산
    from sentence_transformers.util import cos_sim
    similarities = cos_sim(intent_embeddings, code_embeddings)

    # Top-k 정확도 (code 매칭)
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

    # Description 매칭도 평가 (action 단위)
    if action_descs:
        import re
        # 고유 action → description
        action_list = list(action_descs.keys())
        desc_list = [action_descs[a] for a in action_list]
        desc_embeddings = model.encode(desc_list, convert_to_tensor=True,
                                        show_progress_bar=False)

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
    print("=" * 60)
    print("IBL 해마 파일럿: 학습된 임베딩 검색 모델 실험")
    print("=" * 60)

    # Step 1: 데이터 준비
    print("\n--- Step 1: 데이터 준비 ---")
    examples = extract_examples_from_db()
    variations = generate_variations(examples)

    # 학습 데이터 로드 (data/training/ 폴더)
    training_dir = DATA_DIR / "training"
    for synth_file in sorted(training_dir.glob("*.json")) if training_dir.exists() else []:
        try:
            with open(synth_file, 'r', encoding='utf-8') as f:
                synth_data = json.load(f)
            if isinstance(synth_data, list) and synth_data:
                print(f"[데이터] {synth_file.name}: {len(synth_data)}건 로드")
                variations.extend(synth_data)
        except Exception as e:
            print(f"[데이터] {synth_file.name} 로드 실패: {e}")

    train_pairs, test_pairs, code_to_intents = prepare_training_data(
        examples, variations, normalize=True
    )
    all_codes = list(code_to_intents.keys())

    # 액션 description 로드 (평가용)
    action_descs = load_action_descriptions()

    # Step 2: Baseline 평가 (fine-tuning 전)
    print("\n--- Step 2: Baseline 평가 ---")
    from sentence_transformers import SentenceTransformer
    baseline_model = SentenceTransformer('jhgan/ko-sroberta-multitask')
    baseline_results = evaluate_model(
        baseline_model, test_pairs, all_codes,
        "Baseline (ko-sroberta-multitask)",
        action_descs=action_descs
    )

    # Step 3: Fine-tuning (intent→description 매핑 포함)
    print("\n--- Step 3: Fine-tuning (+ description 매핑) ---")
    MODEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    finetuned_model = train_model(train_pairs, code_to_intents, test_pairs=test_pairs)

    # Step 4: Fine-tuned 모델 평가
    print("\n--- Step 4: Fine-tuned 모델 평가 ---")
    finetuned_results = evaluate_model(
        finetuned_model, test_pairs, all_codes,
        "Fine-tuned (IBL + description)",
        action_descs=action_descs
    )

    # 결과 비교
    print("\n" + "=" * 60)
    print("결과 비교")
    print("=" * 60)
    for k in [1, 3, 5]:
        diff = finetuned_results[k] - baseline_results[k]
        arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
        print(f"  Top-{k}: {baseline_results[k]:.1f}% → {finetuned_results[k]:.1f}% ({arrow}{abs(diff):.1f}%p)")

    # 결과 저장
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
        }, f, indent=2, ensure_ascii=False)
    print(f"\n결과 저장: {result_path}")


if __name__ == '__main__':
    main()
