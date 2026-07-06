#!/usr/bin/env python3
"""publish_hippocampus.py — 학습한 해마(모델+용례+벡터)를 GitHub Release 에셋으로 올린다.

fresh 설치(다른 PC)는 학습 없이 이 에셋을 받아 해마를 그대로 쓴다(hippocampus_provision.download_model).
"깃헙에 보내면 다른 PC가 받아쓴다"를 실현하는 도구 — git 저장소(대용량 부적합) 대신 Release 에셋.

담는 것(전개 시 data/ 기준 상대경로):
  - models/ibl_embedding/**       배포용 fine-tuned 모델(422MB). ★epoch_* 체크포인트는 제외(중복 3.7GB).
  - ibl_usage.db                  검색 인덱스(용례 + 새 모델 벡터, ~498MB). fresh 설치가 이걸로 바로 검색.
  - training/ibl_distilled.json   용례 원본(FTS5 폴백·향후 재학습용, 작음)

실행:  python3 scripts/publish_hippocampus.py [--tag hippocampus] [--dry-run]
전제:  gh 인증(repo write). zip 은 build/hippocampus.zip 에 생성.
"""
import argparse
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _iter_model_files():
    """data/models/ibl_embedding 의 배포용 파일(epoch_* 체크포인트 제외)."""
    model_root = DATA / "models" / "ibl_embedding"
    if not (model_root / "model.safetensors").exists():
        print(f"✗ 배포용 모델 없음: {model_root/'model.safetensors'}", file=sys.stderr)
        sys.exit(1)
    for p in model_root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(model_root)
        # epoch_1 … epoch_N 체크포인트 디렉토리 제외
        if any(part.startswith("epoch_") for part in rel.parts):
            continue
        yield p, Path("models") / "ibl_embedding" / rel


def build_zip(out_zip: Path) -> int:
    extra = [
        # 검색 인덱스(용례 + 새 모델 벡터). fresh 설치가 이걸로 바로 검색 — 없으면 해마가 빈다.
        (DATA / "ibl_usage.db", Path("ibl_usage.db")),
        # 용례 원본(FTS 폴백·향후 재학습용, 작음)
        (DATA / "training" / "ibl_distilled.json", Path("training") / "ibl_distilled.json"),
    ]
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for src, arc in _iter_model_files():
            z.write(src, str(arc))
            n += 1
        for src, arc in extra:
            if src.exists():
                z.write(src, str(arc))
                n += 1
            else:
                print(f"  ⚠ 없음(건너뜀): {src}")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="hippocampus", help="릴리스 태그(고정, 에셋 갱신용)")
    ap.add_argument("--dry-run", action="store_true", help="zip 만 만들고 업로드 안 함")
    args = ap.parse_args()

    out_zip = ROOT / "build" / "hippocampus.zip"
    print(f"[publish] zip 생성: {out_zip}")
    n = build_zip(out_zip)
    size_mb = out_zip.stat().st_size / 1024 / 1024
    print(f"[publish] {n}개 파일, {size_mb:.0f}MB")

    if args.dry_run:
        print("[publish] --dry-run — 업로드 생략")
        return

    # 릴리스가 없으면 생성, 있으면 에셋만 덮어쓰기(--clobber)
    tag = args.tag
    has = subprocess.run(["gh", "release", "view", tag], capture_output=True, text=True)
    if has.returncode != 0:
        print(f"[publish] 릴리스 '{tag}' 생성")
        subprocess.run(
            ["gh", "release", "create", tag, "--title", "IndieBiz 해마 (모델+용례)",
             "--notes", "fine-tuned IBL 임베딩 모델 + 미리계산 벡터 + 용례. 첫 실행 시 자동 다운로드됨.",
             "--prerelease"],
            check=True,
        )
    print(f"[publish] 에셋 업로드(--clobber): {out_zip.name}")
    subprocess.run(["gh", "release", "upload", tag, str(out_zip), "--clobber"], check=True)
    print(f"[publish] ✅ 완료 — https://github.com/kangkukjin/indiebizOS/releases/tag/{tag}")


if __name__ == "__main__":
    main()
