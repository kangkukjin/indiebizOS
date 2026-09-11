"""이미 떠 있는 이전 uvicorn 마스터의 1회 인계 영수증. 새 독립 데몬은 만들지 않는다."""
import os
import secrets
from pathlib import Path

import psutil
from restart_process import identity
from restart_protocol import atomic_json, code_manifest, control_dir


def register(base, code_root, parent_pid):
    master = psutil.Process(parent_pid)
    nonce, token = "legacy-" + secrets.token_hex(12), secrets.token_hex(32)
    digest = code_manifest(code_root)["digest"]
    os.environ.update(INDIEBIZ_RUNTIME_GENERATION=nonce, INDIEBIZ_RUNTIME_CONTROL=token,
                      INDIEBIZ_RUNTIME_DIGEST=digest)
    keeper = master.parent()
    keeper_ident = None
    if keeper and any(str(Path(code_root) / "scripts/backend_keeper.sh") == arg for arg in keeper.cmdline()):
        keeper_ident = identity(keeper.pid)
    receipt = {"generation": nonce, "code_digest": digest, "control_token": token,
               "worker": identity(parent_pid), "serving_worker": identity(os.getpid()),
               "legacy_keeper": keeper_ident, "legacy": True}
    atomic_json(control_dir(base) / "legacy.json", receipt)
    return nonce
