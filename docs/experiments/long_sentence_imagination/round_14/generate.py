"""Recreate the six synthetic, deliberately unfinished config drafts."""
import json
import shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
LOCAL=HERE.parents[3]/'outputs/long_sentence_imagination/2026-09-30_14회차'
for name in ('inputs','variant','uppercase'):
    shutil.copytree(HERE/'fixtures',LOCAL/name,dirs_exist_ok=True)
(LOCAL/'variant/b.json').unlink(missing_ok=True)
p=LOCAL/'uppercase/manifest.json';m=json.loads(p.read_text());m['files'][0]['name']='a.JSON';p.write_text(json.dumps(m))
(LOCAL/'uppercase/a.json').rename(LOCAL/'uppercase/a.JSON')
(LOCAL/'uppercase/e.json').write_text('')
