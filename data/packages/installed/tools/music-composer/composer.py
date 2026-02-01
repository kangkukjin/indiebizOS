"""
Music Composer - ABC Notation → MIDI → Audio 변환 핵심 로직
"""

import os
import subprocess
import json
import re
import shutil
import urllib.request
import urllib.parse
from datetime import datetime
from html.parser import HTMLParser

# 패키지 내 사운드폰트 경로
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_BUNDLED_SOUNDFONT = os.path.join(_PACKAGE_DIR, "soundfonts", "GeneralUser_GS.sf2")

# GM 악기 맵 (이름 → MIDI Program Number)
GM_INSTRUMENTS = {
    # 피아노 계열 (0-7)
    "piano": 0, "acoustic_grand_piano": 0, "bright_acoustic_piano": 1,
    "electric_grand_piano": 2, "honky_tonk_piano": 3,
    "electric_piano": 4, "electric_piano_1": 4, "electric_piano_2": 5,
    "harpsichord": 6, "clavinet": 7,
    # 크로매틱 퍼커션 (8-15)
    "celesta": 8, "glockenspiel": 9, "music_box": 10,
    "vibraphone": 11, "marimba": 12, "xylophone": 13,
    "tubular_bells": 14, "dulcimer": 15,
    # 오르간 (16-23)
    "organ": 19, "drawbar_organ": 16, "percussive_organ": 17,
    "rock_organ": 18, "church_organ": 19, "reed_organ": 20,
    "accordion": 21, "harmonica": 22, "tango_accordion": 23,
    # 기타 (24-31)
    "guitar": 25, "acoustic_guitar_nylon": 24, "acoustic_guitar_steel": 25,
    "electric_guitar_jazz": 26, "electric_guitar_clean": 27,
    "electric_guitar_muted": 28, "overdriven_guitar": 29,
    "distortion_guitar": 30, "guitar_harmonics": 31,
    # 베이스 (32-39)
    "bass": 33, "acoustic_bass": 32, "electric_bass_finger": 33,
    "electric_bass_pick": 34, "fretless_bass": 35,
    "slap_bass": 36, "slap_bass_1": 36, "slap_bass_2": 37,
    "synth_bass": 38, "synth_bass_1": 38, "synth_bass_2": 39,
    # 현악기 (40-47)
    "violin": 40, "viola": 41, "cello": 42, "contrabass": 43,
    "tremolo_strings": 44, "pizzicato_strings": 45,
    "orchestral_harp": 46, "harp": 46, "timpani": 47,
    # 앙상블 (48-55)
    "strings": 48, "string_ensemble": 48, "string_ensemble_1": 48,
    "string_ensemble_2": 49, "synth_strings": 50, "synth_strings_1": 50,
    "synth_strings_2": 51, "choir": 52, "choir_aahs": 52,
    "voice_oohs": 53, "synth_voice": 54, "orchestra_hit": 55,
    # 관악기 - 금관 (56-63)
    "trumpet": 56, "trombone": 57, "tuba": 58,
    "muted_trumpet": 59, "french_horn": 60, "horn": 60,
    "brass_section": 61, "brass": 61,
    "synth_brass": 62, "synth_brass_1": 62, "synth_brass_2": 63,
    # 관악기 - 목관 (64-71)
    "soprano_sax": 64, "alto_sax": 65, "tenor_sax": 66, "baritone_sax": 67,
    "sax": 66, "saxophone": 66,
    "oboe": 68, "english_horn": 69, "bassoon": 70, "clarinet": 71,
    # 관악기 - 기타 (72-79)
    "piccolo": 72, "flute": 73, "recorder": 74, "pan_flute": 75,
    "blown_bottle": 76, "shakuhachi": 77, "whistle": 78, "ocarina": 79,
    # 신스 리드 (80-87)
    "synth_lead": 80, "square_lead": 80, "sawtooth_lead": 81,
    "calliope": 82, "chiff": 83, "charang": 84,
    # 신스 패드 (88-95)
    "synth_pad": 88, "new_age": 88, "warm_pad": 89,
    "polysynth": 90, "space_voice": 91, "bowed_glass": 92,
    "metallic": 93, "halo": 94, "sweep": 95,
    # 민속 악기 등 (104-111)
    "sitar": 104, "banjo": 105, "shamisen": 106, "koto": 107,
    "kalimba": 108, "bagpipe": 109, "fiddle": 110, "shanai": 111,
    # 타악기 (112-119)
    "tinkle_bell": 112, "agogo": 113, "steel_drums": 114,
    "woodblock": 115, "taiko_drum": 116, "melodic_tom": 117,
    "synth_drum": 118, "reverse_cymbal": 119,
}


