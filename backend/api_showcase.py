"""
api_showcase.py — 공개파일 라이브 서빙 (인덱싱 없음).

공개 Worker 가 이 엔드포인트로 갤러리를 **실시간**으로 그린다. 사전 인덱싱·manifest·
썸네일 사전 업로드가 없다 — 파일시스템이 곧 진실이라, 파일을 옮기거나 지우면 즉시 반영.
  · /showcase/list/{slug}?path=   — 그 바스켓의 한 디렉토리를 즉석에서 훑어 목록 반환.
  · /showcase/thumb/{slug}/{fid}?rel=  — 썸네일을 그 자리에서 생성(Worker 가 R2 에 캐시).
  · /showcase/media/{slug}/{fid}?rel=  — 원본(EXIF 제거·동영상 H.264 변환·Range).
  · /showcase/subtitle/{slug}/{fid}?rel=&cls= — 형제 자막(srt/ass/smi/vtt)을 WebVTT 로 변환.
보안: X-Showcase-Secret(Worker 만 보유) + slug→바스켓→folder 소속 + 경로 이탈 방어.
raw 절대경로는 절대 안 받는다 — folder_id + 발행 폴더 기준 상대경로(rel)만.

이 라우트들은 is_public_remote_path 에서 /showcase/* 로 열려 터널로 접근(자체 시크릿 게이트).
"""

import os
import json
import asyncio
import hashlib
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

import thumbnails
import nas_subtitle
import hls_ladder

router = APIRouter(prefix="/showcase", tags=["showcase"])

_ROOT = Path(__file__).resolve().parent.parent
_STATE = _ROOT / "data" / "showcase_state.json"
_WEB_MEDIA = _ROOT / "data" / "showcase_stage" / "media_web"   # 트랜스코드 로컬 캐시
_WEB_MEDIA_CAP = 30 * 1024 * 1024 * 1024   # 렌디션 캐시 LRU 상한(전부 파생물 — 재생성 가능)
_EXCLUDE_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", ".Trash", "thumbnail_cache"}
_THUMB_SIZE = 512


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


def _load_state() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _check_secret(secret_header: str) -> None:
    secret = _read_env("SHOWCASE_ORIGIN_SECRET")
    if not secret or secret_header != secret:
        raise HTTPException(status_code=403, detail="forbidden")


def _basket(state: dict, slug: str) -> dict:
    b = next((x for x in state.get("baskets", []) if x.get("slug") == slug), None)
    if not b:
        raise HTTPException(status_code=404, detail="no such gallery")
    return b


def _basket_fids(state: dict, basket: dict) -> list:
    if basket.get("all_folders"):
        return [f.get("id") for f in state.get("folders", [])]
    return list(basket.get("folder_ids", []))


def _folder(state: dict, fid: str) -> dict:
    return next((f for f in state.get("folders", []) if f.get("id") == fid), None)


def _safe_abspath(base: str, rel: str):
    """base/rel 을 절대경로로 — base 하위여야(경로 이탈 방어). 아니면 None."""
    base_abs = os.path.abspath(base)
    target = os.path.abspath(os.path.join(base_abs, rel or ""))
    if target == base_abs or target.startswith(base_abs + os.sep):
        return target
    return None


def _resolve(slug: str, fid: str, rel: str, secret_header: str):
    """공통 검증 — 시크릿 + slug→바스켓 + fid 소속 + 경로 이탈. (folder, abspath) 반환."""
    _check_secret(secret_header)
    state = _load_state()
    basket = _basket(state, slug)
    if fid not in _basket_fids(state, basket):
        raise HTTPException(status_code=404, detail="not in gallery")
    folder = _folder(state, fid)
    if not folder:
        raise HTTPException(status_code=404, detail="no folder")
    abspath = _safe_abspath(folder.get("path", ""), rel)
    if not abspath or not os.path.isfile(abspath):
        raise HTTPException(status_code=404, detail="not found")
    return folder, abspath


