#!/usr/bin/env python3
"""Reviewed native replacements. Builds source, never executes user workflows."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: E402,F401
import json



def candidates():
    from ibl_v2_store import definition_name
    paths = sorted((Path(__file__).resolve().parents[1] / 'data/idioms').glob('retirement_*.ibl'))
    return {definition_name(p.read_text()): p.read_text() for p in paths}


if __name__ == '__main__':
    from function_library import compile_current, definitions
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    sources = candidates()
    library = definitions()
    library.update(sources)
    registry = load_registry()
    failures = {}
    for name, source in sources.items():
        try:
            plan = compile_program(source, registry, definitions=library)
            if plan.issues:
                failures[name] = plan.issues
        except Exception as exc:
            failures[name] = str(exc)
    print(json.dumps(failures, ensure_ascii=False, indent=2))
    raise SystemExit(bool(failures))
