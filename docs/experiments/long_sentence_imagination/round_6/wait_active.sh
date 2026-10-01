#!/bin/bash
# 재기동 제어자 phase 가 ACTIVE 이고 /health 가 healthy 일 때까지 대기(최대 300초). FAILED 면 api.py start 로 복구.
S=/Users/kangkukjin/Desktop/AI/indiebizOS/data/restart_control/state.json
for i in $(seq 1 75); do
  ph=$(python3 -c "import json;d=json.load(open('$S'));print(d.get('phase'))" 2>/dev/null)
  h=$(curl -s -m 3 localhost:8765/health | head -c 30)
  if [ "$ph" = "ACTIVE" ] && [[ "$h" == *healthy* ]]; then echo "$(date +%H:%M:%S) ACTIVE"; exit 0; fi
  if [ "$ph" = "FAILED" ]; then echo "$(date +%H:%M:%S) FAILED -> start"; (cd /Users/kangkukjin/Desktop/AI/indiebizOS && nohup .venv/bin/python3 backend/api.py start > /dev/null 2>&1 &); sleep 8; fi
  sleep 4
done
echo "timeout ($ph)"; exit 1