@router.get("/list/{slug}")
async def list_dir(slug: str, path: str = Query(default=""), x_showcase_secret: str = Header(default="")):
    """바스켓의 한 디렉토리를 즉석에서 훑어 목록 반환. path 는 '<fid>/<하위경로>'.
    빈 path = 바스켓 루트(담긴 폴더들 나열)."""
    _check_secret(x_showcase_secret)
    state = _load_state()
    basket = _basket(state, slug)
    fids = _basket_fids(state, basket)
    folders = [f for f in state.get("folders", []) if f.get("id") in fids]

    if not path:
        # 바스켓 루트 — 담긴 폴더들을 디렉토리로 나열.
        dirs = [{"name": f.get("title") or Path(f.get("path", "")).name, "path": f.get("id")}
                for f in folders]
        return {"title": basket.get("title") or "공개파일", "path": "", "dirs": dirs, "items": []}

    # path = '<fid>' 또는 '<fid>/<sub>'
    fid, _, sub = path.partition("/")
    if fid not in fids:
        raise HTTPException(status_code=404, detail="not in gallery")
    folder = _folder(state, fid)
    if not folder:
        raise HTTPException(status_code=404, detail="no folder")
    base = folder.get("path", "")
    target = _safe_abspath(base, sub)
    if not target or not os.path.isdir(target):
        raise HTTPException(status_code=404, detail="not a dir")
    mode = folder.get("mode", "media")

    dirs, items, sub_files = [], [], []
    try:
        entries = sorted(os.scandir(target), key=lambda e: e.name)
    except OSError:
        entries = []
    for e in entries:
        if e.name.startswith("."):
            continue
        try:
            if e.is_dir():
                if e.name in _EXCLUDE_DIRS:
                    continue
                child = f"{fid}/{sub + '/' if sub else ''}{e.name}"
                dirs.append({"name": e.name, "path": child})
            elif e.is_file():
                kind = thumbnails.classify(e.path)
                if os.path.splitext(e.name)[1].lower() in nas_subtitle.SUBTITLE_EXTENSIONS:
                    sub_files.append((e.name, e.path, int(e.stat().st_mtime)))
                if mode == "media" and kind is None:
                    continue
                st = e.stat()
                rel = os.path.relpath(e.path, os.path.abspath(base)).replace(os.sep, "/")
                items.append({
                    "fid": fid, "rel": rel, "title": e.name,
                    "kind": kind or "file", "mtime": int(st.st_mtime),
                    "thumb": kind in ("photo", "video"),
                })
        except OSError:
            continue
    if sub_files:
        _attach_subs(items, sub_files, os.path.abspath(base))
    return {"title": basket.get("title") or "공개파일", "path": path, "fid": fid,
            "dirs": dirs, "items": items}


def _decode_text(raw: bytes) -> str | None:
    for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr", "shift_jis", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def _smi_lang_entries(spath: str):
    """SMI 언어 클래스 목록 — 헤더 선언을 본문의 실제 Class= 와 대조해 고친다.
    옛 SMI 는 헤더가 EGCC(English) 선언인데 본문은 KRCC 인 불일치가 흔하다."""
    import re
    entries = nas_subtitle._detect_smi_languages(Path(spath))
    try:
        text = _decode_text(Path(spath).read_bytes())
        if text:
            body = re.findall(r"<P\s+Class\s*=\s*(\w+)", text, re.I)
            if body:
                bodyset = {c.upper() for c in body}
                ok = [e for e in entries if e[0].upper() in bodyset]
                if ok:
                    return ok
                from collections import Counter
                top = Counter(c.upper() for c in body).most_common(1)[0][0]
                label = "한국어" if top.upper().startswith("KR") else "자막"
                return [(top, "ko" if top.upper().startswith("KR") else "", label)]
    except Exception:
        pass
    return entries


