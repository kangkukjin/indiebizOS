"""Signed local document-engine I/O, included under the owner document router."""
from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter()


def engine():
    from api_documents import service
    from document_office import OfficeEngine
    return OfficeEngine(service())


@router.get("/engine-io/{session_id}/content")
def content(session_id: str, ticket: str):
    from api_documents import invoke
    data, _ = invoke(engine().content, session_id, ticket)
    return Response(data, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


@router.post("/engine-io/{session_id}/callback")
async def callback(session_id: str, ticket: str, request: Request):
    from api_documents import invoke
    from starlette.concurrency import run_in_threadpool
    from fastapi import HTTPException
    import json
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 1024 * 1024:
            raise HTTPException(413, "편집 엔진 콜백 크기 초과")
    try:
        body = json.loads(data)
        if not isinstance(body, dict):
            raise ValueError()
    except ValueError as exc:
        raise HTTPException(400, "편집 엔진 콜백 형식 오류") from exc
    return await run_in_threadpool(invoke, engine().callback, session_id, ticket, body,
                                  request.headers.get("authorization", ""))


@router.get("/engine-io/{session_id}/plugin/{ticket}/{asset}")
def plugin(session_id: str, ticket: str, asset: str, request: Request):
    from api_documents import invoke
    from document_office import settings
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi import HTTPException
    from pathlib import Path
    from html import escape
    from urllib.parse import urlencode
    _, session = invoke(engine().ticket, session_id, ticket)
    if asset == "config.json":
        query = urlencode({"channel": ticket, "ib_parent": session["plugin_parent"]})
        return JSONResponse({"name": "IndieBiz 문서 AI", "guid": "asc.{49DC913A-68D4-44AA-8A07-88107E1F9012}",
            "baseUrl": str(request.url).rsplit("/", 1)[0] + "/",
            "variations": [{"description": "선택 수정", "url": "index.html?" + query,
                "isViewer": False, "EditorsSupport": ["word"], "isVisual": False,
                "isModal": False, "isInsideMode": False, "initDataType": "none", "initData": "", "buttons": []}]},
            headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": settings()["url"]})
    if asset == "index.html":
        sdk = escape(settings()["url"].rstrip("/") + "/sdkjs-plugins/v1/plugins.js", quote=True)
        return HTMLResponse('<!doctype html><meta charset="utf-8"><script src="'+sdk+'"></script><script src="plugin.js"></script>',
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    if asset == "plugin.js":
        return Response((Path(__file__).resolve().parents[1]/"static/document_plugin/plugin.js").read_text(),
                        media_type="application/javascript", headers={"Cache-Control": "no-store"})
    raise HTTPException(404, "없는 문서 플러그인 자산입니다")


@router.get("/convert-io/{conversion_id}")
def conversion_content(conversion_id: str, ticket: str):
    from api_documents import invoke, service
    from document_formats import content
    return Response(invoke(content, service(), conversion_id, ticket), media_type="application/octet-stream",
                    headers={"Cache-Control": "no-store"})
