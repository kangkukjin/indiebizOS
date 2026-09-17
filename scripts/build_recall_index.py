#!/usr/bin/env python3
"""트리 기억 회상 색인을 미리 만든다 — 심층기억 DB 전부 + 세계의 기억(읽기 전용) → data/recall_index/ (git 밖).

평소에는 필요 없다: 회상이 변경분을 그 자리에서(12건까지) 또는 백그라운드로 동기화한다. 심층기억의 `memories_vec`(중복 판정·증류 조회용)도 인코더 표식이 어긋나면 여기서 재임베딩된다. 이 스크립트는
인코더·텍스트 규칙을 바꾼 뒤나 새 몸에서 첫 턴부터 의미 채널을 쓰고 싶을 때 돌린다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import glob  # noqa: E402

sys.path.insert(0, str(ROOT / "data/packages/installed/tools/memory"))
import tree_recall  # noqa: E402
from recall_store import DeepMemoryStore  # noqa: E402


def main():
    paths = [str(ROOT / "data/system_ai_state/memory_system_ai.db")] + sorted(glob.glob(str(ROOT / "projects/*/memory_*.db")))
    built = 0
    for p in paths:
        try:
            store = DeepMemoryStore(p)
            if not store.items():
                continue
            import memory_db
            stamped = memory_db._ensure_vec_current(p)      # 중복 판정·증류 조회용 벡터(memories_vec)도 같은 인코더로
            tree_recall.build_now(store)
            built += 1
            print(f"✓ {Path(p).relative_to(ROOT)} — 항목 {len(store.items())} · 가지 {len(store.branches())}"
                  + ("" if stamped else " · ✗ memories_vec 표식 실패"))
        except Exception as e:  # noqa: BLE001
            print(f"✗ {p}: {e}")
    try:
        from world_recall_store import WorldStore
        world = WorldStore(ROOT)
        tree_recall.build_now(world)
        built += 1
        print(f"✓ 세계의 기억 — 어휘 {len(world.items())} · 가지 {len(world.branches())}"
              + (f" · 사전에만 있는 경로 {world.unknown_dictionary_paths()}" if world.unknown_dictionary_paths() else ""))
    except Exception as e:  # noqa: BLE001
        print(f"✗ 세계의 기억: {e}")
    print(f"색인 {built}개 → {tree_recall._index_dir()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
