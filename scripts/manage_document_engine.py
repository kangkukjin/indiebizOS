#!/usr/bin/env python3
"""Install/start the owner's local ONLYOFFICE container; never prints secrets.
Requires Docker (macOS: Colima profile indiebiz-office). No host files are mounted.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINE_HOME = ROOT / "data/document_workspace"
IMAGE = "onlyoffice/documentserver:9.3.1"


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    docker = ["docker", "--context", "colima-indiebiz-office"] if sys.platform == "darwin" else ["docker"]
    if action == "status":
        subprocess.run(docker + ["ps", "-a", "--filter", "name=indiebiz-office", "--format", "{{.Names}} {{.Status}}"], check=True)
        return
    if action == "stop":
        subprocess.run(docker + ["stop", "indiebiz-office"], check=True)
        return
    if action != "start":
        raise SystemExit("usage: manage_document_engine.py start|stop|status")
    if sys.platform == "darwin":
        ready = subprocess.run(docker + ["info"], capture_output=True, timeout=15)
        if ready.returncode:
            subprocess.run(["colima", "start", "indiebiz-office", "--cpus", "4", "--memory", "6",
                            "--disk", "50", "--vm-type", "vz", "--mount", "none",
                            "--activate=false", "--ssh-config=false"], check=True, timeout=180)
    ENGINE_HOME.mkdir(parents=True, exist_ok=True)
    config_path = ENGINE_HOME / "engine.json"
    if not config_path.exists():
        cfg = {"url": "http://127.0.0.1:8093", "callback_origin": "http://192.168.5.2:8765" if sys.platform == "darwin" else "http://host.docker.internal:8765", "secret": secrets.token_urlsafe(48), "image": IMAGE}
        fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as file:
            json.dump(cfg, file)
    cfg = json.loads(config_path.read_text())
    exists = subprocess.run(docker + ["container", "inspect", "indiebiz-office"], capture_output=True).returncode == 0
    if exists:
        subprocess.run(docker + ["start", "indiebiz-office"], check=True)
        return
    env = dict(os.environ, JWT_SECRET=cfg["secret"])
    subprocess.run(docker + ["run", "-d", "--name", "indiebiz-office", "--restart", "unless-stopped",
        "-p", "127.0.0.1:8093:80", "--shm-size", "1g", "--add-host", "host.docker.internal:host-gateway",
        "-e", "JWT_ENABLED=true", "-e", "JWT_SECRET", "-e", "ALLOW_PRIVATE_IP_ADDRESS=true",
        "-v", "indiebiz-office-data:/var/www/onlyoffice/Data", cfg["image"]], env=env, check=True)


if __name__ == "__main__":
    main()
