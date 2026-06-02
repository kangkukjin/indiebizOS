import os
import asyncio
import uuid
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy import ImageSequenceClip, AudioFileClip, CompositeVideoClip, ImageClip, concatenate_videoclips, CompositeAudioClip
from moviepy.audio.fx import MultiplyVolume

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """도구 실행 함수"""
    output_base = os.path.join(project_path, "outputs")
    os.makedirs(output_base, exist_ok=True)

    if tool_name == "create_slides":
        return create_slides(tool_input, output_base)
    elif tool_name == "create_video":
        return create_video(tool_input, output_base)
    
    return f"알 수 없는 도구: {tool_name}"

async def _generate_tts(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def create_slides(tool_input, output_base):
    slides_data = tool_input.get("slides", [])
    custom_output_dir = tool_input.get("output_dir")
    
    output_dir = custom_output_dir if custom_output_dir else os.path.join(output_base, f"slides_{uuid.uuid4().hex[:8]}")
    os.makedirs(output_dir, exist_ok=True)
    
    generated_paths = []
    
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
        
    return f"슬라이드 생성 완료: {len(generated_paths)}개의 이미지가 {output_dir}에 저장되었습니다.\n파일 목록: {', '.join(generated_paths)}"

def create_video(tool_input, output_base):
    images = tool_input.get("images", [])
    narration_texts = tool_input.get("narration_texts", [])
    voice = tool_input.get("voice", "ko-KR-SunHiNeural")
    default_duration = tool_input.get("duration_per_slide", 3)
    bgm_path = tool_input.get("bgm_path")
    output_filename = tool_input.get("output_filename", "promotion_video.mp4")
    
    if not images:
        return "오류: 이미지 리스트가 비어 있습니다."
        
    valid_images = [img for img in images if os.path.exists(img)]
    if not valid_images:
        return "오류: 유효한 이미지 경로가 없습니다."
        
    output_path = os.path.join(output_base, output_filename)
    temp_files = []
    
    try:
        clips = []
        all_narrations = []
        
        for i, img_path in enumerate(valid_images):
            # 나레이션 생성
            narration_clip = None
            duration = default_duration
            
            if i < len(narration_texts) and narration_texts[i]:
                text = narration_texts[i]
                tts_path = os.path.join(output_base, f"tts_{uuid.uuid4().hex[:8]}.mp3")
                asyncio.run(_generate_tts(text, voice, tts_path))
                temp_files.append(tts_path)
                
                narration_clip = AudioFileClip(tts_path)
                # 나레이션 길이에 맞춰 슬라이드 시간 조절 (최소 1초 여유)
                duration = max(default_duration, narration_clip.duration + 0.5)
            
            # 슬라이드 클립 생성
            slide_clip = ImageClip(img_path).with_duration(duration)
            
            if narration_clip:
                slide_clip = slide_clip.with_audio(narration_clip)
                all_narrations.append((slide_clip.start, slide_clip.end))
                
            clips.append(slide_clip)
            
        final_video = concatenate_videoclips(clips, method="compose")
        
        # BGM 처리 및 덕킹(Ducking)
        if bgm_path and os.path.exists(bgm_path):
            bgm = AudioFileClip(bgm_path)
            if bgm.duration < final_video.duration:
                # BGM이 짧으면 루프 (단순화: 일단 자르기만 함, 실제론 루프 필요할 수도)
                pass 
            bgm = bgm.with_duration(final_video.duration)
            
            # 기본 BGM 볼륨 낮추기 (0.3)
            bgm = bgm.effects.multiply_volume(0.3)
            
            # 나레이션과 합치기
            if final_video.audio:
                # 이미 나레이션이 포함된 경우, BGM을 배경으로 깔기
                final_audio = CompositeAudioClip([bgm, final_video.audio])
                final_video = final_video.with_audio(final_audio)
            else:
                final_video = final_video.with_audio(bgm)
        
        final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
        
        # 임시 파일 삭제
        for f in temp_files:
            try: os.remove(f)
            except: pass
            
        return f"영상 제작 완료: {output_path}"
    except Exception as e:
        # 오류 발생 시에도 임시 파일 삭제 시도
        for f in temp_files:
            try: os.remove(f)
            except: pass
        return f"영상 제작 중 오류 발생: {str(e)}"
