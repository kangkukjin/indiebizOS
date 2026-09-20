"""합성 원문 8개를 같은 직전 기억으로 비교. 라이브 기억 쓰기 없음.

실행: PYTHONPATH=backend .venv/bin/python3 docs/experiments/unified_distill_2026_09_21/compare.py
A=기존 분리+background, B=통합+실행 모델, C=기존 분리+동일 실행 모델.
실제 모델 호출을 포함한다. 모델/프롬프트/입력·출력 및 관측 토큰을 결과 JSON에 기록한다.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

import boot_paths  # noqa: F401
from dotenv import load_dotenv
from model_resolver import freeze_descriptor, resolve, provider_from_frozen
from consciousness_agent import call_oneshot_provider
from cognitive_distill import CognitiveDistillMixin
from distill_memory_adapters import memory_modules, prepare_deep, apply_deep, _version
from unified_distill import SYSTEM_PROMPT, fit_input, model_input, parse_decision, value_rejection
from distill_receipts import fingerprint

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name('results.json')
CASES = [
    ('small_fact', '오늘 점심은 김밥을 먹었어.', 0, []),
    ('one_off', '이번 영상은 30초로 만들기로 했어.', 0, []),
    ('quoted', '> 나는 앞으로 답변을 짧게 받을 거야.', 0, []),
    ('assistant_fact', '그렇구나.', 0, []),
    ('lasting_preference', '나는 앞으로 모든 답변을 존댓말로 받기를 원해.', 1, []),
    ('known_preference', '나는 앞으로 모든 답변을 존댓말로 받기를 원해.', 0,
     ['나는 앞으로 모든 답변을 존댓말로 받기를 원해.']),
    ('explicit_correction', '전에 생일을 11월 18일이라고 말한 것은 틀렸어. 내 생일은 11월 19일이야.', 1,
     ['내 생일은 11월 18일이야.']),
    ('dangling', '그걸 앞으로도 계속 쓰기로 했어.', 0, []),
]


def main():
    load_dotenv(ROOT / '.env', override=False)
    models = {role: freeze_descriptor(resolve(role), role=role) for role in ('background', 'execution')}
    results = {'models': models, 'sample': '8 synthetic source cases, fixed pre-turn memory',
               'live_writes': False, 'cases': [], 'limitations': [
                   'historical episode replay is not included', 'small deep-memory precision sample',
                   'subscription cost and unreported reasoning tokens are unknown']}
    db, tree = memory_modules()
    for name, user, expected, existing in CASES:
        for arm in 'ABC':
            with tempfile.TemporaryDirectory(prefix='distill-compare-') as folder:
                rows = [dict(id=i+1, content=text, source_ref=None, node='사용자', category='사용자정보', keywords='')
                        for i, text in enumerate(existing)]
                for row in rows:
                    row['version'] = _version(row)
                saved, calls = [], []
                def save(*a, **kw):
                    saved.append({'content': kw.get('content'), 'relation': 'NEW', 'source_ref': kw.get('source_ref')})
                    return 99
                def update(*a, **kw):
                    saved.append({'content': kw.get('content'), 'relation': 'REPLACE', 'source_ref': kw.get('source_ref')})
                    return True
                descriptor = models['background' if arm == 'A' else 'execution']
                def ask(prompt, system_prompt=None, **kwargs):
                    usage = {}
                    start = time.monotonic()
                    provider = provider_from_frozen(descriptor)
                    raw = call_oneshot_provider(provider, prompt, system_prompt=system_prompt,
                                                role='execution', step_role='distill_compare', usage_sink=usage)
                    calls.append({'elapsed_s': time.monotonic()-start, 'usage': usage,
                                  'prompt_hash': fingerprint([system_prompt, prompt]), 'raw': raw})
                    return raw
                job = {'job_key': name, 'project_path': folder, 'agent_id': 'test', 'user_message': user,
                       'response': '네. 사용자는 커피를 항상 좋아합니다.', 'turn_id': name,
                       'recorded_at': '2026-09-21T09:00:00+09:00', 'timezone': 'Asia/Seoul'}
                logs = io.StringIO()
                error = None
                with contextlib.redirect_stdout(logs), \
                     patch.object(db, 'search', lambda *a, **kw: copy.deepcopy(rows)), \
                     patch.object(db, 'read', lambda p,a,i,**kw: copy.deepcopy(next(r for r in rows if r['id']==i))), \
                     patch.object(db, 'save', save), patch.object(db, 'update', update), \
                     patch.object(tree, 'map_text', lambda *a: '- 사용자'), \
                     patch('consciousness_agent.oneshot_ai_call', ask):
                    try:
                        if arm != 'B':
                            runner = CognitiveDistillMixin()
                            runner.project_path, runner.agent_id = folder, 'test'
                            runner._distill_deep_memory(user, job['response'])
                        else:
                            section = prepare_deep(job)
                            prepared = fit_input({'sections': {'deep': section} if section.get('eligible') else {},
                                                  'snapshot': {'recorded_at': job['recorded_at']}, 'skip_reasons': {}})
                            if prepared['sections']:
                                raw = ask(json.dumps(model_input(prepared), ensure_ascii=False), SYSTEM_PROMPT)
                                decision = parse_decision(raw)
                                for i, candidate in enumerate(decision['deep']):
                                    if not value_rejection(candidate):
                                        apply_deep(job, section, candidate, f'{name}-{i}')
                    except Exception as exc:
                        error = type(exc).__name__ + ':' + str(exc)
                result = {'name': name, 'arm': arm, 'user': user, 'expected_saved': expected,
                          'saved': saved, 'calls': calls, 'error': error, 'logs': logs.getvalue(),
                          'count_matches_expectation': len(saved) == expected and error is None}
                results['cases'].append(result)
                OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
                print(name, arm, 'saved', len(saved), 'expected', expected, 'calls', len(calls), 'error', error, flush=True)


if __name__ == '__main__':
    main()