def _attach_subs(items, sub_files, base: str) -> None:
    """비디오 아이템에 형제 자막을 subs 로 붙인다 — 자막 파일명이 비디오 이름으로
    시작해야 짝(영화.srt·영화.ko.srt). smi 는 내부 언어 클래스별로 나눈다."""
    smi_langs = {}
    for it in items:
        if it.get("kind") != "video":
            continue
        stem = os.path.splitext(it["title"])[0].lower()
        subs = []
        for name, spath, smtime in sub_files:
            sstem, sext = os.path.splitext(name)
            # 정확히 같거나 '이름.' 접두(영화.ko.srt)만 — 단순 startswith 는
            # '영화2.smi' 가 '영화.mp4' 에도 붙는 과잉 매칭.
            low = sstem.lower()
            if low != stem and not low.startswith(stem + "."):
                continue
            srel = os.path.relpath(spath, base).replace(os.sep, "/")
            if sext.lower() == ".smi":
                if spath not in smi_langs:
                    smi_langs[spath] = _smi_lang_entries(spath)
                for cls_name, lang_code, lang_label in smi_langs[spath]:
                    subs.append({"rel": srel, "label": lang_label or "자막",
                                 "lang": lang_code, "cls": cls_name, "mtime": smtime})
            else:
                remaining = sstem[len(stem):]
                lang = remaining[1:].lower() if remaining.startswith(".") else ""
                label = nas_subtitle.LANG_NAMES.get(lang, lang) or "자막"
                subs.append({"rel": srel, "label": label, "lang": lang, "mtime": smtime})
        if subs:
            priority = {"ko": 0, "": 1, "en": 2}
            subs.sort(key=lambda s: (priority.get(s.get("lang", ""), 9), s.get("lang", "")))
            it["subs"] = subs


@router.get("/thumb/{slug}/{fid}")
async def thumb(slug: str, fid: str, rel: str = Query(...), x_showcase_secret: str = Header(default="")):
    """썸네일을 그 자리에서 생성해 JPEG 바이트로 반환. Worker 가 R2 에 캐시(mtime 버전키)."""
    folder, abspath = _resolve(slug, fid, rel, x_showcase_secret)
    kind = thumbnails.classify(abspath)
    if kind not in ("photo", "video"):
        raise HTTPException(status_code=404, detail="no thumb")
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
        tmp = tf.name
    try:
        ok = await run_in_threadpool(thumbnails.generate_thumbnail, abspath, tmp, _THUMB_SIZE, kind)
        if not ok or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            raise HTTPException(status_code=500, detail="thumb gen failed")
        data = Path(tmp).read_bytes()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


async def _live_stream(first: bytes, proc, tmp: str, cache_dst: str):
    """스트리밍 트랜스코드 본문 — ffmpeg stdout 을 흘리면서 같은 바이트를 tmp(.part)에
    쓴다(파이썬 tee). 완주 시 faststart 리먹스로 캐시 완성, 시청 중단 시엔
    백그라운드로 마저 인코딩해 캐시를 완성."""
    f = open(tmp, "wb")
    try:
        f.write(first)
        yield first
        while True:
            chunk = await run_in_threadpool(proc.stdout.read, 1 << 16)
            if not chunk:
                break
            f.write(chunk)
            yield chunk
        f.close()
        await run_in_threadpool(thumbnails.finish_stream_transcode, proc, tmp, cache_dst)
    except (asyncio.CancelledError, GeneratorExit):
        f.close()
        thumbnails.detach_stream_transcode(proc, tmp, cache_dst)
        raise


async def _offset_stream_body(head: bytes, proc):
    """오프셋(t>0) 스트림 본문 — 캐시 의무 없음, 중단 시 즉시 kill."""
    try:
        yield head
        while True:
            chunk = await run_in_threadpool(proc.stdout.read, 1 << 16)
            if not chunk:
                break
            yield chunk
        await run_in_threadpool(proc.wait)
    except (asyncio.CancelledError, GeneratorExit):
        thumbnails.kill_stream(proc)
        raise


