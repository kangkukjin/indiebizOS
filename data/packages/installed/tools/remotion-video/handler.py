"""
remotion-video 도구 핸들러
React/TSX 코드를 Remotion으로 렌더링하여 MP4 동영상 생성

에셋(이미지/오디오) → public/ 폴더 복사 → staticFile()로 참조
나레이션 → edge-tts 생성 → ffmpeg로 후처리 믹싱
"""
import os
import json
import uuid
import shutil
import subprocess
import platform
import asyncio
import glob as glob_module
from pathlib import Path

# 패키지 디렉토리
PACKAGE_DIR = Path(__file__).parent

# 영구 Remotion 프로젝트 (node_modules 보관)
REMOTION_PROJECT_DIR = PACKAGE_DIR / "remotion_project"

# npm install 완료 락 파일
INSTALL_LOCK = REMOTION_PROJECT_DIR / ".install_done"

# 임시 렌더 워크스페이스
TEMP_BASE = PACKAGE_DIR / ".render_workspaces"

# 출력 디렉토리
OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "outputs" / "remotion_video"


def get_node_cmd():
    """번들된 Node.js 또는 시스템 Node.js 경로 반환"""
    node_cmd = "node"
    current = Path(__file__).parent
    while current.parent != current:
        if (current / "backend").exists():
            base_path = current
            break
        current = current.parent
    else:
        return node_cmd

    runtime_path = base_path / "runtime"
    if not runtime_path.exists():
        resources_path = base_path.parent / "Resources" / "runtime"
        if resources_path.exists():
            runtime_path = resources_path

    is_windows = platform.system() == "Windows"
    if runtime_path.exists():
        if is_windows:
            bundled_node = runtime_path / "node" / "node.exe"
        else:
            bundled_node = runtime_path / "node" / "bin" / "node"
        if bundled_node.exists():
            node_cmd = str(bundled_node)

    return node_cmd


def get_npx_cmd():
    """npx 경로 반환"""
    node_cmd = get_node_cmd()
    node_dir = Path(node_cmd).parent
    is_windows = platform.system() == "Windows"
    npx_path = node_dir / ("npx.cmd" if is_windows else "npx")
    if npx_path.exists():
        return str(npx_path)
    return "npx"


def get_npm_cmd():
    """npm 경로 반환"""
    node_cmd = get_node_cmd()
    node_dir = Path(node_cmd).parent
    is_windows = platform.system() == "Windows"
    npm_path = node_dir / ("npm.cmd" if is_windows else "npm")
    if npm_path.exists():
        return str(npm_path)
    return "npm"


# ============================================================
# Entry Point
# ============================================================

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    output_base = os.path.join(project_path, "outputs")
    os.makedirs(output_base, exist_ok=True)

    if tool_name == "create_remotion_video":
        return create_remotion_video(tool_input, output_base)
    elif tool_name == "check_remotion_status":
        return check_remotion_status(tool_input)

    return f"알 수 없는 도구: {tool_name}"


# ============================================================
# 환경 설정
# ============================================================

def ensure_remotion_project():
    """영구 Remotion 프로젝트 디렉토리 확보 및 npm install"""
    REMOTION_PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    src_dir = REMOTION_PROJECT_DIR / "src"
    src_dir.mkdir(exist_ok=True)

    # package.json
    package_json = {
        "name": "indiebiz-remotion-renderer",
        "version": "1.0.0",
        "private": True,
        "dependencies": {
            "remotion": "^4.0.0",
            "@remotion/cli": "^4.0.0"
        },
        "devDependencies": {
            "typescript": "^5.5.0",
            "@types/react": "^18.3.0",
            "react": "^18.3.1",
            "react-dom": "^18.3.1"
        }
    }
    _write_json(REMOTION_PROJECT_DIR / "package.json", package_json)

    # tsconfig.json
    tsconfig = {
        "compilerOptions": {
            "target": "ES2022",
            "module": "ES2022",
            "moduleResolution": "bundler",
            "jsx": "react-jsx",
            "strict": False,
            "esModuleInterop": True,
            "skipLibCheck": True,
            "forceConsistentCasingInFileNames": True,
            "outDir": "./dist",
            "rootDir": "./src"
        },
        "include": ["src/**/*"]
    }
    _write_json(REMOTION_PROJECT_DIR / "tsconfig.json", tsconfig)

    # npm install 필요 여부 확인
    node_modules = REMOTION_PROJECT_DIR / "node_modules"
    if node_modules.exists() and INSTALL_LOCK.exists():
        return (True, "Remotion 프로젝트 준비 완료")

    return _run_npm_install()


