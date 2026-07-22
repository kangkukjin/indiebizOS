import os
import uuid
import json
import asyncio
import base64
# ★무거운 미디어 의존성(edge_tts·moviepy)은 모듈레벨에서 import하지 않는다 — 폰엔 이 라이브러리가
# 없어 모듈 전체 import가 실패하고, 그러면 같은 파일의 *순수* 연산(image_critic·image_gemini =
# 문자열/HTTP뿐)까지 mac에 갇혔다. 무거운 건 쓰는 함수 안에서 지연 import.
# (table:document/structure 문서 emitter는 2026-07-03 표준 패키지 data-ops로 이관 — 표준 코어
#  어휘가 개인 패키지에 살던 경계 이상 해소. 이 패키지는 순수 미디어 생성(engines)만 남음.)
# (moviepy는 이미 각 함수가 로컬 re-import 중이라 모듈레벨 심볼은 0회 사용 — 그냥 제거. edge_tts는 generate_tts로.)

# Helper functions
def get_image_base64(image_path):
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            ext = os.path.splitext(image_path)[1].lower()
            mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/jpeg"
            return f"data:{mime};base64,{encoded_string}"
    except Exception as e:
        print(f"Base64 인코딩 실패: {e}")
        return None


def execute(tool_input: dict, context) -> str:
    """도구 실행 함수 (ToolContext 기반 신규 시그니처).

    context는 tool_context.ToolContext. tool_name 분기와 출력 경로 결정에 사용.
    output_dir()은 항상 절대경로 + mkdir 자동.
    """
    tool_name = context.tool_name
    output_base = context.output_dir()

    # 통합 액션: tool_name=="html_video" + scene_dir 유무로 분기
    if tool_name == "html_video":
        if tool_input.get("scene_dir"):
            return render_html_video(tool_input, output_base)
        return create_html_video(tool_input, output_base)

    if tool_name == "render_html_to_image":
        return render_html_to_image(tool_input, output_base)
    elif tool_name == "generate_gemini_image":
        return generate_gemini_image(tool_input, output_base)
    elif tool_name == "generate_icon":
        return generate_icon(tool_input, output_base)
    elif tool_name == "critique_gemini_image":
        return critique_gemini_image(tool_input, output_base)
    elif tool_name == "read_gemini_image":
        return read_gemini_image(tool_input, output_base)
    elif tool_name == "create_tts":
        return create_tts(tool_input, output_base)
    elif tool_name == "create_shadcn_slides":
        # shadcn 스타일 슬라이드 생성 (별도 모듈)
        import importlib.util
        import sys
        module_path = os.path.join(os.path.dirname(__file__), "shadcn_slides.py")
        spec = importlib.util.spec_from_file_location("shadcn_slides", module_path)
        shadcn_slides = importlib.util.module_from_spec(spec)
        sys.modules["shadcn_slides"] = shadcn_slides
        spec.loader.exec_module(shadcn_slides)
        return shadcn_slides.create_shadcn_slides(tool_input, output_base)
    elif tool_name == "create_slide":
        # [engines:slide] 저작 기층 — 명령 → 슬라이드 1장 (별도 모듈, 호출마다 재로드)
        import importlib.util
        import sys
        module_path = os.path.join(os.path.dirname(__file__), "slide_author.py")
        spec = importlib.util.spec_from_file_location("slide_author", module_path)
        slide_author = importlib.util.module_from_spec(spec)
        sys.modules["slide_author"] = slide_author
        spec.loader.exec_module(slide_author)
        return slide_author.create_slide(tool_input, output_base)
    # (2026-06-04 은퇴) create_lecture_plan/write/illustrate/compose 4단계 파이프라인 제거.
    # 강의 = AI가 lecture_slide_principles.md 가이드로 계획 → [engines:slide] × N(같은 style, & 병렬).
    # 계획은 인지(가이드+추론)지 액션 아님 (ibl_design_philosophy Mode C).

    return f"알 수 없는 도구: {tool_name}"

def _normalize_tts_text(text):
    """TTS 낭독 품질용 보수적 텍스트 정규화.

    모델(edge-tts=Azure 뉴럴)의 원본 음질은 이미 좋다 — 화자를 헷갈리게 하는
    *서식 잡음*만 걷어낸다. 한국어 본문·숫자·퍼센트·문장 구조는 건드리지 않는다
    (edge-tts 가 이미 자연스럽게 읽으므로 손대면 오히려 위험).

    제거 대상: 마크다운 링크/강조/코드 기호, 줄머리 목록·헤더 기호, 날 URL,
    잉여 공백. 영어 약어·티커의 한글 음차는 대본 작성자(가이드 규칙)의 몫 —
    여기서 결정적으로 바꾸면 문맥 오독 위험이 크다.
    """
    if not text:
        return text
    import re
    t = text
    t = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', t)   # [텍스트](url) → 텍스트
    t = re.sub(r'https?://\S+', ' ', t)               # 날 URL 제거 (읽으면 재앙)
    t = re.sub(r'(?m)^\s*[-*•·▪◦>#]+\s*', '', t)      # 줄머리 목록/헤더 기호
    t = re.sub(r'[*_`]{1,3}', '', t)                  # 강조/코드 기호(별표·언더스코어·백틱)
    t = re.sub(r'[ \t]+', ' ', t)                     # 가로 공백 정리
    t = re.sub(r'\n{2,}', '\n', t)                    # 빈 줄 축소
    return t.strip()


async def generate_tts(text, output_path, voice="ko-KR-SunHiNeural", rate="+0%", pitch="+0Hz"):
    import edge_tts  # 지연 import — 폰엔 없음(tts는 mac_only라 폰선 호출 안 됨)
    text = _normalize_tts_text(text)  # 서식 잡음 제거 — 모든 tts 호출(브리핑·영상 나레이션) 공통
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)

def _prepare_scene_html(html, base_path, video_width, video_height):
    """씬 HTML을 렌더링 가능하도록 전처리 (이미지 Base64 변환, 뷰포트 설정)"""
    import re

    # 항상 이미지 경로를 Base64로 변환 (절대 경로 포함)
    resolved_base = os.path.abspath(base_path) if base_path else None

    def replace_img_src(match):
        src = match.group(1)
        if src.startswith(('data:', 'http://', 'https://')):
            return match.group(0)
        # file:// 프로토콜 처리
        if src.startswith('file://'):
            src = src[7:]  # file:// 제거
        # 절대 경로이면 바로 사용, 상대 경로이면 base_path 기준
        if os.path.isabs(src):
            abs_path = src
        elif resolved_base:
            abs_path = os.path.join(resolved_base, src)
        else:
            return match.group(0)  # base_path도 없고 상대 경로면 스킵
        base64_data = get_image_base64(abs_path)
        if base64_data:
            return f'src="{base64_data}"'
        return match.group(0)

    html = re.sub(r'src=["\']([^"\']+)["\']', replace_img_src, html)

    def replace_bg_url(match):
        url = match.group(1)
        if url.startswith(('data:', 'http://', 'https://')):
            return match.group(0)
        if url.startswith('file://'):
            url = url[7:]
        if os.path.isabs(url):
            abs_path = url
        elif resolved_base:
            abs_path = os.path.join(resolved_base, url)
        else:
            return match.group(0)
        base64_data = get_image_base64(abs_path)
        if base64_data:
            return f'url("{base64_data}")'
        return match.group(0)

    html = re.sub(r'url\(["\']?([^"\')\s]+)["\']?\)', replace_bg_url, html)

    # 한글 폰트 보장을 위한 CSS (Google Fonts 로드 실패 시에도 시스템 폰트 fallback)
    korean_font_css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700;900&display=swap');
