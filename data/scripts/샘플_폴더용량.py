"""등록 스크립트 데모 — outputs/ 1단계 폴더 용량 요약을 items 통화로 출력."""
import json, os
from pathlib import Path

root = Path(__file__).resolve().parents[1]  # outputs/
items = []
for p in sorted(root.iterdir()):
    if not p.is_dir():
        continue
    size = 0
    for dirpath, _, files in os.walk(p):
        for f in files:
            try:
                size += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    items.append({"title": p.name, "mb": round(size / 1048576, 1)})
items.sort(key=lambda x: -x["mb"])
print(json.dumps({"items": items}, ensure_ascii=False))
