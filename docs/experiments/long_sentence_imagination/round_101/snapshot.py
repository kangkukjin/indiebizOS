"""101회차 — 출력 폴더의 파일 목록·sha256·바이트 스냅샷(후속 턴의 '최초 파일 보존' 대조용). 사용: snapshot.py <folder> <out.json>"""
import hashlib, json, sys, time
from pathlib import Path
F = Path(sys.argv[1]); OUT = Path(sys.argv[2]); rows = []
for p in sorted(F.rglob("*")):
    if p.is_file(): b = p.read_bytes(); rows.append({"file": str(p.relative_to(F)), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(), "mtime": time.strftime("%H:%M:%S", time.localtime(p.stat().st_mtime))})
OUT.write_text(json.dumps({"folder": str(F), "at": time.strftime("%Y-%m-%d %H:%M:%S"), "files": rows}, ensure_ascii=False, indent=1))
print(len(rows), "files;", "; ".join(f"{r['file']} {r['bytes']}B {r['sha256'][:8]}" for r in rows))