* { font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', '맑은 고딕', sans-serif !important; }
</style>"""

    # 이미 완전한 HTML 문서인 경우 한글 폰트 CSS만 주입
    if html.strip().lower().startswith("<!doctype") or html.strip().lower().startswith("<html"):
        # </head> 앞에 폰트 CSS 삽입
        if '</head>' in html:
            html = html.replace('</head>', korean_font_css + '\n</head>', 1)
        elif '<body' in html:
            html = html.replace('<body', korean_font_css + '\n<body', 1)
        return html

    # 그렇지 않으면 래핑 (Google Fonts + Lottie CDN 포함)
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<script src="https://cdn.tailwindcss.com"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Black+Han+Sans&family=Do+Hyeon&family=Gothic+A1:wght@400;700;900&family=Noto+Sans+KR:wght@300;400;500;700;900&family=Sunflower:wght@300;500;700&family=Jua&family=Inter:wght@300;400;500;600;700;800;900&family=Montserrat:wght@400;600;700;800;900&family=Playfair+Display:wght@400;600;700;900&family=Poppins:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css"/>
<script src="https://unpkg.com/lucide@latest"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
<script src="https://unpkg.com/@lottiefiles/lottie-player@2/dist/lottie-player.js"></script>
<style>body,html{{margin:0;padding:0;width:{video_width}px;height:{video_height}px;overflow:hidden;font-family:'Noto Sans KR',sans-serif;}}</style>
</head><body>{html}</body></html>"""


def _auto_split_scenes(scenes, narration_texts, default_duration):
    """단일 HTML에 여러 씬이 들어있는 경우 자동 분리.

    AI 에이전트가 모든 씬을 하나의 HTML에 <div id="scene1">, <div id="scene2">... 형태로
    넣는 경우를 감지하여 각 씬을 독립 HTML 문서로 분리합니다.
    """
    import re
    from bs4 import BeautifulSoup

    if len(scenes) != 1:
        return scenes, narration_texts

    html = scenes[0].get("html", "")
    duration = scenes[0].get("duration", default_duration)
    base_path = scenes[0].get("base_path")

    # scene/씬 패턴의 id를 가진 div 요소가 2개 이상인지 확인
    scene_id_pattern = re.compile(r'id=["\'](?:scene|씬)\s*(\d+)["\']', re.IGNORECASE)
    scene_matches = scene_id_pattern.findall(html)

    if len(scene_matches) < 2:
        return scenes, narration_texts

    print(f"[create_html_video] 단일 HTML에 {len(scene_matches)}개의 씬 감지 → 자동 분리")

    try:
        soup = BeautifulSoup(html, 'html.parser')

        # <head> 내용 추출 (공통 스타일/스크립트)
        head_tag = soup.find('head')
        head_content = str(head_tag) if head_tag else "<head><meta charset='UTF-8'></head>"

        # 씬 div 찾기 (id="scene1", id="scene2", ...)
        scene_divs = []
        for match in scene_matches:
            div = soup.find(id=re.compile(f'^(?:scene|씬)\\s*{match}$', re.IGNORECASE))
            if div:
                scene_divs.append(div)

        if len(scene_divs) < 2:
            return scenes, narration_texts

        # body의 style 추출 (배경색, 폰트 등)
        body_tag = soup.find('body')
        body_attrs = ""
        if body_tag and body_tag.attrs:
            attrs_str = " ".join(f'{k}="{v}"' if isinstance(v, str) else f'{k}="{" ".join(v)}"' for k, v in body_tag.attrs.items())
            body_attrs = f" {attrs_str}"

        # 각 씬을 독립 HTML 문서로 구성
        new_scenes = []
        per_scene_duration = duration / len(scene_divs) if duration else default_duration

        for i, div in enumerate(scene_divs):
            # 씬 div에 overflow:hidden과 뷰포트 크기 강제 적용
            div_style = div.get('style', '')
            if 'overflow' not in div_style:
                div['style'] = div_style + '; overflow: hidden;' if div_style else 'overflow: hidden;'

            scene_html = f"""<!DOCTYPE html>
<html lang="ko">
{head_content}
<body{body_attrs}>
{str(div)}
</body>
</html>"""
            new_scenes.append({
                "html": scene_html,
                "duration": per_scene_duration,
                "base_path": base_path
            })

        # narration_texts가 원래 씬 개수와 맞지 않으면 조정
        new_narrations = narration_texts
        if len(narration_texts) == 1 and len(new_scenes) > 1:
            # 하나의 나레이션만 있으면 첫 씬에만 적용
            new_narrations = narration_texts + [""] * (len(new_scenes) - 1)
        elif len(narration_texts) == 0:
            new_narrations = []

        print(f"[create_html_video] 자동 분리 완료: {len(new_scenes)}개 씬, 각 {per_scene_duration:.1f}초")
        return new_scenes, new_narrations

    except Exception as e:
        print(f"[create_html_video] 자동 분리 실패, 원본 유지: {e}")
        return scenes, narration_texts


def create_html_video(tool_input, output_base):
    """HTML 씬들을 프레임별 스크린샷으로 캡처하여 MP4 동영상을 생성합니다.

    각 씬은 독립된 HTML 문서와 재생 시간(duration)으로 구성됩니다.
    CSS 애니메이션, GSAP, Animate.css 등 브라우저에서 렌더링 가능한 모든 애니메이션이 지원됩니다.

    파이프라인:
      1) 나레이션 TTS 먼저 생성
      2) 나레이션 길이에 맞게 씬 duration 자동 조정 (겹침 방지)
      3) HTML → Playwright 프레임 캡처(PNG)
      4) FFmpeg MP4 인코딩
      5) 나레이션/BGM 합성 → 최종 MP4
    """
    import subprocess
    import shutil
    from playwright.sync_api import sync_playwright

    scenes = tool_input.get("scenes", [])
    narration_texts = tool_input.get("narration_texts", [])
    bgm_path = tool_input.get("bgm_path")
    voice = tool_input.get("voice", "ko-KR-SunHiNeural")
    rate = tool_input.get("rate", "+0%")
    pitch = tool_input.get("pitch", "+0Hz")
    output_filename = tool_input.get("output_filename", "html_video.mp4")
    video_width = tool_input.get("width", 1280)
    video_height = tool_input.get("height", 720)
    fps = tool_input.get("fps", 24)
    default_duration = tool_input.get("duration_per_scene", 5)
    # 씬 전환 효과 설정
    transition_type = tool_input.get("transition", "fade")  # fade, wipeleft, wiperight, slidedown, slideup, circleopen, dissolve, none
    transition_duration = tool_input.get("transition_duration", 0.5)  # 전환 시간(초)

    if not scenes:
        if tool_input.get("topic"):
            return (
                "오류: topic만으로는 영상을 만들 수 없습니다. 이 액션은 완성된 HTML 씬을 합성합니다 — "
                "scenes(각 {html, duration} 배열) 또는 scene_dir(저장된 씬 디렉토리)을 주세요. "
                "주제→슬라이드 자동 생성은 [engines:slide] 또는 [engines:lecture_*] 파이프라인을 사용하세요."
            )
        return "오류: scenes 리스트가 비어 있습니다 (scenes 배열 또는 scene_dir 필요)."

    # scenes 검증: html 키 필수
    missing_html = [i for i, s in enumerate(scenes) if isinstance(s, dict) and "html" not in s]
    if missing_html:
        wrong_keys = list(scenes[missing_html[0]].keys()) if missing_html else []
        return (
            f"오류: scenes[{missing_html[0]}]에 'html' 키가 없습니다. "
            f"(현재 키: {wrong_keys})\n"
            f"각 씬은 완전한 HTML 문서가 필요합니다.\n"
            f"올바른 형식:\n"
            f'  scenes: [{{"html": "<!DOCTYPE html><html><head><meta charset=\\"utf-8\\"><script src=\\"https://cdn.tailwindcss.com\\"></script></head>'
            f'<body><div style=\\"width:{video_width}px;height:{video_height}px\\" class=\\"flex items-center justify-center bg-gradient-to-br from-slate-900 to-purple-900\\">'
            f'<h1 class=\\"text-6xl font-bold text-white\\">제목</h1></div></body></html>", "duration": 5}}]\n'
            f"narration_texts: [\"나레이션 텍스트\"]  (씬별 나레이션은 별도 배열)"
        )

    # 자동 씬 분리: 단일 HTML에 여러 씬이 들어있는 경우 감지 및 분리
    scenes, narration_texts = _auto_split_scenes(scenes, narration_texts, default_duration)

    output_path = os.path.join(output_base, output_filename)
    temp_dir = os.path.join(output_base, f"temp_htmlvideo_{uuid.uuid4().hex[:8]}")
    frames_dir = os.path.join(temp_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    try:
        # ============================================================
        # 1단계: 나레이션 TTS를 먼저 생성 (씬 duration 조정을 위해)
        # ============================================================
        narration_audio_paths = []
        narration_durations = []  # 각 나레이션의 실제 재생 시간
        has_narration = False

        for i, scene in enumerate(scenes):
            if i < len(narration_texts) and narration_texts[i]:
                tts_path = os.path.join(temp_dir, f"narration_{i}.mp3")
                asyncio.run(generate_tts(narration_texts[i], tts_path, voice, rate, pitch))
                narration_audio_paths.append(tts_path)
                has_narration = True

                # 나레이션 길이 측정
                from moviepy import AudioFileClip as MpAudioClip
                narr_clip = MpAudioClip(tts_path)
                narration_durations.append(narr_clip.duration)
                narr_clip.close()
            else:
                narration_audio_paths.append(None)
                narration_durations.append(0)

        # ============================================================
        # 2단계: 나레이션 길이에 맞게 씬 duration 자동 조정
        #   나레이션이 씬보다 길면 → 씬을 나레이션 + 여유시간으로 늘림
        #   이렇게 해야 나레이션끼리 겹치지 않음
        # ============================================================
        NARRATION_PADDING = 0.5  # 나레이션 끝나고 다음 씬 시작까지 여유 시간(초)

        for i, scene in enumerate(scenes):
            original_dur = scene.get("duration", default_duration)
            narr_dur = narration_durations[i] if i < len(narration_durations) else 0

            if narr_dur > 0:
                needed_dur = narr_dur + NARRATION_PADDING
                if needed_dur > original_dur:
                    print(f"[create_html_video] 씬 {i+1}: duration {original_dur:.1f}s → {needed_dur:.1f}s (나레이션 {narr_dur:.1f}s에 맞춤)")
                    scene["duration"] = needed_dur

        # ============================================================
        # 3단계: 씬별 프레임 캡처 및 개별 MP4 인코딩
        # ============================================================
        scene_videos = []  # 씬별 MP4 경로 리스트
        scene_durations = []  # 씬별 실제 duration 리스트

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": video_width, "height": video_height})

            for i, scene in enumerate(scenes):
                html = scene.get("html", "")
                duration = scene.get("duration", default_duration)
                base_path_opt = scene.get("base_path") or output_base

                if not html:
                    continue

                html_ready = _prepare_scene_html(html, base_path_opt, video_width, video_height)

                scene_html_dir = base_path_opt if base_path_opt and os.path.isdir(base_path_opt) else temp_dir
                scene_html_path = os.path.join(scene_html_dir, f"_scene_{i}_{uuid.uuid4().hex[:6]}.html")
                with open(scene_html_path, "w", encoding="utf-8") as sf:
                    sf.write(html_ready)
                page.goto(f"file://{scene_html_path}")

                # 모든 애니메이션을 즉시 일시정지
                page.evaluate("""() => {
                    const style = document.createElement('style');
                    style.id = '__anim_pause__';
                    style.textContent = '*, *::before, *::after { animation-play-state: paused !important; }';
                    document.head.appendChild(style);
                }""")

                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(1500 if i == 0 else 500)

                # 리소스 로딩 완료 후 애니메이션 재개
                page.evaluate("""() => {
                    const pauseStyle = document.getElementById('__anim_pause__');
                    if (pauseStyle) pauseStyle.remove();
                }""")

                # 씬별 프레임 디렉토리
                scene_frames_dir = os.path.join(temp_dir, f"frames_scene_{i}")
                os.makedirs(scene_frames_dir, exist_ok=True)

                total_frames = int(duration * fps)
                frame_interval_ms = 1000.0 / fps

                for f in range(total_frames):
                    frame_path = os.path.join(scene_frames_dir, f"frame_{f:06d}.png")
                    page.screenshot(path=frame_path)
                    page.wait_for_timeout(int(frame_interval_ms))

                if total_frames == 0:
                    continue

                # 씬별 MP4 인코딩
                scene_mp4 = os.path.join(temp_dir, f"scene_{i}.mp4")
                enc_result = subprocess.run([
                    "ffmpeg", "-y",
                    "-framerate", str(fps),
                    "-i", os.path.join(scene_frames_dir, "frame_%06d.png"),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-pix_fmt", "yuv420p",
                    scene_mp4
                ], capture_output=True)

                if enc_result.returncode != 0:
                    print(f"[create_html_video] 씬 {i} 인코딩 실패: {enc_result.stderr.decode()}")
                    continue

                scene_videos.append(scene_mp4)
                scene_durations.append(duration)

            browser.close()

        if not scene_videos:
            shutil.rmtree(temp_dir)
            return "오류: 캡처된 프레임이 없습니다."

        # ============================================================
        # 4단계: 씬 전환 효과 적용 및 병합
        # ============================================================
        merged_video = os.path.join(temp_dir, "merged.mp4")
        use_transition = transition_type != "none" and len(scene_videos) > 1 and transition_duration > 0

        if use_transition:
            # FFmpeg xfade 필터를 사용하여 씬 간 전환 효과 적용
            # 유효한 xfade 전환 효과 목록
            valid_transitions = {
                "fade", "wipeleft", "wiperight", "wipeup", "wipedown",
                "slidedown", "slideup", "slideleft", "slideright",
                "circleopen", "circleclose", "dissolve", "pixelize",
                "radial", "hblur", "fadegrays", "squeezeh", "squeezev",
            }
            if transition_type not in valid_transitions:
                transition_type = "fade"

            td = min(transition_duration, min(scene_durations) * 0.4)  # 전환이 씬 길이의 40%를 넘지 않도록

            if len(scene_videos) == 2:
                # 2개 씬: 단일 xfade
                offset = scene_durations[0] - td
                ffmpeg_cmd = [
                    "ffmpeg", "-y",
                    "-i", scene_videos[0], "-i", scene_videos[1],
                    "-filter_complex",
                    f"[0:v][1:v]xfade=transition={transition_type}:duration={td}:offset={offset},format=yuv420p[v]",
                    "-map", "[v]", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    merged_video
                ]
            else:
                # 3개 이상 씬: xfade 체이닝
                inputs = []
                for sv in scene_videos:
                    inputs.extend(["-i", sv])

                filter_parts = []
                cumulative_offset = 0.0

                # 첫 번째 xfade
                cumulative_offset = scene_durations[0] - td
                filter_parts.append(
                    f"[0:v][1:v]xfade=transition={transition_type}:duration={td}:offset={cumulative_offset}[v1]"
                )

                # 나머지 xfade 체이닝
                for j in range(2, len(scene_videos)):
                    prev_label = f"v{j-1}"
                    out_label = f"v{j}"
                    # 이전까지의 총 길이 = 이전 누적 + 현재 씬 duration - 전환 겹침
                    cumulative_offset += scene_durations[j-1] - td
                    filter_parts.append(
                        f"[{prev_label}][{j}:v]xfade=transition={transition_type}:duration={td}:offset={cumulative_offset}[{out_label}]"
                    )

                final_label = f"v{len(scene_videos)-1}"
                filter_complex = ";".join(filter_parts) + f";[{final_label}]format=yuv420p[vout]"

                ffmpeg_cmd = [
                    "ffmpeg", "-y",
                    *inputs,
                    "-filter_complex", filter_complex,
                    "-map", "[vout]", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    merged_video
                ]

            print(f"[create_html_video] 씬 전환 적용: {transition_type}, {td:.2f}초")
            xfade_result = subprocess.run(ffmpeg_cmd, capture_output=True)

            if xfade_result.returncode != 0:
                # xfade 실패 시 fallback: 전환 없이 단순 concat
                print(f"[create_html_video] xfade 실패, concat으로 대체: {xfade_result.stderr.decode()[:300]}")
                use_transition = False

        if not use_transition:
            # 전환 효과 없이 단순 연결 (1개 씬이거나 transition=none이거나 xfade 실패 시)
            if len(scene_videos) == 1:
                shutil.copy2(scene_videos[0], merged_video)
            else:
                concat_list = os.path.join(temp_dir, "concat.txt")
                with open(concat_list, "w") as cl:
                    for sv in scene_videos:
                        cl.write(f"file '{sv}'\n")
                concat_result = subprocess.run([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_list,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-pix_fmt", "yuv420p",
                    merged_video
                ], capture_output=True)
                if concat_result.returncode != 0:
                    shutil.rmtree(temp_dir)
                    return f"FFmpeg concat 오류: {concat_result.stderr.decode()}"

        # ============================================================
        # 5단계: 나레이션과 BGM 합성
        # ============================================================
        if bgm_path:
            bgm_path = os.path.abspath(bgm_path)
        has_bgm = bgm_path and os.path.exists(bgm_path)

        if has_narration or has_bgm:
            from moviepy import AudioFileClip as MpAudioClip, CompositeAudioClip as MpCompositeAudioClip, VideoFileClip

            video_clip = VideoFileClip(merged_video)
            audio_layers = []

            if has_narration:
                # 씬 전환 시 xfade 겹침만큼 시작 타이밍을 앞당김
                actual_td = 0.0
                if use_transition and len(scene_videos) > 1:
                    actual_td = min(transition_duration, min(scene_durations) * 0.4)

                scene_start = 0.0
                for i, scene in enumerate(scenes):
                    dur = scene.get("duration", default_duration)
                    if i < len(narration_audio_paths) and narration_audio_paths[i]:
                        narr = MpAudioClip(narration_audio_paths[i])
                        narr = narr.with_start(scene_start)
                        audio_layers.append(narr)
                    # xfade 적용 시 씬 간 겹침을 반영
                    if i < len(scenes) - 1 and actual_td > 0:
                        scene_start += dur - actual_td
                    else:
                        scene_start += dur

            if has_bgm:
                bgm_clip = MpAudioClip(bgm_path).with_duration(video_clip.duration)
                if has_narration:
                    bgm_clip = bgm_clip.multiply_volume(0.2)
                else:
                    bgm_clip = bgm_clip.multiply_volume(0.5)
                audio_layers.append(bgm_clip)

            if audio_layers:
                final_audio = MpCompositeAudioClip(audio_layers)
                video_clip = video_clip.with_audio(final_audio)

            video_clip.write_videofile(output_path, fps=fps, codec="libx264", audio_codec="aac")
            video_clip.close()
        else:
            shutil.copy2(merged_video, output_path)

        # 임시 파일 정리
        shutil.rmtree(temp_dir)
        # output_base에 생성된 임시 씬 HTML 파일도 정리
        import glob
        for tmp_html in glob.glob(os.path.join(output_base, "_scene_*_*.html")):
            try:
                os.remove(tmp_html)
            except OSError:
                pass

        transition_info = ""
        if use_transition and len(scene_videos) > 1:
            actual_td = min(transition_duration, min(scene_durations) * 0.4)
            transition_info = f" | 씬 전환: {transition_type} ({actual_td:.1f}초)"

        return f"HTML 동영상 제작 완료: {os.path.abspath(output_path)}{transition_info}"
    except subprocess.CalledProcessError as e:
        return f"FFmpeg 오류: {e.stderr.decode() if e.stderr else str(e)}"
    except Exception as e:
        return f"HTML 동영상 제작 중 오류 발생: {str(e)}"


def render_html_to_image(tool_input, output_base="."):
    """HTML을 이미지로 렌더링

    로컬 이미지 사용 방법:
    1. base_path 옵션: HTML 내 상대 경로의 기준 디렉토리 지정
       - base_path="/Users/.../project" 설정 시 <img src="images/photo.jpg">가 작동
    2. 절대 경로: <img src="file:///Users/.../image.jpg">
    3. Base64: <img src="data:image/png;base64,...">
    """
    from playwright.sync_api import sync_playwright
    import re
    import tempfile

    html = tool_input.get("html")
    output_path = tool_input.get("output_path")
    width = tool_input.get("width", 1280)
    height = tool_input.get("height", 720)
    selector = tool_input.get("selector")
    base_path = tool_input.get("base_path")  # 로컬 파일 기준 경로

    if not html:
        return "오류: html은 필수입니다."

    # output_path가 지정되면 파일명만 추출하여 output_base에 저장
    if output_path:
        filename = os.path.basename(output_path)
        output_path = os.path.join(output_base, filename)
    else:
        output_path = os.path.join(output_base, f"rendered_{uuid.uuid4().hex[:8]}.png")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})

            # base_path가 있으면 임시 HTML 파일 생성 후 file:// 프로토콜로 로드
            if base_path:
                base_path = os.path.abspath(base_path)

                # HTML 내 상대 경로 이미지를 Base64로 변환
                def replace_img_src(match):
                    src = match.group(1)
                    # 이미 data: 또는 http로 시작하면 스킵
                    if src.startswith(('data:', 'http://', 'https://', 'file://')):
                        return match.group(0)
                    # 상대 경로를 절대 경로로 변환
                    if not os.path.isabs(src):
                        abs_path = os.path.join(base_path, src)
                    else:
                        abs_path = src
                    # Base64로 변환
                    base64_data = get_image_base64(abs_path)
                    if base64_data:
                        return f'src="{base64_data}"'
                    return match.group(0)  # 변환 실패시 원본 유지

                # src="..." 패턴 찾아서 변환
                html = re.sub(r'src=["\']([^"\']+)["\']', replace_img_src, html)

                # CSS background-image의 url()도 처리
                def replace_bg_url(match):
                    url = match.group(1)
                    if url.startswith(('data:', 'http://', 'https://', 'file://')):
                        return match.group(0)
                    if not os.path.isabs(url):
                        abs_path = os.path.join(base_path, url)
                    else:
                        abs_path = url
                    base64_data = get_image_base64(abs_path)
                    if base64_data:
                        return f'url("{base64_data}")'
                    return match.group(0)

                html = re.sub(r'url\(["\']?([^"\')\s]+)["\']?\)', replace_bg_url, html)

            # 스타일 추가: 여백 제거 및 크기 강제
            html_with_style = f"""
            <style>
                body, html {{ margin: 0; padding: 0; width: {width}px; height: {height}px; overflow: hidden; }}
            </style>
            {html}
            """
            page.set_content(html_with_style)

            # 이미지 로딩 대기
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(500)  # Tailwind/폰트 로딩 대기

            if selector:
                element = page.query_selector(selector)
                if element:
                    element.screenshot(path=output_path)
                else:
                    browser.close()
                    return f"오류: 셀렉터 '{selector}'를 찾을 수 없습니다."
            else:
                page.screenshot(path=output_path)
            browser.close()
        # 절대 경로로 변환하여 반환 (에이전트 간 경로 혼동 방지)
        return f"렌더링 완료: {os.path.abspath(output_path)}"
    except Exception as e:
        return f"렌더링 중 오류 발생: {str(e)}"