async def _read_init_segment(proc) -> bytes:
    """fMP4 init 세그먼트(ftyp+moov)가 통째로 잡힐 때까지 모은다(duration 패치용)."""
    head = b""
    while len(head) < (1 << 18):
        chunk = await run_in_threadpool(proc.stdout.read, 1 << 16)
        if not chunk:
            break
        head += chunk
        if b"moof" in head:
            break
    return head


@router.get("/media/{slug}/{fid}")
async def media(slug: str, fid: str, rel: str = Query(...), t: float = Query(default=0),
                q: str = Query(default=""),
                x_showcase_secret: str = Header(default="")):
    """원본 서빙 — EXIF 제거·동영상 H.264 변환(스트리밍)·Range(FileResponse 자동).
    t>0 = 그 지점부터의 오프셋 스트림(첫 시청 중 멀리 seek — SPA 가 스왑해 요청).
    q=low = 저대역 렌디션(720p·1.2Mbps 상한, h264) — 느린 회선(차 브라우저 등)용.
    q=lowh = 같은 저대역의 HEVC 판(~0.75Mbps) — SPA 가 mediaCapabilities 로 하드웨어
    디코드를 확인한 기기만 요청한다(안 되는 기기는 low 로 폴백). SPA 가
    navigator.connection 으로 자동 선택하거나 사용자가 토글한다.

    ★저대역은 캐시 슬롯이 갈린다(`<key>.low.mp4` / `<key>.lowh.mp4`). 같은 슬롯을
    쓰면 한 번 저대역으로 본 영상이 데스크탑에도 720p 로 나가고 그 반대도 생긴다
    (오프셋 스트림 t= 가 캐시 키를 갈라야 했던 것과 같은 부류)."""
    folder, abspath = _resolve(slug, fid, rel, x_showcase_secret)
    settings = _load_state().get("settings") or {}
    kind = thumbnails.classify(abspath)
    low = q in ("low", "lowh", "tiny", "nano")   # tiny/nano=HLS 사다리 하부 렁 — hls_ladder 참조
    qual = q if low else ""

    # ⓪ 오프셋 스트림 — 항상 0 기준 fMP4 로 결정론 응답(SPA 스왑 계약).
    #    소스는 완성 캐시가 있으면 캐시(-c copy, 즉시)·없으면 원본(재인코딩).
    if kind == "video" and t > 0:
        key = hashlib.md5(f"{fid}/{rel}".encode("utf-8")).hexdigest()[:16]
        cache = _WEB_MEDIA / fid / (key + (f".{qual}.mp4" if low else ".mp4"))
        use_cache = cache.exists() and cache.stat().st_size > 0
        src = str(cache) if use_cache else abspath
        # 캐시가 소스면 그 캐시가 이미 요청된 화질이므로 그냥 -c copy(재인코딩 0).
        # 원본이 소스일 때만: 저대역이면 저대역 재인코딩 / 아니면 웹 코덱 여부로 v-copy 판정.
        vcopy = (False if (use_cache or low)
                 else await run_in_threadpool(thumbnails.video_codec_web_playable, abspath))
        total = await run_in_threadpool(thumbnails.probe_video_duration, src)
        proc = thumbnails.start_offset_stream(src, t, copy=use_cache, video_copy=vcopy,
                                              quality=("" if use_cache else qual))
        head = await _read_init_segment(proc)
        if not head and use_cache:
            # 캐시 스트림 복사 실패(드묾) — 원본 재인코딩 재시도.
            thumbnails.kill_stream(proc)
            total = await run_in_threadpool(thumbnails.probe_video_duration, abspath)
            vcopy = (False if low
                     else await run_in_threadpool(thumbnails.video_codec_web_playable, abspath))
            proc = thumbnails.start_offset_stream(abspath, t, copy=False, video_copy=vcopy,
                                                  quality=qual)
            head = await _read_init_segment(proc)
        if not head:
            thumbnails.kill_stream(proc)
            raise HTTPException(status_code=500, detail="offset stream failed")
        head = thumbnails.patch_fmp4_duration(head, max(total - t, 0.0))
        return StreamingResponse(
            _offset_stream_body(head, proc), media_type="video/mp4",
            headers={"X-Transcode-Live": "1", "Cache-Control": "no-store"})

    # ① 이미지 + EXIF 제거 → 위치·기기 메타 벗긴 JPEG.
    if kind == "photo" and settings.get("strip_exif", True) and thumbnails.needs_exif_strip(abspath):
        data = await run_in_threadpool(thumbnails.sanitize_image_bytes, abspath)
        if data:
            return Response(content=data, media_type="image/jpeg")

    # ② 동영상 + 브라우저 비재생 코덱 → H.264 MP4.
    #    캐시가 있으면 직행(Range·seek 완전). 없으면 전체 변환을 기다리지 않고 fMP4 를
    #    인코딩되는 대로 흘린다(긴 영상도 수 초 안에 재생 시작) — 같은 인코딩이 tee 로
    #    faststart 캐시도 만들어(인코딩 1회) 다음 재생부터는 캐시 직행.
    if kind == "video" and settings.get("transcode_video", True):
        key = hashlib.md5(f"{fid}/{rel}".encode("utf-8")).hexdigest()[:16]
        cache = _WEB_MEDIA / fid / (key + (f".{qual}.mp4" if low else ".mp4"))
        if cache.exists() and cache.stat().st_size > 0:
            hls_ladder.touch(str(cache))   # LRU 근거 — 재생(HLS 세그먼트 포함)마다 젊어진다
            return FileResponse(str(cache), media_type="video/mp4")
        # ★저대역은 코덱과 무관하게 항상 변환한다 — h264 원본이라도 해상도·비트레이트를
        #   내리는 게 목적이라 '이미 재생 가능'은 이유가 되지 못한다(원본 경로와 갈리는 곳).
        if low or await run_in_threadpool(thumbnails.needs_video_transcode, abspath):
            duration = await run_in_threadpool(thumbnails.probe_video_duration, abspath)
            # 비디오가 이미 웹 코덱(h264 등, 오디오만 DTS/AC3)이면 -c:v copy —
            # 1080p 재인코딩 없이 리먹스 속도로 흘린다. 저대역은 해당 없음.
            vcopy = (False if low
                     else await run_in_threadpool(thumbnails.video_codec_web_playable, abspath))
            proc, tmp = thumbnails.start_stream_transcode(abspath, str(cache), video_copy=vcopy,
                                                          quality=qual)
            # init 세그먼트(ftyp+moov)가 통째로 잡힐 때까지 모아 duration 패치 —
            # 안 하면 empty_moov 생방송이 '버퍼된 만큼'을 총 길이로 표시(몇 초짜리로 보임).
            head = await _read_init_segment(proc)
            if head:
                head = thumbnails.patch_fmp4_duration(head, duration)
                # X-Transcode-Live: 생방송(중단되면 반쪽)이라 Worker 가 R2 캐시하지 않게.
                return StreamingResponse(
                    _live_stream(head, proc, tmp, str(cache)),
                    media_type="video/mp4",
                    headers={"X-Transcode-Live": "1", "Cache-Control": "no-store"})
            # 첫 바이트도 못 뽑음(ffmpeg 부재 등) — 정리 후 원본 폴백.
            await run_in_threadpool(thumbnails.finish_stream_transcode, proc, tmp, str(cache))

    # ③ 오디오 — filename 을 주면 Content-Disposition: attachment 라 브라우저가 재생
    #    대신 내려받는다. inline + 명시 MIME 으로 <audio> 가 물게. Range 는 FileResponse.
    if kind == "audio":
        return FileResponse(abspath, media_type=thumbnails.audio_mime(abspath))

    # 그 외(또는 폴백) — FileResponse 가 content-type + Range 자동 처리.
    return FileResponse(abspath, filename=os.path.basename(abspath))


