"""warehouse_paths.py — 내 창고(공유창고)의 경로 규칙 한 벌 (2026-10-05, 설치 목록 ⑩).

레벨 0~4 폴더, 휴지통/<레벨>, 경로 감옥(safe_rel), 리트윗 포인터(.url) 해석 — 공개면(portal_warehouse)과 창고 관리
서비스(warehouse_admin)가 같은 규칙을 쓴다(둘 다 여기서 import). base 층: 위를 모른다.
"""
import os
from pathlib import Path

from runtime_utils import WAREHOUSE_DIRNAME, get_base_path

LEVELS = {0: "0", 1: "1", 2: "2", 3: "3", 4: "4"}
TRASH_DIRNAME = "휴지통"


def root() -> Path:
    return Path(get_base_path()) / WAREHOUSE_DIRNAME


def warehouse_dir(level: int) -> Path:
    return root() / LEVELS[int(level)]


def trash_dir(level: int) -> Path:
    return root() / TRASH_DIRNAME / LEVELS[int(level)]


def check_level(level) -> int:
    try:
        lv = int(level)
    except (TypeError, ValueError):
        raise ValueError("레벨은 0~4 정수입니다")
    if lv not in LEVELS:
        raise ValueError("레벨은 0~4 정수입니다")
    return lv


def ensure_dirs() -> None:
    for lv in LEVELS:
        warehouse_dir(lv).mkdir(parents=True, exist_ok=True)


def safe_rel(base: Path, rel: str) -> Path:
    """창고 안 상대경로 → 절대경로. 감옥 밖이면 ValueError (공개면은 400 으로 바꾼다)."""
    p = (base / str(rel or "").lstrip("/")).resolve()
    b = base.resolve()
    if not str(p).startswith(str(b) + os.sep) and p != b:
        raise ValueError("bad path")
    return p


def parse_urlfile(p: Path) -> tuple:
    """.url(InternetShortcut) 파일에서 (대상, 출처 창고). 실패면 ("", "")."""
    target, warehouse = "", ""
    try:
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            up = line.upper()
            if up.startswith("URL="):
                t = line[4:].strip()
                if t.startswith("http://") or t.startswith("https://"):
                    target = t
            elif up.startswith("WAREHOUSEURL="):
                w = line[len("WarehouseURL="):].strip()
                if w.startswith("http://") or w.startswith("https://"):
                    warehouse = w
    except Exception:
        pass
    return (target, warehouse) if target else ("", "")
