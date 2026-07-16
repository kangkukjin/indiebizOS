"""bulletin_core.py — 자유게시판 상태·글 저장 단일 소스.

handler.py(IBL 운영자 어휘: 게시판 CRUD·모더레이션)와 backend/api_bulletin.py(공개 서빙·
익명 글쓰기)가 같은 데이터를 만지므로, 읽기-수정-쓰기를 여기 한 곳에 모으고 flock 으로
직렬화한다(모듈 인스턴스가 둘이어도 파일락이 지켜줌 — showcase '동시 쓰기 금지' 교훈,
portal_core 선례).

★이 파일 수정 시: handler 는 /packages/reload 로 갱신되지만, api_bulletin 이 sys.modules
  에 캐시한 인스턴스는 백엔드 재시작으로만 갱신된다.

데이터 배치 (인덱싱 없음 — 상태 파일 + 게시판별 글 파일):
- data/bulletin/state.json                : {settings, boards:[{id,slug,title,allow_images,created_at}]}
- data/bulletin/<board_id>/posts.json      : [{id,name,body,image,at,ip}]  (게시판별, flock)
- data/bulletin/<board_id>/img/<fname>     : EXIF 제거·다운스케일된 첨부 이미지
게시판의 글 수는 저장하지 않고 posts.json 길이로 즉석 산출(공개 글쓰기가 state.json 을
건드리지 않게 — 경합 최소화).
"""

