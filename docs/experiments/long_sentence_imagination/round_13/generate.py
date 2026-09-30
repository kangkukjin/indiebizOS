"""Reproduce normal and ambiguous synthetic JSON, without solving the task."""
import shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
LOCAL=HERE.parents[3]/'outputs/long_sentence_imagination/2026-09-30_13회차'
for name in ('inputs','variant','nested'):
    shutil.copytree(HERE/'fixtures',LOCAL/name,dirs_exist_ok=True)
p=LOCAL/'variant/calibration.json'
p.write_text(p.read_text().replace('"slope": 2','"slope": 2, "slope": 20',1))
p=LOCAL/'nested/readings.json'
p.write_text(p.read_text().replace('"raw": 0','"raw": 0, "raw": 100',1))
for src,dst in [('inputs','main'),('variant','variant')]:
    shutil.copytree(LOCAL/src,LOCAL/'system_inputs'/dst,dirs_exist_ok=True)
