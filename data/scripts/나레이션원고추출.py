#!/usr/bin/env python3
"""강의 덱의 스피커 노트에서 ‘굽는 원고’를 뽑아 texts JSON 으로 내린다.

왜 필요한가: 시작·끝 인사말은 복제 음성이 아니라 사용자가 직접 낭독한 실음성
(outputs/narration/bookends3/)을 이어 붙인다. 그러려면 인사말은 노트에는 남기고
(자막이 그 구간까지 덮어야 한다) 굽는 원고에서만 뺌야 한다. 매 영상마다
되풀이되는 손질이라 얼렸다.

args (stdin JSON):
  lecture_id : 강의 id (필수)
  out        : 저장할 JSON 경로 (기본 <강의폴더>/narration_texts.json)
  intro      : 첫 장 노트 앞에서 떼어낼 문구 (기본 표준 인트로)
  outro      : 끝 장 노트 뒤에서 떼어낼 문구 (기본 표준 아웃트로)
  strict     : true(기본) 면 인사말이 없을 때 실패. false 면 그냥 둘다.

산출: {"items":[{"title","meta"}], "path":..., "message":...}
다음 단계: [self:script]{op:"run", id:"나레이션생성",
            args:{texts_file:"<path>", out_dir:"<강의>/narration", voice:"kkj3"}, background:true}
"""
import json
import sys
from pathlib import Path

ROOT = Path("/Users/kangkukjin/Desktop/AI/indiebizOS")
INTRO = "안녕하세요. 오늘의 질문 강국진입니다."
OUTRO = "오늘은 여기까지 하겠습니다. 여기까지 강국진이었습니다. 안녕히 계세요."


def fail(msg):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(1)


def main():
    raw = sys.stdin.read().strip()
    args = json.loads(raw) if raw else {}

    lecture_id = args.get("lecture_id")
    if not lecture_id:
        fail("lecture_id 가 필요합니다.")

    lec = ROOT / "outputs" / "lectures" / lecture_id
    deck_path = lec / "deck.json"
    if not deck_path.exists():
        fail(f"강의를 찾을 수 없습니다: {deck_path}")

    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    order = deck.get("slide_order") or []
    if not order:
        fail("덱에 슬라이드가 없습니다.")

    intro = args.get("intro", INTRO)
    outro = args.get("outro", OUTRO)
    strict = args.get("strict", True)

    texts, items = {}, []
    for sid in order:
        note = (deck["slides"][sid].get("speaker_note") or "").strip()
        trimmed = []
        if sid == order[0] and intro:
            if note.startswith(intro):
                note = note[len(intro):].strip()
                trimmed.append("intro")
            elif strict:
                fail(f"첫 장 노트가 인트로 문구로 시작하지 않습니다: {note[:40]}")
        if sid == order[-1] and outro:
            if note.endswith(outro):
                note = note[:-len(outro)].strip()
                trimmed.append("outro")
            elif strict:
                fail(f"끝 장 노트가 아웃트로 문구로 끝나지 않습니다: {note[-40:]}")
        if not note:
            continue
        texts[sid] = note
        items.append({"title": sid,
                      "meta": f"{len(note)}자" + (f" ({'+'.join(trimmed)} 제거)" if trimmed else ""),
                      "summary": note[:40]})

    out = Path(args.get("out") or (lec / "narration_texts.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")

    total = sum(len(t) for t in texts.values())
    print(json.dumps({
        "items": items,
        "path": str(out),
        "count": len(texts),
        "chars": total,
        "message": f"{len(texts)}장 {total}자 → {out}",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