import io
import os
import re
import sys
import json
import time
import fcntl
import string
import secrets
import unicodedata
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parents[5]
_BACKEND = str(_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_DATA = _ROOT / "data" / "bulletin"
_STATE_PATH = _DATA / "state.json"
_LOCK_PATH = _DATA / "state.lock"

# 익명 글쓰기 방어(개인 규모)
NAME_MAX = 24
BODY_MAX = 4000
_TITLE_MAX = 60
POST_MIN_INTERVAL_S = 8            # 같은 IP 연속 글쓰기 간격
POSTS_CAP = 5000                   # 게시판당 보관 글 수(최신 유지)
IMG_MAX_BYTES = 20 * 1024 * 1024
IMG_MAX_DIM = 1600                 # 첨부 이미지 최대 변(px)
_BOARD_CAP = 100

# 이미지 매직바이트 (JPEG/PNG/GIF/WebP·RIFF/HEIC·HEIF ftyp)
_IMG_MAGIC = [b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"RIFF"]

_DEFAULT_SETTINGS = {
    "public_base": "",       # 공개 사이트 base URL (게시판 주소 조립용) — showcase 와 같은 Worker
    "allow_images": True,    # 새 게시판 기본값
}


# ── 공개 base (공개파일·가족신문과 같은 Worker) ──────────────────────────

def _default_public_base() -> str:
    try:
        sc = json.loads((_ROOT / "data" / "showcase_state.json").read_text(encoding="utf-8"))
        return (sc.get("settings") or {}).get("public_base", "") or ""
    except Exception:
        return ""


# ── 상태(state.json) — flock 직렬화 ──────────────────────────────────────

def load_state() -> dict:
    try:
        st = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    settings = {**_DEFAULT_SETTINGS, **(st.get("settings") or {})}
    if not settings.get("public_base"):
        settings["public_base"] = _default_public_base()
    return {"settings": settings, "boards": st.get("boards") or []}


def mutate_state(fn):
    """load-modify-save 를 파일락으로 직렬화. fn(state) 반환값이 있으면 그걸, 없으면 state 반환."""
    _DATA.mkdir(parents=True, exist_ok=True)
    with open(_LOCK_PATH, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            state = load_state()
            ret = fn(state)
            tmp = _STATE_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(_STATE_PATH)
            return state if ret is None else ret
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


# ── 유틸 ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def new_slug(existing=None) -> str:
    """짧은 5자 대문자 코드(A-Z). 26^5 ≈ 1,180만 — bare 루트가 잠겨 있어 충분. 충돌 시 재발급."""
    existing = existing or set()
    while True:
        s = "".join(secrets.choice(string.ascii_uppercase) for _ in range(5))
        if s not in existing:
            return s


def board_url(settings: dict, board: dict) -> str:
    base = (settings.get("public_base") or "").rstrip("/")
    slug = board.get("slug") or ""
    return f"{base}/b/{slug}" if base and slug else ""


def get_board(state: dict, ident: str) -> dict:
    """id 또는 slug 로 게시판 찾기."""
    for b in state.get("boards", []):
        if b.get("id") == ident or b.get("slug") == ident:
            return b
    return None


def _board_dir(board_id: str) -> Path:
    return _DATA / board_id


def _posts_path(board_id: str) -> Path:
    return _board_dir(board_id) / "posts.json"


def post_count(board_id: str) -> int:
    try:
        return len(json.loads(_posts_path(board_id).read_text(encoding="utf-8")))
    except Exception:
        return 0


def board_row(settings: dict, b: dict) -> dict:
    n = post_count(b.get("id", ""))
    return {
        "title": b.get("title") or "이름 없는 게시판",
        "meta": f"📋 글 {n}개 · {'🖼 사진 허용' if b.get('allow_images', True) else '📝 글만'}",
        "url": board_url(settings, b),
        "id": b.get("id", ""),
        "slug": b.get("slug", ""),
        "allow_images": bool(b.get("allow_images", True)),
        "post_count": n,
    }


# ── 게시판 CRUD (state.json) ─────────────────────────────────────────────

def create_board(title: str, allow_images=True) -> dict:
    title = (title or "").strip()[:_TITLE_MAX]

    def _do(state):
        existing = {b.get("slug") for b in state["boards"]}
        b = {"id": "brd_" + secrets.token_hex(6), "slug": new_slug(existing),
             "title": title or "새 게시판", "allow_images": bool(allow_images),
             "created_at": _now()}
        state["boards"].append(b)
        return b
    return mutate_state(_do)


def config_board(board_id: str, title=None, allow_images=None):
    """게시판 설정 — 제목·사진허용. 제목 변경(개명)도 여기서 함께 처리."""
    def _do(state):
        b = get_board(state, board_id)
        if not b:
            return {"_err": "게시판을 찾을 수 없습니다."}
        if title is not None and str(title).strip():
            b["title"] = str(title).strip()[:_TITLE_MAX]
        if allow_images is not None:
            b["allow_images"] = bool(allow_images)
        return b
    return mutate_state(_do)


def delete_board(board_id: str):
    def _do(state):
        b = get_board(state, board_id)
        if not b:
            return {"_err": "게시판을 찾을 수 없습니다."}
        state["boards"] = [x for x in state["boards"] if x.get("id") != board_id]
        return {"_ok": True}
    ret = mutate_state(_do)
    # 게시판 데이터 폴더(글·이미지) 동반 삭제
    if isinstance(ret, dict) and ret.get("_ok"):
        import shutil
        try:
            shutil.rmtree(_board_dir(board_id), ignore_errors=True)
        except Exception:
            pass
    return ret


# ── 글(posts.json) — 게시판별 flock ──────────────────────────────────────

def _posts_lock(board_id: str):
    d = _board_dir(board_id)
    d.mkdir(parents=True, exist_ok=True)
    return open(d / "posts.lock", "w")


def load_posts(board_id: str) -> list:
    try:
        return json.loads(_posts_path(board_id).read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_posts(board_id: str, posts: list):
    p = _posts_path(board_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(posts, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def looks_image(head: bytes) -> bool:
    if any(head.startswith(m) for m in _IMG_MAGIC):
        return True
    if len(head) > 12 and head[4:8] == b"ftyp":   # HEIC/HEIF/AVIF
        return True
    return False


def _strip_and_downscale(data: bytes) -> bytes:
    """PIL 재인코딩으로 EXIF(위치 포함) 전부 제거 + 최대 변 다운스케일 → JPEG.

    처리 불가한 포맷은 예외를 올린다(호출측이 이미지 거부, 텍스트 글은 살림) —
    공개 게시판이라 메타데이터 유출을 절대 남기지 않는다."""
    from PIL import Image, ImageOps
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)   # 회전 방향 반영 후 EXIF 폐기
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    im.thumbnail((IMG_MAX_DIM, IMG_MAX_DIM))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return out.getvalue()


def save_post_image(board_id: str, data: bytes) -> str:
    """이미지 바이트 → 게시판 img/ 에 EXIF 제거본 저장, 파일명 반환. 실패 시 예외."""
    if len(data) < 100 or not looks_image(data[:16]):
        raise ValueError("이미지가 아닙니다.")
    if len(data) > IMG_MAX_BYTES:
        raise ValueError("이미지가 너무 큽니다.")
    clean = _strip_and_downscale(data)
    img_dir = _board_dir(board_id) / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(3)}.jpg"
    (img_dir / fname).write_bytes(clean)
    return fname


def image_path(board_id: str, fname: str) -> Path:
    """첨부 이미지 절대경로 — 경로 이탈 방어(img/ 하위, basename 만)."""
    base = (_board_dir(board_id) / "img").resolve()
    target = (base / os.path.basename(fname)).resolve()
    if target.parent != base or not target.is_file():
        return None
    return target


_LAST_POST_BY_IP: dict = {}


def add_post(board_id: str, name: str, body: str, image_bytes: bytes = None, ip: str = "") -> dict:
    """익명 글 등록. 이름/본문 캡, IP 간격 제한(예외 raise), 이미지 EXIF 제거.

    반환 {ok:True} 또는 예외(호출측이 400/429 매핑). image_bytes 는 이미 매직 검사됨."""
    name = (name or "").strip()[:NAME_MAX]
    body = (body or "").strip()[:BODY_MAX]
    if not name or not body:
        raise ValueError("이름과 내용을 입력해 주세요.")
    now = time.time()
    if ip and now - _LAST_POST_BY_IP.get(ip, 0) < POST_MIN_INTERVAL_S:
        raise _TooFast("너무 빠릅니다. 잠시 후 다시 시도해 주세요.")
    image_name = None
    if image_bytes:
        image_name = save_post_image(board_id, image_bytes)   # 실패 시 예외 전파
    if ip:
        _LAST_POST_BY_IP[ip] = now
    entry = {"id": "pst_" + secrets.token_hex(6), "name": name, "body": body,
             "image": image_name, "at": _now(), "ip": ip}
    with _posts_lock(board_id):
        posts = load_posts(board_id)
        posts.append(entry)
        if len(posts) > POSTS_CAP:
            posts = posts[-POSTS_CAP:]
        _save_posts(board_id, posts)
    return entry


def delete_post(board_id: str, post_id: str) -> bool:
    removed = None
    with _posts_lock(board_id):
        posts = load_posts(board_id)
        keep = []
        for p in posts:
            if p.get("id") == post_id:
                removed = p
            else:
                keep.append(p)
        if removed is None:
            return False
        _save_posts(board_id, keep)
    # 첨부 이미지 동반 삭제
    if removed.get("image"):
        tgt = image_path(board_id, removed["image"])
        if tgt:
            try:
                tgt.unlink()
            except Exception:
                pass
    return True


class _TooFast(Exception):
    """IP 간격 제한 — 호출측이 429 로 매핑."""
    pass


TooFast = _TooFast
