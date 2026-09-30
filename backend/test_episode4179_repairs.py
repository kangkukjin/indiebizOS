"""4179: repair inputs/results, current supervision, and stable script observation."""
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from test_conscious_supervisor import supervisor, verdict  # noqa: F401
from test_ibl_general_capabilities import boundary, adapter  # noqa: F401
from test_audio_listen import audio, _fake_value  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def finish(controller, code, error=False):
    key = controller._start('execute_ibl', {'code': code})
    controller._finish(key, {'success': not error}, error)


@pytest.mark.parametrize('recovery', ['during_review', 'before_delivery'])
def test_changed_program_recovery_retires_old_failure_instruction(supervisor, monkeypatch, recovery):
    finish(supervisor, '[t:read]{path:"wrong"}', True)
    bad = ('$s=[t:read]{path:"right"};return $s >> '
           '[table:filter]{where:($r)=> contains($r.id,"render")} >> [table:select]{columns:["id"]}')
    good = bad.replace('return $s >>', 'return $s.items >>')
    finish(supervisor, bad, True)
    def review(c, *a, **kw):
        if recovery == 'during_review':
            finish(c, good)
        return verdict(c, 'REWORK', instruction='repeat old lookup')
    monkeypatch.setattr('supervisor_runtime.invoke', review)
    supervisor.review('repeated_failure')
    if recovery == 'before_delivery':
        assert supervisor.pending
        finish(supervisor, good)
    assert supervisor.boundary() is None
    assert any(v['open'] for v in supervisor.issues.values())


def test_result_paging_does_not_discard_needed_failure_instruction(supervisor, monkeypatch):
    finish(supervisor, 'bad path', True)
    finish(supervisor, 'bad shape', True)
    monkeypatch.setattr('supervisor_runtime.invoke', lambda c, *a, **kw:
                        verdict(c, 'REWORK', instruction='repair shape'))
    supervisor.review('repeated_failure')
    key = supervisor._start('execute_ibl', {'code': '', 'read_result': {'id': 'saved'}})
    supervisor._finish(key, {'text': 'diagnostic'})
    assert supervisor.boundary()['instruction'] == 'repair shape'


@pytest.mark.parametrize('code', [
    '[t:read]{path:"elsewhere"}.items',
    '[if:false]{[t:read]{path:"broken"}}',
])
def test_unrelated_ibl_success_keeps_failure_guidance(supervisor, monkeypatch, code):
    finish(supervisor, '[t:read]{path:"broken"}', True)
    finish(supervisor, '[t:read]{path:"broken"}', True)
    monkeypatch.setattr('supervisor_runtime.invoke', lambda c, *a, **kw:
                        verdict(c, 'REWORK', instruction='repair original source'))
    supervisor.review('repeated_failure')
    finish(supervisor, code)
    assert supervisor.boundary()['instruction'] == 'repair original source'


def test_tool_stall_clock_excludes_prior_model_authoring(supervisor, monkeypatch):
    seen = []
    monkeypatch.setattr(supervisor, 'review', lambda reason: seen.append(reason))
    supervisor.config.update(stall_s=180, long_task_s=10000)
    key = supervisor._start('execute_ibl', {'code': 'render'})
    started = supervisor.active[key]['started']
    supervisor.last_progress = started - 300
    supervisor.tick(started + 19)
    assert not seen
    # A newly started parallel call cannot hide an older stalled call.
    supervisor._start('execute_ibl', {'code': 'other'})
    supervisor.tick(started + 181)
    assert seen == ['tool_stalled']


def test_failed_large_inputs_are_referenced_with_types_and_without_retyping(boundary, tmp_path):
    from system_tools_ibl import _execute_ibl_unified_impl as run
    from model_result_view import resolve_input_refs
    values = {'template': 'HTML' * 4000, 'rows': [{'n': Decimal('1.25')}]}
    first = json.loads(run({'edition': 2, 'code': '$i=1;return $rows', 'inputs': values}, str(tmp_path)))
    assert first['executed'] is False
    refs = first['request_inputs']['input_args']
    assert resolve_input_refs(refs)[0] == values
    assert 'HTMLHTML' not in json.dumps(first)
    second = json.loads(run({'edition': 2, 'code': 'return len($template)', 'inputs': refs}, str(tmp_path)))
    assert second['success'] and second['value'] == 16000


