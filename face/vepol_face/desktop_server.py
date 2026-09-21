"""Owned native backend. Authentication enters only through the inherited pipe."""
from __future__ import annotations

import json
import pathlib
import socket
import sys

import uvicorn

from .app import create_app
from .config import Config
from .server import port_in_use


def main():
    boot = json.loads(sys.stdin.readline())
    token = boot.pop("token", "")
    if not isinstance(token, str) or len(token) < 40:
        print(json.dumps({"error": "Invalid native bootstrap"}), flush=True)
        return 2
    port = int(boot.get("port", 8781))
    holder = port_in_use("127.0.0.1", port)
    if holder:
        print(json.dumps({"error": f"Порт {port} занят: {holder}. Закрой прежний Vepol Face и нажми «Повторить».", "holder": holder}), flush=True)
        return 3
    # Reserve the socket before opening the state store, preventing two writers.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
        sock.listen(128)
    except OSError:
        print(json.dumps({"error": f"Порт {port} уже занят. Повтори запуск."}), flush=True)
        return 3
    hub = pathlib.Path(boot["hub"]).expanduser() if boot.get("hub") else None
    state = pathlib.Path(boot["state_dir"]).expanduser() if boot.get("state_dir") else None
    app = create_app(hub=hub, config=Config(port=port, desktop=True), store_dir=state, auth_token=token)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_level="error"))
    app.state.shutdown = lambda: setattr(server, "should_exit", True)
    print(json.dumps({"ready": True, "port": port}), flush=True)
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
