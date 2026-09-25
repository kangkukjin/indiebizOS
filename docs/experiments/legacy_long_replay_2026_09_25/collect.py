"""Read-only census and exact historical source extraction. No corpus mutation."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import hashlib
import json
import sqlite3
from ibl_scanner import source_heads

HERE = Path(__file__).resolve().parent
SELECTED = {
 'news': '924cde5d19ad', 'housing': '2bd72c0c3d97',
 'rotation': 'e442363b2db0', 'shops': '47086c21a3f1',
 'stocks': '844bdb8ce94b', 'forex': '1af761255a9e',
 'videos': '0f2c49590173', 'transcripts': '757b17ba9334',
 'ledger': '39a270bb0870', 'sources': '50d941add19c',
 'reinforce': '4489b82c9994', 'enterprise': '7a5d06788377',
}

def main():
    conn = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    candidates, selected = [], []
    for row in conn.execute("SELECT * FROM ibl_code_corpus WHERE edition=1 AND code_chars>=500 AND first_seen<'2026-09-23'"):
        code = row['code']
        heads = list(source_heads(code))
        if len(heads) < 4:
            continue
        record = {k: row[k] for k in ('code_sha256','code_chars','first_seen','success_count','fail_count','masked')}
        record['heads'] = len(heads)
        candidates.append(record)
        for name, prefix in SELECTED.items():
            if row['code_sha256'].startswith(prefix):
                assert hashlib.sha256(code.encode()).hexdigest() == row['code_sha256']
                (HERE / 'original' / f'{name}.ibl').write_text(code)
                selected.append({**record, 'name': name,
                                 'origin': 'data/world_pulse.db:ibl_code_corpus'})
    assert len(selected) == len(SELECTED)
    (HERE / 'census.json').write_text(json.dumps({
        'cutoff': '2026-09-23 (before edition-2 implementation)',
        'selection': '>=500 characters, >=4 lexical action/control heads; purposive 12-flow sample',
        'candidates': candidates, 'selected': selected,
    }, ensure_ascii=False, indent=None)+'\n')
    print(len(candidates), 'candidates;', len(selected), 'selected')
if __name__ == '__main__':
    main()
