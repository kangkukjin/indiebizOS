"""49회차 합성 자료 — 사진 묶음(PNG)·job.json·oracle(중앙 SHA-256). PIL 필요(.venv).
사용: .venv/bin/python3 prepare.py → outputs/.../2026-10-10_49회차/{trainer/{base,a,b},agent/a}/input + _oracle"""
import hashlib, json, random, shutil, unicodedata
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-10_49회차'
REMOTE = '/Users/kangkukjin/indiebiz-training/r49'
SUBJECTS = ['가을 들판', '시장 골목', '바닷가 아침', '공방 선반', '도자 머그', '호두 도마', '창가 화분', '옥상 저녁']
SIZES = [(2400, 1600), (1600, 2400), (2000, 1125), (1200, 800), (600, 600), (900, 1350)]
JOBS = {'base': {'long_side': 800, 'quality': 80, 'bundle': '가을사진_800', 'skip': {'min_bytes': 1, 'name_prefix': ''}, 'pace_ms': 1500},
        'a': {'long_side': 800, 'quality': 80, 'bundle': '가을사진_800', 'skip': {'min_bytes': 1, 'name_prefix': ''}, 'pace_ms': 3000},
        'b': {'long_side': 480, 'quality': 60, 'bundle': 'thumb 480 (웹용)', 'skip': {'min_bytes': 1, 'name_prefix': '초안_'}, 'pace_ms': 300}}


def photo(path, seed, size):
    rnd = random.Random(seed); w, h = size
    im = Image.linear_gradient('L').resize((w, h)).convert('RGB')
    im.paste(Image.frombytes('RGB', (256, 180), bytes(rnd.getrandbits(8) for _ in range(256 * 180 * 3))), (rnd.randrange(0, w - 256), rnd.randrange(0, h - 180)))
    im.save(path, 'PNG')


def build(who, mode):
    inp = OUT / who / mode / 'input'; ph = inp / 'photos'; ph.mkdir(parents=True); (OUT / who / mode / 'out').mkdir()
    n = 3 if mode == 'b' else 1; k = 0; meta = {}
    for rep in range(n):
        for s in SUBJECTS:
            for i in range(1, 7):
                name = unicodedata.normalize('NFC', f'{s} ({i + rep * 6}).png'); k += 1
                if mode == 'b' and k % 12 == 0: name = '초안_' + name
                photo(ph / name, f'{mode}-{k}', SIZES[k % len(SIZES)]); meta[name] = {'size': SIZES[k % len(SIZES)]}
    empty = sorted(meta)[5]; (ph / empty).write_bytes(b''); meta[empty]['empty'] = True
    broken = None
    if mode == 'a':
        broken = sorted(meta)[20]; (ph / broken).write_bytes(b'\x89PNG\r\n\x1a\n' + bytes(random.Random(7).getrandbits(8) for _ in range(4000))); meta[broken]['broken'] = True
    job = {'pc': '맥12', 'remote_dir': f'{REMOTE}/{who}_{mode}', 'format': 'jpeg', **JOBS[mode]}
    (inp / 'job.json').write_text(json.dumps(job, ensure_ascii=False, indent=1))
    files = {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size, **meta[p.name]} for p in sorted(ph.iterdir())}
    skipped = sorted(nm for nm, f in files.items() if f['bytes'] < job['skip']['min_bytes'] or (job['skip']['name_prefix'] and nm.startswith(job['skip']['name_prefix'])))
    return {'job': job, 'files': files, 'skipped': skipped, 'broken': [broken] if broken else [], 'expect_converted': len(files) - len(skipped) - (1 if broken else 0), 'total_bytes': sum(f['bytes'] for f in files.values())}


def main():
    for sub in ('trainer', 'agent', '_oracle'): shutil.rmtree(OUT / sub, ignore_errors=True)
    (OUT / 'runs').mkdir(parents=True, exist_ok=True); (OUT / '_oracle').mkdir()
    exp = {f'{who}_{mode}': build(who, mode) for who, mode in (('trainer', 'base'), ('trainer', 'a'), ('trainer', 'b'), ('agent', 'a'))}
    (OUT / '_oracle' / 'expected.json').write_text(json.dumps(exp, ensure_ascii=False, indent=1))
    for k, v in exp.items(): print(k, len(v['files']), 'files', v['total_bytes'], 'bytes', 'skip', v['skipped'], 'broken', v['broken'], 'expect', v['expect_converted'])


if __name__ == '__main__':
    main()
