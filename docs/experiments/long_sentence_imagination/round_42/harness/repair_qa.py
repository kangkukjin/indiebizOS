"""Reuse the round's artifact checks with explicit paths; never mutate a source deck."""
import contextlib
import importlib.util
import io
import json
import sys
from html.parser import HTMLParser
from pathlib import Path


class Heading(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "h1":
            self.active = True

    def handle_endtag(self, tag):
        if tag == "h1":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.text += data


def main(production, source, output):
    report = json.loads(production.read_text())
    render = report["render"]
    output.mkdir(parents=True, exist_ok=True)
    original = Path(__file__).resolve().parents[1] / "artifacts/agent/verify.py"
    spec = importlib.util.spec_from_file_location("round42_existing_qa", original)
    qa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qa)
    qa.SRC_MP4, qa.SRC_ASS = Path(render["output"]), Path(render["caption_file"])
    qa.LEC = qa.SRC_MP4.parent.parent
    qa.INPUT, qa.WORK, qa.FRAMES = source, output, output / "frames"
    qa.MP4, qa.ASS, qa.SRT = output / "video.mp4", output / "captions.ass", output / "captions.srt"
    with contextlib.redirect_stdout(io.StringIO()):
        qa.main()
    result_path = output / "verify_result.json"
    result = json.loads(result_path.read_text())
    deck = json.loads((qa.LEC / "deck.json").read_text())
    headings = []
    for sid in deck["slide_order"]:
        slide = json.loads((qa.LEC / "slides" / f"{sid}.json").read_text())
        parser = Heading()
        parser.feed(slide["custom_html"])
        headings.append(parser.text)
    expected = [s["title"] for s in json.loads(source.read_text())["scenes"]]
    result["html_headings"] = headings
    result["checks"]["rendered_html_titles_exact"] = headings == expected
    result["scope"] = "All slide PNGs and caption-midpoint frames; no human pronunciation approval."
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({"checks": result["checks"], "duration": result["duration_sec"],
                      "file": str(result_path)}, ensure_ascii=False))
    if not all(result["checks"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main(*(Path(p).resolve() for p in sys.argv[1:]))
