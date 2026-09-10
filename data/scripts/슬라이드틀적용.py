#!/usr/bin/env python3
"""공통 HTML 틀 한 벌 + 장별 내용 JSON → 덱 슬라이드. AI 호출 없음.
args: lecture_id, lecture_dir(선택), template_path, contents_path, inspect(기본 false).
contents=[{id,title,speaker_note,fields:{subtitle,visual_html,...}}].
speaker_note는 새 슬라이드 노트의 초깃값이다. 기존 노트는 보존하며 정본 원고는 영상제작파이프라인으로 적용한다.
틀의 {{slot}}은 일반 문자열을 HTML escape, *_html만 명시적 HTML로 삽입한다.
"""
from filelock import FileLock
import hashlib
import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
sys.path.insert(0, str(ROOT / "data/packages/installed/tools/lecture_workspace"))
import lecture_store  # noqa: E402
import slide_ai  # noqa: E402
from verification_cache import file_hash  # noqa: E402


def specs(template, rows):
    names = set(re.findall(r"\{\{([a-zA-Z_][a-zA-Z_0-9]*)\}\}", template))
    if not names or not isinstance(rows, list) or not 1 <= len(rows) <= 60:
        raise ValueError("틀에 {{slot}}이 있어야 하며 contents는 1~60개 배열이어야 합니다")
    seen, result = set(), []
    for row in rows:
        sid = row["id"]
        if not re.fullmatch(r"s[0-9]{3,6}", sid) or sid in seen:
            raise ValueError("슬라이드 ID 중복 또는 잘못된 형식")
        seen.add(sid)
        fields = {"title": row["title"], **row.get("fields", {})}
        if names - fields.keys() or any(not isinstance(fields[n], str) for n in names):
            raise ValueError(f"{sid}: 슬롯이 없거나 문자열이 아닙니다: {sorted(names - fields.keys())}")
        def replace(match):
            key = match[1]
            return fields[key] if key.endswith("_html") else html.escape(fields[key], quote=True)
        content = re.sub(r"\{\{([a-zA-Z_][a-zA-Z_0-9]*)\}\}", replace, template)
        result.append((sid, {"layout": "custom", "title": row["title"], "custom_html": content}, row.get("speaker_note")))
    return result


def apply(args):
    lecture_id = args["lecture_id"]
    directory = Path(args.get("lecture_dir") or lecture_store.lecture_dir(lecture_id)).resolve()
    if directory.name != lecture_id:
        raise ValueError("lecture_dir의 폴더 이름은 lecture_id와 같아야 합니다")
    deck = json.loads((directory / "deck.json").read_text())
    if deck.get("lecture_id") != lecture_id:
        raise ValueError("덱의 lecture_id가 다릅니다")
    template = Path(args["template_path"]).read_text()
    rows = json.loads(Path(args["contents_path"]).read_text())
    prepared = specs(template, rows)  # 쓰기 전 전 행 검증
    if args.get("inspect"):
        return {"success": True, "count": len(prepared), "model_calls": 0, "template_chars": len(template),
                "content_chars": len(json.dumps(rows, ensure_ascii=False)), "expanded_chars": sum(len(s[1]["custom_html"]) for s in prepared)}
    lecture_store.set_roots(directory.parent, [directory.parent])
    state_path = directory / "slide_template_state.json"
    with FileLock(str(directory / "slide_template.lock"), timeout=0):
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        items = []
        for sid, spec, note in prepared:
            key = hashlib.sha256(json.dumps([spec, deck.get("design_system"), file_hash(slide_ai.__file__)], ensure_ascii=False).encode()).hexdigest()
            png = directory / "slides" / (sid + ".png")
            old = state.get(sid, {})
            reused = old.get("key") == key and png.exists() and old.get("png_hash") == file_hash(png)
            if not reused:
                with tempfile.TemporaryDirectory(dir=directory) as tmp:
                    slide_ai.render_slide_to_files(spec, deck.get("design_system", "vintage_book"), Path(tmp), sid)
                    png.parent.mkdir(exist_ok=True)
                    for file in Path(tmp).iterdir():
                        os.replace(file, png.parent / file.name)
                lecture_store.register_slide(lecture_id, sid, spec["title"], "custom", f"slides/{sid}.json", f"slides/{sid}.png", speaker_note=note)
                state[sid] = {"key": key, "png_hash": file_hash(png)}
                tmp_state = state_path.with_suffix(".json.tmp")
                tmp_state.write_text(json.dumps(state, ensure_ascii=False))
                tmp_state.replace(state_path)
            items.append({"id": sid, "path": str(png), "reused": reused})
        return {"success": True, "items": items, "model_calls": 0}


if __name__ == "__main__":
    try:
        print(json.dumps(apply(json.loads(sys.stdin.read() or "{}")), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
