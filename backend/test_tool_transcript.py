"""자막 길이가 본문·세그먼트 반환 계약과 후속 요약을 바꾸지 않는다."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest


@pytest.fixture
def transcript(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/youtube/tool_transcript.py'
    spec = importlib.util.spec_from_file_location('transcript_contract_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'get_youtube_info', lambda url: {
        'success': True, 'title': '자막 계약', 'duration': 120})
    # 이전 구현의 파일 저장도 격리해서 실패 재현이 실 사용자 파일을 쓰지 않게 한다.
    monkeypatch.setattr(module, '__file__', str(tmp_path / 'a/b/c/d/tool_transcript.py'))
    return module


def source(monkeypatch, texts):
    segments = [SimpleNamespace(start=i * 10, duration=10, text=t) for i, t in enumerate(texts)]
    monkeypatch.setitem(sys.modules, 'youtube_transcript_api', SimpleNamespace(
        YouTubeTranscriptApi=lambda: SimpleNamespace(fetch=lambda *a, **kw: segments)))


@pytest.mark.parametrize('size', [9999, 10000, 10001, 70000])
def test_transcript_shape_and_last_segment_survive_length_boundary(transcript, monkeypatch, size):
    texts = ['앞' * (size - len(' 마지막 근거')), '마지막 근거']
    source(monkeypatch, texts)
    result = transcript.get_youtube_transcript('abcdefghijk', languages=['en'], include_timestamps=True)
    assert result['success'], result
    assert result['transcript'] == ' '.join(texts)
    assert result['segments'] == result['items']
    assert result['items'][-1]['text'] == texts[-1]
    assert result['formatted_transcript'].endswith('[00:10] 마지막 근거')
    assert not result.get('saved_to_file')


def test_long_transcript_reaches_summary_without_empty_source(transcript, monkeypatch, tmp_path):
    source(monkeypatch, ['긴 자막 ' * 3000, '끝의 중요한 결론'])
    seen = []
    def summarize(text, prompt, model):
        seen.append(text)
        return '요약', {'transcript_chars': len(text), 'transcript_chunks': 1}
    monkeypatch.setattr(transcript, '_summarize_complete_transcript', summarize)
    monkeypatch.setattr(transcript, 'OUTPUTS_DIR', str(tmp_path))
    monkeypatch.setattr(transcript, 'get_summary_ai_client', lambda: object())
    monkeypatch.setattr('webbrowser.open', lambda *a: None)
    result = transcript.summarize_youtube('abcdefghijk', languages=['en'])
    assert result['success'], result
    assert len(seen) == 1 and seen[0].endswith('끝의 중요한 결론')


def test_large_transcript_display_is_bounded_but_reference_keeps_full_value(transcript, monkeypatch, tmp_path):
    import model_result_view as view
    from supervision_store import TurnStore
    source(monkeypatch, ['본문 ' * 24000, '마지막 문장'])
    value = transcript.get_youtube_transcript('abcdefghijk', languages=['en'])
    store = TurnStore(tmp_path / 'evidence')
    monkeypatch.setattr(view, 'evidence_store', lambda: store)
    shown = view.project_v2_result({'edition': 2, 'success': True, 'source_complete': True, 'value': value})
    assert len(json.dumps(shown, ensure_ascii=False)) < len(value['transcript'])
    restored, _ = view.resolve_input_refs(shown['result_ref']['input_args'])
    assert restored['입력'] == value
    assert restored['입력']['transcript'].endswith('마지막 문장')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
