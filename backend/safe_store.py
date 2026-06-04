"""안전한 JSON 단일소스 저장 유틸.

데이터 유실 안티패턴 방지(2026-06 캘린더 생일 유실 사고에서 도출):
  "로드 실패 → 빈 기본값 반환 → 다음 save로 통째 덮어쓰기 → 사용자 데이터 영구 유실"

- safe_load_json: 파싱 실패 시 손상본을 .corrupt.<ts> 로 백업하고 default 반환
  (빈 기본값으로 조용히 덮어쓰기 전에 원본을 보존 — 복구 가능하게).
- safe_save_json: 임시파일+os.replace 원자적 쓰기 + 직전 파일 .bak 보존(1단계 롤백).
"""
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


def safe_load_json(path, default: Any) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        try:
            bak = p.with_name(p.stem + f".corrupt.{datetime.now():%Y%m%d_%H%M%S}" + p.suffix)
            shutil.copy(p, bak)
            print(f"[safe_store] {p.name} 파싱 실패: {e} — 손상본 백업: {bak} (빈 기본값으로 덮어쓰기 방지)")
        except Exception:
            print(f"[safe_store] {p.name} 파싱 실패: {e}")
        return default


def safe_save_json(path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # 직전 파일을 .bak으로 보존 (로직 오류로 인한 유실 대비 1단계 롤백)
    if p.exists():
        try:
            shutil.copy(p, p.with_suffix(p.suffix + ".bak"))
        except Exception:
            pass
    # 임시파일에 쓰고 원자적 교체 (부분 쓰기 손상 방지)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
