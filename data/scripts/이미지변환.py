"""이미지변환 — 결정론 이미지 변환(모델 호출 없음). 크기 조정·형식 변환(HEIC→JPG 포함)·자르기·EXIF 제거·정보.

args(JSON stdin):
  paths: [파일…]           (또는 path 하나, 또는 items:[{path|saved_path|src|file}] — 파이프 봉투 그대로)
  op: "convert"(기본)      | "info" (변환 없이 크기·형식·EXIF/GPS 유무만 items 로)
  format: "jpg"|"png"|"webp"   (생략 = 원본 형식 유지, 단 heic/heif 는 jpg)
  max_side: 1600           (긴 변 상한 px — 넘을 때만 축소, 확대 없음)
  width / height: px       (한쪽만 주면 비율 유지)
  scale: 0.5               (배율)
  max_kb: 1000             (목표 용량 — jpg/webp 품질을 낮추고 그래도 크면 단계적 축소)
  quality: 85              (jpg/webp 저장 품질)
  crop: [l, t, r, b]       (px 상자) 또는 aspect: "3:4" (가운데 기준 비율 자르기)
  strip_exif: false        (true 면 EXIF·GPS 제거. 제출용·공개용이면 true 권장)
  out_dir: 폴더            (생략 = 원본 옆 `<이름>_변환.<확장자>`. 원본은 절대 덮어쓰지 않는다)
  overwrite: false         (출력 파일이 이미 있으면 거절)
출력: {"items":[{src,out,format,width,height,bytes,exif_stripped,steps}], "count", "errors":[…]}
"""
import io
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend" / "base"))
try:
    from runtime_utils import expand_body_path  # ~workspace/ · ~ 단일 해소점
except Exception:  # noqa: BLE001 — 몸 밖에서 돌 때
    expand_body_path = os.path.expanduser

_EXT = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "gif": "GIF", "bmp": "BMP", "tif": "TIFF", "tiff": "TIFF"}
_LOSSY = {"JPEG", "WEBP"}


def _resolve(p: str) -> Path:
    q = Path(expand_body_path(str(p)))
    return q if q.is_absolute() else (_REPO / q)


def _collect_paths(args: dict) -> list[str]:
    if args.get("paths"):
        return [str(p) for p in args["paths"]]
    if args.get("path"):
        return [str(args["path"])]
    out = []
    for it in args.get("items") or []:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict):
            v = it.get("path") or it.get("saved_path") or it.get("src") or it.get("file") or it.get("out")
            if v:
                out.append(str(v))
    return out


def _open(path: Path):
    from PIL import Image, ImageOps
    if path.suffix.lower() in (".heic", ".heif"):
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            raise RuntimeError("HEIC 읽기에 pillow-heif 가 필요합니다 — [self:install_lib]{name:\"pillow-heif\"}")
    img = Image.open(str(path))
    img.load()
    src_format = (img.format or "").upper()
    has_exif = bool(img.getexif())
    has_gps = False
    try:
        has_gps = 0x8825 in img.getexif()
    except Exception:  # noqa: BLE001
        pass
    img = ImageOps.exif_transpose(img) or img  # 회전 태그를 픽셀에 반영(뷰어마다 다르게 보이는 문제 제거)
    return img, src_format, has_exif, has_gps


def _target_format(args: dict, path: Path, src_format: str) -> str:
    f = (args.get("format") or "").lower().lstrip(".")
    if f:
        if f not in _EXT:
            raise ValueError(f"지원하지 않는 format: {f} (jpg/png/webp/gif/bmp/tiff)")
        return _EXT[f]
    if path.suffix.lower() in (".heic", ".heif"):
        return "JPEG"
    return src_format if src_format in _EXT.values() else "PNG"


def _apply_crop(img, args: dict, steps: list):
    crop = args.get("crop")
    aspect = args.get("aspect")
    if crop:
        l, t, r, b = [int(v) for v in crop]
        if not (0 <= l < r <= img.width and 0 <= t < b <= img.height):
            raise ValueError(f"crop 상자가 이미지({img.width}x{img.height}) 밖입니다: {crop}")
        img = img.crop((l, t, r, b))
        steps.append(f"crop {l},{t},{r},{b}")
    elif aspect:
        aw, ah = [float(x) for x in str(aspect).replace("x", ":").split(":")]
        target = aw / ah
        cur = img.width / img.height
        if cur > target:
            nw = int(round(img.height * target))
            l = (img.width - nw) // 2
            img = img.crop((l, 0, l + nw, img.height))
        else:
            nh = int(round(img.width / target))
            t = (img.height - nh) // 2
            img = img.crop((0, t, img.width, t + nh))
        steps.append(f"aspect {aspect} → {img.width}x{img.height}")
    return img