def test_failed_inputs_never_offer_secret_masked_values(boundary, tmp_path):
    from system_tools_ibl import _execute_ibl_unified_impl as run
    first = json.loads(run({'edition': 2, 'code': '$i=1',
                           'inputs': {'config': {'api_key': 'sk-test-not-a-real-credential-12345678901234567890'}}}, str(tmp_path)))
    assert 'config' not in first['request_inputs']['input_args']
    assert 'config' in first['request_inputs']['unavailable']


def test_completed_image_like_call_survives_later_failure(boundary, tmp_path, monkeypatch):
    import ibl_v2_adapters
    from ibl_v2_ir import Fault
    from system_tools_ibl import _execute_ibl_unified_impl as run
    calls = []
    def fail(*_):
        raise Fault('TOOL', 'invalid audio timing')
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: {
        't:image': adapter(lambda *_: calls.append('image') or {'answer': 'clear'}, result='Record'),
        't:audio': adapter(fail)})
    first = json.loads(run({'edition': 2, 'code': '$img=[t:image]{}; [t:audio]{}'}, str(tmp_path)))
    assert not first['success']
    done = first['result_ref']['completed_calls']
    assert [d['action'] for d in done] == ['t:image']
    second = json.loads(run({'edition': 2, 'code': 'return $입력.answer',
                            'inputs': done[0]['input_args']}, str(tmp_path)))
    assert second['success'] and second['value'] == 'clear' and calls == ['image']


def test_completed_call_reference_keeps_incomplete_source(boundary, tmp_path, monkeypatch):
    import ibl_v2_adapters
    from ibl_v2_adapters import Adapted
    from system_tools_ibl import _execute_ibl_unified_impl as run
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: {
        't:read': adapter(lambda *_: Adapted(7, {'incomplete': True}))})
    first = json.loads(run({'edition': 2, 'code': '[t:read]{};return 1/0'}, str(tmp_path)))
    args = first['result_ref']['completed_calls'][0]['input_args']
    second = json.loads(run({'edition': 2, 'code': 'return $입력', 'inputs': args}, str(tmp_path)))
    assert second['success'] and second['value'] == 7 and second['source_complete'] is False
    # A subsequent rejected edit must retain that source status too.
    failed = json.loads(run({'edition': 2, 'code': '$i=1', 'inputs': args}, str(tmp_path)))
    third = json.loads(run({'edition': 2, 'code': 'return $입력',
                           'inputs': failed['request_inputs']['input_args']}, str(tmp_path)))
    assert third['success'] and third['source_complete'] is False


def test_completed_call_keeps_incomplete_input_ancestry(boundary, tmp_path, monkeypatch):
    import ibl_v2_adapters
    from ibl_v2_adapters import Adapted
    from system_tools_ibl import _execute_ibl_unified_impl as run
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: {
        't:read': adapter(lambda *_: Adapted(7, {'incomplete': True})),
        't:copy': adapter(lambda _, params: params['value'], params={'value': 'Number'}),
        't:other': adapter(lambda *_: 9)})
    first = json.loads(run({'edition': 2,
                           'code': '$x=[t:read]{};[t:copy]{value:$x};[t:other]{};return 1/0'}, str(tmp_path)))
    calls = first['result_ref']['completed_calls']
    assert len(calls) == 3
    for call, complete in zip(calls, [False, False, True]):
        assert call['source_complete'] is complete
        replay = json.loads(run({'edition': 2, 'code': 'return $입력',
                                 'inputs': call['input_args']}, str(tmp_path)))
        assert replay['success'] and replay['source_complete'] is complete


