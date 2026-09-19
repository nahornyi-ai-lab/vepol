"""Serve the real Face app against owned, isolated state; never start a runtime."""
from __future__ import annotations

import json
import pathlib
import socket
import sys

app_root, fixture_root = map(pathlib.Path, sys.argv[1:3])
sys.path.insert(0, str(app_root))

import uvicorn
from vepol_face.app import create_app
from vepol_face.config import Config

hub = fixture_root / "hub"
for slug in ("alpha", "beta", "gamma", "delta"):
    (hub / "projects" / slug).mkdir(parents=True, exist_ok=True)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
app = create_app(hub=hub, config=Config(port=port), store_dir=fixture_root / "state")
print(json.dumps({"port": port, "token": app.state.auth.token}), flush=True)
uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False,
                             log_level="error")).run(sockets=[sock])
