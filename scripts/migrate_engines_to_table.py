#!/usr/bin/env python3
"""해마/학습코퍼스 engines→table 노드 이전 마이그레이션 (action-scoped).

13개 이동 액션만 [engines:X]→[table:X] 로 재작성하고, nodes 컬럼은 재작성된
ibl_code 에서 [node: 접두어를 추출해 재계산한다. 잔존 13개(slide/tts/web 등)는 불변.
"""
import re, sqlite3, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "ibl_usage.db"
MOVED = ["chart","spreadsheet","structure","document","filter","sort","take",
         "select","dedup","groupby","join","union","merge"]
_moved_re = re.compile(r"\[engines:(" + "|".join(MOVED) + r")\b")
_node_re = re.compile(r"\[([a-z_]+):")

def rewrite_code(code: str) -> str:
    return _moved_re.sub(lambda m: f"[table:{m.group(1)}", code)

def nodes_of(code: str) -> str:
    seen, order = set(), []
    for n in _node_re.findall(code):
        if n not in seen:
            seen.add(n); order.append(n)
    return ",".join(sorted(order))

def migrate_db():
    conn = sqlite3.connect(str(DB)); conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, ibl_code, nodes FROM ibl_examples WHERE ibl_code LIKE '%[engines:%'").fetchall()
    touched = 0
    for r in rows:
        new_code = rewrite_code(r["ibl_code"])
        if new_code == r["ibl_code"]:
            continue  # only staying engines actions → leave
        new_nodes = nodes_of(new_code)
        conn.execute("UPDATE ibl_examples SET ibl_code=?, nodes=? WHERE id=?",
                     (new_code, new_nodes, r["id"]))
        touched += 1
    conn.commit()
    remain = conn.execute(
        "SELECT COUNT(*) FROM ibl_examples WHERE ibl_code LIKE '%[engines:chart]%' OR ibl_code LIKE '%[engines:filter]%' OR ibl_code LIKE '%[engines:sort]%' OR ibl_code LIKE '%[engines:take]%' OR ibl_code LIKE '%[engines:select]%' OR ibl_code LIKE '%[engines:dedup]%' OR ibl_code LIKE '%[engines:groupby]%' OR ibl_code LIKE '%[engines:join]%' OR ibl_code LIKE '%[engines:union]%' OR ibl_code LIKE '%[engines:merge]%' OR ibl_code LIKE '%[engines:document]%' OR ibl_code LIKE '%[engines:spreadsheet]%' OR ibl_code LIKE '%[engines:structure]%'").fetchone()[0]
    tablecnt = conn.execute("SELECT COUNT(*) FROM ibl_examples WHERE ibl_code LIKE '%[table:%'").fetchone()[0]
    conn.close()
    print(f"[DB] rows rewritten: {touched} | residual moved-engines: {remain} | table-bearing now: {tablecnt}")
    return remain == 0

def migrate_json(path: Path):
    if not path.exists():
        print(f"[JSON] skip (missing): {path.name}"); return
    data = json.load(open(path, encoding="utf-8"))
    n = 0
    def fix(obj):
        nonlocal n
        if isinstance(obj, dict):
            for k,v in obj.items():
                if isinstance(v,str) and "[engines:" in v:
                    nv = rewrite_code(v)
                    if nv!=v: obj[k]=nv; n+=1
                else: fix(v)
        elif isinstance(obj, list):
            for x in obj: fix(x)
    fix(data)
    json.dump(data, open(path,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[JSON] {path.name}: {n} fields rewritten")

if __name__ == "__main__":
    ok = migrate_db()
    migrate_json(ROOT/"data"/"training"/"ibl_distilled.json")
    migrate_json(ROOT/"data"/"training"/"ibl_training_balanced_20260516.json")
    sys.exit(0 if ok else 1)
