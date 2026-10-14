"""Build a fresh read-only phone rehearsal request; never overwrite evidence."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ROUND = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-14_66회차"
PURPOSES = ["사진 촬영", "음성 녹음", "위치 확인", "음성 안내", "진동 알림", "라디오 듣기",
            "음악 듣기", "원격 영상 보기", "폰 화면 공유", "가속도 측정", "Bluetooth 주변기기", "NFC 읽기"]
CAPS = ["camera", "microphone", "", "speaker", "", "playback", "playback", "video_playback", "screen", "", "", ""]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("label", help="new execution folder, e.g. replay_base")
    parser.add_argument("--variant", action="store_true")
    parser.add_argument("--new-variant", action="store_true")
    args = parser.parse_args()
    if not args.label.replace("_", "").replace("-", "").isalnum():
        parser.error("label must be a simple unique folder name")
    notes = ["한글 점검", '따옴표 "시험"', "첫 줄\n둘째 줄", ""]
    rows = [dict(id=f"P{i+1:02}", purpose=purpose, note=notes[i % 4])
            for i, purpose in enumerate(PURPOSES)]
    devices = ["삼성1"]
    if args.variant or args.new_variant:
        rows.reverse()
        next(row for row in rows if row["id"] == "P03")["note"] = "변형\\경로 | 한글"
        devices.append("round66-no-such-phone")
    if args.new_variant:
        notes = ["CRLF\r\n둘째 줄", "'인용' \\\\ 경로 | 가", "한글 🧪", ""]
        for index, row in enumerate(rows):
            row["note"] = notes[index % 4]
    remote = f"outputs/long_sentence_imagination/round66/trainer/{args.label}/checklist.json"
    literal = json.dumps(json.dumps(rows, ensure_ascii=False), ensure_ascii=False)
    code = ('#!ibl edition=2\n$s=[self:write]{path:' + json.dumps(remote)
            + ',content:' + literal + '}\n$r=[self:read]{path:$s.path}\n'
            + 'return {path:$s.path,rows:$r.data.items,text:$r.text}')
    request = {"code": (ROUND / "base_v2.ibl").read_text(), "edition": 2,
               "project_id": "수동모드", "origin": "training", "inputs": {
                   "devices": devices, "rows": rows,
                   "out": str(OUT / "trainer" / args.label),
                   "capmap": {f"P{i+1:02}": key for i, key in enumerate(CAPS)},
                   "probes": [{"id": "info", "op": "info", "code": ""},
                              {"id": "playback", "op": "ibl", "code": '#!ibl edition=2\nreturn {radio:[limbs:radio]{op:"status"},music:[limbs:music]{op:"queue"}}'},
                              {"id": "roundtrip", "op": "ibl", "code": code}]}}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / (args.label + ".request.json")
    with path.open("x") as stream:
        json.dump(request, stream, ensure_ascii=False, indent=2)
    print(path)


if __name__ == "__main__":
    main()