def _resolve_instrument(name):
    """악기 이름을 GM Program Number로 변환"""
    if name is None:
        return 0  # 기본 피아노
    if isinstance(name, int):
        return max(0, min(127, name))

    key = name.lower().strip().replace(' ', '_').replace('-', '_')
    if key in GM_INSTRUMENTS:
        return GM_INSTRUMENTS[key]

    # 부분 매칭
    for gm_name, prog in GM_INSTRUMENTS.items():
        if key in gm_name or gm_name in key:
            return prog

    return 0  # 매칭 실패 시 피아노


def _find_soundfont():
    """사운드폰트 파일을 찾는다. 패키지 내장 → 시스템 순서로 탐색."""
    # 1순위: 패키지에 포함된 GM 사운드폰트
    if os.path.exists(_BUNDLED_SOUNDFONT):
        return _BUNDLED_SOUNDFONT

    # 2순위: 시스템 경로 탐색
    search_paths = [
        "/opt/homebrew/share/soundfonts",
        "/opt/homebrew/Cellar/fluid-synth",
        "/usr/local/share/soundfonts",
        "/usr/share/sounds/sf2",
        "/usr/share/soundfonts",
    ]

    for base in search_paths:
        if not os.path.exists(base):
            continue
        for root, dirs, files in os.walk(base):
            for f in files:
                if f.endswith(('.sf2', '.sf3')) and not f.startswith('.'):
                    path = os.path.join(root, f)
                    try:
                        path.encode('utf-8')
                        if os.path.getsize(path) > 10000:
                            return path
                    except (UnicodeEncodeError, OSError):
                        continue
    return None


