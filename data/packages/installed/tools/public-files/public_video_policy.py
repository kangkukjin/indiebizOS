"""웹 동영상의 재생 판정·변환 정책. 파일/프로세스/네트워크를 소유하지 않는다."""


def transform(value):
    video = (value.get('video_codec') or '').lower()
    audio = (value.get('audio_codec') or '').lower()
    width, height = value.get('width'), value.get('height')
    max_edge, crf = 1920, 24
    known_size = all(type(n) is int and n > 0 for n in (width, height))
    copy = video in {'h264', 'vp8', 'vp9', 'av1'} and known_size and max(width, height) <= max_edge
    transcode = (not copy or bool(audio and audio not in {'aac', 'mp3', 'opus', 'vorbis', 'flac'}))
    if not video:
        transcode = value.get('extension', '').lower() not in {'mp4', 'm4v', 'webm'}
    return [{'copy_video': copy, 'needs_transcode': transcode, 'max_edge': max_edge, 'crf': crf}]
