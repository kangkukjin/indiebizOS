"""프리미엄 이미지 슬라이드 — 개념 일러스트(Nano Banana Pro) + 또렷한 타이포 레이어.

[engines:slide]{style: ink_blueprint|cinematic_3d|isometric|lineart_duotone} 경로.
흐름: 저작 AI(구성 선택 + 제목/장면/필드) → Gemini 이미지 생성 → style×composition 합성.

구성 아키타입(6): diptych(좌우대비) / hero(선언) / side_panel(설명) / center_anchor(중심상징)
                  / annotated(주석도면) / process(3단 흐름). (스타일 4) × (구성 6) = 24 조합.
"""
import os, re, json, base64, importlib.util, sys

import httpx


def _load_styles():
    path = os.path.join(os.path.dirname(__file__), "slide_styles.py")
    spec = importlib.util.spec_from_file_location("slide_styles", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["slide_styles"] = mod
    spec.loader.exec_module(mod)
    return mod


def _system_ai_config() -> dict:
    from runtime_utils import get_base_path
    p = get_base_path() / "data" / "system_ai_config.json"
    if p.exists():
        return json.load(open(p, encoding="utf-8"))
    return {"provider": "anthropic", "model": "", "apiKey": ""}


# ── 저작 시스템 프롬프트 ───────────────────────────────────────────
_AUTHOR_PROMPT = """당신은 프리미엄 일러스트 슬라이드 한 장을 설계하는 아트디렉터 AI다. JSON 한 객체만 출력한다.

# 원칙
- **제목 = 명제** (제목만 봐도 핵심을 얻는 단정문, 챕터명·라벨 금지). 한 슬라이드 = 한 아이디어.
- 일러스트는 **개념을 시각화**한다 — 장식이 아니라 은유/구조/관계로 의미를 나른다.

# 1) 구성(composition) 선택 — 내용에 맞는 하나
- "diptych" 좌우 대비(A→B, 전/후, 우리/경쟁). 필드: captions[2]{lab,txt}.
- "hero" 강한 선언 한 문장 + 분위기 일러스트(표지·임팩트). 필드: subtitle.
- "side_panel" 일러스트 + 설명 컬럼(개념 풀이). 필드: bullets[2~3] 또는 body(1~2문장).
- "center_anchor" 중앙의 단일 상징 + 위 제목/아래 부제(부 도입·핵심상징). 필드: subtitle.
- "annotated" 한 대상의 부위를 라벨로 설명(해부/구조). 필드: labels[2~4]{x,y,lab,txt} (x,y는 이미지상 0~100 위치).
- "process" 좌→우 3단계 흐름. 필드: steps[3]{lab,txt}.

# 2) scene (영어, 일러스트가 그릴 장면) — 핵심
- 개념의 은유/다이어그램을 **구체 사물·관계**로. 아트 스타일·색·폰트는 쓰지 말 것(스타일은 따로 입힘).
- **구성별 여백 지시를 scene에 꼭 포함**(글자 들어갈 자리):
  - diptych/annotated/process → "leave the top third empty"
  - hero → "leave the lower-left area empty and calm"
  - side_panel → "place the subject on the RIGHT half, leave the LEFT half empty"
  - center_anchor → "a single centered subject with generous empty margin all around"
- process는 "three stages left to right, evenly spaced in one scene".

# 3) 공통 필드
- "composition": 위 6 중 하나
- "title": 한글 명제 (18~30자)
- "kicker": 짧은 라벨 (예: "PART 1 · 하네스란")
- "reasoning": 한 줄

# 예시 (diptych)
{"composition":"diptych","title":"AI 모델만으로는 세계를 만날 수 없다","kicker":"PART 1 · 하네스란",
 "scene":"Left: an isolated brain with a dotted line toward an apple it cannot grasp. Right: the same brain extended by a mechanical arm grasping the apple. Leave the top third empty.",
 "captions":[{"lab":"뇌 — 모델","txt":"압축된 보편 지식, 팔이 없으면 문제조차 정의 못 한다."},
             {"lab":"몸 — 하네스","txt":"도구·감각·기억을 연결해 세계의 사과에 닿는다."}],
 "reasoning":"대비 개념"}
# 예시 (side_panel)
{"composition":"side_panel","title":"하네스는 모델을 세계에 연결한다","kicker":"개념",
 "scene":"A glowing model core on the right connected by elegant conduits to tools, memory and sensors. Place the subject on the RIGHT half, leave the LEFT half empty.",
 "bullets":["눈 = 파일 읽기/쓰기","팔 = 도구 실행","기억 = 맥락 유지"],"reasoning":"개념 풀이"}
"""


def _get_ai():
    cfg = _system_ai_config()
    api_key = (cfg.get("apiKey") or "").strip()
    if not api_key:
        raise RuntimeError("시스템 AI API 키가 없습니다 (설정 → 시스템 AI).")
    from providers import get_provider
    prov = get_provider((cfg.get("provider") or "anthropic").strip(), api_key=api_key,
                        model=(cfg.get("model") or "").strip(), system_prompt=_AUTHOR_PROMPT, tools=[])
    prov.init_client()
    return prov


def _extract_json(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    cand = m.group(1) if m else None
    if cand is None:
        a, b = text.find("{"), text.rfind("}")
        if a == -1 or b <= a:
            raise ValueError("JSON 없음: " + text[:200])
        cand = text[a:b + 1]
    return json.loads(cand)


def _gen_image(scene_prompt: str, out_path: str, quality: str = "pro"):
    cfg = _system_ai_config()
    api_key = (cfg.get("apiKey") or "").strip()
    model = {"pro": "gemini-3-pro-image-preview", "fast": "gemini-3.1-flash-image-preview"}.get(quality, "gemini-3-pro-image-preview")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {"contents": [{"parts": [{"text": scene_prompt}]}],
               "generationConfig": {"responseModalities": ["IMAGE", "TEXT"],
                                    "imageConfig": {"aspectRatio": "16:9", "imageSize": "2K"}}}
    with httpx.Client(timeout=300.0) as c:
        r = c.post(url, params={"key": api_key}, json=payload, headers={"Content-Type": "application/json"})
        r.raise_for_status()
        data = r.json()
    for part in data["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            open(out_path, "wb").write(base64.b64decode(part["inlineData"]["data"]))
            return out_path
    raise RuntimeError(f"이미지 생성 실패: {json.dumps(data)[:300]}")


def _b64(path: str) -> str:
    ext = os.path.splitext(path)[1].lstrip(".").replace("jpg", "jpeg") or "png"
    return f"data:image/{ext};base64," + base64.b64encode(open(path, "rb").read()).decode()


def _esc(s) -> str:
    return str(s or "").replace("<", "&lt;").replace(">", "&gt;")


# ── 합성 셸 + 구성별 합성 함수 ──────────────────────────────────────
def _wrap(st: dict, inner: str, extra_css: str) -> str:
    links = "".join(f'<link rel="stylesheet" href="{l}">' for l in st["font_links"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">{links}<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1280px;height:720px;overflow:hidden;background:{st['bg']};font-family:'Pretendard Variable','Noto Sans KR',sans-serif}}
.stage{{position:relative;width:1280px;height:720px;overflow:hidden}}
.bg{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.kick{{font-family:'JetBrains Mono',monospace;font-size:13px;letter-spacing:0.30em;text-transform:uppercase;color:{st['kicker_color']}}}
.title{{font-family:{st['title_font']};font-weight:{st['title_weight']};color:{st['title_color']};letter-spacing:-0.025em;line-height:1.1;word-break:keep-all}}
.foot{{position:absolute;right:26px;bottom:14px;font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:0.16em;color:{st['sub_color']};opacity:0.55;z-index:20}}
{extra_css}
</style></head><body><div class="stage">{inner}<div class="foot">indiebiz · os</div></div></body></html>"""


def _fades(st):
    f = st["fade"]
    top = f"<div style='position:absolute;top:0;left:0;right:0;height:250px;background:linear-gradient(180deg,rgba({f},0.97),rgba({f},0.80) 46%,rgba({f},0))'></div>"
    bot = f"<div style='position:absolute;bottom:0;left:0;right:0;height:185px;background:linear-gradient(0deg,rgba({f},0.95),rgba({f},0))'></div>"
    return top, bot


def _comp_diptych(spec, st, img):
    top, bot = _fades(st)
    caps = spec.get("captions") or [{}, {}]
    css = """.t{position:absolute;top:48px;left:0;right:0;text-align:center}
.h{position:absolute;top:78px;left:80px;right:80px;text-align:center;font-size:56px}
.caps{position:absolute;bottom:40px;left:84px;right:84px;display:flex;justify-content:space-between;align-items:flex-end}
.cap{width:45%}.cap.r{text-align:right}.lab{font-weight:900;font-size:21px;margin-bottom:5px}
.tx{font-size:15px;line-height:1.5;word-break:keep-all}"""
    sub = st["sub_color"]
    inner = f"""<img class="bg" src="{img}">{top}{bot}
<div class="t kick">{_esc(spec.get('kicker'))}</div><div class="h title">{_esc(spec.get('title'))}</div>
<div class="caps">
<div class="cap"><div class="lab" style="color:{st['title_color']}">{_esc(caps[0].get('lab'))}</div><div class="tx" style="color:{sub}">{_esc(caps[0].get('txt'))}</div></div>
<div class="cap r"><div class="lab" style="color:{st['kicker_color']}">{_esc(caps[1].get('lab'))}</div><div class="tx" style="color:{sub}">{_esc(caps[1].get('txt'))}</div></div>
</div>"""
    return _wrap(st, inner, css)


def _comp_hero(spec, st, img):
    f = st["fade"]
    scrim = f"<div style='position:absolute;inset:0;background:linear-gradient(105deg,rgba({f},0.93) 0%,rgba({f},0.66) 34%,rgba({f},0.08) 62%,rgba({f},0) 100%),linear-gradient(0deg,rgba({f},0.82),rgba({f},0) 46%)'></div>"
    css = f""".c{{position:absolute;left:84px;bottom:104px;right:520px}}
.rule{{width:54px;height:3px;background:{st['kicker_color']};border-radius:2px;margin-bottom:24px}}
.c .kick{{margin-bottom:20px}}.c .h{{font-size:72px;margin-bottom:0}}
.sub{{margin-top:24px;font-size:21px;line-height:1.6;color:{st['sub_color']};max-width:560px;word-break:keep-all}}"""
    inner = f"""<img class="bg" src="{img}">{scrim}
<div class="c"><div class="rule"></div><div class="kick">{_esc(spec.get('kicker'))}</div>
<div class="h title">{_esc(spec.get('title'))}</div>
<div class="sub">{_esc(spec.get('subtitle'))}</div></div>"""
    return _wrap(st, inner, css)


def _comp_side_panel(spec, st, img):
    f = st["fade"]
    panel = f"<div style='position:absolute;top:0;left:0;bottom:0;width:560px;background:linear-gradient(90deg,rgba({f},0.97) 0%,rgba({f},0.93) 62%,rgba({f},0) 100%)'></div>"
    bullets = spec.get("bullets")
    if isinstance(bullets, list) and bullets:
        body = "".join(f"<li style='display:flex;gap:12px;margin-bottom:16px'><span style='color:{st['kicker_color']};font-weight:800'>—</span><span>{_esc(b)}</span></li>" for b in bullets[:4])
        body = f"<ul style='list-style:none;font-size:21px;line-height:1.4'>{body}</ul>"
    else:
        body = f"<p style='font-size:21px;line-height:1.7;color:{st['sub_color']};word-break:keep-all'>{_esc(spec.get('body'))}</p>"
    css = f""".pc{{position:absolute;top:0;left:84px;width:470px;height:100%;display:flex;flex-direction:column;justify-content:center}}
.pc .kick{{margin-bottom:18px}}.pc .h{{font-size:48px;margin-bottom:28px}}
.pc ul li, .pc{{color:{st['title_color']}}}"""
    inner = f"""<img class="bg" src="{img}">{panel}
<div class="pc"><div class="kick">{_esc(spec.get('kicker'))}</div>
<div class="h title">{_esc(spec.get('title'))}</div>{body}</div>"""
    return _wrap(st, inner, css)


def _comp_center_anchor(spec, st, img):
    top, bot = _fades(st)
    css = """.t{position:absolute;top:52px;left:0;right:0;text-align:center}
.h{position:absolute;top:84px;left:120px;right:120px;text-align:center;font-size:54px}
.sub{position:absolute;bottom:62px;left:0;right:0;text-align:center;font-size:21px;line-height:1.5;padding:0 200px;word-break:keep-all}"""
    inner = f"""<img class="bg" src="{img}">{top}{bot}
<div class="t kick">{_esc(spec.get('kicker'))}</div><div class="h title">{_esc(spec.get('title'))}</div>
<div class="sub" style="color:{st['sub_color']}">{_esc(spec.get('subtitle'))}</div>"""
    return _wrap(st, inner, css)


def _comp_annotated(spec, st, img):
    top, _ = _fades(st)
    labels = spec.get("labels") or []
    fade = st["fade"]
    border = "rgba(255,255,255,0.16)" if st["dark"] else "rgba(20,30,50,0.10)"
    chips = ""
    for lb in labels[:4]:
        try:
            x = max(8, min(92, float(lb.get("x", 50))))
            y = max(26, min(80, float(lb.get("y", 50))))
        except Exception:
            x, y = 50, 50
        right = x >= 50
        pos = f"right:{100 - x:.1f}%" if right else f"left:{x:.1f}%"
        ta = "right" if right else "left"
        dot = (f"<span style='display:inline-block;width:8px;height:8px;border-radius:50%;"
               f"background:{st['kicker_color']};box-shadow:0 0 8px {st['kicker_color']};flex:none'></span>")
        head = (f"<div style='display:flex;align-items:center;gap:8px;"
                f"{'flex-direction:row-reverse' if right else ''}'>{dot}"
                f"<span style='font-weight:800;font-size:17px;color:{st['title_color']}'>{_esc(lb.get('lab'))}</span></div>")
        chips += (
            f"<div style='position:absolute;{pos};top:{y:.1f}%;transform:translateY(-50%);max-width:250px;"
            f"text-align:{ta};background:rgba({fade},0.90);border:1px solid {border};border-radius:11px;"
            f"padding:11px 14px;box-shadow:0 12px 30px -14px rgba(0,0,0,0.5);"
            f"-webkit-backdrop-filter:blur(7px);backdrop-filter:blur(7px)'>{head}"
            f"<div style='font-size:13.5px;line-height:1.45;color:{st['sub_color']};margin-top:5px;"
            f"word-break:keep-all'>{_esc(lb.get('txt'))}</div></div>")
    css = """.t{position:absolute;top:48px;left:0;right:0;text-align:center}
.h{position:absolute;top:78px;left:90px;right:90px;text-align:center;font-size:50px}"""
    inner = f"""<img class="bg" src="{img}">{top}
<div class="t kick">{_esc(spec.get('kicker'))}</div><div class="h title">{_esc(spec.get('title'))}</div>{chips}"""
    return _wrap(st, inner, css)


def _comp_process(spec, st, img):
    top, bot = _fades(st)
    steps = spec.get("steps") or []
    cols = ""
    for i, s in enumerate(steps[:3]):
        arrow = f"<div style='position:absolute;left:-22px;top:6px;color:{st['kicker_color']};font-size:24px'>→</div>" if i > 0 else ""
        cols += (f"<div style='position:relative;flex:1;padding:0 14px'>{arrow}"
                 f"<div style='font-family:JetBrains Mono,monospace;font-size:13px;color:{st['kicker_color']};margin-bottom:6px'>0{i+1}</div>"
                 f"<div style='font-weight:900;font-size:22px;color:{st['title_color']};margin-bottom:6px'>{_esc(s.get('lab'))}</div>"
                 f"<div style='font-size:15px;line-height:1.5;color:{st['sub_color']};word-break:keep-all'>{_esc(s.get('txt'))}</div></div>")
    css = """.t{position:absolute;top:48px;left:0;right:0;text-align:center}
.h{position:absolute;top:78px;left:80px;right:80px;text-align:center;font-size:50px}
.steps{position:absolute;bottom:54px;left:96px;right:96px;display:flex;gap:24px}"""
    inner = f"""<img class="bg" src="{img}">{top}{bot}
<div class="t kick">{_esc(spec.get('kicker'))}</div><div class="h title">{_esc(spec.get('title'))}</div>
<div class="steps">{cols}</div>"""
    return _wrap(st, inner, css)


COMPOSITIONS = {
    "diptych": _comp_diptych, "hero": _comp_hero, "side_panel": _comp_side_panel,
    "center_anchor": _comp_center_anchor, "annotated": _comp_annotated, "process": _comp_process,
}


def _render(html: str, out_path: str):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
        pg.set_content(html, wait_until="networkidle")
        pg.wait_for_timeout(900)
        pg.screenshot(path=out_path)
        b.close()
    return out_path


# ── G 루프: 생성된 일러스트 비평 + 생성→critique→수정 ────────────────
def _critique(img_path: str, scene: str, style: str) -> dict:
    """생성된 원시 일러스트를 Gemini Vision으로 평가한다(합성 전).

    체크는 합성 전 일러스트 전용 — 글자 미포함/여백 보존/객체 배치/톤 일관.
    반환: {"passed": bool, "score": 0-10, "issues": [...], "notes": "..."}.
    ★fail-open: 키 부재·읽기 실패·VLM 실패 시 {"passed": True, "_error": ...} —
    비평은 품질 향상기이지 산출을 막는 게이트가 아니다.
    """
    cfg = _system_ai_config()
    api_key = (cfg.get("apiKey") or "").strip()
    if not api_key:
        return {"passed": True, "_error": "no_api_key"}
    try:
        b64 = base64.b64encode(open(img_path, "rb").read()).decode()
    except Exception as e:
        return {"passed": True, "_error": f"read_fail: {e}"}

    checks = [
        "이 일러스트는 회화적 '씬'이 아니라 정보 전달용 다이어그램/인포그래픽 양식인가?",
        "일러스트 안에 글자(한글·영문 단어/문장)가 렌더되어 있는가? (있으면 실패 — 텍스트는 합성 레이어가 따로 얹는다)",
        "scene이 지정한 빈 공간(여백)이 실제로 그 위치에 비어 있는가? (제목/캡션이 들어갈 자리)",
        "핵심 객체가 의도한 영역에 명확히 배치되어 있는가?",
        f"스타일 톤이 '{style}'와 일관되는가?",
    ]
    instruction = (
        "당신은 슬라이드 일러스트 평가자입니다. 아래 일러스트가 '의도'를 잘 표현하는지 엄격히 평가하세요.\n\n"
        f"**의도(이 일러스트가 그려야 할 장면·여백)**:\n{scene}\n\n"
        "**체크 항목**:\n" + "\n".join(f"{i+1}. {c}" for i, c in enumerate(checks)) +
        "\n\nJSON 한 개만 출력(다른 텍스트 금지):\n"
        '{"passed": true|false, "score": 0-10, "issues": ["체크N 실패 — 구체 이유", ...], "notes": "1~2문장"}\n'
        "글자가 일러스트에 렌더되어 있으면 무조건 passed=false. issues 없거나 score>=7이면 passed=true."
    )
    payload = {
        "contents": [{"parts": [
            {"inlineData": {"mimeType": "image/png", "data": b64}},
            {"text": instruction},
        ]}],
        "generationConfig": {"temperature": 0.2, "responseModalities": ["TEXT"]},
    }
    last = None
    for model in ("gemini-3-pro-preview", "gemini-2.5-pro"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            with httpx.Client(timeout=120.0) as c:
                r = c.post(url, params={"key": api_key}, json=payload,
                           headers={"Content-Type": "application/json"})
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                data = r.json()
            parts = (data.get("candidates", [{}])[0].get("content", {}) or {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts).strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:]
                text = text.split("```")[0].strip()
            verdict = json.loads(text)
            verdict["passed"] = bool(verdict.get("passed"))
            return verdict
        except Exception as e:
            last = e
            continue
    return {"passed": True, "_error": f"vlm_fail: {last}"}


def _gen_with_critique(illo_prompt, scene, style, base_img_path, output_base,
                       base, quality, max_rounds):
    """생성→비평→수정 루프. 최고 점수 일러스트의 (path, verdict, attempts) 반환.

    통과하거나 비평이 fail-open이면 즉시 종료. 끝까지 못 통과하면 최고 점수본 채택.
    수정 라운드는 critic의 issues를 일러스트 프롬프트에 영어 교정 지시로 되먹인다.
    """
    attempts = []
    best_path, best_verdict, best_score = None, None, -1.0
    cur_prompt = illo_prompt
    for rnd in range(1, max_rounds + 1):
        path_r = base_img_path if rnd == 1 else os.path.join(output_base, f"{base}_img_r{rnd}.png")
        _gen_image(cur_prompt, path_r, quality=quality)
        verdict = _critique(path_r, scene, style)
        try:
            score = float(verdict.get("score")) if verdict.get("score") is not None else 0.0
        except Exception:
            score = 0.0
        attempts.append({"round": rnd, "passed": verdict.get("passed"),
                         "score": verdict.get("score"), "issues": verdict.get("issues"),
                         "error": verdict.get("_error")})
        if score > best_score:
            best_path, best_verdict, best_score = path_r, verdict, score
        # 통과 또는 비평 불가(fail-open) → 현재본으로 종료
        if verdict.get("_error") or verdict.get("passed"):
            best_path, best_verdict = path_r, verdict
            break
        # 다음 라운드: issues를 교정 지시로 되먹임
        if rnd < max_rounds:
            issues = verdict.get("issues") or []
            cur_prompt = (
                illo_prompt +
                "\n\n# Corrections — the previous attempt FAILED these. Fix strictly:\n" +
                "\n".join(f"- {i}" for i in issues) +
                "\n- Render NO text, letters, or words inside the image."
                "\n- Strictly preserve the empty/negative space described in the scene."
            )
    return best_path, best_verdict, attempts


def create_image_slide(tool_input: dict, output_base: str, style: str, slide_id: str = None) -> str:
    """[engines:slide]{style:...} — 개념 일러스트 슬라이드 1장 저작·생성·합성.

    style="auto"면 AI가 4 스타일 중 내용에 맞는 것을 직접 고른다.
    slide_id가 있으면 출력 파일명을 {slide_id}.png 로 고정(강의창 통합용).
    """
    styles_mod = _load_styles()
    auto = (style == "auto")
    if not auto and not styles_mod.is_image_style(style):
        return json.dumps({"success": False,
            "message": f"알 수 없는 style: {style}. 가능: auto / {styles_mod.style_keys_help()}"}, ensure_ascii=False)

    instruction = (tool_input.get("instruction") or "").strip()
    if not instruction:
        return json.dumps({"success": False, "message": "instruction은 필수입니다."}, ensure_ascii=False)
    content = (tool_input.get("content") or "").strip()
    quality = (tool_input.get("quality") or "pro").strip()
    forced_comp = (tool_input.get("composition") or "").strip()

    # 1) 저작
    if auto:
        catalog = " / ".join(f'{k}({v["ko"]})' for k, v in styles_mod.STYLES.items())
        user = (f"# 만들 슬라이드\n{instruction}\n# 스타일\n자동 선택 — 내용·분위기에 맞는 스타일을 "
                f"다음에서 골라 JSON에 \"style\" 필드로 출력하라: {catalog}.")
    else:
        st0 = styles_mod.STYLES[style]
        user = f"# 만들 슬라이드\n{instruction}\n# 스타일\n{style} ({st0['ko']})"
    if forced_comp in COMPOSITIONS:
        user += f"\n# 구성 강제\ncomposition은 반드시 \"{forced_comp}\""
    if content:
        user += f"\n# 참고 내용 (여기서 인용, 지어내지 말 것)\n{content[:10000]}"
    user += "\n위 정보로 JSON 한 객체를 출력하라."
    try:
        ai = _get_ai()
        resp = ai.process_message(user, history=[], images=[], execute_tool=None)
        spec = _extract_json(resp)
    except Exception as e:
        return json.dumps({"success": False, "message": f"저작 실패: {e}"}, ensure_ascii=False)

    # auto면 AI가 고른 style 확정
    if auto:
        chosen = spec.get("style")
        style = chosen if styles_mod.is_image_style(chosen) else "ink_blueprint"
    st = styles_mod.STYLES[style]

    scene = (spec.get("scene") or "").strip()
    if not scene:
        return json.dumps({"success": False, "message": "scene 누락", "spec": spec}, ensure_ascii=False)
    comp = spec.get("composition") if spec.get("composition") in COMPOSITIONS else "diptych"
    if forced_comp in COMPOSITIONS:
        comp = forced_comp

    # 2) 이미지 생성 + 비평 루프 (G 루프: 생성→critique→수정)
    os.makedirs(output_base, exist_ok=True)
    base = slide_id if slide_id else f"slide_{style}_{comp}"
    img_path = os.path.join(output_base, f"{base}_img.png")
    illo_prompt = styles_mod.build_illustration_prompt(scene, style)
    _c = tool_input.get("critique", True)
    critique_on = _c if isinstance(_c, bool) else str(_c).strip().lower() not in ("false", "0", "no", "off")
    crit_rounds = max(1, int(tool_input.get("critique_rounds") or 2))
    critique_verdict, critique_attempts = None, []
    try:
        if critique_on:
            img_path, critique_verdict, critique_attempts = _gen_with_critique(
                illo_prompt, scene, style, img_path, output_base, base, quality, crit_rounds)
        else:
            _gen_image(illo_prompt, img_path, quality=quality)
    except Exception as e:
        return json.dumps({"success": False, "message": f"이미지 생성 실패: {e}", "spec": spec}, ensure_ascii=False)

    # 3) 합성
    out_path = os.path.join(output_base, f"{base}.png")
    try:
        _render(COMPOSITIONS[comp](spec, st, _b64(img_path)), out_path)
    except Exception as e:
        return json.dumps({"success": False, "message": f"합성 렌더 실패: {e}",
                          "image_path": img_path, "spec": spec}, ensure_ascii=False)

    result = {
        "success": True, "image_path": out_path, "illustration_path": img_path,
        "style": style, "composition": comp, "title": spec.get("title"),
        "kicker": spec.get("kicker"), "reasoning": spec.get("reasoning"),
        "spec": spec,
        "message": f"프리미엄 일러스트 슬라이드 1장 ({st['ko']} · {comp}).",
    }
    if critique_verdict is not None:
        result["critique"] = {
            "passed": critique_verdict.get("passed"),
            "score": critique_verdict.get("score"),
            "issues": critique_verdict.get("issues"),
            "notes": critique_verdict.get("notes"),
            "error": critique_verdict.get("_error"),
            "rounds": len(critique_attempts),
        }
        n = len(critique_attempts)
        if critique_verdict.get("_error"):
            result["message"] += f" (비평 건너뜀: {critique_verdict.get('_error')})"
        elif n > 1:
            verb = "통과" if critique_verdict.get("passed") else "최고점 채택"
            result["message"] += f" — 비평 {n}라운드 후 {verb}(score={critique_verdict.get('score')})"
    return json.dumps(result, ensure_ascii=False)
