"""세 자료 과제의 재독/저장/확인 비용 비교(합성 자료, 결정적 실행자, 모델 0회).

이 시험은 LLM의 추론/토큰 절감을 측정하지 않는다. 이전 방식의 보수적 전량 재독과
새 방식의 근거 범위 대조를 같은 정답에서 비교한다. PYTHONPATH=backend 로 실행.
"""
import boot_paths  # noqa: F401
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
import time

import forage_doc as fd
import forage_memory as fm
import forage_evidence as fe
import source_observation as so
from forage_recall_store import ForageStore, place_ids, _cache


def run():
    rows = []
    old_db, old_docs, old_state = fm._DB_PATH, fd.DOC_DIR, os.environ.get('INDIEBIZ_RUNTIME_STATE_DIR')
    cases = [
        ('table', '금액 단위 고객번호 결합', '금액은 1000 원 단위, 고객번호로 결합', {'unit': 1000, 'amount': 3}, 3000),
        ('repository', '빌드 진입점 원본', '빌드 진입점은 src/main.py이며 dist는 생성 결과', {'entry': 'src/main.py'}, 'src/main.py'),
        ('documents', '규정 판본 유효 기간', '2025년 이후 규정은 v2를 적용한다', {'edition': 'v2', 'since': 2025}, 'v2'),
    ]
    try:
        with tempfile.TemporaryDirectory(prefix='forage-benchmark-') as temp:
            root = Path(temp)
            os.environ['INDIEBIZ_RUNTIME_STATE_DIR'] = str(root / 'state')
            fm._DB_PATH, fd.DOC_DIR = str(root / 'memory.db'), str(root / 'memories')
            for name, query, claim, source, expected in cases:
                corpus = root / name; corpus.mkdir()
                for n in range(100):
                    (corpus / f'background{n}.txt').write_text('관계없는 자료 본문\n' * 100)
                relevant = corpus / 'source.json'; relevant.write_text(json.dumps(source, ensure_ascii=False))
                started = time.perf_counter()
                content = {p.name: p.read_bytes() for p in corpus.iterdir()}
                parsed = json.loads(content['source.json'])
                answer = parsed['unit'] * parsed['amount'] if name == 'table' else parsed['entry' if name == 'repository' else 'edition']
                baseline_ms = (time.perf_counter() - started) * 1000
                assert answer == expected
                started = time.perf_counter()
                before = so.file_state(relevant); raw = relevant.read_bytes()
                evidence = so.file_evidence(str(relevant), before, hashlib.sha256(raw).hexdigest(), {'complete': True})
                ref = so.publish(evidence, raw.decode())
                result = fm.note_map(body='mac', locus=str(relevant), kind='convention', claim=claim,
                                     prior_class='semantic', provenance={'observation_refs': [{'receipt_id': ref}]})
                assert result['success']
                storage_ms = (time.perf_counter() - started) * 1000
                started = time.perf_counter()
                store = ForageStore(); items = store.items()
                assert str(relevant) in place_ids(store.lexical(query, items))
                conn = fm._connect(); memory = dict(conn.execute('SELECT * FROM forage_map WHERE id=?', (result['id'],)).fetchone()); conn.close()
                checker = fe.Checker('content'); status = checker.status(memory)
                assert status['state'] == 'unchanged'
                # Same task result; no fabricated model inference or counterfactual error count.
                meaning = memory['claim']
                if name == 'table':
                    reused = source['amount'] * int(re.search(r'(\d+) 원 단위', meaning)[1])
                elif name == 'repository':
                    reused = re.search(r'src/[^ ]+?\.py', meaning)[0]
                else:
                    reused = re.search(r'v\d+', meaning)[0]
                assert reused == expected
                use_ms = (time.perf_counter() - started) * 1000
                rows.append({'task': name, 'meaning_errors': {'before': 0, 'after': 0},
                             'baseline': {'files_reread': len(content), 'bytes_read': sum(map(len, content.values())), 'wall_ms': round(baseline_ms, 3)},
                             'new': {'sources_checked': len(checker.observed), 'bytes_checked': checker.bytes,
                                     'storage_read_bytes': len(raw), 'storage_ms': round(storage_ms, 3),
                                     'discovery_and_check_ms': round(use_ms, 3), 'total_ms': round(storage_ms + use_ms, 3)},
                             'model_calls': {'before': 0, 'after': 0}, 'model_tokens': {'before': 0, 'after': 0}})
    finally:
        fm._DB_PATH, fd.DOC_DIR = old_db, old_docs
        _cache.clear()
        if old_state is None:
            os.environ.pop('INDIEBIZ_RUNTIME_STATE_DIR', None)
        else:
            os.environ['INDIEBIZ_RUNTIME_STATE_DIR'] = old_state
    return {'method': 'deterministic fixture tasks, conservative full-reread baseline; not an LLM performance experiment', 'tasks': rows}


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, indent=2))
