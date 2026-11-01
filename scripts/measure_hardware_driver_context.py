#!/usr/bin/env python3
"""Replay prompt assembly and explicit follow-up reads; never invoke models/devices."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import hashlib
import json
import subprocess
import tempfile
import types
from unittest.mock import patch

import guide_registry
import prompt_builder
from model_result_view import describe_actions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, help='Verified pre-change Git revision')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    def original(path):
        return subprocess.check_output(['git', 'show', f'{args.baseline}:{path}'], cwd=ROOT).decode()

    old = types.ModuleType('hardware_prompt_baseline')
    old.__file__ = str(ROOT / 'backend/cognition/prompt_builder.py')
    exec(compile(original('backend/cognition/prompt_builder.py'), old.__file__, 'exec'), old.__dict__)
    old_builder, new_builder = old.PromptBuilder(ROOT), prompt_builder.PromptBuilder(ROOT)
    cases = [
        ('remote_diagnosis', '원격 PC의 환경을 진단해줘', 'guest_helper.md', 'remote_pc_execution.md',
         ['limbs:guestpc'], [('remote_pc_execution.md', '3. 기본 어휘·GUI·작업 기록')]),
        ('file_transfer', '원격 파일을 가져와줘', 'guest_helper.md', 'remote_pc_execution.md',
         ['limbs:guestpc'], [('remote_pc_execution.md', '파일 전송과 결과 회수')]),
        ('long_update_status', '진행 중인 업데이트 결과를 확인해줘', 'guest_helper.md', 'remote_pc_execution.md',
         ['limbs:guestpc', 'self:limb'], [('remote_pc_execution.md', '작업 종료·출력·확인 자리')]),
        ('unattended_setup', '무인관리 설치 조건을 확인해줘', 'guest_helper.md', 'remote_pc_installation.md',
         ['self:limb'], [('remote_pc_installation.md', '모든 폴더·외장 드라이브와 관리자 명령')]),
        ('pc_control', 'PC 음량 상태를 확인해줘', 'pc_control.md', 'pc_control.md', [], []),
        ('phone_control', '폰 화면을 확인해줘', 'android_control.md', 'android_control.md', [], []),
        ('mixed_devices', 'PC와 폰의 상태를 확인해줘', 'guest_helper.md', 'guest_helper.md',
         ['limbs:guestpc'], [('pc_control.md', '빠른 호출'), ('android_control.md', '빠른 호출')]),
    ]
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        baseline_data = Path(directory)
        (baseline_data / 'guide_db.json').write_text(original('data/guide_db.json'))
        with patch.object(guide_registry, 'record_use'), patch.object(guide_registry, 'mark_injected'), \
                patch.object(guide_registry, 'freshness_note', return_value=''), \
                patch.object(guide_registry, 'catalog_revision', return_value='fixed-revision'), \
                patch.object(old_builder, '_load_guide_file', side_effect=lambda name: original('data/guides/' + name)):
            for name, request, before_guide, after_guide, actions, reads in cases:
                def co(guide):
                    return {'guide_files': [guide], 'capability_focus': {'highlight_actions': actions}}
                with patch.object(guide_registry, 'DATA_PATH', baseline_data):
                    before = old_builder._guide_block(before_guide) + old.compile_user_command(request, co(before_guide))
                after = new_builder._guide_block(after_guide) + prompt_builder.compile_user_command(request, co(after_guide))
                followups = []
                for filename, section in reads:
                    view = guide_registry.guide_read_view(
                        {'file': filename, 'content': (ROOT / 'data/guides' / filename).read_text()}, {'section': section})
                    if view.get('error'):
                        raise ValueError(view)
                    followups.append({'file': filename, 'section': section, 'response_chars': len(json.dumps(view, ensure_ascii=False))})
                # A conservative extra full describe, even if a supplied brief suffices.
                describe_chars = len(json.dumps(describe_actions(actions, ['self', 'limbs'], edition=2), ensure_ascii=False)) if actions else 0
                added = sum(r['response_chars'] for r in followups) + describe_chars
                rows.append({'case': name, 'initial_before_chars': len(before), 'initial_after_chars': len(after),
                             'guide_reads': followups, 'extra_full_describe_calls': int(bool(actions)),
                             'extra_full_describe_chars': describe_chars,
                             'after_with_explicit_reads_chars': len(after) + added,
                             'before_sha256': hashlib.sha256(before.encode()).hexdigest(),
                             'after_sha256': hashlib.sha256(after.encode()).hexdigest()})
    result = {'baseline_commit': subprocess.check_output(['git', 'rev-parse', args.baseline], cwd=ROOT).decode().strip(),
              'method': 'Deterministic assembly replay. Same request/actions; no model calls or remote execution. '
                        'Adds one conservative complete describe plus indicated section response to the new context. '
                        'Counts concatenated text once, not cumulative model tokens across rounds.',
              'model_input_tokens': None, 'model_output_tokens': None, 'cache_tokens': None,
              'user_wait_seconds': None, 'postprocessing_model_cost': None,
              'live_execution': False, 'cases': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    for row in rows:
        print(row['case'], row['initial_before_chars'], '->', row['initial_after_chars'],
              'with reads:', row['after_with_explicit_reads_chars'])


if __name__ == '__main__':
    main()
