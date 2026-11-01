#!/usr/bin/env python3
"""Compare connected_limbs on identical snapshots; no models or device commands."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import ast
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import subprocess
from unittest.mock import patch
from xml.etree import ElementTree as ET

import associative_recall as recall
import control_observations
import device_registry
import guide_registry
import hardware_registry
import limb_keys


def encoded(value):
    return json.dumps(value, ensure_ascii=False)


def summary(text):
    root = ET.fromstring(text)
    rows = root.findall('limb')
    return {'chars': len(text), 'device_rows': len(rows),
            'row_chars': sum(len(ET.tostring(r, encoding='unicode')) for r in rows),
            'driver_references': len(root.findall('driver')),
            'control_briefs': len(root.findall('control_brief')),
            'sha256': hashlib.sha256(text.encode()).hexdigest()}


def synthetic(count):
    specs = [('pc', 'windows', 'resident-v1', 'user_login'),
             ('pc', 'darwin', 'resident-v1', 'user_login'),
             ('phone', 'android', 'indiebiz-v1', 'unknown'),
             ('tv', 'tizen', 'network-api', 'unknown'),
             ('pc', 'windows', 'resident-v1', 'machine')]
    keys, hardware, live = [], [], []
    for i in range(count):
        kind, platform, adapter, scope = specs[i % len(specs)]
        row = {'device_id': f'device-{i:04}', 'alias': f'장치-{i:04}', 'revoked': False,
               'registration': {'state': 'active', 'kind': kind, 'adapter': adapter,
                                'context': f'작업 공간 {i} / 등록된 사용자 용도', 'generation': f'g-{i}',
                                'paused': bool(i % 3), 'capabilities': {'os': platform, 'service_scope': scope}}}
        (hardware if adapter == 'network-api' else keys).append(row)
        if adapter != 'network-api' and i % 2:
            live.append(row)
    return keys, hardware, live


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--live', action='store_true', help='Read existing registries; store only aggregate sizes/hashes')
    args = parser.parse_args()
    baseline = subprocess.check_output(['git', 'rev-parse', args.baseline], cwd=ROOT, text=True).strip()
    source = subprocess.check_output(['git', 'show', f'{baseline}:backend/cognition/associative_recall.py'], cwd=ROOT, text=True)
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == '_connected_limbs')
    namespace = dict(vars(recall))
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<baseline-connected-limbs>', 'exec'), namespace)
    old = namespace['_connected_limbs']
    request = recall.RecallRequest(None, '같은 요청', [])

    def compare(snapshot, local_count=0):
        keys, hardware, live = snapshot
        with patch.object(limb_keys, 'list_keys', side_effect=lambda **kw: deepcopy(keys)), \
                patch.object(hardware_registry, 'devices', side_effect=lambda: deepcopy(hardware)), \
                patch.object(device_registry, 'live_with_capability', side_effect=lambda *a: deepcopy(live)), \
                patch.object(control_observations, 'count', return_value=local_count), redirect_stdout(io.StringIO()):
            before = old(request, None).text
            after = recall._connected_limbs(request, None).text
        before_rows = {r.attrib['device_id']: (r.attrib['name'], r.text) for r in ET.fromstring(before).findall('limb')}
        after_rows = {r.attrib['device_id']: (r.attrib['name'], r.text) for r in ET.fromstring(after).findall('limb')}
        assert before_rows == after_rows
        return {'before': summary(before), 'after': summary(after), 'identity_context_preserved': True}, before, after

    scales = []
    for count in (1, 10, 100, 1000):
        result, _, _ = compare(synthetic(count))
        scales.append({'registered_devices': count, **result})
    report = {'baseline_commit': baseline, 'method': 'Same registration/live-cache snapshot, old and new introduction. '
              'Synthetic scales include local body. Explicit followups are predetermined guide section and single-target '
              'detail reads, not a measured model trajectory. Count each response once; no cumulative-token claim.',
              'model_input_tokens': None, 'model_output_tokens': None, 'cache_tokens': None,
              'total_completion_seconds': None, 'model_quality': None, 'postprocessing_model_cost': None,
              'device_commands_executed': False, 'scales': scales}
    if args.live:
        snapshot = (limb_keys.list_keys(include_revoked=False), hardware_registry.devices(),
                    device_registry.live_with_capability(limb_keys.GUEST_PC_CLASS))
        result, before, after = compare(snapshot, control_observations.count('device:__local__'))
        report['live_snapshot'] = result
        rows = ET.fromstring(after).findall('limb')[1:]
        pc = next((r.attrib['device_id'] for r in rows if 'pc_control' in r.attrib.get('drivers', '').split(',')), None)
        phone = next((r.attrib['device_id'] for r in rows if 'android_control' in r.attrib.get('drivers', '').split(',')), None)
        spec = importlib.util.spec_from_file_location('connected_context_handler', ROOT / 'data/packages/installed/tools/guest-helper/handler.py')
        handler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(handler)
        existing = {r.attrib['file'] for r in ET.fromstring(before).findall('control_brief')}
        cases = [('non_hardware', [], []), ('simple_pc_control', ['pc_control.md'], []),
                 ('target_details', [], [pc] if pc else []),
                 ('mixed_devices', ['pc_control.md', 'android_control.md'], [d for d in (pc, phone) if d])]
        results = []
        with patch.object(limb_keys, 'list_keys', side_effect=lambda **kw: deepcopy(snapshot[0])), \
                patch.object(hardware_registry, 'devices', side_effect=lambda: deepcopy(snapshot[1])), \
                patch.object(device_registry, 'live_with_capability', side_effect=lambda *a: deepcopy(snapshot[2])), \
                redirect_stdout(io.StringIO()):
            for name, guides, targets in cases:
                sections = []
                for filename in guides:
                    section = guide_registry.guide_delivery(filename)['section']
                    content = (guide_registry.GUIDES_DIR / filename).read_text()
                    view = guide_registry.guide_read_view({'file': filename, 'content': content}, {'section': section})
                    assert 'error' not in view
                    sections.append({'file': filename, 'section': section, 'chars': len(encoded(view))})
                status_chars = sum(len(encoded(handler._limb_list({'limb': target}))) for target in targets)
                old_extra = sum(s['chars'] for s in sections if s['file'] not in existing) + status_chars
                new_extra = sum(s['chars'] for s in sections) + status_chars
                results.append({'case': name, 'guide_reads': sections, 'target_detail_reads': len(targets),
                                'target_detail_chars': status_chars, 'before_with_reads_chars': len(before) + old_extra,
                                'after_with_reads_chars': len(after) + new_extra})
        report['explicit_followups'] = results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