def generate_ai_image(tool_input, output_base):
    import urllib.parse
    import httpx
    prompt = tool_input.get("prompt")
    if not prompt:
        return "오류: prompt는 필수입니다."
    output_path = tool_input.get("output_path")
    width = min(tool_input.get("width", 1024), 2048)
    height = min(tool_input.get("height", 1024), 2048)
    model = tool_input.get("model", "flux")
    seed = tool_input.get("seed")
    # output_path가 지정되면 파일명만 추출하여 output_base에 저장
    if output_path:
        filename = os.path.basename(output_path)
        output_path = os.path.join(output_base, filename)
    else:
        output_path = os.path.join(output_base, f"ai_image_{uuid.uuid4().hex[:8]}.png")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model={model}&nologo=true"
    if seed is not None:
        url += f"&seed={seed}"
    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(response.content)
        # 절대 경로로 변환하여 반환 (에이전트 간 경로 혼동 방지)
        return f"AI 이미지 생성 완료: {os.path.abspath(output_path)}\n프롬프트: {prompt}"
    except Exception as e:
        return f"이미지 생성 중 오류 발생: {str(e)}"


# ─────────────────────────────────────────────────────────────────────
# [engines:icon] — 앱 전용(prompt_hidden) 아이콘 생성
#   기본 = Gemini 이미지 모델 단일 호출(한국어 아이디어 직접 이해 — 확장 단계가
#   모델 안으로 접힘, GEMINI_API_KEY 는 맥·폰 공통 프로비저닝) → 실패/키 없음 시
#   폴백 = AI 확장 프롬프트 → Pollinations flux(무료).
#   → 미리보기(data URI) 반환 + (폰이면) 이미지 클립보드 자동 복사(카톡 붙여넣기용).
#   ★AI 어휘에 노출 안 됨(prompt_hidden). runs_on: anywhere 라 폰서 로컬 실행.
# ─────────────────────────────────────────────────────────────────────