def test_script_list_shape_is_checked_before_execution():
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    reg = load_registry(str(ROOT))
    # 긴문장 10회차: 행 목록을 가진 것으로 알려진 봉투는 행 목록 자리가 그대로 받는다. 모양은 여전히 실행 전에 검사한다.
    enveloped = compile_program('$s=[self:script]{op:"list"};return $s >> [table:select]{columns:["id"]}', reg)
    good = compile_program('$s=[self:script]{op:"list"};return $s.items >> [table:select]{columns:["id"]}', reg)
    bad = compile_program('$s=[self:script]{op:"list"};return $s.count >> [table:select]{columns:["id"]}', reg)
    assert not enveloped.issues, enveloped.issues
    assert bad.issues
    assert not good.issues, good.issues
    # Status changes over time: it must not become a reusable frozen read.
    assert reg['self:script'].contract['per_run'] is True
    implicit = compile_program('return [self:script]{id:"example"}', reg)
    assert not implicit.issues and str(implicit.result_type) == 'Unknown'


@pytest.mark.parametrize('status', ['starting', 'running', 'done', 'failed'])
def test_script_progress_shape_survives_job_completion(tmp_path, monkeypatch, status):
    from test_script_bg_progress import S
    jobs = tmp_path / 'jobs'
    jobs.mkdir()
    log = tmp_path / 'job.log'
    log.write_text('# job exit=0\n--- stdout ---\nRESULT\n--- stderr ---\nPROGRESS last\n')
    job = {'job_id': 'job', 'id': 'render', 'status': status, 'log': str(log),
           'result': {'success': status != 'failed', 'items': [{'title': 'business result'}]}}
    (jobs / 'job.json').write_text(json.dumps(job))
    monkeypatch.setattr(S, '_JOB_DIR', jobs)
    monkeypatch.setattr(S, '_pid_alive', lambda _: True)
    result = S.op_status({'job_id': 'job'})
    assert result['items'][0]['progress'] == ['PROGRESS last']
    log.unlink()
    assert S.op_status({'job_id': 'job'})['items'][0]['progress'] == []


def test_audio_selected_ranges_do_not_process_whole_file(audio, monkeypatch):
    api, ctx, _ = audio
    calls = []
    monkeypatch.setattr(api, 'analyze_clip', lambda *a: calls.append(a[1]) or _fake_value())
    result = api.listen_file({'path': 'tone.wav', 'question': 'Inspect both ends',
                             'ranges': [{'start': 0, 'end': 1}, {'start': 5, 'end': 6}]}, ctx, 'analyze')
    assert result['success'] and calls == [1, 1]
    assert result['completed_ranges'] == [(0, 1), (5, 6)]
    assert result['coverage'] == 'selected_or_partial'


def test_audio_prompt_bounds_and_actual_model_accounting(audio, monkeypatch):
    import android_audio_provider as provider
    from model_call_context import capture_usage
    from types import SimpleNamespace
    _, _, directory = audio
    clip = directory / 'clip.flac'
    clip.write_bytes(b'audio fixture')
    requests = []
    monkeypatch.setattr('model_resolver.env_key_for_provider', lambda _: 'fixture')
    data = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps({
        'answer': 'clear', 'text': '', 'uncertain': False, 'events': []})}]}}],
        'usageMetadata': {'promptTokenCount': 12, 'candidatesTokenCount': 3}}
    monkeypatch.setattr(provider.requests, 'post', lambda *a, **kw:
                        requests.append(kw) or SimpleNamespace(ok=True, json=lambda: data))
    chosen = {'provider': 'google', 'model': 'audio-fixture', 'api': 'generate', 'base_url': 'https://fixture.invalid'}
    with capture_usage() as usage:
        result = provider.analyze_clip(clip, 73.7, 'analyze', chosen, 'listen')
    prompt = requests[0]['json']['contents'][0]['parts'][0]['text']
    assert '73.700000' in prompt and '0 <= start <= end' in prompt
    assert result['model'] == 'audio-fixture'
    assert len(usage) == 1 and usage[0]['model'] == 'audio-fixture'
    assert usage[0]['input'] == 12 and usage[0]['output'] == 3


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
