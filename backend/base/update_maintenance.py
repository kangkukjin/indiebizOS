"""Source-update admission. A failed update stays closed until explicitly resumed."""
import json
import os
from pathlib import Path


def maintenance_path(base):
    return Path(base) / "data/runtime/update-maintenance.json"


def check_start(base, env=None):
    path = maintenance_path(base)
    if not path.exists():
        return
    state = json.loads(path.read_text(encoding="utf-8"))
    env = os.environ if env is None else env
    if (state.get("phase") == "starting" and state.get("token")
            and env.get("INDIEBIZ_UPDATE_TOKEN") == state["token"]):
        return
    raise ValueError("Source update in progress; resume its existing plan before starting the app")
