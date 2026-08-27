#!/usr/bin/env bash
# 상상훈련 마라톤 — 명령 한 번 = 라운드 이어달리기 (기본 4회)
#
# 정본 = docs/SELF_EVOLUTION_AUTOMATION_HANDOFF.md Part B.
# 스케줄(시계)이 아니라 이어달리기다: 다음 라운드의 방아쇠는 시각이 아니라
# 앞 라운드의 완료이고, 라운드 사이에 종료 판단 둘이 낀다 —
#   ① 판정 큐(PENDING_VERDICTS.md) 미결 ≥ 임계 → 중단하고 사용자를 부른다
#   ② 마른 라운드(신규 커밋 0) 2연속 → 조기 종료 (loop-until-dry)
#
# 개발 도구다(몸 실행에 불요) — Claude Code CLI 가 있는 개발기에서만 돈다.
# 이식성 계명 비적용 대상이지만, 저장소 경로는 스스로 푼다(하드코딩 없음).
#
# 사용:
#   bash scripts/imagination_marathon.sh        # 4라운드
#   bash scripts/imagination_marathon.sh 2      # 2라운드
#   MARATHON_CLAUDE_FLAGS="..." 로 권한 플래그 교체 가능.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROUNDS="${1:-4}"
VERDICT_LIMIT=5
PV="$ROOT/outputs/imagination_training/PENDING_VERDICTS.md"
LOG_DIR="$ROOT/outputs/imagination_training"
# 무인 라운드는 관문 실행·커밋까지 스스로 해야 해서 승인 프롬프트가 설 자리가 없다.
# 이 저장소, 이 기계, 사용자 본인이 명령한 자리에서만 쓰는 전제의 플래그다.
CLAUDE_FLAGS="${MARATHON_CLAUDE_FLAGS:---dangerously-skip-permissions}"

command -v claude >/dev/null || { echo "claude CLI 가 없습니다 — 마라톤은 개발기 전용"; exit 1; }
git -C "$ROOT" rev-parse HEAD >/dev/null || { echo "git 저장소가 아닙니다"; exit 1; }

PROMPT=$(cat <<'EOF'
상상훈련 1회차를 수행하라. 축 선정은 훈련 가이드(data/guides/imagination_training.md —
표류 방지 4조항: 축 선정 관문 질문·닫힌 밭 재검침 금지·표현력 갭 복귀)를 따르라.
보통때의 4배 규모로 하라. 수리성 결함은 근본 수리하고 관문을 세운 뒤 pathspec 으로
커밋하라(동시 세션 공유 인덱스 — 전량 add 금지). 언어 개정·파괴적 변경 2종은 집행 금지 —
outputs/imagination_training/PENDING_VERDICTS.md 의 '미결' 절에 `- [ ]` 로 적립만 하라.
신규 발견이 없으면 억지로 만들지 말고 커밋 없이 "마른 라운드"로 보고서만 남겨라.
회차 보고서는 outputs/imagination_training/YYYY-MM-DD_N회차.md 규약으로 남겨라.
EOF
)

pending_count() {
  grep -c '^- \[ \]' "$PV" 2>/dev/null || true
}

dry_streak=0
for i in $(seq 1 "$ROUNDS"); do
  p="$(pending_count)"
  if [ "${p:-0}" -ge "$VERDICT_LIMIT" ]; then
    echo "판정 큐 미결 ${p}건 ≥ ${VERDICT_LIMIT} — 사용자 판정 없이 계속 돌면 보류 더미가 된다. 중단."
    exit 2
  fi
  before_head="$(git -C "$ROOT" rev-parse HEAD)"
  stamp="$(date '+%Y-%m-%d %H:%M')"
  echo "── 라운드 ${i}/${ROUNDS} 시작 ${stamp} (HEAD ${before_head:0:9}) ──"
  ( cd "$ROOT" && claude -p "$PROMPT" $CLAUDE_FLAGS ) \
    || echo "(라운드 ${i} 세션 비정상 종료 — 종료 판단으로 계속)"
  after_head="$(git -C "$ROOT" rev-parse HEAD)"
  new_commits="$(git -C "$ROOT" rev-list --count "${before_head}..${after_head}" 2>/dev/null || echo 0)"
  echo "── 라운드 ${i} 종료: 새 커밋 ${new_commits}건, 판정 큐 미결 $(pending_count)건 ──"
  if [ "${new_commits}" = "0" ]; then
    dry_streak=$((dry_streak + 1))
  else
    dry_streak=0
  fi
  if [ "$dry_streak" -ge 2 ]; then
    echo "마른 라운드 2연속 — 수확이 말랐다. 조기 종료 (loop-until-dry)."
    break
  fi
done
echo "마라톤 종료 — 회차 보고서·판정 큐는 outputs/imagination_training/"
