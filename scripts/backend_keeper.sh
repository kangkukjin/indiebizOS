#!/bin/bash
# 호환 입구: keeper의 감시·재기동은 외부 단일 제어자가 소유한다.
REPO="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -x "$REPO/.venv/bin/python3" ]; then
    echo "재기동 보류 — .venv가 없습니다. python3 scripts/bootstrap.py를 실행하세요." >&2
    exit 1
fi
cd "$REPO/backend" || exit 1
exec "$REPO/.venv/bin/python3" api.py serve
