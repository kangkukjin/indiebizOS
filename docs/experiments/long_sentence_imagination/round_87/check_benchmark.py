"""Compile the original triad program without executing any device action."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import hashlib
import json
import time

from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_store import installed_definitions


def run():
    source = Path(__file__).with_name("base_v0.ibl").read_text()
    inputs = {
        "tv1": "fixture-pc", "mac26": "fixture-mac",
        "s0": "fixture-phone0", "s1": "fixture-phone1", "yena": "fixture-phone2",
        "url": "https://example.com", "window": 1, "out": "/tmp/l87-report.json",
    }
    registry = load_registry(str(ROOT))
    definitions = installed_definitions()
    started = time.monotonic()
    plan = compile_program(source, registry, inputs=inputs, definitions=definitions)
    seconds = time.monotonic() - started
    report = plan.report()
    semantic_report = {k: v for k, v in report.items()
                       if k not in {"plan_hash", "dependencies"}}
    encoded = json.dumps(semantic_report, ensure_ascii=False, sort_keys=True).encode()
    return {
        "mode": "offline-check-only", "device_calls": 0, "model_calls": 0,
        "seconds": seconds, "issues": len(plan.issues), "guards": len(plan.guards),
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "semantic_report_sha256": hashlib.sha256(encoded).hexdigest(),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
