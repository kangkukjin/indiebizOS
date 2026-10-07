"""Independent byte-level oracle; never trusts product success or report counts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(source, output, teams):
    source, output = Path(source), Path(output)
    expected = {}
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        if rel.parts[0] not in teams and rel.as_posix() != "안내.txt":
            continue
        if "internal" in rel.parts or path.suffix == ".tmp":
            continue
        data = path.read_bytes()
        expected[rel.as_posix()] = {"size": len(data), "sha256": digest(data)}
    checks = []

    def add(name, passed, details=None):
        checks.append({"name": name, "ok": bool(passed), "details": details})

    add("nonempty_expected", bool(expected), len(expected))
    archive = output / "delivery.zip"
    add("archive_exists", archive.is_file())
    if archive.is_file():
        with zipfile.ZipFile(archive) as z:
            members = [i for i in z.infolist() if not i.is_dir()]
            names = [i.filename for i in members]
            dup = {name: n for name, n in Counter(names).items() if n > 1}
            add("unique_members", not dup, dup)
            add("exact_archive_paths", set(names) == set(expected),
                {"missing": sorted(set(expected) - set(names)), "extra": sorted(set(names) - set(expected))})
            bad = [i.filename for i in members if i.filename in expected and
                   digest(z.read(i)) != expected[i.filename]["sha256"]]
            add("archive_bytes", len(names) == len(expected) and not bad, bad)
    restored = {p.relative_to(output / "restored").as_posix(): p
                for p in (output / "restored").rglob("*") if p.is_file()}
    add("exact_restored_paths", set(restored) == set(expected), sorted(set(expected) - set(restored)))
    bad = [name for name, value in expected.items() if name not in restored or
           digest(restored[name].read_bytes()) != value["sha256"]]
    add("restored_bytes", bool(restored) and not bad, bad)
    manifest_path = output / "manifest.json"
    add("manifest_exists", manifest_path.is_file())
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        if isinstance(manifest, dict):
            manifest = manifest.get("items", manifest.get("files", []))
        got = {r.get("path"): r.get("size") for r in manifest}
        add("manifest_unique_exact", len(manifest) == len(expected) and
            got == {k: v["size"] for k, v in expected.items()}, len(manifest))
    rp = output / "report.json"
    add("report_exists", rp.is_file())
    report = json.loads(rp.read_text()) if rp.is_file() else None
    if report is not None:
        add("report_completion_is_honest", report.get("complete") is all(c["ok"] for c in checks),
            report.get("complete"))
        counts = report.get("counts", report)
        add("report_expected_count", counts.get("expected_count", counts.get("planned_files")) == len(expected))
        if archive.is_file():
            add("report_archive_count", counts.get("archive_count", counts.get("zip_file_entries")) == len(names))
        add("report_restored_count", counts.get("restored_count", counts.get("restored_files")) == len(restored))
    return {"expected_count": len(expected), "checks": checks,
            "artifact_ok": all(c["ok"] for c in checks),
            "report": report}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("output")
    p.add_argument("--teams", nargs="+", default=["사진", "설치", "영상"])
    p.add_argument("--save")
    a = p.parse_args()
    result = inspect(a.source, a.output, a.teams)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if a.save:
        Path(a.save).write_text(text)
    print(text)
