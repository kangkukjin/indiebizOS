"""Recreate only this round's synthetic inputs; no task solution generation."""
import shutil
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LOCAL = ROOT/'outputs/long_sentence_imagination/2026-09-30_12회차'
for name in ('inputs','variant','short','duplicate'):
    shutil.copytree(HERE/'fixtures',LOCAL/name,dirs_exist_ok=True)
with (LOCAL/'variant/received.csv').open('a') as stream:
    stream.write('D0,S00,5,999\n')
with (LOCAL/'short/received.csv').open('a') as stream:
    stream.write('D0,S00\n')
p = LOCAL/'duplicate/received.csv'
p.write_text(p.read_text().replace('depot,sku,qty', 'depot,sku,sku', 1))
for src,dst in [('inputs','main'),('variant','variant')]:
    shutil.copytree(LOCAL/src,LOCAL/'system_inputs'/dst,dirs_exist_ok=True)
