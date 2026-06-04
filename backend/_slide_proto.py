"""자유형 HTML 슬라이드 프로토타입 — 주제+내용 → 이미지 생성 + 맞춤 HTML + PNG 렌더.
(기층 슬라이드 액션의 '출력'을 손으로 시연. 실제 액션은 경량 LLM이 이 작곡을 대신함.)
"""
import os, sys, json, base64, uuid
BASE = "/Users/kangkukjin/Desktop/AI/indiebizOS"
sys.path.insert(0, os.path.join(BASE, "data/packages/installed/tools/media_producer"))
OUT = os.path.join(BASE, "outputs/slide_proto")
os.makedirs(OUT, exist_ok=True)

# 1) gemini 키
key = json.load(open(os.path.join(BASE, "data/system_ai_config.json")))["apiKey"]

# 2) 이미지 생성
import handler
img_prompt = (
    "Minimal editorial conceptual illustration for a physics lecture slide: a delicate glass "
    "vessel shattering and dispersing into a fine stream of particles flowing toward the right, "
    "evoking the irreversible arrow of time and rising entropy. Warm off-white paper background, "
    "deep ink-navy forms with a single muted amber accent, elegant, lots of negative space, "
    "soft paper grain, restrained, sophisticated, no text, no letters."
)
print("이미지 생성 중...")
res = handler.generate_gemini_image(
    {"prompt": img_prompt, "api_key": key, "aspect_ratio": "3:4", "image_size": "2K",
     "output_path": "entropy.png"}, OUT)
print(res[:120])
img_path = os.path.join(OUT, "entropy.png")
img_b64 = ""
if os.path.exists(img_path):
    with open(img_path, "rb") as f:
        img_b64 = "data:image/png;base64," + base64.b64encode(f.read()).decode()

# 3) 자유형 HTML (1280x720) — 에디토리얼 split 레이아웃
img_block = (f'<img src="{img_b64}" class="w-full h-full object-cover"/>'
             if img_b64 else '<div class="w-full h-full" style="background:linear-gradient(135deg,#1e293b,#c2632c)"></div>')

html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<script src="https://cdn.tailwindcss.com"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@500;700;900&family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root {{ --paper:#f6f1e9; --ink:#1d2433; --muted:#5b6472; --amber:#c2632c; --line:#d9cfbf; }}
  * {{ box-sizing:border-box; }}
  .serif {{ font-family:'Noto Serif KR',serif; }}
  .sans  {{ font-family:'Noto Sans KR',sans-serif; }}
  .grain:after {{ content:''; position:absolute; inset:0; pointer-events:none;
     background-image:radial-gradient(rgba(0,0,0,.035) 1px,transparent 1px); background-size:4px 4px; }}
</style></head>
<body class="grain" style="width:1280px;height:720px;background:var(--paper);position:relative;overflow:hidden">
  <div class="flex h-full">
    <!-- 좌: 텍스트 -->
    <div class="sans" style="width:56%;padding:72px 56px 56px 80px;display:flex;flex-direction:column;justify-content:center">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:22px">
        <span style="width:34px;height:3px;background:var(--amber);display:inline-block"></span>
        <span style="font-weight:700;letter-spacing:.18em;font-size:13px;color:var(--amber)">열역학 제2법칙</span>
      </div>
      <h1 class="serif" style="font-weight:900;font-size:54px;line-height:1.12;color:var(--ink);margin:0 0 26px">
        엔트로피와<br>시간의 화살</h1>
      <p style="font-size:19px;line-height:1.75;color:var(--muted);margin:0 0 30px;max-width:30em">
        미시 세계의 물리 법칙은 시간에 대칭이다. 그런데 왜 시간은 한 방향으로만 흐르는가?
        답은 <b style="color:var(--ink)">엔트로피</b> — 무질서가 통계적으로 거의 항상 증가하기 때문이다.</p>
      <div style="display:flex;flex-direction:column;gap:14px">
        <div style="display:flex;gap:14px;align-items:flex-start">
          <span style="margin-top:7px;width:7px;height:7px;border-radius:50%;background:var(--amber);flex:none"></span>
          <span style="font-size:16.5px;line-height:1.6;color:var(--ink)">깨진 컵은 스스로 다시 합쳐지지 않는다 — <span style="color:var(--muted)">비가역성</span></span>
        </div>
        <div style="display:flex;gap:14px;align-items:flex-start">
          <span style="margin-top:7px;width:7px;height:7px;border-radius:50%;background:var(--amber);flex:none"></span>
          <span style="font-size:16.5px;line-height:1.6;color:var(--ink)">질서 잡힌 배열은 드물고, 흐트러진 배열은 압도적으로 많다</span>
        </div>
        <div style="display:flex;gap:14px;align-items:flex-start">
          <span style="margin-top:7px;width:7px;height:7px;border-radius:50%;background:var(--amber);flex:none"></span>
          <span style="font-size:16.5px;line-height:1.6;color:var(--ink)">초기 우주의 <span style="color:var(--muted)">낮은 엔트로피</span>가 시간의 방향을 정했다</span>
        </div>
      </div>
      <div style="margin-top:auto;padding-top:34px;font-size:12.5px;color:#9aa1ac;letter-spacing:.04em">
        IndieBiz OS · 슬라이드 기층 프로토타입 · 자유형 HTML + 생성 이미지</div>
    </div>
    <!-- 우: 이미지 -->
    <div style="width:44%;position:relative;padding:28px 28px 28px 0">
      <div style="position:relative;width:100%;height:100%;border-radius:14px;overflow:hidden;
           box-shadow:0 24px 60px -20px rgba(29,36,51,.45);border:1px solid var(--line)">
        {img_block}
        <div style="position:absolute;inset:0;background:linear-gradient(180deg,transparent 55%,rgba(29,36,51,.28))"></div>
        <div class="serif" style="position:absolute;left:22px;bottom:18px;color:#f6f1e9;font-size:15px;
             font-weight:700;text-shadow:0 1px 6px rgba(0,0,0,.4)">"시간은 엔트로피가 가리키는 쪽으로 흐른다"</div>
      </div>
    </div>
  </div>
</body></html>"""

# 4) 렌더
print("렌더 중...")
r = handler.render_html_to_image({"html": html, "output_path": "slide_entropy.png",
                                  "width": 1280, "height": 720}, OUT)
print(r[:160])
print("최종:", os.path.join(OUT, "slide_entropy.png"))
