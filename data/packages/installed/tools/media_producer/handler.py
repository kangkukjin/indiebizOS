import os
import uuid
import json
import asyncio
import base64
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy import ImageSequenceClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips, ImageClip, CompositeAudioClip, afx
from jinja2 import Template

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

# HTML Templates
MODERN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    body { margin: 0; padding: 0; width: {{width|default(1280)}}px; height: {{height|default(720)}}px; overflow: hidden; font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; }
    .slide { 
        width: {{width|default(1280)}}px; height: {{height|default(720)}}px; padding: 80px; box-sizing: border-box; 
        background: {{bg_color}}; color: {{text_color}};
        display: flex; flex-direction: column; justify-content: center; position: relative;
    }
    .title { font-size: 80px; font-weight: 800; line-height: 1.1; margin-bottom: 40px; }
    .body { font-size: 36px; line-height: 1.6; opacity: 0.8; max-width: 800px; white-space: pre-wrap; }
    .image-container { 
        position: absolute; right: 80px; top: 50%; transform: translateY(-50%);
        width: 450px; height: 450px; border-radius: 30px; overflow: hidden;
        box-shadow: 0 30px 60px rgba(0,0,0,0.15);
    }
    .image-container img { width: 100%; height: 100%; object-fit: cover; }
    .accent { position: absolute; left: 80px; top: 80px; width: 60px; height: 8px; background: {{text_color}}; border-radius: 4px; }
</style>
</head>
<body>
    <div class="slide">
        <div class="accent"></div>
        <div class="title">{{title}}</div>
        <div class="body">{{body}}</div>
        {% if image_data %}
        <div class="image-container">
            <img src="{{image_data}}">
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

