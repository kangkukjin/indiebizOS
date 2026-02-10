"""
nas_subtitle.py - NAS 자막 처리 모듈
자막 변환 (SRT/ASS/SMI → WebVTT) 및 자막 API

api_nas.py에서 분리됨
"""

import re
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Request, Response, Query

# ============ 상수 ============

# 지원하는 자막 확장자
SUBTITLE_EXTENSIONS = {'.srt', '.vtt', '.ass', '.ssa', '.smi'}

# 언어 코드 → 표시명
LANG_NAMES = {
    'ko': '한국어', 'en': 'English', 'ja': '日本語', 'zh': '中文',
    'es': 'Español', 'fr': 'Français', 'de': 'Deutsch', 'pt': 'Português',
    'ru': 'Русский', 'it': 'Italiano', 'th': 'ไทย', 'vi': 'Tiếng Việt',
}


# ============ 자막 변환 함수 ============

def srt_to_vtt(srt_content: str) -> str:
    """SRT 자막을 WebVTT 형식으로 변환"""
    lines = srt_content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    vtt_lines = ['WEBVTT', '']

    for line in lines:
        # SRT 타임코드: 00:01:23,456 --> 00:01:25,789
        # VTT 타임코드: 00:01:23.456 --> 00:01:25.789
        if '-->' in line:
            line = line.replace(',', '.')
        vtt_lines.append(line)

    return '\n'.join(vtt_lines)


def ass_to_vtt(ass_content: str) -> str:
    """ASS/SSA 자막을 WebVTT 형식으로 변환 (기본 텍스트만 추출)"""
    vtt_lines = ['WEBVTT', '']
    counter = 1

    for line in ass_content.split('\n'):
        line = line.strip()
        # Dialogue: 0,0:01:23.45,0:01:25.67,Default,,0,0,0,,자막 텍스트
        if line.startswith('Dialogue:'):
            parts = line.split(',', 9)
            if len(parts) >= 10:
                start_raw = parts[1].strip()
                end_raw = parts[2].strip()

                # ASS 타임코드: H:MM:SS.CC → HH:MM:SS.CCC
                def convert_ass_time(t):
                    # H:MM:SS.CC 형식
                    match = re.match(r'(\d+):(\d{2}):(\d{2})\.(\d{2,3})', t)
                    if match:
                        h, m, s, cs = match.groups()
                        ms = cs.ljust(3, '0')[:3]
                        return f"{int(h):02d}:{m}:{s}.{ms}"
                    return t

                start = convert_ass_time(start_raw)
                end = convert_ass_time(end_raw)

                # 텍스트에서 ASS 태그 제거 {\tag} 및 \N → 줄바꿈
                text = parts[9]
                text = re.sub(r'\{[^}]*\}', '', text)
                text = text.replace('\\N', '\n').replace('\\n', '\n').strip()

                if text:
                    vtt_lines.append(str(counter))
                    vtt_lines.append(f"{start} --> {end}")
                    vtt_lines.append(text)
                    vtt_lines.append('')
                    counter += 1

    return '\n'.join(vtt_lines)