@router.get("/hls/{slug}/{fid}")
async def hls_playlist(slug: str, fid: str, rel: str = Query(...), r: str = Query(default=""),
                       x_showcase_secret: str = Header(default="")):
    """HLS 적응형 플레이리스트 — r 없음=마스터, r=렁(tiny|low|orig)=변형.

    로컬 파일 사다리(hls_ladder): 렌디션 = 기존 캐시 슬롯 그대로(전역 sidx fMP4 한
    파일), 세그먼트 = 기존 media URL 의 byterange — 새 저장 구조가 없다. 사다리가
    아직 없으면 404(표면이 기존 프로그레시브로 폴백)하되 결핍 렁 빌드를 enqueue —
    첫 시청이 tee 로 만든 캐시가 첫 렁이 되어, 볼수록 사다리가 자란다.
    ★플레이리스트는 no-store — 렁 가용성이 빌드에 따라 변한다(Worker·엣지 동형)."""
    from urllib.parse import quote
    folder, abspath = _resolve(slug, fid, rel, x_showcase_secret)
    if thumbnails.classify(abspath) != "video":
        raise HTTPException(status_code=404, detail="not a video")
    key = hashlib.md5(f"{fid}/{rel}".encode("utf-8")).hexdigest()[:16]
    orig_cache = str(_WEB_MEDIA / fid / (key + ".mp4"))
    v = int(os.stat(abspath).st_mtime)
    base = f"/s/{quote(slug, safe='')}"
    qs = f"rel={quote(rel, safe='')}&v={v}"

    if not r:
        rungs = await run_in_threadpool(hls_ladder.available_rungs, orig_cache)
        # 결핍 렁 빌드 enqueue(중복 dedupe·전역 단일 워커) + 10분 주기 LRU 정리
        hls_ladder.ensure_ladder(abspath, orig_cache,
                                 prune_root=str(_WEB_MEDIA), prune_cap=_WEB_MEDIA_CAP)
        if not rungs:
            raise HTTPException(status_code=404, detail="사다리 준비 전 — 프로그레시브로 폴백")
        body = hls_ladder.master_m3u8(
            rungs, lambda rung: f"{base}/hls/{quote(fid, safe='')}?{qs}&r={rung}")
    else:
        if r not in hls_ladder.RUNG_ORDER:
            raise HTTPException(status_code=404, detail="없는 렁")
        path = hls_ladder.rung_path(orig_cache, r)
        idx = await run_in_threadpool(hls_ladder.parse_sidx_file, path)
        if not idx:
            raise HTTPException(status_code=404, detail="렁 캐시 없음")
        # rv=렌디션 파일 크기 — 재인코딩·재인덱스로 바이트가 바뀌면 Worker R2 캐시
        # 키가 갈리게(낡은 R2 바이트에 새 색인의 byterange 를 대면 재생이 깨진다).
        # mtime 은 LRU touch 로 매 시청 변해 캐시 재사용을 죽이므로 크기를 쓴다.
        rv = os.stat(path).st_size
        q = "" if r == "orig" else r
        seg = (f"{base}/media/{quote(fid, safe='')}?{qs}"
               + (f"&q={q}" if q else "") + f"&rv={rv}")
        hls_ladder.touch(path)
        body = hls_ladder.variant_m3u8(idx, seg)
    return Response(body, media_type="application/vnd.apple.mpegurl",
                    headers={"Cache-Control": "no-store"})


