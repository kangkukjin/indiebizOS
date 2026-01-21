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
    body { margin: 0; padding: 0; width: 1280px; height: 720px; overflow: hidden; font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; }
    .slide { 
        width: 1280px; height: 720px; padding: 80px; box-sizing: border-box; 
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
    body { margin: 0; padding: 0; width: 1280px; height: 720px; overflow: hidden; font-family: 'Courier New', monospace; }
    .slide { 
        width: 1280px; height: 720px; padding: 60px; box-sizing: border-box; 
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
    body { margin: 0; padding: 0; width: 1280px; height: 720px; overflow: hidden; font-family: 'Arial', sans-serif; }
    .slide {
        width: 1280px; height: 720px; background: white; border-top: 15px solid #1a237e;
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
    body { margin: 0; padding: 0; width: 1280px; height: 720px; overflow: hidden; }
    .slide {
        width: 1280px; height: 720px; box-sizing: border-box;
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
    body { margin: 0; padding: 0; width: 1280px; height: 720px; overflow: hidden; }
    .slide {
        width: 1280px; height: 720px; box-sizing: border-box;
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
    body { margin: 0; padding: 0; width: 1280px; height: 720px; overflow: hidden; }
    .slide {
        width: 1280px; height: 720px; box-sizing: border-box;
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
    body { margin: 0; padding: 0; width: 1280px; height: 720px; overflow: hidden; }
    .slide {
        width: 1280px; height: 720px; box-sizing: border-box;
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
    body { margin: 0; padding: 0; width: 1280px; height: 720px; overflow: hidden; }
    .slide {
        width: 1280px; height: 720px; display: flex;
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
    body { margin: 0; padding: 0; width: 1280px; height: 720px; overflow: hidden; }
    .slide {
        width: 1280px; height: 720px; box-sizing: border-box;
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
    body { margin: 0; padding: 0; width: 1280px; height: 720px; overflow: hidden; }
    .slide {
        width: 1280px; height: 720px; position: relative;
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
    body { margin: 0; padding: 0; width: 1280px; height: 720px; overflow: hidden; }
    .slide {
        width: 1280px; height: 720px; box-sizing: border-box;
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
}

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """도구 실행 함수"""
    output_base = os.path.join(project_path, "outputs")
    os.makedirs(output_base, exist_ok=True)

    if tool_name == "create_slides":
        return create_slides(tool_input, output_base)
    elif tool_name == "create_video":
        return create_video(tool_input, output_base)
    elif tool_name == "render_html_to_image":
        return render_html_to_image(tool_input)
    elif tool_name == "generate_ai_image":
        return generate_ai_image(tool_input, output_base)

    return f"알 수 없는 도구: {tool_name}"

def create_slides(tool_input, output_base):
    slides_data = tool_input.get("slides", [])
    custom_output_dir = tool_input.get("output_dir")
    
    output_dir = custom_output_dir if custom_output_dir else os.path.join(output_base, f"slides_{uuid.uuid4().hex[:8]}")
    os.makedirs(output_dir, exist_ok=True)
    
    # HTML/Playwright를 사용한 렌더링 시도
    try:
        from playwright.sync_api import sync_playwright
        generated_paths = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            
            for i, slide in enumerate(slides_data):
                theme_name = slide.get("theme", "modern")
                template_str = TEMPLATES.get(theme_name, MODERN_TEMPLATE)
                
                # 데이터 준비
                img_path = slide.get("image_path")
                abs_img_path = os.path.abspath(img_path) if img_path and os.path.exists(img_path) else None
                image_data = get_image_base64(abs_img_path) if abs_img_path else None
                
                render_data = {
                    "title": slide.get("title", ""),
                    "body": slide.get("body", ""),
                    "bg_color": slide.get("bg_color", "#FFFFFF"),
                    "text_color": slide.get("text_color", "#000000"),
                    "image_data": image_data,
                    "uuid_val": uuid.uuid4().hex[:8]
                }
                
                html = Template(template_str).render(**render_data)
                page.set_content(html)
                
                file_path = os.path.join(output_dir, f"slide_{i+1:02d}.png")
                page.screenshot(path=file_path)
                generated_paths.append(file_path)
            
            browser.close()
            
        return f"슬라이드 생성 완료 (HTML 엔진): {len(generated_paths)}개의 이미지가 {output_dir}에 저장되었습니다.\n파일 목록: {', '.join(generated_paths)}"
        
    except Exception as e:
        # 실패 시 기존 Pillow 로직으로 폴백
        print(f"HTML 렌더링 실패, Pillow로 전환: {e}")
        return create_slides_pillow(slides_data, output_dir)

def create_slides_pillow(slides_data, output_dir):
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
        
        img = Image.new("RGB", (1280, 720), color=bg_color)
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
                overlay.thumbnail((400, 400))
                img.paste(overlay, (800, 200))
            except:
                pass
                
        file_path = os.path.join(output_dir, f"slide_{i+1:02d}.png")
        img.save(file_path)
        generated_paths.append(file_path)
        
    return f"슬라이드 생성 완료 (Pillow 엔진): {len(generated_paths)}개의 이미지가 {output_dir}에 저장되었습니다.\n파일 목록: {', '.join(generated_paths)}"

async def generate_tts(text, output_path, voice="ko-KR-SunHiNeural"):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def create_video(tool_input, output_base):
    images = tool_input.get("images", [])
    narration_texts = tool_input.get("narration_texts", [])
    duration_per_slide = tool_input.get("duration_per_slide", 3)
    bgm_path = tool_input.get("bgm_path")
    voice = tool_input.get("voice", "ko-KR-SunHiNeural")
    output_filename = tool_input.get("output_filename", "promotion_video.mp4")
    video_width = tool_input.get("width", 1280)
    video_height = tool_input.get("height", 720)

    if not images:
        return "오류: 이미지 리스트가 비어 있습니다."

    valid_images = [img for img in images if os.path.exists(img)]
    if not valid_images:
        return "오류: 유효한 이미지 경로가 없습니다."

    output_path = os.path.join(output_base, output_filename)
    temp_dir = os.path.join(output_base, f"temp_{uuid.uuid4().hex[:8]}")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        clips = []
        audio_clips = []

        for i, img_path in enumerate(valid_images):
            # 나레이션 처리
            slide_audio = None
            slide_duration = duration_per_slide

            if i < len(narration_texts) and narration_texts[i]:
                tts_path = os.path.join(temp_dir, f"narration_{i}.mp3")
                asyncio.run(generate_tts(narration_texts[i], tts_path, voice))
                slide_audio = AudioFileClip(tts_path)
                slide_duration = slide_audio.duration + 0.5 # 약간의 여유

            # 이미지를 정확한 비디오 크기로 리사이즈하여 클립 생성
            img = Image.open(img_path)

            # 이미지가 비디오 크기와 다르면 리사이즈 (비율 유지하며 중앙 크롭 또는 패딩)
            if img.size != (video_width, video_height):
                # 비율 유지하며 비디오 크기에 맞게 조정 (배경색으로 패딩)
                resized_img = Image.new("RGB", (video_width, video_height), (0, 0, 0))

                # 비율 계산
                img_ratio = img.width / img.height
                target_ratio = video_width / video_height

                if img_ratio > target_ratio:
                    # 이미지가 더 넓음 - 너비 기준 맞춤
                    new_width = video_width
                    new_height = int(video_width / img_ratio)
                else:
                    # 이미지가 더 높음 - 높이 기준 맞춤
                    new_height = video_height
                    new_width = int(video_height * img_ratio)

                img_resized = img.resize((new_width, new_height), Image.LANCZOS)

                # 중앙 배치
                x_offset = (video_width - new_width) // 2
                y_offset = (video_height - new_height) // 2
                resized_img.paste(img_resized, (x_offset, y_offset))

                # 임시 파일로 저장
                temp_img_path = os.path.join(temp_dir, f"resized_{i}.png")
                resized_img.save(temp_img_path)
                img_clip = ImageClip(temp_img_path).with_duration(slide_duration)
            else:
                img_clip = ImageClip(img_path).with_duration(slide_duration)

            if slide_audio:
                img_clip = img_clip.with_audio(slide_audio)

            clips.append(img_clip)

        # 클립 합치기 - 모든 이미지가 동일 크기이므로 method 불필요
        final_video = concatenate_videoclips(clips)
        
        # 배경음악 추가
        if bgm_path and os.path.exists(bgm_path):
            bgm = AudioFileClip(bgm_path).with_duration(final_video.duration)
            # 나레이션이 있을 경우 BGM 볼륨 조절 (더킹)
            if narration_texts:
                bgm = bgm.multiply_volume(0.2) # 나레이션이 주가 되도록 배경음은 작게
            else:
                bgm = bgm.multiply_volume(0.5)
            
            if final_video.audio:
                final_audio = CompositeAudioClip([bgm, final_video.audio])
            else:
                final_audio = bgm
            final_video = final_video.with_audio(final_audio)
            
        final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
        
        # 임시 파일 삭제 (선택 사항)
        import shutil
        shutil.rmtree(temp_dir)
        
        return f"영상 제작 완료: {output_path}"
    except Exception as e:
        return f"영상 제작 중 오류 발생: {str(e)}"

def render_html_to_image(tool_input):
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

    if not html or not output_path:
        return "오류: html과 output_path는 필수입니다."

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

            page.set_content(html)

            # 이미지 로딩 대기
            page.wait_for_load_state("networkidle")

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
        return f"렌더링 완료: {output_path}"
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
    if not output_path:
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
        return f"AI 이미지 생성 완료: {output_path}\n프롬프트: {prompt}"
    except Exception as e:
        return f"이미지 생성 중 오류 발생: {str(e)}"
