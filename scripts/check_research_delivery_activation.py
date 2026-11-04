#!/usr/bin/env python3
"""Read-only/pure-result production smoke through REST and a fresh MCP subprocess."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import asyncio
import hashlib
import json
import os
import urllib.request

from measure_research_delivery import WORK, write


def post(payload):
    req = urllib.request.Request('http://localhost:8765/ibl/execute',
                                 data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read())


async def main():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    body = ('원문 조건·반례를 보존한다.\n' * 530)[:7978]
    sample = {'text': body, 'blocks': [{'text': body, 'type': 'paragraph', 'page': 7}],
              '_display': {'mirror_fields': [{'field': 'text', 'collection': 'blocks',
                                              'text_field': 'text', 'separator': ''}]}}
    args = {'edition': 2, 'code': 'return $sample', 'inputs': {'sample': sample}, 'project_path': str(WORK), 'origin': 'training'}
    app = post(args)
    assert 'value' in app, {k: app[k] for k in app if k not in ('inputs', 'code')}
    assert app['value']['text'] == body and app['value']['blocks'][0]['text'] == body
    assert app['value_wire']
    env = {**os.environ, 'INDIEBIZOS_PROJECT_PATH': str(WORK),
           'INDIEBIZOS_AGENT_ID': 'research-delivery-verification',
           'INDIEBIZOS_TASK_ID': 'research-delivery-pure-smoke'}
    params = StdioServerParameters(command=str(ROOT / '.venv/bin/python3'), args=[str(ROOT / 'mcp_server.py')], env=env)
    with (WORK / 'mcp-smoke.log').open('w') as errors:
        async with stdio_client(params, errlog=errors) as (read, writer):
            async with ClientSession(read, writer) as session:
                await session.initialize()
                response = await session.call_tool('execute_ibl', args)
                assert not response.isError, response
                shown = next(json.loads(block.text) for block in response.content
                             if getattr(block, 'text', '').startswith('{'))
                assert shown['value']['text'] == {'$model_mirror_of': 'blocks'}
                assert shown['value']['blocks'][0]['text'] == body
                restored = []
                for path in (['value', 'text'], ['value', 'blocks', 0, 'text']):
                    response = await session.call_tool('execute_ibl', {'code': '', 'project_path': str(WORK),
                        'read_result': {'id': shown['result_ref']['id'], 'path': path, 'limit': 12000}})
                    assert not response.isError
                    page = next(json.loads(block.text) for block in response.content
                                if getattr(block, 'text', '').startswith('{'))
                    assert page['text'] == body
                    restored.append(path)
    state = json.loads((ROOT / 'data/restart_control/state.json').read_text())
    generation = Path(state['generation_dir'])
    paths = ['backend/cognition/evaluation_input.py', 'backend/cognition/evaluation_evidence.py',
             'backend/cognition/final_evaluator.py', 'backend/cognition/cognitive_eval.py',
             'backend/cognition/model_result_view.py', 'backend/common/value_relations.py',
             'backend/base/situation_delivery.py', 'backend/services/research_library.py']
    same = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() ==
               hashlib.sha256((generation / p).read_bytes()).hexdigest() for p in paths}
    assert all(same.values()), same
    result = {'generation': state['worker']['generation'], 'generation_matches_worktree': same,
              'rest_structured_body_and_wire_preserved': True, 'fresh_mcp_mirror': True,
              'full_body_chars': len(body), 'original_paths_read': restored,
              'external_business_actions': 0}
    write(ROOT / 'docs/experiments/research_delivery_activation_2026_11_04.json', result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