def _subtitle_vtt(abspath: str, cls: str) -> str:
    """자막 파일 → WebVTT 텍스트. 인코딩 자동 감지(한국어 cp949 흔함)."""
    content = _decode_text(Path(abspath).read_bytes())
    if content is None:
        raise HTTPException(status_code=400, detail="자막 인코딩 인식 불가")
    suffix = os.path.splitext(abspath)[1].lower()
    if suffix == ".vtt":
        return content if content.lstrip().startswith("WEBVTT") else "WEBVTT\n\n" + content
    if suffix == ".srt":
        return nas_subtitle.srt_to_vtt(content)
    if suffix in (".ass", ".ssa"):
        return nas_subtitle.ass_to_vtt(content)
    if suffix == ".smi":
        if not cls:
            langs = _smi_lang_entries(abspath)
            cls = langs[0][0] if langs else "KRCC"
        out = nas_subtitle.smi_to_vtt(content, lang_class=cls)
        if "-->" not in out:
            # 요청 클래스가 본문에 없음(헤더-본문 불일치 등) — 본문 최빈 클래스로 재시도.
            import re
            from collections import Counter
            body = re.findall(r"<P\s+Class\s*=\s*(\w+)", content, re.I)
            if body:
                out = nas_subtitle.smi_to_vtt(
                    content, lang_class=Counter(c.upper() for c in body).most_common(1)[0][0])
        return out
    raise HTTPException(status_code=400, detail="지원하지 않는 자막 형식")