def smi_to_vtt(smi_content: str, lang_class: str = "KRCC") -> str:
    """SMI(SAMI) 자막을 WebVTT 형식으로 변환. lang_class로 언어 필터링 (기본 한국어)"""
    vtt_lines = ['WEBVTT', '']

    # SYNC + P 블록 추출 (클래스 정보 포함)
    sync_pattern = re.compile(
        r'<SYNC\s+Start\s*=\s*(\d+)\s*>\s*<P\s+Class\s*=\s*(\w+)\s*>(.*?)(?=<SYNC|</BODY|$)',
        re.IGNORECASE | re.DOTALL
    )

    matches = sync_pattern.findall(smi_content)
    if not matches:
        # Class 속성 없는 간단한 SMI → 전체 추출
        simple_pattern = re.compile(
            r'<SYNC\s+Start\s*=\s*(\d+)\s*>.*?<P[^>]*>(.*?)(?=<SYNC|</BODY|$)',
            re.IGNORECASE | re.DOTALL
        )
        matches = [(ms, lang_class, text) for ms, text in simple_pattern.findall(smi_content)]

    if not matches:
        return 'WEBVTT\n'

    # 지정 언어 클래스만 필터링
    cues = []
    for ms_str, cls, raw_text in matches:
        if cls.upper() != lang_class.upper():
            continue
        ms = int(ms_str)
        # HTML 태그 제거
        text = re.sub(r'<[^>]+>', '', raw_text)
        # <br> → 줄바꿈 (태그 제거 전에 처리)
        raw_text_br = re.sub(r'<br\s*/?\s*>', '\n', raw_text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', raw_text_br)
        # HTML 엔티티 변환
        text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        text = text.strip()
        if not text or text == ' ':
            cues.append((ms, ''))
        else:
            cues.append((ms, text))

    # 밀리초 → VTT 타임코드
    def ms_to_vtt_time(ms):
        h = ms // 3600000
        m = (ms % 3600000) // 60000
        s = (ms % 60000) // 1000
        ms_rem = ms % 1000
        return f"{h:02d}:{m:02d}:{s:02d}.{ms_rem:03d}"

    counter = 1
    for i, (start_ms, text) in enumerate(cues):
        if not text:
            continue
        # 다음 큐의 시작을 종료 시간으로 사용
        end_ms = start_ms + 5000
        for j in range(i + 1, len(cues)):
            end_ms = cues[j][0]
            break
        if end_ms <= start_ms:
            end_ms = start_ms + 5000

        vtt_lines.append(str(counter))
        vtt_lines.append(f"{ms_to_vtt_time(start_ms)} --> {ms_to_vtt_time(end_ms)}")
        vtt_lines.append(text)
        vtt_lines.append('')
        counter += 1

    return '\n'.join(vtt_lines)


def _detect_smi_languages(file_path: Path) -> list:
    """SMI 파일에서 사용 가능한 언어 클래스를 감지"""
    try:
        raw = file_path.read_bytes()
        for enc in ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr', 'latin-1']:
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return [('KRCC', 'ko', '한국어')]

        # .KRCC {Name:Korean; lang:ko-KR; ...} 패턴
        classes = re.findall(
            r'\.(\w+)\s*\{[^}]*Name\s*:\s*([^;]*)[^}]*lang\s*:\s*([^;}\s]*)',
            text, re.IGNORECASE
        )
        if classes:
            results = []
            for cls_name, name, lang in classes:
                lang_code = lang.split('-')[0].lower() if lang else ''
                lang_label = name.strip() or LANG_NAMES.get(lang_code, lang_code)
                results.append((cls_name, lang_code, lang_label))
            return results
    except Exception:
        pass
    return [('KRCC', 'ko', '한국어')]


def detect_subtitles(video_path: Path) -> list:
    """동영상 파일과 같은 디렉토리에서 자막 파일 탐지"""
    video_stem = video_path.stem
    video_dir = video_path.parent
    subtitles = []

    if not video_dir.exists():
        return subtitles

    for f in video_dir.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in SUBTITLE_EXTENSIONS:
            continue

        # 동영상 이름으로 시작하는 자막만 (예: movie.srt, movie.ko.srt)
        if not f.stem.lower().startswith(video_stem.lower()):
            continue

        # SMI 파일: 내부 언어 클래스별로 별도 항목 생성
        if f.suffix.lower() == '.smi':
            langs = _detect_smi_languages(f)
            for cls_name, lang_code, lang_label in langs:
                subtitles.append({
                    'path': str(f),
                    'filename': f.name,
                    'format': 'smi',
                    'lang_code': lang_code,
                    'lang_label': lang_label,
                    'smi_class': cls_name,
                })
            continue

        # 일반 자막: 언어 태그 추출 (movie.ko.srt → ko)
        remaining = f.stem[len(video_stem):]
        lang_code = ''
        if remaining.startswith('.') and len(remaining) > 1:
            lang_code = remaining[1:]

        lang_label = LANG_NAMES.get(lang_code, lang_code) if lang_code else '기본'

        subtitles.append({
            'path': str(f),
            'filename': f.name,
            'format': f.suffix.lower().lstrip('.'),
            'lang_code': lang_code,
            'lang_label': lang_label,
        })

    # 정렬: 한국어 우선 → 영어 → 나머지
    priority = {'ko': 0, '': 1, 'en': 2}
    subtitles.sort(key=lambda s: (priority.get(s['lang_code'], 99), s['lang_code']))

    return subtitles


# ============ 자막 API 라우트 함수 ============
# 주의: 이 함수들은 api_nas.py에서 router에 등록됨 (직접 router를 갖지 않음)

async def api_get_subtitles(request, path, load_config, verify_session, get_safe_path):
    """동영상에 연결된 자막 파일 목록 반환"""
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    subtitles = detect_subtitles(safe_path)
    return {"video": str(safe_path), "subtitles": subtitles}


async def api_get_subtitle_file(request, path, smi_class, load_config, verify_session, get_safe_path):
    """자막 파일을 WebVTT 형식으로 반환 (SRT/ASS/SMI 자동 변환)"""
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="자막 파일을 찾을 수 없습니다")

    suffix = safe_path.suffix.lower()
    if suffix not in SUBTITLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="지원하지 않는 자막 형식입니다")

    # 파일 읽기 (바이트를 한 번만 읽고 여러 인코딩 시도 — 디스크 I/O 1회)
    raw_bytes = safe_path.read_bytes()
    content = None
    for encoding in ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr', 'shift_jis', 'latin-1']:
        try:
            content = raw_bytes.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if content is None:
        raise HTTPException(status_code=400, detail="자막 파일 인코딩을 인식할 수 없습니다")

    # VTT 변환
    if suffix == '.vtt':
        vtt_content = content
    elif suffix == '.srt':
        vtt_content = srt_to_vtt(content)
    elif suffix in ('.ass', '.ssa'):
        vtt_content = ass_to_vtt(content)
    elif suffix == '.smi':
        vtt_content = smi_to_vtt(content, lang_class=smi_class)
    else:
        raise HTTPException(status_code=400, detail="변환할 수 없는 형식입니다")

    return Response(
        content=vtt_content,
        media_type="text/vtt; charset=utf-8",
        headers={"Content-Type": "text/vtt; charset=utf-8"},
    )
