"""
안드로이드 스크린샷 좌표 캘리브레이션 도구
- 스크린샷 위에 좌표 그리드를 오버레이
- 터치 좌표를 정확히 파악할 수 있게 도움
"""
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO


def capture_with_grid(
    grid_spacing: int = 200,
    output_path: str = "/tmp/android_calibrated.png",
    show_crosshair: bool = True,
):
    """스크린샷을 찍고 좌표 그리드를 오버레이한다."""
    # adb screencap
    result = subprocess.run(
        ["adb", "exec-out", "screencap", "-p"],
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        print(f"스크린샷 실패: {result.stderr.decode()}")
        return None

    img = Image.open(BytesIO(result.stdout))
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size

    # 반투명 그리드 라인
    line_color = (255, 0, 0, 80)
    text_color = (255, 0, 0, 200)
    bg_color = (255, 255, 255, 160)

    # 폰트 (기본 폰트 사용)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    except Exception:
        font = ImageFont.load_default()

    # 세로선 + x좌표 라벨
    for x in range(0, w, grid_spacing):
        draw.line([(x, 0), (x, h)], fill=line_color, width=2)
        label = str(x)
        bbox = font.getbbox(label)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.rectangle([x + 2, 2, x + tw + 8, th + 8], fill=bg_color)
        draw.text((x + 4, 2), label, fill=text_color, font=font)

    # 가로선 + y좌표 라벨
    for y in range(0, h, grid_spacing):
        draw.line([(0, y), (w, y)], fill=line_color, width=2)
        label = str(y)
        bbox = font.getbbox(label)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.rectangle([2, y + 2, tw + 8, y + th + 8], fill=bg_color)
        draw.text((4, y + 2), label, fill=text_color, font=font)

    # 중앙 십자선
    if show_crosshair:
        cx, cy = w // 2, h // 2
        draw.line([(cx - 30, cy), (cx + 30, cy)], fill=(0, 255, 0, 150), width=3)
        draw.line([(cx, cy - 30), (cx, cy + 30)], fill=(0, 255, 0, 150), width=3)
        label = f"center({cx},{cy})"
        draw.text((cx + 5, cy + 5), label, fill=(0, 255, 0, 200), font=font)

    # 해상도 표시
    info = f"{w}x{h}"
    draw.text((w - 200, h - 40), info, fill=text_color, font=font)

    img.save(output_path)
    print(f"캘리브레이션 이미지 저장: {output_path} ({w}x{h})")
    return output_path


if __name__ == "__main__":
    spacing = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    output = sys.argv[2] if len(sys.argv) > 2 else "/tmp/android_calibrated.png"
    capture_with_grid(grid_spacing=spacing, output_path=output)
