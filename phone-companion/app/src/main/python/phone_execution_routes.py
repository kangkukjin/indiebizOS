"""Phone IBL execution and media routes; shares the authenticated app middleware."""
import asyncio
import json
import os
from fastapi import Request
from fastapi.responses import JSONResponse


def install(app, get_scratch, _save_audio_to_phone):
    @app.get("/ibl/capabilities")
    async def ibl_capabilities():
        from ibl_v2_entry import capabilities
        return capabilities()


    @app.post("/ibl/call")
    async def call_ibl_leaf(req: Request):
        from ibl_remote_call import receive
        payload = await req.json()
        return await asyncio.to_thread(receive, payload, get_scratch())


    @app.post("/ibl/execute")
    async def execute(req: Request):
        """정본 통합 실행기로 라우팅 — PC /ibl/execute 와 동일 계약.

        분산 라우팅은 엔진(ibl_engine.execute_ibl)이 액션 단위로 수행한다: 폰서 못 도는
        액션을 만나면 그 액션만 맥(연합 두뇌)에 위임(_forward_to_mac)하고 결과를 받아온다.
        합성 code(&/>>/??)의 각 leaf 가 chokepoint 를 거치므로 혼합 code 도 액션별로 쪼개져
        로컬/맥에서 따로 실행된다. 여기선 항상 로컬 엔진에 넘기면 됨(엔진이 알아서 라우팅)."""
        body = await req.json()
        code = body.get("code", "")
        if not code:
            return JSONResponse({"success": False, "error": "code 파라미터가 필요합니다."})

        # 빌림은 호출하는 주체가 액션 주체(설계결정 §6.4): 맥→폰 위임(forward_to_phone)이 호출자
        # 신원을 실어 보내면 그걸로 기록하고, 폰 자체 표면 호출(미동봉)이면 폰-자아("phone")로 떨어진다.
        agent_id = body.get("agent_id") or "phone"

        # 무거운 import(system_tools→api_engine 등)는 첫 호출 시 지연 — 트리 + env 준비 후라 안전.
        from system_tools import _execute_ibl_unified

        def _run():
            request = {"code": code}
            for key in ("edition", "inputs", "check", "resume", "files", "files_from"):
                if key in body:
                    request[key] = body[key]
            return _execute_ibl_unified(request, get_scratch(), agent_id=agent_id)

        # 엔진은 동기(내부에 자체 이벤트 루프 관리). 서버 asyncio 루프 블록 방지 위해 스레드로.
        result = await asyncio.to_thread(_run)

        obj = result
        if isinstance(obj, str):
            try:
                obj = json.loads(obj)
            except json.JSONDecodeError:
                return JSONResponse({"result": obj})
        # 분산 IBL: 맥서 위임받은 mp3(b64)를 폰 Music 폴더에 네이티브 저장(빌린 연산→로컬 산출물).
        # b64 는 WebView 로 안 보냄(Python↔Kotlin 으로만). 큰 파일도 JS 브리지 우회.
        if isinstance(obj, dict) and obj.get("download_in_client") and obj.get("b64"):
            obj = await asyncio.to_thread(_save_audio_to_phone, obj)
        return JSONResponse(obj)


    # === 조종실(수동) 폰-로컬 — 번역·검수·증류·사전 (2026-07-22 표면 분리) ==================
    # 조종실은 폰네이티브 3탭의 핵심(사용자 확정). 리모컨 은퇴 후 catch-all 404 로 끊겨 있던
    # /ibl/translate·validate·distill·actions/catalog 를 몸-로컬로 채운다.
    # 번역 = body_ask 컴파일러 재사용(능력 축=해마 — 폰은 해마가 없어 사전-동봉 Gemini 경로,
    # 소유-필터로 자기 어휘만). 검수·사전 = 정본 api_ibl 로직 그대로(레지스트리=폰 번들 사전).


    @app.post("/ibl/translate")
    async def ibl_translate(payload: dict):
        intent = str((payload or {}).get("intent") or "").strip()
        if not intent:
            return JSONResponse({"detail": "빈 명령입니다."}, status_code=400)

        def _run():
            from body_ask import _compile
            return _compile(intent)

        r = await asyncio.to_thread(_run)
        if not (r.get("ok") and r.get("code")):
            return JSONResponse({"detail": r.get("error") or "번역 실패"}, status_code=503)
        # 리터러시 병기: 이 몸이 어느 컴파일러로 번역했는지 (해마 용례가 없는 몸=사전-동봉 gemini)
        refs = ("(폰-로컬 컴파일: %s — 이 몸의 사전이 근거)" % r.get("compiler", "?")
                if not r.get("had_references") else "")
        return JSONResponse({"intent": intent, "ibl_code": r["code"],
                             "references": refs, "raw": r.get("raw") or r["code"]})


    @app.post("/ibl/validate")
    async def ibl_validate(payload: dict):
        # 정본 검수기 재사용 — 순수 함수(파싱+레지스트리 조회)라 직접 await. 빈 코드=400(HTTPException).
        import api_ibl

        class _Req:
            code = str((payload or {}).get("code") or "")
            edition = (payload or {}).get("edition")
            inputs = (payload or {}).get("inputs")

        return JSONResponse(await api_ibl.validate_ibl(_Req()))


    @app.post("/ibl/distill")
    async def ibl_distill(payload: dict):
        # 정본 distill_ibl 과 동형(경량 LLM 일반화·top_score<0.7 게이트). 폰의 축적은 폰-로컬
        # ibl_distilled.json — 로컬 해마 인덱스는 없으니 즉효는 없고, 재학습 코퍼스 몸별 분리에서 합류.
        intent = str((payload or {}).get("intent") or "").strip()
        code = str((payload or {}).get("code") or "").strip()
        if not intent or not code:
            return JSONResponse({"distilled": False, "reason": "intent/code 가 비어 있습니다."})

        def _run():
            from ibl_usage_rag import distill_experience
            tool_calls = [{"tool_name": "execute_ibl", "input": {"code": code}, "success": True}]
            return distill_experience(intent, tool_calls, float((payload or {}).get("top_score") or 0.0))

        try:
            ok = await asyncio.to_thread(_run)
            return JSONResponse({"distilled": bool(ok)})
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"distilled": False, "reason": str(e)})


    @app.get("/ibl/actions/catalog")
    async def ibl_catalog():
        # 조종실 'IBL 사전' 팔레트 — 폰 번들 레지스트리(자기 어휘만)가 그대로 카탈로그.
        import api_ibl
        return JSONResponse(await api_ibl.get_actions_catalog())


    # ============================================================================
    # 사진/미디어 서빙 — 폰 로컬 (몸-로컬 I/O, 맥 프록시 아님). ★catch-all 보다 먼저 등록.
    # [self:photo] 가 반환하는 records.image = "/photo/thumbnail?path=<폰 MediaStore 경로>" 를
    # 앱모드 image_grid 가 <img src> 로 부른다. 이 경로는 *폰 자신*의 파일(/storage/emulated/0/...)
    # 이라 catch-all 로 맥에 프록시하면 맥엔 그 경로가 없어 404 → 사진 뷰어가 통째로 깨졌다(원래 신고건).
    # 사진 뷰어는 몸-로컬: 폰이 자기 미디어를 직접 서빙한다(맥이 자기 미디어를 api_photo 로 서빙하듯,
    # file_index 가 Spotlight↔MediaStore 로 몸 분기하듯 — 패리티 기본·드리프트 0). 정본 api_photo 의
    # 함수(PIL 썸네일·EXIF 회전·FileResponse)를 그대로 위임한다. 폰 사진은 전부 JPEG(A36 검증)라 PIL OK.
    # 지연 import = serve() 의 _init_base 후 호출돼 sys.path/INDIEBIZ_BASE_PATH 준비됨.
    # ============================================================================
    @app.get("/photo/thumbnail")
    async def _photo_thumbnail(path: str, size: int = 200):
        from api_photo import get_thumbnail
        return await get_thumbnail(path=path, size=size)


    @app.get("/photo/video-thumbnail")
    async def _photo_video_thumbnail(path: str, size: int = 200):
        # 동영상 프레임 썸네일 — api_photo 는 ffmpeg 를 쓰지만 폰엔 ffmpeg 가 없다. Android 네이티브
        # ThumbnailUtils(OS 디코더, PhoneActions.videoThumbnail)로 프레임을 뽑아 JPEG 로 서빙한다.
        # 캐시는 api_photo 와 같은 THUMBNAIL_CACHE_DIR 공유(반복 그리드 로드 시 재디코딩 방지).
        # 네이티브 실패 시 정본 api_photo(ffmpeg) 폴백 — 폰엔 보통 미가용이나 맥/일관성 유지.
        import hashlib
        from fastapi.responses import FileResponse

        def _native():
            try:
                from api_photo import THUMBNAIL_CACHE_DIR
                os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)
                cache = os.path.join(
                    THUMBNAIL_CACHE_DIR,
                    hashlib.md5(f"pv:{path}:{size}".encode()).hexdigest() + ".jpg")
                if (os.path.exists(cache) and os.path.exists(path)
                        and os.path.getmtime(cache) >= os.path.getmtime(path)):
                    return cache
                from java import jclass  # Chaquopy — 폰 네이티브에만 존재
                PA = jclass("com.indiebiz.phoneagent.PhoneActions")
                raw = PA.videoThumbnail(path, int(size))
                data = bytes(raw) if raw else b""
                if not data:
                    return None
                with open(cache, "wb") as fh:
                    fh.write(data)
                return cache
            except Exception:
                return None

        cache = await asyncio.to_thread(_native)
        if cache:
            return FileResponse(cache, media_type="image/jpeg")
        from api_photo import get_video_thumbnail
        return await get_video_thumbnail(path=path, size=size)


    @app.get("/photo/image")
    async def _photo_image(path: str):
        # 원본 이미지(라이트박스·상세). FileResponse 라 실제 폰 경로면 그대로 서빙.
        from api_photo import get_image
        return await get_image(path=path)


    @app.get("/photo/video")
    async def _photo_video(path: str, request: Request):
        # 동영상 재생(Range 지원). FileResponse 라 실제 폰 경로면 그대로 서빙.
        from api_photo import get_video
        return await get_video(path=path, request=request)