def _apply_resize(img, args: dict, steps: list):
    from PIL import Image
    w, h = img.width, img.height
    nw = nh = None
    if args.get("scale"):
        s = float(args["scale"])
        nw, nh = max(1, int(w * s)), max(1, int(h * s))
    elif args.get("width") or args.get("height"):
        tw, th = args.get("width"), args.get("height")
        if tw and th:
            nw, nh = int(tw), int(th)
        elif tw:
            nw = int(tw); nh = max(1, int(h * nw / w))
        else:
            nh = int(th); nw = max(1, int(w * nh / h))
    elif args.get("max_side"):
        ms = int(args["max_side"])
        if max(w, h) > ms:
            r = ms / max(w, h)
            nw, nh = max(1, int(w * r)), max(1, int(h * r))
    if nw and (nw, nh) != (w, h):
        img = img.resize((nw, nh), Image.LANCZOS)
        steps.append(f"resize {w}x{h} → {nw}x{nh}")
    return img


def _encode(img, fmt: str, quality: int, exif: bytes | None) -> bytes:
    buf = io.BytesIO()
    kw = {}
    if fmt in _LOSSY:
        kw["quality"] = quality
    if fmt == "JPEG":
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        kw["optimize"] = True
    if exif:
        kw["exif"] = exif
    img.save(buf, format=fmt, **kw)
    return buf.getvalue()


def _fit_size(img, fmt: str, quality: int, exif: bytes | None, max_kb: int, steps: list) -> bytes:
    from PIL import Image
    data = _encode(img, fmt, quality, exif)
    limit = max_kb * 1024
    q = quality
    while len(data) > limit and fmt in _LOSSY and q > 40:
        q -= 10
        data = _encode(img, fmt, q, exif)
        steps.append(f"quality {q}")
    while len(data) > limit and max(img.width, img.height) > 320:
        img = img.resize((max(1, int(img.width * 0.8)), max(1, int(img.height * 0.8))), Image.LANCZOS)
        data = _encode(img, fmt, q, exif)
        steps.append(f"downscale → {img.width}x{img.height}")
    if len(data) > limit:
        steps.append(f"max_kb {max_kb} 미달성({len(data) // 1024}KB)")
    return data


def _out_path(src: Path, fmt: str, args: dict) -> Path:
    ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif", "BMP": "bmp", "TIFF": "tif"}[fmt]
    if args.get("out_dir"):
        d = _resolve(args["out_dir"])
        d.mkdir(parents=True, exist_ok=True)
        out = d / f"{src.stem}.{ext}"
    else:
        out = src.with_name(f"{src.stem}_변환.{ext}")
    if out.resolve() == src.resolve():
        out = src.with_name(f"{src.stem}_변환.{ext}")
    return out


def _one(p: str, args: dict) -> dict:
    src = _resolve(p)
    if not src.is_file():
        raise FileNotFoundError(f"파일이 없습니다: {src}")
    img, src_format, has_exif, has_gps = _open(src)
    if (args.get("op") or "convert") == "info":
        return {"src": str(src), "format": src_format, "width": img.width, "height": img.height,
                "bytes": src.stat().st_size, "has_exif": has_exif, "has_gps": has_gps}
    steps: list = []
    fmt = _target_format(args, src, src_format)
    img = _apply_crop(img, args, steps)
    img = _apply_resize(img, args, steps)
    strip = bool(args.get("strip_exif", False))
    exif = None
    if not strip and has_exif and fmt in ("JPEG", "WEBP", "TIFF"):
        try:
            exif = img.getexif().tobytes()
        except Exception:  # noqa: BLE001
            exif = None
    quality = int(args.get("quality", 85))
    if args.get("max_kb"):
        data = _fit_size(img, fmt, quality, exif, int(args["max_kb"]), steps)
    else:
        data = _encode(img, fmt, quality, exif)
    out = _out_path(src, fmt, args)
    if out.exists() and not args.get("overwrite"):
        raise FileExistsError(f"출력 파일이 이미 있습니다(overwrite:true 로 허용): {out}")
    out.write_bytes(data)
    if fmt != src_format:
        steps.insert(0, f"{src_format or src.suffix} → {fmt}")
    from PIL import Image
    with Image.open(io.BytesIO(data)) as chk:
        w, h = chk.width, chk.height
    return {"src": str(src), "out": str(out), "format": fmt, "width": w, "height": h,
            "bytes": len(data), "exif_stripped": strip or not exif, "steps": steps}


def main() -> int:
    args = json.loads(sys.stdin.read() or "{}")
    paths = _collect_paths(args)
    if not paths:
        print(json.dumps({"success": False, "error": "paths(또는 path/items)가 필요합니다."}, ensure_ascii=False))
        return 1
    items, errors = [], []
    for p in paths:
        try:
            items.append(_one(p, args))
        except Exception as e:  # noqa: BLE001 — 한 파일 실패는 errors 로
            errors.append({"src": str(p), "error": str(e)})
    res = {"items": items, "count": len(items), "errors": errors}
    if not items:
        res["success"] = False
        res["error"] = errors[0]["error"] if errors else "변환된 파일이 없습니다."
    print(json.dumps(res, ensure_ascii=False))
    return 0 if items else 1


if __name__ == "__main__":
    sys.exit(main())