def _sanitize_filename(name):
    """파일명에 사용 불가능한 문자 제거"""
    name = re.sub(r'[^\w\s가-힣-]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name[:50] if name else "untitled"


def _ensure_output_dir(project_path):
    """출력 디렉토리 확보"""
    if project_path:
        output_dir = os.path.join(project_path, "outputs", "music")
    else:
        output_dir = os.path.expanduser("~/Desktop/music_output")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _extract_abc_metadata(abc_text):
    """ABC Notation에서 메타데이터 추출"""
    metadata = {}
    field_map = {
        'T': 'title', 'C': 'composer', 'M': 'meter',
        'L': 'default_length', 'Q': 'tempo', 'K': 'key',
        'R': 'rhythm', 'Z': 'transcription',
    }
    for line in abc_text.strip().split('\n'):
        match = re.match(r'^([A-Z]):\s*(.+)$', line.strip())
        if match:
            field, value = match.group(1), match.group(2).strip()
            if field in field_map:
                metadata[field_map[field]] = value
    return metadata


def _get_score_info(score):
    """music21 Score 객체에서 곡 정보 추출"""
    info = {}
    try:
        # 총 길이 (초)
        import math
        secs = score.seconds if hasattr(score, 'seconds') else None
        if secs is not None and not math.isnan(secs):
            info['duration_seconds'] = round(secs, 1)
        else:
            # quarterLength 기반 추정
            ql = score.duration.quarterLength
            # 기본 BPM 120 가정
            info['duration_seconds'] = round(ql / 2.0, 1) if ql else None
        # 마디 수
        measures = score.recurse().getElementsByClass('Measure')
        info['measure_count'] = len(measures)
        # 파트(악기) 수
        parts = score.parts
        info['part_count'] = len(parts)
        # 각 파트의 악기 정보
        instruments = []
        for part in parts:
            inst = part.getInstrument()
            if inst:
                instruments.append(inst.instrumentName or "Unknown")
        info['instruments'] = instruments if instruments else ["Piano"]
        # 음표 수
        notes = score.recurse().notes
        info['note_count'] = len(notes)
    except Exception:
        pass
    return info


def _fix_midi_channels(midi_path, num_parts, instruments=None,
                       volumes=None, panning=None, reverb=60, chorus=30):
    """MIDI 파일의 각 트랙에 개별 채널, 악기, 믹싱 설정 적용

    Args:
        midi_path: MIDI 파일 경로
        num_parts: 파트(보이스) 수
        instruments: 파트별 악기 리스트 (예: ["piano", "violin", "bass"])
        volumes: 파트별 볼륨 리스트 (0-127). None이면 자동 밸런스
        panning: 파트별 패닝 리스트 (0=좌, 64=중앙, 127=우). None이면 자동 분배
        reverb: 리버브 깊이 (0-127, 기본 60)
        chorus: 코러스 깊이 (0-127, 기본 30)
    """
    try:
        import mido
    except ImportError:
        return

    try:
        mid = mido.MidiFile(midi_path)

        # 음표가 있는 트랙 찾기
        note_tracks = []
        for i, track in enumerate(mid.tracks):
            has_notes = any(msg.type == 'note_on' for msg in track)
            if has_notes:
                note_tracks.append(i)

        if not note_tracks:
            return

        n = len(note_tracks)

        # 악기 리스트 정규화
        if instruments:
            inst_programs = [_resolve_instrument(inst) for inst in instruments]
            while len(inst_programs) < n:
                inst_programs.append(inst_programs[-1] if inst_programs else 0)
        else:
            inst_programs = [0] * n

        # 패닝: 사용자 지정 또는 자동 분배
        if panning:
            pan_values = [max(0, min(127, v)) for v in panning]
            while len(pan_values) < n:
                pan_values.append(64)
        else:
            pan_values = []
            for i in range(n):
                if n == 1:
                    pan_values.append(64)
                else:
                    pan_values.append(32 + int(64 * i / (n - 1)))

        # 볼륨: 사용자 지정 또는 자동 밸런스
        if volumes:
            vol_values = [max(0, min(127, v)) for v in volumes]
            while len(vol_values) < n:
                vol_values.append(80)
        else:
            vol_values = []
            for idx in range(n):
                if n == 1:
                    vol_values.append(100)
                elif idx == 0:
                    vol_values.append(110)   # 멜로디 강조
                elif idx == n - 1:
                    vol_values.append(80)    # 베이스
                else:
                    vol_values.append(70)    # 내성부

        # 리버브/코러스 범위 제한
        reverb_depth = max(0, min(127, int(reverb)))
        chorus_depth = max(0, min(127, int(chorus)))

        # 각 트랙에 채널, 악기, 믹싱 적용
        for idx, track_idx in enumerate(note_tracks):
            track = mid.tracks[track_idx]

            # 채널 배정 (ch 9는 드럼 전용이므로 건너뜀)
            new_channel = idx
            if new_channel >= 9:
                new_channel += 1
            if new_channel > 15:
                new_channel = idx % 9

            header = [
                mido.Message('program_change', channel=new_channel,
                             program=inst_programs[idx], time=0),
                mido.Message('control_change', channel=new_channel,
                             control=10, value=pan_values[idx], time=0),
                mido.Message('control_change', channel=new_channel,
                             control=7, value=vol_values[idx], time=0),
                mido.Message('control_change', channel=new_channel,
                             control=91, value=reverb_depth, time=0),
                mido.Message('control_change', channel=new_channel,
                             control=93, value=chorus_depth, time=0),
            ]

            new_track = header[:]
            for msg in track:
                if hasattr(msg, 'channel'):
                    msg = msg.copy(channel=new_channel)
                new_track.append(msg)

            mid.tracks[track_idx] = mido.MidiTrack(new_track)

        mid.save(midi_path)
    except Exception:
        pass


def _preprocess_abc(abc_text):
    """ABC Notation 전처리: LLM이 생성한 ABC의 흔한 문제를 수정"""
    lines = abc_text.strip().split('\n')
    fixed = []
    for line in lines:
        stripped = line.strip()
        # 헤더 필드(X:, T:, M: 등)는 그대로 유지
        if re.match(r'^[A-Za-z]:', stripped):
            fixed.append(stripped)
            continue
        # V: 파트 선언도 그대로
        if stripped.startswith('V:'):
            fixed.append(stripped)
            continue
        # 빈 줄 유지
        if not stripped:
            fixed.append('')
            continue
        # 음표 라인: 끝에 마디선이 없으면 추가
        # (마디선 |, 겹세로줄 ||, 종지선 |], 도돌이표 :| 로 끝나지 않는 경우)
        if stripped and not re.search(r'[|\]:]$', stripped):
            stripped += ' |'
        fixed.append(stripped)
    return '\n'.join(fixed)


def abc_to_midi(args: dict, project_path: str = None) -> str:
    """ABC Notation → MIDI 변환"""
    abc_text = args.get("abc_notation", "")
    filename = args.get("filename", "")
    instruments = args.get("instruments", None)
    volumes = args.get("volumes", None)
    panning = args.get("panning", None)
    reverb = args.get("reverb", 60)
    chorus = args.get("chorus", 30)

    if not abc_text.strip():
        return json.dumps({"error": "abc_notation이 비어있습니다."})

    try:
        from music21 import converter
    except ImportError:
        return json.dumps({"error": "music21이 설치되지 않았습니다. pip3 install music21"})

    # ABC 전처리 (LLM 생성 ABC의 흔한 문제 수정)
    abc_text = _preprocess_abc(abc_text)

    # ABC 메타데이터 추출
    metadata = _extract_abc_metadata(abc_text)

    # 파일명 결정
    if not filename:
        filename = _sanitize_filename(metadata.get('title', '')) or "composition"
    else:
        filename = _sanitize_filename(filename)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename}_{timestamp}"

    output_dir = _ensure_output_dir(project_path)
    midi_path = os.path.join(output_dir, f"{filename}.mid")

    try:
        score = converter.parse(abc_text, format='abc')

        # MIDI 쓰기 (도돌이표 처리 포함)
        try:
            score.write('midi', fp=midi_path)
        except Exception as repeat_err:
            if 'repeat' in str(repeat_err).lower() or 'measure' in str(repeat_err).lower():
                # 도돌이표 관련 에러 → makeMeasures + expandRepeats 시도
                try:
                    score.makeMeasures(inPlace=True)
                    score.write('midi', fp=midi_path)
                except Exception:
                    # 그래도 실패 → 도돌이표 제거 후 재시도
                    abc_no_repeat = abc_text.replace('|:', '|').replace(':|', '|')
                    score = converter.parse(abc_no_repeat, format='abc')
                    score.write('midi', fp=midi_path)
            else:
                raise

        # MIDI 후처리: 채널 분리 + 악기 배정 + 믹싱
        num_parts = len(score.parts)
        _fix_midi_channels(midi_path, num_parts, instruments,
                           volumes, panning, reverb, chorus)

        # 곡 정보 추출
        score_info = _get_score_info(score)

        result = {
            "success": True,
            "midi_path": midi_path,
            "metadata": metadata,
            "score_info": score_info,
            "message": f"MIDI 파일 생성 완료: {midi_path}"
        }

        # 요약 추가
        parts = []
        if metadata.get('title'):
            parts.append(f"제목: {metadata['title']}")
        if metadata.get('key'):
            parts.append(f"조성: {metadata['key']}")
        if metadata.get('meter'):
            parts.append(f"박자: {metadata['meter']}")
        if metadata.get('tempo'):
            parts.append(f"템포: {metadata['tempo']}")
        if score_info.get('duration_seconds'):
            parts.append(f"길이: {score_info['duration_seconds']}초")
        if score_info.get('note_count'):
            parts.append(f"음표: {score_info['note_count']}개")
        if parts:
            result["summary"] = " | ".join(parts)

        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"ABC → MIDI 변환 실패: {str(e)}"})


