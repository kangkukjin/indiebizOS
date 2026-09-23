"""Explicit document adapter shared by owner and member file boundaries.

Text and blocks are stable fields; data retains the entire reader payload,
including tables, sheets, images, ranges and extraction metadata.
"""
from ibl_v2_ir import Fault


def document_value(raw):
    text = raw.get("text", raw.get("message", ""))
    blocks = raw.get("blocks")
    if blocks is None:
        # blocks:true is part of this adapter's declared request. Spreadsheet
        # items are rows, so never relabel them as document blocks.
        items = raw.get("items", [])
        blocks = items if items and all(isinstance(v, dict) and "type" in v for v in items) else []
    if not isinstance(text, str) or not isinstance(blocks, list):
        raise Fault("DOCUMENT_SHAPE", "문서 읽기의 text/blocks 계약이 맞지 않습니다.", kind="protocol")
    if not all(isinstance(v, dict) for v in blocks):
        raise Fault("DOCUMENT_SHAPE", "문서 블록은 Record 목록이어야 합니다.", kind="protocol")
    return {"text": text, "blocks": blocks, "data": raw}
