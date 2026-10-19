"""Evaluator instructions must follow the current prompt file in a live process."""
import boot_paths  # noqa: F401 — direct execution uses the same layered imports.
import pytest

import cognitive_eval


@pytest.fixture
def prompt_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cognitive_eval, '__file__',
                        str(tmp_path / 'backend/cognition/cognitive_eval.py'))
    path = tmp_path / 'data/common_prompts/evaluator_prompt.md'
    path.parent.mkdir(parents=True)
    return path


def test_evaluator_uses_updated_instructions_without_recreation(prompt_file):
    evaluator = cognitive_eval.CognitiveEvalMixin()
    prompt_file.write_text('이전 판정 기준', encoding='utf-8')
    assert evaluator._load_evaluator_prompt() == '이전 판정 기준'
    prompt_file.write_text('정정된 판정 기준', encoding='utf-8')
    assert evaluator._load_evaluator_prompt() == '정정된 판정 기준'


def test_evaluator_missing_prompt_recovers_and_does_not_keep_deleted_text(prompt_file):
    evaluator = cognitive_eval.CognitiveEvalMixin()
    fallback = evaluator._load_evaluator_prompt()
    assert fallback
    prompt_file.write_text('복구된 판정 기준', encoding='utf-8')
    assert evaluator._load_evaluator_prompt() == '복구된 판정 기준'
    prompt_file.unlink()
    assert evaluator._load_evaluator_prompt() == fallback


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