EQ_PRESETS = {
    "balanced": (
        "bass=g=4:f=120:w=0.6,"
        "treble=g=3:f=5000:w=0.5,"
        "equalizer=f=800:t=q:w=1.5:g=-2,"
        "acompressor=threshold=-15dB:ratio=2.5:attack=10:release=100:makeup=1.5,"
        "alimiter=limit=0.95"
    ),
    "warm": (
        "bass=g=5:f=100:w=0.7,"
        "treble=g=-1:f=6000:w=0.5,"
        "equalizer=f=400:t=q:w=1.0:g=2,"
        "acompressor=threshold=-18dB:ratio=2:attack=15:release=150:makeup=1,"
        "alimiter=limit=0.95"
    ),
    "bright": (
        "bass=g=1:f=100:w=0.5,"
        "treble=g=5:f=4000:w=0.6,"
        "equalizer=f=2500:t=q:w=1.5:g=3,"
        "acompressor=threshold=-15dB:ratio=2.5:attack=8:release=80:makeup=1.5,"
        "alimiter=limit=0.95"
    ),
    "powerful": (
        "bass=g=6:f=80:w=0.7,"
        "treble=g=4:f=5000:w=0.5,"
        "equalizer=f=800:t=q:w=1.5:g=-3,"
        "equalizer=f=3000:t=q:w=1.0:g=2,"
        "acompressor=threshold=-12dB:ratio=3:attack=5:release=60:makeup=2,"
        "alimiter=limit=0.95"
    ),
}


