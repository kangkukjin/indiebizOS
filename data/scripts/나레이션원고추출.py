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
  source     : ## s001 — 제목 형식의 원고 파일. 이후 추출에서도 이 원본을 대조한다.
  apply_notes: true면 source 본문을 노트에 일괄 반영. false면 불일치 시 실패.
  inspect    : true면 파일을 쓰지 않고 글자수·예상 초·불일치만 반환.
  chars_per_second / bookend_seconds : 예상 길이 계수(기본 6.67자/초, 인사말 등 8.7초).

산출: {"items":[{"title","meta"}], "path":..., "message":...}
다음 단계: [self:script]{op:"run", id:"나레이션생성",
            args:{texts_file:"<path>", out_dir:"<강의>/narration", voice:"kkj3"}, background:true}
"""
import json
import hashlib
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
INTRO = "안녕하세요. 오늘의 질문 강국진입니다."
OUTRO = "오늘은 여기까지 하겠습니다. 여기까지 강국진이었습니다. 안녕히 계세요."


def fail(msg):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(1)


def prepare(args):
    lecture_id = args.get("lecture_id")
    if not lecture_id or Path(lecture_id).name != lecture_id or lecture_id in {".", ".."}:
        raise ValueError("lecture_id 가 필요합니다.")

    lec = Path(args.get("lecture_dir") or (ROOT / "outputs" / "lectures" / lecture_id))
    deck_path = lec / "deck.json"
    if not deck_path.exists():
        raise ValueError(f"강의를 찾을 수 없습니다: {deck_path}")

    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    order = deck.get("slide_order") or []
    if not order:
        raise ValueError("덱에 슬라이드가 없습니다.")

    source = args.get("source") or (deck.get("narration_source") or {}).get("path")
    source_path, source_text, mismatches = None, None, []
    if source:
        source_path = (ROOT / source).resolve()
        source_text = source_path.read_text(encoding="utf-8")
        parts = re.split(r"^## (s\d+)\s+[—–-]\s+.*$", source_text, flags=re.M)
        ids = parts[1::2]
        notes = {sid: body.strip() for sid, body in zip(ids, parts[2::2])}
        if len(ids) != len(set(ids)) or set(ids) != set(order) or not all(notes.values()):
            raise ValueError("원고의 슬라이드 ID가 덱과 다르거나 중복·빈 본문이 있습니다")
        mismatches = [sid for sid in order if (deck["slides"][sid].get("speaker_note") or "").strip() != notes[sid]]
        if mismatches and not (args.get("apply_notes") or args.get("inspect")):
            raise ValueError(f"원고·노트 불일치: {mismatches}. source를 확인한 뒤 apply_notes:true로 반영하세요")
        for sid in order:
            deck["slides"][sid]["speaker_note"] = notes[sid]

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
                raise ValueError(f"첫 장 노트가 인트로 문구로 시작하지 않습니다: {note[:40]}")
        if sid == order[-1] and outro:
            if note.endswith(outro):
                note = note[:-len(outro)].strip()
                trimmed.append("outro")
            elif strict:
                raise ValueError(f"끝 장 노트가 아웃트로 문구로 끝나지 않습니다: {note[-40:]}")
        if not note:
            continue
        texts[sid] = note
        items.append({"title": sid,
                      "meta": f"{len(note)}자" + (f" ({'+'.join(trimmed)} 제거)" if trimmed else ""),
                      "summary": note[:40]})

    out = Path(args.get("out") or (lec / "narration_texts.json"))
    total = sum(len(t) for t in texts.values())
    rate = float(args.get("chars_per_second", 6.67))
    bookends = float(args.get("bookend_seconds", 8.7))
    if not math.isfinite(rate) or rate <= 0 or not math.isfinite(bookends) or bookends < 0:
        raise ValueError("chars_per_second는 양수, bookend_seconds는 0 이상 유한수여야 합니다")
    if not args.get("inspect"):
        if source_path:
            # 모든 ID·인사말 검증을 마친 뒤 같은 원본을 노트·자료 사본에 반영한다.
            copied = lec / "materials" / source_path.name
            copied.parent.mkdir(parents=True, exist_ok=True)
            copied.write_text(source_text, encoding="utf-8")
            deck["narration_source"] = {"path": str(source_path),
                "sha256": hashlib.sha256(source_text.encode()).hexdigest(),
                "material": str(copied.relative_to(lec))}
            from datetime import datetime
            deck["updated_at"] = datetime.now().isoformat(timespec="seconds")
            temp = deck_path.with_suffix(".json.tmp")
            temp.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(deck_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
    return {
        "success": True, "inspect": bool(args.get("inspect")), "mismatched_notes": mismatches,
        "items": items,
        "path": str(out),
        "count": len(texts),
        "chars": total,
        "estimated_seconds": round(total / rate + bookends, 1),
        "estimate_basis": {"chars_per_second": rate, "bookend_seconds": bookends},
        "message": f"{len(texts)}장 {total}자 → {out}",
    }


def main():
    try:
        print(json.dumps(prepare(json.loads(sys.stdin.read() or "{}")), ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
