"""저장 증거의 일관성만 확인한다. 의미 정확성이나 독립 감사의 대체가 아니다."""
import hashlib
import json
from pathlib import Path

H = Path(__file__).resolve().parent
load = lambda p: json.loads((H / p).read_text())
e = load('evidence.json')
assert e['source_hashes_after'] == e['start']['source_hashes']
assert e['ai_base_changed'] == []
for name, sha in e['ai_base_frozen']['files'].items():
    if name == 'sources.json':
        continue  # 외부 원문은 로컬에만 보존
    assert hashlib.sha256((H / 'ai/base' / name).read_bytes()).hexdigest() == sha, name
for ep in e['episodes']:
    assert ep['terminal_state'] == 'succeeded'
    assert all(d['complete'] and not d['restricted_markers'] for d in ep['tool_input_audit'])
    assert ep['guide_events'][0]['timestamp'] < ep['plans'][0]['timestamp']
a = e['L106_1']['actual_output']
assert a['top_docs'] == ['D02', 'D03', 'D05']
assert '결과 파일 없음은 `RESULT_MISSING`' in a['top_passages'][2]
assert e['L106_1']['auxiliary_analysis']['rrf_bm25ko_dense'] == 22
for p in ['ai/base/runs/results_base.json', 'ai/variant/runs/results_variant.json', 'heldout/ai_heldout_matched_runtime.json']:
    d = load(p)
    assert len(d['results']) == 48 and not d['skipped'] and d['config_unchanged']
    assert all(len(r['top_docs']) <= 3 and r['answer'] is None for r in d['results'])
assert len(load('heldout/ai_heldout_results.json')['skipped']) == 4
old=load('fixtures/base/manifest.json');new=load('fixtures/variant/manifest.json')
assert [x['id'] for x,y in zip(old,new) if x['sha256'] != y['sha256']] == ['S01','S03']
rows=[json.loads(s) for s in (H/'trainer/variant_followup.jsonl').read_text().splitlines()]
assert next(r for r in rows if r['question_id']=='Q03')['reused'] is True
assert next(r for r in rows if r['question_id']=='Q06')['answerable'] is False
for p in H.rglob('*'):
    if p.is_file() and '__pycache__' not in p.parts:
        assert len(p.read_text().splitlines()) <= 1500, p
print('증거 일치: 원본 보존, 3회×48행, 실행환경 차이, RRF 반례, 판본 변경·선택 재사용')