_ICON_AUTHOR_SYSTEM_PROMPT = """You are an expert prompt engineer for CUTE CARTOON ICON / STICKER generation.
Given a user's short idea (often written in Korean), output ONE single-line English
image-generation prompt that yields an adorable, playful cartoon sticker suitable for a
messaging app (KakaoTalk emoticon).

Style — this is the most important part:
- CUTE but COMICAL and EXAGGERATED cartoon / chibi style — like a funny meme sticker or
  caricature. Over-the-top exaggerated proportions and expressions (huge head, tiny body,
  giant sparkly eyes, dramatic emotion, wobbly goofy pose), bursting with personality and
  humor. Bold, snappy, playful — make it read instantly and get a laugh.
- Thick bold clean black outlines, FLAT cel-shaded solid colors (like a sticker or emoji),
  punchy exaggerated shapes, bright saturated cheerful palette. Optional cartoon effect
  lines / sparkles / sweat drops to amplify the emotion.
- Emphasize that it is a flat 2D comic cartoon illustration / vector sticker.

Strictly AVOID (do NOT let it look like this):
- NOT photorealistic, NOT realistic, NOT 3D render.
- NOT watercolor, NOT oil painting, NOT painterly, no visible brushstrokes.
- No soft airbrush gradients, no realistic textures or shading, no photographic detail.

Composition:
- A single clear subject, centered, simple composition, generous padding around it.
- Plain solid or simple flat background — no busy scenery, no clutter.
- Absolutely NO text, letters, numbers, logos, or watermarks in the image.

Output ONLY one single line: a comma-separated list of visual descriptors starting with
the subject. Do NOT use headings, section labels, bullet points, markdown, or line breaks
— just the prompt itself on one line. No quotes, no preamble, no explanation.
"""

