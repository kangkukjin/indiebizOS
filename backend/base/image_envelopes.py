"""Image transport contracts shared by preview, native providers and MCP.

Only explicit image fields are harvested; arbitrary strings and data URLs remain
data. Callers own copies before extraction so stored evidence stays untouched.
"""
import json

MAX_TOOL_IMAGES = 4


def pluck_images(node, found, depth=0):
    """Remove image bytes from a display tree, retaining metadata in their place."""
    if depth > 16:
        return node
    if isinstance(node, dict):
        env = node.get("image_data")
        if isinstance(env, dict) and isinstance(env.get("b64"), str) and env["b64"]:
            node.pop("image_data")
            found.append(env)
            node["image"] = {k: v for k, v in env.items() if k != "b64"}
        # browser vision's existing public return shape remains compatible.
        if isinstance(node.get("image_base64"), str) and node["image_base64"]:
            found.append({"b64": node.pop("image_base64"),
                          "media_type": node.get("mime_type", "image/jpeg")})
            node["image"] = {"media_type": node.get("mime_type", "image/jpeg"),
                             "file_path": node.get("file_path")}
        imgs = node.get("images")
        if isinstance(imgs, list):
            metas = []
            for item in imgs:
                if isinstance(item, dict) and isinstance(item.get("base64"), str) and item["base64"]:
                    found.append({"b64": item["base64"],
                                  "media_type": item.get("media_type", "image/png")})
                    metas.append({k: v for k, v in item.items() if k != "base64"})
                else:
                    metas.append(item)
            node["images"] = metas
        for key in list(node):
            node[key] = pluck_images(node[key], found, depth + 1)
    elif isinstance(node, list):
        return [pluck_images(v, found, depth + 1) for v in node]
    elif isinstance(node, str) and any(key in node for key in ("image_data", "image_base64", "base64")):
        try:
            inner = json.loads(node)
        except (ValueError, TypeError):
            return node
        before = len(found)
        inner = pluck_images(inner, found, depth + 1)
        if len(found) > before:
            return json.dumps(inner, ensure_ascii=False)
    return node


def harvest_images(raw):
    """Return (JSON text without image bytes, up to four image attachments)."""
    if not isinstance(raw, str) or not any(k in raw for k in ("image_data", "image_base64", "base64")):
        return raw, []
    try:
        tree = json.loads(raw)
    except (ValueError, TypeError):
        return raw, []
    found = []
    tree = pluck_images(tree, found)
    if not found:
        return raw, []
    if len(found) > MAX_TOOL_IMAGES and isinstance(tree, dict):
        tree["images_omitted"] = len(found) - MAX_TOOL_IMAGES
    return json.dumps(tree, ensure_ascii=False), found[:MAX_TOOL_IMAGES]