def midi_to_audio(args: dict, project_path: str = None) -> str:
    """MIDI → WAV/MP3 변환"""
    midi_path = args.get("midi_path", "")
    audio_format = args.get("format", "wav").lower()
    gain = args.get("gain", 0.5)
    eq_preset = args.get("eq_preset", "balanced").lower()

    if not midi_path or not os.path.exists(midi_path):
        return json.dumps({"error": f"MIDI 파일을 찾을 수 없습니다: {midi_path}"})

    # FluidSynth 확인
    fluidsynth_path = shutil.which("fluidsynth")
    if not fluidsynth_path:
        return json.dumps({"error": "FluidSynth가 설치되지 않았습니다. brew install fluid-synth"})

    # 사운드폰트 찾기
    soundfont = _find_soundfont()
    if not soundfont:
        return json.dumps({"error": "사운드폰트(.sf2) 파일을 찾을 수 없습니다."})

    # gain 범위 제한
    gain = max(0.1, min(5.0, float(gain)))

    # 출력 경로
    base_name = os.path.splitext(midi_path)[0]
    wav_path = f"{base_name}.wav"

    try:
        # FluidSynth로 MIDI → WAV
        # -R 1: 리버브 ON, -C 1: 코러스 ON (공간감 + 풍성함)
        result = subprocess.run(
            [
                fluidsynth_path, '-ni',
                '-F', wav_path,
                '-r', '44100',
                '-g', str(gain),
                '-R', '1',
                '-C', '1',
                soundfont, midi_path
            ],
            capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            return json.dumps({"error": f"FluidSynth 변환 실패: {result.stderr}"})

        if not os.path.exists(wav_path):
            return json.dumps({"error": "WAV 파일이 생성되지 않았습니다."})

        # ffmpeg EQ 후처리 (프리셋 기반)
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path and eq_preset != "flat":
            eq_filter = EQ_PRESETS.get(eq_preset, EQ_PRESETS["balanced"])
            eq_path = f"{base_name}_eq.wav"
            eq_result = subprocess.run(
                [ffmpeg_path, '-i', wav_path, '-af', eq_filter, '-y', eq_path],
                capture_output=True, text=True, timeout=60
            )
            if eq_result.returncode == 0 and os.path.exists(eq_path):
                os.replace(eq_path, wav_path)
            else:
                if os.path.exists(eq_path):
                    os.remove(eq_path)

        final_path = wav_path
        file_size = os.path.getsize(wav_path)

        # MP3 변환 필요 시
        if audio_format == "mp3":
            if not ffmpeg_path:
                return json.dumps({
                    "success": True,
                    "audio_path": wav_path,
                    "format": "wav",
                    "file_size_kb": round(file_size / 1024, 1),
                    "message": "ffmpeg가 없어 WAV로 생성했습니다."
                })

            mp3_path = f"{base_name}.mp3"
            mp3_result = subprocess.run(
                [ffmpeg_path, '-i', wav_path, '-b:a', '192k', '-y', mp3_path],
                capture_output=True, text=True, timeout=60
            )

            if mp3_result.returncode == 0 and os.path.exists(mp3_path):
                os.remove(wav_path)
                final_path = mp3_path
                file_size = os.path.getsize(mp3_path)

        return json.dumps({
            "success": True,
            "audio_path": final_path,
            "format": os.path.splitext(final_path)[1][1:],
            "file_size_kb": round(file_size / 1024, 1),
            "soundfont": os.path.basename(soundfont),
            "message": f"오디오 파일 생성 완료: {final_path}"
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "오디오 변환 시간 초과 (120초)"})
    except Exception as e:
        return json.dumps({"error": f"오디오 변환 실패: {str(e)}"})


def compose_and_export(args: dict, project_path: str = None) -> str:
    """ABC → MIDI → Audio 원스톱 파이프라인"""
    abc_text = args.get("abc_notation", "")
    title = args.get("title", "")
    audio_format = args.get("format", "wav")
    instruments = args.get("instruments", None)
    # 믹싱 파라미터
    volumes = args.get("volumes", None)
    panning = args.get("panning", None)
    reverb = args.get("reverb", 60)
    chorus = args.get("chorus", 30)
    eq_preset = args.get("eq_preset", "balanced")

    if not abc_text.strip():
        return json.dumps({"error": "abc_notation이 비어있습니다."})

    # 파일명 결정
    if title:
        filename = _sanitize_filename(title)
    else:
        title_match = re.search(r'^T:\s*(.+)$', abc_text, re.MULTILINE)
        filename = _sanitize_filename(title_match.group(1)) if title_match else "composition"

    # Step 1: ABC → MIDI (믹싱 파라미터 전달)
    midi_args = {"abc_notation": abc_text, "filename": filename}
    if instruments:
        midi_args["instruments"] = instruments
    if volumes:
        midi_args["volumes"] = volumes
    if panning:
        midi_args["panning"] = panning
    midi_args["reverb"] = reverb
    midi_args["chorus"] = chorus
    midi_result = abc_to_midi(midi_args, project_path)
    midi_data = json.loads(midi_result)

    if not midi_data.get("success"):
        return midi_result

    midi_path = midi_data["midi_path"]

    # Step 2: MIDI → Audio (EQ 프리셋 전달)
    audio_result = midi_to_audio(
        {"midi_path": midi_path, "format": audio_format, "eq_preset": eq_preset},
        project_path
    )
    audio_data = json.loads(audio_result)

    # 결과 조합
    result = {
        "success": True,
        "midi_path": midi_path,
    }

    # 메타데이터 전달
    if midi_data.get("metadata"):
        result["metadata"] = midi_data["metadata"]
    if midi_data.get("score_info"):
        result["score_info"] = midi_data["score_info"]
    if midi_data.get("summary"):
        result["summary"] = midi_data["summary"]

    if audio_data.get("success"):
        result["audio_path"] = audio_data["audio_path"]
        result["format"] = audio_data.get("format", audio_format)
        result["file_size_kb"] = audio_data.get("file_size_kb")
        result["soundfont"] = audio_data.get("soundfont")
        result["message"] = f"작곡 완료!\n- MIDI: {midi_path}\n- 오디오: {audio_data['audio_path']}"
    else:
        result["audio_error"] = audio_data.get("error", "오디오 변환 실패")
        result["message"] = f"MIDI 생성 완료 (오디오 변환 실패)\n- MIDI: {midi_path}\n- 오류: {result['audio_error']}"

    return json.dumps(result)


# ============================================================
# ABC Tune 검색/가져오기 (abcnotation.com 스크래핑)
# ============================================================

_ABC_BASE_URL = "https://abcnotation.com"


def _parse_search_results(html):
    """abcnotation.com 검색 결과 HTML을 파싱하여 결과 목록과 총 건수를 반환"""
    results = []

    # 결과 항목 파싱: <h3><small>N.</small> Title</h3> ... <a href="/tunePage?a=ID">tune page</a>
    pattern = (
        r'<h3>\s*<small>\d+\.</small>\s*\n?(.*?)\n?\s*</h3>'
        r'.*?<a[^>]*href="(/tunePage\?a=([^"]+))"[^>]*>tune page</a>'
    )
    for m in re.finditer(pattern, html, re.DOTALL):
        title = m.group(1).strip()
        tune_id = m.group(3)
        # source: tune_id의 도메인 부분
        source = tune_id.split("/")[0] if "/" in tune_id else ""
        results.append({
            "title": title,
            "tune_id": tune_id,
            "source": source,
            "url": f"{_ABC_BASE_URL}/tunePage?a={tune_id}",
        })

    # 전체 결과 수: meta description에서 "results 1 - N of P" 추출
    total = 0
    meta_match = re.search(r'results\s+1\s*-\s*(\d[\d,]*)\s+of\s+\d+', html)
    if meta_match:
        total = int(meta_match.group(1).replace(",", ""))
    else:
        # 대안: 마지막 페이지 링크에서 추정
        page_offsets = re.findall(r'/searchTunes\?[^"]*s=(\d+)', html)
        if page_offsets:
            max_offset = max(int(x) for x in page_offsets)
            total = max_offset + 10

    return results, total


class _TunePageParser(HTMLParser):
    """abcnotation.com 곡 페이지에서 ABC Notation 추출"""

    def __init__(self):
        super().__init__()
        self.abc_text = ""
        self._in_textarea = False
        self._in_pre = False
        # 제목
        self.page_title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "textarea":
            self._in_textarea = True
        elif tag == "pre":
            self._in_pre = True
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "textarea":
            self._in_textarea = False
        elif tag == "pre":
            self._in_pre = False
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_textarea:
            self.abc_text += data
        if self._in_title:
            self.page_title += data
        # <pre> 안의 X: 로 시작하는 ABC도 캡처
        if self._in_pre and not self.abc_text:
            if re.match(r'\s*X:\s*\d', data):
                self.abc_text = data


def _fetch_url(url, timeout=15, retries=2):
    """URL에서 HTML을 가져온다. 실패 시 재시도."""
    import time
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    last_err = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, errors="replace")
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(1)
    raise last_err