TECH_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    body { margin: 0; padding: 0; width: {{width|default(1280)}}px; height: {{height|default(720)}}px; overflow: hidden; font-family: 'Courier New', monospace; }
    .slide { 
        width: {{width|default(1280)}}px; height: {{height|default(720)}}px; padding: 60px; box-sizing: border-box; 
        background: #0a0a0b; color: #00f2ff;
        display: flex; flex-direction: column; border: 4px solid #00f2ff;
        background-image: radial-gradient(#1a1a1c 1px, transparent 1px); background-size: 40px 40px;
    }
    .header { font-size: 20px; opacity: 0.6; margin-bottom: 20px; display: flex; justify-content: space-between; }
    .title { font-size: 64px; font-weight: bold; text-transform: uppercase; letter-spacing: 4px; border-bottom: 2px solid #00f2ff; padding-bottom: 20px; margin-bottom: 40px; }
    .body { font-size: 28px; line-height: 1.5; color: #ffffff; white-space: pre-wrap; flex-grow: 1; }
    .image-container { 
        width: 400px; height: 300px; border: 2px solid #00f2ff; margin-top: 20px; align-self: flex-end;
    }
    .image-container img { width: 100%; height: 100%; object-fit: cover; }
</style>
</head>
<body>
    <div class="slide">
        <div class="header"><span>SYSTEM_STATUS: OPTIMIZED</span><span>ID: {{uuid_val}}</span></div>
        <div class="title">{{title}}</div>
        <div class="body">{{body}}</div>
        {% if image_data %}
        <div class="image-container"><img src="{{image_data}}"></div>
        {% endif %}
    </div>
</body>
</html>
"""

BUSINESS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    body { margin: 0; padding: 0; width: {{width|default(1280)}}px; height: {{height|default(720)}}px; overflow: hidden; font-family: 'Arial', sans-serif; }
    .slide {
        width: {{width|default(1280)}}px; height: {{height|default(720)}}px; background: white; border-top: 15px solid #1a237e;
        padding: 80px 100px; box-sizing: border-box; display: flex; flex-direction: column;
    }
    .title { font-size: 60px; color: #1a237e; font-weight: 900; margin-bottom: 60px; border-left: 10px solid #1a237e; padding-left: 30px; }
    .content-wrapper { display: flex; gap: 60px; flex: 1; }
    .body { font-size: 32px; color: #37474f; line-height: 1.6; flex: 1; white-space: pre-wrap; }
    .image-container { flex: 0.8; height: 350px; background: #f5f5f5; border: 1px solid #cfd8dc; display: flex; align-items: center; justify-content: center; }
    .image-container img { max-width: 90%; max-height: 90%; object-fit: contain; }
</style>
</head>
<body>
    <div class="slide">
        <div class="title">{{title}}</div>
        <div class="content-wrapper">
            <div class="body">{{body}}</div>
            {% if image_data %}
            <div class="image-container"><img src="{{image_data}}"></div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

# ========== 2025-2026 트렌드 기반 새 템플릿 ==========

# 공통 폰트 스택 (시스템 폰트 우선, Google Fonts 폴백)
FONT_STACK = "'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif"
FONT_STACK_MONO = "'SF Mono', 'Menlo', 'Courier New', monospace"

# 1. Bold Typography 타이틀 슬라이드 - 큰 텍스트 중심
TITLE_BOLD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
    body { margin: 0; padding: 0; width: {{width|default(1280)}}px; height: {{height|default(720)}}px; overflow: hidden; }
    .slide {
        width: {{width|default(1280)}}px; height: {{height|default(720)}}px; box-sizing: border-box;
        background: {{bg_color|default('#0f0f0f')}};
        display: flex; flex-direction: column; justify-content: center; align-items: center;
        padding: 60px;
    }
    .title {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: {{title_size|default('120')}}px; font-weight: 900;
        color: {{text_color|default('#ffffff')}};
        text-align: center; line-height: 1.1;
        max-width: 1100px;
    }
    .subtitle {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 36px; font-weight: 400;
        color: {{text_color|default('#ffffff')}}; opacity: 0.7;
        margin-top: 40px; text-align: center;
    }
    .accent-line {
        width: 120px; height: 6px;
        background: {{accent_color|default('#00E8FF')}};
        margin-top: 50px; border-radius: 3px;
    }
</style>
</head>
<body>
    <div class="slide">
        <div class="title">{{title}}</div>
        {% if body %}<div class="subtitle">{{body}}</div>{% endif %}
        <div class="accent-line"></div>
    </div>
</body>
</html>
"""

# 2. Dark Tech 다크모드 + 네온 강조
DARK_TECH_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
    body { margin: 0; padding: 0; width: {{width|default(1280)}}px; height: {{height|default(720)}}px; overflow: hidden; }
    .slide {
        width: {{width|default(1280)}}px; height: {{height|default(720)}}px; box-sizing: border-box;
        background: linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 50%, #16213e 100%);
        padding: 70px 80px; position: relative;
    }
    .grid-overlay {
        position: absolute; top: 0; left: 0; right: 0; bottom: 0;
        background-image:
            linear-gradient(rgba(0,232,255,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0,232,255,0.03) 1px, transparent 1px);
        background-size: 50px 50px;
    }
    .content { position: relative; z-index: 1; height: 100%; display: flex; flex-direction: column; }
    .top-bar {
        display: flex; justify-content: space-between; align-items: center;
        font-size: 14px; color: #00E8FF; opacity: 0.6;
        font-family: 'SF Mono', 'Menlo', 'Courier New', monospace; margin-bottom: 40px;
    }
    .title {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 64px; font-weight: 700;
        color: #ffffff;
        text-shadow: 0 0 40px rgba(0,232,255,0.3);
        margin-bottom: 30px;
    }
    .body {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 28px; line-height: 1.7;
        color: rgba(255,255,255,0.85);
        max-width: 700px; white-space: pre-wrap;
        flex-grow: 1;
    }
    .image-container {
        position: absolute; right: 80px; top: 50%; transform: translateY(-50%);
        width: 420px; height: 420px;
        border: 2px solid rgba(0,232,255,0.4);
        border-radius: 20px; overflow: hidden;
        box-shadow: 0 0 60px rgba(0,232,255,0.2);
    }
    .image-container img { width: 100%; height: 100%; object-fit: cover; }
    .neon-accent {
        position: absolute; bottom: 70px; left: 80px;
        width: 80px; height: 4px;
        background: linear-gradient(90deg, #00E8FF, #8A00FF);
        border-radius: 2px;
        box-shadow: 0 0 20px rgba(0,232,255,0.5);
    }
</style>
</head>
<body>
    <div class="slide">
        <div class="grid-overlay"></div>
        <div class="content">
            <div class="top-bar">
                <span>◆ SYSTEM ACTIVE</span>
                <span>{{uuid_val|default('00000000')}}</span>
            </div>
            <div class="title">{{title}}</div>
            <div class="body">{{body}}</div>
            {% if image_data %}
            <div class="image-container"><img src="{{image_data}}"></div>
            {% endif %}
            <div class="neon-accent"></div>
        </div>
    </div>
</body>
</html>
"""

# 3. Glassmorphism 유리 효과
GLASSMORPHISM_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
    body { margin: 0; padding: 0; width: {{width|default(1280)}}px; height: {{height|default(720)}}px; overflow: hidden; }
    .slide {
        width: {{width|default(1280)}}px; height: {{height|default(720)}}px; box-sizing: border-box;
        background: linear-gradient(135deg, {{bg_color1|default('#667eea')}} 0%, {{bg_color2|default('#764ba2')}} 100%);
        display: flex; align-items: center; justify-content: center;
        position: relative;
    }
    .blob1 {
        position: absolute; width: 400px; height: 400px;
        background: rgba(255,255,255,0.15); border-radius: 50%;
        top: -100px; left: -100px; filter: blur(60px);
    }
    .blob2 {
        position: absolute; width: 300px; height: 300px;
        background: rgba(255,255,255,0.1); border-radius: 50%;
        bottom: -50px; right: -50px; filter: blur(40px);
    }
    .glass-card {
        background: rgba(255, 255, 255, 0.15);
        backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(255, 255, 255, 0.25);
        border-radius: 30px;
        padding: 60px 70px;
        max-width: 900px; width: 85%;
        box-shadow: 0 25px 50px rgba(0,0,0,0.15);
    }
    .title {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 56px; font-weight: 700;
        color: #ffffff; margin-bottom: 30px;
        text-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    .body {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 26px; line-height: 1.8;
        color: rgba(255,255,255,0.9);
        white-space: pre-wrap;
    }
    .image-container {
        margin-top: 40px; border-radius: 20px; overflow: hidden;
        box-shadow: 0 15px 35px rgba(0,0,0,0.2);
    }
    .image-container img { width: 100%; max-height: 280px; object-fit: cover; }
</style>
</head>
<body>
    <div class="slide">
        <div class="blob1"></div>
        <div class="blob2"></div>
        <div class="glass-card">
            <div class="title">{{title}}</div>
            <div class="body">{{body}}</div>
            {% if image_data %}
            <div class="image-container"><img src="{{image_data}}"></div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

# 4. Gradient Modern 그라데이션 배경
GRADIENT_MODERN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;800&display=swap');
    body { margin: 0; padding: 0; width: {{width|default(1280)}}px; height: {{height|default(720)}}px; overflow: hidden; }
    .slide {
        width: {{width|default(1280)}}px; height: {{height|default(720)}}px; box-sizing: border-box;
        background: linear-gradient(135deg, {{bg_color1|default('#f093fb')}} 0%, {{bg_color2|default('#f5576c')}} 100%);
        padding: 80px; display: flex; flex-direction: column; justify-content: center;
    }
    .title {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 72px; font-weight: 800;
        color: #ffffff; margin-bottom: 40px;
        text-shadow: 0 4px 30px rgba(0,0,0,0.15);
    }
    .body {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 32px; line-height: 1.7;
        color: rgba(255,255,255,0.95);
        max-width: 750px; white-space: pre-wrap;
    }
    .image-container {
        position: absolute; right: 60px; bottom: 60px;
        width: 380px; height: 380px;
        border-radius: 50%; overflow: hidden;
        border: 6px solid rgba(255,255,255,0.3);
        box-shadow: 0 20px 60px rgba(0,0,0,0.2);
    }
    .image-container img { width: 100%; height: 100%; object-fit: cover; }
    .decorative-circle {
        position: absolute; right: 350px; top: 80px;
        width: 150px; height: 150px;
        border: 3px solid rgba(255,255,255,0.2);
        border-radius: 50%;
    }
</style>
</head>
<body>
    <div class="slide">
        <div class="title">{{title}}</div>
        <div class="body">{{body}}</div>
        {% if image_data %}
        <div class="image-container"><img src="{{image_data}}"></div>
        {% endif %}
        <div class="decorative-circle"></div>
    </div>
</body>
</html>
"""

# 5. Split Asymmetric 비대칭 분할
SPLIT_ASYMMETRIC_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
    body { margin: 0; padding: 0; width: {{width|default(1280)}}px; height: {{height|default(720)}}px; overflow: hidden; }
    .slide {
        width: {{width|default(1280)}}px; height: {{height|default(720)}}px; display: flex;
    }
    .left-panel {
        width: 55%; height: 100%;
        background: {{bg_color|default('#1a1a2e')}};
        padding: 80px 60px; box-sizing: border-box;
        display: flex; flex-direction: column; justify-content: center;
    }
    .right-panel {
        width: 45%; height: 100%;
        background: {{accent_color|default('#00E8FF')}};
        position: relative; overflow: hidden;
    }
    .right-panel img {
        width: 100%; height: 100%; object-fit: cover;
    }
    .right-overlay {
        position: absolute; top: 0; left: 0; right: 0; bottom: 0;
        background: linear-gradient(135deg, transparent 0%, rgba(0,0,0,0.3) 100%);
    }
    .title {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 54px; font-weight: 700;
        color: {{text_color|default('#ffffff')}};
        margin-bottom: 35px; line-height: 1.2;
    }
    .body {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 24px; line-height: 1.8;
        color: {{text_color|default('#ffffff')}}; opacity: 0.85;
        white-space: pre-wrap;
    }
    .accent-bar {
        width: 60px; height: 5px;
        background: {{accent_color|default('#00E8FF')}};
        margin-bottom: 40px; border-radius: 3px;
    }
</style>
</head>
<body>
    <div class="slide">
        <div class="left-panel">
            <div class="accent-bar"></div>
            <div class="title">{{title}}</div>
            <div class="body">{{body}}</div>
        </div>
        <div class="right-panel">
            {% if image_data %}
            <img src="{{image_data}}">
            {% endif %}
            <div class="right-overlay"></div>
        </div>
    </div>
</body>
</html>
"""

# 6. Minimal White 미니멀 화이트
MINIMAL_WHITE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;700&display=swap');
    body { margin: 0; padding: 0; width: {{width|default(1280)}}px; height: {{height|default(720)}}px; overflow: hidden; }
    .slide {
        width: {{width|default(1280)}}px; height: {{height|default(720)}}px; box-sizing: border-box;
        background: #fafafa;
        padding: 100px 120px;
        display: flex; flex-direction: column; justify-content: center;
    }
    .title {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 58px; font-weight: 700;
        color: #1a1a1a; margin-bottom: 50px;
        letter-spacing: -1px;
    }
    .body {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 26px; font-weight: 300;
        line-height: 2; color: #4a4a4a;
        max-width: 800px; white-space: pre-wrap;
    }
    .image-container {
        position: absolute; right: 100px; top: 50%; transform: translateY(-50%);
        max-width: 400px; max-height: 450px;
    }
    .image-container img {
        max-width: 100%; max-height: 450px; object-fit: contain;
        box-shadow: 0 30px 60px rgba(0,0,0,0.08);
    }
    .page-number {
        position: absolute; bottom: 50px; right: 120px;
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 14px; color: #ccc;
    }
</style>
</head>
<body>
    <div class="slide">
        <div class="title">{{title}}</div>
        <div class="body">{{body}}</div>
        {% if image_data %}
        <div class="image-container"><img src="{{image_data}}"></div>
        {% endif %}
    </div>
</body>
</html>
"""

# 7. Image Fullscreen 전체 배경 이미지 + 오버레이
IMAGE_FULLSCREEN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;900&display=swap');
    body { margin: 0; padding: 0; width: {{width|default(1280)}}px; height: {{height|default(720)}}px; overflow: hidden; }
    .slide {
        width: {{width|default(1280)}}px; height: {{height|default(720)}}px; position: relative;
    }
    .bg-image {
        position: absolute; top: 0; left: 0; width: 100%; height: 100%;
        object-fit: cover;
    }
    .overlay {
        position: absolute; top: 0; left: 0; width: 100%; height: 100%;
        background: linear-gradient(
            to bottom,
            rgba(0,0,0,{{overlay_top|default('0.3')}}) 0%,
            rgba(0,0,0,{{overlay_bottom|default('0.7')}}) 100%
        );
    }
    .content {
        position: absolute; bottom: 80px; left: 80px; right: 80px;
        z-index: 1;
    }
    .title {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 68px; font-weight: 900;
        color: #ffffff; margin-bottom: 25px;
        text-shadow: 0 4px 30px rgba(0,0,0,0.5);
        line-height: 1.15;
    }
    .body {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 28px; line-height: 1.6;
        color: rgba(255,255,255,0.9);
        max-width: 800px; white-space: pre-wrap;
        text-shadow: 0 2px 10px rgba(0,0,0,0.3);
    }
</style>
</head>
<body>
    <div class="slide">
        {% if image_data %}
        <img class="bg-image" src="{{image_data}}">
        {% else %}
        <div style="position:absolute;top:0;left:0;width:100%;height:100%;background:linear-gradient(135deg,#1a1a2e,#16213e);"></div>
        {% endif %}
        <div class="overlay"></div>
        <div class="content">
            <div class="title">{{title}}</div>
            <div class="body">{{body}}</div>
        </div>
    </div>
</body>
</html>
"""

# 8. Data Card 숫자/데이터 강조
DATA_CARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
    body { margin: 0; padding: 0; width: {{width|default(1280)}}px; height: {{height|default(720)}}px; overflow: hidden; }
    .slide {
        width: {{width|default(1280)}}px; height: {{height|default(720)}}px; box-sizing: border-box;
        background: {{bg_color|default('#0f0f0f')}};
        padding: 70px 80px;
        display: flex; flex-direction: column;
    }
    .header-title {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 42px; font-weight: 700;
        color: {{text_color|default('#ffffff')}}; margin-bottom: 50px;
    }
    .cards-container {
        display: flex; gap: 30px; flex: 1; align-items: center;
    }
    .data-card {
        flex: 1; padding: 40px;
        background: {{card_bg|default('rgba(255,255,255,0.05)')}};
        border-radius: 20px;
        border: 1px solid rgba(255,255,255,0.1);
        text-align: center;
    }
    .data-value {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 72px; font-weight: 900;
        background: linear-gradient(135deg, {{accent1|default('#00E8FF')}}, {{accent2|default('#8A00FF')}});
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 15px;
    }
    .data-label {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 22px; color: rgba(255,255,255,0.7);
    }
    .body {
        font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
        font-size: 24px; line-height: 1.7;
        color: rgba(255,255,255,0.6);
        margin-top: 40px; white-space: pre-wrap;
    }
</style>
</head>
<body>
    <div class="slide">
        <div class="header-title">{{title}}</div>
        <div class="cards-container">
            <div class="data-card">
                <div class="data-value">{{data1_value|default('100%')}}</div>
                <div class="data-label">{{data1_label|default('항목 1')}}</div>
            </div>
            <div class="data-card">
                <div class="data-value">{{data2_value|default('50+')}}</div>
                <div class="data-label">{{data2_label|default('항목 2')}}</div>
            </div>
            <div class="data-card">
                <div class="data-value">{{data3_value|default('24/7')}}</div>
                <div class="data-label">{{data3_label|default('항목 3')}}</div>
            </div>
        </div>
        {% if body %}<div class="body">{{body}}</div>{% endif %}
    </div>
</body>
</html>
"""

TEMPLATES = {
    # 기존 템플릿
    "modern": MODERN_TEMPLATE,
    "tech": TECH_TEMPLATE,
    "business": BUSINESS_TEMPLATE,
    "default": MODERN_TEMPLATE,
    # 2025-2026 트렌드 신규 템플릿
    "title_bold": TITLE_BOLD_TEMPLATE,
    "dark_tech": DARK_TECH_TEMPLATE,
    "glassmorphism": GLASSMORPHISM_TEMPLATE,
    "gradient_modern": GRADIENT_MODERN_TEMPLATE,
    "split_asymmetric": SPLIT_ASYMMETRIC_TEMPLATE,
    "minimal_white": MINIMAL_WHITE_TEMPLATE,
    "image_fullscreen": IMAGE_FULLSCREEN_TEMPLATE,
    "data_card": DATA_CARD_TEMPLATE,
    "tailwind": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Google Fonts (한국어 + 영문 디자인 폰트) -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Black+Han+Sans&family=Do+Hyeon&family=Gothic+A1:wght@400;700;900&family=Noto+Sans+KR:wght@300;400;500;700;900&family=Sunflower:wght@300;500;700&family=Jua&family=Inter:wght@300;400;500;600;700;800;900&family=Montserrat:wght@400;600;700;800;900&family=Playfair+Display:wght@400;600;700;900&family=Poppins:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <!-- 추가 라이브러리: 애니메이션, 아이콘, Lottie -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css"/>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
    <script src="https://unpkg.com/@lottiefiles/lottie-player@2/dist/lottie-player.js"></script>
    <style>
        body { margin: 0; padding: 0; width: {{width|default(1280)}}px; height: {{height|default(720)}}px; overflow: hidden; font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; }
    </style>
</head>
<body class="bg-white">
    <div class="w-[{{width|default(1280)}}px] h-[{{height|default(720)}}px] overflow-hidden">
        {{custom_html|safe if custom_html else ""}}
        {% if not custom_html %}
        <div class="flex flex-col justify-center h-full p-20 {{bg_class|default('bg-white')}}">
            <h1 class="text-7xl font-black tracking-tighter mb-8 {{title_class|default('text-slate-900')}}">{{title}}</h1>
            <p class="text-3xl leading-relaxed max-w-4xl {{body_class|default('text-slate-600')}}">{{body}}</p>
            {% if image_data %}
            <div class="mt-12 rounded-3xl overflow-hidden shadow-2xl w-2/3 border-8 border-white">
                <img src="{{image_data}}" class="w-full h-auto object-cover">
            </div>
            {% endif %}
        </div>
        {% endif %}
    </div>
    <script>
        // Lucide 아이콘 초기화 (i data-lucide="..." 태그 자동 변환)
        lucide.createIcons();
    </script>
</body>
</html>
""",
}

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """도구 실행 함수"""
    output_base = os.path.join(project_path, "outputs")
    os.makedirs(output_base, exist_ok=True)

    if tool_name == "create_slides":
        return create_slides(tool_input, output_base)
    elif tool_name == "create_html_video":
        return create_html_video(tool_input, output_base)
    elif tool_name == "render_html_to_image":
        return render_html_to_image(tool_input, output_base)
    elif tool_name == "generate_ai_image":
        return generate_ai_image(tool_input, output_base)
    elif tool_name == "generate_gemini_image":
        return generate_gemini_image(tool_input, output_base)
    elif tool_name == "create_tts":
        return create_tts(tool_input, output_base)
    elif tool_name == "render_html_video":
        return render_html_video(tool_input, output_base)
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

    return f"알 수 없는 도구: {tool_name}"

def create_slides(tool_input, output_base):
    slides_data = tool_input.get("slides", [])
    custom_output_dir = tool_input.get("output_dir")
    width = tool_input.get("width", 1280)
    height = tool_input.get("height", 720)
    
    output_dir = custom_output_dir if custom_output_dir else os.path.join(output_base, f"slides_{uuid.uuid4().hex[:8]}")
    os.makedirs(output_dir, exist_ok=True)
    
    # HTML/Playwright를 사용한 렌더링 시도
    try:
        from playwright.sync_api import sync_playwright
        generated_paths = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            
            for i, slide in enumerate(slides_data):
                theme_name = slide.get("theme", "modern")
                template_str = TEMPLATES.get(theme_name, TEMPLATES.get("default", MODERN_TEMPLATE))
                
                # 데이터 준비
                img_path = slide.get("image_path")
                abs_img_path = os.path.abspath(img_path) if img_path and os.path.exists(img_path) else None
                image_data = get_image_base64(abs_img_path) if abs_img_path else None
                
                render_data = slide.copy()
                render_data.update({
                    "image_data": image_data,
                    "uuid_val": uuid.uuid4().hex[:8],
                    "width": width,
                    "height": height
                })
                
                html = Template(template_str).render(**render_data)
                page.set_content(html)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(500)  # Tailwind/폰트 로딩 대기

                file_path = os.path.join(output_dir, f"slide_{i+1:02d}.png")
                page.screenshot(path=file_path)
                generated_paths.append(file_path)
            
            browser.close()
            
        # 절대 경로로 변환하여 반환 (에이전트 간 경로 혼동 방지)
        abs_output_dir = os.path.abspath(output_dir)
        abs_paths = [os.path.abspath(p) for p in generated_paths]
        return f"슬라이드 생성 완료 (HTML 엔진): {len(abs_paths)}개의 이미지가 {abs_output_dir}에 저장되었습니다.\n파일 목록: {', '.join(abs_paths)}"
        
    except Exception as e:
        # 실패 시 기존 Pillow 로직으로 폴백
        print(f"HTML 렌더링 실패, Pillow로 전환: {e}")
        return create_slides_pillow(slides_data, output_dir, width, height)

def create_slides_pillow(slides_data, output_dir, width=1280, height=720):
    generated_paths = []
    # 폰트 설정
    font_paths = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/NanumGothic.ttf"
    ]
    font_path = next((p for p in font_paths if os.path.exists(p)), None)
    
    for i, slide in enumerate(slides_data):
        title = slide.get("title", "")
        body = slide.get("body", "")
        bg_color = slide.get("bg_color", "#FFFFFF")
        text_color = slide.get("text_color", "#000000")
        image_path = slide.get("image_path")
        
        img = Image.new("RGB", (width, height), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        try:
            title_font = ImageFont.truetype(font_path, 60) if font_path else ImageFont.load_default()
            body_font = ImageFont.truetype(font_path, 30) if font_path else ImageFont.load_default()
        except:
            title_font = ImageFont.load_default()
            body_font = ImageFont.load_default()
            
        draw.text((100, 100), title, font=title_font, fill=text_color)
        y_text = 220
        for line in body.split('\n'):
            draw.text((100, y_text), line, font=body_font, fill=text_color)
            y_text += 45
            
        if image_path and os.path.exists(image_path):
            try:
                overlay = Image.open(image_path)
                overlay.thumbnail((int(width * 0.3), int(height * 0.5)))
                img.paste(overlay, (int(width * 0.6), int(height * 0.3)))
            except:
                pass
                
        file_path = os.path.join(output_dir, f"slide_{i+1:02d}.png")
        img.save(file_path)
        generated_paths.append(file_path)
        
    # 절대 경로로 변환하여 반환 (에이전트 간 경로 혼동 방지)
    abs_output_dir = os.path.abspath(output_dir)
    abs_paths = [os.path.abspath(p) for p in generated_paths]
    return f"슬라이드 생성 완료 (Pillow 엔진): {len(abs_paths)}개의 이미지가 {abs_output_dir}에 저장되었습니다.\n파일 목록: {', '.join(abs_paths)}"

async def generate_tts(text, output_path, voice="ko-KR-SunHiNeural"):
    communicate = edge_tts.Communicate(text, voice)
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
    output_filename = tool_input.get("output_filename", "html_video.mp4")
    video_width = tool_input.get("width", 1280)
    video_height = tool_input.get("height", 720)
    fps = tool_input.get("fps", 24)
    default_duration = tool_input.get("duration_per_scene", 5)

    if not scenes:
        return "오류: scenes 리스트가 비어 있습니다."

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
                asyncio.run(generate_tts(narration_texts[i], tts_path, voice))
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
        # 3단계: 모든 씬의 프레임을 순차적으로 캡처
        # ============================================================
        global_frame = 0

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": video_width, "height": video_height})

            for i, scene in enumerate(scenes):
                html = scene.get("html", "")
                duration = scene.get("duration", default_duration)
                # base_path: scene에 지정되지 않으면 output_base를 기본값으로 사용
                # (같은 폴더에 생성된 이미지를 자동으로 찾을 수 있도록)
                base_path_opt = scene.get("base_path") or output_base

                if not html:
                    continue

                html_ready = _prepare_scene_html(html, base_path_opt, video_width, video_height)

                # 씬 HTML을 base_path 기준 디렉토리에 저장 후 file:// 프로토콜로 로딩
                # base_path에 저장하면 상대 경로 이미지(예: "hero.png")가 같은 폴더에서 자동으로 로드됨
                # Base64 변환은 보험으로 유지 (절대 경로/상대 경로 모두 대응)
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

                # 외부 리소스(CDN, 폰트 등) 로딩 대기
                page.wait_for_load_state("networkidle")
                # 첫 씬은 폰트 다운로드가 필요하므로 넉넉하게 대기
                page.wait_for_timeout(1500 if i == 0 else 500)

                # 리소스 로딩 완료 후 애니메이션 재개 → 이제부터 캡처 시작
                page.evaluate("""() => {
                    const pauseStyle = document.getElementById('__anim_pause__');
                    if (pauseStyle) pauseStyle.remove();
                }""")

                # 이 씬에서 캡처할 프레임 수
                total_frames = int(duration * fps)
                # 프레임 간격 (ms)
                frame_interval_ms = 1000.0 / fps

                for f in range(total_frames):
                    frame_path = os.path.join(frames_dir, f"frame_{global_frame:06d}.png")
                    page.screenshot(path=frame_path)
                    global_frame += 1
                    # 다음 프레임까지 대기 (브라우저의 실시간 애니메이션 진행)
                    page.wait_for_timeout(int(frame_interval_ms))

            browser.close()

        if global_frame == 0:
            shutil.rmtree(temp_dir)
            return "오류: 캡처된 프레임이 없습니다."

        # ============================================================
        # 4단계: 프레임 시퀀스를 MP4로 인코딩
        # ============================================================
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
                scene_start = 0.0
                for i, scene in enumerate(scenes):
                    dur = scene.get("duration", default_duration)
                    if i < len(narration_audio_paths) and narration_audio_paths[i]:
                        narr = MpAudioClip(narration_audio_paths[i])
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

        # 임시 파일 정리
        shutil.rmtree(temp_dir)
        # output_base에 생성된 임시 씬 HTML 파일도 정리
        import glob
        for tmp_html in glob.glob(os.path.join(output_base, "_scene_*_*.html")):
            try:
                os.remove(tmp_html)
            except OSError:
                pass

        return f"HTML 동영상 제작 완료: {os.path.abspath(output_path)}"
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

    # output_path가 지정되면 파일명만 추출하여 output_base에 저장
    if output_path:
        filename = os.path.basename(output_path)
        output_path = os.path.join(output_base, filename)
    else:
        output_path = os.path.join(output_base, f"gemini_image_{uuid.uuid4().hex[:8]}.png")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    model = "gemini-2.5-flash-image"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
            "imageConfig": {
                "aspectRatio": aspect_ratio
            }
        }
    }

    try:
        with httpx.Client(timeout=120.0) as client:
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

        result = f"Gemini 이미지 생성 완료: {os.path.abspath(output_path)}\n프롬프트: {prompt}"
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
    output_filename = tool_input.get("output_filename")

    if output_filename:
        output_path = os.path.join(output_base, os.path.basename(output_filename))
    else:
        output_path = os.path.join(output_base, f"tts_{uuid.uuid4().hex[:8]}.mp3")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    try:
        asyncio.run(generate_tts(text, output_path, voice))

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
