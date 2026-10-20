"""Bounded offline diagnosis of reading the captured execution envelope as JSON."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import faulthandler
import json
import time
from ibl_v2_types import infer

if __name__ == '__main__':
    if sys.argv[1] == '--synthetic':
        value = ["scalar", 1]
        for _ in range(int(sys.argv[2])):
            value = ["record", [["key", value]]]
    else:
        value = json.loads(Path(sys.argv[1]).read_text())
    faulthandler.dump_traceback_later(5, exit=True)
    started = time.monotonic()
    result = infer(value)
    faulthandler.cancel_dump_traceback_later()
    print({'seconds': time.monotonic() - started, 'kind': result.kind})