_ICON_FALLBACK_STYLE = (
    "comical exaggerated cute cartoon sticker, chibi caricature, funny meme style, "
    "huge head tiny body, giant sparkly eyes, over-the-top dramatic expression, goofy "
    "playful pose, thick bold black outlines, flat cel-shaded solid colors, punchy "
    "exaggerated shapes, bright saturated palette, cartoon effect lines, flat 2D vector "
    "illustration, single centered subject, plain simple background, generous padding, "
    "NOT realistic, NOT watercolor, NOT painterly, no gradients, no text, no letters, no watermark"
)


def _flatten_expanded(text: str) -> str:
    """Gemini 확장 응답을 한 줄 프롬프트로 평탄화 — 모델이 가끔 헤더/불릿/줄바꿈으로
    구조화 응답을 내므로(첫 줄만 취하면 주제가 유실됨) 전체를 정리해 이어붙인다."""
    import re
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r"```[a-zA-Z]*", " ", t)          # 코드펜스 제거
    t = t.replace("`", " ").replace("**", " ").replace("__", " ")
    t = re.sub(r"(?m)^\s*[-*#>•·]+\s*", " ", t)  # 줄머리 불릿/헤더 기호
    t = t.replace("\r", "\n")
    t = re.sub(r"\n+", ", ", t)                    # 줄바꿈 → 쉼표 이음
    t = t.strip().strip('"').strip()
    t = re.sub(r"\s+", " ", t)                     # 공백 정리
    t = re.sub(r"\s*,\s*(,\s*)+", ", ", t)         # 중복 쉼표
    t = re.sub(r"[:：]\s*,", ": ", t)              # "라벨: ," 정리
    t = t.strip(" ,")
    return t[:600]


def _expand_icon_prompt(user_prompt: str, style_hint: str = "") -> str:
    """사용자의 짧은 아이디어 → 전문가 영어 아이콘 프롬프트.

    ★Gemini 텍스트 모델로 확장 — GEMINI_API_KEY 는 맥·폰 양쪽에 프로비저닝돼 있어
    폰-직결에서도 맥 없이 진짜 AI 확장이 된다(폰 인지는 맥 위임이라 Anthropic 키가
    없다 — 그래서 content_text provider 대신 Gemini 를 쓴다). 실패 시 템플릿 폴백."""
    base = (user_prompt or "").strip()
    if not base:
        return base
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            import httpx
            # ★gemini-flash-latest 별칭은 2026-07 중순 이후 thinkingBudget:0 을
            # 400 INVALID_ARGUMENT 로 거부(별칭이 tb=0 미지원 모델로 이동) →
            # 버전 고정 gemini-2.5-flash 사용(body_ask._compile_gemini 와 동일 조합).
            model = os.environ.get("ICON_EXPAND_MODEL", "gemini-2.5-flash")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            umsg = base if not style_hint else f"{base}\n\nStyle hint: {style_hint}"
            payload = {
                "systemInstruction": {"parts": [{"text": _ICON_AUTHOR_SYSTEM_PROMPT}]},
                "contents": [{"parts": [{"text": umsg}]}],
                # thinkingBudget=0: flash-latest 가 thinking 모델이면 추론이 토큰을 먹어
                # 출력이 잘려 주제가 유실됨(빈/조각 응답) → thinking 끄고 넉넉히.
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 400,
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            }
            with httpx.Client(timeout=30.0) as client:
                r = client.post(url, params={"key": api_key}, json=payload,
                                headers={"Content-Type": "application/json"})
                r.raise_for_status()
                data = r.json()
            parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            out = "".join(p.get("text", "") for p in parts)
            out = _flatten_expanded(out)
            if len(out) >= 4:
                return out
            print(f"[icon] Gemini 확장 결과 비어있음 → 템플릿 폴백")
        except Exception as e:
            print(f"[icon] Gemini 프롬프트 확장 실패 → 템플릿 폴백: {e}")
    else:
        print("[icon] GEMINI_API_KEY 없음 → 템플릿 폴백")
    extra = f", {style_hint}" if style_hint else ""
    return f"{base}{extra}, {_ICON_FALLBACK_STYLE}"


def _sniff_image_mime(b: bytes):
    """바이트 매직으로 이미지 mime/확장자 판정 (Pollinations 는 실제로 JPEG 를 줄 때가 많다 —
    mime 을 png 로 박으면 클립보드 붙여넣기 시 대상 앱이 혼동)."""
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg", ".jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", ".png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return "image/png", ".png"


_ICON_GEMINI_MODEL = "gemini-3.1-flash-image"


def _icon_via_gemini(user_prompt: str, style_hint: str, api_key: str):
    """Gemini 이미지 모델 단일 호출 → (이미지 bytes, 사용한 프롬프트).

    지시 이해력이 좋아 한국어 아이디어를 직접 넣는다 — 별도 확장 호출 불필요
    (2단 호출이 1단으로 접힘). 출력은 1024px 고정이라 호출부에서 다운스케일."""
    import httpx

    extra = f" Extra style hint: {style_hint}." if style_hint else ""
    prompt = (f"Draw a KakaoTalk emoticon sticker of: {user_prompt}.{extra} "
              f"Style: {_ICON_FALLBACK_STYLE}")
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{_ICON_GEMINI_MODEL}:generateContent")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": "1:1"},
        },
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(url, params={"key": api_key}, json=payload,
                        headers={"Content-Type": "application/json"})
        r.raise_for_status()
        data = r.json()
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    for p in parts:
        inline = p.get("inlineData") or p.get("inline_data")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"]), prompt
    raise RuntimeError(f"응답에 이미지 파트 없음: {str(data)[:200]}")


