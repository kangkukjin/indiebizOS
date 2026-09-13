"""가이드 파일 표면 관문 — 목록은 폴더가 정본, 경로 탈출 차단, 등록·파일 불일치를 숨기지 않는다."""
import boot_paths  # noqa: F401
import pytest

import guide_registry as GR


def test_catalog_is_folder_truth():
    c = GR.guide_catalog()
    files = {p.name for p in GR.GUIDES_DIR.glob("*.md")}
    assert {g["file"] for g in c["guides"]} == files
    assert c["budget_bytes"] == GR.guide_budget_bytes() > 0
    for g in c["guides"]:
        assert {"file", "name", "registered", "bytes", "over_budget", "updated", "clean_uses", "last_review",
                "lifecycle_candidate_since"} <= set(g)
        assert g["over_budget"] == (g["bytes"] > c["budget_bytes"])
    # 등록됐지만 파일이 없는 것은 목록이 아니라 missing_files 로 드러난다
    assert all(m["file"] not in files for m in c["missing_files"])


@pytest.mark.parametrize("bad", ["../lifecycle_policy.yaml", "../../backend/api.py", "", "/etc/passwd"])
def test_resolve_guide_blocks_escape(bad):
    p = GR.resolve_guide(bad)
    assert p is None or (p.parent == GR.GUIDES_DIR and p.suffix == ".md")


def test_resolve_guide_accepts_stem_or_filename():
    assert GR.resolve_guide("photo") == GR.GUIDES_DIR / "photo.md"
    assert GR.resolve_guide("photo.md") == GR.GUIDES_DIR / "photo.md"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__]))
