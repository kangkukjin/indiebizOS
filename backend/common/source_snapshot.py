"""원문과 구조 통화를 함께 저장할 때 잃으면 안 되는 자료. 실행 진단은 포함하지 않는다."""
from pathlib import Path


def source_snapshot(envelope):
    """본문이 명시된 봉투만 보존한다. 임의 items를 원문으로 추측하지 않는다."""
    if not isinstance(envelope, dict):
        return {}
    body_keys = ('transcript', 'text', 'content', 'formatted_transcript')
    out = {key: envelope[key] for key in body_keys
           if isinstance(envelope.get(key), str) and envelope[key].strip()}
    if envelope.get('saved_to_file') and envelope.get('file_path'):
        # 저장된 JSON은 캐시 파일의 수명과 독립된 원문 스냅샷이다.
        path = str(envelope['file_path'])
        try:
            out['text'] = Path(path).read_text(encoding='utf-8')
        except (OSError, UnicodeError) as exc:
            raise ValueError(f'원문 파일을 보존할 수 없습니다: {path} — {exc}') from exc
        out['source_file'] = path
    if not out:
        return {}
    for key in ('segments', 'title', 'url', 'source_url', 'video_id', 'language'):
        if key in envelope:
            out[key] = envelope[key]
    return out