_VTT_TIME_RE = None


def _shift_vtt(vtt: str, shift: float) -> str:
    """VTT 큐 시각을 shift 초만큼 앞으로 당긴다(오프셋 스트림의 0 기준 타임라인 정렬).
    당겨서 0 이전에 끝나는 큐는 버린다."""
    import re
    global _VTT_TIME_RE
    if _VTT_TIME_RE is None:
        _VTT_TIME_RE = re.compile(
            r"(\d{2,}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2,}):(\d{2}):(\d{2})\.(\d{3})")

    def fmt(sec: float) -> str:
        ms = max(0, int(round(sec * 1000)))
        return f"{ms//3600000:02d}:{ms%3600000//60000:02d}:{ms%60000//1000:02d}.{ms%1000:03d}"

    out = []
    for line in vtt.split("\n"):
        m = _VTT_TIME_RE.search(line)
        if not m:
            out.append(line)
            continue
        g = [int(x) for x in m.groups()]
        start = g[0]*3600 + g[1]*60 + g[2] + g[3]/1000 - shift
        end = g[4]*3600 + g[5]*60 + g[6] + g[7]/1000 - shift
        if end <= 0:
            out.append("__DROP__")
            continue
        out.append(line[:m.start()] + f"{fmt(max(start, 0))} --> {fmt(end)}" + line[m.end():])
    # 버린 큐는 타임라인 줄 + 본문을 함께 제거
    cleaned, skip = [], False
    for line in out:
        if line == "__DROP__":
            skip = True
            if cleaned and cleaned[-1].strip().isdigit():
                cleaned.pop()          # 큐 번호 줄
            continue
        if skip:
            if line.strip() == "":
                skip = False
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


@router.get("/subtitle/{slug}/{fid}")
async def subtitle(slug: str, fid: str, rel: str = Query(...), cls: str = Query(default=""),
                   shift: float = Query(default=0), x_showcase_secret: str = Header(default="")):
    """형제 자막 파일을 WebVTT 로 변환해 반환 — <track> 이 그대로 문다(nas_subtitle 재사용).
    shift>0 = 오프셋 스트림(media?t=)과 짝 — 큐 시각을 그만큼 당긴다."""
    folder, abspath = _resolve(slug, fid, rel, x_showcase_secret)
    if os.path.splitext(abspath)[1].lower() not in nas_subtitle.SUBTITLE_EXTENSIONS:
        raise HTTPException(status_code=404, detail="not a subtitle")
    vtt = await run_in_threadpool(_subtitle_vtt, abspath, cls)
    if shift > 0:
        vtt = _shift_vtt(vtt, shift)
    return Response(content=vtt, media_type="text/vtt; charset=utf-8",
                    headers={"Cache-Control": "public, max-age=86400"})