def search_abc_tunes(args: dict, project_path: str = None) -> str:
    """abcnotation.com에서 ABC 악보 검색

    Args (in args dict):
        query: 검색어 (곡명, 작곡가 등)
        page: 페이지 번호 (0부터 시작, 기본 0)

    Returns:
        JSON: {results: [{title, tune_id, source, url}], total, page, has_more}
    """
    query = args.get("query", "").strip()
    page = int(args.get("page", 0))

    if not query:
        return json.dumps({"error": "검색어(query)를 입력해주세요."})

    offset = page * 10
    search_url = (
        f"{_ABC_BASE_URL}/searchTunes"
        f"?q={urllib.parse.quote(query)}&f=c&o=a&s={offset}"
    )

    try:
        html = _fetch_url(search_url)
    except Exception as e:
        return json.dumps({
            "error": f"검색 요청 실패: {str(e)}",
            "url": search_url,
            "hint": "영문 곡명/작곡가로 검색하세요. 예: bach cello suite, amazing grace"
        })

    results, total = _parse_search_results(html)
    results = results[:10]

    return json.dumps({
        "success": True,
        "results": results,
        "total": total,
        "page": page,
        "has_more": (offset + 10) < total,
        "message": f"'{query}' 검색 결과: {len(results)}건 표시 (전체 {total}건, 페이지 {page + 1})"
    })


