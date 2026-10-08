"""34회차 합성 자료·단계 연출·독립 oracle. IBL 과제 계산은 하지 않는다(oracle 은 대조용, AI 입력 사본에서 제외).

사용: prepare.py generate          — source/all 에 30일치 파일 생성
      prepare.py stage <run> <executor>  — executor(trainer|agent) 의 inbox 를 run 단계로 연출(1=10파일, 2=+10·3일차 수정, 3=변화 없음, 4=+10·1파일 손상)
      prepare.py oracle <run> <executor> — 그 시점 inbox 의 기대값을 oracle/<executor>_run<run>.json 에 기록
"""
import json
import os
import random
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-08_34회차'
STORES = ['강남', '홍대', '판교']
SKUS = [f'SKU{i:02d}' for i in range(1, 21)]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def day_name(d):
    return f'sales_2026-09-{d:02d}.json'


def generate():
    rng = random.Random(34)
    src = OUT / 'source' / 'all'
    if src.exists():
        shutil.rmtree(src)
    for d in range(1, 31):
        rows = []
        for i in range(200):
            kind = 'refund' if rng.random() < 0.12 else 'sale'
            qty = rng.randint(1, 5)
            rows.append({'id': f'{d:02d}-{i:04d}', 'store': rng.choice(STORES), 'sku': rng.choice(SKUS),
                         'kind': kind, 'qty': qty, 'amount': qty * rng.choice([900, 1500, 2500, 4000, 12000])})
        dump(src / day_name(d), rows)
    print('generated', src)


def inbox(executor):
    return OUT / 'inbox' / executor


def stage(run, executor):
    src = OUT / 'source' / 'all'
    box = inbox(executor)
    box.mkdir(parents=True, exist_ok=True)
    if run == 1:
        for f in box.glob('*.json'):
            f.unlink()
        for d in range(1, 11):
            shutil.copy(src / day_name(d), box / day_name(d))
    elif run == 2:
        for d in range(11, 21):
            shutil.copy(src / day_name(d), box / day_name(d))
        # 3일차 파일 제자리 수정: 첫 행의 amount 를 10배 (크기·mtime 변화)
        p = box / day_name(3)
        rows = json.loads(p.read_text())
        rows[0]['amount'] *= 10
        time.sleep(1.1)
        p.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    elif run == 3:
        pass  # 변화 없음
    elif run == 4:
        for d in range(21, 31):
            shutil.copy(src / day_name(d), box / day_name(d))
        p = box / day_name(25)
        text = p.read_text()
        p.write_text(text[: len(text) // 2])  # 손상(절단)
    else:
        raise SystemExit('run 1~4')
    print('staged', run, box)


def oracle(run, executor):
    box = inbox(executor)
    by_sku = defaultdict(lambda: {'sale': 0, 'refund': 0, 'qty': 0})
    by_store = defaultdict(lambda: {'sale': 0, 'refund': 0, 'qty': 0})
    by_store_kind = defaultdict(lambda: {'amount': 0, 'qty': 0})
    ok, failed, rows_total = [], [], 0
    for p in sorted(box.glob('sales_*.json')):
        try:
            rows = json.loads(p.read_text())
        except ValueError as exc:
            failed.append(p.name)
            continue
        ok.append(p.name)
        rows_total += len(rows)
        for r in rows:
            for bucket in (by_sku[r['sku']], by_store[r['store']]):
                bucket[r['kind']] += r['amount']
                bucket['qty'] += r['qty'] if r['kind'] == 'sale' else -r['qty']
            by_store_kind[(r['store'], r['kind'])]['amount'] += r['amount']
            by_store_kind[(r['store'], r['kind'])]['qty'] += r['qty']
    expect_run = {1: {'processed_new': [day_name(d) for d in range(1, 11)], 'reprocessed': [], 'failed': []},
                  2: {'processed_new': [day_name(d) for d in range(11, 21)], 'reprocessed': [day_name(3)], 'failed': []},
                  3: {'processed_new': [], 'reprocessed': [], 'failed': []},
                  4: {'processed_new': [day_name(d) for d in range(21, 31) if d != 25], 'reprocessed': [], 'failed': [day_name(25)]}}[run]
    result = {
        'run': expect_run,
        'totals_by_sku': [{'sku': k, 'sale': v['sale'], 'refund': v['refund'], 'net': v['sale'] - v['refund'], 'qty': v['qty']} for k, v in sorted(by_sku.items())],
        'totals_by_store': [{'store': k, 'sale': v['sale'], 'refund': v['refund'], 'net': v['sale'] - v['refund'], 'qty': v['qty']} for k, v in sorted(by_store.items())],
        'totals_by_store_kind': [{'store': s, 'kind': k, 'amount': v['amount'], 'qty': v['qty']} for (s, k), v in sorted(by_store_kind.items())],
        'files_total': len(ok), 'rows_total': rows_total, 'processed_files': ok, 'failed_files': failed,
    }
    dump(OUT / 'oracle' / f'{executor}_run{run}.json', result)
    print('oracle', run, executor, 'files', len(ok), 'failed', failed, 'rows', rows_total)


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'generate':
        generate()
    elif cmd == 'stage':
        stage(int(sys.argv[2]), sys.argv[3])
    elif cmd == 'oracle':
        oracle(int(sys.argv[2]), sys.argv[3])
