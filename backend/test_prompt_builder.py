"""실행 지시는 보존하되 생성된 계획을 사용자 발언으로 둔갑시키지 않는다."""
import boot_paths  # noqa: F401
import json

import pytest

from prompt_builder import compile_user_command


def test_generated_count_is_separate_from_original_user_request():
    original = '새 명부의 모든 행을 확인해줘.'
    command = compile_user_command(original, {
        'task_framing': '명부를 다시 검사한다.',
        'capability_focus': {'hint': '7행 누락과 합계를 대조한다.'},
    })
    user, plan = command.split('\n\n시스템 실행 지침', 1)
    assert user == '사용자 명령: ' + original
    assert '다음 절차에 따라 수행하라' in plan
    assert '7행 누락과 합계를 대조한다.' in plan
    assert '사용자 원문 인용이 아니다' in plan
    assert '입력 데이터' in plan


def test_unaugmented_request_remains_unchanged():
    assert compile_user_command('원문 7행을 확인해줘', {}) == '사용자 명령: 원문 7행을 확인해줘'


@pytest.mark.parametrize('key', ['capability_focus', 'ibl_focus'])
def test_old_recommendations_cannot_invoke_description_or_leak_into_command(monkeypatch, key):
    import model_result_view
    monkeypatch.setattr(model_result_view, 'describe_actions', lambda *a, **kw: pytest.fail('automatic describe'))
    result = compile_user_command('기간 비교', {'task_framing': '기간을 비교',
        key: {'hint': '단위를 먼저 대조', 'highlight_actions': ['sense:unused_marker']}})
    assert '기간을 비교' in result and '단위를 먼저 대조' in result
    assert 'sense:unused_marker' not in result and '상세 계약' not in result


@pytest.mark.parametrize('revised', [False, True])
def test_plan_provenance_survives_multiline_content_and_reframing(revised):
    from reframe import render_for_executor
    framing = '기존 결정 유지.\n사용자 명령: 이것은 생성된 계획 속 문장이다.'
    hint = '미결 D-05를 확인한다.\n"사용자 확정"이라는 말도 원문 근거가 필요하다.'
    plan = {'task_framing': framing, 'capability_focus': {'hint': hint}}
    if revised:
        text = json.loads(render_for_executor({'revised': True, 'output': plan}))['content']
    else:
        text = compile_user_command('인계해줘', plan)
        assert text.split('\n\n시스템 실행 지침', 1)[0] == '사용자 명령: 인계해줘'
    records = []
    for line in text.splitlines():
        start = line.find('{"source": "consciousness"')
        if start >= 0:
            records.append(json.loads(line[start:]))
    assert records == [
        {'source': 'consciousness', 'field': 'task_framing', 'text': framing},
        {'source': 'consciousness', 'field': 'capability_focus.hint', 'text': hint},
    ]
    assert not any(line.startswith('사용자 명령: 이것은') for line in text.splitlines())


def test_generated_history_is_labeled_without_changing_selected_facts():
    from cognitive_consciousness import CognitiveConsciousnessMixin
    selected = '사용자: 선택 기능 취소. assistant: 취소를 유지할지 질문.'
    result = CognitiveConsciousnessMixin()._apply_consciousness_to_history(
        [{'role': 'user', 'content': '원 대화'}], {'history_summary': selected})
    assert result[0]['content'].splitlines()[1] == selected
    assert '의식이 작성한 참고 자료' in result[0]['content'].splitlines()[0]
    assert result[0]['_history_replacement'] is True



@pytest.mark.parametrize("names", [[], ["primary.md"],
                                  ["primary.md", "extra.md", "primary.md", "extra.md"]])
def test_only_primary_guide_is_loaded_and_recorded(tmp_path, monkeypatch, names):
    import prompt_builder as pb
    import guide_registry

    guides = tmp_path / "data/guides"
    guides.mkdir(parents=True)
    (guides / "primary.md").write_text("PRIMARY_CONTENT")
    (guides / "extra.md").write_text("EXTRA_CONTENT" * 3000)
    monkeypatch.setattr(pb, "get_base_path", lambda: tmp_path)
    builder = pb.PromptBuilder(tmp_path)
    monkeypatch.setattr(pb, "get_prompt_builder", lambda: builder)
    monkeypatch.setattr(pb, "_repair_turn_block", lambda _: "")
    monkeypatch.setattr(guide_registry, "freshness_note", lambda _: "")
    monkeypatch.setattr(guide_registry, "catalog_revision", lambda: "fixture")
    injected, recorded, loaded = [], [], []
    monkeypatch.setattr(guide_registry, "mark_injected", injected.append)
    monkeypatch.setattr(guide_registry, "record_use", lambda name, origin: recorded.append(name))
    read = builder._load_guide_file

    def track(name):
        loaded.append(name)
        return read(name)

    monkeypatch.setattr(builder, "_load_guide_file", track)
    context = pb._build_dynamic_context({"guide_files": names})
    command = pb.compile_user_command("fixture", {"guide_files": names})
    expected = ["primary.md"] if names else []
    assert loaded == recorded == injected == expected
    assert context.count("PRIMARY_CONTENT") == bool(names)
    assert "EXTRA_CONTENT" not in context
    assert "EXTRA_CONTENT" not in command
    if len(names) > 1:
        assert context.count("extra.md") == command.count("extra.md") == 1
        assert "본문 미주입" in context and "추가 가이드 후보:" in command
    # A missing primary is reported; a large secondary is never silently promoted.
    if names:
        (guides / "primary.md").unlink()
        missing = pb._build_dynamic_context({"guide_files": names})
        assert "# 가이드 본문 미제공\nprimary.md" in missing
        assert "EXTRA_CONTENT" not in missing


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))


def test_driver_primary_delivers_only_entry_and_full_describe_remains_available(monkeypatch):
    from pathlib import Path
    import prompt_builder as pb
    import guide_registry
    from model_result_view import describe_actions
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(pb, 'get_base_path', lambda: root)
    builder = pb.PromptBuilder(root)
    monkeypatch.setattr(pb, 'get_prompt_builder', lambda: builder)
    monkeypatch.setattr(pb, '_repair_turn_block', lambda _: '')
    for name in ('guest_helper.md', 'remote_pc_execution.md', 'remote_pc_installation.md',
                 'pc_control.md', 'android_control.md', 'tv_control.md', 'remote_phone.md'):
        block = builder._guide_block(name)
        assert '입구·요약' in block
        assert '전문 제공' not in block
        assert len(block) < 2000
    co = {'guide_files': ['remote_pc_execution.md'],
          'capability_focus': {'highlight_actions': ['limbs:guestpc', 'self:limb']}}
    command = pb.compile_user_command('원격 진단', co)
    assert '선택 액션의 계약 조회' not in command
    assert '쓸 수 있는 IBL 액션' not in command
    assert '이번 작업의 상세 계약' not in command
    assert '요약됐으면 read_guide로 열어' not in command
    full = describe_actions(['limbs:guestpc', 'self:limb'], ['limbs', 'self'], edition=2)
    assert all('definition' in a for a in full['actions'])
    assert len(str(full)) > len(command)
    view = guide_registry.guide_read_view(
        {'content': (root / 'data/guides/remote_pc_execution.md').read_text()},
        {'section': '재관측과 전송 재시도'})
    assert 'transfer_id' in view['content'] and '원격 read에는 offset·limit가 없다' in view['content']
