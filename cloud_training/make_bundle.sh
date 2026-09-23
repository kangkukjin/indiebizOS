#!/usr/bin/env bash
# 클라우드 학습용 입력 번들 생성.
# 로컬 학습이 참조하는 입력(DB / training json / ibl_nodes.yaml)과
# 포팅 스크립트를 하나의 zip으로 묶는다. 이 zip 하나만 Colab에 올리면 된다.
#
# 사용: cd /Users/kangkukjin/Desktop/AI/indiebizOS && bash cloud_training/make_bundle.sh
# 결과: cloud_training/ibl_train_bundle.zip

set -euo pipefail

REPO="/Users/kangkukjin/Desktop/AI/indiebizOS"
OUT_DIR="$REPO/cloud_training"
STAGE="$(mktemp -d)/bundle"

mkdir -p "$STAGE/data/training"

# 1) DB 시드 용례 — 90MB DB 전체 대신 필요한 컬럼만 작은 JSON으로 추출.
#    (Colab files.upload() 가 대용량에서 잘 끊기므로 번들을 가볍게 유지)
"$REPO/.venv/bin/python3" "$REPO/scripts/export_corpus_training.py" "$STAGE/data"

# 2) 액션 description — 원본 load_action_descriptions 가 참조
cp "$REPO/data/ibl_nodes.yaml" "$STAGE/data/ibl_nodes.yaml"

# 3) 학습 JSON은 위 공통 자격 검사기가 내보낸 현재 판본만 사용한다.

# 4) 포팅 스크립트
cp "$OUT_DIR/ibl_embedding_trainer_cloud.py" "$STAGE/ibl_embedding_trainer_cloud.py"
cp "$REPO/backend/base/corpus_policy.py" "$STAGE/corpus_policy.py"
cp "$REPO/backend/base/ibl_edition.py" "$STAGE/ibl_edition.py"

# 5) 압축
( cd "$STAGE/.." && zip -r -q "ibl_train_bundle.zip" "bundle" )
mv "$STAGE/../ibl_train_bundle.zip" "$OUT_DIR/ibl_train_bundle.zip"

echo "생성 완료: $OUT_DIR/ibl_train_bundle.zip"
echo "--- 포함 내용 ---"
( cd "$STAGE/.." && find bundle -type f | sort )
echo "--- 크기 ---"
du -h "$OUT_DIR/ibl_train_bundle.zip" | cut -f1

rm -rf "$(dirname "$STAGE")"