def get_abc_tune(args: dict, project_path: str = None) -> str:
    """abcnotation.com에서 특정 곡의 ABC Notation을 가져옴

    Args (in args dict):
        tune_id: 곡 ID (search_abc_tunes 결과의 tune_id)

    Returns:
        JSON: {abc_notation, title, source_url}
    """
    tune_id = args.get("tune_id", "").strip()

    if not tune_id:
        return json.dumps({"error": "tune_id를 입력해주세요. search_abc_tunes로 검색 후 사용하세요."})

    tune_url = f"{_ABC_BASE_URL}/tunePage?a={urllib.parse.quote(tune_id)}"

    try:
        html = _fetch_url(tune_url)
    except Exception as e:
        return json.dumps({"error": f"곡 페이지 요청 실패: {str(e)}"})

    # 방법 1: textarea에서 ABC 추출
    parser = _TunePageParser()
    parser.feed(html)
    abc_text = parser.abc_text.strip()

    # 방법 2: 정규식으로 ABC 블록 찾기
    if not abc_text:
        abc_match = re.search(
            r'(X:\s*\d+.*?)(?=<(?:script|div|table|/pre|/textarea))',
            html, re.DOTALL
        )
        if abc_match:
            abc_text = abc_match.group(1).strip()
            abc_text = re.sub(r'<[^>]+>', '', abc_text)
            abc_text = abc_text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')

    if not abc_text:
        return json.dumps({
            "error": "ABC Notation을 추출할 수 없습니다.",
            "url": tune_url,
            "hint": "이 곡은 ABC 형식이 아닐 수 있습니다."
        })

    metadata = _extract_abc_metadata(abc_text)

    return json.dumps({
        "success": True,
        "abc_notation": abc_text,
        "title": metadata.get("title", parser.page_title or "Unknown"),
        "metadata": metadata,
        "source_url": tune_url,
        "message": f"ABC 악보 가져오기 완료: {metadata.get('title', 'Unknown')}"
    })
