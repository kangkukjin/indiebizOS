"""Synthetic source fixture. No product code or expected answers in AI input."""
import json
import sys
from pathlib import Path


def generate(dest):
    root = Path(dest)
    root.mkdir(parents=True, exist_ok=True)
    for team in ("사진", "설치", "영상"):
        for n in range(24):
            path = root / team / f"작품 {n:02d}" / "설명.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            text = "" if n == 0 else (f"작품: {team}-{n:02d}\r\n제목: 빛과 공간\n" +
                                          (f"{team} 자료 {n} — 설치 위치와 작품 설명.\n" * (n + 1)))
            path.write_bytes(text.encode())
        (root / team / "검수.txt").write_text(f"{team} 검수 메모\n")
        (root / team / "draft.tmp").write_text("공개 제외 초안\n")
        internal = root / team / "internal"
        internal.mkdir(exist_ok=True)
        (internal / "연락.txt").write_text("합성 내부 메모 — 납품 제외\n")
    (root / "안내.txt").write_text("전시 전달용 합성 자료. 폴더 구조와 원문 바이트를 보존합니다.\n")
    return root


if __name__ == "__main__":
    generate(sys.argv[1])
