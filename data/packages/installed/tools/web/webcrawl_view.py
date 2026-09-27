"""Explicit content selection and bounded image attachments from saved HTML snapshots."""
import base64
from io import BytesIO

import requests
from bs4 import BeautifulSoup
from PIL import Image

from common.pkg_utils import load_sibling
from image_envelopes import MAX_TOOL_IMAGES

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000


def validate(selector, include_images, image_offset, image_limit, op):
    if selector is not None and (not isinstance(selector, str) or not selector.strip()):
        return "selector는 비어 있지 않은 CSS 선택자여야 합니다."
    if not isinstance(include_images, bool):
        return "include_images는 true/false여야 합니다."
    if type(image_offset) is not int or image_offset < 0:
        return "image_offset은 0 이상의 정수여야 합니다."
    if type(image_limit) is not int or not 1 <= image_limit <= MAX_TOOL_IMAGES:
        return f"image_limit은 1~{MAX_TOOL_IMAGES} 정수여야 합니다."
    if op != "content" and (selector is not None or include_images or image_offset):
        return "selector/include_images/image_offset은 op:content에서 사용합니다."
    if image_offset and not include_images:
        return "image_offset을 사용하려면 include_images:true가 필요합니다."
    return None


def image_attachment(url, source_url):
    """Read a bounded raster image without navigating the user's current tab."""
    with requests.get(url, headers={"Referer": source_url}, stream=True, timeout=15) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(64 * 1024):
            data.extend(chunk)
            if len(data) > MAX_IMAGE_BYTES:
                raise ValueError("이미지 전송 한도 8MiB 초과")
    with Image.open(BytesIO(data)) as picture:
        if picture.width * picture.height > MAX_IMAGE_PIXELS:
            raise ValueError("이미지 해상도 한도 2000만 픽셀 초과")
        original_size = [picture.width, picture.height]
        picture.load()
        picture.thumbnail((1600, 1600))
        output = BytesIO()
        picture.convert("RGB").save(output, format="JPEG", quality=85)
        return {"b64": base64.b64encode(output.getvalue()).decode("ascii"),
                "media_type": "image/jpeg", "url": url, "source_url": source_url,
                "original_size": original_size, "display_size": list(picture.size)}


def project(result, *, selector, include_images, image_offset, image_limit, parse_html):
    if not result.get("success"):
        return result
    structure = result.get("_page_structure") or {}
    documents = structure.get("documents") or []
    if not documents:
        return {"success": False, "items": [], "reason": "structure_unavailable",
                "error": "이 스냅샷에는 선택할 HTML 구조가 없습니다. PDF는 기존 본문 읽기를 사용하세요.",
                "source_ref": result.get("source_ref")}
    helpers = load_sibling(__file__, "webcrawl_structure")
    store = load_sibling(__file__, "webcrawl_store")
    paragraphs, images, seen = [], [], set()
    matched = 0
    for document in documents:
        soup = BeautifulSoup(document["html"], "html.parser")
        base_tag = soup.find("base", href=True)
        base = helpers.http_url(base_tag["href"], document["url"]) if base_tag else document["url"]
        try:
            nodes = soup.select(selector) if selector else [
                soup.find("article") or soup.find("main") or soup.find(attrs={"role": "main"})
                or soup.find("body") or soup]
        except Exception as exc:
            return {"success": False, "items": [], "error": f"CSS 선택자 오류: {exc}"}
        chosen = {id(node) for node in nodes}
        nodes = [node for node in nodes if not any(id(parent) in chosen for parent in node.parents)]
        matched += len(nodes)
        for node in nodes:
            _, text = parse_html(str(node), document["url"])
            rows = store.text_to_blocks("", text) if text else []
            for row in rows:
                row.update(url=document["url"], paragraph_index=len(paragraphs) + 1)
                paragraphs.append(row)
            # UI/hidden markup isn't part of the selected reading surface.
            fragment = BeautifulSoup(str(node), "html.parser")
            for ui in fragment.select("nav,footer,aside,script,style,noscript,[hidden],[aria-hidden=true]"):
                ui.decompose()
            for img in fragment.find_all("img"):
                target = helpers.http_url(img.get("data-src") or img.get("src"), base or document["url"])
                if not target or target in seen:
                    continue
                seen.add(target)
                images.append({"url": target, "alt": img.get("alt", ""),
                               "source_url": document["url"], "index": len(images)})
    if not matched:
        return {"success": False, "items": [], "reason": "selector_no_match",
                "error": "selector에 맞는 영역이 없습니다. 선택자를 확인하세요.",
                "source_ref": result.get("source_ref")}
    out = {k: v for k, v in result.items() if k not in ("_page_structure", "_structure_only")}
    out.update(items=paragraphs, text="\n\n".join(row["text"] for row in paragraphs))
    out["length"] = len(out["text"])
    out["selection"] = {"selector": selector, "matched_regions": matched,
                        "scope": "selected_regions" if selector else "semantic_body"}
    if include_images:
        selected = images[image_offset:image_offset + image_limit]
        out["image_items"] = selected
        out["image_count"] = len(images)
        out["next_image_offset"] = (image_offset + len(selected)
                                     if image_offset + len(selected) < len(images) else None)
        if image_offset or len(selected) < len(images):
            out.setdefault("truncations", []).append({"scope": "selection", "source": "crawl.images",
                "unit": "images", "total": len(images), "retained": len(selected), "offset": image_offset})
        errors = []
        for row in selected:
            try:
                row["image_data"] = {**image_attachment(row["url"], row["source_url"]), "alt": row["alt"]}
            except Exception as exc:
                row["error"] = str(exc)
                errors.append({"url": row["url"], "error": str(exc)})
        if errors:
            out.update(success=False, error="일부 이미지 첨부를 읽지 못했습니다.", errors=errors)
    frame_errors = [e for e in structure.get("errors", [])
                    if not str(e.get("source", "")).startswith("jsonld[")]
    if frame_errors:
        out.update(success=False, error="일부 HTML 구조를 수집하지 못했습니다.",
                   structure_errors=frame_errors)
    return out
