"""고정 커밋의 실제 가이드 8개와 합성 원본 4개로 입력을 복원한다."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
head = json.loads((HERE / 'start.json').read_text())['head']
for version in ['base', 'variant']:
    source = HERE / 'fixtures' / version
    destination = a.output / version
    (destination / 'docs').mkdir(parents=True)
    for name in ['manifest.json', 'queries.json']:
        shutil.copyfile(source / name, destination / name)
    for item in json.loads((source / 'manifest.json').read_text()):
        content = subprocess.check_output(['git', 'show', f"{head}:{item['source']}"], cwd=ROOT) if item['kind'] == 'real' else (source / 'docs' / item['file']).read_bytes()
        assert hashlib.sha256(content).hexdigest() == item['sha256'], item['id']
        (destination / 'docs' / item['file']).write_bytes(content)
shutil.copyfile(HERE / 'heldout.json', a.output / 'heldout.json')
print(f'24개 문서 SHA 일치: {a.output}')
