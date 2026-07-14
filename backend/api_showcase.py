"""
api_showcase.py — 공개파일 온디맨드 원본 서빙 (option 1).

공개 Worker 가 사진/동영상 클릭 시 이 엔드포인트로 원본 하나를 끌어간다(그다음 R2 캐시).
보안 3중:
  1) X-Showcase-Secret 헤더 == .env SHOWCASE_ORIGIN_SECRET (Worker 만 보유).
  2) 대상 폴더가 실제 공개(showcase_state) + 비공개(hidden) 아님.
  3) 색인의 실제 경로가 그 공개 폴더 하위인지(경로 이탈 이중 방어).
raw 경로는 절대 받지 않는다 — folder_id/item_id 만 받아 맥의 비공개 색인으로 해소.

이 라우트는 is_public_remote_path 에 등록돼 터널로 접근 가능(자체 시크릿 게이트 보유).
"""

import os
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import FileResponse, Response

import thumbnails

router = APIRouter(prefix="/showcase", tags=["showcase"])

_ROOT = Path(__file__).resolve().parent.parent
_STATE = _ROOT / "data" / "showcase_state.json"
_STAGE = _ROOT / "data" / "showcase_stage"
_INDEX = _STAGE / "_origin_index.json"
# 트랜스코드한 웹 동영상 로컬 캐시(맥 측 — Worker 재요청 시 재인코딩 회피).
_WEB_MEDIA = _STAGE / "media_web"


def _read_env(name: str) -> str:
    v = os.environ.get(name, "")
    if v:
        return v
    envp = _ROOT / ".env"
    if envp.exists():
        try:
            for line in envp.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return ""


def _load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


@router.get("/origin/{folder_id}/{item_id}")
async def origin(folder_id: str, item_id: str, x_showcase_secret: str = Header(default="")):
    secret = _read_env("SHOWCASE_ORIGIN_SECRET")
    if not secret or x_showcase_secret != secret:
        raise HTTPException(status_code=403, detail="forbidden")

    state = _load_json(_STATE) or {}
    folder = next((f for f in state.get("folders", []) if f.get("id") == folder_id), None)
    if not folder:
        raise HTTPException(status_code=404, detail="not published")
    # 서빙 조건 — 폴더가 어떤 바스켓(비밀주소)에 담겼는가. bare 루트는 잠겨 있어
    # 바스켓만이 노출 경로다. all_folders(전체 공개 갤러리)는 모든 폴더 포함.
    # (Worker 가 이미 slug→바스켓→folder 소속을 검증하고 넘겨준다. 여기선 재확인.)
    served = any(b.get("all_folders") or folder_id in b.get("folder_ids", [])
                 for b in state.get("baskets", []))
    if not served:
        raise HTTPException(status_code=404, detail="not published")

    idx = _load_json(_INDEX) or {}
    path = (idx.get(folder_id) or {}).get(item_id)
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="not found")

    # 경로 이탈 이중 방어 — 색인 경로가 실제 공개 폴더 하위여야.
    base = os.path.abspath(folder.get("path", ""))
    if not os.path.abspath(path).startswith(base + os.sep):
        raise HTTPException(status_code=403, detail="path escape")

    settings = state.get("settings") or {}
    kind = thumbnails.classify(path)

    # ① 이미지 + EXIF 제거 설정 → 위치·기기 메타 벗긴 JPEG 로 서빙(프라이버시).
    if kind == "photo" and settings.get("strip_exif", True) and thumbnails.needs_exif_strip(path):
        data = thumbnails.sanitize_image_bytes(path)
        if data:
            return Response(content=data, media_type="image/jpeg")
        # 실패 시 원본 폴백(서빙 실패보다 낫다) — 아래로.

    # ② 동영상 + 트랜스코드 설정 + 브라우저 비재생 컨테이너 → H.264 MP4.
    if kind == "video" and settings.get("transcode_video", True) and thumbnails.needs_video_transcode(path):
        cache = _WEB_MEDIA / folder_id / (item_id + ".mp4")
        if not (cache.exists() and cache.stat().st_size > 0):
            thumbnails.transcode_video_to_mp4(path, str(cache))
        if cache.exists() and cache.stat().st_size > 0:
            return FileResponse(str(cache), media_type="video/mp4")
        # 실패 시 원본 폴백.

    # 그 외(또는 폴백) — FileResponse 가 content-type + Range(스크러빙) 자동 처리.
    return FileResponse(path, filename=os.path.basename(path))