def _run_npm_install():
    """npm install 실행"""
    npm_cmd = get_npm_cmd()
    try:
        result = subprocess.run(
            [npm_cmd, "install", "--prefer-offline"],
            cwd=str(REMOTION_PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode != 0:
            return (False, f"npm install 실패:\n{result.stderr}")

        INSTALL_LOCK.write_text("installed")
        return (True, "npm install 완료")
    except subprocess.TimeoutExpired:
        return (False, "npm install 시간 초과 (5분)")
    except Exception as e:
        return (False, f"npm install 오류: {str(e)}")


# ============================================================
# 에셋 처리
# ============================================================

def _copy_assets_to_public(asset_paths: list, public_dir: Path) -> dict:
    """
    에셋 파일들을 workspace의 public/ 폴더로 복사.
    Remotion에서 staticFile()로 접근 가능하게 합니다.

    Returns:
        원본 경로 -> 복사된 파일명 매핑
        예: {"/path/to/image.png": "image.png"}
    """
    mapping = {}
    if not asset_paths:
        return mapping

    public_dir.mkdir(parents=True, exist_ok=True)
    used_names = set()

    for asset_path in asset_paths:
        asset_path = str(asset_path).strip()
        if not asset_path:
            continue

        src = Path(asset_path)
        if not src.exists():
            print(f"[에셋 경고] 파일 없음: {asset_path}")
            continue

        # 파일명 중복 방지
        name = src.name
        if name in used_names:
            stem = src.stem
            suffix = src.suffix
            name = f"{stem}_{uuid.uuid4().hex[:4]}{suffix}"
        used_names.add(name)

        dst = public_dir / name
        shutil.copy2(str(src), str(dst))
        mapping[asset_path] = name

    return mapping


def _generate_tts_files(narration_texts: list, voice: str, public_dir: Path) -> list:
    """
    edge-tts로 나레이션 MP3 생성 → public/ 폴더에 저장

    Returns:
        [{"filename": "narration_0.mp3", "duration": 3.5, "text": "..."}, ...]
    """
    results = []
    if not narration_texts:
        return results

    try:
        import edge_tts
    except ImportError:
        print("[나레이션 경고] edge_tts 미설치, 나레이션 생략")
        return results

    public_dir.mkdir(parents=True, exist_ok=True)

    for i, text in enumerate(narration_texts):
        if not text or not text.strip():
            continue

        filename = f"narration_{i}.mp3"
        output_path = public_dir / filename

        try:
            async def _gen():
                communicate = edge_tts.Communicate(text.strip(), voice)
                await communicate.save(str(output_path))

            asyncio.run(_gen())

            # 오디오 길이 측정
            duration = _get_audio_duration(str(output_path))

            results.append({
                "filename": filename,
                "duration": duration,
                "text": text.strip(),
                "index": i
            })
        except Exception as e:
            print(f"[나레이션 오류] {i}번 텍스트: {e}")

    return results


def _get_audio_duration(filepath: str) -> float:
    """ffprobe로 오디오 길이(초) 측정"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception:
        return 3.0  # 기본 3초


def _mix_audio_to_video(video_path: str, narration_files: list, bgm_path: str,
                         public_dir: Path, output_path: str) -> bool:
    """
    ffmpeg로 동영상에 오디오 믹싱 (나레이션 + BGM)

    Returns:
        성공 여부
    """
    has_narration = bool(narration_files)
    has_bgm = bool(bgm_path) and Path(bgm_path).exists()

    if not has_narration and not has_bgm:
        return False

    try:
        # 나레이션 파일들을 하나로 합치기
        narration_merged = None
        if has_narration:
            narration_merged = str(public_dir / "_merged_narration.mp3")
            if len(narration_files) == 1:
                narration_merged = str(public_dir / narration_files[0]["filename"])
            else:
                # ffmpeg concat으로 나레이션 합치기
                concat_list = str(public_dir / "_concat_list.txt")
                with open(concat_list, "w") as f:
                    for nf in narration_files:
                        f.write(f"file '{public_dir / nf['filename']}'\n")
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                     "-i", concat_list, "-c", "copy", narration_merged],
                    capture_output=True, timeout=60
                )

        # 오디오 믹싱
        if narration_merged and has_bgm:
            # 나레이션 + BGM 믹싱
            subprocess.run(
                ["ffmpeg", "-y",
                 "-i", video_path,
                 "-i", narration_merged,
                 "-i", bgm_path,
                 "-filter_complex",
                 "[1:a]volume=1.0[narr];[2:a]volume=0.2[bgm];[narr][bgm]amix=inputs=2:duration=first[aout]",
                 "-map", "0:v", "-map", "[aout]",
                 "-c:v", "copy", "-c:a", "aac", "-shortest",
                 output_path],
                capture_output=True, timeout=120
            )
        elif narration_merged:
            # 나레이션만
            subprocess.run(
                ["ffmpeg", "-y",
                 "-i", video_path,
                 "-i", narration_merged,
                 "-map", "0:v", "-map", "1:a",
                 "-c:v", "copy", "-c:a", "aac", "-shortest",
                 output_path],
                capture_output=True, timeout=120
            )
        elif has_bgm:
            # BGM만
            subprocess.run(
                ["ffmpeg", "-y",
                 "-i", video_path,
                 "-i", bgm_path,
                 "-filter_complex", "[1:a]volume=0.5[bgm]",
                 "-map", "0:v", "-map", "[bgm]",
                 "-c:v", "copy", "-c:a", "aac", "-shortest",
                 output_path],
                capture_output=True, timeout=120
            )

        return Path(output_path).exists()

    except Exception as e:
        print(f"[오디오 믹싱 오류] {e}")
        return False


# ============================================================
# create_remotion_video
# ============================================================

def create_remotion_video(tool_input: dict, output_base: str) -> str:
    composition_code = tool_input.get("composition_code", "")
    duration_in_frames = tool_input.get("duration_in_frames", 150)
    fps = tool_input.get("fps", 30)
    width = tool_input.get("width", 1280)
    height = tool_input.get("height", 720)
    output_filename = tool_input.get("output_filename", "remotion_video.mp4")
    props = tool_input.get("props", {})
    asset_paths = tool_input.get("asset_paths", [])
    narration_texts = tool_input.get("narration_texts", [])
    voice = tool_input.get("voice", "ko-KR-SunHiNeural")
    bgm_path = tool_input.get("bgm_path", "")

    if not composition_code:
        return "오류: composition_code는 필수입니다."

    # 1. 환경 확인
    success, msg = ensure_remotion_project()
    if not success:
        return f"Remotion 환경 설정 실패: {msg}"

    # 2. 임시 워크스페이스 생성
    workspace_id = uuid.uuid4().hex[:8]
    workspace = TEMP_BASE / f"render_{workspace_id}"
    workspace.mkdir(parents=True, exist_ok=True)
    src_dir = workspace / "src"
    src_dir.mkdir(exist_ok=True)
    public_dir = workspace / "public"
    public_dir.mkdir(exist_ok=True)

    log_parts = []

    try:
        # node_modules symlink
        node_modules_link = workspace / "node_modules"
        node_modules_source = REMOTION_PROJECT_DIR / "node_modules"
        os.symlink(str(node_modules_source), str(node_modules_link))

        # 설정 파일 복사
        for fname in ["package.json", "tsconfig.json"]:
            src_file = REMOTION_PROJECT_DIR / fname
            if src_file.exists():
                shutil.copy2(str(src_file), str(workspace / fname))

        # 3. 에셋 파일 복사 → public/
        asset_mapping = _copy_assets_to_public(asset_paths, public_dir)
        if asset_mapping:
            log_parts.append(f"에셋 {len(asset_mapping)}개 로드")

        # 4. 나레이션 TTS 생성 → public/
        narration_files = _generate_tts_files(narration_texts, voice, public_dir)
        if narration_files:
            total_dur = sum(n["duration"] for n in narration_files)
            log_parts.append(f"나레이션 {len(narration_files)}개 생성 ({total_dur:.1f}초)")

            # 나레이션 총 길이에 맞춰 duration_in_frames 자동 조정
            required_frames = int(total_dur * fps) + fps  # +1초 여유
            if required_frames > duration_in_frames:
                duration_in_frames = required_frames
                log_parts.append(f"프레임 수 자동 조정: {duration_in_frames} ({total_dur + 1:.1f}초)")

        # 5. composition_code 작성
        _write_text(src_dir / "Composition.tsx", composition_code)

        # 6. Root.tsx 생성
        root_tsx = _generate_root_tsx(duration_in_frames, fps, width, height, props)
        _write_text(src_dir / "Root.tsx", root_tsx)

        # 7. index.ts 생성
        index_ts = """import {registerRoot} from 'remotion';
import {RemotionRoot} from './Root';
registerRoot(RemotionRoot);
"""
        _write_text(src_dir / "index.ts", index_ts)

        # 8. remotion render 실행
        silent_output = workspace / "output_silent.mp4"
        npx_cmd = get_npx_cmd()

        render_cmd = [
            npx_cmd, "remotion", "render",
            "MainComposition",
            str(silent_output),
        ]
        if props:
            render_cmd.extend(["--props", json.dumps(props, ensure_ascii=False)])

        env = {**os.environ, "NODE_OPTIONS": "--max-old-space-size=4096"}

        result = subprocess.run(
            render_cmd,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=600,
            env=env
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            return f"Remotion 렌더링 실패:\n{error_msg[-2000:]}"

        if not silent_output.exists():
            return f"오류: 렌더링은 완료되었으나 출력 파일이 없습니다.\nstdout: {result.stdout[-1000:]}"

        # 9. 오디오 믹싱 (나레이션/BGM이 있으면)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        final_output = str(OUTPUT_DIR / output_filename)

        audio_mixed = False
        if narration_files or (bgm_path and Path(bgm_path).exists()):
            mixed_output = workspace / "output_with_audio.mp4"
            audio_mixed = _mix_audio_to_video(
                str(silent_output), narration_files, bgm_path,
                public_dir, str(mixed_output)
            )
            if audio_mixed:
                shutil.copy2(str(mixed_output), final_output)
                log_parts.append("오디오 믹싱 완료")
            else:
                shutil.copy2(str(silent_output), final_output)
                log_parts.append("오디오 믹싱 실패, 무음 영상으로 저장")
        else:
            shutil.copy2(str(silent_output), final_output)

        duration_sec = duration_in_frames / fps
        result_msg = f"Remotion 동영상 생성 완료: {os.path.abspath(final_output)}\n"
        result_msg += f"해상도: {width}x{height}, {fps}fps, {duration_sec:.1f}초 ({duration_in_frames}프레임)"
        if log_parts:
            result_msg += "\n" + " | ".join(log_parts)
        if asset_mapping:
            result_msg += "\n\n[에셋 매핑] composition_code에서 staticFile()로 참조:\n"
            for orig, copied in asset_mapping.items():
                result_msg += f"  staticFile(\"{copied}\") ← {orig}\n"

        return result_msg

    except subprocess.TimeoutExpired:
        return "오류: 렌더링 시간 초과 (10분)"
    except Exception as e:
        return f"Remotion 동영상 생성 중 오류: {str(e)}"
    finally:
        # 10. 정리
        try:
            shutil.rmtree(str(workspace))
        except Exception:
            pass


# ============================================================
# Root.tsx 생성
# ============================================================

def _generate_root_tsx(duration_in_frames, fps, width, height, props):
    default_props_line = ""
    if props:
        props_json = json.dumps(props, ensure_ascii=False)
        default_props_line = f"\n        defaultProps={{{props_json}}},"

    return f"""import React from 'react';
import {{Composition}} from 'remotion';
import MyComposition from './Composition';

export const RemotionRoot: React.FC = () => {{
  return (
    <>
      <Composition
        id="MainComposition"
        component={{MyComposition}}
        durationInFrames={{{duration_in_frames}}}
        fps={{{fps}}}
        width={{{width}}}
        height={{{height}}}{default_props_line}
      />
    </>
  );
}};
"""


# ============================================================
# check_remotion_status
# ============================================================

def check_remotion_status(tool_input: dict) -> str:
    action = tool_input.get("action", "status")

    if action == "setup":
        if INSTALL_LOCK.exists():
            INSTALL_LOCK.unlink()
        success, msg = ensure_remotion_project()
        return msg

    # status
    parts = []

    # Node.js
    try:
        node_cmd = get_node_cmd()
        result = subprocess.run(
            [node_cmd, "--version"],
            capture_output=True, text=True, timeout=5
        )
        parts.append(f"Node.js: {result.stdout.strip()} ({node_cmd})")
    except Exception as e:
        parts.append(f"Node.js: 사용 불가 ({e})")

    # npx
    try:
        npx_cmd = get_npx_cmd()
        result = subprocess.run(
            [npx_cmd, "--version"],
            capture_output=True, text=True, timeout=5
        )
        parts.append(f"npx: {result.stdout.strip()}")
    except Exception:
        parts.append("npx: 사용 불가")

    # ffmpeg
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True, timeout=5
        )
        ver_line = result.stdout.split('\n')[0] if result.stdout else "?"
        parts.append(f"ffmpeg: {ver_line}")
    except Exception:
        parts.append("ffmpeg: 사용 불가 (오디오 믹싱 불가)")

    # edge-tts
    try:
        import edge_tts
        parts.append("edge-tts: 사용 가능 (나레이션 지원)")
    except ImportError:
        parts.append("edge-tts: 미설치 (나레이션 불가)")

    # Remotion 설치 상태
    node_modules = REMOTION_PROJECT_DIR / "node_modules"
    if node_modules.exists() and INSTALL_LOCK.exists():
        parts.append("Remotion 패키지: 설치됨")
        remotion_pkg = node_modules / "remotion" / "package.json"
        if remotion_pkg.exists():
            try:
                ver = json.loads(remotion_pkg.read_text()).get("version", "?")
                parts.append(f"Remotion 버전: {ver}")
            except Exception:
                pass
    else:
        parts.append("Remotion 패키지: 미설치 (action='setup'으로 설치하세요)")

    return "\n".join(parts)


# ============================================================
# 유틸리티
# ============================================================

def _write_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def _write_text(path: Path, content: str):
    path.write_text(content, encoding="utf-8")
