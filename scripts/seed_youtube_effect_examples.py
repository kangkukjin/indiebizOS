"""Review repairs for explicit immediate/single-track intents; no device execution."""
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
from ibl_usage_db import DB_PATH, IBLUsageDB  # noqa: E402

REPLACEMENTS = {
    intent: '#!ibl edition=2\nreturn [limbs:youtube]{op:"play",query:"피아노곡",if_playing:"replace"}'
    for intent in ('피아노 영상 검색하고 바로 재생해', '유튜브에서 피아노 찾아서 바로 틀어줘', '피아노곡 찾아서 바로 틀어')
}
REPLACEMENTS['조용한 노래 하나 틀어'] = (
    '#!ibl edition=2\nreturn [limbs:youtube]{op:"play",query:"잔잔한 배경음악",limit:1}')


def main():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute('SELECT id,intent,ibl_code FROM ibl_examples').fetchall()
    stale = [r for r in rows if r[1] in REPLACEMENTS and r[2] != REPLACEMENTS[r[1]]]
    present = {(r[1], r[2]) for r in rows}
    fresh = [{'intent': intent, 'ibl_code': code, 'nodes': 'limbs', 'source': 'synthetic',
              'tags': 'youtube,operation_effect'} for intent, code in REPLACEMENTS.items()
             if (intent, code) not in present]
    if stale or fresh:
        backup = ROOT / 'data/_backups/2026-11-08_youtube_effect_examples'
        backup.mkdir(parents=True, exist_ok=True)
        path = backup / 'previous_examples.json'
        if not path.exists():
            path.write_text(json.dumps(stale, ensure_ascii=False, indent=2) + '\n')
        db = IBLUsageDB()
        assert db._load_model_sync(), 'embedding model unavailable'
        assert db.add_examples_batch(fresh) == len(fresh)
        db._delete_examples([r[0] for r in stale])
    corpus = ROOT / 'data/training/ibl_distilled.json'
    examples = json.loads(corpus.read_text())
    changed = 0
    for row in examples:
        intent = row.get('intent')
        if intent in REPLACEMENTS and row.get('ibl_code') != REPLACEMENTS[intent]:
            row.setdefault('provenance', {}).setdefault('corpus_versions', []).append({
                'edition': 2, 'intent': intent, 'code': row['ibl_code'],
                'reason': '2026-11-08 explicit immediate/single-track contract review'})
            row['ibl_code'] = REPLACEMENTS[intent]
            changed += 1
    if changed:
        corpus.write_text(json.dumps(examples, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'replaced': len(stale), 'added': len(fresh), 'corpus_repaired': changed}))


if __name__ == '__main__':
    main()
