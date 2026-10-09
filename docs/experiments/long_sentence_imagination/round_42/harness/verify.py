"""Independent artifact QA; does not render or alter production inputs."""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def probe(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format',
        '-of', 'json', str(path)], text=True))


def verify(video, captions, source, deck, output):
    media = probe(video)
    expected = json.loads(source.read_text())['scenes']
    metadata = json.loads((deck / 'deck.json').read_text())
    cues = []
    for line in captions.read_text().splitlines():
        if line.startswith('Dialogue:'):
            parts = line.split(',', 9)
            text = re.sub(r'\{[^}]*\}', '', parts[-1]).replace(r'\N', ' ')
            cues.append({'start': parts[1], 'end': parts[2], 'text': text})
    v = [s for s in media['streams'] if s['codec_type'] == 'video']
    a = [s for s in media['streams'] if s['codec_type'] == 'audio']
    duration = float(media['format']['duration'])
    checks = {
        'video_h264_1280x720': len(v) == 1 and v[0]['codec_name'] == 'h264'
        and (v[0]['width'], v[0]['height']) == (1280, 720),
        'audio_aac': len(a) == 1 and a[0]['codec_name'] == 'aac',
        'duration_20_to_70': 20 <= duration <= 70,
        'captions_exact': ' '.join(c['text'] for c in cues)
        == ' '.join(s['note'] for s in expected),
        'deck_notes_exact': [metadata['slides'][sid]['speaker_note']
                             for sid in metadata['slide_order']]
        == [s['note'] for s in expected],
        'deck_titles_exact': [metadata['slides'][sid]['title']
                              for sid in metadata['slide_order']]
        == [s['title'] for s in expected],
    }
    frames = output.parent / (output.stem + '_frames')
    frames.mkdir(exist_ok=True, parents=True)
    for n, seconds in enumerate([1, duration / 2, duration - 1]):
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(seconds),
                        '-i', str(video), '-frames:v', '1',
                        str(frames / f'{n}.png')], check=True)
    result = {'checks': checks, 'duration': duration, 'cues': cues,
              'media': media, 'video': str(video), 'caption_file': str(captions),
              'sha256': hashlib.sha256(video.read_bytes()).hexdigest(),
              'frames': str(frames),
              'scope': 'Deterministic metadata and text QA. Frame visual review is separate; no pronunciation approval.'}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'checks': checks, 'duration': duration}, ensure_ascii=False))


if __name__ == '__main__':
    verify(*(Path(p).resolve() for p in sys.argv[1:]))