def generate_icon(tool_input, output_base):
    """[engines:icon] 앱 전용 아이콘 생성기. dict 통화 반환(app blocks 미리보기)."""
    import urllib.parse
    import httpx

    user_prompt = (tool_input.get("prompt") or tool_input.get("q") or "").strip()
    if not user_prompt:
        return {"success": False, "message": "무엇을 그릴지 한 줄로 알려주세요.", "blocks": []}

    try:
        size = int(tool_input.get("size") or 384)
    except Exception:
        size = 384
    size = max(128, min(size, 1024))
    style_hint = (tool_input.get("style") or "").strip()
    do_copy = tool_input.get("copy")
    do_copy = True if do_copy is None else bool(do_copy)

    # 1순위 = Gemini 이미지(유료 ~$0.07/장, 벡터급 선·스타일 이행) — 키는 맥·폰 공통.
    img_bytes = None
    engine = None
    expanded = None
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            img_bytes, expanded = _icon_via_gemini(user_prompt, style_hint, api_key)
            engine = _ICON_GEMINI_MODEL
        except Exception as e:
            print(f"[icon] Gemini 이미지 생성 실패 → Pollinations 폴백: {e}")

    # 폴백 = 확장 프롬프트 → Pollinations flux(무료).
    # flux 는 ~1024px 학습 분포 — 저해상도 네이티브 생성은 품질 열화라
    # 크게 생성한 뒤 아래 공통 LANCZOS 다운스케일(슈퍼샘플링)을 태운다.
    if img_bytes is None:
        expanded = _expand_icon_prompt(user_prompt, style_hint)
        gen_size = size if size >= 768 else 768
        encoded = urllib.parse.quote(expanded)
        url = (f"https://image.pollinations.ai/prompt/{encoded}"
               f"?width={gen_size}&height={gen_size}&model=flux&nologo=true")
        try:
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                r = client.get(url)
                r.raise_for_status()
                img_bytes = r.content
            engine = "flux"
        except Exception as e:
            return {"success": False, "message": f"아이콘 생성 실패: {e}",
                    "prompt": expanded, "blocks": []}

    # 공통 다운스케일 — 두 엔진 다 요청 size 보다 크게 생성됨. PNG 재인코딩으로 mime 확정.
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(img_bytes))
        if im.size != (size, size):
            im = im.convert("RGB").resize((size, size), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            img_bytes = buf.getvalue()
    except Exception as e:
        print(f"[icon] 다운스케일 실패 → 원본 크기 사용: {e}")

    mime, ext = _sniff_image_mime(img_bytes)
    out_path = os.path.join(output_base, f"icon_{uuid.uuid4().hex[:8]}{ext}")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    try:
        with open(out_path, "wb") as f:
            f.write(img_bytes)
    except Exception as e:
        return {"success": False, "message": f"아이콘 저장 실패: {e}",
                "prompt": expanded, "blocks": []}

    data_uri = f"data:{mime};base64," + base64.b64encode(img_bytes).decode("utf-8")

    # 이미지 클립보드 자동 복사(ClipData.newUri) — 카톡 등에서 붙여넣기.
    # ★capability 게이트: `from java import jclass` 는 폰 네이티브 런타임에만 성공
    # (맥/PC 는 ImportError → 조용히 스킵). 환경변수 프로파일 분기 대신 이 능력감지가 무포크 규율.
    copied = False
    copy_note = ""
    if do_copy:
        try:
            from java import jclass  # 폰 전용 브리지 = 능력 감지
            MS = jclass("com.indiebiz.phoneagent.MediaSaver")
            res = str(MS.imageToClipboard(img_bytes, f"icon_{uuid.uuid4().hex[:8]}{ext}", mime))
            copied = res.startswith("OK")
            if not copied:
                copy_note = res
        except ImportError:
            pass  # 맥/PC — 폰 클립보드 없음(정상)
        except Exception as e:
            copy_note = str(e)

    if copied:
        status = "✓ 클립보드에 복사됨 — 카카오톡 대화창에서 붙여넣기하세요"
    elif do_copy and copy_note:
        status = f"생성 완료 (자동 복사 실패: {copy_note})"
    elif do_copy:
        status = "생성 완료 (클립보드 복사는 폰에서만 동작)"
    else:
        status = "생성 완료"

    return {
        "success": True,
        "blocks": [
            {"type": "image", "src": data_uri, "caption": user_prompt},
            {"text": status},
        ],
        "message": status,
        "prompt": expanded,
        "engine": engine,
        "path": os.path.abspath(out_path),
        "copied": copied,
    }


STYLE_PRESETS = {
    "vintage_book": (
        "Hand-drawn pen and ink illustration on aged beige parchment paper, "
        "two-tone palette of deep navy blue (#2c3e6f) and rust brown (#a55a3e), "
        "fine cross-hatching, geometric grid background lines, subtle paper texture and grain, "
        "vintage scientific manuscript aesthetic, balanced empty space around the central subject, "
        "centered composition with breathing room. "
        "Do NOT include any Korean or Hangul characters. Do NOT add decorative Latin text, ciphers, or unreadable script. "
        "Only the subject illustration — minimal or no text inside the image."
    ),
    "academic_paper": (
        "Clean academic diagram on bright white paper, monochrome with deep navy (#161c2a) line art and crimson (#8b1a1a) accent, "
        "thin precise pen lines, minimal shading, scholarly figure illustration style, generous white space. "
        "Do NOT include Korean or Hangul characters. Only English labels if any text is needed."
    ),
    "tech_minimal": (
        "Minimal vector-style illustration on dark navy background (#0d0f17), "
        "neon cyan (#1ce0ff) accent lines, thin geometric strokes, subtle glow, "
        "Linear/Vercel design aesthetic, isometric or flat composition, generous negative space. "
        "Do NOT include Korean or Hangul characters."
    ),
    "magazine_modern": (
        "Bold editorial illustration in New Yorker / Wired magazine style, "
        "high contrast black ink on pure white background with selective vivid red (#e6182b) accent, "
        "confident brush strokes, modernist composition, ample white space. "
        "Do NOT include Korean or Hangul characters."
    ),
    "sf_blueprint": (
        "Sci-fi HUD blueprint infographic on a deep navy (#050d1a) background, "
        "glowing cyan (#1ad3ff) and pale ice-blue (#6ee0ff) line art, thin precise pen strokes with subtle outer glow, "
        "wireframe / x-ray rendering of the subject, surrounded by faint technical schematic grid lines and HUD frame brackets in the corners, "
        "small English technical labels and arrow annotations allowed (e.g. 'EYE', 'MASS', 'F=ma', 'FAILURE STATE'), "
        "NotebookLM diagram aesthetic, holographic / hologram feel, "
        "composition deliberately leaves clear empty regions on the sides or bottom so Korean caption boxes can be overlaid later without occluding the subject. "
        "Strictly NO Korean / Hangul characters anywhere in the image. "
        "Avoid decorative gibberish Latin text — only meaningful English labels if any."
    ),
}


def _build_image_prompt(user_prompt: str, style_preset: str = None) -> str:
    """스타일 프리셋을 사용자 프롬프트와 결합. 디자인 시스템과 어울리는 일러스트 생성용."""
    if not style_preset or style_preset == "default":
        return user_prompt
    style = STYLE_PRESETS.get(style_preset)
    if not style:
        return user_prompt
    return f"{user_prompt}\n\n--- STYLE GUIDELINES ---\n{style}"


def critique_gemini_image(tool_input, output_base):
    """Gemini Vision으로 이미지를 평가한다 — 일러스트가 의도와 정합하는지 검증.

    파라미터:
      - image_path (필수): 평가할 이미지 절대 경로 (또는 base64 data URI)
      - intent (필수): "이 일러스트가 무엇을 표현해야 하는가" — 자연어 설명
      - checks (선택): 추가 체크 리스트 (예: ["다이어그램형인가", "한글이 들어갔는가", "오른쪽 1/3이 비어있는가"])
      - style_preset (선택): 디자인 시스템 톤 일관성 평가 기준 (sf_blueprint 등)
      - api_key (선택)

    반환:
      JSON 문자열 — {"passed": bool, "score": 0-10, "issues": [...], "notes": "..."}
      그리고 사람이 읽을 수 있는 요약 텍스트가 앞에 옴.
    """
    import httpx
    import base64
    import json as _json

    # path 는 IBL 표준 파라미터(self:read/grep/edit 모두 path) — image_path 미지정 시 폴백 수용.
    image_path = tool_input.get("image_path") or tool_input.get("path")
    intent = tool_input.get("intent", "")
    if not image_path:
        return "오류: image_path(또는 path)가 필요합니다."
    if not intent:
        return "오류: intent(이 일러스트가 무엇을 표현해야 하는지)가 필요합니다."

    api_key = tool_input.get("api_key") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "오류: GEMINI_API_KEY가 설정되지 않았습니다."

    # 이미지 로드 (절대 경로 또는 data URI)
    if image_path.startswith("data:"):
        # data URI → base64 페이로드만 추출
        try:
            _, b64data = image_path.split(",", 1)
            mime = image_path.split(";", 1)[0].split(":", 1)[1]
        except Exception:
            return "오류: 잘못된 data URI."
    else:
        if not os.path.exists(image_path):
            return f"오류: 파일이 없습니다: {image_path}"
        with open(image_path, "rb") as f:
            b64data = base64.b64encode(f.read()).decode("utf-8")
        ext = os.path.splitext(image_path)[1].lower()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(ext, "image/png")

    checks = tool_input.get("checks") or []
    style_preset = tool_input.get("style_preset", "")
    # preset: "slide_illustration"(기본, 현행 슬라이드 일러스트 체크) | "general"(임의 산출물 범용)
    preset = (tool_input.get("preset") or "slide_illustration").strip().lower()

    if preset == "general":
        default_checks = [
            "이미지가 의도(intent)를 정확하고 충분히 충족하는가?",
            "시각적 결함(텍스트 잘림·겹침, 레이아웃 불균형, 깨짐, 저해상도, 빈 공간 과다)이 없는가?",
        ]
        if style_preset:
            default_checks.append(f"스타일/톤이 '{style_preset}'와 일관되는가?")
        intro = "당신은 산출물 품질 평가자입니다. 아래 이미지가 의도를 잘 충족하는지 엄격하게 평가하세요."
        hard_rule = ""
    else:
        default_checks = [
            "이 일러스트는 회화적 '씬(scene)'이 아니라 정보를 전달하는 '다이어그램/인포그래픽'인가? (NotebookLM 양식)",
            "한글(Hangul) 문자가 일러스트 안에 들어가 있는가? (있으면 실패 — 한글은 텍스트 레이어에서 처리)",
            "라벨 박스가 들어갈 빈 공간(여백)이 의도된 위치에 정말 비어 있는가? (intent에 명시된 빈 공간 위치 확인)",
            "주요 객체가 일러스트의 핵심 영역(중앙/지정 위치)에 명확하게 배치되어 있는가?",
        ]
        if style_preset:
            default_checks.append(f"디자인 시스템 톤이 '{style_preset}'와 일관되는가? (색·선·분위기)")
        intro = "당신은 강의 슬라이드 일러스트 평가자입니다. 다음 일러스트가 의도를 잘 표현하는지 엄격하게 평가하세요."
        hard_rule = " 한글이 일러스트에 들어가 있으면 무조건 passed=false."

    all_checks = default_checks + checks

    instruction = (
        intro + "\n\n"
        f"**의도 (이 결과물이 충족해야 할 것)**:\n{intent}\n\n"
        f"**체크 항목** ({len(all_checks)}개):\n"
        + "\n".join(f"{i+1}. {c}" for i, c in enumerate(all_checks))
        + "\n\n반드시 다음 JSON 형식 한 개만 출력하세요. 다른 텍스트 금지.\n"
        "```json\n"
        "{\n"
        '  "passed": true|false,\n'
        '  "score": 0-10,\n'
        '  "issues": ["체크 N번 실패 — 구체적 이유", ...],\n'
        '  "notes": "전반적 평가 (1~2문장)"\n'
        "}\n"
        "```\n"
        "passed는 issues가 없거나 score>=7일 때 true." + hard_rule
    )

    payload = {
        "contents": [{
            "parts": [
                {"inlineData": {"mimeType": mime, "data": b64data}},
                {"text": instruction},
            ]
        }],
        "generationConfig": {"temperature": 0.2, "responseModalities": ["TEXT"]},
    }

    # VLM 모델 — pro 우선, fallback flash
    model = tool_input.get("model") or "gemini-3-pro-preview"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, params={"key": api_key}, json=payload,
                            headers={"Content-Type": "application/json"})
            if r.status_code == 404:
                # 폴백 모델
                model = "gemini-2.5-pro"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                r = client.post(url, params={"key": api_key}, json=payload,
                                headers={"Content-Type": "application/json"})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return f"오류: VLM 호출 실패: {e}"

    parts = (data.get("candidates", [{}])[0].get("content", {}) or {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    # ```json ... ``` 코드 펜스 제거
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
        text = text.split("```")[0].strip()

    try:
        verdict = _json.loads(text)
    except Exception:
        return f"VLM 응답 파싱 실패 — 원문:\n{text[:500]}"

    summary_lines = [
        f"이미지 평가: {image_path}",
        f"의도: {intent[:80]}{'...' if len(intent) > 80 else ''}",
        f"평가 결과: {'✓ 통과' if verdict.get('passed') else '✗ 실패'} (score={verdict.get('score', '?')}/10)",
    ]
    issues = verdict.get("issues") or []
    if issues:
        summary_lines.append("문제점:")
        summary_lines.extend(f"  - {i}" for i in issues)
    if verdict.get("notes"):
        summary_lines.append(f"메모: {verdict['notes']}")
    summary_lines.append("")
    summary_lines.append(f"verdict_json: {_json.dumps(verdict, ensure_ascii=False)}")
    return "\n".join(summary_lines)


def read_gemini_image(tool_input, output_base):
    """Gemini Vision으로 이미지를 *읽어* 질문에 자유서술로 답한다 (시각 QA / OCR / 검증).

    critique_gemini_image 와 다른 점: 합격/점수 채점이 아니라, 주어진 질문에 대한 자유 텍스트
    답을 돌려준다. "스크린샷의 숫자를 읽어줘", "이 그림에 무엇이 보이나", "이 통계 수치가
    332인가 136인가" 같은 시각 읽기·검증에 쓴다. 생성 일러스트 품질 평가는 image_critic 을 쓸 것.

    파라미터:
      - image_path (또는 path): 읽을 이미지 절대 경로 또는 base64 data URI (필수)
      - question (또는 query/intent/prompt): 무엇을 읽거나 답할지 (없으면 전체 묘사)
      - api_key (선택), model (선택)
    """
    import httpx
    import base64

    image_path = tool_input.get("image_path") or tool_input.get("path")
    if not image_path:
        return "오류: image_path(또는 path)가 필요합니다."
    question = (tool_input.get("question") or tool_input.get("query")
               or tool_input.get("intent") or tool_input.get("prompt") or "").strip()

    api_key = tool_input.get("api_key") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "오류: GEMINI_API_KEY가 설정되지 않았습니다."

    # 이미지 로드 (절대 경로 또는 data URI) — critique_gemini_image 와 동일.
    if image_path.startswith("data:"):
        try:
            _, b64data = image_path.split(",", 1)
            mime = image_path.split(";", 1)[0].split(":", 1)[1]
        except Exception:
            return "오류: 잘못된 data URI."
    else:
        if not os.path.exists(image_path):
            return f"오류: 파일이 없습니다: {image_path}"
        with open(image_path, "rb") as f:
            b64data = base64.b64encode(f.read()).decode("utf-8")
        ext = os.path.splitext(image_path)[1].lower()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/png")

    if question:
        instruction = (
            "당신은 이미지를 정확히 읽는 시각 분석가입니다. 아래 이미지를 보고 질문에 "
            "사실에 근거해 답하세요. 이미지에 적힌 텍스트·숫자는 보이는 그대로 정확히 옮기고, "
            "보이지 않거나 불확실하면 추측하지 말고 그렇다고 밝히세요.\n\n"
            f"**질문**: {question}"
        )
    else:
        instruction = ("아래 이미지를 보고 무엇이 있는지 상세히 묘사하세요. 이미지에 적힌 "
                       "텍스트·숫자가 있으면 보이는 그대로 정확히 옮기세요.")

    payload = {
        "contents": [{
            "parts": [
                {"inlineData": {"mimeType": mime, "data": b64data}},
                {"text": instruction},
            ]
        }],
        "generationConfig": {"temperature": 0.0, "responseModalities": ["TEXT"]},
    }
    model = tool_input.get("model") or "gemini-3-pro-preview"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, params={"key": api_key}, json=payload,
                            headers={"Content-Type": "application/json"})
            if r.status_code == 404:
                model = "gemini-2.5-pro"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                r = client.post(url, params={"key": api_key}, json=payload,
                                headers={"Content-Type": "application/json"})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return f"오류: VLM 호출 실패: {e}"

    parts = (data.get("candidates", [{}])[0].get("content", {}) or {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        return "오류: VLM 빈 응답 (이미지를 읽지 못했습니다)."
    return text


def generate_gemini_image(tool_input, output_base):
    """Gemini API를 사용하여 이미지를 생성합니다."""
    import httpx
    import base64

    prompt = tool_input.get("prompt")
    if not prompt:
        return "오류: prompt는 필수입니다."

    api_key = tool_input.get("api_key") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "오류: GEMINI_API_KEY 환경변수가 설정되지 않았거나 api_key 파라미터가 필요합니다."

    output_path = tool_input.get("output_path")
    aspect_ratio = tool_input.get("aspect_ratio", "1:1")
    image_size = tool_input.get("image_size", "1K")  # 512/1K/2K/4K (3.x), 2.5는 무시
    style_preset = tool_input.get("style_preset")
    final_prompt = _build_image_prompt(prompt, style_preset)

    # 모델 선택 — 기본은 Nano Banana 2 (Gemini 3.1 Flash, 2026-02 출시)
    # quality 별칭으로 간편 선택, 또는 model로 직접 지정 가능
    quality = tool_input.get("quality")  # "fast" | "pro" | "legacy"
    quality_map = {
        "fast": "gemini-3.1-flash-image-preview",  # Nano Banana 2 (기본)
        "pro": "gemini-3-pro-image-preview",       # Nano Banana Pro — 4K, 더 정밀
        "legacy": "gemini-2.5-flash-image",        # 구버전 폴백
    }
    model = tool_input.get("model") or quality_map.get(quality, "gemini-3.1-flash-image-preview")

    # output_path가 지정되면 파일명만 추출하여 output_base에 저장
    if output_path:
        filename = os.path.basename(output_path)
        output_path = os.path.join(output_base, filename)
    else:
        output_path = os.path.join(output_base, f"gemini_image_{uuid.uuid4().hex[:8]}.png")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    # 페이로드 구조: 양쪽 모델 모두 generationConfig.imageConfig 사용.
    #   - 2.5: aspectRatio만 지원
    #   - 3.x: aspectRatio + imageSize (1K/2K/4K/512) 지원
    is_legacy = model.startswith("gemini-2.5")
    image_config = {"aspectRatio": aspect_ratio}
    if not is_legacy:
        image_config["imageSize"] = image_size
    payload = {
        "contents": [{"parts": [{"text": final_prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
            "imageConfig": image_config,
        },
    }

    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(
                url,
                params={"key": api_key},
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()

        # 응답에서 이미지 데이터 추출
        candidates = data.get("candidates", [])
        if not candidates:
            return f"오류: Gemini API 응답에 결과가 없습니다. 응답: {data}"

        parts = candidates[0].get("content", {}).get("parts", [])
        image_saved = False
        description = ""

        for part in parts:
            if "inlineData" in part:
                img_data = base64.b64decode(part["inlineData"]["data"])
                with open(output_path, "wb") as f:
                    f.write(img_data)
                image_saved = True
            elif "text" in part:
                description = part["text"]

        if not image_saved:
            return f"오류: 응답에 이미지 데이터가 없습니다. 텍스트 응답: {description or data}"

        size_note = "" if is_legacy else f" / {image_size}"
        result = (
            f"Gemini 이미지 생성 완료: {os.path.abspath(output_path)}\n"
            f"모델: {model}{size_note} (aspect {aspect_ratio})\n"
            f"프롬프트: {prompt}"
        )
        if description:
            result += f"\n설명: {description}"
        return result

    except httpx.HTTPStatusError as e:
        return f"Gemini API 오류 ({e.response.status_code}): {e.response.text}"
    except Exception as e:
        return f"Gemini 이미지 생성 중 오류 발생: {str(e)}"


def create_tts(tool_input, output_base):
    """텍스트를 음성 파일(MP3)로 변환합니다. (Edge TTS)"""
    text = tool_input.get("text")
    if not text:
        return "오류: text는 필수입니다."

    voice = tool_input.get("voice", "ko-KR-SunHiNeural")
    rate = tool_input.get("rate", "+0%")
    pitch = tool_input.get("pitch", "+0Hz")
    output_filename = tool_input.get("output_filename")

    if output_filename:
        output_path = os.path.join(output_base, os.path.basename(output_filename))
    else:
        output_path = os.path.join(output_base, f"tts_{uuid.uuid4().hex[:8]}.mp3")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    try:
        asyncio.run(generate_tts(text, output_path, voice, rate, pitch))

        # 길이 측정
        from moviepy import AudioFileClip as MpAudioClip
        clip = MpAudioClip(output_path)
        duration = clip.duration
        clip.close()

        abs_path = os.path.abspath(output_path)
        return f"TTS 생성 완료: {abs_path}\n길이: {duration:.1f}초\n음성: {voice}"
    except Exception as e:
        return f"TTS 생성 중 오류 발생: {str(e)}"


def render_html_video(tool_input, output_base):
    """HTML 파일 경로 목록을 받아서 MP4 동영상으로 렌더링합니다.

    코드 작성은 에이전트가 system:write로 미리 해두고,
    이 함수는 순수 렌더링만 담당합니다.

    입력:
      scene_files: [{path: "scene1.html", duration: 5}, ...]
      또는
      scene_dir: "씬 HTML 파일들이 있는 폴더" (알파벳 순 정렬)

      narration_files: ["narr1.mp3", "narr2.mp3", ...]  (선택)
      bgm_path: "bgm.mp3"  (선택)
    """
    import subprocess
    import shutil
    import glob as glob_module
    from playwright.sync_api import sync_playwright

    scene_files = tool_input.get("scene_files", [])
    scene_dir = tool_input.get("scene_dir")
    narration_files = tool_input.get("narration_files", [])
    bgm_path = tool_input.get("bgm_path")
    output_filename = tool_input.get("output_filename", "rendered_video.mp4")
    video_width = tool_input.get("width", 1280)
    video_height = tool_input.get("height", 720)
    fps = tool_input.get("fps", 24)
    default_duration = tool_input.get("duration_per_scene", 5)

    # scene_dir이 지정되면 폴더에서 HTML 파일들을 자동 수집
    if scene_dir and not scene_files:
        scene_dir = os.path.abspath(scene_dir)
        if not os.path.isdir(scene_dir):
            return f"오류: scene_dir '{scene_dir}'이 존재하지 않습니다."
        html_paths = sorted(glob_module.glob(os.path.join(scene_dir, "*.html")))
        if not html_paths:
            return f"오류: '{scene_dir}'에 HTML 파일이 없습니다."
        scene_files = [{"path": p, "duration": default_duration} for p in html_paths]

    if not scene_files:
        return "오류: scene_files 또는 scene_dir이 필요합니다."

    # 경로 검증
    for i, sf in enumerate(scene_files):
        path = sf.get("path", "")
        if not os.path.isabs(path):
            path = os.path.join(output_base, path)
            sf["path"] = path
        if not os.path.exists(path):
            return f"오류: scene_files[{i}]의 파일이 없습니다: {path}"

    output_path = os.path.join(output_base, output_filename)
    temp_dir = os.path.join(output_base, f"temp_render_{uuid.uuid4().hex[:8]}")
    frames_dir = os.path.join(temp_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    try:
        # 프레임 캡처
        global_frame = 0

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": video_width, "height": video_height})

            for i, sf in enumerate(scene_files):
                html_path = sf["path"]
                duration = sf.get("duration", default_duration)

                # HTML 파일을 읽어서 전처리 (이미지 Base64 변환 등)
                with open(html_path, "r", encoding="utf-8") as f:
                    html = f.read()

                base_path = os.path.dirname(html_path)
                html_ready = _prepare_scene_html(html, base_path, video_width, video_height)

                # 전처리된 HTML을 임시 파일로 저장 후 로드
                temp_html = os.path.join(temp_dir, f"_render_scene_{i}.html")
                with open(temp_html, "w", encoding="utf-8") as f:
                    f.write(html_ready)
                page.goto(f"file://{temp_html}")

                # 애니메이션 일시정지 → 리소스 로드 → 재개
                page.evaluate("""() => {
                    const style = document.createElement('style');
                    style.id = '__anim_pause__';
                    style.textContent = '*, *::before, *::after { animation-play-state: paused !important; }';
                    document.head.appendChild(style);
                }""")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(1500 if i == 0 else 500)
                page.evaluate("""() => {
                    const s = document.getElementById('__anim_pause__');
                    if (s) s.remove();
                }""")

                total_frames = int(duration * fps)
                frame_interval_ms = 1000.0 / fps

                for f_idx in range(total_frames):
                    frame_path = os.path.join(frames_dir, f"frame_{global_frame:06d}.png")
                    page.screenshot(path=frame_path)
                    global_frame += 1
                    page.wait_for_timeout(int(frame_interval_ms))

            browser.close()

        if global_frame == 0:
            shutil.rmtree(temp_dir)
            return "오류: 캡처된 프레임이 없습니다."

        # FFmpeg 인코딩
        merged_video = os.path.join(temp_dir, "merged.mp4")
        ffmpeg_result = subprocess.run([
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", os.path.join(frames_dir, "frame_%06d.png"),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            merged_video
        ], capture_output=True)

        if ffmpeg_result.returncode != 0:
            shutil.rmtree(temp_dir)
            return f"FFmpeg 인코딩 오류: {ffmpeg_result.stderr.decode()}"

        # 오디오 합성 (나레이션 + BGM)
        if bgm_path:
            bgm_path = os.path.abspath(bgm_path)
        has_bgm = bgm_path and os.path.exists(bgm_path)
        has_narration = any(narration_files)

        if has_narration or has_bgm:
            from moviepy import AudioFileClip as MpAudioClip, CompositeAudioClip as MpCompositeAudioClip, VideoFileClip

            video_clip = VideoFileClip(merged_video)
            audio_layers = []

            if has_narration:
                scene_start = 0.0
                for i, sf in enumerate(scene_files):
                    dur = sf.get("duration", default_duration)
                    if i < len(narration_files) and narration_files[i]:
                        narr_path = narration_files[i]
                        if not os.path.isabs(narr_path):
                            narr_path = os.path.join(output_base, narr_path)
                        if os.path.exists(narr_path):
                            narr = MpAudioClip(narr_path)
                            narr = narr.with_start(scene_start)
                            audio_layers.append(narr)
                    scene_start += dur

            if has_bgm:
                bgm_clip = MpAudioClip(bgm_path).with_duration(video_clip.duration)
                if has_narration:
                    bgm_clip = bgm_clip.multiply_volume(0.2)
                else:
                    bgm_clip = bgm_clip.multiply_volume(0.5)
                audio_layers.append(bgm_clip)

            if audio_layers:
                final_audio = MpCompositeAudioClip(audio_layers)
                video_clip = video_clip.with_audio(final_audio)

            video_clip.write_videofile(output_path, fps=fps, codec="libx264", audio_codec="aac")
            video_clip.close()
        else:
            shutil.copy2(merged_video, output_path)

        shutil.rmtree(temp_dir)
        abs_output = os.path.abspath(output_path)
        scene_count = len(scene_files)
        total_dur = sum(sf.get("duration", default_duration) for sf in scene_files)
        return f"HTML 동영상 렌더링 완료: {abs_output}\n씬 수: {scene_count}개, 총 길이: {total_dur:.1f}초"

    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        return f"렌더링 중 오류 발생: {str(e)}"
